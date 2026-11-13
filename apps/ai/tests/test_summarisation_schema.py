"""The summary parser (apps/ai/summarisation.py): what it repairs, what it refuses (FR-16, D-125).

FR-16 Server-End: "The response is schema-validated before storage". ``parse_summary`` is that
validation. It makes the same three repairs as the statement and classification parsers, a code
fence, a sentence of preamble and a trailing comma, through the same code (apps/ai/schema.py), and
nothing beyond them. Every refusal below is a failed attempt in the loop, never a partial summary
(CLAUDE.md invariant 10). The ones that carry a requirement:

- **UC-04 A1.** An empty ``action_items`` array is a result, "recorded as empty rather than
  omitted"; a reply that leaves the key out is a violation.
- **UC-04, "every element of the summary carries a reference to the passage".** An element with no
  ``passages``, an empty one, or a label that is not ``P<n>`` is a violation, never repaired.
- **Every limit is a refusal, never a trim.** A reply over a limit is retried, not cut to fit.

What the parser does NOT do is checked here too: it does not decide whether a label names a passage
that was sent. That is set membership in apps/meetings/summaries.py (invariant 5), tested in
apps/meetings/tests/test_summary_verification.py.

No provider, no network, no database: a pure function over a string.
"""

import json
import re

import pytest

import apps.ai.schema as schema
import apps.ai.summarisation as summarisation
from apps.ai.base import ExtractedActionItem, SummaryElement
from apps.ai.schema import SchemaViolation
from apps.ai.summarisation import (
    EXAMPLE_FIRST_PASSAGE,
    EXAMPLE_REPLY,
    MAXIMUM_ACTION_ITEMS,
    MAXIMUM_DECISIONS,
    MAXIMUM_ELEMENT_CHARACTERS,
    MAXIMUM_HIGHLIGHTS,
    MAXIMUM_PASSAGES_PER_ELEMENT,
    MAXIMUM_PHRASE_CHARACTERS,
    MAXIMUM_SUMMARY_SENTENCES,
    SUMMARY_SCHEMA,
    ParsedSummary,
    parse_summary,
)

TOP_LEVEL_KEYS = ("summary", "decisions", "highlights", "action_items")
ELEMENT_LISTS = ("summary", "decisions", "highlights")


def element(text="The team reviewed the first quarter.", passages=("P1",)) -> dict:
    return {"text": text, "passages": list(passages)}


def item(description="Reconcile the September card statements", owner="Alex", due="next Friday",
         passages=("P2",)) -> dict:
    return {"description": description, "owner": owner, "due": due, "passages": list(passages)}


def reply(**parts) -> dict:
    """A conforming reply as a dict; ``parts`` replaces whole top-level values."""
    body = {
        "summary": [element(), element("It froze discretionary travel until January.", ("P1", "P2"))],
        "decisions": [element("Discretionary travel is frozen until 31 January.", ("P2",))],
        "highlights": [element("Travel was twice its budget.", ("P1",))],
        "action_items": [item()],
    }
    body.update(parts)
    return body


def parse(body) -> ParsedSummary:
    return parse_summary(json.dumps(body))


def elements(count: int) -> list[dict]:
    return [element(f"Sentence number {number}.") for number in range(count)]


def items(count: int) -> list[dict]:
    return [item(f"Task number {number}") for number in range(count)]


def labels(count: int) -> list[str]:
    return [f"P{number}" for number in range(1, count + 1)]


VALID = json.dumps(reply())


# --- The happy path ------------------------------------------------------------------------


def test_a_conforming_reply_parses_into_the_four_parts():
    parsed = parse_summary(VALID)

    assert isinstance(parsed, ParsedSummary)
    assert parsed.narrative == (
        SummaryElement(text="The team reviewed the first quarter.", passages=(1,)),
        SummaryElement(text="It froze discretionary travel until January.", passages=(1, 2)),
    )
    assert parsed.decisions == (
        SummaryElement(text="Discretionary travel is frozen until 31 January.", passages=(2,)),
    )
    assert parsed.highlights == (SummaryElement(text="Travel was twice its budget.", passages=(1,)),)
    assert parsed.action_items == (
        ExtractedActionItem(
            description="Reconcile the September card statements", owner="Alex", due="next Friday",
            passages=(2,),
        ),
    )


def test_the_worked_examples_own_reply_parses():
    """The reply the prompt teaches must be one the parser accepts, or the example trains a
    violation. Its labels are the example's own, above any real passage."""
    parsed = parse_summary(EXAMPLE_REPLY)

    assert len(parsed.narrative) == 2
    assert len(parsed.decisions) == 1
    assert len(parsed.highlights) == 2
    assert [(a.owner, a.due) for a in parsed.action_items] == [
        ("Bastian", "tomorrow"),
        (None, "before the first frost"),
    ]
    numbers = {
        number
        for part in (parsed.narrative, parsed.decisions, parsed.highlights, parsed.action_items)
        for entry in part
        for number in entry.passages
    }
    assert numbers == {EXAMPLE_FIRST_PASSAGE, EXAMPLE_FIRST_PASSAGE + 1}


def test_the_parts_keep_the_replys_order():
    parsed = parse(
        reply(
            summary=[element("Third."), element("First."), element("Second.")],
            action_items=[item("Zebra"), item("Apple"), item("Mango")],
        )
    )
    assert [e.text for e in parsed.narrative] == ["Third.", "First.", "Second."]
    assert [a.description for a in parsed.action_items] == ["Zebra", "Apple", "Mango"]


# --- The four keys: all required, no fifth ---------------------------------------------------


@pytest.mark.parametrize("missing", TOP_LEVEL_KEYS)
def test_each_of_the_four_keys_is_required(missing):
    body = reply()
    del body[missing]

    with pytest.raises(SchemaViolation, match="missing top-level key"):
        parse(body)


def test_a_fifth_key_is_a_violation():
    with pytest.raises(SchemaViolation, match="unexpected top-level key"):
        parse(reply(notes="The meeting ran over."))


@pytest.mark.parametrize(
    "steered",
    [
        lambda key: reply(**{key: 1}),
        lambda key: {key: []},
        lambda key: reply(summary=[{**element(), key: 1}]),
        lambda key: reply(action_items=[{**item(), key: 1}]),
    ],
    ids=["a fifth top-level key", "the only key", "an element's third key", "an action item's fifth key"],
)
def test_a_violation_never_quotes_a_key_the_reply_chose(steered):
    """A key name is the model's words, which a transcript can steer, and the violation's message
    reaches the attempts log and the warning a failed run writes. The message names the schema's
    own keys and counts the reply's (the security review of 12 November, D-125's third note)."""
    key = "Priya said the merger closes on Friday"

    with pytest.raises(SchemaViolation) as caught:
        parse(steered(key))

    assert key not in str(caught.value)
    assert "Priya" not in str(caught.value)


@pytest.mark.parametrize("key", TOP_LEVEL_KEYS)
@pytest.mark.parametrize("value", [{}, "none", None, 0], ids=["object", "string", "null", "number"])
def test_each_key_must_hold_an_array(key, value):
    with pytest.raises(SchemaViolation, match="not an array"):
        parse(reply(**{key: value}))


# --- UC-04 A1: an empty action-item section is a result; an omitted one is not ----------------


def test_an_empty_action_items_array_is_a_result():
    """UC-04 A1: "The system records the action item section as empty rather than omitting it."
    A meeting that raised no action items is a conforming reply, not a failed attempt."""
    parsed = parse(reply(action_items=[]))

    assert parsed.action_items == ()
    assert parsed.narrative  # and the rest of the reply is still there


def test_a_reply_that_omits_the_action_items_key_is_a_violation():
    body = reply()
    del body["action_items"]

    with pytest.raises(SchemaViolation, match="action_items"):
        parse(body)


def test_decisions_highlights_and_action_items_may_all_be_empty_together():
    parsed = parse(reply(decisions=[], highlights=[], action_items=[]))

    assert (parsed.decisions, parsed.highlights, parsed.action_items) == ((), (), ())
    assert len(parsed.narrative) == 2


# --- The narrative: 1 to MAXIMUM_SUMMARY_SENTENCES --------------------------------------------


def test_the_narrative_needs_at_least_one_sentence():
    with pytest.raises(SchemaViolation, match="fewer than 1"):
        parse(reply(summary=[]))


def test_the_narrative_takes_one_sentence_and_the_maximum_and_refuses_one_more():
    assert len(parse(reply(summary=elements(1))).narrative) == 1
    assert len(parse(reply(summary=elements(MAXIMUM_SUMMARY_SENTENCES))).narrative) == MAXIMUM_SUMMARY_SENTENCES
    with pytest.raises(SchemaViolation, match=f"more than the {MAXIMUM_SUMMARY_SENTENCES} allowed"):
        parse(reply(summary=elements(MAXIMUM_SUMMARY_SENTENCES + 1)))


# --- Every limit is a violation when exceeded, and nothing is trimmed -------------------------


@pytest.mark.parametrize(
    "key,limit,build",
    [
        ("decisions", MAXIMUM_DECISIONS, elements),
        ("highlights", MAXIMUM_HIGHLIGHTS, elements),
        ("action_items", MAXIMUM_ACTION_ITEMS, items),
    ],
    ids=["decisions", "highlights", "action_items"],
)
def test_each_list_takes_its_limit_and_refuses_one_more(key, limit, build):
    """Invariant 10: a reply over a limit is no reply. If the parser trimmed instead, the first
    ``limit`` entries would come back; they do not, the whole reply is refused."""
    part = "action_items" if key == "action_items" else key
    assert len(getattr(parse(reply(**{key: build(limit)})), part)) == limit

    with pytest.raises(SchemaViolation, match=f"more than the {limit} allowed"):
        parse(reply(**{key: build(limit + 1)}))


@pytest.mark.parametrize("where", [*ELEMENT_LISTS, "action_items"])
def test_an_element_takes_the_maximum_passages_and_refuses_one_more(where):
    def body(count):
        entry = item(passages=labels(count)) if where == "action_items" else element(passages=labels(count))
        return reply(**{where: [entry]})

    at_the_limit = parse(body(MAXIMUM_PASSAGES_PER_ELEMENT))
    part = at_the_limit.narrative if where == "summary" else getattr(at_the_limit, where)
    assert part[0].passages == tuple(range(1, MAXIMUM_PASSAGES_PER_ELEMENT + 1))

    with pytest.raises(SchemaViolation, match=f"more than the {MAXIMUM_PASSAGES_PER_ELEMENT} allowed"):
        parse(body(MAXIMUM_PASSAGES_PER_ELEMENT + 1))


def test_the_passage_cap_is_counted_before_repeats_are_collapsed():
    """The array is held to its limit as returned: one label repeated past the limit is refused,
    not collapsed into a single reference."""
    with pytest.raises(SchemaViolation, match="more than the"):
        parse(reply(summary=[element(passages=["P1"] * (MAXIMUM_PASSAGES_PER_ELEMENT + 1))]))


# --- Passage labels: a string "P<n>", and nothing else ------------------------------------------

NOT_A_LABEL = {
    "a bare number": 3,
    "a numeric string": "3",
    "lower case": "p3",
    "zero": "P0",
    "a leading zero": "P03",
    "the word": "passage 3",
    "the header form": "[P3]",
    "a negative": "P-3",
    "a decimal": "P3.0",
    "two labels in one string": "P1, P2",
    "a range": "P1-P3",
    "the prefix alone": "P",
    "an empty string": "",
    "null": None,
    "a boolean": True,
    "a nested array": ["P3"],
    "an object": {"label": "P3"},
}


@pytest.mark.parametrize("label", list(NOT_A_LABEL.values()), ids=list(NOT_A_LABEL))
@pytest.mark.parametrize("where", [*ELEMENT_LISTS, "action_items"])
def test_a_passage_that_is_not_a_p_label_is_a_violation_and_is_not_repaired(where, label):
    """A bare 3 or "p3" is plainly meant as passage 3, and is refused all the same: a reference
    the application guessed at is not a reference the model gave (invariant 5)."""
    entry = item(passages=["P1", label]) if where == "action_items" else element(passages=["P1", label])

    with pytest.raises(SchemaViolation, match="not a label of the form"):
        parse(reply(**{where: [entry]}))


@pytest.mark.parametrize("where", [*ELEMENT_LISTS, "action_items"])
def test_an_empty_passages_array_is_a_violation(where):
    """UC-04: "Every element of the summary carries a reference to the passage of the transcript
    it was drawn from." An element citing nothing breaks the schema."""
    entry = item(passages=[]) if where == "action_items" else element(passages=[])

    with pytest.raises(SchemaViolation, match="fewer than 1"):
        parse(reply(**{where: [entry]}))


@pytest.mark.parametrize("where", [*ELEMENT_LISTS, "action_items"])
def test_a_missing_passages_key_is_a_violation(where):
    entry = item() if where == "action_items" else element()
    del entry["passages"]

    with pytest.raises(SchemaViolation, match="is missing"):
        parse(reply(**{where: [entry]}))


@pytest.mark.parametrize("value", ["P1", 1, None, {"P1": True}], ids=["string", "number", "null", "object"])
def test_passages_must_be_an_array(value):
    body = reply()
    body["summary"][0]["passages"] = value

    with pytest.raises(SchemaViolation, match="not an array"):
        parse(body)


def test_a_label_is_read_as_its_number_and_is_not_checked_against_anything():
    """The parser checks a label's SHAPE. Whether passage 9999 was sent is set membership, done by
    apps/meetings/summaries.py, and a parser that dropped it here would hide the count of
    fabricated references from the run that logs them."""
    parsed = parse(reply(summary=[element(passages=["P7", "P9999", "P1"])]))

    assert parsed.narrative[0].passages == (7, 9999, 1)


def test_surrounding_whitespace_on_a_label_is_stripped():
    assert parse(reply(summary=[element(passages=[" P2 ", "P3\n"])])).narrative[0].passages == (2, 3)


# --- The duplicate-label collapse: a shape tolerance, not a repair --------------------------------


def test_a_label_repeated_within_one_element_is_kept_once_in_first_position():
    parsed = parse(
        reply(
            summary=[element(passages=["P2", "P1", "P2", "P1"])],
            action_items=[item(passages=["P3", "P3"])],
        )
    )

    assert parsed.narrative[0].passages == (2, 1)
    assert parsed.action_items[0].passages == (3,)


def test_the_same_label_in_two_elements_is_two_references():
    parsed = parse(reply(summary=[element("One.", ["P1"]), element("Two.", ["P1"])]))

    assert [e.passages for e in parsed.narrative] == [(1,), (1,)]


# --- owner and due: a string or null --------------------------------------------------------------


@pytest.mark.parametrize("key", ["owner", "due"])
def test_owner_and_due_accept_a_string_and_keep_it_as_said(key):
    said = "the Facilities team" if key == "owner" else "before the first frost"
    parsed = parse(reply(action_items=[item(**{key: said})]))

    assert getattr(parsed.action_items[0], key) == said


@pytest.mark.parametrize("key", ["owner", "due"])
def test_owner_and_due_accept_null(key):
    assert getattr(parse(reply(action_items=[item(**{key: None})])).action_items[0], key) is None


@pytest.mark.parametrize("key", ["owner", "due"])
@pytest.mark.parametrize("blank", ["", "   ", "\n\t"], ids=["empty", "spaces", "newline"])
def test_a_blank_owner_or_due_reads_as_null(key, blank):
    """A blank string says what null says: nobody was named, no deadline was said. It must not
    be stored as an owner called "" or matched against the user list."""
    assert getattr(parse(reply(action_items=[item(**{key: blank})])).action_items[0], key) is None


@pytest.mark.parametrize("key", ["owner", "due"])
@pytest.mark.parametrize("value", [7, 7.5, True, ["Alex"], {"name": "Alex"}],
                         ids=["integer", "float", "boolean", "array", "object"])
def test_an_owner_or_due_that_is_neither_a_string_nor_null_is_a_violation(key, value):
    with pytest.raises(SchemaViolation, match="neither a string nor null"):
        parse(reply(action_items=[item(**{key: value})]))


@pytest.mark.parametrize("key", ["owner", "due"])
def test_an_owner_or_due_takes_the_maximum_length_and_refuses_one_more(key):
    at_the_limit = "x" * MAXIMUM_PHRASE_CHARACTERS
    assert getattr(parse(reply(action_items=[item(**{key: at_the_limit})])).action_items[0], key) == at_the_limit

    with pytest.raises(SchemaViolation, match=f"longer than {MAXIMUM_PHRASE_CHARACTERS}"):
        parse(reply(action_items=[item(**{key: at_the_limit + "x"})]))


@pytest.mark.parametrize("key", ["owner", "due", "description", "passages"])
def test_an_action_item_must_carry_all_four_keys_even_where_one_is_null(key):
    """``owner`` and ``due`` are required keys whose value may be null. A model that leaves the
    key out has not said "nobody was named"; it has left the question unanswered."""
    entry = item()
    del entry[key]

    with pytest.raises(SchemaViolation, match="is missing"):
        parse(reply(action_items=[entry]))


# --- text and description: one non-empty string, bounded -------------------------------------------


@pytest.mark.parametrize("value", ["", "   ", None, 12, ["A sentence."], {"text": "A sentence."}],
                         ids=["empty", "spaces", "null", "number", "array", "object"])
@pytest.mark.parametrize("where", ELEMENT_LISTS)
def test_an_empty_or_non_string_text_is_a_violation(where, value):
    with pytest.raises(SchemaViolation, match="empty or non-string 'text'"):
        parse(reply(**{where: [element(text=value)]}))


@pytest.mark.parametrize("value", ["", "   ", None, 12], ids=["empty", "spaces", "null", "number"])
def test_an_empty_or_non_string_description_is_a_violation(value):
    with pytest.raises(SchemaViolation, match="empty or non-string 'description'"):
        parse(reply(action_items=[item(description=value)]))


@pytest.mark.parametrize("where", ELEMENT_LISTS)
def test_a_text_takes_the_maximum_length_and_refuses_one_more(where):
    at_the_limit = "x" * MAXIMUM_ELEMENT_CHARACTERS
    parsed = parse(reply(**{where: [element(text=at_the_limit)]}))
    part = parsed.narrative if where == "summary" else getattr(parsed, where)
    assert part[0].text == at_the_limit

    with pytest.raises(SchemaViolation, match=f"longer than {MAXIMUM_ELEMENT_CHARACTERS}"):
        parse(reply(**{where: [element(text=at_the_limit + "x")]}))


def test_a_description_takes_the_maximum_length_and_refuses_one_more():
    at_the_limit = "x" * MAXIMUM_ELEMENT_CHARACTERS
    assert parse(reply(action_items=[item(description=at_the_limit)])).action_items[0].description == at_the_limit

    with pytest.raises(SchemaViolation, match=f"longer than {MAXIMUM_ELEMENT_CHARACTERS}"):
        parse(reply(action_items=[item(description=at_the_limit + "x")]))


def test_strings_are_stripped_of_surrounding_whitespace_and_nothing_inside_them_changes():
    parsed = parse(
        reply(
            summary=[element(text="  The team  reviewed the quarter.\n")],
            action_items=[item(description=" Book the  room ", owner="  Alex Morgan ", due=" next  Friday ")],
        )
    )

    assert parsed.narrative[0].text == "The team  reviewed the quarter."  # the inner spacing is the model's
    assert parsed.action_items[0] == ExtractedActionItem(
        description="Book the  room", owner="Alex Morgan", due="next  Friday", passages=(2,)
    )


# --- The shape of an element ------------------------------------------------------------------------


@pytest.mark.parametrize("where", [*ELEMENT_LISTS, "action_items"])
@pytest.mark.parametrize("entry", ["A sentence.", ["A sentence.", "P1"], 4, None],
                         ids=["string", "array", "number", "null"])
def test_an_entry_that_is_not_an_object_is_a_violation(where, entry):
    with pytest.raises(SchemaViolation, match="not an object"):
        parse(reply(**{where: [entry]}))


@pytest.mark.parametrize("where", ELEMENT_LISTS)
def test_an_element_with_a_third_key_is_a_violation(where):
    entry = element()
    entry["confidence"] = 0.9

    with pytest.raises(SchemaViolation, match="unexpected key"):
        parse(reply(**{where: [entry]}))


def test_an_action_item_with_a_fifth_key_is_a_violation():
    entry = item()
    entry["due_date"] = "2026-11-20"  # a date the model computed is exactly what rule 9 forbids

    with pytest.raises(SchemaViolation, match="unexpected key"):
        parse(reply(action_items=[entry]))


def test_an_element_without_text_is_a_violation():
    with pytest.raises(SchemaViolation, match="is missing"):
        parse(reply(decisions=[{"passages": ["P1"]}]))


def test_one_bad_entry_refuses_the_whole_reply():
    """Not a partial summary: the good sentences are not kept and the bad one dropped."""
    body = reply(summary=[element("A good sentence."), element("A sentence citing nothing.", [])])

    with pytest.raises(SchemaViolation):
        parse(body)


# --- What it repairs, and nothing beyond -------------------------------------------------------------


def test_a_markdown_code_fence_is_stripped():
    assert parse_summary(f"```json\n{VALID}\n```") == parse_summary(VALID)
    assert parse_summary(f"```\n{VALID}\n```") == parse_summary(VALID)


def test_prose_around_the_object_is_discarded():
    raw = f"Certainly! Here is the summary of the meeting:\n{VALID}\nLet me know if you need more."

    assert parse_summary(raw) == parse_summary(VALID)


def test_a_trailing_comma_is_repaired():
    raw = (
        '{"summary": [{"text": "The team met.", "passages": ["P1",],},], '
        '"decisions": [], "highlights": [], "action_items": [],}'
    )

    parsed = parse_summary(raw)

    assert parsed.narrative == (SummaryElement(text="The team met.", passages=(1,)),)
    assert parsed.action_items == ()


def test_a_brace_inside_a_string_does_not_end_the_object():
    parsed = parse(reply(summary=[element(text="The {draft} budget was reviewed.")]))

    assert parsed.narrative[0].text == "The {draft} budget was reviewed."


def test_the_repairs_are_the_statement_parsers_own_code():
    """One definition of what is repaired: this module imports the three, it does not copy them."""
    assert summarisation.strip_code_fences is schema.strip_code_fences
    assert summarisation.outermost_json_object is schema.outermost_json_object
    assert summarisation.TRAILING_COMMA_PATTERN is schema.TRAILING_COMMA_PATTERN
    assert summarisation.SchemaViolation is schema.SchemaViolation


# --- Non-object and non-JSON replies ------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,because",
    [
        ("", "empty response"),
        ("   \n", "empty response"),
        ("The meeting reviewed the budget and agreed to freeze travel.", "no JSON object"),
        ("[1, 2, 3]", "no JSON object"),
        ('"a JSON string"', "no JSON object"),
        ("42", "no JSON object"),
        ("null", "no JSON object"),
        ('{"summary": [', "unbalanced"),
        ('{"summary": [{"text": "Cut off mid-sentence', "unbalanced"),
        # Balanced braces, so the object is extracted, and then it is not JSON: a comma is missing
        # between two keys, which no repair here guesses at.
        ('{"summary": [] "decisions": [], "highlights": [], "action_items": []}', "not valid JSON"),
        ("{'summary': [], 'decisions': [], 'highlights': [], 'action_items': []}", "not valid JSON"),
        ("{}", "missing top-level key"),
    ],
)
def test_a_non_conforming_reply_raises_schema_violation(raw, because):
    with pytest.raises(SchemaViolation, match=because):
        parse_summary(raw)


@pytest.mark.parametrize("raw", [None, 12, b'{"summary": []}', {"summary": []}],
                         ids=["None", "int", "bytes", "dict"])
def test_a_non_string_reply_raises_rather_than_crashing(raw):
    with pytest.raises(SchemaViolation, match="empty response"):
        parse_summary(raw)


# --- A violation's message goes to the attempt log, so it quotes no value -----------------------------


@pytest.mark.parametrize(
    "body",
    [
        reply(summary=[element(text="Redundancies were agreed for the Carlton office.", passages=["Carlton-7"])]),
        reply(summary=[element(text="Redundancies in Carlton " + "x" * MAXIMUM_ELEMENT_CHARACTERS)]),
        reply(action_items=[item(owner="Carlton " + "x" * MAXIMUM_PHRASE_CHARACTERS)]),
        reply(action_items=[item(description="Tell Carlton", due=["Carlton"])]),
        reply(decisions=["Carlton closes in March."]),
        reply(highlights="Carlton closes in March."),
    ],
    ids=["label", "long text", "long owner", "due", "entry", "list"],
)
def test_a_violation_message_quotes_no_value_from_the_reply(body):
    """apps/ai/attempt_log.py records the message and quotes no reply: a summary is the meeting's
    content. The message says where the reply broke the schema, never what it said."""
    with pytest.raises(SchemaViolation) as excinfo:
        parse(body)

    assert "Carlton" not in str(excinfo.value)


def test_a_violation_counts_an_unexpected_key_and_no_longer_names_it():
    """Pinned so it reads as known rather than assumed. The VALUES of a reply never reach a message
    (above). Until 8a2eec1 (13 November) the NAME of a key the schema does not have did, so a model
    that wrote content as a key name put that much of it in the attempt log. The security review of
    12 November found it, and this parser now counts such keys instead (D-125's third note). FR-12's
    statement parser and FR-10's classification parser named such keys too, until c016bbe later the
    same day (apps/ai/tests/test_schema.py and test_classification_schema.py)."""
    with pytest.raises(SchemaViolation) as excinfo:
        parse(reply(follow_up="Carlton closes in March."))

    assert "1 unexpected top-level key" in str(excinfo.value)
    assert "follow_up" not in str(excinfo.value)
    assert "Carlton" not in str(excinfo.value)


# --- The schema object and the parser agree on every limit ----------------------------------------------


def test_the_schema_requires_exactly_the_four_keys_and_allows_no_other():
    assert tuple(SUMMARY_SCHEMA["required"]) == TOP_LEVEL_KEYS
    assert set(SUMMARY_SCHEMA["properties"]) == set(TOP_LEVEL_KEYS)
    assert SUMMARY_SCHEMA["additionalProperties"] is False
    for key in TOP_LEVEL_KEYS:
        assert SUMMARY_SCHEMA["properties"][key]["type"] == "array"


def test_the_schema_states_the_limits_the_constants_hold():
    properties = SUMMARY_SCHEMA["properties"]
    assert (properties["summary"]["minItems"], properties["summary"]["maxItems"]) == (1, MAXIMUM_SUMMARY_SENTENCES)
    assert properties["decisions"]["maxItems"] == MAXIMUM_DECISIONS
    assert properties["highlights"]["maxItems"] == MAXIMUM_HIGHLIGHTS
    assert properties["action_items"]["maxItems"] == MAXIMUM_ACTION_ITEMS
    # Only the narrative has a floor: the other three may be empty arrays.
    for key in ("decisions", "highlights", "action_items"):
        assert "minItems" not in properties[key]

    for key in ELEMENT_LISTS:
        entry = properties[key]["items"]
        assert sorted(entry["required"]) == ["passages", "text"]
        assert entry["additionalProperties"] is False
        assert entry["properties"]["text"] == {
            "type": "string", "minLength": 1, "maxLength": MAXIMUM_ELEMENT_CHARACTERS,
        }
        assert (entry["properties"]["passages"]["minItems"], entry["properties"]["passages"]["maxItems"]) == (
            1, MAXIMUM_PASSAGES_PER_ELEMENT,
        )

    action_item = properties["action_items"]["items"]
    assert sorted(action_item["required"]) == ["description", "due", "owner", "passages"]
    assert action_item["additionalProperties"] is False
    assert action_item["properties"]["description"]["maxLength"] == MAXIMUM_ELEMENT_CHARACTERS
    for key in ("owner", "due"):
        assert action_item["properties"][key] == {
            "type": ["string", "null"], "maxLength": MAXIMUM_PHRASE_CHARACTERS,
        }
    assert action_item["properties"]["passages"]["maxItems"] == MAXIMUM_PASSAGES_PER_ELEMENT


@pytest.mark.parametrize("key", TOP_LEVEL_KEYS)
def test_the_parser_refuses_exactly_what_the_schemas_array_bounds_refuse(key):
    """The schema is documentation, validated by hand (no jsonschema dependency), so the two can
    drift. Each bound is READ FROM THE SCHEMA here and held against the parser's behaviour: a
    limit changed in one and not the other fails."""
    declared = SUMMARY_SCHEMA["properties"][key]
    build = items if key == "action_items" else elements
    floor, ceiling = declared.get("minItems", 0), declared["maxItems"]

    parse(reply(**{key: build(floor)}))
    parse(reply(**{key: build(ceiling)}))
    with pytest.raises(SchemaViolation):
        parse(reply(**{key: build(ceiling + 1)}))
    if floor:
        with pytest.raises(SchemaViolation):
            parse(reply(**{key: build(floor - 1)}))


def test_the_parser_refuses_exactly_what_the_schemas_string_and_passage_bounds_refuse():
    element_schema = SUMMARY_SCHEMA["properties"]["summary"]["items"]["properties"]
    item_schema = SUMMARY_SCHEMA["properties"]["action_items"]["items"]["properties"]
    text_ceiling = element_schema["text"]["maxLength"]
    phrase_ceiling = item_schema["owner"]["maxLength"]
    passage_floor = element_schema["passages"]["minItems"]
    passage_ceiling = element_schema["passages"]["maxItems"]

    parse(reply(summary=[element(text="x" * text_ceiling)]))
    parse(reply(action_items=[item(owner="x" * phrase_ceiling, due="y" * phrase_ceiling)]))
    parse(reply(summary=[element(passages=labels(passage_floor))]))
    parse(reply(summary=[element(passages=labels(passage_ceiling))]))
    for over in (
        reply(summary=[element(text="x" * (text_ceiling + 1))]),
        reply(action_items=[item(description="x" * (text_ceiling + 1))]),
        reply(action_items=[item(owner="x" * (phrase_ceiling + 1))]),
        reply(action_items=[item(due="x" * (phrase_ceiling + 1))]),
        reply(summary=[element(passages=labels(passage_ceiling + 1))]),
        reply(summary=[element(passages=labels(passage_floor - 1))]),
    ):
        with pytest.raises(SchemaViolation):
            parse(over)


@pytest.mark.parametrize(
    "label",
    ["P1", "P9", "P10", "P21", "P41", "P100", "P0", "P01", "p1", "1", "P", "P1a", "PP1", "P 1", "P-1", "P1.5"],
)
def test_the_parser_accepts_exactly_the_labels_the_schemas_pattern_accepts(label):
    pattern = SUMMARY_SCHEMA["properties"]["summary"]["items"]["properties"]["passages"]["items"]["pattern"]
    conforms = re.fullmatch(pattern, label) is not None

    if conforms:
        assert parse(reply(summary=[element(passages=[label])])).narrative[0].passages == (int(label[1:]),)
    else:
        with pytest.raises(SchemaViolation, match="not a label of the form"):
            parse(reply(summary=[element(passages=[label])]))
