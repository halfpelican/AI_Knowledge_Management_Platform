"""FastFlowLM implementation: docs/ai-provider.md section 3.

FLM speaks the OpenAI wire format, so the openai package is the client. Only the
base URL, the placeholder key and the model names distinguish it from any other
OpenAI-compatible server. Default for development, testing and demonstration.
"""

from typing import Callable

import openai
from django.conf import settings

from apps.ai import _openai_compat
from apps.ai.base import (
    EmbeddingResult,
    FollowupRewrite,
    Passage,
    ProviderHealth,
    ProviderUnavailable,
    StatementList,
)
from apps.ai.generation import (
    GENERATION_MAX_TOKENS,
    GENERATION_TIMEOUT_SECONDS,
    ChatReply,
    GenerationAttempt,
    run_generation_attempts,
)
from apps.ai.prompting import build_generation_messages
from apps.ai.rewrite import (
    REWRITE_MAX_TOKENS,
    REWRITE_TIMEOUT_SECONDS,
    build_rewrite_messages,
    run_rewrite_attempt,
)


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
        # One value for the request and for the attempt log's record of it.
        max_tokens = GENERATION_MAX_TOKENS
        # The messages are built per attempt, because each attempt's prompt states the
        # statement cap the loop asks it for (apps/ai/generation.py).
        return run_generation_attempts(
            call_once=lambda max_statements: self._chat_once(
                build_generation_messages(question, passages, max_statements=max_statements),
                max_tokens=max_tokens,
            ),
            label=f"FLM at {settings.FLM_BASE_URL}",
            on_attempt=on_attempt,
            max_tokens=max_tokens,
        )

    def rewrite_followup(self, question: str, prior_questions: list[str]) -> FollowupRewrite:
        """FR-13's standalone rewrite, for retrieval only. ONE attempt, no retry.

        The prompt, the one-field schema, the length ceiling and the single-attempt
        policy are apps/ai/rewrite.py's, shared with the Anthropic provider. A transport
        failure or a non-conforming reply raises — ProviderUnavailable or
        RewriteViolation — and the CALLER falls back to the composed join
        (apps/retrieval/pipeline.py): the ask never fails because the rewrite did.
        """
        return run_rewrite_attempt(
            call_once=lambda: self._chat_once(
                build_rewrite_messages(question, prior_questions),
                max_tokens=REWRITE_MAX_TOKENS,
                timeout=REWRITE_TIMEOUT_SECONDS,
            ),
            label=f"FLM at {settings.FLM_BASE_URL}",
        )

    def _chat_once(
        self, messages: list[dict], *, max_tokens: int, timeout: float = GENERATION_TIMEOUT_SECONDS
    ) -> ChatReply:
        """One chat completion. Returns the reply text and what FLM reported about it.

        Raises ProviderUnavailable for a retryable transport failure, and lets a 4xx
        surface unchanged — the same division ``_openai_compat.embed`` makes, for the
        same reason: a misconfiguration is not an outage and repeating it three times
        produces the same answer three times.

        ``finish_reason`` and the usage counts are read for the attempt log only
        (apps/ai/attempt_log.py), and None where FLM leaves them out. FLM v0.9.39 was seen
        on 7 November 2026 to answer "stop" for a reply cut off at ``max_tokens``, so the
        completion-token count is recorded beside it.

        ``timeout`` defaults to the generation call's; the rewrite passes its own,
        tighter one (apps/ai/rewrite.py says why).
        """
        try:
            response = self._client.chat.completions.create(
                model=settings.FLM_CHAT_MODEL,
                messages=messages,
                temperature=0.0,  # the same reply for the same passages, run to run
                max_tokens=max_tokens,
                stream=False,
                timeout=timeout,
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
        usage = getattr(response, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        choices = response.choices or []
        if not choices:
            # No reply at all. Returned as an empty string so the schema check treats it
            # as a failed attempt, which is what it is.
            return ChatReply(
                text="", completion_tokens=completion_tokens, prompt_tokens=prompt_tokens
            )
        return ChatReply(
            text=choices[0].message.content or "",
            finish_reason=getattr(choices[0], "finish_reason", None),
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
        )

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
