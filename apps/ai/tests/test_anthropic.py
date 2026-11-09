"""AnthropicService: Voyage embeddings, Claude generation and health. No network.

The anthropic SDK is never called for real. The provider is funded since D-113, but the
suite never spends: the generation tests below and the health tests inject a fake client,
and the embed tests use the openai SDK's MockTransport, as the FLM tests do.
"""

import base64
import inspect
import json
import logging
import struct
from types import SimpleNamespace

import anthropic as anthropic_sdk
import httpx2
import openai
import pytest
from django.test import override_settings

from apps.ai import attempt_log
from apps.ai.anthropic import CLAUDE_EFFORT, CLAUDE_MAX_TOKENS, AnthropicService
from apps.ai.base import (
    INPUT_TYPE_DOCUMENT,
    INPUT_TYPE_QUERY,
    Passage,
    ProviderHealth,
    ProviderUnavailable,
)
from apps.ai.generation import GENERATION_MAX_TOKENS, GENERATION_TIMEOUT_SECONDS, fewer_statements
from apps.ai.prompting import SYSTEM_PROMPT, build_user_prompt, statement_cap_sentence
from apps.core.constants import MAXIMUM_GENERATION_ATTEMPTS, MAXIMUM_STATEMENTS

VOYAGE_URL = "https://voyage.test/v1"
VOYAGE_MODEL = "voyage-4"
VECTOR_LENGTH = 4


@pytest.fixture(autouse=True)
def anthropic_settings():
    with override_settings(
        VOYAGE_BASE_URL=VOYAGE_URL,
        VOYAGE_MODEL=VOYAGE_MODEL,
        VOYAGE_API_KEY="voyage-test-key",
        ANTHROPIC_API_KEY="",
    ):
        yield


def voyage_client(handler):
    return openai.OpenAI(
        base_url=VOYAGE_URL,
        api_key="voyage-test-key",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def voyage_response(request):
    # The shape Voyage's /v1/embeddings returns, which is the OpenAI shape.
    body = json.loads(request.content)
    return httpx2.Response(
        200,
        json={
            "object": "list",
            "data": [
                {"object": "embedding", "embedding": [0.5] * VECTOR_LENGTH, "index": i}
                for i in range(len(body["input"]))
            ],
            "model": body["model"],
            "usage": {"total_tokens": 7},
        },
    )


class FakeModels:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return []


class FakeAnthropicClient:
    def __init__(self, error=None):
        self.models = FakeModels(error)


def test_embed_goes_to_voyage_and_records_the_voyage_model():
    seen = []

    def handler(request):
        seen.append(request)
        return voyage_response(request)

    result = AnthropicService(embedding_client=voyage_client(handler)).embed(["alpha", "beta"])

    assert result.model == VOYAGE_MODEL
    assert result.dimension == VECTOR_LENGTH
    assert len(result.vectors) == 2
    assert str(seen[0].url) == f"{VOYAGE_URL}/embeddings"
    assert json.loads(seen[0].content)["model"] == VOYAGE_MODEL
    assert seen[0].headers["authorization"] == "Bearer voyage-test-key"


def test_embed_rejects_an_empty_list():
    with pytest.raises(ValueError):
        AnthropicService(embedding_client=voyage_client(voyage_response)).embed([])


def test_embed_wraps_a_voyage_outage():
    def handler(request):
        return httpx2.Response(502, json={"detail": "bad gateway"})

    with pytest.raises(ProviderUnavailable, match="502"):
        AnthropicService(embedding_client=voyage_client(handler)).embed(["alpha"])


def test_embed_without_a_voyage_key_is_unavailable_not_a_crash():
    with override_settings(VOYAGE_API_KEY=""), pytest.raises(ProviderUnavailable, match="VOYAGE_API_KEY"):
        AnthropicService().embed(["alpha"])


@pytest.mark.parametrize("input_type", [INPUT_TYPE_QUERY, INPUT_TYPE_DOCUMENT])
def test_embed_tells_voyage_whether_the_text_is_a_question_or_a_passage(input_type):
    """D-116: Voyage is told on the request, not by a prefix in the text."""
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return voyage_response(request)

    AnthropicService(embedding_client=voyage_client(handler)).embed(
        ["alpha"], input_type=input_type
    )

    assert sent[0]["input_type"] == input_type
    assert sent[0]["input"] == ["alpha"]  # the text goes as given, with no prefix added


def test_embed_without_an_input_type_sends_none_and_no_width():
    """A dimension probe passes no input_type, so Voyage's default (null) applies.

    No output_dimension either: the width is voyage-4's default, and EMBEDDING_DIMENSION
    is what has to match it (D-117).
    """
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return voyage_response(request)

    AnthropicService(embedding_client=voyage_client(handler)).embed(["probe"])

    assert "input_type" not in sent[0]
    assert "output_dimension" not in sent[0]


def test_embed_decodes_the_base64_float32_vectors_it_asks_voyage_for():
    """The openai client asks for base64 and decodes it as float32.

    Voyage documents base64 as a float32 NumPy array, which is little-endian on the
    machines both ends run on. These values are exact in float32, so the round trip is
    exact too.
    """
    values = [0.5, -0.25, 1.0, 0.125]
    encoded = base64.b64encode(struct.pack(f"<{len(values)}f", *values)).decode("ascii")
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [{"object": "embedding", "embedding": encoded, "index": 0}],
                "model": body["model"],
                "usage": {"total_tokens": 3},
            },
        )

    result = AnthropicService(embedding_client=voyage_client(handler)).embed(["alpha"])

    assert sent[0]["encoding_format"] == "base64"
    assert result.vectors == [values]
    assert result.dimension == len(values)


def test_health_is_unavailable_when_the_anthropic_key_is_empty():
    client = FakeAnthropicClient()
    health = AnthropicService(anthropic_client=client).health()
    assert health == ProviderHealth(available=False, detail="ANTHROPIC_API_KEY is not set")
    assert client.models.calls == []


def test_health_is_available_when_models_list_answers():
    client = FakeAnthropicClient()
    with override_settings(ANTHROPIC_API_KEY="sk-ant-test"):
        health = AnthropicService(anthropic_client=client).health()
    assert health.available is True
    assert client.models.calls == [{"limit": 1}]


def test_health_is_unavailable_and_does_not_raise_when_the_api_fails():
    client = FakeAnthropicClient(error=RuntimeError("boom"))
    with override_settings(ANTHROPIC_API_KEY="sk-ant-test"):
        health = AnthropicService(anthropic_client=client).health()
    assert health.available is False
    assert "boom" in health.detail


# --- Generation through Claude (FR-12, Stage 4 item 5) ---------------------------------
#
# Mocked, never live: the suite spends nothing, even with the provider funded (D-113), so
# this path is tested exactly as the Voyage embed path above is. The limitation is real and
# stated rather than implied — the request shape below is checked against the real SDK's
# signature but not against the API, and the first live call will be the first live call.
# What the tests do establish is that the Anthropic
# provider uses the SAME prompt, the SAME schema and the SAME retry policy as FLM, which
# is what keeps the proposal's section 9.2 provider-independence claim true.

CHUNK_ID = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
PASSAGES = [Passage(chunk_id=CHUNK_ID, text="Twenty days of annual leave per year.")]
QUESTION = "How much annual leave do I get?"
CONFORMING = json.dumps({"statements": [{"text": "Twenty days.", "chunk_id": CHUNK_ID}]})


class FakeTextBlock:
    """One content block of a Claude reply."""

    def __init__(self, text, block_type="text"):
        self.text = text
        self.type = block_type


class FakeMessage:
    def __init__(self, blocks):
        self.content = blocks


class FakeMessages:
    """messages.create scripted with a reply per call, recording every call's kwargs."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, FakeMessage):
            return reply
        return FakeMessage([FakeTextBlock(reply)])


class FakeGeneratingClient:
    def __init__(self, *replies):
        self.messages = FakeMessages(replies)
        self.models = FakeModels()


def status_error(status_code):
    """An anthropic APIStatusError carrying ``status_code``, built without a live call."""
    request = httpx2.Request("POST", "https://api.anthropic.test/v1/messages")
    response = httpx2.Response(status_code, json={"error": {"message": "scripted"}}, request=request)
    return anthropic_sdk.APIStatusError("scripted", response=response, body=None)


def test_generate_statements_sends_the_shared_prompt_and_returns_statements():
    client = FakeGeneratingClient(CONFORMING)

    with override_settings(ANTHROPIC_MODEL="claude-sonnet-5-5"):
        result = AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    assert [statement.text for statement in result.statements] == ["Twenty days."]
    assert [statement.chunk_id for statement in result.statements] == [CHUNK_ID]
    (call,) = client.messages.calls
    assert call["model"] == "claude-sonnet-5-5"
    # No sampling parameters: the pinned SDK has none, and current models refuse them.
    assert "temperature" not in call
    # Thinking is left at the model's default; {"type": "disabled"} is a 400 on Sonnet 5.5 and Opus 5.5.
    assert "thinking" not in call
    assert call["output_config"] == {"effort": CLAUDE_EFFORT}
    assert call["max_tokens"] == CLAUDE_MAX_TOKENS
    assert call["timeout"] == GENERATION_TIMEOUT_SECONDS
    # The system prompt goes in the SDK's own parameter, and it is the same string FLM
    # receives as a system message.
    assert call["system"] == SYSTEM_PROMPT
    assert [message["role"] for message in call["messages"]] == ["user"]
    assert call["messages"][0]["content"] == build_user_prompt(QUESTION, PASSAGES)
    assert f"[chunk_id: {CHUNK_ID}]" in call["messages"][0]["content"]


def test_every_argument_sent_is_one_the_real_sdk_accepts():
    """The fake client takes any keyword, so on its own it cannot catch a request the real
    SDK would refuse. Until 10 November 2026 the call sent ``temperature=0.0``, which the
    pinned SDK (anthropic 1.5.0) has no parameter for, so the first live call would have
    raised TypeError before reaching the network. Binding the recorded call against the
    real ``messages.create`` signature catches that kind of fault without a network call;
    the client is built against the suite's unroutable base URL and never sends."""
    client = FakeGeneratingClient(CONFORMING)

    AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    real_create = anthropic_sdk.Anthropic(api_key="sk-ant-test").messages.create
    (call,) = client.messages.calls
    inspect.signature(real_create).bind(**call)  # TypeError on a keyword the SDK lacks


def test_claudes_token_ceiling_leaves_room_for_thinking():
    """Current Claude models think before they answer, and the thinking counts against
    ``max_tokens``. FLM's 800 was sized for the JSON reply alone, so Claude needs its own
    ceiling, or a reply is cut off mid-JSON, fails the schema three times and becomes a 503."""
    assert CLAUDE_MAX_TOKENS > 10 * GENERATION_MAX_TOKENS


def test_generation_joins_only_the_text_blocks_of_the_reply():
    """Claude replies in blocks; a non-text block carries no JSON and is skipped."""
    reply = FakeMessage(
        [FakeTextBlock("", block_type="thinking"), FakeTextBlock(CONFORMING)]
    )
    client = FakeGeneratingClient(reply)

    result = AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    assert result.statements != []


def test_generation_refuses_an_empty_passage_list_without_calling_the_api():
    client = FakeGeneratingClient(CONFORMING)

    with pytest.raises(ValueError, match="at least one passage"):
        AnthropicService(anthropic_client=client).generate_statements(QUESTION, [])

    assert client.messages.calls == []


def test_an_empty_statement_list_is_returned_and_not_retried():
    client = FakeGeneratingClient('{"statements": []}')

    result = AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    assert result.statements == []
    assert len(client.messages.calls) == 1


def test_a_malformed_reply_is_retried_and_the_conforming_one_is_returned():
    client = FakeGeneratingClient("Here is your answer, in prose.", CONFORMING)

    result = AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    assert result.statements != []
    assert len(client.messages.calls) == 2


def test_three_malformed_replies_raise_provider_unavailable_after_exactly_three_calls():
    """The same NFR-19 total as the FLM path, because it is the same loop (D-19)."""
    client = FakeGeneratingClient("prose", "more prose", "still prose")

    with override_settings(ANTHROPIC_MODEL="claude-sonnet-5-5"):
        with pytest.raises(ProviderUnavailable, match="STATEMENT_LIST_SCHEMA"):
            AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    assert len(client.messages.calls) == MAXIMUM_GENERATION_ATTEMPTS == 3


def test_a_transport_failure_is_retried_then_becomes_provider_unavailable():
    failure = anthropic_sdk.APIConnectionError(request=httpx2.Request("POST", "https://api.test"))
    client = FakeGeneratingClient(failure, failure, failure)

    with pytest.raises(ProviderUnavailable, match="unreachable"):
        AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    assert len(client.messages.calls) == 3


def test_a_server_error_is_retried_and_a_later_conforming_reply_is_returned():
    client = FakeGeneratingClient(status_error(529), CONFORMING)

    result = AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    assert result.statements != []
    assert len(client.messages.calls) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 429])
def test_a_client_error_surfaces_as_itself_and_consumes_no_retries(status):
    """4xx is a key, model or quota problem, not an outage; a 429 included (see the
    provider comment: retrying a rate limit inside a 3-attempt budget would exhaust it
    and report a billing condition as an NPU fault)."""
    client = FakeGeneratingClient(status_error(status))

    with pytest.raises(anthropic_sdk.APIStatusError) as excinfo:
        AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    assert excinfo.value.status_code == status
    assert not isinstance(excinfo.value, ProviderUnavailable)
    assert len(client.messages.calls) == 1


def test_every_attempt_is_reported_to_on_attempt():
    client = FakeGeneratingClient("prose", CONFORMING)
    recorded = []

    AnthropicService(anthropic_client=client).generate_statements(
        QUESTION, PASSAGES, on_attempt=recorded.append
    )

    assert [attempt.outcome for attempt in recorded] == ["schema-violation", "parsed"]


def _claude_reply(text, *, stop_reason, input_tokens, output_tokens):
    """A Claude message carrying the stop reason and usage block the SDK documents."""
    message = FakeMessage([FakeTextBlock(text)])
    message.stop_reason = stop_reason
    message.usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return message


def test_claudes_stop_reason_and_usage_reach_the_attempt_log(caplog):
    """7 November 2026, step 7 phase 1 (apps/ai/attempt_log.py). The loop is shared, so Claude's
    replies are described the same way FLM's are: ``stop_reason`` verbatim as the finish reason,
    ``output_tokens`` as the completion count, ``input_tokens`` as the prompt count, and the
    ``max_tokens`` the request carried."""
    truncated = '{"statements": [{"text": "Twenty days.", "chunk_id": "3f2a'
    client = FakeGeneratingClient(
        _claude_reply(
            truncated, stop_reason="max_tokens", input_tokens=900, output_tokens=CLAUDE_MAX_TOKENS
        ),
        _claude_reply(CONFORMING, stop_reason="end_turn", input_tokens=900, output_tokens=25),
    )

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    records = [r for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]
    assert [r.levelno for r in records] == [logging.WARNING, logging.INFO]
    sent = [call["max_tokens"] for call in client.messages.calls]
    assert sent == [CLAUDE_MAX_TOKENS, CLAUDE_MAX_TOKENS]
    failed, parsed = (r.getMessage() for r in records)
    first, second = MAXIMUM_STATEMENTS, fewer_statements(MAXIMUM_STATEMENTS)
    assert (
        f"[finish_reason=max_tokens completion_tokens={CLAUDE_MAX_TOKENS} prompt_tokens=900 max_tokens={sent[0]} "
        f"max_statements={first}] (account not set): SchemaViolation: unbalanced JSON object in the response"
    ) in failed
    assert (
        f"[finish_reason=end_turn completion_tokens=25 prompt_tokens=900 max_tokens={sent[1]} "
        f"max_statements={second}] (account not set): 1 statement(s)"
    ) in parsed


def test_claude_is_asked_for_fewer_statements_after_a_reply_over_the_cap():
    """Step 7 phase 2a: the shared loop's retry reaches Claude's prompt the same way."""
    over = json.dumps(
        {"statements": [{"text": f"S{n}.", "chunk_id": CHUNK_ID} for n in range(MAXIMUM_STATEMENTS + 1)]}
    )
    client = FakeGeneratingClient(over, CONFORMING)

    result = AnthropicService(anthropic_client=client).generate_statements(QUESTION, PASSAGES)

    assert [s.text for s in result.statements] == ["Twenty days."]
    prompts = [call["messages"][0]["content"] for call in client.messages.calls]
    assert statement_cap_sentence(MAXIMUM_STATEMENTS) in prompts[0]
    assert statement_cap_sentence(fewer_statements(MAXIMUM_STATEMENTS)) in prompts[1]
