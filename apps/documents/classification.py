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
  marks it confirmed and ``reject_tag`` deletes it ("either may be accepted or removed in a single
  action").
- **correction** — "any value a user edits [is] retained and is not overwritten by later
  reprocessing, and the machine assignment is retained alongside it":
  ``DocumentAnalysis.user_edited`` guards the effective type, ``Documents.department`` and the two
  outcomes, while the ``machine_*`` columns take every run's values. A confirmed tag "is not
  altered by later reprocessing".

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


# --- The scheme ----------------------------------------------------------------------------------


def tag_scheme(document: Document) -> TagScheme:
    """The established scheme ``document`` is classified against: only values its own audience
    may read.

    **The rule, stated so that it can be checked against the code below.** The audience is every
    role in ``document.visible_to_roles``. A value is in the scheme only if EVERY role in the
    audience can read at least one source carrying it, so the prompt — and therefore any
    suggestion it produces — can never name a value that exists only on material some reader of
    this document may not see (CLAUDE.md invariant 1: the existence of out-of-scope material
    "must not be disclosed"). Whether a role can read a source is decided by ``scoped_documents``
    and ``scoped_meetings`` from apps/retrieval/scoping.py, the one place the FR-11 predicate is
    written (D-53, D-66); nothing here tests ``visible_to_roles`` itself.

    - ``doc_types`` is DOCUMENT_TYPES: a fixed list that says nothing about the corpus.
    - ``departments`` is the intersection, across the audience, of the distinct non-blank
      ``Documents.department`` values of the documents each role may read. A department carried
      only by documents some role in the audience cannot read is withheld.
    - ``tags`` holds, for each of REPOSITORY_TAG_DIMENSIONS, the active ``Tag`` names, except a
      tag that has at least one ``ContentTag`` link and, for some role in the audience, no link to
      a source that role may read: documents through ``scoped_documents``, meetings through
      ``scoped_meetings``, since the join table admits both source types. A tag with no links is
      vocabulary only, says nothing about any source, and is always in. Every link counts,
      provisional and unconfirmed ones included: a held suggestion on a restricted document is
      still a fact about that document.

    **An empty audience gets the full scheme.** A document whose ``visible_to_roles`` is empty is
    readable by nobody (``scoped_*`` fail closed), so there is no reader to protect. D-29 refuses
    an empty list at upload, so this arises only from direct row edits.

    **The scheme is built for the audience at classification time.** A document later widened to
    more roles keeps the values it was classified against; widening should reclassify.

    **A role name scoping does not know** (one missing from EFFECTIVE_ROLES) reads nothing, so
    every linked value and every department is withheld from a document it is in the audience
    of. That fails closed, as ``scoped_documents`` does.
    """
    audience = list(dict.fromkeys(document.visible_to_roles))  # distinct, in order
    active_tags = Tag.objects.filter(
        active=True, dimension__in=REPOSITORY_TAG_DIMENSIONS
    ).values_list("id", "dimension", "tag_name")

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
        linked_tag_ids = set(ContentTag.objects.values_list("tag_id", flat=True).distinct())

        def admitted(tag_id) -> bool:
            # Unlinked: vocabulary only, always in. Linked: every role must read one of its sources.
            return tag_id not in linked_tag_ids or tag_id in readable_tag_ids

    else:
        departments = set(
            Document.objects.exclude(department="").values_list("department", flat=True).distinct()
        )

        def admitted(tag_id) -> bool:
            return True

    names = {dimension: [] for dimension in REPOSITORY_TAG_DIMENSIONS}
    for tag_id, dimension, tag_name in active_tags:
        if admitted(tag_id):
            names[dimension].append(tag_name)
    return TagScheme(
        doc_types=tuple(DOCUMENT_TYPES),
        departments=tuple(sorted(departments)),
        tags={dimension: tuple(sorted(values)) for dimension, values in names.items()},
    )


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
       ``Documents.department`` is untouched; inside and at or above it is applied and
       ``Documents.department`` takes the value (D-72: one source), saved with
       ``update_fields=["department"]``.
    4. **Tags**, for each suggestion whose dimension is one of REPOSITORY_TAG_DIMENSIONS, by its
       normalised name. In ``scheme.tags[dimension]`` and still an active Tag: a link that a
       person applied or confirmed is left alone; an unconfirmed AI link takes the new confidence
       and provisional flag; otherwise a link is created, ``applied_by="ai"``, unconfirmed,
       provisional when below the threshold. Outside the scheme: a Topic goes to
       ``proposed_topics`` (deduplicated by normalised value, the higher confidence kept), a
       Project or Process to ``discarded_suggestions``; both lists are REPLACED by each run. A
       suggestion in any other dimension, or with an empty name, is ignored and logged. Links
       this run does not mention are left alone.

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
            if department_value not in scheme.departments:
                analysis.department_outcome = ASSIGNMENT_DISCARDED
            elif _is_provisional(classification.department.confidence):
                analysis.department_outcome = ASSIGNMENT_PROVISIONAL
            else:
                analysis.department_outcome = ASSIGNMENT_APPLIED
                _write_department(document, department_value)

        # Rule 4: the tags.
        proposed: dict[str, float] = {}
        discarded: dict[tuple[str, str], float] = {}
        ignored = 0
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


def _link_tag(document: Document, tag: Tag, confidence: float) -> ContentTag:
    """Rule 4's in-scheme case: create the AI link, refresh an unconfirmed one, or leave a
    person's alone."""
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
        elif analysis.department_outcome in (ASSIGNMENT_APPLIED, ASSIGNMENT_PROVISIONAL):
            if analysis.department_outcome == ASSIGNMENT_PROVISIONAL:
                _write_department(document, analysis.machine_department)
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
    """Remove a tag "in a single action": the link is deleted; the Tag row, a vocabulary, stays."""
    with transaction.atomic():
        _link_on(document, content_tag_id).delete()


def confirm_proposed_topic(document: Document, value: str) -> ContentTag:
    """A person confirms an out-of-scheme Topic, which is when, and only when, it is created.

    FR-10: a new value "may be proposed only in the Topic dimension and requires user
    confirmation before it is created". The Topic Tag is fetched or created by normalised name
    (reactivated if it had been deactivated), the document's link is created or confirmed with
    ``applied_by="ai"`` — the suggestion was the machine's — and the proposal leaves
    ``proposed_topics``. Raises ``NotOnThisDocument`` when ``value`` is not proposed on this
    document.
    """
    name = normalise_tag_name(value or "")
    with transaction.atomic():
        analysis = _analysis_of(document, for_update=True)
        proposal = _proposal(analysis, name)
        if len(name) > NAME_MAX_LENGTH:
            raise InvalidClassification(f"A tag name may not exceed {NAME_MAX_LENGTH} characters.")
        tag, _ = Tag.objects.get_or_create(tag_name=name, dimension=TOPIC_DIMENSION)
        if not tag.active:
            tag.active = True
            tag.save(update_fields=["active"])
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
            if link.confidence is None:
                link.confidence = confidence
            link.save(update_fields=["confirmed", "provisional", "confidence"])
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
    """The ``ContentTag`` with this id on THIS document, locked; any other id is "not here"."""
    try:
        link = (
            ContentTag.objects.select_for_update()
            .filter(pk=content_tag_id, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)
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
