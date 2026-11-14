"""``manage.py classify_documents``: FR-10 over stored documents, with the Objective 05 record (D-106).

No live provider: the suite's stub answers ``classify_document`` with a scheme-derived reply
(apps/ai/testing.py), and a test that needs an outage sets its ``classification`` attribute to a
callable that raises.
"""

import json
import re
import uuid
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from apps.ai.base import ProviderUnavailable
from apps.ai.testing import STUB_CONFIDENCE
from apps.core.constants import (
    ASSIGNMENT_APPLIED,
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_INDEXED,
    DOCUMENT_PARTIALLY_INDEXED,
    DOCUMENT_PROCESSING,
    DOCUMENT_TYPES,
    EMPLOYEE_ROLE_NAME,
    PROJECT_DIMENSION,
)
from apps.documents.management.commands import classify_documents as command_module
from apps.documents.classification import reject_tag
from apps.documents.models import (
    ContentTag,
    Department,
    Document,
    DocumentAnalysis,
    ExtractedContent,
    Tag,
)

pytestmark = pytest.mark.django_db

TEXT = "Employees may request annual leave in writing. Approval rests with the manager."
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


def make_document(user, title, *, status=DOCUMENT_INDEXED, text=TEXT, department="People"):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=status, department=department,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    if text is not None:
        ExtractedContent.objects.create(document=document, extracted_text=text)
    return document


def run(*args):
    out, err = StringIO(), StringIO()
    call_command("classify_documents", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def outage(*args):
    raise ProviderUnavailable("stub outage")


def test_document_classifies_the_named_document_and_writes_the_record(employee, tmp_path):
    document = make_document(employee, "Leave policy")
    Department.objects.create(name="People")  # listed, so the stub suggests it (D-129)
    record_path = tmp_path / "runs" / "classification.json"

    out, _ = run("--document", str(document.id), "--out", str(record_path))

    analysis = DocumentAnalysis.objects.get(document=document)
    assert analysis.machine_doc_type == DOCUMENT_TYPES[0]  # the stub's reply
    assert str(document.id) in out
    assert "Done: 1 classified, 0 failed." in out

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["database"] == connection.settings_dict["NAME"]
    assert COMMIT_PATTERN.fullmatch(record["commit"])
    assert isinstance(record["uncommitted_tracked_files"], list)
    assert record["started"] <= record["finished"]
    assert record["selection"] == "documents"
    [entry] = record["documents"]
    assert entry["id"] == str(document.id)
    assert entry["title"] == "Leave policy"
    assert entry["machine_doc_type"] == DOCUMENT_TYPES[0]
    assert entry["machine_doc_type_confidence"] == STUB_CONFIDENCE
    assert entry["doc_type_outcome"] == ASSIGNMENT_APPLIED
    assert (entry["machine_department"], entry["department_outcome"]) == ("People", ASSIGNMENT_APPLIED)
    assert entry["department"] == "People"
    assert entry["tags"] == [] and entry["proposed_tags"] == []  # D-128's name for the list
    assert isinstance(entry["discarded_suggestions"], list)
    assert entry["seconds"] >= 0
    assert "error" not in entry


def test_all_takes_indexed_and_partially_indexed_documents_only(employee, stub_ai_service):
    indexed = make_document(employee, "Indexed")
    partial = make_document(employee, "Partially indexed", status=DOCUMENT_PARTIALLY_INDEXED)
    make_document(employee, "Still processing", status=DOCUMENT_PROCESSING)
    make_document(employee, "Extraction failed", status=DOCUMENT_EXTRACTION_FAILED, text=None)

    out, _ = run("--all")

    assert set(DocumentAnalysis.objects.values_list("document_id", flat=True)) == {
        indexed.id, partial.id,
    }
    assert len(stub_ai_service.classify_calls) == 2
    assert "Done: 2 classified, 0 failed." in out


def test_a_document_that_fails_is_recorded_and_the_run_continues(employee, tmp_path):
    classified = make_document(employee, "Has text")
    textless = make_document(employee, "No text", text=None)
    record_path = tmp_path / "record.json"

    out, _ = run("--document", str(textless.id), "--document", str(classified.id),
                 "--out", str(record_path))

    assert DocumentAnalysis.objects.filter(document=classified).exists()
    assert not DocumentAnalysis.objects.filter(document=textless).exists()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    failed, succeeded = record["documents"]
    assert failed["id"] == str(textless.id)
    assert failed["error"] == "InsufficientText"
    assert succeeded["id"] == str(classified.id) and "error" not in succeeded
    assert "ERROR InsufficientText" in out
    assert "Done: 1 classified, 1 failed." in out


def test_a_provider_outage_is_recorded_per_document_and_writes_nothing(employee, stub_ai_service):
    first = make_document(employee, "First")
    second = make_document(employee, "Second")
    stub_ai_service.classification = outage

    out, _ = run("--document", str(first.id), "--document", str(second.id))

    assert not DocumentAnalysis.objects.exists()
    assert out.count("ERROR ProviderUnavailable") == 2
    assert "Done: 0 classified, 2 failed." in out


def test_an_unknown_or_malformed_id_is_an_error_entry_not_a_crash(employee, tmp_path):
    record_path = tmp_path / "record.json"
    unknown = uuid.uuid4()

    out, _ = run("--document", str(unknown), "--document", "not-a-uuid", "--out", str(record_path))

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert [entry["error"] for entry in record["documents"]] == ["NoSuchDocument", "InvalidId"]
    assert "Done: 0 classified, 2 failed." in out


def test_neither_flag_and_both_flags_are_refused(employee):
    with pytest.raises(CommandError, match="--all"):
        run()
    with pytest.raises(CommandError, match="contradict"):
        run("--all", "--document", str(uuid.uuid4()))


def test_the_kmp_database_is_refused(employee, monkeypatch, stub_ai_service):
    """D-84 decision 1, through the measurement scripts' own gate: nothing is classified."""
    document = make_document(employee, "Leave policy")
    monkeypatch.setattr(command_module, "database_name", lambda: "kmp")

    with pytest.raises(CommandError, match="kmp"):
        run("--document", str(document.id))

    assert stub_ai_service.classify_calls == []
    assert not DocumentAnalysis.objects.exists()


def test_a_removed_link_is_recorded_as_removed_and_counted_apart(employee, tmp_path):
    """D-105's dated note of 10 November 2026 (night): a link a person removed stays beside the
    machine's assignment, so the record lists it with ``removed: true``, and the summary line counts
    it as removed rather than as applied."""
    document = make_document(employee, "Bridge works")
    Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)  # in the scheme
    run("--document", str(document.id))
    link = ContentTag.objects.get(source_id=document.id)
    reject_tag(document, link.pk)
    record_path = tmp_path / "record.json"

    out, _ = run("--document", str(document.id), "--out", str(record_path))

    [entry] = json.loads(record_path.read_text(encoding="utf-8"))["documents"]
    [tag] = entry["tags"]
    assert (tag["name"], tag["removed"], tag["provisional"]) == ("bridge maintenance", True, False)
    assert "tags 0 applied, 0 held, 1 removed" in out
