"""Step 7 phase 2b: the per-run score tables in threshold-floor.md, printed from the measurement.

Reads threshold_scores.json (written by threshold_scores.py) and, optionally, an end-to-end JSONL
(written by threshold_floor_e2e.py), and prints markdown. Reads nothing else and changes nothing.

The defaults are the literal rule's values (threshold 0.4472, floor 0.4458, no margin). The
margin rule's tables are printed with ``--threshold 0.4231 --floor 0.4036 --margin 0.006``:
then an answerable run is "lost" when its expected source scores below T + m, and a no-answer
run is "declined" when its top score is at most T - m. Usage:

    python threshold_table.py threshold_scores.json [e2e/e2e_<label>.jsonl]
    python threshold_table.py threshold_scores.json e2e-margin/e2e_T4231_F4036_N6.jsonl \\
        --threshold 0.4231 --floor 0.4036 --margin 0.006
"""

import argparse
import json
import sys
from pathlib import Path

OLD_THRESHOLD = 0.3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scores")
    parser.add_argument("e2e", nargs="?")
    parser.add_argument("--threshold", type=float, default=0.4472)
    parser.add_argument("--floor", type=float, default=0.4458)
    parser.add_argument("--margin", type=float, default=0.0)
    args = parser.parse_args()
    t, f, m = args.threshold, args.floor, args.margin
    data = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    runs = data["runs"]
    lost_label = f"lost at {t}" + (f" with margin {m}" if m else "")
    declined_label = f"declined at {t}" + (f" with margin {m}" if m else "")

    print("Answerable runs (24): the best score of a passage of an expected source, in the ranked list.")
    print()
    print(f"| run | role | expected source | its best score | top item | lost at 0.3 | {lost_label} | admitted at 0.3 / at {t} |")
    print("|---|---|---|---|---|---|---|---|")
    answerable = [r for r in runs if r["expects_answer"]]
    for r in sorted(answerable, key=lambda r: min(x["expected_best"] for x in r["repeats"])):
        best = min(x["expected_best"] for x in r["repeats"])
        first = r["repeats"][0]
        scores = [p["score"] for p in first["ranked"]]
        print(f"| {r['run']} | {r['role']} | {', '.join(r['expected_sources'])} | {best:.6f} | {first['top_item']} | "
              f"{'yes' if best < OLD_THRESHOLD else 'no'} | {'yes' if best < t + m else 'no'} | "
              f"{sum(s >= OLD_THRESHOLD for s in scores)} / {sum(s >= t for s in scores)} |")

    print()
    print("No-answer runs (7): the top in-scope score, and the five items offered as partial matches before the floor.")
    print()
    print(f"| run | role | top score | declined at 0.3 | {declined_label} | path A at {t} | offered before the floor (item score) | offered at {f} |")
    print("|---|---|---|---|---|---|---|---|")
    unanswerable = [r for r in runs if not r["expects_answer"]]
    for r in sorted(unanswerable, key=lambda r: max(x["top"] for x in r["repeats"])):
        top = max(x["top"] for x in r["repeats"])
        offers = r["repeats"][0]["partial_matches"]
        before = "; ".join(f"{o['item']} {o['score']:.6f}" for o in offers)
        after = "; ".join(f"{o['item']} {o['score']:.6f}" for o in offers if o["score"] >= f) or "none"
        if top >= t:
            after += " (only if path B)"
        print(f"| {r['run']} | {r['role']} | {top:.6f} | {'yes' if top < OLD_THRESHOLD else 'no'} | "
              f"{'yes' if top <= t - m else 'no'} | {'yes' if top < t else 'no'} | {before} | {after} |")

    identical = all(r["vectors_identical"] for r in runs)
    spread = max(max(x["top"] for x in r["repeats"]) - min(x["top"] for x in r["repeats"]) for r in runs)
    print()
    print(f"Query vectors identical across the {data['repeats']} embeddings of every run: {identical}; "
          f"largest top-score spread: {spread:.6f}.")
    capped = [r["run"] for r in answerable
              if any(x["expected_best"] != x["expected_best_uncapped"] for x in r["repeats"])]
    print(f"Answerable runs where TOP_K cut the expected source's best passage: {capped or 'none'}.")

    if args.e2e:
        rows = [json.loads(l) for l in Path(args.e2e).read_text(encoding="utf-8").splitlines() if l.strip()]
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
