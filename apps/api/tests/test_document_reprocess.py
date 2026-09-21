"""FR-08's "Processing failed. Please try again" action (docs/decisions.md D-32).

    Once processing completes an "Indexed" status appears against the document; if
    extraction fails, a "Processing failed. Please try again" action is shown.

The action could not succeed as first built. Ingestion commits the document row on
every 422 path so the source survives a failed step (CLAUDE.md invariant 8), and
that row carried the content hash, so re-sending the same bytes met section 7.2's
duplicate check and was answered 409. D-32 settles both halves:

- a failed ingestion releases its content hash, so it reserves no duplicate slot;
- the retry re-runs ingestion against the original already under MEDIA_ROOT rather
  than re-uploading, so three attempts leave one row and not three.

Worth being plain about the proposal's own flaw here, which D-32 records: FR-08 ties
the action to extraction failing, but a scanned PDF with no text layer fails
identically however many times the same bytes are parsed. The retry can only really
recover an "Indexing failed" — a provider outage. The action is shown in every case
the clause names; only its wording stops promising what identical bytes cannot give.
"""

import pytest

from apps.core.constants import (
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_INDEXED,
    DOCUMENT_INDEXING_FAILED,
    DOCUMENT_INSUFFICIENT_CONTENT,
    MAXIMUM_EMBED_ATTEMPTS,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install

UPLOAD_URL = "/api/documents"

pytestmark = pytest.mark.django_db


def post_upload(client, upload_file, **fields):
    body = {"file": upload_file, "title": "Leave Policy 2026", **fields}
    return client.post(UPLOAD_URL, body, format="multipart")


def reprocess(client, doc_id):
    return client.post(f"{UPLOAD_URL}/{doc_id}/reprocess", {}, format="json")


def chunks_for(doc_id):
    return ContentChunk.objects.filter(source_type=SOURCE_TYPES[0], source_id=doc_id)


# --- A failed ingestion reserves no duplicate slot ------------------------------------


def test_a_failed_ingestion_releases_its_content_hash(employee_client, upload):
    response = post_upload(employee_client, upload("no_text.pdf"))

    assert response.status_code == 422
    document = Document.objects.get(pk=response.data["doc_id"])
    assert document.status == DOCUMENT_EXTRACTION_FAILED
    # The row survives, carrying the reason; only the duplicate slot is released.
    assert document.content_hash is None
    assert document.file_path.storage.exists(document.file_path.name)


def test_the_same_file_may_be_uploaded_again_after_a_failure(employee_client, upload):
    """Several failed attempts at one file coexist: Postgres permits many NULLs
    under a unique constraint, which is what makes this possible at all."""
    first = post_upload(employee_client, upload("no_text.pdf"))
    second = post_upload(employee_client, upload("no_text.pdf"))

    assert (first.status_code, second.status_code) == (422, 422)
    assert Document.objects.count() == 2


def test_an_indexed_document_still_occupies_its_hash(employee_client, upload):
    """The release is for failures only. A successful upload must still be caught by
    section 7.2's duplicate rule, or the check would protect nothing."""
    assert post_upload(employee_client, upload("sample.txt")).status_code == 201

    assert post_upload(employee_client, upload("sample.txt")).status_code == 409


# --- The retry re-runs ingestion on the stored original --------------------------------


def test_a_transient_indexing_failure_recovers_on_reprocess(
    monkeypatch, session_client, upload
):
    """The case the retry genuinely helps: the provider was down, and is now back.

    This is the whole point of D-32 — and of the "Indexing failed" status D-28
    restored, since the superseded vocabulary could not tell this apart from a
    document whose text could never be read.
    """
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
    failed = post_upload(session_client.client, upload("sample.txt"))
    assert failed.status_code == 422
    assert failed.data["status"] == DOCUMENT_INDEXING_FAILED
    doc_id = failed.data["doc_id"]

    install(monkeypatch, ScriptedEmbedService(failures=0))  # the provider recovers
    response = reprocess(session_client.client, doc_id)

    assert response.status_code == 201
    assert response.data["status"] == DOCUMENT_INDEXED
    assert chunks_for(doc_id).exists()
    # One row, not two: the retry read the stored original rather than re-uploading.
    assert Document.objects.count() == 1


def test_a_successful_reprocess_restores_the_content_hash(monkeypatch, employee_client, upload):
    """A document that reaches Indexed is protected by the duplicate check exactly
    as one indexed on the first attempt is."""
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
    doc_id = post_upload(employee_client, upload("sample.txt")).data["doc_id"]
    assert Document.objects.get(pk=doc_id).content_hash is None

    install(monkeypatch, ScriptedEmbedService(failures=0))
    assert reprocess(employee_client, doc_id).status_code == 201

    assert Document.objects.get(pk=doc_id).content_hash is not None
    # And the restored hash is doing its job.
    assert post_upload(employee_client, upload("sample.txt")).status_code == 409


def test_reprocess_replaces_the_previous_attempts_text_and_chunks(
    monkeypatch, employee_client, upload
):
    """A reprocess replaces its predecessor rather than adding to it. ContentChunks
    has no database foreign key (D-07), so nothing cascades: the rows are deleted
    explicitly or they accumulate."""
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
    doc_id = post_upload(employee_client, upload("sample.txt")).data["doc_id"]

    install(monkeypatch, ScriptedEmbedService(failures=0))
    assert reprocess(employee_client, doc_id).status_code == 201
    first_pass = set(chunks_for(doc_id).values_list("pk", flat=True))

    Document.objects.filter(pk=doc_id).update(status=DOCUMENT_INDEXING_FAILED)
    assert reprocess(employee_client, doc_id).status_code == 201

    assert ExtractedContent.objects.filter(document_id=doc_id).count() == 1
    assert set(chunks_for(doc_id).values_list("pk", flat=True)).isdisjoint(first_pass)


def test_reprocessing_an_unreadable_file_fails_the_same_way(employee_client, upload):
    """The proposal's own flaw, as a test. A scanned PDF has no text layer, so the
    retry FR-08 asks for cannot change the outcome — it returns the same 422 and the
    same status. The action exists, as the clause requires; what it cannot do is
    make identical bytes parse differently."""
    doc_id = post_upload(employee_client, upload("no_text.pdf")).data["doc_id"]

    response = reprocess(employee_client, doc_id)

    assert response.status_code == 422
    assert response.data["status"] == DOCUMENT_EXTRACTION_FAILED
    assert Document.objects.count() == 1


def test_reprocessing_a_short_document_fails_the_same_way(employee_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    tiny = SimpleUploadedFile("note.txt", b"Too short to index.", content_type="text/plain")
    doc_id = post_upload(employee_client, tiny).data["doc_id"]

    response = reprocess(employee_client, doc_id)

    assert response.status_code == 422
    assert response.data["status"] == DOCUMENT_INSUFFICIENT_CONTENT


# --- Refusals --------------------------------------------------------------------------


def test_reprocessing_an_indexed_document_is_refused(session_client, upload):
    """Re-indexing healthy content is FR-15's business, not a retry's."""
    doc_id = post_upload(session_client.client, upload("sample.txt")).data["doc_id"]

    response = reprocess(session_client.client, doc_id)

    assert response.status_code == 409


def test_a_document_outside_the_callers_scope_is_not_found(
    administrator_client, employee_client, upload
):
    """404, not 403: a 403 would confirm the id names something real."""
    doc_id = post_upload(
        administrator_client, upload("no_text.pdf"), visible_to_roles=["Administrator"]
    ).data["doc_id"]

    assert reprocess(employee_client, doc_id).status_code == 404


def test_an_anonymous_reprocess_is_unauthorised(api_client, administrator_client, upload):
    doc_id = post_upload(administrator_client, upload("no_text.pdf")).data["doc_id"]

    assert reprocess(api_client, doc_id).status_code == 401


def test_a_role_without_contribute_content_cannot_reprocess(
    employee, employee_client, administrator_client, upload
):
    from apps.accounts.models import RolePermission

    doc_id = post_upload(administrator_client, upload("no_text.pdf")).data["doc_id"]
    RolePermission.objects.filter(
        role=employee.role, permission__permission_name="contribute_content"
    ).delete()

    assert reprocess(employee_client, doc_id).status_code == 403


def test_reprocess_collides_when_an_indexed_copy_now_exists(
    monkeypatch, administrator_client, upload
):
    """Restoring the hash can collide, if the same file was uploaded and indexed
    while this one sat failed. 409 is the truthful answer: an indexed copy exists."""
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
    failed_id = post_upload(administrator_client, upload("sample.txt")).data["doc_id"]

    install(monkeypatch, ScriptedEmbedService(failures=0))
    assert post_upload(administrator_client, upload("sample.txt")).status_code == 201

    response = reprocess(administrator_client, failed_id)

    assert response.status_code == 409
    # The failed document is untouched, not half-reprocessed.
    assert Document.objects.get(pk=failed_id).status == DOCUMENT_INDEXING_FAILED
