"""``manage.py reindex`` — the provider-switch path (CLAUDE.md section 4, risk R10).

The command exists so that changing embedding model is a supported operation rather
than an instruction in three documents that nothing implements. What these tests
hold it to is the part that makes it worth having: every rebuilt row records the
model that actually answered, the permission stamp is taken from the source rather
than carried over from the stale chunk, and a provider whose width does not match
the stored column is refused before a single row is touched.
"""

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.testing import STUB_EMBEDDING_MODEL, StubAIService
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    MEETING_INDEXED,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, ExtractedContent
from apps.ingestion.tests.ai_doubles import install
from apps.ingestion.tests.builders import words

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES

# Comfortably above MINIMUM_CONTENT_LENGTH so nothing is rejected as a fragment.
ENOUGH_TEXT = words(200)
STALE_MODEL = "some-older-embedding-model"


@pytest.fixture
def indexed_document(document):
    """A document with extracted text and one chunk recorded against an OLD model.

    This is the state a provider switch leaves behind: rows that look healthy and
    whose vectors are no longer comparable with anything the new model produces.
    """
    ExtractedContent.objects.create(document=document, extracted_text=ENOUGH_TEXT)
    ContentChunk.objects.create(
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        chunk_index=0,
        chunk_text="stale text that the rebuild should replace",
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model=STALE_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    return document


@pytest.fixture
def meeting(db):
    from apps.meetings.models import Meeting

    return Meeting.objects.create(
        title="Operations coordination",
        meeting_date="2026-08-14",
        transcript_text=ENOUGH_TEXT,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )


@pytest.mark.django_db
def test_rebuilds_document_chunks_against_the_current_model(indexed_document):
    call_command("reindex")

    chunks = ContentChunk.objects.filter(
        source_type=DOCUMENT_SOURCE_TYPE, source_id=indexed_document.id
    )
    assert chunks.exists()
    # The whole point: nothing is left recorded against the model that no longer
    # answers, and the recorded name comes from the response (risk R10).
    assert not chunks.filter(embedding_model=STALE_MODEL).exists()
    assert {chunk.embedding_model for chunk in chunks} == {STUB_EMBEDDING_MODEL}
    assert {chunk.embedding_dimension for chunk in chunks} == {settings.EMBEDDING_DIMENSION}
    # Rebuilt from the extracted text, so the stale chunk_text is gone too.
    assert not chunks.filter(chunk_text="stale text that the rebuild should replace").exists()
    indexed_document.refresh_from_db()
    assert indexed_document.status == DOCUMENT_INDEXED


@pytest.mark.django_db
def test_restamps_visibility_from_the_source_not_the_stale_chunk(indexed_document):
    """D-17: the chunk's permission stamp is whatever the source says now.

    A visibility change made while the index was stale must not survive the rebuild
    as the old value, or FR-11 would filter on a predicate the document disagrees
    with — and the chunk is the table retrieval actually reads.
    """
    indexed_document.visible_to_roles = [ADMINISTRATOR_ROLE_NAME]
    indexed_document.save(update_fields=["visible_to_roles"])

    call_command("reindex")

    stamps = {
        tuple(chunk.visible_to_roles)
        for chunk in ContentChunk.objects.filter(
            source_type=DOCUMENT_SOURCE_TYPE, source_id=indexed_document.id
        )
    }
    assert stamps == {(ADMINISTRATOR_ROLE_NAME,)}


@pytest.mark.django_db
def test_rebuilds_meeting_chunks(meeting):
    call_command("reindex")

    chunks = ContentChunk.objects.filter(
        source_type=MEETING_SOURCE_TYPE, source_id=meeting.id
    )
    assert chunks.exists()
    assert {chunk.embedding_model for chunk in chunks} == {STUB_EMBEDDING_MODEL}
    meeting.refresh_from_db()
    assert meeting.status == MEETING_INDEXED


@pytest.mark.django_db
def test_document_without_extracted_text_is_skipped_not_failed(document, capsys):
    """Extraction failure is not something re-embedding can repair.

    A document whose text was never extracted has no chunks to rebuild. Reporting it
    as a failure would make every run of the command look broken on a corpus that
    legitimately contains one scanned PDF.
    """
    call_command("reindex")

    output = capsys.readouterr().out
    assert "skip" in output
    assert "0 failed" in output
    assert not ContentChunk.objects.filter(source_id=document.id).exists()


@pytest.mark.django_db
def test_refuses_a_provider_whose_dimension_does_not_match(indexed_document, monkeypatch):
    """The stored vector column is sized from EMBEDDING_DIMENSION (D-03, D-08).

    A provider of another width cannot be stored at all, so the command stops before
    it writes — rather than deleting a document's chunks and then discovering the
    mismatch on the first insert, which would leave that document unindexed.
    """
    install(monkeypatch, StubAIService(dimension=settings.EMBEDDING_DIMENSION + 1))

    with pytest.raises(CommandError, match="EMBEDDING_DIMENSION"):
        call_command("reindex")

    # Nothing was touched: the stale chunk is still exactly as it was.
    chunk = ContentChunk.objects.get(source_id=indexed_document.id)
    assert chunk.embedding_model == STALE_MODEL
    assert chunk.chunk_text == "stale text that the rebuild should replace"


@pytest.mark.django_db
def test_dry_run_writes_nothing(indexed_document):
    call_command("reindex", "--dry-run")

    chunk = ContentChunk.objects.get(source_id=indexed_document.id)
    assert chunk.embedding_model == STALE_MODEL
    assert chunk.chunk_text == "stale text that the rebuild should replace"


@pytest.mark.django_db
def test_unknown_provider_is_rejected(indexed_document):
    with pytest.raises(CommandError):
        call_command("reindex", "--provider", "not-a-provider")
