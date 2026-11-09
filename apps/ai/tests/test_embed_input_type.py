"""D-116: every AIService implementation declares embed()'s ``input_type``.

apps/ai/base.py says a contract and its implementations differing by a parameter is
the defect this project keeps finding. So the parameter is checked on each
implementation here, rather than left to whichever caller happens to pass it. The
suite's stub is included because every test reaches the callers through it.
"""

import inspect

import pytest

from apps.ai.anthropic import AnthropicService
from apps.ai.base import AIService
from apps.ai.flm import FLMService
from apps.ai.testing import StubAIService


@pytest.mark.parametrize("implementation", [AIService, FLMService, AnthropicService, StubAIService])
def test_embed_takes_input_type_as_a_keyword_that_defaults_to_none(implementation):
    parameter = inspect.signature(implementation.embed).parameters["input_type"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None
