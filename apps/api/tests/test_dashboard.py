"""FR-14 dashboard: ``GET /api/dashboard``, the one endpoint behind every panel.

The contract is docs/api-contract.md, Stage 5, FR-14. The decisions are D-65 (every query
parameter passes a serializer), D-66 (scope is overlap with the role's effective roles), D-68
(recent questions are the caller's own, question only), D-70 (department narrows documents
only; the indexed total counts status "Indexed" split by type; each type filters on its own
date, timestamps by their Melbourne date; offered departments come from scoped documents).

Every test that involves a role runs from both an Employee and an Administrator session,
either through ``session_client`` or with the two clients side by side. Each absence asserted
for one role has its mirror, a presence for a role the row admits, so a dashboard returning
nothing to anybody cannot pass. Since D-66 the Administrator reads Employee content too, so
the row an Administrator is refused is one stamped ``[]`` (``apps/retrieval/tests/scopes.py``).

Leakage is asserted against ``response.content``, the raw bytes, not against parsed fields:
a key nobody anticipated is exactly where a restricted title would turn up.

**Timestamps are set, never left to the clock.** ``auto_now_add`` ignores a value passed to
``create()``, so ``uploaded_at``, ``created_at`` and ``answered_at`` are written with a
queryset ``.update()``. On this Windows machine rows created in one test can share a
timestamp (~15.6 ms clock ticks), so no ordering here relies on creation order.
"""

import uuid
from datetime import date, datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.api.serializers import DATE_RANGE_REVERSED_MESSAGE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DASHBOARD_RECENT_ITEMS,
    DOCUMENT_INDEXED,
    DOCUMENT_PARTIALLY_INDEXED,
    DOCUMENT_PROCESSING,
    EMPLOYEE_ROLE_NAME,
    MEETING_INDEXED,
    MEETING_PROCESSING_FAILED,
    MEETING_RECEIVED,
    NO_RELEVANT_PASSAGE,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import Document
from apps.meetings.models import Meeting
from apps.retrieval.models import Conversation, QueryLog
from apps.retrieval.tests.scopes import unreadable_scope
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

User = get_user_model()

DASHBOARD_URL = "/api/dashboard"
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]
EMPLOYEE_ONLY = [EMPLOYEE_ROLE_NAME]

TOP_LEVEL_KEYS = {
    "filters",
    "departments",
    "indexed_totals",
    "recent_documents",
    "recent_meetings",
    "recent_questions",
}
FILTER_KEYS = {"date_from", "date_to", "department"}
TOTAL_KEYS = {"documents", "meetings", "total"}
# D-68: the question, when, and its thread. Nothing derived from an answer.
QUESTION_KEYS = {"question", "asked_at", "conversation_id"}

MELBOURNE = ZoneInfo("Australia/Melbourne")


def melbourne(month, day, hour=12, minute=0):
    """A 2026 wall-clock time in Melbourne. September 2026 is AEST, UTC+10 (DST starts 4 Oct)."""
    return datetime(2026, month, day, hour, minute, tzinfo=MELBOURNE)


# --- Row builders ----------------------------------------------------------------------------


def add_document(title, *, uploader, roles, department="", status=DOCUMENT_INDEXED, uploaded_at=None):
    document = Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=uploader,
        department=department,
        status=status,
        visible_to_roles=roles,
    )
    if uploaded_at is not None:
        # auto_now_add ignores a value given to create(); update() writes it.
        Document.objects.filter(pk=document.pk).update(uploaded_at=uploaded_at)
    return document


def add_meeting(title, *, roles, meeting_date, status=MEETING_INDEXED, created_at=None):
    meeting = Meeting.objects.create(
        title=title,
        meeting_date=meeting_date,
        transcript_text=f"Transcript of {title}.",
        status=status,
        visible_to_roles=roles,
    )
    if created_at is not None:
        Meeting.objects.filter(pk=meeting.pk).update(created_at=created_at)
    return meeting


def add_question(user, question, *, answered_at=None, conversation=None, **columns):
    columns.setdefault("answered", True)
    row = QueryLog.objects.create(user=user, conversation=conversation, question=question, **columns)
    if answered_at is not None:
        QueryLog.objects.filter(pk=row.pk).update(answered_at=answered_at)
    return row


def dashboard(client, **params):
    response = client.get(DASHBOARD_URL, params)
    assert response.status_code == 200, response.content
    return response


def titles(items):
    return [item["title"] for item in items]


# --- Shape and authentication ------------------------------------------------------------------


def administrators_extra_keys(session_client):
    """FR-19's panel (D-107): ``knowledge_gaps`` is in the payload of a role holding
    ``review_knowledge_gaps``, the Administrator, and of no other. Added on 9 November 2026 to the
    two tests below that assert the whole payload from both roles; the panel itself is tested in
    test_knowledge_gaps.py."""
    return {"knowledge_gaps"} if session_client.role_name == ADMINISTRATOR_ROLE_NAME else set()


def test_the_payload_has_exactly_the_contracts_keys(session_client):
    user = session_client.user
    document = add_document("Leave policy", uploader=user, roles=BOTH_ROLES, department="People")
    meeting = add_meeting("All-hands", roles=BOTH_ROLES, meeting_date=date(2026, 9, 1))
    add_question(user, "How is annual leave accrued?")

    body = dashboard(session_client.client).json()

    assert set(body) == TOP_LEVEL_KEYS | administrators_extra_keys(session_client)
    assert body["filters"] == {"date_from": None, "date_to": None, "department": None}
    assert set(body["indexed_totals"]) == TOTAL_KEYS
    assert body["departments"] == ["People"]
    [question] = body["recent_questions"]
    assert set(question) == QUESTION_KEYS
    # "The same document object GET /api/documents returns", and the same meeting object
    # GET /api/meetings returns, without the transcript.
    listed_document = next(
        item for item in session_client.client.get("/api/documents").json()
        if item["doc_id"] == str(document.id)
    )
    listed_meeting = next(
        item for item in session_client.client.get("/api/meetings").json()
        if item["meeting_id"] == str(meeting.id)
    )
    assert body["recent_documents"] == [listed_document]
    assert body["recent_meetings"] == [listed_meeting]
    assert "transcript_text" not in body["recent_meetings"][0]


def test_an_empty_dashboard_is_200_with_empty_lists_and_zero_counts(session_client):
    body = dashboard(session_client.client).json()
    expected = {
        "filters": {"date_from": None, "date_to": None, "department": None},
        "departments": [],
        "indexed_totals": {"documents": 0, "meetings": 0, "total": 0},
        "recent_documents": [],
        "recent_meetings": [],
        "recent_questions": [],
    }
    if administrators_extra_keys(session_client):
        expected["knowledge_gaps"] = {"open_count": 0, "top": []}
    assert body == expected


def test_an_anonymous_request_is_401(api_client, document):
    response = api_client.get(DASHBOARD_URL)
    assert response.status_code == 401
    assert document.title.encode() not in response.content


# --- Scoping: counts and lists after the permission filter (FR-11, invariant 1) ----------------

SHARED_TITLE = "Employee handbook"
SHARED_DEPARTMENT = "People"
SHARED_MEETING_TITLE = "All-hands briefing"
RESTRICTED_TITLE = "Board remuneration review"
RESTRICTED_DEPARTMENT = "Executive"
RESTRICTED_MEETING_TITLE = "Board in-camera session"


def test_administrator_only_rows_are_absent_for_an_employee_and_present_for_the_administrator(
    employee_client, administrator_client, administrator
):
    add_document(SHARED_TITLE, uploader=administrator, roles=BOTH_ROLES, department=SHARED_DEPARTMENT)
    restricted = add_document(
        RESTRICTED_TITLE, uploader=administrator, roles=ADMINISTRATOR_ONLY, department=RESTRICTED_DEPARTMENT
    )
    add_meeting(SHARED_MEETING_TITLE, roles=BOTH_ROLES, meeting_date=date(2026, 9, 1))
    restricted_meeting = add_meeting(RESTRICTED_MEETING_TITLE, roles=ADMINISTRATOR_ONLY, meeting_date=date(2026, 9, 2))

    employee_response = dashboard(employee_client)
    raw = employee_response.content.decode()
    for trace in (RESTRICTED_TITLE, RESTRICTED_DEPARTMENT, str(restricted.id),
                  RESTRICTED_MEETING_TITLE, str(restricted_meeting.id)):
        assert trace not in raw
    body = employee_response.json()
    assert titles(body["recent_documents"]) == [SHARED_TITLE]
    assert titles(body["recent_meetings"]) == [SHARED_MEETING_TITLE]
    assert body["indexed_totals"] == {"documents": 1, "meetings": 1, "total": 2}
    assert body["departments"] == [SHARED_DEPARTMENT]

    # The mirror: the Administrator, whom the rows admit, is shown them and counts them.
    body = dashboard(administrator_client).json()
    assert set(titles(body["recent_documents"])) == {SHARED_TITLE, RESTRICTED_TITLE}
    assert titles(body["recent_meetings"]) == [RESTRICTED_MEETING_TITLE, SHARED_MEETING_TITLE]
    assert body["indexed_totals"] == {"documents": 2, "meetings": 2, "total": 4}
    assert body["departments"] == [RESTRICTED_DEPARTMENT, SHARED_DEPARTMENT]


def test_an_employee_only_row_is_in_the_administrators_payload(administrator_client, employee_client, employee):
    """D-66: Administrator generalises Employee in scope, so Employee-only content is theirs too."""
    add_document("Payroll calendar", uploader=employee, roles=EMPLOYEE_ONLY, department="Payroll")
    add_meeting("Payroll stand-up", roles=EMPLOYEE_ONLY, meeting_date=date(2026, 9, 3))

    for client in (administrator_client, employee_client):
        body = dashboard(client).json()
        assert titles(body["recent_documents"]) == ["Payroll calendar"]
        assert titles(body["recent_meetings"]) == ["Payroll stand-up"]
        assert body["indexed_totals"] == {"documents": 1, "meetings": 1, "total": 2}
        assert body["departments"] == ["Payroll"]


def test_a_row_the_callers_role_may_not_read_is_absent_from_every_panel(session_client):
    """From both roles. For the Administrator the unreadable row is stamped ``[]`` (D-66)."""
    user = session_client.user
    hidden_scope = unreadable_scope(session_client.role_name)
    add_document("Readable report", uploader=user, roles=BOTH_ROLES, department="Operations")
    hidden = add_document("Sealed report", uploader=user, roles=hidden_scope, department="Sealed unit")
    add_meeting("Readable meeting", roles=BOTH_ROLES, meeting_date=date(2026, 9, 1))
    hidden_meeting = add_meeting("Sealed meeting", roles=hidden_scope, meeting_date=date(2026, 9, 2))

    response = dashboard(session_client.client)
    raw = response.content.decode()
    for trace in ("Sealed report", "Sealed unit", str(hidden.id), "Sealed meeting", str(hidden_meeting.id)):
        assert trace not in raw
    body = response.json()
    # The presence beside each absence, so an empty payload cannot pass.
    assert titles(body["recent_documents"]) == ["Readable report"]
    assert titles(body["recent_meetings"]) == ["Readable meeting"]
    assert body["indexed_totals"] == {"documents": 1, "meetings": 1, "total": 2}
    assert body["departments"] == ["Operations"]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"department": SHARED_DEPARTMENT},
        # A department found only on the restricted documents.
        {"department": RESTRICTED_DEPARTMENT},
        {"date_from": "2026-09-01", "date_to": "2026-09-30"},
    ],
    ids=["no-filter", "shared-department", "restricted-department", "date-range"],
)
def test_an_employees_payload_is_byte_identical_with_and_without_restricted_rows(
    employee_client, administrator_client, employee, administrator, params
):
    """Invariant 1 as one assertion: nothing in the bytes moves when restricted rows arrive.

    Every restricted row is NEWER than every shared one and inside the date range, so a leak
    would put it at the top of a recent list rather than below the cap.
    """
    add_document("Handbook", uploader=administrator, roles=BOTH_ROLES, department=SHARED_DEPARTMENT,
                 uploaded_at=melbourne(9, 10))
    add_document("Rota", uploader=employee, roles=EMPLOYEE_ONLY, department=SHARED_DEPARTMENT,
                 uploaded_at=melbourne(9, 11))
    add_meeting("All-hands", roles=BOTH_ROLES, meeting_date=date(2026, 9, 5))
    add_question(employee, "How is annual leave accrued?", answered_at=melbourne(9, 12))

    employee_before = dashboard(employee_client, **params).content
    administrator_before = dashboard(administrator_client, **params).content

    add_document(RESTRICTED_TITLE, uploader=administrator, roles=ADMINISTRATOR_ONLY,
                 department=RESTRICTED_DEPARTMENT, uploaded_at=melbourne(9, 20))
    add_document("Succession plan", uploader=administrator, roles=ADMINISTRATOR_ONLY,
                 department=RESTRICTED_DEPARTMENT, status=DOCUMENT_PROCESSING, uploaded_at=melbourne(9, 21))
    add_meeting(RESTRICTED_MEETING_TITLE, roles=ADMINISTRATOR_ONLY, meeting_date=date(2026, 9, 25))
    # The Administrator's own question is theirs, not the Employee's (D-68).
    add_question(administrator, "Who is on the succession shortlist?", answered_at=melbourne(9, 22))

    assert dashboard(employee_client, **params).content == employee_before
    # The mirror: the same rows do change the Administrator's payload.
    assert dashboard(administrator_client, **params).content != administrator_before


def test_departments_never_offers_one_found_only_on_restricted_documents(session_client):
    user = session_client.user
    hidden_scope = unreadable_scope(session_client.role_name)
    add_document("Budget", uploader=user, roles=BOTH_ROLES, department="Finance")
    add_document("Forecast", uploader=user, roles=BOTH_ROLES, department="Finance")
    add_document("Induction", uploader=user, roles=BOTH_ROLES, department="Human Resources")
    add_document("Untagged memo", uploader=user, roles=BOTH_ROLES, department="")
    add_document("Sealed", uploader=user, roles=hidden_scope, department="Internal Audit")
    # Used on a readable AND a restricted document: offered, because a readable one carries it.
    add_document("Restricted budget", uploader=user, roles=hidden_scope, department="Finance")

    body = dashboard(session_client.client).json()
    # Distinct, sorted, non-blank, and only from documents in scope.
    assert body["departments"] == ["Finance", "Human Resources"]
    assert b"Internal Audit" not in dashboard(session_client.client).content


def test_departments_are_not_narrowed_by_the_active_filters(session_client):
    user = session_client.user
    add_document("Budget", uploader=user, roles=BOTH_ROLES, department="Finance", uploaded_at=melbourne(9, 1))
    add_document("Induction", uploader=user, roles=BOTH_ROLES, department="Human Resources",
                 uploaded_at=melbourne(9, 20))

    body = dashboard(session_client.client, department="Finance", date_from="2026-09-15").json()
    # Nothing matches both filters, and the control still offers every department in scope.
    assert body["recent_documents"] == []
    assert body["departments"] == ["Finance", "Human Resources"]


def test_a_role_change_takes_effect_on_the_next_request(employee, employee_client, administrator_role, administrator):
    """The scope is re-read from the users table per request (permission_scope), not cached."""
    add_document(RESTRICTED_TITLE, uploader=administrator, roles=ADMINISTRATOR_ONLY)
    assert titles(dashboard(employee_client).json()["recent_documents"]) == []

    employee.role = administrator_role
    employee.save(update_fields=["role"])

    # Same session cookie, no re-login.
    assert titles(dashboard(employee_client).json()["recent_documents"]) == [RESTRICTED_TITLE]


# --- Department (D-70): documents and their figure only ----------------------------------------


def test_department_narrows_documents_and_their_figure_only(session_client):
    user = session_client.user
    add_document("Budget", uploader=user, roles=BOTH_ROLES, department="Finance", uploaded_at=melbourne(9, 1))
    add_document("Forecast", uploader=user, roles=BOTH_ROLES, department="Finance", uploaded_at=melbourne(9, 2))
    add_document("Induction", uploader=user, roles=BOTH_ROLES, department="Human Resources",
                 uploaded_at=melbourne(9, 3))
    add_meeting("Finance sync", roles=BOTH_ROLES, meeting_date=date(2026, 9, 4))
    add_meeting("HR sync", roles=BOTH_ROLES, meeting_date=date(2026, 9, 5))
    add_question(user, "What is the travel budget?", answered_at=melbourne(9, 6))

    unfiltered = dashboard(session_client.client).json()
    filtered = dashboard(session_client.client, department="Finance").json()

    assert filtered["filters"] == {"date_from": None, "date_to": None, "department": "Finance"}
    assert titles(filtered["recent_documents"]) == ["Forecast", "Budget"]
    assert filtered["indexed_totals"] == {"documents": 2, "meetings": 2, "total": 4}
    assert unfiltered["indexed_totals"] == {"documents": 3, "meetings": 2, "total": 5}
    # Meetings and questions carry no department, and are not narrowed by one.
    assert filtered["recent_meetings"] == unfiltered["recent_meetings"]
    assert filtered["recent_questions"] == unfiltered["recent_questions"]
    assert len(filtered["recent_meetings"]) == 2 and len(filtered["recent_questions"]) == 1
    # Trimmed before it is applied (the contract), so surrounding spaces change nothing.
    assert dashboard(session_client.client, department="  Finance  ").json() == filtered


def test_an_unknown_and_a_restricted_only_department_give_the_same_payload(session_client):
    """D-65: shape only, never looked up. The one difference is the caller's own value, echoed."""
    user = session_client.user
    add_document("Readable report", uploader=user, roles=BOTH_ROLES, department="Operations")
    add_document("Sealed report", uploader=user, roles=unreadable_scope(session_client.role_name),
                 department="Internal Audit")
    add_meeting("Readable meeting", roles=BOTH_ROLES, meeting_date=date(2026, 9, 1))

    restricted = session_client.client.get(DASHBOARD_URL, {"department": "Internal Audit"})
    unknown = session_client.client.get(DASHBOARD_URL, {"department": "No such department"})

    assert restricted.status_code == unknown.status_code == 200
    restricted_body, unknown_body = restricted.json(), unknown.json()
    assert restricted_body["filters"].pop("department") == "Internal Audit"
    assert unknown_body["filters"].pop("department") == "No such department"
    assert restricted_body == unknown_body
    assert restricted_body["recent_documents"] == []
    assert restricted_body["indexed_totals"]["documents"] == 0
    assert b"Sealed report" not in restricted.content


# --- Date range (D-65, D-70) -------------------------------------------------------------------


def test_the_date_range_is_inclusive_at_both_ends(session_client):
    user = session_client.user
    add_document("Day before", uploader=user, roles=BOTH_ROLES, uploaded_at=melbourne(9, 9, 23, 30))
    add_document("First minute", uploader=user, roles=BOTH_ROLES, uploaded_at=melbourne(9, 10, 0, 1))
    # Late in the evening of date_to, Melbourne time: a filter on the datetime at midnight
    # would drop it.
    add_document("Late evening", uploader=user, roles=BOTH_ROLES, uploaded_at=melbourne(9, 12, 23, 30))
    add_document("Day after", uploader=user, roles=BOTH_ROLES, uploaded_at=melbourne(9, 13, 0, 30))

    body = dashboard(session_client.client, date_from="2026-09-10", date_to="2026-09-12").json()
    assert body["filters"] == {"date_from": "2026-09-10", "date_to": "2026-09-12", "department": None}
    assert titles(body["recent_documents"]) == ["Late evening", "First minute"]
    assert body["indexed_totals"]["documents"] == 2

    # A range of one day returns that day's items.
    body = dashboard(session_client.client, date_from="2026-09-12", date_to="2026-09-12").json()
    assert titles(body["recent_documents"]) == ["Late evening"]

    # Either end alone.
    body = dashboard(session_client.client, date_from="2026-09-12").json()
    assert titles(body["recent_documents"]) == ["Day after", "Late evening"]
    body = dashboard(session_client.client, date_to="2026-09-09").json()
    assert titles(body["recent_documents"]) == ["Day before"]


def test_a_timestamp_is_compared_by_its_melbourne_date_not_its_utc_date(session_client):
    assert settings.TIME_ZONE == "Australia/Melbourne"  # the premise
    user = session_client.user
    early = add_document("Early on the first day", uploader=user, roles=BOTH_ROLES,
                         uploaded_at=melbourne(9, 10, 7, 0))
    next_morning = add_document("Next morning", uploader=user, roles=BOTH_ROLES,
                                uploaded_at=melbourne(9, 13, 8, 0))
    # Both sit on the other side of a date boundary in UTC. Without that, this tests nothing.
    early.refresh_from_db()
    next_morning.refresh_from_db()
    assert early.uploaded_at.astimezone(dt_timezone.utc).date() == date(2026, 9, 9)
    assert next_morning.uploaded_at.astimezone(dt_timezone.utc).date() == date(2026, 9, 12)

    body = dashboard(session_client.client, date_from="2026-09-10", date_to="2026-09-12").json()
    assert titles(body["recent_documents"]) == ["Early on the first day"]


def test_meetings_filter_on_meeting_date_not_on_when_they_were_recorded(session_client):
    add_meeting("Met in range, recorded long after", roles=BOTH_ROLES, meeting_date=date(2026, 8, 15),
                created_at=melbourne(10, 1))
    add_meeting("Met before, recorded in range", roles=BOTH_ROLES, meeting_date=date(2026, 7, 1),
                created_at=melbourne(8, 15))
    add_meeting("Not indexed, in range", roles=BOTH_ROLES, meeting_date=date(2026, 8, 31),
                status=MEETING_RECEIVED)

    body = dashboard(session_client.client, date_from="2026-08-01", date_to="2026-08-31").json()
    assert titles(body["recent_meetings"]) == ["Not indexed, in range", "Met in range, recorded long after"]
    # The meetings figure is narrowed by the same range, and counts "Indexed" only.
    assert body["indexed_totals"]["meetings"] == 1


def test_questions_filter_on_answered_at_and_an_unanswered_one_is_still_listed(session_client):
    user = session_client.user
    add_question(user, "Unanswered, in range", answered=False, no_answer_reason=NO_RELEVANT_PASSAGE,
                 answered_at=melbourne(9, 12, 23, 45))
    add_question(user, "Answered, in range", answered_at=melbourne(9, 10, 9, 0))
    add_question(user, "Answered, out of range", answered_at=melbourne(9, 13, 9, 0))

    body = dashboard(session_client.client, date_from="2026-09-10", date_to="2026-09-12").json()
    assert [q["question"] for q in body["recent_questions"]] == ["Unanswered, in range", "Answered, in range"]


@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "", "date_to": "", "department": ""},
        {"date_from": ""},
        {"date_to": ""},
        {"department": ""},
        {"department": "   "},
    ],
    ids=["all-empty", "date_from", "date_to", "department", "department-blank"],
)
def test_an_empty_parameter_is_not_applied(session_client, params):
    user = session_client.user
    add_document("Budget", uploader=user, roles=BOTH_ROLES, department="Finance", uploaded_at=melbourne(9, 1))
    add_meeting("Sync", roles=BOTH_ROLES, meeting_date=date(2026, 9, 2))
    add_question(user, "What is the travel budget?", answered_at=melbourne(9, 3))

    response = session_client.client.get(DASHBOARD_URL, params)
    assert response.status_code == 200
    assert response.json()["filters"] == {"date_from": None, "date_to": None, "department": None}
    assert response.content == dashboard(session_client.client).content


# --- Indexed totals (D-70) ---------------------------------------------------------------------


def test_indexed_totals_count_only_status_indexed_split_by_type(session_client):
    user = session_client.user
    for number, status in enumerate(
        [DOCUMENT_INDEXED, DOCUMENT_INDEXED, DOCUMENT_INDEXED, DOCUMENT_PARTIALLY_INDEXED, DOCUMENT_PROCESSING],
        start=1,
    ):
        add_document(f"Document {number}", uploader=user, roles=BOTH_ROLES, status=status,
                     uploaded_at=melbourne(9, number))
    for number, status in enumerate([MEETING_INDEXED, MEETING_RECEIVED, MEETING_PROCESSING_FAILED], start=1):
        add_meeting(f"Meeting {number}", roles=BOTH_ROLES, meeting_date=date(2026, 9, number), status=status)

    body = dashboard(session_client.client).json()
    # Three documents and one meeting, so a figure in the wrong slot or a total that is not
    # the sum cannot pass. "Partially indexed" is not counted.
    assert body["indexed_totals"] == {"documents": 3, "meetings": 1, "total": 4}
    # The recent lists are in any status (the contract): every one of them is listed.
    assert len(body["recent_documents"]) == 5
    assert {d["status"] for d in body["recent_documents"]} == {
        DOCUMENT_INDEXED, DOCUMENT_PARTIALLY_INDEXED, DOCUMENT_PROCESSING
    }
    assert len(body["recent_meetings"]) == 3


# --- Recent lists: capped, newest first --------------------------------------------------------


def test_the_recent_lists_are_capped_and_newest_first_and_the_figures_are_not(session_client):
    assert DASHBOARD_RECENT_ITEMS == 5  # the contract's number
    user = session_client.user
    count = DASHBOARD_RECENT_ITEMS + 2
    for day in range(1, count + 1):
        # Written oldest first; every timestamp is set, so creation order decides nothing.
        add_document(f"Document {day}", uploader=user, roles=BOTH_ROLES, uploaded_at=melbourne(9, day))
        add_meeting(f"Meeting {day}", roles=BOTH_ROLES, meeting_date=date(2026, 9, day))
        add_question(user, f"Question number {day}?", answered_at=melbourne(9, day))

    body = dashboard(session_client.client).json()
    newest = range(count, count - DASHBOARD_RECENT_ITEMS, -1)
    assert titles(body["recent_documents"]) == [f"Document {day}" for day in newest]
    assert titles(body["recent_meetings"]) == [f"Meeting {day}" for day in newest]
    assert [q["question"] for q in body["recent_questions"]] == [f"Question number {day}?" for day in newest]
    # The figures count every indexed item, not the five listed.
    assert body["indexed_totals"] == {"documents": count, "meetings": count, "total": 2 * count}


# --- Recent questions (D-68): the caller's own, and the question only -------------------------


def test_recent_questions_are_only_the_callers_own(session_client, employee, administrator):
    user = session_client.user
    other_role_user = administrator if user == employee else employee
    # Same role as the caller: role scoping would show these, and D-68 says it must not.
    colleague = User.objects.create_user(
        "colleague@example.com", PASSWORD, name="Colin Colleague", role=user.role
    )
    add_question(user, "My own question about leave?")
    add_question(colleague, "A colleague's question about salaries?")
    add_question(other_role_user, "The other role's question about bonuses?")

    response = dashboard(session_client.client)
    assert [q["question"] for q in response.json()["recent_questions"]] == ["My own question about leave?"]
    assert b"colleague's question" not in response.content
    assert b"other role's question" not in response.content


def test_recent_questions_carry_the_question_only(session_client):
    user = session_client.user
    conversation = Conversation.objects.create(user=user, title="Leave questions")
    chunk_id = uuid.uuid4()
    add_question(
        user,
        "How is leave accrued for part-time staff?",
        conversation=conversation,
        answer_text="Leave accrues pro rata to contracted hours.",
        retrieved_chunk_ids=[chunk_id],
        rejected_count=0,
        answered_at=melbourne(9, 14, 10, 2),
    )
    add_question(
        user,
        "Who signs off the travel budget?",
        answered=False,
        no_answer_reason=NO_RELEVANT_PASSAGE,
        answered_at=melbourne(9, 13, 10, 2),
    )

    response = dashboard(session_client.client)
    questions = response.json()["recent_questions"]
    assert questions == [
        {
            "question": "How is leave accrued for part-time staff?",
            "asked_at": "2026-09-14T10:02:00+10:00",
            "conversation_id": str(conversation.id),
        },
        {
            "question": "Who signs off the travel budget?",
            "asked_at": "2026-09-13T10:02:00+10:00",
            "conversation_id": None,
        },
    ]
    raw = response.content.decode()
    for trace in (
        "Leave accrues pro rata",
        str(chunk_id),
        NO_RELEVANT_PASSAGE,
        "answer_text",
        "answered",  # covers answered and answered_at: the timestamp is published as asked_at
        "no_answer_reason",
        "rejected_count",
        "retrieved_chunk_ids",
    ):
        assert trace not in raw


# --- 400: a malformed parameter (D-65; a convention, FR-14 lists no 400) ------------------------


@pytest.mark.parametrize(
    "params, field",
    [
        ({"date_from": "2026-13-01"}, "date_from"),
        ({"date_to": "yesterday"}, "date_to"),
        ({"date_from": "2026-09-01\x00"}, "date_from"),
        ({"date_to": "2026-09-01T00:00:00"}, "date_to"),
        ({"date_from": "2026-09-30", "date_to": "2026-09-01"}, "date_to"),
        ({"department": "Fin\x00ance"}, "department"),
        ({"department": "x" * (NAME_MAX_LENGTH + 1)}, "department"),
    ],
    ids=["impossible-date", "not-a-date", "nul-in-date", "datetime-not-date", "reversed-range",
         "nul-in-department", "over-long-department"],
)
def test_a_malformed_parameter_is_400_keyed_on_its_name(session_client, document, params, field):
    response = session_client.client.get(DASHBOARD_URL, params)
    assert response.status_code == 400
    assert response["Content-Type"] == "application/json"
    body = response.json()
    assert set(body) == {field}
    # A 400 carries no dashboard content.
    assert document.title.encode() not in response.content


def test_a_reversed_range_names_the_rule_under_the_end_date(session_client):
    response = session_client.client.get(DASHBOARD_URL, {"date_from": "2026-09-30", "date_to": "2026-09-01"})
    assert response.status_code == 400
    assert response.json() == {"date_to": [DATE_RANGE_REVERSED_MESSAGE]}


def test_the_boundary_values_are_accepted(session_client):
    longest = "x" * NAME_MAX_LENGTH
    response = session_client.client.get(
        DASHBOARD_URL, {"department": longest, "date_from": "2026-09-01", "date_to": "2026-09-01"}
    )
    assert response.status_code == 200
    assert response.json()["filters"] == {
        "date_from": "2026-09-01", "date_to": "2026-09-01", "department": longest
    }
