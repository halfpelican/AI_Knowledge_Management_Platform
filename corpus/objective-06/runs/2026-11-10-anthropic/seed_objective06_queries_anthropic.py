"""Objective 06 on the anthropic provider (10 November 2026): the seeding, on Voyage and Claude Haiku 5.5.

A copy of scripts/seed_objective06_queries.py at a9934eb, changed only where FLM was named, so
that the frozen thirty (corpus/objective-06/queries.json, D-110) go through the shipped
answer_question and search on the anthropic provider. They run against
kmp_obj0506_anthropic_20261110, the copy made for Objective 05 on the same provider by D-106's
procedure. The changes:

- **The environment is set here, before Django starts.** DATABASE_URL is .env's with the
  database name swapped (never printed). AI_PROVIDER is ``anthropic``, ANTHROPIC_MODEL
  ``claude-haiku-5-5`` (D-121) and EMBEDDING_DIMENSION 1024; the embedder is Voyage ``voyage-4``.
- **The paths** point at scripts/ and the repository root from this folder.
- **The FLM gate** (scripts/check_flm.py's checks and the FLM version, D-83) is replaced by a
  provider gate. It refuses unless the provider, both models and the dimension are the ones
  above, both keys are present (their values are never printed), the database is
  kmp_obj0506_anthropic_20261110 and not a protected one, and voyage-4's threshold and floor are
  D-120's 0.2687 and 0.2468.
- **The record** carries no FLM version, because FLM takes no part. It adds Claude's token
  usage, tallied for D-113's spend report by a wrapper around AnthropicService._claude_once that
  counts each reply and returns it unchanged.

Everything else is the original's: the queries, the users, the calls and the record's fields.
The original docstring follows.

Seed Objective 06's thirty queries through the shipped pipeline, so the gap log has them to read.

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

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]  # corpus/objective-06/runs/<this folder>/<this file>
SCRIPTS = REPOSITORY_ROOT / "scripts"
for entry in (str(SCRIPTS), str(REPOSITORY_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import measurement_record  # noqa: E402

# This copy: the anthropic provider and its own database, set before Django reads its settings,
# so this process cannot reach FLM or another database (D-113).
EXPECTED_DATABASE = "kmp_obj0506_anthropic_20261110"
PROTECTED = frozenset({"kmp", "kmp_demo_20261101", "kmp_obj02_20261101", "kmp_obj0506_20261101",
                       "kmp_voyage_20261110", "kmp_anthropic"})
EXPECTED_SETTINGS = {
    "AI_PROVIDER": "anthropic",
    "ANTHROPIC_MODEL": "claude-haiku-5-5",  # D-121
    "VOYAGE_MODEL": "voyage-4",
    "EMBEDDING_DIMENSION": 1024,
}
EXPECTED_THRESHOLD = 0.2687  # D-120, RELEVANCE_THRESHOLD_BY_MODEL["voyage-4"]
EXPECTED_FLOOR = 0.2468  # D-120, PARTIAL_MATCH_FLOOR_BY_MODEL["voyage-4"]
USD_PER_MILLION_IN, USD_PER_MILLION_OUT = 0.10, 0.50  # Claude Haiku 5.5


def anthropic_database_url() -> str:
    """.env's DATABASE_URL with the database name swapped. Never printed."""
    import re

    for line in (REPOSITORY_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return re.sub(r"/[^/]+$", f"/{EXPECTED_DATABASE}", line.split("=", 1)[1].strip())
    raise SystemExit("no DATABASE_URL in .env")


os.environ["DATABASE_URL"] = anthropic_database_url()
os.environ["AI_PROVIDER"] = "anthropic"
os.environ["ANTHROPIC_MODEL"] = "claude-haiku-5-5"
os.environ["EMBEDDING_DIMENSION"] = "1024"


def provider_problems(settings, database: str) -> list[str]:
    """Why this run is not the anthropic provider on its own database at D-120's values."""
    from apps.retrieval.partial_matches import partial_match_floor
    from apps.retrieval.ranking import relevance_threshold

    problems = [f"settings.{name} is {getattr(settings, name)!r}, not {expected!r}"
                for name, expected in EXPECTED_SETTINGS.items() if getattr(settings, name) != expected]
    for name in ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY"):
        if not getattr(settings, name):
            problems.append(f"settings.{name} is empty")  # the value itself is never printed
    if database.lower() in PROTECTED:
        problems.append(f"the database {database!r} is protected")
    if database != EXPECTED_DATABASE:
        problems.append(f"the database is {database!r}, not {EXPECTED_DATABASE!r}")
    threshold = relevance_threshold(settings.VOYAGE_MODEL)
    floor = partial_match_floor(settings.VOYAGE_MODEL)
    if threshold != EXPECTED_THRESHOLD:
        problems.append(f"the threshold for {settings.VOYAGE_MODEL} is {threshold}, not D-120's {EXPECTED_THRESHOLD}")
    if floor != EXPECTED_FLOOR:
        problems.append(f"the partial-match floor for {settings.VOYAGE_MODEL} is {floor}, not D-120's {EXPECTED_FLOOR}")
    return problems

DEFAULT_QUERIES = REPOSITORY_ROOT / "corpus" / "objective-06" / "queries.json"
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

    # This copy: the provider gate in place of check_flm.py's (FLM takes no part).
    problems = provider_problems(settings, database)
    if problems:
        print("REFUSED: " + "; ".join(problems))
        return 2
    print(f"Provider gate: PASS (anthropic, {settings.ANTHROPIC_MODEL}, {settings.VOYAGE_MODEL} at "
          f"{settings.EMBEDDING_DIMENSION}, both keys present, threshold {EXPECTED_THRESHOLD} and floor "
          f"{EXPECTED_FLOOR}; database {database})")

    # This copy: Claude's token usage, for the spend report; each reply is returned unchanged.
    from apps.ai.anthropic import AnthropicService

    usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "replies_without_usage": 0}
    original_claude_once = AnthropicService._claude_once

    def counting_claude_once(self, *args, **kwargs):
        reply = original_claude_once(self, *args, **kwargs)
        usage["calls"] += 1
        if reply.prompt_tokens is None or reply.completion_tokens is None:
            usage["replies_without_usage"] += 1
        usage["input_tokens"] += reply.prompt_tokens or 0
        usage["output_tokens"] += reply.completion_tokens or 0
        return reply

    AnthropicService._claude_once = counting_claude_once

    User = get_user_model()
    users = {}
    for role, email in ACCOUNTS.items():
        user = User.objects.filter(email=email).select_related("role").first()
        if user is None or user.role.role_name != role:
            print(f"REFUSED: {email} is missing or is not the {role}")
            return 2
        users[role] = user

    record = measurement_record.run_record(dump_sha256=arguments.dump_sha256, database=database, flm=None)  # this copy: FLM takes no part
    record["configuration"] = provider_record(settings)
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
                            "statements": len(outcome.verified_statements)})
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
    # This copy: Claude's token usage (D-113).
    record["claude_usage"] = {**usage, "estimated_usd": round((usage["input_tokens"] * USD_PER_MILLION_IN
                                                               + usage["output_tokens"] * USD_PER_MILLION_OUT) / 1_000_000, 4)}
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
    print(f"Claude usage: {record['claude_usage']}")  # this copy
    return 0


if __name__ == "__main__":
    sys.exit(main())
