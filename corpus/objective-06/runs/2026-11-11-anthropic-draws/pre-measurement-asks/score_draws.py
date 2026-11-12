"""Score the five harness draws of pre-measurement-asks.json for FR-12, by plan.md's rule (11 November 2026).

Reads only the committed records: this folder's draw-*/harness.json, and FLM's 8 November
pre-measurement (corpus/objective-06/runs/2026-11-08/pre-measurement/run1.json and run2.json)
for comparison. It calls nothing and needs no database. It writes scores.json and scores.md
beside itself::

    .venv\\Scripts\\python.exe corpus\\objective-06\\runs\\2026-11-11-anthropic-draws\\pre-measurement-asks\\score_draws.py

The rule (plan.md, committed before any draw):
- first, no leak: ``out_of_scope_ids`` empty, and ``expected_answer_found`` not true for an
  Employee's permission-only ask;
- an unanswerable ask passes when no statement survives verification. It is path A where
  generation was not called, and path B where it was. Path B is split into the model proposing
  nothing, and verification rejecting what it proposed. Any surviving cited statement fails;
- a permission-only ask asked by the Employee passes on a no-answer. An answer from readable
  material is reported with the items cited, and counts against the decline;
- a run that ended in an error is reported and left out of its draw's denominators.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[4]  # corpus/objective-06/runs/2026-11-11-anthropic-draws/<this folder>
FLM_RUNS = [REPOSITORY_ROOT / "corpus/objective-06/runs/2026-11-08/pre-measurement" / name
            for name in ("run1.json", "run2.json")]
KINDS = {"no-answer": "unanswerable", "scoped": "permission-only"}


def outcome(run: dict) -> str:
    """One run's FR-12 outcome, by plan.md's rule."""
    if run.get("error"):
        return "error"
    if run["answered"]:
        return "answered"
    if not run["generation_called"]:
        return "A"
    if run["fabricated_ids"]:
        return "B, all rejected"
    return "B, none proposed" if not run["statements"] else "B, other"


def leaks(run: dict) -> list[str]:
    problems = []
    if run["out_of_scope_ids"]:
        problems.append(f"out-of-scope ids {run['out_of_scope_ids']}")
    if run["kind"] == "scoped" and run["role"] == "Employee" and run.get("expected_answer_found"):
        problems.append("the restricted expected answer was shown")
    return problems


def cited_items(run: dict) -> list[str]:
    return sorted({s.get("item") or s["chunk_id"] for s in run["verified_statements"]})


def main() -> int:
    draw_files = sorted(HERE.glob("draw-*/harness.json"), key=lambda p: int(p.parent.name.split("-")[1]))
    if not draw_files:
        print("no draws found")
        return 2
    draws = []
    for path in draw_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = payload["record"]
        runs = payload["results"]
        per_run = []
        for run in runs:
            per_run.append({
                "id": run["id"], "kind": KINDS[run["kind"]], "role": run["role"],
                "top_score": run["top_score"], "admitted": len(run["retrieved"]),
                "outcome": outcome(run), "statements_proposed": len(run["statements"]),
                "statements_verified": len(run["verified_statements"]),
                "fabricated_ids": len(run["fabricated_ids"]), "cited_items": cited_items(run),
                "leaks": leaks(run),
            })
        summary = {}
        for kind in ("unanswerable", "permission-only"):
            rows = [r for r in per_run if r["kind"] == kind and r["outcome"] != "error"]
            summary[kind] = {
                "runs": len(rows),
                "no_answer": sum(1 for r in rows if r["outcome"] != "answered"),
                "path_a": sum(1 for r in rows if r["outcome"] == "A"),
                "path_b_none_proposed": sum(1 for r in rows if r["outcome"] == "B, none proposed"),
                "path_b_all_rejected": sum(1 for r in rows if r["outcome"] == "B, all rejected"),
                "answered": sum(1 for r in rows if r["outcome"] == "answered"),
                "errors": sum(1 for r in per_run if r["kind"] == kind and r["outcome"] == "error"),
            }
        draws.append({
            "draw": path.parent.name,
            "file": str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
            "commit_sha": record["commit_sha"],
            "uncommitted_tracked_changes": record["uncommitted_tracked_changes"],
            "recorded_at": record["recorded_at"],
            "database": record["database"],
            "dump_sha256": record["dump_sha256"],
            "question_set_sha256": record["question_set_sha256"],
            "corpus_problems": record.get("corpus_problems"),
            "configuration": record["provider_record"],
            "claude_usage": payload["claude_usage"],
            "runs": per_run,
            "summary": summary,
            "leaks": [f"{r['id']}: {problem}" for r in per_run for problem in r["leaks"]],
        })

    flm = []
    for path in FLM_RUNS:
        payload = json.loads(path.read_text(encoding="utf-8"))
        flm.append({"file": str(path.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
                    "configuration": {"provider": payload["provider"], "chat_model": payload["chat_model"],
                                      "embed_model": payload["embed_model"],
                                      "threshold": payload["constants"]["RELEVANCE_THRESHOLD"]},
                    "runs": {run["id"]: {"top_score": run["top_score"], "outcome": outcome(run),
                                         "cited_items": cited_items(run)} for run in payload["results"]}})

    ids = [r["id"] for r in draws[0]["runs"]]
    totals = {}
    for kind in ("unanswerable", "permission-only"):
        totals[kind] = {key: sum(d["summary"][kind][key] for d in draws)
                        for key in draws[0]["summary"][kind]}
    usage = {key: sum(d["claude_usage"][key] for d in draws)
             for key in ("calls", "input_tokens", "output_tokens", "estimated_usd")}
    usage["estimated_usd"] = round(usage["estimated_usd"], 4)
    result = {"draws": draws, "flm_pre_measurement": flm, "totals": totals, "claude_usage_total": usage,
              "all_leaks": [leak for d in draws for leak in d["leaks"]]}
    (HERE / "scores.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    # The tables.
    threshold = draws[0]["configuration"]["threshold"]
    lines = ["# The five harness draws of `pre-measurement-asks.json`, scored for FR-12", "",
             "Written by `score_draws.py` from the committed `draw-*/harness.json`, by `../plan.md`'s rule.",
             "Generated, not edited by hand.", "",
             "## Per draw", "",
             "| Draw | Commit | Unanswerable: no-answer (A / B, none proposed / B, all rejected) | "
             "Permission-only: no-answer (A / B) | Statements proposed / verified | Leaks | "
             "Claude calls, tokens in / out, US$ |",
             "|---|---|---|---|---|---|---|"]
    for d in draws:
        u, p = d["summary"]["unanswerable"], d["summary"]["permission-only"]
        proposed = sum(r["statements_proposed"] for r in d["runs"])
        verified = sum(r["statements_verified"] for r in d["runs"])
        c = d["claude_usage"]
        lines.append(
            f"| {d['draw']} | `{d['commit_sha'][:7]}` | {u['no_answer']} of {u['runs']} "
            f"({u['path_a']} / {u['path_b_none_proposed']} / {u['path_b_all_rejected']}) | "
            f"{p['no_answer']} of {p['runs']} ({p['path_a']} / {p['path_b_none_proposed'] + p['path_b_all_rejected']}) | "
            f"{proposed} / {verified} | {len(d['leaks'])} | "
            f"{c['calls']}, {c['input_tokens']:,} / {c['output_tokens']:,}, {c['estimated_usd']:.4f} |")
    u, p = totals["unanswerable"], totals["permission-only"]
    lines.append(
        f"| **total** | | **{u['no_answer']} of {u['runs']}** ({u['path_a']} / {u['path_b_none_proposed']} / "
        f"{u['path_b_all_rejected']}) | **{p['no_answer']} of {p['runs']}** ({p['path_a']} / "
        f"{p['path_b_none_proposed'] + p['path_b_all_rejected']}) | | {len(result['all_leaks'])} | "
        f"{usage['calls']}, {usage['input_tokens']:,} / {usage['output_tokens']:,}, {usage['estimated_usd']:.4f} |")
    lines += ["", f"## Per ask, beside FLM's 8 November pre-measurement", "",
              f"Top in-scope score over the asking role's readable chunks; voyage-4's threshold is {threshold}, "
              "embed-gemma's 0.30. Outcomes: A, no passage cleared the threshold; B, generation was called "
              "and no statement survived; answered, a cited statement survived.", "",
              "| Id | Kind | Role | voyage-4 top score, min to max over the draws | Passages admitted | "
              "anthropic, outcome in each draw | embed-gemma top score | FLM, both runs |",
              "|---|---|---|---|---|---|---|---|"]
    for ask in ids:
        rows = [next(r for r in d["runs"] if r["id"] == ask) for d in draws]
        scores = [r["top_score"] for r in rows]
        admitted = sorted({r["admitted"] for r in rows})
        outcomes = [r["outcome"] for r in rows]
        same = outcomes.count(outcomes[0]) == len(outcomes)
        outcome_text = f"{outcomes[0]}, all {len(outcomes)}" if same else ", ".join(outcomes)
        flm_runs = [f["runs"][ask] for f in flm]
        flm_outcomes = sorted({f["outcome"] for f in flm_runs})
        flm_text = " / ".join(flm_outcomes)
        cited = sorted({item for f in flm_runs for item in f["cited_items"]})
        if cited:
            flm_text += f" ({', '.join(cited)})"
        lines.append(
            f"| {ask} | {rows[0]['kind']} | {rows[0]['role']} | {min(scores):.4f} to {max(scores):.4f} | "
            f"{', '.join(map(str, admitted))} | {outcome_text} | {flm_runs[0]['top_score']:.4f} | {flm_text} |")
    lines += ["", "## Leaks", "", "None." if not result["all_leaks"] else "\n".join(f"- {x}" for x in result["all_leaks"]), ""]
    (HERE / "scores.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
