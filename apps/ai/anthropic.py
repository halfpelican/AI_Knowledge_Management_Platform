"""Claude + Voyage implementation: the documented production configuration.

Generation goes to Claude through the official anthropic SDK, built at Stage 4 item 5
and sharing the prompt (apps/ai/prompting.py), the schema (apps/ai/schema.py) and the
retry policy (apps/ai/generation.py) with the FLM provider — so "provider independence"
means the same prompt answered by a different model, not a second implementation.
Embeddings go to Voyage, whose /embeddings endpoint speaks the OpenAI wire format,
through the same openai client shape FLM uses (docs/ai-provider.md section 3).
Dormant under D-35 until D-113 (10 November 2026) brought it into use: the Max plan's
monthly Claude API credits fund it. FLM stays implemented and available, and which
provider is the default is decided by measurement (D-113). The suite never calls it
live: tests inject fake clients, and conftest.py points every provider at an
unroutable address (docs/ai-provider.md section 6).
"""

from typing import Callable

# This module is apps/ai/anthropic.py. Python 3 imports are absolute, so
# ``import anthropic`` here resolves to the installed SDK and never to this file;
# the alias only keeps the two visibly distinct for anyone reading the code.
import anthropic as anthropic_sdk
from django.conf import settings

from apps.ai import _openai_compat
from apps.ai.base import (
    EmbeddingResult,
    InputType,
    Passage,
    ProviderHealth,
    ProviderUnavailable,
    StatementList,
)
from apps.ai.generation import (
    GENERATION_TIMEOUT_SECONDS,
    ChatReply,
    GenerationAttempt,
    run_generation_attempts,
)
from apps.ai.prompting import SYSTEM_PROMPT, build_user_prompt

# Claude's own token ceiling, not FLM's GENERATION_MAX_TOKENS (800). Current Claude
# models think before they answer and the thinking counts against max_tokens, so a
# ceiling sized for the JSON reply alone cuts the reply off mid-object: three schema
# failures, then the 503. It is a ceiling, not a target; the bill is for the tokens used.
CLAUDE_MAX_TOKENS = 16000
# How much the model thinks before answering. Low, because the task is extraction from
# passages already supplied, not open reasoning, and every thinking token is paid for.
# A starting value, not a measured one: tune it once the path has run live (D-115).
CLAUDE_EFFORT = "low"


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

    def embed(self, texts: list[str], *, input_type: InputType | None = None) -> EmbeddingResult:
        """Voyage embeddings, at voyage-4's default 1024 dimensions.

        ``input_type`` goes on the request (D-116). Voyage puts a different instruction
        in front of a question and a passage, and Voyage says retrieval improves with
        it. None sends nothing, which is Voyage's default. The texts arrive unprefixed:
        apps/ai/prefixes.py adds EmbeddingGemma's prefixes and nothing for Voyage.

        No ``output_dimension`` is sent, so the width is the model's default. The
        startup check and ``reindex`` compare it with EMBEDDING_DIMENSION, which must be
        1024 for this provider. A database first built at FLM's 768 needs
        ``reindex --resize-column`` (D-117).
        """
        if not texts:
            raise ValueError("embed() needs at least one text")
        return _openai_compat.embed(
            self._voyage(),
            settings.VOYAGE_MODEL,
            texts,
            endpoint=settings.VOYAGE_BASE_URL,
            extra_body={"input_type": input_type} if input_type else None,
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

        Not yet exercised against the live API: the path was dormant under D-35 until
        D-113 funded it. The suite tests it against mocked SDK responses, as it does the
        Voyage embedding path, and binds every request against the real SDK's signature.
        That is a real limitation and it is stated rather than implied: the wire shape is
        taken from the SDK's documented types, and the first live call will be the first
        live call.
        """
        if not passages:
            raise ValueError("generate_statements() needs at least one passage")
        # One value for the request and for the attempt log's record of it, and the
        # shared loop's ceiling-hit test reads it too (apps/ai/generation.py).
        max_tokens = CLAUDE_MAX_TOKENS
        # Built per attempt, because each attempt's prompt states the statement cap the
        # loop asks it for (apps/ai/generation.py).
        return run_generation_attempts(
            call_once=lambda max_statements: self._claude_once(
                build_user_prompt(question, passages, max_statements=max_statements),
                max_tokens=max_tokens,
            ),
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

        No ``temperature``, unlike FLM's call: the pinned SDK has no sampling parameters
        and current Claude models refuse them, so this path is not deterministic run to
        run. ``thinking`` is left at the model's default, because disabling it is a 400 on
        Sonnet 5.5 and Opus 5.5; ``effort`` is what keeps it short. ``output_tokens`` includes the
        thinking, so the attempt log's completion count does too.
        """
        try:
            response = self._anthropic().messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                output_config={"effort": CLAUDE_EFFORT},
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
