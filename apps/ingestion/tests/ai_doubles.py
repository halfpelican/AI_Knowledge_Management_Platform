"""Scripted AIService doubles for the indexing tests.

The suite's own StubAIService (apps/ai/testing.py) always succeeds, which is the
right default and useless for testing the retry policy. These subclass it so the
vectors, the model name and the call log stay identical and only the failure
behaviour is scripted.

Installed the way conftest.py installs the stub — ``monkeypatch.setattr(apps.ai,
"get_ai_service", lambda: service)`` — because embed_and_store_chunks() looks the
function up on the module at call time (docs/ai-provider.md section 6).

Not named test_*.py, so pytest collects the tests and not the doubles.
"""

from collections import Counter

import apps.ai
from apps.ai.base import EmbeddingResult, ProviderUnavailable
from apps.ai.testing import STUB_EMBEDDING_MODEL, StubAIService


def install(monkeypatch, service):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
    return service


class CountingService(StubAIService):
    """StubAIService plus a per-chunk attempt count, which the retry tests assert on."""

    def attempts_for(self, text: str) -> int:
        """How many times embed() was called with exactly this one chunk."""
        return sum(1 for call in self.embed_calls if call == [text])


class ScriptedEmbedService(CountingService):
    """A stub that fails the first ``failures`` attempts for the texts it selects.

    ``failures=MAXIMUM_EMBED_ATTEMPTS`` never succeeds for those texts; a smaller
    number recovers, which is how "two failures then success" is exercised.
    ``should_fail`` picks which chunks are affected, so a document can have one chunk
    fail and another succeed — the only way "Partially indexed" can be reached.

    ``error`` is what a failed attempt raises. ProviderUnavailable by default, which
    the retry policy absorbs; a test that needs the NFR-21 rollback passes something
    else, because an unexpected exception is not an outcome the pipeline decided.
    """

    def __init__(self, failures=0, should_fail=None, error=None, dimension=None):
        super().__init__(dimension=dimension)
        self.failures = failures
        self.should_fail = should_fail if should_fail is not None else (lambda text: True)
        self.error = error if error is not None else ProviderUnavailable("stub outage")
        self.attempts = Counter()

    def embed(self, texts: list[str]) -> EmbeddingResult:
        # Logged before any failure, so a test can count attempts that raised.
        self.embed_calls.append(list(texts))
        text = texts[0]
        self.attempts[text] += 1
        if self.should_fail(text) and self.attempts[text] <= self.failures:
            raise self.error
        return EmbeddingResult(
            vectors=[self.vector_for(each) for each in texts],
            model=STUB_EMBEDDING_MODEL,
            dimension=self.dimension,
        )


class MisreportingEmbedService(CountingService):
    """Declares one dimension and returns a vector of another.

    The corruption risk R10 names, in its least visible form: every value looks
    plausible on its own and only the pair is wrong.
    """

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[[0.0] * (self.dimension - 1) for _ in texts],
            model=STUB_EMBEDDING_MODEL,
            dimension=self.dimension,
        )
