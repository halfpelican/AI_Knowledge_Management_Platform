"""The three Haiku draws of the frozen nine, side by side, read against haiku-draws.md's rule.

It reads the three thread records and prints: where each came from, the scores per way, the
with-history result per follow-up, the readings, what differed between draws (the band), and
the rule's bar. It calls nothing: no provider, no database. The rule it applies is the one in
haiku-draws.md, and this file was committed with that rule, before draw 2.

Usage, from anywhere:
    python compare_draws.py
    python compare_draws.py --records A.json B.json C.json    # other records, for testing this script
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECORDS = (
    ("draw 1", HERE.parent.parent / "2026-11-10" / "haiku" / "threads.json"),
    ("draw 2", HERE.parent / "haiku-draw-2" / "threads.json"),
    ("draw 3", HERE.parent / "haiku-draw-3" / "threads.json"),
)
WAYS = ("first-turn", "with-history", "spelled-out", "cold")

# --- The rule (haiku-draws.md) -----------------------------------------------------------------
MINIMUM_WITH_HISTORY = 8  # of the 9 answerable follow-ups, in every draw
# A follow-up that misses with history in more than one draw is a repeated miss, not noise, and
# fails the rule. t09 is exempt: its frozen prediction is that it fails, which is D-42's recorded
# deviation and not the resolving half this rule reads.
REPEATED_MISS_LIMIT = 1
EXEMPT_FROM_REPEATED_MISS = ("t09@Employee",)


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def follow_up(run: dict) -> str:
    return f"{run['thread_id']}@{run['role']}"


def by_run(record: dict) -> dict[str, dict]:
    return {run["run_id"]: run for run in record["runs"]}


def ratio(pair) -> str:
    return f"{pair[0]}/{pair[1]}"


def table(header: list[str], rows: list[list[str]]) -> None:
    widths = [max(len(str(cell)) for cell in column) for column in zip(header, *rows)]
    for row in (header, ["-" * width for width in widths], *rows):
        print("  " + "  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)).rstrip())


def leak_count(record: dict) -> int:
    return record["summary"]["out_of_scope_total"] + sum(len(run["score"]["leaks"]) for run in record["runs"])


def fabricated(record: dict) -> tuple[int, int]:
    pairs = [record["summary"]["per_way"][way]["fabricated_identifiers"] for way in WAYS]
    return sum(pair[0] for pair in pairs), sum(pair[1] for pair in pairs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--records", nargs=3, type=Path, metavar="JSON",
                        help="three other records, for testing this script; not a result")
    arguments = parser.parse_args()
    named = RECORDS if not arguments.records else tuple(
        (f"draw {number}", path) for number, path in enumerate(arguments.records, 1))
    if arguments.records:
        print("TESTING THIS SCRIPT on other records: nothing below is the run's result.\n")
    draws = [(name, path, load(path)) for name, path in named]
    made = [(name, record) for name, _, record in draws if record is not None]
    names = [name for name, _ in made]
    for name, path, record in draws:
        if record is None:
            print(f"{name}: not made yet ({path})")
    if not made:
        return 1

    print("WHERE EACH DRAW CAME FROM")
    rows = []
    for label, read in (
        ("recorded at", lambda r: r["record"]["recorded_at"]),
        ("commit", lambda r: r["record"]["commit_sha"][:7]),
        ("uncommitted tracked changes", lambda r: str(r["record"]["uncommitted_tracked_changes"])),
        ("database", lambda r: r["record"]["database"]),
        ("dump sha256", lambda r: r["record"]["dump_sha256"][:8] + "..."),
        ("chat model", lambda r: r["record"]["provider_record"]["chat_model"]),
        ("embedding", lambda r: f"{r['record']['provider_record']['embed_model']} at "
                                f"{r['record']['provider_record']['embedding_dimension']}"),
        ("threshold / floor", lambda r: f"{r['record']['provider_record']['threshold']} / "
                                        f"{r['record']['provider_record']['partial_match_floor']}"),
        ("thread set sha256", lambda r: r["record"]["thread_set_sha256"][:8] + "..."),
        ("scoring rule", lambda r: f"v{r['record']['scoring_rule_version']}"),
        ("runs", lambda r: str(len(r["runs"]))),
        ("server", lambda r: r["record"]["server"]["via"]),
    ):
        rows.append([label] + [read(record) for _, record in made])
    table([""] + names, rows)
    same = {key: len({json.dumps(read(record), sort_keys=True) for _, record in made}) == 1 for key, read in (
        ("database and dump", lambda r: [r["record"]["database"], r["record"]["dump_sha256"]]),
        ("provider record", lambda r: r["record"]["provider_record"]),
        ("thread set and rule", lambda r: [r["record"]["thread_set_sha256"], r["record"]["scoring_rule_version"]]),
        ("constants", lambda r: r["constants"]),
        ("the questions, run for run", lambda r: [[run["run_id"], run["question"], run["retrieval_text"],
                                                  run["prompt_question"]] for run in r["runs"]]),
    )}
    for key, value in same.items():
        print(f"  same in every draw, {key}: {'yes' if value else 'NO'}")

    print("\nSCORES PER WAY (expected-answer match, where an answer is expected)")
    rows = []
    for way in WAYS:
        rows.append([way] + [ratio(record["summary"]["per_way"][way]["expected_answer_match"]) for _, record in made])
    rows.append(["scoped Employee runs not answered"] + [
        "/".join(str(sum(record["summary"]["per_way"][way]["not_answered_where_expected"][index]
                         for way in WAYS)) for index in (0, 1)) for _, record in made])
    rows.append(["leaks (out of scope, every run)"] + [str(leak_count(record)) for _, record in made])
    rows.append(["fabricated identifiers"] + [ratio(fabricated(record)) for _, record in made])
    rows.append(["schema conformance"] + [ratio(record["summary"]["schema_conformance"]) for _, record in made])
    rows.append(["unavailable runs"] + [str(sum(record["summary"]["per_way"][way]["outcomes"]["unavailable"]
                                                for way in WAYS)) for _, record in made])
    rows.append(["scoping shown, t06 / t07"] + [" / ".join(
        "yes" if entry["scoping_shown"] else "NO" for entry in record["summary"]["scoping"]) for _, record in made])
    rows.append(["Claude calls"] + [str(record["claude_usage"]["calls"]) for _, record in made])
    rows.append(["input / output tokens"] + [f"{record['claude_usage']['input_tokens']} / "
                                             f"{record['claude_usage']['output_tokens']}" for _, record in made])
    rows.append(["estimated US$"] + [f"{record['claude_usage']['estimated_usd']:.4f}" for _, record in made])
    rows.append(["elapsed, minutes"] + [f"{record['elapsed_seconds'] / 60:.1f}" for _, record in made])
    table([""] + names, rows)

    print("\nWITH HISTORY, PER FOLLOW-UP (outcome; C = correct by the frozen rule, x = not; source rank; passages supplied)")
    indexed = [(name, by_run(record)) for name, record in made]
    follow_ups = [follow_up(run) for run in made[0][1]["runs"] if run["way"] == "with-history"]
    misses: dict[str, list[str]] = {}
    rows = []
    for identifier in follow_ups:
        row = [identifier]
        for name, runs in indexed:
            run = runs[f"{identifier}/with-history"]
            score = run["score"]
            rank = run["source_rank"] if run["source_rank"] is not None else "-"
            row.append(f"{score['outcome']}  {'C' if score['correct'] else 'x'}  rank {rank}  {len(run['retrieved'])} supplied")
            if run["expects_answer"] and not score["expected_answer_match"]:
                misses.setdefault(identifier, []).append(name)
        row.append(", ".join(misses.get(identifier, [])) or "-")
        rows.append(row)
    table(["follow-up"] + names + ["missed in"], rows)

    print("\nREADINGS (scoring rule part 10)")
    rows = []
    for position, identifier in enumerate(follow_ups):
        row = [identifier]
        for _, record in made:
            reading = record["summary"]["readings"][position]
            assert reading["follow_up"] == identifier, (reading["follow_up"], identifier)
            row.append("; ".join(reading["labels"]) + ("" if reading["prediction_held"] else "  [prediction did not hold]"))
        rows.append(row)
    table(["follow-up"] + names, rows)

    print("\nWHAT DIFFERED BETWEEN DRAWS (the band)")
    if len(made) < 2:
        print("  one draw only: nothing to compare")
    else:
        rows = []
        for way in WAYS:
            counts = [record["summary"]["per_way"][way]["expected_answer_match"][0] for _, record in made]
            of = made[0][1]["summary"]["per_way"][way]["expected_answer_match"][1]
            rows.append([way, " ".join(str(count) for count in counts), f"{min(counts)} to {max(counts)} of {of}",
                         str(max(counts) - min(counts))])
        table(["way", "matches per draw", "range", "spread"], rows)
        flips, set_changes, order_changes, largest = [], [], [], (0.0, None)
        statement_changes = 0
        for run_id in indexed[0][1]:
            runs = [runs_[run_id] for _, runs_ in indexed]
            correct = [run["score"]["correct"] for run in runs]
            outcomes = [run["score"]["outcome"] for run in runs]
            supplied = [[passage["chunk_id"] for passage in run["retrieved"]] for run in runs]
            if len(set(correct)) > 1 or len(set(outcomes)) > 1:
                same_set = len({frozenset(ids) for ids in supplied}) == 1
                flips.append([run_id, " ".join("C" if value else "x" for value in correct), " | ".join(outcomes),
                              "the same passages" if same_set else "DIFFERENT passages"])
            if len({frozenset(ids) for ids in supplied}) > 1:
                set_changes.append(run_id)
            elif len({tuple(ids) for ids in supplied}) > 1:
                order_changes.append(run_id)
            scores: dict[str, list[float]] = {}
            for run in runs:
                for passage in run["retrieved"]:
                    scores.setdefault(passage["chunk_id"], []).append(passage["score"])
            for values in scores.values():
                if len(values) == len(runs) and max(values) - min(values) > largest[0]:
                    largest = (max(values) - min(values), run_id)
            texts = [json.dumps([[s["chunk_id"], s["text"]] for s in run["verified_statements"]], sort_keys=True)
                     for run in runs]
            if len(set(texts)) > 1:
                statement_changes += 1
        total = len(indexed[0][1])
        print(f"  runs whose outcome or correctness differs between draws: {len(flips)} of {total}")
        if flips:
            table(["run", "correct per draw", "outcome per draw", "supplied"], flips)
        print(f"  runs whose verified statements differ in any way (wording included): {statement_changes} of {total}")
        print(f"  runs supplied a different SET of passages in some draw: {len(set_changes)} of {total}"
              + (f" ({', '.join(set_changes)})" if set_changes else ""))
        print(f"  runs supplied the same set in a different ORDER: {len(order_changes)} of {total}"
              + (f" ({', '.join(order_changes)})" if order_changes else ""))
        print(f"  largest score difference for one passage in one run: {largest[0]:.5f}"
              + (f" ({largest[1]})" if largest[1] else ""))

    print("\nTHE RULE (haiku-draws.md)")
    rows, every_draw = [], True
    for name, record in made:
        matched, of = record["summary"]["per_way"]["with-history"]["expected_answer_match"]
        leaks, invented = leak_count(record), fabricated(record)[0]
        passed = matched >= MINIMUM_WITH_HISTORY and leaks == 0 and invented == 0
        every_draw = every_draw and passed
        rows.append([name, f"{matched}/{of} (at least {MINIMUM_WITH_HISTORY})", f"{leaks} (0)", f"{invented} (0)",
                     "PASSES" if passed else "FALLS SHORT"])
    table(["", "with history", "leaks", "fabricated identifiers", "the draw"], rows)
    repeated = {identifier: where for identifier, where in misses.items()
                if len(where) > REPEATED_MISS_LIMIT and identifier not in EXEMPT_FROM_REPEATED_MISS}
    exempt = {identifier: where for identifier, where in misses.items()
              if len(where) > REPEATED_MISS_LIMIT and identifier in EXEMPT_FROM_REPEATED_MISS}
    print("  repeated misses (a follow-up missed with history in more than one draw): "
          + ("none" if not repeated else "; ".join(f"{identifier} in {', '.join(where)}" for identifier, where in repeated.items())))
    for identifier, where in exempt.items():
        print(f"  {identifier} missed in {', '.join(where)}: as its frozen prediction says, D-42's recorded deviation; exempt")
    if len(made) < len(named):
        print(f"\n  {len(made)} of {len(named)} draws made: no reading yet")
        return 0
    if every_draw and not repeated:
        print("\n  THE THREE DRAWS PASS. With the HTTP check's bar (haiku-draws.md), the resolving half is read as met.")
    else:
        print("\n  THE THREE DRAWS DO NOT PASS: the follow-up clause is partial on anthropic too, with the band above.")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
