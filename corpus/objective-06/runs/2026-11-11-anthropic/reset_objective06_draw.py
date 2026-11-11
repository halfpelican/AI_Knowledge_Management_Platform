"""Objective 06's repeated draws (11 November 2026): export one draw's rows, then clear them for the next.

The user asked on 11 November for two more draws of Objective 06 on anthropic, on the voyage-4 rule
D-126 ships. D-110's note asks for repeated draws because Claude's generation is not deterministic.
Each draw seeds the frozen thirty again, runs one cycle and verifies, so the previous draw's rows
are first exported, then cleared.

**Exported** (``--export``, JSON):
- **Every seeded query of the previous draw's seed record:** its id, kind, role and wording. For an
  ask, its log row's ``answered``, ``no_answer_reason`` (path A, ``no_relevant_passage``, or path B,
  ``no_statement_verified``), ``rejected_count`` and the number of passages it retrieved. For a
  search, its ``result_count``.
- **The gap log as the cycle left it:** each entry with its subject, count, status, embedding model
  and the seeded queries that are its items, and the cycle rows.

The FR-12 decline session scores FR-12 per draw from these exports, because the seed record alone
does not carry the path.

**Cleared** (unless ``--export-only``), in one transaction, after every count is checked:
- every ``KnowledgeGapItem``, ``KnowledgeGap`` and ``KnowledgeGapCycle`` row. The database had none
  before draw 1;
- the previous draw's seeded ``QueryLog`` rows, whose ``AnswerCitation`` rows go with them;
- the previous draw's seeded ``SearchLog`` rows. Each is found by its user and wording, at or after
  that seeding's start.

The fifty earlier search logs are kept: clause 3 reads them.

It refuses unless the database is kmp_obj0506_anthropic_20261110, every seeded query has exactly one
log row from that seeding, and the gap, item and cycle counts are the expected ones.

Usage, in PowerShell, with the run's DATABASE_URL set::

    & $py corpus\\objective-06\\runs\\2026-11-11-anthropic\\reset_objective06_draw.py `
        --seed <the previous draw's seed.json> --export <its export.json> `
        --expect-gaps 4 --expect-items 11 --expect-cycles 1 [--export-only]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]  # corpus/objective-06/runs/<this folder>/<this file>
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

EXPECTED_DATABASE = "kmp_obj0506_anthropic_20261110"
ACCOUNTS = {"Administrator": "corpus.admin@example.com", "Employee": "corpus.employee@example.com"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--expect-gaps", type=int, required=True)
    parser.add_argument("--expect-items", type=int, required=True)
    parser.add_argument("--expect-cycles", type=int, required=True)
    parser.add_argument("--export-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.export.exists():
        print(f"REFUSED: {arguments.export} already exists. Nothing was exported or cleared.")
        return 2

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import transaction

    from apps.retrieval.models import KnowledgeGap, KnowledgeGapCycle, KnowledgeGapItem, QueryLog, SearchLog

    database = str(settings.DATABASES["default"]["NAME"])
    if database != EXPECTED_DATABASE:
        print(f"REFUSED: connected to {database!r}, not {EXPECTED_DATABASE!r}. Nothing was exported or cleared.")
        return 2
    seed_bytes = arguments.seed.read_bytes()
    seed = json.loads(seed_bytes.decode("utf-8"))
    started = datetime.fromisoformat(seed["record"]["started_at"])
    users = {role: get_user_model().objects.get(email=email) for role, email in ACCOUNTS.items()}

    asks, searches, problems = [], [], []
    for result in seed["results"]:
        user = users[result["role"]]
        base = {key: result.get(key) for key in ("id", "kind", "role", "via", "query", "subject", "expected_in_log")}
        if result["via"] == "ask":
            rows = list(QueryLog.objects.filter(user=user, question=result["query"], answered_at__gte=started))
            if len(rows) != 1:
                problems.append(f"{result['id']}: {len(rows)} QueryLog rows from that seeding")
                continue
            row = rows[0]
            asks.append({**base, "row_id": str(row.pk), "answered": row.answered, "no_answer_reason": row.no_answer_reason,
                         "rejected_count": row.rejected_count, "retrieved": len(row.retrieved_chunk_ids),
                         "answered_at": row.answered_at.isoformat()})
        else:
            rows = list(SearchLog.objects.filter(user=user, query_text=result["query"], searched_at__gte=started))
            if len(rows) != 1:
                problems.append(f"{result['id']}: {len(rows)} SearchLog rows from that seeding")
                continue
            row = rows[0]
            searches.append({**base, "row_id": str(row.pk), "result_count": row.result_count,
                             "searched_at": row.searched_at.isoformat()})
    by_query = {entry["row_id"]: entry["id"] for entry in asks}
    by_search = {entry["row_id"]: entry["id"] for entry in searches}
    gaps = []
    for gap in KnowledgeGap.objects.order_by("subject"):
        items = list(KnowledgeGapItem.objects.filter(gap=gap))
        gaps.append({"subject": gap.subject, "occurrence_count": gap.occurrence_count, "status": gap.status,
                     "embedding_model": gap.embedding_model, "items": len(items),
                     "seeded_ids": sorted(by_query.get(str(item.query_id), "") or by_search.get(str(item.search_id), "")
                                          or "not a seeded query" for item in items)})
    cycles = [{"started_at": c.started_at.isoformat(), "finished_at": c.finished_at.isoformat() if c.finished_at else None,
               "queries_considered": c.queries_considered, "searches_considered": c.searches_considered,
               "entries_created": c.entries_created, "entries_updated": c.entries_updated}
              for c in KnowledgeGapCycle.objects.order_by("started_at")]
    counts = {"gaps": KnowledgeGap.objects.count(), "items": KnowledgeGapItem.objects.count(),
              "cycles": KnowledgeGapCycle.objects.count(), "seeded_asks_found": len(asks),
              "seeded_searches_found": len(searches), "query_logs": QueryLog.objects.count(),
              "search_logs": SearchLog.objects.count()}
    print(f"database {database}: {counts}")
    expected = {"gaps": arguments.expect_gaps, "items": arguments.expect_items, "cycles": arguments.expect_cycles}
    problems += [f"{name}: {counts[name]}, expected {value}" for name, value in expected.items() if counts[name] != value]
    if problems:
        print("REFUSED: " + "; ".join(problems) + ". Nothing was exported or cleared.")
        return 2

    arguments.export.parent.mkdir(parents=True, exist_ok=True)
    arguments.export.write_text(json.dumps({
        "database": database,
        "seed_record": {"path": str(arguments.seed), "sha256": hashlib.sha256(seed_bytes).hexdigest(),
                        "started_at": seed["record"]["started_at"], "commit_sha": seed["record"].get("commit_sha"),
                        "configuration": seed["record"].get("configuration")},
        "exported_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "asks": asks, "searches": searches, "gaps": gaps, "cycles": cycles, "counts_before_clearing": counts,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"exported {len(asks)} asks, {len(searches)} searches, {len(gaps)} gaps and {len(cycles)} cycle(s) to {arguments.export}")
    if arguments.export_only:
        return 0

    with transaction.atomic():
        items_deleted, _ = KnowledgeGapItem.objects.all().delete()
        gaps_deleted, _ = KnowledgeGap.objects.all().delete()
        cycles_deleted, _ = KnowledgeGapCycle.objects.all().delete()
        queries_deleted, _ = QueryLog.objects.filter(pk__in=[entry["row_id"] for entry in asks]).delete()
        searches_deleted, _ = SearchLog.objects.filter(pk__in=[entry["row_id"] for entry in searches]).delete()
    print(f"cleared: {items_deleted} item, {gaps_deleted} gap and {cycles_deleted} cycle row(s); "
          f"{queries_deleted} QueryLog-and-citation row(s); {searches_deleted} SearchLog row(s)")
    print(f"after: gaps {KnowledgeGap.objects.count()}, items {KnowledgeGapItem.objects.count()}, cycles "
          f"{KnowledgeGapCycle.objects.count()}, query logs {QueryLog.objects.count()}, search logs {SearchLog.objects.count()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
