"""get_ai_service() picks the implementation from AI_PROVIDER (docs/ai-provider.md section 2)."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

import apps.ai

# Bound here, at collection time, before the autouse fixture in conftest.py replaces
# the attribute on the apps.ai module for each test: this name is the real selector.
from apps.ai import get_ai_service
from apps.ai.anthropic import AnthropicService
from apps.ai.flm import FLMService


def test_flm_is_selected():
    with override_settings(AI_PROVIDER="flm"):
        assert isinstance(get_ai_service(), FLMService)


def test_anthropic_is_selected():
    with override_settings(AI_PROVIDER="anthropic"):
        assert isinstance(get_ai_service(), AnthropicService)


@pytest.mark.parametrize("value", ["bedrock", ""])
def test_unknown_provider_is_a_configuration_error(value):
    with override_settings(AI_PROVIDER=value), pytest.raises(ImproperlyConfigured, match="AI_PROVIDER"):
        get_ai_service()


def test_the_rest_of_the_suite_receives_the_stub(stub_ai_service):
    # Every other test goes through the module attribute and gets the stub.
    assert apps.ai.get_ai_service() is stub_ai_service
    assert stub_ai_service.health().available is True
