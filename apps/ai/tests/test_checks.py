"""The ai.* startup check: warns when the provider is down, refuses to boot on a mismatch."""

import io

import pytest
from django.core import checks
from django.core.checks.registry import registry
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import override_settings

import apps.ai
from apps.ai.base import ProviderUnavailable
from apps.ai.checks import PROBE_TEXT, check_ai_provider
from apps.ai.testing import StubAIService


def install(monkeypatch, service):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)


def test_check_is_registered_under_the_ai_tag():
    assert check_ai_provider in registry.registered_checks
    assert "ai" in check_ai_provider.tags


def test_matching_dimension_passes_and_probes_once(stub_ai_service):
    assert check_ai_provider(None) == []
    assert stub_ai_service.embed_calls == [[PROBE_TEXT]]


def test_dimension_mismatch_is_an_error(monkeypatch):
    install(monkeypatch, StubAIService(dimension=512))
    with override_settings(EMBEDDING_DIMENSION=768):
        messages = check_ai_provider(None)

    assert [message.id for message in messages] == ["ai.E001"]
    error = messages[0]
    assert error.level == checks.ERROR
    assert "512" in error.msg
    assert "768" in error.msg
    assert "manage.py reindex" in error.hint


def test_unavailable_provider_is_a_warning_and_skips_the_probe(monkeypatch):
    stub = StubAIService(available=False, detail="connection refused")
    install(monkeypatch, stub)

    messages = check_ai_provider(None)

    assert [message.id for message in messages] == ["ai.W001"]
    assert messages[0].level == checks.WARNING
    assert "503" in messages[0].msg
    assert "connection refused" in messages[0].msg
    assert stub.embed_calls == []


def test_probe_failure_is_a_warning(monkeypatch):
    class HealthyButCannotEmbed(StubAIService):
        def embed(self, texts, *, input_type=None):
            raise ProviderUnavailable("embeddings endpoint down")

    install(monkeypatch, HealthyButCannotEmbed())
    messages = check_ai_provider(None)
    assert [message.id for message in messages] == ["ai.W001"]
    assert "embeddings endpoint down" in messages[0].msg


def test_unknown_provider_is_an_error(monkeypatch):
    def misconfigured():
        raise ImproperlyConfigured("Unknown AI_PROVIDER: 'bedrock'")

    monkeypatch.setattr(apps.ai, "get_ai_service", misconfigured)
    messages = check_ai_provider(None)
    assert [message.id for message in messages] == ["ai.E002"]
    assert messages[0].level == checks.ERROR
    assert "bedrock" in messages[0].msg


def test_manage_py_check_refuses_to_boot_on_a_mismatch(monkeypatch):
    install(monkeypatch, StubAIService(dimension=512))
    with override_settings(EMBEDDING_DIMENSION=768), pytest.raises(SystemCheckError, match="ai.E001"):
        call_command("check", "--tag", "ai", stdout=io.StringIO(), stderr=io.StringIO())


def test_manage_py_check_continues_past_an_unreachable_provider(monkeypatch):
    install(monkeypatch, StubAIService(available=False, detail="down"))
    stderr = io.StringIO()
    call_command("check", "--tag", "ai", stdout=io.StringIO(), stderr=stderr)
    assert "ai.W001" in stderr.getvalue()


def test_manage_py_check_is_silent_with_a_matching_provider(stub_ai_service):
    stdout, stderr = io.StringIO(), io.StringIO()
    call_command("check", "--tag", "ai", stdout=stdout, stderr=stderr)
    assert "ai." not in stdout.getvalue()
    assert stderr.getvalue() == ""


# --- Recording transcription's setting (D-123) ---------------------------------------------

from apps.ai.checks import check_transcription_provider  # noqa: E402


def test_the_transcription_check_is_registered_under_the_ai_tag():
    assert check_transcription_provider in registry.registered_checks
    assert "ai" in check_transcription_provider.tags


def test_transcription_off_is_silent_and_calls_nothing(monkeypatch):
    stub = StubAIService(transcription_available=False)
    install(monkeypatch, stub)

    with override_settings(TRANSCRIPTION_PROVIDER="none"):
        assert check_transcription_provider(None) == []


def test_transcription_on_with_flm_answering_passes(stub_ai_service):
    with override_settings(TRANSCRIPTION_PROVIDER="flm"):
        assert check_transcription_provider(None) == []


def test_transcription_on_with_flm_silent_is_a_warning_naming_asr(monkeypatch):
    install(monkeypatch, StubAIService(transcription_available=False))

    with override_settings(TRANSCRIPTION_PROVIDER="flm"):
        messages = check_transcription_provider(None)

    assert [message.id for message in messages] == ["ai.W002"]
    assert messages[0].level == checks.WARNING
    assert "--asr 1" in messages[0].hint


def test_an_unknown_transcription_provider_is_an_error():
    with override_settings(TRANSCRIPTION_PROVIDER="whisper-cpu"):
        messages = check_transcription_provider(None)

    assert [message.id for message in messages] == ["ai.E003"]
    assert messages[0].level == checks.ERROR
    assert "'none' or 'flm'" in messages[0].hint


def test_an_unknown_ai_provider_is_left_to_its_own_check(monkeypatch):
    def unknown():
        raise ImproperlyConfigured("Unknown AI_PROVIDER: 'x'")

    monkeypatch.setattr(apps.ai, "get_ai_service", unknown)
    with override_settings(TRANSCRIPTION_PROVIDER="flm"):
        assert check_transcription_provider(None) == []
