"""FR-19's routes and the dashboard's knowledge-gap panel (docs/api-contract.md, FR-19; D-107).

Three routes, each ``IsAuthenticated`` plus ``review_knowledge_gaps``, which accounts 0007 gives
the Administrator alone:

- ``GET /api/knowledge-gaps``: 200, the entries, Open first by count then recency;
- ``POST /api/knowledge-gaps/cycles``: 201, one cycle run now; 503 when the provider is down;
- ``PATCH /api/knowledge-gaps/{id}``: 200 with ``{"status": "Addressed" | "Open"}``, 400 for any
  other value, 404 for an unknown id.

Every route is exercised from an Employee session (403) and an Administrator session (its
success and failure codes), so the dual-role matrix stays at 100% (CLAUDE.md section 8 item 2).
The 403 is a permission check, not a role-name check: revoking the code from the Administrator
role refuses the Administrator, and granting it to Employee admits the Employee.

**No payload carries an asker, a role, a reason or a count of rows left out** (D-107, D-108).
Leakage is asserted against the raw bytes, not only the parsed fields, as test_dashboard.py does.

The cycle's own rules (the window, D-108's exclusion, D-109's grouping) are tested in
``apps/retrieval/tests/test_knowledge_gaps.py`` with designed vectors. Here the suite's stub
embeds, whose hash-seeded vectors are near-orthogonal, so every question starts its own entry.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

import apps.ai
from apps.accounts.models import Permission, RolePermission
from apps.ai.base import ProviderUnavailable
from apps.api.views import KNOWLEDGE_GAP_CYCLE_UNAVAILABLE_MESSAGE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DASHBOARD_GAP_ITEMS,
    EMPLOYEE_ROLE_NAME,
    KNOWLEDGE_GAP_ADDRESSED,
    KNOWLEDGE_GAP_OPEN,
    NO_RELEVANT_PASSAGE,
    REVIEW_KNOWLEDGE_GAPS_PERMISSION,
)
from apps.retrieval.models import KnowledgeGap, KnowledgeGapCycle, KnowledgeGapItem, QueryLog, SearchLog

pytestmark = pytest.mark.django_db

LIST_URL = "/api/knowledge-gaps"
CYCLES_URL = "/api/knowledge-gaps/cycles"
DASHBOARD_URL = "/api/dashboard"

# The contract's shapes, written out rather than read from the serializers.
GAP_KEYS = {"gap_id", "subject", "occurrence_count", "status", "first_seen_at", "last_seen_at"}
CYCLE_KEYS = {
    "cycle_id", "started_at", "finished_at",
    "queries_considered", "searches_considered", "entries_created", "entries_updated",
}
PANEL_KEYS = {"open_count", "top"}
# FR-14's keys before FR-19, which an Employee's dashboard must still have exactly.
DASHBOARD_KEYS = {"filters", "departments", "indexed_totals", "recent_documents", "recent_meetings", "recent_questions"}

MISSING_PERMISSION = {"detail": f"Your role does not hold the '{REVIEW_KNOWLEDGE_GAPS_PERMISSION}' permission."}


def detail_url(gap) -> str:
    return f"/api/knowledge-gaps/{gap.pk if hasattr(gap, 'pk') else gap}"


def hours_ago(hours: float):
    return timezone.now() - timedelta(hours=hours)


def entry(subject, *, count=1, status=KNOWLEDGE_GAP_OPEN, last_seen_hours_ago=1.0):
    at = hours_ago(last_seen_hours_ago)
    return KnowledgeGap.objects.create(
        subject=subject, occurrence_count=count, status=status, first_seen_at=at, last_seen_at=at
    )


def unanswered(user, question, *, at):
    row = QueryLog.objects.create(
        user=user, question=question, answered=False, no_answer_reason=NO_RELEVANT_PASSAGE
    )
    QueryLog.objects.filter(pk=row.pk).update(answered_at=at)
    return row


def zero_result(user, term, *, at):
    row = SearchLog.objects.create(user=user, query_text=term, result_count=0)
    SearchLog.objects.filter(pk=row.pk).update(searched_at=at)
    return row


def is_administrator(session) -> bool:
    return session.role_name == ADMINISTRATOR_ROLE_NAME


# --- 401 and 403 on every route, from both roles ---------------------------------------------


@pytest.mark.parametrize(
    "method, url",
    [("get", LIST_URL), ("post", CYCLES_URL), ("patch", "/api/knowledge-gaps/00000000-0000-0000-0000-000000000000")],
    ids=["list", "cycles", "patch"],
)
def test_every_route_is_401_without_a_session(api_client, method, url):
    response = getattr(api_client, method)(url, {"status": KNOWLEDGE_GAP_ADDRESSED}, format="json")
    assert response.status_code == 401
    assert KnowledgeGapCycle.objects.count() == 0


def test_the_list_is_403_for_an_employee_and_200_for_an_administrator(session_client):
    entry("Is there a policy on dogs in the office?")
    response = session_client.client.get(LIST_URL)
    if is_administrator(session_client):
        assert response.status_code == 200
        assert [item["subject"] for item in response.json()] == ["Is there a policy on dogs in the office?"]
    else:
        assert response.status_code == 403
        assert response.json() == MISSING_PERMISSION
        assert b"dogs" not in response.content


def test_running_a_cycle_is_403_for_an_employee_and_201_for_an_administrator(session_client, employee):
    unanswered(employee, "Where do I find the parking permit form?", at=hours_ago(1))
    response = session_client.client.post(CYCLES_URL)
    if is_administrator(session_client):
        assert response.status_code == 201
        assert KnowledgeGapCycle.objects.get().triggered_by == session_client.user
    else:
        assert response.status_code == 403
        assert response.json() == MISSING_PERMISSION
        # Refused before anything ran: no cycle, no entry, no item.
        assert KnowledgeGapCycle.objects.count() == 0
        assert KnowledgeGap.objects.count() == 0


def test_marking_an_entry_is_403_for_an_employee_and_200_for_an_administrator(session_client):
    gap = entry("Can I expense a home office chair?")
    response = session_client.client.patch(detail_url(gap), {"status": KNOWLEDGE_GAP_ADDRESSED}, format="json")
    gap.refresh_from_db()
    if is_administrator(session_client):
        assert response.status_code == 200
        assert gap.status == KNOWLEDGE_GAP_ADDRESSED
    else:
        assert response.status_code == 403
        assert gap.status == KNOWLEDGE_GAP_OPEN


def test_an_employee_is_refused_before_an_unknown_id_is_looked_up(employee_client):
    response = employee_client.patch(
        "/api/knowledge-gaps/00000000-0000-0000-0000-000000000000",
        {"status": KNOWLEDGE_GAP_ADDRESSED}, format="json",
    )
    assert response.status_code == 403


def test_the_check_is_the_permission_held_by_the_role_not_the_role_name(
    administrator_client, employee_client, administrator_role, employee_role
):
    """D-107 declined testing the role name. Permissions are the role's (D-14)."""
    RolePermission.objects.filter(
        role=administrator_role, permission__permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION
    ).delete()
    assert administrator_client.get(LIST_URL).status_code == 403
    assert "knowledge_gaps" not in administrator_client.get(DASHBOARD_URL).json()

    RolePermission.objects.create(
        role=employee_role,
        permission=Permission.objects.get(permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION),
    )
    assert employee_client.get(LIST_URL).status_code == 200
    assert set(employee_client.get(DASHBOARD_URL).json()["knowledge_gaps"]) == PANEL_KEYS


# --- GET /api/knowledge-gaps ------------------------------------------------------------------


def test_the_list_is_empty_before_any_cycle(administrator_client):
    response = administrator_client.get(LIST_URL)
    assert response.status_code == 200
    assert response.json() == []


def test_the_list_is_open_first_by_count_then_recency_then_addressed(administrator_client):
    entry("addressed, many", count=9, status=KNOWLEDGE_GAP_ADDRESSED, last_seen_hours_ago=1)
    entry("open, two, older", count=2, last_seen_hours_ago=5)
    entry("open, five", count=5, last_seen_hours_ago=9)
    entry("open, two, newer", count=2, last_seen_hours_ago=1)
    entry("addressed, one", count=1, status=KNOWLEDGE_GAP_ADDRESSED, last_seen_hours_ago=0.5)

    body = administrator_client.get(LIST_URL).json()

    assert [item["subject"] for item in body] == [
        "open, five", "open, two, newer", "open, two, older", "addressed, many", "addressed, one",
    ]
    assert [item["status"] for item in body] == [KNOWLEDGE_GAP_OPEN] * 3 + [KNOWLEDGE_GAP_ADDRESSED] * 2


def test_an_entry_carries_exactly_the_six_fields(administrator_client):
    gap = entry("How do I reset my voicemail PIN?", count=3)

    [item] = administrator_client.get(LIST_URL).json()

    assert set(item) == GAP_KEYS
    assert item["gap_id"] == str(gap.pk)
    assert item["subject"] == "How do I reset my voicemail PIN?"
    assert item["occurrence_count"] == 3
    assert item["status"] == KNOWLEDGE_GAP_OPEN
    assert item["first_seen_at"] and item["last_seen_at"]


def test_no_payload_names_who_asked_or_why(administrator_client, employee):
    """The asker's question is shown verbatim, which is FR-19's design; who asked is not."""
    question = "Which floor is the first-aid room on?"
    unanswered(employee, question, at=hours_ago(2))
    zero_result(employee, "first aid room", at=hours_ago(1))

    cycle = administrator_client.post(CYCLES_URL)
    listing = administrator_client.get(LIST_URL)
    dashboard = administrator_client.get(DASHBOARD_URL)

    assert question in listing.content.decode()
    for response in (cycle, listing, dashboard):
        raw = response.content.decode()
        for trace in (employee.email, employee.name, str(employee.pk), EMPLOYEE_ROLE_NAME,
                      NO_RELEVANT_PASSAGE, '"user', '"role', '"reason', "left_out", "excluded"):
            assert trace not in raw, (response.request["PATH_INFO"], trace)


# --- POST /api/knowledge-gaps/cycles ----------------------------------------------------------


def test_a_cycle_is_201_with_exactly_the_cycle_row(administrator_client, employee, administrator):
    unanswered(employee, "Where do I find the parking permit form?", at=hours_ago(3))
    unanswered(administrator, "Who approves the new seating plan?", at=hours_ago(2))
    zero_result(employee, "seating plan approval", at=hours_ago(1))

    response = administrator_client.post(CYCLES_URL)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == CYCLE_KEYS
    cycle = KnowledgeGapCycle.objects.get()
    assert body["cycle_id"] == str(cycle.pk)
    assert (body["queries_considered"], body["searches_considered"]) == (2, 1)
    assert (body["entries_created"], body["entries_updated"]) == (3, 0)
    assert KnowledgeGapItem.objects.count() == 3
    # The entries are now in the list.
    assert len(administrator_client.get(LIST_URL).json()) == 3


def test_a_cycle_with_nothing_to_take_is_still_201(administrator_client):
    body = administrator_client.post(CYCLES_URL).json()
    assert (body["queries_considered"], body["searches_considered"], body["entries_created"],
            body["entries_updated"]) == (0, 0, 0, 0)


class DownService:
    def embed(self, texts):
        raise ProviderUnavailable("connection refused (designed)")

    def generate_statements(self, question, passages):
        raise AssertionError("not called")

    def health(self):
        raise AssertionError("not called")


def test_a_provider_outage_is_503_with_the_notice_and_changes_nothing(
    administrator_client, employee, monkeypatch, attempts_log_file
):
    unanswered(employee, "Where do I find the parking permit form?", at=hours_ago(1))
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: DownService())

    response = administrator_client.post(CYCLES_URL)

    assert response.status_code == 503
    assert response.json() == {"detail": KNOWLEDGE_GAP_CYCLE_UNAVAILABLE_MESSAGE}
    assert KnowledgeGapCycle.objects.count() == 0
    assert KnowledgeGap.objects.count() == 0
    # The cause is logged beside the failed attempts; the reply's notice stays fixed.
    logged = attempts_log_file.read_text(encoding="utf-8")
    assert "POST /api/knowledge-gaps/cycles answered 503" in logged
    assert "connection refused (designed)" not in response.content.decode()


# --- PATCH /api/knowledge-gaps/{id} -----------------------------------------------------------


def test_an_entry_is_marked_addressed_and_back_to_open(administrator_client):
    gap = entry("Can I expense a home office chair?", count=4)

    addressed = administrator_client.patch(detail_url(gap), {"status": KNOWLEDGE_GAP_ADDRESSED}, format="json")
    assert addressed.status_code == 200
    assert set(addressed.json()) == GAP_KEYS
    assert addressed.json()["status"] == KNOWLEDGE_GAP_ADDRESSED
    assert addressed.json()["occurrence_count"] == 4

    reopened = administrator_client.patch(detail_url(gap), {"status": KNOWLEDGE_GAP_OPEN}, format="json")
    assert reopened.status_code == 200
    gap.refresh_from_db()
    assert gap.status == KNOWLEDGE_GAP_OPEN


@pytest.mark.parametrize(
    "body",
    [{"status": "Closed"}, {"status": "addressed"}, {"status": ""}, {"status": None}, {}, {"subject": "renamed"}],
    ids=["unknown", "wrong-case", "empty", "null", "missing", "another-field"],
)
def test_any_other_status_is_400_keyed_on_status_and_changes_nothing(administrator_client, body):
    gap = entry("Can I expense a home office chair?")

    response = administrator_client.patch(detail_url(gap), body, format="json")

    assert response.status_code == 400
    assert set(response.json()) == {"status"}
    gap.refresh_from_db()
    assert (gap.status, gap.subject) == (KNOWLEDGE_GAP_OPEN, "Can I expense a home office chair?")


def test_an_unknown_id_is_404(administrator_client):
    entry("Can I expense a home office chair?")
    response = administrator_client.patch(
        "/api/knowledge-gaps/00000000-0000-0000-0000-000000000000",
        {"status": KNOWLEDGE_GAP_ADDRESSED}, format="json",
    )
    assert response.status_code == 404


def test_a_patch_changes_the_status_only(administrator_client):
    gap = entry("Can I expense a home office chair?", count=2)
    before = KnowledgeGap.objects.filter(pk=gap.pk).values().get()

    administrator_client.patch(
        detail_url(gap),
        {"status": KNOWLEDGE_GAP_ADDRESSED, "occurrence_count": 99, "subject": "edited"},
        format="json",
    )

    after = KnowledgeGap.objects.filter(pk=gap.pk).values().get()
    assert after.pop("status") == KNOWLEDGE_GAP_ADDRESSED
    before.pop("status")
    assert after == before


# --- The dashboard's panel (D-107, closing D-69) ----------------------------------------------


def test_the_administrators_dashboard_carries_the_open_count_and_the_top_open_entries(administrator_client):
    for number in range(DASHBOARD_GAP_ITEMS + 2):
        entry(f"open question {number}", count=number + 1)
    entry("addressed question", count=99, status=KNOWLEDGE_GAP_ADDRESSED)

    body = administrator_client.get(DASHBOARD_URL).json()

    assert set(body) == DASHBOARD_KEYS | {"knowledge_gaps"}
    panel = body["knowledge_gaps"]
    assert set(panel) == PANEL_KEYS
    assert panel["open_count"] == DASHBOARD_GAP_ITEMS + 2
    # Open entries only, in the list's order, and the list's own entry objects.
    listing = administrator_client.get(LIST_URL).json()
    open_in_order = [item for item in listing if item["status"] == KNOWLEDGE_GAP_OPEN]
    assert panel["top"] == open_in_order[:DASHBOARD_GAP_ITEMS]
    assert [item["subject"] for item in panel["top"]] == [
        f"open question {number}" for number in range(DASHBOARD_GAP_ITEMS + 1, 1, -1)
    ]
    assert all(set(item) == GAP_KEYS for item in panel["top"])
    assert b"addressed question" not in administrator_client.get(DASHBOARD_URL).content


def test_the_administrators_panel_is_present_and_empty_when_there_are_no_gaps(administrator_client):
    body = administrator_client.get(DASHBOARD_URL).json()
    assert body["knowledge_gaps"] == {"open_count": 0, "top": []}


def test_the_employees_dashboard_has_no_panel_and_keeps_its_shape(employee_client):
    entry("open question", count=3)

    response = employee_client.get(DASHBOARD_URL)

    assert response.status_code == 200
    assert set(response.json()) == DASHBOARD_KEYS
    assert b"knowledge_gaps" not in response.content
    assert b"open question" not in response.content


def test_the_panel_is_not_narrowed_by_the_dashboards_filters(administrator_client):
    entry("an entry seen this morning", count=2, last_seen_hours_ago=1)

    unfiltered = administrator_client.get(DASHBOARD_URL).json()["knowledge_gaps"]
    filtered = administrator_client.get(
        DASHBOARD_URL, {"date_from": "2020-01-01", "date_to": "2020-01-31", "department": "Finance"}
    ).json()["knowledge_gaps"]

    assert filtered == unfiltered
    assert filtered["open_count"] == 1


def test_a_promotion_brings_the_panel_on_the_next_request(employee, employee_client, administrator_role):
    assert "knowledge_gaps" not in employee_client.get(DASHBOARD_URL).json()

    employee.role = administrator_role
    employee.save(update_fields=["role"])

    assert "knowledge_gaps" in employee_client.get(DASHBOARD_URL).json()
    assert employee_client.get(LIST_URL).status_code == 200
