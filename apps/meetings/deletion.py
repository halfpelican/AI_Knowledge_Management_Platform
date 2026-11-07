"""Meeting deletion: the meeting and everything derived from it, in one transaction (D-99).

**Not in the proposal.** FR-09 gives Meetings Create, Read and Update status, and FR-15's
permissioned deletion covers documents only. The lead asked for meeting deletion on 7 November
2026, and D-99 builds it as a mirror of D-73's document deletion
(``apps/documents/deletion.py``): the same order, the same transaction and the same reasons.

``meeting.delete()`` alone would leave the meeting answering questions. ``MeetingAttendee`` goes
with it through its CASCADE foreign key, but ``ContentChunk`` and ``ContentTag`` reference their
source by ``source_type`` and ``source_id`` with no foreign key (D-07), so they would survive the
delete: the chunks still embedded, still stamped and still retrievable. This module deletes them
explicitly, in the same transaction as the meeting (CLAUDE.md invariant 9).

**Where it differs from the document's version: there is no stored file.** FR-09 accepts a
transcript as pasted text or as an uploaded file, but an uploaded file is read for its text and
never stored (``MeetingsView._transcript_from``). The meeting row's ``transcript_text`` is the only
copy, so nothing is left to remove on commit, and no ``on_commit`` callback is registered.

**The caller has already decided that this delete may happen.** ``delete_meeting`` takes a
meeting the view resolved through ``scoped_meetings`` (404 outside scope) and checked
``manage_meetings`` against (403), in that order (D-46, D-73, D-99). Nothing here re-checks
either, and nothing here may be reached from a route by any other path.

**Why this lives outside ``apps/api``**, as the document's version does: it reads the
``Meeting`` and ``ContentChunk`` managers directly, by primary key and by source, which is right
for a write against a row already resolved through the scope and is exactly what
``apps/api/tests/test_source_rows_fail_closed.py`` forbids in request-serving packages.
"""

from django.db import transaction

from apps.core.constants import SOURCE_TYPES
from apps.documents.models import ContentChunk, ContentTag
from apps.meetings.models import Meeting

MEETING_SOURCE_TYPE = SOURCE_TYPES[1]


def delete_meeting(meeting: Meeting) -> None:
    """Delete ``meeting``, its attendees, its chunks and its tag links, atomically.

    In one ``transaction.atomic()`` block:

    1. **The meeting row is locked first**, with ``select_for_update``, as ``manage.py reindex``
       locks it before it deletes and rewrites the meeting's chunks. Without waiting for a
       re-index in flight, the chunk delete below would see only the chunks committed before it
       began, and the re-index would then commit fresh chunks for a meeting that no longer
       exists, embedded and retrievable. Waiting means the delete runs after it commits and
       removes what it wrote. (Meetings have no reprocess route, so re-index is the one writer.)
    2. **Its ``ContentChunk`` rows**, by ``source_type`` and ``source_id``. A queryset
       ``delete()``, so Django's ``on_delete`` applies to ``AnswerCitation.chunk``: SET_NULL,
       and the FR-12 record of what was answered survives with ``chunk_uuid`` naming what was
       cited and no text (D-67).
    3. **Its ``ContentTag`` rows**, by the same key. Nothing writes meeting tags yet (FR-10 is
       NIT3004), but ``ContentTags.source_type`` admits ``meeting`` (docs/schema-v1.md §1), so a
       meeting's links are deleted now rather than when the first one appears. The ``Tag`` rows
       stay: they are a vocabulary (D-73's note of 7 October).
    4. **The meeting**, and with it its ``MeetingAttendee`` rows, through their CASCADE foreign
       key. No other model has a foreign key to ``Meeting`` (checked on 7 November 2026): no
       summary or action-item model exists. A model that adds one must decide its ``on_delete``
       with this function in view.

    A meeting deleted by a concurrent request between the caller's lookup and the lock is
    tolerated: its chunks and tag links are deleted by key, which is idempotent, and there is
    then no row left to delete.
    """
    with transaction.atomic():
        locked = Meeting.objects.select_for_update().filter(pk=meeting.pk).first()
        ContentChunk.objects.filter(
            source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk
        ).delete()
        ContentTag.objects.filter(
            source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk
        ).delete()
        if locked is None:
            return
        locked.delete()
