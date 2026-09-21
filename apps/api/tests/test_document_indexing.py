"""FR-08 embedding and indexing, through the upload endpoint (sections 7.7 and 7.8).

    Business logic (embedding consistency): each segment is converted to a vector
    via a hosted embedding service and stored with a reference to its source. The
    embedding model and dimension are recorded against every stored vector.

    Validation: ... Content falling below the minimum length is marked "insufficient
    content" rather than submitted for embedding; embedding failures are retried
    twice before the item is flagged.

The pipeline-level tests are in ``apps/ingestion/tests/``. These assert what a real
request produces: the status the caller is told, the code they get, and what is left
in the database afterwards.

NFR-21 and CLAUDE.md invariant 9 are the point of the last section: a document, its
extracted text, its chunks and its vectors commit together or not at all.
"""

import pytest
from django.core.files.storage import default_storage

from apps.core.constants import (
    DOCUMENT_INDEXED,
    DOCUMENT_INDEXING_FAILED,
    DOCUMENT_INSUFFICIENT_CONTENT,
    DOCUMENT_PARTIALLY_INDEXED,
    DOCUMENT_PROCESSING,
    MAXIMUM_EMBED_ATTEMPTS,
    ROLE_NAMES,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install

UPLOAD_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]

pytestmark = pytest.mark.django_db


def post_upload(client, upload_file, **fields):
    body = {"file": upload_file, "title": "Leave Policy 2026", **fields}
    return client.post(UPLOAD_URL, body, format="multipart")


def chunks_for(doc_id):
    return ContentChunk.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=doc_id)


# --- The indexed path -----------------------------------------------------------------


def test_an_uploaded_document_is_indexed(session_client, upload, stub_ai_service):
    response = post_upload(session_client.client, upload("sample.txt"))

    assert response.status_code == 201
    assert response.data["status"] == DOCUMENT_INDEXED
    chunks = chunks_for(response.data["doc_id"])
    assert chunks.exists()
    assert stub_ai_service.embed_calls  # the provider was actually called


def test_every_chunk_records_the_model_and_dimension_that_produced_it(
    employee_client, upload, stub_ai_service
):
    """FR-08's embedding-consistency clause, and risk R10. The values come from the
    provider's response, not from settings: a value copied from configuration would
    describe what was expected rather than what happened, and a model change would
    then be silent corruption instead of an exclusion at retrieval."""
    response = post_upload(employee_client, upload("sample.pdf"))

    chunks = list(chunks_for(response.data["doc_id"]))
    assert chunks
    for chunk in chunks:
        assert chunk.embedding_model == "stub-embed"
        assert chunk.embedding_dimension == stub_ai_service.dimension
        assert len(chunk.embedding) == chunk.embedding_dimension


def test_chunks_carry_the_sources_visibility(administrator_client, upload):
    """D-17: the FR-11 predicate and the vector live on one table, so Stage 4 filters
    before ranking structurally rather than by a join it could forget."""
    response = post_upload(
        administrator_client, upload("sample.txt"), visible_to_roles=["Administrator"]
    )

    for chunk in chunks_for(response.data["doc_id"]):
        assert chunk.visible_to_roles == ["Administrator"]


def test_chunk_indexes_are_contiguous_and_ordered(employee_client, upload):
    response = post_upload(employee_client, upload("sample.docx"))

    indexes = list(
        chunks_for(response.data["doc_id"]).order_by("chunk_index").values_list("chunk_index", flat=True)
    )
    assert indexes == list(range(len(indexes)))


def test_no_document_is_left_in_the_in_flight_status(employee_client, upload):
    """Processing is synchronous (FR-08), so "Processing" is a status the row holds
    only inside the transaction. One left behind would show as permanently
    processing in the repository, with nothing ever coming to finish it."""
    post_upload(employee_client, upload("sample.txt"))

    assert not Document.objects.filter(status=DOCUMENT_PROCESSING).exists()


# --- Retries: MAXIMUM_EMBED_ATTEMPTS is a total (D-19) ---------------------------------


def test_a_chunk_recovers_within_the_attempt_budget(monkeypatch, employee_client, upload):
    """"embedding failures are retried twice before the item is flagged" — so two
    failures followed by a success must store the chunk, having called the provider
    exactly three times."""
    service = install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS - 1))

    response = post_upload(employee_client, upload("sample.txt"))

    assert response.status_code == 201
    assert response.data["status"] == DOCUMENT_INDEXED
    chunk = chunks_for(response.data["doc_id"]).get()
    # An equality, not a floor: the constant is 1 initial call plus 2 retries, and
    # asserting "at least" would pass just as well if someone read it as a retry
    # count and made it four.
    assert service.attempts_for(chunk.chunk_text) == MAXIMUM_EMBED_ATTEMPTS == 3


def test_a_chunk_that_never_embeds_is_flagged_and_the_document_is_not_indexed(
    monkeypatch, employee_client, upload
):
    """Section 7.8 lines 89-91: every chunk failed, so the document is "Indexing
    failed" and the caller is told 422."""
    service = install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))

    response = post_upload(employee_client, upload("sample.txt"))

    assert response.status_code == 422
    assert response.data["status"] == DOCUMENT_INDEXING_FAILED
    assert not chunks_for(response.data["doc_id"]).exists()
    # The source survives the failed AI step (CLAUDE.md invariant 8, NFR-20): the
    # file is kept and the extracted text with it, so a reprocess has something to
    # work from.
    document = Document.objects.get(pk=response.data["doc_id"])
    assert document.file_path.storage.exists(document.file_path.name)
    assert ExtractedContent.objects.filter(document=document).exists()
    assert service.attempts_for(ExtractedContent.objects.get(document=document).extracted_text)


def test_one_failing_chunk_leaves_the_document_partially_indexed(
    monkeypatch, employee_client, upload
):
    """Section 7.8 lines 92-93. This is the status D-28 restored to the vocabulary:
    schema v1's five values had nothing that could describe it, and the per-chunk
    retry loop of section 7.7 produces it whenever one passage of many fails."""
    # sample.docx is long enough to be one chunk, so a multi-chunk source is built
    # here instead: a long TXT whose second chunk alone is scripted to fail.
    from django.core.files.uploadedfile import SimpleUploadedFile

    words = " ".join(f"clause{n}" for n in range(1200))  # ~3 chunks at 500/450
    long_file = SimpleUploadedFile("long.txt", words.encode("utf-8"), content_type="text/plain")

    service = ScriptedEmbedService(
        failures=MAXIMUM_EMBED_ATTEMPTS, should_fail=lambda text: text.startswith("clause450 ")
    )
    install(monkeypatch, service)

    response = post_upload(employee_client, long_file)

    assert response.status_code == 201
    assert response.data["status"] == DOCUMENT_PARTIALLY_INDEXED
    stored = chunks_for(response.data["doc_id"])
    assert stored.exists()  # the chunks that did embed are kept and searchable
    assert not stored.filter(chunk_text__startswith="clause450 ").exists()


# --- Insufficient content: not submitted for embedding at all --------------------------


def test_content_below_the_minimum_is_marked_and_never_embedded(
    session_client, stub_ai_service
):
    """FR-08 Validation: "Content falling below the minimum length is marked
    'insufficient content' rather than submitted for embedding"."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    tiny = SimpleUploadedFile("note.txt", b"Too short to index.", content_type="text/plain")

    response = post_upload(session_client.client, tiny)

    assert response.status_code == 422
    assert response.data["status"] == DOCUMENT_INSUFFICIENT_CONTENT
    # "rather than submitted for embedding" is the clause, so no call at all — not a
    # call whose result was discarded.
    assert stub_ai_service.embed_calls == []
    assert not chunks_for(response.data["doc_id"]).exists()
    document = Document.objects.get(pk=response.data["doc_id"])
    # The file is kept and remains downloadable (section 7.8 lines 47-52). Section
    # 7.8 returns before CREATE ExtractedContent, so there is no extracted row.
    assert document.file_path.storage.exists(document.file_path.name)
    assert not ExtractedContent.objects.filter(document=document).exists()


# --- NFR-21: one transaction ------------------------------------------------------------


def test_an_unexpected_failure_mid_ingestion_leaves_nothing(
    monkeypatch, employee_client, upload, media_root
):
    """CLAUDE.md invariant 9: a partial ingestion leaves nothing behind.

    The failure is raised from inside the provider call, so this is the real path
    rather than a transaction rolled back by the test. It is deliberately NOT a
    ProviderUnavailable: that one is an outcome the pipeline decided and commits a
    flagged document. An unexpected exception is not, and must leave no row, no
    extracted text, no chunk and no file.
    """
    install(
        monkeypatch,
        ScriptedEmbedService(failures=1, error=RuntimeError("the provider fell over")),
    )

    with pytest.raises(RuntimeError):
        post_upload(employee_client, upload("sample.txt"))

    assert not Document.objects.exists()
    assert not ExtractedContent.objects.exists()
    assert not ContentChunk.objects.exists()
    # The filesystem does not roll back with the database, so the stored original is
    # removed explicitly. Anything left here is bytes no row references.
    assert list(media_root.rglob("*.txt")) == []


def test_a_rolled_back_upload_leaves_its_content_hash_free(
    monkeypatch, employee_client, upload
):
    """The other half of leaving nothing: a failed ingestion must not reserve the
    duplicate check against a document that does not exist, or the same file could
    never be uploaded again."""
    install(
        monkeypatch,
        ScriptedEmbedService(failures=1, error=RuntimeError("the provider fell over")),
    )
    with pytest.raises(RuntimeError):
        post_upload(employee_client, upload("sample.txt"))

    # A healthy provider for the retry. Not monkeypatch.undo(), which would also
    # revert conftest's autouse stub and send the second upload at the real
    # provider — unreachable in the suite by design, so it would fail for a reason
    # that has nothing to do with the content hash.
    install(monkeypatch, ScriptedEmbedService(failures=0))

    # 201, not 409: the rolled-back row reserved nothing.
    assert post_upload(employee_client, upload("sample.txt")).status_code == 201
