"""FR-15's detail fields on ``GET /api/documents/{id}``: ``extracted_text``, ``tags``, ``can_delete``.

FR-15's detail view shows "its metadata, extracted content, and a download link". D-63 restores
the extracted content D-52 cut, read from ``ExtractedContent`` through the route's scoped lookup
and never reassembled from chunks; D-73 adds the tags by dimension and the server-computed
``can_delete``. The download link is Stage 5 item 2a and is not tested here.

``apps/api/tests/test_document_detail.py`` holds the route's Stage 4 properties (404 out of
scope, no ``file_path`` or ``content_hash``). This file holds what Stage 5 adds. Every
role-dependent test runs from both roles; the 404 test has its Administrator mirror.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings

from apps.accounts.models import Permission, RolePermission
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DEPARTMENT_DIMENSION,
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    MANAGE_DOCUMENTS_PERMISSION,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
)
from apps.documents.models import ContentChunk, ContentTag, Document, ExtractedContent, Tag
from apps.meetings.models import Meeting

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
DETAIL_FIELDS = {"extracted_text", "tags", "can_delete"}
NO_TAGS = {"project": [], "process": [], "topic": []}

# Two lines and a tab, so a rendering that collapsed or reflowed it would not be equal.
EXTRACTED_TEXT = "Employees may request annual leave in writing.\n\n\tApproval rests with the manager."
CHUNK_TEXT = "A chunk's own text, which overlaps its neighbours and is not the document."


def make_document(uploader, *, title="Leave policy", roles=None, status=DOCUMENT_INDEXED, **fields):
    return Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=uploader,
        status=status,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
        **fields,
    )


def make_chunk(document, text, roles=None):
    return ContentChunk.objects.create(
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        chunk_index=0,
        chunk_text=text,
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )


def tag(source_id, dimension, name, source_type=DOCUMENT_SOURCE_TYPE):
    tag_row, _ = Tag.objects.get_or_create(tag_name=name, dimension=dimension)
    return ContentTag.objects.create(
        tag=tag_row, source_type=source_type, source_id=source_id, applied_by="user", confirmed=True
    )


def detail(client, document):
    response = client.get(f"{DOCUMENTS_URL}/{document.id}")
    assert response.status_code == 200, response.content
    return response


# --- The shape ---------------------------------------------------------------------------------


def test_the_detail_is_the_list_object_plus_exactly_the_three_detail_fields(session_client):
    document = make_document(session_client.user, department="People")

    [listed] = session_client.client.get(DOCUMENTS_URL).json()
    body = detail(session_client.client, document).json()

    assert set(body) == set(listed) | DETAIL_FIELDS
    assert {key: value for key, value in body.items() if key not in DETAIL_FIELDS} == listed
    # The list stays without them: fifty documents' whole text is not a listing.
    assert not DETAIL_FIELDS & set(listed)


# --- extracted_text (D-63) ---------------------------------------------------------------------


def test_extracted_text_is_the_rows_text_not_the_chunks(session_client):
    """Read from ``ExtractedContent``, never reassembled from chunks: the two differ here."""
    document = make_document(session_client.user)
    ExtractedContent.objects.create(document=document, extracted_text=EXTRACTED_TEXT)
    make_chunk(document, CHUNK_TEXT)

    response = detail(session_client.client, document)

    assert response.json()["extracted_text"] == EXTRACTED_TEXT
    assert CHUNK_TEXT.encode() not in response.content


def test_extracted_text_is_null_when_the_document_has_no_row(session_client):
    """Keyed on the row existing, not on the status: this one says Indexed and has no row."""
    indexed = make_document(session_client.user, title="Indexed, no row")
    failed = make_document(session_client.user, title="Extraction failed",
                           status=DOCUMENT_EXTRACTION_FAILED)

    for document in (indexed, failed):
        body = detail(session_client.client, document).json()
        assert "extracted_text" in body
        assert body["extracted_text"] is None


def test_the_newest_row_is_shown_if_a_document_has_more_than_one(session_client):
    """No shipped path leaves two rows (a reprocess deletes the old one first). If one ever
    did, the detail view shows the newest, the row ``manage.py reindex`` re-embeds from."""
    melbourne = ZoneInfo("Australia/Melbourne")
    document = make_document(session_client.user)
    older = ExtractedContent.objects.create(document=document, extracted_text="Older extraction.")
    newer = ExtractedContent.objects.create(document=document, extracted_text="Newer extraction.")
    # Written oldest first; the timestamps are set, so creation order decides nothing.
    ExtractedContent.objects.filter(pk=newer.pk).update(extracted_at=datetime(2026, 9, 2, tzinfo=melbourne))
    ExtractedContent.objects.filter(pk=older.pk).update(extracted_at=datetime(2026, 9, 1, tzinfo=melbourne))

    assert detail(session_client.client, document).json()["extracted_text"] == "Newer extraction."


def test_an_employee_asking_for_an_administrator_only_document_gets_404_and_no_text(
    employee_client, administrator_client, administrator
):
    """D-63: the extracted text is a document's whole content. It travels only on the scoped
    route, and an Employee who names an Administrator-only document receives 404 and none of it."""
    secret = "Directors' bonus pool is set at four per cent of profit."
    restricted = make_document(administrator, title="Board remuneration", roles=[ADMINISTRATOR_ROLE_NAME])
    ExtractedContent.objects.create(document=restricted, extracted_text=secret)
    tag(restricted.id, PROJECT_DIMENSION, "succession planning")

    refused = employee_client.get(f"{DOCUMENTS_URL}/{restricted.id}")

    assert refused.status_code == 404
    for trace in (secret, "Board remuneration", "succession planning", "can_delete"):
        assert trace.encode() not in refused.content

    # The mirror: the Administrator, whom the document admits, reads the text.
    body = detail(administrator_client, restricted).json()
    assert body["extracted_text"] == secret
    assert body["tags"]["project"] == ["succession planning"]


# --- tags (D-73) -------------------------------------------------------------------------------


def test_tags_are_listed_by_dimension_sorted_and_only_the_documents_own(session_client):
    user = session_client.user
    document = make_document(user)
    other = make_document(user, title="Another document")
    tag(document.id, PROJECT_DIMENSION, "supplier review")
    tag(document.id, PROJECT_DIMENSION, "budget")
    tag(document.id, PROJECT_DIMENSION, "budget")  # linked twice, listed once
    tag(document.id, TOPIC_DIMENSION, "finance")
    # Department is the column, not a tag (D-72), and is not read from tags here.
    tag(document.id, DEPARTMENT_DIMENSION, "tagged department")
    # Another document's tag, and a meeting tag that happens to share this document's id.
    tag(other.id, PROCESS_DIMENSION, "purchasing")
    tag(document.id, PROCESS_DIMENSION, "meeting process", source_type=MEETING_SOURCE_TYPE)

    response = detail(session_client.client, document)

    assert response.json()["tags"] == {"project": ["budget", "supplier review"], "process": [],
                                       "topic": ["finance"]}
    for trace in (b"tagged department", b"purchasing", b"meeting process"):
        assert trace not in response.content


def test_a_document_with_no_tags_has_every_dimension_empty(session_client):
    document = make_document(session_client.user)
    assert detail(session_client.client, document).json()["tags"] == NO_TAGS


# --- can_delete (D-73) -------------------------------------------------------------------------


def test_can_delete_is_true_for_an_administrator_and_false_for_an_employee(session_client):
    document = make_document(session_client.user)
    expected = session_client.role_name == ADMINISTRATOR_ROLE_NAME
    assert detail(session_client.client, document).json()["can_delete"] is expected


def test_can_delete_follows_the_roles_permission_not_the_role_name(
    employee_client, administrator_client, employee_role, administrator_role, employee
):
    """D-14: permissions are held against roles. Granting ``manage_documents`` to Employee and
    revoking it from Administrator moves ``can_delete`` on the next request, both ways."""
    document = make_document(employee)
    permission = Permission.objects.get(permission_name=MANAGE_DOCUMENTS_PERMISSION)

    RolePermission.objects.create(role=employee_role, permission=permission)
    RolePermission.objects.filter(role=administrator_role, permission=permission).delete()

    assert detail(employee_client, document).json()["can_delete"] is True
    assert detail(administrator_client, document).json()["can_delete"] is False


def test_a_meeting_has_none_of_the_document_only_detail_fields(session_client):
    """FR-15's detail clause is about documents (D-63's not-covered list): the meeting detail has
    no ``extracted_text`` and no ``tags``. It has carried ``can_delete`` since D-99 added meeting
    deletion; ``apps/api/tests/test_meeting_delete.py`` tests that field."""
    meeting = Meeting.objects.create(
        title="All-hands", meeting_date=datetime(2026, 9, 1).date(),
        transcript_text="Transcript.", visible_to_roles=BOTH_ROLES,
    )
    body = session_client.client.get(f"/api/meetings/{meeting.id}").json()
    assert not (DETAIL_FIELDS - {"can_delete"}) & set(body)
    assert "can_delete" in body
