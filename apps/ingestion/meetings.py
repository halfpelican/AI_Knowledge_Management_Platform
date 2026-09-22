"""FR-09 meeting transcript ingestion.

    The transcript is stored as plain text and passed to the chunking and embedding
    process in FR-08, making meeting content searchable alongside documents.
    Structural parsing of speaker labels and timestamps is out of scope for this
    version.

So this module has no parser. A transcript is stored exactly as it was submitted —
speaker labels, timestamps and all — and goes through the same
split_into_overlapping_chunks() and embed_and_store_chunks() a document does, with
source_type "meeting". Nothing is stripped either: removing "[00:03:12] Sagarika:"
would be structural parsing by another name, and a reader of a retrieved passage
(FR-12) is better served by the line as it was spoken than by an edited version of
it. A test asserts the verbatim storage, so the exclusion stays honoured rather than
merely unimplemented.

**Attendance is not access control.** Meetings are scoped by ``visible_to_roles``,
mirroring Documents exactly (D-16, CLAUDE.md invariant 3): knowledge has to outlive
the people who were in the room, and a second scoping mechanism would mean two code
paths through the one filter that matters most. MeetingAttendees is a participation
record for FR-20. Nothing here consults it, and nothing in retrieval may.

Validation — title and date present, the date not in the future, the transcript above
MINIMUM_CONTENT_LENGTH — belongs to the serializer, which answers 400 per FR-09
("400 Bad Request for missing fields or insufficient content"). Note the asymmetry
with FR-08, which answers 422 for the same insufficient-content condition; each FR
states its own code and neither is adjusted to match the other.
"""

from dataclasses import dataclass

from django.db import transaction

from apps.core.constants import MEETING_INDEXED, MEETING_PROCESSING_FAILED, MINIMUM_CONTENT_LENGTH
from apps.ingestion.chunking import length_in_tokens, split_into_overlapping_chunks
from apps.ingestion.embedding import MEETING_SOURCE_TYPE, embed_and_store_chunks
from apps.meetings.models import Meeting, MeetingAttendee

# Every chunk failed to embed. FR-09 names no status for this case and no response
# code for it either, so it mirrors FR-08's: the transcript is stored and the record
# carries the reason (CLAUDE.md invariant 8), and the caller is told it is not
# searchable.
INDEXING_FAILED_MESSAGE = "The transcript was stored but could not be indexed."


@dataclass(frozen=True)
class MeetingIngestionOutcome:
    """What ingestion decided, and the status code the view should answer with.

    The meeting is always present: a transcript that could not be embedded is still
    stored, and its status says why it cannot be searched (NFR-20).
    """

    meeting: Meeting
    http_status: int
    detail: str = ""


def ingest_meeting_transcript(
    *,
    title: str,
    meeting_date,
    transcript_text: str,
    visible_to_roles: list[str],
    attendees=(),
) -> MeetingIngestionOutcome:
    """Store a transcript, chunk it, embed it and index it.

    ``attendees`` is an iterable of User objects; each gets a MeetingAttendee row.
    FR-09 associates a transcript "with a meeting title, date, and attendees" and its
    CRUD line lists MeetingAttendees (Create). It is a participation record, not a
    permission (D-16).

    The caller is expected to have validated its input. The one precondition checked
    here is the minimum length, because passing it would embed a fragment and quietly
    pollute retrieval rather than fail. It raises ValueError rather than using
    ``assert``: assertions are stripped under ``python -O``, and an invariant that
    disappears in a production interpreter is not an invariant.
    """
    if length_in_tokens(transcript_text) < MINIMUM_CONTENT_LENGTH:
        raise ValueError(
            "transcript_text is below MINIMUM_CONTENT_LENGTH; FR-09 validation "
            "answers 400 for this and it must not reach ingestion."
        )

    # One transaction: the meeting, its attendees, its chunks and its vectors commit
    # together or not at all (NFR-21, CLAUDE.md invariant 9). There is no stored
    # file to undo, as there is for a document, so no cleanup clause is needed.
    with transaction.atomic():
        meeting = Meeting.objects.create(
            title=title,
            meeting_date=meeting_date,
            # Verbatim. The out-of-scope clause above forbids parsing it; it equally
            # forbids tidying it.
            transcript_text=transcript_text,
            visible_to_roles=visible_to_roles,
        )
        MeetingAttendee.objects.bulk_create(
            [MeetingAttendee(meeting=meeting, user=user) for user in attendees]
        )

        # The FR-08 path, unforked. A meeting chunk differs from a document chunk
        # only in source_type, which is what makes FR-12 able to answer from both
        # without knowing which it read.
        chunks = split_into_overlapping_chunks(transcript_text)
        failed_chunk_count = embed_and_store_chunks(
            chunks=chunks,
            source_type=MEETING_SOURCE_TYPE,
            source_id=meeting.id,
            visible_to_roles=meeting.visible_to_roles,
            title=meeting.title,
        )

        # MEETING_STATUS_VALUES has no "Partially indexed" counterpart, because the
        # proposal defines no status column on Meetings at all and schema v1's three
        # values stand (D-28). The asymmetry with documents is recorded here rather
        # than repaired by inventing a fourth value: a partly indexed meeting is
        # searchable, so it is Indexed.
        if failed_chunk_count and failed_chunk_count == len(chunks):
            meeting.status = MEETING_PROCESSING_FAILED
            meeting.save(update_fields=["status"])
            return MeetingIngestionOutcome(meeting, 422, INDEXING_FAILED_MESSAGE)

        meeting.status = MEETING_INDEXED
        meeting.save(update_fields=["status"])
        return MeetingIngestionOutcome(meeting, 201)
