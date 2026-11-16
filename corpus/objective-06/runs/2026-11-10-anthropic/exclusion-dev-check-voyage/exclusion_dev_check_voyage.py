"""D-108's development check on the anthropic provider (11 November 2026), run after the frozen thirty, not before.

A copy of scripts/exclusion_dev_check.py at a9934eb, changed only where FLM was named, so that
D-108's check of FR-19's permission exclusion runs on Voyage voyage-4's query embeddings over
kmp_obj0506_anthropic_20261110, the copy on which Objective 06's thirty were seeded and cycled.

**It is late.** D-108's and D-110's notes say this check is repeated on a new configuration before
the thirty are run there. On anthropic it was not: the thirty's cycle had already run, and left
U01 out of the log. The user approved running the check afterwards. Its result cannot have shaped
that cycle, which is not re-run.

The changes:
- **The environment is set here, before Django starts.** DATABASE_URL is .env's with the
  database name swapped (never printed). AI_PROVIDER is ``anthropic`` and EMBEDDING_DIMENSION 1024.
- **The paths** point at scripts/ and the repository root from this folder.
- **The FLM gate** is replaced by a provider gate. It refuses unless the provider is anthropic,
  the models are claude-haiku-5-5 and voyage-4 at 1024, both keys are present (their values are
  never printed), the database is kmp_obj0506_anthropic_20261110, and voyage-4's threshold and
  floor are D-120's. No Claude model is called: the check only embeds and ranks.
- **The record and table** carry no FLM version.

Everything else is the original's: the questions, the asker, the cycle's own decision and the
expected outcomes. The record's ``relevance_threshold`` field is the original's
RELEVANCE_THRESHOLD, the default 0.30. The decision does not use it, and the ``admitted`` column
uses voyage-4's own 0.2687 (D-120). The original docstring follows.

D-108's development check: does the permission exclusion leave out what it should, and only that?

D-108 fixed the check before any run: the rule is tried first on development material, the scoped
and no-answer questions of corpus/objective-02/dev-set-v2.json and dev-set.json, every one asked as
the Employee. A scoped question's answer exists only in Administrator-only material, so its row
should be LEFT OUT (a permission boundary, not a gap); a no-answer question has no answer anywhere,
so its row should be KEPT (a gap). If the check fails, the margin rule is chosen on the same
material before Objective 06's thirty are run. The thirty are never used here.

It calls the cycle's own decision, ``apps.retrieval.gaps._question_explained_by_permissions``, with
the cycle's own Administrator scope and the pipeline's own query embedding (``embed_question``), so
what is checked is what ships. Nothing is written: no QueryLog row, no gap, no cycle. The ordinary
questions are reported too, for information: an Employee's unanswered ordinary question should be
kept, because its best passage is one the Employee may read.

Usage, in PowerShell, with FLM serving and DATABASE_URL naming the corpus database::

    .venv\\Scripts\\python.exe scripts\\exclusion_dev_check.py --out-dir corpus\\objective-06\\runs\\<date>\\exclusion-dev-check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]  # corpus/objective-06/runs/<run>/<this folder>/<this file>
for entry in (str(REPOSITORY_ROOT / "scripts"), str(REPOSITORY_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import measurement_record  # noqa: E402

# This copy: the anthropic provider and its database, set before Django reads its settings (D-113).
EXPECTED_DATABASE = "kmp_obj0506_anthropic_20261110"
EXPECTED_SETTINGS = {"AI_PROVIDER": "anthropic", "ANTHROPIC_MODEL": "claude-haiku-5-5",
                     "VOYAGE_MODEL": "voyage-4", "EMBEDDING_DIMENSION": 1024}
EXPECTED_THRESHOLD, EXPECTED_FLOOR = 0.2687, 0.2468  # D-120, for voyage-4


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

DEV_SETS = (
    REPOSITORY_ROOT / "corpus" / "objective-02" / "dev-set-v2.json",
    REPOSITORY_ROOT / "corpus" / "objective-02" / "dev-set.json",
)
ASKER_ROLE = "Employee"


def provider_record(settings) -> dict:
    """The configuration this result belongs to (D-113): the provider, its chat model and its
    embedding model."""
    provider = settings.AI_PROVIDER
    if provider == "anthropic":
        return {"ai_provider": provider, "chat_model": settings.ANTHROPIC_MODEL,
                "embedding_model": settings.VOYAGE_MODEL}
    return {"ai_provider": provider, "chat_model": settings.FLM_CHAT_MODEL,
            "embedding_model": settings.FLM_EMBED_MODEL}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dump-sha256", required=True, help="SHA-256 of the dump the corpus database was restored from")
    arguments = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings

    from apps.core.constants import EFFECTIVE_ROLES, RELEVANCE_THRESHOLD
    from apps.retrieval import gaps
    from apps.retrieval.query_embedding import embed_question
    from apps.retrieval.ranking import admit, rank

    database = str(settings.DATABASES["default"]["NAME"])
    print(f"database: {database}")
    measurement_record.refuse_protected_database(database)
    if arguments.out_dir.exists() and any(arguments.out_dir.iterdir()):
        print(f"REFUSED: {arguments.out_dir} already holds files")
        return 2
    # This copy: the provider gate in place of check_flm.py's (FLM takes no part).
    from apps.retrieval.partial_matches import partial_match_floor
    from apps.retrieval.ranking import relevance_threshold

    problems = [f"settings.{name} is {getattr(settings, name)!r}, not {value!r}"
                for name, value in EXPECTED_SETTINGS.items() if getattr(settings, name) != value]
    for name in ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY"):
        if not getattr(settings, name):
            problems.append(f"settings.{name} is empty")  # the value itself is never printed
    if database != EXPECTED_DATABASE:
        problems.append(f"the database is {database!r}, not {EXPECTED_DATABASE!r}")
    if relevance_threshold(settings.VOYAGE_MODEL) != EXPECTED_THRESHOLD or partial_match_floor(settings.VOYAGE_MODEL) != EXPECTED_FLOOR:
        problems.append("voyage-4's threshold and floor are not D-120's 0.2687 and 0.2468")
    if problems:
        print("REFUSED: " + "; ".join(problems))
        return 2
    print(f"Provider gate: PASS (anthropic, voyage-4 at 1024, both keys present; database {database})")

    # A stand-in for a QueryLog row: the decision reads only the asker's role name from it.
    row = SimpleNamespace(user=SimpleNamespace(role=SimpleNamespace(role_name=ASKER_ROLE)))
    asker_roles = set(EFFECTIVE_ROLES[ASKER_ROLE])
    scope = gaps._AdministratorScope()

    results = []
    for dev_set in DEV_SETS:
        for question in json.loads(dev_set.read_text(encoding="utf-8"))["questions"]:
            kind = question["kind"]
            embedding = embed_question(question["question"])
            left_out = gaps._question_explained_by_permissions(row, embedding, scope)
            chunks, roles = scope.for_model(embedding.model)
            ranked = rank(chunks, embedding.vectors[0])
            admitted = admit(ranked, embedding_model=embedding.model)  # the model's own threshold (D-120)
            # The top-ranked passage, whether or not it clears the threshold: what the rule decides
            # on since D-108's evening note. Until 10 November these columns showed the top
            # admitted passage, so a question decided below the threshold showed None.
            top = ranked[0] if ranked else None
            expected = {"scoped": "left out", "no-answer": "kept"}.get(kind, "kept if unanswered")
            outcome = "left out" if left_out else "kept"
            results.append({
                "set": dev_set.name, "id": question["id"], "kind": kind, "question": question["question"],
                "source": question.get("source"), "asked_as": ASKER_ROLE,
                "admitted": len(admitted),
                "top_score": round(top.score, 4) if top else None,
                "top_readable_by_asker": bool(set(roles[top.chunk_id]) & asker_roles) if top else None,
                "outcome": outcome, "expected": expected,
                "as_expected": outcome == expected if kind in ("scoped", "no-answer") else None,
            })
            mark = {True: "ok  ", False: "MISS", None: "info"}[results[-1]["as_expected"]]
            print(f"  {mark} {dev_set.name:<16} {question['id']:<4} {kind:<9} -> {outcome:<8} (top {results[-1]['top_score']}, readable {results[-1]['top_readable_by_asker']}) {question['question'][:60]}")

    judged = [r for r in results if r["as_expected"] is not None]
    summary = {
        "scoped": {"total": sum(1 for r in judged if r["kind"] == "scoped"),
                   "left_out": sum(1 for r in judged if r["kind"] == "scoped" and r["outcome"] == "left out")},
        "no_answer": {"total": sum(1 for r in judged if r["kind"] == "no-answer"),
                      "kept": sum(1 for r in judged if r["kind"] == "no-answer" and r["outcome"] == "kept")},
        "ordinary_for_information": {"total": sum(1 for r in results if r["kind"] == "ordinary"),
                                     "kept": sum(1 for r in results if r["kind"] == "ordinary" and r["outcome"] == "kept")},
        "passes": all(r["as_expected"] for r in judged),
        "misses": [r["id"] for r in judged if not r["as_expected"]],
    }
    record = measurement_record.run_record(dump_sha256=arguments.dump_sha256, database=database, flm=None)  # this copy: FLM takes no part
    record["configuration"] = provider_record(settings)
    record.update({"kind": "D-108's development check of FR-19's permission exclusion",
                   "dev_sets": {p.name: measurement_record.file_sha256(p) for p in DEV_SETS},
                   "relevance_threshold": RELEVANCE_THRESHOLD, "asked_as": ASKER_ROLE,
                   "finished_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")})
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    (arguments.out_dir / "exclusion-dev-check.json").write_text(
        json.dumps({"record": record, "summary": summary, "results": results}, indent=2), encoding="utf-8")
    lines = ["# D-108's development check of FR-19's permission exclusion", "",
             f"Commit {record['commit_sha'][:7]}" + (" (uncommitted tracked changes)" if record["uncommitted_tracked_changes"] else "")
             + f", database {database}, dump {record['dump_sha256'][:8]}…, configuration {record['configuration']}, "  # this copy: no FLM version
             f"RELEVANCE_THRESHOLD {RELEVANCE_THRESHOLD}; every question asked as the {ASKER_ROLE}.", "",
             f"- Scoped questions left out: {summary['scoped']['left_out']} of {summary['scoped']['total']}",
             f"- No-answer questions kept: {summary['no_answer']['kept']} of {summary['no_answer']['total']}",
             f"- Ordinary questions kept (for information): {summary['ordinary_for_information']['kept']} of {summary['ordinary_for_information']['total']}",
             f"- **{'PASS' if summary['passes'] else 'FAIL'}**; misses: {summary['misses'] or 'none'}", "",
             "| Set | Id | Kind | Outcome | Expected | Admitted | Top score | Top readable by the Employee | Question |",
             "|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['set']} | {r['id']} | {r['kind']} | {r['outcome']} | {r['expected']} | {r['admitted']} | {r['top_score']} | {r['top_readable_by_asker']} | {r['question']} |" for r in results]
    (arguments.out_dir / "exclusion-dev-check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[2:7]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
