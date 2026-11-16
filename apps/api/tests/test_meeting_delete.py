"""Meeting deletion: ``DELETE /api/meetings/{id}``, and the detail's ``can_delete`` (D-99).

**Not in the proposal.** FR-09 gives Meetings Create, Read and Update status, and FR-15's
permissioned deletion covers documents only. The lead asked for meeting deletion on 7 November
2026 and chose its shape: a permission of its own, ``manage_meetings``, held by Administrator only
(accounts 0006), and a design that mirrors D-73's document deletion exactly. So this file mirrors
``test_document_delete.py``: Administrator-only, scoped-first (404 outside scope, then 403),
everything in one transaction, 204.

**Where it differs from the documents' file: a meeting stores no file.** FR-09's uploaded
transcript is read for its text and discarded (``MeetingsView._transcript_from``), so there is no
on-commit removal to test. The tests below assert that the delete registers no commit callback at
all, so a file step added later without its own test is noticed.

What this file holds the delete to is what D-73 holds a document's to, tested end to end rather
than by row counts alone: after the delete, a question only the meeting answered takes no-answer
path A without generation being called, from both roles, and none of the meeting's chunks remain,
including a later chunk that held the answer (item 9a's lesson). The FR-12 record of what was
answered before the delete survives with its chunk null (D-67).

Both roles reach the route: the Administrator's 204 and the Employee's 403, and the 404 from each.
``apps/meetings/tests/test_deletion.py`` tests the deletion function itself: its rollback inside
an enclosing transaction, its isolation by source type and its lock.
"""

import uuid
from datetime import date
from math import sqrt

import pytest
from django.conf import settings

import apps.ai
from apps.accounts.models import Permission, RolePermission
from apps.ai.base import EmbeddingResult, Statement, StatementList
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION,
    NO_ANSWER_MESSAGE,
    NO_RELEVANT_PASSAGE,
    PROJECT_DIMENSION,
    PROVENANCE_REMOVED_MESSAGE,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
)
from apps.documents.models import ContentChunk, ContentTag, Tag
from apps.meetings.models import Meeting, MeetingAttendee
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog
from apps.retrieval.tests.scopes import unreadable_scope

pytestmark = pytest.mark.django_db

MEETINGS_URL = "/api/meetings"
MEETING_SOURCE_TYPE = SOURCE_TYPES[1]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
FORBIDDEN_BODY = {"detail": f"Your role does not hold the '{MANAGE_MEETINGS_PERMISSION}' permission."}

TITLE = "Willow Bridge fault review"
# The phrase the search half is tested with: in the chunk and the transcript, not in the title.
PHRASE = "escalation ladder"
PASSAGE = f"Faults on the Willow Bridge follow the {PHRASE}: duty engineer, then the site lead."
QUESTION = "Who is called after the duty engineer on the Willow Bridge?"
MEETING_DATE = date(2026, 10, 20)

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
    the first passage it was given. The same double ``test_document_delete.py`` uses."""

    def __init__(self):
        self.embed_calls = []
        self.generate_calls = []

    def embed(self, texts, *, input_type=None):
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


class Boom(Exception):
    pass


def tag(meeting, dimension, name):
    tag_row, _ = Tag.objects.get_or_create(tag_name=name, dimension=dimension)
    return ContentTag.objects.create(
        tag=tag_row, source_type=MEETING_SOURCE_TYPE, source_id=meeting.id,
        applied_by="user", confirmed=True,
    )


def stored_meeting(*, title=TITLE, roles=None, text=PASSAGE, cosine=ABOVE, chunks=None, attendees=()):
    """A meeting as ingestion leaves it: its transcript, its attendees, a chunk stamped from it
    (D-17) and two tag links. Nothing writes meeting tags until FR-10, so the links are written
    here directly, as D-74's seed writes a document's.

    ``chunks``, a sequence of ``(text, cosine)``, gives the meeting several chunks in that order
    instead of the one ``text`` at ``cosine``, as a transcript longer than CHUNK_SIZE is
    ingested; its transcript is then theirs joined."""
    roles = BOTH_ROLES if roles is None else roles
    chunks = [(text, cosine)] if chunks is None else list(chunks)
    meeting = Meeting.objects.create(
        title=title, meeting_date=MEETING_DATE,
        transcript_text=" ".join(chunk_text for chunk_text, _ in chunks),
        visible_to_roles=roles,
    )
    MeetingAttendee.objects.bulk_create(
        [MeetingAttendee(meeting=meeting, user=user) for user in attendees]
    )
    for index, (chunk_text, chunk_cosine) in enumerate(chunks):
        ContentChunk.objects.create(
            source_type=MEETING_SOURCE_TYPE,
            source_id=meeting.id,
            chunk_index=index,
            chunk_text=chunk_text,
            embedding=at_cosine(chunk_cosine),
            embedding_model=STUB_EMBEDDING_MODEL,
            embedding_dimension=settings.EMBEDDING_DIMENSION,
            visible_to_roles=roles,
        )
    tag(meeting, PROJECT_DIMENSION, "bridge maintenance")
    tag(meeting, TOPIC_DIMENSION, "escalation")
    return meeting


def remains(meeting) -> dict:
    """What of ``meeting`` is still in the database, by table."""
    return {
        "meeting": Meeting.objects.filter(pk=meeting.pk).exists(),
        "attendees": MeetingAttendee.objects.filter(meeting_id=meeting.pk).exists(),
        "chunks": ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).exists(),
        "tag_links": ContentTag.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).exists(),
    }


ALL_PRESENT = {"meeting": True, "attendees": True, "chunks": True, "tag_links": True}
ALL_GONE = {"meeting": False, "attendees": False, "chunks": False, "tag_links": False}


def delete(client, meeting_id):
    return client.delete(f"{MEETINGS_URL}/{meeting_id}")


def detail(client, meeting_id):
    return client.get(f"{MEETINGS_URL}/{meeting_id}")


def grant(role, permission_name):
    RolePermission.objects.get_or_create(
        role=role, permission=Permission.objects.get(permission_name=permission_name)
    )


def revoke(role, permission_name):
    RolePermission.objects.filter(role=role, permission__permission_name=permission_name).delete()


# --- 204: the Administrator, and everything derived from the meeting ---------------------------


def test_an_administrator_deletes_a_meeting_and_everything_derived_from_it(
    administrator_client, employee, administrator, django_capture_on_commit_callbacks
):
    meeting = stored_meeting(attendees=[employee, administrator])
    survivor = stored_meeting(title="Unrelated survivor", attendees=[employee])
    assert remains(meeting) == ALL_PRESENT  # the premise
    assert ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).count() == 1
    assert ContentTag.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).count() == 2

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = delete(administrator_client, meeting.id)

    assert response.status_code == 204
    assert response.content == b""
    assert remains(meeting) == ALL_GONE
    # A meeting stores no file (FR-09's upload is read and discarded), so nothing waits for the
    # commit. A file step added later must come with its own test.
    assert callbacks == []
    # Nothing of any other meeting moved; the attendees' users and the tag vocabulary stay.
    assert remains(survivor) == ALL_PRESENT
    assert {employee.pk, administrator.pk} <= set(
        type(employee).objects.values_list("pk", flat=True)
    )
    assert set(Tag.objects.values_list("tag_name", flat=True)) == {"bridge maintenance", "escalation"}
    # And the detail is gone for the caller who deleted it.
    assert detail(administrator_client, meeting.id).status_code == 404


def test_an_administrator_can_delete_a_meeting_visible_only_to_employees(administrator_client):
    """D-66 puts every Employee-only meeting in an Administrator's scope, so none is undeletable
    (D-99, as D-73 says of documents)."""
    meeting = stored_meeting(roles=[EMPLOYEE_ROLE_NAME])

    assert delete(administrator_client, meeting.id).status_code == 204

    assert remains(meeting) == ALL_GONE


def test_an_employee_whose_role_is_granted_manage_meetings_may_delete(employee_client, employee_role):
    """D-14: the permission is the role's. Granted to Employee, it admits an Employee."""
    grant(employee_role, MANAGE_MEETINGS_PERMISSION)
    meeting = stored_meeting()

    assert delete(employee_client, meeting.id).status_code == 204

    assert remains(meeting) == ALL_GONE


# --- 403: in scope, without manage_meetings ----------------------------------------------------


def test_an_employee_gets_403_on_a_meeting_in_scope_and_nothing_is_deleted(
    employee_client, employee, django_capture_on_commit_callbacks
):
    meeting = stored_meeting(attendees=[employee])
    # The premise: the Employee may see it, so the 403 is about the permission and nothing else.
    assert detail(employee_client, meeting.id).status_code == 200

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = delete(employee_client, meeting.id)

    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY
    assert callbacks == []
    assert remains(meeting) == ALL_PRESENT


def test_an_administrator_without_manage_meetings_gets_403_though_it_holds_manage_documents(
    administrator_client, administrator_role, administrator
):
    """The permission is the role's (D-14), not the role name's: revoked from Administrator, it
    refuses an Administrator. And it is its own code (D-99): ``manage_documents``, which the role
    still holds here, does not stand in for it."""
    revoke(administrator_role, MANAGE_MEETINGS_PERMISSION)
    assert administrator_role.permissions.filter(permission_name=MANAGE_DOCUMENTS_PERMISSION).exists()
    meeting = stored_meeting(attendees=[administrator])

    response = delete(administrator_client, meeting.id)

    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY
    assert remains(meeting) == ALL_PRESENT


def test_an_employee_granted_manage_documents_still_cannot_delete_a_meeting(
    employee_client, employee_role, employee
):
    """D-99 chose a new code rather than reusing ``manage_documents``, so granting the document
    permission grants nothing over meetings."""
    grant(employee_role, MANAGE_DOCUMENTS_PERMISSION)
    meeting = stored_meeting(attendees=[employee])

    response = delete(employee_client, meeting.id)

    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY
    assert remains(meeting) == ALL_PRESENT


# --- 404 before 403: scope first ---------------------------------------------------------------


def test_unknown_and_out_of_scope_are_both_404_and_never_403(session_client, employee):
    """D-99's order, D-73's, from both roles. For the Employee the meeting is Administrator-only
    and the role lacks ``manage_meetings`` too, so a check in the other order would answer 403 and
    confirm the meeting exists. For the Administrator it is stamped ``[]`` (D-66). The Employee
    attended it, which changes nothing (D-16)."""
    restricted = stored_meeting(title="Board remuneration", attendees=[employee],
                                roles=unreadable_scope(session_client.role_name))

    out_of_scope = delete(session_client.client, restricted.id)
    unknown = delete(session_client.client, uuid.uuid4())

    assert out_of_scope.status_code == unknown.status_code == 404
    assert out_of_scope.content == unknown.content
    assert b"Board remuneration" not in out_of_scope.content
    assert str(restricted.id).encode() not in out_of_scope.content
    assert remains(restricted) == ALL_PRESENT


def test_an_employee_gets_404_for_an_administrator_only_meeting_even_holding_the_permission(
    employee_client, employee_role, employee
):
    """Scope is resolved before the permission, so holding the permission never widens what can be
    deleted: an Employee whose role holds ``manage_meetings`` still cannot reach an
    Administrator-only meeting, and is answered as for an id that names nothing."""
    grant(employee_role, MANAGE_MEETINGS_PERMISSION)
    restricted = stored_meeting(title="Board remuneration", roles=[ADMINISTRATOR_ROLE_NAME],
                                attendees=[employee])

    out_of_scope = delete(employee_client, restricted.id)

    assert out_of_scope.status_code == 404
    assert out_of_scope.content == delete(employee_client, uuid.uuid4()).content
    assert remains(restricted) == ALL_PRESENT


def test_an_anonymous_delete_is_401_and_deletes_nothing(api_client, employee):
    meeting = stored_meeting(attendees=[employee])

    response = delete(api_client, meeting.id)

    assert response.status_code == 401
    assert remains(meeting) == ALL_PRESENT


# --- One transaction (invariant 9) --------------------------------------------------------------


def test_a_failure_inside_the_delete_rolls_back_every_row(
    administrator_client, employee, monkeypatch, django_capture_on_commit_callbacks
):
    """The chunks and tag links are deleted before the meeting; a failure deleting the meeting
    must bring them back, or the meeting would survive with nothing to answer from and no tags,
    and a retried delete would find a half-deleted row."""
    meeting = stored_meeting(attendees=[employee])

    def fail(self, *args, **kwargs):
        # Reached after the chunk and tag deletes, inside the transaction.
        assert not ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).exists()
        assert not ContentTag.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).exists()
        raise Boom

    monkeypatch.setattr(Meeting, "delete", fail)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(Boom):
            delete(administrator_client, meeting.id)

    assert remains(meeting) == ALL_PRESENT
    assert callbacks == []
    assert ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).count() == 1
    assert ContentTag.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).count() == 2


# --- Deleted material is not surfaced again ------------------------------------------------------


def test_a_deleted_meeting_is_gone_from_the_list_detail_and_dashboard(
    administrator_client, employee_client
):
    meeting = stored_meeting()
    stored_meeting(title="Unrelated survivor")

    assert delete(administrator_client, meeting.id).status_code == 204

    for client in (employee_client, administrator_client):
        assert [item["title"] for item in client.get(MEETINGS_URL).json()] == ["Unrelated survivor"]
        dashboard = client.get("/api/dashboard").json()
        assert [item["title"] for item in dashboard["recent_meetings"]] == ["Unrelated survivor"]
        assert detail(client, meeting.id).status_code == 404
        # A second delete of the same id is the unknown-meeting 404.
        assert delete(client, meeting.id).status_code == 404


def test_after_a_delete_search_finds_nothing_and_a_question_only_it_answered_takes_path_a(
    employee_client, administrator_client, employee, administrator, service
):
    """Before the delete both roles find the phrase and have the question answered from the
    meeting; after it, both find nothing and the question takes no-answer path A, with generation
    never called."""
    meeting = stored_meeting()
    users = {employee_client: employee, administrator_client: administrator}

    for client in users:
        found = client.get("/api/search", {"q": PHRASE}).json()
        assert [item["source_id"] for item in found["meetings"]["results"]] == [str(meeting.id)]
        live = client.post("/api/ask", {"question": QUESTION}, format="json").json()
        assert live["answered"] is True
        assert [source["source_id"] for source in live["sources"]] == [str(meeting.id)]
    generated_before = len(service.generate_calls)
    assert generated_before == 2  # the premise: the question was answered from this meeting

    assert delete(administrator_client, meeting.id).status_code == 204

    for client, user in users.items():
        searched = client.get("/api/search", {"q": PHRASE})
        assert searched.status_code == 200
        assert searched.json()["total_count"] == 0
        assert searched.json()["meetings"] == {"count": 0, "results": []}
        for trace in (TITLE, str(meeting.id), "duty engineer"):
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


# A meeting of three chunks whose answer is in the MIDDLE one: the other two score below the
# threshold, so the question's only answer is chunk 1, never chunk 0.
OPENING = "Willow Bridge fault review, part one: attendance and apologies."
CLOSING = "Willow Bridge fault review, part three: actions carried to the next meeting."
BELOW = 0.10
assert BELOW < RELEVANCE_THRESHOLD


def test_after_a_delete_a_question_answered_from_a_later_chunk_takes_path_a_and_no_chunk_remains(
    employee_client, administrator_client, employee, administrator, service
):
    """Item 9a's lesson, applied to meetings: a meeting of more than one chunk, with the answer in
    a later one, so a delete that removed only ``chunk_index`` 0 fails here. A chunk left behind
    is still stamped and still retrievable, and failing closed on the deleted source row drops it
    from ``sources`` only, not from what generation is sent (``test_source_rows_fail_closed.py``),
    so the deleted meeting would go on answering."""
    meeting = stored_meeting(chunks=[(OPENING, BELOW), (PASSAGE, ABOVE), (CLOSING, BELOW)])
    chunks = ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id)
    answer_chunk = chunks.get(chunk_index=1)
    assert chunks.count() == 3  # the premise
    users = {employee_client: employee, administrator_client: administrator}

    for client in users:
        live = client.post("/api/ask", {"question": QUESTION}, format="json").json()
        # The premise: answered, and from the middle chunk.
        assert live["answered"] is True
        assert [statement["chunk_id"] for statement in live["statements"]] == [str(answer_chunk.id)]
    generated_before = len(service.generate_calls)
    assert generated_before == 2

    assert delete(administrator_client, meeting.id).status_code == 204

    for client, user in users.items():
        logged_before = set(QueryLog.objects.values_list("id", flat=True))
        asked = client.post("/api/ask", {"question": QUESTION}, format="json")
        assert asked.status_code == 200
        body = asked.json()
        assert body["answered"] is False
        assert body["message"] == NO_ANSWER_MESSAGE
        assert body["statements"] == [] and body["sources"] == [] and body["partial_matches"] == []
        for trace in (PASSAGE, str(answer_chunk.id)):
            assert trace.encode() not in asked.content
        row = QueryLog.objects.exclude(id__in=logged_before).get()
        assert row.user == user
        assert row.no_answer_reason == NO_RELEVANT_PASSAGE  # path A, not B

    assert len(service.generate_calls) == generated_before
    # None of the three, not only the first.
    assert not ContentChunk.objects.filter(
        source_type=MEETING_SOURCE_TYPE, source_id=meeting.id
    ).exists()


def test_a_citation_of_a_deleted_meeting_chunk_survives_with_its_chunk_null(
    employee_client, administrator_client, employee, service
):
    """D-67: the FR-12 record of what was answered outlives the delete, by identifier and without
    text, and a reopened turn renders it as provenance removed."""
    meeting = stored_meeting()
    chunk = ContentChunk.objects.get(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id)
    conversation = Conversation.objects.create(user=employee, title="Bridge faults")
    answered = employee_client.post(
        "/api/ask", {"question": QUESTION, "conversation_id": str(conversation.id)}, format="json"
    )
    assert answered.json()["answered"] is True
    citation = AnswerCitation.objects.get(query__conversation=conversation)
    assert citation.chunk_id == chunk.id  # the premise

    assert delete(administrator_client, meeting.id).status_code == 204

    citation.refresh_from_db()
    assert citation.chunk_id is None
    assert citation.chunk_uuid == chunk.id
    assert QueryLog.objects.get(pk=citation.query_id).retrieved_chunk_ids == [chunk.id]

    reopened = employee_client.get(f"/api/conversations/{conversation.id}")
    [turn] = reopened.json()["turns"]
    assert turn["statements"] == []
    assert turn["sources"] == []
    assert turn["provenance_removed"] is True
    assert turn["message"] == PROVENANCE_REMOVED_MESSAGE
    assert PHRASE.encode() not in reopened.content
    assert TITLE.encode() not in reopened.content


# --- can_delete on the detail (D-99, as D-73's on a document) -------------------------------------


def test_can_delete_is_true_for_an_administrator_and_false_for_an_employee(session_client):
    meeting = stored_meeting()
    expected = session_client.role_name == ADMINISTRATOR_ROLE_NAME

    body = detail(session_client.client, meeting.id).json()

    assert body["can_delete"] is expected


def test_can_delete_follows_manage_meetings_not_the_role_name_or_manage_documents(
    employee_client, administrator_client, employee_role, administrator_role
):
    """D-14: permissions are held against roles. Granting ``manage_meetings`` to Employee and
    revoking it from Administrator moves ``can_delete`` on the next request, both ways, and the
    Administrator's ``manage_documents``, which it keeps, does not hold it up."""
    meeting = stored_meeting()

    grant(employee_role, MANAGE_MEETINGS_PERMISSION)
    revoke(administrator_role, MANAGE_MEETINGS_PERMISSION)

    assert detail(employee_client, meeting.id).json()["can_delete"] is True
    assert detail(administrator_client, meeting.id).json()["can_delete"] is False


def test_only_the_detail_carries_can_delete(session_client):
    """The list and the dashboard keep the meeting object they had: ``can_delete`` is a
    property of the caller, read on the route that offers the control."""
    stored_meeting()

    listed = session_client.client.get(MEETINGS_URL).json()
    recent = session_client.client.get("/api/dashboard").json()["recent_meetings"]

    assert listed and recent
    assert all("can_delete" not in item for item in listed + recent)
