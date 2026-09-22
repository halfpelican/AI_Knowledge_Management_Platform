"""ingest_meeting_transcript() (FR-09).

Three things are being asserted here, in order of how much they would cost to get
wrong:

1. A transcript takes the FR-08 chunking and embedding path unchanged, with
   source_type "meeting", so FR-12 can answer from meetings and documents alike.
2. Speaker labels and timestamps are stored and chunked VERBATIM. FR-09 puts
   structural parsing of them out of scope for this version, and a test is the only
   thing that tells "deliberately not parsed" apart from "not implemented yet".
3. Scoping is visible_to_roles, mirroring documents. Attendance is a participation
   record and never an access control (D-16, CLAUDE.md invariant 3).
"""

import datetime

import pytest

from apps.ai.prefixes import document_text
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_EMBED_ATTEMPTS,
    MEETING_INDEXED,
    MEETING_PROCESSING_FAILED,
    MINIMUM_CONTENT_LENGTH,
    ROLE_NAMES,
)
from apps.documents.models import ContentChunk
from apps.ingestion.chunking import length_in_tokens, split_into_overlapping_chunks
from apps.ingestion.embedding import MEETING_SOURCE_TYPE
from apps.ingestion.meetings import ingest_meeting_transcript
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install
from apps.ingestion.tests.builders import words
from apps.meetings.models import Meeting, MeetingAttendee

pytestmark = pytest.mark.django_db

MEETING_DATE = datetime.date(2026, 9, 14)
MEETING_TITLE = "Records management working group"

# A transcript in the shape FR-09 receives one: speaker labels, timestamps, and a
# blank line between turns. Long enough to clear MINIMUM_CONTENT_LENGTH.
TRANSCRIPT = (
    "[00:00:04] Haseeb Malik: The retention schedule changes on the first of "
    "November, so every record created before that date keeps its current period.\n"
    "\n"
    "[00:01:37] Sagarika Dey: Finance asked whether purchase orders above ten "
    "thousand dollars still need two approvals under the new schedule.\n"
    "\n"
    "[00:02:52] Benjamin Morovan: They do. The delegation table is unchanged and "
    "the second approval must come from a finance delegate, as it does today.\n"
)
SPEAKER_LABEL = "[00:01:37] Sagarika Dey:"


def ingest(transcript=TRANSCRIPT, *, roles=None, attendees=()):
    return ingest_meeting_transcript(
        title=MEETING_TITLE,
        meeting_date=MEETING_DATE,
        transcript_text=transcript,
        visible_to_roles=roles if roles is not None else list(ROLE_NAMES),
        attendees=attendees,
    )


# --- The same path as a document -------------------------------------------------------


def test_a_transcript_is_stored_chunked_and_embedded(stub_ai_service):
    outcome = ingest()

    assert outcome.http_status == 201
    assert outcome.meeting.status == MEETING_INDEXED
    chunks = ContentChunk.objects.filter(source_id=outcome.meeting.id)
    assert chunks.count() == 1
    assert {chunk.source_type for chunk in chunks} == {MEETING_SOURCE_TYPE}
    # The same AIService, called the same way: one embed call per chunk (section 7.7).
    # A meeting takes the document path unchanged, prefix included: the title is the
    # meeting's own (apps/ai/prefixes.py).
    assert stub_ai_service.embed_calls == [
        [document_text(MEETING_TITLE, chunk.text)]
        for chunk in split_into_overlapping_chunks(TRANSCRIPT)
    ]


def test_meeting_chunks_carry_the_meetings_visibility_not_its_attendance(employee):
    """D-16 and CLAUDE.md invariant 3. The attendee is an Employee and the meeting is
    Administrator-only; the chunk records the meeting's roles and nothing about who
    was in the room, because attendance is not an access control."""
    outcome = ingest(roles=[ADMINISTRATOR_ROLE_NAME], attendees=[employee])

    chunk = ContentChunk.objects.get(source_id=outcome.meeting.id)
    assert chunk.visible_to_roles == [ADMINISTRATOR_ROLE_NAME]
    assert MeetingAttendee.objects.filter(meeting=outcome.meeting, user=employee).exists()
    # Nothing on the row says who attended, so no retrieval path can scope by it.
    assert EMPLOYEE_ROLE_NAME not in chunk.visible_to_roles


def test_a_long_transcript_produces_the_same_chunks_a_document_would():
    long_transcript = words(501)

    outcome = ingest(long_transcript)

    chunks = ContentChunk.objects.filter(source_id=outcome.meeting.id).order_by("chunk_index")
    assert [chunk.chunk_text for chunk in chunks] == [
        chunk.text for chunk in split_into_overlapping_chunks(long_transcript)
    ]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]


# --- Out of scope: speaker labels and timestamps (FR-09) ----------------------------------


def test_the_transcript_is_stored_verbatim():
    """FR-09: "Structural parsing of speaker labels and timestamps is out of scope
    for this version." Not parsed, and equally not stripped: a reader of a retrieved
    passage (FR-12) is better served by the line as it was spoken."""
    outcome = ingest()

    assert Meeting.objects.get(pk=outcome.meeting.pk).transcript_text == TRANSCRIPT


def test_speaker_labels_and_timestamps_survive_into_the_chunks():
    outcome = ingest()

    chunk = ContentChunk.objects.get(source_id=outcome.meeting.id)
    assert SPEAKER_LABEL in chunk.chunk_text
    assert chunk.chunk_text in TRANSCRIPT  # verbatim substring, D-31


def test_no_speaker_or_timestamp_fields_are_written_anywhere():
    # The schema has no column for either, and nothing here invents a place to put
    # them. If speaker attribution is ever wanted it is a new requirement, not a
    # quiet addition to this path.
    outcome = ingest()

    assert not hasattr(outcome.meeting, "speakers")
    assert [field.name for field in MeetingAttendee._meta.get_fields()] == [
        "id",
        "meeting",
        "user",
    ]


# --- Attendees (FR-09 CRUD: MeetingAttendees (Create)) ---------------------------------------


def test_attendees_are_recorded(employee, administrator):
    outcome = ingest(attendees=[employee, administrator])

    assert {row.user_id for row in MeetingAttendee.objects.all()} == {
        employee.pk,
        administrator.pk,
    }
    assert {row.meeting_id for row in MeetingAttendee.objects.all()} == {outcome.meeting.pk}


def test_a_meeting_with_no_attendees_is_still_ingested():
    # FR-20 reads these rows; retrieval never does, so their absence changes nothing.
    outcome = ingest()

    assert outcome.meeting.status == MEETING_INDEXED
    assert not MeetingAttendee.objects.exists()


# --- Failure paths -----------------------------------------------------------------------------


def test_every_chunk_failing_is_processing_failed_and_the_transcript_survives(monkeypatch):
    """NFR-20 and CLAUDE.md invariant 8: a failed AI step never discards the source.
    The transcript is stored and readable (FR-09's "viewable in full"); only its
    searchability is lost, and the status says so."""
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))

    outcome = ingest()

    assert outcome.http_status == 422
    assert outcome.detail
    stored = Meeting.objects.get(pk=outcome.meeting.pk)
    assert stored.status == MEETING_PROCESSING_FAILED
    assert stored.transcript_text == TRANSCRIPT
    assert not ContentChunk.objects.exists()


def test_a_partly_indexed_meeting_is_indexed(monkeypatch):
    """MEETING_STATUS_VALUES has no "Partially indexed": the proposal defines no
    status column on Meetings at all, so schema v1's three values stand (D-28). A
    meeting with one usable chunk is searchable, so it is Indexed rather than a
    fourth value invented here."""
    long_transcript = words(501)
    install(
        monkeypatch,
        ScriptedEmbedService(
            failures=MAXIMUM_EMBED_ATTEMPTS,
            should_fail=lambda text: text.rstrip().endswith("w500"),
        ),
    )

    outcome = ingest(long_transcript)

    assert outcome.http_status == 201
    assert outcome.meeting.status == MEETING_INDEXED
    assert ContentChunk.objects.filter(source_id=outcome.meeting.id).count() == 1


def test_an_unexpected_failure_leaves_no_meeting_at_all(monkeypatch, employee):
    """NFR-21. The meeting row, its attendees, its chunks and its vectors commit
    together or not at all."""
    install(
        monkeypatch,
        ScriptedEmbedService(failures=1, error=RuntimeError("the provider client crashed")),
    )

    with pytest.raises(RuntimeError):
        ingest(attendees=[employee])

    assert not Meeting.objects.exists()
    assert not MeetingAttendee.objects.exists()
    assert not ContentChunk.objects.exists()


def test_a_transcript_below_the_minimum_is_refused_before_anything_is_written(stub_ai_service):
    """The serializer answers 400 for this (FR-09's own code, unlike FR-08's 422), so
    reaching here means validation was bypassed. A ValueError rather than an assert,
    which python -O would strip."""
    short = words(MINIMUM_CONTENT_LENGTH - 1)
    assert length_in_tokens(short) < MINIMUM_CONTENT_LENGTH

    with pytest.raises(ValueError):
        ingest(short)

    assert not Meeting.objects.exists()
    assert stub_ai_service.embed_calls == []
