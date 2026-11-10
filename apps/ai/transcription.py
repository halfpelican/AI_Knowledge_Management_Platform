"""Recording transcription through FLM's Whisper, shared by both providers (D-123).

Only FLM has speech-to-text: Claude and Voyage have none. So ``AIService.transcribe`` is the same
call whichever ``AI_PROVIDER`` is set, and it lives here, once, as the classification prompt and
the generation loop do, so the two providers cannot drift. ``TRANSCRIPTION_PROVIDER`` selects it,
independently of ``AI_PROVIDER``:

- ``none``, the default: ``transcribe`` raises TranscriptionDisabled before any call, and
  ``health`` reports it unavailable. A host without the NPU (D-114) offers nothing that cannot
  work, and still ingests a transcript made elsewhere through FR-09.
- ``flm``: each segment goes to FLM's OpenAI-compatible ``/v1/audio/transcriptions`` at
  ``FLM_BASE_URL``, with ``FLM_ASR_MODEL`` (``whisper-v3:turbo``), through the ``openai`` client
  the FLM provider already uses. FLM must be started with ``--asr 1``.

**One segment per call, never a whole recording.** The page cuts a recording into WAV segments of
at most TRANSCRIPTION_SEGMENT_SECONDS and sends them one at a time, so each request is short: FLM
measured 0.24-0.31x real time on 6 November, and an hour in one request would hold a Waitress
thread for a quarter of an hour.

**Attempts** follow D-19 and D-118 exactly as the other operations do: a transport failure, a 5xx
or a 429 is a failed attempt and is retried, to MAXIMUM_TRANSCRIBE_ATTEMPTS (1 initial call + 2
retries), then ProviderUnavailable; any other 4xx is ProviderRefused (apps/ai/_status.py) and is
re-raised at once, because the same segment would be refused again. Each failed attempt is logged
through apps/ai/attempt_log.py under the step "transcription". No retry here can lose anything:
the page holds the segment and the draft (invariant 8).

**Silence is the caller's to refuse**, before this module is reached (apps/ingestion/audio.py):
Whisper invents text from a silent track, and a refused segment costs no NPU time.
"""

import time
from typing import Callable

import openai
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.ai import _openai_compat, attempt_log
from apps.ai._status import error_for_status
from apps.ai.base import (
    ProviderHealth,
    ProviderRefused,
    ProviderUnavailable,
    Transcription,
    TranscriptionDisabled,
)
from apps.core.constants import MAXIMUM_TRANSCRIBE_ATTEMPTS

# The two TRANSCRIPTION_PROVIDER values. "none" is the default (config/settings.py).
TRANSCRIPTION_OFF = "none"
TRANSCRIPTION_FLM = "flm"
TRANSCRIPTION_PROVIDERS = (TRANSCRIPTION_OFF, TRANSCRIPTION_FLM)

# How long one call may take. A segment is at most MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS (60 s) of
# audio, which FLM transcribes in about 15-19 s; the rest is room for a request queued behind
# another on the one NPU. Every call carries it, as every FLM chat call carries its own.
TRANSCRIPTION_TIMEOUT_SECONDS = 120
# The language Whisper is told the speech is in. The platform is English-only (multi-language
# work is out of scope, §1.9), and on a short or quiet segment Whisper's own guess can wander
# into another language.
TRANSCRIPTION_LANGUAGE = "en"
# The part type a segment is sent as.
WAV_CONTENT_TYPE = "audio/wav"
# How long the status check waits for FLM's model list. The page asks once, when the recording
# option is chosen, and a person is waiting on the answer; FLM answers its list at once when it
# is up.
HEALTH_TIMEOUT_SECONDS = 5

DISABLED_DETAIL = "Recording transcription is not enabled on this server (TRANSCRIPTION_PROVIDER=none)."


def transcription_provider() -> str:
    """The configured TRANSCRIPTION_PROVIDER, or ImproperlyConfigured for a value that is neither."""
    provider = settings.TRANSCRIPTION_PROVIDER
    if provider not in TRANSCRIPTION_PROVIDERS:
        raise ImproperlyConfigured(
            f"Unknown TRANSCRIPTION_PROVIDER: {provider!r} (expected 'none' or 'flm')"
        )
    return provider


def is_enabled() -> bool:
    """Whether recording transcription is switched on here. Reads the setting; calls nothing."""
    return transcription_provider() != TRANSCRIPTION_OFF


def build_client() -> openai.OpenAI:
    """An openai client for FLM, built from settings, with the SDK's own retries off."""
    return _openai_compat.build_client(settings.FLM_BASE_URL, settings.FLM_API_KEY)


def transcribe(
    get_client: Callable[[], openai.OpenAI], audio: bytes, *, filename: str = "segment.wav"
) -> Transcription:
    """One segment's text through FLM's Whisper, under the attempt policy above.

    ``get_client`` returns the FLM client, and is called only once transcription is known to be
    on, so a provider with no FLM client of its own builds none while the setting is ``none``.
    """
    if not is_enabled():
        raise TranscriptionDisabled(DISABLED_DETAIL)
    client = get_client()
    last_detail = "no attempt was made"
    for number in range(1, MAXIMUM_TRANSCRIBE_ATTEMPTS + 1):  # 1 initial call + 2 retries
        started = time.perf_counter()
        try:
            text = _transcribe_once(client, audio, filename)
        except ProviderUnavailable as exc:
            last_detail = str(exc)
            attempt_log.failed_attempt(
                "transcription", number, MAXIMUM_TRANSCRIBE_ATTEMPTS, time.perf_counter() - started,
                attempt_log.cause_of(exc), str(exc),
            )
            if isinstance(exc, ProviderRefused):
                raise  # D-118: the same segment would be refused again
            continue
        return Transcription(text=text, model=settings.FLM_ASR_MODEL)
    raise ProviderUnavailable(
        f"FLM at {settings.FLM_BASE_URL} gave no transcription after "
        f"{MAXIMUM_TRANSCRIBE_ATTEMPTS} attempts; the last failure was: {last_detail}"
    )


def _transcribe_once(client: openai.OpenAI, audio: bytes, filename: str) -> str:
    """One call. Raises ProviderUnavailable for any failed call, ProviderRefused for a refusal."""
    endpoint = settings.FLM_BASE_URL
    try:
        response = client.audio.transcriptions.create(
            model=settings.FLM_ASR_MODEL,
            file=(filename, audio, WAV_CONTENT_TYPE),
            language=TRANSCRIPTION_LANGUAGE,
            response_format="json",
            timeout=TRANSCRIPTION_TIMEOUT_SECONDS,
        )
    except (openai.APITimeoutError, openai.APIConnectionError) as exc:
        raise ProviderUnavailable(f"{endpoint} unreachable: {exc}") from exc
    except openai.APIStatusError as exc:
        raise error_for_status(endpoint, exc.status_code, str(exc)) from exc  # D-118
    except ValueError as exc:
        # An HTTP 200 whose body the SDK cannot read as a transcription, as FLM reports an NPU
        # fault on its other endpoints.
        raise ProviderUnavailable(f"{endpoint} returned no transcription ({exc})") from exc
    text = getattr(response, "text", None)
    if not isinstance(text, str):
        # A 200 carrying something other than a transcription, such as {"error": ...}. The SDK
        # does not validate the body, so the missing field is the only sign.
        raise ProviderUnavailable(f"{endpoint} returned no transcription text")
    return text.strip()


def health(get_client: Callable[[], openai.OpenAI]) -> ProviderHealth:
    """A report, not a call path: never raises.

    Unavailable when transcription is off or FLM does not answer its model list. Available means
    FLM answered, not that Whisper is loaded: FLM's ``/v1/models`` lists its chat catalogue and
    names neither the speech model nor the embedding model, so ``--asr 1`` cannot be seen from
    here. A server started without it fails the first segment instead. ``get_client`` is called
    only when transcription is on, as in ``transcribe``.
    """
    try:
        enabled = is_enabled()
    except ImproperlyConfigured as exc:
        return ProviderHealth(available=False, detail=str(exc))
    if not enabled:
        return ProviderHealth(available=False, detail=DISABLED_DETAIL)
    try:
        get_client().models.list(timeout=HEALTH_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - any failure means "not available"
        return ProviderHealth(
            available=False, detail=f"FLM unreachable at {settings.FLM_BASE_URL}: {exc}"
        )
    return ProviderHealth(
        available=True,
        detail=f"FLM at {settings.FLM_BASE_URL} answered; speech model {settings.FLM_ASR_MODEL}",
    )
