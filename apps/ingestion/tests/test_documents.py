"""ingest_and_index_document() (proposal section 7.8, FR-08).

The pipeline at its own level: the statuses section 7.8 assigns, the
insufficient-content guard, and the NFR-21 transaction. The same journey through the
HTTP endpoint is apps/api/tests/, which is the coordinator's.

Every test uses the media_root fixture, so uploads are written into the test's own
temporary directory and "the stored file was removed" means something.
"""

import pytest

from apps.core.constants import (
    DOCUMENT_INDEXED,
    DOCUMENT_INDEXING_FAILED,
    DOCUMENT_INSUFFICIENT_CONTENT,
    DOCUMENT_PARTIALLY_INDEXED,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_EMBED_ATTEMPTS,
    MINIMUM_CONTENT_LENGTH,
)
from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.ingestion.chunking import length_in_tokens, split_into_overlapping_chunks
from apps.ingestion.documents import ingest_and_index_document
from apps.ingestion.embedding import DOCUMENT_SOURCE_TYPE
from apps.ingestion.signatures import compute_content_hash
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install
from apps.ingestion.tests.builders import upload, words

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("media_root")]

# Comfortably above MINIMUM_CONTENT_LENGTH and below CHUNK_SIZE: one chunk.
ONE_CHUNK_TEXT = words(120)
# Two chunks, and the second is the only one ending in "w500", which is how a test
# fails exactly one chunk of a document (the "Partially indexed" case).
TWO_CHUNK_TEXT = words(501)
SECOND_CHUNK_MARKER = "w500"


def ingest(text=ONE_CHUNK_TEXT, *, user, roles=None, name="policy.txt"):
    """ingest_and_index_document() for a TXT upload of ``text``."""
    file = upload(text.encode("utf-8"), name)
    return ingest_and_index_document(
        uploaded_file=file,
        file_format="txt",
        content_hash=compute_content_hash(file),
        title="Leave Policy 2026",
        department="People",
        visible_to_roles=roles if roles is not None else [EMPLOYEE_ROLE_NAME],
        uploaded_by=user,
    )


def fail_second_chunk_only(text):
    return text.rstrip().endswith(SECOND_CHUNK_MARKER)


# --- The happy path: indexed ---------------------------------------------------------


def test_a_document_is_extracted_chunked_embedded_and_indexed(employee, stub_ai_service):
    outcome = ingest(user=employee)

    assert outcome.http_status == 201
    assert outcome.document.status == DOCUMENT_INDEXED
    assert ExtractedContent.objects.get(document=outcome.document).extracted_text == ONE_CHUNK_TEXT
    chunks = ContentChunk.objects.filter(source_id=outcome.document.id)
    assert chunks.count() == 1
    assert stub_ai_service.embed_calls == [[ONE_CHUNK_TEXT]]


def test_chunks_are_keyed_to_the_document_and_carry_its_visibility(employee):
    """D-17: stamped at ingestion from the owning Document, so FR-11 can filter
    before ranking without a join."""
    outcome = ingest(TWO_CHUNK_TEXT, user=employee, roles=[EMPLOYEE_ROLE_NAME])

    chunks = ContentChunk.objects.filter(source_id=outcome.document.id).order_by("chunk_index")
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert {chunk.source_type for chunk in chunks} == {DOCUMENT_SOURCE_TYPE}
    assert all(chunk.visible_to_roles == [EMPLOYEE_ROLE_NAME] for chunk in chunks)
    # The stored chunk text is what the chunker produced, verbatim (D-31).
    assert [chunk.chunk_text for chunk in chunks] == [
        chunk.text for chunk in split_into_overlapping_chunks(TWO_CHUNK_TEXT)
    ]


# --- Partially indexed and indexing failed (section 7.8 lines 89-96, D-28) --------------


def test_some_chunks_failing_is_partially_indexed_and_still_a_201(employee, monkeypatch):
    install(
        monkeypatch,
        ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS, should_fail=fail_second_chunk_only),
    )

    outcome = ingest(TWO_CHUNK_TEXT, user=employee)

    assert outcome.http_status == 201
    assert outcome.document.status == DOCUMENT_PARTIALLY_INDEXED
    # The record is committed with the status that names the outcome; it is not a
    # half-written row, which is the distinction D-28 draws.
    assert Document.objects.get(pk=outcome.document.pk).status == DOCUMENT_PARTIALLY_INDEXED
    assert ContentChunk.objects.filter(source_id=outcome.document.id).count() == 1
    assert ExtractedContent.objects.filter(document=outcome.document).exists()


def test_every_chunk_failing_is_indexing_failed_and_a_422(employee, monkeypatch):
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))

    outcome = ingest(TWO_CHUNK_TEXT, user=employee)

    assert outcome.http_status == 422
    assert outcome.detail
    assert Document.objects.get(pk=outcome.document.pk).status == DOCUMENT_INDEXING_FAILED
    assert not ContentChunk.objects.filter(source_id=outcome.document.id).exists()
    # CLAUDE.md invariant 8 and NFR-20: a failed AI step never discards the source.
    # The original and its text both survive the failure.
    assert ExtractedContent.objects.filter(document=outcome.document).exists()
    assert outcome.document.file_path.storage.exists(outcome.document.file_path.name)


def test_a_transient_failure_costs_nothing_when_a_retry_succeeds(employee, monkeypatch):
    service = install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS - 1))

    outcome = ingest(user=employee)

    assert outcome.document.status == DOCUMENT_INDEXED
    assert service.attempts_for(ONE_CHUNK_TEXT) == MAXIMUM_EMBED_ATTEMPTS == 3


# --- Insufficient content (section 7.8 lines 46-53, D-31) ---------------------------------


def test_text_below_the_minimum_is_marked_and_never_embedded(employee, stub_ai_service):
    """FR-08: content below the threshold is marked "insufficient content" and is
    not submitted for embedding. A fragment embeds into an unreliable vector that
    would match unpredictably against every later query."""
    short_text = words(MINIMUM_CONTENT_LENGTH - 1)
    assert length_in_tokens(short_text) < MINIMUM_CONTENT_LENGTH

    outcome = ingest(short_text, user=employee)

    assert outcome.http_status == 422
    assert outcome.detail
    assert Document.objects.get(pk=outcome.document.pk).status == DOCUMENT_INSUFFICIENT_CONTENT
    # "Not submitted for embedding" is the clause, so no call was made at all.
    assert stub_ai_service.embed_calls == []
    assert not ContentChunk.objects.filter(source_id=outcome.document.id).exists()


def test_insufficient_content_writes_no_extracted_content_row(employee):
    """Section 7.8 returns at line 53, before CREATE ExtractedContent at line 58.
    Deliberate, and asserted here so it cannot be "tidied up" later: the file itself
    is kept and stays downloadable, and re-parsing it would produce the same text."""
    outcome = ingest(words(MINIMUM_CONTENT_LENGTH - 1), user=employee)

    assert not ExtractedContent.objects.filter(document=outcome.document).exists()
    assert outcome.document.file_path.storage.exists(outcome.document.file_path.name)


def test_text_exactly_at_the_minimum_is_indexed(employee):
    # The boundary is "below the minimum", so the minimum itself passes.
    at_the_line = words(MINIMUM_CONTENT_LENGTH)
    assert length_in_tokens(at_the_line) == MINIMUM_CONTENT_LENGTH

    outcome = ingest(at_the_line, user=employee)

    assert outcome.document.status == DOCUMENT_INDEXED


# --- NFR-21: ingestion is atomic ------------------------------------------------------------


def test_an_unexpected_failure_mid_ingestion_leaves_nothing_behind(
    employee, monkeypatch, media_root
):
    """CLAUDE.md invariant 9. The failure is raised from inside the embed call, so
    it happens on the real path with the document row, its text and its first chunk
    already written inside the transaction.

    RuntimeError rather than ProviderUnavailable on purpose: an outage is an outcome
    the pipeline decides about and commits a status for, while an unexpected
    exception is a defect and must leave no trace."""
    install(
        monkeypatch,
        ScriptedEmbedService(
            failures=1,
            should_fail=fail_second_chunk_only,
            error=RuntimeError("the provider client crashed"),
        ),
    )

    with pytest.raises(RuntimeError):
        ingest(TWO_CHUNK_TEXT, user=employee)

    assert not Document.objects.exists()
    assert not ExtractedContent.objects.exists()
    assert not ContentChunk.objects.exists()
    # A filesystem does not roll back with the database, so the stored original has
    # to be removed explicitly or it is an orphan nothing references.
    assert [path for path in media_root.rglob("*") if path.is_file()] == []
