"""``manage.py reindex`` — every stored vector rebuilt with the database's own provider (risk R10).

What these tests hold it to: every rebuilt row records the model that actually answered, the
permission stamp is taken from the source rather than carried over from the stale chunk, and a
provider whose width does not match the stored column is refused before a single row is touched.
A database keeps the provider it was set up with (D-131), so the command neither resizes the
column nor takes another provider.
"""

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings

from apps.ai.testing import STUB_EMBEDDING_MODEL, StubAIService
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMBEDDING_DIMENSION_BY_PROVIDER,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    MEETING_INDEXED,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, ExtractedContent
from apps.ingestion.management.commands.reindex import VALID_PROVIDERS
from apps.ingestion.tests.ai_doubles import install
from apps.ingestion.tests.builders import words

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES

# Comfortably above MINIMUM_CONTENT_LENGTH so nothing is rejected as a fragment.
ENOUGH_TEXT = words(200)
STALE_MODEL = "some-older-embedding-model"
# A width the test database's column was not built at: a provider of another width (D-131).
NEW_WIDTH = settings.EMBEDDING_DIMENSION + 256


def column_type():
    """The stored column's type as Postgres reports it, e.g. "vector(768)"."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "WHERE a.attrelid = 'content_chunks'::regclass AND a.attname = 'embedding'"
        )
        (type_name,) = cursor.fetchone()
    return type_name


def database_name():
    """The connected database's name, which --resize-column was given until 14 November 2026."""
    return connection.settings_dict["NAME"]


@pytest.fixture
def indexed_document(document):
    """A document with extracted text and one chunk recorded against an OLD model.

    This is the state a change of embedding model leaves behind, within one provider and one
    width (D-131): rows that look healthy and whose vectors are no longer comparable with
    anything the new model produces.
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


# --- A database keeps its provider (D-131) --------------------------------------------------
#
# --resize-column (D-117) was removed on 14 November 2026, and --provider no longer overrides
# AI_PROVIDER: it is a confirmation, and any provider but the configured one is refused.


@pytest.mark.django_db
def test_resize_column_is_gone(indexed_document):
    with pytest.raises(CommandError, match="unrecognized arguments"):
        call_command("reindex", "--resize-column", database_name())

    assert column_type() == f"vector({settings.EMBEDDING_DIMENSION})"
    assert ContentChunk.objects.get(source_id=indexed_document.id).embedding_model == STALE_MODEL


@pytest.mark.django_db
def test_a_column_of_another_width_is_refused_and_a_new_database_is_named(document):
    """A database set up for the other provider: the setting and the provider agree on one width,
    and the stored chunk column has the other provider's. Nothing moves the database across, and
    nothing is touched. Postgres DDL is transactional, so the column is back at
    EMBEDDING_DIMENSION when the test's transaction rolls back; the table has no row to convert."""
    ExtractedContent.objects.create(document=document, extracted_text=ENOUGH_TEXT)
    other = next(width for width in EMBEDDING_DIMENSION_BY_PROVIDER.values() if width != settings.EMBEDDING_DIMENSION)
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE content_chunks ALTER COLUMN embedding TYPE vector({other})")

    with pytest.raises(CommandError) as raised:
        call_command("reindex")

    message = str(raised.value)
    assert f"vector({other})" in message and f"embeds at {settings.EMBEDDING_DIMENSION}" in message
    assert "D-131" in message and "set up a new one" in message
    assert "--resize-column" not in message
    assert column_type() == f"vector({other})"
    assert not ContentChunk.objects.filter(source_id=document.id).exists()


@pytest.mark.django_db
def test_a_width_that_disagrees_with_the_provider_is_refused(indexed_document, monkeypatch):
    """ai.E004's condition, for a caller that skips the checks: an EMBEDDING_DIMENSION that is not
    the provider's is refused before the provider is asked, even when the provider and the stored
    column would agree with it."""
    install(monkeypatch, StubAIService(dimension=NEW_WIDTH))

    with override_settings(EMBEDDING_DIMENSION=NEW_WIDTH), pytest.raises(CommandError) as raised:
        call_command("reindex")

    message = str(raised.value)
    assert f"EMBEDDING_DIMENSION is {NEW_WIDTH}" in message and "D-131" in message
    assert ContentChunk.objects.get(source_id=indexed_document.id).embedding_model == STALE_MODEL


@pytest.mark.django_db
def test_another_provider_is_refused_and_the_setting_is_left_alone(indexed_document):
    """Until 14 November 2026 --provider overrode AI_PROVIDER for the run, which is how a database
    was moved to another provider. Now it is refused before the provider is even asked."""
    configured = settings.AI_PROVIDER
    other = next(name for name in VALID_PROVIDERS if name != configured)

    with pytest.raises(CommandError) as raised:
        call_command("reindex", "--provider", other)

    message = str(raised.value)
    assert repr(other) in message and repr(configured) in message and "D-131" in message
    assert settings.AI_PROVIDER == configured
    chunk = ContentChunk.objects.get(source_id=indexed_document.id)
    assert chunk.embedding_model == STALE_MODEL


@pytest.mark.django_db
def test_naming_the_configured_provider_is_an_ordinary_reindex(indexed_document):
    call_command("reindex", "--provider", settings.AI_PROVIDER)

    chunks = ContentChunk.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=indexed_document.id)
    assert chunks.exists()
    assert {chunk.embedding_model for chunk in chunks} == {STUB_EMBEDDING_MODEL}
