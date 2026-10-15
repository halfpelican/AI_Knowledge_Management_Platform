"""FR-15's download: ``GET /api/documents/{id}/download`` (D-75), with D-76's headers on it.

FR-15: "Selecting a document opens a detail view showing its metadata, extracted content, and a
download link." D-75 settles the route: scoped through ``scoped_documents`` exactly as the detail
view is, 404 and never 403 outside scope, every status downloadable, the original returned by
``FileResponse`` as an attachment, typed by the format its signature proved and named by its stored
name with the last extension corrected to that format. A document with no file is the same 404 as
one outside scope, logged on the server, and an out-of-scope document logs nothing.

Every role-dependent test runs from an Employee session and from an Administrator session
(``session_client``), so the route stays inside the dual-role matrix (CLAUDE.md section 8).

**Every response is read to the end.** A ``FileResponse`` holds the stored file open until it is
closed, and Windows will not delete a file another handle holds. Reading a streamed response to
the end is what closes it: the test client wraps the stream so the response's ``close()`` runs when
it is exhausted, with Django's ``close_old_connections`` disconnected. A bare ``response.close()``
in a test does not disconnect it, so the ``request_finished`` signal it sends closes the test's
database connection in the middle of its transaction; that was measured, not assumed.
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_STATUS_VALUES,
    EMPLOYEE_ROLE_NAME,
)
from apps.documents.models import Document
from apps.retrieval.tests.scopes import unreadable_scope
from conftest import FIXTURE_CORPUS

pytestmark = pytest.mark.django_db

BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
# The download view's module logger, where a missing original is reported (D-75).
VIEW_LOGGER = "apps.api.views"

# What a browser sends when it follows a link: its navigation Accept header.
BROWSER_NAVIGATION_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

# D-75's table, written out rather than imported, so a typo in the constant fails here.
EXPECTED_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "txt": "text/plain; charset=utf-8",
}
# What add_never_cache_headers sets (D-76).
NEVER_CACHE_DIRECTIVES = {"max-age=0", "no-cache", "no-store", "must-revalidate", "private"}

TITLE = "Harbour lease schedule"
STORED_NAME = "harbour_lease.pdf"
STORED_BYTES = b"%PDF-1.4\n% the harbour lease schedule, as stored\n"

# Prose long enough to index (MINIMUM_CONTENT_LENGTH is 50 tokens), so an upload of it is a 201
# and the premise "the server accepted it as txt" is the upload's own answer.
PROSE = (
    "The third quarter budget holds operating costs flat against the second quarter, moves two "
    "contractor roles into the permanent establishment, and defers the depot refit to the new "
    "financial year. Travel is capped at the approved ceiling, and every variance above five per "
    "cent is reported to the finance committee with a short explanation and a recovery plan. "
)
# D-75's two named cases: UTF-8 text that would run or render under the name it was uploaded with.
VBSCRIPT = ("MsgBox \"Q3 budget\"\r\n" + "".join(f"' {line}\r\n" for line in PROSE.split(". "))).encode()
HTML = (
    "<!DOCTYPE html><html><body><p>" + PROSE + "</p>"
    "<script>document.title = 'rendered, not downloaded';</script></body></html>"
).encode()


@dataclass
class Download:
    response: object
    body: bytes


def read_to_the_end(response) -> bytes:
    """The whole body; for a streamed response, reading it to the end also closes it (see the
    module docstring)."""
    if response.streaming:
        return b"".join(response.streaming_content)
    return response.content


def download(client, document_id, **extra) -> Download:
    response = client.get(f"/api/documents/{document_id}/download", **extra)
    return Download(response, read_to_the_end(response))


def cache_directives(response) -> set[str]:
    return {directive.strip() for directive in response["Cache-Control"].split(",")}


def stored_document(uploader, *, roles=None, status=None, title=TITLE, name=STORED_NAME, content=STORED_BYTES):
    """A pdf document with a stored original, as an upload leaves one."""
    document = Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=uploader,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
        **({"status": status} if status else {}),
    )
    document.file_path.save(name, ContentFile(content), save=True)
    return document


def document_without_a_file(uploader, *, roles=None):
    """A row with a blank ``file_path``: no shipped path makes one, and a script can (D-75)."""
    return Document.objects.create(
        title="Unfiled minutes", file_type="pdf", uploaded_by=uploader,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )


def upload(client, name, content):
    """``POST /api/documents``, the real upload path, with the suite's stub AI provider."""
    return client.post(
        "/api/documents",
        {"file": SimpleUploadedFile(name, content, content_type="application/octet-stream"),
         "title": f"Uploaded as {name}"},
        format="multipart",
    )


def view_records(caplog):
    return [record for record in caplog.records if record.name == VIEW_LOGGER]


# --- 200: each format, uploaded and downloaded through the routes -------------------------------


@pytest.mark.parametrize("fixture_name", ["sample.pdf", "sample.docx", "sample.xlsx", "sample.txt"])
def test_each_format_downloads_as_the_stored_original_byte_for_byte(session_client, fixture_name):
    original = (FIXTURE_CORPUS / fixture_name).read_bytes()
    uploaded = upload(session_client.client, fixture_name, original)
    file_format = fixture_name.removeprefix("sample.")
    assert uploaded.status_code == 201, uploaded.json()
    assert uploaded.json()["file_type"] == file_format  # the premise: the signature's format

    result = download(session_client.client, uploaded.json()["doc_id"])

    assert result.response.status_code == 200
    assert result.body == original
    assert int(result.response["Content-Length"]) == len(original)
    assert result.response["Content-Type"] == EXPECTED_CONTENT_TYPES[file_format]
    assert result.response["Content-Disposition"] == f'attachment; filename="{fixture_name}"'
    # nosniff is what makes the Content-Type binding (D-75); no-store is D-76.
    assert result.response["X-Content-Type-Options"] == "nosniff"
    assert cache_directives(result.response) == NEVER_CACHE_DIRECTIVES
    assert "Expires" in result.response


# --- The name and the type come from the signature, never from the uploaded name ------------------


@pytest.mark.parametrize(
    ("uploaded_as", "content", "proven", "downloads_as"),
    [
        # D-75's two security cases. The server never reads the extension, so both are accepted
        # as txt; served under their own names they would run or render on a colleague's machine.
        ("Q3_budget.vbs", VBSCRIPT, "txt", "Q3_budget.txt"),
        ("invoice.html", HTML, "txt", "invoice.txt"),
        # Only the last extension is replaced.
        ("report.pdf.exe", PROSE.encode(), "txt", "report.pdf.txt"),
        # An extension that already agrees, in any case, is kept.
        ("Report.PDF", (FIXTURE_CORPUS / "sample.pdf").read_bytes(), "pdf", "Report.PDF"),
        # None at all: one is added.
        ("minutes", (FIXTURE_CORPUS / "sample.docx").read_bytes(), "docx", "minutes.docx"),
        # A genuine PDF called notes.txt is a PDF (FR-08), and downloads as one.
        ("notes.txt", (FIXTURE_CORPUS / "sample.pdf").read_bytes(), "pdf", "notes.pdf"),
    ],
    ids=["vbs", "html", "double-extension", "upper-case", "no-extension", "pdf-named-txt"],
)
def test_a_download_is_named_and_typed_by_its_signature_not_by_its_uploaded_name(
    session_client, uploaded_as, content, proven, downloads_as
):
    """Uploaded through the real ``POST /api/documents``, so the path that accepts a ``.vbs`` or an
    ``.html`` file as text is the path exercised, not a row made to look like one."""
    uploaded = upload(session_client.client, uploaded_as, content)
    assert uploaded.status_code == 201, uploaded.json()
    assert uploaded.json()["file_type"] == proven
    stored = Document.objects.get(pk=uploaded.json()["doc_id"])
    assert Path(stored.file_path.name).name == uploaded_as  # stored under the name it came with

    result = download(session_client.client, stored.pk)

    assert result.response.status_code == 200
    assert result.body == content
    assert result.response["Content-Disposition"] == f'attachment; filename="{downloads_as}"'
    assert result.response["Content-Type"] == EXPECTED_CONTENT_TYPES[proven]
    assert result.response["X-Content-Type-Options"] == "nosniff"


# --- Scope: 404 and never 403, from the same lookup as the detail view -----------------------------


def test_an_administrator_only_document_is_an_employees_unknown_id_and_the_administrators_file(
    employee_client, administrator_client, administrator
):
    document = stored_document(administrator, roles=[ADMINISTRATOR_ROLE_NAME])

    withheld = download(employee_client, document.id)
    unknown = download(employee_client, uuid.uuid4())

    assert withheld.response.status_code == unknown.response.status_code == 404
    assert withheld.body == unknown.body
    # The contract's body (docs/api-contract.md, FR-15, "A 404 body").
    assert withheld.response.json() == {"detail": "No Document matches the given query."}
    assert STORED_BYTES not in withheld.body and TITLE.encode() not in withheld.body

    admitted = download(administrator_client, document.id)
    assert admitted.response.status_code == 200
    assert admitted.body == STORED_BYTES


def test_an_employee_only_document_downloads_for_both_roles(session_client, employee):
    """D-66: Administrator generalises Employee in scope, so an Employee-only original is the
    Administrator's to download too."""
    document = stored_document(employee, roles=[EMPLOYEE_ROLE_NAME])

    result = download(session_client.client, document.id)

    assert result.response.status_code == 200
    assert result.body == STORED_BYTES


def test_unknown_and_out_of_scope_are_one_404_from_both_roles(session_client, administrator):
    """From each role, a document stamped with a scope it cannot read (``[Administrator]`` for the
    Employee, ``[]`` for the Administrator, D-66) is answered exactly as an id that names nothing."""
    restricted = stored_document(administrator, roles=unreadable_scope(session_client.role_name))

    withheld = download(session_client.client, restricted.id)
    unknown = download(session_client.client, uuid.uuid4())

    assert withheld.response.status_code == unknown.response.status_code == 404
    assert withheld.body == unknown.body
    assert STORED_BYTES not in withheld.body


def test_an_anonymous_download_is_401_whatever_it_accepts(api_client, employee):
    document = stored_document(employee)

    for extra in ({}, {"HTTP_ACCEPT": "application/pdf"}):
        result = download(api_client, document.id, **extra)
        assert result.response.status_code == 401
        assert result.response["WWW-Authenticate"] == "Session"
        assert STORED_BYTES not in result.body


@pytest.mark.parametrize("status", DOCUMENT_STATUS_VALUES)
def test_a_document_downloads_in_every_status(session_client, employee, status):
    """D-75 and D-52's note: the original is stored whether or not it was indexed, so a failed
    extraction is exactly when its uploader most needs it back."""
    document = stored_document(employee, status=status)

    result = download(session_client.client, document.id)

    assert result.response.status_code == 200
    assert result.body == STORED_BYTES


def test_the_stored_file_is_not_served_at_its_media_url(session_client, employee):
    """D-75: the link is this route, never ``file_path.url``, and ``config/urls.py`` serves nothing
    outside ``/api/``. ``static(MEDIA_URL)`` would serve every original to anyone with its path."""
    document = stored_document(employee)
    assert document.file_path.url.startswith("/media/")  # the premise: the path is guessable

    response = session_client.client.get(document.file_path.url)

    assert response.status_code == 404
    assert STORED_BYTES not in read_to_the_end(response)


# --- A missing original: the out-of-scope 404, logged; out of scope, nothing logged ----------------


def test_a_document_with_no_stored_original_is_the_out_of_scope_404_and_is_logged(
    session_client, employee, administrator, caplog, error_log_file
):
    unfiled = document_without_a_file(employee)
    restricted = stored_document(administrator, roles=unreadable_scope(session_client.role_name))
    out_of_scope = download(session_client.client, restricted.id)
    caplog.clear()

    missing = download(session_client.client, unfiled.id)

    assert out_of_scope.response.status_code == missing.response.status_code == 404
    assert missing.body == out_of_scope.body  # a real out-of-scope response, not a string
    [record] = view_records(caplog)
    assert record.levelno == logging.ERROR
    assert str(unfiled.id) in record.getMessage()
    assert "stored name ''" in record.getMessage()
    # And it reaches D-75's error file, not only the test's capture.
    assert str(unfiled.id) in error_log_file.read_text(encoding="utf-8")


def test_a_document_whose_file_is_gone_from_disk_is_the_out_of_scope_404_and_is_logged(
    session_client, employee, administrator, caplog, error_log_file
):
    """A delete committing between the lookup and the open, or a hand edit: the row stands and the
    file does not. Opened before the response is built, so this is a 404 and not a 500."""
    document = stored_document(employee)
    Path(document.file_path.path).unlink()
    restricted = stored_document(
        administrator, title="Restricted", name="restricted.pdf", content=b"%PDF-1.4 restricted",
        roles=unreadable_scope(session_client.role_name),
    )
    out_of_scope = download(session_client.client, restricted.id)
    caplog.clear()

    missing = download(session_client.client, document.id)

    assert out_of_scope.response.status_code == missing.response.status_code == 404
    assert missing.body == out_of_scope.body
    [record] = view_records(caplog)
    assert record.levelno == logging.ERROR
    assert str(document.id) in record.getMessage()
    assert repr(document.file_path.name) in record.getMessage()
    assert record.exc_info is not None and issubclass(record.exc_info[0], OSError)
    logged = error_log_file.read_text(encoding="utf-8")
    assert str(document.id) in logged and "FileNotFoundError" in logged


def test_an_out_of_scope_document_whose_file_is_also_missing_logs_nothing(
    session_client, administrator, caplog, error_log_file
):
    """Scope first, then the file (D-75). An out-of-scope document never reaches the file checks,
    so its missing file is neither reported to the caller nor logged: logging it would put the
    existence of a document the caller cannot see on record against their request."""
    scope = unreadable_scope(session_client.role_name)
    gone = stored_document(administrator, roles=scope)
    Path(gone.file_path.path).unlink()
    unfiled = document_without_a_file(administrator, roles=scope)

    caplog.clear()
    unknown = download(session_client.client, uuid.uuid4())
    logged_for_an_unknown_id = [(record.name, record.levelno) for record in caplog.records]

    for document in (gone, unfiled):
        caplog.clear()
        result = download(session_client.client, document.id)
        assert result.response.status_code == 404
        assert result.body == unknown.body
        # Exactly what an unknown id logs, which is Django's WARNING for any 404, and nothing more.
        assert [(record.name, record.levelno) for record in caplog.records] == logged_for_an_unknown_id
        assert view_records(caplog) == []
        assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert not error_log_file.exists() or error_log_file.read_text(encoding="utf-8") == ""


# --- Content negotiation: the Accept header is not consulted ----------------------------------------


@pytest.mark.parametrize(
    "accept",
    [BROWSER_NAVIGATION_ACCEPT, "application/pdf", "application/octet-stream", "text/html", "*/*"],
    ids=["browser-navigation", "pdf", "octet-stream", "html-only", "anything"],
)
def test_the_download_is_served_whatever_the_accept_header_asks_for(session_client, employee, accept):
    """A browser following the link sends its navigation header. A client naming the file's own
    type, ``Accept: application/pdf``, was answered 406 by DRF's negotiation before the view ran,
    because the API's only renderer is JSON; this route ignores the header (D-75's item notes)."""
    document = stored_document(employee)

    result = download(session_client.client, document.id, HTTP_ACCEPT=accept)

    assert result.response.status_code == 200
    assert result.body == STORED_BYTES
    assert result.response["Content-Type"] == EXPECTED_CONTENT_TYPES["pdf"]


def test_an_accept_header_naming_the_file_type_still_gets_the_json_404(session_client):
    asked_for_a_pdf = download(session_client.client, uuid.uuid4(), HTTP_ACCEPT="application/pdf")
    plain = download(session_client.client, uuid.uuid4())

    assert asked_for_a_pdf.response.status_code == 404
    assert asked_for_a_pdf.response["Content-Type"] == "application/json"
    assert asked_for_a_pdf.body == plain.body
