"""Read-only: the state of kmp_fr12_declines_20261111 before the first draw (11 November 2026).

Counts only. It writes nothing, calls no AI provider, and prints no credential or URL. Run from the
repository root with the worktree's .env naming that database::

    .venv\\Scripts\\python.exe corpus\\objective-06\\runs\\2026-11-11-anthropic-draws\\pre-measurement-asks\\setup\\state_check.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]  # corpus/objective-06/runs/<run>/<half>/setup/<this file>
sys.path.insert(0, str(REPOSITORY_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402

from apps.documents.models import ContentChunk, Document  # noqa: E402
from apps.meetings.models import Meeting  # noqa: E402
from apps.retrieval.models import (  # noqa: E402
    AnswerCitation,
    Conversation,
    KnowledgeGap,
    KnowledgeGapCycle,
    KnowledgeGapItem,
    QueryLog,
    SearchLog,
)

EXPECTED = "kmp_fr12_declines_20261111"


def main() -> int:
    database = str(settings.DATABASES["default"]["NAME"])
    print(f"database: {database}")
    if database != EXPECTED:
        print(f"REFUSED: not {EXPECTED}")
        return 2
    print(f"settings: AI_PROVIDER={settings.AI_PROVIDER}, VOYAGE_MODEL={settings.VOYAGE_MODEL}, "
          f"ANTHROPIC_MODEL={settings.ANTHROPIC_MODEL}, EMBEDDING_DIMENSION={settings.EMBEDDING_DIMENSION}")

    chunks = Counter(ContentChunk.objects.values_list("embedding_model", "embedding_dimension"))
    print(f"content chunks: {sum(chunks.values())}, by (embedding_model, embedding_dimension): "
          f"{dict(sorted(chunks.items()))}")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "WHERE c.relname = 'content_chunks' AND a.attname = 'embedding'"
        )
        print(f"content_chunks.embedding column: {cursor.fetchone()[0]}")
    print(f"chunks by source type: {dict(Counter(ContentChunk.objects.values_list('source_type', flat=True)))}")
    distinct = Counter(source_type for source_type, _ in
                       set(ContentChunk.objects.values_list("source_type", "source_id")))
    print(f"distinct sources with chunks: {dict(distinct)}")
    print(f"chunks by visible_to_roles: "
          f"{dict(Counter(tuple(sorted(r)) for r in ContentChunk.objects.values_list('visible_to_roles', flat=True)))}")
    print(f"documents: {Document.objects.count()}, by status: "
          f"{dict(Counter(Document.objects.values_list('status', flat=True)))}")
    print(f"meetings: {Meeting.objects.count()}, by status: "
          f"{dict(Counter(Meeting.objects.values_list('status', flat=True)))}")
    print(f"query logs: {QueryLog.objects.count()}, answer citations: {AnswerCitation.objects.count()}, "
          f"conversations: {Conversation.objects.count()}")
    print(f"search logs: {SearchLog.objects.count()}")
    print(f"knowledge gaps: {KnowledgeGap.objects.count()}, items: {KnowledgeGapItem.objects.count()}, "
          f"cycles: {KnowledgeGapCycle.objects.count()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
