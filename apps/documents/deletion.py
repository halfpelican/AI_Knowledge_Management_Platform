"""FR-15's document deletion: the document and everything derived from it, in one transaction.

FR-15: "deleting a document also removes its extracted content, embeddings and tag links, so
that deleted material cannot subsequently be surfaced through search." ``document.delete()``
alone does not do that. ``ExtractedContent`` goes with it through its foreign key, but
``ContentChunk`` and ``ContentTag`` reference their source by ``source_type`` and ``source_id``
with no foreign key (D-07), so they would survive the delete: the chunks still embedded, still
stamped and still retrievable, and the deleted document still answering questions. This module
deletes them explicitly, in the same transaction as the document (CLAUDE.md invariant 9, D-73).

**The caller has already decided that this delete may happen.** ``delete_document`` takes a
document the view resolved through ``scoped_documents`` (404 outside scope) and checked
``manage_documents`` against (403), in that order (D-46, D-73). Nothing here re-checks either,
and nothing here may be reached from a route by any other path.

**Why this lives outside ``apps/api``.** It reads the ``Document`` and ``ContentChunk``
managers directly, by primary key and by source, which is right for a write against a row
already resolved through the scope and is exactly what
``apps/api/tests/test_source_rows_fail_closed.py`` forbids in request-serving packages. Keeping
it here keeps that scan strict for every read a route makes, as ``apps/ingestion`` does for
reprocess and re-index.
"""

from django.db import transaction

from apps.core.constants import SOURCE_TYPES
from apps.documents.models import ContentChunk, ContentTag, Document

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]


def delete_document(document: Document) -> None:
    """Delete ``document``, its extracted content, its chunks and its tag links, atomically.

    In one ``transaction.atomic()`` block:

    1. **The document row is locked first**, with ``select_for_update``, as
       ``reprocess_document`` and ``manage.py reindex`` lock it before they touch its chunks.
       A reprocess in flight holds that lock while it deletes the old chunks and writes new
       ones; without waiting for it, the chunk delete below would see only the chunks
       committed before the reprocess began, and the reprocess would then commit fresh chunks
       for a document that no longer exists, embedded and retrievable. Waiting means the
       delete runs after the reprocess commits and removes what it wrote.
    2. **Its ``ContentChunk`` rows**, by ``source_type`` and ``source_id``. A queryset
       ``delete()``, so Django's ``on_delete`` applies to ``AnswerCitation.chunk``: SET_NULL,
       and the FR-12 record of what was answered survives with ``chunk_uuid`` naming what was
       cited and no text (D-67).
    3. **Its ``ContentTag`` rows**, by the same key. The ``Tag`` rows they pointed at are a
       vocabulary and stay. FR-15's facets never read ``Tag`` on its own (D-72), so a tag left with
       no links is never a facet value. FR-10's ``tag_options`` and classification prompt do read
       the vocabulary: a tag that is not grown stays offered to every reader whatever this deletion
       removes, and a grown tag left without a source every audience role reads is offered nowhere
       (``tag_scheme``; D-105's dated note of 10 November 2026, night: the security review).
       Deleting a document therefore never makes a restricted value appear anywhere.
    4. **The document**, and with it its ``ExtractedContent`` rows, through their CASCADE
       foreign key.

    **The stored original is removed in ``transaction.on_commit``**, so a delete that rolls
    back, here or in any transaction that encloses this one, keeps the file its surviving row
    points at. Registered with ``robust=True``: once the rows are committed the document is
    deleted, and a file the storage could not remove (held open by another process, say) is
    logged by Django rather than turned into an error for a request that has already
    succeeded. ``config/urls.py`` serves nothing outside ``/api/``, so a file left behind is
    unreachable; it is recorded rather than fixed here.

    A document deleted by a concurrent request between the caller's lookup and the lock is
    tolerated: its chunks and tag links are deleted by key, which is idempotent, and there is
    then no row and no file left to remove.
    """
    with transaction.atomic():
        locked = Document.objects.select_for_update().filter(pk=document.pk).first()
        ContentChunk.objects.filter(
            source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk
        ).delete()
        ContentTag.objects.filter(
            source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk
        ).delete()
        if locked is None:
            return
        stored_name = locked.file_path.name
        storage = locked.file_path.storage
        locked.delete()
        if stored_name:
            transaction.on_commit(lambda: storage.delete(stored_name), robust=True)
