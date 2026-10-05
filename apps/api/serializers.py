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
from apps.core.constants import NO_ANSWER_MESSAGE, PROVENANCE_REMOVED_MESSAGE, ROLE_NAMES
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import Document
from apps.meetings.models import Meeting
from apps.retrieval.models import Conversation
from apps.retrieval.query_log import FIRST_POSITION
from apps.retrieval.scoping import permission_scope, scoped_chunks

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
    MAXIMUM_QUESTION_LENGTH are enforced by ``answer_question``, which raises
    ``QuestionLengthOutOfRange``; the view maps that exception to FR-12's 400. Declaring
    ``min_length`` here would be a second definition of "too short" that could drift from
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


def permitted_citation_chunk_ids(turns, *, role_name) -> frozenset:
    """Which of these turns' cited chunks the reader's CURRENT role may still see.

    One query for the whole thread, and it is ``scoped_chunks`` — the same predicate the
    answer path and the keyword search run, not a second implementation of it. Invariant 3's
    reasoning is the argument: "a second scoping mechanism would mean two code paths through
    the single filter that matters most", and a thread read is a route that returns material
    exactly as much as those two are. A chunk that has been deleted, or whose stamp is now an
    empty array, is absent from the result for the same reason a restricted one is: this asks
    the store what is readable and takes the answer, rather than deciding anything itself.

    **A citation whose chunk was deleted has ``chunk_id`` NULL (D-67) and is skipped here**,
    before the query, so NULL is never an identifier that could be "permitted". Its
    ``chunk_uuid`` is not consulted either: that names a chunk that no longer exists, and
    asking the store about it could only ever return nothing.
    """
    cited = {
        citation.chunk_id
        for turn in turns
        for citation in turn.citations.all()
        if citation.chunk_id is not None
    }
    if not cited:
        return frozenset()
    return frozenset(
        scoped_chunks(role_name=role_name).filter(id__in=cited).values_list("id", flat=True)
    )


class ConversationTurnSerializer(serializers.Serializer):
    """One logged turn of a thread: the question, whether it was answered, its citations.

    The object is a ``QueryLog`` row, and only four of its columns are read.
    ``no_answer_reason`` and ``rejected_count`` are not among them, for the same reason
    they are absent from the live reply: a reopened thread that showed which no-answer
    path a turn took would disclose across two requests exactly what one request may not
    (``QueryLog``'s docstring; invariant 1). ``retrieved_chunk_ids`` is not read either —
    it is the traceability record of what was put in front of the model, including
    passages nothing cited, and it is not part of what the user was shown.

    ``message`` is derived rather than stored: a turn that was not answered was answered
    with NO_ANSWER_MESSAGE, the one fixed text both no-answer paths return, so
    re-rendering it from ``answered`` cannot leak which path was taken.

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
    ``answered`` false, the fixed message, an empty list — which is the state item 7 already
    built and the front end already renders. Not a blank turn, and emphatically not "content
    withheld" and not a count of what was removed: a notice that something was removed is
    itself a disclosure that material exists which this role may not read, which is the
    disclosure invariant 1 forbids by name. Nothing here can tell the reader whether a turn
    was re-scoped, whether it hit no-answer path A or B when it was live, or whether it was
    ever answered at all.

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
       ``apps/api/tests/test_fr11_thread_scope.py`` continue to hold a re-scoped turn to five
       keys. A turn with some rows whose chunk is gone and some whose chunk exists but is out
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
    into a body. But **not** NO_ANSWER_MESSAGE, which says the question cannot be answered
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

        ``permitted_chunk_ids`` is read from the context with no default, so a caller that
        renders turns without supplying it raises rather than returning a body. Both
        available defaults are wrong: permitting everything is precisely the leak, and
        permitting nothing would render every thread in the system as no-answer and look
        like a retrieval problem for as long as it took someone to find.

        A row whose chunk was deleted (``chunk_id`` NULL, D-67) is never returned, whatever
        ``permitted_chunk_ids`` holds: it is excluded by name rather than by NULL happening
        not to be in a set, so a later change to how that set is built cannot let one
        through. Its statement is not shown and does not take a number.
        """
        permitted = self.context["permitted_chunk_ids"]
        citations = sorted(turn.citations.all(), key=lambda citation: citation.position)
        return [
            citation
            for citation in citations
            if citation.chunk_id is not None and citation.chunk_id in permitted
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


class ConversationDetailSerializer(ConversationSerializer):
    """A thread and its turns, so FR-13's "previous conversations ... can be reopened"
    renders from the server rather than from whatever the browser still holds.

    The turns are read here rather than prefetched by the view, so the turn ordering and
    the citation ordering live beside the fields that use them: two queries per read, at a
    thread length bounded by how much one person types, plus one for the scope.

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
                # One scope query for the whole thread, not one per turn.
                "permitted_chunk_ids": permitted_citation_chunk_ids(
                    turns, role_name=role_name
                ),
            },
        ).data
