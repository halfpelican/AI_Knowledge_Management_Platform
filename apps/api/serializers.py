"""Serializers for the API contract (docs/api-contract.md).

``UserSerializer`` is the one user object every endpoint returns. It never carries
``password_hash``, ``failed_attempts`` or ``locked_until``; a test asserts the exact
key set so a field cannot leak in later.
"""

from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from django.utils import timezone

from apps.accounts.models import Role
from apps.core.constants import ROLE_NAMES
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import Document
from apps.meetings.models import Meeting

User = get_user_model()

USER_FIELDS = ("id", "name", "email", "role", "created_at")


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="role.role_name", read_only=True)

    class Meta:
        model = User
        fields = USER_FIELDS
        read_only_fields = USER_FIELDS


class DirectoryEntrySerializer(serializers.ModelSerializer):
    """A person, for choosing FR-09 meeting attendees. Deliberately not UserSerializer.

    FR-09's Front-End clause has any user associate a transcript "with a meeting
    title, date, and attendees", so any session must be able to name a colleague.
    The only list that existed was FR-05's ``GET /api/users``, which is
    Administrator-only because it carries the role each person holds and drives role
    management — so an Employee had no way to populate an attendee picker and the
    clause was unreachable for them (Stage 3 audit, finding 4).

    Three fields, and none of them is ``role``: who may change roles, and who holds
    which, stays FR-05's business. This is a staff directory, which is what naming
    an attendee needs and no more.
    """

    class Meta:
        model = User
        fields = ("id", "name", "email")
        read_only_fields = fields


# --- FR-01, FR-02 -------------------------------------------------------------------


class RegisterSerializer(serializers.Serializer):
    """FR-01 request body. The role is never accepted from the client: registration
    always creates an Employee (docs/schema-v1.md Users.role_id)."""

    name = serializers.CharField(max_length=NAME_MAX_LENGTH)
    # Bounded by the column itself, so the two cannot drift. Without the bound an
    # over-long address passes validation and the INSERT raises DataError, which is
    # a sibling of IntegrityError rather than a subclass, so the 409 handler below
    # does not catch it and an anonymous caller gets a 500 instead of the 400 the
    # contract names.
    email = serializers.EmailField(max_length=User._meta.get_field("email").max_length)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        return value.lower()  # D-02: the address is unique case-insensitively

    def validate(self, attrs):
        # AUTH_PASSWORD_VALIDATORS run against the would-be user so the similarity
        # validator can compare the password with the name and the address.
        candidate = User(name=attrs["name"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages})
        return attrs


class LoginSerializer(serializers.Serializer):
    """FR-02 request body. FR-02 Server-End, Validation rules: "required field check
    on both inputs. Email format checked before database lookup" — and the UC-02
    pseudocode is explicit that a malformed address is 400 ("IF NOT
    isValidEmailFormat(submittedEmail) THEN RETURN response(400, ...)"), before the
    account is read. A 400 on malformed syntax discloses nothing, because it is
    returned whether or not the address is registered; the generic 401 is kept for a
    well-formed address that is unknown and for a wrong password, which is where the
    enumeration protection actually lives (D-02). Bounded by the column length, as
    the registration serializer is, so the two agree."""

    email = serializers.EmailField(max_length=User._meta.get_field("email").max_length)
    password = serializers.CharField(trim_whitespace=False)

    def validate_email(self, value):
        return value.strip().lower()  # D-02


# --- FR-05 ----------------------------------------------------------------------------


class RoleSerializer(serializers.ModelSerializer):
    """``GET /api/roles`` item: the role, its permission codes (D-14) and the
    ``role_id`` FR-05's request body carries, which the client reads from here."""

    role_id = serializers.UUIDField(source="id", read_only=True)
    name = serializers.CharField(source="role_name", read_only=True)
    permissions = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="permission_name"
    )

    class Meta:
        model = Role
        fields = ("role_id", "name", "description", "permissions")
        read_only_fields = fields


class RoleChangeSerializer(serializers.Serializer):
    """``PATCH /api/users/{id}/role`` body. FR-05 Server-End: "Receives { user_id,
    new_role_id } from an authenticated Admin session only", and "new_role_id must
    exist in Roles table". The user id is the one in the path, which carries the same
    information. A missing or non-UUID ``role_id`` is a malformed body and is 400
    here; a well-formed id that names no row is 404, which the view decides, because
    "404 Not Found if user/role doesn't exist" is FR-05's own response for it."""

    role_id = serializers.UUIDField()


# --- FR-08 document upload ------------------------------------------------------------


class DocumentSerializer(serializers.ModelSerializer):
    """The document object every FR-08 and FR-15 endpoint returns.

    ``doc_id`` rather than ``id``, matching the proposal's Documents table and the
    ``201 Created with the document ID`` FR-08 promises. ``file_path`` is never
    exposed: it is a path inside MEDIA_ROOT and the client has no use for it, while
    publishing it invites a caller to construct one. ``content_hash`` is likewise
    internal — it exists to answer 409, and echoing it would let a caller probe
    whether a document they cannot see has already been uploaded.
    """

    doc_id = serializers.UUIDField(source="id", read_only=True)
    uploaded_by = serializers.CharField(source="uploaded_by.email", read_only=True)

    class Meta:
        model = Document
        fields = ("doc_id", "title", "file_type", "status", "uploaded_at", "department",
                  "visible_to_roles", "file_size_bytes", "uploaded_by")
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    """FR-08 request body, sent as ``multipart/form-data``.

    Field shapes only, and deliberately not the whole request. The *order* of the
    rejections is the view's, because section 7.2 ``validateUpload()`` fixes it —
    contribute permission, then signature, then size, then title, then duplicate —
    and a serializer reports every field at once. So the view reads the file part
    and checks its signature and size BEFORE running this serializer, and this
    serializer never sees a request that should have been 415 or 413.
    """

    file = serializers.FileField()
    title = serializers.CharField(max_length=NAME_MAX_LENGTH, allow_blank=False,
                                  trim_whitespace=True)
    department = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False,
                                       allow_blank=True, default="")
    # docs/decisions.md D-29. Omitted means both roles: a document nobody thought
    # about is visible to everybody, so an omitted field can never accidentally hide
    # content. Present but empty is 400 (``allow_empty=False``) — "visible to
    # nobody" is not something anyone means to ask for, and FR-11 would filter such a
    # document out of every search in silence. A name outside ROLE_NAMES is 400.
    visible_to_roles = serializers.ListField(
        child=serializers.ChoiceField(choices=ROLE_NAMES),
        required=False,
        allow_empty=False,
    )

    def validate_visible_to_roles(self, value):
        # Stored in ROLE_NAMES order and deduplicated, so two requests naming the
        # same roles differently produce the same row and the FR-11 predicate has
        # one shape to match.
        return [name for name in ROLE_NAMES if name in set(value)]


# --- FR-09 meeting transcript ingestion ------------------------------------------------


class MeetingSerializer(serializers.ModelSerializer):
    """The meeting object FR-09's endpoints return.

    ``transcript_text`` is included: FR-09's front end requires that "once processed,
    the stored transcript is then viewable in full", and it is the caller's own
    permitted content. The list view trims it (see ``MeetingListSerializer``) so a
    listing does not carry every transcript in the organisation.
    """

    meeting_id = serializers.UUIDField(source="id", read_only=True)
    attendees = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = ("meeting_id", "title", "meeting_date", "status", "created_at",
                  "visible_to_roles", "attendees", "transcript_text")
        read_only_fields = fields

    def get_attendees(self, meeting):
        return [attendee.user.email for attendee in meeting.attendees.all()]


class MeetingListSerializer(MeetingSerializer):
    """The same object without the transcript body.

    A list of fifty meetings should not ship fifty full transcripts to render a table
    of titles and dates; the detail route serves the full text.
    """

    class Meta(MeetingSerializer.Meta):
        fields = tuple(f for f in MeetingSerializer.Meta.fields if f != "transcript_text")
        read_only_fields = fields


class MeetingIngestSerializer(serializers.Serializer):
    """FR-09 request body, as JSON with pasted text or multipart with a file.

    FR-09 Validation: "title and date are required; the date may not be in the
    future; transcript content must exceed a minimum length, since a near-empty
    transcript produces unusable AI output." All three are 400 here, which is FR-09's
    own "400 Bad Request for missing fields or insufficient content" — note that this
    differs from FR-08, which answers 422 for too little content. Each requirement
    gets the code its own Responses clause names.

    The minimum-length check is NOT here: it applies to the transcript's final text,
    which for an uploaded file exists only after extraction. The view runs it.
    """

    title = serializers.CharField(max_length=NAME_MAX_LENGTH, allow_blank=False,
                                  trim_whitespace=True)
    meeting_date = serializers.DateField()
    # Exactly one of the two carries the transcript. Both optional at the field
    # level so that "neither was given" is one clear error rather than two.
    transcript_text = serializers.CharField(required=False, allow_blank=True,
                                            trim_whitespace=False)
    file = serializers.FileField(required=False)
    attendees = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )
    visible_to_roles = serializers.ListField(
        child=serializers.ChoiceField(choices=ROLE_NAMES),
        required=False,
        allow_empty=False,
    )

    def validate_meeting_date(self, value):
        # FR-09: "the date may not be in the future". Compared in the project's own
        # timezone (TIME_ZONE, Australia/Melbourne) rather than UTC, or a meeting
        # minuted this morning in Melbourne is "tomorrow" for part of the day.
        if value > timezone.localdate():
            raise serializers.ValidationError("A meeting date may not be in the future.")
        return value

    def validate_visible_to_roles(self, value):
        return [name for name in ROLE_NAMES if name in set(value)]

    def validate(self, attrs):
        has_text = bool((attrs.get("transcript_text") or "").strip())
        has_file = attrs.get("file") is not None
        if not has_text and not has_file:
            raise serializers.ValidationError(
                {"transcript_text": ["Provide the transcript as text or upload a file."]}
            )
        if has_text and has_file:
            # Ambiguous rather than harmless: whichever the server picked, the other
            # would be discarded in silence and the user would not know which.
            raise serializers.ValidationError(
                {"transcript_text": ["Provide either transcript text or a file, not both."]}
            )
        return attrs


# --- FR-12 keyword search ---------------------------------------------------------------

# ``SearchResult.date`` is the source's own date and so is not one type: a datetime for a
# document (``uploaded_at``) and a date for a meeting (``meeting_date``). These two render
# whichever arrived, and they live at module level rather than on the serializer because a
# Field assigned to a Serializer class becomes a *declared field* of it — these are
# formatters, not fields. Reusing DRF's own fields is what keeps a search result's date
# string byte-identical to the one ``GET /api/documents`` and ``GET /api/meetings`` already
# return for the same row, timezone conversion included; a test asserts that equality.
_DATETIME_FORMATTER = serializers.DateTimeField()
_DATE_FORMATTER = serializers.DateField()


class SearchResultSerializer(serializers.Serializer):
    """One item in an FR-12 search group.

    Exactly the four things the Front-End clause says a result shows — "its title, the
    matching passage as a snippet, its department, and its date" — plus the identifier and
    type the front end needs to link to the source.

    **This serializes the frozen ``SearchResult`` dataclass ``apps.retrieval.search``
    returned, and never the ``Document``, ``Meeting`` or ``ContentChunk`` row behind it.**
    That is the security property rather than a style choice: the dataclass carries only
    what the scoped queries selected, so no field here can reach a column nobody scoped,
    and ``file_path`` and ``content_hash`` are not reachable from it at all — the same rule
    the document object follows in docs/api-contract.md, for the same two reasons.

    ``snippet`` and ``department`` may both be blank, and legitimately: a source matched by
    title alone that holds no chunk has no passage to show, and a meeting has no department
    to carry (see ``SearchResult``'s own docstring for why that is an empty string rather
    than an invented value).
    """

    source_type = serializers.CharField(read_only=True)
    source_id = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    snippet = serializers.CharField(read_only=True, allow_blank=True)
    department = serializers.CharField(read_only=True, allow_blank=True)
    date = serializers.SerializerMethodField()

    def get_date(self, result):
        # datetime subclasses date, so the narrower test has to come first.
        if isinstance(result.date, datetime):
            return _DATETIME_FORMATTER.to_representation(result.date)
        return _DATE_FORMATTER.to_representation(result.date)


class SearchGroupSerializer(serializers.Serializer):
    """One of FR-12's two groups and the count beside it.

    ``count`` is READ from ``SearchGroup.count``, which is a property over the rows in the
    group. It is never recomputed here, never stored, and never overridden: a number
    computed from the list it labels cannot be a number taken before the permission filter,
    which is what CLAUDE.md invariant 1 asks of a reply that is mostly counts. There is no
    "showing n of m" because the wider figure does not exist in ``apps.retrieval.search``
    to be serialized, and nothing in this module may introduce one.
    """

    count = serializers.IntegerField(read_only=True)
    results = SearchResultSerializer(many=True, read_only=True)


class SearchResultsSerializer(serializers.Serializer):
    """``GET /api/search`` — two groups, their counts, and the total across both.

    ``total_count`` is likewise ``SearchResults.total_count``, a property equal to the two
    group counts added together, and is the same post-filter number written to
    ``SearchLog.result_count``. The caller, the record and the group headings therefore
    cannot disagree, because there is one place it is computed and it is not here.
    """

    query = serializers.CharField(source="query_text", read_only=True)
    documents = SearchGroupSerializer(read_only=True)
    meetings = SearchGroupSerializer(read_only=True)
    total_count = serializers.IntegerField(read_only=True)
