"""FastFlowLM implementation: docs/ai-provider.md section 3.

FLM speaks the OpenAI wire format, so the openai package is the client. Only the
base URL, the placeholder key and the model names distinguish it from any other
OpenAI-compatible server. Default for development, testing and demonstration.
"""

import openai
from django.conf import settings

from apps.ai import _openai_compat
from apps.ai.base import EmbeddingResult, Passage, ProviderHealth, StatementList

GENERATION_NOT_BUILT = "Grounded generation is built in Stage 4 (FR-12)"


class FLMService:
    def __init__(self, client: openai.OpenAI | None = None):
        # ``client`` is injected by tests; production builds one from settings.
        self._client = client or _openai_compat.build_client(
            settings.FLM_BASE_URL, settings.FLM_API_KEY
        )

    def embed(self, texts: list[str]) -> EmbeddingResult:
        return _openai_compat.embed(
            self._client, settings.FLM_EMBED_MODEL, texts, endpoint=settings.FLM_BASE_URL
        )

    def generate_statements(self, question: str, passages: list[Passage]) -> StatementList:
        raise NotImplementedError(GENERATION_NOT_BUILT)

    def health(self) -> ProviderHealth:
        # A report, not a call path: this never raises.
        try:
            models = self._client.models.list()
        except Exception as exc:  # noqa: BLE001 - any failure means "not available"
            return ProviderHealth(
                available=False, detail=f"FLM unreachable at {settings.FLM_BASE_URL}: {exc}"
            )
        count = len(list(models.data))
        return ProviderHealth(
            available=True, detail=f"FLM at {settings.FLM_BASE_URL} advertises {count} model(s)"
        )
