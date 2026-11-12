"""NFR-20 and UC-04 E1: a summary's failure never touches the transcript, and the failed summary
is queued for an automatic retry (apps/meetings/summaries.py, D-125 choice 2).

NFR-20: "the raw transcript must still be stored, retrievable, and flagged for automatic retry";
its test: "Simulate summary-generation failure; confirm the raw transcript persists, is searchable,
and appears in a retry queue." **That test is the last section of this file, through HTTP and from
both roles**: with summarisation failing, ``POST /api/meetings`` still answers 201, the transcript
comes back from ``GET /api/meetings/{id}``, ``GET /api/search`` finds a word of it, ``POST
/api/ask`` cites it, and its summary is in ``retry_queue()``. It is run with an outage the provider
decided and with an error nobody expected, because CLAUDE.md invariant 8 is about ANY failed AI
step.

Before it, the queue's own rules:

- every way a run fails ends Unavailable and queued, under its own reason;
- ``retry_summary`` runs a queued row again, and a success takes it out of the queue Ready;
- after MAXIMUM_SUMMARY_RETRY_RUNS failed queued runs the row stays Unavailable, NOT queued,
  until a person asks again;
- a new request supersedes whatever was waiting;
- a run a stopped server left Processing is reclaimed once it is older than
  SUMMARY_STALE_AFTER_SECONDS, and a fresh one is left alone.

``manage.py retry_meeting_summaries``, which drives these on the hourly schedule, is tested in
apps/meetings/tests/test_summary_commands.py. Rows are told apart by ``run_number`` and by
content, never by a timestamp, and staleness is tested through ``reclaim_orphans(now=...)``.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.ai.base import EmbeddingResult, MalformedSummary, ProviderRefused, ProviderUnavailable
from apps.ai.summarisation import SUMMARY_TIMEOUT_SECONDS
from apps.ai.testing import STUB_EMBEDDING_MODEL, StubAIService
from apps.core.constants import (
    MAXIMUM_SUMMARY_ATTEMPTS,
    MAXIMUM_SUMMARY_RETRY_RUNS,
    MEETING_INDEXED,
    SOURCE_TYPES,
    SUMMARY_FAILED_ERROR,
    SUMMARY_FAILED_MALFORMED,
    SUMMARY_FAILED_ORPHANED,
    SUMMARY_FAILED_PROVIDER_REFUSED,
    SUMMARY_FAILED_PROVIDER_UNAVAILABLE,
    SUMMARY_FAILURE_REASONS,
    SUMMARY_PROCESSING,
    SUMMARY_READY,
    SUMMARY_STALE_AFTER_SECONDS,
    SUMMARY_UNAVAILABLE,
)
from apps.documents.models import ContentChunk
from apps.ingestion.tests.ai_doubles import install
from apps.meetings.models import ActionItem, Meeting, MeetingSummary
from apps.meetings.summaries import (
    current_summary,
    is_in_progress,
    latest_run,
    reclaim_orphans,
    request_summary,
    retry_queue,
    retry_summary,
)
from apps.meetings.tests.summary_builders import ingest, raising, regenerate, summarised, transcript

pytestmark = pytest.mark.django_db

_, MEETING_SOURCE_TYPE = SOURCE_TYPES
OUTAGE = ProviderUnavailable("stub outage")


def failed_meeting(stub_ai_service, capture, error=OUTAGE, **meeting):
    """A meeting whose first summary run has failed with ``error``."""
    stub_ai_service.summary = raising(error)
    ingested = summarised(capture, **meeting)
    return ingested, MeetingSummary.objects.get(meeting=ingested)


def make_stale(summary, *, by=60):
    """Move a run's start to before the staleness cut-off, as a server stopped long ago left it."""
    started = timezone.now() - timedelta(seconds=SUMMARY_STALE_AFTER_SECONDS + by)
    MeetingSummary.objects.filter(pk=summary.pk).update(started_at=started)
    summary.refresh_from_db()
    return summary


# --- Every way a run fails ends Unavailable and queued, under its own reason ------------------


@pytest.mark.parametrize(
    "error,reason",
    [
        (ProviderUnavailable("the provider did not answer in three attempts"), SUMMARY_FAILED_PROVIDER_UNAVAILABLE),
        (ProviderRefused("HTTP 401: invalid api key"), SUMMARY_FAILED_PROVIDER_REFUSED),
        (MalformedSummary("two replies broke SUMMARY_SCHEMA"), SUMMARY_FAILED_MALFORMED),
    ],
    ids=["provider_unavailable", "provider_refused", "malformed"],
)
def test_each_failure_ends_unavailable_and_queued_under_its_own_reason(
    stub_ai_service, django_capture_on_commit_callbacks, error, reason
):
    """ProviderRefused and MalformedSummary are both ProviderUnavailables, so a handler that
    caught the parent first would record every failure as an outage. The reason is what tells an
    operator whether to check the key, the prompt or the server."""
    meeting, summary = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks, error)

    assert summary.status == SUMMARY_UNAVAILABLE
    assert summary.failure_reason == reason
    assert summary.queued_for_retry is True
    assert list(retry_queue()) == [summary]
    assert (summary.retry_runs, summary.summary_text, summary.generated_at) == (0, "", None)
    summary.full_clean()  # the reason is one of the fixed vocabulary
    # The transcript is untouched: stored as submitted, indexed, and not a word shorter.
    stored = Meeting.objects.get(pk=meeting.pk)
    assert (stored.status, stored.transcript_text) == (MEETING_INDEXED, transcript())
    assert ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id, ai_generated=False).exists()
    assert len(stub_ai_service.summarise_calls) == 1  # the provider's own retries are inside the call


def test_the_failure_reasons_are_the_fixed_vocabulary():
    assert SUMMARY_FAILURE_REASONS == (
        "provider_unavailable", "provider_refused", "malformed", "no_verified_narrative", "indexing_failed",
        "orphaned", "error",
    )
    summary = MeetingSummary(meeting=Meeting(title="x", meeting_date="2026-11-10"), failure_reason="because")
    with pytest.raises(ValidationError) as excinfo:
        summary.full_clean(exclude=["meeting"])
    assert "failure_reason" in excinfo.value.error_dict


# --- retry_summary --------------------------------------------------------------------------------


def test_a_retry_that_succeeds_leaves_the_queue_ready(stub_ai_service, django_capture_on_commit_callbacks):
    meeting, failed = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    stub_ai_service.summary = None  # the provider is back

    retried = retry_summary(failed)

    assert retried.pk == failed.pk and retried.run_number == 1  # the same run, not a new one
    assert (retried.status, retried.queued_for_retry, retried.failure_reason) == (SUMMARY_READY, False, "")
    assert retried.retry_runs == 1
    assert retried.summary_text and retried.generated_at is not None
    assert list(retry_queue()) == []
    assert current_summary(meeting) == retried
    assert ActionItem.objects.filter(meeting=meeting).count() == 1
    assert ContentChunk.objects.filter(source_id=meeting.id, ai_generated=True).count() == 1
    assert len(stub_ai_service.summarise_calls) == 2


def test_a_retry_that_fails_moves_the_count_on_and_queues_the_run_again(
    stub_ai_service, django_capture_on_commit_callbacks
):
    meeting, failed = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    stub_ai_service.summary = raising(MalformedSummary("still malformed"))

    retried = retry_summary(failed)

    assert (retried.status, retried.queued_for_retry, retried.retry_runs) == (SUMMARY_UNAVAILABLE, True, 1)
    assert retried.failure_reason == SUMMARY_FAILED_MALFORMED  # this run's reason, not the first one's
    assert list(retry_queue()) == [retried]


def test_after_the_last_queued_run_fails_the_summary_is_unavailable_and_not_queued(
    stub_ai_service, django_capture_on_commit_callbacks
):
    """MAXIMUM_SUMMARY_RETRY_RUNS queued runs, after the first one: then it waits for a person.
    Queued after the first failure and after each retry but the last, an equality at each step."""
    assert MAXIMUM_SUMMARY_RETRY_RUNS == 3
    meeting, summary = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    assert (summary.retry_runs, summary.queued_for_retry) == (0, True)

    for run in range(1, MAXIMUM_SUMMARY_RETRY_RUNS + 1):
        summary = retry_summary(summary)
        assert summary.status == SUMMARY_UNAVAILABLE
        assert summary.retry_runs == run
        assert summary.queued_for_retry is (run < MAXIMUM_SUMMARY_RETRY_RUNS), run

    assert summary.queued_for_retry is False
    assert list(retry_queue()) == []
    assert len(stub_ai_service.summarise_calls) == 1 + MAXIMUM_SUMMARY_RETRY_RUNS
    assert is_in_progress(summary) is False  # the routes stop answering 202 for it

    # A further retry does nothing: the row is not in the queue.
    again = retry_summary(summary)
    assert (again.retry_runs, again.status, again.queued_for_retry) == (MAXIMUM_SUMMARY_RETRY_RUNS, SUMMARY_UNAVAILABLE, False)
    assert len(stub_ai_service.summarise_calls) == 1 + MAXIMUM_SUMMARY_RETRY_RUNS

    # Until a person presses Generate: a new run, with a queue allowance of its own.
    stub_ai_service.summary = None
    fresh = regenerate(django_capture_on_commit_callbacks, meeting)
    assert (fresh.run_number, fresh.status, fresh.retry_runs) == (2, SUMMARY_READY, 0)


@pytest.mark.parametrize("state", ["ready", "processing", "unavailable and not queued"])
def test_retrying_a_run_that_is_not_in_the_queue_does_nothing(
    stub_ai_service, django_capture_on_commit_callbacks, state
):
    if state == "ready":
        meeting = summarised(django_capture_on_commit_callbacks)
    elif state == "processing":
        with django_capture_on_commit_callbacks(execute=False):
            meeting = ingest()
    else:
        meeting, _ = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)
        MeetingSummary.objects.filter(meeting=meeting).update(queued_for_retry=False)
    summary = MeetingSummary.objects.get(meeting=meeting)
    before = (summary.status, summary.retry_runs, summary.queued_for_retry, summary.failure_reason)
    calls = len(stub_ai_service.summarise_calls)

    returned = retry_summary(summary)

    assert returned.pk == summary.pk
    summary.refresh_from_db()
    assert (summary.status, summary.retry_runs, summary.queued_for_retry, summary.failure_reason) == before
    assert len(stub_ai_service.summarise_calls) == calls


def test_a_retry_of_a_failed_regenerate_replaces_the_previous_summary_when_it_succeeds(
    stub_ai_service, django_capture_on_commit_callbacks
):
    meeting = summarised(django_capture_on_commit_callbacks)
    first = MeetingSummary.objects.get(meeting=meeting)
    stub_ai_service.summary = raising(OUTAGE)
    second = regenerate(django_capture_on_commit_callbacks, meeting)
    assert second.queued_for_retry is True and current_summary(meeting) == first

    stub_ai_service.summary = None
    retried = retry_summary(second)

    assert (retried.pk, retried.status) == (second.pk, SUMMARY_READY)
    assert current_summary(meeting) == latest_run(meeting) == retried


def test_the_queue_is_oldest_request_first(stub_ai_service, django_capture_on_commit_callbacks):
    """``requested_at`` is set here, a day apart, rather than left to three rows written inside
    one tick of this machine's clock."""
    now = timezone.now()
    rows = {}
    for name, age in (("middle", 2), ("oldest", 3), ("newest", 1)):
        _, summary = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks, title=name)
        MeetingSummary.objects.filter(pk=summary.pk).update(requested_at=now - timedelta(days=age))
        rows[name] = summary

    assert [summary.meeting.title for summary in retry_queue()] == ["oldest", "middle", "newest"]


def test_the_queue_holds_only_rows_flagged_for_retry(stub_ai_service, django_capture_on_commit_callbacks):
    ready = summarised(django_capture_on_commit_callbacks, title="Ready")
    with django_capture_on_commit_callbacks(execute=False):
        processing = ingest(title="Processing")
    _, queued = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks, title="Failed")

    assert list(retry_queue()) == [queued]
    assert MeetingSummary.objects.count() == 3
    assert {ready.title, processing.title}.isdisjoint({summary.meeting.title for summary in retry_queue()})


# --- A new request supersedes whatever was waiting ----------------------------------------------------


def test_a_new_request_takes_an_older_queued_run_out_of_the_queue(stub_ai_service, django_capture_on_commit_callbacks):
    """The newer result is the one wanted. The old run keeps its record of having failed, and is
    no longer run again behind the new one's back."""
    meeting, first = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    assert list(retry_queue()) == [first]

    with django_capture_on_commit_callbacks(execute=False):
        second, is_new = request_summary(meeting)

    first.refresh_from_db()
    assert (is_new, second.run_number, second.status) == (True, 2, SUMMARY_PROCESSING)
    assert (first.status, first.failure_reason, first.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_PROVIDER_UNAVAILABLE, False,
    )
    assert list(retry_queue()) == []
    calls = len(stub_ai_service.summarise_calls)
    assert retry_summary(first).pk == first.pk and len(stub_ai_service.summarise_calls) == calls  # a no-op now


def test_when_the_new_run_fails_too_only_the_new_run_is_queued(stub_ai_service, django_capture_on_commit_callbacks):
    meeting, first = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)

    second = regenerate(django_capture_on_commit_callbacks, meeting)

    assert (second.status, second.queued_for_retry) == (SUMMARY_UNAVAILABLE, True)
    assert list(retry_queue()) == [second]
    assert latest_run(meeting) == second


def test_a_ready_summary_leaves_no_older_run_of_its_meeting_in_the_queue(
    stub_ai_service, django_capture_on_commit_callbacks
):
    """An older run flagged while a newer one was out (a late failure) is unflagged by the newer
    run's success: the queue would otherwise replace a good summary with a retry of a stale one."""
    meeting, first = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    other_meeting, other = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks, title="Another meeting")
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        second, _ = request_summary(meeting)
    MeetingSummary.objects.filter(pk=first.pk).update(queued_for_retry=True)  # flagged again, late

    stub_ai_service.summary = None
    callbacks[0]()

    second.refresh_from_db()
    first.refresh_from_db()
    assert second.status == SUMMARY_READY
    assert first.queued_for_retry is False
    assert list(retry_queue()) == [other]  # another meeting's place in the queue is not this run's to give up


# --- A run a stopped server left Processing ---------------------------------------------------------------


def test_the_staleness_cut_off_is_longer_than_a_run_can_legitimately_take():
    """Three attempts of the slowest call, and then some. Shorter, and a run still working would
    be reclaimed and run a second time beside itself."""
    assert SUMMARY_STALE_AFTER_SECONDS > MAXIMUM_SUMMARY_ATTEMPTS * SUMMARY_TIMEOUT_SECONDS


def test_a_processing_run_older_than_the_cut_off_is_closed_as_orphaned_and_queued(
    stub_ai_service, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()
    summary = MeetingSummary.objects.get(meeting=meeting)
    just_past = summary.started_at + timedelta(seconds=SUMMARY_STALE_AFTER_SECONDS + 1)

    assert reclaim_orphans(now=just_past) == 1

    summary.refresh_from_db()
    assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_ORPHANED, True,
    )
    assert SUMMARY_FAILED_ORPHANED == "orphaned"
    assert list(retry_queue()) == [summary]
    assert stub_ai_service.summarise_calls == []  # reclaiming runs nothing; the queue does
    assert reclaim_orphans(now=just_past) == 0  # and it is not counted twice


def test_a_processing_run_within_the_cut_off_is_left_alone(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()
    summary = MeetingSummary.objects.get(meeting=meeting)

    assert reclaim_orphans() == 0  # by the clock: it started a moment ago
    assert reclaim_orphans(now=summary.started_at + timedelta(seconds=SUMMARY_STALE_AFTER_SECONDS)) == 0  # at the cut-off exactly
    assert reclaim_orphans(now=summary.started_at + timedelta(seconds=SUMMARY_STALE_AFTER_SECONDS - 1)) == 0

    summary.refresh_from_db()
    assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (SUMMARY_PROCESSING, "", False)


def test_reclaiming_by_the_clock_takes_every_stale_run_and_only_runs_that_are_processing(
    stub_ai_service, django_capture_on_commit_callbacks
):
    stale = []
    for title in ("First stale", "Second stale"):
        with django_capture_on_commit_callbacks(execute=False):
            meeting = ingest(title=title)
        stale.append(make_stale(MeetingSummary.objects.get(meeting=meeting)))
    with django_capture_on_commit_callbacks(execute=False):
        fresh_meeting = ingest(title="Fresh")
    ready = make_stale(MeetingSummary.objects.get(meeting=summarised(django_capture_on_commit_callbacks, title="Ready long ago")))
    _, failed = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks, title="Failed long ago")
    MeetingSummary.objects.filter(pk=failed.pk).update(queued_for_retry=False)
    failed = make_stale(failed)

    assert reclaim_orphans() == 2

    for summary in stale:
        summary.refresh_from_db()
        assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (
            SUMMARY_UNAVAILABLE, SUMMARY_FAILED_ORPHANED, True,
        )
    assert MeetingSummary.objects.get(meeting=fresh_meeting).status == SUMMARY_PROCESSING
    ready.refresh_from_db()
    failed.refresh_from_db()
    assert (ready.status, ready.failure_reason) == (SUMMARY_READY, "")
    assert (failed.status, failed.failure_reason, failed.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_PROVIDER_UNAVAILABLE, False,
    )


def test_a_reclaimed_run_is_ready_after_its_retry(stub_ai_service, django_capture_on_commit_callbacks):
    """The whole recovery from a restart mid-run: reclaimed, queued, run again, Ready."""
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()
    summary = make_stale(MeetingSummary.objects.get(meeting=meeting))
    assert reclaim_orphans() == 1
    [queued] = retry_queue()

    retried = retry_summary(queued)

    assert (retried.pk, retried.status, retried.failure_reason, retried.retry_runs) == (summary.pk, SUMMARY_READY, "", 1)
    assert current_summary(meeting) == retried


def test_a_request_over_a_stale_run_closes_it_and_starts_a_new_one(
    stub_ai_service, django_capture_on_commit_callbacks, employee
):
    """One run in flight per meeting must not mean a meeting whose run died can never be
    summarised again by hand. The dead run is closed as orphaned, and is not queued, because the
    new run is the one wanted."""
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()
    dead = make_stale(MeetingSummary.objects.get(meeting=meeting))

    fresh = regenerate(django_capture_on_commit_callbacks, meeting, requested_by=employee)

    dead.refresh_from_db()
    assert (dead.status, dead.failure_reason, dead.queued_for_retry) == (SUMMARY_UNAVAILABLE, SUMMARY_FAILED_ORPHANED, False)
    assert (fresh.run_number, fresh.status, fresh.requested_by) == (2, SUMMARY_READY, employee)
    assert list(retry_queue()) == []
    assert len(stub_ai_service.summarise_calls) == 1


# --- is_in_progress: FR-16's "202 Accepted while processing" ------------------------------------------------


def test_is_in_progress_for_each_state_a_run_can_be_in(stub_ai_service, django_capture_on_commit_callbacks):
    assert is_in_progress(None) is False  # no summary was ever requested

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        meeting = ingest()
    summary = MeetingSummary.objects.get(meeting=meeting)
    assert is_in_progress(summary) is True  # Processing

    assert is_in_progress(make_stale(summary)) is True  # stale: the next retry reclaims it, so it is still coming

    stub_ai_service.summary = raising(OUTAGE)
    MeetingSummary.objects.filter(pk=summary.pk).update(started_at=timezone.now())
    callbacks[0]()
    summary.refresh_from_db()
    assert (summary.status, summary.queued_for_retry) == (SUMMARY_UNAVAILABLE, True)
    assert is_in_progress(summary) is True  # queued for its automatic retry

    MeetingSummary.objects.filter(pk=summary.pk).update(queued_for_retry=False)
    summary.refresh_from_db()
    assert is_in_progress(summary) is False  # Unavailable, retries spent: only a person will try again

    stub_ai_service.summary = None
    ready = regenerate(django_capture_on_commit_callbacks, meeting)
    assert ready.status == SUMMARY_READY and is_in_progress(ready) is False


# --- NFR-20's own test, through HTTP, from both roles ---------------------------------------------------------

MEETINGS_URL = "/api/meetings"
WORD = "quokka"
TRANSCRIPT = (
    f"Priya: The {WORD} enclosure contract goes to tender on Monday. "
    + transcript(240, seed="spoken")
    + " Tom: Agreed, and I will write to the three bidders this afternoon."
)
QUESTION = "When does the enclosure contract go to tender?"


class OneVectorService(StubAIService):
    """Every text embeds to the same unit vector, so any passage in scope scores 1.0 against any
    question and generation is reached; the stub's own ``generate_statements`` then cites the
    first passage it was given. ``summary`` is whatever the test sets, as on the plain stub."""

    def embed(self, texts, *, input_type=None):
        self.embed_calls.append(list(texts))
        self.embed_input_types.append(input_type)
        vector = [1.0] + [0.0] * (self.dimension - 1)
        return EmbeddingResult(vectors=[list(vector) for _ in texts], model=STUB_EMBEDDING_MODEL, dimension=self.dimension)


def post_meeting(client, **fields):
    body = {"title": "Enclosure tender", "meeting_date": str(timezone.localdate()), "transcript_text": TRANSCRIPT, **fields}
    return client.post(MEETINGS_URL, body, format="json")


@pytest.mark.parametrize(
    "error,reason",
    [
        (ProviderUnavailable("the provider did not answer in three attempts"), SUMMARY_FAILED_PROVIDER_UNAVAILABLE),
        (ProviderRefused("HTTP 400: credit balance too low"), SUMMARY_FAILED_PROVIDER_REFUSED),
        (MalformedSummary("two replies broke SUMMARY_SCHEMA"), SUMMARY_FAILED_MALFORMED),
        # Nothing the provider decided: a defect. The runner records it as "error" and nothing propagates.
        (RuntimeError("a defect nobody expected"), SUMMARY_FAILED_ERROR),
    ],
    ids=["provider_unavailable", "provider_refused", "malformed", "unexpected_error"],
)
def test_a_summary_failure_leaves_the_transcript_stored_retrievable_searchable_citable_and_queued(
    session_client, monkeypatch, django_capture_on_commit_callbacks, error, reason
):
    """NFR-20's test, clause by clause. The failure is injected where summarisation really fails,
    in the provider, and the run is carried out by the commit that follows the ingestion, exactly
    as the server carries it; an exception escaping the runner would surface here as the test's
    own error."""
    service = install(monkeypatch, OneVectorService(summary=raising(error)))
    client = session_client.client

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        created = post_meeting(client)

    # "summary failure never blocks the transcript from being stored": 201, as with no failure.
    assert created.status_code == 201, created.content
    assert len(callbacks) == 1 and len(service.summarise_calls) == 1  # the premise: a run was made, and it failed
    meeting_id = created.json()["meeting_id"]
    assert created.json()["status"] == MEETING_INDEXED

    # "the raw transcript must still be stored, retrievable": in full, as submitted.
    detail = client.get(f"{MEETINGS_URL}/{meeting_id}")
    assert detail.status_code == 200
    assert detail.json()["transcript_text"] == TRANSCRIPT
    assert Meeting.objects.get(pk=meeting_id).transcript_text == TRANSCRIPT

    # "is searchable": FR-12's keyword search finds a word of it.
    found = client.get("/api/search", {"q": WORD})
    assert found.status_code == 200
    assert [result["source_id"] for result in found.json()["meetings"]["results"]] == [meeting_id]
    assert WORD in found.json()["meetings"]["results"][0]["snippet"]

    # And FR-12's answer path can cite it.
    asked = client.post("/api/ask", {"question": QUESTION}, format="json")
    assert asked.status_code == 200, asked.content
    answer = asked.json()
    assert answer["answered"] is True
    assert [source["source_id"] for source in answer["sources"]] == [meeting_id]
    transcript_chunk = ContentChunk.objects.get(source_id=meeting_id)  # the transcript's, the only chunk there is
    assert transcript_chunk.ai_generated is False
    assert [statement["chunk_id"] for statement in answer["statements"]] == [str(transcript_chunk.id)]

    # "and appears in a retry queue", "flagged for automatic retry".
    [queued] = retry_queue()
    assert str(queued.meeting_id) == meeting_id
    assert (queued.status, queued.failure_reason, queued.queued_for_retry) == (SUMMARY_UNAVAILABLE, reason, True)
    # UC-04, on failure: "never presented to a user": the panel is told one is still coming.
    panel = client.get(f"{MEETINGS_URL}/{meeting_id}/summary")
    assert panel.status_code == 202
    assert (panel.json()["status"], panel.json()["queued_for_retry"], panel.json()["summary"]) == (
        SUMMARY_UNAVAILABLE, True, None,
    )


def test_the_queued_summary_is_ready_once_the_provider_is_back_and_the_transcript_never_moved(
    session_client, monkeypatch, django_capture_on_commit_callbacks
):
    """UC-04 E1 to its end: "marks the summary as pending and queues the transcript for a later
    attempt". The later attempt succeeds, and what the transcript's own route returns is the same
    before and after."""
    service = install(monkeypatch, OneVectorService(summary=raising(OUTAGE)))
    client = session_client.client
    with django_capture_on_commit_callbacks(execute=True):
        meeting_id = post_meeting(client).json()["meeting_id"]
    before = client.get(f"{MEETINGS_URL}/{meeting_id}").json()

    service.summary = None
    [queued] = retry_queue()
    retried = retry_summary(queued)

    assert retried.status == SUMMARY_READY
    assert list(retry_queue()) == []
    assert client.get(f"{MEETINGS_URL}/{meeting_id}").json() == before
    panel = client.get(f"{MEETINGS_URL}/{meeting_id}/summary")
    assert (panel.status_code, panel.json()["status"]) == (200, SUMMARY_READY)
    assert panel.json()["summary"]["summary_id"] == str(retried.pk)


def test_an_unexpected_error_in_a_run_is_logged_with_its_traceback_and_the_ingestion_never_sees_it(
    employee_client, stub_ai_service, django_capture_on_commit_callbacks, error_log_file
):
    stub_ai_service.summary = raising(RuntimeError("a defect nobody expected"))

    with django_capture_on_commit_callbacks(execute=True):
        created = post_meeting(employee_client)

    assert created.status_code == 201
    summary = MeetingSummary.objects.get(meeting_id=created.json()["meeting_id"])
    assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (SUMMARY_UNAVAILABLE, SUMMARY_FAILED_ERROR, True)
    logged = error_log_file.read_text(encoding="utf-8")
    assert f"Meeting summary {summary.pk} failed with an unexpected error" in logged
    assert "RuntimeError: a defect nobody expected" in logged  # the traceback, for whoever fixes it
    assert WORD not in logged  # and no word of the transcript
