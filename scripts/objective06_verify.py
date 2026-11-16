"""Objective 06's verification: the seeded thirty against the gap log after one aggregation cycle.

Reads the seeding record `scripts/seed_objective06_queries.py --out-dir` wrote, finds each
seeded query's own log row (QueryLog by user and question, SearchLog by user and term), and
checks the objective's three clauses against the KnowledgeGap tables (D-107 to D-109):

1. "every genuinely unanswerable query and zero-result search must appear in the log within one
   aggregation cycle": every seeded query with expected_in_log true has a KnowledgeGapItem.
   A seeded ask that FR-12 ANSWERED has no no-answer to aggregate; it is reported on its own
   line as answered, which is FR-12's open decline finding (D-102) and not FR-19's.
2. "differently worded questions on a single subject must group into one entry with an accurate
   occurrence count": the items of one subject's queries all point at one gap, and that gap's
   occurrence_count equals its item count.
3. "no query returning nothing on permission grounds may appear in the log at all": no seeded
   permission-only query has an item, and none of the database's pre-existing zero-result
   searches by the Employee for Administrator-only phrases has one either.

Writes nothing to the database. Usage, in PowerShell::

    $env:DATABASE_URL = "<the measurement database's URL>"
    .venv\\Scripts\\python.exe scripts\\objective06_verify.py --dump-sha256 <hex> `
        --seed corpus\\objective-06\\runs\\<date>\\seed\\seed.json --out-dir corpus\\objective-06\\runs\\<date>\\verification
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for entry in (str(REPOSITORY_ROOT / "scripts"), str(REPOSITORY_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import check_flm  # noqa: E402
import measurement_record  # noqa: E402

ACCOUNTS = {"Administrator": "corpus.admin@example.com", "Employee": "corpus.employee@example.com"}


def provider_record(settings) -> dict:
    """The configuration this result belongs to (D-113): the provider, its chat model and its
    embedding model. A value tuned, or a result measured, on one configuration does not carry
    over to another, so every record names its own."""
    provider = settings.AI_PROVIDER
    if provider == "anthropic":
        return {"ai_provider": provider, "chat_model": settings.ANTHROPIC_MODEL,
                "embedding_model": settings.VOYAGE_MODEL}
    return {"ai_provider": provider, "chat_model": settings.FLM_CHAT_MODEL,
            "embedding_model": settings.FLM_EMBED_MODEL}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=Path, required=True, help="seed.json from seed_objective06_queries.py")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dump-sha256", required=True)
    arguments = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from apps.retrieval.models import KnowledgeGap, KnowledgeGapCycle, KnowledgeGapItem, QueryLog, SearchLog

    database = str(settings.DATABASES["default"]["NAME"])
    print(f"database: {database}")
    measurement_record.refuse_protected_database(database)
    if arguments.out_dir.exists() and any(arguments.out_dir.iterdir()):
        print(f"REFUSED: {arguments.out_dir} already holds files")
        return 2

    seed = json.loads(arguments.seed.read_text(encoding="utf-8"))
    User = get_user_model()
    users = {role: User.objects.get(email=email) for role, email in ACCOUNTS.items()}
    version = check_flm.flm_version(settings.FLM_BASE_URL, settings.FLM_API_KEY)
    record = measurement_record.run_record(dump_sha256=arguments.dump_sha256, database=database, flm=version.as_record())
    cycles = list(KnowledgeGapCycle.objects.order_by("started_at"))
    record["configuration"] = provider_record(settings)
    record.update({
        "kind": "Objective 06 verification (D-107 to D-110)",
        "seed_record": str(arguments.seed), "seed_query_set_sha256": seed["record"].get("query_set_sha256"),
        "verified_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "cycles": [{"cycle_id": str(c.pk), "started_at": c.started_at.isoformat(), "finished_at": c.finished_at.isoformat() if c.finished_at else None,
                    "queries_considered": c.queries_considered, "searches_considered": c.searches_considered,
                    "entries_created": c.entries_created, "entries_updated": c.entries_updated} for c in cycles],
    })

    rows = []
    gaps_by_subject = defaultdict(set)
    for result in seed["results"]:
        user = users[result["role"]]
        row = {k: result.get(k) for k in ("id", "kind", "role", "via", "query", "subject", "expected_in_log", "answered", "result_count")}
        if result["via"] == "ask":
            log_rows = list(QueryLog.objects.filter(user=user, question=result["query"]).order_by("-answered_at"))
            item = KnowledgeGapItem.objects.filter(query=log_rows[0]).select_related("gap").first() if log_rows else None
        else:
            log_rows = list(SearchLog.objects.filter(user=user, query_text=result["query"]).order_by("-searched_at"))
            item = KnowledgeGapItem.objects.filter(search=log_rows[0]).select_related("gap").first() if log_rows else None
        row["log_rows_found"] = len(log_rows)
        row["in_log"] = item is not None
        row["gap_id"] = str(item.gap.pk) if item else None
        row["gap_subject"] = item.gap.subject if item else None
        row["gap_count"] = item.gap.occurrence_count if item else None
        if result.get("subject") and item:
            gaps_by_subject[result["subject"]].add(str(item.gap.pk))
        if result["via"] == "ask" and result.get("answered"):
            row["note"] = "answered by FR-12, so there was no no-answer to aggregate (D-102's open finding)"
        rows.append(row)

    # Clause 1.
    expected = [r for r in rows if r["expected_in_log"]]
    present = [r for r in expected if r["in_log"]]
    missing = [r for r in expected if not r["in_log"]]
    missing_answered = [r for r in missing if r["via"] == "ask" and r.get("answered")]
    missing_unexplained = [r for r in missing if r not in missing_answered]
    # Clause 2.
    subjects = {}
    for subject in sorted({r["subject"] for r in rows if r.get("subject")}):
        members = [r for r in rows if r.get("subject") == subject and r["in_log"]]
        gap_ids = gaps_by_subject.get(subject, set())
        count_ok = None
        if len(gap_ids) == 1:
            gap = KnowledgeGap.objects.get(pk=next(iter(gap_ids)))
            count_ok = gap.occurrence_count == KnowledgeGapItem.objects.filter(gap=gap).count()
        subjects[subject] = {"queries": sum(1 for r in rows if r.get("subject") == subject), "in_log": len(members),
                             "distinct_gaps": len(gap_ids), "one_entry": len(gap_ids) == 1 if members else None,
                             "count_matches_items": count_ok,
                             "gap_count": members[0]["gap_count"] if members and len(gap_ids) == 1 else None}
    # Clause 3.
    permission_rows = [r for r in rows if r["kind"] == "permission-only"]
    permission_in_log = [r for r in permission_rows if r["in_log"]]
    employee = users["Employee"]
    preexisting = []
    for search in SearchLog.objects.filter(user=employee, result_count=0).order_by("searched_at"):
        if any(r["via"] == "search" and r["role"] == "Employee" and r["query"] == search.query_text for r in rows):
            continue
        preexisting.append({"query_text": search.query_text, "searched_at": search.searched_at.isoformat(),
                            "in_log": KnowledgeGapItem.objects.filter(search=search).exists()})
    answerable_in_log = [r for r in rows if r["kind"] == "answerable" and r["in_log"]]

    summary = {
        "clause_1": {"expected_in_log": len(expected), "present": len(present), "missing": [r["id"] for r in missing],
                     "missing_because_fr12_answered": [r["id"] for r in missing_answered],
                     "missing_unexplained": [r["id"] for r in missing_unexplained],
                     "passes_as_worded": not missing, "passes_for_rows_that_reached_a_no_answer": not missing_unexplained},
        "clause_2": {"subjects": subjects,
                     "passes": all(v["one_entry"] and v["count_matches_items"] for v in subjects.values() if v["in_log"])},
        "clause_3": {"permission_only_queries": len(permission_rows), "in_log": [r["id"] for r in permission_in_log],
                     "preexisting_employee_zero_result_searches": preexisting,
                     "passes": not permission_in_log and not any(p["in_log"] for p in preexisting)},
        "controls": {"answerable_in_log": [r["id"] for r in answerable_in_log]},
        "gap_log": [{"gap_id": str(g.pk), "subject": g.subject, "occurrence_count": g.occurrence_count, "status": g.status,
                     "items": KnowledgeGapItem.objects.filter(gap=g).count()} for g in KnowledgeGap.objects.order_by("-occurrence_count", "subject")],
    }
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    (arguments.out_dir / "verification.json").write_text(json.dumps({"record": record, "rows": rows, "summary": summary}, indent=2, default=str), encoding="utf-8")

    c1, c2, c3 = summary["clause_1"], summary["clause_2"], summary["clause_3"]
    lines = ["# Objective 06 verification (D-107 to D-110)", "",
             f"Commit {record['commit_sha'][:7]}" + (" (uncommitted tracked changes)" if record["uncommitted_tracked_changes"] else "")
             + f", database {database}, dump {record['dump_sha256'][:8]}…, FLM {version.summary()}, provider {record['configuration']}, {len(cycles)} cycle(s).", "",
             "| Id | Kind | Role | Via | Expected in log | In log | Gap subject | Gap count | Note |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['kind']} | {r['role']} | {r['via']} | {r['expected_in_log']} | {r['in_log']} | {r['gap_subject'] or ''} | {r['gap_count'] if r['gap_count'] is not None else ''} | {r.get('note','')} |")
    lines += ["", f"**Clause 1:** {c1['present']} of {c1['expected_in_log']} expected queries are in the log after one cycle. Missing: {c1['missing'] or 'none'}; of those, answered by FR-12: {c1['missing_because_fr12_answered'] or 'none'}; unexplained: {c1['missing_unexplained'] or 'none'}. As worded: {'MET' if c1['passes_as_worded'] else 'NOT MET'}; for every query that reached a no-answer or zero result: {'MET' if c1['passes_for_rows_that_reached_a_no_answer'] else 'NOT MET'}.",
              f"**Clause 2:** {json.dumps(c2['subjects'])}. {'MET' if c2['passes'] else 'NOT MET'}.",
              f"**Clause 3:** permission-only queries in the log: {c3['in_log'] or 'none'}; pre-existing Employee zero-result searches in the log: {[p['query_text'] for p in c3['preexisting_employee_zero_result_searches'] if p['in_log']] or 'none'}. {'MET' if c3['passes'] else 'NOT MET'}.",
              f"Controls: answerable queries in the log: {summary['controls']['answerable_in_log'] or 'none'}.", "",
              "## The gap log after the cycle", "", "| Subject | Count | Items | Status |", "|---|---|---|---|"]
    lines += [f"| {g['subject']} | {g['occurrence_count']} | {g['items']} | {g['status']} |" for g in summary["gap_log"]]
    (arguments.out_dir / "verification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-(len(summary['gap_log']) + 9):]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
