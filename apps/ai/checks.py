"""Startup check: the provider is reachable and embeds at EMBEDDING_DIMENSION.

Registered under the ``ai`` tag from AiConfig.ready(). Django runs system checks
before runserver, migrate, check and most other commands: an Error stops the
command, a Warning is printed and the command continues.

- A dimension mismatch is an Error (ai.E001). Vectors of the wrong length would
  corrupt retrieval silently, so the process refuses to boot (docs/ai-provider.md
  section 4, risk R10).
- An unreachable provider is a Warning (ai.W001). The API answers 503 until the
  provider returns (NFR-19); nothing else is affected.
- An unknown AI_PROVIDER is an Error (ai.E002).
- An unknown TRANSCRIPTION_PROVIDER is an Error (ai.E003), and transcription switched on with
  FLM not answering is a Warning (ai.W002): the recording option reports it unavailable until
  FLM returns, and nothing else is affected (D-123).

pytest never runs this check: the stub in conftest.py stands in for the provider
and test database creation skips system checks.
"""

from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured

from apps.ai.base import ProviderUnavailable

PROBE_TEXT = "embedding dimension probe"
UNREACHABLE = "AI provider unreachable; the API will answer 503 until it is."
REINDEX_COMMAND = "python manage.py reindex --provider <name>"
TRANSCRIPTION_UNREACHABLE = (
    "Recording transcription is on (TRANSCRIPTION_PROVIDER=flm) but FLM does not answer; the "
    "recording option will report it unavailable until it does."
)
TRANSCRIPTION_SERVE_HINT = "Start FLM with speech loaded: flm serve gemma3:4b --embed 1 --asr 1"


@checks.register("ai")
def check_transcription_provider(app_configs, **kwargs):
    """D-123's setting: a known value, and FLM answering when it is on."""
    # Imported at call time so the attribute the test suite patches is the one used.
    from apps.ai import get_ai_service, transcription_enabled

    try:
        enabled = transcription_enabled()
    except ImproperlyConfigured as exc:
        return [checks.Error(str(exc), hint="Set TRANSCRIPTION_PROVIDER to 'none' or 'flm'.", id="ai.E003")]
    if not enabled:
        return []
    try:
        health = get_ai_service().transcription_health()
    except ImproperlyConfigured:
        return []  # an unknown AI_PROVIDER is ai.E002's to report, once
    if not health.available:
        return [
            checks.Warning(
                f"{TRANSCRIPTION_UNREACHABLE} {health.detail}",
                hint=TRANSCRIPTION_SERVE_HINT,
                id="ai.W002",
            )
        ]
    return []


@checks.register("ai")
def check_ai_provider(app_configs, **kwargs):
    # Imported at call time so the attribute the test suite patches is the one used.
    from apps.ai import get_ai_service

    try:
        service = get_ai_service()
    except ImproperlyConfigured as exc:
        return [checks.Error(str(exc), hint="Set AI_PROVIDER to 'flm' or 'anthropic'.", id="ai.E002")]

    health = service.health()
    if not health.available:
        return [checks.Warning(f"{UNREACHABLE} {health.detail}", id="ai.W001")]

    try:
        result = service.embed([PROBE_TEXT])
    except ProviderUnavailable as exc:
        return [checks.Warning(f"{UNREACHABLE} {exc}", id="ai.W001")]

    expected = settings.EMBEDDING_DIMENSION
    if result.dimension != expected:
        return [
            checks.Error(
                f"Embedding model {result.model!r} returns {result.dimension}-dimensional "
                f"vectors but EMBEDDING_DIMENSION is {expected}. Vectors of different lengths "
                f"are not comparable, so the process will not start (risk R10).",
                hint=(
                    f"Set EMBEDDING_DIMENSION to {result.dimension} and re-index every chunk: "
                    f"{REINDEX_COMMAND}"
                ),
                id="ai.E001",
            )
        ]
    return []
