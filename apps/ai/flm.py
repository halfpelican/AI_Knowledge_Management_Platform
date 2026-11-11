"""FastFlowLM implementation: docs/ai-provider.md section 3.

FLM speaks the OpenAI wire format, so the openai package is the client. Only the
base URL, the placeholder key and the model names distinguish it from any other
OpenAI-compatible server. Default for development, testing and demonstration.
"""

from typing import Callable

import openai
from django.conf import settings

from apps.ai import _openai_compat, transcription
from apps.ai._status import error_for_status
from apps.ai.base import (
    DocumentClassification,
    EmbeddingResult,
    InputType,
    Passage,
    ProviderHealth,
    ProviderUnavailable,
    StatementList,
    TagScheme,
    Transcription,
)
from apps.ai.classification import (
    CLASSIFICATION_MAX_TOKENS,
    CLASSIFICATION_TIMEOUT_SECONDS,
    build_classification_messages,
    classification_input,
    run_classification_attempts,
)
from apps.ai.generation import (
    GENERATION_MAX_TOKENS,
    GENERATION_TIMEOUT_SECONDS,
    ChatReply,
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

    def embed(self, texts: list[str], *, input_type: InputType | None = None) -> EmbeddingResult:
        # input_type is accepted and not sent (D-116). EmbeddingGemma learns whether a
        # text is a question or a passage from the task prefix the caller has already
        # put in the text (apps/ai/prefixes.py). FLM's /embeddings has no such field.
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

    def _chat_once(
        self, messages: list[dict], *, max_tokens: int, timeout: int = GENERATION_TIMEOUT_SECONDS
    ) -> ChatReply:
        """One chat completion. Returns the reply text and what FLM reported about it.

        ``timeout`` is generation's unless the caller passes its own: classification passes
        CLASSIFICATION_TIMEOUT_SECONDS (FR-10). Every FLM call carries one.

        Raises ProviderUnavailable for any failed call, as ``_openai_compat.embed`` does
        (apps/ai/_status.py, D-118). A transport failure, a 5xx or a 429 is retried by the
        caller. Any other 4xx is ProviderRefused, which the caller does not retry. A 4xx
        is logged first with its status and body, and surfaced as itself would have
        reached the user as a 500, not the NFR-19 503. Classification calls come through
        here too, so the same holds for them.

        ``finish_reason`` and the usage counts are read for the attempt log only
        (apps/ai/attempt_log.py), and None where FLM leaves them out. FLM v0.9.39 was seen
        on 7 November 2026 to answer "stop" for a reply cut off at ``max_tokens``, so the
        completion-token count is recorded beside it.
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
            raise error_for_status(settings.FLM_BASE_URL, exc.status_code, str(exc)) from exc  # D-118
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

    def classify_document(
        self, title: str, text: str, scheme: TagScheme
    ) -> DocumentClassification:
        """FR-10 classification through FLM (D-104): one structured call, the shared loop.

        The prompt, the schema, the input cut and the retry policy are all in
        apps/ai/classification.py, shared with the Anthropic provider so the two cannot
        drift; this method supplies the one call (``_chat_once``, with its error mapping)
        and names the model that answered. Whether the suggestions are applied is decided
        in apps/documents (D-105), not here.
        """
        body, truncated = classification_input(text)
        messages = build_classification_messages(title, body, scheme)
        # One value for the request and for the attempt log's record of it.
        max_tokens = CLASSIFICATION_MAX_TOKENS
        return run_classification_attempts(
            lambda: self._chat_once(
                messages, max_tokens=max_tokens, timeout=CLASSIFICATION_TIMEOUT_SECONDS
            ),
            scheme=scheme,
            label=f"FLM at {settings.FLM_BASE_URL}",
            model=settings.FLM_CHAT_MODEL,
            input_truncated=truncated,
            max_tokens=max_tokens,
        )

    def transcribe(self, audio: bytes, *, filename: str = "segment.wav") -> Transcription:
        """One recording segment's text, through Whisper on this FLM server (D-123).

        apps/ai/transcription.py holds the call and its attempt policy, shared with the Anthropic
        provider, which has no speech model of its own. TRANSCRIPTION_PROVIDER decides whether it
        runs at all; this provider's client already points at FLM_BASE_URL, so it is reused.
        """
        return transcription.transcribe(lambda: self._client, audio, filename=filename)

    def transcription_health(self) -> ProviderHealth:
        return transcription.health(lambda: self._client)

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
