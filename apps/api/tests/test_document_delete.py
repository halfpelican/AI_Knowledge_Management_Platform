"""FR-15's deletion: ``DELETE /api/documents/{id}`` (D-73).

FR-15: deletion "is available only to users holding the appropriate permission", "the
requesting user must hold manage_documents to delete", "deleting a document also removes its
extracted content, embeddings and tag links, so that deleted material cannot subsequently be
surfaced through search", and its Responses name 403 without permission and 404 for an unknown
document. D-73 settles the rest: Administrator-only, scoped-first (404 outside scope, then 403),
everything in one transaction, the file removed on commit, 204.

What this file holds FR-15 to is its own promise, tested end to end rather than by row counts
alone: after the delete, a phrase known to be in the document is found by nothing, and a question
only it answered takes no-answer path A without generation being called. The FR-12 record of
what was answered before the delete survives with its chunk null (D-67).

Both roles reach the route: the Administrator's 204 and the Employee's 403, and the 404 from
each. ``apps/documents/tests/test_deletion.py`` tests the deletion function itself: its
rollback, its on-commit file removal and its lock.
"""

import uuid
from math import sqrt
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.base import ContentFile

import apps.ai
from apps.ai.base import EmbeddingResult, Statement, StatementList
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MANAGE_DOCUMENTS_PERMISSION,
    NO_ANSWER_MESSAGE,
    NO_RELEVANT_PASSAGE,
    PROJECT_DIMENSION,
    PROVENANCE_REMOVED_MESSAGE,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
)
from apps.documents.models import ContentChunk, ContentTag, Document, ExtractedContent, Tag
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog
from apps.retrieval.tests.scopes import unreadable_scope

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
FORBIDDEN_BODY = {"detail": f"Your role does not hold the '{MANAGE_DOCUMENTS_PERMISSION}' permission."}

TITLE = "Willow Bridge escalation policy"
# The phrase FR-15's promise is tested with: in the chunk, the extracted text and the file.
PHRASE = "escalation ladder"
PASSAGE = f"Faults on the Willow Bridge follow the {PHRASE}: duty engineer, then the site lead."
QUESTION = "Who is called after the duty engineer on the Willow Bridge?"
STORED_BYTES = PASSAGE.encode()

ABOVE = 0.80
assert RELEVANCE_THRESHOLD < ABOVE


def wide(*components) -> list[float]:
    return list(components) + [0.0] * (settings.EMBEDDING_DIMENSION - len(components))


QUERY = wide(1.0)


def at_cosine(value: float) -> list[float]:
    """A unit vector whose cosine with QUERY is exactly ``value``."""
    return wide(value, sqrt(1.0 - value * value))


class ControlledService:
    """The query vector is QUERY, so a chunk at ``at_cosine(v)`` scores ``v``; the reply cites
    the first passage it was given. The same double ``test_ask.py`` uses, restated."""

    def __init__(self):
        self.embed_calls = []
        self.generate_calls = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[list(QUERY)], model=STUB_EMBEDDING_MODEL, dimension=settings.EMBEDDING_DIMENSION
        )

    def generate_statements(self, question, passages):
        self.generate_calls.append((question, list(passages)))
        return StatementList(
            statements=[Statement(text="The site lead is called next.", chunk_id=passages[0].chunk_id)]
        )

    def health(self):  # pragma: no cover - the answer path does not check provider health
        raise AssertionError("not called")


@pytest.fixture
def service(monkeypatch):
    double = ControlledService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


def tag(document, dimension, name):
    tag_row, _ = Tag.objects.get_or_create(tag_name=name, dimension=dimension)
    return ContentTag.objects.create(
        tag=tag_row, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.id,
        applied_by="user", confirmed=True,
    )


def stored_document(
    uploader, *, title=TITLE, roles=None, text=PASSAGE, department="Operations", cosine=ABOVE
):
    """A document as ingestion leaves it: a stored file, its extracted text, a chunk stamped
    from it (D-17) and, as D-74's seed leaves it, two tag links. ``cosine`` is the chunk's
    score against QUERY, so two documents can be given a rank order."""
    roles = BOTH_ROLES if roles is None else roles
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=uploader, department=department,
        visible_to_roles=roles,
    )
    document.file_path.save("escalation.txt", ContentFile(STORED_BYTES), save=True)
    ExtractedContent.objects.create(document=document, extracted_text=text)
    ContentChunk.objects.create(
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        chunk_index=0,
        chunk_text=text,
        embedding=at_cosine(cosine),
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )
    tag(document, PROJECT_DIMENSION, "bridge maintenance")
    tag(document, TOPIC_DIMENSION, "escalation")
    return document


def stored_path(document) -> Path:
    return Path(document.file_path.path)


def remains(document) -> dict:
    """What of ``document`` is still in the database, by table."""
    return {
        "document": Document.objects.filter(pk=document.pk).exists(),
        "extracted_content": ExtractedContent.objects.filter(document_id=document.pk).exists(),
        "chunks": ContentChunk.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk).exists(),
        "tag_links": ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk).exists(),
    }


ALL_PRESENT = {"document": True, "extracted_content": True, "chunks": True, "tag_links": True}
ALL_GONE = {"document": False, "extracted_content": False, "chunks": False, "tag_links": False}


def delete(client, document_id):
    return client.delete(f"{DOCUMENTS_URL}/{document_id}")


# --- 204: the Administrator, and everything derived from the document --------------------------


def test_an_administrator_deletes_a_document_and_everything_derived_from_it(
    administrator_client, employee, django_capture_on_commit_callbacks
):
    document = stored_document(employee)
    survivor = stored_document(employee, title="Unrelated survivor")
    path = stored_path(document)
    assert remains(document) == ALL_PRESENT and path.exists()  # the premise

    with django_capture_on_commit_callbacks(execute=True):
        response = delete(administrator_client, document.id)

    assert response.status_code == 204
    assert response.content == b""
    assert remains(document) == ALL_GONE
    assert not path.exists()
    # Nothing of any other document moved, and the tag vocabulary stays (D-73).
    assert remains(survivor) == ALL_PRESENT
    assert stored_path(survivor).exists()
    assert set(Tag.objects.values_list("tag_name", flat=True)) == {"bridge maintenance", "escalation"}


def test_the_stored_file_is_removed_only_when_the_delete_commits(
    administrator_client, employee, django_capture_on_commit_callbacks
):
    document = stored_document(employee)
    path = stored_path(document)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert delete(administrator_client, document.id).status_code == 204
        # The rows are gone inside the transaction; the file waits for the commit.
        assert remains(document) == ALL_GONE
        assert path.exists()

    assert len(callbacks) == 1
    assert not path.exists()


def test_an_administrator_can_delete_a_document_visible_only_to_employees(
    administrator_client, employee, django_capture_on_commit_callbacks
):
    """D-66 puts every Employee-only document in an Administrator's scope, so none is
    undeletable (D-73)."""
    document = stored_document(employee, roles=[EMPLOYEE_ROLE_NAME])

    with django_capture_on_commit_callbacks(execute=True):
        assert delete(administrator_client, document.id).status_code == 204

    assert remains(document) == ALL_GONE


# --- 403: in scope, without manage_documents ---------------------------------------------------


def test_an_employee_gets_403_on_a_document_in_scope_and_nothing_is_deleted(
    employee_client, employee, django_capture_on_commit_callbacks
):
    document = stored_document(employee)
    # The premise: the Employee may see it, so the 403 is about the permission and nothing else.
    assert employee_client.get(f"{DOCUMENTS_URL}/{document.id}").status_code == 200

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = delete(employee_client, document.id)

    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY
    assert callbacks == []
    assert remains(document) == ALL_PRESENT
    assert stored_path(document).read_bytes() == STORED_BYTES


def test_an_administrator_without_the_permission_gets_403(
    administrator_client, administrator_role, employee
):
    """The permission is the role's (D-14), not the role name's: revoked from Administrator,
    it refuses an Administrator."""
    from apps.accounts.models import RolePermission

    RolePermission.objects.filter(
        role=administrator_role, permission__permission_name=MANAGE_DOCUMENTS_PERMISSION
    ).delete()
    document = stored_document(employee)

    response = delete(administrator_client, document.id)

    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY
    assert remains(document) == ALL_PRESENT


# --- 404 before 403: scope first ---------------------------------------------------------------


def test_unknown_and_out_of_scope_are_both_404_and_never_403(session_client, administrator):
    """D-73's order, from both roles. For the Employee the document is Administrator-only and the
    role lacks ``manage_documents`` too, so a check in the other order would answer 403 and
    confirm the document exists. For the Administrator it is stamped ``[]`` (D-66)."""
    restricted = stored_document(administrator, title="Board remuneration",
                                 roles=unreadable_scope(session_client.role_name))

    out_of_scope = delete(session_client.client, restricted.id)
    unknown = delete(session_client.client, uuid.uuid4())

    assert out_of_scope.status_code == unknown.status_code == 404
    assert out_of_scope.content == unknown.content
    assert b"Board remuneration" not in out_of_scope.content
    assert remains(restricted) == ALL_PRESENT
    assert stored_path(restricted).exists()


def test_an_anonymous_delete_is_401_and_deletes_nothing(api_client, employee):
    document = stored_document(employee)
    assert delete(api_client, document.id).status_code == 401
    assert remains(document) == ALL_PRESENT


# --- What FR-15 promises: deleted material is not surfaced again --------------------------------


def test_a_deleted_document_is_gone_from_the_list_browse_and_detail(
    administrator_client, employee_client, employee
):
    document = stored_document(employee)
    stored_document(employee, title="Unrelated survivor", department="Finance")

    assert delete(administrator_client, document.id).status_code == 204

    for client in (employee_client, administrator_client):
        listed = client.get(DOCUMENTS_URL).json()
        assert [item["title"] for item in listed] == ["Unrelated survivor"]
        body = client.get(f"{DOCUMENTS_URL}/browse").json()
        assert [item["title"] for item in body["documents"]] == ["Unrelated survivor"]
        # Its department and its tags' counts went with it: one document left, counted once.
        assert body["facets"]["department"] == [{"value": "Finance", "count": 1}]
        assert body["facets"]["project"] == [{"value": "bridge maintenance", "count": 1}]
        assert client.get(f"{DOCUMENTS_URL}/{document.id}").status_code == 404
        # A second delete of the same id is the unknown-document 404.
        assert delete(client, document.id).status_code == 404


def test_after_a_delete_search_finds_nothing_and_a_question_only_it_answered_takes_path_a(
    employee_client, administrator_client, employee, administrator, service
):
    """FR-15: "so that deleted material cannot subsequently be surfaced through search". Before
    the delete both roles find the phrase and have the question answered; after it, both find
    nothing and the question takes no-answer path A, with generation never called."""
    document = stored_document(employee)
    users = {employee_client: employee, administrator_client: administrator}

    for client in users:
        found = client.get("/api/search", {"q": PHRASE}).json()
        assert [item["source_id"] for item in found["documents"]["results"]] == [str(document.id)]
        assert client.post("/api/ask", {"question": QUESTION}, format="json").json()["answered"] is True
    generated_before = len(service.generate_calls)
    assert generated_before == 2  # the premise: the question was answered from this document

    assert delete(administrator_client, document.id).status_code == 204

    for client, user in users.items():
        searched = client.get("/api/search", {"q": PHRASE})
        assert searched.status_code == 200
        assert searched.json()["total_count"] == 0
        assert searched.json()["documents"] == {"count": 0, "results": []}
        # The reply echoes the term searched for; nothing of the document is beside it.
        for trace in (TITLE, str(document.id), "duty engineer"):
            assert trace.encode() not in searched.content

        logged_before = set(QueryLog.objects.values_list("id", flat=True))
        asked = client.post("/api/ask", {"question": QUESTION}, format="json")
        assert asked.status_code == 200
        body = asked.json()
        assert body["answered"] is False
        assert body["message"] == NO_ANSWER_MESSAGE
        assert body["statements"] == [] and body["sources"] == [] and body["partial_matches"] == []
        row = QueryLog.objects.exclude(id__in=logged_before).get()
        assert row.user == user
        assert row.answered is False
        assert row.no_answer_reason == NO_RELEVANT_PASSAGE  # path A, not B

    # Path A returns without invoking generation at all (invariant 7).
    assert len(service.generate_calls) == generated_before


def test_a_citation_of_a_deleted_chunk_survives_with_its_chunk_null(
    employee_client, administrator_client, employee, service
):
    """D-67: the FR-12 record of what was answered outlives the delete, by identifier and
    without text, and a reopened turn renders it as provenance removed."""
    document = stored_document(employee)
    chunk = ContentChunk.objects.get(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.id)
    conversation = Conversation.objects.create(user=employee, title="Bridge faults")
    answered = employee_client.post(
        "/api/ask", {"question": QUESTION, "conversation_id": str(conversation.id)}, format="json"
    )
    assert answered.json()["answered"] is True
    citation = AnswerCitation.objects.get(query__conversation=conversation)
    assert citation.chunk_id == chunk.id  # the premise

    assert delete(administrator_client, document.id).status_code == 204

    citation.refresh_from_db()
    assert citation.chunk_id is None
    assert citation.chunk_uuid == chunk.id
    assert QueryLog.objects.get(pk=citation.query_id).retrieved_chunk_ids == [chunk.id]

    reopened = employee_client.get(f"/api/conversations/{conversation.id}")
    [turn] = reopened.json()["turns"]
    assert turn["statements"] == []
    assert turn["sources"] == []  # no passage outlives the delete, in the panel either (D-78)
    assert turn["provenance_removed"] is True
    assert turn["message"] == PROVENANCE_REMOVED_MESSAGE
    assert PHRASE.encode() not in reopened.content
    assert TITLE.encode() not in reopened.content


CONSULTED_TITLE = "Willow Bridge inspection calendar"
CONSULTED_PASSAGE = "The Willow Bridge bearings are inspected every April by the structures team."


def test_a_consulted_but_uncited_document_deleted_is_gone_from_the_reopened_panel(
    session_client, administrator_client, employee, service, django_capture_on_commit_callbacks
):
    """D-78 item 4 through FR-15's real deletion (D-73), read from an Employee session and an
    Administrator session.

    The reader's turn cited one document and consulted a second it did not cite. An
    Administrator deletes the second through ``DELETE /api/documents/{id}``. The reopened turn is
    still answered, its statement is unchanged, and its panel lists the cited document alone:
    the deleted one's title, identifiers and passage are nowhere in the body. FR-15's "deleted
    material cannot subsequently be surfaced" holds on the reopen path because the passage is
    read from the chunk and no copy of it was ever stored (D-67).
    """
    cited = stored_document(employee, cosine=0.90)
    consulted = stored_document(
        employee, title=CONSULTED_TITLE, text=CONSULTED_PASSAGE, department="Structures",
        cosine=0.80,
    )
    consulted_chunk = ContentChunk.objects.get(
        source_type=DOCUMENT_SOURCE_TYPE, source_id=consulted.id
    )
    conversation = Conversation.objects.create(user=session_client.user, title="Bridge faults")
    live = session_client.client.post(
        "/api/ask", {"question": QUESTION, "conversation_id": str(conversation.id)}, format="json"
    ).json()
    # The premise: both documents consulted, in rank order, and only the first cited.
    assert [source["title"] for source in live["sources"]] == [TITLE, CONSULTED_TITLE]
    assert str(consulted_chunk.id) not in {statement["chunk_id"] for statement in live["statements"]}
    [before] = session_client.client.get(f"/api/conversations/{conversation.id}").json()["turns"]
    assert before["sources"] == live["sources"]

    with django_capture_on_commit_callbacks(execute=True):
        assert delete(administrator_client, consulted.id).status_code == 204

    reopened = session_client.client.get(f"/api/conversations/{conversation.id}")

    assert reopened.status_code == 200
    [turn] = reopened.json()["turns"]
    assert turn["answered"] is True
    assert turn["statements"] == before["statements"]
    assert turn["sources"] == [before["sources"][0]]
    assert turn["sources"][0]["source_id"] == str(cited.id)
    for trace in (CONSULTED_TITLE, CONSULTED_PASSAGE, str(consulted.id), str(consulted_chunk.id)):
        assert trace.encode() not in reopened.content, trace
