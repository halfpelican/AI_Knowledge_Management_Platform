"""FR-16 meeting summaries: the AIService operation ``summarise_meeting`` (docs/decisions.md D-125).

One meeting's narrative, decisions, highlights and action items in one structured call, FR-16's
"single structured request returning both the summary and the action items against a defined
schema rather than prose". The module follows FR-10's (apps/ai/classification.py, D-104): it holds
everything specific to this call and redefines nothing shared with generation.

- ``SUMMARY_SCHEMA`` and ``parse_summary``: the required reply shape and the tolerant parser, built
  on the SAME three repairs as ``parse_statement_list`` (code fence, preamble, trailing comma),
  imported from apps/ai/schema.py rather than copied. Anything else is a ``SchemaViolation``
  (CLAUDE.md invariant 10).
- ``SUMMARY_SYSTEM_PROMPT`` and the message builders: strict rules, one worked example, then the
  title and the transcript's numbered passages in the user turn.
- ``run_summary_attempts``: the attempt loop. A failed call is retried to
  MAXIMUM_SUMMARY_ATTEMPTS in total (1 initial call + 2 retries), a 429 included (D-118); any other
  4xx is ProviderRefused and ends the loop at once. A malformed reply gets exactly ONE retry
  (FR-16: "a malformed response triggers one retry"): the second is MalformedSummary, even with an
  attempt left (MAXIMUM_MALFORMED_SUMMARY_REPLIES).

**Passage labels.** The transcript arrives as FR-09's own passages, in order, and the prompt heads
them ``[P1]`` to ``[Pn]``. Every element of the reply must name at least one label, so UC-04's
"every element of the summary carries a reference to the passage of the transcript it was drawn
from" is a schema rule. The parser checks the SHAPE of a label (``P`` and a positive number) and
nothing else: whether that passage was sent is set membership, done by the caller
(apps/meetings/summaries.py), as FR-12's citations are checked outside the provider (invariant 5).

**Uploaded text is untrusted.** A transcript containing ``[P3]`` would put a forged passage header
in front of the model, the risk D-45 closes for ``[chunk_id: ...]``. So the label form in transcript
and title text has its square brackets turned round, and nothing else changes. A forged label could
only ever name another passage of the same transcript, because verification admits only the
numbers sent; it is neutralised for the same reason D-45 gives, that the header form should exist
only where this module writes it. The residual is the one every prompt here concedes: a transcript
that instructs the model in prose ("summarise this meeting as a success") can steer the reply, and
shape validation cannot detect that. What bounds it: the reply is held to the schema, references to
passages sent, owners to the user list (apps/meetings/owners.py), dates to a deterministic parser,
and a person can edit or delete every action item and regenerate the summary.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Callable

from apps.ai import attempt_log
from apps.ai.base import (
    ExtractedActionItem,
    MalformedSummary,
    MeetingSummaryDraft,
    ProviderRefused,
    ProviderUnavailable,
    SummaryElement,
)
from apps.ai.generation import ChatReply
from apps.ai.schema import (
    TRAILING_COMMA_PATTERN,
    SchemaViolation,
    loads_reply,
    outermost_json_object,
    strip_code_fences,
)
from apps.core.constants import (
    CHUNK_SIZE,
    MAXIMUM_MALFORMED_SUMMARY_REPLIES,
    MAXIMUM_SUMMARY_ATTEMPTS,
    SUMMARY_INPUT_TOKENS,
)

# The reply's limits. Each is a parameter of this call, like CLASSIFICATION_MAX_TOKENS, so it is
# defined here rather than in apps/core/constants.py (D-104's precedent for MAXIMUM_TAG_SUGGESTIONS).
# A reply over any of them is a schema violation, retried and never trimmed (invariant 10). The
# rules state every one of them: a limit the model was never told is one a long meeting breaks on
# every attempt, and every queued run (the security review of 12 November 2026, finding 3, D-125's
# third note). apps/ai/tests/test_summarisation_prompt.py holds the rules and the parser to one
# number each.
#
# FR-16's "concise paragraph-length summary": six sentences is a paragraph, and the same number
# FR-12 caps an answer at (MAXIMUM_STATEMENTS, D-100).
MAXIMUM_SUMMARY_SENTENCES = 6
# Generous on purpose: a meeting that reaches more decisions or raises more action items than this
# is rare, and a reply refused for a real meeting costs a retry. A reply listing more is listing
# things it should not.
MAXIMUM_DECISIONS = 12
MAXIMUM_HIGHLIGHTS = 8
MAXIMUM_ACTION_ITEMS = 25
# An element drawn from more passages than this is citing the transcript rather than its source.
MAXIMUM_PASSAGES_PER_ELEMENT = 6
# One sentence, decision, highlight or action item, in characters; an owner's name or a deadline as
# said, in characters. A longer one is not the thing the key asks for.
MAXIMUM_ELEMENT_CHARACTERS = 600
MAXIMUM_PHRASE_CHARACTERS = 120

# FLM's ceiling on one reply, and the timeout for one call. The longest conforming reply, every
# limit above filled, is about 2,600 tokens; 3,000 lets it finish and stops one that is listing
# far more. Claude takes CLAUDE_MAX_TOKENS instead, because its thinking counts against the ceiling
# (D-115). Nobody waits on the call (the route answered 202), so the timeout is generous: a 4B
# model on the NPU reading up to SUMMARY_INPUT_TOKENS of transcript.
SUMMARY_MAX_TOKENS = 3000
SUMMARY_TIMEOUT_SECONDS = 600

# A passage label, as the reply must give it: "P" and a positive number with no leading zero.
LABEL_PREFIX = "P"
_LABEL = re.compile(rf"^{LABEL_PREFIX}([1-9][0-9]*)$")
# The label's header form inside untrusted text: "[P3]", with any spacing or case. Its square
# brackets become round ones, "(P3)", and nothing else changes (D-45's transformation).
_HEADER_IN_TEXT = re.compile(rf"\[(\s*{LABEL_PREFIX}\s*\d+\s*)\]", re.IGNORECASE)

# The most passages one request may carry. The caller cuts the transcript at SUMMARY_INPUT_TOKENS
# of whole passages, and every passage but the last holds CHUNK_SIZE tokens, so no real request
# exceeds this. The worked example's labels start above it, so a label copied from the example
# can never name a real passage and verification drops it (see EXAMPLE_FIRST_PASSAGE below).
MAXIMUM_PASSAGES = SUMMARY_INPUT_TOKENS // CHUNK_SIZE + 1

# The required reply shape, as JSON Schema, documented like STATEMENT_LIST_SCHEMA and
# CLASSIFICATION_SCHEMA and validated by hand in ``parse_summary``: the project takes no jsonschema
# dependency. All four keys are required. ``summary`` holds at least one sentence, and the other
# three may be empty arrays, so a reply that leaves out the action-item section is a violation and
# one that lists none is a result (UC-04 A1).
_PASSAGES_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "maxItems": MAXIMUM_PASSAGES_PER_ELEMENT,
    "items": {"type": "string", "pattern": _LABEL.pattern},
}
_TEXT_SCHEMA = {"type": "string", "minLength": 1, "maxLength": MAXIMUM_ELEMENT_CHARACTERS}
_PHRASE_SCHEMA = {"type": ["string", "null"], "maxLength": MAXIMUM_PHRASE_CHARACTERS}
_ELEMENT_SCHEMA = {
    "type": "object",
    "required": ["text", "passages"],
    "additionalProperties": False,
    "properties": {"text": _TEXT_SCHEMA, "passages": _PASSAGES_SCHEMA},
}
SUMMARY_SCHEMA = {
    "type": "object",
    "required": ["summary", "decisions", "highlights", "action_items"],
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "array", "minItems": 1, "maxItems": MAXIMUM_SUMMARY_SENTENCES,
                    "items": _ELEMENT_SCHEMA},
        "decisions": {"type": "array", "maxItems": MAXIMUM_DECISIONS, "items": _ELEMENT_SCHEMA},
        "highlights": {"type": "array", "maxItems": MAXIMUM_HIGHLIGHTS, "items": _ELEMENT_SCHEMA},
        "action_items": {
            "type": "array",
            "maxItems": MAXIMUM_ACTION_ITEMS,
            "items": {
                "type": "object",
                "required": ["description", "owner", "due", "passages"],
                "additionalProperties": False,
                "properties": {
                    "description": _TEXT_SCHEMA,
                    "owner": _PHRASE_SCHEMA,
                    "due": _PHRASE_SCHEMA,
                    "passages": _PASSAGES_SCHEMA,
                },
            },
        },
    },
}

_TOP_LEVEL_KEYS = frozenset(SUMMARY_SCHEMA["required"])
_ELEMENT_KEYS = frozenset(_ELEMENT_SCHEMA["required"])
_ACTION_ITEM_KEYS = frozenset(SUMMARY_SCHEMA["properties"]["action_items"]["items"]["required"])


@dataclass(frozen=True)
class ParsedSummary:
    """What ``parse_summary`` returns: the reply's four parts, and nothing about who said it."""

    narrative: tuple[SummaryElement, ...]
    decisions: tuple[SummaryElement, ...]
    highlights: tuple[SummaryElement, ...]
    action_items: tuple[ExtractedActionItem, ...]


# --- The parser ------------------------------------------------------------------------------


def parse_summary(raw: str) -> ParsedSummary:
    """Parse a raw model reply into a ParsedSummary, or raise SchemaViolation.

    The same tolerance as ``parse_statement_list`` and ``parse_classification`` and no more: a
    markdown code fence, a sentence of preamble around the object and a trailing comma are
    repaired, through the same three pieces of code (apps/ai/schema.py). Anything still
    unparseable, or parseable but the wrong shape, is rejected rather than repaired into a
    plausible-looking summary (invariant 10). In particular:

    - exactly the four keys, each an array; ``summary`` holds 1 to MAXIMUM_SUMMARY_SENTENCES
      elements and the other three at most their own limit, counted as returned;
    - every element names 1 to MAXIMUM_PASSAGES_PER_ELEMENT labels, each a string ``P<n>``; a bare
      number, ``"p3"`` or ``"passage 3"`` is a violation, not repaired;
    - an empty or over-long ``text`` or ``description`` is a violation;
    - ``owner`` and ``due`` are a string or null. A blank string is read as null, because it says
      the same thing; one longer than MAXIMUM_PHRASE_CHARACTERS is a violation.

    Surrounding whitespace is stripped from every string, and a label repeated within one element
    is kept once, in first position: two mentions of one passage are one reference. These are
    SHAPE tolerances, like the trailing comma; no text is changed and nothing is invented. Whether
    a label names a passage that was sent is NOT checked here (apps/meetings/summaries.py).
    """
    if not isinstance(raw, str) or not raw.strip():
        raise SchemaViolation("empty response")
    candidate = outermost_json_object(strip_code_fences(raw))
    try:
        decoded = loads_reply(candidate)
    except json.JSONDecodeError:
        try:
            decoded = loads_reply(TRAILING_COMMA_PATTERN.sub("", candidate))
        except json.JSONDecodeError as exc:
            raise SchemaViolation(f"not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise SchemaViolation(f"top level is {type(decoded).__name__}, not an object")
    missing = sorted(_TOP_LEVEL_KEYS - set(decoded))
    if missing:
        # The keys the reply did send are the model's words, which a transcript can steer, so they
        # are counted and never quoted: the message reaches the attempts log and the warning a
        # failed run writes (the security review of 12 November, D-125's third note).
        raise SchemaViolation(f"missing top-level key(s): {missing} (the reply had {len(decoded)} key(s))")
    extra = sorted(set(decoded) - _TOP_LEVEL_KEYS)
    if extra:
        raise SchemaViolation(f"{len(extra)} unexpected top-level key(s)")

    return ParsedSummary(
        narrative=_elements(decoded["summary"], "summary", minimum=1, maximum=MAXIMUM_SUMMARY_SENTENCES),
        decisions=_elements(decoded["decisions"], "decisions", minimum=0, maximum=MAXIMUM_DECISIONS),
        highlights=_elements(decoded["highlights"], "highlights", minimum=0, maximum=MAXIMUM_HIGHLIGHTS),
        action_items=_action_items(decoded["action_items"]),
    )


def _array(value, where: str, *, minimum: int, maximum: int) -> list:
    if not isinstance(value, list):
        raise SchemaViolation(f"'{where}' is {type(value).__name__}, not an array")
    if len(value) < minimum:
        raise SchemaViolation(f"'{where}' has {len(value)} item(s), fewer than {minimum}")
    if len(value) > maximum:
        raise SchemaViolation(f"'{where}' has {len(value)} items, more than the {maximum} allowed")
    return value


def _object(item, where: str, keys: frozenset) -> dict:
    if not isinstance(item, dict):
        raise SchemaViolation(f"{where} is {type(item).__name__}, not an object")
    missing = sorted(keys - set(item))
    if missing:
        raise SchemaViolation(f"{where} is missing {missing}")
    unexpected = sorted(set(item) - keys)
    if unexpected:
        raise SchemaViolation(f"{where} has {len(unexpected)} unexpected key(s)")
    return item


def _elements(value, where: str, *, minimum: int, maximum: int) -> tuple[SummaryElement, ...]:
    elements = []
    for position, item in enumerate(_array(value, where, minimum=minimum, maximum=maximum)):
        label = f"{where} item {position}"
        item = _object(item, label, _ELEMENT_KEYS)
        elements.append(
            SummaryElement(text=_text(item["text"], label, "text"), passages=_passages(item["passages"], label))
        )
    return tuple(elements)


def _action_items(value) -> tuple[ExtractedActionItem, ...]:
    items = []
    for position, item in enumerate(_array(value, "action_items", minimum=0, maximum=MAXIMUM_ACTION_ITEMS)):
        label = f"action item {position}"
        item = _object(item, label, _ACTION_ITEM_KEYS)
        items.append(
            ExtractedActionItem(
                description=_text(item["description"], label, "description"),
                owner=_phrase(item["owner"], label, "owner"),
                due=_phrase(item["due"], label, "due"),
                passages=_passages(item["passages"], label),
            )
        )
    return tuple(items)


def _text(value, where: str, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaViolation(f"{where} has an empty or non-string '{key}'")
    text = value.strip()
    if len(text) > MAXIMUM_ELEMENT_CHARACTERS:
        raise SchemaViolation(f"{where} has a '{key}' longer than {MAXIMUM_ELEMENT_CHARACTERS} characters")
    return text


def _phrase(value, where: str, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SchemaViolation(f"{where} has a '{key}' that is neither a string nor null")
    phrase = value.strip()
    if len(phrase) > MAXIMUM_PHRASE_CHARACTERS:
        raise SchemaViolation(f"{where} has a '{key}' longer than {MAXIMUM_PHRASE_CHARACTERS} characters")
    return phrase or None


def _passages(value, where: str) -> tuple[int, ...]:
    labels = _array(value, f"{where} passages", minimum=1, maximum=MAXIMUM_PASSAGES_PER_ELEMENT)
    numbers: list[int] = []
    for label in labels:
        match = _LABEL.match(label.strip()) if isinstance(label, str) else None
        if match is None:
            # The label is not quoted: a reply's content is not written into the attempt log.
            raise SchemaViolation(f"{where} names a passage that is not a label of the form P<n>")
        number = int(match.group(1))
        if number not in numbers:
            numbers.append(number)
    return tuple(numbers)


# --- The input -------------------------------------------------------------------------------


def neutralise_passage_headers(text: str) -> str:
    """Turn the label's header form, ``[P3]``, into ``(P3)`` in untrusted text; change nothing else."""
    return _HEADER_IN_TEXT.sub(r"(\1)", text)


def passage_label(number: int) -> str:
    return f"{LABEL_PREFIX}{number}"


def _passage_block(passages: list[str], first: int = 1) -> str:
    return "\n\n".join(
        f"[{passage_label(number)}]\n{neutralise_passage_headers(text.strip())}"
        for number, text in enumerate(passages, start=first)
    )


# --- The prompt ------------------------------------------------------------------------------
#
# READ THE COMMENT ABOVE SYSTEM_PROMPT IN apps/ai/prompting.py BEFORE EDITING THE EXAMPLE. A worked
# example is training data for the response, in its identifiers and in its content. So:
#
# - Its CONTENT is an orchard co-operative's harvest meeting, with speakers named Wren, Bastian
#   and Odile: no organisation's meeting is about cider presses and plum netting, and the names are
#   chosen to appear in no real transcript. apps/ai/tests/test_summarisation_prompt.py asserts the
#   example's words appear in no Objective 04 or demonstration transcript.
# - Its IDENTIFIERS start at EXAMPLE_FIRST_PASSAGE, above MAXIMUM_PASSAGES, the most any real
#   request carries. A label copied from the example therefore names no passage that was sent, and
#   verification drops it, where a copied "P1" would silently cite the real first passage.
# - It demonstrates the hard rules rather than stating them only: an owner taken from the speaker
#   label of an "I'll", an owner left null where nobody is named, a deadline copied as said, a
#   suggestion that is NOT an action item, and a decision.

EXAMPLE_FIRST_PASSAGE = 41
assert EXAMPLE_FIRST_PASSAGE > MAXIMUM_PASSAGES, "the example's labels must name no real passage"

EXAMPLE_TITLE = "Orchard co-operative harvest planning"
EXAMPLE_PASSAGES = [
    "Wren: The early apples are ready a fortnight sooner than last year, so picking starts on the "
    "first Saturday of next month. Bastian, can you book the cider press for that weekend?\n"
    "Bastian: I'll ring the press hire people tomorrow.\n"
    "Odile: We could also try selling at the Sunday market one day.\n"
    "Wren: Maybe, but not this season.",
    "Odile: The netting over the plum trees is torn again. I propose we replace it rather than "
    "patch it.\n"
    "Wren: Agreed, we replace it. The new netting needs collecting from the depot before the first "
    "frost.\n"
    "Bastian: The ladders were checked last week and are safe for another season.",
]
EXAMPLE_REPLY = json.dumps(
    {
        "summary": [
            {
                "text": "The co-operative planned an early harvest: picking starts on the first "
                "Saturday of next month, and the cider press is to be booked for that weekend.",
                "passages": ["P41"],
            },
            {
                "text": "It agreed to replace the torn netting over the plum trees rather than patch it.",
                "passages": ["P42"],
            },
        ],
        "decisions": [
            {"text": "The torn plum netting will be replaced, not patched.", "passages": ["P42"]},
        ],
        "highlights": [
            {"text": "The early apples are ready a fortnight sooner than last year.", "passages": ["P41"]},
            {"text": "The ladders are safe for another season.", "passages": ["P42"]},
        ],
        "action_items": [
            {
                "description": "Book the cider press for the first picking weekend",
                "owner": "Bastian",
                "due": "tomorrow",
                "passages": ["P41"],
            },
            {
                "description": "Collect the new plum netting from the depot",
                "owner": None,
                "due": "before the first frost",
                "passages": ["P42"],
            },
        ],
    }
)

REPLY_INSTRUCTION = "Reply with the JSON object only."

_RULES = f"""\
You summarise one meeting transcript and reply with JSON.

The transcript is given as numbered passages, each under a header such as [P1] or [P2]. Passages
overlap a little at their edges.

Rules, all of them mandatory:
1. Reply with one JSON object and nothing else: no greeting, no explanation, no markdown code
   fence, no text before or after the object.
2. The object has exactly four keys: "summary", "decisions", "highlights" and "action_items".
   All four must be present, even when one is an empty array.
3. "summary" is an array of 1 to {MAXIMUM_SUMMARY_SENTENCES} objects that together are a concise,
   paragraph-length account of the meeting: what it was for and what came of it. Each object is
   one sentence, with exactly two keys: "text", the sentence, and "passages", an array of the
   labels of the passages it is drawn from, such as ["P2", "P5"].
4. "decisions" is an array of at most {MAXIMUM_DECISIONS} decisions the meeting reached, each an
   object with "text" and "passages". A proposal nobody agreed to is not a decision. If the
   meeting reached more, list the {MAXIMUM_DECISIONS} that matter most. An empty array is a correct
   answer.
5. "highlights" is an array of at most {MAXIMUM_HIGHLIGHTS} points of discussion worth remembering
   that are neither decisions nor action items, each an object with "text" and "passages". An
   empty array is a correct answer.
6. "action_items" is an array of at most {MAXIMUM_ACTION_ITEMS} tasks the meeting agreed will be
   done: someone committed to it, was asked to do it and accepted, or the meeting agreed it must be
   done. If the meeting agreed more, list the {MAXIMUM_ACTION_ITEMS} that matter most. Each is an
   object with exactly four keys:
   - "description": the task, in a few words;
   - "owner": the person or team who will do it, copied exactly as the transcript names them, or
     null if the transcript does not say who;
   - "due": the deadline copied word for word as it was said, such as "next Friday" or "by the
     14th", or null if no deadline was said;
   - "passages": the labels of the passages it is drawn from.
7. These are NOT action items: something already done, something cancelled or declined in the
   meeting, an idea parked or left for later, a suggestion nobody agreed to, and a plan that was
   only reported. An empty "action_items" array is a correct answer, and it must still be present.
8. Never guess an owner. When a speaker says "I'll" or "I will", the owner is the name on that
   speaker's label. If the line has no speaker label, the owner is null. Never complete a first
   name into a full name, and never choose one of two people.
9. Never turn a deadline into a date, and never invent a deadline.
10. Every "passages" array names 1 to {MAXIMUM_PASSAGES_PER_ELEMENT} labels, copied exactly from
    passage headers in this conversation: the passages it is most directly drawn from. Never
    invent, renumber or shorten a label.
11. Write only what the transcript says. Add no facts, names, numbers or dates it does not contain.
12. Keep each "text" and each "description" to at most {MAXIMUM_ELEMENT_CHARACTERS} characters,
    and each "owner" and each "due" to at most {MAXIMUM_PHRASE_CHARACTERS} characters.

One worked example. Its meeting, names and passages are EXAMPLE values and appear in no real
transcript: never reuse them, and never summarise a real meeting by its resemblance to the example.
"""


def _meeting_block(title: str, passages: list[str], first: int) -> str:
    """The title, then the passages under their headers: the shape of the example and of every real turn."""
    return (
        f"Meeting title: {neutralise_passage_headers(title.strip())}\n"
        f"Transcript passages:\n\n{_passage_block(passages, first)}"
    )


SUMMARY_SYSTEM_PROMPT = (
    _RULES
    + "\n"
    + _meeting_block(EXAMPLE_TITLE, EXAMPLE_PASSAGES, EXAMPLE_FIRST_PASSAGE)
    + "\n\nYour reply:\n"
    + EXAMPLE_REPLY
)


def build_summary_user_prompt(title: str, passages: list[str]) -> str:
    """The user turn: the title, the passages under ``[P1]`` to ``[Pn]``, then the reply instruction.

    **The title and the passages are untrusted input.** The one transformation is the header
    form's brackets (``neutralise_passage_headers``); see the module docstring for why that and
    no more. ``passages`` must be non-empty and hold at most MAXIMUM_PASSAGES, so that the worked
    example's labels can never name a real passage; the caller's cut at SUMMARY_INPUT_TOKENS
    guarantees it, and a caller that broke it would be a bug, so it raises ValueError.
    """
    if not passages:
        raise ValueError("summarise_meeting() needs at least one passage")
    if len(passages) > MAXIMUM_PASSAGES:
        raise ValueError(
            f"summarise_meeting() takes at most {MAXIMUM_PASSAGES} passages; the caller cuts the "
            f"transcript at SUMMARY_INPUT_TOKENS"
        )
    return _meeting_block(title, passages, 1) + f"\n\n{REPLY_INSTRUCTION}"


def build_summary_messages(title: str, passages: list[str]) -> list[dict]:
    """The chat messages for one summary call, in the OpenAI wire shape: system, then user.

    The Anthropic provider takes SUMMARY_SYSTEM_PROMPT and ``build_summary_user_prompt``
    separately, because that SDK carries the system prompt in its own parameter; the strings are
    the same either way.
    """
    return [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": build_summary_user_prompt(title, passages)},
    ]


# --- The attempt loop ------------------------------------------------------------------------


def run_summary_attempts(
    call_once: Callable[[], str | ChatReply],
    *,
    label: str,
    model: str,
    max_tokens: int | None = None,
) -> MeetingSummaryDraft:
    """Call ``call_once`` until it returns a conforming reply, or give up loudly.

    - ``call_once()`` makes one provider call and returns the reply, as a ChatReply or as bare
      text. A failed call (unreachable, timed out, a 5xx or, since D-118, a 429) raises
      ProviderUnavailable and is a failed attempt. A refused call, any other 4xx, raises
      ProviderRefused, and the loop re-raises it at once. The provider logs either 4xx first.
    - A reply that does not parse into SUMMARY_SCHEMA is a malformed reply (invariant 10). The
      first is retried; the second raises MalformedSummary at once, because FR-16 allows "one
      retry" for a malformed response (MAXIMUM_MALFORMED_SUMMARY_REPLIES).
    - Anything else ``call_once`` raises propagates untouched and consumes no retry: an exception
      the provider did not decide is a bug, not an outage.
    - After MAXIMUM_SUMMARY_ATTEMPTS (1 initial call + 2 retries), ProviderUnavailable naming
      ``label`` and the last failure. The caller marks the run Unavailable and queues it for
      retry (NFR-20); nothing about the transcript's storage or indexing depends on this call.

    Every attempt is recorded through apps/ai/attempt_log.py under the step "summarisation":
    failures at WARNING, the parsed attempt at INFO with its counts. No line quotes the reply:
    a schema violation names the schema's own keys and counts the reply's, never quoting them.
    ``model`` is the chat model the provider answered with, written onto the draft and not parsed.
    """
    last_detail = "no attempt was made"
    malformed = 0
    for number in range(1, MAXIMUM_SUMMARY_ATTEMPTS + 1):  # 1 initial call + 2 retries
        started = time.perf_counter()
        try:
            reply = call_once()
        except ProviderUnavailable as exc:
            last_detail = f"call failed: {exc}"
            attempt_log.failed_attempt(
                "summarisation", number, MAXIMUM_SUMMARY_ATTEMPTS, time.perf_counter() - started,
                attempt_log.cause_of(exc), str(exc),
                reply=attempt_log.ReplyFacts(max_tokens=max_tokens),
            )
            if isinstance(exc, ProviderRefused):
                raise  # D-118: a retry cannot fix a refusal; the caller queues the run
            continue
        if not isinstance(reply, ChatReply):
            reply = ChatReply(text=reply)
        facts = attempt_log.ReplyFacts(
            max_tokens=max_tokens,
            finish_reason=reply.finish_reason,
            completion_tokens=reply.completion_tokens,
            prompt_tokens=reply.prompt_tokens,
        )
        try:
            parsed = parse_summary(reply.text)
        except SchemaViolation as exc:
            # Invariant 10: a reply that does not conform is no reply at all.
            malformed += 1
            last_detail = f"schema violation: {exc}"
            attempt_log.failed_attempt(
                "summarisation", number, MAXIMUM_SUMMARY_ATTEMPTS, time.perf_counter() - started,
                "SchemaViolation", str(exc),
                reply=facts,
            )
            if malformed >= MAXIMUM_MALFORMED_SUMMARY_REPLIES:
                raise MalformedSummary(
                    f"{label} returned {malformed} replies not conforming to SUMMARY_SCHEMA, and "
                    f"FR-16 allows one retry for a malformed response; last failure: {last_detail}"
                ) from exc
            continue
        attempt_log.parsed_summary(
            number, MAXIMUM_SUMMARY_ATTEMPTS, time.perf_counter() - started,
            sentences=len(parsed.narrative), decisions=len(parsed.decisions),
            highlights=len(parsed.highlights), action_items=len(parsed.action_items),
            reply=facts,
        )
        return MeetingSummaryDraft(
            narrative=parsed.narrative,
            decisions=parsed.decisions,
            highlights=parsed.highlights,
            action_items=parsed.action_items,
            model=model,
        )
    raise ProviderUnavailable(
        f"{label} returned no response conforming to SUMMARY_SCHEMA in "
        f"{MAXIMUM_SUMMARY_ATTEMPTS} attempts; last failure: {last_detail}"
    )
