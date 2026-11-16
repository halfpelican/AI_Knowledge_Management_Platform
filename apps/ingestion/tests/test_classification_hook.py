"""FR-08's hand-off to FR-10 inside ingestion: section 7.8 step 4 (D-33 part 1, D-105).

FR-08 Business logic (classification): "on successful extraction the document is passed to FR-10
for classification. A failure of classification marks the document unclassified but never prevents
it reaching indexed status" (CLAUDE.md invariant 8). The hook runs after the extracted text is
written and before chunking, in its own savepoint, and nothing it raises reaches the ingestion
transaction. A reprocess runs the same pipeline and so reclassifies.

No live provider: the stub answers ``classify_document`` from the scheme (apps/ai/testing.py); a
test that needs a failure sets its ``classification`` attribute to a callable that raises.
"""

import logging

import pytest

from apps.ai.base import ProviderUnavailable
from apps.ai.testing import StubAIService
from apps.core.constants import (
    ASSIGNMENT_APPLIED,
    DOCUMENT_INDEXED,
    DOCUMENT_INDEXING_FAILED,
    DOCUMENT_TYPES,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_EMBED_ATTEMPTS,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    USER_APPLIED,
)
from apps.documents.models import ContentTag, Department, Document, DocumentAnalysis, Tag
from apps.ingestion.documents import ingest_and_index_document, reprocess_document
from apps.ingestion.signatures import compute_content_hash
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install
from apps.ingestion.tests.builders import upload, words

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("media_root")]

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
TEXT = words(120)
TITLE = "Leave Policy 2026"


def ingest(user, text=TEXT):
    file = upload(text.encode("utf-8"), "policy.txt")
    return ingest_and_index_document(
        uploaded_file=file,
        file_format="txt",
        content_hash=compute_content_hash(file),
        title=TITLE,
        department="People",
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
        uploaded_by=user,
    )


def test_a_successful_ingestion_classifies_the_document_in_the_same_transaction(
    employee, stub_ai_service
):
    Department.objects.create(name="People")  # the list is the scheme's departments (D-129)
    outcome = ingest(employee)

    assert (outcome.http_status, outcome.document.status) == (201, DOCUMENT_INDEXED)
    analysis = DocumentAnalysis.objects.get(document=outcome.document)
    assert outcome.analysis == analysis
    assert analysis.machine_doc_type == DOCUMENT_TYPES[0]
    assert analysis.doc_type_outcome == ASSIGNMENT_APPLIED
    # The upload's own department is listed, so in the scheme, and the stub's suggestion of it is
    # applied.
    assert (analysis.machine_department, analysis.department_outcome) == ("People", ASSIGNMENT_APPLIED)
    [(title, text, scheme)] = stub_ai_service.classify_calls
    assert (title, text) == (TITLE, TEXT)
    assert "People" in scheme.departments


def test_the_analysis_commits_with_the_document_or_not_at_all(employee, monkeypatch):
    """Invariant 9: the classification succeeded, then embedding crashed unexpectedly. The
    document rolls back, and the analysis written before it goes with it."""
    service = install(
        monkeypatch, ScriptedEmbedService(failures=1, error=RuntimeError("the client crashed"))
    )

    with pytest.raises(RuntimeError):
        ingest(employee)

    assert len(service.classify_calls) == 1  # classification ran, inside the transaction
    assert not Document.objects.exists()
    assert not DocumentAnalysis.objects.exists()


def test_a_provider_outage_leaves_the_document_indexed_and_unclassified(
    employee, stub_ai_service, caplog
):
    def outage(title, text, scheme):
        raise ProviderUnavailable("stub outage")

    stub_ai_service.classification = outage
    caplog.set_level(logging.INFO, logger="apps.ingestion.documents")

    outcome = ingest(employee)

    assert (outcome.http_status, outcome.document.status) == (201, DOCUMENT_INDEXED)
    assert outcome.analysis is None
    assert not DocumentAnalysis.objects.exists()
    assert Document.objects.get(pk=outcome.document.pk).status == DOCUMENT_INDEXED
    # An outage is an expected way to be left unclassified: recorded at INFO, never as the
    # WARNING with a traceback that marks a defect in classification.
    hook = [record for record in caplog.records if record.name == "apps.ingestion.documents"]
    assert [record.levelno for record in hook] == [logging.INFO]
    assert "ProviderUnavailable" in hook[0].getMessage()


def test_an_unexpected_classification_error_is_logged_and_swallowed(
    employee, stub_ai_service, caplog
):
    def defect(title, text, scheme):
        raise RuntimeError("a defect in classification")

    stub_ai_service.classification = defect
    caplog.set_level(logging.WARNING, logger="apps.ingestion.documents")

    outcome = ingest(employee)

    assert (outcome.http_status, outcome.document.status) == (201, DOCUMENT_INDEXED)
    assert not DocumentAnalysis.objects.exists()
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert any("unclassified" in record.getMessage() for record in warnings)
    assert any(
        record.exc_info and str(record.exc_info[1]) == "a defect in classification"
        for record in warnings
    )


def test_a_reprocess_reclassifies_and_keeps_a_confirmed_tag(employee, monkeypatch):
    # The first attempt classifies (the hook runs before embedding) and then fails to index.
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
    first = ingest(employee)
    assert (first.http_status, first.document.status) == (422, DOCUMENT_INDEXING_FAILED)
    document = first.document
    before = DocumentAnalysis.objects.get(document=document)

    # A person tags the document meanwhile.
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    confirmed = ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=USER_APPLIED, confirmed=True,
    )

    healthy = install(monkeypatch, StubAIService())
    outcome = reprocess_document(document)

    assert (outcome.http_status, outcome.document.status) == (201, DOCUMENT_INDEXED)
    assert len(healthy.classify_calls) == 1
    after = DocumentAnalysis.objects.get(document=document)
    assert after.pk == before.pk  # one row per document, updated
    assert outcome.analysis == after
    confirmed.refresh_from_db()
    assert (confirmed.applied_by, confirmed.confirmed, confirmed.provisional) == (USER_APPLIED, True, False)
    assert ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk).count() == 1
