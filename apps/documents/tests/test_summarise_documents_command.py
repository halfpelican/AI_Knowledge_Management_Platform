"""``manage.py summarise_documents``: D-139's backfill of FR-10's summary for documents classified
before it existed.

No live provider: the suite's stub answers ``classify_document`` with a scheme-derived reply that
carries ``stub_document_summary(title)`` and STUB_KEY_POINTS (apps/ai/testing.py). A document
"classified before D-139" is made the way such a run left it: an analysis row written by
``apply_classification`` from a reply with no summary.
"""

import json
import re
import uuid
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from apps.ai.base import ProviderUnavailable
from apps.ai.testing import STUB_CHAT_MODEL, STUB_KEY_POINTS, stub_document_summary
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
)
from apps.documents.classification import apply_classification
from apps.documents.management.commands import summarise_documents as command_module
from apps.documents.models import ContentTag, Document, DocumentAnalysis, ExtractedContent, Tag

from .classification_builders import ABOVE_THRESHOLD, REPORT, classification, scheme

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
TEXT = "Employees may request annual leave in writing. Approval rests with the manager."
EARLIER_SUMMARY = "A summary an earlier run wrote."
EARLIER_KEY_POINTS = ("An earlier key point.",)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


def make_document(user, title, *, text=TEXT, roles=None, status=DOCUMENT_INDEXED, department=""):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=status, department=department,
        visible_to_roles=[EMPLOYEE_ROLE_NAME] if roles is None else roles,
    )
    if text is not None:
        ExtractedContent.objects.create(document=document, extracted_text=text)
    return document


def classified_before_d139(document, **fields):
    """An analysis row with a classification and no summary, as a run before D-139 left it."""
    return apply_classification(document, classification(doc_type=REPORT, **fields), scheme=scheme())


def summarised(document):
    """An analysis row that already has a summary."""
    return apply_classification(
        document,
        classification(doc_type=REPORT, summary=EARLIER_SUMMARY, key_points=EARLIER_KEY_POINTS),
        scheme=scheme(),
    )


def summary_of(document):
    analysis = DocumentAnalysis.objects.get(document=document)
    return analysis.summary, analysis.key_points


def run(*args):
    out, err = StringIO(), StringIO()
    call_command("summarise_documents", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def titles_sent(stub):
    return [title for title, _text, _scheme in stub.classify_calls]


def stub_summary_of(document):
    return stub_document_summary(document.title), list(STUB_KEY_POINTS)


# --- Selection ---------------------------------------------------------------------------------


def test_by_default_every_classified_document_without_a_summary_is_summarised(employee, stub_ai_service):
    first = make_document(employee, "Leave policy")
    second = make_document(employee, "Purchasing procedure")
    already = make_document(employee, "Travel policy")
    never = make_document(employee, "Unclassified notes")
    classified_before_d139(first)
    classified_before_d139(second)
    summarised(already)

    out, _ = run()

    assert sorted(titles_sent(stub_ai_service)) == ["Leave policy", "Purchasing procedure"]
    assert summary_of(first) == stub_summary_of(first)
    assert summary_of(second) == stub_summary_of(second)
    assert summary_of(already) == (EARLIER_SUMMARY, list(EARLIER_KEY_POINTS))  # not selected
    assert not DocumentAnalysis.objects.filter(document=never).exists()  # skipped, not classified
    assert f"{never.id}  'Unclassified notes'" in out and "SKIPPED no classification" in out
    assert "classify_documents --document <uuid>" in out
    assert "Done: 2 summarised, 0 failed, 1 skipped." in out


def test_force_also_summarises_the_documents_that_already_have_a_summary(employee, stub_ai_service):
    """And still never a document with no analysis row: --force widens the summary rule, not the
    rule that a summary needs a classification to sit beside."""
    without = make_document(employee, "Leave policy")
    already = make_document(employee, "Travel policy")
    never = make_document(employee, "Unclassified notes")
    classified_before_d139(without)
    summarised(already)

    out, _ = run("--force")

    assert sorted(titles_sent(stub_ai_service)) == ["Leave policy", "Travel policy"]
    assert summary_of(without) == stub_summary_of(without)
    assert summary_of(already) == stub_summary_of(already)
    assert not DocumentAnalysis.objects.filter(document=never).exists()
    assert f"{never.id}  'Unclassified notes'" in out and "SKIPPED no classification" in out
    assert "ERROR" not in out
    assert "Done: 2 summarised, 0 failed, 1 skipped." in out


def test_id_summarises_only_the_documents_named(employee, stub_ai_service, tmp_path):
    named = make_document(employee, "Leave policy")
    other = make_document(employee, "Purchasing procedure")
    classified_before_d139(named)
    classified_before_d139(other)
    record_path = tmp_path / "record.json"

    out, _ = run("--id", str(named.id), "--out", str(record_path))

    assert titles_sent(stub_ai_service) == ["Leave policy"]
    assert summary_of(named) == stub_summary_of(named)
    assert summary_of(other) == ("", [])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["selection"] == "ids"
    assert [entry["id"] for entry in record["documents"]] == [str(named.id)]
    assert "Done: 1 summarised, 0 failed, 0 skipped." in out


def test_a_named_document_with_a_summary_is_skipped_without_force_and_summarised_with_it(
    employee, stub_ai_service
):
    already = make_document(employee, "Travel policy")
    summarised(already)

    out, _ = run("--id", str(already.id))

    assert stub_ai_service.classify_calls == []
    assert summary_of(already) == (EARLIER_SUMMARY, list(EARLIER_KEY_POINTS))
    assert "SKIPPED already summarised" in out
    assert "Pass --force to summarise them again." in out
    assert "Done: 0 summarised, 0 failed, 1 skipped." in out

    out, _ = run("--id", str(already.id), "--force")

    assert titles_sent(stub_ai_service) == ["Travel policy"]
    assert summary_of(already) == stub_summary_of(already)
    assert "Done: 1 summarised, 0 failed, 0 skipped." in out


def test_a_document_with_no_classification_is_skipped_and_listed_never_classified(
    employee, stub_ai_service, tmp_path
):
    """Named or not, whatever its status: listed with its status and a line pointing at
    ``classify_documents``, and never given an analysis row or a provider call here."""
    indexed = make_document(employee, "Unclassified notes")
    failed = make_document(employee, "Scanned form", text=None, status=DOCUMENT_EXTRACTION_FAILED)
    record_path = tmp_path / "record.json"

    named_out, _ = run("--id", str(indexed.id), "--out", str(record_path))
    default_out, _ = run()

    assert stub_ai_service.classify_calls == []
    assert not DocumentAnalysis.objects.exists()
    [skipped] = json.loads(record_path.read_text(encoding="utf-8"))["skipped"]
    assert skipped == {
        "id": str(indexed.id), "title": "Unclassified notes", "status": DOCUMENT_INDEXED,
        "reason": "NoClassification",
    }
    assert "classify_documents --document <uuid>" in named_out
    assert "Done: 0 summarised, 0 failed, 1 skipped." in named_out
    assert f"SKIPPED no classification (status {DOCUMENT_EXTRACTION_FAILED})" in default_out
    assert str(failed.id) in default_out and str(indexed.id) in default_out
    assert "1 document(s)" not in default_out and "2 document(s) have no classification" in default_out
    assert "Done: 0 summarised, 0 failed, 2 skipped." in default_out


def test_an_unknown_or_malformed_id_is_an_error_entry_not_a_crash(employee, tmp_path):
    record_path = tmp_path / "record.json"
    unknown = uuid.uuid4()

    out, _ = run("--id", str(unknown), "--id", "not-a-uuid", "--out", str(record_path))

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert [entry["error"] for entry in record["documents"]] == ["NoSuchDocument", "InvalidId"]
    assert "Done: 0 summarised, 2 failed, 0 skipped." in out


def test_a_document_is_summarised_whatever_its_visibility(employee, administrator, stub_ai_service):
    """An operator's command reads every document, an Administrator-only one included."""
    restricted = make_document(administrator, "Board pack", roles=[ADMINISTRATOR_ROLE_NAME])
    classified_before_d139(restricted)

    out, _ = run()

    assert summary_of(restricted) == stub_summary_of(restricted)
    assert "Done: 1 summarised, 0 failed, 0 skipped." in out


# --- One document's failure ----------------------------------------------------------------------


def test_a_failure_is_recorded_against_its_document_and_the_run_continues(
    employee, stub_ai_service, tmp_path
):
    outage = make_document(employee, "Outage")
    textless = make_document(employee, "No text")
    fine = make_document(employee, "Fine")
    for document in (outage, textless, fine):
        classified_before_d139(document)
    ExtractedContent.objects.filter(document=textless).delete()  # nothing left to summarise

    def reply(title, text, scheme):
        if title == "Outage":
            raise ProviderUnavailable("stub outage")
        return classification(summary=f"Summary of {title}.", key_points=("A point.",))

    stub_ai_service.classification = reply
    record_path = tmp_path / "record.json"

    out, _ = run(
        "--id", str(outage.id), "--id", str(textless.id), "--id", str(fine.id),
        "--out", str(record_path),
    )

    assert summary_of(fine) == ("Summary of Fine.", ["A point."])
    assert summary_of(outage) == ("", []) and summary_of(textless) == ("", [])
    entries = json.loads(record_path.read_text(encoding="utf-8"))["documents"]
    assert [(entry["id"], entry.get("error")) for entry in entries] == [
        (str(outage.id), "ProviderUnavailable"),
        (str(textless.id), "InsufficientText"),
        (str(fine.id), None),
    ]
    assert "ERROR ProviderUnavailable: stub outage" in out
    assert "ERROR InsufficientText" in out
    assert "Done: 1 summarised, 2 failed, 0 skipped." in out


# --- What it leaves alone ------------------------------------------------------------------------


def test_a_classified_documents_type_department_tags_and_classified_at_are_unchanged(
    employee, stub_ai_service
):
    """D-139, decision 4. The stub's reply differs from the classification on record in its type,
    its department and its tag, so had the command applied the classification, each would show."""
    Tag.objects.create(tag_name="alpha project", dimension=PROJECT_DIMENSION)
    Tag.objects.create(tag_name="beta project", dimension=PROJECT_DIMENSION)
    document = make_document(employee, "Bridge works")
    # Classified before D-139: a type, a department written into the blank one, a tag, no summary.
    apply_classification(
        document,
        classification(
            doc_type=REPORT, department="People",
            tags=[(PROJECT_DIMENSION, "beta project", ABOVE_THRESHOLD)],
        ),
        scheme=scheme(departments=["Finance", "People"], project=["beta project"]),
    )
    columns = (
        "machine_doc_type", "machine_doc_type_confidence", "machine_department",
        "machine_department_confidence", "doc_type", "doc_type_outcome", "department_outcome",
        "department_applied_by", "user_edited", "proposed_tags", "discarded_suggestions",
        "rejected_tags", "model", "input_truncated", "classified_at",
    )
    before = DocumentAnalysis.objects.filter(document=document).values(*columns).get()
    links_before = list(
        ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk).values()
    )
    assert before["doc_type"] == REPORT and Document.objects.get(pk=document.pk).department == "People"

    run()

    [(_title, _text, sent_scheme)] = stub_ai_service.classify_calls
    # What the stub replied, which differs from what is on record in each of the three.
    assert sent_scheme.doc_types[0] != REPORT
    assert sent_scheme.departments[0] == "Finance"
    assert sent_scheme.tags[PROJECT_DIMENSION][0] == "alpha project"
    assert DocumentAnalysis.objects.filter(document=document).values(*columns).get() == before
    assert Document.objects.get(pk=document.pk).department == "People"
    assert list(
        ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk).values()
    ) == links_before
    assert summary_of(document) == stub_summary_of(document)


# --- The record ----------------------------------------------------------------------------------


def test_the_record_carries_the_run_and_each_documents_summary(employee, tmp_path):
    document = make_document(employee, "Leave policy")
    classified_at = classified_before_d139(document).classified_at
    record_path = tmp_path / "runs" / "summaries.json"

    out, _ = run("--out", str(record_path))

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["database"] == connection.settings_dict["NAME"]
    assert COMMIT_PATTERN.fullmatch(record["commit"])
    assert isinstance(record["uncommitted_tracked_files"], list)
    assert record["started"] <= record["finished"]
    assert (record["selection"], record["force"], record["skipped"]) == ("default", False, [])
    [entry] = record["documents"]
    assert entry["id"] == str(document.id)
    assert (entry["title"], entry["status"]) == ("Leave policy", DOCUMENT_INDEXED)
    assert entry["summary"] == stub_document_summary("Leave policy")
    assert entry["key_points"] == list(STUB_KEY_POINTS)
    assert entry["summary_truncated"] is False
    assert entry["summary_model"] == STUB_CHAT_MODEL
    assert entry["summarised_at"]
    assert entry["classified_at"] == classified_at.isoformat()  # the classification's, unchanged
    assert entry["seconds"] >= 0
    assert "error" not in entry
    assert f"Record written to {record_path}." in out


def test_an_existing_record_is_refused_before_anything_is_summarised(employee, stub_ai_service, tmp_path):
    document = make_document(employee, "Leave policy")
    classified_before_d139(document)
    record_path = tmp_path / "record.json"
    record_path.write_text("an earlier run's record", encoding="utf-8")

    with pytest.raises(CommandError, match="never overwritten"):
        run("--out", str(record_path))

    assert record_path.read_text(encoding="utf-8") == "an earlier run's record"
    assert stub_ai_service.classify_calls == []
    assert summary_of(document) == ("", [])


def test_a_record_that_appears_during_the_run_is_not_overwritten_and_is_printed_instead(
    employee, stub_ai_service, tmp_path
):
    document = make_document(employee, "Leave policy")
    classified_before_d139(document)
    record_path = tmp_path / "record.json"

    def reply(title, text, scheme):
        record_path.write_text("written meanwhile", encoding="utf-8")
        return classification(summary="Summary.", key_points=("A point.",))

    stub_ai_service.classification = reply
    out = StringIO()

    with pytest.raises(CommandError, match="appeared during the run"):
        call_command("summarise_documents", "--out", str(record_path), stdout=out, stderr=StringIO())

    assert record_path.read_text(encoding="utf-8") == "written meanwhile"
    printed = out.getvalue()
    assert f'"id": "{document.id}"' in printed and '"summary": "Summary."' in printed
    assert summary_of(document) == ("Summary.", ["A point."])  # the run itself was kept


def test_the_kmp_database_is_refused(employee, monkeypatch, stub_ai_service):
    """D-84 decision 1, through the gate classify_documents applies: nothing is summarised."""
    document = make_document(employee, "Leave policy")
    classified_before_d139(document)
    monkeypatch.setattr(command_module, "database_name", lambda: "kmp")

    with pytest.raises(CommandError, match="kmp"):
        run()

    assert stub_ai_service.classify_calls == []
    assert summary_of(document) == ("", [])
