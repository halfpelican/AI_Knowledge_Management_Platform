"""Meetings and MeetingAttendees (FR-09, docs/decisions.md D-12)."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from apps.core.constants import DEFAULT_MEETING_STATUS, EMPLOYEE_ROLE_NAME, MEETING_STATUS_VALUES
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


def test_meeting_visible_to_roles_mirrors_documents_and_ignores_attendance(employee):
    # D-16: the FR-11 filter for meeting content; attendance does not scope anything.
    from apps.documents.models import Document

    meeting = make_meeting()
    meeting.refresh_from_db()
    assert meeting.visible_to_roles == []
    meeting_field = Meeting._meta.get_field("visible_to_roles")
    document_field = Document._meta.get_field("visible_to_roles")
    assert meeting_field.base_field.max_length == document_field.base_field.max_length
    assert meeting_field.default is list and document_field.default is list
    meeting.visible_to_roles = [EMPLOYEE_ROLE_NAME]
    meeting.save()
    assert Meeting.objects.get(pk=meeting.pk).visible_to_roles == [EMPLOYEE_ROLE_NAME]
    MeetingAttendee.objects.create(meeting=meeting, user=employee)
    assert Meeting.objects.get(pk=meeting.pk).visible_to_roles == [EMPLOYEE_ROLE_NAME]


def test_attendees_cascade_with_their_meeting(employee):
    meeting = make_meeting()
    MeetingAttendee.objects.create(meeting=meeting, user=employee)
    meeting.delete()
    assert MeetingAttendee.objects.count() == 0


def test_deleting_an_attending_user_is_protected(employee):
    MeetingAttendee.objects.create(meeting=make_meeting(), user=employee)
    with pytest.raises(ProtectedError):
        employee.delete()
