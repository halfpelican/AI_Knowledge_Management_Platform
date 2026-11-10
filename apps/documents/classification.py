"""FR-10's apply layer: the scheme a document is classified against, and what becomes of the
model's suggestions (docs/decisions.md D-105).

``AIService.classify_document`` (apps/ai/classification.py) returns a ``DocumentClassification``:
the model's suggestions AS MADE, with nothing decided. Everything FR-10's Server-End calls
business logic is decided here, in application code over those suggestions, and never by the
model:

- **confidence** — "a confidence value is recorded with each assignment. Assignments below the
  configured threshold are marked provisional and presented for confirmation rather than applied
  silently." ``CLASSIFICATION_CONFIDENCE_THRESHOLD`` is compared in one place, ``_is_provisional``.
- **controlled taxonomy growth** — "suggested tags are matched against values already held in the
  scheme. A value that does not match may be proposed only in the Topic dimension and requires
  user confirmation before it is created; suggestions falling outside the scheme in the
  Department, Project or Process dimensions are discarded." Rules 3 and 4 of
  ``apply_classification``.
- **provenance** — an AI link is ``applied_by="ai"`` and unconfirmed; a person's ``confirm_tag``
  marks it confirmed and ``reject_tag`` removes it ("either may be accepted or removed in a single
  action"). A person applies a tag of their own with ``apply_tag``, ``applied_by="user"`` (UC-09
  A3: a person "adds one it did not"). ``DocumentAnalysis.department_applied_by`` says, in the same
  vocabulary, whose value the document's department is.
- **correction** — "any value a user edits [is] retained and is not overwritten by later
  reprocessing, and the machine assignment is retained alongside it":
  ``DocumentAnalysis.user_edited`` guards the effective type, ``Documents.department`` and the two
  outcomes, while the ``machine_*`` columns take every run's values. A confirmed tag "is not
  altered by later reprocessing". A removed AI tag is kept, marked ``removed``, with the machine's
  confidence, and later reprocessing neither links it again nor alters it (D-105's dated note of
  10 November 2026, night).

**The scheme is built for the document's own audience** (``tag_scheme``), so a suggestion can
never name a value that exists only on material some reader of this document may not see
(CLAUDE.md invariant 1).

**What this module does not do.** It calls the provider only in ``classify_document_now``; it
decides no status code (the route and the ingestion hook map the exceptions below); and it never
resolves a ``Document`` for a caller: every function takes one the caller already reached through
``scoped_documents`` (D-46, D-53). It lives in ``apps/documents`` beside ``deletion.py``, outside
the request-serving packages ``apps/api/tests/test_source_rows_fail_closed.py`` scans, for the
reason that module gives: it reads managers directly, for writes against a row already resolved
and for the vocabulary tables.
"""

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

import apps.ai
from apps.ai.base import DocumentClassification, TagScheme
from apps.core.constants import (
    AI_APPLIED,
    ASSIGNMENT_APPLIED,
    ASSIGNMENT_CONFIRMED,
    ASSIGNMENT_DISCARDED,
    ASSIGNMENT_PROVISIONAL,
    CLASSIFICATION_CONFIDENCE_THRESHOLD,
    DOCUMENT_TYPES,
    REPOSITORY_TAG_DIMENSIONS,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import ContentTag, Document, DocumentAnalysis, Tag, normalise_tag_name
from apps.retrieval.scoping import scoped_documents, scoped_meetings

logger = logging.getLogger(__name__)

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES

# The confidence columns are decimal(4,3). The provisional rule compares the value the model
# reported, never this three-place rendering of it (see _is_provisional).
_CONFIDENCE_PLACES = Decimal("0.001")


# --- Exceptions: the caller decides the status code --------------------------------------------


class ClassificationError(Exception):
    """Base of what this module raises. The ingestion hook must catch it as a whole, with
    ``ProviderUnavailable``, so that no classification failure can fail an ingestion
    (CLAUDE.md invariant 8, D-33 part 1)."""


class InsufficientText(ClassificationError):
    """The document has no extracted text to classify. FR-10 Responses: "422 Unprocessable
    Entity where insufficient text was extracted"."""


class InvalidClassification(ClassificationError):
    """A value outside its fixed list or its column. The route answers 400."""


class NotOnThisDocument(ClassificationError):
    """The tag link, proposed topic or analysis named is not this document's. The route answers
    404, the same answer as for a document outside the caller's scope (D-46)."""


class TagNotOffered(ClassificationError):
    """``apply_tag``'s ``tag_id`` names no tag in this document's scheme: unknown, inactive, outside
    the three dimensions, or carried only by material some reader of the document may not see. The
    route answers one 400 with one body for every one of them, so the answer cannot tell a tag that
    does not exist from one the caller may not know of (CLAUDE.md invariant 1)."""


class TopicAlreadyOffered(ClassificationError):
    """``apply_tag``'s new Topic name is an active Topic already in this document's scheme: FR-10
    Responses, "409 Conflict on a duplicate tag name within a dimension". ``tag_id`` is that Topic,
    which ``tag_options`` already offers this document's readers, so naming it discloses nothing."""

    def __init__(self, tag_id):
        super().__init__("A Topic with this name is already offered for this document.")
        self.tag_id = tag_id


@dataclass(frozen=True)
class AppliedTag:
    """What ``apply_tag`` did: the link, and whether it is a new one (the route's 201) or an
    existing one confirmed, restored or left as it was (its 200)."""

    link: ContentTag
    created: bool


# --- The scheme ----------------------------------------------------------------------------------


def tag_scheme(document: Document) -> TagScheme:
    """The established scheme ``document`` is classified against: only values its own audience
    may read.

    **The rule, stated so that it can be checked against the code below.** The audience is every
    role in ``document.visible_to_roles``. A tag is in the scheme if it is **not grown**, whatever its
    links, or if EVERY role in the audience can read at least one source carrying it. So the prompt,
    and therefore any suggestion it produces, can never name a grown value that exists only on
    material some reader of this document may not see (CLAUDE.md invariant 1: the existence of
    out-of-scope material "must not be disclosed"), and nothing a reader can see moves when links on
    material they cannot read are made or destroyed, but for one open exception ``tag_options``
    states. Whether a role can read a source is decided by ``scoped_documents`` and
    ``scoped_meetings`` from apps/retrieval/scoping.py, the one place the FR-11 predicate is written
    (D-53, D-66); nothing here tests ``visible_to_roles`` itself.

    - ``doc_types`` is DOCUMENT_TYPES: a fixed list that says nothing about the corpus.
    - ``departments`` is the intersection, across the audience, of the distinct non-blank
      ``Documents.department`` values of the documents each role may read. A department carried
      only by documents some role in the audience cannot read is withheld.
    - ``tags`` holds, for each of REPOSITORY_TAG_DIMENSIONS, the active ``Tag`` names admitted by
      the rule above.
    - **A tag that is not grown is vocabulary** and is in every scheme, unlinked, carried only by
      restricted material, or carried by readable material alike: its presence says nothing about
      any source, and no link anyone makes or destroys moves it, but for one open exception
      (``tag_options`` states it; D-105's dated note of 10 November 2026, night: the security
      review of ``84b5771``). Until then the scheme read every link of a tag that was not grown,
      links no reader of the document can see included, so a seeded value vanished from an
      Employee's options exactly when Administrator-only material still carried it: when an
      Employee removed its readable person links, when restricted material took it up, or, the
      other way round, when an Administrator removed the only restricted links.
    - **A grown tag is in only where every role in the audience reads a source carrying it**:
      documents through ``scoped_documents``, meetings through ``scoped_meetings``, since the join
      table admits both source types. Every link counts, provisional, unconfirmed and removed ones
      included: a held suggestion, or one a person removed, on a readable document is still a
      carrier. ``grown`` is set on the Topic a person's name brings into use (``apply_tag``'s name
      form, ``confirm_proposed_topic``: the lead's oracle review), and by ``documents 0011`` and
      the seed script's linked mode on every tag carried only by material some role cannot read.

    **An empty audience gets the full scheme.** A document whose ``visible_to_roles`` is empty is
    readable by nobody (``scoped_*`` fail closed), so there is no reader to protect. D-29 refuses
    an empty list at upload, so this arises only from direct row edits.

    **The scheme is built for the audience at classification time.** A document later widened to
    more roles keeps the values it was classified against; widening should reclassify.

    **A role name scoping does not know** (one missing from EFFECTIVE_ROLES) reads nothing, so
    every grown tag and every department is withheld from a document it is in the audience of, as
    ``scoped_documents`` fails closed. Vocabulary, a tag that is not grown, is still in: it says
    nothing about any source, so there is nothing for that reader to be kept from.
    """
    audience = list(dict.fromkeys(document.visible_to_roles))  # distinct, in order
    active_tags = Tag.objects.filter(
        active=True, dimension__in=REPOSITORY_TAG_DIMENSIONS
    ).values_list("id", "dimension", "tag_name", "grown")

    if audience:
        departments: set[str] | None = None
        readable_tag_ids: set | None = None
        for role_name in audience:
            documents = scoped_documents(role_name=role_name)
            meetings = scoped_meetings(role_name=role_name)
            role_departments = set(
                documents.exclude(department="").values_list("department", flat=True).distinct()
            )
            role_tag_ids = set(
                ContentTag.objects.filter(
                    Q(source_type=DOCUMENT_SOURCE_TYPE, source_id__in=documents.values("id"))
                    | Q(source_type=MEETING_SOURCE_TYPE, source_id__in=meetings.values("id"))
                ).values_list("tag_id", flat=True)
            )
            departments = (
                role_departments if departments is None else departments & role_departments
            )
            readable_tag_ids = (
                role_tag_ids if readable_tag_ids is None else readable_tag_ids & role_tag_ids
            )

        def admitted(tag_id, grown) -> bool:
            # Vocabulary is in whatever its links; a grown tag only on a source every role reads.
            # Links on material some reader cannot see are never consulted for vocabulary, so making
            # or destroying them moves nothing a reader of this document is offered.
            return not grown or tag_id in readable_tag_ids

    else:
        departments = set(
            Document.objects.exclude(department="").values_list("department", flat=True).distinct()
        )

        def admitted(tag_id, grown) -> bool:
            return True

    names = {dimension: [] for dimension in REPOSITORY_TAG_DIMENSIONS}
    for tag_id, dimension, tag_name, grown in active_tags:
        if admitted(tag_id, grown):
            names[dimension].append(tag_name)
    return TagScheme(
        doc_types=tuple(DOCUMENT_TYPES),
        departments=tuple(sorted(departments)),
        tags={dimension: tuple(sorted(values)) for dimension, values in names.items()},
    )


def offered_tags(document: Document) -> dict:
    """``tag_scheme(document)``'s tags with their ids, keyed ``(dimension, tag_name)``: exactly the
    values the scheme admits, no more, because the names are taken from the scheme and only then
    matched to their active Tag rows (a name is unique within a dimension)."""
    scheme = tag_scheme(document)
    names = {(dimension, name) for dimension, values in scheme.tags.items() for name in values}
    rows = Tag.objects.filter(active=True, dimension__in=REPOSITORY_TAG_DIMENSIONS).values_list(
        "id", "dimension", "tag_name"
    )
    return {(dimension, name): tag_id for tag_id, dimension, name in rows if (dimension, name) in names}


def tag_options(document: Document) -> dict[str, list[dict]]:
    """What a person may apply to ``document``: ``{dimension: [{"tag_id", "tag_name"}, ...]}`` for
    Project, Process and Topic, each sorted by name. The detail route carries it (D-105's dated
    note of 10 November 2026, night), so the interface offers the existing values to choose from.

    **Why it discloses nothing to anyone who may read the document.** It is ``tag_scheme``'s tags
    and nothing else (``offered_tags``), and the detail route reaches it only after
    ``scoped_documents`` admitted the document for the caller (D-46), so ``visible_to_roles``
    overlaps the effective roles of the caller's role: some audience role R is one the caller's
    role reads. ``tag_scheme`` admits a grown tag only if EVERY audience role, R included, can read
    a source carrying it, and EFFECTIVE_ROLES is closed under generalisation (each role reads its
    own, and an Administrator also reads all an Employee reads, D-66; apps/core/tests/
    test_constants.py asserts the closure), so what R reads, the caller reads: every grown value
    offered is on a source the caller could open. A tag that is not grown is vocabulary (D-105):
    its name is offered to every reader, and its being offered says nothing about any source. An
    inactive tag is never offered. A document with an empty audience would get the full scheme, but
    ``scoped_*`` fail closed on it, so no caller ever reaches its detail.

    **What can appear or disappear, stated rather than glossed** (D-105's dated note of 10 November
    2026, night: the security review of ``84b5771``):

    - **A grown tag appears** when a source every audience role reads comes to carry it, and
      **disappears** when the last such link is removed or that source is deleted. Links on
      material some reader cannot see neither add nor remove it.
    - **A tag that is not grown never moves** while it is active: no link anyone makes or destroys,
      on readable material or restricted, changes whether it is offered. It leaves only when an
      Administrator retires or deletes it (``DELETE /api/tags/{id}``), and a retired Topic a person
      brings back by name returns grown (``apply_tag``, ``confirm_proposed_topic``).
    - **One exception, open** (D-105's dated note): ``confirm_proposed_topic`` grows the Topic it
      fetches even when it is active and not grown. That needs a proposal still pending for a name
      that became vocabulary after it was proposed, since the machine links a vocabulary Topic
      rather than proposing it, and no route of today's code makes one. The seed script creating
      that Topic after the proposal does, and so does a Topic a person brought in by name on another
      document before ``documents 0010``, which 0011 left as vocabulary because a source every role
      reads carries it. Confirmed on restricted material, the Topic is grown, so it leaves an
      audience's options once no source that whole audience reads carries it, where vocabulary
      would have stayed.
    - So the names of every active tag that is not grown are offered to every reader: the values a
      database is seeded with, and those vocabulary values restricted material has taken up since.
      That is what vocabulary means here. The classification prompt lists the same names; before
      the security review it listed only the unlinked ones and those a readable source carried.
    """
    options = {dimension: [] for dimension in REPOSITORY_TAG_DIMENSIONS}
    for (dimension, name), tag_id in sorted(offered_tags(document).items(), key=lambda item: item[0][1]):
        options[dimension].append({"tag_id": str(tag_id), "tag_name": name})
    return options


# --- Classify now: the orchestration the ingestion hook and the route call ----------------------


def classify_document_now(document: Document) -> DocumentAnalysis:
    """Classify ``document`` from its extracted text, then apply the result.

    Reads the document's latest ``ExtractedContent`` (newest by ``extracted_at``, the primary key
    breaking a tie, as apps/api/repository.py and ``manage.py reindex`` read it), builds the
    scheme ONCE, sends both to the provider, and applies the reply against that same scheme, so
    what the model was shown and what its suggestions are matched against cannot differ.

    Raises ``InsufficientText`` when there is no extracted text, before any provider call: the
    route answers 422 "insufficient text was extracted". ``ProviderUnavailable`` propagates from
    the service after MAXIMUM_CLASSIFY_ATTEMPTS, and the caller decides: ingestion leaves the
    document unclassified and indexed (invariant 8), the route answers 503.

    The service is looked up on the ``apps.ai`` module at call time, as
    apps/ingestion/embedding.py and apps/retrieval/pipeline.py do, so the suite's stub applies
    (docs/ai-provider.md section 6).
    """
    text = (
        document.extracted_contents.order_by("-extracted_at", "pk")
        .values_list("extracted_text", flat=True)
        .first()
    )
    if text is None or not text.strip():
        raise InsufficientText("No text was extracted from this document.")
    scheme = tag_scheme(document)
    service = apps.ai.get_ai_service()
    classification = service.classify_document(document.title, text, scheme)
    return apply_classification(document, classification, scheme=scheme)


# --- Apply ---------------------------------------------------------------------------------------


def apply_classification(
    document: Document, classification: DocumentClassification, *, scheme: TagScheme
) -> DocumentAnalysis:
    """Turn ``classification`` into records, in one transaction (a savepoint inside a caller's).

    ``scheme`` must be the scheme the prompt was built from. The rules, in order:

    1. The analysis row is fetched or created (one per document), and the machine's values —
       ``machine_doc_type`` and its confidence, ``machine_department`` and its confidence,
       ``model``, ``input_truncated``, ``classified_at`` — are ALWAYS overwritten, whatever a
       person has decided: "the machine assignment is retained alongside it so that
       classification accuracy can be measured over time".
    2. **Type**, unless ``user_edited``: provisional when its confidence is below
       CLASSIFICATION_CONFIDENCE_THRESHOLD, in which case ``doc_type`` is None; otherwise applied
       and ``doc_type`` is the machine type. A type outside DOCUMENT_TYPES is a contract
       violation the parser should have refused and raises ``InvalidClassification`` before
       anything is written.
    3. **Department**, unless ``user_edited``: compared with ``scheme.departments`` after
       stripping, exactly in case because the column is not case-normalised. Outside the scheme
       is discarded and nothing is written; inside and below the threshold is provisional and
       ``Documents.department`` is untouched. Inside and at or above it, **the machine fills only
       a blank department** (the user's decision of 10 November 2026, D-105's note): a blank
       column takes the value (D-72: one source), saved with ``update_fields=["department"]``,
       and the outcome is applied; a column that already holds the suggested value is left as it
       is, and the outcome is applied; a column holding a different value is left as it is, and
       the suggestion is provisional, held for a person to accept. That value was typed by the
       uploader, confirmed, or written by an earlier run, and FR-10 says a value a person gives
       "is not overwritten by later reprocessing". ``department_applied_by`` records whose value
       the column now holds (``_department_provenance``): "ai" when this run wrote it, or an
       earlier run did and nobody has written it since; "user" for any other non-blank value,
       which a person gave; null for a blank one.
    4. **Tags**, for each suggestion whose dimension is one of REPOSITORY_TAG_DIMENSIONS, by its
       normalised name. In ``scheme.tags[dimension]`` and still an active Tag: a link a person
       REMOVED is left exactly as it is (FR-10's correction clause; D-105's dated note of 10
       November 2026, night), as is a link that a person applied or confirmed; an unconfirmed AI
       link takes the new confidence and provisional flag; otherwise a link is created,
       ``applied_by="ai"``, unconfirmed, provisional when below the threshold. Outside the
       scheme: a Topic goes to ``proposed_topics`` (deduplicated by normalised value, the higher
       confidence kept) unless a person removed that Topic from this document, a Project or
       Process to ``discarded_suggestions``; both lists are REPLACED by each run. A suggestion in
       any other dimension, or with an empty name, is ignored and logged. Links this run does not
       mention are left alone.

    The document row is locked first, as deletion and reprocess lock it, so a classification
    cannot write links for a document a concurrent delete is removing.
    """
    if classification.doc_type.value not in DOCUMENT_TYPES:
        raise InvalidClassification(
            f"doc_type must be one of {', '.join(DOCUMENT_TYPES)}, not "
            f"{classification.doc_type.value!r}."
        )
    now = timezone.now()
    department_value = (classification.department.value or "").strip()

    with transaction.atomic():
        locked = Document.objects.select_for_update().filter(pk=document.pk).first()
        if locked is None:
            raise NotOnThisDocument("The document no longer exists.")
        analysis, _ = DocumentAnalysis.objects.get_or_create(
            document=locked, defaults={"classified_at": now}
        )

        # Rule 1: the machine's values, always.
        analysis.machine_doc_type = classification.doc_type.value
        analysis.machine_doc_type_confidence = _as_decimal(classification.doc_type.confidence)
        analysis.machine_department = department_value[:NAME_MAX_LENGTH]
        analysis.machine_department_confidence = _as_decimal(classification.department.confidence)
        analysis.model = classification.model[:NAME_MAX_LENGTH]
        analysis.input_truncated = classification.input_truncated
        analysis.classified_at = now

        if not analysis.user_edited:
            # Rule 2: the type.
            if _is_provisional(classification.doc_type.confidence):
                analysis.doc_type = None
                analysis.doc_type_outcome = ASSIGNMENT_PROVISIONAL
            else:
                analysis.doc_type = classification.doc_type.value
                analysis.doc_type_outcome = ASSIGNMENT_APPLIED
            # Rule 3: the department.
            current = (locked.department or "").strip()
            machine_wrote = False
            if department_value not in scheme.departments:
                analysis.department_outcome = ASSIGNMENT_DISCARDED
            elif _is_provisional(classification.department.confidence):
                analysis.department_outcome = ASSIGNMENT_PROVISIONAL
            elif current == department_value:
                # Already the document's department: nothing to write. Whose value it is, the
                # uploader's or an earlier run's, is department_applied_by's to say.
                analysis.department_outcome = ASSIGNMENT_APPLIED
            elif current:
                # A department is already there and it is not the machine's to replace: held for
                # a person to accept (FR-10's correction clause; D-105's note of 10 November).
                analysis.department_outcome = ASSIGNMENT_PROVISIONAL
            else:
                analysis.department_outcome = ASSIGNMENT_APPLIED
                _write_department(document, department_value)
                current, machine_wrote = department_value, True
            analysis.department_applied_by = _department_provenance(
                analysis.department_applied_by, current, machine_wrote=machine_wrote
            )

        # Rule 4: the tags.
        proposed: dict[str, float] = {}
        discarded: dict[tuple[str, str], float] = {}
        ignored = 0
        # Topics a person removed from this document. A Topic whose Tag is still active is in the
        # scheme through that very link (tag_scheme counts a removed link) and reaches _link_tag,
        # which leaves it alone; one deactivated since, or withheld from the scheme, would
        # otherwise be proposed again, and a person has already said no to it here.
        removed_topics = set(
            ContentTag.objects.filter(
                source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk, removed=True,
                tag__dimension=TOPIC_DIMENSION,
            ).values_list("tag__tag_name", flat=True)
        )
        for suggestion in classification.tags:
            name = normalise_tag_name(suggestion.value or "")
            if suggestion.dimension not in REPOSITORY_TAG_DIMENSIONS or not name:
                ignored += 1
                continue
            if name in scheme.tags.get(suggestion.dimension, ()):
                tag = Tag.objects.filter(
                    dimension=suggestion.dimension, tag_name=name, active=True
                ).first()
                if tag is not None:
                    _link_tag(document, tag, suggestion.confidence)
                    continue
                # Deactivated since the scheme was built: treated as outside it.
            if suggestion.dimension == TOPIC_DIMENSION:
                if name in removed_topics:
                    continue  # removed by a person on this document: not proposed again
                if suggestion.confidence > proposed.get(name, -1.0):
                    proposed[name] = suggestion.confidence
            else:
                key = (suggestion.dimension, name)
                if suggestion.confidence > discarded.get(key, -1.0):
                    discarded[key] = suggestion.confidence
        analysis.proposed_topics = [
            {"value": value, "confidence": confidence} for value, confidence in proposed.items()
        ]
        analysis.discarded_suggestions = [
            {"dimension": dimension, "value": value, "confidence": confidence}
            for (dimension, value), confidence in discarded.items()
        ]
        analysis.save()

    if ignored:
        logger.info(
            "FR-10: %d tag suggestion(s) outside %s, or without a name, ignored for document %s",
            ignored, REPOSITORY_TAG_DIMENSIONS, document.pk,
        )
    return analysis


def _is_provisional(confidence: float) -> bool:
    """FR-10's one confidence comparison: below the threshold is provisional; at it is applied."""
    return confidence < CLASSIFICATION_CONFIDENCE_THRESHOLD


def _as_decimal(confidence: float) -> Decimal:
    """``confidence`` as the columns hold it: three places, half up."""
    return Decimal(str(confidence)).quantize(_CONFIDENCE_PLACES, rounding=ROUND_HALF_UP)


def _write_department(document: Document, value: str) -> None:
    """``Documents.department`` takes ``value``: the one source FR-14 and FR-15 read (D-72).

    ``update_fields`` names only this column, so the save writes nothing else the caller's
    instance may hold stale, and D-47's visibility cascade is not entered.
    """
    document.department = value
    document.save(update_fields=["department"])


def _department_provenance(previous: str | None, current: str, *, machine_wrote: bool) -> str | None:
    """Whose value ``Documents.department`` holds after a run decided it (D-119 finding 10).

    ``current`` is the department as the run leaves it, and ``previous`` the analysis row's
    ``department_applied_by`` before the run. A blank department is nobody's (None). One this run
    wrote is the machine's. One already there is the machine's only if an earlier run wrote it,
    which is what a ``previous`` of "ai" records: the machine fills only a blank department, and a
    person who writes it afterwards does so through ``confirm_classification``, which sets
    ``user_edited`` and so keeps every later run out of rule 3. Any other value already there was
    given by a person: the uploader typed it. That is the case finding 10 found mislabelled, where
    the suggestion equals the uploader's department and the outcome reads "applied".
    """
    if not current:
        return None
    if machine_wrote or previous == AI_APPLIED:
        return AI_APPLIED
    return USER_APPLIED


def _link_tag(document: Document, tag: Tag, confidence: float) -> ContentTag:
    """Rule 4's in-scheme case: create the AI link, refresh an unconfirmed one, or leave a
    person's decision alone: a link a person removed, confirmed or applied."""
    link = (
        ContentTag.objects.filter(tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)
        .order_by("pk")
        .first()
    )
    if link is None:
        return ContentTag.objects.create(
            tag=tag,
            source_type=DOCUMENT_SOURCE_TYPE,
            source_id=document.pk,
            applied_by=AI_APPLIED,
            confirmed=False,
            provisional=_is_provisional(confidence),
            confidence=_as_decimal(confidence),
        )
    if link.removed:
        # A person removed it: neither linked again nor altered, so the confidence it keeps is
        # the machine's assignment at the time of the removal (FR-10's correction clause).
        return link
    if link.confirmed or link.applied_by == USER_APPLIED:
        return link  # a person's decision: "not altered by later reprocessing"
    link.confidence = _as_decimal(confidence)
    link.provisional = _is_provisional(confidence)
    link.save(update_fields=["confidence", "provisional"])
    return link


# --- A person's decisions ----------------------------------------------------------------------


def confirm_classification(
    document: Document, *, doc_type: str | None = None, department: str | None = None
) -> DocumentAnalysis:
    """A person confirms the classification as it stands (both None) or edits it.

    - ``doc_type`` given: must be one of DOCUMENT_TYPES (else ``InvalidClassification``) and
      becomes the effective type. None keeps the machine type, applying it if it was provisional.
    - ``department`` given (blank allowed, stripped): written to ``Documents.department``. None
      keeps the machine suggestion if it was applied or provisional, writing
      ``Documents.department`` when it was provisional, and leaves things as they are if it was
      discarded.

    Each outcome becomes ``confirmed`` where a value now stands, and ``user_edited`` is set, after
    which a re-run writes only the machine's values. Raises ``NotOnThisDocument`` when the
    document has no classification.

    ``department_applied_by`` follows the department (D-119 finding 10): a department a person
    gives is "user" (null when blank); a held suggestion confirmed as it stands is written and
    keeps "ai", its provenance, as ``confirm_tag`` keeps an AI tag's ``applied_by``; an applied
    department confirmed as it stands keeps whatever it was.
    """
    if doc_type is not None and doc_type not in DOCUMENT_TYPES:
        raise InvalidClassification(f"doc_type must be one of {', '.join(DOCUMENT_TYPES)}.")
    if department is not None:
        department = department.strip()
        if len(department) > NAME_MAX_LENGTH:
            raise InvalidClassification(f"department may not exceed {NAME_MAX_LENGTH} characters.")

    with transaction.atomic():
        analysis = _analysis_of(document, for_update=True)
        if doc_type is not None:
            analysis.doc_type = doc_type
            analysis.doc_type_outcome = ASSIGNMENT_CONFIRMED
        else:
            if analysis.doc_type is None and analysis.machine_doc_type:
                analysis.doc_type = analysis.machine_doc_type
            if analysis.doc_type is not None:
                analysis.doc_type_outcome = ASSIGNMENT_CONFIRMED

        if department is not None:
            _write_department(document, department)
            analysis.department_outcome = ASSIGNMENT_CONFIRMED
            analysis.department_applied_by = USER_APPLIED if department else None
        elif analysis.department_outcome in (ASSIGNMENT_APPLIED, ASSIGNMENT_PROVISIONAL):
            if analysis.department_outcome == ASSIGNMENT_PROVISIONAL:
                _write_department(document, analysis.machine_department)
                analysis.department_applied_by = AI_APPLIED if analysis.machine_department else None
            analysis.department_outcome = ASSIGNMENT_CONFIRMED
        # Discarded, or never classified: left as it is.

        analysis.user_edited = True
        analysis.save()
    return analysis


def confirm_tag(document: Document, content_tag_id) -> ContentTag:
    """Accept an AI tag "in a single action": confirmed, no longer provisional, provenance kept."""
    with transaction.atomic():
        link = _link_on(document, content_tag_id)
        link.confirmed = True
        link.provisional = False
        link.save(update_fields=["confirmed", "provisional"])
    return link


def reject_tag(document: Document, content_tag_id) -> None:
    """Remove a tag "in a single action" (FR-10's provenance clause), keeping a machine's assignment.

    **An AI link** (``applied_by="ai"``: held or applied, confirmed or not) is KEPT and marked
    ``removed``, with the confidence and provisional flag the machine gave it. FR-10's correction
    clause: "any value a user edits [is] retained and is not overwritten by later reprocessing, and
    the machine assignment is retained alongside it". Deleting the row, as this did until D-119
    finding 3, lost the machine's assignment and let the next classify or reprocess link the tag
    again; ``_link_tag`` now leaves a removed link alone. No read lists it.

    **A person's link** (``applied_by="user"``) is deleted: there is no machine assignment to keep.
    The ``Tag`` row, a vocabulary, stays either way.

    A link already removed is not found here (``_link_on``), so removing it again is the same
    "not on this document" as an unknown id. A person puts it back by applying the tag
    (``apply_tag``).
    """
    with transaction.atomic():
        link = _link_on(document, content_tag_id)
        if link.applied_by == AI_APPLIED:
            link.removed = True
            link.save(update_fields=["removed"])
        else:
            link.delete()


def apply_tag(document: Document, *, tag_id=None, tag_name: str | None = None) -> AppliedTag:
    """A person applies a tag to ``document`` (FR-10's provenance clause; UC-09 A3), in one
    transaction with the document row locked, as the other writers lock it.

    Exactly one form, which the route's serializer has already enforced:

    - ``tag_id``: an existing tag, which must be in ``tag_scheme(document)`` (``offered_tags``). One
      that is unknown, inactive, in another dimension or withheld from this document's audience
      raises ``TagNotOffered``, the same for all of them.
    - ``tag_name``: a new Topic, already normalised (only Topic may grow: FR-10's controlled
      taxonomy growth). **The 409 and the rule that keeps it from disclosing anything:** a name that
      is an active Topic in this document's scheme raises ``TopicAlreadyOffered``, because the
      caller is already offered it. A Topic of that name that exists but is NOT in the scheme is
      grown and carried by no source every reader of this document can read (only by restricted
      material, or by nothing at all), or it is inactive; a Topic that is not grown is vocabulary
      and always in the scheme of an active one. Answering 409 for one outside the scheme would tell
      the caller whether a restricted value exists, directly or by applying, removing and applying
      again. So it is linked as it stands, reactivated if it was inactive (as
      ``confirm_proposed_topic`` does), and answered exactly as a new Topic is. Only a name no Topic
      has creates a Tag.
    - **The Topic the name form links is marked grown** (``Tag.grown``, D-105's dated note of 10
      November 2026, night), whether it was created or fetched, so that once its link is removed it
      is not vocabulary, whatever it was before. Without the mark, a retired, seeded, unlinked Topic
      a person names would come back as vocabulary after the removal, and apply, remove and apply
      again would answer 201, 204, 409 where a new name answers 201, 204, 201. The ``tag_id`` form
      marks nothing: an offered tag is already readable or vocabulary.

    Then the link (``_apply_link``): a new one is ``applied_by="user"``, ``confirmed=True`` (as the
    D-74 seed sets a person's links), not provisional, not removed, ``confidence`` null, and
    ``created`` is True. A link already there is confirmed if it was held, restored if it was
    removed, and otherwise left alone, and ``created`` is False. Raises ``NotOnThisDocument`` if the
    document was deleted meanwhile, and ``InvalidClassification`` for a name that normalises to
    nothing or overruns the column.
    """
    with transaction.atomic():
        locked = Document.objects.select_for_update().filter(pk=document.pk).first()
        if locked is None:
            raise NotOnThisDocument("The document no longer exists.")
        offered = offered_tags(locked)
        if tag_id is not None:
            if tag_id not in set(offered.values()):
                raise TagNotOffered("This tag is not offered for this document.")
            tag = Tag.objects.get(pk=tag_id)
        else:
            name = normalise_tag_name(tag_name or "")
            if not name or len(name) > NAME_MAX_LENGTH:
                raise InvalidClassification(
                    f"A tag name must have at least one character and at most {NAME_MAX_LENGTH}."
                )
            if (TOPIC_DIMENSION, name) in offered:
                raise TopicAlreadyOffered(offered[(TOPIC_DIMENSION, name)])
            tag, _ = Tag.objects.get_or_create(tag_name=name, dimension=TOPIC_DIMENSION)
            _bring_into_use(tag)
        return _apply_link(locked, tag)


def _bring_into_use(topic: Tag) -> None:
    """A Topic a person brought into use by name (``apply_tag``'s name form, or
    ``confirm_proposed_topic``), created or fetched: active, and grown, so that once nothing links
    it, it is not vocabulary (``tag_scheme``; D-105's dated note of 10 November 2026, night)."""
    changed = []
    if not topic.active:
        topic.active = True
        changed.append("active")
    if not topic.grown:
        topic.grown = True
        changed.append("grown")
    if changed:
        topic.save(update_fields=changed)


def _apply_link(document: Document, tag: Tag) -> AppliedTag:
    """``apply_tag``'s link: a live link is preferred to a removed one, should both exist."""
    links = list(
        ContentTag.objects.select_for_update()
        .filter(tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)
        .order_by("pk")
    )
    live = next((link for link in links if not link.removed), None)
    if live is not None:
        if live.provisional:
            # Held: confirmed, as the confirm route confirms it; provenance and confidence kept.
            live.confirmed = True
            live.provisional = False
            live.save(update_fields=["confirmed", "provisional"])
        # Applied or confirmed already: nothing to change.
        return AppliedTag(link=live, created=False)
    if links:
        # Removed: restored and confirmed; applied_by and the machine's confidence kept. It is no
        # longer held either, since a confirmed link is never provisional (confirm_tag's pair).
        restored = links[0]
        restored.removed = False
        restored.confirmed = True
        restored.provisional = False
        restored.save(update_fields=["removed", "confirmed", "provisional"])
        return AppliedTag(link=restored, created=False)
    created = ContentTag.objects.create(
        tag=tag,
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.pk,
        applied_by=USER_APPLIED,
        confirmed=True,
        provisional=False,
        removed=False,
        confidence=None,
    )
    return AppliedTag(link=created, created=True)


def confirm_proposed_topic(document: Document, value: str) -> ContentTag:
    """A person confirms an out-of-scheme Topic, which is when, and only when, it is created.

    FR-10: a new value "may be proposed only in the Topic dimension and requires user
    confirmation before it is created". The Topic Tag is fetched or created by normalised name
    (reactivated if it had been deactivated, and marked grown either way, as ``apply_tag``'s name
    form marks the Topic it links: a Topic a person brought in by name is not vocabulary once
    nothing links it, D-105's dated note of 10 November 2026, night), the document's link is
    created or confirmed with ``applied_by="ai"`` — the suggestion was the machine's — and the
    proposal leaves ``proposed_topics``. Raises ``NotOnThisDocument`` when ``value`` is not proposed
    on this document.
    """
    name = normalise_tag_name(value or "")
    with transaction.atomic():
        analysis = _analysis_of(document, for_update=True)
        proposal = _proposal(analysis, name)
        if len(name) > NAME_MAX_LENGTH:
            raise InvalidClassification(f"A tag name may not exceed {NAME_MAX_LENGTH} characters.")
        tag, _ = Tag.objects.get_or_create(tag_name=name, dimension=TOPIC_DIMENSION)
        _bring_into_use(tag)
        confidence = proposal.get("confidence")
        confidence = None if confidence is None else _as_decimal(confidence)
        link = (
            ContentTag.objects.filter(
                tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk
            )
            .order_by("pk")
            .first()
        )
        if link is None:
            link = ContentTag.objects.create(
                tag=tag,
                source_type=DOCUMENT_SOURCE_TYPE,
                source_id=document.pk,
                applied_by=AI_APPLIED,
                confirmed=True,
                provisional=False,
                confidence=confidence,
            )
        else:
            link.confirmed = True
            link.provisional = False
            link.removed = False  # a person confirming the Topic wants it on the document
            if link.confidence is None:
                link.confidence = confidence
            link.save(update_fields=["confirmed", "provisional", "removed", "confidence"])
        _drop_proposal(analysis, name)
    return link


def reject_proposed_topic(document: Document, value: str) -> None:
    """Decline an out-of-scheme Topic: it leaves ``proposed_topics`` and no Tag is created."""
    name = normalise_tag_name(value or "")
    with transaction.atomic():
        analysis = _analysis_of(document, for_update=True)
        _proposal(analysis, name)
        _drop_proposal(analysis, name)


# --- Lookups that answer "not on this document" ---------------------------------------------------


def _analysis_of(document: Document, *, for_update: bool = False) -> DocumentAnalysis:
    queryset = DocumentAnalysis.objects.select_for_update() if for_update else DocumentAnalysis.objects
    analysis = queryset.filter(document_id=document.pk).first()
    if analysis is None:
        raise NotOnThisDocument("This document has no classification.")
    return analysis


def _link_on(document: Document, content_tag_id) -> ContentTag:
    """The ``ContentTag`` with this id on THIS document, locked; any other id is "not here".

    A removed link is "not here" too: it is no longer a tag of the document, no read lists it, and
    confirming or removing it by id would act on something the caller is never shown. Applying its
    tag again restores it (``apply_tag``)."""
    try:
        link = (
            ContentTag.objects.select_for_update()
            .filter(
                pk=content_tag_id, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
                removed=False,
            )
            .first()
        )
    except (ValueError, ValidationError):  # not a UUID at all
        link = None
    if link is None:
        raise NotOnThisDocument("No such tag on this document.")
    return link


def _proposal(analysis: DocumentAnalysis, name: str) -> dict:
    for proposal in analysis.proposed_topics:
        if proposal.get("value") == name:
            return proposal
    raise NotOnThisDocument("No such proposed topic on this document.")


def _drop_proposal(analysis: DocumentAnalysis, name: str) -> None:
    analysis.proposed_topics = [
        proposal for proposal in analysis.proposed_topics if proposal.get("value") != name
    ]
    analysis.save(update_fields=["proposed_topics"])
