"""FR-08 document ingestion: storing the original and creating its record.

This is the first half of the proposal's section 7.8 ``ingestAndIndexDocument()``.
Validation — the contribute permission, the file signature, the size ceiling, the
title and the duplicate check — has already run in the view, in the order section
7.2 ``validateUpload()`` fixes, so everything here is work on a file already known
to be acceptable.

Extraction, chunking and embedding are the later items of this stage and are not
here yet.

Two rules govern the transaction, and they are the same rule seen from two sides
(CLAUDE.md invariant 9, NFR-21):

- An *outcome the pipeline decided* — insufficient content, a failed extraction, a
  partly embedded document — is committed, with the status that says so. Section
  7.8 is explicit that a record is created before extraction begins "so that a
  failure part-way through leaves a visible record carrying a status rather than
  nothing at all".
- An *unexpected* failure commits nothing. The row, the extracted text and the
  vectors arrive together or not at all, and the stored original is removed on the
  way out, since the filesystem does not roll back with the database.
"""

from django.db import transaction

from apps.documents.models import Document


def store_document(
    *,
    uploaded_file,
    file_format: str,
    content_hash: str,
    title: str,
    department: str,
    visible_to_roles: list[str],
    uploaded_by,
) -> Document:
    """Write the original beneath MEDIA_ROOT and create its Documents row.

    The record is created with the default status, ``Processing`` (D-28), which is
    what section 7.8 writes before extraction begins. The original file and the
    extracted plain text are stored separately (FR-08, D-05) so that retrieval never
    re-parses the original; ``extracted_content`` is written by a later item.
    """
    stored_name = None
    document = Document(
        title=title,
        file_type=file_format,
        uploaded_by=uploaded_by,
        department=department,
        visible_to_roles=visible_to_roles,
        content_hash=content_hash,
        file_size_bytes=uploaded_file.size,
    )
    try:
        with transaction.atomic():
            # save=False: the field is populated and the bytes are written, but the
            # row is inserted once, below, rather than twice.
            document.file_path.save(uploaded_file.name, uploaded_file, save=False)
            stored_name = document.file_path.name
            document.save()
    except Exception:
        # The database has rolled back; the file has not, because a filesystem is
        # not transactional. Remove it, or an abandoned ingestion leaves bytes under
        # MEDIA_ROOT that no row references and nothing will ever clean up.
        if stored_name:
            document.file_path.storage.delete(stored_name)
        raise
    return document
