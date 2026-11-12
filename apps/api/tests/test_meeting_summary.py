"""``GET`` and ``POST /api/meetings/{id}/summary`` — FR-16's Summary panel and its button (D-125).

FR-16 Responses: "202 Accepted while processing, 200 OK with the summary and item list once ready,
an empty item list being a valid result, 422 Unprocessable Entity where the transcript is too short
to summarise." Each state of a summary is read here through the route, from an Employee and from an
Administrator session (CLAUDE.md §8; Objective 01), with the contract's exact key sets.

The order on every request is the security property: the meeting is resolved through the caller's
scope first, so one outside it and one that does not exist are the same 404 with the same body
(invariant 1), and only then is ``contribute_content`` checked for the POST (invariant 4). And no
request here waits on the provider: the POST answers while the run is still to be carried.
"""

import uuid
from datetime import date

import pytest

from apps.accounts.models import RolePermission
from apps.ai.base import ProviderUnavailable
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    CONTRIBUTE_CONTENT_PERMISSION,
    MAXIMUM_SUMMARY_RETRY_RUNS,
    MINIMUM_SUMMARY_TRANSCRIPT_LENGTH,
    ROLE_NAMES,
    SUMMARY_PROCESSING,
    SUMMARY_READY,
    SUMMARY_UNAVAILABLE,
)
from apps.ai.testing import STUB_ACTION_ITEM, STUB_CHAT_MODEL, STUB_DECISION, stub_summary_sentence
from apps.meetings.models import ActionItem, Meeting, MeetingSummary
from apps.meetings.tests.summary_builders import (
    TITLE,
    draft,
    element,
    ingest,
    raising,
    regenerate,
    summarised,
    transcript,
)

pytestmark = pytest.mark.django_db

STATE_KEYS = {"status", "queued_for_retry", "summary", "action_items", "can_edit"}
SUMMARY_KEYS = {
    "summary_id", "summary_text", "narrative", "decisions", "highlights", "passages", "model",
    "generated_at", "input_truncated", "passages_sent", "passages_total", "action_items_extracted",
}
ITEM_KEYS = {
    "action_item_id", "description", "owner", "owner_name", "due_date", "due_text", "passages",
    "origin", "edited", "created_at", "updated_at",
}
NOT_FOUND = {"detail": "No Meeting matches the given query."}


def url(meeting_id) -> str:
    return f"/api/meetings/{meeting_id}/summary"


def stored_meeting(*, words=MINIMUM_SUMMARY_TRANSCRIPT_LENGTH + 40, visible_to_roles=ROLE_NAMES) -> Meeting:
    """A meeting as one stored before FR-16: no summary was ever requested for it."""
    return Meeting.objects.create(
        title=TITLE, meeting_date=date(2026, 11, 10), transcript_text=transcript(words),
        visible_to_roles=list(visible_to_roles),
    )


def revoke_contribute(user):
    RolePermission.objects.filter(
        role=user.role, permission__permission_name=CONTRIBUTE_CONTENT_PERMISSION
    ).delete()


# --- GET: every state, from both roles -----------------------------------------------------------


def test_a_meeting_nobody_asked_a_summary_of_is_200_with_no_status(session_client):
    response = session_client.client.get(url(stored_meeting().id))

    assert response.status_code == 200
    assert response.json() == {
        "status": None, "queued_for_retry": False, "summary": None, "action_items": [], "can_edit": True,
    }


def test_a_run_in_flight_is_202(session_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()

    response = session_client.client.get(url(meeting.id))

    assert response.status_code == 202
    body = response.json()
    assert set(body) == STATE_KEYS
    assert (body["status"], body["queued_for_retry"], body["summary"]) == (SUMMARY_PROCESSING, False, None)


def test_a_ready_summary_is_200_with_the_contracts_exact_shape(session_client, django_capture_on_commit_callbacks):
    meeting = summarised(django_capture_on_commit_callbacks)

    response = session_client.client.get(url(meeting.id))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == STATE_KEYS
    assert (body["status"], body["queued_for_retry"], body["can_edit"]) == (SUMMARY_READY, False, True)
    summary = body["summary"]
    assert set(summary) == SUMMARY_KEYS
    assert summary["summary_text"] == stub_summary_sentence(TITLE)
    assert summary["narrative"] == [{"text": stub_summary_sentence(TITLE), "passages": [1]}]
    assert summary["decisions"] == [{"text": STUB_DECISION, "passages": [1]}]
    assert summary["highlights"] == []
    # UC-04: every element's passage is there to be read, and it is the transcript's own text.
    assert summary["passages"] == {"1": transcript()}
    assert summary["model"] == STUB_CHAT_MODEL and summary["generated_at"]
    assert (summary["input_truncated"], summary["passages_sent"], summary["passages_total"]) == (False, 1, 1)
    assert summary["action_items_extracted"] == 1
    [item] = body["action_items"]
    assert set(item) == ITEM_KEYS
    assert (item["description"], item["origin"], item["edited"], item["owner"]) == (STUB_ACTION_ITEM, "ai", False, None)


def test_a_meeting_that_raised_no_action_items_is_ready_with_an_empty_list(
    session_client, django_capture_on_commit_callbacks, stub_ai_service
):
    """FR-16: "an empty item list being a valid result"; UC-04 A1: recorded as empty, not omitted."""
    stub_ai_service.summary = draft(action_items=[])
    meeting = summarised(django_capture_on_commit_callbacks)

    body = session_client.client.get(url(meeting.id)).json()

    assert body["status"] == SUMMARY_READY and body["action_items"] == []
    assert body["summary"]["action_items_extracted"] == 0


def test_a_failed_summary_queued_for_retry_is_202_and_shows_nothing_of_it(
    session_client, django_capture_on_commit_callbacks, stub_ai_service
):
    """NFR-20's flag reads as "still coming". UC-04: a failed summary is never presented."""
    stub_ai_service.summary = raising(ProviderUnavailable("the provider is down"))
    meeting = summarised(django_capture_on_commit_callbacks)

    response = session_client.client.get(url(meeting.id))

    assert response.status_code == 202
    assert response.json() == {
        "status": SUMMARY_UNAVAILABLE, "queued_for_retry": True, "summary": None, "action_items": [],
        "can_edit": True,
    }
    # The transcript is untouched and readable (invariant 8).
    assert session_client.client.get(f"/api/meetings/{meeting.id}").json()["transcript_text"] == transcript()


def test_a_failed_summary_whose_retries_are_spent_is_200(
    session_client, django_capture_on_commit_callbacks, stub_ai_service
):
    stub_ai_service.summary = raising(ProviderUnavailable("the provider is down"))
    meeting = summarised(django_capture_on_commit_callbacks)
    MeetingSummary.objects.filter(meeting=meeting).update(
        queued_for_retry=False, retry_runs=MAXIMUM_SUMMARY_RETRY_RUNS
    )

    response = session_client.client.get(url(meeting.id))

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["queued_for_retry"]) == (SUMMARY_UNAVAILABLE, False)


def test_a_failed_regenerate_keeps_showing_the_previous_ready_summary(
    session_client, django_capture_on_commit_callbacks, stub_ai_service
):
    stub_ai_service.summary = draft(narrative=[element("The first summary.")])
    meeting = summarised(django_capture_on_commit_callbacks)
    stub_ai_service.summary = raising(ProviderUnavailable("the provider is down"))
    assert regenerate(django_capture_on_commit_callbacks, meeting).status == SUMMARY_UNAVAILABLE

    response = session_client.client.get(url(meeting.id))

    # The latest run failed and is queued, so 202; what is shown is the earlier Ready summary.
    assert response.status_code == 202
    body = response.json()
    assert (body["status"], body["queued_for_retry"]) == (SUMMARY_UNAVAILABLE, True)
    assert body["summary"]["summary_text"] == "The first summary."


def test_a_transcript_under_the_minimum_is_422_with_the_same_keys(session_client):
    meeting = stored_meeting(words=MINIMUM_SUMMARY_TRANSCRIPT_LENGTH - 1)
    ActionItem.objects.create(meeting=meeting, description="Added by hand", origin="user")

    response = session_client.client.get(url(meeting.id))

    assert response.status_code == 422
    body = response.json()
    assert set(body) == STATE_KEYS | {"detail"}
    assert "too short to summarise" in body["detail"]
    assert (body["status"], body["summary"]) == (None, None)
    assert [item["description"] for item in body["action_items"]] == ["Added by hand"]


def test_exactly_the_minimum_is_long_enough(session_client):
    assert session_client.client.get(url(stored_meeting(words=MINIMUM_SUMMARY_TRANSCRIPT_LENGTH).id)).status_code == 200


# --- POST: Generate and Regenerate ----------------------------------------------------------------


def test_post_answers_202_at_once_and_the_run_follows(
    session_client, django_capture_on_commit_callbacks, stub_ai_service
):
    meeting = stored_meeting()

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = session_client.client.post(url(meeting.id))

    assert response.status_code == 202
    assert set(response.json()) == STATE_KEYS and response.json()["status"] == SUMMARY_PROCESSING
    [run] = MeetingSummary.objects.filter(meeting=meeting)
    assert (run.status, run.requested_by, run.run_number) == (SUMMARY_PROCESSING, session_client.user, 1)
    # Nothing was sent to the provider while the request was open.
    assert stub_ai_service.summarise_calls == [] and len(callbacks) == 1

    callbacks[0]()
    ready = session_client.client.get(url(meeting.id))
    assert ready.status_code == 200 and ready.json()["status"] == SUMMARY_READY


def test_post_while_a_run_is_in_flight_starts_nothing(session_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = session_client.client.post(url(meeting.id))

    assert response.status_code == 202
    assert MeetingSummary.objects.filter(meeting=meeting).count() == 1 and len(callbacks) == 0


def test_post_regenerates_and_the_new_summary_replaces_the_old(
    session_client, django_capture_on_commit_callbacks, stub_ai_service
):
    stub_ai_service.summary = draft(narrative=[element("The first summary.")])
    meeting = summarised(django_capture_on_commit_callbacks)
    stub_ai_service.summary = draft(narrative=[element("The second summary.")])

    with django_capture_on_commit_callbacks(execute=True):
        assert session_client.client.post(url(meeting.id)).status_code == 202

    body = session_client.client.get(url(meeting.id)).json()
    assert body["summary"]["summary_text"] == "The second summary."
    assert MeetingSummary.objects.filter(meeting=meeting, status=SUMMARY_READY).count() == 2


def test_post_under_the_minimum_is_422_and_writes_nothing(session_client, django_capture_on_commit_callbacks, stub_ai_service):
    """FR-16 Validation: "rejected rather than submitted"."""
    meeting = stored_meeting(words=MINIMUM_SUMMARY_TRANSCRIPT_LENGTH - 1)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = session_client.client.post(url(meeting.id))

    assert response.status_code == 422 and "too short to summarise" in response.json()["detail"]
    assert not MeetingSummary.objects.filter(meeting=meeting).exists()
    assert stub_ai_service.summarise_calls == [] and len(callbacks) == 0


# --- Who may: scope first, then the permission ----------------------------------------------------


@pytest.mark.parametrize("method", ["get", "post"])
def test_both_routes_are_401_without_a_session(api_client, method):
    assert getattr(api_client, method)(url(stored_meeting().id)).status_code == 401


@pytest.mark.parametrize("method", ["get", "post"])
def test_a_meeting_outside_the_callers_scope_is_the_unknown_ids_404(
    employee_client, employee, administrator_client, method, django_capture_on_commit_callbacks
):
    restricted = summarised(django_capture_on_commit_callbacks, visible_to_roles=[ADMINISTRATOR_ROLE_NAME])

    withheld = getattr(employee_client, method)(url(restricted.id))
    unknown = getattr(employee_client, method)(url(uuid.uuid4()))

    assert withheld.status_code == unknown.status_code == 404
    assert withheld.json() == unknown.json() == NOT_FOUND
    assert MeetingSummary.objects.filter(meeting=restricted).count() == 1  # the POST started nothing

    # The 404 comes BEFORE the 403: without the permission, the answer is still the scope's.
    revoke_contribute(employee)
    assert getattr(employee_client, method)(url(restricted.id)).json() == NOT_FOUND

    # The mirror: the Administrator, whom the meeting admits, is answered.
    assert getattr(administrator_client, method)(url(restricted.id)).status_code in (200, 202)


def test_a_role_without_contribute_content_reads_the_summary_and_cannot_generate(
    session_client, django_capture_on_commit_callbacks
):
    meeting = summarised(django_capture_on_commit_callbacks)
    revoke_contribute(session_client.user)

    read = session_client.client.get(url(meeting.id))
    refused = session_client.client.post(url(meeting.id))

    assert read.status_code == 200
    assert read.json()["can_edit"] is False and read.json()["summary"] is not None
    assert refused.status_code == 403
    assert MeetingSummary.objects.filter(meeting=meeting).count() == 1
