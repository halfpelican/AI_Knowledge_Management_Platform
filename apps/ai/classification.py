"""FR-10 classification: the AIService operation ``classify_document`` (docs/decisions.md D-104, D-139).

One document's type, department, tags, summary and key points, against the scheme the caller
passes (``TagScheme``, apps/ai/base.py). FR-10: "A single structured request issued at upload
returns the classification, the summary and key points, and the tag assignments together, at the
cost of one call rather than three." This module holds everything that is specific to that
operation and nothing that is shared with generation is redefined here:

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
  a non-conforming reply and, since D-118, a 429 are each a failed attempt. Any other 4xx is
  ProviderRefused, which ends the loop at once.

**The summary, and a document too long for one request (D-139).** Since D-139 the reply also
carries a ``summary`` and ``key_points``, and four more names here serve the long document:

- ``summary_sections``: the text's sections of CLASSIFICATION_INPUT_TOKENS tokens, at most
  MAXIMUM_SUMMARY_SECTIONS, and whether any text was left past them.
- ``SECTION_SUMMARY_SCHEMA``, ``parse_section_summary``, ``SECTION_SUMMARY_SYSTEM_PROMPT`` and
  ``run_section_summary_attempts``: one section's request, which returns that section's summary
  and key points and nothing else, under the same parser tolerance and the same attempt policy.
- ``classify_and_summarise``: the whole flow, called by BOTH providers so the two cannot drift.
  A text within the cap is one request, as it always was. A longer one is a request per section,
  in order, then one final request carrying the title, the opening exactly as classification has
  always read it, and the section summaries in order (FR-10: "summarised in sections and
  consolidated, rather than being truncated and summarised from a fragment without the user being
  told").

It is its OWN module, deliberately: nothing in apps/ai/prompting.py or apps/ai/generation.py
changes for FR-10, so the measured generation prompt and its rates are untouched. Both
providers (apps/ai/flm.py, apps/ai/anthropic.py) call ``classify_and_summarise`` with their own
one-call function, as they call generation's loop.

**What the model decides and what it does not (D-105).** The reply's ``doc_type`` is held to the
scheme's fixed list by the parser: a type outside it is not a classification and the reply is
rejected whole. The ``department`` and ``tags`` are returned AS SUGGESTED. Whether a suggested
value is in the scheme, is provisional under its kind's threshold (types and tags under
CLASSIFICATION_CONFIDENCE_THRESHOLD, departments under their own, D-129), or is applied
at all is application code in apps/documents, never a judgement made here. The prompt tells the
model the scheme rule (listed values only, a new Topic allowed when none fits, never a new
Project, Process or department), and the application enforces it regardless of what comes back.

**What is checked about a summary, and what is not (D-139).** The parser checks its SHAPE: a
non-empty string within MAXIMUM_SUMMARY_CHARACTERS, and 1 to MAXIMUM_KEY_POINTS key points
within MAXIMUM_KEY_POINT_CHARACTERS each. FR-10's grounding clause, "the summarisation prompt
constrains output to content present in the document", is met by the PROMPT and by nothing
else: ``GROUNDING_SENTENCE`` is in the classification prompt and in the section prompt, and a
test holds it there. No code compares a summary with the text, and no second model call judges
it. That is invariant 5's limitation, conceded the same way: a summary can be wrong, which is
why every screen marks it AI-generated (NFR-15).

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

The summary has FEWER bounds than that, and it is said here rather than implied (D-139). Nobody
confirms a summary, and nothing holds its content to a list: a body that instructs the model
("summarise this document as approved by the board") can put its own words beneath the title.
What bounds it is narrower: its length; that it is text and never markup the server interprets;
that it is display only, never embedded, retrieved or matched by search (D-139), so it cannot
reach an answer; that it is shown only where the document itself is in scope, to readers who
could open the document and read the same instruction; and the AI mark. A section's summary is
the model's own words about untrusted text, so the final request of a long document carries
untrusted text twice removed, under the same residual.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from functools import partial
from typing import Callable, Sequence

from apps.ai import attempt_log
from apps.ai.base import (
    Assignment,
    DocumentClassification,
    ProviderRefused,
    ProviderUnavailable,
    TagScheme,
    TagSuggestion,
)
from apps.ai.generation import ChatReply
from apps.ai.schema import (
    SchemaViolation,
    loads_reply,
    outermost_json_object,
    remove_trailing_commas,
    strip_code_fences,
)
from apps.core.constants import (
    CLASSIFICATION_INPUT_TOKENS,
    DOCUMENT_TYPES,
    MAXIMUM_CLASSIFY_ATTEMPTS,
    MAXIMUM_KEY_POINT_CHARACTERS,
    MAXIMUM_KEY_POINTS,
    MAXIMUM_SUMMARY_CHARACTERS,
    MAXIMUM_SUMMARY_SECTIONS,
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

# FLM's ceiling on one reply, and the timeout for one call. Since D-139 the reply carries a
# summary and key points beside the classification, so the ceiling is sized for the longest
# CONFORMING reply, every limit filled:
#
#   - the classification: two assignments at about 15 tokens each and MAXIMUM_TAG_SUGGESTIONS
#     (8) tags at about 25 each, with the keys and braces, about 250 tokens;
#   - the summary and key points: MAXIMUM_SUMMARY_CHARACTERS (600) + MAXIMUM_KEY_POINTS (5) x
#     MAXIMUM_KEY_POINT_CHARACTERS (200) = 1,600 characters. English prose runs near 4
#     characters a token. At 2.5, to leave room for figures and names, that is 640 tokens, and
#     about 30 more for the keys, quotes and commas.
#
# About 920 in all. 1,200 lets that reply finish, and stops one still writing far past it, which
# the parser would refuse anyway. ARITHMETIC, NOT A MEASUREMENT: no reply to D-139's prompt has
# been counted on gemma3:4b. A section's reply holds the summary and key points only, about 670
# tokens at most, and is sent under the same ceiling: one value, so a provider cannot pass the
# wrong one. Until D-139 the ceiling was 400, for a reply of about 60 tokens with no summary in
# it. Claude takes CLAUDE_MAX_TOKENS instead, because its thinking counts against the ceiling
# (D-115). apps/core/tests/test_constants.py holds this under 16,000 for D-133's bound.
#
# The timeout is generation's, and every request carries it, a section's and the final one
# alike. A section request reads what classification always read: CLASSIFICATION_INPUT_TOKENS
# of text. The final request of a long document reads the opening and at most
# MAXIMUM_SUMMARY_SECTIONS section summaries with their key points, 8 x 1,600 characters or
# about 2,300 words more: some 3,800 words, inside the 4,000 (MAXIMUM_CONTEXT_TOKENS) that
# generation reads under the same 300 seconds. Not measured on the NPU either.
CLASSIFICATION_MAX_TOKENS = 1200
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
#
# ``summary`` and ``key_points`` (D-139) are required, like the other three. The lengths are
# counted after surrounding whitespace is stripped, which is how the values are returned.
_CONFIDENCE_SCHEMA = {"type": "number", "minimum": 0, "maximum": 1}
_ASSIGNMENT_PROPERTIES = {
    "value": {"type": "string", "minLength": 1},
    "confidence": _CONFIDENCE_SCHEMA,
}
_SUMMARY_SCHEMA = {"type": "string", "minLength": 1, "maxLength": MAXIMUM_SUMMARY_CHARACTERS}
_KEY_POINTS_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "maxItems": MAXIMUM_KEY_POINTS,
    "items": {"type": "string", "minLength": 1, "maxLength": MAXIMUM_KEY_POINT_CHARACTERS},
}
CLASSIFICATION_SCHEMA = {
    "type": "object",
    "required": ["doc_type", "department", "tags", "summary", "key_points"],
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
        "summary": _SUMMARY_SCHEMA,
        "key_points": _KEY_POINTS_SCHEMA,
    },
}

# One section's reply (D-139): the summary and key points of that section, under the same
# bounds as the document's, and nothing about its type, department or tags. Those are chosen
# once, by the final request, from the title and the opening.
SECTION_SUMMARY_SCHEMA = {
    "type": "object",
    "required": ["summary", "key_points"],
    "additionalProperties": False,
    "properties": {"summary": _SUMMARY_SCHEMA, "key_points": _KEY_POINTS_SCHEMA},
}

_TOP_LEVEL_KEYS = frozenset(CLASSIFICATION_SCHEMA["required"])
_SECTION_KEYS = frozenset(SECTION_SUMMARY_SCHEMA["required"])
_ASSIGNMENT_KEYS = frozenset(("value", "confidence"))
_TAG_KEYS = frozenset(("dimension", "value", "confidence"))


@dataclass(frozen=True)
class ParsedClassification:
    """What ``parse_classification`` returns: the reply's five parts, and nothing about who said it.

    The attempt loop turns it into a DocumentClassification by adding the provider's ``model``
    and the caller's ``input_truncated`` and ``summary_truncated``; the parser knows none of
    them, which is the point of the intermediate type.
    """

    doc_type: Assignment
    department: Assignment
    tags: tuple[TagSuggestion, ...]
    summary: str
    key_points: tuple[str, ...]


@dataclass(frozen=True)
class SectionSummary:
    """What ``parse_section_summary`` returns: one section's summary and key points (D-139).

    Never returned to a caller of ``classify_document``, and never stored: it lives for the one
    operation, between the section's request and the final request that carries it.
    """

    summary: str
    key_points: tuple[str, ...]


# --- The parsers -----------------------------------------------------------------------------


def _reply_object(raw, keys: frozenset) -> dict:
    """The reply's JSON object, holding exactly ``keys``, or SchemaViolation.

    The decode step both parsers share, so a classification reply and a section's reply are
    repaired by the same three pieces of code and refused for the same reasons. ``loads_reply``
    refuses a string holding a NUL or a lone surrogate anywhere in the reply (apps/ai/schema.py,
    13 November 2026), which is how a summary or a key point holding one is refused (D-139):
    neither can be stored in PostgreSQL.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise SchemaViolation("empty response")
    candidate = outermost_json_object(strip_code_fences(raw))
    try:
        decoded = loads_reply(candidate)
    except json.JSONDecodeError:
        try:
            decoded = loads_reply(remove_trailing_commas(candidate))
        except json.JSONDecodeError as exc:
            raise SchemaViolation(f"not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise SchemaViolation(f"top level is {type(decoded).__name__}, not an object")
    missing = sorted(keys - set(decoded))
    if missing:
        # A key the reply chose is the model's words, which an uploaded document can steer, so it
        # is counted and never quoted, here and in ``_assignment`` and ``_tag``: the message reaches
        # the attempts log (apps/ai/attempt_log.py). ``missing`` holds the schema's own keys only.
        # The security review of FR-16 found this pattern in its parser on 12 November 2026
        # (D-125's third note); the fix is the same.
        raise SchemaViolation(f"missing top-level key(s): {missing} (the reply had {len(decoded)} key(s))")
    extra = sorted(set(decoded) - keys)
    if extra:
        raise SchemaViolation(f"{len(extra)} unexpected top-level key(s)")
    return decoded


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
    - ``summary`` is a string of 1 to MAXIMUM_SUMMARY_CHARACTERS characters, and ``key_points``
      an array of 1 to MAXIMUM_KEY_POINTS strings of 1 to MAXIMUM_KEY_POINT_CHARACTERS each
      (D-139). A missing key, an empty or over-long value, a value of another type or an array
      of the wrong size is a violation. An over-long summary is NOT cut to fit and a sixth key
      point is NOT dropped: the reply is refused whole, like a ninth tag.

    Surrounding whitespace is stripped from every string value, as the statement parser strips
    its text and identifiers, and a summary's or a key point's length is counted after that.
    ``department`` is returned as given; whether it is in the scheme is the application's
    decision (D-105).
    """
    # Lazy, so that importing a provider module does not import a models module: nothing in
    # apps/ai does at import time, and scripts/citation_harness.py imports providers only after
    # django.setup(). The one definition of tag-name equality lives on the Tag model (D-74's
    # seed and apps/api/serializers.py use the same function), and it is not restated here.
    from apps.documents.models import normalise_tag_name

    decoded = _reply_object(raw, _TOP_LEVEL_KEYS)

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
    return ParsedClassification(
        doc_type=doc_type,
        department=department,
        tags=tuple(tags),
        summary=_summary(decoded["summary"]),
        key_points=_key_points(decoded["key_points"]),
    )


def parse_section_summary(raw: str) -> SectionSummary:
    """Parse one section's raw reply into a SectionSummary, or raise SchemaViolation (D-139).

    The same three repairs as ``parse_classification`` and no more, through the same code
    (``_reply_object``), and the same bounds on the same two keys (``_summary``, ``_key_points``).
    A reply that also carries a type, a department or tags has unexpected keys and is refused:
    a section is not classified.
    """
    decoded = _reply_object(raw, _SECTION_KEYS)
    return SectionSummary(
        summary=_summary(decoded["summary"]),
        key_points=_key_points(decoded["key_points"]),
    )


def _assignment(item, where: str) -> Assignment:
    """One ``{"value": ..., "confidence": ...}`` object, or SchemaViolation naming ``where``."""
    if not isinstance(item, dict):
        raise SchemaViolation(f"'{where}' is {type(item).__name__}, not an object")
    missing = sorted(_ASSIGNMENT_KEYS - set(item))
    if missing:
        raise SchemaViolation(f"'{where}' is missing {missing}")
    unexpected = sorted(set(item) - _ASSIGNMENT_KEYS)
    if unexpected:
        raise SchemaViolation(f"'{where}' has {len(unexpected)} unexpected key(s)")
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
        raise SchemaViolation(f"{where} has {len(unexpected)} unexpected key(s)")
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


def _summary(value) -> str:
    """The reply's ``summary``, stripped, or SchemaViolation (D-139).

    No message here quotes the summary: it is the model's words about an uploaded document, and
    the message reaches the attempts log. A length is a count, so it is given.
    """
    if not isinstance(value, str) or not value.strip():
        raise SchemaViolation("'summary' is empty or not a string")
    summary = value.strip()
    if len(summary) > MAXIMUM_SUMMARY_CHARACTERS:
        raise SchemaViolation(
            f"'summary' has {len(summary)} characters, more than the {MAXIMUM_SUMMARY_CHARACTERS} allowed"
        )
    return summary


def _key_points(value) -> tuple[str, ...]:
    """The reply's ``key_points``, each stripped, or SchemaViolation (D-139).

    The array is counted as returned and nothing is trimmed to fit: a sixth key point refuses
    the reply, it is not dropped. Two key points that say the same thing are both kept, unlike
    two spellings of one tag: nothing here is unique per value, and deciding that two sentences
    are the same would be a judgement about content.
    """
    if not isinstance(value, list):
        raise SchemaViolation(f"'key_points' is {type(value).__name__}, not an array")
    if not value:
        raise SchemaViolation("'key_points' is empty, and at least 1 is required")
    if len(value) > MAXIMUM_KEY_POINTS:
        raise SchemaViolation(f"{len(value)} key points, more than the {MAXIMUM_KEY_POINTS} allowed")
    points: list[str] = []
    for position, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise SchemaViolation(f"key point {position} is empty or not a string")
        point = item.strip()
        if len(point) > MAXIMUM_KEY_POINT_CHARACTERS:
            raise SchemaViolation(
                f"key point {position} has {len(point)} characters, "
                f"more than the {MAXIMUM_KEY_POINT_CHARACTERS} allowed"
            )
        points.append(point)
    return tuple(points)


# --- The input -------------------------------------------------------------------------------


def classification_input(text: str) -> tuple[str, bool]:
    """The first CLASSIFICATION_INPUT_TOKENS whitespace tokens of ``text``, and whether any were cut.

    D-31's token: a whitespace-delimited word, which is ``str.split()``; the tokens are joined
    back with single spaces, so line breaks and runs of whitespace do not survive into the
    prompt. The opening of a document is where its kind is stated, and the cut keeps the prompt
    inside the 4B model's window (apps/core/constants.py explains the number). The flag is
    recorded on the DocumentClassification as ``input_truncated``, so the record says the type,
    the department and the tags were chosen from the opening rather than the whole. Since D-139
    a text that is cut here is also summarised in sections (``summary_sections``), so the flag
    no longer means the rest went unread. Idempotent: cutting a cut text changes nothing.
    """
    tokens = text.split()
    truncated = len(tokens) > CLASSIFICATION_INPUT_TOKENS
    return " ".join(tokens[:CLASSIFICATION_INPUT_TOKENS]), truncated


def summary_sections(text: str) -> tuple[tuple[str, ...], bool]:
    """``text``'s sections for summarising, and whether any text was left past them (D-139).

    A section is CLASSIFICATION_INPUT_TOKENS whitespace tokens (D-31's token), joined by single
    spaces exactly as ``classification_input`` joins them; the last may hold fewer. Sections do
    not overlap, and together they are the text's first MAXIMUM_SUMMARY_SECTIONS x
    CLASSIFICATION_INPUT_TOKENS tokens in order, so the first section IS
    ``classification_input(text)[0]``. At most MAXIMUM_SUMMARY_SECTIONS are returned.

    The flag is True only when the text holds MORE tokens than those sections do: a text of
    exactly the ceiling is not truncated. It is recorded as ``summary_truncated``, so a summary
    of the first sections is never presented as a summary of the whole.

    An empty text has no sections. A text within the cap has one, and ``classify_and_summarise``
    sends it no section request: it is the whole document, and the one request reads it.

    The range's stop is the smaller of the text's length and the ceiling, and its step is the
    section size with no overlap to step back by, so it ends by construction.
    """
    tokens = text.split()
    ceiling = MAXIMUM_SUMMARY_SECTIONS * CLASSIFICATION_INPUT_TOKENS
    sections = tuple(
        " ".join(tokens[start : start + CLASSIFICATION_INPUT_TOKENS])
        for start in range(0, min(len(tokens), ceiling), CLASSIFICATION_INPUT_TOKENS)
    )
    return sections, len(tokens) > ceiling


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
#
# The example's summary and key points (D-139) follow the same lesson. They are about the
# lighthouse text and nothing else, so no word of them is one a real document's summary would
# want. They demonstrate what the rules ask: one sentence that says what the text is about and
# not a copy of it, and key points that each restate one thing the text says, with no fact the
# text does not hold. Three key points are shown, under the cap, because a demonstrated count
# is copied too: an example at the cap would have every document reach for five. The section
# prompt's example is the SAME text with the SAME summary and key points, so there is one set
# of example words to keep alien, not two.

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
EXAMPLE_SUMMARY = (
    "Each evening before the lamp is lit, the keeper trims both wicks and wipes the lens, "
    "because a ragged wick smokes the glass and a sooted lens cannot be seen from the shoals."
)
EXAMPLE_KEY_POINTS = (
    "Both wicks are trimmed square to a quarter inch before the lamp is lit.",
    "The lens is wiped with a dry cloth.",
    "A ragged wick smokes the glass within the hour.",
)
EXAMPLE_REPLY = json.dumps(
    {
        "doc_type": {"value": "Procedure", "confidence": 0.92},
        "department": {"value": "Lantern Room", "confidence": 0.88},
        "tags": [
            {"dimension": "Process", "value": "wick trimming", "confidence": 0.9},
            {"dimension": "Topic", "value": "lens soot", "confidence": 0.75},
        ],
        "summary": EXAMPLE_SUMMARY,
        "key_points": list(EXAMPLE_KEY_POINTS),
    }
)
# The example is one section of two: a real section request is only ever made for a document
# of at least two.
EXAMPLE_SECTION_NUMBER, EXAMPLE_SECTION_COUNT = 1, 2
EXAMPLE_SECTION_REPLY = json.dumps({"summary": EXAMPLE_SUMMARY, "key_points": list(EXAMPLE_KEY_POINTS)})

REPLY_INSTRUCTION = "Reply with the JSON object only."

# FR-10's grounding clause (D-139): "the summarisation prompt constrains output to content
# present in the document." One sentence, written once, in BOTH prompts: rule 11 of the
# classification prompt and rule 5 of the section prompt. apps/ai/tests/test_classification_prompt.py
# and test_classification_sections.py assert it is in each. It is the whole of the grounding:
# nothing checks a summary against the text afterwards (see the module docstring).
GROUNDING_SENTENCE = (
    "The summary and the key points state only what the document's text says, "
    "with nothing from outside it"
)

# Rules 1 and 3 to 8 are word for word the rules D-106's sweeps and Objective 05's runs were
# measured on. D-139 changed rule 2's count of keys, from three to five, and added rules 9 to 11
# AFTER them, so that everything the model is told about the type, the department and the tags
# reads as it did. The reply's keys are in the same order for the same reason: the summary comes
# last, so the classification is written before a word of it. Whether the measurements still
# hold on this prompt is a question for a new sweep, not something this ordering proves.
#
# Rules 9 and 10 give a length in sentences as well as in characters. A small model cannot count
# characters, and on FLM, at temperature 0.0, the same request gives the same reply: an over-long
# summary would fail all three attempts alike. So the rules ask for well under the limits, and
# the limits are what the parser enforces.
_RULES = f"""\
You classify one document against an established scheme and reply with JSON.

Rules, all of them mandatory:
1. Reply with one JSON object and nothing else: no greeting, no explanation, no
   markdown code fence, no text before or after the object.
2. The object has exactly five keys: "doc_type", "department", "tags", "summary" and
   "key_points".
3. "doc_type" is an object with exactly two keys: "value", one of the document types
   listed, copied exactly; and "confidence", a number from 0 to 1. Choose the type by the
   document's purpose:
   - Policy: states the organisation's rules or entitlements: what is allowed, required or
     forbidden.
   - Procedure: tells the reader how to do something: steps, instructions or a guide to
     follow, even where it mentions rules along the way.
   - Report: presents information rather than rules or steps: results, figures or news,
     data laid out as a register, inventory, schedule, roster, tracker or table, or an
     announcement.
   - Meeting Paper: is addressed to a committee, board or meeting, putting a proposal, a
     decision or a briefing before it. A document is not a Meeting Paper because its title
     or subject mentions a meeting, a room, a session or an event.
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
9. "summary" is one string, never an array or an object: a short paragraph of one to
   three plain sentences saying what the document is about and what it says, at most
   {MAXIMUM_SUMMARY_CHARACTERS} characters in all.
10. "key_points" is an array of 1 to {MAXIMUM_KEY_POINTS} strings, never an empty array and never
    more than {MAXIMUM_KEY_POINTS}. Each is one point the document makes, as a single short sentence
    of at most {MAXIMUM_KEY_POINT_CHARACTERS} characters.
11. {GROUNDING_SENTENCE}:
    add no fact, name, number or date that the text does not contain.

One worked example. Its departments, tag values and subject are EXAMPLE values and appear
in no real scheme: never reuse them, and never classify a real document by its
resemblance to the example.
"""

# The section prompt (D-139): its own rules, for a request that classifies nothing. The same
# JSON-only rule, the same two bounds in the same words, the same grounding sentence, and one
# rule the classification prompt does not need: a section is cut by length, so it can start or
# stop in the middle of a sentence, and the model is told not to finish it.
_SECTION_RULES = f"""\
You summarise one section of a longer document and reply with JSON.

The document was cut into sections by length, so a section may begin or end in the middle
of a sentence.

Rules, all of them mandatory:
1. Reply with one JSON object and nothing else: no greeting, no explanation, no
   markdown code fence, no text before or after the object.
2. The object has exactly two keys: "summary" and "key_points".
3. "summary" is one string, never an array or an object: a short paragraph of one to
   three plain sentences saying what the section is about and what it says, at most
   {MAXIMUM_SUMMARY_CHARACTERS} characters in all.
4. "key_points" is an array of 1 to {MAXIMUM_KEY_POINTS} strings, never an empty array and never
   more than {MAXIMUM_KEY_POINTS}. Each is one point the section makes, as a single short sentence
   of at most {MAXIMUM_KEY_POINT_CHARACTERS} characters.
5. {GROUNDING_SENTENCE}:
   here that text is the section you are given. Add no fact, name, number or date that it
   does not contain.
6. Summarise what the section holds. Never complete a sentence that is cut off, and never
   guess what the rest of the document says.

One worked example. Its subject is an EXAMPLE and appears in no real document: never reuse
it, and never summarise a real section by its resemblance to the example.
"""

# What the final request of a long document says after the opening text and before the reply
# instruction (D-139). The type, the department and the tags are still chosen from the title
# and the opening, which is what ``input_truncated`` records and what every measurement of
# this prompt read. The summary and key points are written from the section summaries, which
# are all the model has of the document past its opening.
SECTIONED_NOTICE = (
    "The text above is only the opening of a longer document. The document was summarised "
    "one section at a time, and the section summaries follow in order."
)
CONSOLIDATION_INSTRUCTION = (
    'Choose "doc_type", "department" and "tags" from the title and the text above. Write '
    '"summary" and "key_points" for the document as a whole from the section summaries, '
    "which stand for its text."
)


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


def _section_block(title: str, section: str, number: int, of: int) -> str:
    """The title, which section this is, then its text: the shape of the section example and of every real section turn."""
    return f"Title: {title.strip()}\nSection {number} of {of}:\n{section}"


def _section_summaries_block(section_summaries: Sequence[SectionSummary]) -> str:
    """The section summaries in order, each under its number, with its key points beneath it.

    The key points go with the summary: they were asked for and held to the schema, and they
    are the best evidence the final request has for the document's own key points.
    """
    of = len(section_summaries)
    return "\n\n".join(
        f"Section {number} of {of}\nSummary: {section.summary}\nKey points:\n"
        + "\n".join(f"- {point}" for point in section.key_points)
        for number, section in enumerate(section_summaries, start=1)
    )


CLASSIFICATION_SYSTEM_PROMPT = (
    _RULES
    + "\n"
    + _document_block(EXAMPLE_TITLE, EXAMPLE_TEXT, EXAMPLE_SCHEME)
    + "\n\nYour reply:\n"
    + EXAMPLE_REPLY
)

SECTION_SUMMARY_SYSTEM_PROMPT = (
    _SECTION_RULES
    + "\n"
    + _section_block(EXAMPLE_TITLE, EXAMPLE_TEXT, EXAMPLE_SECTION_NUMBER, EXAMPLE_SECTION_COUNT)
    + "\n\nYour reply:\n"
    + EXAMPLE_SECTION_REPLY
)


def build_classification_user_prompt(
    title: str,
    text: str,
    scheme: TagScheme,
    *,
    section_summaries: Sequence[SectionSummary] = (),
) -> str:
    """The user turn: the scheme's lists, the title, the (cut) text, then the reply instruction.

    The scheme lists come first, so the model has read the values before it reads the document;
    the title next, because it is the strongest single signal of a document's kind; then the
    text, cut by ``classification_input`` here as well as by the caller — the cut is idempotent,
    and making it at the boundary means no caller can send more than CLASSIFICATION_INPUT_TOKENS
    by mistake. The closing instruction is the one sentence after the document.

    ``section_summaries`` (D-139) is given only for the FINAL request of a document longer than
    the cap, and is empty otherwise, which leaves the turn exactly as it was before D-139. When
    given, three things follow the text and precede the closing instruction: SECTIONED_NOTICE,
    saying the text is only the opening; each section's summary and key points, in order, under
    "Section n of m"; and CONSOLIDATION_INSTRUCTION, saying the type, department and tags come
    from the title and the opening and the summary and key points from the section summaries.

    **The title and the text are untrusted input, and nothing in them is transformed.** There
    is no delimiter to neutralise: this prompt cites no identifier, so unlike the generation
    prompt (D-45, Stage 4 item 12a) no label in it converts into an accepted citation when
    forged. A body that contains the lines above — "Departments (choose one): ..." or a second
    "Title:" — misleads the model about the scheme, which is the same residual as a body that
    instructs the model in prose, and neither is detectable by shape validation. What bounds it
    is stated in the module docstring: the type is held to the fixed list by the parser, the
    department and tag values are held to the scheme by the application (D-105), and a person
    confirms. Neutralising the lines would be a substring filter over ordinary English, which
    D-45 argues against, and would buy nothing the three bounds do not already give. A section
    summary is the model's words about that same untrusted text, and a body that forges a
    "Section 2 of 3" line misleads the model in the same way: the module docstring says what
    bounds a steered summary, which is less than what bounds a steered tag.
    """
    body, _ = classification_input(text)
    turn = _document_block(title, body, scheme)
    if section_summaries:
        turn += (
            f"\n\n{SECTIONED_NOTICE}\n\n"
            f"{_section_summaries_block(section_summaries)}\n\n"
            f"{CONSOLIDATION_INSTRUCTION}"
        )
    return turn + f"\n\n{REPLY_INSTRUCTION}"


def build_section_summary_user_prompt(title: str, section: str, number: int, of: int) -> str:
    """One section's user turn (D-139): the title, "Section n of m", its text, the reply instruction.

    The title is context only: a middle section seldom says what document it belongs to. The
    section is cut by ``classification_input`` here as well as by ``summary_sections``, for the
    reason ``build_classification_user_prompt`` cuts its text: the cut is idempotent, and no
    caller can send more than CLASSIFICATION_INPUT_TOKENS by mistake. The title and the section
    are untrusted and nothing in them is transformed, under the residual the module docstring
    states.
    """
    body, _ = classification_input(section)
    return _section_block(title, body, number, of) + f"\n\n{REPLY_INSTRUCTION}"


def chat_messages(system_prompt: str, user_prompt: str) -> list[dict]:
    """One request's chat messages in the OpenAI wire shape: system, then user.

    What the FLM provider sends for every request ``classify_and_summarise`` makes, a section's
    or the final one. The Anthropic provider takes the two strings separately, because that SDK
    carries the system prompt in its own parameter; the strings are the same either way.
    """
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_classification_messages(title: str, text: str, scheme: TagScheme) -> list[dict]:
    """The chat messages for one classification call, in the OpenAI wire shape: system, then user.

    The Anthropic provider takes CLASSIFICATION_SYSTEM_PROMPT and
    ``build_classification_user_prompt`` separately, because that SDK carries the system prompt
    in its own parameter; the strings are the same either way, as for generation.
    """
    return chat_messages(
        CLASSIFICATION_SYSTEM_PROMPT, build_classification_user_prompt(title, text, scheme)
    )


# --- The attempt loops -----------------------------------------------------------------------


def _run_attempts(
    call_once: Callable[[], str | ChatReply],
    parse: Callable[[str], object],
    *,
    step: str,
    schema: str,
    label: str,
    max_tokens: int | None,
    where: str = "",
):
    """One request's attempts: the policy ``run_classification_attempts`` documents, written once.

    Both of this module's loops are this one, so a section's request and the final request
    cannot follow different policies (D-139). ``parse`` turns the reply's text into the parsed
    value or raises SchemaViolation. ``step`` is the attempt log's step; ``schema`` names the
    schema in the final failure; ``where`` names the section ("section 2 of 6") in a section's
    log lines and its final failure, and is empty for a classification request, whose lines and
    message are exactly what they were before D-139.

    Returns the parsed value with what its parsed-attempt line needs: the attempt's number, its
    duration and the reply facts. The caller logs that line, because what it counts differs.
    """
    prefix = f"{where}: " if where else ""
    last_detail = "no attempt was made"
    for number in range(1, MAXIMUM_CLASSIFY_ATTEMPTS + 1):  # 1 initial call + 2 retries
        started = time.perf_counter()
        try:
            reply = call_once()
        except ProviderUnavailable as exc:
            last_detail = f"call failed: {exc}"
            attempt_log.failed_attempt(
                step, number, MAXIMUM_CLASSIFY_ATTEMPTS, time.perf_counter() - started,
                attempt_log.cause_of(exc), f"{prefix}{exc}",
                reply=attempt_log.ReplyFacts(max_tokens=max_tokens),
            )
            if isinstance(exc, ProviderRefused):
                raise  # D-118: a retry cannot fix a refusal; the caller leaves it unclassified
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
            parsed = parse(reply.text)
        except SchemaViolation as exc:
            # Invariant 10: a reply that does not conform is no reply at all.
            last_detail = f"schema violation: {exc}"
            attempt_log.failed_attempt(
                step, number, MAXIMUM_CLASSIFY_ATTEMPTS, time.perf_counter() - started,
                "SchemaViolation", f"{prefix}{exc}",
                reply=facts,
            )
            continue
        return parsed, number, time.perf_counter() - started, facts
    raise ProviderUnavailable(
        f"{label} returned no response conforming to {schema}{f' for {where}' if where else ''} in "
        f"{MAXIMUM_CLASSIFY_ATTEMPTS} attempts; last failure: {last_detail}"
    )


def run_classification_attempts(
    call_once: Callable[[], str | ChatReply],
    *,
    scheme: TagScheme,
    label: str,
    model: str,
    input_truncated: bool,
    summary_truncated: bool = False,
    max_tokens: int | None = None,
) -> DocumentClassification:
    """Call ``call_once`` until it returns a conforming reply, or give up loudly.

    The policy is ``run_generation_attempts``' exactly (NFR-19, D-19), with MAXIMUM_CLASSIFY_ATTEMPTS
    as the total — 1 initial call + 2 retries:

    - ``call_once()`` makes one provider call and returns the reply, as a ChatReply or as bare
      text. It raises ProviderUnavailable for a failed call, and that is a failed attempt. A
      failed call is one that was unreachable or timed out, or that got a 5xx or, since D-118,
      a 429. A refused call, any other 4xx, raises ProviderRefused instead, and the loop
      re-raises it at once. Either 4xx is logged by the provider first (apps/ai/_status.py).
    - A reply that does not parse into CLASSIFICATION_SCHEMA, including one whose type is outside
      the scheme or whose summary or key points break their bounds (D-139), is a failed attempt,
      not a partial classification (invariant 10).
    - Anything else ``call_once`` raises propagates untouched and consumes no retry. An
      exception the provider did not decide is a bug, not an outage. Since D-118 a 4xx is not
      one of these: the providers raise it as ProviderUnavailable or ProviderRefused.
    - After the last attempt, ProviderUnavailable naming ``label`` and the last failure. The
      caller leaves the document unclassified (invariant 8, NFR-20); nothing about its storage
      or indexing depends on this call.

    Every attempt is recorded through apps/ai/attempt_log.py under the step "classification":
    failures at WARNING, the parsed attempt at INFO, each with the reply facts the provider
    reported. There is no observer: the ``on_attempt`` hook is generation's, for the citation
    harness, and nothing measures classification per attempt.

    ``model`` is the chat model the provider answered with, for the DocumentAnalysis record;
    ``input_truncated`` is ``classification_input``'s flag and ``summary_truncated`` is
    ``summary_sections``' (D-139). All three are written onto the returned
    DocumentClassification and none is parsed. ``max_tokens`` is the value the provider's
    request carried, recorded on each attempt's line.

    The loop itself is ``_run_attempts``, shared with ``run_section_summary_attempts``.
    """
    parsed, number, seconds, facts = _run_attempts(
        call_once,
        lambda text: parse_classification(text, scheme),
        step="classification",
        schema="CLASSIFICATION_SCHEMA",
        label=label,
        max_tokens=max_tokens,
    )
    attempt_log.parsed_classification(
        number, MAXIMUM_CLASSIFY_ATTEMPTS, seconds, len(parsed.tags), reply=facts
    )
    return DocumentClassification(
        doc_type=parsed.doc_type,
        department=parsed.department,
        tags=parsed.tags,
        model=model,
        input_truncated=input_truncated,
        summary=parsed.summary,
        key_points=parsed.key_points,
        summary_truncated=summary_truncated,
    )


def run_section_summary_attempts(
    call_once: Callable[[], str | ChatReply],
    *,
    label: str,
    number: int,
    of: int,
    max_tokens: int | None = None,
) -> SectionSummary:
    """One section's request: call ``call_once`` until it conforms, or give up loudly (D-139).

    The same policy as ``run_classification_attempts``, through the same loop
    (``_run_attempts``), and its OWN MAXIMUM_CLASSIFY_ATTEMPTS, 1 initial call + 2 retries: a
    section that took three attempts leaves the next section, and the final request, three of
    their own. A failed call or a reply that does not parse into SECTION_SUMMARY_SCHEMA is a
    failed attempt; ProviderRefused is re-raised at once; after the last attempt,
    ProviderUnavailable naming ``label``, the section and the last failure.

    ``number`` and ``of`` say which section this is, for the log and the failure only. Every
    attempt is recorded under the step "section summary": failures at WARNING with the section
    named in the detail, the parsed attempt at INFO with the section and its count of key
    points. No line quotes the reply.
    """
    where = f"section {number} of {of}"
    parsed, attempt, seconds, facts = _run_attempts(
        call_once,
        parse_section_summary,
        step=attempt_log.SECTION_SUMMARY_STEP,
        schema="SECTION_SUMMARY_SCHEMA",
        label=label,
        max_tokens=max_tokens,
        where=where,
    )
    attempt_log.parsed_section_summary(
        attempt, MAXIMUM_CLASSIFY_ATTEMPTS, seconds,
        section=number, sections=of, key_points=len(parsed.key_points), reply=facts,
    )
    return parsed


# --- The whole operation ---------------------------------------------------------------------


def classify_and_summarise(
    call_once: Callable[[str, str], str | ChatReply],
    *,
    title: str,
    text: str,
    scheme: TagScheme,
    label: str,
    model: str,
    max_tokens: int | None = None,
) -> DocumentClassification:
    """``classify_document`` for either provider: every request it makes, in order (D-139).

    ``call_once(system_prompt, user_prompt)`` makes ONE provider call with those two strings and
    returns the reply, raising as ``run_classification_attempts`` describes. It is all a
    provider supplies besides its ``label``, its ``model`` and the ``max_tokens`` its requests
    carry, so the two providers cannot differ in what they ask or in how often.

    - **A text within CLASSIFICATION_INPUT_TOKENS: one request.** The classification prompt and
      the user turn exactly as before D-139; the reply now carries the summary and key points
      beside the type, the department and the tags (FR-10: "at the cost of one call rather than
      three"). At most MAXIMUM_CLASSIFY_ATTEMPTS calls.
    - **A longer text: one request per section, then one final request.** The sections are
      ``summary_sections``', at most MAXIMUM_SUMMARY_SECTIONS, sent in order under the section
      prompt. The final request is the classification prompt again, its user turn carrying the
      title, the opening exactly as ``classification_input`` cuts it, and every section's
      summary and key points in order. So n sections are n + 1 requests, each with its own
      MAXIMUM_CLASSIFY_ATTEMPTS: at most (MAXIMUM_SUMMARY_SECTIONS + 1) x
      MAXIMUM_CLASSIFY_ATTEMPTS calls for one document, one after another.
    - **A failure anywhere returns nothing.** A request that uses up its attempts raises
      ProviderUnavailable, and a ProviderRefused is re-raised at once; either ends the operation
      there, so no later section is sent and no final request is made. No partial result is
      built from the sections that did succeed: a summary of some sections presented as the
      document's would be the fragment FR-10 forbids. The caller leaves the document
      unclassified and unsummarised, and its storage and indexing are untouched (invariant 8).

    ``input_truncated`` and ``summary_truncated`` on the result come from the same token count:
    the first is True when the text has more than one section, the second when it has more than
    MAXIMUM_SUMMARY_SECTIONS.
    """
    opening, input_truncated = classification_input(text)
    sections, summary_truncated = summary_sections(text)
    section_summaries: list[SectionSummary] = []
    if input_truncated:  # more than one section: summarise each, in order, before the final request
        for number, section in enumerate(sections, start=1):
            section_prompt = build_section_summary_user_prompt(title, section, number, len(sections))
            section_summaries.append(
                run_section_summary_attempts(
                    partial(call_once, SECTION_SUMMARY_SYSTEM_PROMPT, section_prompt),
                    label=label,
                    number=number,
                    of=len(sections),
                    max_tokens=max_tokens,
                )
            )
    user_prompt = build_classification_user_prompt(
        title, opening, scheme, section_summaries=section_summaries
    )
    return run_classification_attempts(
        partial(call_once, CLASSIFICATION_SYSTEM_PROMPT, user_prompt),
        scheme=scheme,
        label=label,
        model=model,
        input_truncated=input_truncated,
        summary_truncated=summary_truncated,
        max_tokens=max_tokens,
    )
