"""Meetings: Meetings and MeetingAttendees (docs/schema-v1.md section 1)."""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.constants import DEFAULT_MEETING_STATUS, MEETING_STATUS_VALUES, SOURCE_TYPES
from apps.core.models import (
    NAME_MAX_LENGTH,
    VOCABULARY_MAX_LENGTH,
    uuid_primary_key,
    vocabulary_field,
)
from apps.core.visibility import VisibilityCascadeMixin, VisibilityCascadeQuerySet

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES


class Meeting(VisibilityCascadeMixin, models.Model):
    """A meeting record. Its chunks follow its ``visible_to_roles``, exactly as a
    Document's do — the same mixin, because D-16 makes meeting visibility mirror document
    visibility and a second cascade would be the second code path invariant 3 refuses.
    """

    id = uuid_primary_key("meeting_id")
    title = models.CharField(max_length=NAME_MAX_LENGTH)
    # "May not be in the future" is application validation in Stage 3 (FR-09),
    # not a database constraint.
    meeting_date = models.DateField()
    transcript_text = models.TextField()
    status = vocabulary_field(MEETING_STATUS_VALUES, default=DEFAULT_MEETING_STATUS)
    created_at = models.DateTimeField(auto_now_add=True)
    # Role names, mirroring Documents.visible_to_roles exactly: the FR-11 permission
    # filter for meeting content (docs/decisions.md D-16). Meetings are NOT scoped by
    # attendance; MeetingAttendees is a participation record only.
    visible_to_roles = ArrayField(
        models.CharField(max_length=VOCABULARY_MAX_LENGTH), default=list, blank=True
    )

    # See Document for both: the source type the cascade re-stamps on, and the manager that
    # carries it to ``Meeting.objects.filter(...).update(visible_to_roles=...)``.
    visibility_source_type = MEETING_SOURCE_TYPE
    objects = VisibilityCascadeQuerySet.as_manager()

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
