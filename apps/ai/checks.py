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
