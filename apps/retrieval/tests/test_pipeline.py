"""FR-12 steps 1 to 6 and no-answer path A (apps/retrieval/pipeline.py).

The autouse ``stub_ai_service`` is replaced here by a local double whose query vector
is fixed, because the stub's vectors are seeded random and no score could be predicted
from them. ``ControlledEmbeddingService`` answers with ``QUERY`` — the unit vector on
the first axis — so a chunk built by ``at_cosine(v)`` scores exactly ``v``, the same
arrangement apps/retrieval/tests/test_ranking.py uses. Its ``embed_calls`` and
``generate_calls`` lists are named as the stub's are, so a call-count assertion reads
the same either way, and its ``generate_statements`` raises: nothing in this module may
reach generation at all.

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
from apps.ai.base import EmbeddingResult, ProviderUnavailable
from apps.ai.prefixes import query_text
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    NO_ANSWER_MESSAGE,
    NO_RELEVANT_PASSAGE,
    NO_STATEMENT_VERIFIED,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk
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


class ControlledEmbeddingService:
    """An AIService whose query vector is known and whose generation call explodes.

    ``model`` defaults to the stub's name because that is what make_chunk stamps, so
    the embedding-model predicate passes and the candidate set is decided by the role
    scope alone. A test that wants the mismatch case passes another name.
    """

    def __init__(self, *, vector=None, model=STUB_EMBEDDING_MODEL):
        self.vector = QUERY if vector is None else vector
        self.model = model
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
        # Recorded first so an assertion on generate_calls can still see it, then
        # raised: at item 4 nothing may call generation, and a double that merely
        # counted the call would let a wrong implementation get as far as a diff.
        self.generate_calls.append((question, list(passages)))
        raise AssertionError(
            "generation was called from the retrieval pipeline; no-answer path A "
            "returns without invoking it (FR-12, CLAUDE.md invariant 7)"
        )

    def health(self):
        raise AssertionError("the pipeline does not check provider health")


@pytest.fixture
def service(monkeypatch):
    """Install the double where apps.ai.get_ai_service is looked up at call time."""
    double = ControlledEmbeddingService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


# --- No-answer path A ------------------------------------------------------------------


@pytest.mark.django_db
def test_path_a_returns_the_no_answer_response_without_calling_generation(document, service):
    """Nothing cleared the threshold: the no-answer outcome, and no generation call.

    **On the strength of the generate_calls assertion at this item.** There is no
    generation call site anywhere in apps/retrieval yet, so this assertion currently
    proves something the code is not able to do wrong. It is written now because it
    becomes load-bearing at item 5, when the call site appears immediately after this
    branch: KEEP IT AND RE-ASSERT IT THEN — at that point it is the test standing
    between path A and an ungrounded answer, and it is the test FR-12 and the M6 build
    plan actually ask for. Read today it is a placeholder with the right shape.

    ``embed_calls`` is the assertion that does carry weight here: retrieval genuinely
    ran — the question was embedded and a candidate set was ranked — so the empty
    result is a decision taken on the scores, not a short circuit that never looked.
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
    double = ControlledEmbeddingService(model="some-other-model")
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
    """The admitted branch at item 4: passages, a count, and no answer of any kind.

    ``answered`` is False here as well as on path A, and deliberately: no generation
    has run, so no answer has been returned, and a True here would put a
    not-yet-answered question into the answered rate. The branches are told apart by
    ``no_answer_reason`` being None and ``passages`` being non-empty. Item 5 is where
    ``answered=True`` first becomes reachable, and this assertion is expected to change
    there — it is pinned now so that the change is visible in that diff rather than
    assumed.
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
    # No answer is claimed, and no no-answer response is returned either.
    assert outcome.answered is False
    assert outcome.no_answer_reason is None
    assert outcome.message is None
    assert not hasattr(outcome, "statements")
    assert not hasattr(outcome, "citations")
    assert service.generate_calls == []


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

    class DownService(ControlledEmbeddingService):
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
    assert service.generate_calls == []


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


# --- Item 8's concern, asserted as absent here ----------------------------------------


@pytest.mark.django_db
def test_no_query_log_row_is_written_yet(document, service):
    """Item 4 writes nothing to the database; item 8 adds the QueryLog row.

    Asserted rather than left unsaid, so that item 8's diff shows the row appearing
    and this test being replaced, instead of nobody noticing which commit was supposed
    to add it. 7.10 calls recordQuery at line 76, inside this branch.
    """
    from apps.retrieval.models import QueryLog

    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=BELOW)
    answer_question(question=QUESTION, user=document.uploaded_by)

    assert QueryLog.objects.count() == 0
