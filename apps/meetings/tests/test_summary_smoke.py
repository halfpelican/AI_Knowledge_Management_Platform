"""A first end-to-end pass over FR-16's apply layer; replaced by the full modules beside it."""

import pytest

from apps.core.constants import SUMMARY_PROCESSING, SUMMARY_READY
from apps.documents.models import ContentChunk
from apps.meetings.models import ActionItem, MeetingSummary
from apps.meetings.tests.summary_builders import ingest

pytestmark = pytest.mark.django_db


def test_ingestion_requests_a_summary_and_the_commit_runs_it(django_capture_on_commit_callbacks, stub_ai_service):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        meeting = ingest()
    [summary] = MeetingSummary.objects.filter(meeting=meeting)
    assert summary.status == SUMMARY_PROCESSING
    assert stub_ai_service.summarise_calls == []
    assert len(callbacks) == 1

    callbacks[0]()
    summary.refresh_from_db()
    assert summary.status == SUMMARY_READY, summary.failure_reason
    assert summary.summary_text
    assert ActionItem.objects.filter(meeting=meeting).count() == 1
    assert ContentChunk.objects.filter(source_id=meeting.id, ai_generated=True).count() == 1
