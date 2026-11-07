"""Step 7 phase 2a: the sweep table and the per-run matrix, from the sweep_*.jsonl files.

Reads the JSONL that sweep_statement_cap.py wrote, one file per setting, and prints:
the summary per setting (sweep_statement_cap.summarise), then one row per dev-set run showing,
per setting, its outcome: M (answered, expected answer matched with an expected cited source),
A (answered, no match), - (no answer), 503, and * where the run went against its expectation
(answered where none was expected, or not answered where one was).

Usage: python sweep_table.py <folder holding sweep_*.jsonl> baseline N3 N4 N5 N6
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sweep_statement_cap import summarise  # noqa: E402


def main() -> int:
    folder = Path(sys.argv[1])
    labels = sys.argv[2:]
    rows = {
        label: [json.loads(l) for l in (folder / f"sweep_{label}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        for label in labels
    }
    keys = ["ceiling_hits", "server_503", "cap_violations", "answered_where_expected", "no_answer_where_expected",
            "expected_answer_match", "phrase_anywhere", "out_of_scope_citations", "completion_tokens_median",
            "completion_tokens_max", "attempt_seconds_median", "attempt_seconds_max", "ask_seconds_median",
            "ask_seconds_max", "statements_per_answer_max", "attempts"]
    summaries = {label: summarise(rows[label]) for label in labels}
    print("| | " + " | ".join(labels) + " |")
    print("|---|" + "---|" * len(labels))
    for key in keys:
        print(f"| {key} | " + " | ".join(str(summaries[label][key]) for label in labels) + " |")

    print("\nPer run: M matched, A answered without a match, - no answer, 503; * against expectation.")
    print("| run | expects | " + " | ".join(labels) + " |")
    print("|---|---|" + "---|" * len(labels))
    by_run = {label: {r["run"]: r for r in rows[label]} for label in labels}
    for run in [r["run"] for r in rows[labels[0]]]:
        cells = []
        for label in labels:
            r = by_run[label][run]
            if r["status"] == 503:
                cell = "503"
            elif r["answered"]:
                cell = "M" if r["match"] else "A"
            else:
                cell = "-"
            if r["status"] == 200 and r["answered"] != r["expects_answer"]:
                cell += "*"
            cells.append(cell)
        expects = "answer" if by_run[labels[0]][run]["expects_answer"] else "none"
        print(f"| {run} | {expects} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
