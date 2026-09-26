"""FR-09 meeting transcript ingestion: ``/api/meetings``.

    Users can upload a transcript file or paste transcript text directly into a
    form, associating it with a meeting title, date, and attendees. ... Once
    processed, the stored transcript is then viewable in full.

    Validation: title and date are required; the date may not be in the future;
    transcript content must exceed a minimum length, since a near-empty transcript
    produces unusable AI output.

    Responses: 201 Created with the meeting ID; 400 Bad Request for missing fields
    or insufficient content.

Note the difference from FR-08: too little content is **400** here and **422**
there. Each requirement gets the code its own Responses clause names, rather than
one being made to match the other.

Speaker and timestamp parsing is explicitly out of scope for this version, and
``test_a_transcript_is_stored_verbatim`` proves the transcript survives untouched
rather than merely that nothing was written to parse it.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MEETING_INDEXED,
    ROLE_NAMES,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk
from apps.meetings.models import Meeting, MeetingAttendee

MEETINGS_URL = "/api/meetings"

pytestmark = pytest.mark.django_db

# Comfortably over MINIMUM_CONTENT_LENGTH (50 tokens, D-31). Written as a real
# transcript, with the speaker labels and timestamps FR-09 declines to parse.
TRANSCRIPT = """[09:02] Priya Raman: Right, let's start with the delegation review.
The finance team has asked us to confirm the approval thresholds before the audit.
[09:04] Tom Oyelaran: The current threshold is ten thousand dollars for a second
approval. Anything below that sits with the requesting manager alone.
[09:07] Priya Raman: And we agreed last quarter to leave that where it is for now,
because moving it would have meant retraining every delegate before the end of the
financial year.
[09:11] Tom Oyelaran: Agreed. I will confirm that in writing to the finance team
this afternoon so the audit has something to point at.
"""

SHORT_TRANSCRIPT = "We met. We agreed. We left."


def post_meeting(client, **fields):
    body = {
        "title": "Q3 Planning Sync",
        "meeting_date": str(timezone.localdate()),
        "transcript_text": TRANSCRIPT,
        **fields,
    }
    body = {key: value for key, value in body.items() if value is not None}
    return client.post(MEETINGS_URL, body, format="json")


# --- The happy path, from both roles --------------------------------------------------


def test_a_pasted_transcript_is_ingested(session_client):
    response = post_meeting(session_client.client)

    assert response.status_code == 201, response.data
    # FR-09 Responses: "201 Created with the meeting ID".
    meeting = Meeting.objects.get(pk=response.data["meeting_id"])
    assert meeting.status == MEETING_INDEXED
    assert response.data["title"] == "Q3 Planning Sync"


def test_a_transcript_is_chunked_and_embedded_by_the_same_path_as_a_document(
    employee_client,
):
    """FR-09: the transcript is "passed to the chunking and embedding process in
    FR-08, making meeting content searchable alongside documents"."""
    response = post_meeting(employee_client)

    chunks = ContentChunk.objects.filter(
        source_type=SOURCE_TYPES[1], source_id=response.data["meeting_id"]
    )
    assert chunks.exists()
    for chunk in chunks:
        assert chunk.embedding_model
        assert chunk.embedding_dimension
        # D-17: the FR-11 predicate is stamped on the chunk, for meetings exactly as
        # for documents, so Stage 4 has one filter and not two.
        assert chunk.visible_to_roles == list(ROLE_NAMES)


def test_a_transcript_is_stored_verbatim(employee_client):
    """"Structural parsing of speaker labels and timestamps is out of scope for this
    version." Out of scope means untouched, not quietly stripped: a transcript whose
    timestamps were removed could not be checked against the recording later."""
    response = post_meeting(employee_client)

    meeting = Meeting.objects.get(pk=response.data["meeting_id"])
    assert meeting.transcript_text == TRANSCRIPT
    assert "[09:02] Priya Raman:" in meeting.transcript_text
    # And the stored chunks carry the labels too, rather than a cleaned-up version.
    combined = " ".join(
        ContentChunk.objects.filter(source_id=meeting.pk)
        .order_by("chunk_index")
        .values_list("chunk_text", flat=True)
    )
    assert "Tom Oyelaran" in combined


def test_an_uploaded_transcript_file_is_ingested(session_client, upload):
    """The other half of "upload a transcript file or paste transcript text"."""
    response = session_client.client.post(
        MEETINGS_URL,
        {
            "title": "Policy workshop",
            "meeting_date": str(timezone.localdate()),
            "file": upload("sample.txt"),
        },
        format="multipart",
    )

    assert response.status_code == 201, response.data
    meeting = Meeting.objects.get(pk=response.data["meeting_id"])
    assert "Annual leave is accrued" in meeting.transcript_text


def test_a_transcript_file_of_an_unrecognised_format_is_rejected(employee_client, upload):
    response = employee_client.post(
        MEETINGS_URL,
        {
            "title": "Policy workshop",
            "meeting_date": str(timezone.localdate()),
            "file": upload("disguised.pdf"),
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert "file" in response.data
    assert not Meeting.objects.exists()


def test_a_transcript_archive_declaring_more_than_it_may_inflate_is_rejected(employee_client):
    """The same bound as FR-08's upload (Stage 4 item 12b), in this endpoint's own shape.

    FR-09 enumerates only 201 and 400, so the transcript path cannot answer FR-08's 413 —
    it reports a field error instead, and the MESSAGE is what keeps the two rejections
    distinguishable: this file's format was never the problem, so it must not be told that
    its type is unsupported.
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.ingestion.tests.builders import ooxml_declaring

    bomb = SimpleUploadedFile(
        "workshop.docx",
        ooxml_declaring(
            {"word/document.xml": b"A" * 100_003},
            declared_sizes={"word/document.xml": 200 * 1024 * 1024},
        ),
    )

    response = employee_client.post(
        MEETINGS_URL,
        {
            "title": "Policy workshop",
            "meeting_date": str(timezone.localdate()),
            "file": bomb,
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert "expand" in response.data["file"][0]
    assert "not supported" not in response.data["file"][0]
    assert not Meeting.objects.exists()


# --- Validation: FR-09's own 400s -----------------------------------------------------


@pytest.mark.parametrize("missing", ["title", "meeting_date"])
def test_title_and_date_are_required(employee_client, missing):
    response = post_meeting(employee_client, **{missing: None})

    assert response.status_code == 400
    assert missing in response.data


def test_an_empty_title_is_rejected(employee_client):
    assert post_meeting(employee_client, title="   ").status_code == 400


def test_a_future_date_is_rejected(employee_client):
    """FR-09: "the date may not be in the future"."""
    tomorrow = timezone.localdate() + timedelta(days=1)

    response = post_meeting(employee_client, meeting_date=str(tomorrow))

    assert response.status_code == 400
    assert "meeting_date" in response.data
    assert not Meeting.objects.exists()


def test_todays_date_is_accepted(employee_client):
    """The boundary the check above sits on: today is not the future."""
    response = post_meeting(employee_client, meeting_date=str(timezone.localdate()))

    assert response.status_code == 201


def test_a_transcript_below_the_minimum_length_is_rejected(employee_client):
    """FR-09 answers 400 for this, where FR-08 answers 422 for a document."""
    response = post_meeting(employee_client, transcript_text=SHORT_TRANSCRIPT)

    assert response.status_code == 400
    assert "transcript_text" in response.data
    assert not Meeting.objects.exists()
    assert not ContentChunk.objects.exists()


def test_neither_text_nor_file_is_rejected(employee_client):
    response = employee_client.post(
        MEETINGS_URL,
        {"title": "Q3 Planning Sync", "meeting_date": str(timezone.localdate())},
        format="json",
    )

    assert response.status_code == 400


def test_both_text_and_file_is_rejected(employee_client, upload):
    """Ambiguous rather than harmless: whichever the server picked, the other would
    be discarded in silence."""
    response = employee_client.post(
        MEETINGS_URL,
        {
            "title": "Q3 Planning Sync",
            "meeting_date": str(timezone.localdate()),
            "transcript_text": TRANSCRIPT,
            "file": upload("sample.txt"),
        },
        format="multipart",
    )

    assert response.status_code == 400


# --- Attendees: a participation record, never an access control (D-16) -----------------


def test_attendees_are_recorded(employee_client, employee, administrator):
    response = post_meeting(
        employee_client, attendees=[str(employee.id), str(administrator.id)]
    )

    assert response.status_code == 201
    meeting = Meeting.objects.get(pk=response.data["meeting_id"])
    assert MeetingAttendee.objects.filter(meeting=meeting).count() == 2
    assert set(response.data["attendees"]) == {employee.email, administrator.email}


def test_an_unknown_attendee_is_rejected(employee_client):
    import uuid

    response = post_meeting(employee_client, attendees=[str(uuid.uuid4())])

    assert response.status_code == 400
    assert "attendees" in response.data
    assert not Meeting.objects.exists()


def test_attendance_does_not_grant_access(employee_client, employee, administrator_client):
    """D-16, stated as a test: meetings are scoped by role, never by attendance.

    An Employee who attended a meeting visible only to Administrators still cannot
    see it, and the scoping does not consult MeetingAttendees at all.
    """
    response = post_meeting(
        administrator_client,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
        attendees=[str(employee.id)],
    )
    assert response.status_code == 201
    meeting_id = response.data["meeting_id"]

    assert employee_client.get(f"{MEETINGS_URL}/{meeting_id}").status_code == 404
    assert employee_client.get(MEETINGS_URL).data == []


# --- Reading: FR-09's "viewable in full" ------------------------------------------------


def test_the_stored_transcript_is_viewable_in_full(session_client):
    created = post_meeting(session_client.client)

    response = session_client.client.get(f"{MEETINGS_URL}/{created.data['meeting_id']}")

    assert response.status_code == 200
    assert response.data["transcript_text"] == TRANSCRIPT


def test_the_listing_omits_the_transcript_body(session_client):
    post_meeting(session_client.client)

    response = session_client.client.get(MEETINGS_URL)

    assert response.status_code == 200
    assert len(response.data) == 1
    # A table of titles and dates should not ship every transcript in the
    # organisation; the detail route serves the text.
    assert "transcript_text" not in response.data[0]
    assert response.data[0]["title"] == "Q3 Planning Sync"


def test_a_meeting_outside_the_callers_scope_is_not_found(administrator_client, employee_client):
    """404, not 403: a 403 would confirm the id names something real (CLAUDE.md
    invariant 1 — the existence of out-of-scope material is not disclosed)."""
    created = post_meeting(administrator_client, visible_to_roles=[ADMINISTRATOR_ROLE_NAME])

    assert employee_client.get(f"{MEETINGS_URL}/{created.data['meeting_id']}").status_code == 404


def test_the_listing_is_scoped_to_the_callers_role(session_client, administrator_client):
    post_meeting(administrator_client, visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
                 title="Board minutes")

    response = session_client.client.get(MEETINGS_URL)

    assert response.status_code == 200
    titles = {row["title"] for row in response.data}
    if session_client.role_name == EMPLOYEE_ROLE_NAME:
        assert titles == set()
    else:
        assert titles == {"Board minutes"}


# --- Authorisation ----------------------------------------------------------------------


def test_an_anonymous_caller_is_unauthorised(api_client):
    assert post_meeting(api_client).status_code == 401
    assert api_client.get(MEETINGS_URL).status_code == 401


def test_a_role_without_contribute_content_cannot_ingest(employee, employee_client):
    from apps.accounts.models import RolePermission

    RolePermission.objects.filter(
        role=employee.role, permission__permission_name="contribute_content"
    ).delete()

    assert post_meeting(employee_client).status_code == 403
    assert not Meeting.objects.exists()
    # Reading is not contributing: the listing is still permitted.
    assert employee_client.get(MEETINGS_URL).status_code == 200


def test_an_ingester_may_not_exclude_their_own_role(employee_client):
    response = post_meeting(employee_client, visible_to_roles=[ADMINISTRATOR_ROLE_NAME])

    assert response.status_code == 403
    assert not Meeting.objects.exists()


def test_the_detail_route_is_401_anonymously(api_client, administrator_client):
    created = post_meeting(administrator_client)

    assert api_client.get(f"{MEETINGS_URL}/{created.data['meeting_id']}").status_code == 401
