"""FR-10's document summary as the routes write it (D-139).

FR-10: "A single structured request issued at upload returns the classification, the summary and
key points, and the tag assignments together". So the upload's 201 and the classify route's 200
carry the summary in the classification object, the document detail then returns it, and
``GET /api/search`` carries it on that document's result. Each test runs from an Employee session
and from an Administrator session (``session_client``; CLAUDE.md section 8 item 2), and the one
about scope uses both roles' clients.

apps/api/tests/test_document_classification.py and test_search.py test what the replies show of a
summary written straight through the ORM; this file tests that the routes write one.

No live provider: the suite's stub answers ``classify_document`` with
``stub_document_summary(title)`` and STUB_KEY_POINTS (apps/ai/testing.py).
"""

import pytest

from apps.ai.base import ProviderUnavailable
from apps.ai.testing import STUB_CHAT_MODEL, STUB_KEY_POINTS, stub_document_summary
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    ROLE_NAMES,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document, DocumentAnalysis, ExtractedContent
from apps.documents.tests.classification_builders import classification

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
SEARCH_URL = "/api/search"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
# In sample.txt's text ("at least fourteen days before the intended start date") and in no title
# used here, so a search for it finds the uploaded document by its passage.
TERM_IN_TEXT = "fourteen"
TEXT = "Employees may request annual leave in writing. Approval rests with the manager."
NO_SUMMARY = ("", [], False)


def upload_sample(client, upload, title, **fields):
    return client.post(
        DOCUMENTS_URL, {"file": upload("sample.txt"), "title": title, **fields}, format="multipart"
    )


def make_document(user, title):
    """A stored, indexed document with extracted text and no classification, readable by both roles."""
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=list(ROLE_NAMES),
    )
    ExtractedContent.objects.create(document=document, extracted_text=TEXT)
    return document


def classify(client, doc_id):
    return client.post(f"{DOCUMENTS_URL}/{doc_id}/classify", {}, format="json")


def detail(client, doc_id):
    return client.get(f"{DOCUMENTS_URL}/{doc_id}")


def summary_of(obj):
    """The three summary keys of a classification object or a search result."""
    return obj["summary"], obj["key_points"], obj["summary_truncated"]


def stub_summary(title):
    return stub_document_summary(title), list(STUB_KEY_POINTS), False


def search_result(client, term, doc_id):
    """The one document result of a search that is ``doc_id``'s."""
    response = client.get(SEARCH_URL, {"q": term})
    assert response.status_code == 200, response.content
    [result] = [
        result for result in response.json()["documents"]["results"]
        if result["source_id"] == str(doc_id)
    ]
    return result


def outage(title, text, scheme):
    raise ProviderUnavailable("stub outage")


def test_the_upload_201_carries_the_summary_and_the_detail_and_search_then_return_it(
    session_client, upload
):
    client = session_client.client
    title = "Leave and purchasing"

    response = upload_sample(client, upload, title)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == DOCUMENT_INDEXED
    assert summary_of(body["classification"]) == stub_summary(title)
    shown = detail(client, body["doc_id"])
    assert shown.status_code == 200, shown.content
    assert summary_of(shown.json()["classification"]) == stub_summary(title)
    assert summary_of(search_result(client, TERM_IN_TEXT, body["doc_id"])) == stub_summary(title)
    # Stored with the model that wrote it and when, which no reply carries (D-139).
    analysis = DocumentAnalysis.objects.get(document_id=body["doc_id"])
    assert analysis.summary_model == STUB_CHAT_MODEL
    assert analysis.summarised_at == analysis.classified_at
    for raw in (response.content, shown.content):
        assert b"summary_model" not in raw and b"summarised_at" not in raw


def test_the_classify_route_200_carries_the_summary_and_a_second_run_replaces_it(
    session_client, stub_ai_service
):
    """The detail page's classify updates the summary it shows from this reply (the contract's
    section 7), so a second run's summary must be in the second reply and then in the detail."""
    client = session_client.client
    document = make_document(session_client.user, "Quarantine handbook")

    first = classify(client, document.id)

    assert first.status_code == 200, first.content
    assert summary_of(first.json()["classification"]) == stub_summary("Quarantine handbook")
    assert summary_of(detail(client, document.id).json()["classification"]) == stub_summary(
        "Quarantine handbook"
    )
    # Found by its title: this document has no passages.
    assert summary_of(search_result(client, "quarantine", document.id)) == stub_summary(
        "Quarantine handbook"
    )

    stub_ai_service.classification = classification(
        summary="A second summary.", key_points=("A second point.",), summary_truncated=True,
    )
    second = classify(client, document.id)

    assert second.status_code == 200, second.content
    replaced = ("A second summary.", ["A second point."], True)
    assert summary_of(second.json()["classification"]) == replaced
    assert summary_of(detail(client, document.id).json()["classification"]) == replaced
    assert summary_of(search_result(client, "quarantine", document.id)) == replaced


def test_an_outage_at_upload_answers_201_with_the_document_stored_indexed_and_unclassified(
    session_client, upload, stub_ai_service
):
    """Invariant 8: a failed AI step never discards the source. The provider failing after its
    attempts leaves the document stored, extracted, chunked and Indexed, with no analysis row, so
    no summary, and the 201 carries ``classification: null``."""
    client = session_client.client
    stub_ai_service.classification = outage

    response = upload_sample(client, upload, "Leave and purchasing")

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["classification"] is None
    assert body["status"] == DOCUMENT_INDEXED
    assert len(stub_ai_service.classify_calls) == 1
    document = Document.objects.get(pk=body["doc_id"])
    assert document.status == DOCUMENT_INDEXED
    assert ExtractedContent.objects.filter(document=document).exists()
    assert ContentChunk.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk).exists()
    assert not DocumentAnalysis.objects.filter(document=document).exists()
    assert detail(client, document.id).json()["classification"] is None
    # Searchable by its passage, and carrying no summary.
    assert summary_of(search_result(client, TERM_IN_TEXT, document.id)) == NO_SUMMARY


def test_a_summary_written_at_upload_reaches_no_reader_outside_the_documents_scope(
    employee_client, administrator_client, upload
):
    """Invariant 1. An Administrator uploads an Administrator-only document, and the upload writes
    its summary. An Employee's detail of it is the scoped 404 and an Employee's search for its
    passage finds nothing, with no word of the summary in either body; the Administrator's search
    returns it with the summary, so a search that showed nobody anything could not pass."""
    title = "Board remuneration"
    response = upload_sample(
        administrator_client, upload, title, visible_to_roles=[ADMINISTRATOR_ROLE_NAME]
    )
    assert response.status_code == 201, response.content
    doc_id = response.json()["doc_id"]
    assert summary_of(response.json()["classification"]) == stub_summary(title)

    refused = detail(employee_client, doc_id)
    searched = employee_client.get(SEARCH_URL, {"q": TERM_IN_TEXT})

    assert refused.status_code == 404
    assert searched.status_code == 200
    assert searched.json()["documents"]["results"] == []
    for raw in (refused.content, searched.content):
        for trace in (stub_document_summary(title), "remuneration", *STUB_KEY_POINTS, doc_id):
            assert trace.encode() not in raw
    assert summary_of(search_result(administrator_client, TERM_IN_TEXT, doc_id)) == stub_summary(title)
