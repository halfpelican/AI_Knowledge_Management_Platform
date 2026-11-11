"""FR-16's two management commands and the committed retry schedule (D-125; NFR-20).

- ``retry_meeting_summaries`` is NFR-20's "automatic retry": it reclaims runs a stopped server left
  Processing and runs each queued summary again, and its exit status says whether anything is
  still unavailable.
- ``summarise_meetings`` is the Objective 04 instrument and the backfill: it carries each run
  itself, once, and records what the application stored.
- ``scripts/register_meeting_summary_schedule.ps1`` is what makes the retry automatic on the host.
  Registering it is the host owner's step, so what the repository can hold, and these tests pin, is
  the script and the runbook: the retry command, from the checkout's venv, every hour, and never a
  password (the pattern of apps/retrieval/tests/test_knowledge_gap_schedule.py).
"""

import io
import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.ai.base import ProviderUnavailable
from apps.ai.testing import STUB_CHAT_MODEL
from apps.core.constants import (
    MAXIMUM_SUMMARY_RETRY_RUNS,
    MINIMUM_SUMMARY_TRANSCRIPT_LENGTH,
    SUMMARY_FAILED_ORPHANED,
    SUMMARY_FAILED_PROVIDER_UNAVAILABLE,
    SUMMARY_PROCESSING,
    SUMMARY_READY,
    SUMMARY_STALE_AFTER_SECONDS,
    SUMMARY_UNAVAILABLE,
)
from apps.documents.models import ContentChunk
from apps.meetings.models import Meeting, MeetingSummary
from apps.meetings.summaries import retry_queue
from apps.meetings.tests.summary_builders import action, draft, element, ingest, transcript

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "register_meeting_summary_schedule.ps1"
RUNBOOK = ROOT / "docs" / "alpha-deployment.md"


def outage(title, passages):
    raise ProviderUnavailable("the provider is down")


def run(command, *args):
    out = io.StringIO()
    call_command(command, *args, stdout=out, stderr=io.StringIO())
    return out.getvalue()


def failed_meeting(stub_ai_service, capture, **kwargs):
    """A meeting whose first summary run met an outage: Unavailable, and in the retry queue."""
    stub_ai_service.summary = outage
    with capture(execute=True):
        meeting = ingest(**kwargs)
    summary = MeetingSummary.objects.get(meeting=meeting)
    assert summary.status == SUMMARY_UNAVAILABLE and summary.queued_for_retry
    return meeting, summary


# --- retry_meeting_summaries -----------------------------------------------------------------


@pytest.mark.django_db
def test_an_empty_queue_is_reported_and_is_not_a_failure():
    output = run("retry_meeting_summaries")

    assert output.splitlines()[0].startswith("database: ")
    assert "queue: empty" in output


@pytest.mark.django_db
def test_a_queued_summary_is_run_again_and_becomes_ready(
    stub_ai_service, django_capture_on_commit_callbacks
):
    meeting, summary = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    stub_ai_service.summary = None  # the provider is back

    output = run("retry_meeting_summaries")

    summary.refresh_from_db()
    assert summary.status == SUMMARY_READY
    assert summary.retry_runs == 1 and not summary.queued_for_retry
    assert list(retry_queue()) == []
    assert ContentChunk.objects.filter(source_id=meeting.id, ai_generated=True).exists()
    assert f"meeting {meeting.id} summary {summary.id}: Ready" in output
    assert "ready=1 queued_again=0 given_up=0" in output
    # The line names ids only: no title and no content.
    assert meeting.title not in output and summary.summary_text not in output


@pytest.mark.django_db
def test_a_summary_still_failing_is_queued_again_and_the_command_exits_non_zero(
    stub_ai_service, django_capture_on_commit_callbacks
):
    meeting, summary = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)

    with pytest.raises(CommandError) as raised:
        run("retry_meeting_summaries")

    summary.refresh_from_db()
    assert summary.status == SUMMARY_UNAVAILABLE
    assert summary.failure_reason == SUMMARY_FAILED_PROVIDER_UNAVAILABLE
    assert summary.retry_runs == 1 and summary.queued_for_retry
    assert "still unavailable" in str(raised.value)
    # NFR-20: the transcript is untouched by any of it.
    assert Meeting.objects.get(pk=meeting.pk).transcript_text == transcript()


@pytest.mark.django_db
def test_the_queue_gives_up_after_the_last_queued_run_and_leaves_the_summary_unavailable(
    stub_ai_service, django_capture_on_commit_callbacks
):
    _, summary = failed_meeting(stub_ai_service, django_capture_on_commit_callbacks)

    for expected_runs in range(1, MAXIMUM_SUMMARY_RETRY_RUNS + 1):
        with pytest.raises(CommandError):
            run("retry_meeting_summaries")
        summary.refresh_from_db()
        assert summary.retry_runs == expected_runs

    assert summary.status == SUMMARY_UNAVAILABLE and not summary.queued_for_retry
    # Out of the queue: the next run finds nothing, calls nothing and succeeds.
    calls = len(stub_ai_service.summarise_calls)
    assert "queue: empty" in run("retry_meeting_summaries")
    assert len(stub_ai_service.summarise_calls) == calls


@pytest.mark.django_db
def test_a_run_a_stopped_server_left_processing_is_reclaimed_and_run(
    stub_ai_service, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()  # the commit callback never runs: the server "stopped"
    summary = MeetingSummary.objects.get(meeting=meeting)
    assert summary.status == SUMMARY_PROCESSING
    MeetingSummary.objects.filter(pk=summary.pk).update(
        started_at=timezone.now() - timedelta(seconds=SUMMARY_STALE_AFTER_SECONDS + 60)
    )

    output = run("retry_meeting_summaries")

    summary.refresh_from_db()
    assert "reclaimed 1 run(s)" in output
    assert summary.status == SUMMARY_READY and summary.retry_runs == 1


@pytest.mark.django_db
def test_a_run_still_within_its_time_is_left_alone(stub_ai_service, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()

    output = run("retry_meeting_summaries")

    assert "reclaimed" not in output and "queue: empty" in output
    assert MeetingSummary.objects.get(meeting=meeting).status == SUMMARY_PROCESSING
    assert stub_ai_service.summarise_calls == []


@pytest.mark.django_db
def test_an_orphan_closed_by_the_command_carries_its_reason_when_the_provider_is_still_down(
    stub_ai_service, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()
    MeetingSummary.objects.filter(meeting=meeting).update(
        started_at=timezone.now() - timedelta(seconds=SUMMARY_STALE_AFTER_SECONDS + 60)
    )
    stub_ai_service.summary = outage

    with pytest.raises(CommandError):
        run("retry_meeting_summaries")

    summary = MeetingSummary.objects.get(meeting=meeting)
    # Reclaimed as orphaned, then run once and failed on the outage: the later reason stands.
    assert summary.failure_reason == SUMMARY_FAILED_PROVIDER_UNAVAILABLE
    assert summary.failure_reason != SUMMARY_FAILED_ORPHANED
    assert summary.retry_runs == 1 and summary.queued_for_retry


# --- summarise_meetings ----------------------------------------------------------------------


def a_meeting_without_a_run(**kwargs) -> Meeting:
    """A meeting as one ingested before FR-16 existed: stored, and never asked for a summary."""
    return Meeting.objects.create(
        title=kwargs.get("title", "Older meeting"),
        meeting_date=kwargs.get("meeting_date", timezone.localdate()),
        transcript_text=kwargs.get("text", transcript()),
        visible_to_roles=["Employee", "Administrator"],
    )


@pytest.mark.django_db
def test_it_needs_exactly_one_way_of_choosing_meetings():
    with pytest.raises(CommandError):
        run("summarise_meetings")
    with pytest.raises(CommandError):
        run("summarise_meetings", "--missing", "--meeting", "00000000-0000-0000-0000-000000000000")
    with pytest.raises(CommandError):
        run("summarise_meetings", "--meeting", "not-a-uuid")
    with pytest.raises(CommandError):
        run("summarise_meetings", "--meeting", "00000000-0000-0000-0000-000000000000")


@pytest.mark.django_db
def test_missing_summarises_only_meetings_with_no_run_and_enough_text(stub_ai_service, tmp_path):
    older = a_meeting_without_a_run()
    short = a_meeting_without_a_run(
        title="Short", text=transcript(MINIMUM_SUMMARY_TRANSCRIPT_LENGTH - 1)
    )
    out = tmp_path / "run" / "record.json"

    output = run("summarise_meetings", "--missing", "--out", str(out))

    assert MeetingSummary.objects.get(meeting=older).status == SUMMARY_READY
    assert not MeetingSummary.objects.filter(meeting=short).exists()
    assert len(stub_ai_service.summarise_calls) == 1  # one run, carried once, by the command
    assert "Done: 1 ready, 0 not" in output
    # A second pass finds nothing left to do.
    run("summarise_meetings", "--missing")
    assert len(stub_ai_service.summarise_calls) == 1

    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["selection"] == "missing" and record["provider"]
    [entry] = record["meetings"]
    assert entry["id"] == str(older.id) and entry["status"] == SUMMARY_READY
    assert entry["model"] == STUB_CHAT_MODEL


@pytest.mark.django_db
def test_the_record_holds_each_action_item_as_stored_with_its_owner_and_date(
    stub_ai_service, administrator, tmp_path
):
    from apps.meetings.models import MeetingAttendee
    from datetime import date

    meeting = a_meeting_without_a_run(meeting_date=date(2026, 11, 10))  # a Tuesday
    MeetingAttendee.objects.create(meeting=meeting, user=administrator)  # "Ada Administrator"
    stub_ai_service.summary = draft(
        narrative=[element("The team reviewed the budget.")],
        decisions=[element("Travel is frozen.")],
        action_items=[
            action("Send the notice", owner="Ada", due="by Friday"),
            action("Label the crates", owner="the facilities team", due="before the move"),
            action("Call the customer", owner=None, due=None),
        ],
    )
    out = tmp_path / "record.json"

    run("summarise_meetings", "--meeting", str(meeting.id), "--out", str(out))

    [entry] = json.loads(out.read_text(encoding="utf-8"))["meetings"]
    assert entry["attendees"] == ["Ada Administrator"]
    assert entry["summary_text"] == "The team reviewed the budget."
    assert [d["text"] for d in entry["decisions"]] == ["Travel is frozen."]
    assert entry["action_items_extracted"] == 3
    assert entry["action_items"] == [
        {"description": "Send the notice", "owner_name": "Ada", "owner": "Ada Administrator",
         "due_text": "by Friday", "due_date": "2026-11-13", "passages": [1], "origin": "ai",
         "edited": False},
        {"description": "Label the crates", "owner_name": "the facilities team", "owner": None,
         "due_text": "before the move", "due_date": None, "passages": [1], "origin": "ai",
         "edited": False},
        {"description": "Call the customer", "owner_name": "", "owner": None, "due_text": "",
         "due_date": None, "passages": [1], "origin": "ai", "edited": False},
    ]


@pytest.mark.django_db
def test_naming_a_meeting_gives_it_a_new_run_and_a_failure_is_recorded_not_raised(
    stub_ai_service, tmp_path
):
    meeting = a_meeting_without_a_run()
    run("summarise_meetings", "--meeting", str(meeting.id))
    assert MeetingSummary.objects.filter(meeting=meeting).count() == 1
    stub_ai_service.summary = outage
    out = tmp_path / "record.json"

    output = run("summarise_meetings", "--meeting", str(meeting.id), "--out", str(out))

    assert MeetingSummary.objects.filter(meeting=meeting).count() == 2
    assert "Done: 0 ready, 1 not" in output
    [entry] = json.loads(out.read_text(encoding="utf-8"))["meetings"]
    assert entry["status"] == SUMMARY_UNAVAILABLE
    assert entry["failure_reason"] == SUMMARY_FAILED_PROVIDER_UNAVAILABLE
    assert entry["queued_for_retry"] is True
    assert "summary_text" not in entry and "action_items" not in entry


@pytest.mark.django_db
def test_a_meeting_whose_summary_the_server_is_generating_is_not_run_a_second_time(
    stub_ai_service, django_capture_on_commit_callbacks, tmp_path
):
    with django_capture_on_commit_callbacks(execute=False):
        meeting = ingest()  # a run is in flight
    out = tmp_path / "record.json"

    run("summarise_meetings", "--meeting", str(meeting.id), "--out", str(out))

    assert stub_ai_service.summarise_calls == []
    assert MeetingSummary.objects.filter(meeting=meeting).count() == 1
    [entry] = json.loads(out.read_text(encoding="utf-8"))["meetings"]
    assert entry["error"] == "in_progress"


@pytest.mark.django_db
def test_the_record_counts_the_tokens_the_attempts_log_reported(stub_ai_service, tmp_path, monkeypatch):
    """The usage block is read from the attempts log's summarisation lines, so it is what the
    provider reported for the calls this run made. The stub makes no provider call and logs no
    attempt, so a line is written here as the attempt loop writes one."""
    from apps.ai import attempt_log
    from apps.meetings.summaries import run_summary as real_run_summary
    from apps.meetings.management.commands import summarise_meetings

    def run_and_log(summary_id):
        attempt_log.parsed_summary(
            1, 3, 2.5, sentences=1, decisions=1, highlights=0, action_items=1,
            reply=attempt_log.ReplyFacts(
                max_tokens=16000, finish_reason="end_turn", completion_tokens=321, prompt_tokens=4567
            ),
        )
        return real_run_summary(summary_id)

    monkeypatch.setattr(summarise_meetings, "run_summary", run_and_log)
    a_meeting_without_a_run()
    out = tmp_path / "record.json"

    run("summarise_meetings", "--missing", "--out", str(out))

    assert json.loads(out.read_text(encoding="utf-8"))["usage"] == {
        "attempts": 1,
        "attempts_without_reported_tokens": 0,
        "prompt_tokens": 4567,
        "completion_tokens": 321,
    }


# --- The committed schedule -----------------------------------------------------------------


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_schedule_runs_the_retry_command_from_the_checkouts_venv():
    text = script_text()
    assert "manage.py retry_meeting_summaries" in text
    assert ".venv\\Scripts\\python.exe" in text


def test_the_schedule_repeats_hourly_by_default_and_never_overlaps_itself():
    text = script_text()
    assert "[int]$EveryMinutes = 60" in text
    assert "-RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)" in text
    assert "-MultipleInstances IgnoreNew" in text
    for other in ("-Daily", "-Weekly", "-AtLogOn", "-AtStartup"):
        assert other not in text, other


def test_the_schedule_takes_no_password():
    """The standing rule: no password is asked for, written or stored by the project."""
    text = script_text().lower()
    for credential in ("-password", "get-credential", "securestring", "-userid"):
        assert credential not in text, credential


def test_the_runbook_says_how_to_register_it():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "register_meeting_summary_schedule.ps1" in text
    assert "manage.py retry_meeting_summaries" in text
