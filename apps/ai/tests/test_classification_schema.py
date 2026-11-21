"""The classification parser (apps/ai/classification.py): what it repairs, what it refuses (FR-10).

The same three repairs as the statement parser — a code fence, a sentence of preamble, a
trailing comma — reached through the same code (the public aliases in apps/ai/schema.py), and
nothing beyond them. Every refusal below is a failed attempt in the loop, never a partial
classification (invariant 10); the one that matters most is a ``doc_type`` outside the fixed
list, which FR-10 says must come from that list and not be generated freely.

No provider, no network, no database: a pure function over a string and a scheme.

Since D-139 (21 November 2026) the reply has five keys, not three: ``summary`` and ``key_points``
are required. Every reply built here carries a conforming pair, so each case below still fails on
the thing it names and not on a missing key. What the parser accepts and refuses of the summary
and the key points themselves is in test_classification_summary_schema.py.
"""

import json
import math
import sys

import pytest

import apps.ai.classification as classification
import apps.ai.schema as schema
from apps.ai.base import Assignment, TagScheme, TagSuggestion
from apps.ai.classification import (
    CLASSIFICATION_SCHEMA,
    MAXIMUM_TAG_SUGGESTIONS,
    ParsedClassification,
    parse_classification,
)
from apps.ai.schema import SchemaViolation
from apps.core.constants import DOCUMENT_TYPES, REPOSITORY_TAG_DIMENSIONS

SCHEME = TagScheme(
    doc_types=DOCUMENT_TYPES,
    departments=("Finance", "Human Resources"),
    tags={
        "Project": ("atlas", "office move"),
        "Process": ("onboarding",),
        "Topic": ("safety", "finance"),
    },
)


SUMMARY = "Staff book business travel through the approved agent."
KEY_POINTS = ("Meals are reimbursed at the daily rate.",)


def reply(
    *,
    doc_type="Policy",
    type_confidence=0.9,
    department="Finance",
    department_confidence=0.7,
    tags=(("Process", "onboarding", 0.8),),
    summary=SUMMARY,
    key_points=KEY_POINTS,
) -> str:
    """A conforming reply; ``tags`` is a sequence of ``(dimension, value, confidence)`` triples."""
    return json.dumps(
        {
            "doc_type": {"value": doc_type, "confidence": type_confidence},
            "department": {"value": department, "confidence": department_confidence},
            "tags": [{"dimension": d, "value": v, "confidence": c} for d, v, c in tags],
            "summary": summary,
            "key_points": list(key_points),
        }
    )


VALID = reply()

# A conforming summary and key points, as the text that closes a hand-written reply (D-139).
SUMMARY_TAIL = f', "summary": {json.dumps(SUMMARY)}, "key_points": {json.dumps(list(KEY_POINTS))}}}'


def with_summary(raw: str) -> str:
    """``raw``, a hand-written JSON object, with a conforming summary and key points added.

    The cases below are written out as text so that each shows the exact malformation it is
    about. Since D-139 a reply without the two keys is refused for THAT, before the parser reaches
    anything else, so every case about something else carries them."""
    assert raw.endswith("}"), raw
    return raw[:-1] + SUMMARY_TAIL


# --- The happy path ------------------------------------------------------------------------


def test_a_conforming_reply_parses_into_the_five_parts():
    parsed = parse_classification(VALID, SCHEME)

    assert isinstance(parsed, ParsedClassification)
    assert parsed.doc_type == Assignment(value="Policy", confidence=0.9)
    assert parsed.department == Assignment(value="Finance", confidence=0.7)
    assert parsed.tags == (TagSuggestion(dimension="Process", value="onboarding", confidence=0.8),)
    assert parsed.summary == SUMMARY  # D-139
    assert parsed.key_points == KEY_POINTS and isinstance(parsed.key_points, tuple)


def test_an_empty_tag_array_is_a_valid_reply():
    """Rule 7 asks for it when the document is clearly about none of the listed values."""
    parsed = parse_classification(reply(tags=()), SCHEME)
    assert parsed.tags == ()


def test_integer_confidences_at_the_bounds_are_accepted_as_floats():
    parsed = parse_classification(
        reply(type_confidence=1, department_confidence=0, tags=(("Topic", "safety", 1),)), SCHEME
    )
    assert parsed.doc_type.confidence == 1.0 and isinstance(parsed.doc_type.confidence, float)
    assert parsed.department.confidence == 0.0
    assert parsed.tags[0].confidence == 1.0


def test_every_document_type_in_the_scheme_is_accepted():
    for doc_type in DOCUMENT_TYPES:
        assert parse_classification(reply(doc_type=doc_type), SCHEME).doc_type.value == doc_type


def test_a_department_outside_the_scheme_is_returned_as_suggested():
    """Whether it is in the scheme is the application's decision (D-105), not the parser's."""
    parsed = parse_classification(reply(department="Catering"), SCHEME)
    assert parsed.department.value == "Catering"


def test_a_tag_value_outside_the_scheme_is_returned_as_suggested():
    """A new Topic is allowed by the prompt and judged by the application; the parser passes it on."""
    parsed = parse_classification(reply(tags=(("Topic", "ergonomics", 0.6),)), SCHEME)
    assert parsed.tags == (TagSuggestion(dimension="Topic", value="ergonomics", confidence=0.6),)


def test_several_tags_keep_their_order():
    parsed = parse_classification(
        reply(tags=(("Topic", "safety", 0.9), ("Project", "atlas", 0.5), ("Process", "onboarding", 0.4))),
        SCHEME,
    )
    assert [t.value for t in parsed.tags] == ["safety", "atlas", "onboarding"]


# --- What it repairs, and nothing beyond ----------------------------------------------------


def test_a_markdown_code_fence_is_stripped():
    assert parse_classification(f"```json\n{VALID}\n```", SCHEME).doc_type.value == "Policy"
    assert parse_classification(f"```\n{VALID}\n```", SCHEME).doc_type.value == "Policy"


def test_prose_around_the_object_is_discarded():
    raw = f"Certainly! Here is the classification:\n{VALID}\nLet me know if you need more."
    assert parse_classification(raw, SCHEME).department.value == "Finance"


def test_a_trailing_comma_is_repaired():
    raw = (
        '{"doc_type": {"value": "Report", "confidence": 0.8,}, '
        '"department": {"value": "Finance", "confidence": 0.5}, "tags": [], '
        '"summary": "A quarterly report.", "key_points": ["Spending fell.",],}'
    )
    parsed = parse_classification(raw, SCHEME)
    assert parsed.doc_type.value == "Report"
    assert parsed.key_points == ("Spending fell.",)  # the comma inside the array went too


def test_a_brace_inside_a_string_does_not_end_the_object():
    raw = reply(department="Finance {Group}")
    assert parse_classification(raw, SCHEME).department.value == "Finance {Group}"


# Text inside a JSON string is never repaired (16 November 2026, D-136): the statement parser's
# three tests of it, through this parser (apps/ai/tests/test_schema.py has the history).


def test_a_code_block_quoted_in_a_value_is_not_a_fence():
    value = "build ```make release``` steps"

    parsed = parse_classification(reply(tags=(("Topic", value, 0.6),)), SCHEME)

    assert parsed.tags[0].value == value


def test_a_fence_inside_a_value_does_not_close_the_reply_s_fence():
    raw = f"```json\n{reply(department='Platform ``` Engineering')}\n```"

    assert parse_classification(raw, SCHEME).department.value == "Platform ``` Engineering"


def test_the_trailing_comma_repair_leaves_values_alone():
    raw = (
        '{"doc_type": {"value": "Report", "confidence": 0.8,}, '
        '"department": {"value": "Finance, }", "confidence": 0.5}, '
        '"tags": [{"dimension": "Topic", "value": "budget [q1, ]", "confidence": 0.4}], '
        '"summary": "Spending by quarter [q1, ], then by team.", "key_points": ["Totals {net, }."],}'
    )

    parsed = parse_classification(raw, SCHEME)

    assert parsed.department.value == "Finance, }"
    assert parsed.tags[0].value == "budget [q1, ]"
    assert parsed.summary == "Spending by quarter [q1, ], then by team."  # D-139: a summary is a string too
    assert parsed.key_points == ("Totals {net, }.",)


def test_values_are_stripped_of_surrounding_whitespace_only():
    raw = reply(doc_type=" Policy ", department="  Finance ", tags=(("Topic", " Supplier  Review ", 0.5),))
    parsed = parse_classification(raw, SCHEME)
    assert parsed.doc_type.value == "Policy"
    assert parsed.department.value == "Finance"
    assert parsed.tags[0].value == "Supplier  Review"  # internal spacing is the model's, kept


def test_the_repairs_are_the_statement_parsers_own_code():
    """One definition of what is repaired: the public names are the private helpers, and this
    module imports them. The decode step joined them on 13 November 2026. The trailing-comma
    repair became a function on 16 November (D-136), and its regex's name is gone."""
    assert schema.strip_code_fences is schema._strip_code_fences
    assert schema.outermost_json_object is schema._outermost_json_object
    assert schema.remove_trailing_commas is schema._remove_trailing_commas
    assert schema.loads_reply is schema._loads_reply
    assert classification.strip_code_fences is schema.strip_code_fences
    assert classification.outermost_json_object is schema.outermost_json_object
    assert classification.remove_trailing_commas is schema.remove_trailing_commas
    assert classification.loads_reply is schema.loads_reply
    assert not hasattr(schema, "TRAILING_COMMA_PATTERN")
    assert not hasattr(classification, "TRAILING_COMMA_PATTERN")


# --- Duplicate tags: a shape tolerance, not a repair ----------------------------------------


def test_a_duplicate_tag_keeps_the_first_occurrence():
    """Same dimension, same name after normalise_tag_name (lower case, single spaces)."""
    raw = reply(tags=(("Topic", "Supplier  Review", 0.9), ("Topic", "supplier review", 0.4)))
    parsed = parse_classification(raw, SCHEME)
    assert parsed.tags == (TagSuggestion(dimension="Topic", value="Supplier  Review", confidence=0.9),)


def test_the_same_name_in_two_dimensions_is_two_tags():
    raw = reply(tags=(("Topic", "finance", 0.9), ("Project", "finance", 0.4)))
    assert [t.dimension for t in parse_classification(raw, SCHEME).tags] == ["Topic", "Project"]


def test_the_cap_is_counted_before_duplicates_are_dropped():
    """The array is held to maxItems as returned: a reply listing one tag nine times is refused,
    not collapsed into one."""
    raw = reply(tags=tuple(("Topic", "safety", 0.5) for _ in range(MAXIMUM_TAG_SUGGESTIONS + 1)))
    with pytest.raises(SchemaViolation, match="more than the"):
        parse_classification(raw, SCHEME)


# --- What it refuses (each one is a failed attempt, never a partial classification) ---------


def test_a_doc_type_outside_the_scheme_is_a_violation():
    """FR-10: the type is selected from a fixed list, never generated freely. A reply with a type
    outside it is not a classification with a correctable field; the whole reply is refused."""
    with pytest.raises(SchemaViolation, match="not one of the scheme's document types"):
        parse_classification(reply(doc_type="Memo"), SCHEME)


def test_the_doc_type_check_is_exact_not_case_insensitive():
    with pytest.raises(SchemaViolation, match="document types"):
        parse_classification(reply(doc_type="policy"), SCHEME)


def test_the_scheme_passed_wins_over_the_fixed_list():
    """A scheme listing fewer types than DOCUMENT_TYPES is what the prompt showed the model."""
    narrow = TagScheme(doc_types=("Report",), departments=(), tags={})
    assert parse_classification(reply(doc_type="Report"), narrow).doc_type.value == "Report"
    with pytest.raises(SchemaViolation, match="document types"):
        parse_classification(reply(doc_type="Policy"), narrow)


@pytest.mark.parametrize(
    "value,because",
    [
        (1.2, "outside"),
        (-0.1, "outside"),
        ("0.8", "non-numeric"),
        (True, "non-numeric"),
        (None, "non-numeric"),
        ([0.8], "non-numeric"),
    ],
    ids=["1.2", "-0.1", "string", "bool", "null", "list"],
)
def test_a_confidence_outside_zero_to_one_or_not_a_number_is_a_violation(value, because):
    with pytest.raises(SchemaViolation, match=because):
        parse_classification(reply(type_confidence=value), SCHEME)
    with pytest.raises(SchemaViolation, match=because):
        parse_classification(reply(department_confidence=value), SCHEME)
    with pytest.raises(SchemaViolation, match=because):
        parse_classification(reply(tags=(("Topic", "safety", value),)), SCHEME)


def test_a_nan_confidence_is_a_violation():
    """json.loads admits NaN; a comparison against the bounds does not."""
    raw = VALID.replace('"confidence": 0.9', '"confidence": NaN')
    assert math.isnan(json.loads(raw)["doc_type"]["confidence"])  # it really does parse as NaN
    with pytest.raises(SchemaViolation, match="outside"):
        parse_classification(raw, SCHEME)


@pytest.mark.parametrize(
    "raw,because",
    [
        ("", "empty response"),
        ("   ", "empty response"),
        ("I cannot classify this document.", "no JSON object"),
        ('{"doc_type": {', "unbalanced"),
        ("[1, 2, 3]", "no JSON object"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}}', "missing top-level key"),
        ('{"tags": []}', "missing top-level key"),
        # The unexpected key was "summary" until D-139 made that one of the reply's own.
        (reply()[:-1] + ', "reason": "It reads like a policy."}', "unexpected top-level key"),
        # From here to the "not json" case each reply is whole but for the one thing it is about,
        # so each carries a conforming summary and key points (``with_summary``, D-139).
        (with_summary('{"doc_type": "Policy", "department": {"value": "Finance", "confidence": 0.5}, "tags": []}'), "'doc_type' is str, not an object"),
        (with_summary('{"doc_type": {"value": "Policy"}, "department": {"value": "Finance", "confidence": 0.5}, "tags": []}'), "'doc_type' is missing"),
        # This and tag 0's case below match a count, not "has unexpected key", since 13 November
        # 2026: an unexpected key is counted and never named, because the reply chose its name
        # (test_a_violation_never_quotes_a_key_the_reply_chose, below).
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9, "reason": "x"}, "department": {"value": "Finance", "confidence": 0.5}, "tags": []}'), "'doc_type' has 1 unexpected key"),
        (with_summary('{"doc_type": {"value": "", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": []}'), "empty or non-string 'value'"),
        (with_summary('{"doc_type": {"value": 4, "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": []}'), "empty or non-string 'value'"),
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance"}, "tags": []}'), "'department' is missing"),
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "  ", "confidence": 0.5}, "tags": []}'), "empty or non-string 'value'"),
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": {}}'), "'tags' is dict, not an array"),
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": ["safety"]}'), "tag 0 is str, not an object"),
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "Topic", "value": "safety"}]}'), "tag 0 is missing"),
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "Topic", "value": "safety", "confidence": 0.5, "why": "x"}]}'), "tag 0 has 1 unexpected key"),
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "Department", "value": "Finance", "confidence": 0.5}]}'), "dimension outside"),
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "topic", "value": "safety", "confidence": 0.5}]}'), "dimension outside"),
        (with_summary('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "Topic", "value": "", "confidence": 0.5}]}'), "tag 0 has an empty or non-string 'value'"),
        ("not json {at all", "unbalanced"),
        # Balanced braces, so the object is extracted, and then it is not JSON: a comma is
        # missing between two keys, which no repair here guesses at.
        ('{"doc_type": {"value": "Policy" "confidence": 0.9}, "department": {}, "tags": []}', "not valid JSON"),
    ],
)
def test_a_non_conforming_reply_raises_schema_violation(raw, because):
    with pytest.raises(SchemaViolation, match=because):
        parse_classification(raw, SCHEME)


@pytest.mark.parametrize(
    "raw,read_by_json",
    [
        # A type outside the scheme, then a conforming one: json alone keeps "Policy".
        ('{"doc_type": {"value": "Memo", "confidence": 0.9}, ' + VALID[1:], ("doc_type", "value", "Policy")),
        (VALID.replace('{"value": "Policy"', '{"value": "Memo", "value": "Policy"', 1), ("doc_type", "value", "Policy")),
        (VALID.replace('"confidence": 0.7}', '"confidence": 2, "confidence": 0.7}', 1), ("department", "confidence", 0.7)),
        (
            VALID.replace('{"dimension": "Process"', '{"dimension": "Department", "dimension": "Process"', 1),
            ("tags", "dimension", "Process"),
        ),
    ],
    ids=["a second doc_type", "doc_type's value twice", "department's confidence twice", "a tag's dimension twice"],
)
def test_an_object_that_repeats_a_key_is_a_violation_at_any_depth(raw, read_by_json):
    """json.loads keeps the LAST of two equal keys, so each reply below conformed until 21 November
    2026: the refused value was dropped unseen, a fourth repair where invariant 10 allows three.
    The object is refused whole now, at the top level or nested, with a fixed message that quotes
    nothing (``_reply_object``'s ``unique_keys``; the review of D-139). The summary's and the key
    points' own repeats are in test_classification_summary_schema.py."""
    outer, inner, value = read_by_json
    decoded = json.loads(raw)[outer]
    assert (decoded[0] if outer == "tags" else decoded)[inner] == value  # what json alone reads

    with pytest.raises(SchemaViolation) as caught:
        parse_classification(raw, SCHEME)
    assert str(caught.value) == "a JSON object repeats a key"


def test_more_tags_than_the_cap_is_a_violation_and_nothing_is_trimmed():
    over = tuple(("Topic", f"topic {n}", 0.5) for n in range(MAXIMUM_TAG_SUGGESTIONS + 1))
    with pytest.raises(SchemaViolation, match=f"more than the {MAXIMUM_TAG_SUGGESTIONS} allowed"):
        parse_classification(reply(tags=over), SCHEME)
    # Exactly the cap is fine.
    assert len(parse_classification(reply(tags=over[:MAXIMUM_TAG_SUGGESTIONS]), SCHEME).tags) == MAXIMUM_TAG_SUGGESTIONS


def test_a_non_string_reply_raises_rather_than_crashing():
    with pytest.raises(SchemaViolation, match="empty response"):
        parse_classification(None, SCHEME)


def test_a_violation_message_does_not_quote_the_models_value():
    """The attempt log records the message (apps/ai/attempt_log.py quotes no reply)."""
    with pytest.raises(SchemaViolation) as excinfo:
        parse_classification(reply(doc_type="Confidential Memo About Layoffs"), SCHEME)
    assert "Layoffs" not in str(excinfo.value)


VALID_OBJECT = json.loads(VALID)


@pytest.mark.parametrize(
    "steered,message",
    [
        (lambda key: {**VALID_OBJECT, key: 1}, "1 unexpected top-level key(s)"),
        (
            lambda key: {key: VALID_OBJECT["tags"]},
            # Five keys since D-139: the schema's own names, sorted, and still none of the reply's.
            "missing top-level key(s): ['department', 'doc_type', 'key_points', 'summary', 'tags'] (the reply had 1 key(s))",
        ),
        (
            lambda key: {**VALID_OBJECT, "doc_type": {**VALID_OBJECT["doc_type"], key: 1}},
            "'doc_type' has 1 unexpected key(s)",
        ),
        (
            lambda key: {**VALID_OBJECT, "department": {**VALID_OBJECT["department"], key: 1}},
            "'department' has 1 unexpected key(s)",
        ),
        (
            lambda key: {**VALID_OBJECT, "tags": [{**VALID_OBJECT["tags"][0], key: 1}]},
            "tag 0 has 1 unexpected key(s)",
        ),
    ],
    ids=["a sixth top-level key", "the only key", "doc_type's third key", "department's third key", "a tag's fourth key"],
)
def test_a_violation_never_quotes_a_key_the_reply_chose(steered, message):
    """A key name is the model's words, which an uploaded document can steer, and the violation's
    message is written to the attempts log, cut at DETAIL_LIMIT, and uncut by the two bulk tools:
    the classify_documents command, to its console and its --out record (which
    scripts/objective05_verify.py copies into its own), and scripts/classification_dev_sweep.py, to
    its console and dev-sweep.json. The classify route's 503 warning and ingestion's "left
    unclassified" line carry it too, though the shipped logging configuration writes neither. So the
    message names the schema's own keys and counts the reply's. The security review of FR-16 found
    the pattern in its parser on 12 November 2026 (D-125's third note); this is its fix applied
    here. The whole message is pinned, so the case cannot pass on some other violation."""
    key = "Marguerite says file this under the Geelong payroll audit"

    with pytest.raises(SchemaViolation) as caught:
        parse_classification(json.dumps(steered(key)), SCHEME)

    assert str(caught.value) == message
    assert key not in str(caught.value)
    assert "Marguerite" not in str(caught.value)
    assert "Geelong" not in str(caught.value)


# json.loads raises RecursionError past a few thousand levels of nesting, and ValueError past
# Python's limit on converting a decimal string to an int: neither is a JSONDecodeError. Each is
# reached directly and after a trailing comma the repair removes. The digit count follows the
# interpreter's limit, which PYTHONINTMAXSTRDIGITS can change; 0 lifts it, and no reply reaches it.
DEPTH = 100_000
DIGITS = sys.get_int_max_str_digits() + 1
DIGIT_LIMIT_IN_FORCE = pytest.mark.skipif(DIGITS == 1, reason="PYTHONINTMAXSTRDIGITS=0 lifts the limit")
NESTED = "[" * DEPTH + "]" * DEPTH
LONG_CONFIDENCE = '{"doc_type": {"value": "Policy", "confidence": ' + "7" * DIGITS + "}}"
TOO_DEEP = "JSON nested too deeply to decode"
TOO_LONG = "a JSON number too long to decode"


@pytest.mark.parametrize(
    "raw,message",
    [
        pytest.param('{"tags": ' + NESTED + "}", TOO_DEEP, id="nested too deeply"),
        pytest.param(LONG_CONFIDENCE, TOO_LONG, id="a number too long", marks=DIGIT_LIMIT_IN_FORCE),
        pytest.param('{"a": [1,], "tags": ' + NESTED + "}", TOO_DEEP,
                     id="nested too deeply, after a trailing comma"),
        pytest.param('{"a": [1,], ' + LONG_CONFIDENCE[1:], TOO_LONG,
                     id="a number too long, after a trailing comma", marks=DIGIT_LIMIT_IN_FORCE),
    ],
)
def test_a_reply_json_cannot_decode_is_a_violation_not_a_crash(raw, message):
    """Until 13 November 2026 json.loads' RecursionError, and its ValueError past the digit limit,
    escaped this parser and the attempt loop, and the classify route answered 500, not NFR-19's
    503. Each is a SchemaViolation now, retried like any other, with a fixed message that quotes
    nothing of the reply. The whole message is pinned, so a case cannot pass on another violation."""
    with pytest.raises(SchemaViolation) as caught:
        parse_classification(raw, SCHEME)

    assert str(caught.value) == message


@pytest.mark.parametrize(
    "raw,message",
    [
        pytest.param(reply(department="Finance\x00"), "a NUL character in a JSON string",
                     id="a NUL in the department"),
        pytest.param(reply(tags=(("Topic", "safety\ud800", 0.5),)), "an unpaired surrogate in a JSON string",
                     id="an unpaired surrogate in a tag"),
    ],
)
def test_a_string_nothing_downstream_can_take_is_a_violation(raw, message):
    """A NUL, which PostgreSQL text refuses, or an unpaired surrogate, which it cannot encode,
    decoded fine and then broke apply_classification's write: the classify route answered 500
    until 13 November 2026. Each is a SchemaViolation now."""
    with pytest.raises(SchemaViolation) as caught:
        parse_classification(raw, SCHEME)

    assert str(caught.value) == message


# --- The schema object itself ---------------------------------------------------------------


def test_the_schema_describes_what_the_parser_enforces():
    """The declared shape and the hand-written checks must not drift apart. The schema is not
    executed (no jsonschema dependency), so the keys, the enums and the cap are asserted here.
    Five required keys since D-139; the summary's and the key points' own bounds are asserted in
    test_classification_summary_schema.py, beside the cases that hold the parser to them."""
    assert sorted(CLASSIFICATION_SCHEMA["required"]) == ["department", "doc_type", "key_points", "summary", "tags"]
    assert sorted(CLASSIFICATION_SCHEMA["properties"]) == sorted(CLASSIFICATION_SCHEMA["required"])
    assert CLASSIFICATION_SCHEMA["additionalProperties"] is False
    doc_type = CLASSIFICATION_SCHEMA["properties"]["doc_type"]
    assert sorted(doc_type["required"]) == ["confidence", "value"]
    assert doc_type["additionalProperties"] is False
    assert doc_type["properties"]["value"]["enum"] == list(DOCUMENT_TYPES)
    assert doc_type["properties"]["confidence"] == {"type": "number", "minimum": 0, "maximum": 1}
    department = CLASSIFICATION_SCHEMA["properties"]["department"]
    assert sorted(department["required"]) == ["confidence", "value"]
    assert "enum" not in department["properties"]["value"]  # the application decides (D-105)
    tags = CLASSIFICATION_SCHEMA["properties"]["tags"]
    assert tags["maxItems"] == MAXIMUM_TAG_SUGGESTIONS
    item = tags["items"]
    assert sorted(item["required"]) == ["confidence", "dimension", "value"]
    assert item["additionalProperties"] is False
    assert item["properties"]["dimension"]["enum"] == list(REPOSITORY_TAG_DIMENSIONS) == ["Project", "Process", "Topic"]
