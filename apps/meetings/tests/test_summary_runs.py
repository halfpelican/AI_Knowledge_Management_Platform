"""FR-16's apply layer end to end (apps/meetings/summaries.py, D-125): a run requested, carried
out against the stub provider, and stored.

What a Ready row must hold is UC-04's success guarantee: "a narrative account of the meeting, the
decisions reached, the action items raised, and the highlights of discussion", every element with
"a reference to the passage of the transcript it was drawn from", and "a record of the model that
produced it and the date of production". What an action item must hold is FR-16's: "description,
suggested owner and due date", the owner matched "against the user list" or left unassigned, the
date converted "using the meeting date as reference".

Then the rules about more than one run:

- **One run in flight per meeting.** A second request while one is Processing returns that run.
- **Regenerate keeps what a person did.** Items a person added or edited survive; the extracted
  items nobody touched are replaced.
- **A failed run changes nothing that was shown.** The previous Ready summary stays current, with
  its items and its index entries.
- **Everything a run writes commits together or not at all.**

A run is driven as the brief describes: ``request_summary`` registers it with
``transaction.on_commit``, and ``django_capture_on_commit_callbacks`` executes it inline. Rows are
told apart by ``run_number``, ``position`` and content, never by a timestamp: this machine's clock
ticks at about 15.6 ms.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth import get_user_model

import apps.meetings.summaries as summaries
from apps.ai.base import ProviderUnavailable
from apps.ai.testing import STUB_ACTION_ITEM, STUB_CHAT_MODEL, STUB_DECISION, stub_summary_sentence
from apps.core.constants import (
    ACTION_ITEM_FROM_AI,
    ACTION_ITEM_FROM_USER,
    MINIMUM_CONTENT_LENGTH,
    MINIMUM_SUMMARY_TRANSCRIPT_LENGTH,
    ROLE_NAMES,
    SOURCE_TYPES,
    SUMMARY_FAILED_ORPHANED,
    SUMMARY_FAILED_PROVIDER_UNAVAILABLE,
    SUMMARY_PROCESSING,
    SUMMARY_READY,
    SUMMARY_STATUS_VALUES,
    SUMMARY_UNAVAILABLE,
)
from apps.documents.models import ContentChunk
from apps.ingestion.chunking import split_into_overlapping_chunks
from apps.meetings.models import ActionItem, Meeting, MeetingSummary
from apps.meetings.summaries import (
    TranscriptTooShort,
    action_items_of,
    add_action_item,
    current_summary,
    edit_action_item,
    latest_run,
    request_summary,
    run_summary,
    transcript_is_long_enough,
)
from apps.meetings.tests.summary_builders import (
    MEETING_DATE,
    TITLE,
    action,
    draft,
    element,
    ingest,
    raising,
    regenerate,
    summarised,
    transcript,
)

pytestmark = pytest.mark.django_db

_, MEETING_SOURCE_TYPE = SOURCE_TYPES


def person(name: str):
    return get_user_model().objects.create_user(f"{'.'.join(name.lower().split())}@kmp.example", None, name=name)


def stored_meeting(words: int = MINIMUM_SUMMARY_TRANSCRIPT_LENGTH + 40, **fields) -> Meeting:
    """A meeting row written directly, as one ingested before FR-16 existed: no run was requested."""
    return Meeting.objects.create(
        title=fields.pop("title", TITLE), meeting_date=MEETING_DATE, transcript_text=transcript(words),
        visible_to_roles=list(ROLE_NAMES), **fields,
    )


def descriptions(meeting) -> list[str]:
    return [item.description for item in action_items_of(meeting)]


def summary_chunk_ids(meeting) -> set:
    return set(
        ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id, ai_generated=True)
        .values_list("id", flat=True)
    )


# --- A run's life: requested, then carried to Ready ------------------------------------------


def test_ingestion_requests_a_processing_run_and_the_commit_carries_it_to_ready(
    django_capture_on_commit_callbacks, stub_ai_service
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        meeting = ingest()

    [summary] = MeetingSummary.objects.filter(meeting=meeting)
    assert summary.status == SUMMARY_PROCESSING == SUMMARY_STATUS_VALUES[0]
    assert (summary.run_number, summary.requested_by, summary.queued_for_retry) == (1, None, False)
    assert summary.started_at is not None and summary.generated_at is None
    assert (summary.summary_text, summary.action_items_extracted) == ("", None)
    assert stub_ai_service.summarise_calls == []  # nothing was sent while the ingestion was open
    assert len(callbacks) == 1

    callbacks[0]()

    summary.refresh_from_db()
    assert summary.status == SUMMARY_READY, summary.failure_reason
    assert len(stub_ai_service.summarise_calls) == 1
    assert ActionItem.objects.filter(meeting=meeting).count() == 1
    assert len(summary_chunk_ids(meeting)) == 1


def test_the_default_stub_reply_is_stored_part_for_part(django_capture_on_commit_callbacks):
    meeting = summarised(django_capture_on_commit_callbacks)

    summary = MeetingSummary.objects.get(meeting=meeting)
    assert summary.summary_text == stub_summary_sentence(TITLE)
    assert summary.narrative == [{"text": stub_summary_sentence(TITLE), "passages": [1]}]
    assert summary.decisions == [{"text": STUB_DECISION, "passages": [1]}]
    assert summary.highlights == []
    assert summary.model == STUB_CHAT_MODEL
    [item] = ActionItem.objects.filter(meeting=meeting)
    assert (item.description, item.owner, item.due_date) == (STUB_ACTION_ITEM, None, None)


def test_a_ready_summary_holds_the_narrative_the_elements_their_passages_and_its_provenance(
    django_capture_on_commit_callbacks, stub_ai_service
):
    text = transcript(1300)  # three passages
    passages = [chunk.text for chunk in split_into_overlapping_chunks(text)]
    stub_ai_service.summary = draft(
        narrative=[element("The team reviewed the first quarter.", 1), element("It froze discretionary travel.", 1, 3)],
        decisions=[element("Discretionary travel is frozen until 31 January.", 3)],
        highlights=[element("Travel was twice its budget.", 1), element("Two renewals moved into October.", 3)],
        action_items=[action("Reconcile the cards", passages=(3,)), action("Send the forecast", passages=(1,))],
        model="claude-haiku-5-5",
    )

    meeting = summarised(django_capture_on_commit_callbacks, text=text)

    summary = MeetingSummary.objects.get(meeting=meeting)
    assert summary.status == SUMMARY_READY
    # FR-16's "concise paragraph-length summary": the narrative's sentences, joined.
    assert summary.summary_text == "The team reviewed the first quarter. It froze discretionary travel."
    assert summary.narrative == [
        {"text": "The team reviewed the first quarter.", "passages": [1]},
        {"text": "It froze discretionary travel.", "passages": [1, 3]},
    ]
    assert summary.decisions == [{"text": "Discretionary travel is frozen until 31 January.", "passages": [3]}]
    assert summary.highlights == [
        {"text": "Travel was twice its budget.", "passages": [1]},
        {"text": "Two renewals moved into October.", "passages": [3]},
    ]
    # The TEXT of exactly the passages an element names: 1 and 3, and not 2, which nothing cites.
    assert summary.passages == {"1": passages[0], "3": passages[2]}
    # UC-04: "a record of the model that produced it and the date of production".
    assert summary.model == "claude-haiku-5-5"
    assert summary.generated_at is not None and summary.generated_at >= summary.requested_at
    assert (summary.passages_sent, summary.passages_total, summary.input_truncated) == (3, 3, False)
    assert summary.action_items_extracted == 2
    assert (summary.queued_for_retry, summary.retry_runs, summary.failure_reason) == (False, 0, "")
    assert current_summary(meeting) == latest_run(meeting) == summary


def test_a_meeting_that_raised_no_action_items_is_ready_with_an_empty_section_recorded(
    django_capture_on_commit_callbacks, stub_ai_service
):
    """UC-04 A1: "The system records the action item section as empty rather than omitting it."
    Zero is recorded, which is not the null of a run that never finished, and the run is Ready."""
    stub_ai_service.summary = draft(action_items=())

    meeting = summarised(django_capture_on_commit_callbacks)

    summary = MeetingSummary.objects.get(meeting=meeting)
    assert summary.status == SUMMARY_READY
    assert summary.action_items_extracted == 0
    assert summary.action_items_extracted is not None
    assert not ActionItem.objects.filter(meeting=meeting).exists()
    assert list(action_items_of(meeting)) == []


def test_a_person_who_requests_a_run_is_recorded_and_ingestion_records_nobody(
    django_capture_on_commit_callbacks, employee
):
    meeting = summarised(django_capture_on_commit_callbacks)

    second = regenerate(django_capture_on_commit_callbacks, meeting, requested_by=employee)

    first = MeetingSummary.objects.get(meeting=meeting, run_number=1)
    assert first.requested_by is None
    assert second.requested_by == employee
    assert second.status == SUMMARY_READY


# --- Action items: owner, date, the transcript's own words, and the order -----------------------


def test_extracted_items_get_their_owner_their_date_and_the_words_as_said(
    django_capture_on_commit_callbacks, stub_ai_service
):
    """The meeting is on Tuesday 10 November 2026. Alex Morgan and Priya Raman attended; Alex
    Petrov and Wei Zhang are users who did not."""
    alex, priya, other_alex, wei = (person(name) for name in ("Alex Morgan", "Priya Raman", "Alex Petrov", "Wei Zhang"))
    stub_ai_service.summary = draft(
        action_items=[
            action("Reconcile the September card statements", owner="Alex", due="next Friday", passages=(1,)),
            action("Send the forecast to the board", owner="Wei Zhang", due="by the 14th", passages=(1,)),
            action("Chase the fit-out quote", owner="the facilities team", due="before the move", passages=(1,)),
            action("Book the boardroom", owner="Wei", due="tomorrow", passages=(1,)),
            action("Circulate the minutes", passages=(1,)),
        ]
    )

    meeting = summarised(django_capture_on_commit_callbacks, attendees=[alex, priya])

    summary = MeetingSummary.objects.get(meeting=meeting)
    items = list(action_items_of(meeting))
    assert [
        (item.description, item.owner, item.owner_name, item.due_date, item.due_text) for item in items
    ] == [
        # A lone first name, and exactly one attendee has it: assigned. "Next Friday" from a
        # Tuesday is the Friday of the following week.
        ("Reconcile the September card statements", alex, "Alex", date(2026, 11, 20), "next Friday"),
        # A full name one user has: assigned, though she did not attend.
        ("Send the forecast to the board", wei, "Wei Zhang", date(2026, 11, 14), "by the 14th"),
        # A team, and a deadline no rule fixes: unassigned and undated, both phrases kept.
        ("Chase the fit-out quote", None, "the facilities team", None, "before the move"),
        # A first name whose only holder did not attend: unassigned, not guessed.
        ("Book the boardroom", None, "Wei", date(2026, 11, 11), "tomorrow"),
        # Nobody named, nothing said: unassigned, undated, and blank rather than null.
        ("Circulate the minutes", None, "", None, ""),
    ]
    for position, item in enumerate(items):
        assert (item.origin, item.edited, item.position) == (ACTION_ITEM_FROM_AI, False, position)
        assert item.summary == summary
        assert item.passages == [1]
        assert item.meeting == meeting
    assert summary.action_items_extracted == 5
    assert other_alex not in [item.owner for item in items]


def test_a_due_date_is_resolved_from_the_meetings_date_and_not_from_today(
    django_capture_on_commit_callbacks, stub_ai_service
):
    """A transcript ingested long after its meeting: "tomorrow" is the day after the meeting."""
    stub_ai_service.summary = draft(action_items=[action("Ring the supplier", due="tomorrow")])

    meeting = summarised(django_capture_on_commit_callbacks, meeting_date=date(2024, 2, 28))

    assert ActionItem.objects.get(meeting=meeting).due_date == date(2024, 2, 29)


def test_extracted_items_are_listed_in_the_replys_order(django_capture_on_commit_callbacks, stub_ai_service):
    stub_ai_service.summary = draft(action_items=[action(name) for name in ("Zebra", "Apple", "Mango", "Banana")])

    meeting = summarised(django_capture_on_commit_callbacks)

    assert descriptions(meeting) == ["Zebra", "Apple", "Mango", "Banana"]
    assert [item.position for item in action_items_of(meeting)] == [0, 1, 2, 3]


def test_a_deadline_no_date_can_hold_leaves_the_item_undated_and_the_summary_ready(
    django_capture_on_commit_callbacks, stub_ai_service
):
    """The consequence of the defect apps/meetings/tests/test_due_dates.py reports. A deadline is
    the model's copy of uploaded text; one that names no possible date must leave that one item
    undated ("a date is never invented"), not end the whole run as an error.

    **This test found a defect.** As first written on 11 November 2026, ``resolve_due_date``
    raised OverflowError inside ``_store``, so the run was recorded as "error" and every retry of
    the same reply would have failed the same way. Fixed on 12 November in due_dates.py."""
    stub_ai_service.summary = draft(
        action_items=[action("Archive the ledgers", due="in 3000000 days"), action("Ring the supplier", due="tomorrow")]
    )

    meeting = summarised(django_capture_on_commit_callbacks)

    summary = MeetingSummary.objects.get(meeting=meeting)
    assert summary.status == SUMMARY_READY, f"run ended {summary.status} ({summary.failure_reason})"
    assert [(item.due_date, item.due_text) for item in action_items_of(meeting)] == [
        (None, "in 3000000 days"),
        (date(2026, 11, 11), "tomorrow"),
    ]


# --- A person's own action items (FR-16: "edit, delete or manually add") --------------------------


def test_a_hand_added_item_goes_after_every_item_and_carries_no_ai_mark(
    django_capture_on_commit_callbacks, stub_ai_service
):
    wei = person("Wei Zhang")
    stub_ai_service.summary = draft(action_items=[action("First extracted"), action("Second extracted")])
    meeting = summarised(django_capture_on_commit_callbacks)

    added = add_action_item(meeting, description="Order the catering", owner=wei, due_date=date(2026, 11, 30))
    bare = add_action_item(meeting, description="Tidy the shared drive")

    assert descriptions(meeting) == ["First extracted", "Second extracted", "Order the catering", "Tidy the shared drive"]
    assert (added.position, bare.position) == (2, 3)
    for item in (added, bare):
        assert (item.origin, item.edited, item.summary) == (ACTION_ITEM_FROM_USER, False, None)
        assert (item.owner_name, item.due_text, item.passages) == ("", "", [])
    assert (added.owner, added.due_date) == (wei, date(2026, 11, 30))
    assert (bare.owner, bare.due_date) == (None, None)


def test_the_first_item_of_a_meeting_with_none_takes_the_first_position():
    meeting = stored_meeting(MINIMUM_CONTENT_LENGTH)  # too short to summarise; items can still be added

    first = add_action_item(meeting, description="First")
    second = add_action_item(meeting, description="Second")

    assert (first.position, second.position) == (0, 1)
    assert descriptions(meeting) == ["First", "Second"]


def test_editing_an_extracted_item_changes_the_fields_given_and_marks_it_edited(
    django_capture_on_commit_callbacks, stub_ai_service
):
    alex, wei = person("Alex Morgan"), person("Wei Zhang")
    stub_ai_service.summary = draft(
        action_items=[action("Reconcile the cards", owner="Alex", due="next Friday", passages=(1,))]
    )
    meeting = summarised(django_capture_on_commit_callbacks, attendees=[alex])
    item = ActionItem.objects.get(meeting=meeting)
    assert (item.owner, item.due_date, item.edited) == (alex, date(2026, 11, 20), False)

    edit_action_item(item, description="Reconcile the cards and the float")

    item.refresh_from_db()
    assert item.description == "Reconcile the cards and the float"
    assert item.edited is True
    assert item.origin == ACTION_ITEM_FROM_AI  # still extracted; NFR-15's badge reads both
    # The fields not given are unchanged, and so is everything the transcript said.
    assert (item.owner, item.due_date) == (alex, date(2026, 11, 20))
    assert (item.owner_name, item.due_text, item.passages, item.position) == ("Alex", "next Friday", [1], 0)

    edit_action_item(item, owner=wei, due_date=date(2026, 12, 1))

    item.refresh_from_db()
    assert (item.owner, item.due_date, item.description) == (wei, date(2026, 12, 1), "Reconcile the cards and the float")
    assert (item.owner_name, item.due_text) == ("Alex", "next Friday")  # what was said, beside what was chosen


def test_none_clears_an_owner_and_a_date_and_is_not_the_same_as_leaving_them_out(
    django_capture_on_commit_callbacks, stub_ai_service
):
    alex = person("Alex Morgan")
    stub_ai_service.summary = draft(action_items=[action("Reconcile the cards", owner="Alex", due="next Friday")])
    meeting = summarised(django_capture_on_commit_callbacks, attendees=[alex])
    item = ActionItem.objects.get(meeting=meeting)

    edit_action_item(item, owner=None)
    item.refresh_from_db()
    assert (item.owner, item.due_date) == (None, date(2026, 11, 20))  # unassigned; the date untouched

    edit_action_item(item, due_date=None)
    item.refresh_from_db()
    assert (item.owner, item.due_date) == (None, None)
    assert (item.owner_name, item.due_text) == ("Alex", "next Friday")


def test_editing_a_hand_added_item_does_not_mark_it_edited():
    """``edited`` means "a person changed what the AI extracted". A person's own item was never
    the AI's, so it carries no badge before or after."""
    meeting = stored_meeting()
    item = add_action_item(meeting, description="Order the catering")

    edit_action_item(item, description="Order the catering for twelve", due_date=date(2026, 11, 30))

    item.refresh_from_db()
    assert (item.description, item.due_date) == ("Order the catering for twelve", date(2026, 11, 30))
    assert (item.origin, item.edited) == (ACTION_ITEM_FROM_USER, False)


# --- More than one run ------------------------------------------------------------------------------


def test_run_numbers_rise_per_meeting_and_latest_and_current_follow_them(
    django_capture_on_commit_callbacks, stub_ai_service
):
    meeting = summarised(django_capture_on_commit_callbacks)
    other = summarised(django_capture_on_commit_callbacks, title="Another meeting")
    first = MeetingSummary.objects.get(meeting=meeting)
    assert (first.run_number, latest_run(meeting), current_summary(meeting)) == (1, first, first)

    stub_ai_service.summary = raising(ProviderUnavailable("stub outage"))
    second = regenerate(django_capture_on_commit_callbacks, meeting)
    assert (second.run_number, second.status) == (2, SUMMARY_UNAVAILABLE)
    assert latest_run(meeting) == second
    assert current_summary(meeting) == first  # a failed run is never the one shown

    stub_ai_service.summary = None
    third = regenerate(django_capture_on_commit_callbacks, meeting)
    assert (third.run_number, third.status) == (3, SUMMARY_READY)
    assert latest_run(meeting) == current_summary(meeting) == third

    # Each meeting counts its own runs.
    assert [s.run_number for s in MeetingSummary.objects.filter(meeting=other)] == [1]
    assert sorted(MeetingSummary.objects.filter(meeting=meeting).values_list("run_number", flat=True)) == [1, 2, 3]


def test_a_meeting_never_asked_for_a_summary_has_no_latest_and_no_current_run():
    meeting = stored_meeting()

    assert latest_run(meeting) is None
    assert current_summary(meeting) is None
    assert list(action_items_of(meeting)) == []


def test_a_second_request_while_one_is_processing_returns_that_run_and_starts_nothing(
    django_capture_on_commit_callbacks, stub_ai_service, employee
):
    """D-125: one run in flight per meeting. One callback is registered, by the first request; the
    second registers none, creates no row, and does not take the first run's place."""
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        meeting = ingest()
        first = MeetingSummary.objects.get(meeting=meeting)
        again, is_new = request_summary(meeting, requested_by=employee)
        a_third_time, still_not_new = request_summary(meeting)

    assert again == first and a_third_time == first
    assert (is_new, still_not_new) == (False, False)
    assert len(callbacks) == 1
    assert MeetingSummary.objects.filter(meeting=meeting).count() == 1
    first.refresh_from_db()
    assert (first.status, first.requested_by) == (SUMMARY_PROCESSING, None)
    assert stub_ai_service.summarise_calls == []


def test_a_request_after_a_run_has_ended_is_a_new_run(django_capture_on_commit_callbacks):
    meeting = summarised(django_capture_on_commit_callbacks)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        summary, is_new = request_summary(meeting)

    assert (is_new, summary.run_number, summary.status) == (True, 2, SUMMARY_PROCESSING)
    assert len(callbacks) == 1


def test_start_false_creates_the_run_and_registers_no_callback(django_capture_on_commit_callbacks, stub_ai_service):
    """The management commands carry their own runs: a run they make must not also be carried by a
    background thread. With ``start=False`` the row is there, nothing is registered, and the
    caller's own ``run_summary`` finishes it."""
    meeting = stored_meeting()

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        summary, is_new = request_summary(meeting, start=False)

    assert callbacks == []
    assert (is_new, summary.status, summary.run_number) == (True, SUMMARY_PROCESSING, 1)
    assert stub_ai_service.summarise_calls == []

    finished = run_summary(summary.pk)

    assert finished.status == SUMMARY_READY
    assert len(stub_ai_service.summarise_calls) == 1


def test_run_summary_does_nothing_to_a_run_that_has_ended_and_returns_none_for_one_that_is_gone(
    django_capture_on_commit_callbacks, stub_ai_service
):
    import uuid

    meeting = summarised(django_capture_on_commit_callbacks)
    summary = MeetingSummary.objects.get(meeting=meeting)
    before = (summary.generated_at, summary.summary_text)

    again = run_summary(summary.pk)

    assert again == summary
    assert len(stub_ai_service.summarise_calls) == 1  # not called a second time
    summary.refresh_from_db()
    assert (summary.generated_at, summary.summary_text) == before
    assert run_summary(uuid.uuid4()) is None


# --- Regenerate keeps what a person did ----------------------------------------------------------------


def test_a_regenerate_keeps_hand_added_and_edited_items_and_replaces_the_untouched_ones(
    django_capture_on_commit_callbacks, stub_ai_service
):
    """FR-16: "Users can edit, delete or manually add items the extraction missed", and a
    "Regenerate Summary" button. D-125: Regenerate keeps every item a person added or edited and
    replaces the AI items nobody touched."""
    stub_ai_service.summary = draft(action_items=[action("Alpha"), action("Bravo"), action("Charlie")])
    meeting = summarised(django_capture_on_commit_callbacks)
    first = MeetingSummary.objects.get(meeting=meeting)
    alpha, bravo, charlie = action_items_of(meeting)
    edit_action_item(bravo, description="Bravo, as corrected by a person")
    hand_added = add_action_item(meeting, description="Hand-added")

    stub_ai_service.summary = draft(action_items=[action("Xray"), action("Yankee")])
    second = regenerate(django_capture_on_commit_callbacks, meeting)

    assert second.status == SUMMARY_READY
    remaining = {item.description: item for item in ActionItem.objects.filter(meeting=meeting)}
    assert set(remaining) == {"Bravo, as corrected by a person", "Hand-added", "Xray", "Yankee"}
    # The untouched extracted items are gone, not merely hidden.
    assert not ActionItem.objects.filter(pk__in=[alpha.pk, charlie.pk]).exists()
    # The edited one is the same row, still marked as the AI's and as edited, from the first run.
    kept = remaining["Bravo, as corrected by a person"]
    assert (kept.pk, kept.origin, kept.edited, kept.summary) == (bravo.pk, ACTION_ITEM_FROM_AI, True, first)
    # The hand-added one is the same row.
    assert (remaining["Hand-added"].pk, remaining["Hand-added"].origin) == (hand_added.pk, ACTION_ITEM_FROM_USER)
    # The new ones are this run's.
    for name in ("Xray", "Yankee"):
        assert (remaining[name].origin, remaining[name].edited, remaining[name].summary) == (
            ACTION_ITEM_FROM_AI, False, second,
        )
    assert second.action_items_extracted == 2
    assert current_summary(meeting) == second


def test_a_regenerate_that_extracts_nothing_still_keeps_a_persons_items(
    django_capture_on_commit_callbacks, stub_ai_service
):
    meeting = summarised(django_capture_on_commit_callbacks)
    add_action_item(meeting, description="Hand-added")

    stub_ai_service.summary = draft(action_items=())
    second = regenerate(django_capture_on_commit_callbacks, meeting)

    assert (second.status, second.action_items_extracted) == (SUMMARY_READY, 0)
    assert descriptions(meeting) == ["Hand-added"]


def test_after_a_regenerate_extracted_items_come_first_in_the_models_order_then_hand_added_ones(
    django_capture_on_commit_callbacks, stub_ai_service
):
    """docs/api-contract.md, the action item object: "Order: extracted items in the model's order,
    then hand-added items in the order added." It must still hold after a Regenerate that extracts
    more items than the run before it.

    **This test found a defect.** As first written on 11 November 2026, a hand-added item kept
    the position it was given when added (after the items the meeting THEN had), and a new run
    numbered its items from 0 again, so the hand-added items ended up among the extracted ones.
    Fixed on 12 November: ``_store`` renumbers the kept items to follow the new run's."""
    stub_ai_service.summary = draft(action_items=[action("Extracted by the first run")])
    meeting = summarised(django_capture_on_commit_callbacks)
    add_action_item(meeting, description="Hand-added first")
    add_action_item(meeting, description="Hand-added second")
    assert descriptions(meeting) == ["Extracted by the first run", "Hand-added first", "Hand-added second"]

    stub_ai_service.summary = draft(action_items=[action(f"Extracted {number}") for number in (1, 2, 3, 4)])
    regenerate(django_capture_on_commit_callbacks, meeting)

    assert descriptions(meeting) == [
        "Extracted 1", "Extracted 2", "Extracted 3", "Extracted 4", "Hand-added first", "Hand-added second",
    ]


def test_an_item_added_after_a_regenerate_goes_after_everything(django_capture_on_commit_callbacks, stub_ai_service):
    stub_ai_service.summary = draft(action_items=[action("Alpha"), action("Bravo"), action("Charlie")])
    meeting = summarised(django_capture_on_commit_callbacks)
    stub_ai_service.summary = draft(action_items=[action("Xray")])
    regenerate(django_capture_on_commit_callbacks, meeting)

    add_action_item(meeting, description="Added last")

    assert descriptions(meeting)[-1] == "Added last"
    assert descriptions(meeting) == ["Xray", "Added last"]


# --- A failed run changes nothing that was shown ------------------------------------------------------------


def test_a_failed_regenerate_leaves_the_previous_summary_its_items_and_its_index_entries(
    django_capture_on_commit_callbacks, stub_ai_service
):
    """D-125: "The previous Ready summary stays shown until the new run is Ready; if it fails, the
    old one stays." Not only the row: the extracted items and the searchable passages are the old
    summary's too, untouched."""
    stub_ai_service.summary = draft(
        narrative=[element("The first summary.", 1)], action_items=[action("Alpha"), action("Bravo")]
    )
    meeting = summarised(django_capture_on_commit_callbacks)
    first = MeetingSummary.objects.get(meeting=meeting)
    items_before = sorted(ActionItem.objects.filter(meeting=meeting).values_list("pk", flat=True))
    chunks_before = summary_chunk_ids(meeting)
    assert len(items_before) == 2 and len(chunks_before) == 1

    stub_ai_service.summary = raising(ProviderUnavailable("stub outage"))
    second = regenerate(django_capture_on_commit_callbacks, meeting)

    assert (second.status, second.failure_reason) == (SUMMARY_UNAVAILABLE, SUMMARY_FAILED_PROVIDER_UNAVAILABLE)
    assert (second.summary_text, second.narrative, second.model, second.generated_at) == ("", [], "", None)
    assert latest_run(meeting) == second
    shown = current_summary(meeting)
    assert shown == first and shown.summary_text == "The first summary."
    first.refresh_from_db()
    assert first.status == SUMMARY_READY
    assert sorted(ActionItem.objects.filter(meeting=meeting).values_list("pk", flat=True)) == items_before
    assert summary_chunk_ids(meeting) == chunks_before
    assert descriptions(meeting) == ["Alpha", "Bravo"]


def test_a_run_someone_else_concluded_while_the_model_was_working_writes_nothing(
    django_capture_on_commit_callbacks, stub_ai_service
):
    """A run closed while its call was out (a new request closing a stale one, say) is left as it
    was closed. The reply that then arrives is not stored: not as text, not as items, not as index
    entries, and the row does not become Ready."""
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        meeting = ingest()
    summary = MeetingSummary.objects.get(meeting=meeting)

    def closed_meanwhile(title, passages):
        MeetingSummary.objects.filter(pk=summary.pk).update(
            status=SUMMARY_UNAVAILABLE, failure_reason=SUMMARY_FAILED_ORPHANED, queued_for_retry=False
        )
        return draft(narrative=[element("A reply that arrived too late.", 1)], action_items=[action("Too late")])

    stub_ai_service.summary = closed_meanwhile
    callbacks[0]()

    summary.refresh_from_db()
    assert (summary.status, summary.failure_reason, summary.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_ORPHANED, False,
    )
    assert (summary.summary_text, summary.narrative, summary.generated_at) == ("", [], None)
    assert not ActionItem.objects.filter(meeting=meeting).exists()
    assert summary_chunk_ids(meeting) == set()


def test_everything_a_run_writes_commits_together_or_not_at_all(
    django_capture_on_commit_callbacks, stub_ai_service, monkeypatch
):
    """The summary, its action items and its index entries are one transaction (NFR-21's rule for
    a derived record). The index step is made to fail unexpectedly, after the row was saved Ready
    and the old items were replaced: all of it must roll back, so no Ready summary exists that is
    not searchable and no item of a summary that was never stored."""
    stub_ai_service.summary = draft(narrative=[element("The first summary.", 1)], action_items=[action("Alpha")])
    meeting = summarised(django_capture_on_commit_callbacks)
    first = MeetingSummary.objects.get(meeting=meeting)
    items_before = sorted(ActionItem.objects.filter(meeting=meeting).values_list("pk", flat=True))
    chunks_before = summary_chunk_ids(meeting)

    seen = {}

    def index_fails(meeting_row, summary_row):
        # Reached inside the transaction, after the writes it will roll back.
        seen["status"] = MeetingSummary.objects.get(pk=summary_row.pk).status
        seen["items"] = sorted(ActionItem.objects.filter(meeting=meeting_row).values_list("description", flat=True))
        raise RuntimeError("the index step failed unexpectedly")

    monkeypatch.setattr(summaries, "index_summary", index_fails)
    stub_ai_service.summary = draft(narrative=[element("The second summary.", 1)], action_items=[action("Xray")])
    with django_capture_on_commit_callbacks(execute=False):
        second, _ = request_summary(meeting)

    with pytest.raises(RuntimeError, match="index step failed"):
        run_summary(second.pk)

    assert seen == {"status": SUMMARY_READY, "items": ["Xray"]}  # the premise: it really was mid-write
    second.refresh_from_db()
    assert (second.status, second.summary_text, second.narrative) == (SUMMARY_PROCESSING, "", [])
    assert sorted(ActionItem.objects.filter(meeting=meeting).values_list("pk", flat=True)) == items_before
    assert descriptions(meeting) == ["Alpha"]
    assert summary_chunk_ids(meeting) == chunks_before
    assert current_summary(meeting) == first


# --- FR-16: "transcripts below a minimum length are rejected rather than submitted" ----------------------------


def test_the_minimum_is_counted_in_the_chunkers_tokens_and_is_met_at_exactly_the_minimum():
    assert MINIMUM_SUMMARY_TRANSCRIPT_LENGTH > MINIMUM_CONTENT_LENGTH  # a summary needs more than an index does
    assert transcript_is_long_enough(stored_meeting(MINIMUM_SUMMARY_TRANSCRIPT_LENGTH)) is True
    assert transcript_is_long_enough(stored_meeting(MINIMUM_SUMMARY_TRANSCRIPT_LENGTH - 1)) is False
    # Words, not characters: one very long word is one token.
    long_word = Meeting.objects.create(title=TITLE, meeting_date=MEETING_DATE, transcript_text="x" * 5000)
    assert transcript_is_long_enough(long_word) is False


def test_a_request_below_the_minimum_raises_and_writes_nothing(django_capture_on_commit_callbacks, stub_ai_service):
    meeting = stored_meeting(MINIMUM_SUMMARY_TRANSCRIPT_LENGTH - 1)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(TranscriptTooShort):
            request_summary(meeting)
        with pytest.raises(TranscriptTooShort):
            request_summary(meeting, start=False)

    assert callbacks == []
    assert not MeetingSummary.objects.exists()
    assert stub_ai_service.summarise_calls == []  # "rejected rather than submitted"


def test_a_request_at_exactly_the_minimum_is_carried_out(django_capture_on_commit_callbacks):
    meeting = stored_meeting(MINIMUM_SUMMARY_TRANSCRIPT_LENGTH)

    summary = regenerate(django_capture_on_commit_callbacks, meeting)

    assert summary.status == SUMMARY_READY
