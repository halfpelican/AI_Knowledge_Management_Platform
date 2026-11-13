"""The tolerant parser (apps/ai/schema.py): what it repairs, and what it refuses.

Moved from scripts/citation_harness.py at Stage 4 item 5 and given the tests it never
had while it lived in scripts/. The malformations exercised here are the ones a small
local model actually produces — a code fence, a sentence of preamble, a trailing comma —
and the refusals are everything else, because a parser that repairs too much turns a
wrong answer into a plausible one.

No provider, no network, no database: this is a pure function over a string.
"""

import json
import sys

import pytest

from apps.ai.base import StatementList
from apps.ai.schema import STATEMENT_LIST_SCHEMA, SchemaViolation, parse_statement_list

CHUNK_ID = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
VALID = json.dumps({"statements": [{"text": "Twenty days of leave.", "chunk_id": CHUNK_ID}]})


# --- The happy path ---------------------------------------------------------------------


def test_a_conforming_reply_parses_into_statements():
    parsed = parse_statement_list(VALID)

    assert isinstance(parsed, StatementList)
    assert len(parsed.statements) == 1
    assert parsed.statements[0].text == "Twenty days of leave."
    assert parsed.statements[0].chunk_id == CHUNK_ID


def test_an_empty_statement_list_is_a_valid_response_not_a_violation():
    """``{"statements": []}`` is the model correctly saying the passages do not answer.

    This one matters more than it looks. If it were treated as a violation it would be
    retried three times and then raise a 503 — turning the model's most honest possible
    reply into an outage, and destroying the evidence for no-answer path B, which is the
    project's main quality signal (invariant 7).
    """
    parsed = parse_statement_list('{"statements": []}')

    assert parsed.statements == []


def test_several_statements_keep_their_order_and_their_own_identifiers():
    other = "8b5d04e2-1a7f-4c93-b620-de91f3805c47"
    raw = json.dumps(
        {
            "statements": [
                {"text": "First.", "chunk_id": CHUNK_ID},
                {"text": "Second.", "chunk_id": other},
            ]
        }
    )

    parsed = parse_statement_list(raw)

    assert [s.text for s in parsed.statements] == ["First.", "Second."]
    assert [s.chunk_id for s in parsed.statements] == [CHUNK_ID, other]


# --- What it repairs, and nothing beyond ------------------------------------------------


def test_a_markdown_code_fence_is_stripped():
    assert parse_statement_list(f"```json\n{VALID}\n```").statements[0].chunk_id == CHUNK_ID
    assert parse_statement_list(f"```\n{VALID}\n```").statements[0].chunk_id == CHUNK_ID


def test_prose_around_the_object_is_discarded():
    raw = f"Certainly! Here is the JSON you asked for:\n{VALID}\nLet me know if you need more."
    assert parse_statement_list(raw).statements[0].text == "Twenty days of leave."


def test_a_trailing_comma_is_repaired():
    raw = '{"statements": [{"text": "Twenty days.", "chunk_id": "%s"},]}' % CHUNK_ID
    assert parse_statement_list(raw).statements[0].chunk_id == CHUNK_ID


def test_a_brace_inside_a_string_does_not_end_the_object():
    raw = json.dumps({"statements": [{"text": "Use {braces} carefully.", "chunk_id": CHUNK_ID}]})
    assert parse_statement_list(raw).statements[0].text == "Use {braces} carefully."


def test_text_and_identifiers_are_stripped_of_surrounding_whitespace():
    raw = json.dumps({"statements": [{"text": "  Padded.  ", "chunk_id": f" {CHUNK_ID} "}]})
    parsed = parse_statement_list(raw)
    assert parsed.statements[0].text == "Padded."
    assert parsed.statements[0].chunk_id == CHUNK_ID


# --- What it refuses (each one is a failed attempt, never a partial answer) --------------


@pytest.mark.parametrize(
    "raw,because",
    [
        ("", "empty response"),
        ("   ", "empty response"),
        ("I am afraid I cannot answer that.", "no JSON object"),
        ('{"statements": [', "unbalanced"),
        ("[1, 2, 3]", "no JSON object"),  # no brace at all, so nothing to extract
        ('{"statements": {}}', "not an array"),
        ('{"answers": []}', "no 'statements' key"),
        ('{"statements": [], "note": "hi"}', "unexpected top-level key"),
        ('{"statements": ["a sentence"]}', "not an object"),
        ('{"statements": [{"text": "No id."}]}', "missing"),
        ('{"statements": [{"chunk_id": "x"}]}', "missing"),
        ('{"statements": [{"text": "t", "chunk_id": "x", "score": 1}]}', "unexpected key"),
        ('{"statements": [{"text": "", "chunk_id": "x"}]}', "empty or non-string 'text'"),
        ('{"statements": [{"text": "t", "chunk_id": ""}]}', "empty or non-string 'chunk_id'"),
        ('{"statements": [{"text": 42, "chunk_id": "x"}]}', "empty or non-string 'text'"),
        ('{"statements": [{"text": "t", "chunk_id": 7}]}', "empty or non-string 'chunk_id'"),
        ('{"statements": "none"}', "not an array"),
        ("not json {at all", "unbalanced"),
        # Balanced braces, so the object is extracted, and then it is not JSON: a comma
        # is missing between the two keys, which no repair here guesses at.
        ('{"statements": [{"text": "t" "chunk_id": "x"}]}', "not valid JSON"),
    ],
)
def test_a_non_conforming_reply_raises_schema_violation(raw, because):
    with pytest.raises(SchemaViolation, match=because):
        parse_statement_list(raw)


def test_a_non_string_reply_raises_rather_than_crashing():
    """The provider returns a string; None would mean a bug upstream, not an answer."""
    with pytest.raises(SchemaViolation, match="empty response"):
        parse_statement_list(None)


def test_a_json_array_at_the_top_level_is_refused():
    """Refused rather than unwrapped: guessing at a shape is how a wrong answer gets in."""
    with pytest.raises(SchemaViolation):
        parse_statement_list('[{"text": "t", "chunk_id": "x"}]')


VALID_OBJECT = json.loads(VALID)


@pytest.mark.parametrize(
    "steered,message",
    [
        (lambda key: {**VALID_OBJECT, key: 1}, "1 unexpected top-level key(s)"),
        (lambda key: {**VALID_OBJECT, key: 1, f"{key}, again": 2}, "2 unexpected top-level key(s)"),
        (lambda key: {key: VALID_OBJECT["statements"]}, "no 'statements' key (the reply had 1 key(s))"),
        (
            lambda key: {"statements": [{**VALID_OBJECT["statements"][0], key: 1}]},
            "statement 0 has 1 unexpected key(s)",
        ),
    ],
    ids=["a second top-level key", "two more top-level keys", "the only key", "a statement's third key"],
)
def test_a_violation_never_quotes_a_key_the_reply_chose(steered, message):
    """A key name is the model's words, which a retrieved passage can steer, and the violation's
    message reaches the attempts log and the ask's 503 line (apps/ai/attempt_log.py). So the
    message names the schema's own keys and counts the reply's. The security review of FR-16
    found the pattern in its parser on 12 November 2026 (D-125's third note); this is its fix
    applied here. The whole message is pinned, so the case cannot pass on some other violation."""
    key = "Marguerite confirmed the Geelong site closes in June"

    with pytest.raises(SchemaViolation) as caught:
        parse_statement_list(json.dumps(steered(key)))

    assert str(caught.value) == message
    assert key not in str(caught.value)
    assert "Marguerite" not in str(caught.value)
    assert "Geelong" not in str(caught.value)


# --- A reply json.loads cannot decode (13 November 2026) --------------------------------

# json.loads raises RecursionError past a few thousand levels of nesting, and ValueError past
# Python's limit on converting a decimal string to an int: neither is a JSONDecodeError. Each is
# reached directly and after a trailing comma the repair removes, so the repair's own decode is
# held to the same rule. The digit count follows the interpreter's limit, which
# PYTHONINTMAXSTRDIGITS can change; 0 lifts it, and then no reply can reach it.
DEPTH = 100_000
DIGITS = sys.get_int_max_str_digits() + 1
DIGIT_LIMIT_IN_FORCE = pytest.mark.skipif(DIGITS == 1, reason="PYTHONINTMAXSTRDIGITS=0 lifts the limit")
NESTED = "[" * DEPTH + "]" * DEPTH
NUMBER = "7" * DIGITS
TOO_DEEP = "JSON nested too deeply to decode"
TOO_LONG = "a JSON number too long to decode"


@pytest.mark.parametrize(
    "raw,message",
    [
        pytest.param('{"statements": ' + NESTED + "}", TOO_DEEP, id="nested too deeply"),
        pytest.param('{"statements": [], "n": ' + NUMBER + "}", TOO_LONG, id="a number too long",
                     marks=DIGIT_LIMIT_IN_FORCE),
        pytest.param('{"a": [1,], "statements": ' + NESTED + "}", TOO_DEEP,
                     id="nested too deeply, after a trailing comma"),
        pytest.param('{"a": [1,], "statements": [], "n": ' + NUMBER + "}", TOO_LONG,
                     id="a number too long, after a trailing comma", marks=DIGIT_LIMIT_IN_FORCE),
    ],
)
def test_a_reply_json_cannot_decode_is_a_violation_not_a_crash(raw, message):
    """Until 13 November 2026 json.loads' RecursionError, and its ValueError past the digit limit,
    escaped this parser and the attempt loop, and POST /api/ask answered 500, not NFR-19's 503.
    Each is a SchemaViolation now, retried like any other, with a fixed message that quotes nothing
    of the reply. The whole message is pinned, so a case cannot pass on some other violation."""
    with pytest.raises(SchemaViolation) as caught:
        parse_statement_list(raw)

    assert str(caught.value) == message


@pytest.mark.parametrize(
    "raw,message",
    [
        pytest.param(json.dumps({"statements": [{"text": "Twenty days.\x00", "chunk_id": CHUNK_ID}]}),
                     "a NUL character in a JSON string", id="a NUL in a statement"),
        pytest.param(json.dumps({"statements": [{"text": "Twenty days.\ud800", "chunk_id": CHUNK_ID}]}),
                     "an unpaired surrogate in a JSON string", id="an unpaired surrogate in a statement"),
        pytest.param(json.dumps({"statements": [], "\x00": 1}), "a NUL character in a JSON string",
                     id="a NUL in a key"),
        pytest.param('{"a": [1,], "statements": [{"text": "t\\udc00", "chunk_id": "x"}]}',
                     "an unpaired surrogate in a JSON string",
                     id="an unpaired surrogate, after a trailing comma"),
    ],
)
def test_a_string_nothing_downstream_can_take_is_a_violation(raw, message):
    """A NUL, which PostgreSQL text refuses, or an unpaired surrogate, which neither the database
    nor DRF's renderer can encode, decoded fine and then broke the answer's QueryLog write or its
    rendering: POST /api/ask answered 500 until 13 November 2026. Each is a SchemaViolation now."""
    with pytest.raises(SchemaViolation) as caught:
        parse_statement_list(raw)

    assert str(caught.value) == message


def test_an_escaped_surrogate_pair_is_one_character_and_parses():
    """json.loads joins an escaped pair into the one character it stands for, so only an unpaired
    surrogate is refused, and a reply with an emoji in it still parses."""
    raw = json.dumps({"statements": [{"text": "Twenty days \U0001F600", "chunk_id": CHUNK_ID}]})
    assert "\\ud83d\\ude00" in raw  # the pair really is escaped in the reply

    assert parse_statement_list(raw).statements[0].text == "Twenty days \U0001F600"


# --- The schema object itself -----------------------------------------------------------


def test_the_schema_describes_what_the_parser_enforces():
    """The declared shape and the hand-written checks must not drift apart.

    The schema is not executed — the project takes no jsonschema dependency for one small
    shape — so this asserts the two agree on the keys, which is the part a future edit
    could change in one place and not the other.
    """
    assert STATEMENT_LIST_SCHEMA["required"] == ["statements"]
    assert STATEMENT_LIST_SCHEMA["additionalProperties"] is False
    item = STATEMENT_LIST_SCHEMA["properties"]["statements"]["items"]
    assert sorted(item["required"]) == ["chunk_id", "text"]
    assert item["additionalProperties"] is False
