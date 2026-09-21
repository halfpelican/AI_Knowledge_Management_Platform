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
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.audit import log_role_change
from apps.accounts.models import Permission, Role
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    CONTRIBUTE_CONTENT_PERMISSION,
    LOCKOUT_DURATION,
    LOCKOUT_NOTICE_CEILING,
    LOCKOUT_THRESHOLD,
    DOCUMENT_INDEXED,
    MANAGE_ROLES_PERMISSION,
    MAX_UPLOAD_BYTES,
    MINIMUM_CONTENT_LENGTH,
    ROLE_NAMES,
)
from apps.documents.models import Document
from apps.ingestion.chunking import length_in_tokens
from apps.ingestion.documents import ingest_and_index_document, reprocess_document
from apps.ingestion.errors import ExtractionError
from apps.ingestion.extraction import extract_plain_text
from apps.ingestion.meetings import ingest_meeting_transcript
from apps.ingestion.signatures import compute_content_hash, read_file_signature
from apps.meetings.models import Meeting

from .permissions import HasRolePermission
from .serializers import (
    DirectoryEntrySerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
    LoginSerializer,
    MeetingIngestSerializer,
    MeetingListSerializer,
    MeetingSerializer,
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

# FR-08 Responses: "415 Unsupported Media Type for a disallowed format". The four
# accepted formats are named so the message is actionable, and they are the same four
# the client-side rejection names (D-15).
UNSUPPORTED_FORMAT_MESSAGE = (
    "File type not supported. Accepted formats: PDF, DOCX, XLSX, TXT."
)
NO_FILE_SUBMITTED_MESSAGE = "No file was submitted."
# FR-08 Responses: "413 Payload Too Large beyond the size limit".
FILE_TOO_LARGE_MESSAGE = "File exceeds the maximum permitted size of 50 MB."
# FR-08 Responses: "409 Duplicate document exists for duplicate documents in the
# database". Compared by content, not by filename (section 7.2).
DUPLICATE_DOCUMENT_MESSAGE = "A duplicate document already exists."
# docs/decisions.md D-29.
SELF_EXCLUDING_VISIBILITY_MESSAGE = (
    "You cannot upload content into a scope your own role cannot read."
)
# FR-09 Validation: "transcript content must exceed a minimum length, since a
# near-empty transcript produces unusable AI output."
INSUFFICIENT_TRANSCRIPT_MESSAGE = (
    "The transcript is too short to index. Paste the full transcript and try again."
)
# An uploaded transcript file of an accepted format that yields no readable text.
NO_TEXT_IN_TRANSCRIPT_MESSAGE = "No readable text could be extracted from that file."
# FR-09 associates a transcript with its attendees; MeetingAttendees is a
# participation record for FR-20 and never an access control (D-16).
UNKNOWN_ATTENDEE_MESSAGE = "One or more of those attendees is not a registered user."
# D-32: FR-08's retry re-runs ingestion on the stored original. Re-indexing a
# document that is already indexed is FR-15's business, not a retry's.
ALREADY_INDEXED_MESSAGE = "This document is already indexed."
NO_STORED_ORIGINAL_MESSAGE = "This document has no stored original to reprocess."

CanManageRoles = HasRolePermission.for_code(MANAGE_ROLES_PERMISSION)
CanContributeContent = HasRolePermission.for_code(CONTRIBUTE_CONTENT_PERMISSION)


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


class UserDirectoryView(APIView):
    """``GET /api/users/directory`` — the people an FR-09 transcript can name.

    Any signed-in session. FR-09 gives attendee association to any user, and the
    gate is demonstrated from both roles, but the only user listing was FR-05's
    ``GET /api/users``, which is Administrator-only: an Employee could not populate
    an attendee picker, so the clause was unreachable for them (Stage 3 audit,
    finding 4). FR-05's list is untouched — it carries roles and drives role
    management, and relaxing it would have handed every Employee the role of every
    colleague to satisfy a requirement that only needs their name.

    What this does disclose, stated rather than glossed: every signed-in user can
    read the name and address of every other registered user. That is what a staff
    directory is, and naming an attendee is not possible without it. No role, no
    timestamps, no account state (D-34).
    """

    def get(self, request):
        people = User.objects.order_by("name", "pk")
        return Response(DirectoryEntrySerializer(people, many=True).data)


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


# --- FR-08 document upload -----------------------------------------------------------


class DocumentsView(APIView):
    """``/api/documents`` — FR-08 upload (POST) and the repository list (GET).

    **POST.** The rejection order is the proposal's section 7.2 ``validateUpload()``,
    not a serializer's field order, because 7.2 fixes it and says why the permission
    check comes first: "it is the cheapest rejection, and the user's role may have
    changed during a transfer of up to 50 MB". ``CanContributeContent`` is returned
    by ``get_permissions()`` for POST, so DRF runs it in ``initial()`` before this
    method is entered and before the body is parsed at all (D-30). Processing is
    synchronous, as FR-08 states, with the interface displaying progress.

    **GET.** The list FR-08's front end reads the "Indexed" status from, scoped by
    ``visible_to_roles`` from the first day it exists. FR-11 is Stage 4 work and this
    is not that filter, but a list disclosing documents outside the caller's scope
    would be a leak to remove later rather than a feature, and CLAUDE.md invariant 1
    is explicit that the existence of out-of-scope material must not be disclosed
    "by a result count, a total, or an error message". FR-15's filtered browsing
    builds on this in Stage 5.
    """

    permission_classes = [IsAuthenticated]
    # The one endpoint that accepts something other than JSON. The global JSON-only
    # default (D-24) exists to stop a cross-site HTML form reaching an *anonymous*
    # endpoint; it is not what protects this one. This route requires a session, and
    # DRF enforces CSRF as soon as its session authenticator resolves a user, so a
    # cross-site multipart POST here is rejected for want of the token.
    parser_classes = [MultiPartParser]

    def get_permissions(self):
        # Contributing is not reading: FR-08's 403 guards the upload, and a session
        # that may read the repository is not thereby entitled to add to it.
        if self.request.method == "POST":
            return [IsAuthenticated(), CanContributeContent()]
        return [IsAuthenticated()]

    def get(self, request):
        documents = (
            Document.objects.select_related("uploaded_by")
            .filter(visible_to_roles__contains=[request.user.role.role_name])
            .order_by("-uploaded_at", "pk")
        )
        return Response(DocumentSerializer(documents, many=True).data)

    def post(self, request):
        # Enforced against the declared length BEFORE request.data is touched, so
        # an oversized body is refused without being parsed or buffered: FR-08 wants
        # the ceiling applied "before the file is written to storage", and reading
        # 50 MB into memory to discover it is 50 MB is the thing to avoid. A client
        # that lies about or omits Content-Length is caught by the second check
        # below, against the size Django actually received.
        declared_length = request.META.get("CONTENT_LENGTH") or 0
        try:
            declared_length = int(declared_length)
        except (TypeError, ValueError):
            declared_length = 0
        if declared_length > MAX_UPLOAD_BYTES:
            return Response(
                {"detail": FILE_TOO_LARGE_MESSAGE},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # The file is taken from the parsed body BEFORE the serializer runs, because
        # section 7.2 fixes the order of the rejections and a serializer reports
        # every field at once. Validating the whole body first would answer 400 for
        # a blank title on a request whose file is a disguised binary, where 7.2
        # lines 10-22 fix 415 first, then 413, then 400. The auditor found exactly
        # that inversion on 2026-09-21: the order was claimed in a comment and not
        # implemented, and no test pinned it because each test varied one condition
        # at a time. There are now tests for the combinations.
        uploaded_file = request.data.get("file")
        if not hasattr(uploaded_file, "read"):
            # Not a file part at all. The serializer would say this too, but it has
            # not run yet, so the message is given in its shape.
            return Response(
                {"file": [NO_FILE_SUBMITTED_MESSAGE]}, status=status.HTTP_400_BAD_REQUEST
            )

        # 415: the format is established from the file's CONTENT (FR-08 Validation:
        # "confirmed by inspecting the file signature rather than the extension
        # alone, preventing a disguised file from being accepted"). The extension is
        # never consulted here; it gates only the upload control's own convenience
        # check, client-side.
        file_format = read_file_signature(uploaded_file)
        if file_format is None:
            return Response(
                {"detail": UNSUPPORTED_FORMAT_MESSAGE},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        # 413 again, now against the bytes actually received.
        if uploaded_file.size > MAX_UPLOAD_BYTES:
            return Response(
                {"detail": FILE_TOO_LARGE_MESSAGE},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # 400: the title, and the shape of the remaining fields. FR-08: "400 A
        # Document title is required for empty titles".
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400 in DRF's shape
        data = serializer.validated_data

        visible_to_roles = data.get("visible_to_roles") or list(ROLE_NAMES)
        if request.user.role.role_name not in visible_to_roles:
            # D-29. Uploading into a scope you cannot read is how content is lost:
            # the uploader could not find their own document again, and no error
            # would ever say so. A refusal to act on an otherwise authorised
            # request, so 403, as the two FR-05 refusals are.
            return Response(
                {"detail": SELF_EXCLUDING_VISIBILITY_MESSAGE},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 409: "Compared by content hash rather than by filename, so that the same
        # document uploaded under two different names is still caught" (section
        # 7.2). The hash is retained on the record so later uploads compare to it.
        content_hash = compute_content_hash(uploaded_file)
        if Document.objects.filter(content_hash=content_hash).exists():
            return Response(
                {"detail": DUPLICATE_DOCUMENT_MESSAGE}, status=status.HTTP_409_CONFLICT
            )

        try:
            outcome = ingest_and_index_document(
                uploaded_file=uploaded_file,
                file_format=file_format,
                content_hash=content_hash,
                title=data["title"],
                department=data.get("department", ""),
                visible_to_roles=visible_to_roles,
                uploaded_by=request.user,
            )
        except IntegrityError:
            # Two uploads of the same bytes raced past the check above; the unique
            # index on content_hash is what actually decides it.
            return Response(
                {"detail": DUPLICATE_DOCUMENT_MESSAGE}, status=status.HTTP_409_CONFLICT
            )
        # The document object is returned whatever the code: on a 422 the file is
        # kept and the record carries the status saying why it is not indexed, which
        # is what FR-08's "Processing failed. Please try again" action reads.
        body = DocumentSerializer(outcome.document).data
        if outcome.detail:
            body["detail"] = outcome.detail
        return Response(body, status=outcome.http_status)


# --- FR-09 meeting transcript ingestion -------------------------------------------------


class MeetingsView(APIView):
    """``/api/meetings`` — FR-09 transcript ingestion (POST) and the listing (GET).

    A transcript arrives either as pasted text, as JSON, or as an uploaded file, as
    multipart. FR-09 offers both: "Users can upload a transcript file or paste
    transcript text directly into a form". An uploaded file goes through the same
    signature check and the same parsers as FR-08, because FR-09 says the transcript
    is "passed to the chunking and embedding process in FR-08" and a second
    extraction path would be a second thing to keep correct.

    Gated on the same contribute permission as the document upload (D-30).
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), CanContributeContent()]
        return [IsAuthenticated()]

    def get(self, request):
        meetings = (
            Meeting.objects.prefetch_related("attendees__user")
            .filter(visible_to_roles__contains=[request.user.role.role_name])
            .order_by("-meeting_date", "-created_at", "pk")
        )
        return Response(MeetingListSerializer(meetings, many=True).data)

    def post(self, request):
        serializer = MeetingIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400: FR-09's own code
        data = serializer.validated_data

        transcript_text, error = self._transcript_from(data)
        if error is not None:
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

        # FR-09 Validation: "transcript content must exceed a minimum length, since a
        # near-empty transcript produces unusable AI output." Counted in tokens by
        # the one definition the chunker also uses (D-31), so a transcript judged
        # long enough can never then produce no chunks.
        if length_in_tokens(transcript_text) < MINIMUM_CONTENT_LENGTH:
            return Response(
                {"transcript_text": [INSUFFICIENT_TRANSCRIPT_MESSAGE]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        visible_to_roles = data.get("visible_to_roles") or list(ROLE_NAMES)
        if request.user.role.role_name not in visible_to_roles:
            return Response(
                {"detail": SELF_EXCLUDING_VISIBILITY_MESSAGE},
                status=status.HTTP_403_FORBIDDEN,
            )

        attendee_ids = data.get("attendees") or []
        attendees = list(User.objects.filter(pk__in=attendee_ids))
        if len(attendees) != len(set(attendee_ids)):
            # A silently dropped attendee is a participation record that quietly
            # disagrees with what was submitted (FR-20 reads these rows).
            return Response(
                {"attendees": [UNKNOWN_ATTENDEE_MESSAGE]}, status=status.HTTP_400_BAD_REQUEST
            )

        outcome = ingest_meeting_transcript(
            title=data["title"],
            meeting_date=data["meeting_date"],
            transcript_text=transcript_text,
            visible_to_roles=visible_to_roles,
            attendees=attendees,
        )
        body = MeetingSerializer(outcome.meeting).data
        if outcome.detail:
            body["detail"] = outcome.detail
        return Response(body, status=outcome.http_status)

    @staticmethod
    def _transcript_from(data):
        """The transcript's text, or a 400 body. The serializer has already ensured
        exactly one of the two was supplied."""
        uploaded_file = data.get("file")
        if uploaded_file is None:
            return data["transcript_text"], None

        file_format = read_file_signature(uploaded_file)
        if file_format is None:
            # The same four formats as FR-08, decided the same way: by content. A
            # 400 rather than FR-08's 415, because FR-09 enumerates only 201 and 400
            # and this is one field of a form being wrong.
            return None, {"file": [UNSUPPORTED_FORMAT_MESSAGE]}
        try:
            return extract_plain_text(uploaded_file, file_format), None
        except ExtractionError:
            return None, {"file": [NO_TEXT_IN_TRANSCRIPT_MESSAGE]}


class MeetingDetailView(APIView):
    """``GET /api/meetings/{id}`` — FR-09: "once processed, the stored transcript is
    then viewable in full".

    Scoped by ``visible_to_roles``, and a meeting outside the caller's scope is 404,
    not 403: CLAUDE.md invariant 1 requires that its existence not be disclosed, and
    a 403 would confirm the id names something real.
    """

    def get(self, request, pk):
        meeting = get_object_or_404(
            Meeting.objects.prefetch_related("attendees__user").filter(
                visible_to_roles__contains=[request.user.role.role_name]
            ),
            pk=pk,
        )
        return Response(MeetingSerializer(meeting).data)


class DocumentReprocessView(APIView):
    """``POST /api/documents/{doc_id}/reprocess`` — FR-08's "Please try again".

    Re-runs ingestion against the original already stored under MEDIA_ROOT, rather
    than asking for the file again (D-32). Invariant 8 kept those bytes when the
    first attempt failed, so a re-upload would only create a second row per attempt
    and leave FR-15's repository list full of near-identical entries.

    Scoped and permissioned exactly as the upload is: ``contribute_content``, and a
    document outside the caller's scope is 404 rather than 403, because a 403 would
    confirm the id names something real (CLAUDE.md invariant 1).
    """

    permission_classes = [IsAuthenticated, CanContributeContent]

    def post(self, request, pk):
        document = get_object_or_404(
            Document.objects.filter(visible_to_roles__contains=[request.user.role.role_name]),
            pk=pk,
        )
        if document.status == DOCUMENT_INDEXED:
            # Re-indexing healthy content is FR-15's business, not a retry's.
            return Response(
                {"detail": ALREADY_INDEXED_MESSAGE}, status=status.HTTP_409_CONFLICT
            )
        if not document.file_path:
            # No original to re-read. Unreachable through the API, which always
            # stores one, but a row can be made without a file.
            return Response(
                {"detail": NO_STORED_ORIGINAL_MESSAGE},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        try:
            outcome = reprocess_document(document)
        except IntegrityError:
            # Restoring the content hash collided: the same file was uploaded and
            # indexed successfully while this one sat failed.
            return Response(
                {"detail": DUPLICATE_DOCUMENT_MESSAGE}, status=status.HTTP_409_CONFLICT
            )
        body = DocumentSerializer(outcome.document).data
        if outcome.detail:
            body["detail"] = outcome.detail
        return Response(body, status=outcome.http_status)
