"""The required generation response shape and its tolerant parser.

docs/ai-provider.md section 5, steps 1 and 3. FR-12 needs discrete statements each
tagged with the identifier of the passage it came from: free prose cannot be verified
statement by statement, so this structure is what makes citation verification possible
at all (CLAUDE.md invariant 5).

**Moved here from scripts/citation_harness.py at Stage 4 item 5, substantively
unchanged.** The schema and the parser below are what measured 100% schema conformance
and a 2.4% fabricated-identifier rate over 50 questions on gemma3:4b
(docs/flm-baseline.md); a rewrite would invalidate those numbers, so only imports and
docstrings were adjusted. The harness now imports these names instead of defining
them, because two definitions of a schema drift and the day they drift the baseline
document stops describing the shipped system. The test at
``apps/ai/tests/test_prompt_is_not_duplicated.py`` asserts the harness holds no second
copy, by reading its source text.

A response that does not parse is a FAILED ATTEMPT, never a partial answer: the caller
retries to MAXIMUM_GENERATION_ATTEMPTS and then raises ProviderUnavailable, which the
view turns into the NFR-19 503 (invariant 10). An empty statement list that DOES parse
is not a violation — it is the model correctly reporting that the passages do not answer
the question, and it must be returned rather than retried.
"""

import json
import re

from apps.ai.base import Statement, StatementList
from apps.core.constants import MAXIMUM_STATEMENTS

# docs/ai-provider.md section 5. Expressed as JSON Schema so it can be handed to a
# constrained-decoding option if FLM ever exposes one; validated by hand below,
# since the project takes no jsonschema dependency for one small shape.
#
# ``maxItems`` (step 7 phase 2a, 7 November 2026) is the statement cap. A reply with more
# statements than the attempt asked for is a violation like any other: retried, never
# trimmed to fit (invariant 10). An attempt after a reply that hit max_tokens or broke the
# cap asks for fewer than MAXIMUM_STATEMENTS (apps/ai/generation.py), and its reply is held
# to the number it was asked for, which is never more than this.
STATEMENT_LIST_SCHEMA = {
    "type": "object",
    "required": ["statements"],
    "additionalProperties": False,
    "properties": {
        "statements": {
            "type": "array",
            "maxItems": MAXIMUM_STATEMENTS,
            "items": {
                "type": "object",
                "required": ["text", "chunk_id"],
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "chunk_id": {"type": "string", "minLength": 1},
                },
            },
        }
    },
}


class SchemaViolation(Exception):
    """The response did not parse into STATEMENT_LIST_SCHEMA.

    Treated as no response at all: retried, then 503 after
    MAXIMUM_GENERATION_ATTEMPTS (CLAUDE.md invariant 10). Never a partial answer.
    """


class StatementCapExceeded(SchemaViolation):
    """The reply holds more statements than the attempt asked for.

    A SchemaViolation, so it is retried and never trimmed. Its own class because the attempt
    loop asks the next attempt for fewer statements after it (apps/ai/generation.py).
    """


_CODE_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*|\s*```\s*$")
_TRAILING_COMMA = re.compile(r",\s*(?=[}\]])")


def _strip_code_fences(raw: str) -> str:
    """Remove a leading ```json (or bare ```) and a trailing ``` if both are present."""
    text = raw.strip()
    if "```" not in text:
        return text
    # Prefer the contents of the first fenced block; fall back to stripping markers.
    fenced = re.search(r"```[a-zA-Z0-9_-]*\s*(.*?)```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return _CODE_FENCE.sub("", text).strip()


def _outermost_json_object(text: str) -> str:
    """Return the first balanced {...} span, ignoring braces inside JSON strings."""
    start = text.find("{")
    if start == -1:
        raise SchemaViolation("no JSON object in the response")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise SchemaViolation("unbalanced JSON object in the response")


def _loads_reply(text: str):
    """``json.loads`` for a model reply: every way it can fail to decode is a SchemaViolation.

    ``json.loads`` raises more than JSONDecodeError. A reply nested past the interpreter's limit,
    a few thousand levels of ``[`` or ``{``, raises RecursionError, and an integer literal past
    Python's 4,300-digit limit on converting a string to an int raises ValueError. Both are a
    reply that does not conform, so both are a violation, retried like any other (invariant 10).

    Before 13 November 2026 they escaped the three attempt loops, which catch only
    SchemaViolation. POST /api/ask and POST /api/documents/{id}/classify answered 500 instead of
    NFR-19's 503, and a meeting summary's run ended as "error", without the one retry FR-16
    allows a malformed reply. A security review found it that day.

    The two messages are fixed and quote nothing of the reply. A JSONDecodeError propagates
    unchanged, so the caller can try its trailing-comma repair before it reports "not valid
    JSON".
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise
    except RecursionError as exc:
        raise SchemaViolation("JSON nested too deeply to decode") from exc
    except ValueError as exc:  # after JSONDecodeError, itself a ValueError: the digit limit
        raise SchemaViolation("a JSON number too long to decode") from exc


# Public names for the three repairs, added on 9 November 2026 for FR-10 (D-104):
# apps/ai/classification.py applies exactly this tolerance to a classification reply by
# importing these rather than copying them, so there is one definition of what is
# repaired. The private names stay bound, for the parser below and anything that reached
# for them.
strip_code_fences = _strip_code_fences
outermost_json_object = _outermost_json_object
TRAILING_COMMA_PATTERN = _TRAILING_COMMA
# And the decode step, added on 13 November 2026 on the same principle: the statement,
# classification and summary parsers all decode through it, so all three fail the same way.
loads_reply = _loads_reply


def parse_statement_list(raw: str, *, max_statements: int | None = None) -> StatementList:
    """Parse a raw model reply into a StatementList, or raise SchemaViolation.

    Tolerant of the malformations a small model commonly produces — a markdown
    code fence, a sentence of preamble around the object, a trailing comma — and
    of nothing else. Anything still unparseable, or parseable but the wrong shape,
    is rejected outright rather than repaired into a plausible-looking answer.

    ``{"statements": []}`` parses successfully and returns an empty StatementList.
    That is a valid response and not a violation: rule 7 of the system prompt asks
    for exactly it when the passages do not answer the question, and the no-answer
    path that follows from it is FR-12's second one, reached through verification
    (invariant 7), not through a retry.

    ``max_statements`` is the cap the attempt asked for, MAXIMUM_STATEMENTS when it is not
    given. More statements than that raises StatementCapExceeded, whatever the statements
    say: the whole reply is rejected, and none of it is kept (invariant 10).
    """
    limit = MAXIMUM_STATEMENTS if max_statements is None else max_statements
    if not isinstance(raw, str) or not raw.strip():
        raise SchemaViolation("empty response")
    candidate = _outermost_json_object(_strip_code_fences(raw))
    try:
        decoded = _loads_reply(candidate)
    except json.JSONDecodeError:
        try:
            decoded = _loads_reply(_TRAILING_COMMA.sub("", candidate))
        except json.JSONDecodeError as exc:
            raise SchemaViolation(f"not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise SchemaViolation(f"top level is {type(decoded).__name__}, not an object")
    if "statements" not in decoded:
        # A key the reply chose is the model's words, which a passage can steer, so it is
        # counted and never quoted, here and for a statement's keys below: the message reaches
        # the attempts log (apps/ai/attempt_log.py). Only the schema's own keys are named. The
        # security review of FR-16 found this pattern in its parser on 12 November 2026 (D-125's
        # third note); the fix is the same. Only the wording changed: what parses and what is
        # refused are exactly as measured.
        raise SchemaViolation(f"no 'statements' key (the reply had {len(decoded)} key(s))")
    extra = sorted(set(decoded) - {"statements"})
    if extra:
        raise SchemaViolation(f"{len(extra)} unexpected top-level key(s)")
    items = decoded["statements"]
    if not isinstance(items, list):
        raise SchemaViolation(f"'statements' is {type(items).__name__}, not an array")
    if len(items) > limit:
        raise StatementCapExceeded(f"{len(items)} statements, more than the {limit} asked for")
    statements: list[Statement] = []
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            raise SchemaViolation(f"statement {position} is {type(item).__name__}, not an object")
        missing = sorted({"text", "chunk_id"} - set(item))
        if missing:
            raise SchemaViolation(f"statement {position} is missing {missing}")
        unexpected = sorted(set(item) - {"text", "chunk_id"})
        if unexpected:
            raise SchemaViolation(f"statement {position} has {len(unexpected)} unexpected key(s)")
        text, chunk_id = item["text"], item["chunk_id"]
        if not isinstance(text, str) or not text.strip():
            raise SchemaViolation(f"statement {position} has an empty or non-string 'text'")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise SchemaViolation(f"statement {position} has an empty or non-string 'chunk_id'")
        statements.append(Statement(text=text.strip(), chunk_id=chunk_id.strip()))
    return StatementList(statements=statements)
