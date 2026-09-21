"""FR-08 upload endpoint: ``POST /api/documents`` and ``GET /api/documents``.

The rejection order is the proposal's section 7.2 ``validateUpload()`` — contribute
permission, then signature, then size, then title, then duplicate — and each code
below is quoted from FR-08's own Responses clause:

    201 Created with the document ID; 400 A Document title is required for empty
    titles; 415 Unsupported Media Type for a disallowed format; 413 Payload Too
    Large beyond the size limit; 409 Duplicate document exists for duplicate
    documents in the database. 422 Unprocessable Entity where no text can be
    extracted.

The 422 paths belong to extraction and indexing, which are later items of this
stage; they are tested where they are built.

Every protected endpoint is exercised from both an Employee and an Administrator
session (CLAUDE.md section 8 item 2), which is what ``session_client`` does.
"""

import uuid

import pytest
from django.urls import reverse

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    MAX_UPLOAD_BYTES,
    ROLE_NAMES,
)
from apps.documents.models import Document

UPLOAD_URL = "/api/documents"


def post_upload(client, upload_file, **fields):
    body = {"file": upload_file, "title": "Leave Policy 2026", **fields}
    return client.post(UPLOAD_URL, body, format="multipart")


# --- The happy path, from both roles -------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_name", ["sample.pdf", "sample.docx", "sample.xlsx", "sample.txt"])
def test_each_accepted_format_uploads(session_client, upload, fixture_name):
    """All four of D-15's formats are accepted, from either role."""
    response = post_upload(session_client.client, upload(fixture_name))

    assert response.status_code == 201, response.data
    # "201 Created with the document ID" — the client needs the id to poll status.
    assert uuid.UUID(str(response.data["doc_id"]))
    assert response.data["file_type"] == fixture_name.removeprefix("sample.")
    # Processing is synchronous (FR-08), so the request does not return until the
    # document is indexed. "Processing" is the status the row holds inside the
    # transaction and never one a caller can observe.
    assert response.data["status"] == DOCUMENT_INDEXED
    document = Document.objects.get(pk=response.data["doc_id"])
    assert document.uploaded_by == session_client.user
    # The original is stored, separately from any extracted text (FR-08, D-05).
    assert document.file_path.name
    assert document.file_path.storage.exists(document.file_path.name)
    assert document.file_size_bytes == document.file_path.size


@pytest.mark.django_db
def test_upload_stores_the_original_under_media_root(employee_client, upload, media_root):
    """No upload writes outside MEDIA_ROOT, whatever it claims to be called."""
    response = post_upload(employee_client, upload("sample.txt", name="../../escape.txt"))

    assert response.status_code == 201
    document = Document.objects.get(pk=response.data["doc_id"])
    stored = (media_root / document.file_path.name).resolve()
    assert stored.is_file()
    assert media_root.resolve() in stored.parents


# --- 415: the signature decides, not the extension ------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_name", ["disguised.pdf", "disguised_utf8.pdf"])
def test_executable_renamed_as_pdf_is_rejected(session_client, upload, fixture_name):
    """FR-08 Validation: the signature is inspected "rather than the extension alone,
    preventing a disguised file from being accepted".

    Both payloads are PE executables called .pdf. ``disguised_utf8.pdf`` is the one
    that matters: it decodes cleanly as UTF-8, so section 7.3's literal last rule
    would have admitted it as TXT.
    """
    response = post_upload(session_client.client, upload(fixture_name))

    assert response.status_code == 415
    assert "Accepted formats" in response.data["detail"]
    assert not Document.objects.exists()  # nothing is recorded for a refused upload


@pytest.mark.django_db
def test_a_genuine_pdf_renamed_as_txt_is_accepted_as_pdf(employee_client, upload):
    """The mirror of the case above: the extension lies in the harmless direction and
    the server still believes the bytes."""
    response = post_upload(employee_client, upload("sample.pdf", name="notes.txt"))

    assert response.status_code == 201
    assert response.data["file_type"] == "pdf"


@pytest.mark.django_db
def test_an_unrecognised_format_is_rejected(employee_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    # A GIF: a real format, with a real signature, that is not one of the four.
    gif = SimpleUploadedFile("photo.gif", b"GIF89a" + bytes(64), content_type="image/gif")
    response = post_upload(employee_client, gif)

    assert response.status_code == 415


# --- 413: the size ceiling ------------------------------------------------------------


@pytest.mark.django_db
def test_a_file_over_the_ceiling_is_rejected(employee_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    oversize = SimpleUploadedFile(
        "big.txt", b"a " * (MAX_UPLOAD_BYTES // 2 + 1), content_type="text/plain"
    )
    response = post_upload(employee_client, oversize)

    assert response.status_code == 413
    assert not Document.objects.exists()


@pytest.mark.django_db
def test_an_oversized_body_is_refused_before_it_is_parsed(employee_client, upload):
    """FR-08 wants the ceiling applied before the file is read into memory.

    A declared Content-Length past the ceiling is refused without the body being
    parsed at all, which is what stops a 50 MB transfer being buffered only to be
    thrown away. The body here is small; the header is what is being tested.
    """
    response = employee_client.post(
        UPLOAD_URL,
        {"file": upload("sample.txt"), "title": "Leave Policy 2026"},
        format="multipart",
        CONTENT_LENGTH=str(MAX_UPLOAD_BYTES + 1),
    )

    assert response.status_code == 413
    assert not Document.objects.exists()


# --- 400: the title ------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("title", ["", "   "])
def test_an_empty_title_is_rejected(employee_client, upload, title):
    """FR-08 Responses: "400 A Document title is required for empty titles"."""
    response = post_upload(employee_client, upload("sample.txt"), title=title)

    assert response.status_code == 400
    assert "title" in response.data


@pytest.mark.django_db
def test_a_missing_file_is_rejected(employee_client):
    response = employee_client.post(
        UPLOAD_URL, {"title": "Leave Policy 2026"}, format="multipart"
    )

    assert response.status_code == 400
    assert "file" in response.data


# --- 409: duplicates are compared by content -----------------------------------------


@pytest.mark.django_db
def test_the_same_bytes_under_a_different_name_are_a_duplicate(employee_client, upload):
    """Section 7.2: "Compared by content hash rather than by filename, so that the
    same document uploaded under two different names is still caught"."""
    assert post_upload(employee_client, upload("sample.txt")).status_code == 201

    response = post_upload(
        employee_client, upload("sample.txt", name="renamed.txt"), title="A different title"
    )

    assert response.status_code == 409
    assert Document.objects.count() == 1


@pytest.mark.django_db
def test_different_content_is_not_a_duplicate(employee_client, upload):
    assert post_upload(employee_client, upload("sample.txt")).status_code == 201
    assert post_upload(employee_client, upload("sample.pdf")).status_code == 201
    assert Document.objects.count() == 2


# --- 403: the contribute permission (D-30) --------------------------------------------


@pytest.mark.django_db
def test_a_role_without_contribute_content_cannot_upload(employee, employee_client, upload):
    """The gate is proven, not assumed: both seeded roles hold the permission, so the
    only way to show it is enforced is to take it away.

    Section 7.2 puts this check first, before the signature, size and title checks,
    which is why the payload below is a perfectly good file with a perfectly good
    title and still never reaches them.
    """
    from apps.accounts.models import RolePermission

    RolePermission.objects.filter(
        role=employee.role, permission__permission_name="contribute_content"
    ).delete()

    response = post_upload(employee_client, upload("sample.txt"))

    assert response.status_code == 403
    assert not Document.objects.exists()


@pytest.mark.django_db
def test_an_anonymous_upload_is_unauthorised(api_client, upload):
    response = post_upload(api_client, upload("sample.txt"))

    assert response.status_code == 401
    assert not Document.objects.exists()


# --- visible_to_roles at ingestion (D-29) ---------------------------------------------


@pytest.mark.django_db
def test_an_omitted_visibility_defaults_to_both_roles(session_client, upload):
    """A document nobody thought about is visible to everybody, so an omitted field
    can never accidentally hide content."""
    response = post_upload(session_client.client, upload("sample.txt"))

    assert response.status_code == 201
    assert response.data["visible_to_roles"] == list(ROLE_NAMES)


@pytest.mark.django_db
def test_visibility_may_be_narrowed_to_the_uploaders_own_role(administrator_client, upload):
    response = post_upload(
        administrator_client, upload("sample.txt"), visible_to_roles=[ADMINISTRATOR_ROLE_NAME]
    )

    assert response.status_code == 201
    assert response.data["visible_to_roles"] == [ADMINISTRATOR_ROLE_NAME]


@pytest.mark.django_db
def test_an_uploader_may_not_exclude_their_own_role(employee_client, upload):
    """D-29: uploading into a scope you cannot read is how content is lost."""
    response = post_upload(
        employee_client, upload("sample.txt"), visible_to_roles=[ADMINISTRATOR_ROLE_NAME]
    )

    assert response.status_code == 403
    assert not Document.objects.exists()


@pytest.mark.django_db
def test_an_empty_visibility_list_is_rejected(employee_client, upload):
    """"Visible to nobody" is not something anyone means to ask for, and FR-11 would
    filter such a document out of every search in silence."""
    response = employee_client.post(
        UPLOAD_URL,
        {"file": upload("sample.txt"), "title": "Leave Policy 2026", "visible_to_roles": ""},
        format="multipart",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_an_unknown_role_name_is_rejected(employee_client, upload):
    response = post_upload(
        employee_client, upload("sample.txt"), visible_to_roles=["Auditor"]
    )

    assert response.status_code == 400


# --- GET: the repository list ---------------------------------------------------------


@pytest.mark.django_db
def test_the_repository_list_is_scoped_to_the_callers_role(
    session_client, employee, upload
):
    """CLAUDE.md invariant 1: the existence of out-of-scope material is not disclosed,
    "not by a result count, a total, or an error message"."""
    Document.objects.create(
        title="Board minutes",
        file_type="pdf",
        uploaded_by=employee,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )
    Document.objects.create(
        title="Leave policy",
        file_type="pdf",
        uploaded_by=employee,
        visible_to_roles=list(ROLE_NAMES),
    )

    response = session_client.client.get(UPLOAD_URL)

    assert response.status_code == 200
    titles = {row["title"] for row in response.data}
    if session_client.role_name == EMPLOYEE_ROLE_NAME:
        assert titles == {"Leave policy"}
        assert len(response.data) == 1  # the count discloses nothing either
    else:
        assert titles == {"Leave policy", "Board minutes"}


@pytest.mark.django_db
def test_an_anonymous_caller_cannot_read_the_repository(api_client):
    assert api_client.get(UPLOAD_URL).status_code == 401


@pytest.mark.django_db
def test_an_uploaded_document_appears_in_the_list(employee_client, upload):
    post_upload(employee_client, upload("sample.txt"), title="Leave Policy 2026")

    response = employee_client.get(UPLOAD_URL)

    assert [row["title"] for row in response.data] == ["Leave Policy 2026"]
    # The stored path and the content hash are internal and never published: one is
    # a path inside MEDIA_ROOT, the other would let a caller probe whether a document
    # they cannot see has already been uploaded.
    assert "file_path" not in response.data[0]
    assert "content_hash" not in response.data[0]


# --- The order of the rejections is itself the contract (section 7.2) -----------------
#
# Every test above varies one condition at a time, which is how the view came to
# report 400 for a blank title on a request whose file was a disguised binary while
# a comment claimed section 7.2's order. The order was asserted in prose and not in
# code, and nothing caught it until the requirements audit of 2026-09-21. These
# combine conditions, so the order is pinned by a test and not by a docstring.
#
# Section 7.2 lines 6-32, in its own sequence: contribute permission (403), then
# signature (415), then size (413), then title (400), then duplicate (409).


@pytest.mark.django_db
def test_a_disguised_file_is_415_even_with_a_blank_title(employee_client, upload):
    """415 before 400: the file is refused on its content before the form is read."""
    response = post_upload(employee_client, upload("disguised.pdf"), title="")

    assert response.status_code == 415


@pytest.mark.django_db
def test_an_oversized_file_is_413_even_with_a_blank_title(employee_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    oversize = SimpleUploadedFile(
        "big.txt", b"a " * (MAX_UPLOAD_BYTES // 2 + 1), content_type="text/plain"
    )

    response = post_upload(employee_client, oversize, title="")

    assert response.status_code == 413


@pytest.mark.django_db
def test_a_disguised_file_is_415_even_with_an_unknown_role(employee_client, upload):
    response = post_upload(
        employee_client, upload("disguised.pdf"), visible_to_roles=["Auditor"]
    )

    assert response.status_code == 415


@pytest.mark.django_db
def test_the_permission_is_refused_before_the_file_is_even_looked_at(
    employee, employee_client, upload
):
    """403 before everything. Section 7.2 puts it first and says why: "it is the
    cheapest rejection, and the user's role may have changed during a transfer of up
    to 50 MB". A disguised binary with a blank title still gets the 403."""
    from apps.accounts.models import RolePermission

    RolePermission.objects.filter(
        role=employee.role, permission__permission_name="contribute_content"
    ).delete()

    response = post_upload(employee_client, upload("disguised.pdf"), title="")

    assert response.status_code == 403
