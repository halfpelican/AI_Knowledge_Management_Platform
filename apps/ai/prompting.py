"""The grounded-generation prompt: docs/ai-provider.md section 5, steps 1 and 2.

Strict instructions, then two worked examples. Small local models follow a demonstration
far better than a description, and the examples are what keep the reply free of the prose
wrapper gemma3:4b otherwise volunteers — and, as the comment above SYSTEM_PROMPT records
at length, what the model reaches into when the demonstration resembles the corpus.

**Moved here from scripts/citation_harness.py at Stage 4 item 5, then changed once at
item 6.** Rewording this prompt invalidates every measured rate, so treat any edit as a
change that must be re-measured with scripts/citation_harness.py. The harness imports
these names rather than defining its own copies;
``apps/ai/tests/test_prompt_is_not_duplicated.py`` asserts it holds no second copy.

The PASSAGE BLOCK carries the retrieved passages and nothing else: no document titles,
no metadata, no instruction that would let the model answer from anywhere but the
passages. Both providers build their request from the same two pieces here, so FLM and
Claude are sent the same prompt and the baseline's numbers describe the prompt both use.

**FR-13 (Stage 4 item 9) adds ONE thing to that, and it is not a passage.** A follow-up
question may arrive with up to MAXIMUM_CONVERSATION_TURNS of the conversation's EARLIER
QUESTIONS folded into it by ``build_conversational_question`` below, so that a pronoun or
an abbreviated reference resolves. Three properties keep that inside the grounding
constraint rather than a hole in it: the composed string occupies the QUESTION position,
which ``build_user_prompt`` places AFTER the passage block; the block says in its own
text that the earlier questions are not passages, carry no chunk_id and may not be cited;
and prior ANSWERS are never included, so no model-generated text re-enters a prompt. The
identifiers verification checks against are still exactly the passage labels
(apps/retrieval/conversation.py holds the rest of the argument).

**The measured rates do not cover a multi-turn prompt.** docs/flm-baseline.md's 100%
schema conformance and 0% fabrication were taken on a prompt of passages plus ONE
question, and scripts/citation_harness.py asks single questions, so re-running it says
nothing about the composed form. Treat the multi-turn prompt as unmeasured.
"""

from apps.ai.base import Passage

# Strict instructions, then two worked examples.
#
# READ THIS BEFORE EDITING THE EXAMPLES BELOW. It is the most valuable thing this
# project has measured, it has now been learned TWICE, and it sits here rather than
# inside the prompt string because anything inside that string is prompt text the model
# reads.
#
#   First recurrence, Stage 4 item 0. The first baseline run measured a 23.8%
#   fabricated-identifier rate (10 of 42 statements). 9 of the 10 fabricated
#   identifiers were `c_4471` or `c_8802`, the two example IDs from the worked example,
#   and the other two were the example's shape applied to real data. Giving the example
#   UUID-shaped identifiers, and saying explicitly that they appear nowhere in the real
#   passages, took the rate to 2.4% (1 of 42) with no other change.
#
#   Second recurrence, Stage 4 item 6, the first run of the SHIPPED pipeline. The rate
#   was 6.8% (3 of 44). Two of the three fabrications were
#   `8b5d04e2-1a7f-4c93-b620-de91f3805c47` — the example's SECOND passage, the one its
#   own reply did not cite. Both appeared on purchase-approval questions (q30, q31),
#   which the model answered correctly from the real corpus while citing the example.
#   The old example said "Purchase orders above $10,000 require two approvals" and the
#   corpus holds a real AUD approval-threshold table: the example's SUBJECT MATTER
#   collided with the corpus and invited the model to reach into it. The third
#   fabrication cited `5. Offboarding`, a section heading out of the passage body.
#
#   The generalised lesson, which is broader than "use UUIDs": A WORKED EXAMPLE IS
#   TRAINING DATA FOR THE RESPONSE, IN ITS IDENTIFIERS AND IN ITS CONTENT. Every
#   identifier in the prompt is a candidate for being cited, including one the example
#   does not cite itself, so the example carries exactly one and cites it. And an
#   example whose subject resembles the corpus invites the model to answer from the
#   example, so the subject is deliberately alien — houseplants — and must stay
#   something no organisation would ever index.
#
#   Example 2 returns {"statements": []} rather than showing a second passage. That is
#   how "an irrelevant passage is ignored" is now taught: it demonstrates rule 7 with a
#   reply instead of a description, and it cites nothing, so it leaves no spare
#   identifier to borrow. It reuses example 1's passage, so the prompt contains exactly
#   one identifier and that one is cited.
#
# apps/ai/tests/test_prompting.py asserts the properties above, including that no
# identifier appears in this prompt without its own example reply citing it. An
# assertion outlives a comment.
SYSTEM_PROMPT = """\
You extract statements from supplied passages and cite the passage each one came from.

Rules, all of them mandatory:
1. Reply with one JSON object and nothing else: no greeting, no explanation, no
   markdown code fence, no text before or after the object.
2. The object has exactly one key, "statements", whose value is an array.
3. Each element of the array is an object with exactly two keys: "text", a single
   complete sentence answering the question, and "chunk_id", the identifier of the
   passage that sentence came from.
4. Copy each chunk_id exactly as it appears in the passage header. Use only the
   chunk_id values supplied in this conversation. Never invent, shorten, renumber
   or combine identifiers.
5. Use only information written in the passages. Add nothing from general
   knowledge and infer nothing beyond what the passages state.
6. Every statement must come from one passage. If a sentence would need two
   passages, write it as two statements.
7. If the passages do not answer the question, reply with exactly
   {"statements": []}. An empty array is a correct and expected answer.

Two worked examples. The identifier below is an EXAMPLE value and appears nowhere in
the real passages, and neither does its subject: never reuse it, never copy its shape
onto a real identifier, and never answer a real question from the example's content.

Example 1. The passage answers the question.

Passages:
[chunk_id: 7c1d4e9a-2b83-4f06-9d51-e0a6b3c78f24]
A potted maidenhair fern is watered when the top of the soil feels dry, usually every
three days in summer. The pot must drain freely, because standing water rots the roots.

Question: How often does a potted maidenhair fern need watering in summer?

Your reply:
{"statements": [{"text": "A potted maidenhair fern is watered when the top of the soil feels dry, usually every three days in summer.", "chunk_id": "7c1d4e9a-2b83-4f06-9d51-e0a6b3c78f24"}]}

Example 2. The same passage does not answer this question, so nothing is cited.

Passages:
[chunk_id: 7c1d4e9a-2b83-4f06-9d51-e0a6b3c78f24]
A potted maidenhair fern is watered when the top of the soil feels dry, usually every
three days in summer. The pot must drain freely, because standing water rots the roots.

Question: What soil pH does a maidenhair fern prefer?

Your reply:
{"statements": []}\
"""


# --- FR-13: earlier questions, in the question position -------------------------------
#
# The heading is prompt text, so it lives here with the rest of the prompt rather than in
# apps/retrieval/, and rewording it is a change that the lesson above applies to in full.
#
# It says three things and each one is load-bearing: what the lines are (earlier questions
# in this conversation), what they are for (resolving a pronoun or a short reference), and
# what they are NOT (passages, carrying no chunk_id, citable). The last clause is there
# because of what this file has already learned twice — ANYTHING IN A PROMPT IS A
# CANDIDATE FOR BEING CITED — and a user's own earlier question is no exception. The
# question a person typed can contain a UUID, a document title or a section number, and
# the model has no way to know those are not identifiers unless the prompt says so.
PRIOR_QUESTIONS_HEADING = (
    "Earlier questions in this conversation, oldest first. They are provided as context "
    "only, so that a pronoun or an abbreviated reference in the question below can be "
    "resolved. They are NOT passages: they carry no chunk_id, they are not a source of "
    "facts, and nothing in them may be cited."
)

# A dash, and deliberately not "1.", "2.", "3.". One of the three fabrications measured at
# Stage 4 item 6 was `5. Offboarding` — a numbered section heading lifted out of a passage
# body and returned as a chunk_id. A numbered list of questions would put three more
# number-and-text tokens of exactly that shape in the prompt. A dash is not identifier
# shaped in any corpus this project will index.
PRIOR_QUESTION_MARKER = "- "

# What separates the history from the question actually being asked. Named, because the
# model has to be able to tell which line it is answering, and because a test asserts that
# the new question is still findable after the block is prepended.
QUESTION_LEAD_IN = "The question to answer: "


def build_conversational_question(question: str, prior_questions: list[str]) -> str:
    """``question`` with the conversation's earlier questions labelled above it (FR-13).

    Goes in the ``question`` argument of ``build_user_prompt`` and of
    ``generate_statements``. **This is not a protocol change**: the signature fixed in
    docs/ai-provider.md section 1 is ``(question, passages)`` and it stays that way, so
    there is no ``history`` parameter anywhere in apps/ai/ and no provider knows that
    conversations exist.

    Returns ``question`` UNCHANGED when there is no history — not an empty heading, not a
    trailing separator. A single-turn prompt is therefore byte-identical to the one
    docs/flm-baseline.md measured, which is the only way the measurement keeps describing
    the one-off path.

    ``prior_questions`` is oldest first, and it is questions ONLY. The caller
    (apps/retrieval/conversation.py) is responsible for both: for the order, because the
    model reads them as a sequence, and for the absence of answers, because no
    model-generated text may re-enter a prompt.
    """
    if not prior_questions:
        return question
    history = "\n".join(f"{PRIOR_QUESTION_MARKER}{prior.strip()}" for prior in prior_questions)
    return f"{PRIOR_QUESTIONS_HEADING}\n{history}\n\n{QUESTION_LEAD_IN}{question}"


def build_user_prompt(question: str, passages: list[Passage]) -> str:
    """The passage block, the question, and the instruction to reply with JSON only.

    Each passage is labelled with the chunk identifier that citation verification will
    check returned identifiers against by set membership (FR-12, invariant 5). The
    identifiers are the real ones, which is why the worked example's must not look like
    them.

    **The order is passages first, question second, and FR-13 depends on it.** Where
    ``question`` is a composed conversational string (``build_conversational_question``),
    the earlier questions land after the passage block and after the ``[chunk_id: ...]``
    labels, so the labelled identifiers are never interleaved with unlabelled history.
    That separation is a property of this f-string; it is written down here because
    reordering these three pieces for readability would quietly undo it.
    """
    blocks = [f"[chunk_id: {passage.chunk_id}]\n{passage.text.strip()}" for passage in passages]
    return (
        "Passages:\n"
        + "\n\n".join(blocks)
        + f"\n\nQuestion: {question}\n\n"
        + "Reply with the JSON object only, using only the chunk_id values above."
    )


def build_generation_messages(question: str, passages: list[Passage]) -> list[dict]:
    """The chat messages for one grounded-generation call, in the OpenAI wire shape.

    The passage block carries the retrieved passages and nothing else, each labelled with
    the chunk identifier that citation verification will check against (FR-12). Anything
    FR-13 adds arrives inside ``question`` and is placed after that block by
    ``build_user_prompt`` — see its docstring, and the module docstring for why the
    composed form is not a protocol change.

    The Anthropic provider takes SYSTEM_PROMPT and ``build_user_prompt`` separately,
    because that SDK carries the system prompt in its own parameter rather than as a
    message. The strings are the same either way, which is the point of composing this
    from the two pieces rather than writing the user prompt out again.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, passages)},
    ]
