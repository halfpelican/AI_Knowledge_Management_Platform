"""FR-12 query logging: the row every question leaves behind (apps/retrieval/query_log.py).

What is tested here is the RECORD, where apps/retrieval/tests/test_pipeline.py tests the
REPLY. The two are different documents on purpose — on no-answer path B the reply carries
no passages and a count of 0 while the row carries the identifiers that were supplied to
generation — so they are asserted in different files, and the test that matters most in
this one (``test_the_two_no_answer_paths_are_one_reply_and_two_rows``) is the pair of that
file's ``test_the_two_no_answer_paths_are_one_reply_and_two_reasons``. Together they are
CLAUDE.md invariant 7: identical to the caller, distinguishable in the record.

The helpers and the double are restated here rather than imported from test_pipeline.py,
following this suite's habit of a test stating its own premise instead of inheriting it
from another module's fixture. ``ControlledService`` is the leaner cousin of that file's:
its query vector is QUERY, the unit vector on the first axis, so a chunk built by
``at_cosine(v)`` scores exactly ``v``, and its generation reply is scripted.

Nothing here reaches a provider: conftest.py's ``no_live_provider`` still points every
endpoint at a closed port underneath the double.
"""

from math import sqrt
from uuid import UUID

import pytest
from django.conf import settings
from django.db import DatabaseError

import apps.ai
from apps.ai.base import EmbeddingResult, ProviderUnavailable, Statement, StatementList
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    NO_ANSWER_MESSAGE,
    NO_ANSWER_REASONS,
    NO_RELEVANT_PASSAGE,
    NO_STATEMENT_VERIFIED,
    PARTIAL_MATCH_FLOOR,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk
from apps.retrieval import query_log as query_log_module
from apps.retrieval.models import AnswerCitation, QueryLog, SearchLog
from apps.retrieval.pipeline import QuestionLengthOutOfRange, answer_question
from apps.retrieval.tests.scopes import unreadable_scope


QUESTION = "How much annual leave do I get?"
assert MINIMUM_QUESTION_LENGTH <= len(QUESTION) <= MAXIMUM_QUESTION_LENGTH

BELOW = 0.10
ABOVE = 0.80
ALSO_ABOVE = 0.70
NEAREST = 0.99  # what a restricted chunk scores, so it would lead the ranking
assert BELOW < RELEVANCE_THRESHOLD < ALSO_ABOVE < ABOVE < NEAREST

# Step 7 phase 2b: between PARTIAL_MATCH_FLOOR and RELEVANCE_THRESHOLD, so not admitted but
# offered as a partial match. Asserted where it is used, so a break fails the test by name.
NEAR_MISS = (PARTIAL_MATCH_FLOOR + RELEVANCE_THRESHOLD) / 2

FABRICATED = "00000000-0000-4000-8000-000000000000"


# --- Vectors, rows and the double ------------------------------------------------------


def wide(*components) -> list[float]:
    values = list(components)
    return values + [0.0] * (settings.EMBEDDING_DIMENSION - len(values))


QUERY = wide(1.0)


def at_cosine(value: float) -> list[float]:
    """A unit vector whose cosine with QUERY is exactly ``value``."""
    return wide(value, sqrt(1.0 - value * value))


def make_chunk(document, visible_to_roles, *, index, cosine, text="A passage."):
    """A chunk stamped with a visibility scope (D-17), at a known angle to QUERY."""
    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=index,
        chunk_text=text,
        embedding=at_cosine(cosine),
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=visible_to_roles,
    )


class ControlledService:
    """A known query vector and a scripted generation reply; see the module docstring."""

    def __init__(self, *, statements=None, generation_failure=None):
        self.statements = statements
        self.generation_failure = generation_failure
        self.embed_calls: list[list[str]] = []
        self.generate_calls: list[tuple] = []

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[list(QUERY)],
            model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        self.generate_calls.append((question, list(passages)))
        if self.generation_failure is not None:
            raise self.generation_failure
        if self.statements is not None:
            return StatementList(statements=list(self.statements))
        return StatementList(
            statements=[Statement(text="A grounded statement.", chunk_id=passages[0].chunk_id)]
        )

    def health(self):
        raise AssertionError("the pipeline does not check provider health")


def install(monkeypatch, double):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


@pytest.fixture
def service(monkeypatch):
    return install(monkeypatch, ControlledService())


@pytest.fixture
def service_with(monkeypatch):
    def build(**kwargs):
        return install(monkeypatch, ControlledService(**kwargs))

    return build


def only_row() -> QueryLog:
    """The one row this call wrote, asserted to be exactly one."""
    assert QueryLog.objects.count() == 1
    return QueryLog.objects.get()


def every_stored_string(row: QueryLog) -> list[str]:
    """Every string this row and its citations hold, for "the text is nowhere" assertions.

    Column by column rather than by name, so a column added later is searched too: a
    rejected statement smuggled into a new field would otherwise pass a test that only
    knew about ``answer_text``.
    """
    values = [str(getattr(row, field.attname)) for field in QueryLog._meta.fields]
    for citation in row.citations.all():
        values += [str(getattr(citation, field.attname)) for field in AnswerCitation._meta.fields]
    return values


# --- One row per outcome kind ----------------------------------------------------------


@pytest.mark.django_db
def test_an_answered_query_writes_one_row_carrying_the_whole_traceability_clause(
    document, service
):
    """FR-12 traceability: the question, the identifiers, the answer and its citations.

    All four in one row plus its citation rows, which is what "any answer can later be
    traced to the material that produced it" means in practice: from this row alone, a
    reader reaches the exact chunk the statement was drawn from.
    """
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days.")

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert row.question == QUESTION  # as asked, unaltered
    assert row.retrieved_chunk_ids == [chunk.id]  # UUIDs, read back from the array column
    assert row.answered is True
    assert row.no_answer_reason is None
    assert row.answer_text == "A grounded statement."
    assert row.user == document.uploaded_by
    # NULL is the one-off question, which is what this call is: FR-13's conversation turn
    # is asserted in test_conversation.py, and the column still means what D-12 says.
    assert row.conversation is None
    assert row.rejected_count == 0  # generation ran and invented nothing; not NULL
    assert row.answered_at is not None
    # The reply and the record agree on this branch, and the count is derived from the
    # array rather than stored beside it (see the module docstring on result_count).
    assert len(row.retrieved_chunk_ids) == outcome.result_count == 1

    citation = row.citations.get()
    assert citation.chunk_id == chunk.id
    # The same identifier again, in the column that outlives the chunk (D-67): chunk_id is
    # set NULL when the chunk is deleted, and chunk_uuid is what still traces the statement.
    assert citation.chunk_uuid == chunk.id
    assert citation.statement_text == "A grounded statement."
    assert citation.position == 1


@pytest.mark.django_db
def test_path_a_writes_a_row_with_no_identifiers_and_the_first_reason(document, service):
    """Nothing cleared the threshold: a row, an empty array, and NO_RELEVANT_PASSAGE.

    The empty array is the record of 7.10 line 76's ``EMPTY LIST``: nothing was supplied to
    generation, so there is nothing to trace to, and ``answered=False`` with no identifiers
    is FR-19's evidence that the corpus held nothing relevant rather than that retrieval
    admitted the wrong thing.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=BELOW, text="Barely related.")

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert row.retrieved_chunk_ids == []
    assert row.answered is False
    assert row.no_answer_reason == NO_RELEVANT_PASSAGE
    assert row.answer_text is None  # nullable for exactly this case
    assert row.rejected_count is None  # NULL means the model was not asked
    assert row.question == QUESTION
    assert row.user == document.uploaded_by
    assert row.citations.count() == 0
    assert service.generate_calls == []  # and the model was never asked


@pytest.mark.django_db
def test_path_b_logs_the_supplied_identifiers_the_reply_no_longer_carries(
    document, service_with
):
    """**The traceability clause on the path where the reply says nothing.**

    Passages cleared the floor and reached the prompt; every statement was rejected. The
    reply carries no passages and a count of 0, deliberately, so that a caller cannot tell
    path B from path A. The ROW carries the identifiers that were supplied — that is the
    point of logging them at all, and it is the only place the diagnostic survives.
    """
    admitted = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Close.")
    double = service_with(statements=[Statement(text="Ungrounded.", chunk_id=FABRICATED)])

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    # The reply admits to nothing.
    assert outcome.result_count == 0
    assert outcome.passages == ()
    # The record admits to everything.
    row = only_row()
    assert row.retrieved_chunk_ids == [admitted.id]
    assert row.answered is False
    assert row.no_answer_reason == NO_STATEMENT_VERIFIED
    assert row.answer_text is None
    assert row.rejected_count == 1  # generation ran; one statement, one invented citation
    assert row.citations.count() == 0
    assert len(double.generate_calls) == 1
    # Which is exactly the FR-19 signal: unanswered WITH identifiers means retrieval
    # admitted passages that did not answer the question, where unanswered without them
    # means the corpus held nothing. The distinction needs no result_count column.
    assert row.answered is False and len(row.retrieved_chunk_ids) == 1


@pytest.mark.django_db
def test_the_two_no_answer_paths_are_one_reply_and_two_rows(document, monkeypatch):
    """**The test this item exists for.** Two runs, identical responses, two rows that differ.

    The pair of test_pipeline.py's ``test_the_two_no_answer_paths_are_one_reply_and_two
    _reasons``, which asserts the replies equal field by field. Here the same two calls are
    made and the ROWS are asserted different: different reason codes, and a different
    identifier array. That pairing is invariant 7 — a rising rate of the path-B reason
    means retrieval is admitting passages that do not answer the question, and it can only
    be counted because the two paths were written down differently while being replied to
    identically.
    """
    from dataclasses import asdict

    # A near miss, not BELOW, since step 7's floor: below it path A offers no partial match
    # and path B offers its admitted item, so the replies would differ in that one field
    # (apps/retrieval/partial_matches.py states it). In the band both offer this document.
    assert PARTIAL_MATCH_FLOOR <= NEAR_MISS < RELEVANCE_THRESHOLD
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=NEAR_MISS, text="Too far.")
    install(monkeypatch, ControlledService())

    path_a = answer_question(question=QUESTION, user=document.uploaded_by)

    admitted = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=ABOVE, text="Close.")
    install(
        monkeypatch,
        ControlledService(statements=[Statement(text="Ungrounded.", chunk_id=FABRICATED)]),
    )

    path_b = answer_question(question=QUESTION, user=document.uploaded_by)

    # The replies are the same document. (Asserted exhaustively in test_pipeline.py; the
    # summary is repeated here because it is the premise of everything below. The two
    # fields excluded are the two no caller ever sees.)
    def caller_visible(outcome):
        return {
            name: value
            for name, value in asdict(outcome).items()
            if name not in ("no_answer_reason", "rejected_count")
        }

    assert caller_visible(path_a) == caller_visible(path_b)
    assert path_a.message == path_b.message == NO_ANSWER_MESSAGE

    # The rows are not.
    assert QueryLog.objects.count() == 2
    # Told apart by CONTENT rather than by answered_at: path A supplied no passages and
    # path B did. auto_now_add is ~15.6 ms granular on Windows, so two rows written in one
    # tick share the timestamp and an order_by on it tie-breaks on a random UUID.
    row_a = QueryLog.objects.get(retrieved_chunk_ids=[])
    row_b = QueryLog.objects.exclude(retrieved_chunk_ids=[]).get()
    assert row_a.no_answer_reason != row_b.no_answer_reason
    assert {row_a.no_answer_reason, row_b.no_answer_reason} == set(NO_ANSWER_REASONS)
    assert row_a.no_answer_reason == NO_RELEVANT_PASSAGE
    assert row_b.no_answer_reason == NO_STATEMENT_VERIFIED
    # And they differ in the second way the record tells the paths apart, which is what
    # lets FR-19 count them without reading the vocabulary at all.
    assert row_a.retrieved_chunk_ids == []
    assert row_b.retrieved_chunk_ids == [admitted.id]
    # And in the third: NULL where the model was not asked, an integer where it was.
    assert row_a.rejected_count is None
    assert row_b.rejected_count == 1
    # Everything else about them is the same event: same question, same user, unanswered.
    assert row_a.question == row_b.question == QUESTION
    assert row_a.user == row_b.user == document.uploaded_by
    assert row_a.answered is row_b.answered is False
    assert row_a.answer_text is row_b.answer_text is None


# --- Citations: order, position, and what is not stored --------------------------------


@pytest.mark.django_db
def test_a_citation_row_per_verified_statement_in_the_order_they_were_verified(
    document, service_with
):
    """Two statements, two rows, positions 1 and 2, each pointing at its own chunk.

    ``position`` is the citation's number as a reader sees it, so it starts at 1 and the
    presentation layer renders the stored value rather than the stored value plus one. The
    order is the order verification preserved, which is the order the model produced — the
    order the answer reads in, and the order ``answer_text`` joins them in.
    """
    first = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days.")
    second = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=2, cosine=ALSO_ABOVE, text="Pro rata in year one."
    )
    service_with(
        statements=[
            Statement(text="Twenty days a year.", chunk_id=str(first.id)),
            Statement(text="Pro rata in the first year.", chunk_id=str(second.id)),
        ]
    )

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    citations = list(row.citations.order_by("position"))
    assert [citation.position for citation in citations] == [1, 2]
    assert [citation.statement_text for citation in citations] == [
        "Twenty days a year.",
        "Pro rata in the first year.",
    ]
    assert [citation.chunk_id for citation in citations] == [first.id, second.id]
    # Each row's chunk_uuid is its own chunk_id, not the first statement's or the last one's.
    assert [citation.chunk_uuid for citation in citations] == [first.id, second.id]
    # answer_text is the same statements in the same order, joined. The numbering a reader
    # sees is recoverable from position beside each chunk, which is why it is not stored in
    # the text (apps/retrieval/query_log.py).
    assert row.answer_text == "Twenty days a year. Pro rata in the first year."
    assert row.retrieved_chunk_ids == [first.id, second.id]  # best first


@pytest.mark.django_db
def test_where_verification_rejected_everything_no_rejected_text_is_stored_anywhere(
    document, service_with
):
    """Path B: no citation row exists, and the rejected sentence is in no column of any row.

    Invariant 6 says no interface state shows an uncited factual statement, and the log is
    a surface like any other — a FR-19 review reads these rows. The text was dropped at the
    RetrievalOutcome boundary, so it is not reachable from the recorder; this asserts the
    consequence rather than trusting it.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    service_with(
        statements=[
            Statement(text="Rejected text that must not survive.", chunk_id=FABRICATED),
            Statement(text="Also invented.", chunk_id="c_4471"),
        ]
    )

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert AnswerCitation.objects.count() == 0
    assert row.answer_text is None
    stored = every_stored_string(row)
    assert not any("Rejected text that must not survive." in value for value in stored)
    assert not any("invented" in value.lower() for value in stored)
    assert not any(FABRICATED in value for value in stored)


@pytest.mark.django_db
def test_a_rejected_statement_beside_a_verified_one_reaches_no_column(document, service_with):
    """The answered branch of the same rule: one survived, one did not, one row is written.

    The answer was still given, so this is not path B — and the statement that lost its
    citation is absent from ``answer_text``, absent from the citation rows, and absent from
    the row entirely. An answer is the statements that survived, not the ones the model
    offered.
    """
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    service_with(
        statements=[
            Statement(text="Grounded.", chunk_id=str(chunk.id)),
            Statement(text="Invented alongside it.", chunk_id=FABRICATED),
        ]
    )

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert row.answered is True
    assert row.answer_text == "Grounded."
    assert [citation.statement_text for citation in row.citations.all()] == ["Grounded."]
    assert row.citations.get().position == 1  # numbering follows the answer, not the model
    stored = every_stored_string(row)
    assert not any("Invented alongside it." in value for value in stored)
    assert not any(FABRICATED in value for value in stored)


# --- FR-11 through the record ----------------------------------------------------------


@pytest.mark.django_db
def test_an_out_of_scope_chunk_cannot_reach_a_row(document, service):
    """The scoping assertion, applied to the log rather than to the answer.

    The restricted chunk is the nearest match and would have led the ranking under a
    post-filter. It is not in the candidate set, so it is not in the supplied identifiers,
    so it cannot be in the row — the guarantee is structural, and this asserts it anyway
    because a logger that re-read the corpus for "context" is exactly how it would be lost.
    Not its identifier, not its text, not a count that implies it.
    """
    restricted = make_chunk(
        document, [ADMINISTRATOR_ROLE_NAME], index=1, cosine=NEAREST, text="Restricted, nearest."
    )
    permitted = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=2, cosine=ABOVE, text="Permitted, relevant."
    )

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert row.retrieved_chunk_ids == [permitted.id]
    assert restricted.id not in row.retrieved_chunk_ids
    assert len(row.retrieved_chunk_ids) == 1  # the count discloses nothing either
    stored = every_stored_string(row)
    assert not any(str(restricted.id) in value for value in stored)
    assert not any(restricted.chunk_text in value for value in stored)
    assert restricted.id not in [citation.chunk_id for citation in row.citations.all()]
    assert ContentChunk.objects.count() == 2  # the row it must not name does exist


@pytest.mark.django_db
def test_a_statement_citing_an_out_of_scope_chunk_reaches_neither_a_citation_nor_the_row(
    document, service_with
):
    """The model names another role's chunk; verification rejects it; path B is recorded.

    The identifier was never supplied, so the statement is rejected exactly as an invented
    one would be — and the restricted identifier appears in no column, including the array
    of supplied identifiers, which holds only the passage this role may read.
    """
    restricted = make_chunk(
        document, [ADMINISTRATOR_ROLE_NAME], index=1, cosine=NEAREST, text="Restricted, nearest."
    )
    permitted = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=ABOVE, text="Permitted.")
    service_with(
        statements=[Statement(text="Claimed of a restricted chunk.", chunk_id=str(restricted.id))]
    )

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert row.no_answer_reason == NO_STATEMENT_VERIFIED
    assert row.retrieved_chunk_ids == [permitted.id]
    assert row.citations.count() == 0
    stored = every_stored_string(row)
    assert not any(str(restricted.id) in value for value in stored)
    assert not any("Claimed of a restricted chunk." in value for value in stored)


@pytest.mark.django_db
def test_rows_are_written_from_both_role_sessions(session_client, document, service):
    """The same assertions from an Employee session and an Administrator session
    (CLAUDE.md section 8 item 2). The restricted chunk is one the asking role may not
    read — Administrator-only for an Employee, scoped to nobody for an Administrator since
    D-66 — so each run has a row it must not name."""
    role_name = session_client.role_name
    restricted = make_chunk(
        document, unreadable_scope(role_name), index=1, cosine=NEAREST, text="Restricted, nearest."
    )
    permitted = make_chunk(document, [role_name], index=2, cosine=ABOVE, text="Permitted.")

    answer_question(question=QUESTION, user=session_client.user)

    row = only_row()
    assert row.user == session_client.user
    assert row.answered is True
    assert row.retrieved_chunk_ids == [permitted.id]
    assert restricted.id not in row.retrieved_chunk_ids
    assert row.citations.get().chunk_id == permitted.id
    assert not any(str(restricted.id) in value for value in every_stored_string(row))


@pytest.mark.django_db
def test_path_a_rows_from_both_role_sessions(session_client, document, service):
    """Path A from both roles: a row is still written, with nothing in its array."""
    role_name = session_client.role_name
    make_chunk(document, unreadable_scope(role_name), index=1, cosine=NEAREST, text="Restricted, nearest.")

    answer_question(question=QUESTION, user=session_client.user)

    row = only_row()
    assert row.user == session_client.user
    assert row.answered is False
    assert row.no_answer_reason == NO_RELEVANT_PASSAGE
    assert row.retrieved_chunk_ids == []


# --- Atomicity, and one row per call ---------------------------------------------------


@pytest.mark.django_db
def test_the_row_and_its_citations_commit_together_or_not_at_all(
    document, service, monkeypatch
):
    """A failure writing the citations leaves no QueryLog row either.

    A row recorded as answered with no citations beneath it would be a traceability record
    that traces to nothing — and worse, it would read as evidence that an uncited answer
    was returned, which is the one thing invariant 6 says cannot happen. The failure is
    induced at ``bulk_create`` because that is the only part of the write that can fail
    after the row exists; the reverse order cannot fail, since the citations need the
    query's primary key and so are written second by construction.

    The rollback is to the savepoint ``transaction.atomic`` opened, which is exactly what
    would happen inside a request that is itself in a transaction — the row is gone either
    way, which is what is being asserted.
    """

    def fail(*args, **kwargs):
        raise DatabaseError("citations could not be written")

    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    monkeypatch.setattr(AnswerCitation.objects, "bulk_create", fail)

    with pytest.raises(DatabaseError):
        answer_question(question=QUESTION, user=document.uploaded_by)

    assert QueryLog.objects.count() == 0
    assert AnswerCitation.objects.count() == 0


@pytest.mark.django_db
def test_a_logging_failure_loses_the_answer_rather_than_returning_it_unrecorded(
    document, service, monkeypatch
):
    """The deliberate choice: not swallowed, not caught, not "best effort".

    An answer delivered after the record failed is an answer that cannot be traced, which
    is the guarantee FR-12 makes; and a swallowed failure would delete the FR-19 gap
    evidence with nobody the wiser, which is the one failure mode this project keeps saying
    it will not accept. The write is against the same database retrieval just read the
    candidate set out of, so a failure here means the request was largely doomed anyway.
    """

    def fail(**kwargs):
        raise DatabaseError("the log could not be written")

    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    monkeypatch.setattr("apps.retrieval.pipeline.record_query", fail)

    # The answer existed a line earlier and is not returned. No try/except catches this,
    # and adding one is the change this test is here to prevent.
    with pytest.raises(DatabaseError):
        answer_question(question=QUESTION, user=document.uploaded_by)


@pytest.mark.django_db
def test_one_row_per_call_and_not_one_more(document, service):
    """Zero to one to two. Every call that reaches retrieval writes exactly one row."""
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)

    assert QueryLog.objects.count() == 0
    answer_question(question=QUESTION, user=document.uploaded_by)
    assert QueryLog.objects.count() == 1
    answer_question(question=QUESTION, user=document.uploaded_by)
    assert QueryLog.objects.count() == 2
    assert AnswerCitation.objects.count() == 2  # one verified statement per call


@pytest.mark.django_db
def test_no_search_log_row_is_written(document, service):
    """SearchLogs is deliberately unwritten, and this is where that is said out loud.

    It records FR-12's keyword-search half — the "200 OK with grouped results" response,
    as against the "answer and citations" half this pipeline serves — and that path is not
    built. Whichever item builds it writes ``SearchLogs``; a question answered through
    ``answer_question`` must never write one, or the same question would be counted twice
    in FR-19's evidence.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)

    answer_question(question=QUESTION, user=document.uploaded_by)

    assert QueryLog.objects.count() == 1
    assert SearchLog.objects.count() == 0


# --- rejected_count, and what its NULL means -------------------------------------------
#
# The column exists because invariant 7 needs the two kinds of no-answer path B separable:
# both carry NO_STATEMENT_VERIFIED, and only the count says whether the model declined or
# whether verification stripped everything it proposed. Item 6's live runs are the evidence
# — 2 declines and 3 all-rejected before the prompt fix, 6 and 0 after — an aggregate of 5
# to 6 that would have read as "no effect" without the split.


@pytest.mark.django_db
def test_a_clean_answered_response_records_zero_and_not_null(document, service):
    """Generation ran and every citation checked out: 0, which is not the same as NULL.

    The distinction is the whole point of the column. 0 says "the model was asked and
    invented nothing"; NULL says "the model was not asked". A row that conflated them
    would put path A's silence into the same bucket as a clean generation.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert row.answered is True
    assert row.rejected_count == 0
    assert row.rejected_count is not None
    assert QueryLog.objects.filter(rejected_count__isnull=True).count() == 0


@pytest.mark.django_db
def test_an_answered_row_records_the_rejection_that_did_not_cost_the_answer(
    document, service_with
):
    """**The early warning**, and the reason this column is not written on path B alone.

    One statement survived beside one whose identifier was invented, so the answer was
    given — ``answered`` is True — and a fabrication happened anyway. This is the shape item
    6 observed, it is fabrication before it has cost anything, and a column written only
    where nothing survived would not see it until it was too late to be a warning.
    """
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    service_with(
        statements=[
            Statement(text="Grounded.", chunk_id=str(chunk.id)),
            Statement(text="Invented alongside it.", chunk_id=FABRICATED),
        ]
    )

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert row.answered is True
    assert row.no_answer_reason is None
    assert row.rejected_count == 1
    assert row.answer_text == "Grounded."  # and the rejected statement is still nowhere
    assert row.citations.count() == 1


@pytest.mark.django_db
def test_the_two_ways_of_reaching_path_b_are_one_reason_and_two_counts(document, monkeypatch):
    """**The pair this column was added for.** Same ``no_answer_reason``, different count.

    First run: the model declines with an empty statement list — it read the passages and
    correctly said nothing, so there was nothing to reject and the count is 0. Second run:
    it proposed two statements and every identifier was invented, so the count is 2. Both
    are NO_STATEMENT_VERIFIED, because 7.10 step 10 folds them into one reason and
    NO_ANSWER_REASONS holds exactly two values. Without the count they are the same row,
    and the item-6 finding — one failure mode removed while the other grew — would have
    been invisible behind an unmoved total.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Close enough.")

    install(monkeypatch, ControlledService(statements=[]))
    declined = answer_question(question=QUESTION, user=document.uploaded_by)

    install(
        monkeypatch,
        ControlledService(
            statements=[
                Statement(text="Invented.", chunk_id=FABRICATED),
                Statement(text="Also invented.", chunk_id="c_4471"),
            ]
        ),
    )
    all_rejected = answer_question(question=QUESTION, user=document.uploaded_by)

    assert declined.no_answer_reason == all_rejected.no_answer_reason == NO_STATEMENT_VERIFIED
    # Asserted as a multiset, because the two rows cannot be told apart by anything but
    # the very field under test, and answered_at cannot order them reliably — it is
    # ~15.6 ms granular on Windows, so two rows written in one tick tie and the tie-break
    # is a random UUID. One row counts 0 and the other 2, which is the whole claim.
    assert sorted(QueryLog.objects.values_list("rejected_count", flat=True)) == [0, 2]
    row_declined = QueryLog.objects.get(rejected_count=0)
    row_all_rejected = QueryLog.objects.get(rejected_count=2)
    assert row_declined.no_answer_reason == row_all_rejected.no_answer_reason
    # Both reached generation, so neither is NULL: the count is a real 0, not an absence.
    assert row_declined.rejected_count is not None
    assert QueryLog.objects.filter(rejected_count__isnull=True).count() == 0


@pytest.mark.django_db
def test_path_a_records_null_and_null_is_not_zero(document, service):
    """NULL means generation was NOT CALLED. It never means "path B did not occur".

    Asserted as NULL specifically rather than as falsy, because ``not 0`` and ``not None``
    are both true and a reader who tested for falsiness would have merged the one
    distinction this column carries. The database is asked as well as the attribute, so a
    0 written and read back as 0 could not pass.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=BELOW)

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert row.rejected_count is None
    assert row.rejected_count != 0
    assert QueryLog.objects.filter(rejected_count__isnull=True).count() == 1
    assert QueryLog.objects.filter(rejected_count=0).count() == 0
    assert service.generate_calls == []  # the premise: the model was never asked
    # And the reason it is NULL is not "this was a no-answer": path B rows are no-answers
    # too and carry an integer. It is NULL because generation did not run.
    assert row.no_answer_reason == NO_RELEVANT_PASSAGE


@pytest.mark.django_db
def test_rejected_count_from_both_role_sessions(session_client, document, service_with):
    """The early-warning shape from an Employee session and an Administrator session."""
    role_name = session_client.role_name
    chunk = make_chunk(document, [role_name], index=1, cosine=ABOVE)
    service_with(
        statements=[
            Statement(text="Grounded.", chunk_id=str(chunk.id)),
            Statement(text="Invented.", chunk_id=FABRICATED),
        ]
    )

    answer_question(question=QUESTION, user=session_client.user)

    row = only_row()
    assert row.user == session_client.user
    assert row.answered is True
    assert row.rejected_count == 1


# --- What is not a query outcome, and so is not recorded -------------------------------


@pytest.mark.django_db
def test_a_question_outside_the_bounds_writes_no_row(employee, service):
    """Failure path: the question never reached retrieval, so there is nothing to record.

    A typo in the no-answer rate would corrupt the number invariant 7 asks the team to
    watch: "a question that was never asked properly" and "a corpus that cannot answer a
    proper question" are different events.
    """
    with pytest.raises(QuestionLengthOutOfRange):
        answer_question(question="x" * (MINIMUM_QUESTION_LENGTH - 1), user=employee)

    assert QueryLog.objects.count() == 0
    assert service.embed_calls == []


@pytest.mark.django_db
def test_a_provider_outage_writes_no_row(document, service_with):
    """The 503 is not a no-answer, and it is not a logged query either.

    7.10 returns its 503 at line 146 without calling ``recordQuery``. "The system could not
    ask" is a different event from "the corpus has no answer", and recording it as a query
    would inflate exactly the rate FR-19 reads.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    service_with(generation_failure=ProviderUnavailable("three non-conforming replies"))

    with pytest.raises(ProviderUnavailable):
        answer_question(question=QUESTION, user=document.uploaded_by)

    assert QueryLog.objects.count() == 0
    assert AnswerCitation.objects.count() == 0


# --- The composed answer text ----------------------------------------------------------


@pytest.mark.django_db
def test_answer_text_holds_the_verified_statements_and_no_citation_markers(
    document, service_with
):
    """The stored answer is model text verbatim: no "[1]", no NO_ANSWER_MESSAGE, no JSON.

    Composition with inline citations is the presentation layer (item 10) and the numbering
    it adds is recoverable from ``AnswerCitation.position``. Storing the markers here would
    freeze one marker format into the record and make the column unreadable the first time
    presentation changed its mind.
    """
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    service_with(
        statements=[
            Statement(text="Twenty days a year.", chunk_id=str(chunk.id)),
            Statement(text="Approved by a manager.", chunk_id=str(chunk.id)),
        ]
    )

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert row.answer_text == "Twenty days a year. Approved by a manager."
    assert "[1]" not in row.answer_text
    assert NO_ANSWER_MESSAGE not in row.answer_text
    # Two statements from one chunk: two citation rows, one supplied identifier, and the
    # array is the supplied set rather than one entry per statement.
    assert [citation.position for citation in row.citations.order_by("position")] == [1, 2]
    assert row.retrieved_chunk_ids == [chunk.id]


def test_the_answer_text_helper_is_none_rather_than_empty_for_nothing_verified():
    """A unit of the one decision the column embodies: NULL where no answer was returned.

    None rather than "" so that "an answer was given" is a null test in SQL and cannot be
    confused with an answer that happened to be empty.
    """
    assert query_log_module.answer_text_for(()) is None
    assert query_log_module.answer_text_for([Statement(text="One.", chunk_id="c1")]) == "One."
    assert (
        query_log_module.answer_text_for(
            [Statement(text="One.", chunk_id="c1"), Statement(text="Two.", chunk_id="c2")]
        )
        == "One. Two."
    )


@pytest.mark.django_db
def test_identifiers_are_stored_as_uuids_not_as_strings(document, service):
    """The array column holds UUIDs, so a later query can join them against ContentChunks.

    RankedPassage.chunk_id is a string, because that is the form the prompt labels passages
    with and the form the model hands back; the record converts. A column of strings would
    have looked identical in a test that compared ``str`` values and been useless to the
    traceability query this table exists for.
    """
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)

    answer_question(question=QUESTION, user=document.uploaded_by)

    row = only_row()
    assert all(isinstance(value, UUID) for value in row.retrieved_chunk_ids)
    assert ContentChunk.objects.filter(id__in=row.retrieved_chunk_ids).count() == 1
    assert row.citations.get().chunk == chunk
