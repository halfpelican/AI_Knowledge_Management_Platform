"""Where a meeting summary's run happens: a background thread in the server process (D-125).

FR-16 answers "202 Accepted while processing", and the stack has no task queue. So a run is one
daemon thread, started after the transaction that requested it has committed
(``apps/meetings/summaries.py::request_summary`` registers ``start_summary_run`` with
``transaction.on_commit``). The request that asked has answered by then; nobody waits on the
thread.

- **At most MAXIMUM_SUMMARIES_IN_FLIGHT runs call the provider at once** in one process. A further
  run waits for a place inside its own thread: nothing is refused, because nothing is waiting for
  an answer.
- **A run cannot take the server down or leave its row Processing.** ``run_summary`` ends every
  expected failure itself. Anything else is caught here, logged with its traceback and recorded
  on the row as "error", which queues it for retry like any other failure (invariant 8).
- **If the process stops mid-run,** the thread dies with it (it is a daemon) and the row stays
  Processing. ``manage.py retry_meeting_summaries`` reclaims a row older than
  SUMMARY_STALE_AFTER_SECONDS on its next hourly run (NFR-20's queue).
- **The thread closes its own database connection** when it ends: Django opens one per thread and
  closes it only at the end of a request, which a thread never reaches.

``SUMMARY_RUNNER`` (config/settings.py) chooses between this and running inline, in the caller's
thread. The suite runs inline, so a test that executes the commit callbacks sees the finished
summary; the management commands call ``run_summary`` directly and never come through here.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import connections

from apps.core.constants import MAXIMUM_SUMMARIES_IN_FLIGHT

logger = logging.getLogger(__name__)

THREAD_RUNNER = "thread"
INLINE_RUNNER = "inline"
SUMMARY_RUNNERS = (THREAD_RUNNER, INLINE_RUNNER)

_places = threading.BoundedSemaphore(MAXIMUM_SUMMARIES_IN_FLIGHT)


def start_summary_run(summary_id) -> None:
    """Begin the run for ``summary_id``: in a new thread, or inline where the setting says so."""
    if settings.SUMMARY_RUNNER == INLINE_RUNNER:
        run_guarded(summary_id)
        return
    threading.Thread(
        target=_run_in_thread, args=(summary_id,), name=f"meeting-summary-{summary_id}", daemon=True
    ).start()


def _run_in_thread(summary_id) -> None:
    try:
        with _places:
            run_guarded(summary_id)
    finally:
        connections.close_all()


def run_guarded(summary_id) -> None:
    """``run_summary``, with anything it did not expect caught, logged and recorded on the row."""
    # Imported here: summaries.py imports this module's ``start_summary_run``.
    from apps.meetings.summaries import fail_after_error, run_summary

    try:
        run_summary(summary_id)
    except Exception:  # noqa: BLE001 - a summary's failure must never propagate (invariant 8)
        logger.exception("Meeting summary %s failed with an unexpected error", summary_id)
        try:
            fail_after_error(summary_id)
        except Exception:  # noqa: BLE001 - the row stays Processing and is reclaimed as an orphan
            logger.exception("Meeting summary %s could not be marked unavailable", summary_id)
