"""``python manage.py classify_documents`` — FR-10's classification over stored documents, recorded.

The Objective 05 run's instrument (docs/decisions.md D-106). It classifies the documents it is
given through ``classify_document_now`` (apps/documents/classification.py, D-105), the one path the
upload hook and ``POST /api/documents/{id}/classify`` also take, and writes a JSON record of what
the machine said and what the apply rules did with it, so the measurement reads the same rows the
application wrote and nothing is re-derived.

**Selection.** ``--all`` takes every document whose status is Indexed or Partially indexed, oldest
first: a document that reached neither has no extracted text worth classifying, or none at all.
``--document <uuid>`` names one and repeats. The two are not combined.

**One document at a time.** A provider outage (``ProviderUnavailable``) or a document the apply
layer refuses (``ClassificationError``: no extracted text, a value outside its list) is recorded
against that document and the run continues, because one failure must not cost the rest of the run
its record. Any other exception propagates: it is a defect, not an outcome.

**The record** (``--out``) carries the database name, the commit (``git rev-parse HEAD`` through
``scripts/measurement_record.py``, with the tracked files that were uncommitted, since a SHA names a
commit and not a working tree), when the run started and finished, and per document the machine's
values and confidences, both outcomes, the tag links with their provisional flags, the proposed and
discarded suggestions, and the seconds the call took, or the error. The database named ``kmp`` is
refused (D-84 decision 1) through the same gate the measurement scripts apply.
"""

import json
import time
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from apps.ai.base import ProviderUnavailable
from apps.core.constants import (
    DOCUMENT_INDEXED,
    DOCUMENT_PARTIALLY_INDEXED,
    REPOSITORY_TAG_DIMENSIONS,
    SOURCE_TYPES,
)
from apps.documents.classification import ClassificationError, classify_document_now
from apps.documents.models import ContentTag, Document
from scripts.measurement_record import (
    RecordError,
    git_commit_sha,
    git_tracked_changes,
    refuse_protected_database,
)

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
# What --all selects: the two statuses under which a document has text and is searchable.
CLASSIFIABLE_STATUSES = (DOCUMENT_INDEXED, DOCUMENT_PARTIALLY_INDEXED)


def database_name() -> str:
    """The configured database's name, never its URL: the record carries no credential."""
    return connection.settings_dict["NAME"]


def _number(value):
    return None if value is None else float(value)


def document_entry(document: Document, analysis, seconds: float) -> dict:
    """One classified document's record: what the machine said, what the rules did, the links."""
    links = (
        ContentTag.objects.filter(
            source_type=DOCUMENT_SOURCE_TYPE,
            source_id=document.pk,
            tag__dimension__in=REPOSITORY_TAG_DIMENSIONS,
        )
        .select_related("tag")
        .order_by("tag__dimension", "tag__tag_name", "pk")
    )
    return {
        "id": str(document.pk),
        "title": document.title,
        "status": document.status,
        "machine_doc_type": analysis.machine_doc_type,
        "machine_doc_type_confidence": _number(analysis.machine_doc_type_confidence),
        "machine_department": analysis.machine_department,
        "machine_department_confidence": _number(analysis.machine_department_confidence),
        "doc_type": analysis.doc_type,
        "doc_type_outcome": analysis.doc_type_outcome,
        "department": document.department,
        "department_outcome": analysis.department_outcome,
        "user_edited": analysis.user_edited,
        "tags": [
            {
                "dimension": link.tag.dimension,
                "name": link.tag.tag_name,
                "applied_by": link.applied_by,
                "confirmed": link.confirmed,
                "provisional": link.provisional,
                "confidence": _number(link.confidence),
            }
            for link in links
        ],
        "proposed_topics": analysis.proposed_topics,
        "discarded_suggestions": analysis.discarded_suggestions,
        "model": analysis.model,
        "input_truncated": analysis.input_truncated,
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


class Command(BaseCommand):
    help = (
        "Classify stored documents with the configured AI provider (FR-10) and record the run "
        "(Objective 05, D-106). Pass --all, or --document <uuid> (repeatable)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="every document whose status is Indexed or Partially indexed, oldest first",
        )
        parser.add_argument(
            "--document",
            action="append",
            default=[],
            metavar="UUID",
            help="one document by id; repeat the option for several",
        )
        parser.add_argument(
            "--out",
            type=Path,
            default=None,
            metavar="PATH",
            help="write the run's JSON record here (the directory is created)",
        )

    def handle(self, *args, **options):
        database = database_name()
        try:
            refuse_protected_database(database)
        except RecordError as exc:
            raise CommandError(str(exc))
        if options["all"] and options["document"]:
            raise CommandError("--all and --document contradict each other; pass one.")
        if not options["all"] and not options["document"]:
            raise CommandError("Pass --all, or --document <uuid> (repeatable).")

        started = timezone.now()
        record = {
            "database": database,
            "commit": None,
            "uncommitted_tracked_files": [],
            "started": started.isoformat(),
            "finished": None,
            "selection": "all" if options["all"] else "documents",
            "documents": [],
        }
        try:
            record["commit"] = git_commit_sha()
            record["uncommitted_tracked_files"] = git_tracked_changes()
        except RecordError as exc:
            # Recorded rather than fatal: the run's own results are still worth keeping, and the
            # record says plainly that it does not know which commit produced them.
            record["commit_error"] = str(exc)
            self.stderr.write(self.style.WARNING(f"Commit not recorded: {exc}"))

        self.stdout.write(f"Classifying against database {database!r}.")
        if options["all"]:
            for document in self._all_classifiable():
                self._run_one(record, self._classify(document))
        else:
            for raw_id in options["document"]:
                self._run_one(record, self._classify_id(raw_id))

        record["finished"] = timezone.now().isoformat()
        classified = sum(1 for entry in record["documents"] if "error" not in entry)
        failed = len(record["documents"]) - classified
        summary = f"Done: {classified} classified, {failed} failed."
        self.stdout.write(self.style.ERROR(summary) if failed else self.style.SUCCESS(summary))

        out = options["out"]
        if out is not None:
            out = Path(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(record, indent=2), encoding="utf-8")
            self.stdout.write(f"Record written to {out}.")

    # --- selection ---------------------------------------------------------------------------

    def _all_classifiable(self):
        return list(
            Document.objects.filter(status__in=CLASSIFIABLE_STATUSES).order_by("uploaded_at", "pk")
        )

    def _classify_id(self, raw_id: str) -> dict:
        try:
            document_id = uuid.UUID(str(raw_id))
        except ValueError:
            return error_entry(raw_id, "", "InvalidId", f"{raw_id!r} is not a UUID.", 0.0)
        document = Document.objects.filter(pk=document_id).first()
        if document is None:
            return error_entry(document_id, "", "NoSuchDocument", "No document has this id.", 0.0)
        return self._classify(document)

    # --- one document ------------------------------------------------------------------------

    def _classify(self, document: Document) -> dict:
        clock = time.perf_counter()
        try:
            analysis = classify_document_now(document)
        except (ProviderUnavailable, ClassificationError) as exc:
            return error_entry(
                document.pk, document.title, type(exc).__name__, str(exc),
                time.perf_counter() - clock,
            )
        seconds = time.perf_counter() - clock
        document.refresh_from_db(fields=["department", "status"])
        return document_entry(document, analysis, seconds)

    def _run_one(self, record: dict, entry: dict) -> None:
        record["documents"].append(entry)
        self.stdout.write(self._line(entry))

    @staticmethod
    def _line(entry: dict) -> str:
        title = entry["title"][:40]
        if "error" in entry:
            return f"{entry['id']}  {title!r:<42}  ERROR {entry['error']}: {entry['detail']}"
        tags = sum(1 for tag in entry["tags"] if not tag["provisional"])
        held = len(entry["tags"]) - tags
        return (
            f"{entry['id']}  {title!r:<42}  type {entry['machine_doc_type']}/"
            f"{entry['doc_type_outcome']}  department {entry['machine_department']!r}/"
            f"{entry['department_outcome']}  tags {tags} applied, {held} held, "
            f"{len(entry['proposed_topics'])} proposed, {len(entry['discarded_suggestions'])} "
            f"discarded  {entry['seconds']}s"
        )
