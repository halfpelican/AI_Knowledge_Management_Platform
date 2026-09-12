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
from rest_framework.views import APIView

from apps.accounts.audit import log_role_change
from apps.accounts.models import Permission, Role
from apps.core.constants import (
    LOCKOUT_DURATION,
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

CanManageRoles = HasRolePermission.for_code(MANAGE_ROLES_PERMISSION)


def not_found(request, exception=None):
    """handler404: JSON like every other error, never Django's HTML page."""
    return JsonResponse({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


# --- FR-01 registration --------------------------------------------------------------


class RegisterView(APIView):
    permission_classes = [AllowAny]  # one of the two opt-outs (D-21)

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


def _record_failed_attempt(email: str) -> None:
    """FR-02 side effect (docs/api-contract.md): count the failure against the account
    and, at the LOCKOUT_THRESHOLDth consecutive one, stamp locked_until. The lock is
    only recorded here; enforcing it is FR-03 (NIT3004) and is not part of Stage 2."""
    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(email=email)
        except User.DoesNotExist:
            return
        user.failed_attempts += 1
        fields = ["failed_attempts"]
        if user.failed_attempts >= LOCKOUT_THRESHOLD:
            user.locked_until = timezone.now() + LOCKOUT_DURATION
            fields.append("locked_until")
        user.save(update_fields=fields)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]  # one of the two opt-outs (D-21)

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400 malformed body
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        # Django's ModelBackend runs the password hasher even when the address is
        # unknown, so the two 401 cases take the same time as far as practical.
        user = authenticate(request, username=email, password=password)
        if user is None:
            _record_failed_attempt(email)
            return Response(
                {"detail": INVALID_CREDENTIALS_MESSAGE}, status=status.HTTP_401_UNAUTHORIZED
            )
        # Cycles the session key and, through the user_logged_in signal, sets
        # last_login (stored as last_login_at). The CSRF token is rotated too.
        django_login(request, user)
        if user.failed_attempts:
            user.failed_attempts = 0
            user.save(update_fields=["failed_attempts"])
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
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        serializer.is_valid(raise_exception=True)  # 400 {"role": [...]}
        new_role = Role.objects.get(role_name=serializer.validated_data["role"])
        with transaction.atomic():
            user = get_object_or_404(
                User.objects.select_for_update(of=("self",)).select_related("role"), pk=pk
            )
            old_role_name = user.role.role_name
            user.role = new_role
            user.save(update_fields=["role"])
            # FR-05: every role change writes an audit entry, including a no-op
            # one, so the log shows what was asked for as well as what changed.
            log_role_change(
                actor=request.user, target=user, old_role=old_role_name, new_role=new_role.role_name
            )
        return Response(UserSerializer(user).data)
