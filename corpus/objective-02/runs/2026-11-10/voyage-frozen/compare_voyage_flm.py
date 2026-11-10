"""D-113 (10 November 2026): the frozen thirty and the nine threads, Voyage beside FLM.

Reads the two records of each set and prints them side by side. Nothing is re-scored here:
every number is read from a record's own ``summary`` or ``results``/``runs``, as
scripts/citation_harness.py wrote it.

- FLM: corpus/objective-02/runs/2026-11-08/after-030/ (8 November, ``main`` at 19c98a8,
  threshold 0.30, no floor, cap 6, gemma3:4b and embed-gemma on kmp_obj02_20261101).
- Voyage: this folder (anthropic provider, voyage-4 and Claude Sonnet 5.5 on
  kmp_voyage_20261110, D-120's 0.2687 and 0.2468, cap 6).

Usage, from anywhere:  python compare_voyage_flm.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLM = HERE.parents[1] / "2026-11-08" / "after-030"


def load(folder: Path, name: str) -> dict:
    return json.loads((folder / name).read_text(encoding="utf-8"))


def fraction(pair) -> str:
    return f"{pair[0]}/{pair[1]}"


def seconds(timing: dict, key: str) -> str:
    entry = timing.get(key) or {}
    if not entry.get("n"):
        return "n/a"
    return f"{entry['median']:.1f} / {entry['p90']:.1f} s"


def thirty_table(flm: dict, voyage: dict) -> None:
    f, v = flm["summary"], voyage["summary"]
    rows = [
        ("ordinary answered correctly (expected answer shown)", "expected_answer_match"),
        ("ordinary left unanswered", "empty_answer_ordinary"),
        ("scoped, answered for the role that can see the source", "scoped_answered"),
        ("scoped, declined for the role that cannot", "scoped_empty"),
        ("no-answer questions declined", "no_answer_empty"),
        ("first-attempt conformance (responses)", "first_attempt_conformance"),
        ("schema conformance (responses)", "schema_conformance"),
        ("fabricated identifiers (of statements)", "fabricated_identifiers"),
    ]
    print("THE FROZEN THIRTY (34 runs)")
    print(f"  {'':<56} {'FLM, 8 Nov':>14} {'Voyage + Claude':>16}")
    for label, key in rows:
        print(f"  {label:<56} {fraction(f[key]):>14} {fraction(v[key]):>16}")
    for label, key in (("path A (nothing above the threshold)", "path_a"),
                       ("generation responses", "responses"),
                       ("call failures (503s)", "call_failures"),
                       ("leaks (out-of-scope chunks)", "leaks")):
        print(f"  {label:<56} {f[key]:>14} {v[key]:>16}")
    print(f"  {'answered question, median / p90':<56} "
          f"{seconds(f['timing_seconds'], 'per_answered_question'):>14} "
          f"{seconds(v['timing_seconds'], 'per_answered_question'):>16}")


def outcome(result: dict) -> str:
    if result.get("error") and not result.get("answered"):
        return "unavailable"
    if not result.get("generation_called"):
        return "path A"
    if not result.get("answered"):
        return "path B"
    if result.get("expects_answer"):
        return "correct" if result.get("expected_answer_found") else "answered, not the answer"
    return "answered (expected none)"


def right(result: dict) -> bool:
    if result.get("expects_answer"):
        return bool(result.get("expected_answer_found"))
    return not result.get("answered")


def thirty_runs(flm: dict, voyage: dict) -> None:
    by_id = {r["id"]: r for r in flm["results"]}
    print("\nPER RUN, WHERE THE TWO DIFFER (right = expected answer shown, or declined where none was expected)")
    print(f"  {'run':<18} {'expects':<8} {'FLM':<26} {'top':>6}   {'Voyage':<26} {'top':>6}")
    changed = 0
    for v in voyage["results"]:
        f = by_id.get(v["id"])
        if f is None:
            print(f"  {v['id']:<18} not in the FLM record")
            continue
        if right(f) == right(v) and outcome(f) == outcome(v):
            continue
        changed += 1
        expects = "answer" if v["expects_answer"] else "none"
        f_top = "-" if f["top_score"] is None else f"{f['top_score']:.3f}"
        v_top = "-" if v["top_score"] is None else f"{v['top_score']:.3f}"
        print(f"  {v['id']:<18} {expects:<8} {outcome(f):<26} {f_top:>6}   {outcome(v):<26} {v_top:>6}")
    print(f"  {changed} run(s) differ; FLM right {sum(right(r) for r in flm['results'])}/{len(flm['results'])}, "
          f"Voyage right {sum(right(r) for r in voyage['results'])}/{len(voyage['results'])}")


def threads_table(flm: dict, voyage: dict) -> None:
    print("\nTHE NINE THREADS (44 runs: 11 first turns, 11 follow-ups three ways)")
    print(f"  {'way':<13} {'measure':<34} {'FLM, 8 Nov':>12} {'Voyage + Claude':>16}")
    for way in ("first-turn", "with-history", "cold", "spelled-out"):
        f, v = flm["summary"]["per_way"][way], voyage["summary"]["per_way"][way]
        for label, key in (("expected-answer match", "expected_answer_match"),
                           ("correct (scoring rule)", "correct"),
                           ("first-attempt conformance", "first_attempt_conformance"),
                           ("fabricated identifiers", "fabricated_identifiers")):
            print(f"  {way:<13} {label:<34} {fraction(f[key]):>12} {fraction(v[key]):>16}")
        print(f"  {way:<13} {'path A':<34} {f['outcomes']['path-A']:>12} {v['outcomes']['path-A']:>16}")
        print(f"  {way:<13} {'out of scope':<34} {f['out_of_scope']:>12} {v['out_of_scope']:>16}")
    print("\n  READINGS PER FOLLOW-UP")
    f_readings = {r["follow_up"]: r for r in flm["summary"]["readings"]}
    for r in voyage["summary"]["readings"]:
        f = f_readings.get(r["follow_up"], {})
        print(f"  {r['follow_up']:<22} FLM:    {'; '.join(f.get('labels', ['(none)']))}")
        print(f"  {'':<22} Voyage: {'; '.join(r['labels'])}")


def main() -> None:
    thirty_table(load(FLM, "harness.json"), load(HERE, "harness.json"))
    thirty_runs(load(FLM, "harness.json"), load(HERE, "harness.json"))
    threads_table(load(FLM, "threads.json"), load(HERE, "threads.json"))


if __name__ == "__main__":
    main()
