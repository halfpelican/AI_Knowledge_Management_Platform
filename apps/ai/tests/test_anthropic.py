"""AnthropicService: Voyage embeddings through the openai client, Claude health. No network."""

import json

import httpx2
import openai
import pytest
from django.test import override_settings

from apps.ai.anthropic import AnthropicService
from apps.ai.base import ProviderHealth, ProviderUnavailable

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


def test_generate_statements_is_not_built_yet():
    with pytest.raises(NotImplementedError, match="Stage 4"):
        AnthropicService().generate_statements("question?", [])
