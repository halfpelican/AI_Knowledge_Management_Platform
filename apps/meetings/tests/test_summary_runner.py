"""Where a summary's run happens (apps/meetings/summary_runner.py, D-125 choice 2).

FR-16 answers "202 Accepted while processing", and the stack has no task queue, so the server
carries a run in a daemon thread started after the requesting transaction commits. Three things
are held here:

- **Nothing a run raises reaches whoever started it** (CLAUDE.md invariant 8). ``run_guarded``
  catches what ``run_summary`` did not expect, logs it with its traceback and records it on the
  row as "error"; if even that fails, the row stays Processing for ``reclaim_orphans``.
- **Inline mode runs in the caller's thread**, which is what the rest of the suite relies on.
- **Thread mode really is another thread, the caller is not kept waiting, and no more than
  MAXIMUM_SUMMARIES_IN_FLIGHT runs call the provider at once.**

**The thread tests are the only tests in the repository marked ``transaction=True``.** A thread
writes through its own database connection, which cannot see a test transaction's uncommitted
rows, so these commit for real and the database is flushed after each. ``serialized_rollback``
restores the rows the migrations seeded (the roles and their permissions) before each one, and
pytest-django runs transactional tests after every other database test, so the flush costs no
other test its roles. Each test blocks the stub provider on an Event, asserts while it is blocked,
then releases it and JOINS every summary thread before it ends: no thread outlives its test, and
nothing is asserted on the strength of a sleep having been long enough, except the one negative
("a third run has not reached the provider"), which waits half a second for something that must
not happen.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

import apps.meetings.summaries as summaries
from apps.ai.base import ProviderUnavailable
from apps.core.constants import (
    MAXIMUM_SUMMARIES_IN_FLIGHT,
    MAXIMUM_SUMMARIES_WAITING,
    ROLE_NAMES,
    SUMMARY_FAILED_BUSY,
    SUMMARY_FAILED_ERROR,
    SUMMARY_FAILED_ORPHANED,
    SUMMARY_FAILED_PROVIDER_UNAVAILABLE,
    SUMMARY_PROCESSING,
    SUMMARY_READY,
    SUMMARY_STALE_AFTER_SECONDS,
    SUMMARY_UNAVAILABLE,
)
from apps.documents.models import ContentChunk
from apps.meetings import summary_runner
from apps.meetings.models import ActionItem, Meeting, MeetingSummary
from apps.meetings.summaries import reclaim_orphans, request_summary, retry_queue
from apps.meetings.summary_runner import (
    INLINE_RUNNER,
    SUMMARY_RUNNERS,
    THREAD_RUNNER,
    run_guarded,
    start_summary_run,
)
from apps.meetings.tests.summary_builders import MEETING_DATE, draft, ingest, raising, summarised, transcript

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
THREAD_PREFIX = "meeting-summary-"
# How long a test waits for something that must happen. Generous: it is only ever waited out when
# the test is about to fail.
PATIENCE = 30
RUNNER_LOGGER = "apps.meetings.summary_runner"


def summary_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name.startswith(THREAD_PREFIX)]


def join_summary_threads() -> None:
    """Wait for every summary thread to end. A thread that has already ended is not listed, and a
    thread cannot be "not started yet": ``start_summary_run`` starts it before it returns."""
    for thread in summary_threads():
        thread.join(PATIENCE)
    assert summary_threads() == [], "a summary thread outlived its test"


def processing_run(capture, **meeting) -> MeetingSummary:
    """A run requested by ingestion and not yet carried out."""
    with capture(execute=False):
        ingested = ingest(**meeting)
    return MeetingSummary.objects.get(meeting=ingested)


def runner_errors(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == RUNNER_LOGGER and record.levelno == logging.ERROR]


# --- The setting -------------------------------------------------------------------------------


def test_the_server_runs_in_a_thread_by_default_and_the_suite_inline(settings):
    """The default is what makes the route's 202 true: the request has answered before the run.
    The suite's own value is conftest.py's autouse fixture."""
    assert SUMMARY_RUNNERS == (THREAD_RUNNER, INLINE_RUNNER) == ("thread", "inline")
    assert settings.SUMMARY_RUNNER == INLINE_RUNNER
    source = (REPOSITORY_ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    assert 'SUMMARY_RUNNER = env.str("SUMMARY_RUNNER", default="thread")' in source


# --- Inline mode ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_inline_mode_runs_in_the_callers_thread_and_has_finished_when_it_returns(
    stub_ai_service, django_capture_on_commit_callbacks
):
    summary = processing_run(django_capture_on_commit_callbacks)
    seen = {}

    def observed(title, passages):
        seen["thread"] = threading.current_thread()
        return draft()

    stub_ai_service.summary = observed

    start_summary_run(summary.pk)

    assert seen["thread"] is threading.current_thread()
    assert summary_threads() == []  # no thread was started at all
    summary.refresh_from_db()
    assert summary.status == SUMMARY_READY


# --- run_guarded: nothing a run raises reaches its caller ------------------------------------------


@pytest.mark.django_db
def test_run_guarded_swallows_an_unexpected_exception_and_records_it_on_the_row(
    stub_ai_service, django_capture_on_commit_callbacks, caplog
):
    summary = processing_run(django_capture_on_commit_callbacks)
    stub_ai_service.summary = raising(RuntimeError("a defect nobody expected"))

    with caplog.at_level(logging.ERROR, logger=RUNNER_LOGGER):
        assert run_guarded(summary.pk) is None  # and it did not raise

    summary.refresh_from_db()
    assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_ERROR, True,
    )
    assert SUMMARY_FAILED_ERROR == "error"
    assert list(retry_queue()) == [summary]  # an unexpected failure is retried like any other (NFR-20)
    [record] = runner_errors(caplog)
    assert str(summary.pk) in record.getMessage()
    assert record.exc_info and str(record.exc_info[1]) == "a defect nobody expected"  # with its traceback


@pytest.mark.django_db
def test_an_unexpected_error_while_storing_is_swallowed_too_and_nothing_half_written_stays(
    stub_ai_service, django_capture_on_commit_callbacks, monkeypatch
):
    """The reply was good and the failure came inside the storing transaction. The run is recorded
    as "error", and what that transaction had written is gone: no Ready row, no item, no chunk."""
    meeting = summarised(django_capture_on_commit_callbacks)
    first = MeetingSummary.objects.get(meeting=meeting)
    items_before = sorted(ActionItem.objects.filter(meeting=meeting).values_list("pk", flat=True))
    chunks_before = set(ContentChunk.objects.filter(source_id=meeting.id).values_list("pk", flat=True))
    with django_capture_on_commit_callbacks(execute=False):
        second, _ = request_summary(meeting)

    def index_fails(*args, **kwargs):
        raise RuntimeError("the index step failed unexpectedly")

    monkeypatch.setattr(summaries, "index_summary", index_fails)

    run_guarded(second.pk)

    second.refresh_from_db()
    assert (second.status, second.failure_reason, second.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_ERROR, True,
    )
    assert (second.summary_text, second.narrative, second.generated_at) == ("", [], None)
    assert summaries.current_summary(meeting) == first
    assert sorted(ActionItem.objects.filter(meeting=meeting).values_list("pk", flat=True)) == items_before
    assert set(ContentChunk.objects.filter(source_id=meeting.id).values_list("pk", flat=True)) == chunks_before


@pytest.mark.django_db
def test_a_failure_the_run_expected_is_not_an_error_and_logs_no_traceback(
    stub_ai_service, django_capture_on_commit_callbacks, caplog
):
    """An outage is an outcome ``run_summary`` decided. It keeps its own reason, and the error
    log is not given a traceback for something that is not a defect."""
    summary = processing_run(django_capture_on_commit_callbacks)
    stub_ai_service.summary = raising(ProviderUnavailable("stub outage"))

    with caplog.at_level(logging.ERROR, logger=RUNNER_LOGGER):
        run_guarded(summary.pk)

    summary.refresh_from_db()
    assert (summary.status, summary.failure_reason) == (SUMMARY_UNAVAILABLE, SUMMARY_FAILED_PROVIDER_UNAVAILABLE)
    assert runner_errors(caplog) == []


@pytest.mark.django_db
def test_if_the_row_cannot_even_be_marked_nothing_propagates_and_the_orphan_is_reclaimed_later(
    stub_ai_service, django_capture_on_commit_callbacks, monkeypatch, caplog
):
    """The last resort itself fails, as it would with the database gone. Still nothing is raised:
    the row is left Processing, both failures are logged, and the retry command's
    ``reclaim_orphans`` closes the row once it is stale."""
    summary = processing_run(django_capture_on_commit_callbacks)
    stub_ai_service.summary = raising(RuntimeError("a defect nobody expected"))

    def cannot_mark(summary_id):
        raise RuntimeError("the row could not be written")

    monkeypatch.setattr(summaries, "fail_after_error", cannot_mark)

    with caplog.at_level(logging.ERROR, logger=RUNNER_LOGGER):
        assert run_guarded(summary.pk) is None

    summary.refresh_from_db()
    assert (summary.status, summary.failure_reason) == (SUMMARY_PROCESSING, "")
    messages = [record.getMessage() for record in runner_errors(caplog)]
    assert len(messages) == 2
    assert "failed with an unexpected error" in messages[0]
    assert "could not be marked unavailable" in messages[1]

    from datetime import timedelta

    assert reclaim_orphans(now=summary.started_at + timedelta(seconds=SUMMARY_STALE_AFTER_SECONDS + 1)) == 1
    summary.refresh_from_db()
    assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_ORPHANED, True,
    )


@pytest.mark.django_db
def test_run_guarded_for_a_run_that_no_longer_exists_does_nothing(stub_ai_service, caplog):
    import uuid

    with caplog.at_level(logging.ERROR, logger=RUNNER_LOGGER):
        assert run_guarded(uuid.uuid4()) is None

    assert runner_errors(caplog) == []
    assert stub_ai_service.summarise_calls == []


# --- Thread mode -----------------------------------------------------------------------------------

threaded = pytest.mark.django_db(transaction=True, serialized_rollback=True)


@threaded
def test_thread_mode_runs_in_another_thread_and_does_not_keep_its_caller_waiting(settings, stub_ai_service):
    """The run is started by the commit of the ingestion's own transaction. The provider is held
    on an Event: ``ingest`` has returned and the row is still Processing, which is the state
    FR-16's 202 reports. Released, the thread carries the run to Ready through a connection of its
    own."""
    settings.SUMMARY_RUNNER = THREAD_RUNNER
    entered, release = threading.Event(), threading.Event()
    seen = {}

    def held(title, passages):
        seen["thread"] = threading.current_thread()
        entered.set()
        if not release.wait(PATIENCE):
            raise AssertionError("the test never released the provider")
        return draft()

    stub_ai_service.summary = held
    try:
        meeting = ingest()  # commits; the commit starts the run; and this returns
        assert entered.wait(PATIENCE), "the run never reached the provider"
        summary = MeetingSummary.objects.get(meeting=meeting)
        assert summary.status == SUMMARY_PROCESSING  # the caller has control back, and the run is still out
        assert seen["thread"] is not threading.current_thread()
        assert seen["thread"].name == f"{THREAD_PREFIX}{summary.pk}"
        assert seen["thread"].daemon is True  # it dies with the server rather than holding it open
        assert seen["thread"].is_alive()
    finally:
        release.set()
        join_summary_threads()

    summary.refresh_from_db()
    assert summary.status == SUMMARY_READY, summary.failure_reason
    assert ContentChunk.objects.filter(source_id=meeting.id, ai_generated=True).count() == 1
    assert ActionItem.objects.filter(meeting=meeting).exists() is False  # ``draft()`` raises none
    assert len(stub_ai_service.summarise_calls) == 1


@threaded
def test_no_more_runs_than_the_limit_call_the_provider_at_once_and_none_is_refused(settings, stub_ai_service):
    """Two more runs than MAXIMUM_SUMMARIES_IN_FLIGHT are started. Exactly the limit reach the
    provider and are held there; the others wait for a place inside their own threads. Released,
    every run ends Ready: a further run waits, it is never refused. The most ever inside the
    provider at once is counted by the provider itself and must EQUAL the limit: more would be the
    limit broken, fewer would be runs that never overlap at all."""
    settings.SUMMARY_RUNNER = THREAD_RUNNER
    runs = MAXIMUM_SUMMARIES_IN_FLIGHT + 2
    lock = threading.Lock()
    inside = {"now": 0, "most": 0, "calls": 0}
    entered = threading.Semaphore(0)
    release = threading.Event()

    def counted(title, passages):
        with lock:
            inside["now"] += 1
            inside["calls"] += 1
            inside["most"] = max(inside["most"], inside["now"])
        entered.release()
        released = release.wait(PATIENCE)
        with lock:
            inside["now"] -= 1
        if not released:
            raise AssertionError("the test never released the provider")
        return draft()

    stub_ai_service.summary = counted
    try:
        meetings = [ingest(title=f"Meeting {number}") for number in range(runs)]
        for _ in range(MAXIMUM_SUMMARIES_IN_FLIGHT):
            assert entered.acquire(timeout=PATIENCE), "fewer runs than the limit reached the provider"
        # The one wait for something that must NOT happen: a further run reaching the provider.
        assert not entered.acquire(timeout=0.5), "a run past the limit reached the provider"
        with lock:
            assert inside["now"] == MAXIMUM_SUMMARIES_IN_FLIGHT
        assert len(summary_threads()) == runs  # every run has its thread; the extra ones are waiting, not refused
        assert MeetingSummary.objects.filter(status=SUMMARY_PROCESSING).count() == runs
    finally:
        release.set()
        join_summary_threads()

    assert inside == {"now": 0, "most": MAXIMUM_SUMMARIES_IN_FLIGHT, "calls": runs}
    assert MAXIMUM_SUMMARIES_IN_FLIGHT == 2
    statuses = list(MeetingSummary.objects.filter(meeting__in=meetings).values_list("status", flat=True))
    assert statuses == [SUMMARY_READY] * runs


@threaded
def test_an_unexpected_error_in_a_thread_is_recorded_on_the_row_and_the_place_is_given_back(settings, stub_ai_service):
    """A run that raises inside its thread must not take a place with it: after more failures than
    there are places, a further run still gets one."""
    settings.SUMMARY_RUNNER = THREAD_RUNNER
    stub_ai_service.summary = raising(RuntimeError("a defect nobody expected"))
    try:
        failed = [ingest(title=f"Failing {number}") for number in range(MAXIMUM_SUMMARIES_IN_FLIGHT + 1)]
    finally:
        join_summary_threads()
    for summary in MeetingSummary.objects.filter(meeting__in=failed):
        assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (
            SUMMARY_UNAVAILABLE, SUMMARY_FAILED_ERROR, True,
        )

    stub_ai_service.summary = None
    try:
        healthy = ingest(title="Healthy")
    finally:
        join_summary_threads()

    assert MeetingSummary.objects.get(meeting=healthy).status == SUMMARY_READY


@threaded
def test_the_summary_route_answers_202_while_the_provider_is_still_working(settings, stub_ai_service, employee_client):
    """FR-16: "202 Accepted while processing, 200 OK with the summary and item list once ready",
    under the server's own runner. The POST has answered and the page has polled while the
    provider is held; neither request waited for it."""
    meeting = Meeting.objects.create(
        title="Budget review", meeting_date=MEETING_DATE, transcript_text=transcript(),
        visible_to_roles=list(ROLE_NAMES),
    )
    url = f"/api/meetings/{meeting.id}/summary"
    settings.SUMMARY_RUNNER = THREAD_RUNNER
    entered, release = threading.Event(), threading.Event()

    def held(title, passages):
        entered.set()
        if not release.wait(PATIENCE):
            raise AssertionError("the test never released the provider")
        return draft()

    stub_ai_service.summary = held
    try:
        started = employee_client.post(url)
        assert entered.wait(PATIENCE), "the run never reached the provider"
        polled = employee_client.get(url)
        assert (started.status_code, started.json()["status"]) == (202, SUMMARY_PROCESSING)
        assert (polled.status_code, polled.json()["status"], polled.json()["summary"]) == (202, SUMMARY_PROCESSING, None)
        assert len(summary_threads()) == 1
    finally:
        release.set()
        join_summary_threads()

    ready = employee_client.get(url)
    assert (ready.status_code, ready.json()["status"]) == (200, SUMMARY_READY)
    assert ready.json()["summary"]["summary_text"] == "The team reviewed the budget."
    assert len(stub_ai_service.summarise_calls) == 1


@pytest.mark.django_db
def test_past_the_waiting_cap_a_run_is_queued_as_busy_and_no_thread_is_started(
    settings, stub_ai_service, django_capture_on_commit_callbacks, monkeypatch
):
    """The security review of 12 November, finding 4 (D-125's third note): every run waited in a
    thread of its own, with no bound. With MAXIMUM_SUMMARIES_IN_FLIGHT + MAXIMUM_SUMMARIES_WAITING
    threads live, a further run is closed Unavailable and queued as "busy", for the hourly retry,
    and no thread is started for it. The count is set directly, so no thread is needed to fill it."""
    assert (MAXIMUM_SUMMARIES_WAITING, summary_runner.MAXIMUM_LIVE) == (20, MAXIMUM_SUMMARIES_IN_FLIGHT + 20)
    summary = processing_run(django_capture_on_commit_callbacks)
    settings.SUMMARY_RUNNER = THREAD_RUNNER
    monkeypatch.setattr(summary_runner, "_live", summary_runner.MAXIMUM_LIVE)

    asked = []

    def no_thread(*args, **kwargs):
        # Recorded, not raised: start_summary_run catches a thread that fails to start and queues
        # the run as busy too, so a raise here could not tell the cap from that fallback.
        asked.append(kwargs.get("name"))
        raise RuntimeError("a thread was asked for past the cap")

    monkeypatch.setattr(summary_runner.threading, "Thread", no_thread)

    start_summary_run(summary.pk, claim=0)

    assert asked == []  # the cap refused it before any thread was asked for
    summary.refresh_from_db()
    assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_BUSY, True,
    )
    assert list(retry_queue()) == [summary]
    assert stub_ai_service.summarise_calls == []
    assert summary_runner._live == summary_runner.MAXIMUM_LIVE  # nothing was counted for it


@pytest.mark.django_db
def test_one_below_the_cap_a_run_gets_its_thread(settings, django_capture_on_commit_callbacks, monkeypatch):
    summary = processing_run(django_capture_on_commit_callbacks)
    settings.SUMMARY_RUNNER = THREAD_RUNNER
    monkeypatch.setattr(summary_runner, "_live", summary_runner.MAXIMUM_LIVE - 1)
    started = []

    class Recorded:
        def __init__(self, target, args, name, daemon):
            started.append((target, args, name, daemon))

        def start(self):
            pass

    monkeypatch.setattr(summary_runner.threading, "Thread", Recorded)

    start_summary_run(summary.pk, claim=0)

    assert started == [(summary_runner._run_in_thread, (summary.pk, 0), f"{THREAD_PREFIX}{summary.pk}", True)]
    assert summary_runner._live == summary_runner.MAXIMUM_LIVE
    summary.refresh_from_db()
    assert summary.status == SUMMARY_PROCESSING


@pytest.mark.django_db
def test_a_thread_the_system_refuses_is_queued_as_busy_and_not_raised(
    settings, django_capture_on_commit_callbacks, monkeypatch, caplog
):
    """``start_summary_run`` runs from ``transaction.on_commit``, after the transcript committed:
    raising there would answer a stored upload with a 500 (invariant 8)."""
    summary = processing_run(django_capture_on_commit_callbacks)
    settings.SUMMARY_RUNNER = THREAD_RUNNER
    monkeypatch.setattr(summary_runner, "_live", 0)

    class Refused:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(summary_runner.threading, "Thread", Refused)

    start_summary_run(summary.pk, claim=0)  # does not raise

    summary.refresh_from_db()
    assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_BUSY, True,
    )
    assert summary_runner._live == 0  # the place it took was given back
    assert runner_errors(caplog)


def test_the_thread_mode_tests_leave_no_thread_behind():
    """Collected last in this module; pytest-django runs it after the transactional tests above
    because it uses no database."""
    assert summary_threads() == []
    assert summary_runner.live_runs() == 0  # every thread gave back its count
    # Every place was given back: all of them can be taken now, and not one more.
    places = summary_runner._places
    taken = [places.acquire(blocking=False) for _ in range(MAXIMUM_SUMMARIES_IN_FLIGHT)]
    one_more = places.acquire(blocking=False)
    for was_taken in [*taken, one_more]:
        if was_taken:
            places.release()
    assert taken == [True] * MAXIMUM_SUMMARIES_IN_FLIGHT
    assert one_more is False
