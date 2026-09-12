"""Stage 1 item 8: no test can reach a live provider, by construction.

Two autouse layers in the root conftest.py:

1. apps.ai.get_ai_service is replaced with a StubAIService, so code that obtains
   the service the documented way never builds a real client.
2. Every provider endpoint is pointed at a closed loopback port and every key is
   blanked, so code that bypasses layer 1 is refused at once rather than quietly
   answered by a developer's running FLM server.

These tests assert both layers are in force and that layer 2 actually bites. The
selector's own behaviour (which class each AI_PROVIDER value yields, and how a
test opts out of the stub) is covered in test_selection.py and not repeated here.
"""

import os
import re
import time
from pathlib import Path

import pytest
from django.conf import settings
from django.test import override_settings

import apps.ai
from apps.ai import get_ai_service as real_get_ai_service  # bound before the stub is installed
from apps.ai.anthropic import AnthropicService
from apps.ai.base import ProviderUnavailable
from apps.ai.flm import FLMService
from apps.ai.testing import UNROUTABLE_PROVIDER_HOST, UNROUTABLE_PROVIDER_URL, StubAIService

# Windows actively refuses a closed loopback port after about 2 s (measured); Linux
# is quicker. The bound is loose on purpose: it turns a hang (the SDK's default
# timeout is minutes) into a failure, and measures nothing else. The three tests
# that really connect cost the suite roughly 6 s on Windows; that is the price of
# proving the port refuses rather than trusting that it does.
FAIL_FAST_SECONDS = 10

ROOT = Path(__file__).resolve().parents[3]
AI_TESTS = ROOT / "apps" / "ai" / "tests"  # may bind the real selector deliberately
MODULE_LEVEL_BINDING = re.compile(r"^from apps\.ai import\b[^\n]*\bget_ai_service\b", re.MULTILINE)


# --- Layer 1: the stub -------------------------------------------------------------


def test_get_ai_service_returns_the_stub_during_the_suite(stub_ai_service):
    service = apps.ai.get_ai_service()
    assert isinstance(service, StubAIService)
    assert service is stub_ai_service

    result = service.embed(["probe"])
    assert len(result.vectors) == 1
    assert len(result.vectors[0]) == settings.EMBEDDING_DIMENSION
    assert stub_ai_service.embed_calls == [["probe"]]


# --- Layer 2: the endpoints ---------------------------------------------------------


def test_every_provider_endpoint_is_unroutable_and_every_key_is_blank():
    assert settings.FLM_BASE_URL == UNROUTABLE_PROVIDER_URL
    assert settings.VOYAGE_BASE_URL == UNROUTABLE_PROVIDER_URL
    assert os.environ["ANTHROPIC_BASE_URL"] == UNROUTABLE_PROVIDER_HOST
    assert settings.ANTHROPIC_API_KEY == ""
    assert settings.VOYAGE_API_KEY == ""
    # Loopback and a closed port: refused at once, and nothing leaves the machine.
    assert UNROUTABLE_PROVIDER_URL.startswith("http://127.0.0.1:9/")


def test_a_real_flm_client_built_from_settings_is_refused_at_once():
    # This is where a test that bypasses the stub ends up: ProviderUnavailable
    # naming the closed port, not an answer from a running FLM.
    with override_settings(AI_PROVIDER="flm"):
        service = real_get_ai_service()
    assert isinstance(service, FLMService)
    assert str(service._client.base_url).rstrip("/") == UNROUTABLE_PROVIDER_URL

    started = time.monotonic()
    with pytest.raises(ProviderUnavailable, match=re.escape(UNROUTABLE_PROVIDER_URL)):
        service.embed(["probe"])
    assert time.monotonic() - started < FAIL_FAST_SECONDS


def test_a_real_voyage_client_built_from_settings_is_refused_at_once():
    # A key is supplied so the blank-key short circuit does not apply: this proves
    # the VOYAGE_BASE_URL override alone is enough to stop the call.
    with override_settings(AI_PROVIDER="anthropic", VOYAGE_API_KEY="not-a-real-key"):
        service = real_get_ai_service()
        assert isinstance(service, AnthropicService)

        started = time.monotonic()
        with pytest.raises(ProviderUnavailable, match=re.escape(UNROUTABLE_PROVIDER_URL)):
            service.embed(["probe"])
        assert time.monotonic() - started < FAIL_FAST_SECONDS


def test_a_real_anthropic_sdk_client_honours_the_unroutable_base_url():
    # health() is the one Stage 1 path that builds the official anthropic SDK
    # client from settings. The SDK takes its base URL from ANTHROPIC_BASE_URL,
    # which the guard sets, so the probe is refused and health() reports it.
    with override_settings(ANTHROPIC_API_KEY="not-a-real-key"):
        service = AnthropicService()
        started = time.monotonic()
        health = service.health()
        assert time.monotonic() - started < FAIL_FAST_SECONDS

    assert health.available is False
    assert str(service._anthropic_client.base_url).rstrip("/") == UNROUTABLE_PROVIDER_HOST


# --- The footgun that would defeat layer 1 --------------------------------------------


def application_python_files():
    for folder in ("apps", "config"):
        for path in (ROOT / folder).rglob("*.py"):
            if AI_TESTS not in path.parents:
                yield path
    yield ROOT / "conftest.py"
    yield ROOT / "manage.py"


def test_no_module_level_binding_of_get_ai_service_outside_apps_ai_tests():
    # ``from apps.ai import get_ai_service`` at module level copies the real
    # function before conftest.py installs the stub, so every test touching that
    # module would build a real client. Call apps.ai.get_ai_service() instead, or
    # import inside the function as apps/ai/checks.py does.
    offenders = [
        str(path.relative_to(ROOT))
        for path in application_python_files()
        if MODULE_LEVEL_BINDING.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"get_ai_service bound at import time; the stub cannot apply: {offenders}"


def test_the_binding_guard_sees_the_codebase():
    scanned = list(application_python_files())
    assert ROOT / "apps" / "ai" / "checks.py" in scanned
    assert ROOT / "conftest.py" in scanned
    assert AI_TESTS / "test_selection.py" not in scanned
    # The pattern catches the shape it is meant to and ignores the sanctioned ones.
    assert MODULE_LEVEL_BINDING.search("from apps.ai import get_ai_service\n")
    assert MODULE_LEVEL_BINDING.search("from apps.ai import AIService, get_ai_service\n")
    assert not MODULE_LEVEL_BINDING.search("    from apps.ai import get_ai_service\n")
    assert not MODULE_LEVEL_BINDING.search("import apps.ai\n")
