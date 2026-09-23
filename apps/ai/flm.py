"""FastFlowLM implementation: docs/ai-provider.md section 3.

FLM speaks the OpenAI wire format, so the openai package is the client. Only the
base URL, the placeholder key and the model names distinguish it from any other
OpenAI-compatible server. Default for development, testing and demonstration.
"""

from typing import Callable

import openai
from django.conf import settings

from apps.ai import _openai_compat
from apps.ai.base import EmbeddingResult, Passage, ProviderHealth, ProviderUnavailable, StatementList
from apps.ai.generation import (
    GENERATION_MAX_TOKENS,
    GENERATION_TIMEOUT_SECONDS,
    GenerationAttempt,
    run_generation_attempts,
)
from apps.ai.prompting import build_generation_messages


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

    def generate_statements(
        self,
        question: str,
        passages: list[Passage],
        *,
        on_attempt: Callable[[GenerationAttempt], None] | None = None,
    ) -> StatementList:
        """Grounded generation (FR-12): statements drawn only from ``passages``.

        The prompt is built from the passages and the question and nothing else
        (apps/ai/prompting.py). The retry policy, the schema check and the 503 after
        MAXIMUM_GENERATION_ATTEMPTS are in apps/ai/generation.py, shared with the
        Anthropic provider so the two cannot drift.

        ``on_attempt`` is the diagnostic hook scripts/citation_harness.py measures
        with; application code leaves it unset. Verification of the returned
        identifiers is NOT done here — it is application code over set membership
        (invariant 5), and it belongs to the caller.
        """
        if not passages:
            # Nothing to ground an answer in. The pipeline cannot reach this — FR-12's
            # no-answer path A returns before generation when nothing clears the
            # threshold — so an empty list here is a caller's bug, not an outage, and it
            # must not be spent as an NPU call that can only invite invention.
            raise ValueError("generate_statements() needs at least one passage")
        messages = build_generation_messages(question, passages)
        return run_generation_attempts(
            call_once=lambda: self._chat_once(messages),
            label=f"FLM at {settings.FLM_BASE_URL}",
            on_attempt=on_attempt,
        )

    def _chat_once(self, messages: list[dict]) -> str:
        """One chat completion. Returns the raw reply text.

        Raises ProviderUnavailable for a retryable transport failure, and lets a 4xx
        surface unchanged — the same division ``_openai_compat.embed`` makes, for the
        same reason: a misconfiguration is not an outage and repeating it three times
        produces the same answer three times.
        """
        try:
            response = self._client.chat.completions.create(
                model=settings.FLM_CHAT_MODEL,
                messages=messages,
                temperature=0.0,  # the same reply for the same passages, run to run
                max_tokens=GENERATION_MAX_TOKENS,
                stream=False,
                timeout=GENERATION_TIMEOUT_SECONDS,
            )
        except (openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise ProviderUnavailable(f"{settings.FLM_BASE_URL} unreachable: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(
                    f"{settings.FLM_BASE_URL} returned HTTP {exc.status_code}: {exc}"
                ) from exc
            raise  # 4xx is a configuration or request error, not an outage
        except ValueError as exc:
            # An HTTP 200 carrying an error body instead of a completion: how FLM
            # reports an NPU fault (see the embed path's test for the observed case).
            raise ProviderUnavailable(f"{settings.FLM_BASE_URL} returned no completion ({exc})") from exc
        choices = response.choices or []
        if not choices:
            # No reply at all. Returned as an empty string so the schema check treats it
            # as a failed attempt, which is what it is.
            return ""
        return choices[0].message.content or ""

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
