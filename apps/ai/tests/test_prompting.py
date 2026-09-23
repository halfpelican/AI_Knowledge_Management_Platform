"""The grounded-generation prompt (apps/ai/prompting.py).

Two things are worth asserting about a prompt in a test suite. First, that it carries the
retrieved passages and their identifiers and nothing else — that is FR-12's grounding
constraint, and anything extra in the prompt is something the model may answer from.
Second, that the worked example's identifiers do not look like real ones, which is the
one measured lesson from Stage 4 item 0: example identifiers get cited. The first baseline
run fabricated an identifier in 23.8% of statements and 9 of the 10 were the example's own
IDs; UUID-shaped examples took it to 2.4%.

No provider, no network, no database.
"""

import re
from pathlib import Path

import pytest

import apps.ai.prompting as prompting
from apps.ai.base import Passage
from apps.ai.prompting import SYSTEM_PROMPT, build_generation_messages, build_user_prompt


def flat(text: str) -> str:
    """Whitespace collapsed to single spaces.

    The prompt and the source are hard-wrapped, so a sentence worth asserting on is
    usually split across a line break and an indent. Comparisons go through this so a test
    asserts on the wording rather than on where the line happened to end.
    """
    return " ".join(text.split())


FLAT_PROMPT = flat(SYSTEM_PROMPT)
# Comment markers stripped as well as line breaks: the lesson below is a hard-wrapped
# block comment, so every continuation line starts with a "#" that is not part of a
# sentence.
PROMPTING_SOURCE = flat(Path(prompting.__file__).read_text(encoding="utf-8").replace("#", ""))

QUESTION = "How much annual leave do I get?"
PASSAGES = [
    Passage(chunk_id="11111111-1111-4111-8111-111111111111", text="Twenty days per year."),
    Passage(chunk_id="22222222-2222-4222-8222-222222222222", text="Carry over up to five."),
]

UUID_SHAPE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


# --- The messages -----------------------------------------------------------------------


def test_the_messages_are_the_system_prompt_and_one_user_turn():
    messages = build_generation_messages(QUESTION, PASSAGES)

    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert messages[1]["content"] == build_user_prompt(QUESTION, PASSAGES)


def test_every_passage_is_labelled_with_its_chunk_identifier():
    """The label is what citation verification checks returned identifiers against."""
    user = build_user_prompt(QUESTION, PASSAGES)

    for passage in PASSAGES:
        assert f"[chunk_id: {passage.chunk_id}]" in user
        assert passage.text in user


def test_the_prompt_carries_the_question_and_the_passages_and_nothing_else():
    """FR-12: the model answers solely from the supplied passages.

    Asserted as an absence, which is the only way to assert it: no history, no titles, no
    metadata, no invitation to use general knowledge. The passage texts and the question
    account for everything in the prompt that is not a fixed instruction.
    """
    user = build_user_prompt(QUESTION, PASSAGES)
    remainder = user
    for passage in PASSAGES:
        remainder = remainder.replace(passage.text, "").replace(passage.chunk_id, "")
    remainder = remainder.replace(QUESTION, "")

    # What is left is the three fixed labels and punctuation, and nothing that could be
    # mistaken for content.
    assert "chunk_id" in remainder
    assert "Passages:" in remainder
    assert "Question:" in remainder
    assert "Reply with the JSON object only" in remainder
    for stray in ("uploaded_by", "title:", "conversation", "previously", "role"):
        assert stray not in remainder


def test_the_instruction_to_use_only_the_supplied_identifiers_is_in_both_halves():
    """Rule 4 in the system prompt, restated in the user turn where the IDs actually are."""
    assert "Use only the chunk_id values supplied in this conversation" in FLAT_PROMPT
    assert "using only the chunk_id values above" in build_user_prompt(QUESTION, PASSAGES)


def test_an_empty_statement_list_is_asked_for_explicitly():
    """Rule 7: the model is told that an empty array is a correct answer.

    Without this a small model invents something rather than returning nothing, and the
    no-answer paths stop being reachable from the model's side at all.
    """
    assert '{"statements": []}' in SYSTEM_PROMPT
    assert "An empty array is a correct and expected answer" in SYSTEM_PROMPT


def test_passage_text_is_stripped_but_not_otherwise_altered():
    passage = Passage(chunk_id="33333333-3333-4333-8333-333333333333", text="  Padded text.\n\n")
    user = build_user_prompt(QUESTION, [passage])
    assert "[chunk_id: 33333333-3333-4333-8333-333333333333]\nPadded text." in user


def test_no_passages_produces_no_passage_block():
    """The providers refuse an empty passage list before reaching here; this records that
    the builder itself does not invent a placeholder passage if it ever is called with
    one."""
    user = build_user_prompt(QUESTION, [])
    assert "chunk_id" in user  # the closing instruction still names the field
    assert "[chunk_id:" not in user


# --- The worked example: the 23.8% -> 2.4% lesson ---------------------------------------


def test_the_worked_examples_identifiers_are_uuid_shaped():
    """Real chunk identifiers are UUIDs, so the example's must be too.

    The point is not that UUIDs are better prompt decoration. It is that an example
    identifier WILL be cited by a small model, and a UUID-shaped one is then caught by
    verification as a fabrication instead of colliding with a real identifier or teaching
    the model a shape to invent in. Measured: 23.8% fabricated identifiers before, 2.4%
    after, with no other change.
    """
    example_ids = UUID_SHAPE.findall(SYSTEM_PROMPT)
    assert len(example_ids) >= 2, "the worked example should show more than one passage"


def test_the_worked_example_holds_no_short_synthetic_identifier():
    """The two IDs that were fabricated 9 times out of 10 were `c_4471` and `c_8802`.

    Any identifier of that shape in the prompt is an invitation. This asserts the shape
    is absent rather than asserting those two strings are, so a new `c_1234` or `chunk-7`
    fails here too.
    """
    assert not re.search(r"\b(c|chunk|id)[_-]?\d{1,6}\b", SYSTEM_PROMPT, re.IGNORECASE)


def test_the_example_identifiers_are_declared_to_be_examples():
    """The declaration is half the fix: the model is told they appear nowhere real."""
    assert "EXAMPLE values and appear nowhere in the" in SYSTEM_PROMPT
    assert "never reuse them" in SYSTEM_PROMPT


def test_the_lesson_is_recorded_next_to_the_example_it_applies_to():
    """The measured reason lives in the source, not only in docs/flm-baseline.md.

    A future editor shortening the worked example will read apps/ai/prompting.py and not
    the baseline document. Asserted because a comment is the only place this can live —
    inside the string it would be prompt text the model reads.
    """
    assert "23.8%" in PROMPTING_SOURCE and "2.4%" in PROMPTING_SOURCE
    assert "Do not put a plausible chunk ID in a prompt" in PROMPTING_SOURCE
    # And it is a comment, so it is not sent to the model.
    assert "23.8%" not in SYSTEM_PROMPT


@pytest.mark.parametrize("rule", ["1.", "2.", "3.", "4.", "5.", "6.", "7."])
def test_all_seven_rules_survive_an_edit(rule):
    """docs/ai-provider.md section 5 step 1: the strict instruction set, all of it.

    Numbered so that dropping one is a failure rather than a diff nobody reads. The
    conformance rate in docs/flm-baseline.md was measured with all seven present.
    """
    assert f"\n{rule}" in SYSTEM_PROMPT
