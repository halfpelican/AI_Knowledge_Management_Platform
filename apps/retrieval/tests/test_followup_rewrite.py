"""FR-13 step 7 phase 4, option 3: the follow-up rewrite in the pipeline (D-103).

What is pinned here, in the pipeline's own terms:

- **A single turn is byte-identical to the pre-phase-4 path**: no rewrite call is made
  at all, the embedded string is the question, the prompt is the question. The same
  holds for a thread's FIRST turn, which has no history to resolve.
- **With history, retrieval ranks by the REWRITE's embedding** — the one observable
  consequence the option exists for — while the generation prompt still carries the
  original question with the labelled history block. The rewrite reaches no prompt.
- **Any rewrite failure falls back to the composed join**, and the ask succeeds on it:
  transport failure, non-conforming reply (invariant 10's shape), empty, over-length,
  and an implementation that lacks the operation entirely. The fallback's retrieval is
  the pre-phase-4 retrieval, asserted byte for byte on the embedded string.
- **The scope is applied before any score, whatever string is embedded**: an
  out-of-scope chunk sitting exactly on the rewrite's vector is never fetched into
  ranking, never scored, never in the prompt and never cited (invariant 1).
- **``QueryLog.retrieval_rewrite`` records exactly what was embedded, only when a
  rewrite was used**, and the attempt log's rewrite lines carry no question text.

The double here states its own premise, as every file in this suite does: a known
query vector PER TEXT, so "the rewrite was embedded" is observable as which chunk
could score at all, not inferred from call order.
"""

import logging
from math import sqrt

import pytest
from django.conf import settings

import apps.ai
from apps.ai.base import (
    EmbeddingResult,
    FollowupRewrite,
    ProviderUnavailable,
    Statement,
    StatementList,
)
from apps.ai.prefixes import query_text
from apps.ai.prompting import build_conversational_question
from apps.ai.rewrite import MAXIMUM_REWRITE_LENGTH, RewriteViolation
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.retrieval.conversation import RETRIEVAL_JOIN, compose
from apps.retrieval.models import Conversation, QueryLog
from apps.retrieval.pipeline import ResolvedRetrieval, answer_question, resolve_retrieval_text

pytestmark = pytest.mark.django_db

QUESTION = "How much annual leave do I get?"
FOLLOW_UP = "And who approves it for me?"
REWRITE = "Who approves annual leave for employees?"
COMPOSED_JOIN = f"{QUESTION}{RETRIEVAL_JOIN}{FOLLOW_UP}"

ABOVE = 0.80
assert ABOVE > RELEVANCE_THRESHOLD


# --- Vectors: one axis per retrieval string, so what was embedded decides what can rank ---


def wide(*components) -> list[float]:
    values = list(components)
    return values + [0.0] * (settings.EMBEDDING_DIMENSION - len(values))


JOIN_AXIS = wide(1.0)  # every text embeds here unless the double is told otherwise
REWRITE_AXIS = wide(0.0, 1.0)  # orthogonal: a chunk on one axis scores 0.0 on the other


def on_axis(axis: list[float], cosine: float) -> list[float]:
    """A unit vector at ``cosine`` to ``axis`` and orthogonal to the other axis' plane."""
    third = [0.0, 0.0, sqrt(1.0 - cosine * cosine)]
    base = [component * cosine for component in axis[:2]]
    return wide(*(base[:2] + third[2:]))


def make_chunk(document, roles, *, index, embedding, text):
    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=index,
        chunk_text=text,
        embedding=embedding,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )


class RewritingService:
    """An AIService double with a scripted rewrite and a known vector PER TEXT.

    ``vectors`` maps the exact (prefixed) embedded string to its query vector;
    anything unmapped embeds on JOIN_AXIS. So a chunk placed on REWRITE_AXIS can be
    admitted only if the rewrite's text was what reached ``embed`` — which is the
    whole measurement.
    """

    def __init__(self, *, rewrite=REWRITE, rewrite_error=None, vectors=None):
        self.rewrite = rewrite
        self.rewrite_error = rewrite_error
        self.vectors = {} if vectors is None else dict(vectors)
        self.embed_calls: list[list[str]] = []
        self.generate_calls: list[tuple] = []
        self.rewrite_calls: list[tuple] = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[list(self.vectors.get(texts[0], JOIN_AXIS))],
            model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        self.generate_calls.append((question, list(passages)))
        return StatementList(
            statements=[Statement(text="A grounded statement.", chunk_id=passages[0].chunk_id)]
        )

    def rewrite_followup(self, question, prior_questions):
        self.rewrite_calls.append((question, list(prior_questions)))
        if self.rewrite_error is not None:
            raise self.rewrite_error
        return FollowupRewrite(question=self.rewrite)

    def health(self):
        raise AssertionError("the pipeline does not check provider health")


def install(monkeypatch, double):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


def rewriting_corpus(document):
    """Two Employee-readable chunks, one per axis: which was supplied says what was embedded."""
    join_chunk = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=1,
        embedding=on_axis(JOIN_AXIS, ABOVE), text="Joined-string passage.",
    )
    rewrite_chunk = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=2,
        embedding=on_axis(REWRITE_AXIS, ABOVE), text="Rewrite passage.",
    )
    return join_chunk, rewrite_chunk


def second_turn(document, monkeypatch, **service_kwargs):
    """Turn 1 asked (no history), then the follow-up asked with history; returns both."""
    service = install(
        monkeypatch,
        RewritingService(vectors={query_text(REWRITE): REWRITE_AXIS}, **service_kwargs),
    )
    conversation = Conversation.objects.create(user=document.uploaded_by, title="Leave")
    first = answer_question(
        question=QUESTION, user=document.uploaded_by, conversation=conversation
    )
    outcome = answer_question(
        question=FOLLOW_UP, user=document.uploaded_by, conversation=conversation
    )
    return service, conversation, first, outcome


# --- Single turn: byte-identical, and no rewrite call at all ------------------------------


def test_a_single_turn_makes_no_rewrite_call_and_is_byte_identical(document, monkeypatch):
    """Prompt AND retrieval: the one-off path is exactly the pre-phase-4 path."""
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1,
               embedding=on_axis(JOIN_AXIS, ABOVE), text="A passage.")
    service = install(monkeypatch, RewritingService())

    outcome = answer_question(question=QUESTION, user=document.uploaded_by)

    assert service.rewrite_calls == []  # the provider was never asked to rewrite
    assert service.embed_calls == [[query_text(QUESTION)]]  # retrieval: the question, exactly
    [(prompt_question, _)] = service.generate_calls
    assert prompt_question == QUESTION  # prompt: the question, exactly
    assert outcome.answered is True
    assert QueryLog.objects.get().retrieval_rewrite is None


def test_a_threads_first_turn_makes_no_rewrite_call(document, monkeypatch):
    """A first turn has no history: same guard, through the conversation path."""
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1,
               embedding=on_axis(JOIN_AXIS, ABOVE), text="A passage.")
    service = install(monkeypatch, RewritingService())
    conversation = Conversation.objects.create(user=document.uploaded_by, title="Leave")

    answer_question(question=QUESTION, user=document.uploaded_by, conversation=conversation)

    assert service.rewrite_calls == []
    assert service.embed_calls == [[query_text(QUESTION)]]
    assert QueryLog.objects.get().retrieval_rewrite is None


def test_resolve_makes_no_provider_lookup_without_history(monkeypatch):
    """Stronger than "no call": without history the service is not even looked up.

    Detected by RECORDING the lookup rather than raising from it, because a raise would
    be swallowed by the fallback's own ``except Exception`` and the test would pass
    exactly when the guard it pins had been removed.
    """
    looked_up = []

    def recording_lookup():
        looked_up.append(True)
        return RewritingService()

    monkeypatch.setattr(apps.ai, "get_ai_service", recording_lookup)

    resolved = resolve_retrieval_text(question=QUESTION, context=compose(QUESTION, []))

    assert looked_up == []  # the provider was not consulted at all
    assert resolved == ResolvedRetrieval(text=QUESTION, rewrite=None)


# --- With history: the rewrite is what retrieval ranks by --------------------------------


def test_a_follow_up_ranks_by_the_rewrites_embedding_not_the_joins(document, monkeypatch):
    """The option's whole point, observable: only the rewrite's axis can admit this chunk."""
    join_chunk, rewrite_chunk = rewriting_corpus(document)
    service, conversation, first, outcome = second_turn(document, monkeypatch)

    # Turn 1 (no history) answered from the join axis, as ever.
    assert first.answered and first.passages[0].chunk_id == str(join_chunk.id)
    # Turn 2 embedded the REWRITE — asserted on the string and on its consequence.
    assert service.rewrite_calls == [(FOLLOW_UP, [QUESTION])]
    assert service.embed_calls[-1] == [query_text(REWRITE)]
    assert outcome.answered is True
    assert [passage.chunk_id for passage in outcome.passages] == [str(rewrite_chunk.id)]
    [statement] = outcome.verified_statements
    assert statement.chunk_id == str(rewrite_chunk.id)


def test_the_generation_prompt_is_untouched_by_the_rewrite(document, monkeypatch):
    """The prompt still carries the original question and the labelled history block;
    the rewrite appears in no prompt, no reply and no citation."""
    rewriting_corpus(document)
    service, conversation, first, outcome = second_turn(document, monkeypatch)

    follow_up_prompt, _ = service.generate_calls[-1]
    assert follow_up_prompt == build_conversational_question(FOLLOW_UP, [QUESTION])
    assert REWRITE not in follow_up_prompt
    assert all(REWRITE not in statement.text for statement in outcome.verified_statements)


def test_the_rewrite_is_recorded_exactly_as_embedded_and_only_when_used(document, monkeypatch):
    rewriting_corpus(document)
    service, conversation, first, outcome = second_turn(document, monkeypatch)

    rows = {row.question: row for row in QueryLog.objects.all()}
    assert rows[QUESTION].retrieval_rewrite is None  # the first turn did not rewrite
    assert rows[FOLLOW_UP].retrieval_rewrite == REWRITE  # the follow-up's, verbatim
    # The question column is untouched by the rewrite: still the question as asked.
    assert set(rows) == {QUESTION, FOLLOW_UP}


# --- Any failure: the composed join, exactly as today ------------------------------------


@pytest.mark.parametrize(
    "service_kwargs",
    [
        {"rewrite_error": ProviderUnavailable("the NPU went away")},  # transport/timeout
        {"rewrite_error": RewriteViolation("no 'question' key")},  # non-conforming
        {"rewrite": ""},  # empty
        {"rewrite": "   "},  # whitespace-only
        {"rewrite": "x" * (MAXIMUM_REWRITE_LENGTH + 1)},  # over the ceiling
        {"rewrite_error": RuntimeError("an implementation bug")},  # anything else at all
    ],
    ids=["unavailable", "non-conforming", "empty", "whitespace", "over-length", "unexpected"],
)
def test_a_failing_rewrite_falls_back_to_the_composed_join(document, monkeypatch, service_kwargs):
    """The ask never fails because the rewrite did: retrieval proceeds exactly as today."""
    join_chunk, rewrite_chunk = rewriting_corpus(document)
    service, conversation, first, outcome = second_turn(document, monkeypatch, **service_kwargs)

    assert len(service.rewrite_calls) == 1  # it was attempted, once
    # The fallback retrieval is byte-identical to the pre-phase-4 path: the plain join.
    assert service.embed_calls[-1] == [query_text(COMPOSED_JOIN)]
    assert outcome.answered is True  # the ask succeeded on the fallback
    assert [passage.chunk_id for passage in outcome.passages] == [str(join_chunk.id)]
    assert QueryLog.objects.get(question=FOLLOW_UP).retrieval_rewrite is None


class LegacyService:
    """An AIService from before the operation existed: no ``rewrite_followup`` at all.

    Every pre-phase-4 test double in this suite is this shape, which is why the
    fallback on AttributeError is load-bearing: it is what keeps those doubles valid
    providers, and what keeps an ask alive against an implementation that missed the
    merge.
    """

    def __init__(self):
        self.embed_calls: list[list[str]] = []
        self.generate_calls: list[tuple] = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[list(JOIN_AXIS)],
            model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        self.generate_calls.append((question, list(passages)))
        return StatementList(
            statements=[Statement(text="A grounded statement.", chunk_id=passages[0].chunk_id)]
        )

    def health(self):
        raise AssertionError("the pipeline does not check provider health")


def test_a_provider_missing_the_operation_falls_back(document, monkeypatch):
    join_chunk, _ = rewriting_corpus(document)
    service = install(monkeypatch, LegacyService())
    conversation = Conversation.objects.create(user=document.uploaded_by, title="Leave")
    answer_question(question=QUESTION, user=document.uploaded_by, conversation=conversation)

    outcome = answer_question(
        question=FOLLOW_UP, user=document.uploaded_by, conversation=conversation
    )

    assert service.embed_calls[-1] == [query_text(COMPOSED_JOIN)]
    assert outcome.answered is True
    assert QueryLog.objects.get(question=FOLLOW_UP).retrieval_rewrite is None


# --- Scope before any score, with the rewrite as the query --------------------------------


def test_an_out_of_scope_chunk_on_the_rewrites_vector_is_never_scored(document, monkeypatch):
    """Invariant 1 with the rewrite as the query: the restricted chunk sits EXACTLY on
    the rewrite's axis, so a post-filter would have ranked it first. It is never
    fetched into ranking at all — asserted on the candidate rows the ranking step
    received, not only on the prompt and the reply."""
    _, rewrite_chunk = rewriting_corpus(document)
    restricted = make_chunk(
        document, [ADMINISTRATOR_ROLE_NAME], index=3,
        embedding=on_axis(REWRITE_AXIS, 0.999), text="Administrator-only passage.",
    )

    import apps.retrieval.pipeline as pipeline

    scored_rows = []
    original_rank = pipeline.rank

    def spying_rank(candidates, query_vector):
        rows = list(candidates)
        scored_rows.extend(rows)
        return original_rank(rows, query_vector)

    monkeypatch.setattr(pipeline, "rank", spying_rank)
    service, conversation, first, outcome = second_turn(document, monkeypatch)

    assert str(restricted.id) not in {str(row.id) for row in scored_rows}  # never scored
    for _, passages in service.generate_calls:
        assert str(restricted.id) not in {passage.chunk_id for passage in passages}
        assert all("Administrator-only" not in passage.text for passage in passages)
    assert outcome.answered is True
    assert [passage.chunk_id for passage in outcome.passages] == [str(rewrite_chunk.id)]


# --- The attempt log: outcome only, no question text --------------------------------------


def test_the_rewrite_log_lines_carry_the_outcome_and_no_question_text(
    document, monkeypatch, caplog
):
    rewriting_corpus(document)
    with caplog.at_level(logging.INFO, logger="apps.ai.attempts"):
        second_turn(document, monkeypatch)

    used = [record for record in caplog.records if "follow-up rewrite used" in record.getMessage()]
    assert len(used) == 1
    for record in caplog.records:
        message = record.getMessage()
        assert QUESTION not in message
        assert FOLLOW_UP not in message
        assert REWRITE not in message


def test_the_fallback_log_line_names_the_cause_and_no_question_text(
    document, monkeypatch, caplog
):
    rewriting_corpus(document)
    with caplog.at_level(logging.INFO, logger="apps.ai.attempts"):
        second_turn(
            document, monkeypatch,
            rewrite_error=ProviderUnavailable("connection refused by the provider"),
        )

    fell_back = [
        record for record in caplog.records
        if "follow-up rewrite fell back to the composed join" in record.getMessage()
    ]
    assert len(fell_back) == 1
    assert fell_back[0].levelno == logging.WARNING
    assert "ProviderUnavailable" in fell_back[0].getMessage()
    for record in caplog.records:
        message = record.getMessage()
        assert QUESTION not in message
        assert FOLLOW_UP not in message
