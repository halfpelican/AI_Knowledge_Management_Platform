"""``python manage.py reindex`` — rebuild every stored vector with the database's own provider.

Vectors from different models are not comparable yet still return a plausible similarity
score, so a mixed table is silent corruption rather than an error (risk R10). This command
rebuilds every chunk with the configured provider's model: after a change to chunking, or to
the provider's model at the same width, or to bring rows a startup warning names (ai.W003) up
to date. **It does not change provider.** A database keeps the provider it was set up with
(the user's decision of 13 November 2026, D-131), so a change of provider means a new
database, set up under that provider and ingested again. ``--provider`` is kept as a
confirmation: it must name the configured provider, and any other is refused.

It re-embeds from the text already stored — ExtractedContent for a document, the
transcript for a meeting — and never re-reads an original or re-parses a file.
Extraction is not what changed; the embedding model is. A document whose text was
never extracted has no chunks to rebuild and is reported as skipped, not failed.

**A meeting's AI-generated summary is re-embedded with it** (FR-16, D-125). A Ready
summary is indexed as passages of the meeting itself, so the rebuild that deletes the
meeting's chunks deletes those too, and they are rebuilt in the same transaction from
the summary's stored text. No model is asked to summarise anything: the summary is
not regenerated, only embedded again. If none of its chunks can be embedded, the whole
meeting fails and rolls back, like any other source, so a re-indexed meeting never
loses its summary from search while keeping its transcript.

Each source is rebuilt in its own transaction, so its chunks and its status commit
together or not at all (NFR-21, CLAUDE.md invariant 9). One source failing leaves
the sources already rebuilt committed and the rest untouched; the command reports
what it did rather than rolling the whole corpus back, because a half-finished
re-index that names its own extent is recoverable and an all-or-nothing one over
thousands of chunks is not.

**No new width (D-131).** Migration 0002 sizes the vector column from EMBEDDING_DIMENSION
when it first runs, and EMBEDDING_DIMENSION follows AI_PROVIDER, so a database keeps the width,
and the provider, it was set up with. A stored column of another width is refused before
anything is touched. ``--resize-column``, which deleted every chunk and resized the column
(D-117), was removed on 14 November 2026.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

import apps.ai
from apps.ai.base import ProviderUnavailable
from apps.core.constants import (
    DOCUMENT_INDEXED,
    EMBEDDING_DIMENSION_BY_PROVIDER,
    DOCUMENT_INDEXING_FAILED,
    DOCUMENT_PARTIALLY_INDEXED,
    MEETING_INDEXED,
    MEETING_PROCESSING_FAILED,
)
from apps.core.vector_columns import describe_width, stored_width
from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.ingestion.chunking import split_into_overlapping_chunks
from apps.ingestion.embedding import (
    DOCUMENT_SOURCE_TYPE,
    MEETING_SOURCE_TYPE,
    embed_and_store_chunks,
)
from apps.meetings.models import Meeting
from apps.meetings.summaries import current_summary, index_summary

PROBE_TEXT = "embedding dimension probe"
VALID_PROVIDERS = ("flm", "anthropic")


class Command(BaseCommand):
    help = "Re-embed and re-index every stored chunk with the configured AI provider."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            choices=VALID_PROVIDERS,
            help=(
                f"the configured provider ({settings.AI_PROVIDER!r}), named as confirmation. "
                "A database keeps the provider it was set up with (D-131), so any other is refused."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report what would be rebuilt and leave every row untouched",
        )

    def handle(self, *args, **options):
        provider = settings.AI_PROVIDER
        dry_run = options["dry_run"]
        if options["provider"] is not None and options["provider"] != provider:
            raise CommandError(
                f"--provider {options['provider']!r} names another provider than this "
                f"database's, {provider!r} (AI_PROVIDER). A database keeps the provider it was "
                f"set up with (D-131), so reindex rebuilds with that provider only. To use "
                f"{options['provider']!r}, set up a new database for it: create it, set "
                f"AI_PROVIDER in .env, run migrate, and ingest the content again. Nothing was "
                f"changed."
            )
        width = EMBEDDING_DIMENSION_BY_PROVIDER.get(provider)
        if width is not None and settings.EMBEDDING_DIMENSION != width:
            # ai.E004's condition, for a caller that skips the checks (D-131).
            raise CommandError(
                f"EMBEDDING_DIMENSION is {settings.EMBEDDING_DIMENSION}, but AI_PROVIDER="
                f"{provider!r} embeds at {width}. The width follows the provider (D-131): remove "
                f"EMBEDDING_DIMENSION from .env. Nothing was changed."
            )
        service = apps.ai.get_ai_service()

        self._guard_dimension(service, provider)
        self._guard_column()

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
        """Refuse to start if the provider's width is not EMBEDDING_DIMENSION.

        The pgvector column is sized from settings.EMBEDDING_DIMENSION (D-03, D-08),
        so a provider returning a different width cannot be stored at all. Checked
        once here, against a probe, rather than discovered part-way through the
        corpus as an opaque database error on some arbitrary chunk. The stored
        column's own width is checked separately, in _guard_column(), because a
        database set up for another provider keeps that provider's width (D-131).
        """
        try:
            result = service.embed([PROBE_TEXT])
        except ProviderUnavailable as exc:
            raise CommandError(f"Provider {provider!r} is unavailable: {exc}") from exc

        expected = settings.EMBEDDING_DIMENSION
        if result.dimension != expected:
            raise CommandError(
                f"Provider {provider!r} embeds at {result.dimension} dimensions but "
                f"EMBEDDING_DIMENSION, which follows AI_PROVIDER (D-131), is {expected}. The "
                f"embedding model setting names a model of another width; set it back to the "
                f"provider's own model. Nothing was changed."
            )
        self.stdout.write(
            f"Provider {provider!r} embeds at {result.dimension} dimensions "
            f"with model {result.model!r}; matches EMBEDDING_DIMENSION."
        )

    def _guard_column(self):
        """Refuse a database whose stored vector column is not EMBEDDING_DIMENSION wide (D-131).

        A database keeps the width, and so the provider, it was set up with. A column of
        another width means the database was set up for another provider, and nothing here
        moves it across: ``--resize-column``, which did (D-117), was removed on 14 November
        2026. The startup check refuses the same database first (ai.E005); this guard is for
        a caller that skips system checks, as ``call_command`` does.
        """
        width = stored_width(ContentChunk)
        expected = settings.EMBEDDING_DIMENSION
        if width != expected:
            raise CommandError(
                f"The stored vector column is {describe_width(width)}, but AI_PROVIDER="
                f"{settings.AI_PROVIDER!r} embeds at {expected}. This database was set up for "
                f"another provider, and a database keeps the provider it was set up with "
                f"(D-131). Point DATABASE_URL at a database set up for "
                f"{settings.AI_PROVIDER!r}, or set up a new one. Nothing was changed."
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
                    # Into the document task prefix that is embedded, not into a column.
                    title=locked.title,
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

        summary_note = ""
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
                    title=locked.title,
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
                # FR-16 (D-125): the Ready summary's passages were among the chunks deleted
                # above, so they are rebuilt here, under the same lock and stamped from the
                # same row. index_summary raises if none can be embedded, which fails this
                # meeting as a whole.
                summary = current_summary(locked)
                if summary is not None:
                    summary_failed = index_summary(locked, summary)
                    summary_note = "; its summary re-embedded" + (
                        f" ({summary_failed} chunk(s) failed)" if summary_failed else ""
                    )
        except Exception as exc:  # noqa: BLE001 - one source failing must not stop the run
            self.stderr.write(f"  FAIL  meeting {meeting.title!r}: {type(exc).__name__}: {exc}")
            return "failed"

        note = f" ({failed_chunk_count} chunk(s) failed)" if failed_chunk_count else ""
        self.stdout.write(
            f"  ok    meeting {meeting.title!r}: {len(chunks)} chunk(s), "
            f"{locked.status}{note}{summary_note}"
        )
        return "rebuilt"
