"""``python manage.py reindex --provider <name>`` — rebuild every stored vector.

Promised in CLAUDE.md section 4, docs/ai-provider.md section 4 and the ai.E001
hint in apps/ai/checks.py, and referenced by apps/ingestion/embedding.py, but not
built until now. Switching provider or embedding model is a full re-index event:
vectors from different models are not comparable yet still return a plausible
similarity score, so a mixed table is silent corruption rather than an error
(risk R10). This command is what makes that switch a supported operation instead
of an instruction nobody can follow.

It re-embeds from the text already stored — ExtractedContent for a document, the
transcript for a meeting — and never re-reads an original or re-parses a file.
Extraction is not what changed; the embedding model is. A document whose text was
never extracted has no chunks to rebuild and is reported as skipped, not failed.

Each source is rebuilt in its own transaction, so its chunks and its status commit
together or not at all (NFR-21, CLAUDE.md invariant 9). One source failing leaves
the sources already rebuilt committed and the rest untouched; the command reports
what it did rather than rolling the whole corpus back, because a half-finished
re-index that names its own extent is recoverable and an all-or-nothing one over
thousands of chunks is not.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

import apps.ai
from apps.ai.base import ProviderUnavailable
from apps.core.constants import (
    DOCUMENT_INDEXED,
    DOCUMENT_INDEXING_FAILED,
    DOCUMENT_PARTIALLY_INDEXED,
    MEETING_INDEXED,
    MEETING_PROCESSING_FAILED,
)
from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.ingestion.chunking import split_into_overlapping_chunks
from apps.ingestion.embedding import (
    DOCUMENT_SOURCE_TYPE,
    MEETING_SOURCE_TYPE,
    embed_and_store_chunks,
)
from apps.meetings.models import Meeting

PROBE_TEXT = "embedding dimension probe"
VALID_PROVIDERS = ("flm", "anthropic")


class Command(BaseCommand):
    help = "Re-embed and re-index every stored chunk with the configured AI provider."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            choices=VALID_PROVIDERS,
            help=(
                "provider to re-index with; overrides AI_PROVIDER for this run. "
                f"Defaults to the configured provider ({settings.AI_PROVIDER!r})."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report what would be rebuilt and leave every row untouched",
        )

    def handle(self, *args, **options):
        provider = options["provider"] or settings.AI_PROVIDER
        dry_run = options["dry_run"]

        # get_ai_service() reads settings.AI_PROVIDER at call time, so assigning it
        # here is what makes --provider take effect for the whole run, including
        # inside embed_and_store_chunks().
        settings.AI_PROVIDER = provider
        service = apps.ai.get_ai_service()

        self._guard_dimension(service, provider)

        documents = list(Document.objects.order_by("uploaded_at"))
        meetings = list(Meeting.objects.order_by("created_at"))
        self.stdout.write(
            f"Re-indexing with provider {provider!r}: "
            f"{len(documents)} document(s), {len(meetings)} meeting(s), "
            f"{ContentChunk.objects.count()} existing chunk(s)."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: nothing will be written."))

        rebuilt = skipped = failed = 0
        for document in documents:
            outcome = self._reindex_document(document, dry_run)
            rebuilt += outcome == "rebuilt"
            skipped += outcome == "skipped"
            failed += outcome == "failed"
        for meeting in meetings:
            outcome = self._reindex_meeting(meeting, dry_run)
            rebuilt += outcome == "rebuilt"
            skipped += outcome == "skipped"
            failed += outcome == "failed"

        summary = f"Done: {rebuilt} rebuilt, {skipped} skipped, {failed} failed."
        self.stdout.write(self.style.ERROR(summary) if failed else self.style.SUCCESS(summary))
        if not dry_run:
            self.stdout.write(f"Chunks now stored: {ContentChunk.objects.count()}.")

    def _guard_dimension(self, service, provider):
        """Refuse to start if the provider's width is not the column's width.

        The pgvector column is sized from settings.EMBEDDING_DIMENSION (D-03, D-08),
        so a provider returning a different width cannot be stored at all. Checked
        once here, against a probe, rather than discovered part-way through the
        corpus as an opaque database error on some arbitrary chunk.
        """
        try:
            result = service.embed([PROBE_TEXT])
        except ProviderUnavailable as exc:
            raise CommandError(f"Provider {provider!r} is unavailable: {exc}") from exc

        expected = settings.EMBEDDING_DIMENSION
        if result.dimension != expected:
            raise CommandError(
                f"Provider {provider!r} embeds at {result.dimension} dimensions but "
                f"EMBEDDING_DIMENSION is {expected}, which is the width of the stored "
                f"vector column. Set EMBEDDING_DIMENSION to {result.dimension}, run "
                f"makemigrations and migrate to resize the column, then run this "
                f"command again."
            )
        self.stdout.write(
            f"Provider {provider!r} embeds at {result.dimension} dimensions "
            f"with model {result.model!r}; matches EMBEDDING_DIMENSION."
        )

    def _reindex_document(self, document, dry_run):
        extracted = (
            ExtractedContent.objects.filter(document=document).order_by("-extracted_at").first()
        )
        if extracted is None or not extracted.extracted_text:
            # Extraction failed or the text was below MINIMUM_CONTENT_LENGTH, so the
            # document never had chunks. Re-embedding cannot create text that was
            # never extracted; this is a skip, not a failure.
            self.stdout.write(f"  skip  document {document.title!r}: no extracted text")
            return "skipped"

        if dry_run:
            self.stdout.write(f"  would rebuild document {document.title!r}")
            return "rebuilt"

        try:
            with transaction.atomic():
                # Locked for the duration, matching reprocess_document(): two
                # concurrent rebuilds would each delete the other's chunks.
                locked = Document.objects.select_for_update().get(pk=document.pk)
                ContentChunk.objects.filter(
                    source_type=DOCUMENT_SOURCE_TYPE, source_id=locked.id
                ).delete()
                chunks = split_into_overlapping_chunks(extracted.extracted_text)
                failed_chunk_count = embed_and_store_chunks(
                    chunks=chunks,
                    source_type=DOCUMENT_SOURCE_TYPE,
                    source_id=locked.id,
                    # From the document row, so the chunks carry what it says (D-17).
                    visible_to_roles=locked.visible_to_roles,
                )
                # The same three decided outcomes _run_pipeline() sets, so a
                # re-indexed document and a freshly ingested one cannot disagree
                # about what their status means (D-28).
                if failed_chunk_count and failed_chunk_count == len(chunks):
                    locked.status = DOCUMENT_INDEXING_FAILED
                else:
                    locked.status = (
                        DOCUMENT_PARTIALLY_INDEXED if failed_chunk_count else DOCUMENT_INDEXED
                    )
                locked.save(update_fields=["status"])
        except Exception as exc:  # noqa: BLE001 - one source failing must not stop the run
            self.stderr.write(f"  FAIL  document {document.title!r}: {type(exc).__name__}: {exc}")
            return "failed"

        note = f" ({failed_chunk_count} chunk(s) failed)" if failed_chunk_count else ""
        self.stdout.write(
            f"  ok    document {document.title!r}: {len(chunks)} chunk(s), "
            f"{locked.status}{note}"
        )
        return "rebuilt"

    def _reindex_meeting(self, meeting, dry_run):
        if not meeting.transcript_text:
            self.stdout.write(f"  skip  meeting {meeting.title!r}: no transcript")
            return "skipped"

        if dry_run:
            self.stdout.write(f"  would rebuild meeting {meeting.title!r}")
            return "rebuilt"

        try:
            with transaction.atomic():
                locked = Meeting.objects.select_for_update().get(pk=meeting.pk)
                ContentChunk.objects.filter(
                    source_type=MEETING_SOURCE_TYPE, source_id=locked.id
                ).delete()
                chunks = split_into_overlapping_chunks(locked.transcript_text)
                failed_chunk_count = embed_and_store_chunks(
                    chunks=chunks,
                    source_type=MEETING_SOURCE_TYPE,
                    source_id=locked.id,
                    visible_to_roles=locked.visible_to_roles,
                )
                # MEETING_STATUS_VALUES has no "Partially indexed" counterpart, so a
                # partly indexed meeting is Indexed — the asymmetry recorded in
                # apps/ingestion/meetings.py (D-28), mirrored rather than repaired.
                locked.status = (
                    MEETING_PROCESSING_FAILED
                    if failed_chunk_count and failed_chunk_count == len(chunks)
                    else MEETING_INDEXED
                )
                locked.save(update_fields=["status"])
        except Exception as exc:  # noqa: BLE001 - one source failing must not stop the run
            self.stderr.write(f"  FAIL  meeting {meeting.title!r}: {type(exc).__name__}: {exc}")
            return "failed"

        note = f" ({failed_chunk_count} chunk(s) failed)" if failed_chunk_count else ""
        self.stdout.write(
            f"  ok    meeting {meeting.title!r}: {len(chunks)} chunk(s), {locked.status}{note}"
        )
        return "rebuilt"
