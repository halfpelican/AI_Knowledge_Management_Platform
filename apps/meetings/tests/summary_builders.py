"""Shared builders for the FR-16 tests (D-125): transcripts of a known length, meetings ingested
through FR-09's own function, and drafts for the stub's ``summary`` override.

Not a conftest: these are plain functions a test imports and calls, so each test says which
meeting and which reply it is about.
"""

from __future__ import annotations

from datetime import date

from apps.ai.base import ExtractedActionItem, MeetingSummaryDraft, SummaryElement
from apps.ai.testing import STUB_CHAT_MODEL
from apps.core.constants import MINIMUM_SUMMARY_TRANSCRIPT_LENGTH, ROLE_NAMES
from apps.ingestion.meetings import ingest_meeting_transcript

# A Tuesday, so the relative-date tests read against a known weekday.
MEETING_DATE = date(2026, 11, 10)
TITLE = "Budget review"


def transcript(words: int = MINIMUM_SUMMARY_TRANSCRIPT_LENGTH + 40, *, seed: str = "budget") -> str:
    """A transcript of exactly ``words`` whitespace tokens, each distinct enough to locate."""
    return " ".join(f"{seed}{number}" for number in range(words))


def ingest(
    *,
    title: str = TITLE,
    meeting_date: date = MEETING_DATE,
    text: str | None = None,
    visible_to_roles=ROLE_NAMES,
    attendees=(),
):
    """A meeting through FR-09's own ingestion, so its chunks, its status and its summary request
    are the ones the route would make. The commit callback that starts the run does not fire unless
    the test executes callbacks."""
    return ingest_meeting_transcript(
        title=title,
        meeting_date=meeting_date,
        transcript_text=transcript() if text is None else text,
        visible_to_roles=list(visible_to_roles),
        attendees=attendees,
    ).meeting


def element(text: str, *passages: int) -> SummaryElement:
    return SummaryElement(text=text, passages=tuple(passages) or (1,))


def action(description: str, *, owner=None, due=None, passages=(1,)) -> ExtractedActionItem:
    return ExtractedActionItem(description=description, owner=owner, due=due, passages=tuple(passages))


def draft(
    *,
    narrative=None,
    decisions=(),
    highlights=(),
    action_items=(),
    model: str = STUB_CHAT_MODEL,
) -> MeetingSummaryDraft:
    return MeetingSummaryDraft(
        narrative=tuple(narrative if narrative is not None else [element("The team reviewed the budget.")]),
        decisions=tuple(decisions),
        highlights=tuple(highlights),
        action_items=tuple(action_items),
        model=model,
    )


def raising(error: BaseException):
    """A value for the stub's ``summary``: every call raises ``error``, after being recorded."""

    def summarise(title, passages):
        raise error

    return summarise


def summarised(capture, **meeting):
    """A meeting through FR-09 whose first summary run has been carried out.

    ``capture`` is the ``django_capture_on_commit_callbacks`` fixture: the commit callbacks are
    executed, so the run ends as the stub's reply decides (Ready by default)."""
    with capture(execute=True):
        ingested = ingest(**meeting)
    return ingested


def regenerate(capture, meeting, *, requested_by=None):
    """Generate or Regenerate through ``request_summary`` and carry the run out. Returns the run
    as it ended, re-read from the database."""
    # Imported here so that importing these builders does not import the module under test first.
    from apps.meetings.summaries import request_summary

    with capture(execute=True):
        summary, _ = request_summary(meeting, requested_by=requested_by)
    summary.refresh_from_db()
    return summary
