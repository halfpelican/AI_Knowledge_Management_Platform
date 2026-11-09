"""FR-13's follow-up rewrite: the prompt, the one-field schema, and the single attempt.

Step 7 phase 4, option 3 (D-103's "before any further attempt" condition met first). The
operation turns a follow-up plus the conversation's EARLIER QUESTIONS into one standalone
question — the question a user would have typed had they spelled the follow-up out — and
that string is embedded as the retrieval query in place of the plain composed join.
D-103 measured the reason this exists: the spelled-out arm answered 6 of 9 frozen
follow-ups where the with-history arm answered 2, so the fix is to manufacture the
spelled-out question rather than to re-rank around the composed one (option 2, measured
and not adopted) or to instruct generation around it (option 1, likewise).

**What the rewrite is, and is not.**

- **Input is QUESTIONS ONLY, never answers.** D-42 stands: no model-generated text
  re-enters a prompt, and ``QueryLog.answer_text`` is as unread here as it is in
  apps/retrieval/conversation.py. The previous-answer failure class (t31, t09) is
  expected to keep failing, and that is the accepted cost, measured rather than hidden.
- **Output is for RETRIEVAL ONLY.** The rewrite is embedded; it never enters a
  generation prompt, a reply, a citation or any user-visible text. The generation prompt
  still carries the original question with the labelled history block
  (``build_conversational_question``), exactly as before this module existed. A wrong
  rewrite therefore costs retrieval quality only — the same cost a bad composed join
  already carries — and verification is unchanged behind it.
- **ONE attempt, then the caller falls back.** There is deliberately no retry constant:
  a retry would put a second NPU generation call in front of every follow-up's retrieval
  on the failure path, and the composed join is a known-good fallback that costs nothing.
  On any failure — transport, timeout, non-conforming, empty, over-length — the caller
  (``apps.retrieval.pipeline.resolve_retrieval_text``) proceeds with the join exactly as
  the pipeline did before this module existed. The ask must never fail because the
  rewrite did. A non-conforming reply is "no response", invariant 10's shape; what
  differs from generation is only what follows no response (fall back, not 503), because
  here a correct degraded path exists and there it does not.

**The prompt follows the project's structured-output strategy** (docs/ai-provider.md
section 5): strict rules, ONE worked example, a tolerant parser. The example's subject
is the houseplant of apps/ai/prompting.py's examples, for the lesson that file records
twice over: an example whose subject resembles the corpus invites the model to answer
from the example, so the subject stays something no organisation would ever index. This
prompt carries NO identifiers at all — no chunk_id, no label verification would accept —
so a fabrication here cannot become a citation; the worst a bad rewrite does is retrieve
the wrong passages, which generation then declines over (D-102: generation does most of
the declining).

**No neutralisation, deliberately.** D-45's transformation defends the passage header in
PROMPTS that carry passages; this prompt carries none, and the rewrite's output is
embedded, where "a vector has no delimiters" (``ConversationContext``). The original
question still passes through ``build_conversational_question`` on its way to the
generation prompt, neutralised there as before.
"""

from __future__ import annotations

import json

from apps.ai.base import FollowupRewrite
# The tolerant-parse helpers are the generation parser's own, imported rather than
# restated: one definition of "strip the fence, take the outermost object, forgive a
# trailing comma", so the two parsers cannot drift in what they repair
# (apps/ai/schema.py's header records why one definition matters).
from apps.ai.schema import (
    SchemaViolation,
    _outermost_json_object,
    _strip_code_fences,
    _TRAILING_COMMA,
)
from apps.core.constants import MAXIMUM_QUESTION_LENGTH

# A rewrite longer than this is a failed attempt, whatever it says: the caller falls
# back. Twice the question bound, because a rewrite legitimately merges up to
# MAXIMUM_CONVERSATION_TURNS questions' referents into one — but a reply still growing at
# double the longest question a user may ask is the model talking, not rewriting, and an
# embedded string that long dilutes the query vector the way the labelled block would
# (apps/retrieval/conversation.py's "for_retrieval" argument). Derived, not tuned: it
# moves with MAXIMUM_QUESTION_LENGTH and is not a CLAUDE.md section 5 constant.
MAXIMUM_REWRITE_LENGTH = 2 * MAXIMUM_QUESTION_LENGTH

# One short question in a one-field JSON object. MAXIMUM_REWRITE_LENGTH is ~1000
# characters, roughly 250 model tokens, plus the object's own syntax; 300 leaves room
# without inviting an essay. A reply cut off at this ceiling is broken JSON, which is a
# RewriteViolation, which is the fallback — the failure direction is the safe one.
# Beside the request parameters for the same reason GENERATION_MAX_TOKENS sits in
# apps/ai/generation.py: a parameter of a provider call, not a tuned retrieval constant.
REWRITE_MAX_TOKENS = 300

# Tighter than GENERATION_TIMEOUT_SECONDS (300 s) on purpose. The rewrite runs BEFORE
# retrieval on every follow-up turn, so its worst case is added to every follow-up's
# latency; a provider that cannot produce ~60 tokens in two minutes is a provider whose
# fallback should answer instead. NFR-08's numbers are generation-dominated either way.
REWRITE_TIMEOUT_SECONDS = 120


class RewriteViolation(Exception):
    """The rewrite reply did not conform: not the one-field object, empty, or over-length.

    Invariant 10's shape — a non-conforming reply is no reply at all — with the rewrite's
    consequence: the caller falls back to the composed join rather than retrying or
    failing the ask. Messages describe the malformation and never quote the reply, so an
    attempt-log line built from one carries no question text.
    """


# Expressed as JSON Schema for the same reason STATEMENT_LIST_SCHEMA is: handed to a
# constrained-decoding option if FLM ever exposes one, validated by hand below.
REWRITE_SCHEMA = {
    "type": "object",
    "required": ["question"],
    "additionalProperties": False,
    "properties": {
        "question": {"type": "string", "minLength": 1, "maxLength": MAXIMUM_REWRITE_LENGTH},
    },
}

# Strict rules, then ONE worked example. Read the lesson above SYSTEM_PROMPT in
# apps/ai/prompting.py before editing the example: a worked example is training data for
# the response, in its content as much as in its identifiers. This one carries no
# identifiers — there is nothing here verification would accept — and its subject is the
# same deliberately alien houseplant, so a model reaching into the example produces a
# rewrite about ferns, which retrieves nothing and is declined, rather than a plausible
# wrong answer about the corpus.
REWRITE_SYSTEM_PROMPT = """\
You rewrite a follow-up question so that it stands alone, using the earlier questions
from the same conversation to resolve what it refers to.

Rules, all of them mandatory:
1. Reply with one JSON object and nothing else: no greeting, no explanation, no
   markdown code fence, no text before or after the object.
2. The object has exactly one key, "question", whose value is one standalone question.
3. Replace every pronoun, dropped subject or short reference in the follow-up ("it",
   "they", "that", "the same one", "over there") with the thing it refers to from the
   earlier questions.
4. Ask what the FOLLOW-UP asks. Do not repeat an earlier question, do not answer the
   question, and do not add anything the questions themselves do not say.
5. If the follow-up already stands alone, return it unchanged.
6. Keep the rewrite to one question of ordinary length.

One worked example. Its subject is an EXAMPLE and appears in no real conversation:
never copy its words into a real rewrite.

Earlier questions in this conversation, oldest first:
- How often does a potted maidenhair fern need watering in summer?

Follow-up question: And what about over winter?

Your reply:
{"question": "How often does a potted maidenhair fern need watering over winter?"}\
"""

# The user turn's three pieces, named so a test can pin them without restating the
# wording. A dash for the list marker, as PRIOR_QUESTION_MARKER is and for its reason.
REWRITE_HISTORY_HEADING = "Earlier questions in this conversation, oldest first:"
REWRITE_QUESTION_LEAD_IN = "Follow-up question: "
REWRITE_REPLY_INSTRUCTION = "Reply with the JSON object only."


def build_rewrite_messages(question: str, prior_questions: list[str]) -> list[dict]:
    """The chat messages for one rewrite call, in the OpenAI wire shape.

    ``prior_questions`` is oldest first and is questions ONLY — the caller's obligation,
    as it is for ``build_conversational_question``, and D-42's clause 1. An empty history
    is a caller's bug, not a prompt to build: a question with no predecessors has nothing
    to resolve and the pipeline never calls the operation for one (under test).
    """
    if not prior_questions:
        raise ValueError("rewrite_followup() needs at least one prior question")
    history = "\n".join(f"- {prior.strip()}" for prior in prior_questions)
    return [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{REWRITE_HISTORY_HEADING}\n{history}\n\n"
                f"{REWRITE_QUESTION_LEAD_IN}{question}\n\n{REWRITE_REPLY_INSTRUCTION}"
            ),
        },
    ]


def parse_rewrite(raw: str) -> FollowupRewrite:
    """Parse a raw reply into a FollowupRewrite, or raise RewriteViolation.

    Tolerant of exactly what ``parse_statement_list`` tolerates — a code fence, a
    sentence of preamble, a trailing comma — and of nothing else. The wrong shape, an
    empty value or a value over MAXIMUM_REWRITE_LENGTH is rejected outright; no part of
    a non-conforming reply is kept. No message below quotes the reply.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise RewriteViolation("empty response")
    try:
        candidate = _outermost_json_object(_strip_code_fences(raw))
    except SchemaViolation as exc:
        # The helpers' own messages ("no JSON object in the response", "unbalanced JSON
        # object in the response") carry no reply text; only the exception type changes,
        # so a caller catching the rewrite's violations does not catch generation's.
        raise RewriteViolation(str(exc)) from exc
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            decoded = json.loads(_TRAILING_COMMA.sub("", candidate))
        except json.JSONDecodeError as exc:
            # JSONDecodeError's message is positional ("Expecting value: line 1 column
            # 1"), never the document text.
            raise RewriteViolation(f"not valid JSON: {exc.msg} at position {exc.pos}") from exc
    if not isinstance(decoded, dict):
        raise RewriteViolation(f"top level is {type(decoded).__name__}, not an object")
    if "question" not in decoded:
        raise RewriteViolation("no 'question' key")
    extra = sorted(set(decoded) - {"question"})
    if extra:
        raise RewriteViolation(f"{len(extra)} unexpected top-level key(s)")
    value = decoded["question"]
    if not isinstance(value, str) or not value.strip():
        raise RewriteViolation("'question' is empty or not a string")
    rewritten = value.strip()
    if len(rewritten) > MAXIMUM_REWRITE_LENGTH:
        raise RewriteViolation(
            f"the rewrite is {len(rewritten)} characters, over the "
            f"{MAXIMUM_REWRITE_LENGTH} ceiling"
        )
    return FollowupRewrite(question=rewritten)


def run_rewrite_attempt(*, call_once, label: str) -> FollowupRewrite:
    """ONE provider call, parsed, or an exception the caller falls back on.

    ``call_once()`` makes the single call and returns the reply text (or a ChatReply,
    whose ``text`` is read); it raises ProviderUnavailable for a transport failure,
    which propagates untouched, as does a 4xx — there is no loop here to consume
    retries in, and no second attempt by design. ``label`` names the provider in a
    violation's context; it is not put into the message, which stays text-free.

    Shared by both implementations so the single-attempt policy cannot drift between
    them, as apps/ai/generation.py is shared for the three-attempt one.
    """
    reply = call_once()
    text = getattr(reply, "text", reply)
    return parse_rewrite(text)
