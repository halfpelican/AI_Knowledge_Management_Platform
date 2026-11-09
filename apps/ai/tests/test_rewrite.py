"""FR-13's follow-up rewrite at the provider boundary (apps/ai/rewrite.py).

Step 7 phase 4. What is asserted here is the operation's own contract, below the
pipeline: ONE provider call — never a second, whatever the first returned — a reply
parsed against the one-field schema with exactly the tolerances the generation parser
has, violations that carry no reply text into their messages, and both implementations
sharing the prompt and the single-attempt runner. The FALLBACK is deliberately not
here: falling back is the pipeline's job and is tested where the pipeline is
(apps/retrieval/tests/test_followup_rewrite.py), because a provider that quietly fell
back itself would hide the failure the attempt log exists to count.

FLM is exercised through the openai SDK's MockTransport, as test_generation.py does;
Anthropic through a fake SDK client, as test_anthropic.py does (D-35: no external AI
spend). Nothing here reaches a network.
"""

import json

import httpx2
import openai
import pytest
from django.test import override_settings

from apps.ai.anthropic import AnthropicService
from apps.ai.base import FollowupRewrite, ProviderUnavailable
from apps.ai.flm import FLMService
from apps.ai.rewrite import (
    MAXIMUM_REWRITE_LENGTH,
    REWRITE_HISTORY_HEADING,
    REWRITE_MAX_TOKENS,
    REWRITE_QUESTION_LEAD_IN,
    REWRITE_SYSTEM_PROMPT,
    REWRITE_TIMEOUT_SECONDS,
    RewriteViolation,
    build_rewrite_messages,
    parse_rewrite,
)
from apps.core.constants import MAXIMUM_QUESTION_LENGTH

BASE_URL = "http://flm.test/v1"
CHAT_MODEL = "gemma3:4b"
QUESTION = "And who approves it for me?"
PRIOR = ["How much annual leave do I get?"]
STANDALONE = "Who approves annual leave for me?"
CONFORMING = json.dumps({"question": STANDALONE})


@pytest.fixture(autouse=True)
def flm_settings():
    with override_settings(FLM_BASE_URL=BASE_URL, FLM_API_KEY="flm", FLM_CHAT_MODEL=CHAT_MODEL):
        yield


# --- The parser: the generation parser's tolerances, the rewrite's shape ----------------


def test_a_conforming_reply_parses_to_the_standalone_question():
    assert parse_rewrite(CONFORMING) == FollowupRewrite(question=STANDALONE)


@pytest.mark.parametrize(
    "raw",
    [
        f"```json\n{CONFORMING}\n```",  # a code fence
        f"Here is the rewrite you asked for: {CONFORMING}",  # a sentence of preamble
        '{"question": "%s",}' % STANDALONE,  # a trailing comma
        f"  {CONFORMING}  \n",  # surrounding whitespace
    ],
)
def test_the_parser_repairs_the_malformations_the_generation_parser_repairs(raw):
    assert parse_rewrite(raw).question == STANDALONE


def test_the_value_is_stripped_so_what_is_embedded_has_no_surrounding_whitespace():
    assert parse_rewrite(json.dumps({"question": f"  {STANDALONE}\n"})).question == STANDALONE


@pytest.mark.parametrize(
    "raw",
    [
        "",  # nothing at all
        "I would rewrite it as: who approves leave?",  # prose, no object
        json.dumps(["not", "an", "object"]),  # wrong top-level type
        json.dumps({"rewrite": STANDALONE}),  # wrong key
        json.dumps({"question": STANDALONE, "confidence": 0.9}),  # an extra key
        json.dumps({"question": ""}),  # empty value
        json.dumps({"question": "   "}),  # whitespace-only value
        json.dumps({"question": 7}),  # non-string value
        json.dumps({"question": "x" * (MAXIMUM_REWRITE_LENGTH + 1)}),  # over the ceiling
        '{"question": "unterminated',  # unbalanced JSON
    ],
)
def test_a_non_conforming_reply_is_a_rewrite_violation(raw):
    """Invariant 10's shape: not the one-field object means no reply at all.

    Every case is rejected whole — no partial repair beyond the three tolerances the
    generation parser has, and nothing of the reply is kept.
    """
    with pytest.raises(RewriteViolation):
        parse_rewrite(raw)


def test_a_violations_message_never_quotes_the_reply():
    """The message reaches the attempt log, which holds no question or reply text."""
    sentinel = "SENTINEL-the-reply-text-must-not-leak"
    for raw in (
        f"{sentinel} is my answer",
        json.dumps({"rewrite": sentinel}),
        json.dumps({"question": sentinel, "extra": sentinel}),
        json.dumps({"question": sentinel * 200}),  # over-length, value is the sentinel
    ):
        with pytest.raises(RewriteViolation) as caught:
            parse_rewrite(raw)
        assert sentinel not in str(caught.value)


def test_the_ceiling_is_twice_the_question_bound():
    """The task's stated guard, pinned to the constant it is derived from."""
    assert MAXIMUM_REWRITE_LENGTH == 2 * MAXIMUM_QUESTION_LENGTH
    assert parse_rewrite(json.dumps({"question": "x" * MAXIMUM_REWRITE_LENGTH})).question


# --- The messages ------------------------------------------------------------------------


def test_the_messages_carry_the_history_oldest_first_and_the_follow_up():
    system, user = build_rewrite_messages(QUESTION, ["first question", "second question"])
    assert system == {"role": "system", "content": REWRITE_SYSTEM_PROMPT}
    content = user["content"]
    assert content.index(REWRITE_HISTORY_HEADING) < content.index("- first question")
    assert content.index("- first question") < content.index("- second question")
    assert f"{REWRITE_QUESTION_LEAD_IN}{QUESTION}" in content
    # Questions only ever reach this prompt; there is no identifier in it for a reply
    # to cite, and no passage block for one to be mistaken for.
    assert "[chunk_id:" not in REWRITE_SYSTEM_PROMPT + content


def test_an_empty_history_is_a_caller_bug_not_a_prompt():
    with pytest.raises(ValueError):
        build_rewrite_messages(QUESTION, [])


# --- FLM: one call, exactly --------------------------------------------------------------


def chat_response(content: str):
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": CHAT_MODEL,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content},
                 "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        },
    )


def make_service(handler):
    client = openai.OpenAI(
        base_url=BASE_URL,
        api_key="flm",
        max_retries=0,  # the single-attempt policy is the application's, not the SDK's
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return FLMService(client=client)


def scripted(*replies):
    seen = []

    def handler(request):
        seen.append(request)
        reply = replies[min(len(seen) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx2.Response):
            return reply
        return chat_response(reply)

    handler.seen = seen
    return handler


def test_flm_returns_the_rewrite_after_exactly_one_call():
    handler = scripted(CONFORMING)
    assert make_service(handler).rewrite_followup(QUESTION, PRIOR).question == STANDALONE
    assert len(handler.seen) == 1


def test_the_request_carries_the_rewrite_prompt_and_its_own_parameters():
    """The rewrite's prompt and ceiling go over the wire, not generation's."""
    handler = scripted(CONFORMING)
    make_service(handler).rewrite_followup(QUESTION, PRIOR)
    body = json.loads(handler.seen[0].content)
    assert body["model"] == CHAT_MODEL
    assert body["max_tokens"] == REWRITE_MAX_TOKENS
    assert body["temperature"] == 0.0
    assert body["messages"] == build_rewrite_messages(QUESTION, PRIOR)
    assert body["messages"][0]["content"] == REWRITE_SYSTEM_PROMPT


def test_a_non_conforming_reply_raises_after_exactly_one_call_never_a_retry():
    """ONE attempt is the whole policy: a second request here is the bug."""
    handler = scripted("I think the standalone question would be about leave approval.",
                       CONFORMING)  # a second call WOULD succeed; it must never be made
    with pytest.raises(RewriteViolation):
        make_service(handler).rewrite_followup(QUESTION, PRIOR)
    assert len(handler.seen) == 1


def test_a_transport_failure_is_provider_unavailable_after_one_call():
    handler = scripted(httpx2.ConnectError("refused"))
    with pytest.raises(ProviderUnavailable):
        make_service(handler).rewrite_followup(QUESTION, PRIOR)
    assert len(handler.seen) == 1


def test_a_server_error_is_provider_unavailable_after_one_call():
    handler = scripted(httpx2.Response(500, json={"error": "NPU fault"}))
    with pytest.raises(ProviderUnavailable):
        make_service(handler).rewrite_followup(QUESTION, PRIOR)
    assert len(handler.seen) == 1


def test_a_client_error_surfaces_as_itself():
    """A 4xx is a configuration error, as it is on every other call path."""
    handler = scripted(httpx2.Response(404, json={"error": "no such model"}))
    with pytest.raises(openai.APIStatusError):
        make_service(handler).rewrite_followup(QUESTION, PRIOR)
    assert len(handler.seen) == 1


def test_an_empty_choices_list_is_a_rewrite_violation():
    handler = scripted(httpx2.Response(200, json={
        "id": "chatcmpl-test", "object": "chat.completion", "created": 0,
        "model": CHAT_MODEL, "choices": [],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }))
    with pytest.raises(RewriteViolation):
        make_service(handler).rewrite_followup(QUESTION, PRIOR)


# --- Anthropic: the same prompt and policy through the other SDK --------------------------


class FakeTextBlock:
    def __init__(self, text, block_type="text"):
        self.text = text
        self.type = block_type


class FakeMessage:
    def __init__(self, text):
        self.content = [FakeTextBlock(text)]
        self.stop_reason = "end_turn"
        self.usage = None


class FakeMessages:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeMessage(self.text)


class FakeAnthropicClient:
    def __init__(self, text):
        self.messages = FakeMessages(text)


def test_anthropic_sends_the_rewrite_system_prompt_in_the_system_parameter():
    client = FakeAnthropicClient(CONFORMING)
    service = AnthropicService(anthropic_client=client)

    assert service.rewrite_followup(QUESTION, PRIOR).question == STANDALONE

    [call] = client.messages.calls  # exactly one attempt
    assert call["system"] == REWRITE_SYSTEM_PROMPT
    assert call["max_tokens"] == REWRITE_MAX_TOKENS
    assert call["timeout"] == REWRITE_TIMEOUT_SECONDS
    _, user = build_rewrite_messages(QUESTION, PRIOR)
    assert call["messages"] == [{"role": "user", "content": user["content"]}]


def test_anthropic_raises_the_violation_after_exactly_one_call():
    client = FakeAnthropicClient("Certainly! The standalone form would be as follows.")
    with pytest.raises(RewriteViolation):
        AnthropicService(anthropic_client=client).rewrite_followup(QUESTION, PRIOR)
    assert len(client.messages.calls) == 1
