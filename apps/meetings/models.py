"""Meetings: Meetings and MeetingAttendees (docs/schema-v1.md section 1)."""

from django.conf import settings
from django.db import models

from apps.core.constants import DEFAULT_MEETING_STATUS, MEETING_STATUS_VALUES
from apps.core.models import NAME_MAX_LENGTH, uuid_primary_key, vocabulary_field


class Meeting(models.Model):
    id = uuid_primary_key("meeting_id")
    title = models.CharField(max_length=NAME_MAX_LENGTH)
    # "May not be in the future" is application validation in Stage 3 (FR-09),
    # not a database constraint.
    meeting_date = models.DateField()
    transcript_text = models.TextField()
    status = vocabulary_field(MEETING_STATUS_VALUES, default=DEFAULT_MEETING_STATUS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meetings"

    def __str__(self):
        return self.title


class MeetingAttendee(models.Model):
    id = uuid_primary_key("attendee_id")
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="attendees")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="meeting_attendances"
    )

    class Meta:
        db_table = "meeting_attendees"
