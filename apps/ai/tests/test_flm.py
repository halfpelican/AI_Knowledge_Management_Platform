"""FLMService against an in-process mock of the OpenAI wire format. No live server."""

import json
import logging

import httpx2  # the openai SDK's HTTP layer; its MockTransport keeps every call in-process
import openai
import pytest
from django.test import override_settings

from apps.ai import attempt_log
from apps.ai.base import (
    INPUT_TYPE_DOCUMENT,
    INPUT_TYPE_QUERY,
    EmbeddingResult,
    ProviderHealth,
    ProviderRefused,
    ProviderUnavailable,
)
from apps.ai.flm import FLMService

BASE_URL = "http://flm.test/v1"
EMBED_MODEL = "embed-gemma"
VECTOR_LENGTH = 4  # whatever the fake server returns; the dimension is the server's to report


@pytest.fixture(autouse=True)
def flm_settings():
    with override_settings(FLM_BASE_URL=BASE_URL, FLM_API_KEY="flm", FLM_EMBED_MODEL=EMBED_MODEL):
        yield


def make_service(handler):
    client = openai.OpenAI(
        base_url=BASE_URL,
        api_key="flm",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return FLMService(client=client)


def embeddings_response(request, reverse=False):
    body = json.loads(request.content)
    items = [
        {"object": "embedding", "index": i, "embedding": [float(i + 1)] * VECTOR_LENGTH}
        for i in range(len(body["input"]))
    ]
    if reverse:
        items.reverse()
    return httpx2.Response(
        200,
        json={
            "object": "list",
            "model": body["model"],
            "data": items,
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        },
    )


def models_response(request):
    return httpx2.Response(
        200,
        json={
            "object": "list",
            "data": [{"id": "gemma3:4b", "object": "model", "created": 0, "owned_by": "flm"}],
        },
    )


def test_embed_returns_configured_model_dimension_and_one_vector_per_text():
    seen = []

    def handler(request):
        seen.append(request)
        return embeddings_response(request)

    result = make_service(handler).embed(["alpha", "beta"])

    assert isinstance(result, EmbeddingResult)
    assert result.model == EMBED_MODEL
    assert result.dimension == VECTOR_LENGTH
    assert len(result.vectors) == 2
    assert all(len(vector) == VECTOR_LENGTH for vector in result.vectors)
    # One request, to /embeddings, carrying the configured model and the texts in order.
    assert len(seen) == 1
    assert str(seen[0].url) == f"{BASE_URL}/embeddings"
    sent = json.loads(seen[0].content)
    assert sent["model"] == EMBED_MODEL
    assert sent["input"] == ["alpha", "beta"]
    assert seen[0].headers["authorization"] == "Bearer flm"


def test_embed_orders_vectors_by_index_not_by_response_order():
    result = make_service(lambda request: embeddings_response(request, reverse=True)).embed(
        ["a", "b", "c"]
    )
    assert [vector[0] for vector in result.vectors] == [1.0, 2.0, 3.0]


@pytest.mark.parametrize("input_type", [None, INPUT_TYPE_QUERY, INPUT_TYPE_DOCUMENT])
def test_embed_never_sends_an_input_type_to_flm(input_type):
    """D-116: EmbeddingGemma reads the side from the task prefix already in the text
    (apps/ai/prefixes.py), and FLM's /embeddings has no input_type field."""
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return embeddings_response(request)

    make_service(handler).embed(["alpha"], input_type=input_type)

    assert "input_type" not in sent[0]
    assert sent[0]["input"] == ["alpha"]


def test_embed_rejects_an_empty_list_without_calling_the_server():
    def handler(request):
        raise AssertionError("no request expected for an empty input list")

    with pytest.raises(ValueError):
        make_service(handler).embed([])


def test_embed_wraps_a_connection_failure():
    def handler(request):
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(ProviderUnavailable, match="unreachable"):
        make_service(handler).embed(["alpha"])


def test_embed_wraps_a_timeout():
    def handler(request):
        raise httpx2.ReadTimeout("timed out")

    with pytest.raises(ProviderUnavailable, match="unreachable"):
        make_service(handler).embed(["alpha"])


def test_embed_wraps_a_server_error():
    def handler(request):
        return httpx2.Response(503, json={"error": {"message": "model loading"}})

    with pytest.raises(ProviderUnavailable, match="503"):
        make_service(handler).embed(["alpha"])


def test_embed_turns_a_client_error_into_unavailable_and_logs_it(caplog):
    # D-118: a 4xx surfaced as itself reached the user as a 500, not NFR-19's 503. It is
    # raised as unavailable instead, and its status and body go to the log, which is
    # where a mistyped model name now shows.
    def handler(request):
        return httpx2.Response(404, json={"error": {"message": "unknown model"}})

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with pytest.raises(ProviderRefused, match="HTTP 404"):
            make_service(handler).embed(["alpha"])

    (refusal,) = [r for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]
    assert refusal.levelno == logging.ERROR
    assert f"{BASE_URL} refused the request with HTTP 404" in refusal.getMessage()
    assert "unknown model" in refusal.getMessage()


def test_embed_wraps_an_error_body_delivered_with_status_200():
    # Observed on 2026-09-12 when the NPU dropped out under FLM: HTTP 200 with
    # {"error": "Failed to submit command to hw queue ... The device has been removed."}
    # and no data at all. The SDK's parser raises ValueError on that; it must
    # become ProviderUnavailable (503 with the NFR-19 notice), not a crash.
    def handler(request):
        return httpx2.Response(
            200,
            json={"error": "Failed to submit command to hw queue: The device has been removed."},
        )

    with pytest.raises(ProviderUnavailable, match="no embedding data"):
        make_service(handler).embed(["alpha"])


def test_embed_rejects_a_response_with_too_few_vectors():
    def handler(request):
        body = json.loads(request.content)
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": body["model"],
                "data": [{"object": "embedding", "index": 0, "embedding": [1.0] * VECTOR_LENGTH}],
                "usage": {"prompt_tokens": 0, "total_tokens": 0},
            },
        )

    with pytest.raises(ProviderUnavailable, match="1 usable vector"):
        make_service(handler).embed(["alpha", "beta"])


def test_health_is_available_when_models_list_answers():
    health = make_service(models_response).health()
    assert isinstance(health, ProviderHealth)
    assert health.available is True
    assert "1 model" in health.detail


def test_health_is_unavailable_and_does_not_raise_when_the_server_is_down():
    def handler(request):
        raise httpx2.ConnectError("connection refused")

    health = make_service(handler).health()
    assert health.available is False
    assert BASE_URL in health.detail


def test_generate_statements_reaches_the_chat_endpoint_and_returns_statements():
    """FLMService's third operation, built at Stage 4 item 5 (FR-12).

    The retry policy, the schema check and the 503 are exercised in
    apps/ai/tests/test_generation.py, which owns the NFR-19 fault injection; this asserts
    only that the operation exists, goes to /chat/completions with the configured chat
    model, and returns parsed statements.
    """
    from apps.ai.base import Passage

    chunk_id = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
    seen = []

    def handler(request):
        seen.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "gemma3:4b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"statements": [{"text": "Twenty days.", "chunk_id": chunk_id}]}
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    with override_settings(FLM_CHAT_MODEL="gemma3:4b"):
        result = make_service(handler).generate_statements(
            "How much annual leave do I get?", [Passage(chunk_id=chunk_id, text="Twenty days.")]
        )

    assert [statement.chunk_id for statement in result.statements] == [chunk_id]
    assert str(seen[0].url) == f"{BASE_URL}/chat/completions"
    assert json.loads(seen[0].content)["model"] == "gemma3:4b"


def test_production_client_is_built_from_settings_without_sdk_retries():
    service = FLMService()
    assert str(service._client.base_url).rstrip("/") == BASE_URL
    assert service._client.api_key == "flm"
    assert service._client.max_retries == 0
