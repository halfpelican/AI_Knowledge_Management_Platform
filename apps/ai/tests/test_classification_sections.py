"""A document too long for one request: its sections, their prompt, and the whole flow (FR-10, D-139).

FR-10: "Documents exceeding the model's context limit are summarised in sections and
consolidated, rather than being truncated and summarised from a fragment without the user being
told." D-139 reads the limit as CLASSIFICATION_INPUT_TOKENS. Four things are held here:

- ``summary_sections``: the cut, at its boundary sizes, and the flag that says text was left over;
- the section prompt and the two user turns D-139 added, a section's and the final request's;
- ``run_section_summary_attempts``: one section's attempts, MAXIMUM_CLASSIFY_ATTEMPTS of its own;
- ``classify_and_summarise``: how many provider calls each path makes, in what order, carrying
  what, and that a failure anywhere returns nothing.

Every count below is an equality on calls a scripted ``call_once`` recorded, and the script holds
exactly the replies the path should use: one call more raises IndexError, so a path that makes
too many calls fails as loudly as one that makes too few. The two providers are driven through
this same flow in test_classification_providers.py.

No provider, no network, no database.
"""

from __future__ import annotations

import json
import logging
import re

import pytest

from apps.ai import attempt_log
from apps.ai.base import DocumentClassification, ProviderRefused, ProviderUnavailable, TagScheme
from apps.ai.classification import (
    CLASSIFICATION_SYSTEM_PROMPT,
    CONSOLIDATION_INSTRUCTION,
    EXAMPLE_SECTION_REPLY,
    EXAMPLE_TEXT,
    EXAMPLE_TITLE,
    GROUNDING_SENTENCE,
    REPLY_INSTRUCTION,
    SECTION_SUMMARY_SYSTEM_PROMPT,
    SECTIONED_NOTICE,
    SectionSummary,
    build_classification_user_prompt,
    build_section_summary_user_prompt,
    chat_messages,
    classification_input,
    classify_and_summarise,
    parse_section_summary,
    run_section_summary_attempts,
    summary_sections,
)
from apps.ai.prompting import SYSTEM_PROMPT
from apps.core.constants import (
    CLASSIFICATION_INPUT_TOKENS,
    DOCUMENT_TYPES,
    MAXIMUM_CLASSIFY_ATTEMPTS,
    MAXIMUM_KEY_POINT_CHARACTERS,
    MAXIMUM_KEY_POINTS,
    MAXIMUM_SUMMARY_CHARACTERS,
    MAXIMUM_SUMMARY_SECTIONS,
)

SECTION = CLASSIFICATION_INPUT_TOKENS  # one section's size, in whitespace tokens
CEILING = MAXIMUM_SUMMARY_SECTIONS * SECTION  # the most tokens that are summarised

SCHEME = TagScheme(
    doc_types=DOCUMENT_TYPES,
    departments=("Finance", "Human Resources"),
    tags={"Project": ("atlas",), "Process": ("onboarding",), "Topic": ("safety",)},
)
TITLE = "Operations handbook"
LABEL = "FLM at http://flm.test/v1"
MODEL = "gemma3:4b"
MAX_TOKENS = 1234  # a value no constant has, so a line that shows it got it from the caller


def words(count: int) -> list[str]:
    """``count`` distinct tokens, w0, w1, ...: each names its own position in the text."""
    return [f"w{n}" for n in range(count)]


def text_of(count: int) -> str:
    return " ".join(words(count))


def flat(text: str) -> str:
    return " ".join(text.split())


# --- summary_sections: the cut --------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\t \n"], ids=["empty", "spaces", "whitespace"])
def test_an_empty_text_has_no_sections_and_nothing_left_over(text):
    assert summary_sections(text) == ((), False)


def test_a_text_shorter_than_one_section_is_one_section():
    assert summary_sections("one two three") == (("one two three",), False)
    text = text_of(SECTION - 1)
    assert summary_sections(text) == ((text,), False)


def test_a_text_of_exactly_one_section_is_one_section():
    text = text_of(SECTION)
    assert summary_sections(text) == ((text,), False)


def test_one_section_plus_one_token_is_two_sections_and_the_second_holds_the_one_token():
    tokens = words(SECTION + 1)
    sections, left_over = summary_sections(" ".join(tokens))

    assert len(sections) == 2
    assert sections[0].split() == tokens[:SECTION]
    assert sections[1] == tokens[SECTION]  # the one token, and the cut ends there
    assert left_over is False


def test_the_sections_are_the_text_in_order_with_no_overlap_and_no_gap():
    tokens = words(3 * SECTION + 7)
    sections, left_over = summary_sections(" ".join(tokens))

    assert [len(section.split()) for section in sections] == [SECTION, SECTION, SECTION, 7]
    assert " ".join(sections).split() == tokens  # every token once, in order
    assert left_over is False


def test_the_first_section_is_the_opening_classification_reads():
    """The final request carries "the opening exactly as classification reads it"; section 1 is
    that same text, so no token is summarised that classification did not see, or the reverse."""
    for count in (1, SECTION - 1, SECTION, SECTION + 1, 2 * SECTION + 5, CEILING + 9):
        text = text_of(count)
        assert summary_sections(text)[0][0] == classification_input(text)[0], count


def test_whitespace_is_collapsed_exactly_as_the_input_cut_collapses_it():
    assert summary_sections("  one\n\ntwo\tthree   four  ") == (("one two three four",), False)


def test_exactly_the_ceiling_is_every_section_full_and_nothing_left_over():
    """The boundary: a text of exactly MAXIMUM_SUMMARY_SECTIONS sections is summarised whole, so
    it is NOT reported truncated."""
    tokens = words(CEILING)
    sections, left_over = summary_sections(" ".join(tokens))

    assert len(sections) == MAXIMUM_SUMMARY_SECTIONS
    assert all(len(section.split()) == SECTION for section in sections)
    assert sections[-1].split()[-1] == tokens[-1]  # the last token is in the last section
    assert left_over is False


def test_one_token_past_the_ceiling_is_left_over_and_is_in_no_section():
    tokens = words(CEILING + 1)
    sections, left_over = summary_sections(" ".join(tokens))

    assert len(sections) == MAXIMUM_SUMMARY_SECTIONS  # never a ninth
    assert left_over is True
    assert tokens[-1] not in " ".join(sections).split()
    assert " ".join(sections).split() == tokens[:CEILING]


def test_a_text_many_times_the_ceiling_still_has_only_the_maximum_sections():
    sections, left_over = summary_sections(text_of(5 * CEILING + 3))
    assert len(sections) == MAXIMUM_SUMMARY_SECTIONS and left_over is True


@pytest.mark.parametrize("count", [0, 1, SECTION - 1, SECTION, SECTION + 1, 2 * SECTION, CEILING, CEILING + 1])
def test_more_than_one_section_is_exactly_what_input_truncated_means(count):
    """``classify_and_summarise`` branches on ``input_truncated`` and sends ``summary_sections``'
    sections, so the two must agree at every size: cut means two sections or more."""
    text = text_of(count)
    sections, _ = summary_sections(text)
    assert (len(sections) > 1) is classification_input(text)[1]


def test_the_section_ceiling_is_the_contracts():
    """D-139's value, marked tune. A change is a decision, so this fails until it is recorded."""
    assert MAXIMUM_SUMMARY_SECTIONS == 8
    assert CEILING == 12_000


# --- The section prompt ----------------------------------------------------------------------

FLAT_SECTION_PROMPT = flat(SECTION_SUMMARY_SYSTEM_PROMPT)


def test_the_grounding_sentence_is_in_the_section_prompt():
    """FR-10's grounding clause, in the section prompt as in the classification prompt: the same
    sentence, once, as a rule."""
    assert SECTION_SUMMARY_SYSTEM_PROMPT.count(GROUNDING_SENTENCE) == 1
    assert f"\n5. {GROUNDING_SENTENCE}:" in SECTION_SUMMARY_SYSTEM_PROMPT
    assert GROUNDING_SENTENCE in CLASSIFICATION_SYSTEM_PROMPT  # the same sentence, not a second wording
    assert "Add no fact, name, number or date that it does not contain" in FLAT_SECTION_PROMPT


def test_the_section_rules_say_json_only_two_keys_and_the_bounds_the_parser_holds():
    assert "Reply with one JSON object and nothing else" in FLAT_SECTION_PROMPT
    assert 'The object has exactly two keys: "summary" and "key_points".' in FLAT_SECTION_PROMPT
    assert '"summary" is one string, never an array or an object' in FLAT_SECTION_PROMPT
    assert f"at most {MAXIMUM_SUMMARY_CHARACTERS} characters in all" in FLAT_SECTION_PROMPT
    assert f'"key_points" is an array of 1 to {MAXIMUM_KEY_POINTS} strings' in FLAT_SECTION_PROMPT
    assert f"never more than {MAXIMUM_KEY_POINTS}" in FLAT_SECTION_PROMPT
    assert f"of at most {MAXIMUM_KEY_POINT_CHARACTERS} characters" in FLAT_SECTION_PROMPT


def test_the_section_rules_say_a_cut_sentence_is_not_to_be_finished():
    """A section is cut by length, so it can stop mid-sentence: the model is told not to complete
    it or to guess the rest, which would be content from outside the text."""
    assert "may begin or end in the middle of a sentence" in FLAT_SECTION_PROMPT
    assert "Never complete a sentence that is cut off" in FLAT_SECTION_PROMPT
    assert "never guess what the rest of the document says" in FLAT_SECTION_PROMPT


@pytest.mark.parametrize("rule", ["1.", "2.", "3.", "4.", "5.", "6."])
def test_all_six_section_rules_survive_an_edit(rule):
    assert f"\n{rule} " in SECTION_SUMMARY_SYSTEM_PROMPT
    assert "\n7." not in SECTION_SUMMARY_SYSTEM_PROMPT


def test_the_section_prompt_classifies_nothing():
    """A section is summarised and not classified: the prompt names no type, department or tag,
    shows no scheme, and asks for no confidence."""
    for word in ("doc_type", "department", "tags", "confidence", "Document types", "Departments (choose one)",
                 *DOCUMENT_TYPES):
        assert word not in SECTION_SUMMARY_SYSTEM_PROMPT, word
    assert SECTION_SUMMARY_SYSTEM_PROMPT != CLASSIFICATION_SYSTEM_PROMPT
    assert SECTION_SUMMARY_SYSTEM_PROMPT != SYSTEM_PROMPT


def test_the_section_prompt_has_one_worked_example_and_ends_with_its_reply():
    assert SECTION_SUMMARY_SYSTEM_PROMPT.count("Your reply:") == 1
    assert SECTION_SUMMARY_SYSTEM_PROMPT.rstrip().endswith(EXAMPLE_SECTION_REPLY)
    assert "Its subject is an EXAMPLE and appears in no real document" in FLAT_SECTION_PROMPT
    assert "never summarise a real section by its resemblance to the example" in FLAT_SECTION_PROMPT


def test_the_section_examples_reply_conforms_to_the_schema_it_teaches():
    parsed = parse_section_summary(EXAMPLE_SECTION_REPLY)
    assert isinstance(parsed, SectionSummary)
    assert parsed.summary and 1 <= len(parsed.key_points) <= MAXIMUM_KEY_POINTS


def test_the_section_example_is_in_the_same_shape_as_a_real_section_turn():
    """The example's block is built by the code that builds a real section's, so the two cannot
    drift; the closing instruction is the user turn's and is not in the system prompt."""
    real = build_section_summary_user_prompt(EXAMPLE_TITLE, EXAMPLE_TEXT, 1, 2)
    block = real[: real.rindex(REPLY_INSTRUCTION)].rstrip()
    assert block in SECTION_SUMMARY_SYSTEM_PROMPT
    assert REPLY_INSTRUCTION not in SECTION_SUMMARY_SYSTEM_PROMPT


def test_the_section_prompt_carries_no_identifier_of_any_shape():
    assert not re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-", SECTION_SUMMARY_SYSTEM_PROMPT)
    assert not re.search(r"(c|chunk|id)[_-]?\d{1,6}", SECTION_SUMMARY_SYSTEM_PROMPT, re.IGNORECASE)
    assert "chunk_id" not in SECTION_SUMMARY_SYSTEM_PROMPT


# --- A section's user turn -------------------------------------------------------------------


def test_a_sections_user_turn_is_the_title_its_number_its_text_and_the_instruction():
    turn = build_section_summary_user_prompt("  Operations handbook\n", "First words of the section.", 2, 3)
    assert turn == (
        "Title: Operations handbook\n"
        "Section 2 of 3:\n"
        "First words of the section.\n"
        "\n"
        f"{REPLY_INSTRUCTION}"
    )


def test_a_sections_user_turn_cuts_the_section_itself():
    """Cut at the boundary as well as by ``summary_sections``, so no caller can send more."""
    tokens = words(SECTION + 1)
    turn = build_section_summary_user_prompt(TITLE, " ".join(tokens), 1, 2)
    assert f" {tokens[SECTION - 1]}\n" in turn
    assert tokens[SECTION] not in turn.split()


def test_a_sections_user_turn_carries_no_scheme_and_nothing_from_the_example():
    turn = build_section_summary_user_prompt(TITLE, "Some text.", 1, 2)
    for word in ("Document types", "Departments", "tags:", *SCHEME.departments, EXAMPLE_TITLE, "lamp", "wick"):
        assert word not in turn, word


# --- The final request's user turn -----------------------------------------------------------

SUMMARIES = (
    SectionSummary(summary="The first part covers purchasing.", key_points=("Orders need a number.", "Quotes over a limit.")),
    SectionSummary(summary="The second part covers travel.", key_points=("Book through the agent.",)),
)


def test_the_final_turn_is_the_ordinary_turn_then_the_section_summaries_then_the_instructions():
    """Written out whole: the scheme, the title and the opening exactly as a short document's
    turn has them, then the notice, each section under its number with its key points, the
    consolidation instruction, and the one closing instruction last."""
    turn = build_classification_user_prompt(TITLE, "The opening text.", SCHEME, section_summaries=SUMMARIES)

    assert turn == (
        "Document types (choose one): Policy; Procedure; Report; Meeting Paper\n"
        "Departments (choose one): Finance; Human Resources\n"
        "Project tags: atlas\n"
        "Process tags: onboarding\n"
        "Topic tags: safety\n"
        "\n"
        "Title: Operations handbook\n"
        "Text:\n"
        "The opening text.\n"
        "\n"
        f"{SECTIONED_NOTICE}\n"
        "\n"
        "Section 1 of 2\n"
        "Summary: The first part covers purchasing.\n"
        "Key points:\n"
        "- Orders need a number.\n"
        "- Quotes over a limit.\n"
        "\n"
        "Section 2 of 2\n"
        "Summary: The second part covers travel.\n"
        "Key points:\n"
        "- Book through the agent.\n"
        "\n"
        f"{CONSOLIDATION_INSTRUCTION}\n"
        "\n"
        f"{REPLY_INSTRUCTION}"
    )


def test_the_final_turn_begins_exactly_as_a_short_documents_turn_does():
    """Everything up to the closing instruction of the ordinary turn is the start of the final
    one, so the type, the department and the tags are chosen from the same words."""
    ordinary = build_classification_user_prompt(TITLE, "The opening text.", SCHEME)
    final = build_classification_user_prompt(TITLE, "The opening text.", SCHEME, section_summaries=SUMMARIES)
    shared = ordinary[: ordinary.rindex(REPLY_INSTRUCTION)]
    assert final.startswith(shared)
    assert final.endswith(REPLY_INSTRUCTION) and final.count(REPLY_INSTRUCTION) == 1


def test_the_final_turn_says_where_the_classification_and_the_summary_each_come_from():
    assert "only the opening of a longer document" in SECTIONED_NOTICE
    assert "the section summaries follow in order" in SECTIONED_NOTICE
    assert 'Choose "doc_type", "department" and "tags" from the title and the text above' in CONSOLIDATION_INSTRUCTION
    assert 'Write "summary" and "key_points" for the document as a whole from the section summaries' in CONSOLIDATION_INSTRUCTION


def test_the_final_turn_still_cuts_its_text_to_the_opening():
    tokens = words(SECTION + 1)
    final = build_classification_user_prompt(TITLE, " ".join(tokens), SCHEME, section_summaries=SUMMARIES)
    assert tokens[SECTION - 1] in final.split()
    assert tokens[SECTION] not in final.split()


def test_chat_messages_is_system_then_user():
    assert chat_messages("the system prompt", "the user turn") == [
        {"role": "system", "content": "the system prompt"},
        {"role": "user", "content": "the user turn"},
    ]


# --- Scripted provider calls ------------------------------------------------------------------


class Script:
    """A ``call_once(system_prompt, user_prompt)`` answering from a list, in order.

    Every call is recorded. A step that is an exception is raised; anything else is returned as
    the reply. The list holds exactly what the path under test should use, so a call past its end
    raises IndexError, which is neither ProviderUnavailable nor anything a loop catches."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system_prompt: str, user_prompt: str):
        self.calls.append((system_prompt, user_prompt))
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    @property
    def kinds(self) -> list[str]:
        """Which prompt each call carried: "section" or "final"."""
        names = {SECTION_SUMMARY_SYSTEM_PROMPT: "section", CLASSIFICATION_SYSTEM_PROMPT: "final"}
        return [names[system] for system, _ in self.calls]


def section_reply(number: int) -> str:
    """Section ``number``'s conforming reply, its words naming the section they came from."""
    return json.dumps(
        {
            "summary": f"Summary of section {number}.",
            "key_points": [f"Point {number}a.", f"Point {number}b."],
        }
    )


FINAL_SUMMARY = "The handbook covers purchasing, travel and safety."
FINAL_KEY_POINTS = ("Orders need a number.", "Travel is booked through the agent.")
FINAL = json.dumps(
    {
        "doc_type": {"value": "Procedure", "confidence": 0.9},
        "department": {"value": "Finance", "confidence": 0.6},
        "tags": [{"dimension": "Process", "value": "onboarding", "confidence": 0.8}],
        "summary": FINAL_SUMMARY,
        "key_points": list(FINAL_KEY_POINTS),
    }
)


def unavailable() -> ProviderUnavailable:
    return ProviderUnavailable("http://flm.test/v1 unreachable: refused")


def refused() -> ProviderRefused:
    return ProviderRefused("http://flm.test/v1 refused the request with HTTP 401: bad key")


def classify(script: Script, text: str, **overrides) -> DocumentClassification:
    arguments = dict(title=TITLE, text=text, scheme=SCHEME, label=LABEL, model=MODEL, max_tokens=MAX_TOKENS)
    arguments.update(overrides)
    return classify_and_summarise(script, **arguments)


def attempt_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]


# --- The flow: a text within the cap is ONE call ----------------------------------------------


@pytest.mark.parametrize("count", [0, 1, SECTION - 1, SECTION], ids=["empty", "one token", "one under the cap", "exactly the cap"])
def test_a_text_within_the_cap_makes_exactly_one_call(count):
    """FR-10: "at the cost of one call rather than three". The one request returns the type, the
    department, the tags, the summary and the key points together, and no section is sent."""
    text = text_of(count)
    script = Script(FINAL)

    result = classify(script, text)

    assert len(script.calls) == 1
    assert script.kinds == ["final"]
    assert script.calls[0] == (CLASSIFICATION_SYSTEM_PROMPT, build_classification_user_prompt(TITLE, text, SCHEME))
    assert result.doc_type.value == "Procedure" and result.department.value == "Finance"
    assert [tag.value for tag in result.tags] == ["onboarding"]
    assert result.summary == FINAL_SUMMARY and result.key_points == FINAL_KEY_POINTS
    assert result.model == MODEL
    assert result.input_truncated is False  # exactly the cap is not cut
    assert result.summary_truncated is False


def test_a_text_within_the_cap_is_never_told_about_sections():
    script = Script(FINAL)
    classify(script, text_of(SECTION))
    assert "Section" not in script.calls[0][1]
    assert SECTIONED_NOTICE not in script.calls[0][1]


# --- The flow: a longer text is a call per section, then one final call -----------------------


def test_a_text_of_three_sections_makes_exactly_four_calls():
    """Three section requests in order, each carrying its own section's text and no other's, then
    the final request, carrying the title, the opening and every section summary in order."""
    tokens = words(2 * SECTION + 40)
    text = " ".join(tokens)
    sections, _ = summary_sections(text)
    assert len(sections) == 3
    script = Script(section_reply(1), section_reply(2), section_reply(3), FINAL)

    result = classify(script, text)

    assert len(script.calls) == 4
    assert script.kinds == ["section", "section", "section", "final"]
    # The section requests: the section prompt, and the sections' texts in order.
    for index, section in enumerate(sections):
        system, user = script.calls[index]
        assert system == SECTION_SUMMARY_SYSTEM_PROMPT
        assert user == build_section_summary_user_prompt(TITLE, section, index + 1, 3)
        assert f"Section {index + 1} of 3:\n{section}\n" in user
    # Each section's turn holds its own first token and neither neighbour's.
    firsts = [tokens[0], tokens[SECTION], tokens[2 * SECTION]]
    for index, first in enumerate(firsts):
        held = [other in script.calls[index][1].split() for other in firsts]
        assert held == [position == index for position in range(3)], index
    # The final request: the classification prompt, the opening, the section summaries in order.
    system, final = script.calls[3]
    assert system == CLASSIFICATION_SYSTEM_PROMPT
    assert f"Title: {TITLE}\nText:\n{classification_input(text)[0]}\n" in final
    assert tokens[SECTION] not in final.split()  # nothing past the opening is sent as text
    positions = [final.index(f"Summary: Summary of section {n}.") for n in (1, 2, 3)]
    assert positions == sorted(positions)
    for n in (1, 2, 3):
        assert f"Section {n} of 3\nSummary: Summary of section {n}.\nKey points:\n- Point {n}a.\n- Point {n}b." in final
    assert final == build_classification_user_prompt(
        TITLE, text, SCHEME,
        section_summaries=[parse_section_summary(section_reply(n)) for n in (1, 2, 3)],
    )
    # The result is the FINAL reply's, with both flags from the text's length.
    assert result.summary == FINAL_SUMMARY and result.key_points == FINAL_KEY_POINTS
    assert result.doc_type.value == "Procedure"
    assert result.model == MODEL
    assert result.input_truncated is True  # the classification read the opening only
    assert result.summary_truncated is False  # every section was summarised


def test_one_token_over_the_cap_is_two_sections_and_three_calls():
    """The other side of the cap's boundary: one token more than a single request reads, and the
    document is sectioned. Its second section is that one token."""
    tokens = words(SECTION + 1)
    script = Script(section_reply(1), section_reply(2), FINAL)

    result = classify(script, " ".join(tokens))

    assert script.kinds == ["section", "section", "final"]
    assert script.calls[1][1] == build_section_summary_user_prompt(TITLE, tokens[SECTION], 2, 2)
    assert result.input_truncated is True and result.summary_truncated is False


def test_a_text_of_exactly_the_ceiling_is_summarised_whole_and_not_reported_truncated():
    """The ceiling's boundary: MAXIMUM_SUMMARY_SECTIONS full sections, every one sent, nothing
    left over, so ``summary_truncated`` is False."""
    script = Script(*[section_reply(n) for n in range(1, MAXIMUM_SUMMARY_SECTIONS + 1)], FINAL)

    result = classify(script, text_of(CEILING))

    assert len(script.calls) == MAXIMUM_SUMMARY_SECTIONS + 1
    assert script.kinds == ["section"] * MAXIMUM_SUMMARY_SECTIONS + ["final"]
    assert result.summary_truncated is False
    assert result.input_truncated is True


def test_a_text_past_the_ceiling_makes_the_maximum_sections_plus_one_calls_and_says_it_was_truncated():
    """One token past the ceiling: still MAXIMUM_SUMMARY_SECTIONS section requests and the final
    one, never a ninth section; the token is sent in no request; and the result says the summary
    covers only the first sections, so it is not presented as a summary of the whole."""
    tokens = words(CEILING + 1)
    script = Script(*[section_reply(n) for n in range(1, MAXIMUM_SUMMARY_SECTIONS + 1)], FINAL)

    result = classify(script, " ".join(tokens))

    assert len(script.calls) == MAXIMUM_SUMMARY_SECTIONS + 1 == 9
    assert script.kinds == ["section"] * MAXIMUM_SUMMARY_SECTIONS + ["final"]
    assert result.summary_truncated is True
    assert result.input_truncated is True
    for _, user in script.calls:
        assert tokens[-1] not in user.split()
    assert f"Section {MAXIMUM_SUMMARY_SECTIONS} of {MAXIMUM_SUMMARY_SECTIONS}:" in script.calls[MAXIMUM_SUMMARY_SECTIONS - 1][1]
    assert f"Section {MAXIMUM_SUMMARY_SECTIONS} of {MAXIMUM_SUMMARY_SECTIONS}\n" in script.calls[-1][1]


def test_a_text_many_times_the_ceiling_makes_no_more_calls_than_one_just_past_it():
    script = Script(*[section_reply(n) for n in range(1, MAXIMUM_SUMMARY_SECTIONS + 1)], FINAL)

    result = classify(script, text_of(4 * CEILING))

    assert len(script.calls) == MAXIMUM_SUMMARY_SECTIONS + 1
    assert result.summary_truncated is True


def test_the_final_reply_is_the_result_and_no_section_summary_is_returned():
    script = Script(section_reply(1), section_reply(2), FINAL)

    result = classify(script, text_of(SECTION + 10))

    assert "Summary of section" not in result.summary
    assert all("Point " not in point for point in result.key_points)


# --- The flow: failures -----------------------------------------------------------------------


def test_a_section_whose_calls_all_fail_raises_after_exactly_three_calls_and_no_final_request_is_sent():
    """THE count: the first section fails every attempt, so exactly MAXIMUM_CLASSIFY_ATTEMPTS calls
    are made, an equality, then ProviderUnavailable. No later section is sent and no final request
    is made: the script holds nothing more, and a fourth call would raise IndexError."""
    script = Script(unavailable(), unavailable(), unavailable())

    with pytest.raises(ProviderUnavailable) as excinfo:
        classify(script, text_of(2 * SECTION + 1))

    assert len(script.calls) == MAXIMUM_CLASSIFY_ATTEMPTS == 3
    assert script.kinds == ["section"] * 3
    assert "final" not in script.kinds
    assert all("Section 1 of 3:" in user for _, user in script.calls)  # the same section, three times
    assert not isinstance(excinfo.value, ProviderRefused)
    message = str(excinfo.value)
    assert LABEL in message and "SECTION_SUMMARY_SCHEMA" in message
    assert "for section 1 of 3" in message
    assert f"in {MAXIMUM_CLASSIFY_ATTEMPTS} attempts" in message and "call failed" in message


def test_a_later_section_that_fails_ends_the_operation_there():
    """Section 1 succeeds and section 2 fails all three: four calls, then nothing. Section 3 is not
    sent, the final request is not made, and section 1's summary is not returned as the document's."""
    script = Script(section_reply(1), unavailable(), unavailable(), unavailable())

    with pytest.raises(ProviderUnavailable, match="for section 2 of 3"):
        classify(script, text_of(2 * SECTION + 1))

    assert len(script.calls) == 1 + MAXIMUM_CLASSIFY_ATTEMPTS
    assert script.kinds == ["section"] * 4
    assert ["Section 1 of 3:" in user for _, user in script.calls] == [True, False, False, False]
    assert all("Section 2 of 3:" in user for _, user in script.calls[1:])
    assert not any("Section 3 of 3:" in user for _, user in script.calls)


def test_a_malformed_section_reply_is_retried():
    """Invariant 10 for a section: prose is no reply. The section is asked again, and its
    conforming reply is the one the final request carries."""
    script = Script("Here is a summary of the section, in prose.", section_reply(1), section_reply(2), FINAL)

    result = classify(script, text_of(SECTION + 5))

    assert len(script.calls) == 4
    assert script.kinds == ["section", "section", "section", "final"]
    assert script.calls[0] == script.calls[1]  # the same request, sent again
    assert "Section 2 of 2:" in script.calls[2][1]
    assert "Summary: Summary of section 1." in script.calls[3][1]
    assert "in prose" not in script.calls[3][1]  # the malformed reply reached nothing
    assert result.summary == FINAL_SUMMARY


@pytest.mark.parametrize(
    "malformed",
    [
        "no json here",
        json.dumps({"summary": "A summary with no key points."}),
        json.dumps({"summary": "s" * (MAXIMUM_SUMMARY_CHARACTERS + 1), "key_points": ["A point."]}),
        json.dumps({"summary": "A summary.", "key_points": ["k"] * (MAXIMUM_KEY_POINTS + 1)}),
        FINAL,  # a classification where a section's summary was asked for
    ],
    ids=["prose", "no key points", "an over-long summary", "a sixth key point", "a classification reply"],
)
def test_three_malformed_section_replies_are_an_outage_after_exactly_three_calls(malformed):
    script = Script(malformed, malformed, malformed)

    with pytest.raises(ProviderUnavailable) as excinfo:
        classify(script, text_of(SECTION + 5))

    assert len(script.calls) == MAXIMUM_CLASSIFY_ATTEMPTS
    assert script.kinds == ["section"] * MAXIMUM_CLASSIFY_ATTEMPTS
    assert "SECTION_SUMMARY_SCHEMA for section 1 of 2" in str(excinfo.value)
    assert "schema violation" in str(excinfo.value)


def test_a_refusal_from_a_section_is_re_raised_after_one_call():
    """D-118: a bad key is refused the same way every time, so the section's remaining attempts
    are not spent, no other section is sent and no final request is made."""
    error = refused()
    script = Script(error)

    with pytest.raises(ProviderRefused) as excinfo:
        classify(script, text_of(2 * SECTION + 1))

    assert excinfo.value is error  # re-raised as itself, not wrapped
    assert len(script.calls) == 1
    assert script.kinds == ["section"]


def test_a_refusal_from_a_later_section_stops_there_too():
    error = refused()
    script = Script(section_reply(1), error)

    with pytest.raises(ProviderRefused) as excinfo:
        classify(script, text_of(2 * SECTION + 1))

    assert excinfo.value is error
    assert script.kinds == ["section", "section"]


def test_every_request_has_its_own_three_attempts():
    """A section that needed all three attempts leaves the next section, and the final request,
    three of their own: nine calls for two sections and the final request, and it succeeds. A
    budget shared across the operation would have run out at the fourth call."""
    script = Script(
        unavailable(), "prose", section_reply(1),
        "prose", unavailable(), section_reply(2),
        unavailable(), "prose", FINAL,
    )

    result = classify(script, text_of(SECTION + 5))

    assert len(script.calls) == 3 * MAXIMUM_CLASSIFY_ATTEMPTS
    assert script.kinds == ["section"] * 6 + ["final"] * 3
    assert result.summary == FINAL_SUMMARY


def test_a_final_request_that_fails_after_every_section_succeeded_returns_nothing():
    """The sections' work is not turned into a result: the operation raises, as it does when a
    short document's one request fails."""
    script = Script(section_reply(1), section_reply(2), "prose", "prose", "prose")

    with pytest.raises(ProviderUnavailable) as excinfo:
        classify(script, text_of(SECTION + 5))

    assert len(script.calls) == 2 + MAXIMUM_CLASSIFY_ATTEMPTS
    assert script.kinds == ["section", "section", "final", "final", "final"]
    assert f"conforming to CLASSIFICATION_SCHEMA in {MAXIMUM_CLASSIFY_ATTEMPTS} attempts" in str(excinfo.value)
    assert " for section " not in str(excinfo.value)  # it was the final request that failed, and it says so


def test_a_refusal_from_the_final_request_is_re_raised_after_one_call_of_it():
    error = refused()
    script = Script(section_reply(1), section_reply(2), error)

    with pytest.raises(ProviderRefused) as excinfo:
        classify(script, text_of(SECTION + 5))

    assert excinfo.value is error
    assert script.kinds == ["section", "section", "final"]


class UndecidedError(Exception):
    """An exception the provider did not decide: a bug, not an outage."""


def test_any_other_exception_from_a_section_propagates_after_one_call():
    error = UndecidedError("unexpected")
    script = Script(error)

    with pytest.raises(UndecidedError) as excinfo:
        classify(script, text_of(SECTION + 5))

    assert excinfo.value is error
    assert len(script.calls) == 1


def test_a_within_cap_request_that_fails_makes_exactly_three_calls():
    script = Script(unavailable(), unavailable(), unavailable())

    with pytest.raises(ProviderUnavailable, match="CLASSIFICATION_SCHEMA"):
        classify(script, text_of(SECTION))

    assert len(script.calls) == MAXIMUM_CLASSIFY_ATTEMPTS
    assert script.kinds == ["final"] * MAXIMUM_CLASSIFY_ATTEMPTS


# --- One section's loop, directly -------------------------------------------------------------


def scripted(*steps):
    """A no-argument ``call_once`` for ``run_section_summary_attempts``, counting its calls."""
    remaining = list(steps)
    calls = []

    def call_once():
        calls.append(len(calls) + 1)
        step = remaining.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    return call_once, calls


def test_a_conforming_section_reply_is_returned_after_exactly_one_call():
    call_once, calls = scripted(section_reply(4))

    result = run_section_summary_attempts(call_once, label=LABEL, number=4, of=6, max_tokens=MAX_TOKENS)

    assert result == SectionSummary(summary="Summary of section 4.", key_points=("Point 4a.", "Point 4b."))
    assert calls == [1]


def test_three_failed_section_calls_raise_after_exactly_three_calls():
    """MAXIMUM_CLASSIFY_ATTEMPTS is a total of 3, 1 initial call + 2 retries. If someone
    reconciles the proposal's "2 retries" by setting it to 2, this fails."""
    call_once, calls = scripted(unavailable(), unavailable(), unavailable())

    with pytest.raises(ProviderUnavailable) as excinfo:
        run_section_summary_attempts(call_once, label=LABEL, number=2, of=6)

    assert len(calls) == MAXIMUM_CLASSIFY_ATTEMPTS == 3
    assert str(excinfo.value).startswith(
        f"{LABEL} returned no response conforming to SECTION_SUMMARY_SCHEMA for section 2 of 6 in 3 attempts; "
        "last failure: call failed: "
    )


def test_a_section_reply_that_conforms_on_the_third_attempt_is_returned():
    call_once, calls = scripted(unavailable(), "prose", section_reply(1))

    assert run_section_summary_attempts(call_once, label=LABEL, number=1, of=2).summary == "Summary of section 1."
    assert calls == [1, 2, 3]


# --- The attempt log ---------------------------------------------------------------------------


def test_section_attempts_are_logged_under_their_own_step_and_the_final_request_under_classification(caplog):
    """A failed call and a malformed reply for section 1, then its parsed reply, then section 2's,
    then the final request's: five lines. A section's line names the section; the final request's
    lines are the classification lines they always were. Each carries the caller's max_tokens."""
    script = Script(unavailable(), "prose", section_reply(1), section_reply(2), FINAL)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with attempt_log.account("account-4"):
            classify(script, text_of(SECTION + 5))

    records = [r for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]
    assert [r.levelno for r in records] == [
        logging.WARNING, logging.WARNING, logging.INFO, logging.INFO, logging.INFO,
    ]
    lines = [r.getMessage() for r in records]
    bracket = (
        rf"\[finish_reason=unreported completion_tokens=unreported prompt_tokens=unreported "
        rf"max_tokens={MAX_TOKENS} max_statements=unreported\]"
    )
    of = MAXIMUM_CLASSIFY_ATTEMPTS
    expected = [
        rf"section summary attempt 1 of {of} failed after \d+\.\d s {bracket} \(account account-4\): "
        r"ProviderUnavailable: section 1 of 2: .+unreachable.+",
        rf"section summary attempt 2 of {of} failed after \d+\.\d s {bracket} \(account account-4\): "
        r"SchemaViolation: section 1 of 2: no JSON object in the response",
        rf"section summary attempt 3 of {of} parsed after \d+\.\d s {bracket} \(account account-4\): "
        r"section 1 of 2, 2 key point\(s\)",
        rf"section summary attempt 1 of {of} parsed after \d+\.\d s {bracket} \(account account-4\): "
        r"section 2 of 2, 2 key point\(s\)",
        rf"classification attempt 1 of {of} parsed after \d+\.\d s {bracket} \(account account-4\): 1 tag\(s\)",
    ]
    for line, pattern in zip(lines, expected, strict=True):
        assert re.fullmatch(pattern, line), line
    assert attempt_log.SECTION_SUMMARY_STEP == "section summary"


def test_no_line_quotes_a_section_summary_or_the_documents(caplog):
    """A summary is the document's content in the model's words, and the log quotes no reply."""
    over_long = json.dumps({"summary": "Marguerite approved the Geelong audit. " * 20, "key_points": ["A point."]})
    script = Script(over_long, section_reply(1), section_reply(2), FINAL)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        classify(script, text_of(SECTION + 5))

    lines = attempt_lines(caplog)
    assert len(lines) == 4
    assert "SchemaViolation: section 1 of 2: 'summary' has" in lines[0]
    for line in lines:
        for word in ("Marguerite", "Geelong", "Summary of section", "Point 1a", "handbook covers", "Orders need"):
            assert word not in line, line


def test_logging_changes_no_call_count(caplog):
    script = Script(unavailable(), unavailable(), unavailable())

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with pytest.raises(ProviderUnavailable):
            classify(script, text_of(SECTION + 5))

    assert len(script.calls) == MAXIMUM_CLASSIFY_ATTEMPTS
    lines = attempt_lines(caplog)
    assert len(lines) == MAXIMUM_CLASSIFY_ATTEMPTS
    assert all(line.startswith("section summary attempt ") for line in lines)
