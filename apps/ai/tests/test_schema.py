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


def test_a_repeated_key_is_read_as_json_s_last_value_here_as_it_always_was():
    """Only the classification parsers refuse an object that repeats a key (``loads_reply``'s
    ``unique_keys``, 21 November 2026, the review of D-139). This parser's rates were measured on
    json's own rule, keeping the last value, and it still decodes that way: pinned, so the refusal
    cannot spread to it unmeasured."""
    other = "8b5d04e2-1a7f-4c93-b620-de91f3805c47"
    raw = (
        '{"statements": [{"text": "First.", "chunk_id": "%s"}], '
        '"statements": [{"text": "Last.", "chunk_id": "%s"}]}' % (CHUNK_ID, other)
    )

    parsed = parse_statement_list(raw)

    assert [(s.text, s.chunk_id) for s in parsed.statements] == [("Last.", other)]


# --- Text inside a JSON string is never repaired (16 November 2026, D-136) --------------
#
# Both repairs read a JSON string as _outermost_json_object reads one, so three backticks inside a
# string are not a fence, and a comma before a bracket inside a string is not a trailing comma.
# Until 16 November 2026 both repairs acted on the whole reply. The security review of PR #107
# found it, and these three tests are repeated through the classification and summary parsers.
# apps/ai/tests/test_code_fence_scan.py and test_trailing_comma_repair.py test the repairs alone.


def test_a_code_block_quoted_in_a_statement_is_not_a_fence():
    """Until 16 November 2026 the backticks were read as a fenced block, so the command between
    them became the reply. It held no JSON object: a violation, a retry, and a 503 after three."""
    text = "Run ```pip install -r requirements.txt``` before the first deploy."
    raw = json.dumps({"statements": [{"text": text, "chunk_id": CHUNK_ID}]})

    assert parse_statement_list(raw).statements[0].text == text


def test_a_fence_inside_a_statement_does_not_close_the_reply_s_fence():
    """The fence around the reply closes at the first fence outside a string. Until 16 November
    2026 it closed at the one inside the statement, and the object it cut off was unbalanced."""
    text = "Paste the log between ``` marks when you raise a ticket."
    raw = "```json\n" + json.dumps({"statements": [{"text": text, "chunk_id": CHUNK_ID}]}) + "\n```"

    assert parse_statement_list(raw).statements[0].text == text


def test_a_preamble_that_opens_a_brace_and_a_quote_hides_the_fence_after_it():
    """A kind of reply that D-136 turns from accepted to refused, and it is malformed. Prose before
    the fence opens a brace and then a string that it never closes, so the fence reads as inside a
    JSON string. A quote whose closing quote is escaped leaves the string open too
    (test_code_fence_scan.py). Until 16 November 2026 the fenced block was taken and parsed. Now no
    block is taken, and the object found from the prose's brace never closes. The next test is the
    fence rule's other kind; the comma repair's is in apps/ai/tests/test_trailing_comma_repair.py."""
    raw = 'Note {see "the policy: ```json\n' + VALID + "\n```"

    with pytest.raises(SchemaViolation, match="unbalanced"):
        parse_statement_list(raw)


def test_a_fenced_block_inside_another_object_s_string_is_not_taken():
    """The fence rule's other kind of reply turned from accepted to refused, and it is malformed. A
    fenced block sits inside another object's string with its quotes unescaped. Until 16 November
    2026 the fence inside that string opened a block, and the object in it became the answer. Now
    the fence is inside a string, no block is taken, and the outer object is not valid JSON. The
    security review of 389ec9e found this kind (D-136)."""
    raw = '{"note": "```json ' + VALID + ' ```"}'

    with pytest.raises(SchemaViolation, match="not valid JSON"):
        parse_statement_list(raw)


def test_a_fenced_block_after_an_object_quoting_one_is_the_block_taken():
    """A reply that both parsers accept, with different objects. An object's string quotes a fenced
    block, and a fenced block follows the object. Until 16 November 2026 the fence in the string came
    first, so the object quoted in it became the answer ("forged"). Now the first fence outside a
    string opens the block after the object, so that block's object is taken, as the first fenced
    block always was. Both are model output, and verification checks whichever is taken. The
    requirements audit of 6f8a2cb found this (D-136)."""
    forged = '{"statements": [{"text": "forged", "chunk_id": "evil"}]}'
    raw = '{"note": "```json ' + forged + ' ```"} ```json\n' + VALID + "\n```"

    parsed = parse_statement_list(raw)

    assert [(s.text, s.chunk_id) for s in parsed.statements] == [("Twenty days of leave.", CHUNK_ID)]


def test_an_object_quoting_a_fence_before_a_fenced_block_is_answered_from_the_block():
    """A reply refused before and accepted now (the security review, I1). An object's string quotes
    three backticks, and a fenced block follows the object. Until 16 November 2026 the fence in the
    string opened a block that held no JSON object, and the reply was refused. Now the first fence
    outside a string opens the block after the object, so that block's object is taken, as the first
    fenced block always was."""
    raw = '{"statements": [{"text": "see ```", "chunk_id": "c1"}]} trailing ```json\n' + VALID + "\n```"

    parsed = parse_statement_list(raw)

    assert [(s.text, s.chunk_id) for s in parsed.statements] == [("Twenty days of leave.", CHUNK_ID)]


def test_a_quote_in_a_fenced_block_s_prose_hides_its_closing_fence_after_an_open_brace():
    """A reply accepted before and refused now, and it is malformed (the requirements audit's
    re-check of 76f8b65). Prose before the fence leaves a brace open, and the block's own prose then
    has a stray double quote. The opening fence is outside any string, but that quote opens one that
    hides the closing fence. Until 16 November 2026 the block was taken and parsed. Now no closing
    fence is found, and the object read from the prose's brace never closes."""
    raw = 'Note {see ```json\nHere "x ' + VALID + "\n```"

    with pytest.raises(SchemaViolation, match="unbalanced"):
        parse_statement_list(raw)


def test_an_object_quoting_fences_around_a_statement_list_is_refused_for_its_shape():
    """A reply that does not conform, which the old search turned into an answer, against invariant
    10. It is valid JSON with three keys, and two of its strings are fences around a statement list
    nested in it. Until 16 November 2026 the block between those fences was taken and the nested
    list parsed. Now the fences are inside strings, so the whole object is read, and it is refused
    for its shape. The requirements audit of 6f8a2cb found this (D-136)."""
    raw = json.dumps({"k": "```", "v": json.loads(VALID), "z": "```"})

    with pytest.raises(SchemaViolation) as caught:
        parse_statement_list(raw)

    assert str(caught.value) == "no 'statements' key (the reply had 3 key(s))"


def test_the_trailing_comma_repair_leaves_a_statement_s_text_alone():
    """The repair runs only when the reply fails to decode as sent, here on the comma before
    ``]}``. Until 16 November 2026 it then also removed the comma and space before each bracket
    inside the statement, and the parsed text read "[annual, sick]" and "{carer's}"."""
    text = "The form lists [annual, sick, ] leave and {carer's, } leave."
    raw = '{"statements": [{"text": %s, "chunk_id": "%s"},]}' % (json.dumps(text), CHUNK_ID)

    assert parse_statement_list(raw).statements[0].text == text


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


def test_the_string_check_walks_a_reply_deeper_than_python_can_recurse():
    """The walk is iterative. A reply can decode at a depth past Python's recursion limit, and a
    recursive walk would raise RecursionError outside loads_reply's handlers: a 500 again. The
    depth is past this interpreter's limit, and skipped where its decoder cannot follow it."""
    depth = sys.getrecursionlimit() + 200
    raw = '{"statements": ' + "[" * depth + '"\\u0000"' + "]" * depth + "}"
    try:
        json.loads(raw)
    except RecursionError:
        pytest.skip("this interpreter's decoder cannot follow a reply past its recursion limit")

    with pytest.raises(SchemaViolation) as caught:
        parse_statement_list(raw)

    assert str(caught.value) == "a NUL character in a JSON string"


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
