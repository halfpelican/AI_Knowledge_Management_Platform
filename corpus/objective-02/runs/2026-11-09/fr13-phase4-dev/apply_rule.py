"""Apply the fixed phase-4 adoption rule to the six dev draws. Pure read; no model, no DB.

Means over 3 draws per arm. Adopt option 3 only if:
- its mean with-history expected-answer match exceeds main's by MORE THAN 2 runs;
- no guard arm's mean (first-turn match, spelled-out match, correct declines) is lower
  by more than 1 run;
- schema conformance intact (no draw below 100% is "intact" only if the misses are the
  band's own: reported, judged by the reader — the rule says intact, so every
  non-conforming response is printed);
- 0 out-of-scope in every draw of both arms.

Cold ran once per arm (draw 1), diagnostic only; it is reported, not ruled on.
Usage: python apply_rule.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("main", "option3")
DRAWS = (1, 2, 3)
GUARDS = ("first_turn_match", "spelled_out_match", "correct_declines")


def load(arm: str, draw: int) -> dict:
    record = json.loads((HERE / f"dev_{arm}_draw{draw}.json").read_text(encoding="utf-8"))
    assert record["limit"] == 0, f"{arm} draw {draw} was a limited run, not rule evidence"
    assert record["arm"] == arm and record["draw"] == draw
    return record


def main() -> int:
    records = {(arm, draw): load(arm, draw) for arm in ARMS for draw in DRAWS}
    means: dict[str, dict[str, float]] = {}
    print("per-draw rule numbers (matched/of):")
    for arm in ARMS:
        values: dict[str, list[int]] = {}
        for draw in DRAWS:
            numbers = records[(arm, draw)]["rule_numbers"]
            line = ", ".join(
                f"{key} {numbers[key][0]}/{numbers[key][1]}"
                for key in ("with_history_match", *GUARDS)
            )
            cold = numbers.get("cold_match")
            rewrites = records[(arm, draw)]["summary"].get("rewrites_used")
            print(f"  {arm} draw {draw}: {line}"
                  + (f", cold {cold[0]}/{cold[1]}" if cold else "")
                  + f", schema {numbers['schema_conformance'][0]}/{numbers['schema_conformance'][1]}"
                  + f", out-of-scope {numbers['out_of_scope']}"
                  + (f", rewrites used {rewrites[0]}/{rewrites[1]}" if rewrites else ""))
            for key in ("with_history_match", *GUARDS):
                values.setdefault(key, []).append(numbers[key][0])
        means[arm] = {key: statistics.mean(draws) for key, draws in values.items()}

    print("\nmeans over the three draws:")
    for arm in ARMS:
        print("  " + arm + ": " + ", ".join(f"{k} {v:.2f}" for k, v in means[arm].items()))

    gain = means["option3"]["with_history_match"] - means["main"]["with_history_match"]
    guard_drops = {g: means["main"][g] - means["option3"][g] for g in GUARDS}
    out_of_scope = sum(r["rule_numbers"]["out_of_scope"] for r in records.values())
    conformance_misses = [
        (arm, draw, r["rule_numbers"]["schema_conformance"])
        for (arm, draw), r in records.items()
        if r["rule_numbers"]["schema_conformance"][0] != r["rule_numbers"]["schema_conformance"][1]
    ]
    fallbacks = []
    rewrite_seconds = []
    for draw in DRAWS:
        entries = records[("option3", draw)]["rewrites"]
        fallbacks.append([sum(not e["used"] for e in entries), len(entries)])
        rewrite_seconds += [e["seconds"] for e in entries if e["used"]]

    print(f"\nwith-history gain (option3 - main): {gain:+.2f} runs (rule needs > 2)")
    for guard, drop in guard_drops.items():
        print(f"guard {guard}: option3 mean lower by {drop:+.2f} (rule allows at most 1)")
    print(f"out-of-scope, all draws, both arms: {out_of_scope} (rule needs 0)")
    print(f"conformance misses: {conformance_misses or 'none'}")
    print(f"rewrite fallbacks per option3 draw: {fallbacks}")
    if rewrite_seconds:
        ordered = sorted(rewrite_seconds)
        print(f"rewrite seconds over {len(ordered)} used: min {ordered[0]:.1f}, median "
              f"{ordered[len(ordered) // 2]:.1f}, p90 {ordered[int(len(ordered) * 0.9)]:.1f}, "
              f"max {ordered[-1]:.1f}")

    adopt = (
        gain > 2
        and all(drop <= 1 for drop in guard_drops.values())
        and not conformance_misses
        and out_of_scope == 0
    )
    print(f"\nRULE: {'ADOPT option 3' if adopt else 'DO NOT ADOPT (the rule was not met)'}")
    return 0


if __name__ == "__main__":
    main()
