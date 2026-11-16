"""FR-12 step 2: embedding the question (apps/retrieval/query_embedding.py).

The doubles here are local to this module and deliberately not subclasses of
StubAIService: they answer with their OWN model name, which is what lets
test_the_service_is_obtained_at_call_time tell the module's lookup apart from the
autouse stub. apps/ingestion/tests/ai_doubles.py has the scripted-failure double
for ingestion, whose services all answer as the stub does; that is right for
ingestion and useless for the lookup test below.

Nothing here reaches a provider, live or otherwise: no socket, no openai SDK, and
the fakes are plain classes with a call counter.
"""

import pytest
from django.conf import settings
from django.test import override_settings

import apps.ai
from apps.ai.base import INPUT_TYPE_QUERY, EmbeddingResult, ProviderUnavailable
from apps.ai.prefixes import query_text
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import EMPLOYEE_ROLE_NAME, MAXIMUM_EMBED_ATTEMPTS, SOURCE_TYPES
from apps.documents.models import ContentChunk
from apps.retrieval.query_embedding import embed_question
from apps.retrieval.scoping import candidate_chunks

QUESTION = "How much annual leave do I get?"

# A name that is neither the stub's nor anything in settings, so a test asserting on
# it can only be reading the fake's own response.
FAKE_EMBEDDING_MODEL = "fake-embed-model"
# The same spelling test_scoping.py uses for a corpus indexed by another model.
OTHER_EMBEDDING_MODEL = "some-other-model"


class FakeEmbeddingService:
    """A minimal AIService with a call counter, a scripted outage and a scripted answer.

    ``fail_first`` attempts raise ProviderUnavailable and then it succeeds;
    ``always_down=True`` never succeeds. Each failure carries its attempt number in
    its message, so a test can prove which failure was the one that escaped.

    The last three arguments script a response that ARRIVES rather than failing, and
    is not usable: ``vector_count`` other than 1, a ``declared_dimension`` that is not
    the index's, or a ``vector_width`` that is not the width declared. They default to
    a well-formed answer, so a test only names the one thing it is breaking.
    """

    def __init__(
        self,
        *,
        model=FAKE_EMBEDDING_MODEL,
        fail_first=0,
        always_down=False,
        vector_count=1,
        declared_dimension=None,
        vector_width=None,
    ):
        self.model = model
        self.fail_first = fail_first
        self.always_down = always_down
        self.vector_count = vector_count
        self.declared_dimension = (
            settings.EMBEDDING_DIMENSION if declared_dimension is None else declared_dimension
        )
        self.vector_width = self.declared_dimension if vector_width is None else vector_width
        self.calls = 0
        self.texts: list[list[str]] = []

    def embed(self, texts: list[str], *, input_type=None) -> EmbeddingResult:
        self.calls += 1  # counted before any failure, so failed attempts count too
        self.texts.append(list(texts))
        if self.always_down or self.calls <= self.fail_first:
            raise ProviderUnavailable(f"fake outage on attempt {self.calls}")
        return EmbeddingResult(
            vectors=[[0.5] * self.vector_width for _ in range(self.vector_count)],
            model=self.model,
            dimension=self.declared_dimension,
        )


def install(monkeypatch, service):
    """Install a double the way conftest.py installs the stub, for the same reason:
    query_embedding looks get_ai_service up on the module at call time."""
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
    return service


def make_chunk(document, *, index, embedding_model):
    """An Employee-visible chunk recorded against ``embedding_model``.

    Deliberately small and local: the only thing this module needs from a chunk is
    the pair of columns the candidate filter reads. test_scoping.py owns the fuller
    builder for the permission cases.
    """
    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=index,
        chunk_text=f"Passage {index}.",
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model=embedding_model,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )


def test_the_question_is_embedded_by_the_suites_stub(stub_ai_service):
    """Happy path: one vector of the configured width, and the stub's model name."""
    result = embed_question(QUESTION)

    assert result.model == STUB_EMBEDDING_MODEL
    assert result.dimension == settings.EMBEDDING_DIMENSION
    assert len(result.vectors) == 1
    assert len(result.vectors[0]) == settings.EMBEDDING_DIMENSION
    assert all(isinstance(value, float) for value in result.vectors[0])
    # One batch of one, carrying the model's query task prefix; the tests below
    # assert the prefixed form itself.
    assert stub_ai_service.embed_calls == [[query_text(QUESTION)]]


def test_the_question_is_embedded_as_a_query(stub_ai_service):
    """D-116: the request says it is a question. That is how Voyage learns what
    EmbeddingGemma reads from the query prefix."""
    embed_question(QUESTION)

    assert stub_ai_service.embed_input_types == [INPUT_TYPE_QUERY]


def test_the_model_name_comes_from_the_response_not_from_settings(monkeypatch):
    """The name the candidate filter matches on is whatever the provider answered.

    The fake answers with a name that appears in no setting, so an implementation
    reading settings.FLM_EMBED_MODEL — or any literal — fails here. Ingestion records
    the response's name on every chunk; this is the query side of that one value
    (risk R10, docs/ai-provider.md section 4).
    """
    service = install(monkeypatch, FakeEmbeddingService())

    result = embed_question(QUESTION)

    assert result.model == FAKE_EMBEDDING_MODEL
    assert result.model != settings.FLM_EMBED_MODEL
    assert result.model != STUB_EMBEDDING_MODEL
    assert service.calls == 1  # no needless retry on a provider that answered


def test_the_service_is_obtained_at_call_time(monkeypatch, stub_ai_service):
    """The lookup is ``apps.ai.get_ai_service()`` on the module, not a bound name.

    The autouse fixture has already installed the stub; this replaces it AFTER
    apps.retrieval.query_embedding was imported. A module that had written
    ``from apps.ai import get_ai_service`` would hold the old reference and quietly
    answer as the stub — plausible, passing, and reaching a real provider in
    production. The assertion that distinguishes them is which double was called.
    """
    service = install(monkeypatch, FakeEmbeddingService())

    result = embed_question(QUESTION)

    assert service.calls == 1
    assert service.texts == [[query_text(QUESTION)]]
    assert result.model == FAKE_EMBEDDING_MODEL
    assert stub_ai_service.embed_calls == []  # the stub installed at setup was not used


def test_a_recovering_provider_is_retried_and_its_result_returned(monkeypatch):
    """Two outages then an answer: the answer is returned, after exactly 3 calls."""
    service = install(monkeypatch, FakeEmbeddingService(fail_first=2))

    result = embed_question(QUESTION)

    assert result.model == FAKE_EMBEDDING_MODEL
    assert len(result.vectors[0]) == settings.EMBEDDING_DIMENSION
    assert service.calls == 3 == MAXIMUM_EMBED_ATTEMPTS


def test_a_provider_that_stays_down_raises_after_exactly_three_attempts(monkeypatch):
    """MAXIMUM_EMBED_ATTEMPTS is a TOTAL: 1 initial call + 2 retries (D-19).

    The exact count is the point of this test. ``>= 1`` would pass against a constant
    someone had helpfully "corrected" from 3 to 2, reading it as a retry count, and
    the system would then give up one attempt early on every transient outage. The
    equality is what keeps the constant honest, exactly as NFR-19's fault-injection
    test does for generation.
    """
    service = install(monkeypatch, FakeEmbeddingService(always_down=True))

    with pytest.raises(ProviderUnavailable):
        embed_question(QUESTION)

    assert service.calls == 3
    assert service.calls == MAXIMUM_EMBED_ATTEMPTS


def test_the_last_failures_own_message_survives(monkeypatch):
    """The escaping exception is the third failure itself, not a generic replacement.

    The view turns this into the 503 (NFR-19); whoever reads the log wants the
    provider's last words, not a summary of them.
    """
    install(monkeypatch, FakeEmbeddingService(always_down=True))

    with pytest.raises(ProviderUnavailable) as excinfo:
        embed_question(QUESTION)

    assert str(excinfo.value) == f"fake outage on attempt {MAXIMUM_EMBED_ATTEMPTS}"


# --- A response that arrives and cannot be used: one attempt, not three ----------------


def test_two_vectors_for_one_question_is_refused_without_a_retry(monkeypatch):
    """One question, one vector. Two means the response is not the one asked for."""
    service = install(monkeypatch, FakeEmbeddingService(vector_count=2))

    with pytest.raises(ProviderUnavailable) as excinfo:
        embed_question(QUESTION)

    assert service.calls == 1  # exactly one: not retried
    assert "2 vectors" in str(excinfo.value)


def test_an_empty_vector_list_is_refused_without_a_retry(monkeypatch):
    """The IndexError case: ranking would read vectors[0] of nothing."""
    service = install(monkeypatch, FakeEmbeddingService(vector_count=0))

    with pytest.raises(ProviderUnavailable):
        embed_question(QUESTION)

    assert service.calls == 1


def test_a_declared_dimension_that_is_not_the_indexs_is_refused_without_a_retry(monkeypatch):
    """A provider embedding at another width cannot be compared with this index.

    The chunks were written at EMBEDDING_DIMENSION; a query vector of another width is
    not a lower-quality comparison, it is not a comparison at all (risk R10).
    """
    service = install(
        monkeypatch,
        FakeEmbeddingService(declared_dimension=settings.EMBEDDING_DIMENSION // 2),
    )

    with pytest.raises(ProviderUnavailable) as excinfo:
        embed_question(QUESTION)

    assert service.calls == 1
    assert str(settings.EMBEDDING_DIMENSION) in str(excinfo.value)


def test_a_vector_narrower_than_the_dimension_it_declares_is_refused_without_a_retry(monkeypatch):
    """Declared-versus-actual: the check ingestion's _is_usable() ends with.

    Both numbers are plausible on their own and only the pair is wrong, which is why
    it needs its own test — the declared width matches the index, so nothing but this
    check notices. pgvector refuses it on the chunk side; on the query side there is
    no column to refuse it.
    """
    service = install(
        monkeypatch,
        FakeEmbeddingService(
            declared_dimension=settings.EMBEDDING_DIMENSION,
            vector_width=settings.EMBEDDING_DIMENSION - 1,
        ),
    )

    with pytest.raises(ProviderUnavailable) as excinfo:
        embed_question(QUESTION)

    assert service.calls == 1
    assert str(settings.EMBEDDING_DIMENSION - 1) in str(excinfo.value)


def test_an_outage_is_worth_three_attempts_and_a_misconfiguration_is_worth_one(monkeypatch):
    """The contrast, stated in one place, because the call counts are the whole rule.

    A transient outage may succeed on the next call, so it is worth
    MAXIMUM_EMBED_ATTEMPTS of them. A provider that answered — with something
    unusable — has told us how it is configured, and two more calls would collect the
    same answer twice more; it is worth exactly one. Both leave as
    ProviderUnavailable and both become the same 503, so the exception type cannot
    tell them apart and only these counts can. The precedent is
    apps/ingestion/embedding.py, which retries the outage and fails the chunk at once
    on the unusable response.
    """
    down = install(monkeypatch, FakeEmbeddingService(always_down=True))
    with pytest.raises(ProviderUnavailable):
        embed_question(QUESTION)
    assert down.calls == MAXIMUM_EMBED_ATTEMPTS == 3

    misconfigured = install(monkeypatch, FakeEmbeddingService(vector_count=2))
    with pytest.raises(ProviderUnavailable):
        embed_question(QUESTION)
    assert misconfigured.calls == 1


def test_the_question_is_embedded_without_being_length_checked(stub_ai_service):
    """Question bounds are the pipeline entry point's job, not this function's.

    A question far below MINIMUM_QUESTION_LENGTH is embedded here without complaint;
    FR-12's 400 is returned before this function is reached, so that no provider is
    called for a question the request should never have made.
    """
    result = embed_question("hi")

    assert result.model == STUB_EMBEDDING_MODEL
    assert stub_ai_service.embed_calls == [[query_text("hi")]]


@pytest.mark.django_db
def test_the_query_model_and_the_chunk_model_are_the_same_name(document, stub_ai_service):
    """The two halves of risk R10 meet here.

    ``embed_question`` reports the model the provider answered with; ingestion
    recorded the same value on each chunk from its own response. Feeding one into the
    other is the whole mechanism, and this is the test that shows both sides read one
    name from one place rather than two configuration values that happen to agree.
    """
    comparable = make_chunk(document, index=1, embedding_model=STUB_EMBEDDING_MODEL)
    stale = make_chunk(document, index=2, embedding_model=OTHER_EMBEDDING_MODEL)

    result = embed_question(QUESTION)
    candidates = list(candidate_chunks(role_name=EMPLOYEE_ROLE_NAME, embedding_model=result.model))

    assert result.model == STUB_EMBEDDING_MODEL
    assert candidates == [comparable]
    assert stale not in candidates
    assert ContentChunk.objects.count() == 2  # the stale row exists and is simply not a candidate


# --- The query task prefix (apps/ai/prefixes.py) ----------------------------------------


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL="embed-gemma")
def test_the_prefixed_question_is_what_the_provider_is_handed(monkeypatch):
    """EmbeddingGemma is told it is embedding a query, in the form it documents.

    The prefix exists on the wire and nowhere else: the EmbeddingResult is unchanged,
    and the caller's own question is what gets logged, shown and stored.
    """
    service = install(monkeypatch, FakeEmbeddingService())

    result = embed_question(QUESTION)

    assert service.texts == [[f"task: search result | query: {QUESTION}"]]
    assert QUESTION in service.texts[0][0]  # verbatim inside it, not rewritten
    assert result.model == FAKE_EMBEDDING_MODEL
    assert len(result.vectors[0]) == settings.EMBEDDING_DIMENSION


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL="some-other-embedding-model")
def test_a_model_without_task_prefixes_is_handed_the_bare_question(monkeypatch):
    """The prefix belongs to the model, not to the pipeline."""
    service = install(monkeypatch, FakeEmbeddingService())

    embed_question(QUESTION)

    assert service.texts == [[QUESTION]]
