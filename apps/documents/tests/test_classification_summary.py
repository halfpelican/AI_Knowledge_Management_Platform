"""FR-10's document summary, written (D-139): ``apply_classification`` rule 1's five summary
columns, ``apply_summary`` (the backfill's write), and ``summarise_document_now`` (what the
backfill command calls).

Driven with classifications and schemes built by hand (classification_builders.py), as
test_classification_apply.py drives the other rules, and with the suite's stub where a test needs
the provider's own computation of ``summary_truncated`` (apps/ai/testing.py). No live provider.
"""

import datetime
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import apps.ai
from apps.ai.base import ProviderUnavailable
from apps.ai.testing import STUB_CHAT_MODEL, STUB_KEY_POINTS, stub_document_summary
from apps.core.constants import (
    ASSIGNMENT_APPLIED,
    ASSIGNMENT_CONFIRMED,
    CLASSIFICATION_INPUT_TOKENS,
    MAXIMUM_SUMMARY_SECTIONS,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.classification import (
    SUMMARY_FIELDS,
    InsufficientText,
    NotOnThisDocument,
    apply_classification,
    apply_summary,
    classify_document_now,
    confirm_classification,
    reject_proposed_tag,
    summarise_document_now,
    tag_scheme,
)
from apps.documents.models import (
    ContentTag,
    Department,
    Document,
    DocumentAnalysis,
    ExtractedContent,
    Tag,
)

from .classification_builders import (
    ABOVE_THRESHOLD,
    POLICY,
    PROCEDURE,
    REPORT,
    RecordingClassifier,
    classification,
    scheme,
)

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
TEXT = "Leave requests need a manager's approval. Annual leave accrues monthly."

SUMMARY = "How annual leave is requested, approved and carried over."
KEY_POINTS = ("Leave is requested in writing.", "A manager approves it.")
OTHER_SUMMARY = "When purchase orders need a second approval."
OTHER_KEY_POINTS = ("Orders above ten thousand dollars need two approvals.",)

NUL = chr(0)
LONE_SURROGATE = "\ud800"  # what json.loads makes of a \ud800 escape in a reply
REPLACEMENT = "�"

# The five summary columns as an analysis with no summary holds them.
NO_SUMMARY = ("", [], False, "", None)


def summary_columns(analysis):
    analysis.refresh_from_db()
    return (
        analysis.summary,
        analysis.key_points,
        analysis.summary_truncated,
        analysis.summary_model,
        analysis.summarised_at,
    )


def row(model, pk):
    """Every column of one row, as the database holds it."""
    return model.objects.filter(pk=pk).values().get()


def links_of(document):
    return list(
        ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)
        .order_by("pk")
        .values()
    )


def install(monkeypatch, service):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
    return service


def run(document, **fields):
    """One classification run, against an empty scheme."""
    return apply_classification(document, classification(**fields), scheme=scheme())


def classified_without_a_summary(document):
    """An analysis row as a run before D-139 left it: a classification and no summary."""
    return run(document, doc_type=REPORT)


# Each writer of the summary, so that a rule they share is asserted of both: a classification run,
# and the backfill's write, which needs an analysis row to be there already.
def write_by_a_run(document, result):
    return apply_classification(document, result, scheme=scheme())


def write_by_the_backfill(document, result):
    if not DocumentAnalysis.objects.filter(document=document).exists():
        classified_without_a_summary(document)
    return apply_summary(document, result)


WRITERS = pytest.mark.parametrize(
    "write", [write_by_a_run, write_by_the_backfill], ids=["classification run", "backfill"]
)


# --- Rule 1: every run writes the five ----------------------------------------------------------


def test_a_run_stores_the_summary_its_key_points_the_flag_the_model_and_when(document):
    analysis = run(
        document, summary=SUMMARY, key_points=KEY_POINTS, summary_truncated=True,
        model="first-model",
    )

    summary, key_points, truncated, model, summarised_at = summary_columns(analysis)
    assert summary == SUMMARY
    # A list of strings in the reply's order, as the jsonb column hands it back.
    assert key_points == list(KEY_POINTS)
    assert isinstance(key_points, list) and all(isinstance(point, str) for point in key_points)
    assert truncated is True
    assert model == "first-model"
    # The run's time: the same instant the classification on record was made.
    assert summarised_at is not None and summarised_at == analysis.classified_at


def test_a_second_run_replaces_all_five(document):
    run(document, summary=SUMMARY, key_points=KEY_POINTS, summary_truncated=True, model="first-model")

    analysis = run(
        document, summary=OTHER_SUMMARY, key_points=OTHER_KEY_POINTS, summary_truncated=False,
        model="second-model",
    )

    assert DocumentAnalysis.objects.filter(document=document).count() == 1
    summary, key_points, truncated, model, summarised_at = summary_columns(analysis)
    assert (summary, key_points, truncated, model) == (
        OTHER_SUMMARY, list(OTHER_KEY_POINTS), False, "second-model",
    )
    # Told apart from the first run by what it wrote, never by the clock (Windows ticks ~15.6 ms).
    assert summarised_at == analysis.classified_at


def test_a_user_edited_row_keeps_the_persons_type_and_department_and_takes_the_new_summary(document):
    """D-139: the summary is the machine's, so a person's edit, which protects the type and the
    department from reprocessing, does not protect it."""
    apply_classification(
        document,
        classification(doc_type=POLICY, department="Finance", summary=SUMMARY, key_points=KEY_POINTS),
        scheme=scheme(departments=["Finance"]),
    )
    confirm_classification(document, doc_type=PROCEDURE, department="People")

    analysis = apply_classification(
        document,
        classification(
            doc_type=REPORT, department="Finance", summary=OTHER_SUMMARY,
            key_points=OTHER_KEY_POINTS, summary_truncated=True, model="second-model",
        ),
        scheme=scheme(departments=["Finance"]),
    )

    analysis.refresh_from_db()
    document.refresh_from_db()
    # The person's decisions stand, and the machine's own values were still recorded beside them.
    assert analysis.user_edited is True
    assert (analysis.doc_type, analysis.doc_type_outcome) == (PROCEDURE, ASSIGNMENT_CONFIRMED)
    assert analysis.department_outcome == ASSIGNMENT_CONFIRMED
    assert document.department == "People"
    assert analysis.machine_doc_type == REPORT
    # And the summary is this run's.
    assert summary_columns(analysis)[:4] == (
        OTHER_SUMMARY, list(OTHER_KEY_POINTS), True, "second-model",
    )
    assert analysis.summarised_at == analysis.classified_at


@WRITERS
@pytest.mark.parametrize("empty", ["", "  \n\t "], ids=["empty", "whitespace"])
def test_an_empty_summary_resets_all_five_to_their_defaults(document, write, empty):
    """An analysis never claims a summary it does not hold: an empty one resets the key points, the
    flag, the model and the time with it, whatever else the reply carried."""
    run(document, summary=SUMMARY, key_points=KEY_POINTS, summary_truncated=True, model="first-model")

    analysis = write(
        document,
        classification(summary=empty, key_points=("A point.",), summary_truncated=True,
                       model="second-model"),
    )

    assert summary_columns(analysis) == NO_SUMMARY


@WRITERS
@pytest.mark.parametrize("character", [NUL, LONE_SURROGATE], ids=["nul", "lone surrogate"])
def test_a_summary_or_key_point_that_cannot_be_stored_is_stored_with_the_replacement_character(
    document, write, character
):
    """PostgreSQL refuses a NUL in a text column and in jsonb, and a lone surrogate cannot be
    encoded for either, so without the guard the save raises. The parser refuses such a reply
    (D-139); this is the guard behind it, the one rule 4d gives a tag name."""
    analysis = write(
        document,
        classification(
            summary=f"Leave{character}policy.",
            key_points=(f"First{character}point.", "Second point."),
        ),
    )

    summary, key_points, *_ = summary_columns(analysis)
    assert summary == f"Leave{REPLACEMENT}policy."
    assert key_points == [f"First{REPLACEMENT}point.", "Second point."]


@WRITERS
def test_the_summary_and_key_points_are_stored_stripped_and_a_blank_key_point_is_left_out(
    document, write
):
    analysis = write(
        document,
        classification(summary="  Leave policy.\n", key_points=("  First point. ", "   ", "Second point.")),
    )

    summary, key_points, *_ = summary_columns(analysis)
    assert summary == "Leave policy."
    assert key_points == ["First point.", "Second point."]


@WRITERS
def test_the_summary_model_is_cut_to_the_column(document, write):
    long_name = "m" * (NAME_MAX_LENGTH + 10)

    analysis = write(document, classification(summary=SUMMARY, key_points=KEY_POINTS, model=long_name))

    assert summary_columns(analysis)[3] == "m" * NAME_MAX_LENGTH


@pytest.mark.parametrize(
    ("words", "truncated"),
    [(MAXIMUM_SUMMARY_SECTIONS * CLASSIFICATION_INPUT_TOKENS + 1, True), (40, False)],
    ids=["past the last section", "one section"],
)
def test_summary_truncated_is_stored_as_the_reply_reports_it_for_the_text(document, words, truncated):
    """Through the suite's stub, which reports ``summary_truncated`` from the real sectioning
    function (apps/ai/testing.py): a text longer than MAXIMUM_SUMMARY_SECTIONS sections is stored
    as summarised from its first sections only."""
    ExtractedContent.objects.create(document=document, extracted_text="word " * words)

    analysis = classify_document_now(document)

    analysis.refresh_from_db()
    assert analysis.summary_truncated is truncated
    assert analysis.summary == stub_document_summary(document.title)
    assert analysis.key_points == list(STUB_KEY_POINTS)
    assert analysis.summary_model == STUB_CHAT_MODEL


# --- apply_summary: the backfill writes the five and nothing else -------------------------------


def test_apply_summary_writes_the_five_columns_and_nothing_else(document):
    """D-139, decision 4. The row is first given a value in as many other columns as the module can
    write, a person's edit and a rejection included; then a reply that differs in every one of them
    is applied with ``apply_summary``. Only the five change, the UPDATE names only the five, and
    nothing else in the database is written."""
    Tag.objects.create(tag_name="alpha project", dimension=PROJECT_DIMENSION)
    Tag.objects.create(tag_name="beta project", dimension=PROJECT_DIMENSION)
    apply_classification(
        document,
        classification(
            doc_type=REPORT, department="People",
            tags=[
                (PROJECT_DIMENSION, "beta project", ABOVE_THRESHOLD),  # linked
                (TOPIC_DIMENSION, "night shifts", ABOVE_THRESHOLD),  # proposed
                (TOPIC_DIMENSION, "budget planning", ABOVE_THRESHOLD),  # proposed, then rejected
                (PROCESS_DIMENSION, "unlisted process", ABOVE_THRESHOLD),  # discarded
            ],
            input_truncated=True, model="first-model", summary=SUMMARY, key_points=KEY_POINTS,
        ),
        scheme=scheme(departments=["Finance", "People"], project=["beta project"]),
    )
    reject_proposed_tag(document, TOPIC_DIMENSION, "budget planning")
    confirm_classification(document, doc_type=PROCEDURE)
    analysis = DocumentAnalysis.objects.get(document=document)
    # A time no run made, so the new one differs from it whatever the clock's resolution.
    long_ago = timezone.now() - datetime.timedelta(days=30)
    DocumentAnalysis.objects.filter(pk=analysis.pk).update(summarised_at=long_ago)

    analysis_before = row(DocumentAnalysis, analysis.pk)
    document_before = row(Document, document.pk)
    links_before = links_of(document)
    tags_before = list(Tag.objects.order_by("pk").values())
    departments_before = list(Department.objects.order_by("pk").values())
    # The row this test set up holds what it is meant to, so "unchanged" below means something.
    assert analysis_before["user_edited"] is True
    assert analysis_before["doc_type"] == PROCEDURE
    assert analysis_before["machine_doc_type"] == REPORT
    assert analysis_before["proposed_tags"] and analysis_before["discarded_suggestions"]
    assert analysis_before["rejected_tags"]
    assert document_before["department"] == "People"
    assert [link["tag_id"] for link in links_before] == [
        Tag.objects.get(tag_name="beta project").pk
    ]

    with CaptureQueriesContext(connection) as captured:
        apply_summary(
            document,
            classification(
                doc_type=POLICY, department="Finance",
                tags=[
                    (PROJECT_DIMENSION, "alpha project", ABOVE_THRESHOLD),
                    (TOPIC_DIMENSION, "another topic", ABOVE_THRESHOLD),
                ],
                input_truncated=False, model="second-model", summary=OTHER_SUMMARY,
                key_points=OTHER_KEY_POINTS, summary_truncated=True,
            ),
        )

    analysis_after = row(DocumentAnalysis, analysis.pk)
    changed = {column for column in analysis_before if analysis_before[column] != analysis_after[column]}
    assert changed == set(SUMMARY_FIELDS)
    assert analysis_after["summary"] == OTHER_SUMMARY
    assert analysis_after["key_points"] == list(OTHER_KEY_POINTS)
    assert analysis_after["summary_truncated"] is True
    assert analysis_after["summary_model"] == "second-model"
    assert analysis_after["summarised_at"] > long_ago
    # The document, its links, every tag and every department, byte for byte as before.
    assert row(Document, document.pk) == document_before
    assert links_of(document) == links_before
    assert list(Tag.objects.order_by("pk").values()) == tags_before
    assert list(Department.objects.order_by("pk").values()) == departments_before

    writes = [
        query["sql"] for query in captured.captured_queries
        if query["sql"].lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE"))
    ]
    [update] = writes  # one write, and only to the analysis row
    assert update.startswith('UPDATE "document_analysis" SET ')
    set_clause = update.split(" SET ", 1)[1].rsplit(" WHERE ", 1)[0]
    assert set(re.findall(r'"(\w+)" = ', set_clause)) == set(SUMMARY_FIELDS)


def test_apply_summary_on_a_document_with_no_analysis_raises_and_writes_nothing(document):
    document_before = row(Document, document.pk)

    with pytest.raises(NotOnThisDocument):
        apply_summary(document, classification(summary=SUMMARY, key_points=KEY_POINTS))

    assert not DocumentAnalysis.objects.filter(document=document).exists()
    assert row(Document, document.pk) == document_before


def test_apply_summary_on_a_document_deleted_meanwhile_raises(document):
    classified_without_a_summary(document)
    Document.objects.filter(pk=document.pk).delete()

    with pytest.raises(NotOnThisDocument):
        apply_summary(document, classification(summary=SUMMARY, key_points=KEY_POINTS))

    assert not DocumentAnalysis.objects.exists()


# --- summarise_document_now: what the backfill command calls ------------------------------------


def test_summarise_now_without_an_analysis_raises_before_any_provider_call(document, monkeypatch):
    ExtractedContent.objects.create(document=document, extracted_text=TEXT)
    service = install(monkeypatch, RecordingClassifier(result=classification(summary=SUMMARY)))

    with pytest.raises(NotOnThisDocument):
        summarise_document_now(document)

    assert service.classify_calls == []
    assert not DocumentAnalysis.objects.filter(document=document).exists()


@pytest.mark.parametrize("text", [None, "  \n\t "], ids=["no extracted text", "whitespace only"])
def test_summarise_now_without_text_raises_before_any_provider_call(document, monkeypatch, text):
    analysis = classified_without_a_summary(document)
    if text is not None:
        ExtractedContent.objects.create(document=document, extracted_text=text)
    service = install(monkeypatch, RecordingClassifier(result=classification(summary=SUMMARY)))

    with pytest.raises(InsufficientText):
        summarise_document_now(document)

    assert service.classify_calls == []
    assert summary_columns(analysis) == NO_SUMMARY


def test_summarise_now_calls_the_service_once_and_stores_only_the_summary(document, monkeypatch):
    """The latest text and the document's own scheme are sent, once; of the reply, only the summary
    is stored, and the classification on record is left as it was (D-139, decision 4)."""
    Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    analysis = classified_without_a_summary(document)
    classified_at = analysis.classified_at
    older = ExtractedContent.objects.create(document=document, extracted_text="The old extraction.")
    ExtractedContent.objects.create(document=document, extracted_text=TEXT)
    # Told apart by an explicit timestamp, not by creation order (Windows clock granularity).
    ExtractedContent.objects.filter(pk=older.pk).update(
        extracted_at=older.extracted_at - datetime.timedelta(days=1)
    )
    service = install(
        monkeypatch,
        RecordingClassifier(
            result=classification(
                doc_type=POLICY,
                tags=[(PROJECT_DIMENSION, "bridge maintenance", ABOVE_THRESHOLD)],
                model="second-model", summary=SUMMARY, key_points=KEY_POINTS,
            )
        ),
    )

    returned = summarise_document_now(document)

    [(title, text, sent_scheme)] = service.classify_calls
    assert (title, text) == (document.title, TEXT)
    assert sent_scheme == tag_scheme(document)
    returned.refresh_from_db()
    assert summary_columns(returned)[:4] == (SUMMARY, list(KEY_POINTS), False, "second-model")
    # The classification on record: still the earlier run's type, model and time, and no link.
    assert (returned.machine_doc_type, returned.doc_type) == (REPORT, REPORT)
    assert returned.doc_type_outcome == ASSIGNMENT_APPLIED
    assert returned.model != "second-model"
    assert returned.classified_at == classified_at
    assert links_of(document) == []


def test_summarise_now_during_a_provider_outage_propagates_and_writes_nothing(document, monkeypatch):
    ExtractedContent.objects.create(document=document, extracted_text=TEXT)
    analysis = run(document, summary=SUMMARY, key_points=KEY_POINTS, model="first-model")
    before = summary_columns(analysis)
    service = install(monkeypatch, RecordingClassifier(error=ProviderUnavailable("stub outage")))

    with pytest.raises(ProviderUnavailable):
        summarise_document_now(document)

    assert len(service.classify_calls) == 1
    assert summary_columns(analysis) == before
