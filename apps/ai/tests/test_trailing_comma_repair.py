"""The trailing-comma repair removes trailing commas outside JSON strings, and nothing inside one.

Until 16 November 2026 apps/ai/schema.py repaired a reply that failed to decode with
``re.sub(r",\\s*(?=[}\\]])", "", candidate)``, over the whole object, strings included. So "a, ]" in
a string decoded as "a]". A raw newline between a comma and a bracket in a string, which JSON
forbids, was deleted, and the reply passed. The security review of PR #107 found it. Since then
the repair is ``remove_trailing_commas``, a scan that skips strings (D-136). All three parsers call
it: FR-12's statements, FR-10's classification and FR-16's summary.

Outside strings it must remove exactly what the regex removed, so that it changes nothing else
the parser accepts. So the regex is copied below, frozen, and the scan is held to it:
- on named cases, each pinning what the regex gave as well;
- exactly, on every string of up to seven characters over a comma, two kinds of whitespace, both
  closers and a letter (no double quote, so no string);
- between strings only, on every string of up to seven characters over a comma, a space, a closer,
  a double quote, a backslash and a letter, and on generated objects.

No provider, no network, no database: pure functions over strings.
"""

import itertools
import random
import re
import time

import pytest

from apps.ai.schema import SchemaViolation, parse_statement_list, remove_trailing_commas

# --- The reference: the repair as it was before 16 November 2026 -------------------------------
# Copied verbatim and frozen. Never edit it to make a case pass: it is what "unchanged" means.

TRAILING_COMMA = re.compile(r",\s*(?=[}\]])")


def regex_remove_trailing_commas(candidate: str) -> str:
    return TRAILING_COMMA.sub("", candidate)


def regex_between_strings(candidate: str) -> str:
    """The frozen regex applied to each stretch of ``candidate`` outside a JSON string, each string
    copied as it is. A string opens at a double quote and closes at the next one that no backslash
    escapes. No match of the regex can reach across a quote, so this is the regex with strings left
    alone."""
    pieces = []
    stretch = []
    in_string = escaped = False
    for character in candidate:
        if in_string:
            stretch.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                pieces.append("".join(stretch))
                stretch, in_string = [], False
            continue
        if character == '"':
            pieces.append(regex_remove_trailing_commas("".join(stretch)))
            stretch, in_string = [character], True
        else:
            stretch.append(character)
    tail = "".join(stretch)
    pieces.append(tail if in_string else regex_remove_trailing_commas(tail))
    return "".join(pieces)


# --- Named cases --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "candidate,expected,regex_gave",
    [
        pytest.param('{"a": "x, ]", "b": [1,],}', '{"a": "x, ]", "b": [1]}', '{"a": "x]", "b": [1]}',
                     id="a comma before a bracket inside a string"),
        pytest.param('{"a": "x, }", "b": 1,}', '{"a": "x, }", "b": 1}', '{"a": "x}", "b": 1}',
                     id="a comma before a brace inside a string"),
        pytest.param('{"a": "x,\n]", "b": 1,}', '{"a": "x,\n]", "b": 1}', '{"a": "x]", "b": 1}',
                     id="a raw newline between a comma and a bracket inside a string"),
        pytest.param('{"a": "say \\", ]\\" ok", "b": [1, ]}', '{"a": "say \\", ]\\" ok", "b": [1]}',
                     '{"a": "say \\"]\\" ok", "b": [1]}', id="an escaped quote does not close the string"),
    ],
)
def test_a_trailing_comma_inside_a_json_string_is_left_alone(candidate, expected, regex_gave):
    """Each case pins what the frozen regex gave as well, so it records a change."""
    assert regex_remove_trailing_commas(candidate) == regex_gave
    assert remove_trailing_commas(candidate) == expected
    assert regex_between_strings(candidate) == expected


@pytest.mark.parametrize(
    "candidate,expected",
    [
        pytest.param('{"a": "C:\\\\", "b": [1, ]}', '{"a": "C:\\\\", "b": [1]}',
                     id="an escaped backslash ends the string"),
        pytest.param('{"a": [1, ], "b": {"c": 2,\n}}', '{"a": [1], "b": {"c": 2}}',
                     id="the whitespace after the comma goes with it"),
        pytest.param('{"a": [1,\xa0\u3000]}', '{"a": [1]}', id="whitespace is str.isspace, as the regex's was"),
        pytest.param('{"a": [1,,]}', '{"a": [1,]}', id="only the comma next to the closer goes"),
        pytest.param('{"a": [1, 2], "b": "c"}', '{"a": [1, 2], "b": "c"}', id="a comma before a value stays"),
        pytest.param('{"a": [1, "x"], "b": 2,}', '{"a": [1, "x"], "b": 2}',
                     id="a string between the comma and the closer"),
    ],
)
def test_a_trailing_comma_outside_strings_goes_as_the_regex_removed_it(candidate, expected):
    """No trailing comma inside a string here, so the scan agrees with the frozen regex. A scan that
    misread a string would keep a comma that is really outside one."""
    assert regex_remove_trailing_commas(candidate) == expected
    assert remove_trailing_commas(candidate) == expected


# --- Every short string, and generated objects --------------------------------------------------


def short_strings(alphabet, longest):
    return ("".join(letters) for length in range(longest + 1) for letters in itertools.product(alphabet, repeat=length))


def test_every_short_string_without_a_quote_is_repaired_as_the_regex_did():
    """No double quote, so no string: the scan and the frozen regex must agree exactly. Every
    string of up to seven characters over a comma, a space, a no-break space (whitespace to the
    regex, not to JSON), both closers and a letter: 335,923 strings."""
    mismatches = [
        candidate for candidate in short_strings((",", " ", "\xa0", "]", "}", "x"), 7)
        if remove_trailing_commas(candidate) != regex_remove_trailing_commas(candidate)
    ]

    assert mismatches == []


def test_every_short_string_with_quotes_is_repaired_as_the_regex_did_between_strings():
    """Every string of up to seven characters over a comma, a space, a closer, a double quote, a
    backslash and a letter: 335,923 strings, among them escaped quotes, escaped backslashes and a
    string that never closes."""
    mismatches = [
        candidate for candidate in short_strings((",", " ", "]", '"', "\\", "x"), 7)
        if remove_trailing_commas(candidate) != regex_between_strings(candidate)
    ]

    assert mismatches == []


PIECES = (
    [",", ", ", ",\n", ",\t", " ", "\n", "\xa0", "\u3000", "\u200b"]
    + ["]", "}", "[", "{", ":", "1", "a", "null"]
    + ['"', "\\", '\\"', "\\\\", '"x, ]"', '"y,\n}"', '"\\\\"', '"\\""']
    + ['{"statements": [', '{"text": "', '", "chunk_id": "c"},', "]}", "\x00", chr(0xD800), chr(0x1F600)]
)


def test_generated_objects_are_repaired_as_the_regex_did_between_strings():
    """50,000 objects of up to 24 pieces each, from a fixed seed, so a failure reproduces. Both
    kinds are counted, the ones where leaving strings alone changes the result and the ones where
    it does not, so neither half can pass empty."""
    rng = random.Random(20261116)
    candidates = ["".join(rng.choice(PIECES) for _ in range(rng.randint(0, 24))) for _ in range(50_000)]
    differs = [c for c in candidates if regex_between_strings(c) != regex_remove_trailing_commas(c)]

    assert [c for c in candidates if remove_trailing_commas(c) != regex_between_strings(c)] == []
    assert len(differs) > 5_000 and len(candidates) - len(differs) > 5_000


# --- Through the parser -------------------------------------------------------------------------


# The control characters that JSON forbids raw in a string and that str.isspace, like the regex's
# \s, calls whitespace. There are nine: tab, newline, vertical tab, form feed, carriage return and
# U+001C to U+001F.
RAW_CONTROL_WHITESPACE = tuple(c for c in map(chr, range(0x20)) if c.isspace())


@pytest.mark.parametrize("character", RAW_CONTROL_WHITESPACE, ids=lambda c: f"U+{ord(c):04X}")
def test_a_raw_control_character_between_a_comma_and_a_bracket_in_a_string_is_refused(character):
    """The comma repair's kind of reply that D-136 turns from accepted to refused, and it is
    malformed. JSON forbids a raw control character in a string. Until 16 November 2026 the repair
    deleted any of these nine between a comma and a bracket, with the comma, and the statement
    decoded as "Bring forms A] and B.". Now the string is left alone, so the reply is not valid
    JSON: a violation, retried like any other. The fence rule's kinds are in
    apps/ai/tests/test_schema.py."""
    raw = '{"statements": [{"text": "Bring forms A,' + character + '] and B.", "chunk_id": "c"},]}'

    with pytest.raises(SchemaViolation, match="not valid JSON"):
        parse_statement_list(raw)


def test_a_comma_inside_a_string_is_never_repaired_when_the_reply_decodes():
    """The repair runs only when a reply fails to decode as sent, before and after D-136, so a reply
    that decodes keeps every string as written either way."""
    raw = '{"statements": [{"text": "Forms [A, B, ] stay.", "chunk_id": "c"}]}'

    assert parse_statement_list(raw).statements[0].text == "Forms [A, B, ] stay."


# --- In linear time -----------------------------------------------------------------------------

RUN = 200_000
WELL_UNDER = 2.0  # seconds, as in test_code_fence_scan.py; the scan takes a small fraction of it


@pytest.mark.parametrize(
    "candidate,expected",
    [
        pytest.param("{" + ("," + " " * 99) * 2_000 + "}", "{" + ("," + " " * 99) * 1_999 + "}",
                     id="2,000 commas, each before 99 spaces"),
        pytest.param("{" + "," * RUN + "]", "{" + "," * (RUN - 1) + "]", id="200,000 commas"),
        pytest.param('{"a": "' + ", ]" * (RUN // 3) + '"}', '{"a": "' + ", ]" * (RUN // 3) + '"}',
                     id="a string of 200,000 characters of trailing commas"),
        pytest.param('{"a": "' + "\\\\" * (RUN // 2) + '", "b": [1, ]}', '{"a": "' + "\\\\" * (RUN // 2) + '", "b": [1]}',
                     id="200,000 characters of escapes, then a trailing comma"),
    ],
)
def test_the_scan_reads_each_character_a_bounded_number_of_times(candidate, expected):
    """A whitespace run is read once after the comma before it and once more in passing; nothing
    else is read twice. The bound is generous on purpose, so the time is noise on any machine."""
    began = time.perf_counter()
    repaired = remove_trailing_commas(candidate)
    elapsed = time.perf_counter() - began

    assert repaired == expected
    assert elapsed < WELL_UNDER, f"took {elapsed:.2f} s"
