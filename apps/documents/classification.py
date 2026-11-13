"""FR-10's apply layer: the scheme a document is classified against, and what becomes of the
model's suggestions (docs/decisions.md D-105).

``AIService.classify_document`` (apps/ai/classification.py) returns a ``DocumentClassification``:
the model's suggestions AS MADE, with nothing decided. Everything FR-10's Server-End calls
business logic is decided here, in application code over those suggestions, and never by the
model:

- **confidence** — "a confidence value is recorded with each assignment. Assignments below the
  configured threshold are marked provisional and presented for confirmation rather than applied
  silently." The configured threshold is one per kind of assignment (D-129), each the classifying
  model's own, and each compared in one place:
  - a type or a tag in ``_is_provisional``, against ``confidence_threshold``:
    ``CLASSIFICATION_CONFIDENCE_THRESHOLD``, or the model's own value from
    ``CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL`` (D-122);
  - a department in ``_department_is_provisional``, against ``department_threshold``: the model's
    own value from ``CLASSIFICATION_DEPARTMENT_CONFIDENCE_THRESHOLD_BY_MODEL``, else the shared
    value for that model.
- **controlled taxonomy growth** — FR-10: "suggested tags are matched against values already held
  in the scheme. A value that does not match may be proposed only in the Topic dimension and
  requires user confirmation before it is created; suggestions falling outside the scheme in the
  Department, Project or Process dimensions are discarded." Objective 05's clause 3 says the same.
  **Both hold as written** (D-129, 13 November 2026, which reverses D-128's creation of values):
  - a Topic value outside the scheme is proposed, at any confidence, for a person to confirm or
    reject (``confirm_proposed_tag``, ``reject_proposed_tag``);
  - a Project or Process value outside the scheme is discarded, as is a department;
  - the classifier creates, links and reactivates no Tag outside the scheme.

  From 12 to 13 November 2026 D-128 created and applied such a value at or above the threshold.
  Rules 3 and 4 of ``apply_classification``.
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
  10 November 2026, night), nor proposes it again, in any dimension. A proposal a person rejects
  is kept the same way, in ``rejected_tags`` with the machine's confidence, and later reprocessing
  never proposes or links that value on the document, even once it is in the scheme
  (``reject_proposed_tag``; the requirements audit of D-128, finding A5).

**The scheme is built for the document's own audience** (``tag_scheme``), so the prompt never
lists a value that exists only on material some reader of this document may not see, and a
suggestion that names one anyway is treated exactly as a value no Tag has (``apply_classification``
rule 4, CLAUDE.md invariant 1). Its departments are the active ``Department`` names admitted for that
audience (D-129): a hidden (grown) one only for an audience that reads everything, and a department
in use on documents but not in the list never.

**What this module does not do.** It calls the provider only in ``classify_document_now``; it
decides no status code (the route and the ingestion hook map the exceptions below); and it never
resolves a ``Document`` for a caller: every function takes one the caller already reached through
``scoped_documents`` (D-46, D-53). It lives in ``apps/documents`` beside ``deletion.py``, outside
the request-serving packages ``apps/api/tests/test_source_rows_fail_closed.py`` scans, for the
reason that module gives: it reads managers directly, for writes against a row already resolved
and for the vocabulary tables.

**Lock order** (the focused re-audit of ``5c60564``, finding N1; narrowed after the re-audit of
``7377d38``, finding N3).

- **The document and the analysis row.** Every function that writes a document's classification
  records and takes both the document row and its ``DocumentAnalysis`` row takes the document
  first. No function takes the analysis row and then the document.
- **A run takes no Tag row.** Since D-129 rule 4 only links values already in the scheme
  (``_link_tag`` reads the tag unlocked, then creates or updates this document's link). It creates,
  updates and reactivates no tag. Only a person's decisions take Tag rows, and no cycle follows:
  - ``apply_tag`` and ``confirm_proposed_tag`` take a tag and then this document's links, holding
    the document or the analysis row first, and a run holds both for its whole transaction;
  - ``confirm_tag`` and ``reject_tag`` take one link and wait on nothing after it;
  - ``retire_tag`` and ``create_tag`` take one tag.

  From D-128 until D-129 a run also created and reactivated tags, value by value; the narrowing
  after the re-audit of ``7377d38`` (finding N3) was about that.

Each one:

- ``apply_classification``: the document, the analysis row, then this document's links (rule 4c).
  It takes no Tag row.
- ``confirm_classification``: the document, then the analysis row, and only then the document's
  department, which is already locked. Until N1 it took the analysis row first and then wrote the
  document, so a confirmation during a reprocess, which holds the document while classification
  runs, deadlocked with the run.
- ``apply_tag``: the document, then a tag, then the document's links. It never touches the analysis
  row.
- ``confirm_proposed_tag``: the analysis row, then a tag, then the document's link. It never writes
  the document.
- ``reject_proposed_tag``: the analysis row only. It waits on nothing after it.
- ``confirm_tag``, ``reject_tag``: one link only.
- Elsewhere, ``delete_document`` (apps/documents/deletion.py) takes the document, then the analysis
  row, then the links, and deletes the document last. Until N1 it locked the links before the
  analysis row, which its cascade deleted at the end, so a person confirming a proposal deadlocked
  with a deletion. ``reprocess_document`` holds the document while classification runs, and
  ``retire_tag`` and ``create_tag`` (taxonomy.py) take one tag row. ``create_department`` and
  ``retire_department`` (taxonomy.py, D-129) take one department row and wait on nothing after it;
  nothing in this module locks a department row (``tag_scheme`` and rule 3's ``_still_listed`` read
  them unlocked).

apps/documents/tests/test_classification_lock_order.py runs both cycles N1 named, on two
connections.
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
    CLASSIFICATION_DEPARTMENT_CONFIDENCE_THRESHOLD_BY_MODEL,
    DOCUMENT_TYPES,
    REPOSITORY_TAG_DIMENSIONS,
    ROLE_NAMES,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import (
    ContentTag,
    Department,
    Document,
    DocumentAnalysis,
    Tag,
    normalise_tag_name,
)
from apps.retrieval.scoping import reads_everything, scoped_documents, scoped_meetings

logger = logging.getLogger(__name__)

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES

# The confidence columns are decimal(4,3). The provisional rule compares the value the model
# reported, never this three-place rendering of it (see _is_provisional).
_CONFIDENCE_PLACES = Decimal("0.001")

# Rule 4d's one refusal of a value outside the scheme, whatever its dimension (D-129, keeping the 500
# fix of D-128's security review): a value that cannot be stored. A NUL (U+0000) is refused by a text
# column and by jsonb alike, and a lone surrogate (Unicode category Cs), which ``json.loads`` makes of
# a \ud800 escape in a reply, cannot be encoded for either. Such a value is discarded, recorded
# with U+FFFD, the replacement character, in place of each such character (``_recordable``).
_NUL = chr(0)
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
    (``apply_classification`` rule 4d: a Topic proposed, a Project or Process discarded, D-129), and
    nothing a reader can see moves when links on
    material they cannot read are made or destroyed. Whether a role can read a source is decided by
    ``scoped_documents`` and ``scoped_meetings`` from apps/retrieval/scoping.py, the one place the
    FR-11 predicate is written (D-53, D-66); nothing here tests ``visible_to_roles`` itself.

    - ``doc_types`` is DOCUMENT_TYPES: a fixed list that says nothing about the corpus.
    - ``departments`` is the active ``Department`` names, the list an Administrator keeps on the
      Tags page (D-129, the lead's decision of 13 November 2026). A department that is not grown is
      vocabulary and always in. **A grown one**, which ``documents 0015`` seeds for a department
      found only on documents some role cannot read, **is in only for an audience every role of
      which reads everything** (``reads_everything``; today an Administrator-only document). It
      consults no carrier, unlike a grown tag: FR-08's upload field and the classification
      confirm/edit control both take any department, so a reader could make a document they read
      carry a hidden name themselves, and a rule that admitted the name through that document
      would answer "listed, applied" where an unknown name answers "discarded" (D-129's security
      review, finding F1). So the departments of a document some role in a narrower scope reads
      never depend on whether a grown row exists. A retired department is in no scheme, and **a
      department in use on documents but not in the list is not offered**: the list is the scheme,
      and FR-08's upload field stays free text. Until D-129 this was the intersection, across the
      audience, of the distinct non-blank ``Documents.department`` values of the documents each
      role may read; until finding F1 a grown department was admitted where every audience role
      read a document carrying it.
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
      carrier. ``grown`` is set on a value a person's confirmation of a proposal creates or
      reactivates (``confirm_proposed_tag``), on a Topic a person's ``apply_tag`` name form creates
      or reactivates (the lead's oracle review), and by ``documents 0011`` and the seed script's
      linked mode on every tag carried only by material some role cannot read. The classifier sets
      it on nothing: since D-129 it creates and reactivates no tag. (From D-128 until D-129 it set
      it on the values it created.) An active tag either person's path fetches keeps its value. An
      inactive one is reactivated only from a document every role reads (``_bring_into_use``;
      D-128's security review, finding 1), so a link on material some role cannot read never brings
      a retired value back into a scheme through an old readable carrier. So a Topic a person brings
      in on an Administrator-only document is carried by that document alone and offered only to
      an audience every role of which reads it: never to, and never in the prompt for, a document
      an Employee reads, while that stays so. A value an Administrator adds (``POST /api/tags``,
      D-128) is not grown: vocabulary, in every scheme, as a seeded value is.

    **An empty audience gets the full scheme**, every active tag and every active department. A
    document whose ``visible_to_roles`` is empty is readable by nobody (``scoped_*`` fail closed),
    so there is no reader to protect. D-29 refuses an empty list at upload, so this arises only from
    direct row edits.

    **The scheme is built for the audience at classification time.** A document later widened to
    more roles keeps the values it was classified against; widening should reclassify.

    **A role name scoping does not know** (one missing from EFFECTIVE_ROLES) reads nothing, so
    every grown tag and every grown department is withheld from a document it is in the audience
    of, as ``scoped_documents`` and ``reads_everything`` fail closed. Vocabulary, a tag or a
    department that is not grown, is still in: it says nothing about any source, so there is
    nothing for that reader to be kept from.
    """
    audience = list(dict.fromkeys(document.visible_to_roles))  # distinct, in order
    active_tags = Tag.objects.filter(
        active=True, dimension__in=REPOSITORY_TAG_DIMENSIONS
    ).values_list("id", "dimension", "tag_name", "grown")
    active_departments = list(Department.objects.filter(active=True).values_list("name", "grown"))

    if audience:
        readable_tag_ids: set | None = None
        for role_name in audience:
            documents = scoped_documents(role_name=role_name)
            meetings = scoped_meetings(role_name=role_name)
            role_tag_ids = set(
                ContentTag.objects.filter(
                    Q(source_type=DOCUMENT_SOURCE_TYPE, source_id__in=documents.values("id"))
                    | Q(source_type=MEETING_SOURCE_TYPE, source_id__in=meetings.values("id"))
                ).values_list("tag_id", flat=True)
            )
            readable_tag_ids = (
                role_tag_ids if readable_tag_ids is None else readable_tag_ids & role_tag_ids
            )
        # A grown department needs an audience that reads everything, and no carrier (finding F1).
        audience_reads_everything = all(reads_everything(role_name) for role_name in audience)

        def admitted(tag_id, grown) -> bool:
            # Vocabulary is in whatever its links; a grown tag only on a source every role reads.
            # Links on material some reader cannot see are never consulted for vocabulary, so making
            # or destroying them moves nothing a reader of this document is offered.
            return not grown or tag_id in readable_tag_ids

        def department_admitted(name, grown) -> bool:
            # Vocabulary always; a grown department only for an audience that reads everything,
            # whatever any document carries (D-129's security review, finding F1).
            return not grown or audience_reads_everything

    else:

        def admitted(tag_id, grown) -> bool:
            return True

        def department_admitted(name, grown) -> bool:
            return True

    departments = {name for name, grown in active_departments if department_admitted(name, grown)}

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
      confirming a proposal of its name made before it was vocabulary, which links it and leaves it
      vocabulary (``_bring_into_use``). It leaves only when an Administrator retires or deletes it
      (``DELETE /api/tags/{id}``). A retired tag comes back, grown, only through a person, on a
      document every role reads: they name it there (a Topic, ``apply_tag``) or confirm a proposal
      of it there (``confirm_proposed_tag``). The classifier never brings one back: since D-129 a
      retired value it suggests is proposed (a Topic) or discarded (a Project or Process), whatever
      its confidence. From D-128 until D-129 it reactivated one at or above the threshold.
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
       is discarded and nothing is written. **So is a department in the scheme that is no longer an
       active ``Department`` when the suggestion is applied** (``_still_listed``; D-129's security
       review, finding F2): the scheme was built before the provider call, and an Administrator
       may retire or delete the department while the call runs. That is one unlocked ``exists()``
       read, and its answer is the one an unknown name gets, so it adds no oracle. Inside and below
       **the department's own threshold**
       is provisional and ``Documents.department`` is untouched. That threshold is
       ``department_threshold(model)`` (D-129, the lead's decision of 13 November 2026): 0.30 for
       claude-haiku-5-5, and for a model not listed the shared value the type and the tags use, so
       gemma3:4b keeps 0.95. Inside and at or above it, **the machine fills only
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
    4. **Tags**, each suggestion by its dimension and normalised name, in this order. Objective 05's
       clause 3 holds as written (D-129, 13 November 2026, which reverses D-128's creation of
       values):

       a. **Ignored**, and logged: a dimension outside REPOSITORY_TAG_DIMENSIONS, or an empty name.
       b. **A person removed or rejected it.** This document holds a REMOVED link to the tag of
          that dimension and name, or its ``rejected_tags`` holds that dimension and name because a
          person rejected it as a proposal (``reject_proposed_tag``). In any of the three
          dimensions, at any confidence, and before the in-scheme match below, so a rejected value
          is not linked even once it has entered the scheme (an Administrator added it, say). The
          suggestion is skipped: not linked, not proposed, not discarded, not recorded (FR-10's
          correction clause, "not overwritten by later reprocessing"; D-105's dated note of 10
          November 2026, night, generalised from Topic by D-128; the rejection since the
          requirements audit of D-128, finding A5). Only this document's own links and analysis row
          are read.
       c. **In the scheme** (``scheme.tags[dimension]``) and still an active Tag: ``_link_tag``,
          unchanged. A link a person applied or confirmed is left as it is; an unconfirmed AI link
          takes the new confidence and provisional flag; otherwise a link is created,
          ``applied_by="ai"``, unconfirmed, provisional when below the threshold.
       d. **Otherwise**, outside the scheme or deactivated since it was built. The suggestions of
          one dimension and name are taken together at their highest confidence. No Tag is created,
          linked or reactivated, at any confidence:

          - **a Topic** is proposed: held in ``proposed_tags`` as ``{"dimension", "value",
            "confidence"}`` for a person to confirm or reject (``confirm_proposed_tag``,
            ``reject_proposed_tag``), at any confidence, a long or many-worded one included. A
            person who confirms one longer than the column gets ``InvalidClassification``, the
            route's 400;
          - **a Project or Process value** is discarded into ``discarded_suggestions`` as
            ``{"dimension", "value", "confidence"}``, at any confidence;
          - **a value that cannot be stored**, holding a NUL or a lone surrogate, is discarded
            whatever its dimension, recorded with U+FFFD in place of each such character
            (``_recordable``). That is the 500 fix from D-128's security review, kept.

       ``proposed_tags`` and ``discarded_suggestions`` are REPLACED by each run. Links this run
       does not mention are left alone. From 12 to 13 November 2026, D-128 created and linked a value
       outside the scheme at or above the threshold, and proposed one in any of the three dimensions
       below it. D-129 reverses that.

    **Why every value outside the scheme gets the same treatment (CLAUDE.md invariant 1).** Seen
    from a reader of this document, such a value is one of three things, and the reader must not be
    able to tell which: (a) no Tag has it; (b) an active, grown Tag that only material some reader
    of this document cannot see carries (an active Tag that is not grown is vocabulary and always
    in the scheme); (c) a retired Tag. What a reader can observe is identical for all three: a Topic
    is a proposal, and a Project or Process value is discarded and never shown. Nothing returned or
    recorded says whether a Tag row exists, which is the precedent D-105's note set for a person's
    name: a retired value is in no scheme, so answering it differently would disclose it. The
    classifier never brings a retired value back. Only a person's confirmation or Topic name form
    does, on a document every role can read (``_bring_into_use``; D-128's security review, finding
    1).

    The document row is locked first, as deletion and reprocess lock it, so a classification
    cannot write links for a document a concurrent delete is removing. The analysis row is locked
    next, as a person's decisions lock it, so a rejection committed meanwhile is neither missed by
    rule 4b nor overwritten when this run saves the row. This document's links come after, value by
    value, and since D-129 a run takes no Tag row, so nothing cycles ("Lock order" above). Every
    writer here keeps the document before the analysis row. A person's decision that writes the
    document, ``confirm_classification``, locks the document first as well, so it waits for this
    run rather than deadlocking with it. Until the focused re-audit of
    ``5c60564`` (finding N1) this docstring claimed that a person's decision took only the analysis
    lock. That was false of ``confirm_classification``, and the auditor's probe deadlocked on it.
    """
    if classification.doc_type.value not in DOCUMENT_TYPES:
        # The value is the model's and is not quoted: ingestion logs this message and
        # classify_documents writes it uncut. Unreachable while the parser holds the type to the
        # scheme's list; the same wording as confirm_classification's check of a person's input.
        raise InvalidClassification(f"doc_type must be one of {', '.join(DOCUMENT_TYPES)}.")
    now = timezone.now()
    department_value = (classification.department.value or "").strip()

    with transaction.atomic():
        locked = Document.objects.select_for_update().filter(pk=document.pk).first()
        if locked is None:
            raise NotOnThisDocument("The document no longer exists.")
        # The analysis row next, after the document and before any tag or link: the module's lock
        # order, which a person's decisions keep too. This run saves every field of the row, so
        # without the lock a rejection committed between this read and that save would be
        # overwritten by this stale copy, and would not stick (rule 4b).
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
            if department_value not in scheme.departments or not _still_listed(department_value):
                # Outside the scheme, or retired or deleted since it was built (finding F2).
                analysis.department_outcome = ASSIGNMENT_DISCARDED
            elif _department_is_provisional(classification.department.confidence, classification.model):
                # Below the department's own threshold (D-129), not the type's and the tags'.
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

        # Rule 4: the tags (Objective 05's clause 3 as written; D-129).
        ignored = 0
        # 4b: the (dimension, name) of every tag a person removed from this document, and of every
        # proposal a person rejected on it (``rejected_tags``; the requirements audit of D-128,
        # finding A5), in any dimension. A removed one still in the scheme would reach _link_tag,
        # which leaves a removed link alone; any other would otherwise be proposed or linked again, a
        # rejected one even once it has entered the scheme, and a person has already said no to it
        # here. Read from this document's own links and its own analysis
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

        # One treatment for every value outside the scheme, whether no Tag has it, a grown Tag only
        # material some reader cannot see carries, or a retired Tag (CLAUDE.md invariant 1; see the
        # docstring). Nothing below says which it was, and no Tag is created, linked or reactivated:
        # Objective 05's clause 3, as written (D-129, reversing D-128's creation).
        proposed, discarded = [], []
        for (dimension, name), confidence in outside.items():
            if not _storable(name):
                # A NUL or a lone surrogate: discarded, recorded with U+FFFD so the record can be
                # written. Before the fix it answered the classify route 500.
                discarded.append(
                    {"dimension": dimension, "value": _recordable(name), "confidence": confidence}
                )
            elif dimension == TOPIC_DIMENSION:
                # Proposed for a person to confirm or reject, at any confidence.
                proposed.append({"dimension": dimension, "value": name, "confidence": confidence})
            else:
                # Project or Process: discarded, at any confidence.
                discarded.append({"dimension": dimension, "value": name, "confidence": confidence})
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


def department_threshold(model: str) -> float:
    """FR-10's threshold for a department ``model`` suggested (D-129, the lead's decision of 13
    November 2026).

    A model CLASSIFICATION_DEPARTMENT_CONFIDENCE_THRESHOLD_BY_MODEL lists gets its own department
    value: claude-haiku-5-5's 0.30, chosen by D-106's rule on departments alone. Any other gets the
    shared value for that model, ``confidence_threshold(model)``, so gemma3:4b keeps 0.95. The type and
    the tags never read this. Both maps are read at call time, so a test that reassigns one is
    honoured.
    """
    if model in CLASSIFICATION_DEPARTMENT_CONFIDENCE_THRESHOLD_BY_MODEL:
        return CLASSIFICATION_DEPARTMENT_CONFIDENCE_THRESHOLD_BY_MODEL[model]
    return confidence_threshold(model)


def _is_provisional(confidence: float, model: str) -> bool:
    """FR-10's confidence comparison for a type or a tag: below the threshold is provisional; at it
    is applied.

    The threshold is the classifying model's own (``confidence_threshold``, D-122). A department is
    compared against its own threshold instead (``_department_is_provisional``, D-129).
    """
    return confidence < confidence_threshold(model)


def _department_is_provisional(confidence: float, model: str) -> bool:
    """FR-10's confidence comparison for a department, rule 3's: below the department's threshold
    is provisional; at it is applied (``department_threshold``, D-129)."""
    return confidence < department_threshold(model)


def _still_listed(name: str) -> bool:
    """Whether ``name`` is still an active ``Department`` (rule 3; D-129's security review, finding
    F2). ``name`` is a spelling the scheme took from a row, so it is compared exactly.

    One ``exists()`` read and no lock, deliberately. A ``FOR SHARE`` lock on the row would serialise
    with ``retire_department``'s ``FOR UPDATE``, but an ingestion classifies inside its own transaction
    and then embeds, so the lock would hold an Administrator's ``DELETE`` for the whole of the
    embedding. What is left is the window between this read and the commit: a department retired in
    it is written as a retired department is, which is the state every retired department's
    documents are in anyway, and the state a person typing it produces."""
    return Department.objects.filter(name=name, active=True).exists()


def _unstorable(character: str) -> bool:
    """A NUL or a lone surrogate (Unicode category Cs): a character neither a text column nor jsonb
    can hold, for rule 4d (D-129, keeping the 500 fix of D-128's security review). Any other
    character is kept: a Topic of many words, or one holding ";", is proposed, as before D-128."""
    return character == _NUL or unicodedata.category(character) == "Cs"


def _storable(name: str) -> bool:
    """Whether rule 4d may propose ``name`` or record it as written: it holds no NUL and no lone
    surrogate (``_unstorable``)."""
    return not any(_unstorable(character) for character in name)


def _recordable(name: str) -> str:
    """``name`` as ``discarded_suggestions`` records it: each NUL or lone surrogate replaced by U+FFFD,
    so the jsonb column always accepts the record. A NUL made the classify route answer 500 (D-128's
    security review). Every other character is kept as the model wrote it."""
    return "".join(
        _REPLACEMENT_CHARACTER if _unstorable(character) else character for character in name
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

    **The document row is locked first, then the analysis row** (the module's lock order; the focused
    re-audit of ``5c60564``, finding N1). This function writes the document's department, so taking
    the analysis row first, as it did until then, was the opposite of ``apply_classification``'s
    order. A person confirming during a reprocess, which holds the document while classification
    runs, then deadlocked with the run. Now the confirmation waits for the run and goes after it.
    Raises ``NotOnThisDocument`` if the document was deleted meanwhile.
    """
    if doc_type is not None and doc_type not in DOCUMENT_TYPES:
        raise InvalidClassification(f"doc_type must be one of {', '.join(DOCUMENT_TYPES)}.")
    if department is not None:
        department = department.strip()
        if len(department) > NAME_MAX_LENGTH:
            raise InvalidClassification(f"department may not exceed {NAME_MAX_LENGTH} characters.")

    with transaction.atomic():
        if Document.objects.select_for_update().filter(pk=document.pk).first() is None:
            raise NotOnThisDocument("The document no longer exists.")
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
    a later run neither proposes nor links a removed value again, in any dimension
    (``apply_classification`` rule 4b). No read lists a removed link. The ``Tag`` row, a
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
      controlled taxonomy growth lets only Topic grow (D-129: the classifier creates no value).
      An Administrator adds a value in any of the three dimensions through ``POST /api/tags``
      (D-128), and this form is as it was. **The 409 and the rule that keeps it from disclosing
      anything:** a name that is an active Topic in this document's scheme raises
      ``TopicAlreadyOffered``, because the caller is already offered it. A Topic of that name that
      exists but is NOT in the scheme is
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
      ``confirm_proposed_tag`` leaves it (``_bring_into_use``). The answer is the
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
    """A tag a person brings into use by name on ``document``: by confirming a proposal
    (``confirm_proposed_tag``), or by ``apply_tag``'s Topic name form. The classifier never calls
    it: since D-129 it creates and reactivates no tag, as rule 4d did from D-128 until D-129. The
    caller makes or confirms the document's link whatever happens here.

    - **One this call ``created``** is made grown, so that it is never vocabulary: it is offered only
      where every audience role reads a source carrying it (``tag_scheme``; D-105's dated note of 10
      November 2026, night). A new tag has no carrier but ``document``, wherever that is.
    - **An active tag it fetched keeps its state** (the lead's decision after the security review of
      ``84b5771``, D-105's dated note). A grown one is grown already. One that is not grown is
      vocabulary, in every scheme, and stays so: linking it changes nothing anyone is offered, where
      growing it would take it out of every audience that reads no source carrying it, because of a
      link on material that audience may not be able to read. The name form never fetches one, since
      it is offered and the name form answers 409 first; ``confirm_proposed_tag`` does, for a
      proposal made before the name became vocabulary.
    - **An inactive tag it fetched is reactivated, and grown, only when every role can read
      ``document``** (``_every_role_reads``; D-128's security review, finding 1). Otherwise it is left
      exactly as it is: retired, its ``grown`` unchanged. A retired tag can still be carried by
      material every role reads, linked before it was retired, and it is offered nowhere only
      because it is inactive. Reactivating it from material some role cannot read would put it back
      in the options of every document that role reads, through that old carrier, while nothing
      that role can read had changed, and so would show that the restricted material carries it.
      Reactivated from a document every role reads, the change is that document's own link, which
      every role can see, exactly as for a value created there. The rule closes D-105's own path,
      ``apply_tag``'s name form, which reactivated a retired Topic the same way, and it applies to
      ``confirm_proposed_tag``.

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
    """A person confirms a proposal. Since D-129 the classifier proposes a Topic outside the scheme,
    at any confidence. A Project or Process proposal is one a run made while D-128 was in force,
    and this function confirms it the same way: it is dimension-generic (D-128).

    The proposal is matched by its dimension and normalised value, so a value proposed under
    another dimension is not this one; none matching raises ``NotOnThisDocument``, the route's 404.
    The Tag is fetched or created by dimension and normalised name and brought into use
    (``_bring_into_use``): one created is marked grown, as ``apply_tag``'s name form marks it, so a
    value brought in from a proposal is never vocabulary (D-105's dated note of
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
    ``InvalidClassification`` for a name longer than the column, the route's 400. A run proposes a
    Topic of any length (D-129), so this is where a long one is refused.
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
    """A person rejects a proposed value (the route is D-128's; since D-129 a run proposes only a
    Topic, at any confidence), and the rejection sticks (the requirements audit of D-128, finding
    A5: the lead's decision of 13 November 2026).

    Matched as ``confirm_proposed_tag`` matches it, by dimension and normalised value;
    ``NotOnThisDocument`` when it is not proposed, the route's 404. The proposal leaves
    ``proposed_tags``, and an entry ``{"dimension", "value", "confidence"}`` joins ``rejected_tags``
    with the machine's confidence from the proposal, so the machine assignment is kept alongside the
    person's decision (FR-10's correction clause; UC-09 A3). An entry already there for that
    dimension and value is replaced, so one entry is kept, carrying the latest proposal's
    confidence. No Tag is created or changed and no link is made.

    Every later classify, reprocess or ``classify_documents`` run skips the value on this document:
    neither proposed nor linked, at any confidence, in the scheme or out of it
    (``apply_classification`` rule 4b). Until the fix a rejection recorded nothing, and the next run
    that suggested the value proposed it again (or, under D-128, created and linked it at or above
    the threshold). A person may still apply it themselves (``apply_tag``, by id or by the Topic name
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
