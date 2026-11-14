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
- An EMBEDDING_DIMENSION in .env that disagrees with AI_PROVIDER's width is an Error (ai.E004).
  The width follows the provider (D-131), so the line is only ever a way to get it wrong.

**The database the provider is used with** (``check_database_provider``, under its own
``embedding`` tag, D-131). A database keeps the provider it was set up with, and its vector columns
keep the width the first ``migrate`` gave them:

- A vector column of another width than EMBEDDING_DIMENSION is an Error (ai.E005): the database
  was set up for another provider, so the process refuses to use it with this one. It names each
  column that differs, the chunks' and FR-19's gap entries'.
- Rows embedded by another model than the configured one are a Warning (ai.W003). Retrieval
  leaves them out (risk R10); within one provider and one width, ``reindex`` rebuilds them.
- A table not created yet (a database before its first ``migrate``), or a database that cannot be
  read, is passed over: there is nothing of another provider in it to refuse, and the command that
  needs the database fails on its own.

It has a tag of its own so that ``check --tag ai``, which the suite runs without a database, does
not query one. Waitress runs no checks, so the serve steps run ``manage.py check`` first
(``docs/alpha-deployment.md``).

pytest never runs this check: the stub in conftest.py stands in for the provider
and test database creation skips system checks.
"""

from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError

from apps.ai.base import ProviderUnavailable
from apps.core.constants import EMBEDDING_DIMENSION_BY_PROVIDER
from apps.core.vector_columns import NoSuchColumn, describe_width, stored_width

PROBE_TEXT = "embedding dimension probe"
UNREACHABLE = "AI provider unreachable; the API will answer 503 until it is."
NEW_DATABASE_HINT = (
    "A database keeps the provider it was set up with (D-131). Point DATABASE_URL at a database "
    "set up for this provider, or set up a new one: create it, set AI_PROVIDER in .env, run "
    "migrate, and ingest the content again."
)
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
                    "EMBEDDING_DIMENSION follows AI_PROVIDER (D-131), so the embedding model "
                    "setting names a model of another width. Set it back to the provider's own "
                    f"model. {NEW_DATABASE_HINT}"
                ),
                id="ai.E001",
            )
        ]
    return []


@checks.register("ai")
def check_embedding_dimension_setting(app_configs, **kwargs):
    """ai.E004: an EMBEDDING_DIMENSION in .env that disagrees with AI_PROVIDER (D-131).

    An unknown provider is left to ai.E002, which check_ai_provider reports.
    """
    expected = EMBEDDING_DIMENSION_BY_PROVIDER.get(settings.AI_PROVIDER)
    if expected is None or settings.EMBEDDING_DIMENSION == expected:
        return []
    return [
        checks.Error(
            f"EMBEDDING_DIMENSION is {settings.EMBEDDING_DIMENSION}, but AI_PROVIDER="
            f"{settings.AI_PROVIDER!r} embeds at {expected}. The width follows the provider "
            f"(D-131).",
            hint="Remove EMBEDDING_DIMENSION from .env.",
            id="ai.E004",
        )
    ]


@checks.register("embedding")
def check_database_provider(app_configs, **kwargs):
    """ai.E005 and ai.W003: the connected database was set up for this provider (D-131)."""
    from apps.ai.prefixes import configured_embedding_model
    from apps.documents.models import ContentChunk
    from apps.retrieval.models import KnowledgeGap

    expected = settings.EMBEDDING_DIMENSION
    wrong_width = []
    try:
        for model in (ContentChunk, KnowledgeGap):
            try:
                width = stored_width(model)
            except NoSuchColumn:
                continue  # not migrated yet: nothing of another provider can be in it
            if width != expected:
                wrong_width.append(f"{model._meta.db_table}.embedding is {describe_width(width)}")
        if wrong_width:
            return [
                checks.Error(
                    f"This database was set up for another provider: {'; '.join(wrong_width)}, "
                    f"but AI_PROVIDER={settings.AI_PROVIDER!r} embeds at {expected}. The process "
                    f"will not use it with this provider.",
                    hint=NEW_DATABASE_HINT,
                    id="ai.E005",
                )
            ]
        configured = configured_embedding_model()
        others = {}
        for model, label in ((ContentChunk, "chunk(s)"), (KnowledgeGap, "gap entr(ies)")):
            rows = model.objects.exclude(embedding_model="").exclude(embedding_model=configured)
            count = rows.count()
            if count:
                names = sorted(set(rows.values_list("embedding_model", flat=True)))
                others[label] = (count, names)
    except DatabaseError:
        return []  # the database cannot be read: the command that needs it fails on its own
    if not others:
        return []
    described = "; ".join(f"{count} {label} by {', '.join(names)}" for label, (count, names) in others.items())
    return [
        checks.Warning(
            f"Rows embedded by another model than the configured {configured!r}: {described}. "
            f"Retrieval leaves them out (risk R10).",
            hint=(
                "Within this provider, at the same width, `manage.py reindex` rebuilds them with the "
                "configured model. A change of provider is not a re-index: a database keeps the "
                "provider it was set up with (D-131)."
            ),
            id="ai.W003",
        )
    ]
