"""Claude + Voyage implementation: the documented production configuration.

Generation goes to Claude through the official anthropic SDK, built at Stage 4 item 5
and sharing the prompt (apps/ai/prompting.py), the schema (apps/ai/schema.py) and the
retry policy (apps/ai/generation.py) with the FLM provider — so "provider independence"
means the same prompt answered by a different model, not a second implementation.
Embeddings go to Voyage, whose /embeddings endpoint speaks the OpenAI wire format,
through the same openai client shape FLM uses (docs/ai-provider.md section 3).
Kept working so the proposal's section 9.2 remains true; not used day to day, and never
called live in the suite (D-35: no external AI spend).
"""

from typing import Callable

# This module is apps/ai/anthropic.py. Python 3 imports are absolute, so
# ``import anthropic`` here resolves to the installed SDK and never to this file;
# the alias only keeps the two visibly distinct for anyone reading the code.
import anthropic as anthropic_sdk
from django.conf import settings

from apps.ai import _openai_compat
from apps.ai.base import EmbeddingResult, Passage, ProviderHealth, ProviderUnavailable, StatementList
from apps.ai.generation import (
    GENERATION_MAX_TOKENS,
    GENERATION_TIMEOUT_SECONDS,
    ChatReply,
    GenerationAttempt,
    run_generation_attempts,
)
from apps.ai.prompting import SYSTEM_PROMPT, build_user_prompt


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

    def generate_statements(
        self,
        question: str,
        passages: list[Passage],
        *,
        on_attempt: Callable[[GenerationAttempt], None] | None = None,
    ) -> StatementList:
        """Grounded generation through Claude (FR-12), the documented production path.

        The same prompt, the same schema and the same retry loop as the FLM provider:
        SYSTEM_PROMPT and build_user_prompt come from apps/ai/prompting.py, the loop and
        the 503 from apps/ai/generation.py. Only the transport differs, which is what
        keeps the proposal's section 9.2 claim of provider independence true.

        Not exercised against the live API, by decision: D-35 rules out external AI
        spend, so this path is tested against mocked SDK responses exactly as the Voyage
        embedding path is. That is a real limitation and it is stated rather than
        implied — the wire shape is taken from the SDK's documented types, and the first
        live call will be the first live call.
        """
        if not passages:
            raise ValueError("generate_statements() needs at least one passage")
        user_prompt = build_user_prompt(question, passages)
        # One value for the request and for the attempt log's record of it.
        max_tokens = GENERATION_MAX_TOKENS
        return run_generation_attempts(
            call_once=lambda: self._claude_once(user_prompt, max_tokens=max_tokens),
            label=f"Claude ({settings.ANTHROPIC_MODEL})",
            on_attempt=on_attempt,
            max_tokens=max_tokens,
        )

    def _claude_once(self, user_prompt: str, *, max_tokens: int) -> ChatReply:
        """One messages.create call. Returns the reply text and what Claude reported about it.

        The system prompt goes in the SDK's own ``system`` parameter rather than as a
        message, which is this API's shape; the string is the one FLM receives as its
        system message. Transport failures become ProviderUnavailable and 4xx surfaces
        unchanged, the same division the embed path makes. ``stop_reason`` and the usage
        counts are read for the attempt log only (apps/ai/attempt_log.py), and None where
        the reply leaves them out.
        """
        try:
            response = self._anthropic().messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                temperature=0.0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                timeout=GENERATION_TIMEOUT_SECONDS,
            )
        except (anthropic_sdk.APITimeoutError, anthropic_sdk.APIConnectionError) as exc:
            raise ProviderUnavailable(f"Anthropic API unreachable: {exc}") from exc
        except anthropic_sdk.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(
                    f"Anthropic API returned HTTP {exc.status_code}: {exc}"
                ) from exc
            raise  # 4xx, including a 429, is not an outage and consumes no retries
        # Claude replies in content blocks; only the text ones carry the JSON object.
        usage = getattr(response, "usage", None)
        return ChatReply(
            text="".join(
                block.text
                for block in (response.content or [])
                if getattr(block, "type", "") == "text"
            ),
            finish_reason=getattr(response, "stop_reason", None),
            completion_tokens=getattr(usage, "output_tokens", None),
            prompt_tokens=getattr(usage, "input_tokens", None),
        )

    def health(self) -> ProviderHealth:
        # A report, not a call path: this never raises.
        if not settings.ANTHROPIC_API_KEY:
            return ProviderHealth(available=False, detail="ANTHROPIC_API_KEY is not set")
        try:
            self._anthropic().models.list(limit=1)
        except Exception as exc:  # noqa: BLE001 - any failure means "not available"
            return ProviderHealth(available=False, detail=f"Anthropic API unreachable: {exc}")
        return ProviderHealth(available=True, detail="Anthropic API reachable")
