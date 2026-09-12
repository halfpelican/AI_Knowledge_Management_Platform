"""Meetings and MeetingAttendees (FR-09, docs/decisions.md D-12)."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from apps.core.constants import DEFAULT_MEETING_STATUS, MEETING_STATUS_VALUES
from apps.meetings.models import Meeting, MeetingAttendee

pytestmark = pytest.mark.django_db


def make_meeting():
    return Meeting.objects.create(
        title="Quarterly planning",
        meeting_date=date(2026, 9, 1),
        transcript_text="The quarterly planning meeting moved to Thursday.",
    )


def test_meeting_status_vocabulary_and_default():
    meeting = make_meeting()
    assert [choice for choice, _ in Meeting._meta.get_field("status").choices] == list(MEETING_STATUS_VALUES)
    assert meeting.status == DEFAULT_MEETING_STATUS == "Received"
    assert meeting.created_at is not None
    meeting.full_clean()


def test_meeting_rejects_a_status_outside_the_vocabulary():
    meeting = make_meeting()
    meeting.status = "Transcribed"
    with pytest.raises(ValidationError) as excinfo:
        meeting.full_clean()
    assert "status" in excinfo.value.error_dict


def test_attendees_cascade_with_their_meeting(employee):
    meeting = make_meeting()
    MeetingAttendee.objects.create(meeting=meeting, user=employee)
    meeting.delete()
    assert MeetingAttendee.objects.count() == 0


def test_deleting_an_attending_user_is_protected(employee):
    MeetingAttendee.objects.create(meeting=make_meeting(), user=employee)
    with pytest.raises(ProtectedError):
        employee.delete()
