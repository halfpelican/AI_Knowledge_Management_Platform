"""FLMService against an in-process mock of the OpenAI wire format. No live server."""

import json

import httpx2  # the openai SDK's HTTP layer; its MockTransport keeps every call in-process
import openai
import pytest
from django.test import override_settings

from apps.ai.base import EmbeddingResult, ProviderHealth, ProviderUnavailable
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


def test_embed_lets_a_client_error_surface_as_is():
    # 4xx is a bad request or a misconfiguration, not an outage. It must not be
    # dressed up as "provider unavailable" and turned into a 503.
    def handler(request):
        return httpx2.Response(404, json={"error": {"message": "unknown model"}})

    with pytest.raises(openai.APIStatusError) as excinfo:
        make_service(handler).embed(["alpha"])
    assert excinfo.value.status_code == 404
    assert not isinstance(excinfo.value, ProviderUnavailable)


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


def test_generate_statements_is_not_built_yet():
    with pytest.raises(NotImplementedError, match="Stage 4"):
        make_service(models_response).generate_statements("question?", [])


def test_production_client_is_built_from_settings_without_sdk_retries():
    service = FLMService()
    assert str(service._client.base_url).rstrip("/") == BASE_URL
    assert service._client.api_key == "flm"
    assert service._client.max_retries == 0
