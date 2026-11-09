"""Seed Objective 06's thirty queries through the shipped pipeline, so the gap log has them to read.

Objective 06 is verified "by seeding thirty queries of a known outcome". This script sends each
query of corpus/objective-06/queries.json through the SAME functions the API views call, as the
user the set names: a question through ``apps.retrieval.pipeline.answer_question`` (one QueryLog
row at whichever of its three exits it reaches) and a keyword search through
``apps.retrieval.search.search`` (one SearchLog row with the post-filter count). Nothing is
simulated and nothing is written to the logs by this script itself: the rows are the pipeline's.

In process rather than over HTTP, as D-100's development runs were: the rows are identical, and
no throttle, in-flight slot or password is involved. The two accounts are the snapshot's
``corpus.admin@example.com`` (Administrator) and ``corpus.employee@example.com`` (Employee), whose
passwords nobody knows (D-88) and which this script never needs.

**Which database.** Whatever DATABASE_URL names; the name is printed first and ``kmp`` is refused
(D-84). The intended one is ``kmp_obj0506_20261101`` (D-106). The run is recorded: commit, FLM
version, the dump hash you pass, and every query's outcome, to ``--out-dir``.

Usage, in PowerShell, with FLM serving::

    $env:DATABASE_URL = "<the measurement database's URL>"
    .venv\\Scripts\\python.exe scripts\\seed_objective06_queries.py `
        --dump-sha256 <hex> --out-dir corpus\\objective-06\\runs\\<date>\\seed

Then run one aggregation cycle (``manage.py aggregate_knowledge_gaps``) and
scripts/objective06_verify.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
for entry in (str(SCRIPTS), str(REPOSITORY_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import check_flm  # noqa: E402
import measurement_record  # noqa: E402

DEFAULT_QUERIES = REPOSITORY_ROOT / "corpus" / "objective-06" / "queries.json"
ACCOUNTS = {"Administrator": "corpus.admin@example.com", "Employee": "corpus.employee@example.com"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dump-sha256", required=True, help="SHA-256 of the dump the database was restored from")
    parser.add_argument("--limit", type=int, default=0, help="first N queries only (a smoke test, not the seeding)")
    arguments = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from apps.ai.base import ProviderUnavailable
    from apps.retrieval.pipeline import answer_question
    from apps.retrieval.search import search

    database = str(settings.DATABASES["default"]["NAME"])
    print(f"database: {database}")
    try:
        measurement_record.refuse_protected_database(database)
    except measurement_record.RecordError as exc:
        print(f"REFUSED: {exc}")
        return 2
    if arguments.out_dir.exists() and any(arguments.out_dir.iterdir()):
        print(f"REFUSED: {arguments.out_dir} already holds files; a seeding is recorded once")
        return 2

    payload = json.loads(arguments.queries.read_text(encoding="utf-8"))
    queries = payload["queries"][: arguments.limit] if arguments.limit else payload["queries"]

    print("FLM gate: scripts/check_flm.py's checks (D-83)")
    checks = check_flm.run_checks(settings.FLM_BASE_URL, settings.FLM_API_KEY, settings.FLM_CHAT_MODEL, settings.FLM_EMBED_MODEL)
    if not check_flm.checks_passed(checks):
        print("REFUSED: FLM checks failed")
        return 2
    version = check_flm.flm_version(settings.FLM_BASE_URL, settings.FLM_API_KEY)
    if version.problems():
        print("REFUSED: " + "; ".join(version.problems()))
        return 2

    User = get_user_model()
    users = {}
    for role, email in ACCOUNTS.items():
        user = User.objects.filter(email=email).select_related("role").first()
        if user is None or user.role.role_name != role:
            print(f"REFUSED: {email} is missing or is not the {role}")
            return 2
        users[role] = user

    record = measurement_record.run_record(dump_sha256=arguments.dump_sha256, database=database, flm=version.as_record())
    record.update({
        "kind": "Objective 06 seeding of the thirty queries (D-109)",
        "query_set": str(arguments.queries.relative_to(REPOSITORY_ROOT)) if arguments.queries.is_relative_to(REPOSITORY_ROOT) else str(arguments.queries),
        "query_set_sha256": measurement_record.file_sha256(arguments.queries),
        "query_set_status": payload.get("status"),
        "started_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    })
    arguments.out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for query in queries:
        user = users[query["role"]]
        started = time.perf_counter()
        row = {k: query.get(k) for k in ("id", "kind", "role", "via", "query", "subject", "expected_in_log")}
        try:
            if query["via"] == "ask":
                outcome = answer_question(question=query["query"], user=user)
                row.update({"answered": outcome.answered, "result_count": outcome.result_count,
                            "statements": len(outcome.statements)})
                shown = "answered" if outcome.answered else "no-answer"
            elif query["via"] == "search":
                results_ = search(query_text=query["query"], user=user)
                row.update({"result_count": results_.total_count})
                shown = f"{results_.total_count} result(s)"
            else:
                raise ValueError(f"{query['id']}: unknown via {query['via']!r}")
        except ProviderUnavailable as exc:
            row.update({"error": f"provider unavailable: {exc}"})
            shown = "PROVIDER UNAVAILABLE (no row written)"
        row["seconds"] = round(time.perf_counter() - started, 1)
        results.append(row)
        print(f"  {query['id']} {query['role']:<13} {query['via']:<6} {shown:<28} {row['seconds']}s  {query['query'][:60]}")

    record["finished_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    asks = [r for r in results if r["via"] == "ask" and "error" not in r]
    summary = {
        "queries": len(results),
        "errors": sum(1 for r in results if "error" in r),
        "asks_answered": sum(1 for r in asks if r["answered"]),
        "asks_no_answer": sum(1 for r in asks if not r["answered"]),
        "searches_zero": sum(1 for r in results if r["via"] == "search" and r.get("result_count") == 0),
        "by_kind": {},
    }
    for kind in ("answerable", "unanswerable", "permission-only"):
        rows = [r for r in results if r["kind"] == kind and "error" not in r]
        summary["by_kind"][kind] = {
            "asks_answered": sum(1 for r in rows if r["via"] == "ask" and r["answered"]),
            "asks_no_answer": sum(1 for r in rows if r["via"] == "ask" and not r["answered"]),
            "searches_with_results": sum(1 for r in rows if r["via"] == "search" and r["result_count"] > 0),
            "searches_zero": sum(1 for r in rows if r["via"] == "search" and r["result_count"] == 0),
        }
    (arguments.out_dir / "seed.json").write_text(
        json.dumps({"record": record, "results": results, "summary": summary}, indent=2), encoding="utf-8")
    print(f"\nwrote {arguments.out_dir / 'seed.json'}")
    print(json.dumps(summary["by_kind"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
