"""FR-08 extraction, through the upload endpoint (proposal sections 7.4 and 7.8).

    Business logic (extraction): the file is routed to a format-appropriate parser.
    The original file and the extracted plain text are stored separately, so that
    the text can be reused for search and AI processing without re-parsing.

    Responses: ... 422 Unprocessable Entity where no text can be extracted.

The parser-level tests are in ``apps/ingestion/tests/test_extraction.py``. These
exercise the same four parsers through a real request, against the committed corpus,
and assert what ends up in the database.
"""

import pytest

from apps.core.constants import DOCUMENT_EXTRACTION_FAILED
from apps.documents.models import Document, ExtractedContent
from apps.ingestion.tests.fixtures.build_fixtures import MARKER_SENTENCE

UPLOAD_URL = "/api/documents"

pytestmark = pytest.mark.django_db


def post_upload(client, upload_file, **fields):
    body = {"file": upload_file, "title": "Leave Policy 2026", **fields}
    return client.post(UPLOAD_URL, body, format="multipart")


# --- The four parsers, end to end -----------------------------------------------------


@pytest.mark.parametrize("fixture_name", ["sample.pdf", "sample.docx", "sample.xlsx", "sample.txt"])
def test_text_is_extracted_from_each_format(session_client, upload, fixture_name):
    """One sentence appears in all four fixture files, so one assertion covers every
    parser: pypdf, python-docx, openpyxl and the direct read."""
    response = post_upload(session_client.client, upload(fixture_name))

    assert response.status_code == 201, response.data
    document = Document.objects.get(pk=response.data["doc_id"])
    extracted = ExtractedContent.objects.get(document=document)
    # Whitespace differs by parser — a PDF wraps at the page width, XLSX joins cells
    # — so the comparison is made on collapsed whitespace, not character for
    # character.
    assert MARKER_SENTENCE in " ".join(extracted.extracted_text.split())
    assert extracted.extracted_at is not None


def test_docx_table_text_is_extracted(employee_client, upload):
    """A policy's approval limits are usually in a table. sample.docx keeps the
    marker sentence in a table cell and nowhere else, so a parser that reads only
    paragraphs fails this test — which is the point of putting it there."""
    response = post_upload(employee_client, upload("sample.docx"))

    extracted = ExtractedContent.objects.get(document_id=response.data["doc_id"])
    assert MARKER_SENTENCE in " ".join(extracted.extracted_text.split())
    assert "Threshold" in extracted.extracted_text  # the table's header row


def test_xlsx_cached_formula_values_not_formula_source(employee_client, upload):
    extracted_text = ExtractedContent.objects.get(
        document_id=post_upload(employee_client, upload("sample.xlsx")).data["doc_id"]
    ).extracted_text
    assert "Delegations" in extracted_text  # the sheet name
    assert "=" not in extracted_text.split("Delegations", 1)[1][:200]


# --- The original and the text are stored separately -----------------------------------


def test_the_original_and_its_text_are_stored_separately(employee_client, upload, corpus):
    """FR-08: "so that the text can be reused for search and AI processing without
    re-parsing". Both must survive, and the original must be byte-identical to what
    was uploaded — a parser must never write back over it."""
    response = post_upload(employee_client, upload("sample.pdf"))

    document = Document.objects.get(pk=response.data["doc_id"])
    with document.file_path.open("rb") as stored:
        assert stored.read() == (corpus / "sample.pdf").read_bytes()
    assert ExtractedContent.objects.filter(document=document).exists()
    # The extracted text lives in its own table, not on the document row.
    assert not hasattr(document, "extracted_text")


# --- 422: no text could be extracted ---------------------------------------------------


def test_a_pdf_with_no_text_layer_is_unprocessable(session_client, upload):
    """The scanned-document case. The PDF is valid and the parser reads it without
    error; there is simply no text. Section 7.8 keeps the file and records why."""
    response = post_upload(session_client.client, upload("no_text.pdf"))

    assert response.status_code == 422
    document = Document.objects.get(pk=response.data["doc_id"])
    assert document.status == DOCUMENT_EXTRACTION_FAILED
    # CLAUDE.md invariant 8: a failed step never discards the source.
    assert document.file_path.storage.exists(document.file_path.name)
    assert not ExtractedContent.objects.filter(document=document).exists()


def test_a_corrupt_file_of_an_accepted_format_is_unprocessable(session_client, upload):
    """corrupt.docx is a real ZIP declaring the Word content type, so it passes the
    signature check and reaches python-docx, which raises. The vendor exception must
    become a 422, never a 500."""
    response = post_upload(session_client.client, upload("corrupt.docx"))

    assert response.status_code == 422
    document = Document.objects.get(pk=response.data["doc_id"])
    assert document.status == DOCUMENT_EXTRACTION_FAILED
    assert document.file_path.storage.exists(document.file_path.name)
    assert not ExtractedContent.objects.filter(document=document).exists()


def test_the_unprocessable_response_still_carries_the_document(employee_client, upload):
    """FR-08's interface shows a "Processing failed. Please try again" action against
    the document, so the client needs the id and the status even on the 422."""
    response = post_upload(employee_client, upload("no_text.pdf"))

    assert response.data["doc_id"]
    assert response.data["status"] == DOCUMENT_EXTRACTION_FAILED
    assert response.data["detail"]


def test_a_failed_extraction_still_occupies_its_content_hash(employee_client, upload):
    """The record is committed, so a second upload of the same bytes is the ordinary
    409 rather than a second attempt. Re-processing an existing document is FR-15's
    business, not a repeat upload's."""
    assert post_upload(employee_client, upload("no_text.pdf")).status_code == 422

    assert post_upload(employee_client, upload("no_text.pdf")).status_code == 409
    assert Document.objects.count() == 1
