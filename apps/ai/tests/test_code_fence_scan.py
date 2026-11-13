"""The code-fence repair is a linear scan, and it strips exactly what the regexes it replaced did.

Until 13 November 2026 apps/ai/schema.py's ``_strip_code_fences`` found the first fenced block with
``re.search(r"```[a-zA-Z0-9_-]*\\s*(.*?)```", text, re.DOTALL)``. With an opening fence and no
closing one, that search backtracks through every split of the fence's tag and whitespace, and it
rescans the rest of the reply each time. It took 1.8 s at 20,000 spaces after the fence, and four
times as long at each doubling, so minutes at 200,000. On ``anthropic`` every call may run to
16,000 tokens (CLAUDE_MAX_TOKENS). All three structured-output parsers strip through it: FR-12's
statements, FR-10's classification and FR-16's summary.

Its fallback, for a fence that never closes, was ``_CODE_FENCE.sub`` with
``^\\s*```[a-zA-Z0-9_-]*\\s*|\\s*```\\s*$``. It was quadratic as well, on a whitespace run anywhere
in such a reply but straight after a leading fence, which its first branch took in one pass:
0.50 s at 20,000 spaces. It is a scan too, since the same day.

The scan must not change what the repair returns, so that it moves none of the numbers measured
on this parser (apps/ai/schema.py's module docstring). So the function as it was is copied below,
frozen, and the scan is held to it in three ways:
- on named edge cases;
- on every string of up to eight characters over a backtick, a letter, two kinds of whitespace
  and a brace;
- on generated replies.

No provider, no network, no database: pure functions over strings.
"""

import itertools
import random
import re
import sys
import time

import pytest

from apps.ai import schema

# --- The reference: _strip_code_fences as it was before 13 November 2026 ---------------------
# Copied verbatim and frozen. Never edit it to make a case pass: it is what "unchanged" means.

_CODE_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*|\s*```\s*$")


def regex_strip_code_fences(raw: str) -> str:
    """Remove a leading ```json (or bare ```) and a trailing ``` if both are present."""
    text = raw.strip()
    if "```" not in text:
        return text
    # Prefer the contents of the first fenced block; fall back to stripping markers.
    fenced = re.search(r"```[a-zA-Z0-9_-]*\s*(.*?)```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return _CODE_FENCE.sub("", text).strip()


# --- What it strips: the scan and the regex agree ----------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param('```json\n{"a": 1}\n```', '{"a": 1}', id="a json fence"),
        pytest.param('```\n{"a": 1}\n```', '{"a": 1}', id="a bare fence"),
        pytest.param('```json{"a": 1}```', '{"a": 1}', id="a tag with no newline"),
        pytest.param("```py-3_x \t\n{}```", "{}", id="a tag of letters, digits, hyphen and underscore"),
        pytest.param("```jsonabc def```", "def", id="the tag runs to the first character outside it"),
        pytest.param("```é{}```", "é{}", id="a non-ASCII letter ends the tag"),
        pytest.param("```json\u3000\x85{}```", "{}", id="Unicode whitespace after the tag"),
        pytest.param("```json\u200b{}```", "\u200b{}", id="a zero-width space is not whitespace"),
        pytest.param("``````", "", id="six backticks"),
        pytest.param("````json\n{}\n```", "`json\n{}", id="four backticks before a tag"),
        pytest.param("Here: ```json\n{}\n``` and ```{x}```", "{}", id="a fence inside prose"),
        pytest.param('```json\n{"a": 1}', '{"a": 1}', id="no closing fence"),
        pytest.param('{"a": 1}\n```', '{"a": 1}', id="a closing fence only"),
        pytest.param("x```y", "x```y", id="a lone fence inside text"),
        pytest.param("````", "`", id="four backticks alone"),
        pytest.param("`````", "``", id="five backticks alone"),
        pytest.param("x````", "x`", id="text, then four backticks"),
        pytest.param('  {"a": 1}  ', '{"a": 1}', id="no fence"),
        pytest.param("", "", id="empty"),
    ],
)
def test_named_cases_strip_as_the_regex_did(raw, expected):
    """Each value is pinned and the reference must give it too, so a case records behaviour
    rather than only comparing two functions."""
    assert regex_strip_code_fences(raw) == expected
    assert schema.strip_code_fences(raw) == expected


def test_every_short_string_strips_as_the_regex_did():
    """Every string of up to eight characters over a backtick, a tag letter, a space, a newline
    and a brace: 488,281 strings. Among them are six backticks, four before a tag, and a fence, a
    tag, whitespace and a closing fence in every order that fits."""
    alphabet = ("`", "j", " ", "\n", "{")
    strings = (
        "".join(letters) for length in range(9) for letters in itertools.product(alphabet, repeat=length)
    )
    mismatches = [raw for raw in strings if schema.strip_code_fences(raw) != regex_strip_code_fences(raw)]

    assert mismatches == []


# Fences and runs of backticks, tag characters and words, ASCII and Unicode whitespace, a
# zero-width space (which is not whitespace), a NUL, CRLF, a lone surrogate, a character outside
# the Basic Multilingual Plane, JSON punctuation and prose.
PIECES = (
    ["`"] * 8
    + ["```", "```json", "```JSON\n", "\n```", "````", "``````", "```py-3_x"]
    + list("ajZ09_-")
    + ["json", "statements", "é", "ß", "Ω"]
    + [" ", "\t", "\n", "\r", "\x0b", "\x0c", "\x1c", "\x1f", "\x85", "\xa0", "\u2028", "\u3000", "\u200b"]
    + ["\x00", "\r\n", chr(0xD800), chr(0x1F600)]
    + ["{", "}", "[", "]", '"', ":", ",", "!", ".", "Here it is: ", '{"statements": []}']
)


def test_generated_replies_strip_as_the_regex_did():
    """50,000 replies of up to 24 pieces each, from a fixed seed, so a failure reproduces."""
    rng = random.Random(20261113)
    replies = ["".join(rng.choice(PIECES) for _ in range(rng.randint(0, 24))) for _ in range(50_000)]
    mismatches = [raw for raw in replies if schema.strip_code_fences(raw) != regex_strip_code_fences(raw)]

    assert mismatches == []


def test_the_scan_reads_the_regex_character_classes():
    """The scan skips a tag by membership of a set, and whitespace with str.isspace. The tag set
    must be exactly [a-zA-Z0-9_-], checked here over every code point, surrogates included. The
    whitespace class cannot change what the repair returns, since every result is stripped of the
    same characters, but it is checked the same way: a str pattern's \\s and str.isspace both call
    Py_UNICODE_ISSPACE."""
    everything = "".join(map(chr, range(sys.maxunicode + 1)))

    assert set(re.findall(r"\s", everything)) == {c for c in everything if c.isspace()}
    assert set(re.findall(r"[a-zA-Z0-9_-]", everything)) == schema._FENCE_TAG_CHARACTERS


# --- In linear time ----------------------------------------------------------------------------

RUN = 200_000
WELL_UNDER = 2.0  # seconds. The scan takes about a hundredth of a second here; the regex, minutes.


def assert_stripped_well_under_the_bound(raw, expected):
    """The bound is generous on purpose: against it, the scan's time is noise on any machine."""
    began = time.perf_counter()
    stripped = schema.strip_code_fences(raw)
    elapsed = time.perf_counter() - began

    assert stripped == expected
    assert elapsed < WELL_UNDER, f"took {elapsed:.2f} s"


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param("```" + " " * RUN + "}", "}", id="a fence, 200,000 spaces and no closing fence"),
        pytest.param("```" + "a" * RUN + "}", "}", id="a fence, a 200,000-character tag and no closing fence"),
    ],
)
def test_a_long_run_after_an_unclosed_fence_is_read_once(raw, expected):
    """The regex's worst case: an opening fence, a long run of whitespace or of tag characters,
    and no closing fence. The regex took 1.8 s at 20,000, and four times as long at each doubling.

    In the whitespace case the brace after the run matters. Without it ``raw.strip()`` removes the
    run before the search sees it, the regex is fast as well, and the case could not catch the
    regression."""
    assert_stripped_well_under_the_bound(raw, expected)


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param(
            "```json\n{" + " " * RUN + "}",
            "{" + " " * RUN + "}",
            id="a fence and a tag, then 200,000 spaces in an object, and no closing fence",
        ),
        pytest.param(
            "{" + " " * RUN + "}```",
            "{" + " " * RUN + "}",
            id="200,000 spaces in an object, then a closing fence only",
        ),
        pytest.param(
            "x" + " " * RUN + "```y",
            "x" + " " * RUN + "```y",
            id="200,000 spaces, then a lone fence inside text",
        ),
    ],
)
def test_a_whitespace_run_in_a_reply_whose_fence_never_closes_is_read_once(raw, expected):
    """The fallback's worst case: a fence that never closes, and a long whitespace run anywhere in
    the reply but straight after a leading fence, which the regex's first branch took in one pass.
    Its second branch, ``\\s*```\\s*$``, was tried at every position in the run. Each time it took
    the rest of the run and backtracked through it, looking for a fence. That took 0.50 s at
    20,000, and four times as long at each doubling. The search is fast on these shapes; only the
    fallback was slow."""
    assert_stripped_well_under_the_bound(raw, expected)
