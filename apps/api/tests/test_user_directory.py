"""``GET /api/users/directory`` — the people an FR-09 transcript can name.

Stage 3's audit, finding 4:

    FR-09's attendee association is Administrator-only in practice. FR-09's
    Front-End clause makes attendees part of what any user associates with a
    transcript. The gate will be demonstrated from both roles; an Employee
    demonstrating FR-09 cannot show this clause.

The server never restricted the *association* — ``POST /api/meetings`` accepts
attendees from any holder of ``contribute_content``, which is both roles (D-30).
What it restricted was the only user *listing*, FR-05's ``GET /api/users``, which is
Administrator-only because it carries roles and drives role management. So an
Employee had no way to populate a picker and the clause was unreachable for them.

This is the directory that closes it, and FR-05's list is deliberately untouched:
the tests below assert both halves, because the fix would be worse than the finding
if it handed every Employee the role of every colleague.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.core.constants import EMPLOYEE_ROLE_NAME

DIRECTORY_URL = "/api/users/directory"
USERS_URL = "/api/users"

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_any_session_may_read_the_directory(session_client, employee, administrator):
    """Both roles, which is the whole point of the fix."""
    response = session_client.client.get(DIRECTORY_URL)

    assert response.status_code == 200
    assert {row["email"] for row in response.data} == {employee.email, administrator.email}


def test_the_directory_carries_only_a_name_and_an_address(session_client, employee):
    """Three fields, and none of them is the role.

    Naming an attendee needs a person, not their standing in the organisation. Who
    holds which role stays FR-05's business, or this endpoint would be FR-05's list
    with the permission removed — which is the fix that would be worse than the
    finding it closes.
    """
    response = session_client.client.get(DIRECTORY_URL)

    for row in response.data:
        assert set(row) == {"id", "name", "email"}
    # Nothing about roles, account state or history leaks through it.
    body = str(response.data)
    for leaked in ("role", "created_at", "password", "failed_attempts", "locked_until"):
        assert leaked not in body


def test_the_directory_is_ordered_by_name(administrator_client, employee):
    User.objects.create_user("aaron@example.com", "Correct-Horse-9-Battery", name="Aaron Ableman")

    names = [row["name"] for row in administrator_client.get(DIRECTORY_URL).data]

    assert names == sorted(names)


def test_the_directory_is_401_anonymously(api_client):
    assert api_client.get(DIRECTORY_URL).status_code == 401


def test_fr_05s_user_list_stays_administrator_only(employee_client, administrator_client):
    """The directory must not have relaxed FR-05's list as a side effect.

    ``GET /api/users`` carries each person's role and is what role management reads;
    the contract makes it Administrator-only and an Employee still gets 403.
    """
    assert employee_client.get(USERS_URL).status_code == 403
    assert administrator_client.get(USERS_URL).status_code == 200


# --- The clause the directory exists to make reachable ---------------------------------


def test_an_employee_can_name_attendees_end_to_end(employee_client, employee, administrator):
    """FR-09's clause, from an Employee session, by the route the interface takes:
    read the directory, take an id, send it with the transcript."""
    from apps.meetings.models import Meeting, MeetingAttendee

    directory = employee_client.get(DIRECTORY_URL).data
    chosen = [row["id"] for row in directory]

    response = employee_client.post(
        "/api/meetings",
        {
            "title": "Q3 Planning Sync",
            "meeting_date": "2026-09-21",
            "transcript_text": (
                "Priya Raman opened the delegation review and confirmed the approval "
                "thresholds ahead of the audit. Tom Oyelaran noted that the current "
                "threshold is ten thousand dollars for a second approval, and that "
                "anything below that sits with the requesting manager alone. The "
                "group agreed to leave the threshold where it is for this financial "
                "year, because moving it would mean retraining every delegate first."
            ),
            "attendees": chosen,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    meeting = Meeting.objects.get(pk=response.data["meeting_id"])
    assert MeetingAttendee.objects.filter(meeting=meeting).count() == len(chosen)
    assert set(response.data["attendees"]) == {employee.email, administrator.email}
    # D-16 and CLAUDE.md invariant 3: recording someone as an attendee is a
    # participation record and grants nothing. The Employee named an Administrator
    # and that changed no one's access.
    assert employee.role.role_name == EMPLOYEE_ROLE_NAME
