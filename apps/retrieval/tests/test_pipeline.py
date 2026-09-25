"""FR-12 steps 1 to 10: retrieval, both no-answer paths, grounded generation and
verification (apps/retrieval/pipeline.py).

The autouse ``stub_ai_service`` is replaced here by a local double whose query vector
is fixed, because the stub's vectors are seeded random and no score could be predicted
from them. ``ControlledService`` answers with ``QUERY`` — the unit vector on the first
axis — so a chunk built by ``at_cosine(v)`` scores exactly ``v``, the same arrangement
apps/retrieval/tests/test_ranking.py uses. Its ``embed_calls`` and ``generate_calls``
lists are named as the stub's are, so a call-count assertion reads the same either way,
and ``generate_calls`` records the question and the passages each generation call
received — which is how the tests below assert what reached the prompt.

The provider's own behaviour — the retry loop, the schema check, the 503 after three
attempts — is tested in apps/ai/tests/test_generation.py against the openai SDK's mock
transport. What is tested here is the pipeline: what it sends, when it does not send at
all, and what it does with what comes back.

The helpers are restated here rather than imported from test_ranking.py, following
this suite's habit of a test stating its own premise instead of inheriting it from
another module's fixture.

Nothing here reaches a provider: the double is a plain class, and conftest.py's
``no_live_provider`` still points every endpoint at a closed port underneath it.
"""

from math import sqrt

import pytest
from django.conf import settings

import apps.ai
from apps.ai.base import EmbeddingResult, ProviderUnavailable, Statement, StatementList
from apps.ai.prefixes import query_text
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
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.retrieval.pipeline import QuestionLengthOutOfRange, answer_question
from apps.retrieval.scoping import UnscopedRequestError

ROLE_PAIR = (EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME)

QUESTION = "How much annual leave do I get?"
assert MINIMUM_QUESTION_LENGTH <= len(QUESTION) <= MAXIMUM_QUESTION_LENGTH

# Scores either side of the floor, stated once. 0.10 and 0.05 are below it and 0.80 is
# comfortably above, at any RELEVANCE_THRESHOLD this project would plausibly set.
BELOW = 0.10
ALSO_BELOW = 0.05
ABOVE = 0.80
NEAREST = 0.99  # what a restricted chunk scores, so it would lead the ranking
assert BELOW < RELEVANCE_THRESHOLD < ABOVE < NEAREST


# --- Vectors and rows ------------------------------------------------------------------


def wide(*components) -> list[float]:
    """The given leading components, zero-padded to the real column width."""
    values = list(components)
    return values + [0.0] * (settings.EMBEDDING_DIMENSION - len(values))


QUERY = wide(1.0)

# A query vector orthogonal to every chunk ``at_cosine`` builds, so each scores 0.0 against
# it: still a candidate, still ranked, below any floor. It is how no-answer path A is reached
# over the same corpus path B is reached over — which matters for the partial matches, since
# they are derived from the corpus and a test that changed the corpus between the two would
# not be comparing the two paths.
ELSEWHERE = wide(0.0, 0.0, 1.0)


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


# --- The double ------------------------------------------------------------------------


class ControlledService:
    """An AIService whose query vector is known and whose generation reply is scripted.

    ``model`` defaults to the stub's name because that is what make_chunk stamps, so
    the embedding-model predicate passes and the candidate set is decided by the role
    scope alone. A test that wants the mismatch case passes another name.

    ``generate_calls`` holds ``(question, passages)`` per call, so a test can assert
    exactly what reached the prompt — which is the only way to check the invariant that
    out-of-scope material never reaches the AI service. ``statements`` scripts the reply;
    the default cites the first passage it was given, as a grounded reply would.
    ``generation_failure`` scripts an outage instead.
    """

    def __init__(
        self,
        *,
        vector=None,
        model=STUB_EMBEDDING_MODEL,
        statements=None,
        generation_failure=None,
    ):
        self.vector = QUERY if vector is None else vector
        self.model = model
        self.statements = statements
        self.generation_failure = generation_failure
        self.embed_calls: list[list[str]] = []
        self.generate_calls: list[tuple] = []

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[list(self.vector)],
            model=self.model,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        # Recorded before anything else, so a test asserting zero calls sees a call that
        # should not have happened even if the scripted reply would have hidden it.
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


@pytest.fixture
def service(monkeypatch):
    """Install the double where apps.ai.get_ai_service is looked up at call time."""
    double = ControlledService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


def install(monkeypatch, double):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


@pytest.fixture
def service_with(monkeypatch):
    """Install a ControlledService with a scripted generation reply or failure."""

    def build(**kwargs):
        return install(monkeypatch, ControlledService(**kwargs))

    return build


# --- No-answer path A ------------------------------------------------------------------


@pytest.mark.django_db
def test_path_a_returns_the_no_answer_response_without_calling_generation(document, service):
    """Nothing cleared the threshold: the no-answer outcome, and no generation call.

    **The generation call site exists as of item 5, so this assertion is now
    load-bearing.** It was written at item 4 when there was nothing it could catch;
    ``answer_question`` now calls ``generate_statements`` two lines below the branch under
    test, and this is the test standing between no-answer path A and an ungrounded answer.
    If the early return were ever removed, or moved below the call, or turned into a
    conditional around it, the model would be handed a question with no grounding material
    and could answer it only by inventing — and nothing downstream could tell. That is the
    failure FR-12 asks for this test by name to prevent.

    ``embed_calls`` carries its own weight: retrieval genuinely ran — the question was
    embedded and a candidate set was ranked — so the empty result is a decision taken on
    the scores, not a short circuit that never looked.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=BELOW, text="Barely related.")
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=ALSO_BELOW, text="Less related.")

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.answered is False
    assert outcome.no_answer_reason == NO_RELEVANT_PASSAGE
    assert outcome.no_answer_reason != NO_STATEMENT_VERIFIED  # invariant 7: distinct paths
    assert outcome.message == NO_ANSWER_MESSAGE
    assert outcome.result_count == 0
    assert outcome.passages == ()
    assert service.generate_calls == []  # see the docstring on what this proves today
    # Retrieval ran: one embedding call, and the question reached it unrewritten but
    # for the documented task prefix (D-38). No sanitiser mangled it.
    assert len(service.embed_calls) == 1
    assert service.embed_calls == [[query_text(QUESTION)]]


@pytest.mark.django_db
def test_path_a_over_an_empty_corpus(employee, service):
    """The same outcome where there was nothing to rank at all.

    Worth its own case: an empty candidate set and a candidate set whose every score is
    too low are different situations that must not be told apart in the response. A
    reason code distinguishing them would disclose whether the corpus holds anything
    for this role (invariant 1).
    """
    outcome = answer_question(question=QUESTION, user=employee)

    assert outcome.answered is False
    assert outcome.no_answer_reason == NO_RELEVANT_PASSAGE
    assert outcome.message == NO_ANSWER_MESSAGE
    assert outcome.result_count == 0
    assert service.generate_calls == []


@pytest.mark.django_db
def test_a_chunk_from_another_embedding_model_leaves_nothing_to_answer_from(document, monkeypatch):
    """Risk R10 reaching path A: a corpus the current model cannot compare against.

    The chunk would have scored 0.99 had it been comparable. Because the provider
    answers with a different model name, it is not in the candidate set at all, and the
    honest no-answer is the outcome until ``manage.py reindex`` has run.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=NEAREST, text="Indexed earlier.")
    double = ControlledService(model="some-other-model")
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.no_answer_reason == NO_RELEVANT_PASSAGE
    assert outcome.result_count == 0
    assert "Indexed earlier." not in [passage.chunk_text for passage in outcome.passages]
    assert double.generate_calls == []


# --- The other branch: passages retrieved, and nothing more claimed --------------------


@pytest.mark.django_db
def test_a_passage_above_the_threshold_comes_back_as_a_passage_and_not_as_an_answer(
    document, service
):
    """The answered branch: passages, a count, verified statements, and answered=True.

    **This is the test items 4 and 5 both pointed at.** At item 4 it asserted
    ``answered is False`` because nothing had been generated; at item 5 it still did,
    because nothing had been verified; both said in this docstring that item 6 was where
    the flip belonged, so that it would appear in this diff rather than be assumed. It has
    flipped here, and only because step 9 now runs: ``answered`` is
    ``bool(verified_statements)``, nothing else sets it, and a statement is citable exactly
    when its identifier has been checked for set membership against the identifiers the
    prompt supplied (invariant 5).
    """
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days.")
    below = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=BELOW, text="Unrelated.")

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.result_count == 1
    assert len(outcome.passages) == 1
    assert outcome.passages[0].chunk_id == str(chunk.id)
    assert outcome.passages[0].chunk_text == "Twenty days."
    assert outcome.passages[0].score == pytest.approx(ABOVE)
    # The threshold still applied: the low-scoring chunk is not in the passages or the
    # count, so the count is of admitted passages and not of candidates.
    assert str(below.id) not in [passage.chunk_id for passage in outcome.passages]
    # Generation ran over exactly the admitted passage, and the statement it returned
    # cited a supplied identifier, so verification admitted it.
    assert len(service.generate_calls) == 1
    question_sent, passages_sent = service.generate_calls[0]
    assert question_sent == QUESTION
    assert [passage.chunk_id for passage in passages_sent] == [str(chunk.id)]
    assert [passage.text for passage in passages_sent] == ["Twenty days."]
    assert [statement.chunk_id for statement in outcome.verified_statements] == [str(chunk.id)]
    assert outcome.rejected_count == 0

    # ANSWERED IS TRUE HERE, for the first time in this stage. Items 4 and 5 both pinned
    # it False and both named item 6 as where it would flip; this is that flip, and it is
    # exactly bool(verified_statements) — a statement is citable once its identifier has
    # been checked for set membership, and not before.
    assert outcome.answered is True
    assert outcome.no_answer_reason is None
    assert outcome.message is None
    # The QueryLog row is item 8's and is asserted in test_query_log.py; the outcome itself
    # carries no composed answer and no resolved sources, which the presentation layer
    # (item 10) builds from `passages`.
    assert not hasattr(outcome, "proposed_statements")
    assert not hasattr(outcome, "answer_text")
    assert not hasattr(outcome, "sources")


@pytest.mark.django_db
def test_the_outcome_is_frozen(document, service):
    """Nothing downstream edits a reason code or a result count after the fact."""
    from dataclasses import FrozenInstanceError

    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    with pytest.raises(FrozenInstanceError):
        outcome.answered = True
    with pytest.raises(FrozenInstanceError):
        outcome.no_answer_reason = NO_STATEMENT_VERIFIED


# --- Step 1: question length, in characters, before any provider call ------------------


@pytest.mark.django_db
def test_a_question_below_the_minimum_length_raises_before_the_provider_is_called(
    employee, service
):
    """Failure path: FR-12's 400, and no NPU time spent on it."""
    too_short = "x" * (MINIMUM_QUESTION_LENGTH - 1)

    with pytest.raises(QuestionLengthOutOfRange):
        answer_question(question=too_short, user=employee)

    assert service.embed_calls == []
    assert service.generate_calls == []


@pytest.mark.django_db
def test_a_question_above_the_maximum_length_raises_before_the_provider_is_called(
    employee, service
):
    too_long = "x" * (MAXIMUM_QUESTION_LENGTH + 1)

    with pytest.raises(QuestionLengthOutOfRange):
        answer_question(question=too_long, user=employee)

    assert service.embed_calls == []
    assert service.generate_calls == []


@pytest.mark.django_db
def test_an_empty_question_raises(employee, service):
    with pytest.raises(QuestionLengthOutOfRange):
        answer_question(question="", user=employee)
    assert service.embed_calls == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "length", [MINIMUM_QUESTION_LENGTH, MAXIMUM_QUESTION_LENGTH], ids=["minimum", "maximum"]
)
def test_a_question_of_exactly_the_boundary_length_is_accepted(employee, service, length):
    """Both bounds are inclusive: 7.10 lines 10-12 reject on `<` and `>`, not `<=`.

    Acceptance is asserted by the provider having been reached — validation let the
    question through — not by the outcome, which over an empty corpus is path A.
    """
    outcome = answer_question(question="x" * length, user=employee)

    assert len(service.embed_calls) == 1
    assert outcome.no_answer_reason == NO_RELEVANT_PASSAGE


@pytest.mark.django_db
def test_a_question_is_measured_in_characters_not_tokens(employee, service):
    """A one-word question longer than MINIMUM_QUESTION_LENGTH characters is accepted.

    It is a single whitespace-delimited token (D-31), so a length check that had reached
    for ingestion's token counter would reject it. The bound is characters, per
    ``lengthInCharacters`` and the constants' own heading.
    """
    one_long_word = "x" * (MINIMUM_QUESTION_LENGTH + 5)
    assert len(one_long_word.split()) == 1

    answer_question(question=one_long_word, user=employee)

    assert len(service.embed_calls) == 1


def test_validation_precedes_scope_resolution(service):
    """Step 1 before step 2: a too-short question from no user is a 400, not a scope error.

    No database needed, and none touched — which is the point: the question never got
    as far as a user lookup.
    """
    from django.contrib.auth.models import AnonymousUser

    with pytest.raises(QuestionLengthOutOfRange):
        answer_question(question="short", user=AnonymousUser())
    assert service.embed_calls == []


# --- Step 2: the scope is not swallowed -----------------------------------------------


@pytest.mark.django_db
def test_a_user_whose_row_no_longer_exists_reaches_unscoped_request_error(employee, service):
    """The pipeline does not convert a missing scope into an empty result.

    A no-answer here would look exactly like a corpus that holds nothing, and the
    request would be served as though it had been scoped when it had not. It raises,
    and the provider is never reached — step 2 precedes step 3.
    """
    from django.contrib.auth import get_user_model

    get_user_model().objects.filter(pk=employee.pk).delete()

    with pytest.raises(UnscopedRequestError):
        answer_question(question=QUESTION, user=employee)

    assert service.embed_calls == []
    assert service.generate_calls == []


@pytest.mark.django_db
def test_an_anonymous_user_with_a_valid_question_reaches_unscoped_request_error(service):
    from django.contrib.auth.models import AnonymousUser

    with pytest.raises(UnscopedRequestError):
        answer_question(question=QUESTION, user=AnonymousUser())
    assert service.embed_calls == []


@pytest.mark.django_db
def test_a_provider_outage_is_not_converted_into_a_no_answer(employee, monkeypatch):
    """A provider outage and an unanswerable question are different events (invariant 7).

    ProviderUnavailable is allowed out, so the view can answer 503; swallowing it into
    path A would file an infrastructure failure under the no-answer rate, which is the
    number the team reads as a retrieval-quality signal.
    """

    class DownService(ControlledService):
        def embed(self, texts):
            self.embed_calls.append(list(texts))
            raise ProviderUnavailable("the provider is down")

    double = DownService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)

    with pytest.raises(ProviderUnavailable):
        answer_question(question=QUESTION, user=employee)
    assert double.generate_calls == []


# --- FR-11 through the pipeline -------------------------------------------------------


@pytest.mark.django_db
def test_an_out_of_scope_chunk_that_would_have_scored_highest_cannot_even_cause_a_call(
    document, service
):
    """The restricted chunk is the ONLY thing above the threshold, so path A is correct.

    This is the assertion that matters most in this file. Had the scope been applied
    after ranking — or not at all — the Administrator-only passage would have been the
    single best match, generation would have been called with it in the prompt, and it
    would have been the answer. Instead it is not in the candidate set, nothing clears
    the floor, and the provider is never asked. Out-of-scope material cannot reach the
    AI service even indirectly, as the thing that caused a call.
    """
    restricted = make_chunk(
        document, [ADMINISTRATOR_ROLE_NAME], index=1, cosine=NEAREST, text="Restricted, nearest."
    )
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=BELOW, text="Permitted, too far.")

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.answered is False
    assert outcome.no_answer_reason == NO_RELEVANT_PASSAGE
    assert outcome.message == NO_ANSWER_MESSAGE
    assert service.generate_calls == []
    # Absent from the passages, by identifier and by text, and from the count. The
    # count is 0 where the store holds two rows: no total discloses the restricted one.
    assert outcome.passages == ()
    assert str(restricted.id) not in [passage.chunk_id for passage in outcome.passages]
    assert restricted.chunk_text not in [passage.chunk_text for passage in outcome.passages]
    assert outcome.result_count == 0
    assert ContentChunk.objects.count() == 2


@pytest.mark.django_db
def test_an_out_of_scope_chunk_is_absent_where_a_permitted_passage_is_admitted(document, service):
    """The same boundary on the branch that does retrieve something.

    The restricted passage outscores the permitted one, so a post-filter would have
    ranked it first; here it is not in the passages, not in the count, and the one
    permitted passage is what came back.
    """
    restricted = make_chunk(
        document, [ADMINISTRATOR_ROLE_NAME], index=1, cosine=NEAREST, text="Restricted, nearest."
    )
    permitted = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=2, cosine=ABOVE, text="Permitted, relevant."
    )

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert [passage.chunk_id for passage in outcome.passages] == [str(permitted.id)]
    assert str(restricted.id) not in [passage.chunk_id for passage in outcome.passages]
    assert restricted.chunk_text not in [passage.chunk_text for passage in outcome.passages]
    assert outcome.result_count == 1  # after both filters and the threshold
    assert ContentChunk.objects.count() == 2

    # The part that could not be asserted before item 5: what the AI service was SENT.
    # The restricted passage outscored the permitted one, so a post-filter would have put
    # it first in this prompt. It is not in the prompt at all — not its text, not its
    # identifier — and no statement could therefore cite it (invariant 1).
    (question_sent, passages_sent) = service.generate_calls[0]
    assert question_sent == QUESTION
    assert [passage.chunk_id for passage in passages_sent] == [str(permitted.id)]
    assert str(restricted.id) not in [passage.chunk_id for passage in passages_sent]
    assert restricted.chunk_text not in [passage.text for passage in passages_sent]


@pytest.mark.django_db
def test_the_pipeline_from_both_role_sessions(session_client, document, service):
    """The same assertions from an Employee session and an Administrator session
    (CLAUDE.md section 8 item 2). The restricted chunk belongs to whichever role is
    not asking, so each run hides a different row."""
    role_name = session_client.role_name
    other_role = next(name for name in ROLE_PAIR if name != role_name)
    restricted = make_chunk(
        document, [other_role], index=1, cosine=NEAREST, text="Restricted, nearest."
    )
    permitted = make_chunk(
        document, [role_name], index=2, cosine=ABOVE, text="Permitted, relevant."
    )

    outcome = answer_question(question=QUESTION, user=session_client.user)

    assert [passage.chunk_id for passage in outcome.passages] == [str(permitted.id)]
    assert str(restricted.id) not in [passage.chunk_id for passage in outcome.passages]
    assert outcome.result_count == 1
    assert outcome.no_answer_reason is None
    # And the prompt, from both roles: exactly the permitted passage reached the provider.
    (_, passages_sent) = service.generate_calls[0]
    assert [passage.chunk_id for passage in passages_sent] == [str(permitted.id)]
    assert restricted.chunk_text not in [passage.text for passage in passages_sent]


@pytest.mark.django_db
def test_path_a_from_both_role_sessions(session_client, document, service):
    """Path A from both roles, where the only near passage belongs to the other one."""
    role_name = session_client.role_name
    other_role = next(name for name in ROLE_PAIR if name != role_name)
    make_chunk(document, [other_role], index=1, cosine=NEAREST, text="Restricted, nearest.")

    outcome = answer_question(question=QUESTION, user=session_client.user)

    assert outcome.answered is False
    assert outcome.no_answer_reason == NO_RELEVANT_PASSAGE
    assert outcome.message == NO_ANSWER_MESSAGE
    assert outcome.result_count == 0
    assert service.generate_calls == []


# --- The query record, which item 8 added ---------------------------------------------


@pytest.mark.django_db
def test_every_call_that_reaches_retrieval_writes_one_query_log_row(document, service):
    """Item 4 wrote nothing to the database; item 8 writes the row, and here it is.

    This test used to assert ``count() == 0`` and named item 8 as the commit that would
    replace it, so that the row appearing would show up in a diff rather than in nobody's
    memory. It is that commit. 7.10 calls recordQuery at line 76 inside path A, at 165
    inside path B and at 185 on the answered path, and all three are covered here — one
    row each, nothing else changed about the reply.

    What the row CONTAINS is apps/retrieval/tests/test_query_log.py's subject, including
    the pair of this file's two-no-answer-paths test: same reply, two rows, two reasons.
    """
    from apps.retrieval.models import QueryLog

    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=BELOW)

    path_a = answer_question(question=QUESTION, user=document.uploaded_by)
    assert path_a.no_answer_reason == NO_RELEVANT_PASSAGE
    assert QueryLog.objects.count() == 1

    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=ABOVE)
    answered = answer_question(question=QUESTION, user=document.uploaded_by)
    assert answered.answered is True
    assert QueryLog.objects.count() == 2


# --- Step 7 and step 8: what is sent, and what comes back ------------------------------


@pytest.mark.django_db
def test_the_prompt_carries_the_passages_in_rank_order_and_nothing_else(document, service):
    """Best first, each with its identifier, and no fourth thing beside them.

    Rank order matters in the prompt as well as in the response: the passages are consumed
    best-first by the context budget, and the model is more likely to draw on what it reads
    first.
    """
    best = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=0.90, text="Best.")
    middle = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=0.60, text="Middle.")
    worst = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=3, cosine=0.35, text="Worst.")

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    (_, passages_sent) = service.generate_calls[0]
    assert [passage.chunk_id for passage in passages_sent] == [
        str(best.id),
        str(middle.id),
        str(worst.id),
    ]
    assert [passage.text for passage in passages_sent] == ["Best.", "Middle.", "Worst."]
    # A Passage carries an identifier and text, and nothing else could leak through it.
    assert {field for field in vars(passages_sent[0])} == {"chunk_id", "text"}
    assert outcome.result_count == 3


@pytest.mark.django_db
def test_a_passage_below_the_threshold_never_reaches_the_prompt(document, service):
    """The floor is applied before the prompt is built, not inside it."""
    admitted = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Relevant.")
    weak = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=BELOW, text="Weak.")

    answer_question(question=QUESTION, user=document.uploaded_by)

    (_, passages_sent) = service.generate_calls[0]
    assert [passage.chunk_id for passage in passages_sent] == [str(admitted.id)]
    assert "Weak." not in [passage.text for passage in passages_sent]


@pytest.mark.django_db
def test_the_context_budget_is_applied_before_generation(document, monkeypatch):
    """Step 7 before step 8: only the passages that fit are sent.

    MAXIMUM_CONTEXT_TOKENS is overridden to a small number for this test rather than the
    corpus being made enormous. The constant is PROVISIONAL and item 5 does not tune it
    (4000 is what docs/flm-baseline.md measured), so a test that needs the budget to bind
    says so locally instead of moving the value everyone else reads.
    """
    from apps.retrieval import ranking

    monkeypatch.setattr(ranking, "MAXIMUM_CONTEXT_TOKENS", 10)
    double = install(monkeypatch, ControlledService())
    best = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=1, cosine=0.90, text=" ".join(["word"] * 8)
    )
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=0.60, text=" ".join(["word"] * 8))

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    (_, passages_sent) = double.generate_calls[0]
    assert [passage.chunk_id for passage in passages_sent] == [str(best.id)]
    # The count reports what was supplied to generation, so it matches the passage list.
    assert outcome.result_count == len(outcome.passages) == 1


@pytest.mark.django_db
def test_a_fabricated_citation_is_stripped_and_its_text_does_not_reach_the_outcome(
    document, service_with
):
    """The 2.4% case through the whole pipeline (item 5 carried it; item 6 removes it).

    The model returns one real citation and one invented one. The real statement is the
    answer, the invented one is gone — and gone means GONE: its text exists nowhere on the
    outcome, only a count. Invariant 6 says no interface state shows an uncited factual
    statement, and a view cannot render what it was never handed.
    """
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    fabricated = "00000000-0000-4000-8000-000000000000"
    double = service_with(
        statements=[
            Statement(text="A real one.", chunk_id=str(chunk.id)),
            Statement(text="An invented one.", chunk_id=fabricated),
        ]
    )

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert [statement.text for statement in outcome.verified_statements] == ["A real one."]
    assert [statement.chunk_id for statement in outcome.verified_statements] == [str(chunk.id)]
    assert outcome.rejected_count == 1
    assert outcome.answered is True  # one good citation is still an answer
    assert len(double.generate_calls) == 1

    # The rejected text is not reachable from the outcome by any route: not in a field, not
    # in a repr that a log line or a debug view might render.
    assert "An invented one." not in repr(outcome)
    assert fabricated not in repr(outcome)
    assert not any(
        "invented" in str(value).lower()
        for value in vars(outcome).values()
    )


@pytest.mark.django_db
def test_the_outcome_has_no_field_carrying_rejected_statement_text(document, service_with):
    """The invariant stated as a property of the object, not of one code path.

    ``proposed_statements`` existed at item 5 and is deliberately gone. A future field
    holding what the model said before verification would be a field a view could reach,
    and the "withheld panel" this project has ruled out is exactly what someone builds
    when the text is right there.
    """
    from dataclasses import fields

    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    service_with(
        statements=[
            Statement(text="Rejected text that must not survive.", chunk_id="fabricated-id")
        ]
    )

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    names = {field.name for field in fields(outcome)}
    assert names == {
        "answered",
        "result_count",
        "passages",
        "verified_statements",
        "rejected_count",
        "no_answer_reason",
        "message",
        # FR-12's partially related items: source identities, no text. Item 10a added it,
        # and it is named here so the field list stays the whole field list — the point of
        # this assertion is that a NEW field holding model text would fail it.
        "partial_matches",
    }
    for banned in ("proposed_statements", "rejected_statements", "unverified_statements"):
        assert banned not in names
        assert not hasattr(outcome, banned)
    assert "Rejected text that must not survive." not in repr(outcome)
    assert outcome.rejected_count == 1  # a number crosses the boundary; the text does not


# --- No-answer path B (item 7): retrieved, generated, and nothing survived -------------
#
# Every test in this section is constructed to reach path B on purpose. None of them gets
# there incidentally, because the path is not incidental: D-37 found that no threshold on
# this corpus separates answerable from unanswerable (no-answer questions reach 0.535 where
# the answerable median is 0.390), so the floor cannot decide answerability and path B is
# what catches the rest. The item-0 baseline found four no-answer questions that cleared
# the threshold, reached generation and came back empty; the item-6 live runs found more.
# A rising rate of this path is the project's main quality signal (invariant 7): it means
# retrieval is admitting passages that score above the floor but do not answer the
# question, which is a tuning problem rather than a missing-content one.


@pytest.mark.django_db
def test_path_b_where_the_model_declines_with_an_empty_statement_list(document, service_with):
    """``{"statements": []}`` is the model reporting that the passages do not answer.

    One of the two ways to reach no-answer path B, and the one that is not a failure of the
    model: it read the passages and correctly declined rather than inventing. Nothing was
    rejected — an empty list has nothing to reject — so ``rejected_count`` is 0, which is
    the only thing separating this from the all-rejected case below. Both record
    NO_STATEMENT_VERIFIED, because 7.10 step 10 folds them into one reason and
    NO_ANSWER_REASONS holds exactly two values; a third code would be a vocabulary change,
    a migration and a requirement nobody wrote.

    A rising rate here is the project's main quality signal (invariant 7): the passages
    scored above RELEVANCE_THRESHOLD and still did not answer the question.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    double = service_with(statements=[])

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.answered is False
    assert outcome.verified_statements == ()
    assert outcome.rejected_count == 0  # the model proposed nothing to reject
    assert outcome.no_answer_reason == NO_STATEMENT_VERIFIED
    assert outcome.no_answer_reason != NO_RELEVANT_PASSAGE  # emphatically not path A
    assert outcome.message == NO_ANSWER_MESSAGE
    # The reply carries nothing about the passages that were retrieved: see the
    # indistinguishability test below for why the count is 0 where one passage was sent.
    assert outcome.result_count == 0
    assert outcome.passages == ()
    # Generation WAS called, which is what makes this path B rather than path A.
    assert len(double.generate_calls) == 1


@pytest.mark.django_db
def test_path_b_where_verification_rejects_every_statement(document, service_with):
    """The other way in: the model answered, and every citation it gave was invented.

    Passages were retrieved and generation returned statements, but not one identifier was
    in the supplied set, so verification removed them all (invariant 5) and there is
    nothing citable left to show. Invariant 6 forbids any interface state showing an
    uncited factual statement, so the answer is not shown in part — the no-answer response
    is returned whole.

    ``rejected_count`` is 2 where the declining case above is 0. That is the field that
    tells the two ways of reaching this path apart, the item-6 live runs showed them moving
    independently, and item 8 is where it reaches the log. The reason code is the same for
    both, deliberately.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    double = service_with(
        statements=[
            Statement(text="Invented.", chunk_id="00000000-0000-4000-8000-000000000000"),
            Statement(text="Also invented.", chunk_id="c_4471"),
        ]
    )

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.answered is False
    assert outcome.verified_statements == ()
    assert outcome.rejected_count == 2
    assert outcome.no_answer_reason == NO_STATEMENT_VERIFIED
    assert outcome.no_answer_reason != NO_RELEVANT_PASSAGE
    assert outcome.message == NO_ANSWER_MESSAGE
    assert outcome.result_count == 0
    assert outcome.passages == ()
    assert len(double.generate_calls) == 1
    # And the unverified text is gone, as on every other branch: a count crosses the
    # boundary, sentences do not.
    assert "Invented." not in repr(outcome)


@pytest.mark.django_db
def test_the_two_no_answer_paths_are_one_reply_and_two_reasons(document, monkeypatch):
    """**The test that pins invariant 7.** Same response, different record.

    Two runs against the same store. In the first, the one permitted chunk scores below
    RELEVANCE_THRESHOLD, so nothing is admitted and generation is never called: path A. In
    the second, a chunk scoring above the floor is added and the model is scripted to cite
    an identifier that was never supplied, so everything is rejected: path B.

    Everything a caller can see is asserted equal, field by field. A user must not be able
    to tell from the reply whether the organisation holds nothing on the subject or whether
    it holds something that could not be cited — the second is a disclosure that material
    exists (invariant 1) and it is one a person would act on by asking again. That is why
    ``result_count`` is 0 on path B even though passages really were supplied to
    generation: a count is part of the reply, and a count that differed between the paths
    would be the field that gave the game away.

    What differs is ``no_answer_reason``, which no caller sees and item 8 records. A rising
    rate of the path-B reason is the project's main quality signal; merging the two codes
    would delete that signal, and returning two different replies would leak it to the
    wrong audience.
    """
    from dataclasses import asdict, fields

    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=BELOW, text="Too far.")
    path_a_double = install(monkeypatch, ControlledService())

    path_a = answer_question(question=QUESTION, user=document.uploaded_by)

    # Path A's premise: nothing was admitted, so the model was never asked.
    assert path_a.no_answer_reason == NO_RELEVANT_PASSAGE
    assert path_a_double.generate_calls == []

    admitted = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=2, cosine=ABOVE, text="Close enough."
    )
    path_b_double = install(
        monkeypatch,
        ControlledService(
            statements=[Statement(text="Ungrounded.", chunk_id="00000000-0000-4000-8000-0000000")]
        ),
    )

    path_b = answer_question(question=QUESTION, user=document.uploaded_by)

    # Path B's premise: the model WAS asked, over a real passage, and everything it said
    # was rejected. The two paths differ in what happened, which is the whole point.
    assert path_b.no_answer_reason == NO_STATEMENT_VERIFIED
    assert len(path_b_double.generate_calls) == 1
    (_, passages_sent) = path_b_double.generate_calls[0]
    assert [passage.chunk_id for passage in passages_sent] == [str(admitted.id)]

    # Field by field, everything the caller is handed:
    assert path_a.answered == path_b.answered is False
    assert path_a.message == path_b.message == NO_ANSWER_MESSAGE
    assert path_a.result_count == path_b.result_count == 0
    assert path_a.passages == path_b.passages == ()
    assert path_a.verified_statements == path_b.verified_statements == ()

    # And exhaustively, so a field added later is not silently allowed to differ. Only the
    # reason and the rejected count — the two fields item 8 records and no caller reads —
    # may vary between the paths.
    caller_visible = {
        field.name for field in fields(path_a)
    } - {"no_answer_reason", "rejected_count"}
    assert asdict(path_a).keys() == asdict(path_b).keys()
    for name in caller_visible:
        assert getattr(path_a, name) == getattr(path_b, name), name

    # The one difference, and it is in the record rather than the reply.
    assert path_a.no_answer_reason != path_b.no_answer_reason
    assert {path_a.no_answer_reason, path_b.no_answer_reason} == set(NO_ANSWER_REASONS)


@pytest.mark.django_db
def test_one_surviving_statement_is_an_answer_and_not_path_b(document, service_with):
    """The boundary: some survived, so this is not the no-answer path.

    Two statements, one citing a supplied identifier and one fabricated. Path B is "NOTHING
    survived", not "something was rejected" — an answer that lost a statement is still an
    answer, and the surviving one carries a verified citation. This is where an off-by-one
    would live, and it would be a bad one in either direction: returning the no-answer
    response here would throw away a properly cited answer, and the reverse would show an
    answer with nothing behind it.
    """
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days.")
    service_with(
        statements=[
            Statement(text="Grounded.", chunk_id=str(chunk.id)),
            Statement(text="Invented.", chunk_id="00000000-0000-4000-8000-000000000000"),
        ]
    )

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.answered is True
    assert [statement.text for statement in outcome.verified_statements] == ["Grounded."]
    assert outcome.rejected_count == 1
    assert outcome.no_answer_reason is None
    assert outcome.no_answer_reason != NO_STATEMENT_VERIFIED
    assert outcome.message is None
    # The passages and the count come back on an answered outcome, unlike on path B: this
    # is what the Sources panel is built from.
    assert outcome.result_count == 1
    assert [passage.chunk_id for passage in outcome.passages] == [str(chunk.id)]


@pytest.mark.django_db
def test_path_b_from_both_role_sessions(session_client, document, service_with):
    """Path B from an Employee session and an Administrator session (section 8 item 2).

    The passage the model was given is the one this role may read; the statement it
    returned cites the other role's chunk, which was never in the prompt and is therefore
    rejected exactly as an invented identifier would be. The no-answer response is what
    comes back, and it says nothing about the restricted chunk — not its identifier, not
    its text, not a count that would imply it.
    """
    role_name = session_client.role_name
    other_role = next(name for name in ROLE_PAIR if name != role_name)
    restricted = make_chunk(
        document, [other_role], index=1, cosine=NEAREST, text="Restricted, nearest."
    )
    permitted = make_chunk(document, [role_name], index=2, cosine=ABOVE, text="Permitted.")
    double = service_with(
        statements=[Statement(text="Claimed of another role's chunk.", chunk_id=str(restricted.id))]
    )

    outcome = answer_question(question=QUESTION, user=session_client.user)

    assert outcome.answered is False
    assert outcome.no_answer_reason == NO_STATEMENT_VERIFIED
    assert outcome.message == NO_ANSWER_MESSAGE
    assert outcome.result_count == 0
    assert outcome.passages == ()
    assert outcome.rejected_count == 1
    # Only the permitted passage ever reached the provider, and nothing of the restricted
    # chunk reaches the outcome by any route.
    (_, passages_sent) = double.generate_calls[0]
    assert [passage.chunk_id for passage in passages_sent] == [str(permitted.id)]
    assert str(restricted.id) not in repr(outcome)
    assert restricted.chunk_text not in repr(outcome)


def test_an_unanswered_outcome_with_no_reason_cannot_be_built():
    """There is no fourth shape, and the type refuses to make one.

    Item 6 returned an outcome with ``answered=False`` and ``no_answer_reason`` None,
    stated in its docstrings as the absence item 7 would fill. It is filled, and
    ``verified`` now raises rather than rebuilding it, so the hole cannot come back through
    a caller that forgets the branch. Without this, the failure mode is silent: a no-answer
    that never reaches the log is a no-answer the team cannot count, and the rate is the
    signal.
    """
    from apps.retrieval.pipeline import RetrievalOutcome
    from apps.retrieval.verification import VerificationResult

    nothing_survived = VerificationResult(
        verified_statements=(), rejected_statements=(), rejected_count=0
    )

    with pytest.raises(ValueError):
        RetrievalOutcome.verified([], nothing_survived)

    # The same input through the path-B constructor is the outcome that was wanted.
    outcome = RetrievalOutcome.no_statement_verified(nothing_survived, partial_matches=())
    assert outcome.answered is False
    assert outcome.no_answer_reason == NO_STATEMENT_VERIFIED
    assert outcome.message == NO_ANSWER_MESSAGE


@pytest.mark.django_db
def test_three_non_conforming_replies_reach_the_view_as_an_outage_not_a_no_answer(
    document, service_with
):
    """Invariant 10 and NFR-19 through the pipeline: ProviderUnavailable propagates.

    The provider raises it after MAXIMUM_GENERATION_ATTEMPTS (tested in
    apps/ai/tests/test_generation.py); here what matters is that the pipeline does not catch
    it and return a no-answer. A 503 tells the user the system could not answer; a
    no-answer would tell them the organisation holds no answer, which is a different and
    false statement, and it would corrupt the one rate FR-12 asks to be watched.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    service_with(generation_failure=ProviderUnavailable("no conforming reply in 3 attempts"))

    with pytest.raises(ProviderUnavailable):
        answer_question(question=QUESTION, user=document.uploaded_by)


@pytest.mark.django_db
def test_generation_is_reached_through_the_module_lookup_not_a_bound_import(document, monkeypatch):
    """The service is obtained at call time, so the suite's stub always applies.

    A name bound at import time would reach a real provider in a test that patched
    apps.ai.get_ai_service, which is the mistake docs/ai-provider.md section 6 warns about.
    Asserted by patching AFTER the pipeline module was imported.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    late = install(monkeypatch, ControlledService(statements=[]))

    answer_question(question=QUESTION, user=document.uploaded_by)

    assert len(late.embed_calls) == 1
    assert len(late.generate_calls) == 1


@pytest.mark.django_db
def test_generation_and_verification_from_both_role_sessions(session_client, document, service):
    """Generation and verification over each role's own passages (section 8 item 2)."""
    role_name = session_client.role_name
    other_role = next(name for name in ROLE_PAIR if name != role_name)
    restricted = make_chunk(
        document, [other_role], index=1, cosine=NEAREST, text="Restricted, nearest."
    )
    permitted = make_chunk(document, [role_name], index=2, cosine=ABOVE, text="Permitted.")

    outcome = answer_question(question=QUESTION, user=session_client.user)

    (_, passages_sent) = service.generate_calls[0]
    assert [passage.chunk_id for passage in passages_sent] == [str(permitted.id)]
    assert [statement.chunk_id for statement in outcome.verified_statements] == [str(permitted.id)]
    assert outcome.answered is True
    assert outcome.rejected_count == 0
    # A verified citation can only ever name a passage this role may read, because the
    # supplied set it was checked against is the scoped, ranked, admitted, truncated one.
    assert str(restricted.id) not in [s.chunk_id for s in outcome.verified_statements]


# --- Step 9: verification against the SUPPLIED set, not the admitted one ----------------


@pytest.mark.django_db
def test_a_citation_of_a_passage_truncated_out_of_the_prompt_is_rejected(document, monkeypatch):
    """The subtle one, and the reason verification takes the truncated set.

    A passage can clear RELEVANCE_THRESHOLD and then be discarded by the context budget.
    It was admitted, but it was never put in front of the model — so a statement citing it
    is a statement about text the model never read, which is exactly as unsupported as an
    invented identifier and is rejected on the same rule. Checking against the admitted set
    instead would quietly admit it, and the answer would carry a citation to a passage that
    was not in the prompt.

    Arranged by shrinking MAXIMUM_CONTEXT_TOKENS for this test only: the constant is
    PROVISIONAL and item 5 did not tune it, so a test that needs the budget to bite says so
    locally rather than moving the value everyone else reads.
    """
    from apps.retrieval import ranking

    monkeypatch.setattr(ranking, "MAXIMUM_CONTEXT_TOKENS", 10)
    kept = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=1, cosine=0.90, text=" ".join(["word"] * 8)
    )
    dropped = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=2, cosine=0.60, text=" ".join(["other"] * 8)
    )
    double = install(
        monkeypatch,
        ControlledService(
            statements=[
                Statement(text="From the passage it was shown.", chunk_id=str(kept.id)),
                Statement(text="From a passage it never saw.", chunk_id=str(dropped.id)),
            ]
        ),
    )

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    # The premise: the dropped chunk cleared the threshold but was not supplied.
    (_, passages_sent) = double.generate_calls[0]
    assert [passage.chunk_id for passage in passages_sent] == [str(kept.id)]

    assert [statement.chunk_id for statement in outcome.verified_statements] == [str(kept.id)]
    assert str(dropped.id) not in [s.chunk_id for s in outcome.verified_statements]
    assert outcome.rejected_count == 1
    assert "From a passage it never saw." not in repr(outcome)
    assert outcome.answered is True


@pytest.mark.django_db
def test_verification_checks_against_exactly_what_was_supplied(document, service_with):
    """Every supplied identifier is a valid citation, and only those.

    Two passages go into the prompt; the model cites both plus one invention. Both real
    citations survive and the invention does not — the supplied set is the whole rule, and
    nothing about rank, score or position affects it.
    """
    first = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=0.90, text="First.")
    second = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=0.60, text="Second.")
    service_with(
        statements=[
            Statement(text="From the best.", chunk_id=str(first.id)),
            Statement(text="Invented.", chunk_id="00000000-0000-4000-8000-000000000000"),
            Statement(text="From the second.", chunk_id=str(second.id)),
        ]
    )

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert [s.chunk_id for s in outcome.verified_statements] == [str(first.id), str(second.id)]
    assert [s.text for s in outcome.verified_statements] == ["From the best.", "From the second."]
    assert outcome.rejected_count == 1
    assert outcome.answered is True


@pytest.mark.django_db
def test_a_statement_citing_an_out_of_scope_chunk_cannot_be_verified(document, service_with):
    """FR-11 and invariant 5 meeting: an out-of-scope identifier is not in the supplied set.

    The identifier here is a REAL chunk in the store, just not one this role may read, so it
    is the strongest form of the case: the model could only have produced it by inventing
    it, and verification rejects it for the same reason it rejects nonsense. No answer can
    cite a passage the asking role may not see, even if something upstream leaked the
    identifier.
    """
    permitted = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Mine.")
    restricted = make_chunk(
        document, [ADMINISTRATOR_ROLE_NAME], index=2, cosine=NEAREST, text="Not mine."
    )
    service_with(
        statements=[
            Statement(text="Permitted fact.", chunk_id=str(permitted.id)),
            Statement(text="Restricted fact.", chunk_id=str(restricted.id)),
        ]
    )

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert [s.chunk_id for s in outcome.verified_statements] == [str(permitted.id)]
    assert str(restricted.id) not in repr(outcome)
    assert "Restricted fact." not in repr(outcome)
    assert outcome.rejected_count == 1


# --- FR-12's partial matches (item 10a): derived once, before the floor ------------------
#
# The reduction itself — rank order, one entry per source, the cap, the absence of any text
# field — is tested in apps/retrieval/tests/test_partial_matches.py, and the rendered field
# in apps/api/tests/test_ask.py. What is tested here is the property that belongs to THIS
# module: where in ``answer_question`` the derivation happens, and therefore that it cannot
# differ between the two no-answer paths or reach an answered reply.


def second_document(owner, title="Second"):
    """Another document of the same owner, visible to Employees, so a test can offer two."""
    return Document.objects.create(
        title=title, file_type="pdf", uploaded_by=owner, visible_to_roles=[EMPLOYEE_ROLE_NAME]
    )


@pytest.mark.django_db
def test_the_offer_is_identical_on_both_no_answer_paths(document, monkeypatch):
    """One corpus, one question, both paths: the same partial matches, non-empty.

    The reply is byte-identical on the two paths by design (invariant 7), and this field is
    the one most able to break that, because it is the only caller-visible thing derived from
    the ranked list. Path A is reached with a query vector orthogonal to the only passage and
    path B with the ordinary one plus a fabricated citation, so the CORPUS is held constant
    and the path is the only difference. A derivation taken from the admitted set, the
    supplied set or the rejected statements would give an empty tuple on path A and a
    populated one on path B — which is exactly the distinction the log is for and the reply
    is not.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)

    install(monkeypatch, ControlledService(vector=ELSEWHERE))
    path_a = answer_question(question=QUESTION, user=document.uploaded_by)

    install(
        monkeypatch,
        ControlledService(statements=[Statement(text="Invented.", chunk_id="not-supplied")]),
    )
    path_b = answer_question(question=QUESTION, user=document.uploaded_by)

    assert path_a.no_answer_reason == NO_RELEVANT_PASSAGE
    assert path_b.no_answer_reason == NO_STATEMENT_VERIFIED
    assert path_a.partial_matches == path_b.partial_matches
    assert [match.source_id for match in path_a.partial_matches] == [document.id]


@pytest.mark.django_db
def test_the_offer_is_taken_before_the_threshold_and_not_from_the_admitted_set(
    document, service_with
):
    """A source whose only passage scored below the floor is still offered.

    This is the "irrespective of the threshold" clause as a test. The admitted set here holds
    one passage and the supplied set holds one passage, and the offer holds TWO items — so it
    cannot have been built from either, and the sub-threshold item is the one that proves it.
    It also fixes the order: the nearer source leads, because ``rank`` ordered the list before
    anything narrowed it.
    """
    near = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    far = second_document(document.uploaded_by)
    make_chunk(far, [EMPLOYEE_ROLE_NAME], index=1, cosine=BELOW)
    double = service_with(statements=[Statement(text="Invented.", chunk_id="not-supplied")])

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.no_answer_reason == NO_STATEMENT_VERIFIED
    assert [match.source_id for match in outcome.partial_matches] == [document.id, far.id]
    # Only the admitted passage was ever supplied to generation: the second item is offered
    # without ever having been sent anywhere.
    [(_, supplied)] = double.generate_calls
    assert [passage.chunk_id for passage in supplied] == [str(near.id)]


@pytest.mark.django_db
def test_an_answered_outcome_offers_no_partial_matches(document, service):
    """FR-12 asks for partially related items in the sentence about the no-answer state.

    An answered outcome carries every item consulted with its date already; a second list of
    items that did NOT make it into the answer, beside statements that cite the ones that
    did, would present unadmitted material as though it supported the answer. The field
    stays on the dataclass — the reply's key must not vary between outcomes — and is empty.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE)
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=2, cosine=BELOW)

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.answered is True
    assert outcome.partial_matches == ()


@pytest.mark.django_db
def test_a_restricted_source_is_not_offered_as_a_partial_match(document, service_with):
    """Invariant 1 on the new field: the nearest source is Administrator-only and absent.

    A near miss is precisely what an out-of-scope document would look like from the outside —
    it is nearer the question than anything visible, so an offer built from an unscoped list
    would put it first. The candidate set was restricted in the query, so it is not in the
    ranked list to be offered, and its title, id and text are unreachable from the outcome.
    """
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=BELOW, text="Barely related.")
    restricted_source = second_document(document.uploaded_by, title="Board remuneration")
    restricted_source.visible_to_roles = [ADMINISTRATOR_ROLE_NAME]
    restricted_source.save(update_fields=["visible_to_roles"])
    restricted = make_chunk(
        restricted_source, [ADMINISTRATOR_ROLE_NAME], index=1, cosine=NEAREST, text="Not yours."
    )
    double = service_with()

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.no_answer_reason == NO_RELEVANT_PASSAGE
    assert [match.source_id for match in outcome.partial_matches] == [document.id]
    assert str(restricted_source.id) not in repr(outcome)
    assert str(restricted.id) not in repr(outcome)
    assert double.generate_calls == []  # path A never called generation either


@pytest.mark.django_db
def test_a_scope_with_no_indexed_chunk_offers_nothing(document, service):
    """No candidates at all: the tuple is empty, and nothing concludes anything from it.

    The document exists and has no chunk — an FR-08 "Insufficient content" upload is this
    shape — so retrieval genuinely ran, ranked nothing and offered nothing. The no-answer
    message is the same one every other path returns.
    """
    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert outcome.no_answer_reason == NO_RELEVANT_PASSAGE
    assert outcome.message == NO_ANSWER_MESSAGE
    assert outcome.partial_matches == ()
