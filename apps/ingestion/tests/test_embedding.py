"""embed_and_store_chunks() (proposal section 7.7, FR-08).

These tests are the retry policy and the embedding-consistency clause (risk R10) at
their own level; the status each outcome produces is asserted in test_documents.py.

They need the database: a ContentChunk row and its pgvector column are what is being
asserted about.
"""

import pytest
from django.conf import settings
from django.test import override_settings

from apps.ai.base import INPUT_TYPE_DOCUMENT, ProviderRefused, ProviderUnavailable
from apps.ai.prefixes import document_text
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_EMBED_ATTEMPTS,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk
from apps.ingestion.chunking import Chunk
from apps.ingestion.embedding import (
    DOCUMENT_SOURCE_TYPE,
    MEETING_SOURCE_TYPE,
    embed_and_store_chunks,
)
from apps.ingestion.tests.ai_doubles import MisreportingEmbedService, ScriptedEmbedService, install

pytestmark = pytest.mark.django_db

CHUNKS = [Chunk(index=0, text="Leave accrues monthly."), Chunk(index=1, text="Approvals are two.")]
# The title store() passes, so a test can say what the provider was sent: the
# document task prefix wraps the chunk text with it (apps/ai/prefixes.py).
TITLE = "Leave policy"


def sent(chunk):
    """The string the provider receives for ``chunk`` — prefixed if the configured
    embedding model takes prefixes, bare if it does not. Read through the same
    function the pipeline uses, so these tests keep measuring retries and counts
    rather than becoming assertions about the prefix; the literal documented forms
    are asserted at the bottom of this file."""
    return document_text(TITLE, chunk.text)


def store(
    chunks=CHUNKS,
    source_type=DOCUMENT_SOURCE_TYPE,
    source_id=None,
    roles=None,
    title=TITLE,
):
    """embed_and_store_chunks() with the arguments a document would supply."""
    import uuid

    return embed_and_store_chunks(
        chunks=chunks,
        source_type=source_type,
        source_id=source_id or uuid.uuid4(),
        visible_to_roles=roles if roles is not None else [EMPLOYEE_ROLE_NAME],
        title=title,
    )


# --- What every row records ------------------------------------------------------------


def test_every_chunk_is_stored_with_the_model_and_dimension_the_provider_returned(
    stub_ai_service,
):
    """FR-08's embedding-consistency clause. Retrieval executes only over chunks
    whose recorded model matches the query model (risk R10), so these two columns
    describe the response, not the configuration."""
    assert store() == 0

    rows = ContentChunk.objects.order_by("chunk_index")
    assert [row.chunk_text for row in rows] == [chunk.text for chunk in CHUNKS]
    assert [row.chunk_index for row in rows] == [0, 1]
    for row in rows:
        assert row.embedding_model == STUB_EMBEDDING_MODEL
        assert row.embedding_dimension == stub_ai_service.dimension
        assert len(row.embedding) == settings.EMBEDDING_DIMENSION


def test_a_refused_chunk_fails_at_once_without_retries(monkeypatch):
    """D-118: a 4xx other than a rate limit is ProviderRefused. A bad key or an exhausted
    quota would be refused the same way three times, so each chunk fails on its first
    attempt instead of spending all MAXIMUM_EMBED_ATTEMPTS. The document still commits with
    the status that says so, as for an outage."""
    service = install(
        monkeypatch,
        ScriptedEmbedService(
            failures=MAXIMUM_EMBED_ATTEMPTS, error=ProviderRefused("HTTP 401: invalid api key")
        ),
    )

    assert store() == len(CHUNKS)

    assert [service.attempts_for(sent(chunk)) for chunk in CHUNKS] == [1] * len(CHUNKS)
    assert not ContentChunk.objects.exists()


def test_every_chunk_is_embedded_as_a_passage(stub_ai_service):
    """D-116: each chunk's request says it is a passage. That is how Voyage learns what
    EmbeddingGemma reads from the document prefix."""
    store()

    assert stub_ai_service.embed_input_types == [INPUT_TYPE_DOCUMENT] * len(CHUNKS)


def test_every_chunk_carries_the_sources_visible_to_roles():
    """D-17: the FR-11 predicate and the vector on one table, so Stage 4 filters
    before ranking structurally rather than by remembering to."""
    store(roles=[ADMINISTRATOR_ROLE_NAME])

    assert {tuple(row.visible_to_roles) for row in ContentChunk.objects.all()} == {
        (ADMINISTRATOR_ROLE_NAME,)
    }


def test_chunks_are_keyed_to_their_source():
    import uuid

    source_id = uuid.uuid4()
    store(source_id=source_id, source_type=MEETING_SOURCE_TYPE)

    rows = ContentChunk.objects.all()
    assert {row.source_id for row in rows} == {source_id}
    assert {row.source_type for row in rows} == {MEETING_SOURCE_TYPE}
    # The two source types are the schema's fixed vocabulary, not free text.
    assert set(SOURCE_TYPES) == {DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE}


def test_one_embed_call_per_chunk_not_one_per_document(stub_ai_service):
    """Section 7.7 loops per chunk. Batching would make one transient failure cost
    the whole document and leave "Partially indexed" unreachable."""
    store()

    assert stub_ai_service.embed_calls == [[sent(CHUNKS[0])], [sent(CHUNKS[1])]]


def test_no_chunks_is_no_calls_and_no_failures(stub_ai_service):
    assert store(chunks=[]) == 0
    assert stub_ai_service.embed_calls == []
    assert ContentChunk.objects.count() == 0


# --- The retry policy (D-19: a TOTAL of 3, not 3 retries) ---------------------------------


def test_two_failures_then_success_stores_the_chunk_on_the_third_attempt(monkeypatch):
    service = install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS - 1))

    assert store(chunks=CHUNKS[:1]) == 0

    assert ContentChunk.objects.count() == 1
    # Exactly three: one initial call plus two retries (D-19). Asserted as an
    # equality, not a floor, because that is what stops MAXIMUM_EMBED_ATTEMPTS being
    # quietly read as a retry count and reduced to 2.
    assert service.attempts_for(sent(CHUNKS[0])) == MAXIMUM_EMBED_ATTEMPTS == 3


def test_a_chunk_that_exhausts_its_attempts_is_flagged_and_written_no_row(monkeypatch):
    service = install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))

    assert store(chunks=CHUNKS[:1]) == 1

    assert ContentChunk.objects.count() == 0
    assert service.attempts_for(sent(CHUNKS[0])) == MAXIMUM_EMBED_ATTEMPTS
    # The policy stops at the ceiling; it does not keep trying.
    assert len(service.embed_calls) == MAXIMUM_EMBED_ATTEMPTS


def test_one_failing_chunk_costs_only_that_chunk(monkeypatch):
    """The reason for the per-chunk loop, and the only way "Partially indexed" can
    be reached (D-28)."""
    install(
        monkeypatch,
        ScriptedEmbedService(
            failures=MAXIMUM_EMBED_ATTEMPTS, should_fail=lambda text: text == sent(CHUNKS[1])
        ),
    )

    assert store() == 1

    assert [row.chunk_text for row in ContentChunk.objects.all()] == [CHUNKS[0].text]


def test_provider_unavailable_is_a_failed_attempt_not_an_escape(monkeypatch):
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))

    # No exception: an outage is an outcome the pipeline decides about, so the
    # source still commits with a status (CLAUDE.md invariant 8, NFR-20).
    assert store() == 2


def test_an_unexpected_exception_propagates(monkeypatch):
    """Not every failure is an outcome. Anything that is not ProviderUnavailable is
    a defect, and it must roll the caller's transaction back rather than be recorded
    as "this document could not be indexed" (NFR-21)."""
    install(
        monkeypatch,
        ScriptedEmbedService(failures=1, error=RuntimeError("the provider client crashed")),
    )

    with pytest.raises(RuntimeError):
        store()


# --- Embedding consistency (risk R10) ------------------------------------------------------


def test_a_wrong_dimension_fails_the_chunk_rather_than_raising(monkeypatch):
    """A provider configured against another model returns vectors that are not
    comparable with the stored ones. pgvector would refuse the insert anyway, but as
    an opaque error part-way through the document's own transaction."""
    from apps.ai.testing import StubAIService

    install(monkeypatch, StubAIService(dimension=settings.EMBEDDING_DIMENSION // 2))

    assert store() == 2
    assert ContentChunk.objects.count() == 0


def test_a_wrong_dimension_is_not_retried(monkeypatch):
    # A misconfigured provider gives the same answer three times; retrying it only
    # spends the time. Transience is what the retry policy is for.
    service = install(monkeypatch, MisreportingEmbedService())

    assert store(chunks=CHUNKS[:1]) == 1
    assert service.attempts_for(sent(CHUNKS[0])) == 1


def test_a_vector_narrower_than_the_declared_dimension_fails_the_chunk(monkeypatch):
    """The declared dimension and the vector must agree, or the row would record a
    width that does not describe what is stored."""
    install(monkeypatch, MisreportingEmbedService())

    assert store() == 2
    assert ContentChunk.objects.count() == 0


def test_provider_unavailable_is_the_class_the_contract_names():
    # Guards the import path the retry policy catches on: a provider raising some
    # other class would not be retried at all.
    assert issubclass(ProviderUnavailable, Exception)


# --- The task prefix goes to the provider and never into the column --------------------


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL="embed-gemma")
def test_the_prefix_is_embedded_and_the_verbatim_text_is_stored(stub_ai_service):
    """The one that matters: chunk_text is what a human reads, so it stays verbatim.

    A document task prefix in the column would be read straight back out into FR-12's
    answers, its citations and every snippet in the Sources panel, and
    apps/ingestion/chunking.py keeps each chunk a verbatim substring of its source
    precisely so that cannot happen. The two strings are asserted separately: what was
    sent carries the prefix, what was stored does not.
    """
    assert store(title=TITLE) == 0

    embedded = [call[0] for call in stub_ai_service.embed_calls]
    assert embedded == [f"title: {TITLE} | text: {chunk.text}" for chunk in CHUNKS]

    stored = list(ContentChunk.objects.order_by("chunk_index").values_list("chunk_text", flat=True))
    assert stored == [chunk.text for chunk in CHUNKS]
    for text in stored:
        assert "title:" not in text
        assert "text:" not in text


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL="embed-gemma")
def test_a_source_without_a_title_still_embeds_a_title_field(stub_ai_service):
    """``title: none``, because the model was trained with the token present."""
    assert store(title=None) == 0

    embedded = [call[0] for call in stub_ai_service.embed_calls]
    assert embedded == [f"title: none | text: {chunk.text}" for chunk in CHUNKS]
    assert list(
        ContentChunk.objects.order_by("chunk_index").values_list("chunk_text", flat=True)
    ) == [chunk.text for chunk in CHUNKS]


@override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL="some-other-embedding-model")
def test_a_model_without_task_prefixes_is_sent_the_bare_chunk(stub_ai_service):
    """The prefix is EmbeddingGemma's convention, not the pipeline's."""
    assert store(title=TITLE) == 0

    assert [call[0] for call in stub_ai_service.embed_calls] == [chunk.text for chunk in CHUNKS]
