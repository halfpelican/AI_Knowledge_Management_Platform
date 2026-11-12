"""What a summary may cite and what the model is shown (apps/meetings/summaries.py, D-125 choice 3).

**Verification is set membership, in application code, never a model judgement** (CLAUDE.md
invariant 5). The transcript is sent as passages numbered 1 to n, so a reference is believed if and
only if ``1 <= number <= n``:

- a reference outside the passages sent is removed;
- an element left with no reference is dropped, and counted;
- a draft whose narrative loses every sentence fails the whole run under its own reason,
  "no_verified_narrative", FR-12's path (b) for a summary (invariant 7's distinction), and nothing
  of it is stored: no summary text, no action item, no index entry (invariant 6: there is no
  state that shows an uncited statement).

What verification cannot do is conceded and pinned, not papered over: it does not know whether
passage 3 supports the sentence citing it.

**What the model reads** is ``summary_input``: FR-09's own chunks of the transcript, whole, up to
SUMMARY_INPUT_TOKENS, always at least one, with the total recorded so a long transcript is never
summarised silently from a fragment.
"""

from __future__ import annotations

import inspect
import logging

import pytest

import apps.meetings.summaries as summaries
from apps.ai.base import ExtractedActionItem, MeetingSummaryDraft, SummaryElement
from apps.ai.summarisation import (
    EXAMPLE_REPLY,
    MAXIMUM_PASSAGES,
    build_summary_user_prompt,
    parse_summary,
)
from apps.core.constants import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    SOURCE_TYPES,
    SUMMARY_FAILED_NO_VERIFIED_NARRATIVE,
    SUMMARY_INPUT_TOKENS,
    SUMMARY_READY,
    SUMMARY_UNAVAILABLE,
)
from apps.documents.models import ContentChunk
from apps.ingestion.chunking import length_in_tokens, split_into_overlapping_chunks
from apps.meetings.models import ActionItem, MeetingSummary
from apps.meetings.summaries import SummaryInput, retry_queue, summary_input, verify_draft
from apps.meetings.tests.summary_builders import action, draft, element, summarised, transcript

_, MEETING_SOURCE_TYPE = SOURCE_TYPES
# The number of words that fills SUMMARY_INPUT_TOKENS with whole passages exactly: the first
# passage, then one per advance of the chunker's step.
WHOLE_PASSAGES = SUMMARY_INPUT_TOKENS // CHUNK_SIZE
EXACTLY_FULL = CHUNK_SIZE + (WHOLE_PASSAGES - 1) * (CHUNK_SIZE - CHUNK_OVERLAP)


# --- verify_draft: set membership -------------------------------------------------------------


def test_a_draft_citing_only_passages_that_were_sent_is_unchanged():
    original = draft(
        narrative=[element("One.", 1), element("Two.", 2, 3)],
        decisions=[element("A decision.", 3)],
        highlights=[element("A highlight.", 1)],
        action_items=[action("Do it", owner="Alex", due="next Friday", passages=(2,))],
    )

    verified = verify_draft(original, passage_count=3)

    assert verified.narrative == original.narrative
    assert verified.decisions == original.decisions
    assert verified.highlights == original.highlights
    assert verified.action_items == original.action_items
    assert verified.dropped == 0
    assert verified.referenced == [1, 2, 3]


@pytest.mark.parametrize("fabricated", [0, 4, 5, 41, 9999, -1], ids=lambda number: f"P{number}")
def test_a_reference_outside_the_passages_sent_is_removed(fabricated):
    """Three passages were sent. P4 was never shown to the model, so nothing may cite it."""
    verified = verify_draft(draft(narrative=[element("One.", 2, fabricated, 1)]), passage_count=3)

    assert verified.narrative == (SummaryElement(text="One.", passages=(2, 1)),)  # the rest, in the reply's order
    assert verified.dropped == 0
    assert fabricated not in verified.referenced


def test_the_boundary_is_the_number_of_passages_sent_exactly():
    verified = verify_draft(
        draft(narrative=[element("First.", 1), element("Last.", 7), element("One past.", 8), element("Zero.", 0)]),
        passage_count=7,
    )

    assert [e.text for e in verified.narrative] == ["First.", "Last."]
    assert verified.dropped == 2


def test_an_element_left_with_no_reference_is_dropped_and_counted_in_every_part():
    original = draft(
        narrative=[element("Kept sentence.", 1), element("Fabricated sentence.", 9)],
        decisions=[element("Fabricated decision.", 8), element("Kept decision.", 2)],
        highlights=[element("Fabricated highlight.", 7, 6)],
        action_items=[action("Fabricated task", passages=(5,)), action("Kept task", passages=(2, 9))],
    )

    verified = verify_draft(original, passage_count=2)

    assert [e.text for e in verified.narrative] == ["Kept sentence."]
    assert [e.text for e in verified.decisions] == ["Kept decision."]
    assert verified.highlights == ()
    assert [a.description for a in verified.action_items] == ["Kept task"]
    assert verified.action_items[0].passages == (2,)
    assert verified.dropped == 4  # one sentence, one decision, one highlight, one action item


def test_referenced_is_every_number_a_kept_element_kept_ascending_and_once():
    verified = verify_draft(
        draft(
            narrative=[element("One.", 5, 2), element("Dropped.", 30)],
            decisions=[element("Two.", 2, 31)],
            highlights=[element("Three.", 7)],
            action_items=[action("Four", passages=(1, 5))],
        ),
        passage_count=10,
    )

    assert verified.referenced == [1, 2, 5, 7]
    assert 30 not in verified.referenced and 31 not in verified.referenced


def test_an_action_item_keeps_its_words_and_loses_only_the_reference():
    item = ExtractedActionItem(description="Chase the quote", owner="the facilities team", due="before the move",
                               passages=(3, 12))

    verified = verify_draft(draft(action_items=[item]), passage_count=4)

    assert verified.action_items == (
        ExtractedActionItem(description="Chase the quote", owner="the facilities team", due="before the move",
                            passages=(3,)),
    )


def test_with_no_passages_sent_nothing_is_verified():
    verified = verify_draft(draft(narrative=[element("One.", 1)], action_items=[action("Do it")]), passage_count=0)

    assert (verified.narrative, verified.action_items, verified.referenced) == ((), (), [])
    assert verified.dropped == 2


def test_verification_does_not_judge_whether_the_passage_supports_the_sentence():
    """Invariant 5's conceded limitation, pinned: membership is all that is checked. A sentence
    citing a passage that was sent survives whatever it says; nothing here reads a passage's text."""
    verified = verify_draft(draft(narrative=[element("The moon is made of cheese.", 1)]), passage_count=1)

    assert [e.text for e in verified.narrative] == ["The moon is made of cheese."]
    # A count is the only thing it is given besides the draft: no passage text reaches it.
    assert list(inspect.signature(verify_draft).parameters) == ["draft", "passage_count"]


def test_a_reply_that_copied_the_worked_examples_labels_loses_every_element():
    """The example's labels start above the most passages any request carries, so a model that
    parroted them cites nothing real, whatever the transcript's length. A copied "P1" would have
    silently cited the real first passage."""
    parsed = parse_summary(EXAMPLE_REPLY)
    copied = MeetingSummaryDraft(
        narrative=parsed.narrative, decisions=parsed.decisions, highlights=parsed.highlights,
        action_items=parsed.action_items, model="stub-chat",
    )

    for passage_count in (1, 2, MAXIMUM_PASSAGES):
        verified = verify_draft(copied, passage_count=passage_count)
        assert verified.narrative == () and verified.decisions == () and verified.highlights == ()
        assert verified.action_items == ()
        assert verified.dropped == 7  # two sentences, one decision, two highlights, two action items


# --- A draft with no verified narrative fails the run, and nothing of it is stored --------------


@pytest.mark.django_db
def test_a_narrative_that_cites_nothing_sent_ends_the_run_unavailable_under_its_own_reason(
    stub_ai_service, django_capture_on_commit_callbacks, caplog
):
    """The reply conformed, a decision and an action item even verified, and still nothing is
    kept: a summary with no narrative is not a summary, and a fragment is not shown (invariant 6)."""
    stub_ai_service.summary = draft(
        narrative=[element("An invented sentence about Carlton.", 41), element("Another about Carlton.", 42)],
        decisions=[element("A decision that did verify.", 1)],
        action_items=[action("A task that did verify", owner="Alex", due="tomorrow", passages=(1,))],
    )

    with caplog.at_level(logging.WARNING, logger="apps.meetings.summaries"):
        meeting = summarised(django_capture_on_commit_callbacks)

    [summary] = MeetingSummary.objects.filter(meeting=meeting)
    assert summary.status == SUMMARY_UNAVAILABLE
    assert summary.failure_reason == SUMMARY_FAILED_NO_VERIFIED_NARRATIVE == "no_verified_narrative"
    assert summary.queued_for_retry is True
    assert list(retry_queue()) == [summary]
    # Nothing was written: no text, no elements, no passages, no provenance.
    assert summary.summary_text == ""
    assert (summary.narrative, summary.decisions, summary.highlights, summary.passages) == ([], [], [], {})
    assert (summary.model, summary.generated_at, summary.action_items_extracted) == ("", None, None)
    assert not ActionItem.objects.filter(meeting=meeting).exists()
    chunks = ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id)
    assert chunks.exists() and not chunks.filter(ai_generated=True).exists()  # the transcript's, and no other
    assert not any("Carlton" in chunk.chunk_text for chunk in chunks)
    assert len(stub_ai_service.summarise_calls) == 1  # one call: verification is not a retry
    # The count of dropped elements is logged for the operator; the dropped words are not.
    dropped = [r.getMessage() for r in caplog.records if "dropped" in r.getMessage()]
    assert len(dropped) == 1 and "2 element(s) dropped" in dropped[0]
    assert all("Carlton" not in record.getMessage() for record in caplog.records)


@pytest.mark.django_db
def test_a_summary_keeps_its_verified_sentences_and_stores_no_trace_of_the_others(
    stub_ai_service, django_capture_on_commit_callbacks
):
    stub_ai_service.summary = draft(
        narrative=[element("The team reviewed the budget.", 1), element("Carlton will close in March.", 9)],
        decisions=[element("Carlton staff are to be told on Monday.", 12)],
        highlights=[element("Travel was twice its budget.", 1, 7)],
        action_items=[
            action("Tell the Carlton staff", owner="Alex", due="Monday", passages=(12,)),
            action("Reconcile the cards", passages=(1, 30)),
        ],
    )

    meeting = summarised(django_capture_on_commit_callbacks)

    [summary] = MeetingSummary.objects.filter(meeting=meeting)
    assert summary.status == SUMMARY_READY
    assert summary.summary_text == "The team reviewed the budget."
    assert summary.narrative == [{"text": "The team reviewed the budget.", "passages": [1]}]
    assert summary.decisions == []
    assert summary.highlights == [{"text": "Travel was twice its budget.", "passages": [1]}]
    assert list(summary.passages) == ["1"]  # only what a kept element cites
    # The action item citing nothing sent is not stored, and the count is of what was stored.
    [item] = ActionItem.objects.filter(meeting=meeting)
    assert (item.description, item.passages) == ("Reconcile the cards", [1])
    assert summary.action_items_extracted == 1
    # The dropped words are nowhere: not on the row, not on an item, not in the index.
    stored = " ".join(
        [summary.summary_text, str(summary.narrative), str(summary.decisions), str(summary.highlights),
         str(summary.passages), item.description, item.owner_name, item.due_text]
        + list(ContentChunk.objects.filter(source_id=meeting.id, ai_generated=True).values_list("chunk_text", flat=True))
    )
    assert "Carlton" not in stored


@pytest.mark.django_db
def test_every_stored_reference_names_a_passage_whose_text_is_stored_with_the_summary(
    stub_ai_service, django_capture_on_commit_callbacks
):
    """UC-04: "Every element of the summary carries a reference to the passage of the transcript
    it was drawn from." Read back from the row: each number resolves to that passage's own text."""
    text = transcript(1300)  # three passages
    passages = [chunk.text for chunk in split_into_overlapping_chunks(text)]
    assert len(passages) == 3
    stub_ai_service.summary = draft(
        narrative=[element("One.", 3), element("Two.", 1)],
        decisions=[element("Three.", 3, 44)],
        action_items=[action("Four", passages=(2,))],
    )

    meeting = summarised(django_capture_on_commit_callbacks, text=text)

    summary = MeetingSummary.objects.get(meeting=meeting)
    assert summary.passages == {"1": passages[0], "2": passages[1], "3": passages[2]}
    cited = [n for part in (summary.narrative, summary.decisions, summary.highlights) for e in part for n in e["passages"]]
    cited += [n for item in ActionItem.objects.filter(meeting=meeting) for n in item.passages]
    assert cited and all(str(number) in summary.passages for number in cited)
    assert 44 not in cited


# --- summary_input: what the model reads ----------------------------------------------------------


def test_a_short_transcript_is_one_passage_and_is_not_truncated():
    text = transcript(240)

    source = summary_input(text)

    assert isinstance(source, SummaryInput)
    assert source.passages == [text]
    assert (source.total, source.truncated) == (1, False)


def test_the_passages_are_the_chunkers_own_whole_and_in_order():
    """Passage n is the text of the transcript's chunk n - 1, so a reference to it names the
    passage FR-09 indexed. Nothing is cut, joined or re-split on the way."""
    text = transcript(1300)

    source = summary_input(text)

    assert source.passages == [chunk.text for chunk in split_into_overlapping_chunks(text)]
    assert (len(source.passages), source.total, source.truncated) == (3, 3, False)


@pytest.mark.django_db
def test_the_passages_are_the_text_of_the_meetings_own_indexed_chunks(django_capture_on_commit_callbacks, stub_ai_service):
    meeting = summarised(django_capture_on_commit_callbacks, text=transcript(1300))

    indexed = list(
        ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id, ai_generated=False)
        .order_by("chunk_index")
        .values_list("chunk_text", flat=True)
    )
    assert summary_input(meeting.transcript_text).passages == indexed
    [(title, sent)] = stub_ai_service.summarise_calls
    assert (title, sent) == (meeting.title, indexed)  # and they are what the provider was sent


def test_a_transcript_that_fills_the_ceiling_exactly_is_sent_whole():
    text = transcript(EXACTLY_FULL)

    source = summary_input(text)

    assert (len(source.passages), source.total, source.truncated) == (WHOLE_PASSAGES, WHOLE_PASSAGES, False)
    assert sum(length_in_tokens(passage) for passage in source.passages) == SUMMARY_INPUT_TOKENS


def test_one_word_more_than_the_ceiling_holds_leaves_the_last_passage_out_and_says_so():
    """Whole passages only: the passage that does not fit is left out, not cut, and the input is
    recorded as truncated with the total, so the panel can say how much the summary covers."""
    text = transcript(EXACTLY_FULL + 1)

    source = summary_input(text)

    assert (len(source.passages), source.total, source.truncated) == (WHOLE_PASSAGES, WHOLE_PASSAGES + 1, True)
    assert source.passages == [chunk.text for chunk in split_into_overlapping_chunks(text)][:WHOLE_PASSAGES]


@pytest.mark.parametrize("words", [EXACTLY_FULL - 1, EXACTLY_FULL, EXACTLY_FULL + 1, SUMMARY_INPUT_TOKENS - 1,
                                   SUMMARY_INPUT_TOKENS, SUMMARY_INPUT_TOKENS + 1, 3 * SUMMARY_INPUT_TOKENS])
def test_a_long_transcript_never_exceeds_the_ceiling_or_the_prompts_bound(words):
    """Three things at once, at the sizes around the ceiling and well past it: every passage sent
    is a whole chunk, they fit SUMMARY_INPUT_TOKENS together, and there are never more than the
    prompt builder accepts, so the caller's cut is what keeps ``build_summary_user_prompt`` from
    raising and the worked example's labels above every real one."""
    text = transcript(words)
    chunks = [chunk.text for chunk in split_into_overlapping_chunks(text)]

    source = summary_input(text)

    assert source.passages == chunks[: len(source.passages)]
    assert source.total == len(chunks)
    assert source.truncated == (len(source.passages) < len(chunks))
    assert sum(length_in_tokens(passage) for passage in source.passages) <= SUMMARY_INPUT_TOKENS
    assert 1 <= len(source.passages) <= MAXIMUM_PASSAGES
    assert f"[P{len(source.passages)}]" in build_summary_user_prompt("Any title", source.passages)
    if source.truncated:
        # The next passage really would not have fitted: nothing that fits is left out.
        assert (
            sum(length_in_tokens(passage) for passage in source.passages)
            + length_in_tokens(chunks[len(source.passages)])
            > SUMMARY_INPUT_TOKENS
        )


def test_the_first_passage_is_always_sent_even_where_it_alone_is_over_the_ceiling(monkeypatch):
    """FR-16 sends "a single structured request": there is always something in it. With the
    ceiling lowered under one passage, the first is still sent whole, and only the first."""
    monkeypatch.setattr(summaries, "SUMMARY_INPUT_TOKENS", 100)

    one = summary_input(transcript(240))
    assert (len(one.passages), one.total, one.truncated) == (1, 1, False)
    assert length_in_tokens(one.passages[0]) == 240 > 100

    two = summary_input(transcript(CHUNK_SIZE + 100))
    assert (len(two.passages), two.total, two.truncated) == (1, 2, True)
    assert length_in_tokens(two.passages[0]) == CHUNK_SIZE


@pytest.mark.parametrize("text", ["", "   \n\t "], ids=["empty", "whitespace"])
def test_no_text_is_no_passages_and_nothing_is_manufactured(text):
    source = summary_input(text)

    assert (source.passages, source.total, source.truncated) == ([], 0, False)


@pytest.mark.django_db
def test_a_truncated_input_is_recorded_on_the_summary_and_only_the_sent_passages_can_be_cited(
    stub_ai_service, django_capture_on_commit_callbacks
):
    """A transcript longer than one request carries: the run records how much it read, and a
    reference to a passage past the cut is a reference to something the model was not shown."""
    text = transcript(EXACTLY_FULL + CHUNK_SIZE)
    total = len(split_into_overlapping_chunks(text))
    assert total > WHOLE_PASSAGES
    stub_ai_service.summary = draft(
        narrative=[element("Read.", WHOLE_PASSAGES), element("Not read.", WHOLE_PASSAGES + 1)],
    )

    meeting = summarised(django_capture_on_commit_callbacks, text=text)

    summary = MeetingSummary.objects.get(meeting=meeting)
    assert summary.status == SUMMARY_READY
    assert (summary.input_truncated, summary.passages_sent, summary.passages_total) == (True, WHOLE_PASSAGES, total)
    assert summary.narrative == [{"text": "Read.", "passages": [WHOLE_PASSAGES]}]
    [(_, sent)] = stub_ai_service.summarise_calls
    assert len(sent) == WHOLE_PASSAGES
