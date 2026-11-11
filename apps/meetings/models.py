"""Meetings: Meetings and MeetingAttendees (docs/schema-v1.md section 1), and FR-16's
MeetingSummaries and ActionItems (docs/decisions.md D-125)."""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.constants import (
    ACTION_ITEM_ORIGINS,
    DEFAULT_MEETING_STATUS,
    DEFAULT_SUMMARY_STATUS,
    MEETING_STATUS_VALUES,
    SOURCE_TYPES,
    SUMMARY_FAILURE_REASONS,
    SUMMARY_STATUS_VALUES,
)
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


class MeetingSummary(models.Model):
    """One summary run for one meeting (FR-16, UC-04; D-125).

    The proposal's field table is ``summary_id``, ``meeting_id``, ``summary_text``, ``status`` and
    ``generated_at``; the rest are UC-04's (the decisions, the highlights, every element's passages,
    "a record of the model ... and the date") and NFR-20's (the retry flag). A run is created
    Processing and ends Ready or Unavailable. ``summary_text`` and the element lists are written
    once, when it is Ready, and never edited: a Regenerate makes a new row. The meeting's current
    summary is its latest Ready row (apps/meetings/summaries.py); a failed row is never shown or
    cited (UC-04, on failure).
    """

    id = uuid_primary_key("summary_id")
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="summaries")
    # 1, 2, 3... per meeting, given under the meeting's row lock when the run is requested. It is
    # what "latest" means, so that no ordering here depends on two timestamps differing: Windows
    # clocks tick at about 15.6 ms, and a stubbed run finishes inside one tick.
    run_number = models.PositiveIntegerField(default=1)
    # The narrative's sentences joined: the "concise paragraph-length summary" FR-16's panel shows.
    summary_text = models.TextField(blank=True)
    status = vocabulary_field(SUMMARY_STATUS_VALUES, default=DEFAULT_SUMMARY_STATUS)
    generated_at = models.DateTimeField(null=True, blank=True)
    # UC-04's elements, each a list of {"text": str, "passages": [int, ...]}, in the reply's order,
    # holding only references that named a passage sent (invariant 5's set membership).
    narrative = models.JSONField(default=list, blank=True)
    decisions = models.JSONField(default=list, blank=True)
    highlights = models.JSONField(default=list, blank=True)
    # The text of every passage an element names, keyed by its number as a string, so a reference
    # resolves without re-splitting the transcript (D-125, choice 3).
    passages = models.JSONField(default=dict, blank=True)
    model = models.CharField(max_length=NAME_MAX_LENGTH, blank=True)
    # How much of the transcript the request carried: SUMMARY_INPUT_TOKENS of whole passages. The
    # panel says so when ``input_truncated``, rather than presenting a fragment as the whole.
    input_truncated = models.BooleanField(default=False)
    passages_sent = models.PositiveIntegerField(default=0)
    passages_total = models.PositiveIntegerField(default=0)
    # How many action items this run extracted. 0 on a Ready row is UC-04 A1's section recorded as
    # empty; null until the run is Ready.
    action_items_extracted = models.PositiveIntegerField(null=True, blank=True)
    # Who pressed Generate or Regenerate; null for the run ingestion starts.
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="requested_summaries",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    # When the current attempt at this run began: a Processing row much older than this is a run a
    # stopped server left behind (SUMMARY_STALE_AFTER_SECONDS).
    started_at = models.DateTimeField(null=True, blank=True)
    # NFR-20's "flagged for automatic retry": the retry queue is every row with this set.
    queued_for_retry = models.BooleanField(default=False)
    retry_runs = models.PositiveIntegerField(default=0)
    # Why the run ended Unavailable, for the operator; never shown to a user. Blank otherwise.
    failure_reason = vocabulary_field(SUMMARY_FAILURE_REASONS, blank=True)

    class Meta:
        db_table = "meeting_summaries"
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "run_number"], name="meeting_summaries_one_run_per_number"
            ),
        ]
        indexes = [
            models.Index(fields=["queued_for_retry"], name="meeting_summaries_queue_idx"),
        ]

    def __str__(self):
        return f"{self.status} summary of {self.meeting_id}"


class ActionItem(models.Model):
    """One action item of one meeting (FR-16: description, suggested owner, due date).

    The proposal names the table (ActionItems: Create, Read, Update, Delete) and gives it no field
    table, so its columns come from FR-16's and UC-04's words (D-125). An item belongs to the
    meeting, not to a summary run, so a person's additions and edits outlive a Regenerate.
    ``owner`` null is "unassigned": FR-16 stores an item without a confident match that way
    rather than attributing it to the wrong person. ``owner_name`` and ``due_text`` keep the
    transcript's own words beside the owner and the date they did or did not resolve to.
    """

    id = uuid_primary_key("action_item_id")
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="action_items")
    # The run that extracted it; null for an item a person added.
    summary = models.ForeignKey(
        MeetingSummary, on_delete=models.SET_NULL, null=True, blank=True, related_name="action_items"
    )
    description = models.TextField()
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="action_items",
    )
    owner_name = models.CharField(max_length=NAME_MAX_LENGTH, blank=True)
    due_date = models.DateField(null=True, blank=True)
    due_text = models.CharField(max_length=NAME_MAX_LENGTH, blank=True)
    # Passage numbers into the extracting summary's ``passages``; empty for an item a person added.
    passages = models.JSONField(default=list, blank=True)
    origin = vocabulary_field(ACTION_ITEM_ORIGINS)
    # The order the panel lists items in: an extracted item's place in the model's reply, and a
    # hand-added item after every item the meeting then had. Not a timestamp, for the reason
    # MeetingSummary.run_number is not.
    position = models.PositiveIntegerField(default=0)
    # A person changed an extracted item. NFR-15's badge then reads "Suggested by AI, edited by a
    # person", and a Regenerate leaves it alone.
    edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "action_items"

    def __str__(self):
        return self.description
