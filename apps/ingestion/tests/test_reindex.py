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
from django.db import connection
from django.test import override_settings

from apps.ai.testing import STUB_EMBEDDING_MODEL, StubAIService
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    DOCUMENT_INDEXING_FAILED,
    EMPLOYEE_ROLE_NAME,
    MEETING_INDEXED,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, ExtractedContent
from apps.ingestion.management.commands.reindex import PROBE_TEXT
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install
from apps.ingestion.tests.builders import words
from apps.retrieval.models import AnswerCitation, QueryLog

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES

# Comfortably above MINIMUM_CONTENT_LENGTH so nothing is rejected as a fragment.
ENOUGH_TEXT = words(200)
STALE_MODEL = "some-older-embedding-model"
# A width the test database's column was not built at: 1024 when the suite runs at
# FLM's 768, which is the Voyage case D-117 exists for.
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
    """The connected database's name, which is what --resize-column must be given."""
    return connection.settings_dict["NAME"]


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


# --- A new width: --resize-column (D-117) ------------------------------------------------
#
# Each test changes the width inside its own transaction. Postgres DDL is transactional,
# so the column is back at EMBEDDING_DIMENSION once the test's transaction rolls back.


@pytest.mark.django_db
def test_a_column_of_another_width_is_refused_until_resize_column_names_the_database(
    indexed_document, monkeypatch
):
    """The restored-snapshot case: the setting says the new width, the column does not.

    migrate cannot resize it, so the command must not tell anyone to try. It names the
    flag and the database, and touches nothing.
    """
    install(monkeypatch, StubAIService(dimension=NEW_WIDTH))

    with override_settings(EMBEDDING_DIMENSION=NEW_WIDTH), pytest.raises(CommandError) as raised:
        call_command("reindex")

    message = str(raised.value)
    assert f"--resize-column {database_name()}" in message
    assert "migrate cannot change it" in message
    assert column_type() == f"vector({settings.EMBEDDING_DIMENSION})"
    chunk = ContentChunk.objects.get(source_id=indexed_document.id)
    assert chunk.embedding_model == STALE_MODEL


@pytest.mark.django_db
def test_resize_column_deletes_every_chunk_resizes_and_rebuilds(
    indexed_document, monkeypatch, capsys
):
    install(monkeypatch, StubAIService(dimension=NEW_WIDTH))

    with override_settings(EMBEDDING_DIMENSION=NEW_WIDTH):
        call_command("reindex", "--resize-column", database_name())
        assert column_type() == f"vector({NEW_WIDTH})"

    chunks = ContentChunk.objects.filter(source_id=indexed_document.id)
    assert chunks.exists()
    assert not chunks.filter(embedding_model=STALE_MODEL).exists()
    assert {chunk.embedding_dimension for chunk in chunks} == {NEW_WIDTH}
    assert {len(chunk.embedding) for chunk in chunks} == {NEW_WIDTH}
    indexed_document.refresh_from_db()
    assert indexed_document.status == DOCUMENT_INDEXED
    output = capsys.readouterr().out
    assert f"from vector({settings.EMBEDDING_DIMENSION}) to vector({NEW_WIDTH})" in output


@pytest.mark.django_db
def test_resize_column_keeps_each_citation_with_its_chunk_nulled(
    indexed_document, employee, monkeypatch
):
    """D-67: deleting every chunk sets each citation's chunk to null and keeps its identifier.

    This is why --resize-column takes the database's name. It is also the case where
    Postgres refuses the ALTER while the delete's deferred foreign-key checks are still
    pending, which is what the command's check_constraints() call clears.
    """
    stale = ContentChunk.objects.get(source_id=indexed_document.id)
    query = QueryLog.objects.create(
        user=employee,
        question="How much annual leave do I get?",
        answered=True,
        answer_text="Twenty days.",
        no_answer_reason=None,
    )
    citation = AnswerCitation.objects.create(
        query=query, chunk=stale, chunk_uuid=stale.id, statement_text="Twenty days.", position=1
    )
    install(monkeypatch, StubAIService(dimension=NEW_WIDTH))

    with override_settings(EMBEDDING_DIMENSION=NEW_WIDTH):
        call_command("reindex", "--resize-column", database_name())

    citation.refresh_from_db()
    assert citation.chunk is None
    assert citation.chunk_uuid == stale.id
    assert column_type() == f"vector({NEW_WIDTH})"


@pytest.mark.django_db
@pytest.mark.parametrize("width", ["the new one", "the stored one"])
def test_resize_column_refuses_a_name_that_is_not_the_connected_database(
    indexed_document, monkeypatch, width
):
    """The confirmation is what keeps the baseline and alpha databases safe (D-117).

    A wrong name is refused even when no resize is needed: the caller believes they are
    connected somewhere else, and an ordinary re-index nulls citations too.
    """
    dimension = NEW_WIDTH if width == "the new one" else settings.EMBEDDING_DIMENSION
    install(monkeypatch, StubAIService(dimension=dimension))

    with override_settings(EMBEDDING_DIMENSION=dimension), pytest.raises(
        CommandError, match="connected to"
    ):
        call_command("reindex", "--resize-column", "kmp_demo_20261101")

    assert column_type() == f"vector({settings.EMBEDDING_DIMENSION})"
    chunk = ContentChunk.objects.get(source_id=indexed_document.id)
    assert chunk.embedding_model == STALE_MODEL


@pytest.mark.django_db
def test_resize_column_with_dry_run_changes_nothing(indexed_document, monkeypatch, capsys):
    install(monkeypatch, StubAIService(dimension=NEW_WIDTH))

    with override_settings(EMBEDDING_DIMENSION=NEW_WIDTH):
        call_command("reindex", "--dry-run", "--resize-column", database_name())

    assert column_type() == f"vector({settings.EMBEDDING_DIMENSION})"
    chunk = ContentChunk.objects.get(source_id=indexed_document.id)
    assert chunk.embedding_model == STALE_MODEL
    output = capsys.readouterr().out
    assert (
        f"would delete 1 chunk(s) and resize the column from "
        f"vector({settings.EMBEDDING_DIMENSION}) to vector({NEW_WIDTH})"
    ) in output


@pytest.mark.django_db
def test_resize_column_on_a_column_already_that_wide_is_an_ordinary_reindex(
    indexed_document, capsys
):
    call_command("reindex", "--resize-column", database_name())

    assert f"already vector({settings.EMBEDDING_DIMENSION}); nothing to resize" in (
        capsys.readouterr().out
    )
    chunks = ContentChunk.objects.filter(source_id=indexed_document.id)
    assert chunks.exists()
    assert not chunks.filter(embedding_model=STALE_MODEL).exists()


@pytest.mark.django_db
def test_a_source_that_fails_after_the_resize_is_marked_failed(
    indexed_document, monkeypatch, capsys
):
    """Its old chunks were deleted with the rest, so "Indexed" would be untrue.

    Without the resize, a failed source keeps its old chunks and status, because its
    transaction rolls back. After it, there is nothing to roll back to.
    """
    install(
        monkeypatch,
        ScriptedEmbedService(
            dimension=NEW_WIDTH,
            failures=1,
            # The width probe succeeds; the document's own chunks then fail with an
            # error the pipeline did not decide, which fails the whole source.
            should_fail=lambda text: text != PROBE_TEXT,
            error=RuntimeError("unexpected provider error"),
        ),
    )

    with override_settings(EMBEDDING_DIMENSION=NEW_WIDTH):
        call_command("reindex", "--resize-column", database_name())

    indexed_document.refresh_from_db()
    assert indexed_document.status == DOCUMENT_INDEXING_FAILED
    assert not ContentChunk.objects.filter(source_id=indexed_document.id).exists()
    assert "marked failed" in capsys.readouterr().out
