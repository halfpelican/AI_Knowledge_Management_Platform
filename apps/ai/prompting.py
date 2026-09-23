"""The grounded-generation prompt: docs/ai-provider.md section 5, steps 1 and 2.

Strict instructions, then one worked example. Small local models follow a demonstration
far better than a description, and the example is what keeps the reply free of the prose
wrapper gemma3:4b otherwise volunteers.

**Moved here from scripts/citation_harness.py at Stage 4 item 5, substantively
unchanged.** This prompt is what measured 100% schema conformance and a 2.4%
fabricated-identifier rate over 50 questions (docs/flm-baseline.md). Rewording it
invalidates those numbers, so treat any edit as a change that must be re-measured with
the harness. The harness now imports these names rather than defining its own copies;
``apps/ai/tests/test_prompt_is_not_duplicated.py`` asserts it holds no second copy.

The prompt carries the retrieved passages and NOTHING else: no conversation history
(that is FR-13, item 9), no document titles, no metadata, no instruction that would let
the model answer from anywhere but the passages. Both providers build their request from
the same two pieces here, so FLM and Claude are sent the same prompt and the baseline's
numbers describe the prompt both use.
"""

from apps.ai.base import Passage

# Strict instructions, then one worked example.
#
# READ THIS BEFORE EDITING THE WORKED EXAMPLE BELOW. It is the single most valuable
# thing learned at Stage 4 item 0, and it sits here rather than inside the prompt
# string because anything inside that string is prompt text the model reads.
#
#   The first baseline run measured a 23.8% fabricated-identifier rate. 9 of the 10
#   fabricated identifiers were `c_4471` or `c_8802`, the two example IDs from this
#   worked example, and the other two were the example's shape applied to real data.
#   Giving the example UUID-shaped identifiers, and saying explicitly that they appear
#   nowhere in the real passages, took the rate to 2.4% with no other change. Any
#   identifier in a worked example is a candidate for being cited. Do not put a
#   plausible chunk ID in a prompt.
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

Worked example. The identifiers below are EXAMPLE values and appear nowhere in the
real passages: never reuse them, and never copy their shape onto a real identifier.

Passages:
[chunk_id: 3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03]
Purchase orders above $10,000 require two approvals. Orders below that amount
require one approval from the team lead.

[chunk_id: 8b5d04e2-1a7f-4c93-b620-de91f3805c47]
The office is closed on public holidays and reopens the following working day.

Question: How many approvals does a $25,000 purchase order need?

Your reply:
{"statements": [{"text": "Purchase orders above $10,000 require two approvals.", "chunk_id": "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"}]}\
"""


def build_user_prompt(question: str, passages: list[Passage]) -> str:
    """The passage block, the question, and the instruction to reply with JSON only.

    Each passage is labelled with the chunk identifier that citation verification will
    check returned identifiers against by set membership (FR-12, invariant 5). The
    identifiers are the real ones, which is why the worked example's must not look like
    them.
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

    The prompt carries the retrieved passages and nothing else, each labelled with
    the chunk identifier that citation verification will check against (FR-12).

    The Anthropic provider takes SYSTEM_PROMPT and ``build_user_prompt`` separately,
    because that SDK carries the system prompt in its own parameter rather than as a
    message. The strings are the same either way, which is the point of composing this
    from the two pieces rather than writing the user prompt out again.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, passages)},
    ]
