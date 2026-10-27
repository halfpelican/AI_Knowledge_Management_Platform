"""FR-08 document ingestion: the proposal's section 7.8 ``ingestAndIndexDocument()``.

Validation — the contribute permission, the file signature, the size ceiling, the
title and the duplicate check — has already run in the view, in the order section 7.2
``validateUpload()`` fixes, so everything here is work on a file already known to be
acceptable.

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

from apps.core.constants import (
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_INDEXED,
    DOCUMENT_INDEXING_FAILED,
    DOCUMENT_INSUFFICIENT_CONTENT,
    DOCUMENT_PARTIALLY_INDEXED,
    DOCUMENT_TOO_LARGE_TO_INDEX,
    MAXIMUM_CHUNKS_PER_SOURCE,
    MINIMUM_CONTENT_LENGTH,
)
from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.ingestion.signatures import compute_content_hash
from apps.ingestion.chunking import (
    chunk_count_for_tokens,
    length_in_tokens,
    split_into_overlapping_chunks,
)
from apps.ingestion.embedding import DOCUMENT_SOURCE_TYPE, embed_and_store_chunks
from apps.ingestion.errors import ExtractionError, TooLargeToExtractError
from apps.ingestion.extraction import extract_plain_text

# Section 7.8 message 43: RETURN response(422, "No readable text could be
# extracted"). FR-08 Responses: "422 Unprocessable Entity where no text can be
# extracted."
NO_TEXT_EXTRACTED_MESSAGE = (
    "The document was stored, but no readable text could be extracted from it."
)

# Section 7.8 lines 46-53: text below MINIMUM_CONTENT_LENGTH is marked and is not
# submitted for embedding. Same 422 as above: the file is kept, nothing is indexed.
INSUFFICIENT_CONTENT_MESSAGE = (
    "The document was stored but contains too little text to index."
)

# Section 7.8 lines 89-91: every chunk failed to embed.
INDEXING_FAILED_MESSAGE = "The document could not be indexed."

# MAXIMUM_CHUNKS_PER_SOURCE exceeded (Stage 4 item 12a). Its own status as well as its own
# message since item 12b — DOCUMENT_TOO_LARGE_TO_INDEX, because this document was refused
# before anything was attempted, which is not what "Indexing failed" means. See the guard in
# _run_pipeline.
TOO_MANY_CHUNKS_MESSAGE = (
    "The document was stored, but it holds too much text to index in one request."
)

# What happened to the document when a PDF met one of D-81's extraction bounds. The bound's
# own sentence follows it (``pdf_bound_detail``): extraction.py's limit sentences say what the
# file met and whether splitting it would help, and nothing about storage, because FR-09's
# file path meets the same bounds having stored nothing (``MeetingsView._transcript_from``).
PDF_BOUND_STORED_CLAUSE = "The document was stored but not indexed."


def pdf_bound_detail(limit_message: str) -> str:
    """The FR-08 detail for a D-81 refusal: the stored clause, then the bound's sentence."""
    return f"{PDF_BOUND_STORED_CLAUSE} {limit_message}"


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
    """Store the original, extract its text, chunk it, embed it and index it.

    The whole of section 7.8 in one transaction: store, extract, guard on
    MINIMUM_CONTENT_LENGTH, chunk, embed, and set the status the outcome earned.

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

            return _run_pipeline(document, uploaded_file)
    except Exception:
        # The database has rolled back; the file has not, because a filesystem is
        # not transactional. Remove it, or an abandoned ingestion leaves bytes under
        # MEDIA_ROOT that no row references and nothing will ever clean up.
        if stored_name:
            document.file_path.storage.delete(stored_name)
        raise


def reprocess_document(document: Document) -> IngestionOutcome:
    """Re-run ingestion against the original already stored under MEDIA_ROOT (D-32).

    This is what FR-08's "Processing failed. Please try again" action calls. It does
    NOT re-upload: invariant 8 kept the original when the first attempt failed, so
    the bytes are already here, and a re-upload would create a second row per
    attempt — three retries would leave three near-identical entries in FR-15's
    repository list, and the user would have to find the file on disk again to retry
    at all. One document, one row, however many attempts it took.

    Any extracted text and chunks from the previous attempt are removed first, so a
    reprocess replaces its predecessor rather than adding to it. ContentChunks has
    no database foreign key (D-07), so its rows are deleted explicitly here rather
    than by a cascade.

    A successful reprocess restores the content hash the failed attempt released, so
    a document that reaches Indexed is protected by the duplicate check exactly as
    one indexed on the first attempt is. If the same file was uploaded and indexed
    successfully in the meantime, that restore collides and raises IntegrityError,
    which the view answers 409 — the truthful answer, since an indexed copy now
    exists.
    """
    with transaction.atomic():
        # Locked for the duration: two retries of the same document would otherwise
        # both delete the other's chunks and both write their own.
        document = Document.objects.select_for_update().get(pk=document.pk)
        ExtractedContent.objects.filter(document=document).delete()
        ContentChunk.objects.filter(
            source_type=DOCUMENT_SOURCE_TYPE, source_id=document.id
        ).delete()

        with document.file_path.open("rb") as stored:
            outcome = _run_pipeline(document, stored)
            if outcome.http_status == 201:
                document.content_hash = compute_content_hash(stored)
                document.save(update_fields=["content_hash"])
    return outcome


def _run_pipeline(document: Document, source_file) -> IngestionOutcome:
    """Extract, guard, chunk, embed, and set the status. Section 7.8, lines 37-100.

    Shared by a first ingestion and by a reprocess, so the two cannot diverge: a
    retry that indexed by a different route from the original upload would be a
    second pipeline to keep correct. The caller owns the transaction; everything
    written here commits with the document row or not at all (NFR-21).
    """
    try:
        text = _extract(source_file, document.file_type)
    except TooLargeToExtractError as exception:
        # A PDF crossed one of D-81's per-stream (decoded or stored), page or operator
        # bounds. Like the chunk-ceiling case below it is "Too large to index", not
        # "Extraction failed": the PDF is readable and a retry fails at the same bound every
        # time (D-51, D-81 item 5). Each bound carries its own sentence, so the uploader
        # learns whether splitting the file would help, and this route adds that the
        # document was stored. Decided before any ExtractedContent row or embed call, with
        # the original kept — the same shape as the chunk-ceiling refusal.
        return _decided_failure(
            document, DOCUMENT_TOO_LARGE_TO_INDEX, pdf_bound_detail(exception.limit_message)
        )
    if not text:
        # Section 7.8 lines 41-44. The original is kept and remains downloadable;
        # only its text is missing. A scanned image-only PDF reaches here, and so
        # does a file whose parser failed.
        return _decided_failure(document, DOCUMENT_EXTRACTION_FAILED, NO_TEXT_EXTRACTED_MESSAGE)

    if length_in_tokens(text) < MINIMUM_CONTENT_LENGTH:
        # Section 7.8 lines 46-53. A fragment embeds into an unreliable vector that
        # matches unpredictably and pollutes every later search, so it is marked and
        # never submitted for embedding.
        #
        # The return is BEFORE line 58's CREATE ExtractedContent, so an
        # insufficient-content document gets no extracted_content row at all. That is
        # the pseudocode's own order and it is deliberate: the text is below the
        # threshold at which it is useful to search or to ground an answer, and the
        # file itself is kept and stays downloadable, so nothing is lost that
        # re-parsing could not produce again.
        return _decided_failure(
            document, DOCUMENT_INSUFFICIENT_CONTENT, INSUFFICIENT_CONTENT_MESSAGE
        )

    if chunk_count_for_tokens(length_in_tokens(text)) > MAXIMUM_CHUNKS_PER_SOURCE:
        # MAXIMUM_CHUNKS_PER_SOURCE (Stage 4 item 12a). Every chunk is a separate,
        # sequential NPU embed call inside the transaction below, in one synchronous
        # request: a 50 MB text file extrapolates to ~23,300 of them, which Objective
        # 02's "20 documents and a 20-page file in under 60 seconds" does not survive.
        #
        # **Decided BEFORE any cost is paid.** No embed call, no ContentChunks row, and
        # deliberately no ExtractedContent row either — there is nothing that would read
        # a 50 MB text column for a document with no chunks (``manage.py reindex``
        # rebuilds from it and would otherwise re-embed past the cap outside a request),
        # and returning here mirrors the insufficient-content branch's own order above.
        # The ORIGINAL FILE IS KEPT and stays downloadable: CLAUDE.md invariant 8 says a
        # failed AI step never discards the source, and this is a refusal to run one.
        #
        # **"Too large to index", its own status value since Stage 4 item 12b.** Item 12a
        # put this outcome on "Indexing failed", which means "attempted, and every chunk
        # failed to embed" — and nothing was attempted here. The vocabulary already
        # separated refused-before-attempting ("Insufficient content") from
        # attempted-and-failed ("Indexing failed"); this condition was the first of the
        # former kind with no term of its own, so the seventh value completes that
        # distinction rather than inventing one (apps/core/constants.py argues it,
        # documents migration 0007 carries it).
        #
        # The overload was user-visible, not merely untidy: FR-08's interface offers
        # "Processing failed. Please try again" against a document that did not index, and
        # a reprocess of an over-cap document fails identically every time because nothing
        # about the file has changed — and D-32's retry re-runs extraction and chunking in
        # full before failing at the identical point. FR-08's retry affordance is therefore
        # suppressed for this status — DONE, 27 September 2026: canReprocess() refuses it and
        # the row carries a sentence explaining the absent control instead of a button that
        # cannot honour it (finishing-pass item 2).
        #
        # 422 either way: docs/api-contract.md already gives that code to "stored but could
        # not be indexed", and the message distinguishes this from the embedding failure.
        return _decided_failure(
            document, DOCUMENT_TOO_LARGE_TO_INDEX, TOO_MANY_CHUNKS_MESSAGE
        )

    # Stored separately from the original so that search and AI processing never
    # require the document to be parsed a second time (FR-08, D-05).
    ExtractedContent.objects.create(document=document, extracted_text=text)

    chunks = split_into_overlapping_chunks(text)
    failed_chunk_count = embed_and_store_chunks(
        chunks=chunks,
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        # Stamped from the document itself, not from an argument, so the chunks
        # carry what the stored row says (D-17).
        visible_to_roles=document.visible_to_roles,
        # Goes into the embedding model's document task prefix, not into any column.
        title=document.title,
    )

    # Section 7.8 lines 89-96. All three are decided outcomes, committed with the
    # status that names them; none is a half-written record (D-28).
    if failed_chunk_count and failed_chunk_count == len(chunks):
        return _decided_failure(document, DOCUMENT_INDEXING_FAILED, INDEXING_FAILED_MESSAGE)
    document.status = DOCUMENT_PARTIALLY_INDEXED if failed_chunk_count else DOCUMENT_INDEXED
    document.save(update_fields=["status"])
    return IngestionOutcome(document, 201)


def _decided_failure(document: Document, status: str, detail: str) -> IngestionOutcome:
    """Commit a failure the pipeline decided, and release the duplicate slot.

    The row is kept, carrying the status that says why it is not indexed (CLAUDE.md
    invariant 8, NFR-20). The content hash is cleared, because a failed ingestion
    must not reserve the duplicate check against a document that never indexed:
    while it did, FR-08's "Please try again" action was answered 409 by section
    7.2's duplicate rule and could never succeed (D-32). The column is nullable and
    Postgres permits many NULLs under a unique constraint, so several failed
    attempts at the same file coexist. A successful reprocess restores the hash.
    """
    document.status = status
    document.content_hash = None
    document.save(update_fields=["status", "content_hash"])
    return IngestionOutcome(document, 422, detail)


def _extract(uploaded_file, file_format: str) -> str:
    """Extracted text, or "" where the parser could not read the file.

    ``ExtractionError`` and "the file genuinely holds no text" are the same outcome
    for the caller — there is nothing to index — and FR-08 gives them one response
    code. They are not the same thing to whoever is diagnosing it later, which is
    what the exception message is for; both land on the "Extraction failed" status.

    ``TooLargeToExtractError`` is an ExtractionError subclass but a DIFFERENT outcome:
    the file is readable and was refused by a D-81 bound, so it must land on "Too large
    to index", not "Extraction failed". It is re-raised here, caught in ``_run_pipeline``,
    which is why the narrower class is listed first.
    """
    try:
        return extract_plain_text(uploaded_file, file_format)
    except TooLargeToExtractError:
        raise
    except ExtractionError:
        return ""
