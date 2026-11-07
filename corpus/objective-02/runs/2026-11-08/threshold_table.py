"""Step 7 phase 2b: the per-run score tables in threshold-floor.md, printed from the measurement.

Reads threshold_scores.json (written by threshold_scores.py) and, optionally, the end-to-end
JSONL (written by threshold_floor_e2e.py), and prints markdown. Reads nothing else and changes
nothing. Usage:

    python threshold_table.py threshold_scores.json [e2e/e2e_T4472_F4458_N6.jsonl]
"""

import json
import sys
from pathlib import Path

OLD_THRESHOLD = 0.3
THRESHOLD = 0.4472
FLOOR = 0.4458


def main() -> int:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    runs = data["runs"]

    print("Answerable runs (24): the best score of a passage of an expected source, in the ranked list.")
    print()
    print("| run | role | expected source | its best score | top item | lost at 0.3 | lost at 0.4472 | admitted at 0.3 / at 0.4472 |")
    print("|---|---|---|---|---|---|---|---|")
    answerable = [r for r in runs if r["expects_answer"]]
    for r in sorted(answerable, key=lambda r: min(x["expected_best"] for x in r["repeats"])):
        best = min(x["expected_best"] for x in r["repeats"])
        first = r["repeats"][0]
        scores = [p["score"] for p in first["ranked"]]
        print(f"| {r['run']} | {r['role']} | {', '.join(r['expected_sources'])} | {best:.6f} | {first['top_item']} | "
              f"{'yes' if best < OLD_THRESHOLD else 'no'} | {'yes' if best < THRESHOLD else 'no'} | "
              f"{sum(s >= OLD_THRESHOLD for s in scores)} / {sum(s >= THRESHOLD for s in scores)} |")

    print()
    print("No-answer runs (7): the top in-scope score, and the five items offered as partial matches before the floor.")
    print()
    print("| run | role | top score | declined at 0.3 | declined at 0.4472 | offered before the floor (item score) | offered at 0.4458 |")
    print("|---|---|---|---|---|---|---|")
    unanswerable = [r for r in runs if not r["expects_answer"]]
    for r in sorted(unanswerable, key=lambda r: max(x["top"] for x in r["repeats"])):
        top = max(x["top"] for x in r["repeats"])
        offers = r["repeats"][0]["partial_matches"]
        before = "; ".join(f"{m['item']} {m['score']:.6f}" for m in offers)
        after = "; ".join(f"{m['item']} {m['score']:.6f}" for m in offers if m["score"] >= FLOOR) or "none"
        print(f"| {r['run']} | {r['role']} | {top:.6f} | {'yes' if top < OLD_THRESHOLD else 'no'} | "
              f"{'yes' if top < THRESHOLD else 'no'} | {before} | {after} |")

    identical = all(r["vectors_identical"] for r in runs)
    spread = max(max(x["top"] for x in r["repeats"]) - min(x["top"] for x in r["repeats"]) for r in runs)
    print()
    print(f"Query vectors identical across the {data['repeats']} embeddings of every run: {identical}; "
          f"largest top-score spread: {spread:.6f}.")
    capped = [r["run"] for r in answerable
              if any(x["expected_best"] != x["expected_best_uncapped"] for x in r["repeats"])]
    print(f"Answerable runs where TOP_K cut the expected source's best passage: {capped or 'none'}.")

    if len(sys.argv) > 2:
        rows = [json.loads(l) for l in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines() if l.strip()]
        print()
        print("End to end, per run: outcome, passages supplied, partial matches the reply carried.")
        print()
        print("| run | expects | status | outcome | reason | supplied items | match | offered (item score) | without the floor |")
        print("|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            outcome = "answered" if r["answered"] else ("503" if r["status"] == 503 else "no answer")
            offered = "; ".join(f"{o['item']} {o['score']:.6f}" for o in r["partial_matches_offered"]) or "none"
            unfloored = "; ".join(f"{o['item']} {o['score']:.6f}" for o in r["partial_matches_unfloored"]) \
                if not r["answered"] else "(answered: none offered)"
            supplied = ", ".join(sorted(set(i for i in (r["supplied_items"] or []) if i))) or "-"
            print(f"| {r['run']} | {'answer' if r['expects_answer'] else 'none'} | {r['status']} | {outcome} | "
                  f"{r['no_answer_reason'] or '-'} | {supplied} | {'yes' if r['match'] else '-'} | {offered} | {unfloored} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
