"""The classification parser (apps/ai/classification.py): what it repairs, what it refuses (FR-10).

The same three repairs as the statement parser — a code fence, a sentence of preamble, a
trailing comma — reached through the same code (the public aliases in apps/ai/schema.py), and
nothing beyond them. Every refusal below is a failed attempt in the loop, never a partial
classification (invariant 10); the one that matters most is a ``doc_type`` outside the fixed
list, which FR-10 says must come from that list and not be generated freely.

No provider, no network, no database: a pure function over a string and a scheme.
"""

import json
import math

import pytest

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


def reply(
    *,
    doc_type="Policy",
    type_confidence=0.9,
    department="Finance",
    department_confidence=0.7,
    tags=(("Process", "onboarding", 0.8),),
) -> str:
    """A conforming reply; ``tags`` is a sequence of ``(dimension, value, confidence)`` triples."""
    return json.dumps(
        {
            "doc_type": {"value": doc_type, "confidence": type_confidence},
            "department": {"value": department, "confidence": department_confidence},
            "tags": [{"dimension": d, "value": v, "confidence": c} for d, v, c in tags],
        }
    )


VALID = reply()


# --- The happy path ------------------------------------------------------------------------


def test_a_conforming_reply_parses_into_the_three_parts():
    parsed = parse_classification(VALID, SCHEME)

    assert isinstance(parsed, ParsedClassification)
    assert parsed.doc_type == Assignment(value="Policy", confidence=0.9)
    assert parsed.department == Assignment(value="Finance", confidence=0.7)
    assert parsed.tags == (TagSuggestion(dimension="Process", value="onboarding", confidence=0.8),)


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
        '"department": {"value": "Finance", "confidence": 0.5}, "tags": [],}'
    )
    assert parse_classification(raw, SCHEME).doc_type.value == "Report"


def test_a_brace_inside_a_string_does_not_end_the_object():
    raw = reply(department="Finance {Group}")
    assert parse_classification(raw, SCHEME).department.value == "Finance {Group}"


def test_values_are_stripped_of_surrounding_whitespace_only():
    raw = reply(doc_type=" Policy ", department="  Finance ", tags=(("Topic", " Supplier  Review ", 0.5),))
    parsed = parse_classification(raw, SCHEME)
    assert parsed.doc_type.value == "Policy"
    assert parsed.department.value == "Finance"
    assert parsed.tags[0].value == "Supplier  Review"  # internal spacing is the model's, kept


def test_the_repairs_are_the_statement_parsers_own_code():
    """One definition of what is repaired: the public names are the private helpers."""
    assert schema.strip_code_fences is schema._strip_code_fences
    assert schema.outermost_json_object is schema._outermost_json_object
    assert schema.TRAILING_COMMA_PATTERN is schema._TRAILING_COMMA


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
        (reply()[:-1] + ', "summary": "A policy."}', "unexpected top-level key"),
        ('{"doc_type": "Policy", "department": {"value": "Finance", "confidence": 0.5}, "tags": []}', "'doc_type' is str, not an object"),
        ('{"doc_type": {"value": "Policy"}, "department": {"value": "Finance", "confidence": 0.5}, "tags": []}', "'doc_type' is missing"),
        # This and tag 0's case below match a count, not "has unexpected key", since 13 November
        # 2026: an unexpected key is counted and never named, because the reply chose its name
        # (test_a_violation_never_quotes_a_key_the_reply_chose, below).
        ('{"doc_type": {"value": "Policy", "confidence": 0.9, "reason": "x"}, "department": {"value": "Finance", "confidence": 0.5}, "tags": []}', "'doc_type' has 1 unexpected key"),
        ('{"doc_type": {"value": "", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": []}', "empty or non-string 'value'"),
        ('{"doc_type": {"value": 4, "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": []}', "empty or non-string 'value'"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance"}, "tags": []}', "'department' is missing"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "  ", "confidence": 0.5}, "tags": []}', "empty or non-string 'value'"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": {}}', "'tags' is dict, not an array"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": ["safety"]}', "tag 0 is str, not an object"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "Topic", "value": "safety"}]}', "tag 0 is missing"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "Topic", "value": "safety", "confidence": 0.5, "why": "x"}]}', "tag 0 has 1 unexpected key"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "Department", "value": "Finance", "confidence": 0.5}]}', "dimension outside"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "topic", "value": "safety", "confidence": 0.5}]}', "dimension outside"),
        ('{"doc_type": {"value": "Policy", "confidence": 0.9}, "department": {"value": "Finance", "confidence": 0.5}, "tags": [{"dimension": "Topic", "value": "", "confidence": 0.5}]}', "tag 0 has an empty or non-string 'value'"),
        ("not json {at all", "unbalanced"),
        # Balanced braces, so the object is extracted, and then it is not JSON: a comma is
        # missing between two keys, which no repair here guesses at.
        ('{"doc_type": {"value": "Policy" "confidence": 0.9}, "department": {}, "tags": []}', "not valid JSON"),
    ],
)
def test_a_non_conforming_reply_raises_schema_violation(raw, because):
    with pytest.raises(SchemaViolation, match=because):
        parse_classification(raw, SCHEME)


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
            "missing top-level key(s): ['department', 'doc_type', 'tags'] (the reply had 1 key(s))",
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
    ids=["a fourth top-level key", "the only key", "doc_type's third key", "department's third key", "a tag's fourth key"],
)
def test_a_violation_never_quotes_a_key_the_reply_chose(steered, message):
    """A key name is the model's words, which an uploaded document can steer, and the violation's
    message reaches the attempts log and the lines a failed classification writes: the classify
    route's 503 warning and ingestion's "left unclassified", neither cut at DETAIL_LIMIT. So the
    message names the schema's own keys and counts the reply's. The security review of FR-16
    found the pattern in its parser on 12 November 2026 (D-125's third note); this is its fix
    applied here. The whole message is pinned, so the case cannot pass on some other violation."""
    key = "Marguerite says file this under the Geelong payroll audit"

    with pytest.raises(SchemaViolation) as caught:
        parse_classification(json.dumps(steered(key)), SCHEME)

    assert str(caught.value) == message
    assert key not in str(caught.value)
    assert "Marguerite" not in str(caught.value)
    assert "Geelong" not in str(caught.value)


# --- The schema object itself ---------------------------------------------------------------


def test_the_schema_describes_what_the_parser_enforces():
    """The declared shape and the hand-written checks must not drift apart. The schema is not
    executed (no jsonschema dependency), so the keys, the enums and the cap are asserted here."""
    assert sorted(CLASSIFICATION_SCHEMA["required"]) == ["department", "doc_type", "tags"]
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
