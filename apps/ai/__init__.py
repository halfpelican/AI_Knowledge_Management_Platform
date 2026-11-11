"""AI provider selection: docs/ai-provider.md section 2.

Call get_ai_service(), looked up on this module at call time (the test suite
replaces it with a stub). Never instantiate an implementation directly outside this
package, and never import openai or anthropic outside it (CLAUDE.md section 4).
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.ai.base import AIService


def get_ai_service() -> AIService:
    provider = settings.AI_PROVIDER
    if provider == "flm":
        from apps.ai.flm import FLMService

        return FLMService()
    if provider == "anthropic":
        from apps.ai.anthropic import AnthropicService

        return AnthropicService()
    raise ImproperlyConfigured(f"Unknown AI_PROVIDER: {provider!r} (expected 'flm' or 'anthropic')")


def transcription_enabled() -> bool:
    """Whether recording transcription is switched on here (D-123). Calls nothing.

    TRANSCRIPTION_PROVIDER, not AI_PROVIDER, decides it, because only FLM has speech-to-text. A
    route asks this before reading a segment, so a server with transcription off refuses at
    once; the transcription itself still goes through ``get_ai_service().transcribe()``.
    ImproperlyConfigured for a value that is neither ``none`` nor ``flm``.
    """
    from apps.ai.transcription import is_enabled

    return is_enabled()
