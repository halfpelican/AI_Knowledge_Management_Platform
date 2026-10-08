"""``GET /api/documents/{id}`` — the route a document citation links to (D-46).

FR-12's Front-End clause requires that each citation "links to the source document or
meeting". ``GET /api/meetings/{id}`` has served the meeting half since Stage 3; this is
the document half, added at Stage 4 item 10b so that it passes through items 11 and 12 —
the scoping test and the security review — rather than after them.

Three properties are the whole of this file:

- **The same authorisation as the repository list**: a session, nothing more. Both roles
  reach it (CLAUDE.md section 8 item 2), and what differs between them is the scope.
- **404 for an unknown id and 404 for a document outside the caller's scope, never 403.**
  A 403 would distinguish "exists but you may not see it" from "does not exist", which is
  the disclosure CLAUDE.md invariant 1 forbids by name. The two cases are asserted to
  produce the identical status and the identical body.
- **``file_path`` and ``content_hash`` are not in the body**, for the reasons
  ``GET /api/documents`` already excludes them. Asserted against the raw bytes of the
  response, not against parsed keys, so a nested or renamed copy fails too.
"""

import json
import uuid

import pytest

from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME
from apps.documents.models import Document
from apps.retrieval.tests.scopes import unreadable_scope

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]

CONTENT_HASH = "f" * 64


def make_document(uploader, *, title="Leave policy", roles=None, **fields):
    return Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=uploader,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
        **fields,
    )


def detail(client, doc_id):
    return client.get(f"{DOCUMENTS_URL}/{doc_id}")


# --- The happy path, from both roles ---------------------------------------------------


def test_a_document_in_scope_is_returned(session_client, employee):
    """The citation's destination resolves, from an Employee session and an Administrator
    session. The route adds no permission beyond the global ``IsAuthenticated`` default,
    which is what ``GET /api/documents`` requires to list the same row."""
    document = make_document(employee, department="People")

    response = detail(session_client.client, document.id)

    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == str(document.id)
    assert body["title"] == "Leave policy"
    assert body["file_type"] == "pdf"
    assert body["department"] == "People"
    assert body["visible_to_roles"] == BOTH_ROLES
    assert body["uploaded_by"] == employee.email


def test_the_body_is_the_object_the_repository_list_returns(session_client, employee):
    """One document object, not a second shape. FR-15 (Stage 5) reads this endpoint for its
    detail screen, so the field set has to be the list's or the two would drift apart.

    Since Stage 5 item 2 the detail carries FR-15's three detail fields as well (D-63, D-73),
    and nothing else differs: ``test_document_detail_fields.py`` asserts the exact key set."""
    document = make_document(employee)

    listed = session_client.client.get(DOCUMENTS_URL).json()
    detailed = detail(session_client.client, document.id).json()

    detail_fields = {"extracted_text", "tags", "can_delete"}
    assert [{key: value for key, value in detailed.items() if key not in detail_fields}] == listed


def test_the_body_carries_no_file_path_and_no_content_hash(session_client, employee):
    """A path inside MEDIA_ROOT is of no use to a client and an invitation to construct
    one; a content hash would let a caller probe whether a document they cannot see has
    already been uploaded. Asserted over every byte sent, so a nested copy fails too."""
    document = make_document(
        employee, file_path="documents/leave-policy.pdf", content_hash=CONTENT_HASH
    )

    response = detail(session_client.client, document.id)

    assert response.status_code == 200
    payload = response.content.decode()
    assert "file_path" not in payload
    assert "leave-policy.pdf" not in payload
    assert "content_hash" not in payload
    assert CONTENT_HASH not in payload


# --- The failure paths: 404 twice, and 401 ---------------------------------------------


def test_an_unknown_id_is_not_found(session_client):
    response = detail(session_client.client, uuid.uuid4())

    assert response.status_code == 404


def test_a_document_outside_the_callers_scope_is_not_found(session_client, employee):
    """404, not 403: a 403 would confirm the id names something real (CLAUDE.md invariant 1
    — the existence of out-of-scope material is not disclosed). Run from both roles, each
    against a document it may not read: Administrator-only for the Employee and, since D-66
    made Administrator generalise Employee, scoped to nobody for the Administrator."""
    document = make_document(
        employee, title="Board remuneration", roles=unreadable_scope(session_client.role_name)
    )

    response = detail(session_client.client, document.id)

    assert response.status_code == 404
    # And the list agrees: the row is not disclosed there either, not even as a count.
    assert session_client.client.get(DOCUMENTS_URL).json() == []


def test_out_of_scope_and_unknown_are_indistinguishable(employee_client, employee):
    """The refusals are the same status AND the same body. A caller comparing the two
    replies learns nothing about which ids are real, which is the point of the 404."""
    restricted = make_document(
        employee, title="Board remuneration", roles=[ADMINISTRATOR_ROLE_NAME]
    )

    out_of_scope = detail(employee_client, restricted.id)
    unknown = detail(employee_client, uuid.uuid4())

    assert out_of_scope.status_code == unknown.status_code == 404
    assert json.loads(out_of_scope.content) == json.loads(unknown.content)


def test_an_anonymous_caller_is_unauthorised(api_client, employee):
    document = make_document(employee)

    assert detail(api_client, document.id).status_code == 401


def test_a_role_that_may_not_contribute_may_still_read(employee, employee_client):
    """Reading a document is not contributing one. The upload's ``contribute_content``
    check is not on this route, and a citation must stay followable for the role the
    answer was generated for."""
    from apps.accounts.models import RolePermission

    RolePermission.objects.filter(
        role=employee.role, permission__permission_name="contribute_content"
    ).delete()
    document = make_document(employee)

    assert detail(employee_client, document.id).status_code == 200
