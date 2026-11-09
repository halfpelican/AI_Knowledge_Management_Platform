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

**The source rows are read through the scoping module, and fail closed (D-53).** Every
passage reached this module through ``candidate_chunks``, whose query carries both FR-11
predicates, so the chunk's stamped ``visible_to_roles`` already admitted this role
(invariant 1, and invariant 2 for why the stamp is on the chunk). Until Stage 5 item 1 this
module therefore read the source row with no predicate at all, on the argument that a second
filter in a second place could only disagree with the first. That argument was half right,
and D-53 kept the half that was: there must not be two *copies* of the predicate. The source
row is now read through ``scoping.scoped_documents`` and ``scoping.scoped_meetings``, the one
place the source predicate is written, and the keyword search reads it through the same
helpers. While D-47's cascade holds, the chunk and the source agree and nothing changes.
Where they disagree, which ``bulk_create(update_conflicts=True)`` or raw SQL can cause, the
source is dropped from the panel exactly as a source row that has gone is dropped. That is
the direction D-53 settled: returning less is a usability defect, and returning more is a
disclosure.

**What failing closed here does not reach.** The passage was a retrieval candidate under its
chunk stamp, so the model was sent it, and a statement citing it survives verification.
Dropping its source removes the item from ``sources`` and ``partial_matches``, and that
statement is left with a citation that has no passage to expand to. D-53's implementation
note records why the boundary sits here.

**The scope is resolved from the user, as ``search`` and ``answer_question`` resolve it.**
``reply_for`` takes the user, not a role, so no view can hand it one user's identity with
another's role. The role is read afresh for this call. If it changed after the pipeline read
it, the result is the intersection of the two reads: a narrower role drops sources, and a
wider one cannot add any, because only passages the pipeline admitted are resolved.

**FR-12's partial matches are resolved here too, and only their titles and dates are.**
``resolve_partial_matches`` is the third thing this module does, added at item 10a for the
second sentence of FR-12's no-answer clause: "Any partially related items found are offered,
clearly labelled as partial matches." The pipeline derived WHICH items — from the ranked
scoped candidates before the threshold, identically on both no-answer paths, as source
identities carrying no passage text (``apps/retrieval/partial_matches.py`` holds that whole
argument). This module does for them exactly what ``resolve_sources`` does for a consulted
passage's source and no more: one title, one date, from the same two queries. It adds no
snippet, because there is no field for one and because a fragment of source text under a
message that has just said the question cannot be answered reads as a partial answer, which
is invariant 6 by a side door. It adds no permission predicate, for the reason given below.

**A passage whose source row has gone, or is outside the reader's scope, is dropped from
the panel**, not rendered with a blank title. Nothing in the M6 build deletes a Document or a
Meeting yet — FR-15's permissioned deletion is Stage 5 item 2 — so the first case is
unreachable today. In both cases an entry with no title and no date is not something the
panel can render or link to, and a placeholder would be inventing text about material that no
longer exists or may not be read.
"""

from dataclasses import dataclass, fields
from datetime import date, datetime
from uuid import UUID

from apps.core.constants import SOURCE_TYPES
from apps.retrieval.models import Conversation
from apps.retrieval.pipeline import RetrievalOutcome
from apps.retrieval.query_log import FIRST_POSITION
from apps.retrieval.scoping import permission_scope, scoped_documents, scoped_meetings

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
class PartialMatchSource:
    """One partially related item offered beside a no-answer: identity, title and date.

    The same four shapes a search result and a Sources panel entry carry —
    ``source_type``, ``source_id``, ``title``, ``date`` — and deliberately not a fifth.
    **There is no ``passages`` field and no ``snippet``**, which is the difference between
    this and ``ConsultedSource``: those are the items an answer was drawn from, and their
    passages travel so a citation can expand to one. These are items nothing could be cited
    from, offered under a notice that has just said the question cannot be answered, so a
    line of their text would read as the partial answer FR-12 says not to present
    (invariant 6). The reader is meant to open the item and judge it.

    No score either, as nowhere in this API: relevance is a tuning signal for the team, and
    a number here would invite the reader to treat the nearest item as the answer.

    ``date`` is the source's own date and so is not one type — ``uploaded_at`` for a
    document, ``meeting_date`` for a meeting — rendered by the serializer's shared
    formatter, exactly as ``ConsultedSource.date`` and ``SearchResult.date`` are.
    """

    source_type: str
    source_id: UUID
    title: str
    date: date | datetime


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
    # FR-12's partially related items. Present on every reply and empty on an answered one,
    # so the key set does not vary between outcomes — the argument ``message`` makes by being
    # present and null there. Taken from the outcome, which derived it from the ranked scoped
    # candidates before the threshold and gave both no-answer paths the same value: this
    # module must not recompute it, filter it or order it, or it becomes a second derivation
    # able to differ between the two paths.
    partial_matches: tuple[PartialMatchSource, ...]
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


def resolve_sources(passages, *, user) -> tuple[ConsultedSource, ...]:
    """7.10's ``resolveSourceDetails(suppliedPassageIds)``: title and date per item.

    Grouped by item in first-appearance order, which is rank order, so the panel's first
    entry is the item the best-scoring passage came from. Three queries at most whatever the
    number of passages (the reader's role, then one per source type), and no query at all
    for the empty list a no-answer outcome carries.
    """
    grouped: dict[tuple[str, UUID], list[ConsultedPassage]] = {}
    for passage in passages:
        key = (passage.source_type, passage.source_id)
        grouped.setdefault(key, []).append(
            ConsultedPassage(chunk_id=passage.chunk_id, text=passage.chunk_text)
        )

    titles_and_dates = _titles_and_dates(grouped, user=user)
    resolved = []
    for (source_type, source_id), items in grouped.items():
        details = titles_and_dates.get((source_type, source_id))
        if details is None:
            continue  # the source row has gone, or is out of scope; see the module docstring
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


def resolve_partial_matches(matches, *, user) -> tuple[PartialMatchSource, ...]:
    """A title and a date for each partially related item the pipeline offered.

    Rank order, preserved exactly as it arrived: ``partial_matches`` deduplicated the ranked
    list by source and capped it, and re-sorting here would either invent an order or undo
    that one. Nothing is added to the list and nothing is removed from it except an item
    whose source row has gone or is outside the reader's scope, which is dropped rather than
    rendered with a blank title — the same rule ``resolve_sources`` follows.

    **The scoping module's source predicate, and no snippet.** Every identity here came off
    a chunk that ``scoping.candidate_chunks`` admitted for the asking role. The source row is
    read through the same helpers the keyword search uses, so the two agree and a
    disagreement fails closed (D-53). The pipeline offers these identically on both no-answer
    paths, and this function resolves them identically, so the field still cannot tell the
    paths apart. A snippet has nowhere to go: see ``PartialMatchSource``.

    Three queries at most, and none at all for the empty tuple an answered reply carries.
    """
    keys = [(match.source_type, match.source_id) for match in matches]
    titles_and_dates = _titles_and_dates(keys, user=user)
    offered = []
    for source_type, source_id in keys:
        details = titles_and_dates.get((source_type, source_id))
        if details is None:
            continue  # the source row has gone, or is out of scope; see the docstring
        title, source_date = details
        offered.append(
            PartialMatchSource(
                source_type=source_type, source_id=source_id, title=title, date=source_date
            )
        )
    return tuple(offered)


def _titles_and_dates(keys, *, user) -> dict:
    """One query per source type, over the ``(source_type, source_id)`` keys given, in scope.

    Any iterable of those pairs will do, which is why both callers can use it: the grouped
    dict of consulted passages iterates as its keys, and the partial matches pass a list.

    The reader's scope is resolved only when there is a row to look up, so the empty list a
    no-answer outcome carries still costs no query. Both no-answer paths reach this with the
    same arguments, so they make the same queries.
    """
    keys = list(keys)
    if not keys:
        return {}
    role_name = permission_scope(user)

    def ids_for(source_type):
        return [source_id for (kind, source_id) in keys if kind == source_type]

    details = {}
    document_ids = ids_for(DOCUMENT_SOURCE_TYPE)
    if document_ids:
        rows = scoped_documents(role_name=role_name).filter(pk__in=document_ids)
        for row in rows.only("id", "title", "uploaded_at"):
            details[(DOCUMENT_SOURCE_TYPE, row.id)] = (row.title, row.uploaded_at)
    meeting_ids = ids_for(MEETING_SOURCE_TYPE)
    if meeting_ids:
        rows = scoped_meetings(role_name=role_name).filter(pk__in=meeting_ids)
        for row in rows.only("id", "title", "meeting_date"):
            details[(MEETING_SOURCE_TYPE, row.id)] = (row.title, row.meeting_date)
    return details


def reply_for(
    *, outcome: RetrievalOutcome, conversation: Conversation | None, user
) -> AnswerReply:
    """The reply for one turn, from the outcome the pipeline returned, for ``user`` to read.

    ``user`` is the asker, and the source rows are resolved in their scope (D-53): see the
    module docstring.

    The one place the outcome becomes a reply, so the fields that do not cross can be
    pointed at: of ``RetrievalOutcome``'s eight fields this reads six, and
    ``no_answer_reason`` and ``rejected_count`` are the two it does not. See
    ``AnswerReply``.
    """
    return AnswerReply(
        answered=outcome.answered,
        result_count=outcome.result_count,
        statements=number_statements(outcome.verified_statements),
        sources=resolve_sources(outcome.passages, user=user),
        # Resolved, never re-derived: the pipeline decided which items these are, once, for
        # both no-answer paths. An answered outcome carries none, so this is an empty tuple
        # and no query runs.
        partial_matches=resolve_partial_matches(outcome.partial_matches, user=user),
        message=outcome.message,
        conversation=conversation,
    )


# The two record-only columns, named once so a test can assert that neither the reply
# dataclass nor the rendered body carries them, and so that spelling them out in a test
# file cannot drift from what QueryLog actually holds.
RECORD_ONLY_FIELDS = ("no_answer_reason", "rejected_count")
ANSWER_REPLY_FIELDS = tuple(field.name for field in fields(AnswerReply))
