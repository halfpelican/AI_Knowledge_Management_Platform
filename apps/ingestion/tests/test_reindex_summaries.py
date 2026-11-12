"""``manage.py reindex`` and a meeting's AI-generated summary (FR-16, D-125; risk R10).

A Ready summary is indexed as passages of the meeting itself, marked ``ai_generated``. ``reindex``
rebuilds a meeting by deleting every chunk of it and re-embedding from stored text, so without
this the first provider switch would silently drop every summary from search: the transcript's
chunks would come back and the summary's would not. These tests hold the rebuild to the summary
too, from its stored text and with no model asked to summarise anything.
"""

import io

import pytest
from django.core.management import call_command

from apps.ai.base import ProviderUnavailable
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, MEETING_INDEXED, SOURCE_TYPES, SUMMARY_READY
from apps.documents.models import ContentChunk
from apps.ingestion.management.commands.reindex import PROBE_TEXT
from apps.meetings.models import Meeting, MeetingSummary
from apps.meetings.tests.summary_builders import draft, element, ingest

pytestmark = pytest.mark.django_db

_, MEETING_SOURCE_TYPE = SOURCE_TYPES
STALE_MODEL = "some-older-embedding-model"
SENTENCE = "The team agreed to freeze discretionary travel."
DECISION = "Travel is frozen until January."


def reindex(*args):
    out, err = io.StringIO(), io.StringIO()
    call_command("reindex", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


@pytest.fixture
def summarised(stub_ai_service, django_capture_on_commit_callbacks):
    """A meeting with a Ready summary, every chunk of it recorded against an OLD model: the
    state a provider switch leaves behind."""
    stub_ai_service.summary = draft(narrative=[element(SENTENCE)], decisions=[element(DECISION)])
    with django_capture_on_commit_callbacks(execute=True):
        meeting = ingest(visible_to_roles=[ADMINISTRATOR_ROLE_NAME])
    assert MeetingSummary.objects.get(meeting=meeting).status == SUMMARY_READY
    ContentChunk.objects.filter(source_id=meeting.id).update(embedding_model=STALE_MODEL)
    return meeting


def chunks_of(meeting, *, ai_generated):
    return ContentChunk.objects.filter(
        source_type=MEETING_SOURCE_TYPE, source_id=meeting.id, ai_generated=ai_generated
    )


def test_a_reindex_rebuilds_the_summarys_chunks_beside_the_transcripts(summarised, stub_ai_service):
    before = set(chunks_of(summarised, ai_generated=True).values_list("id", flat=True))
    stub_ai_service.summarise_calls.clear()

    out, err = reindex()

    [summary_chunk] = chunks_of(summarised, ai_generated=True)
    assert summary_chunk.id not in before  # rebuilt, not carried over
    assert summary_chunk.embedding_model == STUB_EMBEDDING_MODEL  # the model that answered now
    assert summary_chunk.chunk_text == f"{SENTENCE}\n{DECISION}"
    # Stamped from the meeting's own row, as every rebuilt chunk is (D-17, invariant 2).
    assert summary_chunk.visible_to_roles == [ADMINISTRATOR_ROLE_NAME]
    assert chunks_of(summarised, ai_generated=False).exists()
    assert not ContentChunk.objects.filter(embedding_model=STALE_MODEL).exists()
    assert "its summary re-embedded" in out and err == ""
    # Embedded again, never summarised again: no model call, and the summary row is unchanged.
    assert stub_ai_service.summarise_calls == []
    assert MeetingSummary.objects.get(meeting=summarised).summary_text == SENTENCE


def test_a_meeting_without_a_ready_summary_gets_no_summary_chunk(stub_ai_service, django_capture_on_commit_callbacks):
    def outage(title, passages):
        raise ProviderUnavailable("the provider is down")

    stub_ai_service.summary = outage
    with django_capture_on_commit_callbacks(execute=True):
        meeting = ingest()

    out, _ = reindex()

    assert not chunks_of(meeting, ai_generated=True).exists()
    assert chunks_of(meeting, ai_generated=False).exists()
    assert "its summary re-embedded" not in out


class _RefusesTheSummary:
    """Embeds everything but the summary's own text, as a provider failing on that one input would."""

    def __init__(self, stub):
        self._stub = stub

    def embed(self, texts, *, input_type=None):
        if any(SENTENCE in text for text in texts):
            raise ProviderUnavailable("the provider is down for this text")
        return self._stub.embed(texts, input_type=input_type)

    def __getattr__(self, name):
        return getattr(self._stub, name)


def test_a_summary_that_cannot_be_embedded_fails_the_meeting_and_rolls_it_back(
    summarised, stub_ai_service, monkeypatch
):
    """The meeting's chunks and its summary's commit together or not at all: a rebuild that
    cannot embed the summary leaves the meeting exactly as it was, reported as failed."""
    import apps.ai

    before = set(ContentChunk.objects.filter(source_id=summarised.id).values_list("id", flat=True))
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: _RefusesTheSummary(stub_ai_service))

    out, err = reindex()

    assert "SummaryIndexingFailed" in err
    assert "Done: 0 rebuilt, 0 skipped, 1 failed." in out
    assert set(ContentChunk.objects.filter(source_id=summarised.id).values_list("id", flat=True)) == before
    assert Meeting.objects.get(pk=summarised.pk).status == MEETING_INDEXED


def test_a_dry_run_embeds_nothing_of_the_summary_and_leaves_its_chunks(summarised, stub_ai_service):
    """--dry-run makes the one probe call and touches no row, the summary's included."""
    stub_ai_service.embed_calls.clear()

    reindex("--dry-run")

    assert stub_ai_service.embed_calls == [[PROBE_TEXT]]
    assert chunks_of(summarised, ai_generated=True).get().embedding_model == STALE_MODEL
