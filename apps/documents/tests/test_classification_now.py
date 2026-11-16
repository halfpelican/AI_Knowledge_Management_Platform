"""``classify_document_now``: the orchestration the ingestion hook and the route will call (D-105).

It reads the latest extracted text, builds the scheme once, calls the provider exactly once with
that scheme, and applies the reply against the same scheme. No live provider: the service is a
recording fake installed through ``apps.ai.get_ai_service``, the way the suite's stub is.
"""

import datetime

import pytest

import apps.ai
from apps.ai.base import ProviderUnavailable
from apps.core.constants import ASSIGNMENT_APPLIED, PROJECT_DIMENSION, SOURCE_TYPES
from apps.documents.classification import InsufficientText, classify_document_now, tag_scheme
from apps.documents.models import ContentTag, Department, DocumentAnalysis, ExtractedContent, Tag

from .classification_builders import ABOVE_THRESHOLD, POLICY, RecordingClassifier, classification

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
TEXT = "Leave requests need a manager's approval. Annual leave accrues monthly."


def install(monkeypatch, service):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
    return service


def test_a_document_with_no_extracted_text_raises_before_any_provider_call(document, monkeypatch):
    service = install(monkeypatch, RecordingClassifier(result=classification()))
    with pytest.raises(InsufficientText):
        classify_document_now(document)
    assert service.classify_calls == []
    assert not DocumentAnalysis.objects.filter(document=document).exists()


def test_whitespace_only_extracted_text_is_insufficient_too(document, monkeypatch):
    ExtractedContent.objects.create(document=document, extracted_text="  \n\t ")
    service = install(monkeypatch, RecordingClassifier(result=classification()))
    with pytest.raises(InsufficientText):
        classify_document_now(document)
    assert service.classify_calls == []


def test_the_service_is_called_exactly_once_with_the_scheme_the_result_is_then_applied_against(
    document, monkeypatch
):
    ExtractedContent.objects.create(document=document, extracted_text=TEXT)
    Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    Department.objects.create(name="Finance")  # the list is the scheme's departments (D-129)
    document.department = "Finance"
    document.save(update_fields=["department"])
    service = install(
        monkeypatch,
        RecordingClassifier(
            result=classification(
                doc_type=POLICY, type_confidence=ABOVE_THRESHOLD,
                department="Finance", department_confidence=ABOVE_THRESHOLD,
                tags=[(PROJECT_DIMENSION, "bridge maintenance", ABOVE_THRESHOLD)],
            )
        ),
    )

    analysis = classify_document_now(document)

    assert len(service.classify_calls) == 1
    title, text, scheme = service.classify_calls[0]
    assert (title, text) == (document.title, TEXT)
    assert scheme == tag_scheme(document)
    assert "bridge maintenance" in scheme.tags[PROJECT_DIMENSION]
    assert "Finance" in scheme.departments
    # Applied against that scheme: the department and the tag were both in it.
    assert (analysis.doc_type, analysis.doc_type_outcome) == (POLICY, ASSIGNMENT_APPLIED)
    assert analysis.department_outcome == ASSIGNMENT_APPLIED
    link = ContentTag.objects.get(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)
    assert link.tag.tag_name == "bridge maintenance"
    assert DocumentAnalysis.objects.filter(document=document).count() == 1


def test_the_latest_extracted_content_is_the_text_sent(document, monkeypatch):
    older = ExtractedContent.objects.create(document=document, extracted_text="The old extraction.")
    ExtractedContent.objects.create(document=document, extracted_text=TEXT)
    # Told apart by an explicit timestamp, not by creation order (Windows clock granularity).
    ExtractedContent.objects.filter(pk=older.pk).update(
        extracted_at=older.extracted_at - datetime.timedelta(days=1)
    )
    service = install(monkeypatch, RecordingClassifier(result=classification()))
    classify_document_now(document)
    assert service.classify_calls[0][1] == TEXT


def test_a_provider_outage_propagates_and_writes_nothing(document, monkeypatch):
    ExtractedContent.objects.create(document=document, extracted_text=TEXT)
    service = install(monkeypatch, RecordingClassifier(error=ProviderUnavailable("stub outage")))
    with pytest.raises(ProviderUnavailable):
        classify_document_now(document)
    assert len(service.classify_calls) == 1
    assert not DocumentAnalysis.objects.filter(document=document).exists()
    document.refresh_from_db()
    assert document.department == ""
