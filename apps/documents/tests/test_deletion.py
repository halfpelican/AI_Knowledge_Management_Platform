"""``apps.documents.deletion.delete_document``: FR-15's delete, below the route (D-73).

``apps/api/tests/test_document_delete.py`` tests the route: who may delete, the 404 before the
403, and what FR-15 promises afterwards. This file tests the function's own guarantees:

- **one transaction** (CLAUDE.md invariant 9): a failure part-way through leaves every row, and a
  delete rolled back by a transaction enclosing it leaves every row too;
- **the file is removed on commit**, so either kind of rollback keeps the file its surviving row
  points at;
- **only this document's derived rows go**: a chunk or tag link is selected by ``source_type``
  AND ``source_id``, since neither has a foreign key (D-07);
- **the document row is locked before its chunks are deleted**, as ``reprocess_document`` and
  ``manage.py reindex`` lock it, so a delete cannot run between a reprocess's chunk delete and
  its chunk insert and leave fresh chunks behind for a document that no longer exists.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.core.constants import EMPLOYEE_ROLE_NAME, PROJECT_DIMENSION, SOURCE_TYPES
from apps.documents.deletion import delete_document
from apps.documents.models import ContentChunk, ContentTag, Document, ExtractedContent, Tag

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
STORED_BYTES = b"The original, as uploaded."


class Boom(Exception):
    pass


def chunk(source_type, source_id):
    return ContentChunk.objects.create(
        source_type=source_type,
        source_id=source_id,
        chunk_index=0,
        chunk_text="A passage.",
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model="stub-embed",
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )


def tag_link(source_type, source_id):
    tag, _ = Tag.objects.get_or_create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    return ContentTag.objects.create(tag=tag, source_type=source_type, source_id=source_id,
                                     applied_by="user", confirmed=True)


@pytest.fixture
def stored(employee):
    """A document with a stored file, extracted text, a chunk and a tag link."""
    document = Document.objects.create(
        title="Escalation policy", file_type="txt", uploaded_by=employee,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    document.file_path.save("escalation.txt", ContentFile(STORED_BYTES), save=True)
    ExtractedContent.objects.create(document=document, extracted_text="The extracted text.")
    chunk(DOCUMENT_SOURCE_TYPE, document.id)
    tag_link(DOCUMENT_SOURCE_TYPE, document.id)
    return document


def remains(document) -> dict:
    return {
        "document": Document.objects.filter(pk=document.pk).exists(),
        "extracted_content": ExtractedContent.objects.filter(document_id=document.pk).exists(),
        "chunks": ContentChunk.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk).exists(),
        "tag_links": ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk).exists(),
    }


ALL_PRESENT = {"document": True, "extracted_content": True, "chunks": True, "tag_links": True}
ALL_GONE = {"document": False, "extracted_content": False, "chunks": False, "tag_links": False}


def test_the_document_and_everything_derived_from_it_is_deleted(stored, django_capture_on_commit_callbacks):
    path = Path(stored.file_path.path)
    assert remains(stored) == ALL_PRESENT and path.read_bytes() == STORED_BYTES  # the premise

    with django_capture_on_commit_callbacks(execute=True):
        delete_document(stored)

    assert remains(stored) == ALL_GONE
    assert not path.exists()


def test_the_file_is_removed_by_the_commit_callback_and_not_before(stored, django_capture_on_commit_callbacks):
    path = Path(stored.file_path.path)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        delete_document(stored)

    assert remains(stored) == ALL_GONE
    assert path.exists()
    [remove_file] = callbacks
    remove_file()
    assert not path.exists()


def test_a_failure_inside_the_delete_rolls_back_every_row_and_keeps_the_file(
    stored, monkeypatch, django_capture_on_commit_callbacks
):
    """Invariant 9. The chunks and tag links are deleted before the document; a failure deleting
    the document must bring them back, or the document would survive with nothing to answer from
    and no tags, and a retried delete would find a half-deleted row."""

    def fail(self, *args, **kwargs):
        # Reached after the chunk and tag deletes inside the transaction.
        assert not ContentChunk.objects.filter(source_id=stored.pk).exists()
        raise Boom

    monkeypatch.setattr(Document, "delete", fail)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(Boom):
            delete_document(stored)

    assert remains(stored) == ALL_PRESENT
    assert callbacks == []
    assert Path(stored.file_path.path).read_bytes() == STORED_BYTES


def test_a_delete_rolled_back_by_an_enclosing_transaction_keeps_the_file(
    stored, django_capture_on_commit_callbacks
):
    """The callback is registered, and then discarded with the transaction that rolled back."""
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(Boom):
            with transaction.atomic():
                delete_document(stored)
                assert remains(stored) == ALL_GONE
                raise Boom

    assert callbacks == []
    assert remains(stored) == ALL_PRESENT
    assert Path(stored.file_path.path).read_bytes() == STORED_BYTES


def test_only_this_documents_rows_are_deleted(stored, employee, django_capture_on_commit_callbacks):
    """By ``source_type`` and ``source_id`` together: a meeting chunk or tag link that happened to
    carry the same identifier, and another document's rows, are untouched."""
    other = Document.objects.create(title="Other", file_type="txt", uploaded_by=employee,
                                    visible_to_roles=[EMPLOYEE_ROLE_NAME])
    ExtractedContent.objects.create(document=other, extracted_text="Other text.")
    chunk(DOCUMENT_SOURCE_TYPE, other.id)
    tag_link(DOCUMENT_SOURCE_TYPE, other.id)
    meeting_chunk = chunk(MEETING_SOURCE_TYPE, stored.id)
    meeting_link = tag_link(MEETING_SOURCE_TYPE, stored.id)

    with django_capture_on_commit_callbacks(execute=True):
        delete_document(stored)

    assert remains(stored) == ALL_GONE
    assert remains(other) == ALL_PRESENT
    assert ContentChunk.objects.filter(pk=meeting_chunk.pk).exists()
    assert ContentTag.objects.filter(pk=meeting_link.pk).exists()
    # The tag itself is vocabulary, and stays while anything links to it, or nothing does.
    assert Tag.objects.filter(tag_name="bridge maintenance").exists()


def test_a_document_with_no_stored_file_registers_no_callback(employee, django_capture_on_commit_callbacks):
    document = Document.objects.create(title="No original", file_type="txt", uploaded_by=employee,
                                       visible_to_roles=[EMPLOYEE_ROLE_NAME])
    chunk(DOCUMENT_SOURCE_TYPE, document.id)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        delete_document(document)

    assert callbacks == []
    assert not Document.objects.filter(pk=document.pk).exists()
    assert not ContentChunk.objects.filter(source_id=document.pk).exists()


def test_a_document_already_deleted_by_a_concurrent_request_is_tolerated(
    stored, django_capture_on_commit_callbacks
):
    """The caller resolved the row, and another delete committed before the lock was taken."""
    stale = Document.objects.get(pk=stored.pk)
    with django_capture_on_commit_callbacks(execute=True):
        delete_document(stored)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        delete_document(stale)

    assert callbacks == []
    assert remains(stored) == ALL_GONE


def test_the_document_row_is_locked_before_its_chunks_are_deleted(stored):
    """The order, read from the SQL: a ``FOR UPDATE`` on the documents row, then the chunk
    delete. Without the lock first, a delete running during a reprocess sees only the chunks
    committed before it, and the reprocess then commits fresh ones for a deleted document."""
    with CaptureQueriesContext(connection) as queries:
        delete_document(stored)

    statements = [query["sql"] for query in queries.captured_queries]
    lock = next(i for i, sql in enumerate(statements)
                if 'FROM "documents"' in sql and "FOR UPDATE" in sql)
    chunk_delete = next(i for i, sql in enumerate(statements)
                        if sql.startswith('DELETE FROM "content_chunks"'))
    assert lock < chunk_delete
