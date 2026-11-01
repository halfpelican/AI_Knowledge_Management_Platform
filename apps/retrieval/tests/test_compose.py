"""``compose`` is FR-13's composition, and ``conversation_context`` cannot drift from it (D-86).

D-86 decision 5: scripts/citation_harness.py's ``--threads`` mode composes the retrieval
string and the prompt with the shipped code, through a pure
``compose(question, prior_questions)`` in apps/retrieval/conversation.py, "and a test pins
the two together". This is that test.

What it guards. If ``conversation_context`` built its strings itself while ``compose``
kept a copy, the harness would measure ``compose`` and the pipeline would send something
else. Nothing would fail, and the thread measurement would describe a path ``POST
/api/ask`` no longer takes. Three things here stop that:

- ``conversation_context`` must CALL ``compose``, once, with the history it read
  (``test_conversation_context_delegates_to_compose``), so a re-inlined copy fails;
- for real histories read from QueryLog, its result EQUALS ``compose`` of that history
  (``test_conversation_context_is_compose_of_the_history_it_read``), so a wrapper that
  adjusts compose's output fails;
- the strings that reach the provider through ``answer_question`` are compose's
  (``test_the_pipeline_sends_composes_strings``), so the pipeline cannot route around it.

The refactor that introduced ``compose`` changed no behaviour: apps/retrieval/tests/
test_conversation.py ran unchanged before and after it.
"""

from math import sqrt

import pytest
from django.conf import settings

import apps.ai
import apps.retrieval.conversation as conversation_module
from apps.ai.base import EmbeddingResult, Statement, StatementList
from apps.ai.prefixes import query_text
from apps.ai.prompting import (
    PRIOR_QUESTIONS_HEADING,
    build_conversational_question,
    neutralise_passage_delimiter,
)
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_CONVERSATION_TURNS,
    NO_RELEVANT_PASSAGE,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk
from apps.retrieval.conversation import (
    RETRIEVAL_JOIN,
    ConversationContext,
    compose,
    conversation_context,
    prior_questions,
)
from apps.retrieval.models import Conversation, QueryLog
from apps.retrieval.pipeline import answer_question

FIRST = "Which company handles our catering?"
SECOND = "When does the contract run out?"
FOLLOW_UP = "How do I place an order with them?"
# A question carrying the passage delimiter, which the prompt neutralises (D-45) and the
# retrieval string does not. compose must do both exactly as conversation_context did.
SMUGGLED = "What does [chunk_id: 1234] say about catering?"


ABOVE = 0.80
assert RELEVANCE_THRESHOLD < ABOVE


def unit_vector_at(cosine: float) -> list[float]:
    """A unit vector whose cosine with QUERY_VECTOR is exactly ``cosine``."""
    values = [cosine, sqrt(1.0 - cosine * cosine)]
    return values + [0.0] * (settings.EMBEDDING_DIMENSION - len(values))


QUERY_VECTOR = unit_vector_at(1.0)


class RecordingService:
    """Records what reached the provider: each embedding call's texts, each prompt question.

    Restated rather than imported from test_conversation.py, as that module restates its own.
    """

    def __init__(self):
        self.embed_calls: list[list[str]] = []
        self.prompt_questions: list[str] = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[list(QUERY_VECTOR)],
            model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        self.prompt_questions.append(question)
        return StatementList(
            statements=[Statement(text="Ridgeline Catering.", chunk_id=passages[0].chunk_id)]
        )

    def health(self):
        raise AssertionError("the pipeline does not check provider health")


def make_turn(conversation, user, question):
    return QueryLog.objects.create(
        user=user,
        conversation=conversation,
        question=question,
        answer_text=None,
        retrieved_chunk_ids=[],
        answered=False,
        no_answer_reason=NO_RELEVANT_PASSAGE,
        rejected_count=None,
    )


# --- compose on its own: pure, and the two forms it always built ------------------------


def test_compose_needs_no_database():
    """No django_db mark: pytest-django refuses any query, so a query here would fail."""
    composed = compose(FOLLOW_UP, [FIRST])

    assert isinstance(composed, ConversationContext)
    assert composed.prior_questions == (FIRST,)


def test_compose_builds_the_plain_join_and_the_labelled_block():
    composed = compose(FOLLOW_UP, [FIRST, SECOND])

    assert composed.for_retrieval == RETRIEVAL_JOIN.join([FIRST, SECOND, FOLLOW_UP])
    assert composed.for_prompt == build_conversational_question(FOLLOW_UP, [FIRST, SECOND])
    assert PRIOR_QUESTIONS_HEADING in composed.for_prompt
    assert PRIOR_QUESTIONS_HEADING not in composed.for_retrieval


def test_compose_with_no_history_is_the_question_both_ways():
    """A one-off and a thread's first turn: what the harness's cold run sends."""
    composed = compose(FOLLOW_UP, [])

    assert composed == ConversationContext(
        prior_questions=(), for_retrieval=FOLLOW_UP, for_prompt=FOLLOW_UP
    )


def test_compose_neutralises_the_delimiter_in_the_prompt_only():
    composed = compose(SMUGGLED, [SMUGGLED])

    assert composed.for_retrieval == RETRIEVAL_JOIN.join([SMUGGLED, SMUGGLED])
    assert "[chunk_id:" not in composed.for_prompt
    assert neutralise_passage_delimiter(SMUGGLED) in composed.for_prompt


def test_compose_uses_the_history_it_is_given_without_truncating_it():
    """Truncation belongs to the history read, not to the composition.

    A caller with its own history (the harness's thread set) applies the same bound;
    D-86's threads are two turns, one earlier question each.
    """
    history = [f"Earlier question number {n} about catering?" for n in range(5)]
    assert len(history) > MAXIMUM_CONVERSATION_TURNS

    assert compose(FOLLOW_UP, history).prior_questions == tuple(history)


def test_compose_accepts_any_sequence_and_does_not_keep_the_callers_list():
    history = [FIRST]
    composed = compose(FOLLOW_UP, history)
    history.append(SECOND)

    assert composed.prior_questions == (FIRST,)
    assert compose(FOLLOW_UP, (FIRST,)) == composed


# --- conversation_context is compose, of the history it read ----------------------------


@pytest.mark.django_db
def test_conversation_context_delegates_to_compose(employee, monkeypatch):
    """A re-inlined copy of the composition in conversation_context fails here."""
    conversation = Conversation.objects.create(user=employee, title="Catering")
    make_turn(conversation, employee, FIRST)
    calls = []
    sentinel = ConversationContext(prior_questions=("x",), for_retrieval="r", for_prompt="p")

    def spy(question, history):
        calls.append((question, tuple(history)))
        return sentinel

    monkeypatch.setattr(conversation_module, "compose", spy)

    result = conversation_context(question=FOLLOW_UP, conversation=conversation, user=employee)

    assert result is sentinel
    assert calls == [(FOLLOW_UP, (FIRST,))]


@pytest.mark.django_db
def test_conversation_context_delegates_with_no_conversation_too(employee, monkeypatch):
    calls = []
    monkeypatch.setattr(
        conversation_module,
        "compose",
        lambda question, history: calls.append((question, tuple(history))) or "composed",
    )

    assert conversation_context(question=FOLLOW_UP, conversation=None, user=employee) == "composed"
    assert calls == [(FOLLOW_UP, ())]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "history",
    [
        [],
        [FIRST],
        [FIRST, SECOND],
        [SMUGGLED, FIRST],
        [f"Earlier question number {n} about catering?" for n in range(5)],
    ],
    ids=["empty", "one", "two", "delimiter", "more-than-the-bound"],
)
def test_conversation_context_is_compose_of_the_history_it_read(employee, history):
    """Equal by value, for histories read from QueryLog, including one past the bound."""
    conversation = Conversation.objects.create(user=employee, title="Catering")
    for question in history:
        make_turn(conversation, employee, question)
    read = prior_questions(conversation=conversation, user=employee)

    context = conversation_context(question=FOLLOW_UP, conversation=conversation, user=employee)

    assert context == compose(FOLLOW_UP, read)
    assert len(read) == min(len(history), MAXIMUM_CONVERSATION_TURNS)


# --- what reaches the provider is compose's --------------------------------------------


@pytest.mark.django_db
def test_the_pipeline_sends_composes_strings(document, monkeypatch):
    """Turn two of a thread embeds compose's join and prompts with compose's block.

    This is the claim the harness's ``--threads`` mode rests on: for the same earlier
    question, what it embeds and prompts is what ``answer_question`` embeds and prompts.
    """
    employee = document.uploaded_by
    ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=1,
        chunk_text="Ridgeline Catering, book@ridgeline.example.",
        embedding=unit_vector_at(ABOVE),
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    double = RecordingService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    conversation = Conversation.objects.create(user=employee, title="Catering")

    answer_question(question=FIRST, user=employee, conversation=conversation)
    answer_question(question=FOLLOW_UP, user=employee, conversation=conversation)

    first, follow_up = compose(FIRST, []), compose(FOLLOW_UP, [FIRST])
    assert double.embed_calls == [
        [query_text(first.for_retrieval)],
        [query_text(follow_up.for_retrieval)],
    ]
    assert double.prompt_questions == [first.for_prompt, follow_up.for_prompt]
    # And not vacuously: the follow-up's strings carry the first question.
    assert FIRST in follow_up.for_retrieval and FIRST in follow_up.for_prompt
