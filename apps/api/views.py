"""API views. Shapes and status codes are docs/api-contract.md, Stage 2 table.

Authentication is the session cookie (D-21); ``IsAuthenticated`` is the global
default, so only the views that set ``AllowAny`` are reachable anonymously.
Routes that need more than a session add ``HasRolePermission`` (FR-06).
"""

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.audit import log_role_change
from apps.accounts.models import Permission, Role
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    LOCKOUT_DURATION,
    LOCKOUT_NOTICE_CEILING,
    LOCKOUT_THRESHOLD,
    MANAGE_ROLES_PERMISSION,
    ROLE_NAMES,
)

from .permissions import HasRolePermission
from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    RoleChangeSerializer,
    RoleSerializer,
    UserSerializer,
)

User = get_user_model()

# One message for an unknown address and a wrong password (D-02): login must not
# disclose whether an address is registered.
INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."
# FR-01 names the duplicate case explicitly, so this response may say so.
EMAIL_ALREADY_REGISTERED_MESSAGE = "This email address is already registered."
# FR-02 Responses: "403 forbidden if account is locked" (D-25). The wording is the
# proposal's own, from its handleLoginAttempt pseudocode. ACCOUNT_LOCKED_CODE is the
# machine-readable flag for FR-02's front-end clause, "where the account is locked
# and the submitted password was correct, a distinct message is shown": the client
# branches on the code and never has to match on prose.
# FR-03 defines an administrator release route; it is out of the M6 gate and
# unbuilt, so the notice must not promise one (D-26). Waiting is the only remedy.
ACCOUNT_LOCKED_MESSAGE = (
    "This account is temporarily locked after repeated failed sign-ins. "
    "Please try again later."
)
ACCOUNT_LOCKED_CODE = "account_locked"
# FR-04 Front-End: "a brief confirmation 'You've been logged out'".
LOGGED_OUT_MESSAGE = "You have been logged out."
# FR-05 Validation: "a user cannot remove their own administrator role, preventing
# accidental lockout of the last administrator."
SELF_DEMOTION_MESSAGE = "You cannot remove your own Administrator role."
# The same clause's purpose, "preventing accidental lockout of the last
# administrator", when the last one is somebody else (D-26).
LAST_ADMINISTRATOR_MESSAGE = (
    "This is the last Administrator. Promote another user before changing this role."
)
# FR-05 Responses: "404 Not Found if user/role doesn't exist". The user half is
# get_object_or_404's own body; this is the role half.
UNKNOWN_ROLE_MESSAGE = "No role with that role_id exists."

CanManageRoles = HasRolePermission.for_code(MANAGE_ROLES_PERMISSION)


def not_found(request, exception=None):
    """handler404: JSON like every other error, never Django's HTML page."""
    return JsonResponse({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


# --- FR-01 registration --------------------------------------------------------------


class RegisterView(APIView):
    permission_classes = [AllowAny]  # one of the two opt-outs (D-21)
    # Anonymous and unthrottled, this endpoint is an unlimited "is this address
    # registered?" oracle, and the answer feeds the lockout below (D-26).
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400 in DRF's shape
        data = serializer.validated_data
        # The serializer lower-cased the address and User.save() stores every
        # address lower-cased, so an exact match is a case-insensitive one (D-02).
        if User.objects.filter(email=data["email"]).exists():
            return Response(
                {"detail": EMAIL_ALREADY_REGISTERED_MESSAGE}, status=status.HTTP_409_CONFLICT
            )
        try:
            with transaction.atomic():
                # The manager assigns the Employee role (docs/schema-v1.md Users.role_id).
                user = User.objects.create_user(data["email"], data["password"], name=data["name"])
        except IntegrityError:
            # Two registrations of the same address raced past the check above.
            return Response(
                {"detail": EMAIL_ALREADY_REGISTERED_MESSAGE}, status=status.HTTP_409_CONFLICT
            )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


# --- FR-02 login ---------------------------------------------------------------------


def _is_locked(user) -> bool:
    """FR-02: the lock is evaluated before the password result is used, so that no
    session is issued for a locked account whatever credential was submitted."""
    return user is not None and user.locked_until is not None and user.locked_until > timezone.now()


def _record_locked_attempt(email: str) -> int:
    """Count a failed attempt made *during* an active lock, and return the new total.

    The window is deliberately not extended: "locks the account for 15 minutes" stays
    literally true rather than becoming indefinite under a sustained attack (D-25).
    But the counter does move, which D-25 originally said it would not. Leaving it
    still meant the lock withheld only the session cookie and not the *verification
    oracle*: an attacker could guess without limit for the life of the window, each
    guess answered 403 or 401 according to whether it was right. Counting is what
    lets the caller stop announcing the answer (D-26).
    """
    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(email=email)
        except User.DoesNotExist:  # pragma: no cover - the caller found a locked account
            return 0
        user.failed_attempts += 1
        user.save(update_fields=["failed_attempts"])
        return user.failed_attempts


def _record_failed_attempt(email: str) -> None:
    """FR-02 Business Logic: "Failed attempts increment a counter; five consecutive
    failures lock the account for 15 minutes." Reached only for an account that is
    not currently locked, so an attempt made during a lockout window neither extends
    the window nor moves the counter. An expired window resets the counter first: it
    counts *consecutive* failures, and without the reset the single next failure
    after a lock expired would re-lock the account on one attempt rather than five."""
    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(email=email)
        except User.DoesNotExist:
            return
        if user.locked_until is not None:
            # A live lock never reaches here, so this window has expired.
            user.failed_attempts = 0
            user.locked_until = None
        user.failed_attempts += 1
        if user.failed_attempts >= LOCKOUT_THRESHOLD:
            user.locked_until = timezone.now() + LOCKOUT_DURATION
        user.save(update_fields=["failed_attempts", "locked_until"])


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]  # one of the two opt-outs (D-21)
    # Five requests lock any account, so without this anyone could hold every
    # account in the organisation locked indefinitely (D-26).
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        # 400: a missing field, or an address that is not an address. FR-02
        # Validation rules put the format check "before database lookup", and the
        # login pseudocode returns 400 for it explicitly (D-25).
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        account = User.objects.filter(email=email).first()
        # The password is verified even for a locked account, because its result
        # selects the response and can never grant access. Django's ModelBackend runs
        # the hasher even when the address is unknown, so the failing cases take the
        # same time as far as practical.
        user = authenticate(request, username=email, password=password)
        if _is_locked(account):
            # The lock is announced ONLY where the password also matched. The
            # proposal's handleLoginAttempt() pseudocode branches exactly here and
            # says why: "Confirming a lock to anyone who merely knows the email
            # address would convert a protective measure into an account-enumeration
            # tool." So a wrong password against a locked account is the ordinary
            # 401, indistinguishable from a wrong password against any other
            # address. FR-02's unqualified "403 if account is locked" is the summary;
            # the pseudocode and FR-03's messaging clause are the detail (D-25).
            #
            # Announcing it for the whole window, however, leaves the lock withholding
            # only the session and not the answer: guesses are unlimited during a
            # lock, and each 403 or 401 says whether that guess was right. So the
            # attempt is counted, and past LOCKOUT_NOTICE_CEILING the answer stops
            # being given at all (D-26). The password is still verified on every path
            # so the timing does not separate these cases from an unknown address.
            attempts = _record_locked_attempt(email)
            if user is None or attempts > LOCKOUT_NOTICE_CEILING:
                return Response(
                    {"detail": INVALID_CREDENTIALS_MESSAGE}, status=status.HTTP_401_UNAUTHORIZED
                )
            return Response(
                {"detail": ACCOUNT_LOCKED_MESSAGE, "code": ACCOUNT_LOCKED_CODE},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user is None:
            _record_failed_attempt(email)
            return Response(
                {"detail": INVALID_CREDENTIALS_MESSAGE}, status=status.HTTP_401_UNAUTHORIZED
            )
        # Cycles the session key and, through the user_logged_in signal, sets
        # last_login (stored as last_login_at). The CSRF token is rotated too.
        django_login(request, user)
        if user.failed_attempts or user.locked_until:
            # Both, not just the counter. A success that left locked_until standing
            # would refuse the user's next login for the rest of the window, which is
            # the trap D-24 recorded and D-25 closes.
            user.failed_attempts = 0
            user.locked_until = None
            user.save(update_fields=["failed_attempts", "locked_until"])
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


# --- FR-04 logout ----------------------------------------------------------------------


class LogoutView(APIView):
    def post(self, request):
        # Server-side invalidation (D-10): the django_session row is deleted, so a
        # client that keeps the cookie value holds nothing. flush() is what
        # django_logout() does too; it is called first so the row is gone before
        # the user_logged_out signal fires.
        request.session.flush()
        django_logout(request)
        # FR-04 Responses: "200 OK on success" (D-25), with a JSON body like every
        # other response the contract defines.
        return Response({"detail": LOGGED_OUT_MESSAGE}, status=status.HTTP_200_OK)


# --- Current user ----------------------------------------------------------------------


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


# --- FR-05 role management ---------------------------------------------------------------


class RoleListView(APIView):
    """Any session may read the roles and the permission codes each holds."""

    def get(self, request):
        roles = Role.objects.prefetch_related(
            Prefetch("permissions", queryset=Permission.objects.order_by("permission_name"))
        )
        # Listed in ROLE_NAMES order (Employee, then the role that generalises it).
        ordered = sorted(roles, key=lambda role: ROLE_NAMES.index(role.role_name))
        return Response(RoleSerializer(ordered, many=True).data)


class UserListView(APIView):
    permission_classes = [IsAuthenticated, CanManageRoles]

    def get(self, request):
        users = User.objects.select_related("role").order_by("created_at", "pk")
        return Response(UserSerializer(users, many=True).data)


class UserRoleView(APIView):
    permission_classes = [IsAuthenticated, CanManageRoles]

    def patch(self, request, pk):
        serializer = RoleChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400 {"role_id": [...]}
        try:
            # FR-05 Validation: "new_role_id must exist in Roles table"; FR-05
            # Responses: "404 Not Found if user/role doesn't exist" (D-25).
            new_role = Role.objects.get(pk=serializer.validated_data["role_id"])
        except Role.DoesNotExist:
            return Response({"detail": UNKNOWN_ROLE_MESSAGE}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            # Lock the whole administrator set before reading it, not just the target
            # row. Two administrators demoting each other at the same time touch
            # different rows, so a self-only guard lets both commit and leaves zero
            # administrators; manage_roles is held only by that role (D-14), so there
            # is then no way back through the product. Ordered by primary key so
            # concurrent requests take the locks in the same order (D-26).
            administrator_ids = set(
                User.objects.select_for_update()
                .filter(role__role_name=ADMINISTRATOR_ROLE_NAME)
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            user = get_object_or_404(
                User.objects.select_for_update(of=("self",)).select_related("role"), pk=pk
            )
            old_role_name = user.role.role_name
            removes_administrator = (
                old_role_name == ADMINISTRATOR_ROLE_NAME
                and new_role.role_name != ADMINISTRATOR_ROLE_NAME
            )
            if removes_administrator and user.pk == request.user.pk:
                # FR-05 Validation: "a user cannot remove their own administrator
                # role, preventing accidental lockout of the last administrator."
                # 403 is a convention: FR-05 enumerates only 200, 403 and 404, and
                # this is a refusal to act on an authorised request (D-25).
                return Response(
                    {"detail": SELF_DEMOTION_MESSAGE}, status=status.HTTP_403_FORBIDDEN
                )
            if removes_administrator and administrator_ids <= {user.pk}:
                # The same clause's stated purpose, reached by another route.
                return Response(
                    {"detail": LAST_ADMINISTRATOR_MESSAGE}, status=status.HTTP_403_FORBIDDEN
                )
            user.role = new_role
            user.save(update_fields=["role"])
            # FR-05: every role change writes an audit entry, including a no-op
            # one, so the log shows what was asked for as well as what changed.
            log_role_change(
                actor=request.user, target=user, old_role=old_role_name, new_role=new_role.role_name
            )
        return Response(UserSerializer(user).data)
