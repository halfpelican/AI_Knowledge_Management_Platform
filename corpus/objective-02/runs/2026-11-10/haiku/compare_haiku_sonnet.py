"""The Haiku round (10 November 2026): Haiku 5.5 beside Sonnet 5.5 on all three sets.

Reads each pair of records and prints them side by side. Nothing is re-scored: every number comes
from a record's own summary or rows, as the scripts that ran wrote them.

- dev-set-v2 end to end: ../voyage-threshold/e2e/ (Sonnet, 0.2687 / 0.2468 patched in, which D-120
  later made the code's own) against e2e/ here (Haiku, D-120's values unpatched).
- The frozen thirty and the nine threads: ../voyage-frozen/ (#75, Sonnet) against this folder (Haiku).

Same database, dump, embedder and values throughout; only the Claude model differs. Usage, from
anywhere:  python compare_haiku_sonnet.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SONNET_DEV = HERE.parent / "voyage-threshold" / "e2e" / "e2e_v2_voyage_T2687_F2468_N6"
HAIKU_DEV = HERE / "e2e" / "e2e_v2_haiku_T2687_F2468_N6"
SONNET_FROZEN = HERE.parent / "voyage-frozen"
PRICES = {"Sonnet 5.5": (2.0, 10.0), "Haiku 5.5": (0.10, 0.50)}  # US$ per million, in / out


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(stem: Path) -> list[dict]:
    text = stem.with_suffix(".jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def fraction(pair) -> str:
    return f"{pair[0]}/{pair[1]}"


def dollars(model: str, tokens_in: int, tokens_out: int) -> str:
    price_in, price_out = PRICES[model]
    return f"${(tokens_in * price_in + tokens_out * price_out) / 1_000_000:.4f}"


def line(label: str, sonnet, haiku) -> None:
    print(f"  {label:<52} {str(sonnet):>14} {str(haiku):>14}")


def dev_set() -> None:
    s, h = load(SONNET_DEV.parent / f"{SONNET_DEV.name}_summary.json"), load(HAIKU_DEV.parent / f"{HAIKU_DEV.name}_summary.json")
    s_rows, h_rows = rows(SONNET_DEV), rows(HAIKU_DEV)
    print("DEV-SET-V2, END TO END (40 runs)")
    line("", "Sonnet 5.5", "Haiku 5.5")
    for label, key in (("answered, where an answer is expected", "answered_where_expected"),
                       ("declined, where none is expected", "no_answer_where_expected"),
                       ("expected-answer match, from an expected source", "expected_answer_match"),
                       ("schema violations", "schema_violations"), ("503s", "server_503"),
                       ("out-of-scope citations", "out_of_scope_citations"),
                       ("median seconds per ask", "ask_seconds_median")):
        line(label, s[key], h[key])
    line("fabricated identifiers (statements removed)",
         sum(r.get("rejected_count") or 0 for r in s_rows), sum(r.get("rejected_count") or 0 for r in h_rows))
    for name, model_rows in (("Sonnet 5.5", s_rows), ("Haiku 5.5", h_rows)):
        attempts = [a for r in model_rows for a in r["attempts"]]
        tokens_in = sum(a.get("prompt_tokens") or 0 for a in attempts)
        tokens_out = sum(a.get("completion_tokens") or 0 for a in attempts)
        print(f"  {name}: {len(attempts)} attempts, {tokens_in} in / {tokens_out} out, {dollars(name, tokens_in, tokens_out)}")
    differing = [r["run"] for r, o in zip(s_rows, h_rows)
                 if (r["answered"], r["match"], r["no_answer_reason"]) != (o["answered"], o["match"], o["no_answer_reason"])]
    print(f"  runs whose outcome differs: {differing or 'none'}")


def right(result: dict) -> bool:
    return bool(result.get("expected_answer_found")) if result.get("expects_answer") else not result.get("answered")


def frozen_thirty() -> None:
    s, h = load(SONNET_FROZEN / "harness.json"), load(HERE / "harness.json")
    print("\nTHE FROZEN THIRTY (34 runs)")
    line("", "Sonnet 5.5", "Haiku 5.5")
    for label, key in (("ordinary answered correctly", "expected_answer_match"),
                       ("scoped, answered for the role that can see it", "scoped_answered"),
                       ("scoped, declined for the role that cannot", "scoped_empty"),
                       ("no-answer questions declined", "no_answer_empty"),
                       ("first-attempt conformance", "first_attempt_conformance"),
                       ("fabricated identifiers (of statements)", "fabricated_identifiers")):
        line(label, fraction(s["summary"][key]), fraction(h["summary"][key]))
    line("runs right, all kinds", f"{sum(map(right, s['results']))}/34", f"{sum(map(right, h['results']))}/34")
    line("leaks", s["summary"]["leaks"], h["summary"]["leaks"])
    timing = lambda r: r["summary"]["timing_seconds"]["per_answered_question"]  # noqa: E731
    line("answered question, median / p90 seconds",
         f"{timing(s)['median']:.2f} / {timing(s)['p90']:.2f}", f"{timing(h)['median']:.2f} / {timing(h)['p90']:.2f}")
    line("Claude calls, estimated cost", f"{s['claude_usage']['calls']}, ${s['claude_usage']['estimated_usd']:.4f}",
         f"{h['claude_usage']['calls']}, ${h['claude_usage']['estimated_usd']:.4f}")
    by_id = {r["id"]: r for r in s["results"]}
    differing = [r["id"] for r in h["results"] if right(r) != right(by_id[r["id"]])]
    print(f"  runs right on one model and not the other: {differing or 'none'}")


def threads() -> None:
    s, h = load(SONNET_FROZEN / "threads.json"), load(HERE / "threads.json")
    print("\nTHE NINE THREADS (44 runs)")
    line("expected-answer match", "Sonnet 5.5", "Haiku 5.5")
    for way in ("first-turn", "with-history", "cold", "spelled-out"):
        line(way, fraction(s["summary"]["per_way"][way]["expected_answer_match"]),
             fraction(h["summary"]["per_way"][way]["expected_answer_match"]))
    line("fabricated identifiers, all ways",
         sum(w["fabricated_identifiers"][0] for w in s["summary"]["per_way"].values()),
         sum(w["fabricated_identifiers"][0] for w in h["summary"]["per_way"].values()))
    line("out of scope, all ways", sum(w["out_of_scope"] for w in s["summary"]["per_way"].values()),
         sum(w["out_of_scope"] for w in h["summary"]["per_way"].values()))
    line("Claude calls, estimated cost", f"{s['claude_usage']['calls']}, ${s['claude_usage']['estimated_usd']:.4f}",
         f"{h['claude_usage']['calls']}, ${h['claude_usage']['estimated_usd']:.4f}")
    s_runs = {r["run_id"]: r for r in s["runs"]}
    for r in h["runs"]:
        other = s_runs[r["run_id"]]
        if (r["score"].get("outcome"), r["score"].get("correct")) != (other["score"].get("outcome"), other["score"].get("correct")):
            print(f"  differs: {r['run_id']} ({r['question']!r}): Sonnet {other['score'].get('outcome')}, "
                  f"Haiku {r['score'].get('outcome')}; correct {other['score'].get('correct')} / {r['score'].get('correct')}")
    s_read = {x["follow_up"]: x["labels"] for x in s["summary"]["readings"]}
    same = all(s_read.get(x["follow_up"]) == x["labels"] for x in h["summary"]["readings"])
    print(f"  readings per follow-up identical on both models: {same}")


def main() -> None:
    dev_set()
    frozen_thirty()
    threads()


if __name__ == "__main__":
    main()
