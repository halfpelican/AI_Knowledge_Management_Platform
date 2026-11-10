"""API views. Shapes and status codes are docs/api-contract.md, Stage 2 table.

Authentication is the session cookie (D-21); ``IsAuthenticated`` is the global
default, so only the views that set ``AllowAny`` are reachable anonymously.
Routes that need more than a session add ``HasRolePermission`` (FR-06).
"""

import logging

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.core.exceptions import SuspiciousFileOperation
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.http import FileResponse, Http404, JsonResponse
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

import apps.ai
from apps.accounts.audit import log_role_change
from apps.accounts.models import Permission, Role
from apps.ai import attempt_log
from apps.ai.base import ProviderUnavailable, TranscriptionDisabled
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    CONTRIBUTE_CONTENT_PERMISSION,
    DASHBOARD_GAP_ITEMS,
    DASHBOARD_RECENT_ITEMS,
    DOWNLOAD_CONTENT_TYPES,
    LOCKOUT_DURATION,
    LOCKOUT_NOTICE_CEILING,
    LOCKOUT_THRESHOLD,
    DOCUMENT_INDEXED,
    KNOWLEDGE_GAP_OPEN,
    MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION,
    MANAGE_ROLES_PERMISSION,
    MANAGE_TAGS_PERMISSION,
    MAX_UPLOAD_BYTES,
    MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS,
    MEETING_INDEXED,
    MINIMUM_CONTENT_LENGTH,
    REVIEW_KNOWLEDGE_GAPS_PERMISSION,
    ROLE_NAMES,
    TRANSCRIPTION_SEGMENT_SECONDS,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.classification import (
    InsufficientText,
    InvalidClassification,
    NotOnThisDocument,
    TagNotOffered,
    TopicAlreadyOffered,
    apply_tag,
    classify_document_now,
    confirm_classification,
    confirm_proposed_topic,
    confirm_tag,
    reject_proposed_topic,
    reject_tag,
)
from apps.documents.deletion import delete_document
from apps.documents.downloads import download_filename
from apps.documents.models import Document, Tag
from apps.documents.taxonomy import retire_tag, tag_inventory
from apps.ingestion import audio
from apps.ingestion.chunking import length_in_tokens
from apps.ingestion.documents import ingest_and_index_document, reprocess_document
from apps.ingestion.errors import (
    ExtractionError,
    OversizedArchiveContentError,
    TooLargeToExtractError,
)
from apps.ingestion.extraction import extract_plain_text
from apps.ingestion.meetings import ingest_meeting_transcript
from apps.ingestion.signatures import compute_content_hash, read_file_signature
from apps.meetings.deletion import delete_meeting
from apps.retrieval.gaps import ordered_gaps, run_cycle
from apps.retrieval.models import Conversation, KnowledgeGap, QueryLog
from apps.retrieval.pipeline import (
    QuestionLengthOutOfRange,
    answer_question,
    check_question_length,
)
from apps.retrieval.scoping import permission_scope, scoped_documents, scoped_meetings
from apps.retrieval.search import (
    SearchQueryContainsNullCharacter,
    SearchQueryTooLong,
    SearchQueryTooShort,
    search,
)

from .answers import reply_for
from .ask_slot import release_ask_slot, take_ask_slot
from .ingestion_slot import release_ingestion_slot, take_ingestion_slot
from .negotiation import IgnoreClientContentNegotiation
from .transcription_slot import release_transcription_slot, take_transcription_slot
from .permissions import HasRolePermission, role_holds
from .repository import RepositoryFilters, browse, classification_of, repository_documents
from .serializers import (
    AnswerSerializer,
    AskSerializer,
    ClassificationConfirmSerializer,
    ConversationCreateSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
    DashboardQuerySerializer,
    DirectoryEntrySerializer,
    DocumentBrowseQuerySerializer,
    DocumentDetailSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
    KnowledgeGapCycleSerializer,
    KnowledgeGapSerializer,
    KnowledgeGapStatusSerializer,
    LoginSerializer,
    MeetingDetailSerializer,
    MeetingIngestSerializer,
    MeetingListSerializer,
    MeetingSerializer,
    ProposedTopicSerializer,
    RecentQuestionSerializer,
    RegisterSerializer,
    RoleChangeSerializer,
    RoleSerializer,
    SearchResultsSerializer,
    TagApplySerializer,
    TagDetailSerializer,
    TagEntrySerializer,
    UserSerializer,
    classification_payload,
    tag_details_payload,
)

User = get_user_model()

# The download's and reprocess's missing-file errors (D-75). Propagates to the root logger,
# whose ERROR handler writes logs/errors.log (apps/core/logging_config.py).
logger = logging.getLogger(__name__)

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
# Reprocess's 422 for a document whose file_path is blank, names a file missing from disk, or
# names a path outside MEDIA_ROOT (D-75's note of 21 October). The cause is logged, not sent.
NO_STORED_ORIGINAL_MESSAGE = "This document has no stored original to reprocess."
# FR-10 Responses: "422 Unprocessable Entity where insufficient text was extracted" (D-105): the
# classify route's answer for a document with no extracted text, given before any provider call.
INSUFFICIENT_TEXT_MESSAGE = "No text was extracted from this document, so it cannot be classified."
# NFR-19's notice for the classify route, as KNOWLEDGE_SERVICE_UNAVAILABLE_MESSAGE below is for
# /api/ask: what happened, and that nothing was recorded, so the action is safe to repeat.
CLASSIFICATION_UNAVAILABLE_MESSAGE = (
    "The knowledge service is temporarily unavailable. The document was not classified; "
    "please try again shortly."
)
# POST /api/documents/{id}/tags (D-105's dated note of 10 November 2026, night). One 400 for a
# tag_id that is unknown, inactive or outside the document's scheme, keyed on the field, so the
# answer never tells a tag that does not exist from one the caller may not see (invariant 1).
TAG_NOT_OFFERED_MESSAGE = "Choose a tag from this document's tag options."
# FR-10 Responses: "409 Conflict on a duplicate tag name within a dimension". Answered only for a
# Topic already in the document's scheme, which the caller is offered anyway.
TOPIC_ALREADY_OFFERED_MESSAGE = (
    "A Topic with this name is already offered for this document. Choose it from the tag options."
)
# FR-15's download answers a document whose original is not stored, is gone from disk, or is
# named by a path outside MEDIA_ROOT, with
# exactly the 404 body its scoped lookup gives an unknown id or one outside the caller's scope
# (D-75), so the client cannot tell the cases apart. That body is get_object_or_404's own
# message, which DRF passes through, so it is restated here word for word: a bare Http404() or
# NotFound() would answer "Not found." and give the missing file away. A Django release that
# rewords its message fails apps/api/tests/test_document_download.py, which compares this body
# with a real out-of-scope response rather than with this string. Not NO_STORED_ORIGINAL_MESSAGE:
# a GET for bytes that are not there is "not found", while reprocess is an action that cannot
# proceed, and says so with a 422.
DOCUMENT_NOT_FOUND_MESSAGE = "No %s matches the given query." % Document._meta.object_name
# DELETE /api/tags/{id} for an id that names no tag it acts on: get_object_or_404's own wording, as
# DOCUMENT_NOT_FOUND_MESSAGE above restates it for documents.
TAG_NOT_FOUND_MESSAGE = "No %s matches the given query." % Tag._meta.object_name
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
# D-79: a second POST /api/ask from a user whose previous question is still being answered.
# The code is what the client branches on, as with ACCOUNT_LOCKED_CODE; it is also what tells
# this 429 from the rate throttle's, whose body is DRF's and carries no code. No Retry-After,
# because the answer in flight can take many minutes.
ASK_IN_FLIGHT_MESSAGE = "Your previous question is still being answered."
ASK_IN_FLIGHT_CODE = "ask_in_flight"
# D-85: a POST to any of the three ingestion routes from a user whose previous upload, transcript
# or reprocess is still being processed (apps/api/ingestion_slot.py). Its own code, so the client
# tells it from the ingestion rate's 429, whose body is DRF's and carries none, and from the ask's.
# "Upload" covers all three, as the client's "upload limit" already does. No Retry-After, because
# an ingestion's length depends on the file.
INGESTION_IN_FLIGHT_MESSAGE = "Your previous upload is still being processed."
INGESTION_IN_FLIGHT_CODE = "ingestion_in_flight"
# A thread needs a legible title from the moment it exists, since its address reads it (D-77),
# and the interface never asks the user to name a topic before typing (D-43). This placeholder
# stands only until the first question, which replaces it. The thread list leaves a thread out
# until it has a turn (D-80), so the placeholder appears there only on a thread whose first
# question left nothing to name it with.
NEW_CONVERSATION_TITLE = "New conversation"
# NFR-19's informative notice for POST /api/knowledge-gaps/cycles (D-107): the embedding provider
# was unreachable after MAXIMUM_EMBED_ATTEMPTS, and the cycle rolled back. Its own text rather than
# KNOWLEDGE_SERVICE_UNAVAILABLE_MESSAGE, which tells the reader their question was not recorded.
KNOWLEDGE_GAP_CYCLE_UNAVAILABLE_MESSAGE = (
    "The knowledge service is temporarily unavailable, so the aggregation cycle did not run and "
    "nothing was changed. Please try again shortly."
)
# Recording transcription (D-123). Each refusal is answered before any provider call, and
# none stores anything, because the route stores nothing at all. The two 503s carry codes, so the
# page can tell "not enabled on this server" (paste or upload the transcript instead) from "FLM is
# down" (resume shortly) without reading the detail.
TRANSCRIPTION_DISABLED_MESSAGE = (
    "Recording transcription is not enabled on this server. Paste or upload the transcript instead."
)
TRANSCRIPTION_DISABLED_CODE = "transcription_disabled"
# NFR-19's informative notice for a segment the provider failed after MAXIMUM_TRANSCRIBE_ATTEMPTS:
# what happened, and that nothing was stored, so sending the segment again is safe.
TRANSCRIPTION_UNAVAILABLE_MESSAGE = (
    "The transcription service is temporarily unavailable. This segment was not transcribed and "
    "nothing was stored; please send it again shortly."
)
TRANSCRIPTION_UNAVAILABLE_CODE = "transcription_unavailable"
NO_AUDIO_SUBMITTED_MESSAGE = "No audio segment was submitted."
# 415, as FR-08 answers a format it does not accept: the bytes are not a 16-bit PCM WAV, which is
# all the page sends (apps/ingestion/audio.py).
UNSUPPORTED_AUDIO_MESSAGE = "Audio must be a 16-bit PCM WAV segment, mono or stereo."
EMPTY_AUDIO_MESSAGE = "The audio segment holds no audio."
SEGMENT_TOO_LONG_MESSAGE = (
    f"An audio segment may hold at most {MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS} seconds of audio."
)
# A second segment from a user whose previous one is still with FLM (apps/api/transcription_slot.py).
TRANSCRIPTION_IN_FLIGHT_MESSAGE = "Your previous audio segment is still being transcribed."
TRANSCRIPTION_IN_FLIGHT_CODE = "transcription_in_flight"
# The two values of a transcription reply's "status".
SEGMENT_TRANSCRIBED = "transcribed"
SEGMENT_SILENT = "silent"

CanManageRoles = HasRolePermission.for_code(MANAGE_ROLES_PERMISSION)
CanContributeContent = HasRolePermission.for_code(CONTRIBUTE_CONTENT_PERMISSION)
# FR-15's deletion (D-73). Deliberately NOT a permission_classes entry on any view: DRF runs
# those in initial(), before the method, which would answer 403 for a document outside the
# caller's scope and so confirm that it exists. DocumentDetailView.delete resolves the scope
# first and consults this second.
CanManageDocuments = HasRolePermission.for_code(MANAGE_DOCUMENTS_PERMISSION)
# Meeting deletion (D-99), which mirrors D-73 and is not in the proposal. The same rule: never a
# permission_classes entry, because MeetingDetailView.delete must resolve the scope first.
CanManageMeetings = HasRolePermission.for_code(MANAGE_MEETINGS_PERMISSION)
# FR-19's log (D-107): a permission_classes entry on every knowledge-gap route, so the 403 comes
# before anything else. Nothing on those routes is scoped, so there is nothing for a 403 to
# disclose by preceding a 404: an entry's existence is the Administrator's to know.
CanReviewKnowledgeGaps = HasRolePermission.for_code(REVIEW_KNOWLEDGE_GAPS_PERMISSION)
# FR-10's tag administration (D-119 finding 5): the same arrangement as FR-19's, for the same
# reason. A permission_classes entry on both routes, so the 403 precedes the 404 for an unknown
# tag; a tag's existence is the Administrator's to know, since they read every source (D-66).
CanManageTags = HasRolePermission.for_code(MANAGE_TAGS_PERMISSION)


class ThrottlePostOnlyMixin:
    """Throttle a view's POST and nothing else (D-79), for a view that also serves a GET.

    DRF applies a view's ``throttle_classes`` to every method, and the list beside an upload or
    a thread create is read far more often than either is sent. The scope is the view's
    ``throttle_scope``. It picks by method, as ``get_permissions`` on the same views does.
    """

    def get_throttles(self):
        if self.request.method == "POST":
            return super().get_throttles()
        return []


def not_found(request, exception=None):
    """handler404: JSON like every other error, never Django's HTML page."""
    return JsonResponse({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


def ingestion_in_flight():
    """D-85's 429 for a second ingestion while the user's slot is held. Stores nothing."""
    return Response(
        {"detail": INGESTION_IN_FLIGHT_MESSAGE, "code": INGESTION_IN_FLIGHT_CODE},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


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


class DocumentsView(ThrottlePostOnlyMixin, APIView):
    """``/api/documents`` — FR-08 upload (POST) and the repository list (GET).

    **POST.** The rejection order is the proposal's section 7.2 ``validateUpload()``,
    not a serializer's field order, because 7.2 fixes it and says why the permission
    check comes first: "it is the cheapest rejection, and the user's role may have
    changed during a transfer of up to 50 MB". ``CanContributeContent`` is returned
    by ``get_permissions()`` for POST, so DRF runs it in ``initial()`` before this
    method is entered and before the body is parsed at all (D-30). Processing is
    synchronous, as FR-08 states, with the interface displaying progress.

    **POST is throttled per user in the "ingestion" scope** (D-79), one budget with meeting
    ingest and reprocess. DRF checks it in ``initial()`` after the permission and before this
    method, so a rejected upload counts against it too. GET is not throttled.

    **One ingestion in flight per user** (D-85, ``apps/api/ingestion_slot.py``), shared with
    meeting ingest and reprocess. Taken after the last rejection and right before ingestion, so
    only a request that would otherwise be stored can meet it, and released in ``finally``.
    While it is held, another upload is answered at once with ``INGESTION_IN_FLIGHT_CODE``.
    The body has been parsed and hashed by then: the slot bounds the extraction and the
    embedding, not the reading of the request.

    **GET.** The list FR-08's front end reads the "Indexed" status from, scoped by
    ``visible_to_roles`` from the first day it exists, and since Stage 5 item 1 through
    ``scoped_documents``, the one place that predicate is written (D-53). FR-11 is Stage 4
    work and this is not that filter, but a list disclosing documents outside the caller's scope
    would be a leak to remove later rather than a feature, and CLAUDE.md invariant 1
    is explicit that the existence of out-of-scope material must not be disclosed
    "by a result count, a total, or an error message". Since Stage 5 item 2 the list is
    built by ``repository_documents``, the one query FR-15's browse route also builds on
    (D-72), and its body is unchanged: a bare list, newest first.
    """

    permission_classes = [IsAuthenticated]
    # The one endpoint that accepts something other than JSON. The global JSON-only
    # default (D-24) exists to stop a cross-site HTML form reaching an *anonymous*
    # endpoint; it is not what protects this one. This route requires a session, and
    # DRF enforces CSRF as soon as its session authenticator resolves a user, so a
    # cross-site multipart POST here is rejected for want of the token.
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]  # POST only, through ThrottlePostOnlyMixin
    throttle_scope = "ingestion"

    def get_permissions(self):
        # Contributing is not reading: FR-08's 403 guards the upload, and a session
        # that may read the repository is not thereby entitled to add to it.
        if self.request.method == "POST":
            return [IsAuthenticated(), CanContributeContent()]
        return [IsAuthenticated()]

    def get(self, request):
        # The one list query browse also builds on (D-72): no filters, newest first.
        documents = repository_documents(role_name=permission_scope(request.user))
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

        # D-85: one ingestion in flight per user, taken after every rejection above, so a
        # 400, 403, 409, 413 or 415 is answered as before and never holds it. Nothing has been
        # stored yet, so the 429 stores nothing.
        token = take_ingestion_slot(request.user)
        if token is None:
            return ingestion_in_flight()
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
        finally:
            # Whatever the exit: a 201, a 422, the 409 above, or an exception on its way to a 500.
            release_ingestion_slot(request.user, token)
        # The document object is returned whatever the code: on a 422 the file is
        # kept and the record carries the status saying why it is not indexed, which
        # is what FR-08's "Processing failed. Please try again" action reads. A 201
        # also carries the classification, or null (section 7.8 line 100; D-105).
        return Response(ingestion_body(outcome), status=outcome.http_status)


def scoped_document_or_404(request, pk):
    """The document, if the caller's scope holds it; 404 otherwise, unknown or not (D-46).

    The one lookup behind every route that names a document by id and returns it or acts on it:
    the detail view, its delete and the download (D-75). One scoped query and
    ``get_object_or_404``, so an unknown id and one outside the caller's scope are the same
    query with the same answer and there is no branch that could tell them apart.
    """
    return get_object_or_404(
        scoped_documents(role_name=permission_scope(request.user)).select_related(
            "uploaded_by"
        ),
        pk=pk,
    )


def require_contribute_content(request, view) -> None:
    """403 unless the caller's role holds ``contribute_content``, checked AFTER the scoped lookup.

    FR-10's routes (D-105) check the permission inside the method, as FR-15's delete does (D-73):
    a permission class runs in ``initial()``, before the lookup, and would answer 403 for a document
    outside the caller's scope and so confirm that it exists. The message is the permission class's
    own, so this 403 reads as every other 403 does.
    """
    if not CanContributeContent().has_permission(request, view):
        view.permission_denied(request, message=CanContributeContent.message)


def ingestion_body(outcome) -> dict:
    """The upload's and the reprocess's body: the document object; ``detail`` on a 422; and on a 201
    ``classification`` (section 7.8 line 100; D-105), the object or null when classification failed
    and the document is indexed unclassified (invariant 8, D-33 part 1). The list routes never
    carry it."""
    body = DocumentSerializer(outcome.document).data
    if outcome.detail:
        body["detail"] = outcome.detail
    if outcome.http_status == status.HTTP_201_CREATED:
        body["classification"] = classification_payload(outcome.analysis)
    return body


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

    **FR-15 (Stage 5 item 2) adds three fields** to the body, ``extracted_text``, ``tags`` and
    ``can_delete`` (``DocumentDetailSerializer``; D-63, D-73), and the ``DELETE`` method below.
    """

    def _may_delete(self, request) -> bool:
        """Whether the caller's role holds ``manage_documents``, read from ``role_permissions``
        on this request as every permission is (``apps/api/permissions.py``, D-14, D-21)."""
        return CanManageDocuments().has_permission(request, self)

    def get(self, request, pk):
        document = scoped_document_or_404(request, pk)
        return Response(
            DocumentDetailSerializer(
                document, context={"can_delete": self._may_delete(request)}
            ).data
        )

    def delete(self, request, pk):
        """``DELETE /api/documents/{id}``: FR-15's permissioned deletion (D-73).

        **Scope first, permission second, and the order is the security property.** The
        document is resolved through ``scoped_documents`` exactly as ``get`` resolves it, so an
        unknown id and one outside the caller's scope are both 404, by one query (D-46). Only a
        document the caller may see reaches the permission check, which answers 403 for a role
        without ``manage_documents``. In the other order an Employee could tell an
        Administrator-only document from a non-existent one by the code: 403 for the first, 404
        for the second. That is why the check is here and not in ``permission_classes``, which
        DRF runs before this method.

        **Then everything goes in one transaction** (``apps/documents/deletion.py``): the chunks
        and tag links by source, which have no foreign key (D-07), and the document with its
        extracted content. The stored file is removed when that transaction commits. 204 with no
        body is a convention: FR-15 names no success code for a delete.
        """
        document = scoped_document_or_404(request, pk)
        if not self._may_delete(request):
            self.permission_denied(request, message=CanManageDocuments.message)
        delete_document(document)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentDownloadView(APIView):
    """``GET /api/documents/{id}/download`` — FR-15's download link (D-75).

    The first route that returns a document's ORIGINAL BYTES rather than anything derived from
    them. The detail screen's link points here, never at ``file_path.url``: that is
    ``/media/<path>``, and ``config/urls.py`` serves nothing outside ``/api/``, deliberately —
    ``static(MEDIA_URL)`` would serve every document to anyone who had its path.

    **Scope first, then the file, and the order is the security property.** The document is
    resolved by ``scoped_document_or_404``, the lookup the detail view uses, so an unknown id and
    one outside the caller's scope are both 404, never 403 (D-46). Only a document the caller
    may see reaches the file checks below, so an out-of-scope document gets the plain 404 and
    logs nothing, even when its file is missing too. A session and nothing more: FR-15 names no
    permission for the link, and every status downloads, because the original is stored
    whether or not it was indexed (D-52's note).

    **Retrieval scopes chunks; this can only scope the document.** Retrieval reads
    ``ContentChunk.visible_to_roles``, and a download can consult only
    ``Document.visible_to_roles``, because the original is one file. The two agree only while
    the visibility cascade holds (invariant 2, D-17, D-47), and D-53's probe for this route
    seeds a disagreement to show it fails closed.

    **A missing original is the same 404, logged.** ``file_path`` blank, the file gone from
    disk (a delete committing between the lookup and the open, or a hand edit), or a
    ``file_path`` naming a path outside MEDIA_ROOT, which only a script could write, answers with
    the body the lookup gives an unknown id, word for word, so the client cannot tell the cases
    apart; the cause goes to the error log (D-75), not to the client. The blank case is checked
    before opening because opening a blank ``FieldFile`` raises ``ValueError``, not ``OSError``,
    and a path outside MEDIA_ROOT raises ``SuspiciousFileOperation``, which Django would
    otherwise answer 400. The file is opened before the response is built, so a failure is a
    404, not a 500 halfway through a stream.

    **Typed and named by the signature, never by the name** (D-15's principle on the way out).
    The ``Content-Type`` comes from ``file_type``, which ``read_file_signature`` proved from the
    bytes at upload, and ``SecurityMiddleware``'s ``X-Content-Type-Options: nosniff`` makes the
    browser hold to it. The filename is the stored one with its last extension corrected to that
    format (``download_filename``), so text uploaded as ``invoice.html`` downloads as
    ``invoice.txt``. ``FileResponse`` writes ``Content-Disposition``; nothing here builds it.

    **The request's ``Accept`` header is not consulted.** DRF would otherwise answer
    ``Accept: application/pdf`` with 406 before this method ran, because the API's only
    renderer is JSON (``IgnoreClientContentNegotiation`` says why).
    """

    content_negotiation_class = IgnoreClientContentNegotiation

    def get(self, request, pk):
        document = scoped_document_or_404(request, pk)
        stored_name = document.file_path.name
        if not document.file_path:
            logger.error(
                "Document %s has no stored original to download (stored name %r).",
                document.pk,
                stored_name,
            )
            raise Http404(DOCUMENT_NOT_FOUND_MESSAGE)
        try:
            handle = document.file_path.open("rb")
        except (OSError, SuspiciousFileOperation):
            logger.error(
                "The stored original of document %s is missing, unreadable or outside the media "
                "folder (stored name %r).",
                document.pk,
                stored_name,
                exc_info=True,
            )
            raise Http404(DOCUMENT_NOT_FOUND_MESSAGE)
        return FileResponse(
            handle,
            as_attachment=True,
            filename=download_filename(stored_name, document.file_type),
            content_type=DOWNLOAD_CONTENT_TYPES[document.file_type],
        )


class DocumentBrowseView(APIView):
    """``GET /api/documents/browse`` — FR-15's list view, filters, sort and facets (D-72).

    FR-15 asks for "a list view of documents showing title, type, uploader, upload date, and
    status, with sorting and text filtering", and "a browse mode allowing navigation by
    Department, Project, Process or Topic without composing a query", where "filters combine,
    with item counts shown against each available value". One request returns the applied
    filters, the facets and the documents.

    **A session and nothing more**, as ``GET /api/documents``: reading what one's role may see
    is not a privileged action. ``IsAuthenticated`` is the global default (invariant 4).

    **The documents come from the same query as ``GET /api/documents``**
    (``repository_documents``, D-72), starting from ``scoped_documents`` (D-53), and every facet
    count is taken over those scoped rows. A value found only on documents the caller cannot see
    is never offered, and a count never includes one (FR-15: "counts are computed after that
    filter, so a count never discloses inaccessible content"; invariant 1).

    **Parameters pass ``DocumentBrowseQuerySerializer``** (D-65), so a NUL byte, an over-long
    value or a status or sort outside its vocabulary is a 400 keyed on the parameter, and a
    department or tag is never looked up.

    **204 only when a filter is set and nothing matches** (FR-15's "204 No Content for a filter
    combination with no accessible matches"). An unknown value and a value used only on
    restricted documents both match nothing the caller may see, so both are the same 204 with no
    body. ``sort`` alone is not a filter, and an unfiltered empty repository is 200 with empty
    lists, because there is no filter combination to fail (D-72).
    """

    def get(self, request):
        query = DocumentBrowseQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)  # 400 in DRF's shape (D-65, a convention)
        applied = query.validated_data
        filters = RepositoryFilters(
            **{name: value for name, value in applied.items() if name != "sort"}
        )
        result = browse(
            role_name=permission_scope(request.user), filters=filters, sort=applied["sort"]
        )
        if result is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {
                # The filters applied, after validation, with null for any not applied.
                "filters": query.data,
                "facets": result.facets,
                "documents": DocumentSerializer(result.documents, many=True).data,
            }
        )


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

    **Throttled per user, scope "search"** (``SEARCH_THROTTLE_RATE``, D-79's note of 10 November
    2026), and a term over ``MAXIMUM_SEARCH_LENGTH`` is FR-12's 400. Both bound how fast and how
    much one user can put into ``SearchLog``, which FR-19's cycle reads (the security review's L1
    and L2). DRF checks the throttle after authentication, so an anonymous request is still 401,
    and a throttled search writes no row.

    ``UnscopedRequestError`` is not caught. Behind ``IsAuthenticated`` it is unreachable,
    and turning it into a 200 would answer a request whose scope could not be established
    — the same backstop, uncaught, as on the answer path.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "search"

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
        except (SearchQueryTooShort, SearchQueryTooLong, SearchQueryContainsNullCharacter) as exc:
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


class MeetingsView(ThrottlePostOnlyMixin, APIView):
    """``/api/meetings`` — FR-09 transcript ingestion (POST) and the listing (GET).

    A transcript arrives either as pasted text, as JSON, or as an uploaded file, as
    multipart. FR-09 offers both: "Users can upload a transcript file or paste
    transcript text directly into a form". An uploaded file goes through the same
    signature check and the same parsers as FR-08, because FR-09 says the transcript
    is "passed to the chunking and embedding process in FR-08" and a second
    extraction path would be a second thing to keep correct.

    Gated on the same contribute permission as the document upload (D-30), and POST is
    throttled per user in the same "ingestion" scope as the upload and reprocess (D-79). GET is
    not throttled.

    **One ingestion in flight per user** (D-85), the upload's slot. It is taken after every 400
    and 403, and an uploaded transcript file is extracted before that, because the minimum-length
    400 needs its text. So the slot bounds chunking and embedding here, and a file's extraction
    (bounded by D-81 for a PDF) runs outside it.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser]
    throttle_classes = [ScopedRateThrottle]  # POST only, through ThrottlePostOnlyMixin
    throttle_scope = "ingestion"

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

        # D-85: the same slot as the document upload, taken after every 400 and 403 above.
        token = take_ingestion_slot(request.user)
        if token is None:
            return ingestion_in_flight()
        try:
            outcome = ingest_meeting_transcript(
                title=data["title"],
                meeting_date=data["meeting_date"],
                transcript_text=transcript_text,
                visible_to_roles=visible_to_roles,
                attendees=attendees,
            )
        finally:
            release_ingestion_slot(request.user, token)
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
        except TooLargeToExtractError as exc:
            # D-81: a PDF over one of the extraction bounds. Caught before its base class, so
            # the uploader is told which size limit it met, in that bound's own text, rather
            # than that the file held no readable text. The same 400 as an unreadable file,
            # because FR-09 enumerates only 201 and 400. Nothing has been stored yet, so the
            # bound's limit sentence is sent alone: the documents route prefixes it with
            # "The document was stored but not indexed.", which would be untrue here.
            return None, {"file": [exc.limit_message]}
        except ExtractionError:
            return None, {"file": [NO_TEXT_IN_TRANSCRIPT_MESSAGE]}


def scoped_meeting_or_404(request, pk):
    """The meeting, if the caller's scope holds it; 404 otherwise, unknown or not (D-46).

    The one lookup behind the meeting detail and its delete (D-99), as ``scoped_document_or_404``
    is for documents. One scoped query and ``get_object_or_404``, so an unknown id and one outside
    the caller's scope are the same query with the same answer and there is no branch that could
    tell them apart.
    """
    return get_object_or_404(
        scoped_meetings(role_name=permission_scope(request.user)).prefetch_related(
            "attendees__user"
        ),
        pk=pk,
    )


class MeetingDetailView(APIView):
    """``GET /api/meetings/{id}`` — FR-09: "once processed, the stored transcript is
    then viewable in full".

    Scoped through ``scoped_meetings`` (D-53), and a meeting outside the caller's scope is 404,
    not 403: CLAUDE.md invariant 1 requires that its existence not be disclosed, and
    a 403 would confirm the id names something real.

    **D-99 adds ``can_delete``** to the body (``MeetingDetailSerializer``) and the ``DELETE``
    method below. Meeting deletion is not in the proposal: FR-09 gives Meetings Create, Read and
    Update status only. The lead asked for it on 7 November 2026, and it mirrors
    ``DocumentDetailView`` (D-73) clause for clause.
    """

    def _may_delete(self, request) -> bool:
        """Whether the caller's role holds ``manage_meetings``, read from ``role_permissions`` on
        this request as every permission is (``apps/api/permissions.py``, D-14, D-21)."""
        return CanManageMeetings().has_permission(request, self)

    def get(self, request, pk):
        meeting = scoped_meeting_or_404(request, pk)
        return Response(
            MeetingDetailSerializer(
                meeting, context={"can_delete": self._may_delete(request)}
            ).data
        )

    def delete(self, request, pk):
        """``DELETE /api/meetings/{id}`` (D-99, mirroring D-73).

        **Scope first, permission second, and the order is the security property.** The meeting
        is resolved through ``scoped_meetings`` exactly as ``get`` resolves it, so an unknown id
        and one outside the caller's scope are both 404, by one query (D-46). Only a meeting the
        caller may see reaches the permission check, which answers 403 for a role without
        ``manage_meetings``. In the other order an Employee could tell an Administrator-only
        meeting from a non-existent one by the code. That is why the check is here and not in
        ``permission_classes``, which DRF runs before this method.

        **Then everything goes in one transaction** (``apps/meetings/deletion.py``): the chunks
        and tag links by source, which have no foreign key (D-07), and the meeting with its
        attendees. A meeting stores no file, so nothing waits for the commit. 204 with no body,
        the document delete's convention.
        """
        meeting = scoped_meeting_or_404(request, pk)
        if not self._may_delete(request):
            self.permission_denied(request, message=CanManageMeetings.message)
        delete_meeting(meeting)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Recording transcription (D-123) ---------------------------------------------------
# Not in the proposal. A person with a meeting recording has the page turn it into a draft
# transcript, one segment at a time; nothing here indexes anything. The confirmed draft goes in
# through POST /api/meetings, FR-09's own route and the one path into the index.


def transcription_refused(detail: str, code: str):
    """A 503 carrying ``code``, for the page to branch on, as the in-flight 429s carry theirs."""
    return Response({"detail": detail, "code": code}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class TranscriptionStatusView(APIView):
    """``GET /api/transcriptions/status`` — whether a recording can be transcribed here, now.

    The page asks once, when the recording option is chosen, so it can say before a long run
    starts that transcription is not enabled on this server, or that FLM does not answer. The
    body also carries the segment lengths, so the page cuts what the server will accept.

    ``available`` is true only when transcription is enabled and the provider's
    ``transcription_health`` reports FLM answering. That cannot show whether FLM was started with
    ``--asr 1`` (D-123, "What it does not cover"); a server without it fails the first
    segment, which the page reports the same way. No provider detail is returned: it names an
    internal address, and the page needs only the two flags.

    Behind ``contribute_content``, as the transcription itself is: only someone who may add a
    transcript has a reason to ask.
    """

    permission_classes = [IsAuthenticated, CanContributeContent]

    def get(self, request):
        enabled = apps.ai.transcription_enabled()
        available = enabled and apps.ai.get_ai_service().transcription_health().available
        return Response(
            {
                "enabled": enabled,
                "available": available,
                "segment_seconds": TRANSCRIPTION_SEGMENT_SECONDS,
                "maximum_segment_seconds": MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS,
            }
        )


class TranscriptionsView(APIView):
    """``POST /api/transcriptions`` — one recording segment in, its text out (D-123).

    **The request is multipart**, one field, ``audio``: a 16-bit PCM WAV of at most
    MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS. **It creates nothing**: no meeting, no chunk, no file,
    no row. The page assembles the replies into a draft, a person corrects and confirms it, and
    only then does FR-09's ``POST /api/meetings`` store and index it.

    **The rejection order**, each before any provider call:

    1. 401 no session; 403 the role lacks ``contribute_content`` (DRF's ``initial()``, before the
       body is parsed, as the upload's permission is: the cheapest rejection first).
    2. 429 past ``TRANSCRIPTION_THROTTLE_RATE``, scope ``transcription`` (D-79), also in
       ``initial()``, so a rejected request counts against it too.
    3. 503 ``transcription_disabled`` when ``TRANSCRIPTION_PROVIDER`` is ``none``, before the body
       is read.
    4. 413 a declared ``Content-Length`` over MAX_UPLOAD_BYTES, before the body is parsed; then
       400 no ``audio`` part; then 413 again against the bytes that arrived.
    5. 415 not a 16-bit PCM WAV at an accepted channel count and rate; 400 a segment with no audio
       frames, or with more than MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS of audio.
    6. 200 ``"status": "silent"`` for a segment whose loudest half second is below
       TRANSCRIPTION_SILENCE_DBFS, with no provider call: Whisper invents text from silence.
    7. 429 ``transcription_in_flight`` while another segment of this user's is with the provider
       (``apps/api/transcription_slot.py``).

    Then the provider: 200 ``"status": "transcribed"`` with the text and the model, or NFR-19's
    503 ``transcription_unavailable`` after MAXIMUM_TRANSCRIBE_ATTEMPTS (any 4xx refusal at once,
    D-118). Nothing was stored, so the page sends the same segment again when the person resumes;
    its draft and recording are its own and were never here to lose (invariant 8).
    """

    permission_classes = [IsAuthenticated, CanContributeContent]
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "transcription"

    def post(self, request):
        if not apps.ai.transcription_enabled():
            return transcription_refused(TRANSCRIPTION_DISABLED_MESSAGE, TRANSCRIPTION_DISABLED_CODE)

        # The declared length, before request.data is touched, as the document upload does.
        declared_length = request.META.get("CONTENT_LENGTH") or 0
        try:
            declared_length = int(declared_length)
        except (TypeError, ValueError):
            declared_length = 0
        if declared_length > MAX_UPLOAD_BYTES:
            return Response(
                {"detail": FILE_TOO_LARGE_MESSAGE}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )

        uploaded = request.data.get("audio")
        if not hasattr(uploaded, "read"):
            return Response(
                {"audio": [NO_AUDIO_SUBMITTED_MESSAGE]}, status=status.HTTP_400_BAD_REQUEST
            )
        # Again against what arrived, for a client that lies about or omits the length.
        if uploaded.size > MAX_UPLOAD_BYTES:
            return Response(
                {"detail": FILE_TOO_LARGE_MESSAGE}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )

        try:
            segment = audio.read_segment(uploaded.read())
        except audio.UnsupportedAudio:
            return Response(
                {"detail": UNSUPPORTED_AUDIO_MESSAGE}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            )
        except audio.EmptyAudio:
            return Response({"audio": [EMPTY_AUDIO_MESSAGE]}, status=status.HTTP_400_BAD_REQUEST)
        except audio.SegmentTooLong:
            return Response({"audio": [SEGMENT_TOO_LONG_MESSAGE]}, status=status.HTTP_400_BAD_REQUEST)

        duration = round(segment.duration_seconds, 2)
        if segment.silent:
            return Response(
                {"status": SEGMENT_SILENT, "text": "", "model": None, "duration_seconds": duration}
            )

        token = take_transcription_slot(request.user)
        if token is None:
            return Response(
                {"detail": TRANSCRIPTION_IN_FLIGHT_MESSAGE, "code": TRANSCRIPTION_IN_FLIGHT_CODE},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        try:
            # Every failed attempt inside is logged naming this account (apps/ai/attempt_log.py).
            with attempt_log.account(request.user.pk):
                result = audio.transcribe(segment)
        except TranscriptionDisabled:
            # The setting was read as on above; reached only if it changed in between.
            return transcription_refused(TRANSCRIPTION_DISABLED_MESSAGE, TRANSCRIPTION_DISABLED_CODE)
        except ProviderUnavailable as exc:
            # On the attempts logger, beside the failed attempts it ended, as the ask's 503 is.
            logging.getLogger(attempt_log.ATTEMPT_LOGGER_NAME).warning(
                "POST /api/transcriptions answered 503 (account %s): %s: %s",
                request.user.pk,
                attempt_log.cause_of(exc),
                exc,
            )
            return transcription_refused(
                TRANSCRIPTION_UNAVAILABLE_MESSAGE, TRANSCRIPTION_UNAVAILABLE_CODE
            )
        finally:
            release_transcription_slot(request.user, token)
        return Response(
            {
                "status": SEGMENT_TRANSCRIBED,
                "text": result.text,
                "model": result.model,
                "duration_seconds": duration,
            }
        )


class DocumentReprocessView(APIView):
    """``POST /api/documents/{doc_id}/reprocess`` — FR-08's "Please try again".

    Re-runs ingestion against the original already stored under MEDIA_ROOT, rather
    than asking for the file again (D-32). Invariant 8 kept those bytes when the
    first attempt failed, so a re-upload would only create a second row per attempt
    and leave FR-15's repository list full of near-identical entries.

    Scoped and permissioned exactly as the upload is: ``contribute_content``, and a
    document outside the caller's scope is 404 rather than 403, because a 403 would
    confirm the id names something real (CLAUDE.md invariant 1). Throttled per user in the
    "ingestion" scope the upload and meeting ingest share (D-79), and it holds the same
    in-flight slot they do (D-85), taken after the 404, the 409 and the 422.

    **No stored original is a 422 with ``NO_STORED_ORIGINAL_MESSAGE``, logged** (D-75's note of
    21 October). That covers a blank ``file_path``, a file missing from disk and a
    ``file_path`` naming a path outside MEDIA_ROOT, which raises ``SuspiciousFileOperation``
    rather than ``OSError``. The file is opened here and closed again before
    ``reprocess_document`` opens it inside its transaction, so a missing file is found before
    any chunk is deleted. The cause and the document go to the error log, not to the client.
    **Not covered:** a file removed between this check and that open still raises inside the
    transaction, which rolls back and answers 500.
    """

    permission_classes = [IsAuthenticated, CanContributeContent]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ingestion"

    def post(self, request, pk):
        document = get_object_or_404(
            scoped_documents(role_name=permission_scope(request.user)), pk=pk
        )
        if document.status == DOCUMENT_INDEXED:
            # Re-indexing healthy content is FR-15's business, not a retry's.
            return Response(
                {"detail": ALREADY_INDEXED_MESSAGE}, status=status.HTTP_409_CONFLICT
            )
        stored_name = document.file_path.name
        if not document.file_path:
            # No original to re-read. Unreachable through the API, which always
            # stores one, but a row can be made without a file.
            logger.error(
                "Document %s has no stored original to reprocess (stored name %r).",
                document.pk,
                stored_name,
            )
            return Response(
                {"detail": NO_STORED_ORIGINAL_MESSAGE},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        try:
            # Through the storage rather than the FieldFile, so nothing opened here is cached
            # on the field for reprocess_document to find closed.
            with document.file_path.storage.open(stored_name, "rb"):
                pass
        except (OSError, SuspiciousFileOperation):
            logger.error(
                "The stored original of document %s is missing, unreadable or outside the media "
                "folder, so it cannot be reprocessed (stored name %r).",
                document.pk,
                stored_name,
                exc_info=True,
            )
            return Response(
                {"detail": NO_STORED_ORIGINAL_MESSAGE},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        # D-85: the upload's slot, taken after the 404, the 409 and the 422 above, so the
        # document is left exactly as it was when it is refused.
        token = take_ingestion_slot(request.user)
        if token is None:
            return ingestion_in_flight()
        try:
            outcome = reprocess_document(document)
        except IntegrityError:
            # Restoring the content hash collided: the same file was uploaded and
            # indexed successfully while this one sat failed.
            return Response(
                {"detail": DUPLICATE_DOCUMENT_MESSAGE}, status=status.HTTP_409_CONFLICT
            )
        finally:
            release_ingestion_slot(request.user, token)
        return Response(ingestion_body(outcome), status=outcome.http_status)


# --- FR-10 classification (D-104, D-105) -----------------------------------------------------
#
# Seven routes over one document (the seventh, a person applying a tag, since D-105's dated note
# of 10 November 2026, night), and one rule for all of them, in this order: the document is
# resolved through the caller's scope (404 for an unknown id and one outside the scope alike,
# D-46); then ``contribute_content`` is checked, 403 without it (D-105 settles the permission,
# D-73 the order, so a 403 can never confirm that a document the caller cannot see exists); then
# the body is validated; then apps/documents/classification.py does the work, in one transaction.
# No body here says more than the 404 would: ``NotOnThisDocument`` (a link, a proposal or an
# analysis that is not this document's) is answered with the scoped lookup's own 404 body, word
# for word. Two of the routes are throttled, classify in the "ingestion" scope and a person's apply
# in "tagging" (D-79 and its note on tagging). DRF checks a throttle before the method runs, so past
# the rate their 429 comes before the 404, the same for every id.


class DocumentClassifyView(APIView):
    """``POST /api/documents/{id}/classify`` — classify now (FR-10, D-105).

    One provider call through ``classify_document_now``, then the apply rules, in one transaction.
    422 where the document has no extracted text (FR-10 Responses: "where insufficient text was
    extracted"), before any provider call; 503 with NFR-19's notice when the provider failed after
    MAXIMUM_CLASSIFY_ATTEMPTS, nothing written. Throttled in the "ingestion" scope (D-79): it is
    one provider call, like a reprocess. No in-flight slot (D-85): the slot bounds extraction and
    embedding, and this does neither.

    200 ``{classification, tag_details, department}``. ``department`` is the document's
    ``department`` column as it stands after the classification, re-read from the row as the
    confirm route's is: the machine fills a blank department with an applied in-scheme suggestion,
    and keeps a different one, holding the suggestion for a person (D-105's note of 10 November).
    The client cannot tell which from the classification object, which does not carry the
    effective department (D-72), so it is returned rather than inferred.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ingestion"

    def post(self, request, pk):
        document = scoped_document_or_404(request, pk)
        require_contribute_content(request, self)
        try:
            analysis = classify_document_now(document)
        except InsufficientText:
            return Response(
                {"detail": INSUFFICIENT_TEXT_MESSAGE},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except ProviderUnavailable as exc:
            # The failed attempts themselves are in the provider attempts log (apps/ai); this
            # names the route and the document the 503 was answered for.
            logger.warning("POST /api/documents/%s/classify answered 503: %s", document.pk, exc)
            return Response(
                {"detail": CLASSIFICATION_UNAVAILABLE_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        document.refresh_from_db(fields=["department"])
        return Response(
            {
                "classification": classification_payload(analysis),
                "tag_details": tag_details_payload(document),
                "department": document.department,
            }
        )


class DocumentClassificationView(APIView):
    """``POST /api/documents/{id}/classification`` — a person confirms or edits (FR-10, D-105).

    Body ``{doc_type?, department?}``. Both omitted confirms as it stands: a provisional type is
    applied and a provisional department is written to ``Documents.department``. A ``doc_type``
    outside DOCUMENT_TYPES is 400 keyed on ``doc_type``; a document never classified is the scoped
    lookup's 404, so the body says no more than it would for a document the caller cannot see.

    200 ``{classification, department}``: ``department`` is the document's ``department`` column as
    it stands after the confirm or edit, re-read from the row, so the client never has to work out
    the effective department from the outcome (it is not in the classification object, D-72).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        document = scoped_document_or_404(request, pk)
        require_contribute_content(request, self)
        serializer = ClassificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400 in DRF's shape, keyed on the field
        data = serializer.validated_data
        try:
            analysis = confirm_classification(
                document, doc_type=data.get("doc_type"), department=data.get("department")
            )
        except InvalidClassification as exc:
            return Response({"doc_type": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        except NotOnThisDocument:
            raise Http404(DOCUMENT_NOT_FOUND_MESSAGE)
        document.refresh_from_db(fields=["department"])
        return Response(
            {"classification": classification_payload(analysis), "department": document.department}
        )


class DocumentTagConfirmView(APIView):
    """``POST /api/documents/{id}/tags/{content_tag_id}/confirm`` — accept a tag "in a single
    action" (FR-10's provenance clause): confirmed, no longer provisional, ``applied_by`` kept."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk, content_tag_id):
        document = scoped_document_or_404(request, pk)
        require_contribute_content(request, self)
        try:
            link = confirm_tag(document, content_tag_id)
        except NotOnThisDocument:
            raise Http404(DOCUMENT_NOT_FOUND_MESSAGE)
        return Response(TagDetailSerializer(link).data)


class DocumentTagsView(APIView):
    """``POST /api/documents/{id}/tags`` — a person applies a tag (FR-10's provenance clause; UC-09
    A3; D-105's dated note of 10 November 2026, night).

    The FR-10 order: the scoped 404, then ``contribute_content``'s 403, then the body
    (``TagApplySerializer``: exactly one of ``{tag_id}`` and ``{dimension: "Topic", tag_name}``),
    then ``apply_tag``. A ``tag_id`` not offered for this document, for whatever reason, is one 400
    keyed on ``tag_id``. A new Topic whose name is already offered is FR-10's 409, carrying that
    tag's id, which the detail's ``tag_options`` already shows the caller; a Topic of that name that
    exists only beyond the document's audience, or inactive, is linked and answered as a new one.

    201 ``{"tag_details": [...]}`` when a new link was made; 200 with the same shape when the tag was
    already on the document and was confirmed, restored or left as it was. ``tag_details`` is the
    document's whole current list, as the classify reply carries it.

    **Throttled per user, scope "tagging"** (``TAGGING_THROTTLE_RATE``, D-79's note on tagging of 10
    November 2026, night, answering D-105's security review, finding 4). Each new Topic name typed
    here becomes a permanent Tag, which joins the scheme that later classification prompts list with
    no cap and that ``tag_options`` offers, so the rate bounds how fast one user can grow it. DRF
    checks the throttle in ``initial()``, after authentication and the permission classes and before
    ``post`` runs. This route's one permission class is ``IsAuthenticated``, so an anonymous request
    is still 401, and past the rate the 429 comes before the scoped 404 and ``contribute_content``'s
    403. It is the same answer for every id, so it discloses nothing, as the search throttle answers
    before any query runs. Every request the throttle admits counts, whatever ``post`` then answers,
    and a throttled one writes nothing.

    **The other tag routes are not throttled.** Confirming or removing a link and rejecting a
    proposal create no Tag. ``confirm_proposed_topic`` can create a Topic, but only from a proposal
    the classifier made, and classification is reached over HTTP only through upload, reprocess and
    classify, which share the "ingestion" budget.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "tagging"

    def post(self, request, pk):
        document = scoped_document_or_404(request, pk)
        require_contribute_content(request, self)
        serializer = TagApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400 in DRF's shape, keyed on the field
        data = serializer.validated_data
        try:
            applied = apply_tag(document, tag_id=data.get("tag_id"), tag_name=data.get("tag_name"))
        except NotOnThisDocument:
            raise Http404(DOCUMENT_NOT_FOUND_MESSAGE)
        except TagNotOffered:
            return Response({"tag_id": [TAG_NOT_OFFERED_MESSAGE]}, status=status.HTTP_400_BAD_REQUEST)
        except TopicAlreadyOffered as exc:
            return Response(
                {"detail": TOPIC_ALREADY_OFFERED_MESSAGE, "tag_id": str(exc.tag_id)},
                status=status.HTTP_409_CONFLICT,
            )
        except InvalidClassification as exc:
            return Response({"tag_name": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"tag_details": tag_details_payload(document)},
            status=status.HTTP_201_CREATED if applied.created else status.HTTP_200_OK,
        )


class DocumentTagView(APIView):
    """``DELETE /api/documents/{id}/tags/{content_tag_id}`` — remove a tag "in a single action". 204
    with no body. The link is kept, marked removed, a person's as well as an AI link with the
    machine's confidence, and no read lists it again (``reject_tag``, D-105's dated note of 10
    November 2026, night). The ``Tags`` row, a vocabulary, stays (D-73's note). A link already
    removed is the same 404 as an unknown one."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, content_tag_id):
        document = scoped_document_or_404(request, pk)
        require_contribute_content(request, self)
        try:
            reject_tag(document, content_tag_id)
        except NotOnThisDocument:
            raise Http404(DOCUMENT_NOT_FOUND_MESSAGE)
        return Response(status=status.HTTP_204_NO_CONTENT)


class _ProposedTopicView(APIView):
    """The two proposed-topic routes share everything but the function they call: body
    ``{value}``, validated after the 404 and the 403; the value normalised before it is matched;
    200 with the classification and the tag details as they now stand."""

    permission_classes = [IsAuthenticated]

    def act(self, document, value):  # pragma: no cover - the subclasses decide
        raise NotImplementedError

    def post(self, request, pk):
        document = scoped_document_or_404(request, pk)
        require_contribute_content(request, self)
        serializer = ProposedTopicSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400 keyed on "value"
        try:
            self.act(document, serializer.validated_data["value"])
        except NotOnThisDocument:
            raise Http404(DOCUMENT_NOT_FOUND_MESSAGE)
        except InvalidClassification as exc:
            return Response({"value": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "classification": classification_payload(classification_of(document)),
                "tag_details": tag_details_payload(document),
            }
        )


class DocumentProposedTopicConfirmView(_ProposedTopicView):
    """``POST /api/documents/{id}/proposed-topics/confirm`` — a person confirms an out-of-scheme
    Topic, which is when the tag is created (FR-10: "requires user confirmation before it is
    created") and linked ``applied_by="ai"``, confirmed."""

    def act(self, document, value):
        confirm_proposed_topic(document, value)


class DocumentProposedTopicRejectView(_ProposedTopicView):
    """``POST /api/documents/{id}/proposed-topics/reject`` — the proposal is dropped and nothing
    is created."""

    def act(self, document, value):
        reject_proposed_topic(document, value)


# --- FR-10 tag administration (D-119 finding 5; D-105's dated note of 10 November 2026, night) --


class TagListView(APIView):
    """``GET /api/tags`` — every Tag in Project, Process and Topic, active or not, ordered by dimension
    then name, each with ``item_count`` (``apps/documents/taxonomy.py::tag_inventory``).

    ``manage_tags`` is a permission class, so 401 and then 403 come before anything else, as on
    FR-19's routes. The list is not scoped and needs no scope: its one reader, the Administrator,
    reads every source (D-66), and the seed's test holds every holder of the code to that. 200 with a
    bare list, ``[]`` for none.
    """

    permission_classes = [IsAuthenticated, CanManageTags]

    def get(self, request):
        return Response(TagEntrySerializer(tag_inventory(), many=True).data)


class TagDetailView(APIView):
    """``DELETE /api/tags/{id}`` — retire a tag (FR-10: "Tags are deactivated rather than deleted
    where content still references them, preserving historical classification").

    401, then 403 without ``manage_tags``, then 404 for an id naming no tag in the three dimensions.
    A tag any link references, in any state, is deactivated and answered 200 with its entry, again
    for one already inactive; an unreferenced tag is deleted, 204 with no body
    (``apps/documents/taxonomy.py::retire_tag``). There is no route that reactivates a tag.
    """

    permission_classes = [IsAuthenticated, CanManageTags]

    def delete(self, request, pk):
        try:
            tag = retire_tag(pk)
        except Tag.DoesNotExist:
            raise Http404(TAG_NOT_FOUND_MESSAGE)
        if tag is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(TagEntrySerializer(tag).data)


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

    **Two limits, two 429s (D-79).** The "ask" rate throttle runs in ``initial()``, before the
    body is read, and answers with DRF's body and ``Retry-After``. The in-flight slot
    (``apps/api/ask_slot.py``) is taken after every check that can answer 400 or 404 and right
    before the pipeline, so a refused question never holds it, and is released in ``finally``.
    While it is held, another ask from the same user is answered at once with
    ``ASK_IN_FLIGHT_CODE``, writes no ``QueryLog`` row and reaches no provider.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ask"

    def post(self, request):
        serializer = AskSerializer(data=request.data)
        # 400 for a missing question or a conversation_id that is not a UUID. NOT for the
        # question's length: that rule belongs to the pipeline (see AskSerializer).
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data["question"]
        try:
            # The pipeline's own check, called here as well so that its 400 comes before the
            # in-flight slot is taken (D-79). answer_question runs it again first thing.
            check_question_length(question)
        except QuestionLengthOutOfRange as exc:
            # FR-12's 400. The bounds and the message belong to the pipeline; this maps the
            # exception rather than restating the rule, exactly as the search view maps
            # SearchQueryTooShort. No QueryLog row is written for a question that never ran.
            return Response(
                {"question": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
            )
        conversation = self._conversation_for(
            request, serializer.validated_data.get("conversation_id")
        )
        # Read BEFORE the call: the pipeline writes this turn's row, after which no thread
        # has ever had a first turn.
        awaiting_a_name = conversation is not None and self._awaiting_a_name(conversation)

        token = take_ask_slot(request.user)
        if token is None:
            return Response(
                {"detail": ASK_IN_FLIGHT_MESSAGE, "code": ASK_IN_FLIGHT_CODE},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        try:
            return self._answer(request, question, conversation, awaiting_a_name)
        finally:
            # Whatever the exit: an answer, a 503, or an exception on its way to a 500.
            release_ask_slot(request.user, token)

    @staticmethod
    def _answer(request, question, conversation, awaiting_a_name):
        """The turn itself, run while this user's in-flight slot is held."""
        # Every failed provider attempt inside, and the 503 below, are logged naming this
        # account (apps/ai/attempt_log.py, 1 November 2026).
        with attempt_log.account(request.user.pk):
            try:
                outcome = answer_question(
                    question=question, user=request.user, conversation=conversation
                )
            except ProviderUnavailable as exc:
                # NFR-19: "must return a 503 Service Unavailable response with an informative
                # notice, rather than crashing or hanging indefinitely", and FR-12's Responses
                # clause names 503 explicitly. Reached after MAXIMUM_GENERATION_ATTEMPTS — one
                # initial call and two retries — or on a transport failure while embedding. A
                # provider outage is never turned into a no-answer: "the system could not ask"
                # and "the corpus has no answer" are different events, and invariant 7's
                # signal depends on them staying apart. The cause goes to the error file; the
                # reply's notice stays the fixed one.
                attempt_log.unavailable(exc)
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


class ConversationsView(ThrottlePostOnlyMixin, APIView):
    """``/api/conversations`` — FR-13's thread list (GET) and a new thread (POST).

    FR-13's Database clause is ``Conversations (Create, Read, Update)``, with no Delete, so
    there is no delete route and the class defines no ``delete`` method: clearing the
    active thread "to begin a new topic" is starting a new conversation, not destroying the
    old one, and a thread the user asked questions in is the FR-19 evidence QueryLog rows
    exist to be.

    Every route here is scoped to ``request.user``. A caller may not enumerate the
    existence of another user's threads, so someone else's id is 404 and not 403.

    **The list leaves out a thread nobody has asked anything in (D-80).** A thread is listed
    once it has a ``QueryLog`` row, answered or not. An empty thread is not deleted:
    ``GET /api/conversations/{id}`` still reads it, and the Ask screen reuses it by its address.

    **POST is throttled per user in its own "conversation_create" scope** (D-79, D-80), so
    creating a thread does not spend the ask budget. GET is not throttled.
    """

    throttle_classes = [ScopedRateThrottle]  # POST only, through ThrottlePostOnlyMixin
    throttle_scope = "conversation_create"

    def get(self, request):
        # Newest activity first: "previous conversations are listed" is a list a person
        # scans for the thread they were last in, and last_updated_at is the column the
        # pipeline touches on every turn. The primary key is a deterministic tie-break for
        # two threads created in the same microsecond, nothing more.
        #
        # D-80: only threads with at least one turn, through an Exists subquery on QueryLog.
        # Never on the "New conversation" title, which a thread keeps after a turn whose
        # question named nothing, and never on what a turn renders: a thread whose every turn
        # is now re-scoped, or whose only turn was a no-answer, still has its rows and stays
        # listed, so the list cannot show that something was withheld.
        conversations = (
            Conversation.objects.filter(user=request.user)
            .filter(Exists(QueryLog.objects.filter(conversation=OuterRef("pk"))))
            .order_by("-last_updated_at", "pk")
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
    whatever a browser still held. Since D-78 an answered turn also carries the sources it
    consulted, in the live reply's shape, rebuilt from the chunks on every read. The turns
    carry no ``no_answer_reason`` and no ``rejected_count``: see
    ``ConversationTurnSerializer``.

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


# --- FR-14 dashboard ----------------------------------------------------------------------


class DashboardView(APIView):
    """``GET /api/dashboard`` — FR-14: every panel's counts and recent items in one request.

    FR-14's Server-End clause asks for "a single endpoint [that] aggregates counts and recent
    items across the content tables in one request rather than issuing separate calls per
    panel". This is that endpoint, and docs/api-contract.md (Stage 5, FR-14) is its shape.

    **A session and nothing more.** ``IsAuthenticated`` is the global default (invariant 4),
    which gives FR-14's "401 Unauthorised where the session is invalid". No permission code
    is added: reading what one's role may see is not a privileged action, as on
    ``GET /api/documents``.

    **Every document and meeting row, and every number derived from them, starts from the
    scoped helpers** (D-53): ``scoped_documents`` and ``scoped_meetings``, for the role
    ``permission_scope`` re-reads from the users table on this request. The filters narrow
    those querysets and the counts are ``.count()`` over them, so a total is taken after the
    permission filter, never before it (FR-14's "counts are computed after permission
    filtering, consistent with FR-11"; invariant 1). Scope is role scope with D-66's reading,
    and meetings are scoped by role, never by attendance (D-16, invariant 3).

    **Recent questions are the caller's own ``QueryLog`` rows, and the question only** (D-68).
    Role scoping would show one user's questions to another, so these are filtered by owner,
    not by role, and ``RecentQuestionSerializer`` says why the answer and its record-only
    columns are left out.

    **What each filter narrows** (D-70):

    - ``date_from`` / ``date_to``, inclusive: documents by the Melbourne date of
      ``uploaded_at``, meetings by ``meeting_date``, questions by the Melbourne date of
      ``answered_at``. Each type's indexed figure is narrowed with its own panel.
    - ``department``: documents and the documents figure only. Meetings and questions carry no
      department, so it narrows neither, and the screen says so.

    **``departments`` comes from the scoped documents, before any filter is applied** (D-70).
    A department found only on documents the caller cannot see is never offered, and the list
    does not change under the user as the filters do.

    **``ContentChunks`` is not read** (D-70). Ingestion is atomic (invariant 9), so a source's
    ``Indexed`` status already says its chunks exist.

    **The knowledge-gap panel is FR-19's, and only for a role holding ``review_knowledge_gaps``**
    (D-107, which closes D-69). For that role the payload gains ``knowledge_gaps``: the number of
    Open entries and up to ``DASHBOARD_GAP_ITEMS`` of them in the list's order. For any other role
    the key is absent, so an Employee's payload is exactly what it was before FR-19. The filters
    do not narrow it.
    """

    def get(self, request):
        query = DashboardQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)  # 400 in DRF's shape (D-65, a convention)
        date_from = query.validated_data["date_from"]
        date_to = query.validated_data["date_to"]
        department = query.validated_data["department"]

        # Resolved once, so every panel is scoped to the same role on this request.
        role_name = permission_scope(request.user)
        documents = scoped_documents(role_name=role_name)
        meetings = scoped_meetings(role_name=role_name)
        questions = QueryLog.objects.filter(user=request.user)

        # The offered values, from the scoped documents and before any filter (D-70).
        departments = list(
            documents.exclude(department="")
            .values_list("department", flat=True)
            .distinct()
            .order_by("department")
        )

        if date_from is not None:
            documents = documents.filter(uploaded_at__date__gte=date_from)
            meetings = meetings.filter(meeting_date__gte=date_from)
            questions = questions.filter(answered_at__date__gte=date_from)
        if date_to is not None:
            documents = documents.filter(uploaded_at__date__lte=date_to)
            meetings = meetings.filter(meeting_date__lte=date_to)
            questions = questions.filter(answered_at__date__lte=date_to)
        if department is not None:
            # Documents only (D-70). An exact match on the stored value, which is what
            # ``departments`` offers.
            documents = documents.filter(department=department)

        indexed_documents = documents.filter(status=DOCUMENT_INDEXED).count()
        indexed_meetings = meetings.filter(status=MEETING_INDEXED).count()

        recent_documents = documents.select_related("uploaded_by").order_by(
            "-uploaded_at", "pk"
        )[:DASHBOARD_RECENT_ITEMS]
        # The ordering ``GET /api/meetings`` uses: newest met first, then newest recorded.
        recent_meetings = meetings.prefetch_related("attendees__user").order_by(
            "-meeting_date", "-created_at", "pk"
        )[:DASHBOARD_RECENT_ITEMS]
        # Three columns selected and no more, so the answer and the record-only columns are
        # never read out of the database for this route (D-68).
        recent_questions = questions.order_by("-answered_at", "pk").values(
            "question", "answered_at", "conversation_id"
        )[:DASHBOARD_RECENT_ITEMS]

        payload = {
            # The filters applied, after validation, with null for any not applied.
            "filters": query.data,
            "departments": departments,
            "indexed_totals": {
                "documents": indexed_documents,
                "meetings": indexed_meetings,
                "total": indexed_documents + indexed_meetings,
            },
            "recent_documents": DocumentSerializer(recent_documents, many=True).data,
            "recent_meetings": MeetingListSerializer(recent_meetings, many=True).data,
            "recent_questions": RecentQuestionSerializer(recent_questions, many=True).data,
        }
        # FR-19's panel (D-107, closing D-69): present only for a role holding
        # review_knowledge_gaps, read from role_permissions on this request, and absent
        # otherwise, so an Employee's payload keeps its shape. Not narrowed by the date or
        # department filters: an entry has no department, and its dates are its own.
        if role_holds(request.user.role_id, REVIEW_KNOWLEDGE_GAPS_PERMISSION):
            open_gaps = ordered_gaps().filter(status=KNOWLEDGE_GAP_OPEN)
            payload["knowledge_gaps"] = {
                "open_count": open_gaps.count(),
                "top": KnowledgeGapSerializer(open_gaps[:DASHBOARD_GAP_ITEMS], many=True).data,
            }
        return Response(payload)


# --- FR-19 knowledge-gap log (docs/decisions.md D-107 to D-109) -----------------------------


class KnowledgeGapListView(APIView):
    """``GET /api/knowledge-gaps`` — FR-19's list: "questions the system could not answer and
    searches returning no results, grouped by subject with an occurrence count".

    ``IsAuthenticated`` and ``review_knowledge_gaps`` (D-107): 401 without a session, 403 for a
    role that lacks the code. Every entry, Open first by ``occurrence_count`` then
    ``last_seen_at``, then Addressed in the same order (``gaps.ordered_gaps``). No pagination.
    Each entry carries six fields and no asker, role or reason (``KnowledgeGapSerializer``).
    """

    permission_classes = [IsAuthenticated, CanReviewKnowledgeGaps]

    def get(self, request):
        return Response(KnowledgeGapSerializer(ordered_gaps(), many=True).data)


class KnowledgeGapCyclesView(APIView):
    """``POST /api/knowledge-gaps/cycles`` — run one aggregation cycle now (D-107).

    The scheduled trigger is ``manage.py aggregate_knowledge_gaps``. This route runs the same
    ``run_cycle`` synchronously for the demonstration, and answers 201 with the cycle row. A
    provider outage after the embedding retries rolls the cycle back and is NFR-19's 503 with an
    informative notice, never a partial cycle.
    """

    permission_classes = [IsAuthenticated, CanReviewKnowledgeGaps]

    def post(self, request):
        # Every failed embedding attempt inside is logged naming this account (attempt_log).
        with attempt_log.account(request.user.pk):
            try:
                cycle = run_cycle(triggered_by=request.user)
            except ProviderUnavailable as exc:
                # On the attempts logger, beside the failed attempts it ended, as the ask's 503
                # is; the reply's notice stays the fixed one.
                logging.getLogger(attempt_log.ATTEMPT_LOGGER_NAME).warning(
                    "POST /api/knowledge-gaps/cycles answered 503 (account %s): %s: %s",
                    request.user.pk,
                    attempt_log.cause_of(exc),
                    exc,
                )
                return Response(
                    {"detail": KNOWLEDGE_GAP_CYCLE_UNAVAILABLE_MESSAGE},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        return Response(KnowledgeGapCycleSerializer(cycle).data, status=status.HTTP_201_CREATED)


class KnowledgeGapDetailView(APIView):
    """``PATCH /api/knowledge-gaps/{id}`` — FR-19's "mark an entry as addressed", and back.

    Body ``{"status": "Addressed"}`` or ``{"status": "Open"}``; 200 with the entry. The entry is
    looked up first, so an unknown id is 404 whatever the body, and then the body is validated:
    any other value is 400 keyed on ``status``. The row is locked, so a change arriving while a
    cycle runs waits for it and returns the entry as the cycle left it.
    """

    permission_classes = [IsAuthenticated, CanReviewKnowledgeGaps]

    def patch(self, request, pk):
        with transaction.atomic():
            gap = get_object_or_404(KnowledgeGap.objects.select_for_update(), pk=pk)
            serializer = KnowledgeGapStatusSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            gap.status = serializer.validated_data["status"]
            gap.save(update_fields=["status"])
        return Response(KnowledgeGapSerializer(gap).data)
