"""A PDF bomb refused through POST /api/documents lands on "Too large to index" (D-81).

The function-level pipeline is covered in ``apps/ingestion/tests/test_pdf_bounds.py``; this
exercises the same refusal through a real request, from BOTH an Employee and an Administrator
session (``session_client``), since FR-08 lets both roles contribute (D-30). The document row
carries the seventh status, and because every D-81 bound lands on that one status, the front
end's ``canReprocess`` already refuses the retry for it — asserted in
``frontend/tests/documentStatus.test.js`` ("does not offer the retry for 'Too large to
index'"), which this test does not duplicate server-side beyond confirming the status string
those two agree on.

A new file rather than an edit to the existing upload tests, so it does not collide with the
owner of ``apps/api/`` working in the same worktree.
"""

import pytest

from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.ingestion.documents import pdf_bound_detail
from apps.ingestion.extraction import PDF_STREAM_TOO_LARGE_MESSAGE
from apps.ingestion.tests.builders import pdf_pages, repeated_operators

UPLOAD_URL = "/api/documents"

pytestmark = pytest.mark.django_db


def test_a_pdf_bomb_upload_is_too_large_to_index_from_either_role(session_client, monkeypatch):
    """A single stream over a lowered per-stream cap, uploaded as a real PDF. 422, the row's
    status is "Too large to index", and the message is the per-stream one so the uploader can
    tell it from the chunk-ceiling and extraction-failure cases."""
    monkeypatch.setattr("apps.ingestion.extraction.PDF_MAXIMUM_STREAM_BYTES", 4096)
    data = pdf_pages([repeated_operators(100_000)])  # ~400 KB decompressed, tiny file

    response = session_client.client.post(
        UPLOAD_URL,
        {"file": _upload(data), "title": "A large PDF"},
        format="multipart",
    )

    assert response.status_code == 422, response.data
    assert response.data["status"] == "Too large to index"
    # The status string the front end keys its refused-retry on (frontend/src/constants.js:
    # DOCUMENT_STATUS.tooLargeToIndex), so canReprocess refuses it on the screen. The detail
    # is this route's stored clause and then the per-stream limit sentence.
    assert response.data["detail"] == pdf_bound_detail(PDF_STREAM_TOO_LARGE_MESSAGE)
    assert response.data["detail"].startswith("The document was stored but not indexed. ")

    document = Document.objects.get(pk=response.data["doc_id"])
    assert document.status == "Too large to index"
    # The original is kept (invariant 8); nothing was indexed; the duplicate slot is released.
    assert document.file_path.storage.exists(document.file_path.name)
    assert not ContentChunk.objects.filter(source_id=document.id).exists()
    assert not ExtractedContent.objects.filter(document=document).exists()
    assert document.content_hash is None


def _upload(data: bytes):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("bomb.pdf", data, content_type="application/pdf")
