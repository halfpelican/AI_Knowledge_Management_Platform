"""FR-16's action-item routes: add, edit and delete (D-125).

FR-16: "An "Action Items" panel lists each extracted item with description, suggested owner and due
date, all editable. Users can edit, delete or manually add items the extraction missed". Each of
the three writes is driven from an Employee and from an Administrator session (CLAUDE.md §8;
Objective 01).

Every one resolves the meeting through the caller's scope before anything else, so a meeting the
caller cannot see and one that does not exist are one 404, and an item that belongs to another
meeting is that same 404 (invariant 1). ``contribute_content`` is checked after it (invariant 4).
The confirmation FR-16 requires before a delete is the page's and is tested in the front-end suite.
"""

import uuid
from datetime import date

import pytest

from apps.accounts.models import RolePermission
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, CONTRIBUTE_CONTENT_PERMISSION, ROLE_NAMES
from apps.meetings.models import ActionItem, Meeting
from apps.meetings.tests.summary_builders import TITLE, action, draft, summarised, transcript

pytestmark = pytest.mark.django_db

ITEM_KEYS = {
    "action_item_id", "description", "owner", "owner_name", "due_date", "due_text", "passages",
    "origin", "edited", "created_at", "updated_at",
}
NOT_FOUND = {"detail": "No Meeting matches the given query."}


def items_url(meeting_id) -> str:
    return f"/api/meetings/{meeting_id}/action-items"


def item_url(meeting_id, item_id) -> str:
    return f"/api/meetings/{meeting_id}/action-items/{item_id}"


def a_meeting(visible_to_roles=ROLE_NAMES, title=TITLE) -> Meeting:
    return Meeting.objects.create(
        title=title, meeting_date=date(2026, 11, 10), transcript_text=transcript(),
        visible_to_roles=list(visible_to_roles),
    )


def an_item(meeting, **fields) -> ActionItem:
    return ActionItem.objects.create(
        meeting=meeting, **{"description": "Send the notice", "origin": "user", **fields}
    )


def revoke_contribute(user):
    RolePermission.objects.filter(
        role=user.role, permission__permission_name=CONTRIBUTE_CONTENT_PERMISSION
    ).delete()


def snapshot(item) -> dict:
    item.refresh_from_db()
    return {"description": item.description, "owner": item.owner_id, "due_date": item.due_date, "edited": item.edited}


# --- POST: "manually add items the extraction missed" ---------------------------------------------


def test_adding_an_item_is_201_with_the_contracts_shape_and_origin_user(session_client, administrator):
    meeting = a_meeting()

    response = session_client.client.post(
        items_url(meeting.id),
        {"description": "  Book the boardroom  ", "owner_id": str(administrator.id), "due_date": "2026-11-20"},
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == ITEM_KEYS
    assert body["description"] == "Book the boardroom"
    assert body["owner"] == {"id": str(administrator.id), "name": administrator.name}
    assert (body["due_date"], body["origin"], body["edited"]) == ("2026-11-20", "user", False)
    # A person's item carries none of the transcript's words and no passage.
    assert (body["owner_name"], body["due_text"], body["passages"]) == ("", "", [])
    assert ActionItem.objects.get(pk=body["action_item_id"]).meeting_id == meeting.id


def test_only_the_description_is_required(session_client):
    response = session_client.client.post(items_url(a_meeting().id), {"description": "Call the customer"}, format="json")

    assert response.status_code == 201
    assert (response.json()["owner"], response.json()["due_date"]) == (None, None)


@pytest.mark.parametrize(
    "body, field",
    [
        ({}, "description"),
        ({"description": "   "}, "description"),
        ({"description": "x" * 1001}, "description"),
        ({"description": "Fine", "owner_id": str(uuid.uuid4())}, "owner_id"),
        ({"description": "Fine", "owner_id": "not-a-uuid"}, "owner_id"),
        ({"description": "Fine", "due_date": "next Friday"}, "due_date"),
    ],
    ids=["missing", "blank", "over 1,000 characters", "unknown owner", "malformed owner", "malformed date"],
)
def test_an_invalid_add_is_400_keyed_on_its_field_and_writes_nothing(session_client, body, field):
    meeting = a_meeting()

    response = session_client.client.post(items_url(meeting.id), body, format="json")

    assert response.status_code == 400 and list(response.json()) == [field]
    assert not ActionItem.objects.filter(meeting=meeting).exists()


def test_an_added_item_is_listed_after_the_extracted_ones(session_client, django_capture_on_commit_callbacks, stub_ai_service):
    stub_ai_service.summary = draft(action_items=[action("Extracted first"), action("Extracted second")])
    meeting = summarised(django_capture_on_commit_callbacks)

    session_client.client.post(items_url(meeting.id), {"description": "Added by hand"}, format="json")

    listed = session_client.client.get(f"/api/meetings/{meeting.id}/summary").json()["action_items"]
    assert [(item["description"], item["origin"]) for item in listed] == [
        ("Extracted first", "ai"), ("Extracted second", "ai"), ("Added by hand", "user"),
    ]


# --- PATCH: "all editable" -------------------------------------------------------------------------


def test_an_edit_changes_only_the_fields_sent(session_client, employee, administrator):
    meeting = a_meeting()
    item = an_item(meeting, owner=employee, due_date=date(2026, 11, 20), owner_name="Erin", due_text="next Friday",
                   origin="ai", passages=[1])

    response = session_client.client.patch(
        item_url(meeting.id, item.id), {"owner_id": str(administrator.id)}, format="json"
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == ITEM_KEYS
    assert body["owner"] == {"id": str(administrator.id), "name": administrator.name}
    # Unsent fields stand, and the transcript's own words are never changed by an edit.
    assert (body["description"], body["due_date"]) == ("Send the notice", "2026-11-20")
    assert (body["owner_name"], body["due_text"], body["passages"]) == ("Erin", "next Friday", [1])
    # An extracted item a person changed is marked, which keeps it through a Regenerate.
    assert (body["origin"], body["edited"]) == ("ai", True)


def test_null_clears_the_owner_and_the_date(session_client, employee):
    meeting = a_meeting()
    item = an_item(meeting, owner=employee, due_date=date(2026, 11, 20))

    response = session_client.client.patch(
        item_url(meeting.id, item.id), {"owner_id": None, "due_date": None}, format="json"
    )

    assert response.status_code == 200
    assert (response.json()["owner"], response.json()["due_date"]) == (None, None)
    # A person's own item is not "edited": that word is for an extracted item a person changed.
    assert (response.json()["origin"], response.json()["edited"]) == ("user", False)


@pytest.mark.parametrize(
    "body, key",
    [
        ({}, "non_field_errors"),
        ({"description": ""}, "description"),
        ({"owner_id": str(uuid.uuid4())}, "owner_id"),
        ({"due_date": "soon"}, "due_date"),
    ],
    ids=["empty body", "blank description", "unknown owner", "malformed date"],
)
def test_an_invalid_edit_is_400_and_changes_nothing(session_client, body, key):
    meeting = a_meeting()
    item = an_item(meeting, origin="ai")
    before = snapshot(item)

    response = session_client.client.patch(item_url(meeting.id, item.id), body, format="json")

    assert response.status_code == 400 and list(response.json()) == [key]
    assert snapshot(item) == before  # not even marked edited


# --- DELETE ----------------------------------------------------------------------------------------


def test_deleting_an_item_is_204_and_the_row_is_gone(session_client):
    meeting = a_meeting()
    item, other = an_item(meeting), an_item(meeting, description="Stays")

    response = session_client.client.delete(item_url(meeting.id, item.id))

    assert response.status_code == 204 and response.content == b""
    assert list(ActionItem.objects.filter(meeting=meeting)) == [other]


# --- An item is reached only through its own meeting -----------------------------------------------


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_an_item_of_another_meeting_is_the_unknown_items_404_and_is_untouched(session_client, method):
    here, elsewhere = a_meeting(), a_meeting(title="Another meeting")
    item = an_item(elsewhere, origin="ai")
    before = snapshot(item)

    def send(item_id):
        return getattr(session_client.client, method)(
            item_url(here.id, item_id), {"description": "Changed"}, format="json"
        )

    misplaced, unknown = send(item.id), send(uuid.uuid4())

    assert misplaced.status_code == unknown.status_code == 404
    assert misplaced.json() == unknown.json() == NOT_FOUND
    assert snapshot(item) == before


# --- Who may: scope first, then the permission -----------------------------------------------------


def writes(client, meeting, item):
    """The three writes, each as (name, response)."""
    return [
        ("POST", client.post(items_url(meeting.id), {"description": "Added"}, format="json")),
        ("PATCH", client.patch(item_url(meeting.id, item.id), {"description": "Changed"}, format="json")),
        ("DELETE", client.delete(item_url(meeting.id, item.id))),
    ]


def test_all_three_are_401_without_a_session(api_client):
    meeting = a_meeting()
    item = an_item(meeting)

    assert [response.status_code for _, response in writes(api_client, meeting, item)] == [401, 401, 401]
    assert snapshot(item)["description"] == "Send the notice"


def test_an_employee_reaches_nothing_of_an_administrator_only_meetings_items(
    employee_client, employee, administrator_client
):
    restricted = a_meeting(visible_to_roles=[ADMINISTRATOR_ROLE_NAME])
    item = an_item(restricted)
    before = snapshot(item)

    for name, response in writes(employee_client, restricted, item):
        assert response.status_code == 404 and response.json() == NOT_FOUND, name
    # The 404 comes BEFORE the 403: without the permission the answer is still the scope's.
    revoke_contribute(employee)
    for name, response in writes(employee_client, restricted, item):
        assert response.status_code == 404 and response.json() == NOT_FOUND, name
    assert snapshot(item) == before and ActionItem.objects.filter(meeting=restricted).count() == 1

    # The mirror: the Administrator, whom the meeting admits, does all three.
    assert [response.status_code for _, response in writes(administrator_client, restricted, item)] == [201, 200, 204]


def test_a_role_without_contribute_content_is_403_on_all_three_and_changes_nothing(session_client):
    meeting = a_meeting()
    item = an_item(meeting)
    before = snapshot(item)
    revoke_contribute(session_client.user)

    assert [response.status_code for _, response in writes(session_client.client, meeting, item)] == [403, 403, 403]
    assert snapshot(item) == before and ActionItem.objects.filter(meeting=meeting).count() == 1
