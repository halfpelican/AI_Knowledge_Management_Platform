"""Presentation for FR-12's answer path: section 7.10 step 11, and nothing else.

Step 11 does two things before it records, and both are presentation rather than
retrieval, which is why they live here and not in ``apps/retrieval/pipeline.py``:

- ``composeAnswerWithInlineCitations(verifiedStatements)`` — the numbering. FR-12's
  Front-End clause asks for "a written answer with numbered inline citations", so the
  reply carries each verified statement with its position, starting at
  ``FIRST_POSITION``. The number is **imported from the query log** rather than written
  again, so the "[2]" a reader sees is the same 2 stored on that statement's
  ``AnswerCitation`` row and the traceability clause means what it says. No prose is
  composed: the statements are returned as a list and the interface places the markers,
  because a single string with "[1]" spliced into it cannot be re-checked against
  anything once it has been joined.
- ``resolveSourceDetails(suppliedPassageIds)`` — the Sources panel. FR-12: "a Sources
  panel lists every item consulted with its date, allowing the user to judge how current
  the underlying material is."

**Consulted, not cited.** ``resolve_sources`` is given every passage the outcome carries
— the ones that were actually supplied to generation — and resolves all of them, whether
a surviving statement cited them or not. That is 7.10's own argument: the panel is what
lets the reader "judge how current the underlying material is", and a panel listing only
the two items that happened to be cited would misdescribe what the answer was drawn from.
It is not in tension with invariant 6, which is about uncited *statements*: a title and a
date are not a factual claim about the organisation, and every item here is inside the
asking role's scope by construction.

**Why there is no permission predicate in this module.** Every passage reached it through
``candidate_chunks``, whose query carries both FR-11 predicates, so the chunk's stamped
``visible_to_roles`` already admitted this role (invariant 1, and invariant 2 for why the
stamp is on the chunk). Re-deriving the scope here would be a second filter in a second
place, and the one thing worse than one permission filter is two that can disagree.
Changing a source's visibility re-stamps its chunks in the same transaction (D-17), so
the chunk is the authoritative record of what this role may read, and the source row is
consulted only for a title and a date.

**A passage whose source row has gone is dropped from the panel**, not rendered with a
blank title. Nothing in the M6 build deletes a Document or a Meeting — FR-15's
permissioned deletion is Stage 5 — so this is unreachable today; when it is reachable, an
entry with no title and no date is not something the panel can render or link to, and a
placeholder would be inventing text about material that no longer exists.
"""

from dataclasses import dataclass, fields
from datetime import date, datetime
from uuid import UUID

from apps.core.constants import SOURCE_TYPES
from apps.documents.models import Document
from apps.meetings.models import Meeting
from apps.retrieval.models import Conversation
from apps.retrieval.pipeline import RetrievalOutcome
from apps.retrieval.query_log import FIRST_POSITION

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES


@dataclass(frozen=True)
class NumberedStatement:
    """One verified statement and the citation number the interface renders beside it."""

    position: int
    text: str
    chunk_id: str


@dataclass(frozen=True)
class ConsultedPassage:
    """One passage that was supplied to generation, under the item it came from.

    FR-12: "Each citation expands to display the source passage and links to the source
    document or meeting." The expansion needs the passage text, and no endpoint in the
    API returns a chunk, so the text travels with the answer that was drawn from it.
    """

    chunk_id: str
    text: str


@dataclass(frozen=True)
class ConsultedSource:
    """One item consulted: its identity, its title, its date, and its passages.

    Nested rather than flat, so that "which item did this citation come from" is answered
    by the shape of the reply instead of by a join the client has to get right. One list
    for the panel, one lookup for an expanding citation.

    ``date`` is the source's own date and so is not one type — ``uploaded_at`` for a
    document (a datetime), ``meeting_date`` for a meeting (a date) — exactly as
    ``SearchResult.date`` is. The serializer renders whichever arrived with DRF's own
    field, so the string is the one ``GET /api/documents`` and ``GET /api/meetings``
    already give for the same row.
    """

    source_type: str
    source_id: UUID
    title: str
    date: date | datetime
    passages: tuple[ConsultedPassage, ...]


@dataclass(frozen=True)
class AnswerReply:
    """What ``POST /api/ask`` returns, on all three of the pipeline's exits.

    **This dataclass has no field for ``no_answer_reason`` and none for
    ``rejected_count``, and that absence is the security property of this module.** Both
    are record-only: ``QueryLog``'s docstring says so beside each column. The two
    no-answer paths return byte-identical replies on purpose — 7.10 returns
    ``response(200, answered = FALSE, message = NO_ANSWER_MESSAGE)`` from step 6 and from
    step 10, identically — because a caller able to tell them apart would know that
    material exists which could not be cited, which is the disclosure invariant 1 forbids
    and the one a user would act on ("there IS something there, keep asking"). A field
    here would be a field a serializer could name, so there is no field. The same
    reasoning ``RetrievalOutcome`` gives for carrying no rejected statements: the
    reliable guarantee is that the value is unreachable from the object the view holds.

    ``result_count`` and ``sources`` are taken from the outcome and never recomputed. The
    pipeline zeroes the count and empties the passage list on **both** no-answer paths, so
    serialising what it was given is what keeps the two replies identical; reaching past
    the outcome to recover "how many passages were really supplied" would undo it.
    """

    answered: bool
    result_count: int
    statements: tuple[NumberedStatement, ...]
    sources: tuple[ConsultedSource, ...]
    message: str | None
    # FR-13's "updated conversation state": the thread this turn belongs to, refreshed by
    # the pipeline inside the log transaction, or None for a one-off question.
    conversation: Conversation | None


def number_statements(statements) -> tuple[NumberedStatement, ...]:
    """7.10's ``composeAnswerWithInlineCitations``, as data rather than as a string.

    Every statement carries its ``chunk_id`` — invariant 6: there is no interface state
    that shows an uncited factual statement, and the way to guarantee that here is for a
    statement to arrive with its identifier or not at all. Only verified statements reach
    this function: ``RetrievalOutcome`` carries no others.
    """
    return tuple(
        NumberedStatement(position=position, text=statement.text, chunk_id=statement.chunk_id)
        for position, statement in enumerate(statements, start=FIRST_POSITION)
    )


def resolve_sources(passages) -> tuple[ConsultedSource, ...]:
    """7.10's ``resolveSourceDetails(suppliedPassageIds)``: title and date per item.

    Grouped by item in first-appearance order, which is rank order, so the panel's first
    entry is the item the best-scoring passage came from. Two queries whatever the number
    of passages, and no query at all for the empty list a no-answer outcome carries.
    """
    grouped: dict[tuple[str, UUID], list[ConsultedPassage]] = {}
    for passage in passages:
        key = (passage.source_type, passage.source_id)
        grouped.setdefault(key, []).append(
            ConsultedPassage(chunk_id=passage.chunk_id, text=passage.chunk_text)
        )

    titles_and_dates = _titles_and_dates(grouped)
    resolved = []
    for (source_type, source_id), items in grouped.items():
        details = titles_and_dates.get((source_type, source_id))
        if details is None:
            continue  # the source row has gone; see the module docstring
        title, source_date = details
        resolved.append(
            ConsultedSource(
                source_type=source_type,
                source_id=source_id,
                title=title,
                date=source_date,
                passages=tuple(items),
            )
        )
    return tuple(resolved)


def _titles_and_dates(grouped) -> dict:
    """One query per source type, over the ids actually consulted."""

    def ids_for(source_type):
        return [source_id for (kind, source_id) in grouped if kind == source_type]

    details = {}
    document_ids = ids_for(DOCUMENT_SOURCE_TYPE)
    if document_ids:
        for row in Document.objects.filter(pk__in=document_ids).only("id", "title", "uploaded_at"):
            details[(DOCUMENT_SOURCE_TYPE, row.id)] = (row.title, row.uploaded_at)
    meeting_ids = ids_for(MEETING_SOURCE_TYPE)
    if meeting_ids:
        for row in Meeting.objects.filter(pk__in=meeting_ids).only("id", "title", "meeting_date"):
            details[(MEETING_SOURCE_TYPE, row.id)] = (row.title, row.meeting_date)
    return details


def reply_for(*, outcome: RetrievalOutcome, conversation: Conversation | None) -> AnswerReply:
    """The reply for one turn, from the outcome the pipeline returned.

    The one place the outcome becomes a reply, so the fields that do not cross can be
    pointed at: of ``RetrievalOutcome``'s seven fields this reads five, and
    ``no_answer_reason`` and ``rejected_count`` are the two it does not. See
    ``AnswerReply``.
    """
    return AnswerReply(
        answered=outcome.answered,
        result_count=outcome.result_count,
        statements=number_statements(outcome.verified_statements),
        sources=resolve_sources(outcome.passages),
        message=outcome.message,
        conversation=conversation,
    )


# The two record-only columns, named once so a test can assert that neither the reply
# dataclass nor the rendered body carries them, and so that spelling them out in a test
# file cannot drift from what QueryLog actually holds.
RECORD_ONLY_FIELDS = ("no_answer_reason", "rejected_count")
ANSWER_REPLY_FIELDS = tuple(field.name for field in fields(AnswerReply))
