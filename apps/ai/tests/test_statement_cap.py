"""The statement cap and the retry that asks for fewer (FR-12; step 7 phase 2a, 7 November 2026).

The user's decisions of 7 November 2026:

1. Ask for at most MAXIMUM_STATEMENTS statements, and enforce it: a reply with more is a
   schema violation, retried, and never trimmed (invariant 10).
2. After a reply that hit the token ceiling or broke the cap, the next attempt asks for fewer
   statements, instead of repeating the identical request. Phase 1 saw a repeated request
   never recover (D-82's note of 7 November 2026).

MAXIMUM_GENERATION_ATTEMPTS stays 3 in total (NFR-19); apps/ai/tests/test_generation.py keeps
its fault-injection tests, and the last test here holds the count with the cap shrinking.

Exercised through FLMService over the openai SDK's MockTransport, so each prompt is the one the
provider actually sends.
"""

from __future__ import annotations

import json

import httpx2
import openai
import pytest

from apps.ai.base import Passage, ProviderUnavailable
from apps.ai.flm import FLMService
from apps.ai.generation import GENERATION_MAX_TOKENS, fewer_statements
from apps.ai.prompting import SYSTEM_PROMPT, build_user_prompt, statement_cap_sentence
from apps.ai.schema import (
    STATEMENT_LIST_SCHEMA,
    SchemaViolation,
    StatementCapExceeded,
    parse_statement_list,
)
from apps.core.constants import MAXIMUM_GENERATION_ATTEMPTS, MAXIMUM_STATEMENTS

BASE_URL = "http://flm.test/v1"
CHUNK_ID = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
PASSAGES = [Passage(chunk_id=CHUNK_ID, text="Twenty days of annual leave per year.")]
QUESTION = "How much annual leave do I get?"
TRUNCATED = '{"statements": [{"text": "Twenty days.", "chunk_id": "3f2a91c7'


def statements_reply(count: int) -> str:
    return json.dumps(
        {"statements": [{"text": f"Statement {n}.", "chunk_id": CHUNK_ID} for n in range(count)]}
    )


@pytest.fixture(autouse=True)
def flm_settings(settings):
    settings.FLM_BASE_URL = BASE_URL
    settings.FLM_API_KEY = "flm"
    settings.FLM_CHAT_MODEL = "gemma3:4b"


def chat(content: str, completion_tokens: int = 50):
    return httpx2.Response(
        200,
        json={
            "id": "fastflowlm-chat-completion",
            "object": "chat.completion",
            "created": 0,
            "model": "gemma3:4b",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 900,
                "completion_tokens": completion_tokens,
                "total_tokens": 900 + completion_tokens,
            },
        },
    )


def service_answering(*responses):
    """FLMService answering each request with the next response, and the user prompts sent."""
    remaining = list(responses)
    prompts = []

    def handler(request):
        body = json.loads(request.content)
        prompts.append(next(m["content"] for m in body["messages"] if m["role"] == "user"))
        return remaining.pop(0)

    client = openai.OpenAI(
        base_url=BASE_URL,
        api_key="flm",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return FLMService(client=client), prompts


def asked_for(prompt: str) -> int:
    """The cap a user prompt states, read back from its "Give at most N statement(s)." sentence."""
    for n in range(1, 50):
        if statement_cap_sentence(n) in prompt:
            return n
    raise AssertionError(f"no cap stated in the prompt's tail: {prompt[-120:]!r}")


# --- The cap appears in the prompt -----------------------------------------------------------


def test_the_cap_is_stated_in_the_prompt_the_provider_sends():
    service, prompts = service_answering(chat(statements_reply(1)))

    service.generate_statements(QUESTION, PASSAGES)

    assert f"Give at most {MAXIMUM_STATEMENTS} statement" in prompts[0]
    assert asked_for(prompts[0]) == MAXIMUM_STATEMENTS
    # After the question, before the reply instruction, where rule 8 says the number is.
    tail = prompts[0].split(f"Question: {QUESTION}", 1)[1]
    assert tail.strip().startswith(statement_cap_sentence(MAXIMUM_STATEMENTS))


def test_the_system_prompt_tells_the_model_to_keep_to_the_stated_number():
    assert "\n8. Give no more statements than the number stated after the question." in SYSTEM_PROMPT


def test_the_user_prompt_states_the_number_it_is_given():
    assert "Give at most 2 statements." in build_user_prompt(QUESTION, PASSAGES, max_statements=2)
    assert "Give at most 1 statement." in build_user_prompt(QUESTION, PASSAGES, max_statements=1)
    assert statement_cap_sentence(MAXIMUM_STATEMENTS) in build_user_prompt(QUESTION, PASSAGES)


# --- A reply over the cap is a schema violation, retried, never trimmed ------------------------


def test_the_schema_and_the_parser_hold_the_cap():
    assert STATEMENT_LIST_SCHEMA["properties"]["statements"]["maxItems"] == MAXIMUM_STATEMENTS
    assert len(parse_statement_list(statements_reply(MAXIMUM_STATEMENTS)).statements) == MAXIMUM_STATEMENTS
    with pytest.raises(StatementCapExceeded, match=f"more than the {MAXIMUM_STATEMENTS} asked for"):
        parse_statement_list(statements_reply(MAXIMUM_STATEMENTS + 1))
    assert issubclass(StatementCapExceeded, SchemaViolation)
    with pytest.raises(StatementCapExceeded):
        parse_statement_list(statements_reply(3), max_statements=2)


def test_a_reply_over_the_cap_is_retried_and_none_of_it_is_kept():
    over = statements_reply(MAXIMUM_STATEMENTS + 1)
    service, prompts = service_answering(chat(over), chat(statements_reply(1)))

    result = service.generate_statements(QUESTION, PASSAGES)

    assert len(prompts) == 2
    # The second reply's single statement, not the first reply's first N.
    assert [s.text for s in result.statements] == ["Statement 0."]
    assert len(result.statements) == 1


def test_three_replies_over_the_cap_are_a_503_not_a_trimmed_answer():
    service, prompts = service_answering(
        *(chat(statements_reply(MAXIMUM_STATEMENTS + 3)) for _ in range(MAXIMUM_GENERATION_ATTEMPTS))
    )

    with pytest.raises(ProviderUnavailable, match="asked for"):
        service.generate_statements(QUESTION, PASSAGES)
    assert len(prompts) == MAXIMUM_GENERATION_ATTEMPTS


# --- After a ceiling hit or a cap violation, the next attempt asks for fewer -------------------


def test_after_a_ceiling_hit_the_next_attempt_asks_for_fewer():
    service, prompts = service_answering(
        chat(TRUNCATED, completion_tokens=GENERATION_MAX_TOKENS), chat(statements_reply(1))
    )
    recorded = []

    service.generate_statements(QUESTION, PASSAGES, on_attempt=recorded.append)

    assert [asked_for(p) for p in prompts] == [MAXIMUM_STATEMENTS, fewer_statements(MAXIMUM_STATEMENTS)]
    assert [a.max_statements for a in recorded] == [MAXIMUM_STATEMENTS, fewer_statements(MAXIMUM_STATEMENTS)]
    # Fewer, said independently of fewer_statements, which could agree with itself.
    if MAXIMUM_STATEMENTS > 1:
        assert asked_for(prompts[1]) < asked_for(prompts[0])


def test_after_a_cap_violation_the_next_attempt_asks_for_fewer():
    service, prompts = service_answering(
        chat(statements_reply(MAXIMUM_STATEMENTS + 1), completion_tokens=200), chat(statements_reply(1))
    )

    service.generate_statements(QUESTION, PASSAGES)

    assert [asked_for(p) for p in prompts] == [MAXIMUM_STATEMENTS, fewer_statements(MAXIMUM_STATEMENTS)]
    if MAXIMUM_STATEMENTS > 1:
        assert asked_for(prompts[1]) < asked_for(prompts[0])


def test_after_any_other_failure_the_number_stays():
    """Only a reply that was too long asks for fewer: one that was malformed and short is
    retried with the same cap."""
    service, prompts = service_answering(chat("this is not JSON", completion_tokens=6), chat(statements_reply(1)))

    service.generate_statements(QUESTION, PASSAGES)

    assert [asked_for(p) for p in prompts] == [MAXIMUM_STATEMENTS, MAXIMUM_STATEMENTS]


def test_fewer_statements_halves_and_never_goes_below_one():
    assert [fewer_statements(n) for n in (6, 5, 4, 3, 2, 1)] == [3, 2, 2, 1, 1, 1]


# --- Three attempts in total, still ------------------------------------------------------------


def test_three_attempts_in_total_while_the_cap_shrinks():
    """NFR-19's count holds when every attempt asks for fewer: exactly three provider calls,
    then the 503."""
    service, prompts = service_answering(
        *(chat(TRUNCATED, completion_tokens=GENERATION_MAX_TOKENS) for _ in range(MAXIMUM_GENERATION_ATTEMPTS + 2))
    )

    with pytest.raises(ProviderUnavailable):
        service.generate_statements(QUESTION, PASSAGES)

    assert len(prompts) == MAXIMUM_GENERATION_ATTEMPTS == 3
    first = MAXIMUM_STATEMENTS
    asked = [asked_for(p) for p in prompts]
    assert asked == [first, fewer_statements(first), fewer_statements(fewer_statements(first))]
    # Never more than the attempt before, and fewer whenever there was room to go lower.
    assert all(later <= earlier for earlier, later in zip(asked, asked[1:]))
    assert all(later < earlier for earlier, later in zip(asked, asked[1:]) if earlier > 1)
