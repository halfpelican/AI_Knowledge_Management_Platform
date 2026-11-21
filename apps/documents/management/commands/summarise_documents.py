"""``python manage.py summarise_documents`` — FR-10's summary for documents classified before it
existed: D-139's backfill (decision 4).

Since D-139 every classification run writes a document's summary and key points with its
classification (``apply_classification`` rule 1): the upload, ``POST /api/documents/{id}/classify``,
a reprocess and ``classify_documents``. A document classified before ``documents 0016`` has an
analysis row and no summary. This command gives it one and leaves its classification exactly as it
is. For each document it calls ``summarise_document_now`` (apps/documents/classification.py): one
``classify_document`` operation through the configured provider, of which ``apply_summary`` stores
only the five summary columns. The type, the department, the outcomes, the tags, the proposals and
``classified_at`` are not touched, so a person's corrections and the classification on record stand.

**Selection.**

- By default: every document that has an analysis row and an empty summary, oldest first.
- ``--force`` also takes the documents that already have a summary, and summarises them again.
- ``--id <uuid>`` (repeatable) takes the documents named, in the order given, and the rule above
  applies to them too: one that already has a summary is skipped, and listed, unless ``--force``
  is passed. A malformed or unknown id is an error entry, as in ``classify_documents``.
- A document with no analysis row is never summarised: there is no classification for the summary
  to sit beside, and ``apply_summary`` creates none. It is skipped and listed, with a line pointing
  at ``classify_documents``, which classifies it and writes its summary in one ``classify_document``
  operation. By default
  every such document is listed, whatever its status, and its status is shown.

**Every document, whatever its visibility.** An operator's command, run on the server with the
database's own credentials: it reads ``Document`` rows directly and never through
``scoped_documents``, as ``classify_documents`` and ``reindex`` do. It exposes nothing. What it
writes reaches a reader only through the scoped routes, beside the document it belongs to (CLAUDE.md
invariant 1), and each document's prompt is built from that document's own scheme (``tag_scheme``).

**One document at a time.** A provider outage (``ProviderUnavailable``, a refusal included) or a
document the apply layer refuses (``ClassificationError``: no extracted text, or a classification
deleted since it was selected) is recorded against that document and the run continues. Any other
exception propagates: it is a defect, not an outcome. Each document is its own transaction, and no
lock is held while the provider is called.

**The record** (``--out``): the database name, the commit (``git rev-parse HEAD`` through
``scripts/measurement_record.py``, with the tracked files that were uncommitted), when the run
started and finished, the selection and ``--force``; per document the stored summary, key points,
``summary_truncated``, ``summary_model`` and ``summarised_at``, its ``classified_at`` (left as it
was, so the record shows the classification predates the summary) and the seconds the call took,
or the error; and each skipped document with the reason. **A record is never overwritten:** a path
that exists is refused before anything is summarised, and the file is created exclusively at the
end, so one that appears during the run is not overwritten either: the record is then printed
instead, and the command fails. The database named ``kmp`` is refused (D-84 decision 1), through
the gate ``classify_documents`` applies.

**What one document costs.** One ``classify_document`` operation: one request for a document within
CLASSIFICATION_INPUT_TOKENS, and for a longer one a request per section, up to
MAXIMUM_SUMMARY_SECTIONS, and a final one (D-139), each of up to MAXIMUM_CLASSIFY_ATTEMPTS attempts.
"""

import json
import time
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from apps.ai.base import ProviderUnavailable
from apps.documents.classification import ClassificationError, summarise_document_now
from apps.documents.models import Document, DocumentAnalysis
from scripts.measurement_record import (
    RecordError,
    git_commit_sha,
    git_tracked_changes,
    refuse_protected_database,
)

# Why a document was skipped rather than summarised: it has no analysis row, or it already has a
# summary and was named with --id without --force.
NO_CLASSIFICATION = "NoClassification"
ALREADY_SUMMARISED = "AlreadySummarised"

CLASSIFY_FIRST = (
    "{count} document(s) have no classification and were skipped. Classify each with "
    "'manage.py classify_documents --document <uuid>', which writes its summary too."
)
FORCE_TO_REPEAT = (
    "{count} document(s) named already have a summary and were skipped. Pass --force to "
    "summarise them again."
)


def database_name() -> str:
    """The configured database's name, never its URL: the record carries no credential."""
    return connection.settings_dict["NAME"]


def _timestamp(value):
    return None if value is None else value.isoformat()


def summary_entry(document: Document, analysis: DocumentAnalysis, seconds: float) -> dict:
    """One summarised document's record: the five columns as stored, and when it was classified."""
    return {
        "id": str(document.pk),
        "title": document.title,
        "status": document.status,
        "summary": analysis.summary,
        "key_points": list(analysis.key_points),
        "summary_truncated": analysis.summary_truncated,
        "summary_model": analysis.summary_model,
        "summarised_at": _timestamp(analysis.summarised_at),
        "classified_at": _timestamp(analysis.classified_at),
        "seconds": round(seconds, 3),
    }


def error_entry(document_id, title, error: str, detail: str, seconds: float) -> dict:
    return {
        "id": str(document_id),
        "title": title,
        "error": error,
        "detail": detail,
        "seconds": round(seconds, 3),
    }


def skipped_entry(document: Document, reason: str) -> dict:
    return {
        "id": str(document.pk),
        "title": document.title,
        "status": document.status,
        "reason": reason,
    }


class Command(BaseCommand):
    help = (
        "Summarise documents classified before FR-10's summary existed (D-139's backfill), storing "
        "only the summary and key points. By default every classified document without a summary; "
        "--force includes those with one; --id <uuid> (repeatable) names documents."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="also summarise documents that already have a summary",
        )
        parser.add_argument(
            "--id",
            action="append",
            default=[],
            dest="ids",
            metavar="UUID",
            help="one document by id; repeat the option for several",
        )
        parser.add_argument(
            "--out",
            type=Path,
            default=None,
            metavar="PATH",
            help="write the run's JSON record here (the directory is created); never an existing file",
        )

    def handle(self, *args, **options):
        database = database_name()
        try:
            refuse_protected_database(database)
        except RecordError as exc:
            raise CommandError(str(exc))
        out = None if options["out"] is None else Path(options["out"])
        if out is not None and out.exists():
            # Before anything is summarised, so a refused record costs no provider call.
            raise CommandError(f"{out} exists; a record is never overwritten. Choose another path.")
        force = options["force"]

        record = {
            "database": database,
            "commit": None,
            "uncommitted_tracked_files": [],
            "started": timezone.now().isoformat(),
            "finished": None,
            "selection": "ids" if options["ids"] else "default",
            "force": force,
            "documents": [],
            "skipped": [],
        }
        try:
            record["commit"] = git_commit_sha()
            record["uncommitted_tracked_files"] = git_tracked_changes()
        except RecordError as exc:
            # Recorded rather than fatal, as classify_documents records it: the run's results are
            # still worth keeping, and the record says it does not know which commit made them.
            record["commit_error"] = str(exc)
            self.stderr.write(self.style.WARNING(f"Commit not recorded: {exc}"))

        self.stdout.write(f"Summarising against database {database!r}.")
        if options["ids"]:
            for raw_id in options["ids"]:
                self._consider_id(record, raw_id, force=force)
        else:
            for document in self._selected(force=force):
                self._run_one(record, self._summarise(document))
            for document in self._without_classification():
                self._skip(record, document, NO_CLASSIFICATION)

        record["finished"] = timezone.now().isoformat()
        self._pointers(record)
        summarised = sum(1 for entry in record["documents"] if "error" not in entry)
        failed = len(record["documents"]) - summarised
        done = f"Done: {summarised} summarised, {failed} failed, {len(record['skipped'])} skipped."
        self.stdout.write(self.style.ERROR(done) if failed else self.style.SUCCESS(done))

        if out is not None:
            self._write_record(out, record)

    # --- selection ---------------------------------------------------------------------------

    def _selected(self, *, force: bool) -> list[Document]:
        """Every document with an analysis row; without ``--force``, only those whose summary is
        empty. Oldest first, as ``classify_documents --all`` takes them."""
        documents = Document.objects.filter(analysis__isnull=False)
        if not force:
            documents = documents.filter(analysis__summary="")
        return list(documents.order_by("uploaded_at", "pk"))

    def _without_classification(self) -> list[Document]:
        """Every document with no analysis row, whatever its status, oldest first."""
        return list(Document.objects.filter(analysis__isnull=True).order_by("uploaded_at", "pk"))

    def _consider_id(self, record: dict, raw_id: str, *, force: bool) -> None:
        """One ``--id``: parsed as a UUID before any lookup, then the default rule applied to it."""
        try:
            document_id = uuid.UUID(str(raw_id))
        except ValueError:
            self._run_one(record, error_entry(raw_id, "", "InvalidId", f"{raw_id!r} is not a UUID.", 0.0))
            return
        document = Document.objects.filter(pk=document_id).first()
        if document is None:
            self._run_one(
                record, error_entry(document_id, "", "NoSuchDocument", "No document has this id.", 0.0)
            )
            return
        summary = (
            DocumentAnalysis.objects.filter(document_id=document.pk)
            .values_list("summary", flat=True)
            .first()
        )
        if summary is None:
            self._skip(record, document, NO_CLASSIFICATION)
        elif summary and not force:
            self._skip(record, document, ALREADY_SUMMARISED)
        else:
            self._run_one(record, self._summarise(document))

    # --- one document ------------------------------------------------------------------------

    def _summarise(self, document: Document) -> dict:
        clock = time.perf_counter()
        try:
            analysis = summarise_document_now(document)
        except (ProviderUnavailable, ClassificationError) as exc:
            return error_entry(
                document.pk, document.title, type(exc).__name__, str(exc),
                time.perf_counter() - clock,
            )
        return summary_entry(document, analysis, time.perf_counter() - clock)

    def _run_one(self, record: dict, entry: dict) -> None:
        record["documents"].append(entry)
        self.stdout.write(self._line(entry))

    def _skip(self, record: dict, document: Document, reason: str) -> None:
        entry = skipped_entry(document, reason)
        record["skipped"].append(entry)
        why = (
            "no classification" if reason == NO_CLASSIFICATION else "already summarised"
        )
        self.stdout.write(
            f"{entry['id']}  {entry['title'][:40]!r:<42}  SKIPPED {why} (status {entry['status']})"
        )

    def _pointers(self, record: dict) -> None:
        """The lines that say what to do about each kind of skipped document."""
        for reason, message in ((NO_CLASSIFICATION, CLASSIFY_FIRST), (ALREADY_SUMMARISED, FORCE_TO_REPEAT)):
            count = sum(1 for entry in record["skipped"] if entry["reason"] == reason)
            if count:
                self.stdout.write(self.style.WARNING(message.format(count=count)))

    @staticmethod
    def _line(entry: dict) -> str:
        title = entry["title"][:40]
        if "error" in entry:
            return f"{entry['id']}  {title!r:<42}  ERROR {entry['error']}: {entry['detail']}"
        truncated = ", first sections only" if entry["summary_truncated"] else ""
        return (
            f"{entry['id']}  {title!r:<42}  summary of {len(entry['summary'])} characters, "
            f"{len(entry['key_points'])} key point(s){truncated}  {entry['seconds']}s"
        )

    # --- the record --------------------------------------------------------------------------

    def _write_record(self, out: Path, record: dict) -> None:
        """Create ``out`` exclusively and write the record to it. A file that appeared there during
        the run is not overwritten: the record is printed instead, and the command fails."""
        text = json.dumps(record, indent=2)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with out.open("x", encoding="utf-8") as handle:
                handle.write(text)
        except FileExistsError:
            self.stdout.write(text)
            raise CommandError(
                f"{out} appeared during the run; a record is never overwritten, so it was printed "
                "above instead."
            )
        self.stdout.write(f"Record written to {out}.")
