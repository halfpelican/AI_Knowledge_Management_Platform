"""Claude + Voyage implementation: the documented production configuration.

Generation goes to Claude through the official anthropic SDK (built in Stage 4).
Embeddings go to Voyage, whose /embeddings endpoint speaks the OpenAI wire format,
through the same openai client shape FLM uses (docs/ai-provider.md section 3).
Kept working so the proposal's section 9.2 remains true; not used day to day.
"""

# This module is apps/ai/anthropic.py. Python 3 imports are absolute, so
# ``import anthropic`` here resolves to the installed SDK and never to this file;
# the alias only keeps the two visibly distinct for anyone reading the code.
import anthropic as anthropic_sdk
from django.conf import settings

from apps.ai import _openai_compat
from apps.ai.base import EmbeddingResult, Passage, ProviderHealth, ProviderUnavailable, StatementList

GENERATION_NOT_BUILT = "Grounded generation is built in Stage 4 (FR-12)"


class AnthropicService:
    def __init__(self, embedding_client=None, anthropic_client=None):
        # Both clients are injected by tests. Production builds them lazily: the
        # openai client refuses an empty key, and the keys are blank unless the
        # anthropic path is actually in use (docs/decisions.md D-04).
        self._embedding_client = embedding_client
        self._anthropic_client = anthropic_client

    def _voyage(self):
        if self._embedding_client is None:
            if not settings.VOYAGE_API_KEY:
                raise ProviderUnavailable(
                    "VOYAGE_API_KEY is not set; embeddings need it when AI_PROVIDER=anthropic"
                )
            self._embedding_client = _openai_compat.build_client(
                settings.VOYAGE_BASE_URL, settings.VOYAGE_API_KEY
            )
        return self._embedding_client

    def _anthropic(self):
        if self._anthropic_client is None:
            self._anthropic_client = anthropic_sdk.Anthropic(
                api_key=settings.ANTHROPIC_API_KEY, max_retries=0
            )
        return self._anthropic_client

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            raise ValueError("embed() needs at least one text")
        return _openai_compat.embed(
            self._voyage(), settings.VOYAGE_MODEL, texts, endpoint=settings.VOYAGE_BASE_URL
        )

    def generate_statements(self, question: str, passages: list[Passage]) -> StatementList:
        # Stage 4 (FR-12): call self._anthropic().messages.create(...) with
        # settings.ANTHROPIC_MODEL through the official anthropic SDK, enforce the
        # statement schema, and raise ProviderUnavailable after
        # MAXIMUM_GENERATION_ATTEMPTS. Never a bare string, never a partial answer.
        raise NotImplementedError(GENERATION_NOT_BUILT)

    def health(self) -> ProviderHealth:
        # A report, not a call path: this never raises.
        if not settings.ANTHROPIC_API_KEY:
            return ProviderHealth(available=False, detail="ANTHROPIC_API_KEY is not set")
        try:
            self._anthropic().models.list(limit=1)
        except Exception as exc:  # noqa: BLE001 - any failure means "not available"
            return ProviderHealth(available=False, detail=f"Anthropic API unreachable: {exc}")
        return ProviderHealth(available=True, detail="Anthropic API reachable")
