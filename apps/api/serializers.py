"""Serializers for the API contract (docs/api-contract.md).

``UserSerializer`` is the one user object every endpoint returns. It never carries
``password_hash``, ``failed_attempts`` or ``locked_until``; a test asserts the exact
key set so a field cannot leak in later.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from django.utils import timezone

from apps.accounts.models import Role
from apps.core.constants import (
    DEFAULT_DOCUMENT_SORT,
    DOCUMENT_SORT_VALUES,
    DOCUMENT_STATUS_VALUES,
    DOCUMENT_TYPES,
    NO_ANSWER_MESSAGE,
    PROVENANCE_REMOVED_MESSAGE,
    ROLE_NAMES,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import ContentTag, Document, normalise_tag_name
from apps.meetings.models import Meeting
from apps.retrieval.models import Conversation
from apps.retrieval.query_log import FIRST_POSITION
from apps.retrieval.scoping import permission_scope, scoped_chunks

from .answers import resolve_sources
from .repository import classification_of, extracted_text_of, tag_details_of, tags_of

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


class DocumentDetailSerializer(DocumentSerializer):
    """``GET /api/documents/{id}``: the document object plus FR-15's three detail fields.

    FR-15's detail view shows "its metadata, extracted content, and a download link" (D-63,
    D-73). The download link is Stage 5 item 2a and is not here. The three fields:

    - ``extracted_text``: ``ExtractedContent.extracted_text`` of the document the view resolved
      through ``scoped_documents``, never reassembled from chunks, and ``None`` where the
      document has no row ("Extraction failed", "Insufficient content", "Too large to index").
      The client keys its empty state on ``None``, not on the status (D-63). It is a document's
      whole content and is exactly as sensitive as the file, which is why it travels only on
      this scoped route.
    - ``tags``: the document's tag names per Project, Process and Topic. Department is the
      ``department`` field already in the object (D-72).
    - ``can_delete``: whether the caller's role holds ``manage_documents``, supplied by the view
      in the context and resolved the way every permission is (``apps/api/permissions.py``). A
      hint for showing the delete control; ``DELETE`` checks the permission itself whatever the
      screen did (invariant 4). Read from the context with no default, so a caller that forgets
      to decide it raises rather than rendering a guess.

    **FR-10 adds two more (D-105):** ``classification``, the ``ClassificationSerializer`` object
    or ``None`` for a document never classified, and ``tag_details``, one entry per tag link,
    provisional included, with its provenance. ``tags`` keeps its shape and lists applied links
    only. The effective department is the ``department`` field already in the object (D-72).

    The list routes keep ``DocumentSerializer``: a list of fifty documents should not carry
    fifty documents' whole text, as ``MeetingListSerializer`` leaves out the transcript.
    """

    extracted_text = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    classification = serializers.SerializerMethodField()
    tag_details = serializers.SerializerMethodField()

    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + (
            "extracted_text", "tags", "can_delete", "classification", "tag_details",
        )
        read_only_fields = fields

    def get_extracted_text(self, document):
        return extracted_text_of(document)

    def get_tags(self, document):
        return tags_of(document)

    def get_can_delete(self, document):
        return self.context["can_delete"]

    def get_classification(self, document):
        return classification_payload(classification_of(document))

    def get_tag_details(self, document):
        return tag_details_payload(document)


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


# --- FR-10 classification (D-104, D-105) ------------------------------------------------


class ClassificationSerializer(serializers.Serializer):
    """The ``classification`` object: a ``DocumentAnalysis`` as the detail, the classify route and
    the upload's 201 carry it (docs/api-contract.md, NIT3004 — FR-10).

    Confidences are numbers, not DRF's default string rendering of a Decimal, because the client
    compares them with a threshold rather than displaying them verbatim. The effective department
    is NOT here: it is the document object's ``department`` (D-72), and ``department_outcome``
    says how it got there. ``discarded_suggestions`` is not exposed: it is a record for the
    Objective 05 measurement (D-106), not for the interface.
    """

    doc_type = serializers.CharField(read_only=True, allow_null=True)
    doc_type_outcome = serializers.CharField(read_only=True, allow_null=True)
    department_outcome = serializers.CharField(read_only=True, allow_null=True)
    machine_doc_type = serializers.CharField(read_only=True, allow_null=True)
    machine_doc_type_confidence = serializers.FloatField(read_only=True, allow_null=True)
    machine_department = serializers.CharField(read_only=True, allow_blank=True)
    machine_department_confidence = serializers.FloatField(read_only=True, allow_null=True)
    user_edited = serializers.BooleanField(read_only=True)
    proposed_topics = serializers.JSONField(read_only=True)
    classified_at = serializers.DateTimeField(read_only=True)
    model = serializers.CharField(read_only=True, allow_blank=True)
    input_truncated = serializers.BooleanField(read_only=True)


class TagDetailSerializer(serializers.ModelSerializer):
    """One ``tag_details`` entry: a ``ContentTag`` link with its tag's dimension and name, its
    provenance (``applied_by``, ``confirmed``) and FR-10's ``provisional`` and ``confidence``."""

    content_tag_id = serializers.UUIDField(source="id", read_only=True)
    dimension = serializers.CharField(source="tag.dimension", read_only=True)
    name = serializers.CharField(source="tag.tag_name", read_only=True)
    confidence = serializers.FloatField(read_only=True, allow_null=True)

    class Meta:
        model = ContentTag
        fields = ("content_tag_id", "dimension", "name", "applied_by", "confirmed", "provisional",
                  "confidence")
        read_only_fields = fields


def classification_payload(analysis) -> dict | None:
    """The ``classification`` object for ``analysis``, or ``None`` where there is none."""
    return None if analysis is None else ClassificationSerializer(analysis).data


def tag_details_payload(document) -> list[dict]:
    """The document's ``tag_details``, through ``tag_details_of`` (provisional included)."""
    return TagDetailSerializer(tag_details_of(document), many=True).data


class ClassificationConfirmSerializer(serializers.Serializer):
    """``POST /api/documents/{id}/classification``: a person confirms as it stands (both omitted)
    or edits. ``doc_type`` is one of DOCUMENT_TYPES, read through a ChoiceField so the 400 is keyed
    on it (FR-10: "the type must be selected from a fixed list"); ``department`` may be blank, which
    clears it. Null means omitted, for either."""

    doc_type = serializers.ChoiceField(choices=DOCUMENT_TYPES, required=False, allow_null=True)
    department = serializers.CharField(
        max_length=NAME_MAX_LENGTH, required=False, allow_null=True, allow_blank=True,
        trim_whitespace=True,
    )


class ProposedTopicSerializer(serializers.Serializer):
    """The body of the proposed-topic routes: the value as proposed or as typed. It is normalised
    before it is matched, so case and spacing do not matter; blank, or over the column, is 400."""

    value = serializers.CharField(max_length=NAME_MAX_LENGTH, allow_blank=False, trim_whitespace=True)


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


class MeetingDetailSerializer(MeetingSerializer):
    """``GET /api/meetings/{id}``: the meeting object plus ``can_delete`` (D-99).

    ``can_delete`` is whether the caller's role holds ``manage_meetings``, supplied by the view in
    the context, exactly as ``DocumentDetailSerializer`` takes it for ``manage_documents`` (D-73).
    A hint for showing the delete control; ``DELETE`` checks the permission itself whatever the
    screen did (invariant 4). Read from the context with no default, so a caller that forgets to
    decide it raises rather than rendering a guess.

    Only ``can_delete``: the document detail's ``extracted_text`` and ``tags`` stay document
    fields. A meeting's text is already ``transcript_text``, and FR-15's browse by tag is about
    documents (D-74). ``POST /api/meetings`` keeps ``MeetingSerializer``, as the upload keeps
    ``DocumentSerializer``.
    """

    can_delete = serializers.SerializerMethodField()

    class Meta(MeetingSerializer.Meta):
        fields = MeetingSerializer.Meta.fields + ("can_delete",)
        read_only_fields = fields

    def get_can_delete(self, meeting):
        return self.context["can_delete"]


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


def _rendered_date(value):
    """Whichever of the two arrived, rendered by DRF's own field.

    Shared by the search result and the FR-12 Sources panel, so one row's date is the
    same string wherever it appears in the interface. datetime subclasses date, so the
    narrower test has to come first.
    """
    if isinstance(value, datetime):
        return _DATETIME_FORMATTER.to_representation(value)
    return _DATE_FORMATTER.to_representation(value)


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
        return _rendered_date(result.date)


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


# --- FR-12 answer path, FR-13 conversations ---------------------------------------------


class AskSerializer(serializers.Serializer):
    """``POST /api/ask`` request body: the question, and optionally the thread it is a
    turn of.

    **No length bounds on ``question``, deliberately.** MINIMUM_QUESTION_LENGTH and
    MAXIMUM_QUESTION_LENGTH are enforced by the pipeline's ``check_question_length``, which
    raises ``QuestionLengthOutOfRange``. The view calls it before taking the in-flight slot
    (D-79) and maps that exception to FR-12's 400, and ``answer_question`` calls it again.
    Declaring ``min_length`` here would be a second definition of "too short" that could drift from
    the one the pipeline applies, exactly as the keyword search endpoint leaves the
    minimum term length to ``apps.retrieval.search`` (D-41). So this field accepts a blank
    string and untrimmed whitespace: the question travels to the pipeline character for
    character, which is also what ``QueryLog.question`` stores.

    ``conversation_id`` absent means a one-off question and ``QueryLog.conversation``
    stays NULL, which is that column's documented meaning (D-12). A value that is not a
    UUID is a malformed body and is 400 here; a well-formed id that is not this user's is
    404, which the view decides — see the view for why it is not 403.
    """

    question = serializers.CharField(allow_blank=True, trim_whitespace=False)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)


class AnswerStatementSerializer(serializers.Serializer):
    """One verified statement of an answer, with its citation number and its identifier.

    ``chunk_id`` is not optional and there is no serializer for an unverified statement:
    invariant 6 — the interface has no state in which an uncited factual statement is
    shown — is kept by the statement arriving with its identifier or not existing. The
    object behind this is ``NumberedStatement``, built only from
    ``RetrievalOutcome.verified_statements``, which is the only statement list the
    pipeline lets out.
    """

    position = serializers.IntegerField(read_only=True)
    text = serializers.CharField(read_only=True)
    chunk_id = serializers.CharField(read_only=True)


class ConsultedPassageSerializer(serializers.Serializer):
    """The passage a citation expands to show (FR-12: "Each citation expands to display
    the source passage and links to the source document or meeting")."""

    chunk_id = serializers.CharField(read_only=True)
    text = serializers.CharField(read_only=True)


class ConsultedSourceSerializer(serializers.Serializer):
    """One item in FR-12's Sources panel: "every item consulted with its date".

    Consulted, not merely cited — see ``apps.api.answers``. ``date`` is rendered by the
    same helper the search result uses, so the same row carries one date string across the
    interface. No score is exposed: a similarity number is a tuning signal for the team,
    and an interface that displayed it would be presenting relevance as a fact about the
    answer.
    """

    source_type = serializers.CharField(read_only=True)
    source_id = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    date = serializers.SerializerMethodField()
    passages = ConsultedPassageSerializer(many=True, read_only=True)

    def get_date(self, source):
        return _rendered_date(source.date)


class PartialMatchSerializer(serializers.Serializer):
    """One partially related item offered beside a no-answer (FR-12: "Any partially related
    items found are offered, clearly labelled as partial matches").

    The same four shapes a search result and a Sources panel entry carry, and deliberately
    no fifth: **there is no ``passages`` field, no ``snippet`` and no score.** A fragment of
    source text under a message that has just said the question cannot be answered reads as
    the speculative answer FR-12 refuses in the sentence before, and a score would invite
    the reader to treat the nearest item as the answer. The object behind this is
    ``PartialMatchSource``, which has no field for either — so the guarantee is that the
    text is unreachable, not that this serializer chose not to name it.

    ``date`` goes through the shared formatter, so the same row shows one date string
    wherever it appears in the interface.
    """

    source_type = serializers.CharField(read_only=True)
    source_id = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    date = serializers.SerializerMethodField()

    def get_date(self, match):
        return _rendered_date(match.date)


class ConversationSerializer(serializers.ModelSerializer):
    """A thread, as the list and as the "updated conversation state" FR-13 returns.

    Never ``user``: every conversation a caller can reach is their own, so the field would
    only ever echo the requester back to themselves, and a conversation object that
    carried a user id would invite a client to send one.
    """

    conversation_id = serializers.UUIDField(source="id", read_only=True)

    class Meta:
        model = Conversation
        fields = ("conversation_id", "title", "last_updated_at")
        read_only_fields = fields


class AnswerSerializer(serializers.Serializer):
    """``POST /api/ask`` reply, on all three of the pipeline's exits.

    **The key set does not change between them**, so an answered reply and a no-answer
    reply are the same shape with different contents: ``answered`` false, ``message`` set,
    ``result_count`` 0, and both lists empty. That is one branch in the front end instead
    of two response formats, and it is why the two no-answer paths are byte-identical
    without the serializer having to arrange anything.

    **There is no field for ``no_answer_reason`` and none for ``rejected_count``.** They
    are record-only (``QueryLog``'s docstring), and ``AnswerReply`` carries no value for
    either, so there is nothing here to name — see ``apps.api.answers`` for the
    disclosure this protects against.

    **``partial_matches`` is present on every exit and non-empty only on the two no-answer
    ones**, and it is IDENTICAL on those two by design: the pipeline derives it once from the
    ranked scoped candidates before the threshold, so this field cannot become the one that
    tells a caller which no-answer path ran. It is also the field most likely to be
    "improved" into a leak — a score, a snippet, a count of what was left out — and each of
    those is refused in ``PartialMatchSource``'s docstring rather than here.
    """

    answered = serializers.BooleanField(read_only=True)
    message = serializers.CharField(read_only=True, allow_null=True)
    result_count = serializers.IntegerField(read_only=True)
    statements = AnswerStatementSerializer(many=True, read_only=True)
    sources = ConsultedSourceSerializer(many=True, read_only=True)
    partial_matches = PartialMatchSerializer(many=True, read_only=True)
    # Null for a one-off question. FR-13's Responses clause: "200 OK with the answer and
    # updated conversation state" — the pipeline refreshed ``last_updated_at`` inside the
    # log transaction, so the instance rendered here is already current.
    conversation = ConversationSerializer(read_only=True, allow_null=True)


class ConversationCreateSerializer(serializers.Serializer):
    """``POST /api/conversations`` body. ``title`` is optional; see the view for where an
    omitted one comes from instead (D-43)."""

    title = serializers.CharField(
        max_length=NAME_MAX_LENGTH, required=False, allow_blank=True, trim_whitespace=True
    )


class CitedStatementSerializer(serializers.Serializer):
    """One stored ``AnswerCitation``, rendered exactly as the live answer renders a
    statement, so a reopened thread and the turn as first answered are the same shape.

    Rows exist only for statements that survived verification, so a thread read back from
    the server can no more show an uncited statement than the original reply could. Only
    rows whose chunk still exists and is in the reader's scope reach this serializer
    (``ConversationTurnSerializer.surviving_citations``), so ``chunk_id`` is never null here
    and ``chunk_uuid`` is never rendered (D-67).
    """

    position = serializers.IntegerField(read_only=True)
    text = serializers.CharField(source="statement_text", read_only=True)
    chunk_id = serializers.UUIDField(read_only=True)


# The one place this key is spelled. A test, the API contract and the front end all name the
# same string, and it is a field a body carries only where it is true (Stage 4 item 1c).
PROVENANCE_REMOVED_FIELD = "provenance_removed"


def consulted_chunk_ids(turn) -> list:
    """The chunks a turn consulted, in rank order: its ``retrieved_chunk_ids``, if and only if
    it was STORED as answered (D-78 item 1).

    On an answered row the column is exactly the list the live Sources panel was built from:
    ``answer_question`` records the passages it supplied, in the order it supplied them, and
    the live reply resolved the same passages in the same order (D-44). On a row stored as
    unanswered it is never read, because there ``answered`` and ``len(retrieved_chunk_ids)``
    are what tell no-answer path A from path B (``apps/retrieval/query_log.py``, D-48 item 6),
    and nothing derived from it could reach a reopened no-answer turn without telling the two
    apart. Not reading it is a stronger guarantee than reading it and rendering nothing: the
    thread's scope query is never asked about those identifiers either.
    """
    if not turn.answered:
        return []
    return list(turn.retrieved_chunk_ids)


def readable_thread_chunks(turns, *, role_name) -> dict:
    """The chunks of this thread that the reader's CURRENT role may read, keyed by identifier.

    The one ``scoped_chunks`` query of a thread read (D-78 item 2), over every cited chunk and
    every consulted chunk of a turn stored as answered. Both the surviving citations and the
    Sources panel are derived from this one result, so the two cannot be scoped differently:
    a citation cannot survive on a chunk the panel was told is gone, or the reverse. It is the
    same predicate the answer path and the keyword search run, not a second implementation of
    it. Invariant 3's reasoning is the argument: "a second scoping mechanism would mean two
    code paths through the single filter that matters most", and a thread read returns
    material exactly as much as those two do.

    **The passage text comes from these rows, and from nowhere else.** A chunk that has been
    deleted, re-indexed under a fresh identifier, or restamped out of this role's scope is
    absent from the result, in the same way and for the same reason: this asks the store what
    is readable and takes the answer. There is no stored copy to fall back on (D-67), which is
    what keeps FR-15's promise that deleted material is not surfaced again.

    **A citation whose chunk was deleted has ``chunk_id`` NULL (D-67) and is skipped here**,
    before the query, so NULL is never an identifier that could be readable. Its
    ``chunk_uuid`` is not consulted. The same identifier usually reaches the query anyway,
    through the consulted list, and the store answers for it as it answers for any chunk that
    no longer exists: with nothing.

    Only the four columns a passage needs are fetched. The embedding is the largest column on
    the row and has no use here.
    """
    wanted = {
        citation.chunk_id
        for turn in turns
        for citation in turn.citations.all()
        if citation.chunk_id is not None
    }
    for turn in turns:
        wanted.update(consulted_chunk_ids(turn))
    if not wanted:
        return {}
    rows = (
        scoped_chunks(role_name=role_name)
        .filter(id__in=wanted)
        .only("id", "source_type", "source_id", "chunk_text")
    )
    return {row.id: row for row in rows}


@dataclass(frozen=True)
class ReopenedPassage:
    """A consulted chunk read back for a reopened turn, in the shape ``resolve_sources`` reads.

    ``resolve_sources`` is the live reply's own code (D-78 item 3) and reads four attributes of
    each passage: ``source_type``, ``source_id``, ``chunk_id`` and ``chunk_text``. On the live
    path a ``RankedPassage`` carries them; here a ``ContentChunk`` row does, under one different
    name, so this adapter gives the row that shape rather than the function a second input.

    ``chunk_id`` is ``str(chunk.id)``, the expression ``apps.retrieval.ranking.rank`` uses, so
    a passage identifier renders as the same string on a reopened turn as on the live reply.
    There is no score: nothing on a stored turn records one, and nothing renders one.
    """

    chunk_id: str
    chunk_text: str
    source_type: str
    source_id: UUID

    @classmethod
    def of(cls, chunk) -> "ReopenedPassage":
        return cls(
            chunk_id=str(chunk.id),
            chunk_text=chunk.chunk_text,
            source_type=chunk.source_type,
            source_id=chunk.source_id,
        )


class ConversationTurnSerializer(serializers.Serializer):
    """One logged turn of a thread: the question, whether it was answered, its citations, and
    the sources it consulted.

    The object is a ``QueryLog`` row and its citation rows. ``no_answer_reason`` and
    ``rejected_count`` are never read, for the same reason they are absent from the live
    reply: a reopened thread that showed which no-answer path a turn took would disclose
    across two requests exactly what one request may not (``QueryLog``'s docstring;
    invariant 1). **``retrieved_chunk_ids`` is read for a turn stored as answered, and for no
    other (D-78).** On an answered turn it is part of what the user was shown: it is exactly
    the list the live Sources panel was built from (D-44), every passage supplied to
    generation, cited or not. On a turn stored as unanswered the reply showed nothing of it,
    and its length is what separates no-answer path A from path B, so it is not read at all
    (``consulted_chunk_ids``). It is never a field of a turn.

    ``message`` is derived rather than stored: a turn that was not answered was answered
    with NO_ANSWER_MESSAGE, the one fixed text both no-answer paths return, so
    re-rendering it from ``answered`` cannot leak which path was taken.

    **``sources`` is the live reply's Sources panel, rebuilt (D-78).** Every item the turn
    consulted, in rank order, each with its title, its date and the passages supplied from it,
    so a reopened citation expands to its passage and links to its source as it did when the
    turn was live. It is consulted rather than cited for the reason the live reply gives
    (``apps.api.answers``): FR-12's panel "lists every item consulted", and since D-77 Back
    re-reads the thread, so a cited-only panel would visibly shrink on the citation round trip.
    The entries are built by ``answers.resolve_sources``, the live reply's own code, fed the
    consulted chunks in logged order, so the grouping, the rank order and the fail-closed title
    and date read (D-53) are not a copy that can drift. The passages are the chunk rows from the
    thread's one scope query (``readable_thread_chunks``), which is also what the citations
    survive against. Nothing is snapshotted: a consulted chunk that has since been restricted,
    deleted or re-indexed is simply absent, with no count and no marker, as an out-of-scope
    chunk is absent from retrieval.

    **A STORED ANSWER IS RE-SCOPED HERE, ON EVERY READ.** A turn is a derived record: its
    statements were generated from passages the asker's role admitted at the time, and the
    stored row carries no visibility of its own. If the reader's role has narrowed since —
    or the source's scope has — nothing about the row knows that, so every citation is
    filtered through ``scoped_chunks`` under the role resolved for THIS request and a
    statement whose chunk is no longer permitted is dropped.

    **What is being withheld is the PROSE, and framing it as an identifier understates it by
    an order of magnitude.** It is tempting to say that a turn returns no passage text, so at
    worst a ``chunk_id`` leaks and an identifier is not content. That is wrong. A statement
    generated from an Administrator-only passage carries that passage's substance in natural
    language: "Directors accrue annual leave at twice the ordinary rate" IS the restricted
    fact, written out, and it does not become less so for having been produced by a model
    rather than copied. The identifier is the lesser half of the leak and the sentence is the
    greater one. This is why the statement is removed rather than merely unlinked.

    **A turn that loses every statement renders as the ordinary no-answer state** —
    ``answered`` false, the fixed message, no statements and no sources — which is the state
    item 7 already built and the front end already renders. Its sources go with its
    statements even where a passage it consulted is still readable: a no-answer turn listing
    the items it consulted would be the re-scoped turn telling itself apart. Not a blank
    turn, and emphatically not "content withheld" and not a count of what was removed: a
    notice that something was removed is itself a disclosure that material exists which this
    role may not read, which is the disclosure invariant 1 forbids by name. Nothing here can
    tell the reader whether a turn was re-scoped, whether it hit no-answer path A or B when
    it was live, or whether it was ever answered at all.

    ---

    **THREE STATES, TWO RENDERINGS, AND WHY THE THIRD IS SEPARATED (Stage 4 item 1c).**

    ``answered`` and ``message`` above conflated three distinct states into two renderings.
    Everything argued above holds for the first two and is not weakened by the third:

    1. ``turn.answered`` is False — never answered. The silent no-answer state. Unchanged.
    2. ``turn.answered`` is True, at least one citation row **still points at a chunk that
       exists**, and none of those survives the scope filter — re-scoped. **Byte-for-byte
       identical to state 1**, which is the invariant-1 case argued at length above and the
       reason ``provenance_removed`` is ABSENT from the body rather than present and false: a
       field appearing on a re-scoped turn, whatever its value, is a new place for the notice
       invariant 1 forbids to grow, and the exact-key-set assertions in
       ``apps/api/tests/test_fr11_thread_scope.py`` continue to hold a re-scoped turn to the
       six keys a never-answered one has (five until D-78 added ``sources`` to both at once).
       A turn with some rows whose chunk is gone and some whose chunk exists but is out
       of scope is THIS state, not state 3: the rows whose chunk exists decide it.
    3. ``turn.answered`` is True and **no citation row points at a chunk that still exists**
       — the chunks it cited were deleted. ``reprocess_document`` and ``manage.py reindex``
       delete a source's chunks and write new ones with fresh UUIDs, and FR-15's deletion
       removes them for good. Until D-67 (Stage 5 item 1a) ``AnswerCitation.chunk`` was
       CASCADE and the citation rows went with the chunks; now it is SET_NULL, so the rows
       survive with ``chunk_id`` NULL and ``chunk_uuid`` naming what was cited, for FR-12's
       traceability record. **A NULL-chunk row is read here exactly as a row the cascade had
       deleted**: it is not a citation of anything this reader can be shown, so it neither
       renders nor counts towards state 2. That reproduces the rendering the cascade
       produced, now on purpose. ``apps/api/tests/
       test_fr12_traceability_survives_reprocess.py`` is the row-level record.

    **THE DISCRIMINATOR IS WHETHER ANY CITATION ROW STILL POINTS AT AN EXISTING CHUNK, NEVER
    WHETHER ONE SURVIVED SCOPING, AND THE DIFFERENCE IS THE SECURITY PROPERTY.** It is a fact
    about the record — did a delete reach the chunks this turn cited — and not about the
    reader. State 3 says nothing whatever about permissions: an operation deleted the
    material the record pointed at, and this reader may well have been entitled to every word
    of it. Disclosing "this answer's provenance is gone" therefore reveals nothing about what
    the reader may see, where disclosing a re-scope would reveal exactly that. Someone will be
    tempted to simplify ``not has_live_citation_rows`` into "no surviving citations", because
    in most bodies the two read alike — **that collapses state 2 into state 3 and reopens the
    invariant-1 disclosure**, telling a demoted reader that something was taken out of their
    own thread. The distinction is in the rows and the chunks they point at, read before any
    scope is applied, so the predicate is on those.

    **``answered AND no row pointing at an existing chunk`` cannot happen at write time**,
    which is what makes the discriminator sound rather than a guess.
    ``apps.retrieval.query_log`` writes the ``QueryLog`` row and its ``AnswerCitation`` rows in
    one transaction, every one with ``chunk_id`` set, and the database foreign key refuses an
    identifier that names no chunk. It says why: "a row recorded as answered with no citation
    rows beneath it would be a traceability record that traces to nothing". So the state is
    unreachable except by a later deletion of the chunks, which leaves NULL behind, or of the
    rows themselves.

    **What state 3 renders.** No statements — invariant 6 stands, and a statement without its
    citation is exactly what it forbids; a NULL-chunk row's ``statement_text`` is never read
    into a body. No sources either, even where a passage the turn consulted but did not cite
    is still in the corpus: a panel under a turn with no answer is the panel of nothing. But
    **not** NO_ANSWER_MESSAGE, which says the question cannot be answered
    from the available knowledge base: that is untrue of a turn that was answered from
    material a re-index left in the corpus, and a false statement about the corpus is the
    interface lying to the user rather than protecting them.
    ``PROVENANCE_REMOVED_MESSAGE`` says what happened to the record, and
    ``provenance_removed`` is the boolean the client branches on so it never has to parse
    prose. No count of anything removed, in either state.

    **Surviving statements are renumbered from FIRST_POSITION**, for the same reason: a turn
    rendered as "[1] ... [3] ..." announces that [2] was taken out. Where nothing is dropped
    the renumbering is the identity, so an ordinary thread read is byte-for-byte what it was.

    **Re-scoping on read, rather than re-writing the rows when a role or a scope changes.**
    The scope is re-resolved per request everywhere else in this system — ``permission_scope``
    re-reads the role from the users table on every turn, D-21 caches nothing in the session —
    and FR-13's Validation clause already requires that a follow-up "cannot inherit access the
    user no longer holds". A thread read is that principle one step on: the same thread, read
    twice by the same person across a demotion, must not still show what the first read did.
    Re-writing stored citations on a role change would instead destroy the FR-19 evidence of
    what was actually answered, and would have to be re-run for every role and every source
    whose scope ever moves.
    """

    question = serializers.CharField(read_only=True)
    answered = serializers.SerializerMethodField()
    asked_at = serializers.DateTimeField(source="answered_at", read_only=True)
    message = serializers.SerializerMethodField()
    statements = serializers.SerializerMethodField()
    # On every turn, so the answered and the no-answer bodies change together (D-78).
    sources = serializers.SerializerMethodField()
    # Present only where it is true; see ``to_representation`` for why, and state 2 in the
    # class docstring for why that is not tidiness.
    provenance_removed = serializers.SerializerMethodField()

    def has_live_citation_rows(self, turn):
        """Whether any of this turn's ``AnswerCitation`` rows still points at a chunk, before
        any scoping.

        The whole of the state 2 / state 3 distinction, and deliberately not expressed in
        terms of ``surviving_citations``: this asks whether the record still points at
        material that EXISTS, that asks whether this reader may see it, and conflating them
        is the disclosure the class docstring describes. A row whose ``chunk_id`` is NULL
        (D-67) does not count, which is what makes it behave as the row CASCADE used to
        delete. ``chunk_id`` not NULL means the chunk exists: the database foreign key
        refuses any other value. Reads the prefetched rows, so no query of its own.
        """
        return any(citation.chunk_id is not None for citation in turn.citations.all())

    def surviving_citations(self, turn):
        """This turn's citations the reader may still see, in the order they were numbered.

        ``readable_chunks`` is the thread's one scope result (``readable_thread_chunks``),
        read from the context with no default, so a caller that renders turns without
        supplying it raises rather than returning a body. Both available defaults are wrong:
        permitting everything is precisely the leak, and permitting nothing would render
        every thread in the system as no-answer and look like a retrieval problem for as
        long as it took someone to find. ``get_sources`` reads the same mapping, which is
        what keeps a surviving citation and the panel it expands into from disagreeing.

        A row whose chunk was deleted (``chunk_id`` NULL, D-67) is never returned, whatever
        ``readable_chunks`` holds: it is excluded by name rather than by NULL happening
        not to be a key, so a later change to how that mapping is built cannot let one
        through. Its statement is not shown and does not take a number.
        """
        readable = self.context["readable_chunks"]
        citations = sorted(turn.citations.all(), key=lambda citation: citation.position)
        return [
            citation
            for citation in citations
            if citation.chunk_id is not None and citation.chunk_id in readable
        ]

    def get_answered(self, turn):
        # Answered when it was answered AND something it said is still readable. The two
        # conditions are one fact for the reader: an answer they can be shown.
        return bool(turn.answered) and bool(self.surviving_citations(turn))

    def get_provenance_removed(self, turn):
        """State 3, and nothing else: answered, and no citation row of it still points at a
        chunk that exists.

        False for a re-scoped turn, at least one of whose rows still points at an existing
        chunk that is merely unreadable by this role — including a turn where the other rows'
        chunks were deleted — and false for a turn that was never answered.
        """
        return bool(turn.answered) and not self.has_live_citation_rows(turn)

    def get_message(self, turn):
        if self.get_answered(turn):
            return None
        if self.get_provenance_removed(turn):
            # NO_ANSWER_MESSAGE here would tell the reader their question cannot be answered
            # from the knowledge base, which is a claim about the corpus: it was answered, and
            # what is gone is the chunks it cited. See PROVENANCE_REMOVED_MESSAGE for the
            # paths that reach this state and why the message promises nothing about them.
            return PROVENANCE_REMOVED_MESSAGE
        return NO_ANSWER_MESSAGE

    def to_representation(self, turn):
        """The body, with ``provenance_removed`` omitted unless it is true.

        **The omission is the state 2 guarantee, not neatness.** A re-scoped turn must be
        indistinguishable from a never-answered one, and the cheapest way to guarantee that
        for a new field is for the field not to be in the body at all: nothing to compare,
        nothing for a future serializer to make conditional on scope, and the exact-key-set
        assertions that already guard invariant 1 keep guarding it without being relaxed to
        admit a key. The client branch is unaffected — an absent key and ``false`` are the
        same test in JavaScript — and the message is the field a reader sees either way.
        """
        body = super().to_representation(turn)
        if not body[PROVENANCE_REMOVED_FIELD]:
            del body[PROVENANCE_REMOVED_FIELD]
        return body

    def get_statements(self, turn):
        if not self.get_answered(turn):
            # The no-answer state, whether this turn was never answered or has just lost
            # every statement it had. One branch, so the two are indistinguishable.
            return []
        surviving = self.surviving_citations(turn)
        for position, citation in enumerate(surviving, start=FIRST_POSITION):
            # Contiguous numbering, in memory only — these instances are never saved, and
            # the stored position stays what the original reader saw. A gap in the numbers
            # would be the "something was removed" notice this must not give.
            citation.position = position
        return CitedStatementSerializer(surviving, many=True).data

    def get_sources(self, turn):
        """FR-12's Sources panel for this turn, as the live reply built it (D-78).

        Built only for a turn that RENDERS as answered, behind the same branch as
        ``get_statements``. A never-answered turn, a re-scoped one and a provenance-removed one
        carry ``[]``: the second must stay byte for byte the first, and a panel beside a turn
        that shows no answer would be the difference.

        The consulted chunks are taken from the thread's one scope result in the order the
        turn logged them, which is rank order, and handed to ``resolve_sources`` — the live
        reply's own grouping, ordering and fail-closed source read (D-53), resolved for the
        reader of this request. A consulted chunk missing from the result is skipped without
        a placeholder, so nothing in the body counts or marks what dropped.
        """
        if not self.get_answered(turn):
            return []
        readable = self.context["readable_chunks"]
        consulted = [
            ReopenedPassage.of(readable[chunk_id])
            for chunk_id in consulted_chunk_ids(turn)
            if chunk_id in readable
        ]
        sources = resolve_sources(consulted, user=self.context["request"].user)
        return ConsultedSourceSerializer(sources, many=True).data


class ConversationDetailSerializer(ConversationSerializer):
    """A thread and its turns, so FR-13's "previous conversations ... can be reopened"
    renders from the server rather than from whatever the browser still holds.

    The turns are read here rather than prefetched by the view, so the turn ordering and
    the citation ordering live beside the fields that use them. A read costs two queries for
    the turns and their citations, one for the reader's role and one ``scoped_chunks`` query
    for the whole thread, at a thread length bounded by how much one person types. Each turn
    that renders as answered then costs what ``answers.resolve_sources`` costs on the live
    reply: the role re-read and one query per source type it consulted, so three at most
    (D-78). A thread with no answered turn makes no chunk query at all.

    **The reader's role is resolved here, from the request, not passed in by the view.**
    ``permission_scope`` re-reads it from the users table for this request (D-21 caches
    nothing in the session), and taking the user rather than a role name means there is no
    role argument for a view to miswire — the argument ``apps/api/views.py``'s search view
    makes for ``apps.retrieval.search`` doing its own resolution. ``UnscopedRequestError`` is
    not caught, as on every other route: behind ``IsAuthenticated`` it is unreachable, and
    rendering a thread whose scope could not be established is the one thing worse than
    raising.

    ``title`` needs no re-scoping. It is either what the user typed or their own first
    question, truncated (D-43) — their words, kept for the same reason D-42 keeps prior
    questions — so nothing in it was derived from a passage.
    """

    turns = serializers.SerializerMethodField()

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ("turns",)
        read_only_fields = fields

    def get_turns(self, conversation):
        turns = list(
            conversation.queries.prefetch_related("citations").order_by(
                # Chronological, with the primary key as a deterministic tie-break only: it
                # is a random UUID and says nothing about time, but two turns sharing a
                # microsecond would otherwise order arbitrarily between reads. The ordering
                # apps/retrieval/conversation.py reads history with, reversed.
                "answered_at",
                "id",
            )
        )
        role_name = permission_scope(self.context["request"].user)
        return ConversationTurnSerializer(
            turns,
            many=True,
            context={
                **self.context,
                # One scope query for the whole thread, not one per turn, and the only one:
                # the citations and the Sources panels are both derived from it (D-78).
                "readable_chunks": readable_thread_chunks(turns, role_name=role_name),
            },
        ).data


# --- FR-14 dashboard ----------------------------------------------------------------------

# The one cross-field rule D-65 sets for a date range. Keyed on ``date_to`` in the 400 body: the
# end date is the one checked against the start, and the dashboard screen's own copy of this
# check (frontend/src/pages/Dashboard.jsx) shows its message under the same control, so the
# two agree about where the error is.
DATE_RANGE_REVERSED_MESSAGE = "The end date must be on or after the start date."


class DashboardQuerySerializer(serializers.Serializer):
    """``GET /api/dashboard``'s query parameters, read only through this (D-65).

    The view hands it ``request.query_params`` as ``data=`` and uses ``validated_data`` alone,
    so a NUL byte or an over-long value is a 400 at the boundary and never reaches an ORM
    lookup: ``CharField`` carries ``ProhibitNullCharactersValidator``, and a NUL byte is not a
    valid date.

    **Every parameter is optional, and an empty value is the same as an absent one**
    (docs/api-contract.md). Each field defaults to ``None``, which the view reads as "not
    applied". For the two dates DRF already does this with form-style input: ``date_from=``
    on a field that is not required is treated as omitted, so it takes the default rather
    than failing as a malformed date. ``department`` allows a blank value, after trimming,
    and ``validate_department`` turns it into ``None``, so ``department=`` and
    ``department=%20`` narrow nothing.

    **``department`` is validated for shape and never looked up** (D-65, D-70). A field that
    checked the value against the documents table would answer differently for a department
    that does not exist and one used only on documents the caller cannot see, and the
    difference would disclose the restricted ones. Both reach the query and match nothing the
    caller may see.

    **The date range is inclusive at both ends** (D-65). The view compares a timestamp by its
    date in ``TIME_ZONE`` (Australia/Melbourne) with ``__date__gte`` / ``__date__lte``, and
    ``meeting_date``, already a date, directly (D-70).
    """

    date_from = serializers.DateField(required=False, default=None)
    date_to = serializers.DateField(required=False, default=None)
    department = serializers.CharField(
        max_length=NAME_MAX_LENGTH, required=False, default=None, allow_blank=True
    )

    def validate_department(self, value):
        # ``None`` when absent, ``""`` when sent empty or blank: neither narrows anything.
        return value or None

    def validate(self, attrs):
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from is not None and date_to is not None and date_from > date_to:
            raise serializers.ValidationError({"date_to": [DATE_RANGE_REVERSED_MESSAGE]})
        return attrs


class RecentQuestionSerializer(serializers.Serializer):
    """One of the caller's own recent questions on the dashboard: the question only (D-68).

    Three fields and no more. ``answer_text`` was generated under the role the asker held at
    the time, from passages that may since have left their scope (D-48's instance 3);
    ``answered`` has to be re-derived from surviving citations rather than trusted (D-48's
    instance 7); ``no_answer_reason`` and ``rejected_count`` are record-only (D-55, and
    ``QueryLog``'s docstring). None of them is declared here, and the view reads the three
    columns below with ``.values()``, so the others are never selected from the database at
    all.

    ``asked_at`` is ``QueryLog.answered_at``, which is written when the question is logged
    whether or not it was answered (D-70), and is named for what it means to the person who
    asked. Rendered by DRF's own ``DateTimeField``, so it carries the same Melbourne offset as
    a document's ``uploaded_at``.
    """

    question = serializers.CharField(read_only=True)
    asked_at = serializers.DateTimeField(source="answered_at", read_only=True)
    # Null for a one-off question with no thread (D-68).
    conversation_id = serializers.UUIDField(read_only=True, allow_null=True)


# --- FR-15 document repository ------------------------------------------------------------


class _TrimmedChoiceField(serializers.ChoiceField):
    """A ``ChoiceField`` that trims surrounding spaces before matching the vocabulary.

    docs/api-contract.md says every browse parameter "is trimmed of surrounding spaces first",
    and DRF trims a ``CharField`` but not a ``ChoiceField``. Without this, ``status=%20`` would be
    400 where ``department=%20`` means "not applied". The vocabulary itself is still the only
    thing accepted: a value is matched exactly, case included, after the trim.
    """

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.strip()
        return super().to_internal_value(data)


def _optional_text():
    """A free-text browse parameter: optional, blank allowed, trimmed, at most 255 characters.

    Shape only (D-65). ``CharField`` carries ``ProhibitNullCharactersValidator``, so a NUL byte is
    a 400 here and never reaches an ORM lookup.
    """
    return serializers.CharField(
        max_length=NAME_MAX_LENGTH, required=False, default=None, allow_blank=True
    )


class DocumentBrowseQuerySerializer(serializers.Serializer):
    """``GET /api/documents/browse``'s query parameters, read only through this (D-65).

    **Every parameter is optional, and an empty or blank value is the same as an absent one**
    (docs/api-contract.md): each filter validates to ``None`` when not applied, and ``sort`` to
    ``DEFAULT_DOCUMENT_SORT``. ``data`` echoes those applied values back as the reply's
    ``filters``, as FR-14's serializer does.

    - ``status`` and ``sort`` are fixed vocabularies from ``apps/core/constants.py``, read through
      a ``ChoiceField``: anything else, a NUL byte included, is a 400 keyed on the parameter.
    - ``q`` and ``department`` are checked for shape only and kept as sent, trimmed. ``q`` is
      matched with whitespace collapsed (D-71), which is a property of the match rather than of
      the value, so it is echoed uncollapsed.
    - ``project``, ``process`` and ``topic`` are tag names, normalised exactly as ``Tag.save``
      normalises them (``normalise_tag_name``: lower case, single spaces), so ``Supplier  Review``
      finds the tag stored as ``supplier review``. They are echoed normalised, because that is the
      value applied.

    **No value is ever looked up.** A department or tag that does not exist and one used only on
    documents the caller cannot see must give the same answer, FR-15's 204; a field that checked
    for existence would answer 400 for one and 204 for the other, and the difference would
    disclose the restricted one (D-65). 400 for a malformed parameter is this API's convention,
    not one of FR-15's codes.
    """

    q = _optional_text()
    status = _TrimmedChoiceField(
        choices=DOCUMENT_STATUS_VALUES, required=False, default=None, allow_blank=True
    )
    department = _optional_text()
    project = _optional_text()
    process = _optional_text()
    topic = _optional_text()
    sort = _TrimmedChoiceField(
        choices=DOCUMENT_SORT_VALUES, required=False, default=DEFAULT_DOCUMENT_SORT,
        allow_blank=True,
    )

    def validate_q(self, value):
        return value or None

    def validate_status(self, value):
        return value or None

    def validate_department(self, value):
        return value or None

    def validate_project(self, value):
        return normalise_tag_name(value) if value else None

    def validate_process(self, value):
        return normalise_tag_name(value) if value else None

    def validate_topic(self, value):
        return normalise_tag_name(value) if value else None

    def validate_sort(self, value):
        return value or DEFAULT_DOCUMENT_SORT
