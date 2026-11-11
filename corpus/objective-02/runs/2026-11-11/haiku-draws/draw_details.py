"""Details of the three Haiku draws that the write-up quotes. Written AFTER the draws; it applies no bar.

compare_draws.py holds the rule and was committed before draw 2. This file only describes what
the three records hold, for haiku-draws.md's results section:

- per follow-up asked with history: the items cited in each draw, and where the expected source
  ranked;
- the runs that were answered where the frozen prediction is "not correct" (the cold runs), per
  draw, since answering an underspecified question is the risk haiku-round.md watched;
- which runs' verified statements differ between draws, by way;
- every run supplied the same passages in another order, with the two orders;
- the largest score differences between draws.

It calls nothing: no provider, no database. Usage, from anywhere:
    python draw_details.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECORDS = (
    ("draw 1", HERE.parent.parent / "2026-11-10" / "haiku" / "threads.json"),
    ("draw 2", HERE.parent / "haiku-draw-2" / "threads.json"),
    ("draw 3", HERE.parent / "haiku-draw-3" / "threads.json"),
)


def main() -> int:
    draws = [(name, {run["run_id"]: run for run in json.loads(path.read_text(encoding="utf-8"))["runs"]})
             for name, path in RECORDS]
    run_ids = list(draws[0][1])

    print("WITH HISTORY: items cited per draw (statements), expected source's rank, top supplied items")
    for run_id in run_ids:
        if not run_id.endswith("/with-history"):
            continue
        print(f"  {run_id}")
        for name, runs in draws:
            run = runs[run_id]
            cited = Counter(statement["item"] for statement in run["verified_statements"])
            cited_text = ", ".join(f"{item} x{count}" for item, count in cited.items()) or "nothing (declined)"
            supplied = ", ".join(f"{p['item']} {p['score']:.4f}" for p in run["retrieved"][:4])
            print(f"    {name}: cited {cited_text}; expected {run['sources']} at rank {run['source_rank']}; "
                  f"supplied first: {supplied}")

    print("\nCOLD: the runs that were answered (a cold follow-up is predicted not correct, t08 apart)")
    for run_id in run_ids:
        if not run_id.endswith("/cold"):
            continue
        outcomes = [runs[run_id]["score"]["outcome"] for _, runs in draws]
        if "answered" in outcomes:
            cited = [", ".join(sorted({s["item"] for s in runs[run_id]["verified_statements"]})) or "-" for _, runs in draws]
            correct = ["correct" if runs[run_id]["score"]["correct"] else "not correct" for _, runs in draws]
            print(f"  {run_id}: {' | '.join(outcomes)}; cited {' | '.join(cited)}; {' | '.join(correct)}")

    print("\nVERIFIED STATEMENTS: runs whose text or count differs between draws, by way")
    by_way: Counter = Counter()
    totals: Counter = Counter()
    for run_id in run_ids:
        way = run_id.rsplit("/", 1)[1]
        totals[way] += 1
        texts = {json.dumps([[s["chunk_id"], s["text"]] for s in runs[run_id]["verified_statements"]])
                 for _, runs in draws}
        cited = {frozenset(s["chunk_id"] for s in runs[run_id]["verified_statements"]) for _, runs in draws}
        if len(texts) > 1:
            by_way[way] += 1
            if len(cited) > 1:
                by_way[way + ", and the cited passages differ too"] += 1
    for way in ("first-turn", "with-history", "spelled-out", "cold"):
        print(f"  {way}: {by_way[way]} of {totals[way]} differ in wording or count; "
              f"{by_way[way + ', and the cited passages differ too']} of those cite a different set of passages")

    print("\nSUPPLIED PASSAGES: runs with the same set in another order")
    for run_id in run_ids:
        orders = [[p["chunk_id"] for p in runs[run_id]["retrieved"]] for _, runs in draws]
        if len({tuple(order) for order in orders}) > 1 and len({frozenset(order) for order in orders}) == 1:
            print(f"  {run_id}")
            for name, runs in draws:
                print(f"    {name}: " + ", ".join(f"{p['item']}:{p['chunk_id'][:8]} {p['score']:.5f}"
                                                 for p in runs[run_id]["retrieved"]))

    print("\nSCORES: the five largest differences for one passage in one run, across the three draws")
    spreads = []
    for run_id in run_ids:
        scores: dict[str, list[float]] = {}
        for _, runs in draws:
            for passage in runs[run_id]["retrieved"]:
                scores.setdefault(f"{passage['item']}:{passage['chunk_id'][:8]}", []).append(passage["score"])
        for chunk, values in scores.items():
            if len(values) == len(draws):
                spreads.append((max(values) - min(values), run_id, chunk, values))
    spreads.sort(reverse=True)
    for spread, run_id, chunk, values in spreads[:5]:
        print(f"  {spread:.5f}  {run_id}  {chunk}  " + "  ".join(f"{value:.5f}" for value in values))
    between_new = max((abs(values[1] - values[2]) for _, _, _, values in spreads), default=0.0)
    print(f"  largest difference between draws 2 and 3 alone, made two minutes apart: {between_new:.5f}")
    print(f"  passages compared: {len(spreads)}")

    print("\nSCORES: runs in which every supplied passage has exactly the same score in two draws")
    for first, second in ((0, 1), (1, 2), (0, 2)):
        identical = with_passages = 0
        for run_id in run_ids:
            a = [(p["chunk_id"], p["score"]) for p in draws[first][1][run_id]["retrieved"]]
            b = [(p["chunk_id"], p["score"]) for p in draws[second][1][run_id]["retrieved"]]
            if a or b:
                with_passages += 1
                identical += a == b
        print(f"  {draws[first][0]} and {draws[second][0]}: {identical} of the {with_passages} runs that were supplied a passage")

    print("\nTOP SCORES: the seven cold runs that stopped before generation (path A), top score per draw, threshold 0.2687")
    for run_id in run_ids:
        if all(runs[run_id]["score"]["outcome"] == "path-A" for _, runs in draws):
            print(f"  {run_id}: " + "  ".join(f"{runs[run_id]['top_score']:.4f}" for _, runs in draws))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
