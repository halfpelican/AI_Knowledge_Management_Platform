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
