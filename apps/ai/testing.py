"""Test double for the AI service (docs/ai-provider.md section 6).

The suite never reaches a live provider: the root conftest.py installs a
StubAIService for every test through apps.ai.get_ai_service. A test that needs
different behaviour (another dimension, an outage) builds its own instance and
patches it in the same way; apps/ai/tests/test_checks.py shows how.

As a second layer, conftest.py also points every provider endpoint at
UNROUTABLE_PROVIDER_URL for every test: a closed port on loopback, so a call that
bypasses the stub is refused at once instead of quietly answered by a developer's
running FLM server. apps/ai/tests/test_no_live_provider.py asserts both layers.
"""

import hashlib
import random

# The SDKs are imported here, inside apps/ai, so tests elsewhere can run a real provider
# against a scripted endpoint without importing a vendor SDK themselves (CLAUDE.md
# section 4, apps/ai/tests/test_boundary.py). ``import anthropic`` is the installed SDK,
# never apps/ai/anthropic.py: Python 3 imports are absolute.
import anthropic as anthropic_sdk
import httpx2
import openai
from django.conf import settings

from apps.ai.base import (
    EmbeddingResult,
    InputType,
    Passage,
    ProviderHealth,
    Statement,
    StatementList,
)

STUB_EMBEDDING_MODEL = "stub-embed"

# Port 9 (discard) is closed on every development machine and CI runner, so a
# connect is actively refused rather than left to time out: about 2 s per attempt
# on Windows (measured, WinError 10061), less on Linux. Loopback, so nothing leaves
# the machine even in error.
UNROUTABLE_PROVIDER_HOST = "http://127.0.0.1:9"
UNROUTABLE_PROVIDER_URL = f"{UNROUTABLE_PROVIDER_HOST}/v1"


class StubAIService:
    """Deterministic AIService: fixed vectors, fixed statements, no network, a call log."""

    def __init__(
        self,
        dimension: int | None = None,
        available: bool = True,
        detail: str = "stub provider",
    ):
        self.dimension = settings.EMBEDDING_DIMENSION if dimension is None else dimension
        self.available = available
        self.detail = detail
        self.embed_calls: list[list[str]] = []
        # The input_type each embed() call carried (D-116), one entry per call, in step
        # with embed_calls.
        self.embed_input_types: list[InputType | None] = []
        self.generate_calls: list[tuple[str, list[Passage]]] = []

    def vector_for(self, text: str) -> list[float]:
        # Seeded from a content hash so the same text embeds to the same vector in
        # every process; Python's own hash() is salted per process.
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dimension)]

    def embed(self, texts: list[str], *, input_type: InputType | None = None) -> EmbeddingResult:
        if not texts:
            raise ValueError("embed() needs at least one text")
        self.embed_calls.append(list(texts))
        self.embed_input_types.append(input_type)
        return EmbeddingResult(
            vectors=[self.vector_for(text) for text in texts],
            model=STUB_EMBEDDING_MODEL,
            dimension=self.dimension,
        )

    def generate_statements(self, question: str, passages: list[Passage]) -> StatementList:
        self.generate_calls.append((question, list(passages)))
        if not passages:
            return StatementList(statements=[])
        first = passages[0]
        return StatementList(
            statements=[
                Statement(text=f"Stub statement answering {question!r}.", chunk_id=first.chunk_id)
            ]
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=self.available, detail=self.detail)


def scripted_openai_client(base_url: str, handler) -> openai.OpenAI:
    """An openai client whose every request ``handler`` answers in-process.

    ``handler`` takes an httpx2 request and returns an httpx2 response, as a MockTransport
    handler does. For instance, it can stand in for Voyage's /embeddings endpoint in the
    D-118 route tests. ``max_retries=0``, as production builds it (apps/ai/_openai_compat.py).
    """
    return openai.OpenAI(
        base_url=base_url,
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def anthropic_status_error(status: int, message: str) -> anthropic_sdk.APIStatusError:
    """The APIStatusError the anthropic SDK raises for ``status``, built without a live call."""
    request = httpx2.Request("POST", "https://api.anthropic.test/v1/messages")
    response = httpx2.Response(
        status, json={"type": "error", "error": {"message": message}}, request=request
    )
    return anthropic_sdk.APIStatusError(message, response=response, body=None)
