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

from django.conf import settings

from apps.ai.base import (
    EmbeddingResult,
    FollowupRewrite,
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
        self.generate_calls: list[tuple[str, list[Passage]]] = []
        self.rewrite_calls: list[tuple[str, list[str]]] = []

    def vector_for(self, text: str) -> list[float]:
        # Seeded from a content hash so the same text embeds to the same vector in
        # every process; Python's own hash() is salted per process.
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dimension)]

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            raise ValueError("embed() needs at least one text")
        self.embed_calls.append(list(texts))
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

    def rewrite_followup(self, question: str, prior_questions: list[str]) -> FollowupRewrite:
        """A deterministic standalone rewrite, recorded like every other call.

        The shape is DISTINCT from apps/retrieval/conversation.py's plain join — marked,
        question first — so a test can tell "the rewrite was embedded" from "the fallback
        join was embedded" by the exact string, while still containing the question and
        every prior question verbatim for substring assertions. A double without this
        method is also a valid provider to test against: the pipeline falls back on the
        AttributeError, which is the fallback path's own test hook.
        """
        self.rewrite_calls.append((question, list(prior_questions)))
        if not prior_questions:
            raise ValueError("rewrite_followup() needs at least one prior question")
        return FollowupRewrite(
            question=f"{question} (standalone, resolving: {' '.join(prior_questions)})"
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=self.available, detail=self.detail)
