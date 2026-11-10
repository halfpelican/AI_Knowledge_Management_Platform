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

**A new width needs ``--resize-column`` (D-117).** Migration 0002 sizes the vector
column from EMBEDDING_DIMENSION when it first runs, and the model reads the same
setting, so changing the setting leaves ``makemigrations`` with nothing to see and
``migrate`` with nothing to do. A database restored from an FLM snapshot therefore
keeps ``vector(768)``, and voyage-4 never embeds at 768. With ``--resize-column``,
every chunk is deleted and the column resized in one transaction before the rebuild:
the old vectors cannot be cast to the new width, so none can be kept. The flag's
value is the connected database's name, typed back. Deleting every chunk nulls every
answer citation's chunk (D-67), and the name is what stops that happening to the
wrong database. A source that then fails to rebuild has no chunks left, so its status
is set to failed rather than left saying it is indexed.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

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


def stored_column_width() -> int | None:
    """The width the stored vector column was built with, or None if it has no width.

    Read from the database rather than from settings or the model, because that
    difference is the whole point: on a restored database the setting can say 1024
    while the column is still 768. pgvector keeps a ``vector(n)`` column's n as its
    type modifier, and an unsized column has -1.
    """
    table = ContentChunk._meta.db_table
    column = ContentChunk._meta.get_field("embedding").column
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT a.atttypmod FROM pg_attribute a "
            "WHERE a.attrelid = %s::regclass AND a.attname = %s",
            [table, column],
        )
        (modifier,) = cursor.fetchone()
    return modifier if modifier > 0 else None


def describe_width(width: int | None) -> str:
    return "vector" if width is None else f"vector({width})"


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
        parser.add_argument(
            "--resize-column",
            metavar="DATABASE",
            help=(
                "delete every chunk and resize the stored vector column to "
                "EMBEDDING_DIMENSION before rebuilding, for a database whose column was "
                "built at another width (D-117). The value is the connected database's "
                "name, typed back as confirmation."
            ),
        )

    def handle(self, *args, **options):
        provider = options["provider"] or settings.AI_PROVIDER
        dry_run = options["dry_run"]
        # Set once --resize-column has deleted every chunk. A source that then fails to
        # rebuild has none left, and its status is corrected to say so.
        self._chunks_deleted = False

        # get_ai_service() reads settings.AI_PROVIDER at call time, so assigning it
        # here is what makes --provider take effect for the whole run, including
        # inside embed_and_store_chunks().
        settings.AI_PROVIDER = provider
        service = apps.ai.get_ai_service()

        self._guard_dimension(service, provider)
        resize_from = self._planned_resize(options["resize_column"])

        documents = list(Document.objects.order_by("uploaded_at"))
        meetings = list(Meeting.objects.order_by("created_at"))
        self.stdout.write(
            f"Re-indexing with provider {provider!r}: "
            f"{len(documents)} document(s), {len(meetings)} meeting(s), "
            f"{ContentChunk.objects.count()} existing chunk(s)."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: nothing will be written."))
        if resize_from is not None:
            self._resize_column(resize_from, dry_run)

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
        if self._chunks_deleted and failed:
            self.stdout.write(
                self.style.ERROR(
                    f"{failed} source(s) failed after the column was resized. They have no "
                    f"chunks now and are marked failed; run this command again, without "
                    f"--resize-column, to rebuild them."
                )
            )

    def _guard_dimension(self, service, provider):
        """Refuse to start if the provider's width is not EMBEDDING_DIMENSION.

        The pgvector column is sized from settings.EMBEDDING_DIMENSION (D-03, D-08),
        so a provider returning a different width cannot be stored at all. Checked
        once here, against a probe, rather than discovered part-way through the
        corpus as an opaque database error on some arbitrary chunk. The stored
        column's own width is checked separately, in _planned_resize(), because on a
        restored database the column and the setting can disagree (D-117).
        """
        try:
            result = service.embed([PROBE_TEXT])
        except ProviderUnavailable as exc:
            raise CommandError(f"Provider {provider!r} is unavailable: {exc}") from exc

        expected = settings.EMBEDDING_DIMENSION
        if result.dimension != expected:
            raise CommandError(
                f"Provider {provider!r} embeds at {result.dimension} dimensions but "
                f"EMBEDDING_DIMENSION is {expected}. Set EMBEDDING_DIMENSION to "
                f"{result.dimension} and run this command again. If the stored column "
                f"is still another width, the command will say how to resize it (D-117)."
            )
        self.stdout.write(
            f"Provider {provider!r} embeds at {result.dimension} dimensions "
            f"with model {result.model!r}; matches EMBEDDING_DIMENSION."
        )

    def _planned_resize(self, confirmation):
        """The column's current type, such as "vector(768)", if it must be resized first.

        None when the column is already EMBEDDING_DIMENSION wide.

        Refuses when the column is the wrong width and no confirmation was given, and
        whenever the name given is not the connected database's. A wrong name means
        the caller thinks they are somewhere else, so even an ordinary re-index is
        refused, because that nulls citations too, one source at a time.
        """
        database = connection.settings_dict["NAME"]
        if confirmation is not None and confirmation != database:
            raise CommandError(
                f"--resize-column names {confirmation!r}, but this command is connected "
                f"to {database!r}. Nothing was changed."
            )
        width = stored_column_width()
        expected = settings.EMBEDDING_DIMENSION
        if width == expected:
            if confirmation is not None:
                self.stdout.write(
                    f"The stored column is already {describe_width(width)}; nothing to resize."
                )
            return None
        if confirmation is None:
            raise CommandError(
                f"The stored vector column is {describe_width(width)}, but "
                f"EMBEDDING_DIMENSION is {expected}. migrate cannot change it: migration "
                f"0002 sizes the column from EMBEDDING_DIMENSION when it first runs, and "
                f"it has already run on this database. To delete every chunk and resize "
                f"the column before rebuilding, run this command again with "
                f"--resize-column {database} (D-117). That nulls every answer citation's "
                f"chunk (D-67), so do it only on a database copied for this provider."
            )
        return describe_width(width)

    def _resize_column(self, resize_from, dry_run):
        """Delete every chunk and resize the column, in one transaction (D-117).

        Through the ORM, so each AnswerCitation's chunk is set null as D-67 requires,
        the same as a per-source rebuild does. A cast cannot carry the old vectors to
        the new width, so they are deleted, not converted. There is no vector index on
        the column to rebuild.
        """
        expected = int(settings.EMBEDDING_DIMENSION)
        resize_to = describe_width(expected)
        if dry_run:
            self.stdout.write(
                f"  would delete {ContentChunk.objects.count()} chunk(s) and resize the "
                f"column from {resize_from} to {resize_to}"
            )
            return
        table = connection.ops.quote_name(ContentChunk._meta.db_table)
        column = connection.ops.quote_name(ContentChunk._meta.get_field("embedding").column)
        with transaction.atomic():
            deleted, _by_model = ContentChunk.objects.all().delete()
            # Django makes foreign keys DEFERRABLE INITIALLY DEFERRED, so the delete
            # leaves deferred checks pending on this table, and Postgres refuses to alter
            # a table with pending trigger events. Running the checks now clears them.
            # They pass, because the delete has already set the citations' chunk to null.
            connection.check_constraints()
            with connection.cursor() as cursor:
                cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {resize_to}")
        self._chunks_deleted = True
        self.stdout.write(
            self.style.WARNING(
                f"Deleted every chunk ({deleted} row(s) in all) and resized the column from "
                f"{resize_from} to {resize_to}."
            )
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
            if self._chunks_deleted:
                # The resize deleted this document's chunks for good, so its status must
                # stop saying it is indexed (D-28's meaning of the status, D-117).
                Document.objects.filter(pk=document.pk).update(status=DOCUMENT_INDEXING_FAILED)
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
        except Exception as exc:  # noqa: BLE001 - one source failing must not stop the run
            self.stderr.write(f"  FAIL  meeting {meeting.title!r}: {type(exc).__name__}: {exc}")
            if self._chunks_deleted:
                # As for a document: no chunks are left, so the status must say so.
                Meeting.objects.filter(pk=meeting.pk).update(status=MEETING_PROCESSING_FAILED)
            return "failed"

        note = f" ({failed_chunk_count} chunk(s) failed)" if failed_chunk_count else ""
        self.stdout.write(
            f"  ok    meeting {meeting.title!r}: {len(chunks)} chunk(s), {locked.status}{note}"
        )
        return "rebuilt"
