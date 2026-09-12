"""Test double for the AI service (docs/ai-provider.md section 6).

The suite never reaches a live provider: the root conftest.py installs a
StubAIService for every test through apps.ai.get_ai_service. A test that needs
different behaviour (another dimension, an outage) builds its own instance and
patches it in the same way; apps/ai/tests/test_checks.py shows how.
"""

import hashlib
import random

from django.conf import settings

from apps.ai.base import EmbeddingResult, Passage, ProviderHealth, Statement, StatementList

STUB_EMBEDDING_MODEL = "stub-embed"


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

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=self.available, detail=self.detail)
