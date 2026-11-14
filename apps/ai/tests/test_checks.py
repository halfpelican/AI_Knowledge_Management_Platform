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
    # A database keeps its provider (D-131): the hint no longer sends anyone to re-index.
    assert "D-131" in error.hint and "reindex" not in error.hint


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


# --- The width follows the provider, and a database keeps it (D-131) --------------------------------

from django.conf import settings  # noqa: E402
from django.db import OperationalError, connection  # noqa: E402

import apps.ai.checks  # noqa: E402
from apps.ai.checks import check_database_provider, check_embedding_dimension_setting  # noqa: E402
from apps.core.constants import EMBEDDING_DIMENSION_BY_PROVIDER  # noqa: E402
from apps.core.vector_columns import NoSuchColumn  # noqa: E402


def test_the_setting_check_is_registered_under_the_ai_tag():
    assert check_embedding_dimension_setting in registry.registered_checks
    assert "ai" in check_embedding_dimension_setting.tags


@pytest.mark.parametrize("provider", sorted(EMBEDDING_DIMENSION_BY_PROVIDER))
def test_a_width_that_agrees_with_the_provider_passes(provider):
    with override_settings(AI_PROVIDER=provider, EMBEDDING_DIMENSION=EMBEDDING_DIMENSION_BY_PROVIDER[provider]):
        assert check_embedding_dimension_setting(None) == []


@pytest.mark.parametrize("provider, width", [("anthropic", 768), ("flm", 1024)])
def test_a_width_that_disagrees_with_the_provider_is_an_error(provider, width):
    with override_settings(AI_PROVIDER=provider, EMBEDDING_DIMENSION=width):
        messages = check_embedding_dimension_setting(None)

    assert [message.id for message in messages] == ["ai.E004"]
    assert messages[0].level == checks.ERROR
    assert f"EMBEDDING_DIMENSION is {width}" in messages[0].msg
    assert f"embeds at {EMBEDDING_DIMENSION_BY_PROVIDER[provider]}" in messages[0].msg
    assert messages[0].hint == "Remove EMBEDDING_DIMENSION from .env."


def test_an_unknown_provider_is_left_to_ai_e002():
    with override_settings(AI_PROVIDER="bedrock", EMBEDDING_DIMENSION=5):
        assert check_embedding_dimension_setting(None) == []


def test_the_database_check_has_a_tag_of_its_own():
    """Not "ai": the suite runs `check --tag ai` without a database, and this check reads one."""
    assert check_database_provider in registry.registered_checks
    assert "embedding" in check_database_provider.tags and "ai" not in check_database_provider.tags


@pytest.mark.django_db
def test_a_database_of_this_providers_width_passes():
    assert check_database_provider(None) == []


@pytest.mark.django_db
def test_a_database_set_up_for_another_width_is_an_error_naming_both_columns():
    built = settings.EMBEDDING_DIMENSION
    with override_settings(EMBEDDING_DIMENSION=built + 256):
        messages = check_database_provider(None)

    assert [message.id for message in messages] == ["ai.E005"]
    error = messages[0]
    assert error.level == checks.ERROR
    assert f"content_chunks.embedding is vector({built})" in error.msg
    assert f"knowledge_gaps.embedding is vector({built})" in error.msg
    assert f"embeds at {built + 256}" in error.msg
    assert "D-131" in error.hint and "set up a new one" in error.hint


@pytest.mark.django_db
def test_a_gap_column_left_at_another_width_is_an_error_naming_it_alone():
    """kmp_anthropic's case (D-117's note of 12 November 2026): the chunks' column at the provider's
    width, FR-19's gap column still at another. Postgres DDL is transactional, so the column is
    back at EMBEDDING_DIMENSION when the test's transaction rolls back."""
    other = settings.EMBEDDING_DIMENSION - 256
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE knowledge_gaps ALTER COLUMN embedding TYPE vector({other})")

    messages = check_database_provider(None)

    assert [message.id for message in messages] == ["ai.E005"]
    assert f"knowledge_gaps.embedding is vector({other})" in messages[0].msg
    assert "content_chunks" not in messages[0].msg


@pytest.mark.django_db
def test_an_unsized_gap_column_is_an_error_too():
    """pgvector reports an unsized column's modifier as -1, which is no width at all."""
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE knowledge_gaps ALTER COLUMN embedding TYPE vector")

    messages = check_database_provider(None)

    assert [message.id for message in messages] == ["ai.E005"]
    assert "knowledge_gaps.embedding is vector," in messages[0].msg


@pytest.mark.django_db
def test_a_table_not_created_yet_is_passed_over(monkeypatch):
    def missing(model, field_name="embedding"):
        raise NoSuchColumn(model._meta.db_table)

    monkeypatch.setattr(apps.ai.checks, "stored_width", missing)
    with override_settings(EMBEDDING_DIMENSION=settings.EMBEDDING_DIMENSION + 256):
        assert check_database_provider(None) == []


def test_a_database_that_cannot_be_read_is_passed_over(monkeypatch):
    def unreadable(model, field_name="embedding"):
        raise OperationalError("could not connect to server")

    monkeypatch.setattr(apps.ai.checks, "stored_width", unreadable)
    assert check_database_provider(None) == []


def _chunk(document, model_name):
    from apps.core.constants import EMPLOYEE_ROLE_NAME, SOURCE_TYPES
    from apps.documents.models import ContentChunk

    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0], source_id=document.id, chunk_index=ContentChunk.objects.count(),
        chunk_text="text", embedding=[0.0] * settings.EMBEDDING_DIMENSION, embedding_model=model_name,
        embedding_dimension=settings.EMBEDDING_DIMENSION, visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )


def _gap(model_name):
    from django.utils import timezone

    from apps.retrieval.models import KnowledgeGap

    now = timezone.now()
    return KnowledgeGap.objects.create(
        subject="Is there a gym on site?", occurrence_count=1, first_seen_at=now, last_seen_at=now,
        embedding=[0.0] * settings.EMBEDDING_DIMENSION if model_name else None, embedding_model=model_name,
    )


@pytest.mark.django_db
def test_rows_of_another_model_are_a_warning_naming_them(document):
    _chunk(document, "configured-model")
    _chunk(document, "an-older-model")
    _gap("another-model")

    with override_settings(AI_PROVIDER="anthropic", VOYAGE_MODEL="configured-model"):
        messages = check_database_provider(None)

    assert [message.id for message in messages] == ["ai.W003"]
    warning = messages[0]
    assert warning.level == checks.WARNING
    assert "'configured-model'" in warning.msg
    assert "1 chunk(s) by an-older-model" in warning.msg
    assert "1 gap entr(ies) by another-model" in warning.msg
    assert "D-131" in warning.hint


@pytest.mark.django_db
def test_rows_of_the_configured_model_are_silent(document):
    _chunk(document, "configured-model")
    _gap("configured-model")
    _gap("")  # an entry with no vector records no model

    with override_settings(AI_PROVIDER="anthropic", VOYAGE_MODEL="configured-model"):
        assert check_database_provider(None) == []


@pytest.mark.django_db
def test_rows_are_compared_with_the_providers_own_model_name(document):
    """Under flm the configured name is FLM_EMBED_MODEL, not VOYAGE_MODEL (apps/ai/prefixes.py)."""
    _chunk(document, "embed-gemma")
    # EMBEDDING_DIMENSION stays the width this test database was built at, so only the names are compared.
    with override_settings(AI_PROVIDER="flm", FLM_EMBED_MODEL="embed-gemma", VOYAGE_MODEL="voyage-4",
                           EMBEDDING_DIMENSION=settings.EMBEDDING_DIMENSION):
        assert check_database_provider(None) == []


@pytest.mark.django_db
def test_manage_py_check_refuses_a_database_set_up_for_another_width():
    with override_settings(EMBEDDING_DIMENSION=settings.EMBEDDING_DIMENSION + 256), pytest.raises(
        SystemCheckError, match="ai.E005"
    ):
        call_command("check", "--tag", "embedding", stdout=io.StringIO(), stderr=io.StringIO())
