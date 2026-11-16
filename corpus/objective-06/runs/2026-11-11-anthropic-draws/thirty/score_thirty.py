"""Score the frozen thirty's three anthropic draws for FR-12, by plan.md's rule (11 November 2026).

The draws are the Objectives 05/06 session's, not this branch's (the user's decision of 11 November):

| Draw | Seeded at | Seed record | QueryLog export |
|---|---|---|---|
| 1 | `c3ac5b0`, #86 | corpus/objective-06/runs/2026-11-10-anthropic/seed/seed.json, added in `a773333` | corpus/objective-06/runs/2026-11-11-anthropic/draw-1/export.json, added in `854abda` (#90) |
| 2 | `462e8e9`, #90 | corpus/objective-06/runs/2026-11-11-anthropic/draw-2/seed/seed.json, `854abda` | .../draw-2/export.json, `854abda` |
| 3 | `462e8e9`, #90 | .../draw-3/seed/seed.json, `854abda` | .../draw-3/export.json, `854abda` |

Each export holds the seeded rows exactly as the pipeline wrote them, read from the database before
that draw's rows were cleared. For every ask, it gives answered, no_answer_reason, rejected_count and
the retrieved count; for every search, result_count. This script reads the files as committed, through
``git show <commit>:<path>``, so it reads the same bytes whichever PR merges first. It records each
blob's SHA-256, writes scores.json and scores.md beside itself, calls nothing and needs no database::

    .venv\\Scripts\\python.exe corpus\\objective-06\\runs\\2026-11-11-anthropic-draws\\thirty\\score_thirty.py

The rule (plan.md, committed before any draw of this branch):
- an unanswerable ask passes when no statement survives verification: path A (no_relevant_passage)
  or path B (no_statement_verified). Path B is split by rejected_count into the model proposing
  nothing (0) and verification rejecting what it proposed (more than 0). A surviving statement fails;
- an answerable ask passes when it is answered with citations: answered, at least one verified
  statement in the seed record, and rejected_count 0;
- a permission-only ask passes on a no-answer;
- a search passes with results for an answerable term, and with none for an unanswerable or a
  permission-only term.

Beside them, for comparison: FLM's 10 November seeding of the same thirty
(corpus/objective-06/runs/2026-11-10/seed/seed.json, `45d5c25`). Its seed record gives answered or
not; D-110's evening note gives its paths.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[4]  # corpus/objective-06/runs/2026-11-11-anthropic-draws/<this folder>
RUN_90 = "corpus/objective-06/runs/2026-11-11-anthropic"
DRAWS = [
    {"draw": 1, "seeded_at": "c3ac5b0",
     "seed": ("a773333", "corpus/objective-06/runs/2026-11-10-anthropic/seed/seed.json"),
     "export": ("854abda", f"{RUN_90}/draw-1/export.json")},
    {"draw": 2, "seeded_at": "462e8e9",
     "seed": ("854abda", f"{RUN_90}/draw-2/seed/seed.json"),
     "export": ("854abda", f"{RUN_90}/draw-2/export.json")},
    {"draw": 3, "seeded_at": "462e8e9",
     "seed": ("854abda", f"{RUN_90}/draw-3/seed/seed.json"),
     "export": ("854abda", f"{RUN_90}/draw-3/export.json")},
]
FLM_SEED = ("45d5c25", "corpus/objective-06/runs/2026-11-10/seed/seed.json")
FROZEN = "e40a589c91893be6cca1ccd77d175571df8090d51d9ebdcaadade95be4dc1462"  # queries.json, D-110
PATH_A, PATH_B = "no_relevant_passage", "no_statement_verified"


def blob(commit: str, path: str) -> tuple[dict, str]:
    raw = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPOSITORY_ROOT, check=True,
                         capture_output=True).stdout
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def ask_outcome(row: dict) -> str:
    if row["answered"]:
        return "answered"
    if row["no_answer_reason"] == PATH_A:
        return "A"
    if row["no_answer_reason"] == PATH_B:
        return "B, none proposed" if row["rejected_count"] == 0 else "B, all rejected"
    return f"unknown ({row['no_answer_reason']})"


def main() -> int:
    problems: list[str] = []
    draws = []
    for spec in DRAWS:
        seed, seed_hash = blob(*spec["seed"])
        export, export_hash = blob(*spec["export"])
        record = seed["record"]
        seeded = {r["id"]: r for r in seed["results"]}
        if record["commit_sha"][:7] != spec["seeded_at"]:
            problems.append(f"draw {spec['draw']}: seeded at {record['commit_sha'][:7]}, not {spec['seeded_at']}")
        if record["query_set_sha256"] != FROZEN:
            problems.append(f"draw {spec['draw']}: the query set is {record['query_set_sha256'][:8]}, not the frozen file")
        if export["seed_record"]["commit_sha"] != record["commit_sha"]:
            problems.append(f"draw {spec['draw']}: the export names a different seeding commit")
        # The export names the seed record by hash: draw 1's as committed (LF), draws 2 and 3 as the
        # seeding wrote them on Windows (CRLF). Either form identifies the committed file.
        raw = subprocess.run(["git", "show", f"{spec['seed'][0]}:{spec['seed'][1]}"], cwd=REPOSITORY_ROOT,
                             check=True, capture_output=True).stdout
        forms = {hashlib.sha256(raw).hexdigest(): "LF, as committed",
                 hashlib.sha256(raw.replace(b"\n", b"\r\n")).hexdigest(): "CRLF, as written on Windows"}
        named = forms.get(export["seed_record"]["sha256"])
        if named is None:
            problems.append(f"draw {spec['draw']}: the export's seed hash matches neither form of the committed seed record")

        asks = []
        for row in export["asks"]:
            seeded_row = seeded[row["id"]]
            if seeded_row.get("answered") != row["answered"]:
                problems.append(f"draw {spec['draw']} {row['id']}: the seed record and the export disagree on answered")
            outcome = ask_outcome(row)
            verified = seeded_row.get("statements", 0)
            if row["kind"] == "answerable":
                passed = row["answered"] and verified >= 1 and row["rejected_count"] == 0
            else:
                passed = not row["answered"]
            asks.append({"id": row["id"], "kind": row["kind"], "role": row["role"], "outcome": outcome,
                         "no_answer_reason": row["no_answer_reason"], "rejected_count": row["rejected_count"],
                         "retrieved": row["retrieved"], "verified_statements": verified, "passed": passed})
        searches = []
        for row in export["searches"]:
            passed = row["result_count"] > 0 if row["kind"] == "answerable" else row["result_count"] == 0
            searches.append({"id": row["id"], "kind": row["kind"], "role": row["role"],
                             "result_count": row["result_count"], "passed": passed})
        if len(asks) != 21 or len(searches) != 9:
            problems.append(f"draw {spec['draw']}: {len(asks)} asks and {len(searches)} searches, not 21 and 9")

        summary = {}
        for kind in ("answerable", "unanswerable", "permission-only"):
            rows = [a for a in asks if a["kind"] == kind]
            summary[kind] = {
                "asks": len(rows), "passed": sum(a["passed"] for a in rows),
                "answered": sum(a["outcome"] == "answered" for a in rows),
                "path_a": sum(a["outcome"] == "A" for a in rows),
                "path_b_none_proposed": sum(a["outcome"] == "B, none proposed" for a in rows),
                "path_b_all_rejected": sum(a["outcome"] == "B, all rejected" for a in rows),
                "rejected_total": sum(a["rejected_count"] or 0 for a in rows),
                "searches": sum(1 for s in searches if s["kind"] == kind),
                "searches_passed": sum(s["passed"] for s in searches if s["kind"] == kind),
            }
        draws.append({
            "draw": spec["draw"],
            "seed": {"commit": spec["seed"][0], "path": spec["seed"][1], "sha256": seed_hash},
            "export": {"commit": spec["export"][0], "path": spec["export"][1], "sha256": export_hash,
                       "seed_hash_form": named},
            "seeded_at": record["commit_sha"], "uncommitted_tracked_changes": record["uncommitted_tracked_changes"],
            "started_at": record["started_at"], "database": record["database"], "dump_sha256": record["dump_sha256"],
            "query_set_sha256": record["query_set_sha256"], "configuration": record["configuration"],
            "claude_usage": record["claude_usage"], "asks": asks, "searches": searches, "summary": summary,
        })

    flm_seed, flm_hash = blob(*FLM_SEED)
    flm = {"seed": {"commit": FLM_SEED[0], "path": FLM_SEED[1], "sha256": flm_hash},
           "seeded_at": flm_seed["record"]["commit_sha"],
           "answered": {r["id"]: r.get("answered") for r in flm_seed["results"] if r["via"] == "ask"},
           "searches": {r["id"]: r.get("result_count") for r in flm_seed["results"] if r["via"] == "search"}}

    totals = {kind: {key: sum(d["summary"][kind][key] for d in draws) for key in draws[0]["summary"][kind]}
              for kind in draws[0]["summary"]}
    usage = {key: sum(d["claude_usage"][key] for d in draws) for key in ("calls", "input_tokens", "output_tokens")}
    usage["estimated_usd"] = round(sum(d["claude_usage"]["estimated_usd"] for d in draws), 4)
    result = {"draws": draws, "flm_seeding": flm, "totals": totals, "claude_usage_total": usage, "problems": problems}
    (HERE / "scores.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = ["# The frozen thirty's three anthropic draws, scored for FR-12", "",
             "Written by `score_thirty.py` from the Objectives 05/06 session's committed seed records and "
             "QueryLog exports, by `../plan.md`'s rule. Generated, not edited by hand.", "",
             f"Consistency checks: {'none failed' if not problems else '; '.join(problems)}.", "",
             "## Per draw", "",
             "| Draw | Seeded at | Unanswerable asks: no-answer (A / B, none proposed / B, all rejected) | "
             "Permission-only asks: no-answer (A / B) | Answerable asks: answered with citations, none rejected | "
             "Searches as expected | Claude calls, tokens in / out, US$ |",
             "|---|---|---|---|---|---|---|"]
    for d in draws:
        u, p, a = d["summary"]["unanswerable"], d["summary"]["permission-only"], d["summary"]["answerable"]
        searches_ok = sum(d["summary"][k]["searches_passed"] for k in d["summary"])
        searches_all = sum(d["summary"][k]["searches"] for k in d["summary"])
        c = d["claude_usage"]
        lines.append(
            f"| {d['draw']} | `{d['seeded_at'][:7]}` | {u['passed']} of {u['asks']} ({u['path_a']} / "
            f"{u['path_b_none_proposed']} / {u['path_b_all_rejected']}) | {p['passed']} of {p['asks']} "
            f"({p['path_a']} / {p['path_b_none_proposed'] + p['path_b_all_rejected']}) | {a['passed']} of {a['asks']} | "
            f"{searches_ok} of {searches_all} | {c['calls']}, {c['input_tokens']:,} / {c['output_tokens']:,}, "
            f"{c['estimated_usd']:.4f} |")
    u, p, a = totals["unanswerable"], totals["permission-only"], totals["answerable"]
    searches_ok = sum(totals[k]["searches_passed"] for k in totals)
    searches_all = sum(totals[k]["searches"] for k in totals)
    lines.append(
        f"| **total** | | **{u['passed']} of {u['asks']}** ({u['path_a']} / {u['path_b_none_proposed']} / "
        f"{u['path_b_all_rejected']}) | **{p['passed']} of {p['asks']}** ({p['path_a']} / "
        f"{p['path_b_none_proposed'] + p['path_b_all_rejected']}) | **{a['passed']} of {a['asks']}** | "
        f"{searches_ok} of {searches_all} | {usage['calls']}, {usage['input_tokens']:,} / "
        f"{usage['output_tokens']:,}, {usage['estimated_usd']:.4f} |")
    lines += ["", "## Per ask, beside FLM's 10 November seeding", "",
              "A: no passage cleared voyage-4's 0.2687, so generation was not called. B: generation ran and no "
              "statement survived. Retrieved is the number of passages the row records.", "",
              "| Id | Kind | Role | anthropic, outcome in each draw | rejected_count | Retrieved | FLM (embed-gemma, gemma3:4b) |",
              "|---|---|---|---|---|---|---|"]
    for index, ask in enumerate(draws[0]["asks"]):
        rows = [d["asks"][index] for d in draws]
        assert all(r["id"] == ask["id"] for r in rows)
        outcomes = [r["outcome"] for r in rows]
        outcome_text = (f"{outcomes[0]}, all {len(outcomes)}" if len(set(outcomes)) == 1 else ", ".join(outcomes))
        rejected = sorted({str(r["rejected_count"]) if r["rejected_count"] is not None else "null" for r in rows})
        retrieved = sorted({r["retrieved"] for r in rows})
        flm_answered = flm["answered"].get(ask["id"])
        lines.append(f"| {ask['id']} | {ask['kind']} | {ask['role']} | {outcome_text} | {', '.join(rejected)} | "
                     f"{', '.join(map(str, retrieved))} | {'answered' if flm_answered else 'no-answer'} |")
    lines += ["", "## Searches", "", "| Id | Kind | Role | result_count in each draw | FLM |", "|---|---|---|---|---|"]
    for index, search in enumerate(draws[0]["searches"]):
        counts = [d["searches"][index]["result_count"] for d in draws]
        lines.append(f"| {search['id']} | {search['kind']} | {search['role']} | {', '.join(map(str, counts))} | "
                     f"{flm['searches'].get(search['id'])} |")
    lines.append("")
    (HERE / "scores.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
