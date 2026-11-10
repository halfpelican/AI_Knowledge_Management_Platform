"""FR-10 classification: the AIService operation ``classify_document`` (docs/decisions.md D-104).

One document's type, department and tags in one structured call, against the scheme the
caller passes (``TagScheme``, apps/ai/base.py). This module holds everything that is
specific to that call and nothing that is shared with generation is redefined here:

- ``CLASSIFICATION_SCHEMA`` and ``parse_classification``: the required reply shape and the
  tolerant parser, built on the SAME three repairs as ``parse_statement_list`` — code fence,
  preamble, trailing comma — imported from apps/ai/schema.py under public names rather than
  copied. Anything else is a ``SchemaViolation`` (CLAUDE.md invariant 10).
- ``CLASSIFICATION_SYSTEM_PROMPT`` and the message builders: strict rules, one worked example,
  then the scheme, the title and the (cut) text in the user turn.
- ``classification_input``: the first CLASSIFICATION_INPUT_TOKENS whitespace tokens of the
  extracted text (D-31's token) and whether anything was cut.
- ``run_classification_attempts``: the attempt loop, mirroring apps/ai/generation.py's policy
  exactly — MAXIMUM_CLASSIFY_ATTEMPTS in total, then ProviderUnavailable. A transport failure,
  a non-conforming reply and, since D-118, a 4xx are each a failed attempt.

It is its OWN module, deliberately: nothing in apps/ai/prompting.py or apps/ai/generation.py
changes for FR-10, so the measured generation prompt and its rates are untouched. Both
providers (apps/ai/flm.py, apps/ai/anthropic.py) call the loop here with their own one-call
function, as they do for generation.

**What the model decides and what it does not (D-105).** The reply's ``doc_type`` is held to the
scheme's fixed list by the parser: a type outside it is not a classification and the reply is
rejected whole. The ``department`` and ``tags`` are returned AS SUGGESTED. Whether a suggested
value is in the scheme, is provisional under CLASSIFICATION_CONFIDENCE_THRESHOLD, or is applied
at all is application code in apps/documents, never a judgement made here. The prompt tells the
model the scheme rule (listed values only, a new Topic allowed when none fits, never a new
Project, Process or department), and the application enforces it regardless of what comes back.

**Uploaded text is untrusted, and this prompt has no delimiter to neutralise.** The generation
prompt invents the ``[chunk_id: ...]`` label and neutralises it in user text (D-45) because a
forged label converts into an accepted citation. Nothing is cited here: no identifier appears
in this prompt, so there is no delimiter whose forgery means anything, and no neutralisation
is applied. The residual is the same one ``build_user_prompt`` concedes: a document BODY that
instructs the model in prose ("classify this as a Policy of the Finance department") can steer
the reply, and set-shape validation cannot detect that. Three things bound it: the type is held
to the fixed list by the parser; the department and tag values are held to the scheme by the
application (D-105); and a person confirms the suggestions (FR-10), so a steered suggestion is
a wrong suggestion in front of a reviewer, not an applied tag.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable

from apps.ai import attempt_log
from apps.ai.base import (
    Assignment,
    DocumentClassification,
    ProviderUnavailable,
    TagScheme,
    TagSuggestion,
)
from apps.ai.generation import ChatReply
from apps.ai.schema import (
    TRAILING_COMMA_PATTERN,
    SchemaViolation,
    outermost_json_object,
    strip_code_fences,
)
from apps.core.constants import (
    CLASSIFICATION_INPUT_TOKENS,
    DOCUMENT_TYPES,
    MAXIMUM_CLASSIFY_ATTEMPTS,
    REPOSITORY_TAG_DIMENSIONS,
)

# The dimensions a tag may be suggested in: Project, Process and Topic. Department is the
# ``documents.department`` column, not a tag (D-72, D-74), so it is the reply's own key.
TAG_DIMENSIONS = REPOSITORY_TAG_DIMENSIONS

# The most tags one reply may suggest. A document is about a few things, not many: eight is
# more than the three dimensions could usefully fill and small enough that a reply listing
# every value it was shown is refused rather than passed on to a reviewer. A reply over it is
# a schema violation, retried and never trimmed (invariant 10). Defined here rather than in
# apps/core/constants.py because it is a parameter of this call, like GENERATION_MAX_TOKENS.
MAXIMUM_TAG_SUGGESTIONS = 8

# A single classification call's ceiling and timeout. The reply is one short object — at most
# eight tags beside two assignments, about 60 tokens each — so 400 is several times the longest
# conforming reply, and a reply that reaches it is listing things it should not. The timeout is
# generation's: a 4B model on the NPU reading 1,500 tokens of prompt. Every FLM call carries one.
CLASSIFICATION_MAX_TOKENS = 400
CLASSIFICATION_TIMEOUT_SECONDS = 300

# What a scheme line says when the scheme lists nothing for it.
NONE_LISTED = "(none listed)"

# The required reply shape, as JSON Schema, documented like STATEMENT_LIST_SCHEMA: it can be
# handed to a constrained-decoding option if FLM ever exposes one, and it is validated by hand
# in ``parse_classification`` below because the project takes no jsonschema dependency.
#
# ``doc_type.value``'s enum is DOCUMENT_TYPES, the fixed list FR-10 names. The parser holds the
# reply to ``scheme.doc_types``, which apps/documents builds from the same tuple, so the two
# cannot disagree in practice; where a scheme listed fewer, the scheme wins, because it is what
# the prompt showed the model. ``department.value`` is bounded by nothing here: the application
# decides whether it is in the scheme (D-105). Every ``confidence`` is a number in [0, 1]; a
# string, a boolean or a number outside the range is a violation.
_CONFIDENCE_SCHEMA = {"type": "number", "minimum": 0, "maximum": 1}
_ASSIGNMENT_PROPERTIES = {
    "value": {"type": "string", "minLength": 1},
    "confidence": _CONFIDENCE_SCHEMA,
}
CLASSIFICATION_SCHEMA = {
    "type": "object",
    "required": ["doc_type", "department", "tags"],
    "additionalProperties": False,
    "properties": {
        "doc_type": {
            "type": "object",
            "required": ["value", "confidence"],
            "additionalProperties": False,
            "properties": {
                "value": {"type": "string", "minLength": 1, "enum": list(DOCUMENT_TYPES)},
                "confidence": _CONFIDENCE_SCHEMA,
            },
        },
        "department": {
            "type": "object",
            "required": ["value", "confidence"],
            "additionalProperties": False,
            "properties": dict(_ASSIGNMENT_PROPERTIES),
        },
        "tags": {
            "type": "array",
            "maxItems": MAXIMUM_TAG_SUGGESTIONS,
            "items": {
                "type": "object",
                "required": ["dimension", "value", "confidence"],
                "additionalProperties": False,
                "properties": {
                    "dimension": {"type": "string", "enum": list(TAG_DIMENSIONS)},
                    "value": {"type": "string", "minLength": 1},
                    "confidence": _CONFIDENCE_SCHEMA,
                },
            },
        },
    },
}

_TOP_LEVEL_KEYS = frozenset(CLASSIFICATION_SCHEMA["required"])
_ASSIGNMENT_KEYS = frozenset(("value", "confidence"))
_TAG_KEYS = frozenset(("dimension", "value", "confidence"))


@dataclass(frozen=True)
class ParsedClassification:
    """What ``parse_classification`` returns: the reply's three parts, and nothing about who said it.

    The attempt loop turns it into a DocumentClassification by adding the provider's ``model``
    and the caller's ``input_truncated``; the parser knows neither, which is the point of the
    intermediate type.
    """

    doc_type: Assignment
    department: Assignment
    tags: tuple[TagSuggestion, ...]


# --- The parser ------------------------------------------------------------------------------


def parse_classification(raw: str, scheme: TagScheme) -> ParsedClassification:
    """Parse a raw model reply into a ParsedClassification, or raise SchemaViolation.

    The same tolerance as ``parse_statement_list`` and no more: a markdown code fence, a
    sentence of preamble around the object and a trailing comma are repaired, through the
    same three pieces of code (apps/ai/schema.py). Anything still unparseable, or parseable
    but the wrong shape, is rejected outright rather than repaired into a plausible-looking
    classification (invariant 10). In particular:

    - ``doc_type.value`` must be one of ``scheme.doc_types``, exactly. A type outside the fixed
      list is not a classification, so the whole reply is a violation, not a reply with a type
      the application could correct.
    - A ``confidence`` that is a string, a boolean, or a number outside [0, 1] is a violation.
      ``"0.8"`` is not repaired to 0.8.
    - An empty ``value`` anywhere is a violation.
    - More than MAXIMUM_TAG_SUGGESTIONS tags is a violation; the array is counted as returned,
      duplicates included, and nothing is trimmed to fit.
    - A tag with the same dimension and the same name as an earlier one, after
      ``normalise_tag_name`` (lower case, single spaces), is dropped and the FIRST is kept. This
      is a SHAPE tolerance, like the trailing comma — two spellings of one tag are one
      suggestion, not two, and a Tag row is unique per normalised name and dimension — and not a
      repair of the reply's content: no value is changed, re-ranked or invented.

    Surrounding whitespace is stripped from every string value, as the statement parser strips
    its text and identifiers. ``department`` is returned as given; whether it is in the scheme
    is the application's decision (D-105).
    """
    # Lazy, so that importing a provider module does not import a models module: nothing in
    # apps/ai does at import time, and scripts/citation_harness.py imports providers only after
    # django.setup(). The one definition of tag-name equality lives on the Tag model (D-74's
    # seed and apps/api/serializers.py use the same function), and it is not restated here.
    from apps.documents.models import normalise_tag_name

    if not isinstance(raw, str) or not raw.strip():
        raise SchemaViolation("empty response")
    candidate = outermost_json_object(strip_code_fences(raw))
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            decoded = json.loads(TRAILING_COMMA_PATTERN.sub("", candidate))
        except json.JSONDecodeError as exc:
            raise SchemaViolation(f"not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise SchemaViolation(f"top level is {type(decoded).__name__}, not an object")
    missing = sorted(_TOP_LEVEL_KEYS - set(decoded))
    if missing:
        raise SchemaViolation(f"missing top-level key(s): {missing} (keys: {sorted(decoded)})")
    extra = sorted(set(decoded) - _TOP_LEVEL_KEYS)
    if extra:
        raise SchemaViolation(f"unexpected top-level key(s): {extra}")

    doc_type = _assignment(decoded["doc_type"], "doc_type")
    if doc_type.value not in scheme.doc_types:
        # Invariant 10 applied to FR-10's fixed list: the value is not quoted, because a
        # reply's content is not written into the attempt log (apps/ai/attempt_log.py).
        raise SchemaViolation("doc_type value is not one of the scheme's document types")
    department = _assignment(decoded["department"], "department")

    items = decoded["tags"]
    if not isinstance(items, list):
        raise SchemaViolation(f"'tags' is {type(items).__name__}, not an array")
    if len(items) > MAXIMUM_TAG_SUGGESTIONS:
        raise SchemaViolation(
            f"{len(items)} tags, more than the {MAXIMUM_TAG_SUGGESTIONS} allowed"
        )
    tags: list[TagSuggestion] = []
    seen: set[tuple[str, str]] = set()
    for position, item in enumerate(items):
        tag = _tag(item, position)
        key = (tag.dimension, normalise_tag_name(tag.value))
        if key in seen:
            continue  # the first spelling of this tag is kept; see the docstring
        seen.add(key)
        tags.append(tag)
    return ParsedClassification(doc_type=doc_type, department=department, tags=tuple(tags))


def _assignment(item, where: str) -> Assignment:
    """One ``{"value": ..., "confidence": ...}`` object, or SchemaViolation naming ``where``."""
    if not isinstance(item, dict):
        raise SchemaViolation(f"'{where}' is {type(item).__name__}, not an object")
    missing = sorted(_ASSIGNMENT_KEYS - set(item))
    if missing:
        raise SchemaViolation(f"'{where}' is missing {missing}")
    unexpected = sorted(set(item) - _ASSIGNMENT_KEYS)
    if unexpected:
        raise SchemaViolation(f"'{where}' has unexpected key(s): {unexpected}")
    return Assignment(
        value=_text(item["value"], f"'{where}'"),
        confidence=_confidence(item["confidence"], f"'{where}'"),
    )


def _tag(item, position: int) -> TagSuggestion:
    """One tag object, or SchemaViolation naming its position."""
    where = f"tag {position}"
    if not isinstance(item, dict):
        raise SchemaViolation(f"{where} is {type(item).__name__}, not an object")
    missing = sorted(_TAG_KEYS - set(item))
    if missing:
        raise SchemaViolation(f"{where} is missing {missing}")
    unexpected = sorted(set(item) - _TAG_KEYS)
    if unexpected:
        raise SchemaViolation(f"{where} has unexpected key(s): {unexpected}")
    dimension = item["dimension"]
    if not isinstance(dimension, str) or dimension.strip() not in TAG_DIMENSIONS:
        raise SchemaViolation(f"{where} has a dimension outside {list(TAG_DIMENSIONS)}")
    return TagSuggestion(
        dimension=dimension.strip(),
        value=_text(item["value"], where),
        confidence=_confidence(item["confidence"], where),
    )


def _text(value, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaViolation(f"{where} has an empty or non-string 'value'")
    return value.strip()


def _confidence(value, where: str) -> float:
    # bool is an int subclass in Python; ``true`` is not a confidence of 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaViolation(f"{where} has a non-numeric 'confidence'")
    if not 0 <= value <= 1:  # also false for NaN, which json.loads admits
        raise SchemaViolation(f"{where} has a 'confidence' outside [0, 1]")
    return float(value)


# --- The input -------------------------------------------------------------------------------


def classification_input(text: str) -> tuple[str, bool]:
    """The first CLASSIFICATION_INPUT_TOKENS whitespace tokens of ``text``, and whether any were cut.

    D-31's token: a whitespace-delimited word, which is ``str.split()``; the tokens are joined
    back with single spaces, so line breaks and runs of whitespace do not survive into the
    prompt. The opening of a document is where its kind is stated, and the cut keeps the prompt
    inside the 4B model's window (apps/core/constants.py explains the number). The flag is
    recorded on the DocumentClassification as ``input_truncated``, so the record says the model
    read the opening rather than the whole (FR-10's sectioned summarising of long documents is
    deferred). Idempotent: cutting a cut text changes nothing.
    """
    tokens = text.split()
    truncated = len(tokens) > CLASSIFICATION_INPUT_TOKENS
    return " ".join(tokens[:CLASSIFICATION_INPUT_TOKENS]), truncated


# --- The prompt ------------------------------------------------------------------------------
#
# READ THE COMMENT ABOVE SYSTEM_PROMPT IN apps/ai/prompting.py BEFORE EDITING THE EXAMPLE. The
# lesson measured there twice — A WORKED EXAMPLE IS TRAINING DATA FOR THE RESPONSE, IN ITS
# IDENTIFIERS AND IN ITS CONTENT — applies here to CONTENT, because this prompt carries no
# identifiers: the model will reach into the example's departments, tag values and subject
# when a real document resembles them. So the example's subject is lighthouse keeping, and its
# departments and tags are things no organisation's scheme holds; the only values it shares
# with a real prompt are the four document types, which FR-10 fixes and which it cannot avoid.
# apps/ai/tests/test_classification_prompt.py asserts the example's values appear in no real
# scheme and in no real user turn.
#
# The example reply uses LISTED values only and proposes no new Topic, although rule 6 allows
# one. Demonstrated behaviour is copied: an example that invented a Topic would invent one for
# every document, and a reviewer would confirm a stream of near-synonyms. The allowance is
# therefore stated as a rule and not shown. If a measurement on the development documents finds
# the model never proposes one, that is the place to revisit, with the rate recorded.

EXAMPLE_SCHEME = TagScheme(
    doc_types=DOCUMENT_TYPES,
    departments=("Lantern Room", "Kelp Drying Shed"),
    tags={
        "Project": ("foghorn overhaul",),
        "Process": ("wick trimming",),
        "Topic": ("seabird nesting", "lens soot"),
    },
)
EXAMPLE_TITLE = "Trimming the lamp wicks before dusk"
EXAMPLE_TEXT = classification_input(
    """
    Each evening before the lamp is lit, the keeper trims both wicks square to a quarter inch
    and wipes the lens with a dry cloth. A ragged wick smokes the glass within the hour, and a
    sooted lens cannot be seen from the shoals.
    """
)[0]
EXAMPLE_REPLY = json.dumps(
    {
        "doc_type": {"value": "Procedure", "confidence": 0.92},
        "department": {"value": "Lantern Room", "confidence": 0.88},
        "tags": [
            {"dimension": "Process", "value": "wick trimming", "confidence": 0.9},
            {"dimension": "Topic", "value": "lens soot", "confidence": 0.75},
        ],
    }
)

REPLY_INSTRUCTION = "Reply with the JSON object only."

_RULES = f"""\
You classify one document against an established scheme and reply with JSON.

Rules, all of them mandatory:
1. Reply with one JSON object and nothing else: no greeting, no explanation, no
   markdown code fence, no text before or after the object.
2. The object has exactly three keys: "doc_type", "department" and "tags".
3. "doc_type" is an object with exactly two keys: "value", one of the document types
   listed, copied exactly; and "confidence", a number from 0 to 1. Choose the type by the
   document's purpose:
   - Policy: states the organisation's rules or entitlements, what is allowed or required.
   - Procedure: sets out the steps to follow to get something done.
   - Report: presents information, figures or results, about a period, a register, an
     inventory or an audit.
   - Meeting Paper: is written for a committee, board or meeting, to put a proposal, a
     decision or a briefing before it. It usually names the meeting or the decision sought.
4. "department" is an object with the same two keys. Its "value" is one of the
   departments listed, copied exactly. Only if no department is listed, give the
   department the document itself names, or "Unknown" if it names none.
5. "tags" is an array of at most {MAXIMUM_TAG_SUGGESTIONS} objects, each with exactly three keys:
   "dimension", one of "Project", "Process" or "Topic"; "value"; and "confidence".
6. A tag's "value" is one of the values listed for its dimension, copied exactly. The
   one exception: when no listed Topic fits, you may propose a new Topic value of one
   to three words. Never propose a new Project, a new Process or a new department.
7. Give a tag only where the document is clearly about it, and never with an empty
   "value". If no listed value fits a dimension, and it is not a new Topic you are
   proposing, leave that dimension out. An empty "tags" array is a correct answer.
8. Every "confidence" is your honest estimate, from 0 (a guess) to 1 (certain), that the
   value is right for this document.

One worked example. Its departments, tag values and subject are EXAMPLE values and appear
in no real scheme: never reuse them, and never classify a real document by its
resemblance to the example.
"""


def _listed(values) -> str:
    return "; ".join(values) if values else NONE_LISTED


def _document_block(title: str, text: str, scheme: TagScheme) -> str:
    """The scheme lists, then the title, then the text: the shape of the example and of every real turn."""
    lines = [
        f"Document types (choose one): {_listed(scheme.doc_types)}",
        f"Departments (choose one): {_listed(scheme.departments)}",
        *[f"{dimension} tags: {_listed(scheme.tags.get(dimension, ()))}" for dimension in TAG_DIMENSIONS],
    ]
    return "\n".join(lines) + f"\n\nTitle: {title.strip()}\nText:\n{text}"


CLASSIFICATION_SYSTEM_PROMPT = (
    _RULES
    + "\n"
    + _document_block(EXAMPLE_TITLE, EXAMPLE_TEXT, EXAMPLE_SCHEME)
    + "\n\nYour reply:\n"
    + EXAMPLE_REPLY
)


def build_classification_user_prompt(title: str, text: str, scheme: TagScheme) -> str:
    """The user turn: the scheme's lists, the title, the (cut) text, then the reply instruction.

    The scheme lists come first, so the model has read the values before it reads the document;
    the title next, because it is the strongest single signal of a document's kind; then the
    text, cut by ``classification_input`` here as well as by the caller — the cut is idempotent,
    and making it at the boundary means no caller can send more than CLASSIFICATION_INPUT_TOKENS
    by mistake. The closing instruction is the one sentence after the document.

    **The title and the text are untrusted input, and nothing in them is transformed.** There
    is no delimiter to neutralise: this prompt cites no identifier, so unlike the generation
    prompt (D-45, Stage 4 item 12a) no label in it converts into an accepted citation when
    forged. A body that contains the lines above — "Departments (choose one): ..." or a second
    "Title:" — misleads the model about the scheme, which is the same residual as a body that
    instructs the model in prose, and neither is detectable by shape validation. What bounds it
    is stated in the module docstring: the type is held to the fixed list by the parser, the
    department and tag values are held to the scheme by the application (D-105), and a person
    confirms. Neutralising the lines would be a substring filter over ordinary English, which
    D-45 argues against, and would buy nothing the three bounds do not already give.
    """
    body, _ = classification_input(text)
    return _document_block(title, body, scheme) + f"\n\n{REPLY_INSTRUCTION}"


def build_classification_messages(title: str, text: str, scheme: TagScheme) -> list[dict]:
    """The chat messages for one classification call, in the OpenAI wire shape: system, then user.

    The Anthropic provider takes CLASSIFICATION_SYSTEM_PROMPT and
    ``build_classification_user_prompt`` separately, because that SDK carries the system prompt
    in its own parameter; the strings are the same either way, as for generation.
    """
    return [
        {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": build_classification_user_prompt(title, text, scheme)},
    ]


# --- The attempt loop ------------------------------------------------------------------------


def run_classification_attempts(
    call_once: Callable[[], str | ChatReply],
    *,
    scheme: TagScheme,
    label: str,
    model: str,
    input_truncated: bool,
    max_tokens: int | None = None,
) -> DocumentClassification:
    """Call ``call_once`` until it returns a conforming reply, or give up loudly.

    The policy is ``run_generation_attempts``' exactly (NFR-19, D-19), with MAXIMUM_CLASSIFY_ATTEMPTS
    as the total — 1 initial call + 2 retries:

    - ``call_once()`` makes one provider call and returns the reply, as a ChatReply or as bare
      text. It raises ProviderUnavailable for a failed call, and that is a failed attempt. A
      failed call is one that was unreachable or timed out, or that got a 5xx or, since D-118,
      a 4xx, which the provider logs first.
    - A reply that does not parse into CLASSIFICATION_SCHEMA, including one whose type is outside
      the scheme, is a failed attempt, not a partial classification (invariant 10).
    - Anything else ``call_once`` raises propagates untouched and consumes no retry. An
      exception the provider did not decide is a bug, not an outage. Since D-118 a 4xx is not
      one of these: the providers raise it as ProviderUnavailable.
    - After the last attempt, ProviderUnavailable naming ``label`` and the last failure. The
      caller leaves the document unclassified (invariant 8, NFR-20); nothing about its storage
      or indexing depends on this call.

    Every attempt is recorded through apps/ai/attempt_log.py under the step "classification":
    failures at WARNING, the parsed attempt at INFO, each with the reply facts the provider
    reported. There is no observer: the ``on_attempt`` hook is generation's, for the citation
    harness, and nothing measures classification per attempt.

    ``model`` is the chat model the provider answered with, for the DocumentAnalysis record, and
    ``input_truncated`` is ``classification_input``'s flag; both are written onto the returned
    DocumentClassification and neither is parsed. ``max_tokens`` is the value the provider's
    request carried, recorded on each attempt's line.
    """
    last_detail = "no attempt was made"
    for number in range(1, MAXIMUM_CLASSIFY_ATTEMPTS + 1):  # 1 initial call + 2 retries
        started = time.perf_counter()
        try:
            reply = call_once()
        except ProviderUnavailable as exc:
            last_detail = f"call failed: {exc}"
            attempt_log.failed_attempt(
                "classification", number, MAXIMUM_CLASSIFY_ATTEMPTS, time.perf_counter() - started,
                attempt_log.cause_of(exc), str(exc),
                reply=attempt_log.ReplyFacts(max_tokens=max_tokens),
            )
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
            parsed = parse_classification(reply.text, scheme)
        except SchemaViolation as exc:
            # Invariant 10: a reply that does not conform is no reply at all.
            last_detail = f"schema violation: {exc}"
            attempt_log.failed_attempt(
                "classification", number, MAXIMUM_CLASSIFY_ATTEMPTS, time.perf_counter() - started,
                "SchemaViolation", str(exc),
                reply=facts,
            )
            continue
        attempt_log.parsed_classification(
            number, MAXIMUM_CLASSIFY_ATTEMPTS, time.perf_counter() - started, len(parsed.tags),
            reply=facts,
        )
        return DocumentClassification(
            doc_type=parsed.doc_type,
            department=parsed.department,
            tags=parsed.tags,
            model=model,
            input_truncated=input_truncated,
        )
    raise ProviderUnavailable(
        f"{label} returned no response conforming to CLASSIFICATION_SCHEMA in "
        f"{MAXIMUM_CLASSIFY_ATTEMPTS} attempts; last failure: {last_detail}"
    )
