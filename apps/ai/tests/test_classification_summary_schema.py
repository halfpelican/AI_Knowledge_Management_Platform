"""The summary and key points in a reply: what the parsers accept and refuse (FR-10, D-139).

Two replies carry a ``summary`` and ``key_points`` under the same bounds: the classification
reply (``parse_classification``, five keys) and one section's reply (``parse_section_summary``,
two keys). Every case below runs against BOTH, because the contract gives them the same bounds
and a bound held in one parser and not the other is the drift this file exists to catch.

Each refusal is a schema violation, so a failed attempt in the loop: retried, then
ProviderUnavailable (invariant 10). Nothing is trimmed or repaired into shape, so a value exactly
at a maximum is accepted and one character or one item past it refuses the whole reply.

No provider, no network, no database.
"""

import json

import pytest

from apps.ai.base import TagScheme
from apps.ai.classification import (
    CLASSIFICATION_SCHEMA,
    SECTION_SUMMARY_SCHEMA,
    SectionSummary,
    parse_classification,
    parse_section_summary,
)
from apps.ai.schema import SchemaViolation
from apps.core.constants import (
    DOCUMENT_TYPES,
    MAXIMUM_KEY_POINT_CHARACTERS,
    MAXIMUM_KEY_POINTS,
    MAXIMUM_SUMMARY_CHARACTERS,
)

SCHEME = TagScheme(doc_types=DOCUMENT_TYPES, departments=("Finance",), tags={"Topic": ("safety",)})
SUMMARY = "Staff book business travel through the approved agent."
KEY_POINTS = ["Meals are reimbursed at the daily rate.", "Receipts are kept for a year."]
ABSENT = object()  # leave the key out of the reply altogether

CLASSIFICATION_PART = {
    "doc_type": {"value": "Policy", "confidence": 0.9},
    "department": {"value": "Finance", "confidence": 0.7},
    "tags": [{"dimension": "Topic", "value": "safety", "confidence": 0.8}],
}


def reply_text(base: dict, summary, key_points) -> str:
    body = dict(base)
    if summary is not ABSENT:
        body["summary"] = summary
    if key_points is not ABSENT:
        body["key_points"] = key_points
    return json.dumps(body)


def classification(summary=SUMMARY, key_points=KEY_POINTS):
    """The classification reply's summary and key points, through ``parse_classification``."""
    return parse_classification(reply_text(CLASSIFICATION_PART, summary, key_points), SCHEME)


def section(summary=SUMMARY, key_points=KEY_POINTS):
    """One section's reply, through ``parse_section_summary``."""
    return parse_section_summary(reply_text({}, summary, key_points))


BOTH = pytest.mark.parametrize("parse", [classification, section], ids=["classification", "section"])


# --- What conforms --------------------------------------------------------------------------


@BOTH
def test_a_conforming_summary_and_key_points_parse(parse):
    parsed = parse()

    assert parsed.summary == SUMMARY
    assert parsed.key_points == tuple(KEY_POINTS)  # in the reply's order, as a tuple


def test_a_section_reply_parses_into_a_section_summary_and_nothing_else():
    assert section() == SectionSummary(summary=SUMMARY, key_points=tuple(KEY_POINTS))


@BOTH
def test_one_key_point_is_enough(parse):
    assert parse(key_points=["The only point."]).key_points == ("The only point.",)


@BOTH
def test_surrounding_whitespace_is_stripped_and_the_text_inside_is_kept(parse):
    parsed = parse(summary="  Two  spaces\ninside.\n", key_points=[" A point. ", "\tAnother  one."])

    assert parsed.summary == "Two  spaces\ninside."
    assert parsed.key_points == ("A point.", "Another  one.")


@BOTH
def test_two_key_points_that_say_the_same_thing_are_both_kept(parse):
    """Unlike two spellings of one tag: nothing is unique per key point, and deciding that two
    sentences are the same one would be a judgement about content."""
    assert parse(key_points=["Same.", "Same."]).key_points == ("Same.", "Same.")


# --- The maxima: exactly at each is accepted, one past it is refused ------------------------


@BOTH
def test_a_summary_exactly_at_the_maximum_is_accepted_and_one_character_more_is_refused(parse):
    at = "s" * MAXIMUM_SUMMARY_CHARACTERS
    assert parse(summary=at).summary == at

    with pytest.raises(SchemaViolation) as caught:
        parse(summary=at + "s")
    assert str(caught.value) == (
        f"'summary' has {MAXIMUM_SUMMARY_CHARACTERS + 1} characters, "
        f"more than the {MAXIMUM_SUMMARY_CHARACTERS} allowed"
    )


@BOTH
def test_a_summarys_length_is_counted_after_stripping(parse):
    """The stripped value is what is returned and stored, so it is what is measured: padding
    round a summary at the maximum does not refuse it."""
    at = "s" * MAXIMUM_SUMMARY_CHARACTERS
    assert parse(summary=f"   {at}\n\n").summary == at


@BOTH
def test_an_over_long_summary_is_refused_whole_and_never_cut_to_fit(parse):
    with pytest.raises(SchemaViolation, match="'summary' has"):
        parse(summary="word " * MAXIMUM_SUMMARY_CHARACTERS)


@BOTH
def test_exactly_the_maximum_number_of_key_points_is_accepted_and_one_more_is_refused(parse):
    at = [f"Point {n}." for n in range(MAXIMUM_KEY_POINTS)]
    assert parse(key_points=at).key_points == tuple(at)

    with pytest.raises(SchemaViolation) as caught:
        parse(key_points=at + ["One too many."])
    assert str(caught.value) == (
        f"{MAXIMUM_KEY_POINTS + 1} key points, more than the {MAXIMUM_KEY_POINTS} allowed"
    )


@BOTH
def test_a_key_point_exactly_at_the_maximum_is_accepted_and_one_character_more_is_refused(parse):
    at = "k" * MAXIMUM_KEY_POINT_CHARACTERS
    assert parse(key_points=["Short.", at]).key_points == ("Short.", at)
    assert parse(key_points=[f" {at} "]).key_points == (at,)  # counted after stripping

    with pytest.raises(SchemaViolation) as caught:
        parse(key_points=["Short.", at + "k"])
    assert str(caught.value) == (
        f"key point 1 has {MAXIMUM_KEY_POINT_CHARACTERS + 1} characters, "
        f"more than the {MAXIMUM_KEY_POINT_CHARACTERS} allowed"
    )


# --- What is refused ------------------------------------------------------------------------


@BOTH
def test_a_missing_summary_is_refused(parse):
    with pytest.raises(SchemaViolation, match=r"missing top-level key\(s\): \['summary'\]"):
        parse(summary=ABSENT)


@BOTH
def test_missing_key_points_are_refused(parse):
    with pytest.raises(SchemaViolation, match=r"missing top-level key\(s\): \['key_points'\]"):
        parse(key_points=ABSENT)


@BOTH
@pytest.mark.parametrize("summary", ["", "   ", "\n\t "], ids=["empty", "spaces", "whitespace"])
def test_a_summary_empty_after_stripping_is_refused(parse, summary):
    with pytest.raises(SchemaViolation) as caught:
        parse(summary=summary)
    assert str(caught.value) == "'summary' is empty or not a string"


@BOTH
@pytest.mark.parametrize(
    "summary",
    [None, 7, True, ["A summary in an array."], {"text": "A summary in an object."}],
    ids=["null", "number", "boolean", "array", "object"],
)
def test_a_summary_that_is_not_a_string_is_refused(parse, summary):
    """Rule 9 says one string: an array of sentences is not joined into one."""
    with pytest.raises(SchemaViolation) as caught:
        parse(summary=summary)
    assert str(caught.value) == "'summary' is empty or not a string"


@BOTH
def test_an_empty_key_points_array_is_refused(parse):
    with pytest.raises(SchemaViolation) as caught:
        parse(key_points=[])
    assert str(caught.value) == "'key_points' is empty, and at least 1 is required"


@BOTH
@pytest.mark.parametrize(
    "key_points,type_name",
    [("One point.", "str"), ({"0": "One point."}, "dict"), (None, "NoneType"), (3, "int")],
    ids=["a bare string", "an object", "null", "a number"],
)
def test_key_points_that_are_not_an_array_are_refused(parse, key_points, type_name):
    """A bare string is not wrapped into an array of one."""
    with pytest.raises(SchemaViolation) as caught:
        parse(key_points=key_points)
    assert str(caught.value) == f"'key_points' is {type_name}, not an array"


@BOTH
@pytest.mark.parametrize(
    "entry", [7, None, True, ["nested"], {"point": "x"}], ids=["number", "null", "boolean", "array", "object"]
)
def test_a_key_point_that_is_not_a_string_is_refused(parse, entry):
    """Position 1: the entry before it conforms, and the reply is refused whole all the same."""
    with pytest.raises(SchemaViolation) as caught:
        parse(key_points=["A point.", entry])
    assert str(caught.value) == "key point 1 is empty or not a string"


@BOTH
@pytest.mark.parametrize("entry", ["", "  ", "\n"], ids=["empty", "spaces", "newline"])
def test_a_key_point_empty_after_stripping_is_refused_and_not_dropped(parse, entry):
    with pytest.raises(SchemaViolation) as caught:
        parse(key_points=[entry, "A point."])
    assert str(caught.value) == "key point 0 is empty or not a string"


@BOTH
@pytest.mark.parametrize(
    "summary,key_points,message",
    [
        pytest.param("A summary\x00 with a NUL.", KEY_POINTS, "a NUL character in a JSON string",
                     id="a NUL in the summary"),
        pytest.param(SUMMARY, ["A point.", "Another\x00."], "a NUL character in a JSON string",
                     id="a NUL in a key point"),
        pytest.param("A summary\ud800 with a lone surrogate.", KEY_POINTS,
                     "an unpaired surrogate in a JSON string", id="a lone surrogate in the summary"),
        pytest.param(SUMMARY, ["A point\udfff."], "an unpaired surrogate in a JSON string",
                     id="a lone surrogate in a key point"),
    ],
)
def test_a_summary_or_key_point_postgresql_cannot_store_is_refused(parse, summary, key_points, message):
    """U+0000 and a lone surrogate: a text column refuses the first and cannot encode the second,
    so a reply holding either would break the write that stores the summary. Both are refused at
    the decode step both parsers share (``loads_reply``, apps/ai/schema.py)."""
    with pytest.raises(SchemaViolation) as caught:
        parse(summary=summary, key_points=key_points)
    assert str(caught.value) == message


@BOTH
def test_a_paired_surrogate_escape_is_one_character_and_is_accepted(parse):
    """An emoji written as an escaped PAIR decodes to one character: only a LONE surrogate is
    refused."""
    text = json.dumps({"summary": "Done \U0001F389", "key_points": ["A point."]})
    assert "\\ud83c\\udf89" in text  # json.dumps really did write the pair
    assert parse(summary="Done \U0001F389").summary == "Done \U0001F389"


# --- No violation quotes the summary --------------------------------------------------------


@BOTH
def test_no_violation_quotes_a_summary_or_a_key_point(parse):
    """The message reaches the attempts log, and a summary is the document's content in the
    model's words. A length and a position are given; the words never are."""
    secret = "Marguerite approved the Geelong payroll audit"
    cases = [
        dict(summary=f"{secret} " * 40),
        dict(key_points=[f"{secret} " * 10]),
        dict(key_points=[secret] * (MAXIMUM_KEY_POINTS + 1)),
        dict(key_points={secret: secret}),
    ]
    for case in cases:
        with pytest.raises(SchemaViolation) as caught:
            parse(**case)
        assert "Marguerite" not in str(caught.value) and "Geelong" not in str(caught.value), case


# --- A section's reply is not a classification, and the other way round ---------------------


def test_a_section_reply_carrying_a_classification_is_refused():
    """A section is summarised, not classified: the three classification keys are unexpected."""
    with pytest.raises(SchemaViolation) as caught:
        parse_section_summary(reply_text(CLASSIFICATION_PART, SUMMARY, KEY_POINTS))
    assert str(caught.value) == "3 unexpected top-level key(s)"


def test_a_section_shaped_reply_is_not_a_classification():
    with pytest.raises(SchemaViolation, match=r"missing top-level key\(s\): \['department', 'doc_type', 'tags'\]"):
        parse_classification(reply_text({}, SUMMARY, KEY_POINTS), SCHEME)


@pytest.mark.parametrize(
    "raw",
    [
        f"```json\n{reply_text({}, SUMMARY, KEY_POINTS)}\n```",
        f"Here is the summary:\n{reply_text({}, SUMMARY, KEY_POINTS)}\nI hope that helps.",
        '{"summary": "' + SUMMARY + '", "key_points": ["A point.",],}',
    ],
    ids=["a code fence", "prose around the object", "trailing commas"],
)
def test_the_section_parser_makes_the_same_three_repairs(raw):
    assert parse_section_summary(raw).summary == SUMMARY


@pytest.mark.parametrize(
    "raw,because",
    [
        ("", "empty response"),
        ("The section describes travel.", "no JSON object"),
        ('{"summary": "A summary."', "unbalanced"),
        ('{"summary": "A summary." "key_points": ["A point."]}', "not valid JSON"),
        ("[1, 2]", "no JSON object"),
    ],
)
def test_the_section_parser_repairs_nothing_else(raw, because):
    with pytest.raises(SchemaViolation, match=because):
        parse_section_summary(raw)


def test_the_section_parser_refuses_a_non_string_reply():
    with pytest.raises(SchemaViolation, match="empty response"):
        parse_section_summary(None)


# --- A repeated key is refused, never read as json's last value (21 November 2026) ----------
#
# json.loads keeps the LAST of two equal keys. Until the review of D-139 a reply carrying an
# over-long summary and then a short one conformed: the refused value was dropped unseen, a fourth
# repair where invariant 10 allows three. Both parsers now refuse the object whole.

REPEATED = "a JSON object repeats a key"
RAW = pytest.mark.parametrize(
    "base,parse_raw",
    [(CLASSIFICATION_PART, lambda raw: parse_classification(raw, SCHEME)), ({}, parse_section_summary)],
    ids=["classification", "section"],
)


def repeated(base: dict, key: str, first, last, *, spelling: str | None = None, closing: str = "}") -> str:
    """A reply holding ``key`` twice, ``first`` in its place and ``last`` spliced in before the
    closing brace, which json.dumps cannot write. ``spelling`` is how the second key is written."""
    text = json.dumps({**base, "summary": SUMMARY, "key_points": KEY_POINTS, key: first})
    return text[:-1] + f", {spelling or json.dumps(key)}: {json.dumps(last)}{closing}"


@RAW
@pytest.mark.parametrize(
    "key,refused,conforming",
    [
        ("summary", "s" * (MAXIMUM_SUMMARY_CHARACTERS + 1), SUMMARY),
        ("key_points", [f"Point {n}." for n in range(MAXIMUM_KEY_POINTS + 1)], ["One point."]),
    ],
    ids=["an over-long summary, then a short one", "six key points, then one"],
)
def test_a_repeated_key_is_refused_and_never_read_as_its_last_value(base, parse_raw, key, refused, conforming):
    raw = repeated(base, key, refused, conforming)
    assert json.loads(raw)[key] == conforming  # what json alone reads, and what used to conform

    with pytest.raises(SchemaViolation) as caught:
        parse_raw(raw)
    assert str(caught.value) == REPEATED  # fixed: it quotes neither value nor the key


@RAW
def test_a_key_repeated_with_the_same_value_is_refused_too(base, parse_raw):
    """Neither value is chosen, so whether the two agree is never asked."""
    with pytest.raises(SchemaViolation) as caught:
        parse_raw(repeated(base, "summary", SUMMARY, SUMMARY))
    assert str(caught.value) == REPEATED


@RAW
def test_a_key_repeated_through_an_escape_is_the_same_key(base, parse_raw):
    """Keys are compared as decoded: "summ\\u0061ry" is "summary"."""
    raw = repeated(base, "summary", "s" * (MAXIMUM_SUMMARY_CHARACTERS + 1), "Short.", spelling='"summ\\u0061ry"')
    assert json.loads(raw)["summary"] == "Short."

    with pytest.raises(SchemaViolation) as caught:
        parse_raw(raw)
    assert str(caught.value) == REPEATED


@RAW
def test_a_repeated_key_is_refused_after_the_trailing_comma_repair_too(base, parse_raw):
    """The comma before the closing brace stops the first decode before that object's keys are
    checked, so the repaired text's decode must refuse the repeat as well."""
    raw = repeated(base, "summary", "s" * (MAXIMUM_SUMMARY_CHARACTERS + 1), "Short.", closing=",}")
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)  # the repair really is needed to read it

    with pytest.raises(SchemaViolation) as caught:
        parse_raw(raw)
    assert str(caught.value) == REPEATED


# --- The schema objects say what the parsers enforce ----------------------------------------


@pytest.mark.parametrize("schema", [CLASSIFICATION_SCHEMA, SECTION_SUMMARY_SCHEMA], ids=["classification", "section"])
def test_the_schema_declares_the_bounds_the_parser_holds(schema):
    """The schema is documentation the parser is written against, not executed (no jsonschema
    dependency), so its numbers are tied here to the constants the parser uses."""
    assert {"summary", "key_points"} <= set(schema["required"])
    assert schema["properties"]["summary"] == {
        "type": "string", "minLength": 1, "maxLength": MAXIMUM_SUMMARY_CHARACTERS,
    }
    assert schema["properties"]["key_points"] == {
        "type": "array",
        "minItems": 1,
        "maxItems": MAXIMUM_KEY_POINTS,
        "items": {"type": "string", "minLength": 1, "maxLength": MAXIMUM_KEY_POINT_CHARACTERS},
    }


def test_the_section_schema_has_exactly_the_two_keys():
    assert sorted(SECTION_SUMMARY_SCHEMA["required"]) == ["key_points", "summary"]
    assert sorted(SECTION_SUMMARY_SCHEMA["properties"]) == ["key_points", "summary"]
    assert SECTION_SUMMARY_SCHEMA["additionalProperties"] is False


def test_the_bounds_are_the_contracts():
    """D-139's values. A change to one is a decision, so this fails until the decision is recorded."""
    assert (MAXIMUM_KEY_POINTS, MAXIMUM_SUMMARY_CHARACTERS, MAXIMUM_KEY_POINT_CHARACTERS) == (5, 600, 200)
