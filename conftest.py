"""Shared pytest fixtures for the whole suite.

No test ever reaches a live AI provider (docs/ai-provider.md section 6). The
autouse fixture below replaces apps.ai.get_ai_service with a StubAIService for
every test. Code under test must obtain the service through that function, looked
up on the apps.ai module at call time, for the stub to apply.
"""

import pytest

import apps.ai
from apps.ai.testing import StubAIService


@pytest.fixture(autouse=True)
def stub_ai_service(monkeypatch):
    stub = StubAIService()
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: stub)
    return stub
