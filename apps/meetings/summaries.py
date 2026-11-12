"""FR-16's apply layer: requesting, running, verifying and storing a meeting summary
(docs/decisions.md D-125).

The AI operation returns a draft (apps/ai/summarisation.py). Everything that decides what is
believed and stored is here, and none of it is a model's judgement:

- **Whether a summary is attempted at all.** A transcript under
  MINIMUM_SUMMARY_TRANSCRIPT_LENGTH is never sent (FR-16: "rejected rather than submitted").
- **Which passages the model reads.** FR-09's own chunks of the transcript, whole, up to
  SUMMARY_INPUT_TOKENS; a longer transcript is recorded as truncated, not summarised silently
  from a fragment.
- **Which references survive.** A passage number is kept only if that passage was sent: set
  membership, as FR-12's citations are verified (invariant 5). An element left with no reference
  is dropped, and a draft whose narrative loses every sentence fails the run under its own
  reason, FR-12's path (b) for a summary (invariant 7's distinction).
- **Who owns an action item and when it is due.** apps/meetings/owners.py and due_dates.py.
- **Who may read the result.** The summary is indexed as the meeting's own chunks, stamped with
  the meeting's ``visible_to_roles`` read under a row lock in the transaction that writes them
  (invariants 1 and 2). D-47's cascade and the meeting's deletion cover them by construction,
  because they carry the meeting's source type and id.

**Isolation (invariant 8, NFR-20).** Nothing here can fail FR-09's ingestion: the request is a
row written in a savepoint with every exception caught (apps/ingestion/meetings.py), and the run
itself happens after that transaction commits, in a background thread
(apps/meetings/summary_runner.py). A run that fails for any reason leaves the transcript stored
and searchable, marks the summary Unavailable, and queues it for the hourly retry.

**A run's life.** ``request_summary`` creates a Processing row. ``run_summary`` ends it Ready
or Unavailable, and never leaves it Processing unless the process dies, which
``reclaim_orphans`` repairs. The retry queue is every row with ``queued_for_retry`` set;
``retry_summary`` runs one again. One run is in flight per meeting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

import apps.ai
from apps.ai.base import (
    ExtractedActionItem,
    MalformedSummary,
    MeetingSummaryDraft,
    ProviderRefused,
    ProviderUnavailable,
    SummaryElement,
)
from apps.core.constants import (
    ACTION_ITEM_FROM_AI,
    ACTION_ITEM_FROM_USER,
    MAXIMUM_SUMMARY_RETRY_RUNS,
    MINIMUM_SUMMARY_TRANSCRIPT_LENGTH,
    SUMMARY_FAILED_ERROR,
    SUMMARY_FAILED_INDEXING,
    SUMMARY_FAILED_MALFORMED,
    SUMMARY_FAILED_NO_VERIFIED_NARRATIVE,
    SUMMARY_FAILED_ORPHANED,
    SUMMARY_FAILED_PROVIDER_REFUSED,
    SUMMARY_FAILED_PROVIDER_UNAVAILABLE,
    SUMMARY_INPUT_TOKENS,
    SUMMARY_PROCESSING,
    SUMMARY_READY,
    SUMMARY_STALE_AFTER_SECONDS,
    SUMMARY_UNAVAILABLE,
)
from apps.documents.models import ContentChunk
from apps.ingestion.chunking import length_in_tokens, split_into_overlapping_chunks
from apps.ingestion.embedding import MEETING_SOURCE_TYPE, embed_and_store_chunks
from apps.meetings.due_dates import resolve_due_date
from apps.meetings.models import ActionItem, Meeting, MeetingSummary
from apps.meetings.owners import OwnerDirectory

logger = logging.getLogger(__name__)


class TranscriptTooShort(Exception):
    """The transcript is under MINIMUM_SUMMARY_TRANSCRIPT_LENGTH: the routes answer 422 (FR-16)."""


class SummaryIndexingFailed(Exception):
    """No chunk of the summary could be embedded: the storing transaction is rolled back."""


# --- What the model reads --------------------------------------------------------------------


def transcript_is_long_enough(meeting: Meeting) -> bool:
    """FR-16's minimum, counted by the chunker's own definition of a token (D-31)."""
    return length_in_tokens(meeting.transcript_text) >= MINIMUM_SUMMARY_TRANSCRIPT_LENGTH


@dataclass(frozen=True)
class SummaryInput:
    """The passages one request carries, and how many the transcript has in all."""

    passages: list[str]
    total: int

    @property
    def truncated(self) -> bool:
        return len(self.passages) < self.total


def summary_input(transcript_text: str) -> SummaryInput:
    """FR-09's own passages of the transcript, whole, up to SUMMARY_INPUT_TOKENS.

    ``split_into_overlapping_chunks`` is the chunker that indexed the transcript, so passage
    ``n`` here is the text of the transcript's chunk ``n - 1`` wherever it was indexed. The first
    passage is always sent; each later one is sent only if it fits whole. FR-16 sends "a single
    structured request", so what does not fit is left out and recorded, never summarised in a
    second call.
    """
    chunks = split_into_overlapping_chunks(transcript_text)
    passages: list[str] = []
    used = 0
    for chunk in chunks:
        size = length_in_tokens(chunk.text)
        if passages and used + size > SUMMARY_INPUT_TOKENS:
            break
        passages.append(chunk.text)
        used += size
    return SummaryInput(passages=passages, total=len(chunks))


# --- Verification: set membership, never a judgement (invariant 5) ---------------------------


@dataclass(frozen=True)
class VerifiedDraft:
    """A draft with every reference checked against the passages sent, and what was dropped."""

    narrative: tuple[SummaryElement, ...]
    decisions: tuple[SummaryElement, ...]
    highlights: tuple[SummaryElement, ...]
    action_items: tuple[ExtractedActionItem, ...]
    dropped: int

    @property
    def referenced(self) -> list[int]:
        """Every passage number an element kept, ascending."""
        numbers = {
            number
            for element in (*self.narrative, *self.decisions, *self.highlights, *self.action_items)
            for number in element.passages
        }
        return sorted(numbers)


def verify_draft(draft: MeetingSummaryDraft, *, passage_count: int) -> VerifiedDraft:
    """Keep only references to passages that were sent, and only elements that keep one.

    The passages sent were numbered 1 to ``passage_count``, so a reference is verified by
    ``1 <= n <= passage_count`` and by nothing else. This cannot tell whether passage 3 supports
    the sentence that cites it, and does not pretend to (invariant 5's conceded limitation); it
    does guarantee that no element reaches storage citing a passage the model was never shown.
    """
    dropped = 0

    def kept(element):
        nonlocal dropped
        numbers = tuple(number for number in element.passages if 1 <= number <= passage_count)
        if not numbers:
            dropped += 1
            return None
        return numbers

    def elements(items):
        verified = []
        for item in items:
            numbers = kept(item)
            if numbers is not None:
                verified.append(SummaryElement(text=item.text, passages=numbers))
        return tuple(verified)

    action_items = []
    for item in draft.action_items:
        numbers = kept(item)
        if numbers is not None:
            action_items.append(
                ExtractedActionItem(
                    description=item.description, owner=item.owner, due=item.due, passages=numbers
                )
            )
    return VerifiedDraft(
        narrative=elements(draft.narrative),
        decisions=elements(draft.decisions),
        highlights=elements(draft.highlights),
        action_items=tuple(action_items),
        dropped=dropped,
    )


# --- Reading a meeting's summary state -------------------------------------------------------


def latest_run(meeting: Meeting) -> MeetingSummary | None:
    """The most recently requested run, whatever its status: the highest ``run_number``."""
    return meeting.summaries.order_by("-run_number").first()


def current_summary(meeting: Meeting) -> MeetingSummary | None:
    """The summary to show: the latest Ready run. A failed or running one is never shown."""
    return meeting.summaries.filter(status=SUMMARY_READY).order_by("-run_number").first()


def action_items_of(meeting: Meeting):
    """The meeting's action items in the panel's order (``ActionItem.position``)."""
    return meeting.action_items.select_related("owner").order_by("position", "created_at", "pk")


def _is_stale(summary: MeetingSummary, now=None) -> bool:
    """A Processing run older than SUMMARY_STALE_AFTER_SECONDS was left by a stopped server."""
    if summary.status != SUMMARY_PROCESSING or summary.started_at is None:
        return False
    now = now or timezone.now()
    return summary.started_at < now - timedelta(seconds=SUMMARY_STALE_AFTER_SECONDS)


def reported_state(summary: MeetingSummary | None, now=None) -> tuple[str | None, bool]:
    """The status and retry flag a reader is told for ``summary``, the latest run: the one rule.

    Both summary routes report through this, and ``is_in_progress`` decides their 202 from it, so
    the body and the code cannot disagree. Its one translation: **a Processing run older than
    SUMMARY_STALE_AFTER_SECONDS is reported as Unavailable and queued.** Such a run was left by a
    server that stopped mid-run, and no thread is carrying it; reporting it as what the next
    scheduled retry makes of it lets the page stop asking and offer Generate again, and
    ``request_summary`` then closes the stale run and starts a new one. Reported as Processing, it
    would keep the page waiting, with the button disabled, until the scheduled retry ran. Nothing
    is written here: a read repairs nothing (``reclaim_orphans`` does that).
    """
    if summary is None:
        return None, False
    if _is_stale(summary, now):
        return SUMMARY_UNAVAILABLE, True
    return summary.status, summary.queued_for_retry


def is_in_progress(summary: MeetingSummary | None) -> bool:
    """FR-16's "202 Accepted while processing": a run in flight, or one queued for its retry.

    Read from ``reported_state``, so a stale run counts too, as queued: the next scheduled retry
    reclaims it and runs it again, so from the reader's side a summary is still coming.
    """
    status, queued = reported_state(summary)
    return status == SUMMARY_PROCESSING or (status == SUMMARY_UNAVAILABLE and queued)


# --- Requesting a run ------------------------------------------------------------------------


def request_summary(
    meeting: Meeting, *, requested_by=None, start: bool = True
) -> tuple[MeetingSummary, bool]:
    """Create a Processing run for ``meeting`` and start it once this transaction commits.

    Returns the run and whether it is a new one. **One run is in flight per meeting:** where
    one is already Processing, that run is returned and nothing starts. The meeting's row is
    locked for the decision, so two requests cannot both find none.

    ``start=False`` creates the run and starts nothing: the caller then calls ``run_summary``
    itself, in its own process. The management commands do, so that a run they make is carried
    once, by them, and never also by a background thread.

    A new run supersedes whatever was waiting: an older run's place in the retry queue is given
    up, because the newer result is the one wanted, and a stale Processing run is closed as
    orphaned. Raises TranscriptTooShort before anything is written.

    The run is started by ``transaction.on_commit``, so it never begins inside the caller's
    transaction: called from FR-09's ingestion, it starts only after the meeting and its chunks
    have committed, and not at all if they roll back.
    """
    # Imported here: the runner imports this module for ``run_summary``.
    from apps.meetings.summary_runner import start_summary_run

    if not transcript_is_long_enough(meeting):
        raise TranscriptTooShort(str(meeting.pk))
    with transaction.atomic():
        locked = Meeting.objects.select_for_update().get(pk=meeting.pk)
        previous = latest_run(locked)
        in_flight = locked.summaries.filter(status=SUMMARY_PROCESSING).order_by("-run_number").first()
        if in_flight is not None:
            if not _is_stale(in_flight):
                return in_flight, False
            _close(in_flight, SUMMARY_FAILED_ORPHANED, queue=False)
        locked.summaries.filter(queued_for_retry=True).update(queued_for_retry=False)
        summary = MeetingSummary.objects.create(
            meeting=locked,
            run_number=previous.run_number + 1 if previous is not None else 1,
            requested_by=requested_by,
            started_at=timezone.now(),
        )
        if start:
            transaction.on_commit(lambda: start_summary_run(summary.pk))
    return summary, True


# --- Running one -----------------------------------------------------------------------------


def run_summary(summary_id) -> MeetingSummary | None:
    """Carry one Processing run to Ready or Unavailable. Returns the row, or None if it has gone.

    The provider call is made with no transaction open and no lock held. Everything is then
    written in one transaction (``_store``): the summary, its action items and its index entries
    commit together or not at all, so a Ready summary is always searchable and a failed one never
    is (UC-04, NFR-21's rule for a derived record).

    Every way of failing ends in ``_fail`` with its own reason: the provider unreachable after
    MAXIMUM_SUMMARY_ATTEMPTS, a refusal, a second malformed reply, a reply whose narrative cites
    nothing that was sent, and a summary that could not be embedded. Nothing is raised to the
    caller for any of them; the runner catches anything else and records it as "error".
    """
    summary = MeetingSummary.objects.select_related("meeting").filter(pk=summary_id).first()
    if summary is None or summary.status != SUMMARY_PROCESSING:
        return summary
    # The attempt starts now, not when the run was requested: in a background thread it may have
    # waited for one of MAXIMUM_SUMMARIES_IN_FLIGHT places, and a run timed from its request
    # could pass SUMMARY_STALE_AFTER_SECONDS while still queued, be reclaimed as an orphan and run
    # a second time beside itself. Only a row still Processing is touched.
    MeetingSummary.objects.filter(pk=summary.pk, status=SUMMARY_PROCESSING).update(
        started_at=timezone.now()
    )
    meeting = summary.meeting
    source = summary_input(meeting.transcript_text)
    try:
        # Looked up on the module at call time, never from-imported: the suite's autouse fixture
        # replaces this attribute with a stub (docs/ai-provider.md section 6).
        draft = apps.ai.get_ai_service().summarise_meeting(meeting.title, source.passages)
    except ProviderRefused as exc:
        return _fail(summary, SUMMARY_FAILED_PROVIDER_REFUSED, exc)
    except MalformedSummary as exc:
        return _fail(summary, SUMMARY_FAILED_MALFORMED, exc)
    except ProviderUnavailable as exc:
        return _fail(summary, SUMMARY_FAILED_PROVIDER_UNAVAILABLE, exc)

    verified = verify_draft(draft, passage_count=len(source.passages))
    if verified.dropped:
        # Recorded, not shown: a rising count means the model is citing passages it was not
        # given, which the reader never sees because those elements are gone.
        logger.warning(
            "Meeting %s summary %s: %d element(s) dropped for naming no passage that was sent",
            meeting.pk, summary.pk, verified.dropped,
        )
    if not verified.narrative:
        return _fail(
            summary, SUMMARY_FAILED_NO_VERIFIED_NARRATIVE,
            "no narrative sentence named a passage that was sent",
        )
    try:
        with transaction.atomic():
            return _store(summary.pk, verified, source, draft.model)
    except SummaryIndexingFailed as exc:
        return _fail(summary, SUMMARY_FAILED_INDEXING, exc)


def summary_index_text(summary: MeetingSummary) -> str:
    """What is embedded for a summary: its own sentences, and nothing else.

    The narrative, then each decision, then each highlight, one to a line. **No heading, no title,
    no date and no label is added,** because every word here is found by FR-12's keyword search: a
    first line naming the meeting would make a search for its title match the summary and show
    the summary's text where FR-12 shows the opening of the transcript, and a word such as
    "summary" or "decisions" would match every summarised meeting. That the passage is AI content
    is said by ``ContentChunk.ai_generated``, which every surface showing it reads (NFR-15), not
    by words inside it (D-125's dated correction). The embedding model is still told the
    meeting's title, through the document prefix (apps/ai/prefixes.py).

    The action items are not here: they are the table people edit, and an index entry must not
    disagree with the record a person corrected (D-125, choice 1).
    """
    lines = [summary.summary_text]
    lines.extend(element["text"] for element in summary.decisions)
    lines.extend(element["text"] for element in summary.highlights)
    return "\n".join(lines)


def index_summary(meeting: Meeting, summary: MeetingSummary) -> int:
    """Replace the meeting's summary chunks with ``summary``'s. Returns how many failed to embed.

    Called inside a transaction that holds the meeting's row lock, by ``_store`` and by
    ``manage.py reindex``. The rows are stamped from ``meeting.visible_to_roles`` as read under
    that lock (invariant 2), carry the meeting's source type and id, and are marked
    ``ai_generated``. Raises SummaryIndexingFailed when no chunk could be embedded, so the
    caller's transaction rolls back and the previous summary's chunks stay.
    """
    ContentChunk.objects.filter(
        source_type=MEETING_SOURCE_TYPE, source_id=meeting.pk, ai_generated=True
    ).delete()
    chunks = split_into_overlapping_chunks(summary_index_text(summary))
    failed = embed_and_store_chunks(
        chunks=chunks,
        source_type=MEETING_SOURCE_TYPE,
        source_id=meeting.pk,
        visible_to_roles=meeting.visible_to_roles,
        title=meeting.title,
        ai_generated=True,
    )
    if failed == len(chunks):
        raise SummaryIndexingFailed(f"none of the summary's {len(chunks)} chunk(s) could be embedded")
    return failed


def _elements(items) -> list[dict]:
    return [{"text": item.text, "passages": list(item.passages)} for item in items]


def _store(summary_id, verified: VerifiedDraft, source: SummaryInput, model: str) -> MeetingSummary | None:
    """Write a verified draft: the summary, its action items and its chunks, in the caller's transaction.

    **The meeting's row is locked first, and its ``visible_to_roles`` is read under that lock.**
    A visibility change made while the model was working has either committed, and is read here,
    or is waiting for this transaction, and its cascade then re-stamps the chunks written here
    (D-47). There is no interleaving in which a summary chunk carries a scope the meeting no
    longer has. A meeting deleted meanwhile is simply gone, and so is its run.
    """
    meeting = Meeting.objects.select_for_update().filter(pk=_meeting_id_of(summary_id)).first()
    if meeting is None:
        return None
    summary = MeetingSummary.objects.select_for_update().filter(pk=summary_id).first()
    if summary is None or summary.status != SUMMARY_PROCESSING:
        return summary  # closed by someone else while the model was working; nothing is written

    summary.narrative = _elements(verified.narrative)
    summary.decisions = _elements(verified.decisions)
    summary.highlights = _elements(verified.highlights)
    summary.summary_text = " ".join(element.text for element in verified.narrative)
    summary.passages = {str(number): source.passages[number - 1] for number in verified.referenced}
    summary.model = model
    summary.input_truncated = source.truncated
    summary.passages_sent = len(source.passages)
    summary.passages_total = source.total
    summary.action_items_extracted = len(verified.action_items)
    summary.status = SUMMARY_READY
    summary.generated_at = timezone.now()
    summary.queued_for_retry = False
    summary.failure_reason = ""
    summary.save()

    # FR-16: a person's additions and edits survive a Regenerate; the extracted items nobody
    # touched are replaced by this run's. The kept items then follow this run's, in the order
    # they already had, so the panel lists what was just extracted first and in the model's order.
    ActionItem.objects.filter(meeting=meeting, origin=ACTION_ITEM_FROM_AI, edited=False).delete()
    kept = list(action_items_of(meeting))
    for position, item in enumerate(kept, start=len(verified.action_items)):
        item.position = position
    ActionItem.objects.bulk_update(kept, ["position"])
    owners = OwnerDirectory.for_meeting(meeting)
    ActionItem.objects.bulk_create(
        [
            ActionItem(
                meeting=meeting,
                summary=summary,
                description=item.description,
                owner=owners.match(item.owner),
                owner_name=item.owner or "",
                due_date=resolve_due_date(item.due, meeting.meeting_date),
                due_text=item.due or "",
                passages=list(item.passages),
                origin=ACTION_ITEM_FROM_AI,
                position=position,
            )
            for position, item in enumerate(verified.action_items)
        ]
    )
    # An older run still waiting for its retry is superseded by this success.
    meeting.summaries.exclude(pk=summary.pk).filter(queued_for_retry=True).update(queued_for_retry=False)
    failed = index_summary(meeting, summary)
    if failed:
        logger.warning(
            "Meeting %s summary %s: %d of its chunk(s) could not be embedded", meeting.pk, summary.pk, failed
        )
    logger.info(
        "Meeting %s summary %s is ready: %d sentence(s), %d decision(s), %d highlight(s), %d action item(s)",
        meeting.pk, summary.pk, len(verified.narrative), len(verified.decisions),
        len(verified.highlights), len(verified.action_items),
    )
    return summary


def _meeting_id_of(summary_id):
    return MeetingSummary.objects.filter(pk=summary_id).values_list("meeting_id", flat=True).first()


def _close(summary: MeetingSummary, reason: str, *, queue: bool) -> None:
    """Mark a locked Processing row Unavailable. The caller holds its transaction."""
    summary.status = SUMMARY_UNAVAILABLE
    summary.failure_reason = reason
    summary.queued_for_retry = queue
    summary.save(update_fields=["status", "failure_reason", "queued_for_retry"])


def _fail(summary: MeetingSummary, reason: str, detail) -> MeetingSummary | None:
    """End a run Unavailable and queue it for retry (FR-16, NFR-20, UC-04 E1).

    FR-16: "Failures are retried twice before the summary is marked unavailable". NFR-20:
    "flagged for automatic retry". Queued unless MAXIMUM_SUMMARY_RETRY_RUNS queued runs have
    already failed, after which it waits for a person. Only a row still Processing is closed, so
    a run someone else has concluded is left as they left it. The transcript is untouched by
    construction: nothing in this module writes to a Meeting row.
    """
    with transaction.atomic():
        row = MeetingSummary.objects.select_for_update().filter(pk=summary.pk).first()
        if row is None or row.status != SUMMARY_PROCESSING:
            return row
        _close(row, reason, queue=row.retry_runs < MAXIMUM_SUMMARY_RETRY_RUNS)
    logger.warning(
        "Meeting %s summary %s is unavailable (%s; %s): %s",
        row.meeting_id, row.pk, reason,
        "queued for retry" if row.queued_for_retry else "not queued", detail,
    )
    return row


def fail_after_error(summary_id) -> None:
    """Close a run that raised something no rule above expected. The runner's last resort."""
    summary = MeetingSummary.objects.filter(pk=summary_id).first()
    if summary is not None:
        _fail(summary, SUMMARY_FAILED_ERROR, "an unexpected error; see the error log")


# --- The retry queue (NFR-20) ----------------------------------------------------------------


def retry_queue():
    """Every summary flagged for automatic retry, oldest request first."""
    return MeetingSummary.objects.filter(queued_for_retry=True).order_by("requested_at")


def reclaim_orphans(now=None) -> int:
    """Close every run a stopped server left Processing, queueing each. Returns how many."""
    now = now or timezone.now()
    cutoff = now - timedelta(seconds=SUMMARY_STALE_AFTER_SECONDS)
    reclaimed = 0
    for summary in MeetingSummary.objects.filter(status=SUMMARY_PROCESSING, started_at__lt=cutoff):
        closed = _fail(summary, SUMMARY_FAILED_ORPHANED, "left Processing by a stopped server")
        if closed is not None and closed.status == SUMMARY_UNAVAILABLE:
            reclaimed += 1
    return reclaimed


def retry_summary(summary: MeetingSummary) -> MeetingSummary | None:
    """Run one queued summary again, inline. Returns the row as the run left it.

    The row leaves the queue and becomes Processing again in one transaction, with its count of
    queued runs moved on, so two retry commands cannot both take it. ``_fail`` re-queues it if
    this run fails and the count allows.
    """
    with transaction.atomic():
        row = MeetingSummary.objects.select_for_update().filter(pk=summary.pk).first()
        if row is None or not row.queued_for_retry or row.status != SUMMARY_UNAVAILABLE:
            return row
        row.status = SUMMARY_PROCESSING
        row.queued_for_retry = False
        row.failure_reason = ""
        row.retry_runs += 1
        row.started_at = timezone.now()
        row.save(update_fields=["status", "queued_for_retry", "failure_reason", "retry_runs", "started_at"])
    return run_summary(row.pk)


# --- A person's action items (FR-16: "edit, delete or manually add") --------------------------

# Passed for a field a PATCH did not send, so that None can mean "set it to nothing": an owner
# cleared is unassigned, and a due date cleared is no date.
UNCHANGED = object()


def add_action_item(meeting: Meeting, *, description: str, owner=None, due_date=None) -> ActionItem:
    """An item a person adds: FR-16's "manually add items the extraction missed".

    ``origin`` "user", so it carries no AI badge (NFR-15) and no Regenerate replaces it. It goes
    after every item the meeting has. The meeting's row is locked for the position, so two people
    adding at once get different ones.
    """
    with transaction.atomic():
        locked = Meeting.objects.select_for_update().get(pk=meeting.pk)
        last = locked.action_items.aggregate(last=Max("position"))["last"]
        return ActionItem.objects.create(
            meeting=locked,
            description=description,
            owner=owner,
            due_date=due_date,
            origin=ACTION_ITEM_FROM_USER,
            position=0 if last is None else last + 1,
        )


def edit_action_item(
    item: ActionItem, *, description=UNCHANGED, owner=UNCHANGED, due_date=UNCHANGED
) -> ActionItem:
    """Change the fields given. An extracted item becomes ``edited`` and is then kept by Regenerate.

    ``owner_name`` and ``due_text`` are left as they are: they are what the transcript said, which
    an edit does not change, and the panel shows them beside whatever the person chose.
    """
    if description is not UNCHANGED:
        item.description = description
    if owner is not UNCHANGED:
        item.owner = owner
    if due_date is not UNCHANGED:
        item.due_date = due_date
    if item.origin == ACTION_ITEM_FROM_AI:
        item.edited = True
    item.save()
    return item
