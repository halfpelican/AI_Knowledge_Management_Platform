"""FR-10's apply layer: the scheme a document is classified against, and what becomes of the
model's suggestions (docs/decisions.md D-105).

``AIService.classify_document`` (apps/ai/classification.py) returns a ``DocumentClassification``:
the model's suggestions AS MADE, with nothing decided. Everything FR-10's Server-End calls
business logic is decided here, in application code over those suggestions, and never by the
model:

- **confidence** — "a confidence value is recorded with each assignment. Assignments below the
  configured threshold are marked provisional and presented for confirmation rather than applied
  silently." The classifying model's threshold is compared in one place, ``_is_provisional``:
  ``CLASSIFICATION_CONFIDENCE_THRESHOLD``, or the model's own value from
  ``CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL`` (``confidence_threshold``, D-122).
- **controlled taxonomy growth** — FR-10: "suggested tags are matched against values already held
  in the scheme. A value that does not match may be proposed only in the Topic dimension and
  requires user confirmation before it is created; suggestions falling outside the scheme in the
  Department, Project or Process dimensions are discarded." **D-128 (12 November 2026) departs
  from that text for tags,** on for everyone: a value outside the scheme in Project, Process or
  Topic is created and applied when its confidence is at or above the threshold, and held as a
  proposal for a person to confirm or reject when it is below (``confirm_proposed_tag``,
  ``reject_proposed_tag``). A department outside the scheme is still discarded. Rules 3 and 4 of
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
  10 November 2026, night), nor, since D-128, creates, reactivates or proposes it, in any
  dimension. A proposal a person rejects is kept the same way, in ``rejected_tags`` with the
  machine's confidence, and later reprocessing never proposes, creates or links that value on the
  document, even once it is in the scheme (``reject_proposed_tag``; the requirements audit of
  D-128, finding A5).

**The scheme is built for the document's own audience** (``tag_scheme``), so the prompt never
lists a value that exists only on material some reader of this document may not see, and a
suggestion that names one anyway is treated exactly as a value no Tag has (``apply_classification``
rule 4, CLAUDE.md invariant 1).

**What this module does not do.** It calls the provider only in ``classify_document_now``; it
decides no status code (the route and the ingestion hook map the exceptions below); and it never
resolves a ``Document`` for a caller: every function takes one the caller already reached through
``scoped_documents`` (D-46, D-53). It lives in ``apps/documents`` beside ``deletion.py``, outside
the request-serving packages ``apps/api/tests/test_source_rows_fail_closed.py`` scans, for the
reason that module gives: it reads managers directly, for writes against a row already resolved
and for the vocabulary tables.
"""

import logging
import unicodedata
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
    CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL,
    DOCUMENT_TYPES,
    MAXIMUM_CREATED_TAG_WORDS,
    REPOSITORY_TAG_DIMENSIONS,
    ROLE_NAMES,
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

# Rule 4d's limits on a value outside the scheme (D-128's security review, finding 2; see
# ``_may_become_a_tag``). The prompt lists each dimension's values joined by "; "
# (apps/ai/classification.py), so a value holding ";" would read as several. Unicode categories Cc
# (control: NUL among them, which neither a text column nor jsonb accepts) and Cf (format: the
# right-to-left override U+202E, the zero-width space U+200B and their kind) let a name look
# different from what it holds; Cs (a lone surrogate) cannot be written at all
# (``_unsafe_character``). A discard records each such character as U+FFFD, the replacement
# character, so the record can always be written.
_PROMPT_LIST_SEPARATOR = ";"
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})
_REPLACEMENT_CHARACTER = "\ufffd"


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
    """The tag link, proposal or analysis named is not this document's. The route answers 404, the
    same answer as for a document outside the caller's scope (D-46)."""


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
    links, or if EVERY role in the audience can read at least one source carrying it. So the prompt
    never lists a grown value that exists only on material some reader of this document may not see
    (CLAUDE.md invariant 1: the existence of out-of-scope material "must not be disclosed"), a
    suggestion that names one anyway is treated exactly as a value no Tag has
    (``apply_classification`` rule 4, D-128), and nothing a reader can see moves when links on
    material they cannot read are made or destroyed. Whether a role can read a source is decided by
    ``scoped_documents`` and ``scoped_meetings`` from apps/retrieval/scoping.py, the one place the
    FR-11 predicate is written (D-53, D-66); nothing here tests ``visible_to_roles`` itself.

    - ``doc_types`` is DOCUMENT_TYPES: a fixed list that says nothing about the corpus.
    - ``departments`` is the intersection, across the audience, of the distinct non-blank
      ``Documents.department`` values of the documents each role may read. A department carried
      only by documents some role in the audience cannot read is withheld.
    - ``tags`` holds, for each of REPOSITORY_TAG_DIMENSIONS, the active ``Tag`` names admitted by
      the rule above.
    - **A tag that is not grown is vocabulary** and is in every scheme, unlinked, carried only by
      restricted material, or carried by readable material alike: its presence says nothing about
      any source, and no link anyone makes or destroys moves it (D-105's dated note of 10 November
      2026, night: the security review of ``84b5771``). Until then the scheme read every link of a
      tag that was not grown, links no reader of the document can see included, so a seeded value
      vanished from an Employee's options exactly when Administrator-only material still carried
      it: when an Employee removed its readable person links, when restricted material took it up,
      or, the other way round, when an Administrator removed the only restricted links.
    - **A grown tag is in only where every role in the audience reads a source carrying it**:
      documents through ``scoped_documents``, meetings through ``scoped_meetings``, since the join
      table admits both source types. Every link counts, provisional, unconfirmed and removed ones
      included: a held suggestion, or one a person removed, on a readable document is still a
      carrier. ``grown`` is set on a tag the classifier creates or reactivates at or above the
      threshold and on one a person's confirmation of a proposal creates or reactivates, in
      Project, Process or Topic (D-128), on a Topic a person's ``apply_tag`` name form creates or
      reactivates (the lead's oracle review), and by ``documents 0011`` and the seed script's
      linked mode on every tag carried only by material some role cannot read. An active tag any
      of the three fetches keeps its value, and an inactive one is reactivated only from a
      document every role reads (``_bring_into_use``; D-128's security review, finding 1), so a
      link on material some role cannot read never brings a retired value back into a scheme
      through an old readable carrier. So a value the classifier creates
      from an Administrator-only document is carried by that document alone and offered only to
      an audience every role of which reads it: never to, and never in the prompt for, a document
      an Employee reads, while that stays so. A value an Administrator adds (``POST /api/tags``,
      D-128) is not grown: vocabulary, in every scheme, as a seeded value is.

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
      **disappears** only when the last such source is deleted, or the tag is retired: a removed
      link is kept and still counts (``reject_tag``). Links on material some reader cannot see
      neither add nor remove it. That includes a link that would bring a retired tag back: from a
      document some role cannot read the tag is linked and stays retired (``_bring_into_use``;
      D-128's security review, finding 1). Before that fix, such a link reactivated it, and every
      document a readable old carrier made it eligible for offered it again, while nothing those
      readers could read had changed.
    - **A tag that is not grown never moves** while it is active: no link anyone makes or destroys,
      on readable material or restricted, changes whether it is offered. That includes a person
      confirming a proposal of its name made before it was vocabulary, and the classifier linking it
      against a scheme built before it was vocabulary, each of which links it and leaves it
      vocabulary (``_bring_into_use``). It leaves only when an Administrator retires or deletes it
      (``DELETE /api/tags/{id}``). A retired tag comes back, grown, only through a document every
      role reads: a person names it there (a Topic, ``apply_tag``), confirms a proposal of it
      there (``confirm_proposed_tag``), or the classifier suggests it there at or above the
      threshold, in Project, Process or Topic (D-128: retiring a tag no longer keeps it out of
      classification).
    - So the names of every active tag that is not grown are offered to every reader: the values a
      database is seeded with, those an Administrator adds (``POST /api/tags``, D-128), and those
      vocabulary values restricted material has taken up since. That is what vocabulary means
      here. The classification prompt lists the same names; before the security review it listed
      only the unlinked ones and those a readable source carried.
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
    4. **Tags** (D-128, 12 November 2026, which departs from FR-10's controlled taxonomy growth
       clause), each suggestion by its dimension and normalised name, in this order:

       a. **Ignored**, and logged: a dimension outside REPOSITORY_TAG_DIMENSIONS, or an empty name.
       b. **A person removed or rejected it.** This document holds a REMOVED link to the tag of
          that dimension and name, or its ``rejected_tags`` holds that dimension and name because a
          person rejected it as a proposal (``reject_proposed_tag``). In any of the three
          dimensions, at any confidence, and before the in-scheme match below, so a rejected value
          is not linked even once it has entered the scheme (an Administrator added it, or another
          document created it). The suggestion is skipped: not linked, not created, not
          reactivated, not proposed, not recorded (FR-10's correction clause, "not overwritten by
          later reprocessing"; D-105's dated note of 10 November 2026, night, generalised from
          Topic by D-128; the rejection since the requirements audit of D-128, finding A5). Only
          this document's own links and analysis row are read.
       c. **In the scheme** (``scheme.tags[dimension]``) and still an active Tag: ``_link_tag``,
          unchanged. A link a person applied or confirmed is left as it is; an unconfirmed AI link
          takes the new confidence and provisional flag; otherwise a link is created,
          ``applied_by="ai"``, unconfirmed, provisional when below the threshold.
       d. **Otherwise**, outside the scheme or deactivated since it was built. The suggestions of
          one dimension and name are taken together at their highest confidence, then:

          - **not a name a prompt can list** (``_may_become_a_tag``; D-128's security review,
            finding 2): longer than NAME_MAX_LENGTH, more than MAXIMUM_CREATED_TAG_WORDS words,
            holding ";", or holding a control, format or surrogate character. It goes to
            ``discarded_suggestions`` whatever its confidence, recorded with each such character
            replaced by U+FFFD (``_recordable``), and nothing is created, proposed or linked;
          - **at or above the threshold**: the Tag is fetched or created (``get_or_create``, which
            also settles a concurrent create of the same name), brought into use and linked by
            ``_link_tag``: an AI link, unconfirmed, not provisional, with the confidence, unless a
            person's decision is there already. ``_bring_into_use``: one created becomes active
            and grown; an active one fetched keeps its state; an inactive one fetched is
            reactivated, and grown, only when every role can read this document, and otherwise is
            linked and left retired (D-128's security review, finding 1). These are taken in one
            order, by dimension then name, in every run, so two runs that create the same values
            wait on each other rather than deadlocking;
          - **below the threshold**: held in ``proposed_tags`` as ``{"dimension", "value",
            "confidence"}`` for a person to confirm or reject (``confirm_proposed_tag``,
            ``reject_proposed_tag``).

       ``proposed_tags`` and ``discarded_suggestions`` are REPLACED by each run. Links this run
       does not mention are left alone.

    **Why every value outside the scheme gets the same treatment (CLAUDE.md invariant 1).** Seen
    from a reader of this document, such a value is one of three things, and the reader must not be
    able to tell which: (a) no Tag has it; (b) an active, grown Tag that only material some reader
    of this document cannot see carries (an active Tag that is not grown is vocabulary and always
    in the scheme); (c) a retired Tag. What a reader can observe is identical for all three: at or
    above the threshold the value is applied, in ``tag_details`` and afterwards in this document's
    ``tag_options``; below it, it is a proposal. Nothing returned or recorded says whether a Tag row
    was created, and no AI tag is labelled new, which is the precedent D-105's note set for a
    person's name: a retired value is in no scheme, so answering it differently would disclose it.
    **The consequence, recorded in D-128:** retiring a tag no longer keeps it out of
    classification; a suggestion of a retired value at or above the threshold reactivates it,
    grown, in Project and Process as in Topic, **when every role can read this document**. On a
    document some role cannot read, a retired value is linked and stays retired (D-128's security
    review, finding 1): reactivated there, an old readable carrier would offer it again to readers
    who saw nothing change. That document's readers can then tell a retired value from a new one,
    since only the new one enters its ``tag_options``. With today's two roles that reader is an
    Administrator, who reads every source and every retired tag (D-66), so nothing is disclosed.
    ``grown`` is what keeps a value the classifier creates away from readers who cannot see its
    carrier (``tag_scheme``), and it is never unset.

    The document row is locked first, as deletion and reprocess lock it, so a classification
    cannot write links for a document a concurrent delete is removing. The analysis row is locked
    next, as a person's decisions lock it, so a rejection committed meanwhile is neither missed by
    rule 4b nor overwritten when this run saves the row. A person's decision takes only the
    analysis lock, so the two orders cannot deadlock.
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
        # The analysis row is locked too, as a person's decisions lock it (``_analysis_of``). This
        # run saves every field of it, so without the lock a rejection committed between this read
        # and that save would be overwritten by this stale copy, and would not stick (rule 4b).
        analysis, _ = DocumentAnalysis.objects.select_for_update().get_or_create(
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
            if _is_provisional(classification.doc_type.confidence, classification.model):
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
            elif _is_provisional(classification.department.confidence, classification.model):
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

        # Rule 4: the tags (D-128).
        ignored = 0
        # 4b: the (dimension, name) of every tag a person removed from this document, and of every
        # proposal a person rejected on it (``rejected_tags``; the requirements audit of D-128,
        # finding A5), in any dimension. A removed one still in the scheme would reach _link_tag,
        # which leaves a removed link alone; any other would otherwise be created, linked or
        # proposed again, a rejected one even once it has entered the scheme, and a person has
        # already said no to it here. Read from this document's own links and its own analysis
        # row only, so skipping it discloses nothing about other material (CLAUDE.md invariant 1).
        declined = set(
            ContentTag.objects.filter(
                source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk, removed=True,
            ).values_list("tag__dimension", "tag__tag_name")
        ) | _rejected(analysis)
        # 4d: the values outside the scheme, each (dimension, name) at its highest confidence.
        outside: dict[tuple[str, str], float] = {}
        for suggestion in classification.tags:
            name = normalise_tag_name(suggestion.value or "")
            if suggestion.dimension not in REPOSITORY_TAG_DIMENSIONS or not name:
                ignored += 1  # 4a
                continue
            key = (suggestion.dimension, name)
            if key in declined:
                continue  # 4b: removed or rejected by a person on this document
            if name in scheme.tags.get(suggestion.dimension, ()):
                tag = Tag.objects.filter(
                    dimension=suggestion.dimension, tag_name=name, active=True
                ).first()
                if tag is not None:
                    _link_tag(document, tag, suggestion.confidence, classification.model)  # 4c
                    continue
                # Deactivated since the scheme was built: treated as outside it.
            if suggestion.confidence > outside.get(key, -1.0):
                outside[key] = suggestion.confidence

        # One treatment for every value outside the scheme, whether no Tag has it, a grown Tag
        # only material some reader cannot see carries, or a retired Tag (CLAUDE.md invariant 1;
        # see the docstring). Nothing below says which it was.
        proposed, discarded, applied = [], [], []
        for (dimension, name), confidence in outside.items():
            if not _may_become_a_tag(name):
                # Too long, too many words, or holding ";" or a control, format or surrogate
                # character: never created or proposed, whatever its confidence (finding 2).
                # Recorded with each such character replaced, so the record can be written.
                discarded.append(
                    {"dimension": dimension, "value": _recordable(name), "confidence": confidence}
                )
            elif _is_provisional(confidence, classification.model):
                # Held for a person to confirm or reject.
                proposed.append({"dimension": dimension, "value": name, "confidence": confidence})
            else:
                applied.append((dimension, name, confidence))
        # One order, by dimension then name, in every run: two runs creating or reactivating the
        # same values then wait on each other at the first of them rather than deadlocking.
        for dimension, name, confidence in sorted(applied):
            tag, created = Tag.objects.get_or_create(tag_name=name, dimension=dimension)
            # A retired tag is reactivated only if every role reads this document (finding 1);
            # either way the link is made.
            _bring_into_use(tag, created, locked)
            _link_tag(document, tag, confidence, classification.model)
        analysis.proposed_tags = proposed
        analysis.discarded_suggestions = discarded
        analysis.save()

    if ignored:
        logger.info(
            "FR-10: %d tag suggestion(s) outside %s, or without a name, ignored for document %s",
            ignored, REPOSITORY_TAG_DIMENSIONS, document.pk,
        )
    return analysis


def confidence_threshold(model: str) -> float:
    """FR-10's threshold for suggestions ``model`` made (D-122).

    A model CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL lists gets its own value, chosen by
    D-106's rule on that model's classifications. Any other, gemma3:4b included, gets
    CLASSIFICATION_CONFIDENCE_THRESHOLD. ``model`` is the name the classification carries
    (``DocumentClassification.model``, the provider's chat model). Both names are read at call
    time, so a test that reassigns either is honoured.
    """
    return CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL.get(model, CLASSIFICATION_CONFIDENCE_THRESHOLD)


def _is_provisional(confidence: float, model: str) -> bool:
    """FR-10's one confidence comparison: below the threshold is provisional; at it is applied.

    The threshold is the classifying model's own (``confidence_threshold``, D-122).
    """
    return confidence < confidence_threshold(model)


def _unsafe_character(character: str) -> bool:
    """A control (Cc) or format (Cf) character, or a lone surrogate (Cs), for rule 4d (D-128's
    security review, finding 2).

    The review named Cc and Cf. Cs is added here: a lone surrogate, which ``json.loads`` makes of a
    ``\\ud800`` escape in a reply, can be written neither to a text column nor to jsonb, so it 500s
    the classify route exactly as a NUL did."""
    return unicodedata.category(character) in _UNSAFE_CATEGORIES


def _may_become_a_tag(name: str) -> bool:
    """Whether a value outside the scheme may be created or proposed (rule 4d; D-128 and its
    security review, finding 2). ``name`` is normalised, so its words are separated by single spaces.

    - At most NAME_MAX_LENGTH characters, the column's width.
    - At most MAXIMUM_CREATED_TAG_WORDS words: rule 6 of the prompt, enforced. A created value joins
      the scheme every later prompt lists, so a longer one would be text an uploaded document had
      planted in other documents' prompts.
    - No ";", the prompt's list separator, which would make one value read as several.
    - No control, format or surrogate character (``_unsafe_character``). These can make a name look
      different from what it holds, and a NUL or a lone surrogate cannot be written at all.

    Only rule 4d asks. An existing Tag in the scheme is matched as it is (rule 4c), the department
    is rule 3's, and a person's name form (``apply_tag``) has its own checks.
    """
    return (
        len(name) <= NAME_MAX_LENGTH
        and len(name.split()) <= MAXIMUM_CREATED_TAG_WORDS
        and _PROMPT_LIST_SEPARATOR not in name
        and not any(_unsafe_character(character) for character in name)
    )


def _recordable(name: str) -> str:
    """``name`` as ``discarded_suggestions`` records it: each control, format or surrogate character
    replaced by U+FFFD, so the jsonb column always accepts the record (a NUL made the classify route
    answer 500, D-128's security review). Every other character is kept as the model wrote it."""
    return "".join(
        _REPLACEMENT_CHARACTER if _unsafe_character(character) else character for character in name
    )


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


def _link_tag(document: Document, tag: Tag, confidence: float, model: str) -> ContentTag:
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
            provisional=_is_provisional(confidence, model),
            confidence=_as_decimal(confidence),
        )
    if link.removed:
        # A person removed it: neither linked again nor altered, so the confidence it keeps is
        # the machine's assignment at the time of the removal (FR-10's correction clause).
        return link
    if link.confirmed or link.applied_by == USER_APPLIED:
        return link  # a person's decision: "not altered by later reprocessing"
    link.confidence = _as_decimal(confidence)
    link.provisional = _is_provisional(confidence, model)
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
    """Remove a tag "in a single action" (FR-10's provenance clause), keeping the link, marked removed.

    **Every link is KEPT and marked ``removed``,** a person's as well as the machine's: held or
    applied, confirmed or not, with the confidence and provisional flag it had. FR-10's correction
    clause: "any value a user edits [is] retained and is not overwritten by later reprocessing, and
    the machine assignment is retained alongside it" (UC-09 A3 step 3). A deleted row records no
    decision, so the next classify route, reprocess or ``classify_documents`` run that suggested the
    value linked it again, ``applied_by="ai"``, through ``_link_tag``'s create branch: for an AI link
    until D-119 finding 3, and for a person's link until the requirements re-audit of ``5377e3a``
    (D-105's dated note of 10 November 2026, night). ``_link_tag`` leaves a removed link alone, and
    since D-128 a later run neither proposes, creates nor reactivates a removed value, in any
    dimension (``apply_classification`` rule 4b). No read lists a removed link. The ``Tag`` row, a
    vocabulary, stays.

    A link already removed is not found here (``_link_on``), so removing it again is the same
    "not on this document" as an unknown id. A person puts it back by applying the tag
    (``apply_tag``), which restores the row (``_apply_link``).
    """
    with transaction.atomic():
        link = _link_on(document, content_tag_id)
        link.removed = True
        link.save(update_fields=["removed"])


def apply_tag(document: Document, *, tag_id=None, tag_name: str | None = None) -> AppliedTag:
    """A person applies a tag to ``document`` (FR-10's provenance clause; UC-09 A3), in one
    transaction with the document row locked, as the other writers lock it.

    Exactly one form, which the route's serializer has already enforced:

    - ``tag_id``: an existing tag, which must be in ``tag_scheme(document)`` (``offered_tags``). One
      that is unknown, inactive, in another dimension or withheld from this document's audience
      raises ``TagNotOffered``, the same for all of them.
    - ``tag_name``: a new Topic, already normalised. A person's name form is Topic-only: FR-10's
      controlled taxonomy growth let only Topic grow, and D-128, which lets the classifier create a
      Project or Process value and an Administrator add one (``POST /api/tags``), left this form as
      it was. **The 409 and the rule that keeps it from disclosing anything:** a name that
      is an active Topic in this document's scheme raises ``TopicAlreadyOffered``, because the
      caller is already offered it. A Topic of that name that exists but is NOT in the scheme is
      grown and carried by no source every reader of this document can read (only by restricted
      material, or by nothing at all), or it is inactive; a Topic that is not grown is vocabulary
      and always in the scheme of an active one. Answering 409 for one outside the scheme would tell
      the caller whether a restricted value exists, directly or by applying, removing and applying
      again. So it is linked as it stands, and answered exactly as a new Topic is, unless this
      document already holds a link to it, live or removed, which ``_apply_link`` keeps or restores:
      ``created`` is False, the route's 200. Either answer depends only on this document's own
      links. Only a name no Topic has creates a Tag.
    - **An inactive Topic is reactivated only when every role can read the document** (D-128's
      security review, finding 1, which found this D-105 path reactivating a retired Topic from
      Administrator-only material and so putting it back in every Employee's options through an old
      readable carrier). On a document some role cannot read it is linked and left retired, as
      ``confirm_proposed_tag`` and the classifier leave it (``_bring_into_use``). The answer is the
      same either way.
    - **The Topic the name form brings into use is grown** (``Tag.grown``, D-105's dated note of 10
      November 2026, night), so that it is never vocabulary, whatever it was before: it is offered
      only where every audience role reads a source carrying it. ``_bring_into_use`` marks one it
      creates or reactivates; an active one it fetches is grown already, since an active Topic that
      is not grown is vocabulary, offered, and answered 409 above; one left retired is offered
      nowhere, and is marked if it is ever reactivated. Without the mark, a Topic a person brings in
      by name on material some reader cannot see would be vocabulary, offered to that reader too
      (apps/api/tests/test_fr10_tag_vocabulary.py). The ``tag_id`` form marks nothing: an offered
      tag is already readable or vocabulary.

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
            tag, created = Tag.objects.get_or_create(tag_name=name, dimension=TOPIC_DIMENSION)
            _bring_into_use(tag, created, locked)
        return _apply_link(locked, tag)


def _every_role_reads(document: Document) -> bool:
    """Whether every role can read ``document`` (D-128's security review, finding 1).

    Asked of ``scoped_documents`` for each of ROLE_NAMES, the one place the FR-11 predicate is
    written (D-53), and never by reading ``visible_to_roles`` here. A role that scoping does not know
    reads nothing, so this answers False and nothing is reactivated: it fails closed.
    """
    return all(
        scoped_documents(role_name=role_name).filter(pk=document.pk).exists()
        for role_name in ROLE_NAMES
    )


def _bring_into_use(tag: Tag, created: bool, document: Document) -> None:
    """A tag brought into use by name on ``document``: by the classifier at or above the threshold
    (``apply_classification`` rule 4d, D-128), by a person confirming a proposal
    (``confirm_proposed_tag``, D-128), both in Project, Process or Topic, or by a person's
    ``apply_tag`` name form (a Topic). The caller makes or confirms the document's link whatever
    happens here.

    - **One this call ``created``** is made grown, so that it is never vocabulary: it is offered only
      where every audience role reads a source carrying it (``tag_scheme``; D-105's dated note of 10
      November 2026, night). A new tag has no carrier but ``document``, wherever that is.
    - **An active tag it fetched keeps its state** (the lead's decision after the security review of
      ``84b5771``, D-105's dated note). A grown one is grown already. One that is not grown is
      vocabulary, in every scheme, and stays so: linking it changes nothing anyone is offered, where
      growing it would take it out of every audience that reads no source carrying it, because of a
      link on material that audience may not be able to read. The name form never fetches one, since
      it is offered and the name form answers 409 first; ``confirm_proposed_tag`` does, for a
      proposal made before the name became vocabulary, and so does the classifier, for a scheme built
      before it did.
    - **An inactive tag it fetched is reactivated, and grown, only when every role can read
      ``document``** (``_every_role_reads``; D-128's security review, finding 1). Otherwise it is left
      exactly as it is: retired, its ``grown`` unchanged. A retired tag can still be carried by
      material every role reads, linked before it was retired, and it is offered nowhere only
      because it is inactive. Reactivating it from material some role cannot read would put it back
      in the options of every document that role reads, through that old carrier, while nothing
      that role can read had changed, and so would show that the restricted material carries it.
      Reactivated from a document every role reads, the change is that document's own link, which
      every role can see, exactly as for a value created there. This path is D-105's own as well as
      D-128's: ``apply_tag``'s name form reactivated a retired Topic the same way.

    ``grown`` is never unset here or anywhere.
    """
    if not created:
        if tag.active:
            return
        if not _every_role_reads(document):
            return
    changed = []
    if not tag.active:
        tag.active = True
        changed.append("active")
    if not tag.grown:
        tag.grown = True
        changed.append("grown")
    if changed:
        tag.save(update_fields=changed)


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


def confirm_proposed_tag(document: Document, dimension: str, value: str) -> ContentTag:
    """A person confirms a value the classifier held below the threshold, in Project, Process or
    Topic (D-128, which generalised the Topic-only confirmation that preceded it).

    The proposal is matched by its dimension and normalised value, so a value proposed under
    another dimension is not this one; none matching raises ``NotOnThisDocument``, the route's 404.
    The Tag is fetched or created by dimension and normalised name and brought into use
    (``_bring_into_use``): one created is marked grown, as the classifier and ``apply_tag``'s name
    form mark it, so a value brought in from a proposal is never vocabulary (D-105's dated note of
    10 November 2026, night). An active one fetched keeps its state, so confirming a proposal made
    before its name became vocabulary links the vocabulary tag and leaves it vocabulary. **An
    inactive one is reactivated, and grown, only when every role can read the document;** on a
    document some role cannot read it stays retired, and the link is still made and confirmed
    (D-128's security review, finding 1). The reply is the same whether the Tag was created,
    fetched, reactivated or left retired, and nothing returned says which (CLAUDE.md invariant 1;
    ``apply_classification`` rule 4).

    The document's link is created ``applied_by="ai"`` (the suggestion was the machine's),
    confirmed, not provisional, not removed, with the proposal's confidence. A link the document
    already holds, removed or held, is confirmed and put back, keeping the confidence it has, or
    taking the proposal's if it has none. The proposal leaves ``proposed_tags``. Raises
    ``InvalidClassification`` for a name longer than the column, which no run proposes since
    D-128 (it discards one) but an older row might hold.
    """
    name = normalise_tag_name(value or "")
    with transaction.atomic():
        analysis = _analysis_of(document, for_update=True)
        proposal = _proposal(analysis, dimension, name)
        if len(name) > NAME_MAX_LENGTH:
            raise InvalidClassification(f"A tag name may not exceed {NAME_MAX_LENGTH} characters.")
        tag, created = Tag.objects.get_or_create(tag_name=name, dimension=dimension)
        _bring_into_use(tag, created, document)
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
                removed=False,
                confidence=confidence,
            )
        else:
            link.confirmed = True
            link.provisional = False
            link.removed = False  # a person confirming the value wants it on the document
            if link.confidence is None:
                link.confidence = confidence
            link.save(update_fields=["confirmed", "provisional", "removed", "confidence"])
        _drop_proposal(analysis, dimension, name)
    return link


def reject_proposed_tag(document: Document, dimension: str, value: str) -> None:
    """A person rejects a held value (D-128), and the rejection sticks (the requirements audit of
    D-128, finding A5: the lead's decision of 13 November 2026).

    Matched as ``confirm_proposed_tag`` matches it, by dimension and normalised value;
    ``NotOnThisDocument`` when it is not proposed, the route's 404. The proposal leaves
    ``proposed_tags``, and an entry ``{"dimension", "value", "confidence"}`` joins ``rejected_tags``
    with the machine's confidence from the proposal, so the machine assignment is kept alongside the
    person's decision (FR-10's correction clause; UC-09 A3). An entry already there for that
    dimension and value is replaced, so one entry is kept, carrying the latest proposal's
    confidence. No Tag is created or changed and no link is made.

    Every later classify, reprocess or ``classify_documents`` run skips the value on this document:
    not proposed, created, reactivated or linked, at any confidence, in the scheme or out of it
    (``apply_classification`` rule 4b). Until the fix a rejection recorded nothing, and the next run
    that suggested the value created and linked it at or above the threshold, or proposed it again
    below it. A person may still apply it themselves (``apply_tag``, by id or by the Topic name
    form): the rejection blocks the machine, never a person.
    """
    name = normalise_tag_name(value or "")
    with transaction.atomic():
        analysis = _analysis_of(document, for_update=True)
        proposal = _proposal(analysis, dimension, name)
        analysis.rejected_tags = [
            entry for entry in analysis.rejected_tags if not _is_entry(entry, dimension, name)
        ] + [{"dimension": dimension, "value": name, "confidence": proposal.get("confidence")}]
        analysis.proposed_tags = [
            entry for entry in analysis.proposed_tags if not _is_entry(entry, dimension, name)
        ]
        analysis.save(update_fields=["proposed_tags", "rejected_tags"])


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


def _is_entry(entry, dimension: str, name: str) -> bool:
    """Whether a ``proposed_tags`` or ``rejected_tags`` entry is ``name`` in ``dimension`` (D-128)."""
    return (
        isinstance(entry, dict)
        and dimension in REPOSITORY_TAG_DIMENSIONS
        and entry.get("dimension") == dimension
        and entry.get("value") == name
    )


def _rejected(analysis: DocumentAnalysis) -> set[tuple[str, str]]:
    """The (dimension, value) of every proposal a person rejected on ``analysis``'s document, for
    rule 4b (the requirements audit of D-128, finding A5). Only this document's own row is read."""
    return {
        (entry.get("dimension"), entry.get("value"))
        for entry in analysis.rejected_tags
        if isinstance(entry, dict)
    }


def _proposal(analysis: DocumentAnalysis, dimension: str, name: str) -> dict:
    for proposal in analysis.proposed_tags:
        if _is_entry(proposal, dimension, name):
            return proposal
    raise NotOnThisDocument("No such proposed tag on this document.")


def _drop_proposal(analysis: DocumentAnalysis, dimension: str, name: str) -> None:
    analysis.proposed_tags = [
        proposal for proposal in analysis.proposed_tags
        if not _is_entry(proposal, dimension, name)
    ]
    analysis.save(update_fields=["proposed_tags"])
