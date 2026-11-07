"""``apps.meetings.deletion.delete_meeting``: meeting deletion, below the route (D-99).

``apps/api/tests/test_meeting_delete.py`` tests the route: who may delete, the 404 before the
403, and that the meeting answers nothing afterwards. This file tests the function's own
guarantees, as ``apps/documents/tests/test_deletion.py`` tests ``delete_document``'s:

- **one transaction** (CLAUDE.md invariant 9): a failure part-way through leaves every row, and a
  delete rolled back by a transaction enclosing it leaves every row too;
- **only this meeting's derived rows go**: a chunk or tag link is selected by ``source_type``
  AND ``source_id``, since neither has a foreign key (D-07);
- **the meeting row is locked before its chunks are deleted**, as ``manage.py reindex`` locks
  it, so a delete cannot run between a re-index's chunk delete and its chunk insert;
- **nothing waits for the commit**: a meeting stores no file, so no callback is registered.
"""

from datetime import date

import pytest
from django.conf import settings
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.core.constants import EMPLOYEE_ROLE_NAME, PROJECT_DIMENSION, SOURCE_TYPES
from apps.documents.models import ContentChunk, ContentTag, Tag
from apps.meetings.deletion import delete_meeting
from apps.meetings.models import Meeting, MeetingAttendee

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES


class Boom(Exception):
    pass


def chunk(source_type, source_id, index=0):
    return ContentChunk.objects.create(
        source_type=source_type,
        source_id=source_id,
        chunk_index=index,
        chunk_text="A passage.",
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model="stub-embed",
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )


def tag_link(source_type, source_id):
    tag, _ = Tag.objects.get_or_create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    return ContentTag.objects.create(tag=tag, source_type=source_type, source_id=source_id,
                                     applied_by="user", confirmed=True)


def make_meeting(title, attendee):
    meeting = Meeting.objects.create(
        title=title, meeting_date=date(2026, 10, 20), transcript_text="The transcript.",
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    MeetingAttendee.objects.create(meeting=meeting, user=attendee)
    chunk(MEETING_SOURCE_TYPE, meeting.id, 0)
    chunk(MEETING_SOURCE_TYPE, meeting.id, 1)
    tag_link(MEETING_SOURCE_TYPE, meeting.id)
    return meeting


@pytest.fixture
def stored(employee):
    """A meeting with an attendee, two chunks and a tag link."""
    return make_meeting("Fault review", employee)


def remains(meeting) -> dict:
    return {
        "meeting": Meeting.objects.filter(pk=meeting.pk).exists(),
        "attendees": MeetingAttendee.objects.filter(meeting_id=meeting.pk).exists(),
        "chunks": ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).exists(),
        "tag_links": ContentTag.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk).exists(),
    }


ALL_PRESENT = {"meeting": True, "attendees": True, "chunks": True, "tag_links": True}
ALL_GONE = {"meeting": False, "attendees": False, "chunks": False, "tag_links": False}


def test_the_meeting_and_everything_derived_from_it_is_deleted(stored, django_capture_on_commit_callbacks):
    assert remains(stored) == ALL_PRESENT  # the premise

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        delete_meeting(stored)

    assert remains(stored) == ALL_GONE
    # No stored file, so nothing is deferred to the commit.
    assert callbacks == []


def test_a_failure_inside_the_delete_rolls_back_every_row(stored, monkeypatch):
    def fail(self, *args, **kwargs):
        # Reached after the chunk and tag deletes inside the transaction.
        assert not ContentChunk.objects.filter(source_id=stored.pk).exists()
        raise Boom

    monkeypatch.setattr(Meeting, "delete", fail)

    with pytest.raises(Boom):
        delete_meeting(stored)

    assert remains(stored) == ALL_PRESENT
    assert ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=stored.pk).count() == 2


def test_a_delete_rolled_back_by_an_enclosing_transaction_keeps_every_row(stored):
    with pytest.raises(Boom):
        with transaction.atomic():
            delete_meeting(stored)
            assert remains(stored) == ALL_GONE
            raise Boom

    assert remains(stored) == ALL_PRESENT


def test_only_this_meetings_rows_are_deleted(stored, employee):
    """By ``source_type`` and ``source_id`` together: a document chunk or tag link that happened
    to carry the same identifier, and another meeting's rows, are untouched."""
    other = make_meeting("Other", employee)
    document_chunk = chunk(DOCUMENT_SOURCE_TYPE, stored.id)
    document_link = tag_link(DOCUMENT_SOURCE_TYPE, stored.id)

    delete_meeting(stored)

    assert remains(stored) == ALL_GONE
    assert remains(other) == ALL_PRESENT
    assert ContentChunk.objects.filter(pk=document_chunk.pk).exists()
    assert ContentTag.objects.filter(pk=document_link.pk).exists()
    # The tag itself is vocabulary, and stays.
    assert Tag.objects.filter(tag_name="bridge maintenance").exists()
    # The attendee's user is a person, not a derived row.
    assert type(employee).objects.filter(pk=employee.pk).exists()


def test_a_meeting_already_deleted_by_a_concurrent_request_is_tolerated(stored):
    """The caller resolved the row, and another delete committed before the lock was taken."""
    stale = Meeting.objects.get(pk=stored.pk)
    delete_meeting(stored)

    delete_meeting(stale)

    assert remains(stored) == ALL_GONE


def test_the_meeting_row_is_locked_before_its_chunks_are_deleted(stored):
    """The order, read from the SQL: a ``FOR UPDATE`` on the meetings row, then the chunk delete.
    Without the lock first, a delete running during a re-index sees only the chunks committed
    before it, and the re-index then commits fresh ones for a deleted meeting."""
    with CaptureQueriesContext(connection) as queries:
        delete_meeting(stored)

    statements = [query["sql"] for query in queries.captured_queries]
    lock = next(i for i, sql in enumerate(statements)
                if 'FROM "meetings"' in sql and "FOR UPDATE" in sql)
    chunk_delete = next(i for i, sql in enumerate(statements)
                        if sql.startswith('DELETE FROM "content_chunks"'))
    assert lock < chunk_delete
