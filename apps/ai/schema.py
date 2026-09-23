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

# docs/ai-provider.md section 5. Expressed as JSON Schema so it can be handed to a
# constrained-decoding option if FLM ever exposes one; validated by hand below,
# since the project takes no jsonschema dependency for one small shape.
STATEMENT_LIST_SCHEMA = {
    "type": "object",
    "required": ["statements"],
    "additionalProperties": False,
    "properties": {
        "statements": {
            "type": "array",
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


def parse_statement_list(raw: str) -> StatementList:
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
    """
    if not isinstance(raw, str) or not raw.strip():
        raise SchemaViolation("empty response")
    candidate = _outermost_json_object(_strip_code_fences(raw))
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            decoded = json.loads(_TRAILING_COMMA.sub("", candidate))
        except json.JSONDecodeError as exc:
            raise SchemaViolation(f"not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise SchemaViolation(f"top level is {type(decoded).__name__}, not an object")
    if "statements" not in decoded:
        raise SchemaViolation(f"no 'statements' key (keys: {sorted(decoded)})")
    extra = sorted(set(decoded) - {"statements"})
    if extra:
        raise SchemaViolation(f"unexpected top-level key(s): {extra}")
    items = decoded["statements"]
    if not isinstance(items, list):
        raise SchemaViolation(f"'statements' is {type(items).__name__}, not an array")
    statements: list[Statement] = []
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            raise SchemaViolation(f"statement {position} is {type(item).__name__}, not an object")
        missing = sorted({"text", "chunk_id"} - set(item))
        if missing:
            raise SchemaViolation(f"statement {position} is missing {missing}")
        unexpected = sorted(set(item) - {"text", "chunk_id"})
        if unexpected:
            raise SchemaViolation(f"statement {position} has unexpected key(s): {unexpected}")
        text, chunk_id = item["text"], item["chunk_id"]
        if not isinstance(text, str) or not text.strip():
            raise SchemaViolation(f"statement {position} has an empty or non-string 'text'")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise SchemaViolation(f"statement {position} has an empty or non-string 'chunk_id'")
        statements.append(Statement(text=text.strip(), chunk_id=chunk_id.strip()))
    return StatementList(statements=statements)
