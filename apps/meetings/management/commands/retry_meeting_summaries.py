"""``python manage.py retry_meeting_summaries``: run FR-16's retry queue once (D-125, NFR-20).

NFR-20: "If AI summary generation fails for a meeting transcript, the raw transcript must still be
stored, retrievable, and flagged for automatic retry". The flag is
``MeetingSummary.queued_for_retry``, and this command is the retry: a scheduler runs it every hour
(``scripts/register_meeting_summary_schedule.ps1``), FR-19's pattern for a stack with no task
queue (D-107's note of 10 November 2026).

One run does two things, in this order:

1. **Reclaims orphans.** A summary still Processing ``SUMMARY_STALE_AFTER_SECONDS`` after it
   started was left by a server that stopped mid-run. It is marked failed ("orphaned") and joins
   the queue.
2. **Runs each queued summary again,** oldest request first, one at a time, in this process. Each
   ends Ready, or Unavailable again: queued once more while it has had fewer than
   ``MAXIMUM_SUMMARY_RETRY_RUNS`` queued runs, and out of the queue after that, when only a person
   pressing Generate or Regenerate tries again.

**The database name is printed first**, before anything is read or written, as FR-19's command
does. One line follows per summary, naming the meeting and summary by id and never by title or
content.

**Exit status 1 when any summary this run took from the queue is still unavailable after it,**
whether it was queued again or has now left the queue, so the scheduler's last-run result shows
that something needs attention; nothing is lost either way, because a failed run changes nothing
but its own row. An empty queue is exit status 0, even while summaries that left the queue on an
earlier run are still Unavailable: those wait for a person's Generate, and the command does not
look at them.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.constants import SUMMARY_READY
from apps.meetings.summaries import reclaim_orphans, retry_queue, retry_summary


class Command(BaseCommand):
    help = "Run every meeting summary queued for retry once (FR-16, NFR-20; D-125)."

    def handle(self, *args, **options):
        self.stdout.write(f"database: {connection.settings_dict['NAME']}")
        reclaimed = reclaim_orphans()
        if reclaimed:
            self.stdout.write(f"reclaimed {reclaimed} run(s) a stopped server left Processing")

        queued = list(retry_queue())
        if not queued:
            self.stdout.write("queue: empty")
            return
        self.stdout.write(f"queue: {len(queued)} summary(ies)")

        ready = requeued = given_up = 0
        for summary in queued:
            result = retry_summary(summary)
            if result is None:
                self.stdout.write(f"summary {summary.pk}: its meeting has been deleted")
                continue
            if result.status == SUMMARY_READY:
                ready += 1
                outcome = "Ready"
            elif result.queued_for_retry:
                requeued += 1
                outcome = f"Unavailable ({result.failure_reason}); queued again, run {result.retry_runs}"
            else:
                given_up += 1
                outcome = (
                    f"Unavailable ({result.failure_reason}); out of the queue after "
                    f"{result.retry_runs} run(s)"
                )
            self.stdout.write(f"meeting {result.meeting_id} summary {result.pk}: {outcome}")

        self.stdout.write(f"ready={ready} queued_again={requeued} given_up={given_up}")
        if requeued or given_up:
            raise CommandError(
                f"{requeued + given_up} summary(ies) are still unavailable; the transcripts are "
                "stored and searchable, and the provider attempts log has each cause."
            )
