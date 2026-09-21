"""FR-08 document ingestion: the proposal's section 7.8 ``ingestAndIndexDocument()``.

Validation — the contribute permission, the file signature, the size ceiling, the
title and the duplicate check — has already run in the view, in the order section 7.2
``validateUpload()`` fixes, so everything here is work on a file already known to be
acceptable.

Chunking and embedding are later items of this stage and are not here yet.

Two rules govern the transaction, and they are one rule seen from two sides
(CLAUDE.md invariant 9, NFR-21):

- An **outcome the pipeline decided** is committed, with the status that says so.
  Section 7.8 creates the record before extraction begins "so that a failure
  part-way through leaves a visible record carrying a status rather than nothing at
  all", and CLAUDE.md invariant 8 requires that a failed AI step never discard the
  source. A document marked "Extraction failed" is a complete record of a decision,
  not a half-written one.
- An **unexpected** failure commits nothing. The row, the extracted text and the
  vectors arrive together or not at all, and the stored original is removed on the
  way out, because a filesystem does not roll back with the database.
"""

from dataclasses import dataclass

from django.db import transaction

from apps.core.constants import DOCUMENT_EXTRACTION_FAILED
from apps.documents.models import Document, ExtractedContent
from apps.ingestion.extraction import extract_plain_text

# Section 7.8 message 43: RETURN response(422, "No readable text could be
# extracted"). FR-08 Responses: "422 Unprocessable Entity where no text can be
# extracted."
NO_TEXT_EXTRACTED_MESSAGE = (
    "The document was stored, but no readable text could be extracted from it."
)


@dataclass(frozen=True)
class IngestionOutcome:
    """What ingestion decided, and the status code the view should answer with.

    The document is always present, even on a 422: the file is kept and the record
    carries the status explaining why it is not indexed, which is what makes the
    "Processing failed. Please try again" action in FR-08's interface possible.
    """

    document: Document
    http_status: int
    detail: str = ""


def ingest_and_index_document(
    *,
    uploaded_file,
    file_format: str,
    content_hash: str,
    title: str,
    department: str,
    visible_to_roles: list[str],
    uploaded_by,
) -> IngestionOutcome:
    """Store the original, extract its text, and record both.

    Processing is synchronous, as FR-08 states. ``UnsupportedFormatError`` from the
    extractor is deliberately NOT caught: it means a format reached the parser router
    with no parser behind it, which is a defect in the format table rather than a
    problem with this upload, and section 7.4 wants it loud. It rolls the whole
    ingestion back, as any unexpected failure does.
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

            text = _extract(uploaded_file, file_format)
            if not text:
                # Section 7.8 lines 41-44. The original is kept and remains
                # downloadable; only its text is missing. A scanned image-only PDF
                # reaches here, and so does a file whose parser failed.
                document.status = DOCUMENT_EXTRACTION_FAILED
                document.save(update_fields=["status"])
                return IngestionOutcome(document, 422, NO_TEXT_EXTRACTED_MESSAGE)

            # Stored separately from the original so that search and AI processing
            # never require the document to be parsed a second time (FR-08, D-05).
            ExtractedContent.objects.create(document=document, extracted_text=text)
            return IngestionOutcome(document, 201)
    except Exception:
        # The database has rolled back; the file has not, because a filesystem is
        # not transactional. Remove it, or an abandoned ingestion leaves bytes under
        # MEDIA_ROOT that no row references and nothing will ever clean up.
        if stored_name:
            document.file_path.storage.delete(stored_name)
        raise


def _extract(uploaded_file, file_format: str) -> str:
    """Extracted text, or "" where the parser could not read the file.

    ``ExtractionError`` and "the file genuinely holds no text" are the same outcome
    for the caller — there is nothing to index — and FR-08 gives them one response
    code. They are not the same thing to whoever is diagnosing it later, which is
    what the exception message is for; both land on the "Extraction failed" status.
    """
    from apps.ingestion.errors import ExtractionError

    try:
        return extract_plain_text(uploaded_file, file_format)
    except ExtractionError:
        return ""
