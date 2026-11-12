"""FR-09's ingestion asks for the meeting's summary, and can never be failed by it (FR-16, D-125).

FR-16 Business logic (isolation): "summary failure never blocks the transcript from being stored or
searched" (CLAUDE.md invariant 8, NFR-20). The hook in apps/ingestion/meetings.py requests the run
after the meeting's status has been decided, in a savepoint of its own, with every exception caught;
and the run itself starts only when the ingestion has committed, so no model is asked to summarise
anything while the ingestion transaction is open. UC-04's precondition is stored text, not an
index, so a run is requested on both "stored, not indexed" outcomes too.
"""

import logging

import pytest
from django.db import transaction

import apps.ingestion.meetings as ingestion
from apps.ai.base import ProviderUnavailable
from apps.core.constants import (
    MEETING_INDEXED,
    MEETING_PROCESSING_FAILED,
    MINIMUM_CONTENT_LENGTH,
    MINIMUM_SUMMARY_TRANSCRIPT_LENGTH,
    SUMMARY_FAILED_INDEXING,
    SUMMARY_PROCESSING,
    SUMMARY_READY,
    SUMMARY_UNAVAILABLE,
)
from apps.documents.models import ContentChunk
from apps.ingestion.meetings import ingest_meeting_transcript
from apps.meetings.models import Meeting, MeetingSummary
from apps.meetings.tests.summary_builders import MEETING_DATE, TITLE, ingest, transcript

pytestmark = pytest.mark.django_db


def outcome_of(**overrides):
    return ingest_meeting_transcript(
        **{"title": TITLE, "meeting_date": MEETING_DATE, "transcript_text": transcript(),
           "visible_to_roles": ["Employee", "Administrator"], **overrides}
    )


def test_ingestion_requests_one_run_and_sends_nothing_to_the_model_until_it_has_committed(
    django_capture_on_commit_callbacks, stub_ai_service
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        outcome = outcome_of()

    assert outcome.http_status == 201 and outcome.meeting.status == MEETING_INDEXED
    [run] = MeetingSummary.objects.filter(meeting=outcome.meeting)
    assert (run.status, run.requested_by, run.run_number) == (SUMMARY_PROCESSING, None, 1)
    # The transcript was embedded, and no summary call was made inside the ingestion.
    assert stub_ai_service.embed_calls and stub_ai_service.summarise_calls == []
    assert len(callbacks) == 1

    callbacks[0]()
    run.refresh_from_db()
    assert run.status == SUMMARY_READY and len(stub_ai_service.summarise_calls) == 1


def test_a_transcript_under_the_summary_minimum_is_stored_and_indexed_with_no_run(
    django_capture_on_commit_callbacks, stub_ai_service
):
    """FR-09's floor is MINIMUM_CONTENT_LENGTH; FR-16's is higher. Between them a meeting is a
    meeting, searchable, and simply has no summary."""
    words = MINIMUM_SUMMARY_TRANSCRIPT_LENGTH - 1
    assert words > MINIMUM_CONTENT_LENGTH

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        meeting = ingest(text=transcript(words))

    assert meeting.status == MEETING_INDEXED
    assert ContentChunk.objects.filter(source_id=meeting.id).exists()
    assert not MeetingSummary.objects.filter(meeting=meeting).exists()
    assert len(callbacks) == 0 and stub_ai_service.summarise_calls == []


def test_a_meeting_whose_every_chunk_failed_to_embed_still_gets_a_run(
    django_capture_on_commit_callbacks, stub_ai_service, monkeypatch
):
    """UC-04 needs the stored text, not the index. The run is requested; with embedding still
    down it cannot index its summary, so it ends Unavailable and queued, and the transcript stays."""

    def down(texts, *, input_type=None):
        raise ProviderUnavailable("embedding is down")

    monkeypatch.setattr(stub_ai_service, "embed", down)

    with django_capture_on_commit_callbacks(execute=True):
        outcome = outcome_of()

    assert outcome.http_status == 422 and outcome.meeting.status == MEETING_PROCESSING_FAILED
    run = MeetingSummary.objects.get(meeting=outcome.meeting)
    assert (run.status, run.failure_reason, run.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_INDEXING, True,
    )
    assert Meeting.objects.get(pk=outcome.meeting.pk).transcript_text == transcript()


def test_a_meeting_too_large_to_index_still_gets_a_run(django_capture_on_commit_callbacks, monkeypatch):
    monkeypatch.setattr(ingestion, "MAXIMUM_CHUNKS_PER_SOURCE", 0)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        outcome = outcome_of()

    assert outcome.http_status == 422 and outcome.detail == ingestion.TOO_MANY_CHUNKS_MESSAGE
    assert MeetingSummary.objects.filter(meeting=outcome.meeting, status=SUMMARY_PROCESSING).count() == 1
    assert len(callbacks) == 1


def test_a_hook_that_raises_costs_the_ingestion_nothing(
    django_capture_on_commit_callbacks, monkeypatch, caplog
):
    """Invariant 8: every exception is caught and logged, and the meeting, its chunks, its status
    and its 201 are exactly what they would have been."""

    def broken(meeting, **kwargs):
        raise RuntimeError("the summary request is broken")

    monkeypatch.setattr(ingestion, "request_summary", broken)

    with caplog.at_level(logging.ERROR, logger="apps.ingestion.meetings"):
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            outcome = outcome_of()

    assert outcome.http_status == 201 and outcome.meeting.status == MEETING_INDEXED
    assert Meeting.objects.filter(pk=outcome.meeting.pk).exists()
    assert ContentChunk.objects.filter(source_id=outcome.meeting.id, ai_generated=False).exists()
    assert not MeetingSummary.objects.filter(meeting=outcome.meeting).exists() and len(callbacks) == 0
    [record] = [r for r in caplog.records if "its summary could not be requested" in r.getMessage()]
    assert record.exc_info is not None  # the traceback is logged, not swallowed


def test_an_ingestion_that_rolls_back_leaves_no_run_and_starts_none(
    django_capture_on_commit_callbacks, stub_ai_service
):
    class Abandoned(Exception):
        pass

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(Abandoned):
            with transaction.atomic():
                outcome_of()
                raise Abandoned

    assert not Meeting.objects.exists() and not MeetingSummary.objects.exists()
    assert len(callbacks) == 0 and stub_ai_service.summarise_calls == []


def test_post_api_meetings_answers_201_whatever_the_summary_then_does(
    session_client, django_capture_on_commit_callbacks, stub_ai_service
):
    """Through the route, from both roles: the 201 and its body are FR-09's own, unchanged by FR-16,
    and a summary that then fails takes nothing back."""

    def fails(title, passages):
        raise ProviderUnavailable("the provider is down")

    stub_ai_service.summary = fails
    body = {"title": TITLE, "meeting_date": MEETING_DATE.isoformat(), "transcript_text": transcript()}

    with django_capture_on_commit_callbacks(execute=True):
        response = session_client.client.post("/api/meetings", body, format="json")

    assert response.status_code == 201
    assert "summary" not in response.json() and response.json()["status"] == MEETING_INDEXED
    meeting_id = response.json()["meeting_id"]
    assert MeetingSummary.objects.get(meeting_id=meeting_id).status == SUMMARY_UNAVAILABLE
    assert session_client.client.get(f"/api/meetings/{meeting_id}").json()["transcript_text"] == transcript()
    assert session_client.client.get("/api/search", {"q": "budget7"}).json()["total_count"] == 1
