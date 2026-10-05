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
from django.utils.text import Truncator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.audit import log_role_change
from apps.accounts.models import Permission, Role
from apps.ai.base import ProviderUnavailable
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
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import Document
from apps.ingestion.chunking import length_in_tokens
from apps.ingestion.documents import ingest_and_index_document, reprocess_document
from apps.ingestion.errors import ExtractionError, OversizedArchiveContentError
from apps.ingestion.extraction import extract_plain_text
from apps.ingestion.meetings import ingest_meeting_transcript
from apps.ingestion.signatures import compute_content_hash, read_file_signature
from apps.retrieval.models import Conversation
from apps.retrieval.pipeline import QuestionLengthOutOfRange, answer_question
from apps.retrieval.scoping import permission_scope, scoped_documents, scoped_meetings
from apps.retrieval.search import (
    SearchQueryContainsNullCharacter,
    SearchQueryTooShort,
    search,
)

from .answers import reply_for
from .permissions import HasRolePermission
from .serializers import (
    AnswerSerializer,
    AskSerializer,
    ConversationCreateSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
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
    SearchResultsSerializer,
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
# Stage 4 item 12b: a DOCX or XLSX whose own table of contents declares more decompressed
# content than the detector will let a parser inflate (signatures.MEMBER_MAXIMUM_BYTES).
#
# **413, and NOT the 415 the neighbouring rejection uses.** The file's format is not the
# problem — it is a recognisable DOCX or XLSX, and telling its uploader "File type not
# supported" would send them to convert a file that was never the wrong type. It is a SIZE
# rejection, of decompressed size rather than transfer size, so it takes the code FR-08
# already gives to size: "413 Payload Too Large beyond the size limit". The 50 MB in
# FILE_TOO_LARGE_MESSAGE above is the transfer limit and would be equally misleading here,
# since the upload that earns this answer is usually a few hundred kilobytes, so the two
# size rejections carry different text under the one code.
COMPRESSED_CONTENT_TOO_LARGE_MESSAGE = (
    "This file's contents expand to far more than this platform will process. "
    "Upload a smaller document, or split it into parts."
)
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
# FR-12 keyword search: ``q`` was not sent at all. The minimum-length rule is NOT
# restated here — ``apps.retrieval.search`` owns it and raises, and this view maps the
# exception (D-41).
MISSING_SEARCH_TERM_MESSAGE = "A search term is required."
# NFR-19 Fault Tolerance: the system "must return a 503 Service Unavailable response with
# an informative notice, rather than crashing or hanging indefinitely", and FR-12's
# Responses clause names 503 for the AI service being unreachable after retries. The
# wording is 7.10 line 146's, with the one thing the reader can act on added: the question
# was not recorded and nothing partial was stored, so re-asking it is safe.
KNOWLEDGE_SERVICE_UNAVAILABLE_MESSAGE = (
    "The knowledge service is temporarily unavailable. Your question was not recorded; "
    "please ask it again shortly."
)
# FR-13's thread list needs a legible entry from the moment a thread exists, and the
# interface never asks the user to name a topic before typing (D-43). This placeholder
# stands only until the first question, which replaces it.
NEW_CONVERSATION_TITLE = "New conversation"

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
    ``visible_to_roles`` from the first day it exists, and since Stage 5 item 1 through
    ``scoped_documents``, the one place that predicate is written (D-53). FR-11 is Stage 4
    work and this is not that filter, but a list disclosing documents outside the caller's scope
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
            scoped_documents(role_name=permission_scope(request.user))
            .select_related("uploaded_by")
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
        try:
            file_format = read_file_signature(uploaded_file)
        except OversizedArchiveContentError:
            # Stage 4 item 12b. The signature step is where the archive's table of contents
            # is read, so it is where an over-declared DOCX or XLSX is found — but this is a
            # size rejection rather than a format one, so it does not share the 415 below.
            # The exception's own message names a member of the archive and stays in the
            # server's hands; the client gets the fixed text.
            return Response(
                {"detail": COMPRESSED_CONTENT_TOO_LARGE_MESSAGE},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
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


class DocumentDetailView(APIView):
    """``GET /api/documents/{id}`` — the route FR-12's citation clause links to (D-46).

    FR-12 requires that each citation "links to the source document or meeting".
    ``GET /api/meetings/{id}`` has existed since Stage 3, so a meeting citation already
    resolved; a document citation had nowhere to go but the repository list, which is a
    link and not a link to the source. This is that route, and it is deliberately the
    document object the repository list already returns rather than a new shape: FR-15
    (Stage 5) owns document presentation and reads this endpoint rather than replacing it.

    **The same authorisation as ``GET /api/documents``**: a session, and no more. Reading a
    document one's role may see is not a privileged action, and adding a permission class
    here would make a citation unfollowable for the role it was generated for.

    **Scoped through ``scoped_documents`` (D-53), and out of scope is 404 — never 403.** A 403
    distinguishes "exists but you may not see it" from "does not exist", which is the
    disclosure CLAUDE.md invariant 1 forbids by name; D-33's treatment of the upload 409 as
    an existence oracle is the precedent, and ``GET /api/meetings/{id}`` is the sibling that
    already behaves this way. An unknown id and an id outside the caller's scope are
    answered identically, by the same query, so there is no branch that could tell them
    apart even by timing.

    ``file_path`` and ``content_hash`` stay out of the body, because ``DocumentSerializer``
    leaves them out for every endpoint: a path inside MEDIA_ROOT is of no use to a client
    and an invitation to construct one, and echoing a content hash would let a caller probe
    whether a document they cannot see has been uploaded.
    """

    def get(self, request, pk):
        document = get_object_or_404(
            scoped_documents(role_name=permission_scope(request.user)).select_related(
                "uploaded_by"
            ),
            pk=pk,
        )
        return Response(DocumentSerializer(document).data)


# --- FR-12 keyword search ----------------------------------------------------------------


class SearchView(APIView):
    """``GET /api/search?q=<term>`` — FR-12's keyword search half (D-41).

    FR-12 is two paths. This is the Front-End clause's "search field available from every
    page, returning results grouped by type (Documents and Meetings) with a count per
    group", and the "200 OK with grouped results" half of FR-12's Responses. The
    question-and-answer path is a separate endpoint.

    **A session and nothing more.** ``IsAuthenticated`` is the global default (invariant 4)
    and this route adds no role permission, exactly as ``GET /api/documents`` adds none:
    what a search may find is decided by the scope, not by a permission code, and a role
    that may list the repository may search it.

    **The scope is not this view's to resolve, and deliberately cannot be.**
    ``apps.retrieval.search.search`` takes the user and calls ``permission_scope`` on it
    itself, so there is no role argument for a view to miswire — a view passing one user's
    identity with another's role would hand an Employee an Administrator's result set and
    log it under the Employee, plausibly and silently. Nothing is filtered after the call
    either: the counts in the reply are properties over the rows the scoped queries
    returned, so a number here can never be one taken before the permission filter
    (CLAUDE.md invariant 1, which names "a result count, a total" explicitly).

    **One log row per search, written by the function.** ``search`` writes the ``SearchLog``
    row, with the same post-filter total the caller is given. This view must not write a
    second, and a test counts the rows.

    ``UnscopedRequestError`` is not caught. Behind ``IsAuthenticated`` it is unreachable,
    and turning it into a 200 would answer a request whose scope could not be established
    — the same backstop, uncaught, as on the answer path.
    """

    def get(self, request):
        query_text = request.query_params.get("q")
        if query_text is None:
            # No term at all. DRF's validation shape, keyed on the query parameter's own
            # name, because that is the field the client got wrong.
            return Response(
                {"q": [MISSING_SEARCH_TERM_MESSAGE]}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            # Passed as given: no stripping and no sanitiser, so SearchLog records what
            # was actually typed (FR-19's evidence) and the term reaches the database only
            # as a bound parameter of an ORM lookup.
            results = search(query_text=query_text, user=request.user)
        except (SearchQueryTooShort, SearchQueryContainsNullCharacter) as exc:
            # FR-12's 400. The rule and its message belong to the search module; this
            # maps the exception rather than re-checking the length, so there is one
            # definition of "too short" and the two cannot drift. An empty ``q=`` arrives
            # here too, which is the same answer by the same rule.
            #
            # Two exception classes, one 400, and each carrying its own message (Stage 4
            # item 12a): a term with a NUL byte is rejected for a different reason from a
            # term that is too short, and it used to be answered 500 with an HTML body
            # because ``q`` is the only user-supplied string in this system that reaches
            # the database without passing a DRF field.
            return Response({"q": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        # 200 even when nothing matched: an empty reply is a fact about the corpus, not an
        # error, and the SearchLog row for it is exactly the knowledge-gap evidence FR-19
        # wants.
        return Response(SearchResultsSerializer(results).data)


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
            scoped_meetings(role_name=permission_scope(request.user))
            .prefetch_related("attendees__user")
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

        try:
            file_format = read_file_signature(uploaded_file)
        except OversizedArchiveContentError:
            # The same bound as FR-08's upload (Stage 4 item 12b), reported in this
            # endpoint's own shape: FR-09 enumerates only 201 and 400, so the transcript
            # path cannot answer 413, and a field error carrying the accurate message is
            # closer to the truth than FR-08's code on a response FR-09 does not define.
            # The two rejections stay distinguishable by their text.
            return None, {"file": [COMPRESSED_CONTENT_TOO_LARGE_MESSAGE]}
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

    Scoped through ``scoped_meetings`` (D-53), and a meeting outside the caller's scope is 404,
    not 403: CLAUDE.md invariant 1 requires that its existence not be disclosed, and
    a 403 would confirm the id names something real.
    """

    def get(self, request, pk):
        meeting = get_object_or_404(
            scoped_meetings(role_name=permission_scope(request.user)).prefetch_related(
                "attendees__user"
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
            scoped_documents(role_name=permission_scope(request.user)), pk=pk
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


# --- FR-12 answer generation and FR-13 conversations -------------------------------------


def name_thread_from(conversation, question: str) -> None:
    """FR-13's Update: name a still-unnamed thread after its first question (D-43).

    Truncated to the column width rather than refused, because MAXIMUM_QUESTION_LENGTH is
    500 and ``Conversations.title`` holds 255. A question of nothing but whitespace is long
    enough to be asked and leaves nothing to name a thread with, so the placeholder stands
    — a list entry a user cannot tell apart is the failure this whole function exists to
    avoid, and a blank one is the worst case of it.

    ``update_fields`` names the title alone: ``last_updated_at`` is ``auto_now``, so it is
    written only when it is named, and the pipeline has already set it for this turn inside
    the log transaction. Naming it here would move the thread's timestamp on after the
    reply was composed from it.
    """
    conversation.title = Truncator(question.strip()).chars(NAME_MAX_LENGTH) or NEW_CONVERSATION_TITLE
    conversation.save(update_fields=["title"])


class AskView(APIView):
    """``POST /api/ask`` — FR-12's question-and-answer path, and FR-13's turn.

    One endpoint for both, because FR-13 says so: "Answer generation and citation
    verification follow FR-12 unchanged", and each turn "triggers a fresh retrieval based
    on the resolved question rather than reusing the previous turn's passages". A separate
    conversational endpoint would be the same call with a conversation attached, and two
    routes through generation is two places for the permission scope to be got wrong.

    **What this view does not do.** It does not resolve the permission scope, rank,
    truncate, generate, verify or log: ``answer_question`` does all of it and takes the
    user, so there is no role argument here to miswire (the argument the search view
    makes). It composes no prompt and reads no chunk. Its whole job is the three things a
    view is for — decide whether this caller may use this conversation, map the pipeline's
    exceptions to status codes, and render the outcome.

    **The 404 is this view's own work and the pipeline cannot do it.** The history read is
    filtered by conversation AND user, so passing someone else's thread yields no history
    rather than their questions — but the turn's ``QueryLog`` row would still be written
    against their conversation, and would then appear in the owner's thread as a turn that
    is not theirs. So the row is fetched with the user as a predicate and anything else is
    404. **Not 403**: a 403 confirms the id names a real thread, which is the disclosure
    ``GET /api/meetings/{id}`` already refuses to make (CLAUDE.md invariant 1).

    ``UnscopedRequestError`` is deliberately not caught, as on the search route: behind
    ``IsAuthenticated`` it is unreachable, and answering a request whose scope could not be
    established is the one thing worse than a 500.
    """

    def post(self, request):
        serializer = AskSerializer(data=request.data)
        # 400 for a missing question or a conversation_id that is not a UUID. NOT for the
        # question's length: that rule belongs to the pipeline and arrives below as an
        # exception, so there is one definition of it (see AskSerializer).
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data["question"]
        conversation = self._conversation_for(
            request, serializer.validated_data.get("conversation_id")
        )
        # Read BEFORE the call: the pipeline writes this turn's row, after which no thread
        # has ever had a first turn.
        awaiting_a_name = conversation is not None and self._awaiting_a_name(conversation)

        try:
            outcome = answer_question(
                question=question, user=request.user, conversation=conversation
            )
        except QuestionLengthOutOfRange as exc:
            # FR-12's 400. The bounds and the message belong to the pipeline; this maps the
            # exception rather than restating the rule, exactly as the search view maps
            # SearchQueryTooShort. No QueryLog row is written for a question that never ran.
            return Response(
                {"question": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
            )
        except ProviderUnavailable:
            # NFR-19: "must return a 503 Service Unavailable response with an informative
            # notice, rather than crashing or hanging indefinitely", and FR-12's Responses
            # clause names 503 explicitly. Reached after MAXIMUM_GENERATION_ATTEMPTS — one
            # initial call and two retries — or on a transport failure while embedding. A
            # provider outage is never turned into a no-answer: "the system could not ask"
            # and "the corpus has no answer" are different events, and invariant 7's signal
            # depends on them staying apart.
            return Response(
                {"detail": KNOWLEDGE_SERVICE_UNAVAILABLE_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if awaiting_a_name:
            name_thread_from(conversation, question)
        # 200 on all three exits, including both no-answer paths: FR-12's Responses clause
        # is "200 OK with answered: false where nothing was sufficiently relevant or no
        # statement survived verification". Not being answerable from the corpus is a fact
        # about the corpus, not a client error.
        return Response(
            AnswerSerializer(
                reply_for(outcome=outcome, conversation=conversation, user=request.user)
            ).data
        )

    @staticmethod
    def _conversation_for(request, conversation_id):
        """The caller's own thread, or None for a one-off question; 404 for anyone else's.

        ``QueryLog.conversation`` stays NULL where this returns None, which is what that
        column has always meant (D-12).
        """
        if conversation_id is None:
            return None
        return get_object_or_404(
            Conversation.objects.filter(user=request.user), pk=conversation_id
        )

    @staticmethod
    def _awaiting_a_name(conversation) -> bool:
        """Whether this turn should name the thread (D-43): the placeholder still stands
        and no turn has been logged against it yet.

        Both conditions, so a title the user chose is never overwritten and a thread that
        has been used is never renamed out from under them.
        """
        return conversation.title == NEW_CONVERSATION_TITLE and not conversation.queries.exists()


class ConversationsView(APIView):
    """``/api/conversations`` — FR-13's thread list (GET) and a new thread (POST).

    FR-13's Database clause is ``Conversations (Create, Read, Update)``, with no Delete, so
    there is no delete route and the class defines no ``delete`` method: clearing the
    active thread "to begin a new topic" is starting a new conversation, not destroying the
    old one, and a thread the user asked questions in is the FR-19 evidence QueryLog rows
    exist to be.

    Every route here is scoped to ``request.user``. A caller may not enumerate the
    existence of another user's threads, so someone else's id is 404 and not 403.
    """

    def get(self, request):
        # Newest activity first: "previous conversations are listed" is a list a person
        # scans for the thread they were last in, and last_updated_at is the column the
        # pipeline touches on every turn. The primary key is a deterministic tie-break for
        # two threads created in the same microsecond, nothing more.
        conversations = Conversation.objects.filter(user=request.user).order_by(
            "-last_updated_at", "pk"
        )
        return Response(ConversationSerializer(conversations, many=True).data)

    def post(self, request):
        serializer = ConversationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # D-43: a title from the client if one was typed, otherwise the placeholder, which
        # the first turn replaces with that turn's question. FR-13's interface has the user
        # clear the thread and start typing — it never asks them to name a topic first — so
        # requiring a title here would be a field the requirement does not have.
        title = serializer.validated_data.get("title", "").strip() or NEW_CONVERSATION_TITLE
        conversation = Conversation.objects.create(user=request.user, title=title)
        # 201 is a convention: FR-13 enumerates only "200 OK with the answer and updated
        # conversation state", which is the turn rather than the thread, and a created
        # resource is 201 everywhere else in this contract (FR-01, FR-08, FR-09).
        return Response(
            ConversationSerializer(conversation).data, status=status.HTTP_201_CREATED
        )


class ConversationDetailView(APIView):
    """``GET /api/conversations/{id}`` — FR-13: "previous conversations are listed and can
    be reopened".

    A reopened thread renders from the server, so the questions and the cited statements a
    user sees after signing in on another machine are the ones that were logged rather than
    whatever a browser still held. The turns carry no ``no_answer_reason`` and no
    ``rejected_count``: see ``ConversationTurnSerializer``.

    Another user's thread is 404, as on ``POST /api/ask`` and for the same reason.

    **Owner is not the same test as scope, and this route needs both.** The queryset answers
    "is this thread yours"; it says nothing about whether the material the thread's answers
    were generated from is still readable by the role you hold now. A stored turn is a derived
    record carrying no visibility of its own, so every citation is re-scoped on read, through
    the same ``scoped_chunks`` predicate the answer path uses, and a turn that loses every
    statement renders as the ordinary no-answer state. The serializer holds that whole
    argument, including why the leak is the statement prose rather than the identifier; the
    request is passed into its context because the role is resolved from it per request.

    **A third state, separated at item 1c: a turn none of whose citation rows still points at
    an existing chunk.** Not a permission state — a reprocess, a re-index or FR-15's deletion
    removed the chunks it cited. Until D-67 the rows went with them (D-12's cascade); now they
    survive with ``chunk_id`` NULL and are read as if they had gone. Such a turn carries
    ``provenance_removed`` and its own message instead of claiming the question cannot be
    answered. The re-scoped state above stays silent and stays indistinguishable from a
    never-answered turn; the discriminator is whether a row still points at an existing chunk,
    read before any scoping, and ``ConversationTurnSerializer`` argues why it must stay that
    way.
    """

    def get(self, request, pk):
        conversation = get_object_or_404(
            Conversation.objects.filter(user=request.user), pk=pk
        )
        return Response(
            ConversationDetailSerializer(conversation, context={"request": request}).data
        )
