"""D-108's development check: does the permission exclusion leave out what it should, and only that?

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

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for entry in (str(REPOSITORY_ROOT / "scripts"), str(REPOSITORY_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import check_flm  # noqa: E402
import measurement_record  # noqa: E402

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
    print("FLM gate: scripts/check_flm.py's checks (D-83)")
    checks = check_flm.run_checks(settings.FLM_BASE_URL, settings.FLM_API_KEY, settings.FLM_CHAT_MODEL, settings.FLM_EMBED_MODEL)
    if not check_flm.checks_passed(checks):
        print("REFUSED: FLM checks failed")
        return 2
    version = check_flm.flm_version(settings.FLM_BASE_URL, settings.FLM_API_KEY)
    if version.problems():
        print("REFUSED: " + "; ".join(version.problems()))
        return 2

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
            admitted = admit(ranked)
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
    record = measurement_record.run_record(dump_sha256=arguments.dump_sha256, database=database, flm=version.as_record())
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
             + f", database {database}, dump {record['dump_sha256'][:8]}…, FLM {version.summary()}, configuration {record['configuration']}, "
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
