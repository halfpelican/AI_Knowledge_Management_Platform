"""D-118: a provider's refusal reaches the user as NFR-19's 503, never a 500.

On the ``anthropic`` provider, a rate limit (429) and an exhausted credit (400) are
routine. Until 10 November 2026, both providers let a 4xx surface as itself, and the ask
view catches only ProviderUnavailable, so either one reached the user as a 500.

These tests run the real AnthropicService through ``POST /api/ask``, with scripted Voyage
and Claude clients and nothing on a network, from both roles. The user's rule: retry a
429, and answer the rest with the 503.
- **A rate limit** becomes ProviderUnavailable, and the retry loop spends every attempt
  on it.
- **Any other 4xx** becomes ProviderRefused, which stops the loop after one call, an
  exhausted credit included.
- **Either way,** the view answers 503 with the fixed notice.

The clients come from apps.ai.testing, because a vendor SDK may not be imported outside
apps/ai, tests included (CLAUDE.md section 4).
"""

import json

import httpx2
import pytest
from django.conf import settings
from django.test import override_settings

import apps.ai
from apps.ai.anthropic import AnthropicService
from apps.ai.testing import anthropic_status_error, scripted_openai_client
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_EMBED_ATTEMPTS,
    MAXIMUM_GENERATION_ATTEMPTS,
    NO_ANSWER_MESSAGE,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.retrieval.models import QueryLog

pytestmark = pytest.mark.django_db

ASK_URL = "/api/ask"
QUESTION = "How much annual leave do I get?"
VOYAGE_URL = "https://voyage.test/v1"
VOYAGE_MODEL = "voyage-4"
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
# The question's vector and the passage's are the same unit vector, so the passage scores
# 1.0, clears the threshold, and generation is reached.
VECTOR = [1.0] + [0.0] * (settings.EMBEDDING_DIMENSION - 1)
CREDIT_EXHAUSTED = "Your credit balance is too low to access the Anthropic API."


@pytest.fixture(autouse=True)
def anthropic_provider():
    with override_settings(AI_PROVIDER="anthropic", VOYAGE_MODEL=VOYAGE_MODEL):
        yield


@pytest.fixture
def passage(employee):
    """One passage, visible to both roles, embedded by the model the query embeds with."""
    document = Document.objects.create(
        title="Leave policy", file_type="pdf", uploaded_by=employee, visible_to_roles=BOTH_ROLES
    )
    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=0,
        chunk_text="Staff accrue twenty days of annual leave a year.",
        embedding=VECTOR,
        embedding_model=VOYAGE_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=BOTH_ROLES,
    )


def voyage_client(handler):
    return scripted_openai_client(VOYAGE_URL, handler)


def voyage_answering(request):
    body = json.loads(request.content)
    return httpx2.Response(
        200,
        json={
            "object": "list",
            "data": [{"object": "embedding", "embedding": VECTOR, "index": 0}],
            "model": body["model"],
            "usage": {"total_tokens": 7},
        },
    )


class RefusingClaude:
    """A Claude client whose every messages.create raises ``error``, counting the calls."""

    def __init__(self, error):
        self.error = error
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        raise self.error


def install(monkeypatch, service):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
    return service


def ask(session_client):
    return session_client.client.post(ASK_URL, {"question": QUESTION}, format="json")


def assert_the_fixed_503(response, cause):
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail and NO_ANSWER_MESSAGE not in detail
    # The cause goes to the log; the reply keeps the fixed notice.
    assert cause not in response.content.decode()
    # A question that never completed writes no row.
    assert not QueryLog.objects.exists()


@pytest.mark.parametrize(
    "status, message, calls",
    [(429, "rate limited", MAXIMUM_EMBED_ATTEMPTS), (401, "invalid api key", 1)],
    ids=["rate-limited", "refused"],
)
def test_a_refused_question_embedding_is_503(
    session_client, monkeypatch, passage, status, message, calls
):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx2.Response(status, json={"detail": message})

    claude = RefusingClaude(anthropic_status_error(500, "never reached"))
    install(monkeypatch, AnthropicService(embedding_client=voyage_client(handler), anthropic_client=claude))

    response = ask(session_client)

    assert_the_fixed_503(response, message)
    assert len(sent) == calls
    assert claude.calls == 0  # nothing was generated for a question never embedded


@pytest.mark.parametrize(
    "status, message, calls",
    [(429, "rate limited", MAXIMUM_GENERATION_ATTEMPTS), (400, CREDIT_EXHAUSTED, 1)],
    ids=["rate-limited", "credit-exhausted"],
)
def test_a_refused_generation_is_503(session_client, monkeypatch, passage, status, message, calls):
    claude = RefusingClaude(anthropic_status_error(status, message))
    install(
        monkeypatch,
        AnthropicService(embedding_client=voyage_client(voyage_answering), anthropic_client=claude),
    )

    response = ask(session_client)

    assert_the_fixed_503(response, message)
    assert claude.calls == calls
