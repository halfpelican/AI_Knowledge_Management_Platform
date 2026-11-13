"""Objective 04's verification: an adjudication sheet a person completes, and the three numbers.

Objective 04 (proposal section 2): against a reference set of ten transcripts "for which
summaries, action items and decisions have been prepared manually in advance", "at least 80% of
the action items present in the reference must be extracted, no more than 10% of extracted items
may be items absent from the reference, and every extracted item carrying a named owner must
either resolve to a user on the system or be recorded as unassigned rather than attributed to the
wrong person."

Whether an extracted item IS a reference item is a judgement about meaning, so **a person makes
it, not this script** (corpus/objective-04/README.md). The script does the two things either side
of that judgement, and nothing here calls a model or touches a database. Standard library only.

``sheet``  reads a run's record (scripts/objective04_run.py's ``run.json``) and the reference, and
           writes ``adjudication.csv``: one row per extracted action item, beside the reference
           item the script proposes for it. The proposal is word overlap, a convenience and
           nothing more. The person fills in ``decision`` on every row: a reference ``ref`` such
           as ``O01-A2``, or ``none``. Where an item matches nothing but was given to a user, they
           also fill in ``owner_ok`` (``yes`` or ``no``), because no reference item says who it
           should have been.

``score``  reads the completed sheet and writes ``results.json`` and ``results.md``:

           - **recall**: reference items matched, over all reference items. At least 80%.
           - **extras**: extracted items matching none, over all extracted items. At most 10%.
           - **attribution**: extracted items that carry a named owner and were given to a user
             who is not the reference's ``expected_owner``. Must be zero. An item stored as
             unassigned passes whatever the reference says, which is the objective's own rule.

           All three are pooled over the set's transcripts. A reference item may be matched once:
           the sheet is refused if two rows claim the same one, so that a duplicate extraction is
           counted as an extra by the person's decision and never by accident. The sheet is also
           refused while any ``decision`` is blank, or names a ``ref`` the reference does not hold.

           Reported beside them and not scored: due dates against ``expected_due_date``, and the
           count of decisions extracted against the reference's.

Usage::

    .venv\\Scripts\\python.exe scripts\\objective04_verify.py sheet --run <dir>\\run.json `
        --reference corpus\\objective-04\\reference.json --out <dir>\\adjudication.csv
    .venv\\Scripts\\python.exe scripts\\objective04_verify.py score --run <dir>\\run.json `
        --reference corpus\\objective-04\\reference.json --sheet <dir>\\adjudication.csv --out-dir <dir>
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

RECALL_FLOOR = 0.80
EXTRAS_CEILING = 0.10
NONE = "none"
UNASSIGNED = "unassigned"
SHEET_COLUMNS = [
    "transcript", "row", "extracted_description", "owner_as_said", "resolved_owner",
    "due_as_said", "resolved_due_date", "proposed_ref", "proposed_description", "decision",
    "owner_ok", "notes",
]

_WORD = re.compile(r"[a-z0-9']+")
_STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the their them this to "
    "was were will with".split()
)


class SheetError(Exception):
    """The sheet cannot be scored as it stands; the message says which rows and why."""


def words(text: str) -> frozenset[str]:
    return frozenset(word for word in _WORD.findall((text or "").lower()) if word not in _STOP)


def overlap(left: str, right: str) -> float:
    """Jaccard overlap of the two texts' words: 0 where they share none, 1 where they are the same set."""
    a, b = words(left), words(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def propose_pairs(extracted: list[str], reference: list[dict]) -> list[str | None]:
    """For each extracted description, the ``ref`` of the reference item it most resembles, or None.

    Greedy on word overlap, best pair first, each reference item proposed at most once and never
    below a small floor. It is a starting point for the person, who decides every row.
    """
    scored = sorted(
        (
            (overlap(description, f"{item.get('description', '')} {item.get('evidence', '')}"), row, item["ref"])
            for row, description in enumerate(extracted)
            for item in reference
        ),
        key=lambda entry: (-entry[0], entry[1], entry[2]),
    )
    proposed: list[str | None] = [None] * len(extracted)
    taken: set[str] = set()
    for value, row, ref in scored:
        if value < 0.15:
            break
        if proposed[row] is None and ref not in taken:
            proposed[row] = ref
            taken.add(ref)
    return proposed


def reference_by_transcript(reference: dict) -> dict[str, dict]:
    return {block["id"]: block for block in reference["transcripts"]}


def extracted_by_transcript(run: dict) -> dict[str, dict]:
    return {entry["set_id"]: entry for entry in run["meetings"]}


def build_sheet(run: dict, reference: dict) -> list[dict]:
    """One row per extracted action item, in the run's order, with the script's proposed pairing."""
    blocks = reference_by_transcript(reference)
    rows = []
    for set_id, entry in extracted_by_transcript(run).items():
        block = blocks.get(set_id, {"action_items": []})
        items = entry.get("action_items", [])
        described = {item["ref"]: item.get("description", "") for item in block["action_items"]}
        proposals = propose_pairs([item["description"] for item in items], block["action_items"])
        for number, (item, ref) in enumerate(zip(items, proposals), start=1):
            rows.append(
                {
                    "transcript": set_id,
                    "row": number,
                    "extracted_description": item["description"],
                    "owner_as_said": item["owner_name"],
                    "resolved_owner": item["owner"] or UNASSIGNED,
                    "due_as_said": item["due_text"],
                    "resolved_due_date": item["due_date"] or "",
                    "proposed_ref": ref or "",
                    "proposed_description": described.get(ref, "") if ref else "",
                    "decision": "",
                    "owner_ok": "",
                    "notes": "",
                }
            )
    return rows


def score(run: dict, reference: dict, sheet: list[dict]) -> dict:
    """The three numbers and what lies behind them, from a completed sheet. Raises SheetError."""
    blocks = reference_by_transcript(reference)
    extracted = extracted_by_transcript(run)
    known = {item["ref"]: (block["id"], item) for block in blocks.values() for item in block["action_items"]}

    problems: list[str] = []
    expected_rows = {
        (set_id, number)
        for set_id, entry in extracted.items()
        for number in range(1, len(entry.get("action_items", [])) + 1)
    }
    seen_rows = {(row["transcript"], int(row["row"])) for row in sheet}
    if seen_rows != expected_rows:
        problems.append(
            f"the sheet's rows are not the run's extracted items: missing {sorted(expected_rows - seen_rows)}, "
            f"unexpected {sorted(seen_rows - expected_rows)}"
        )
    claimed: dict[str, list[str]] = {}
    for row in sheet:
        where = f"{row['transcript']} row {row['row']}"
        decision = (row.get("decision") or "").strip()
        if not decision:
            problems.append(f"{where}: no decision")
        elif decision.lower() != NONE:
            if decision not in known:
                problems.append(f"{where}: {decision!r} is not a ref in the reference")
            elif known[decision][0] != row["transcript"]:
                problems.append(f"{where}: {decision} belongs to {known[decision][0]}")
            else:
                claimed.setdefault(decision, []).append(where)
    for ref, rows in sorted(claimed.items()):
        if len(rows) > 1:
            problems.append(f"{ref} is claimed by {len(rows)} rows ({', '.join(rows)}); a reference item matches once")
    if problems:
        raise SheetError("The sheet cannot be scored:\n- " + "\n- ".join(problems))

    matched_refs = set(claimed)
    extras, wrong_owner, owner_checked, dates = [], [], 0, {"compared": 0, "agree": 0, "differ": []}
    for row in sheet:
        where = f"{row['transcript']} row {row['row']}"
        decision = row["decision"].strip()
        resolved = (row.get("resolved_owner") or UNASSIGNED).strip()
        named = bool((row.get("owner_as_said") or "").strip())
        if decision.lower() == NONE:
            extras.append({"where": where, "description": row["extracted_description"]})
            if named and resolved != UNASSIGNED:
                owner_checked += 1
                verdict = (row.get("owner_ok") or "").strip().lower()
                if verdict not in ("yes", "no"):
                    raise SheetError(
                        f"The sheet cannot be scored:\n- {where}: matches nothing but was given to "
                        f"{resolved}; owner_ok must be yes or no"
                    )
                if verdict == "no":
                    wrong_owner.append({"where": where, "resolved_owner": resolved, "expected_owner": "(none: an extra item)"})
            continue
        item = known[decision][1]
        if named:
            owner_checked += 1
            expected = (item.get("expected_owner") or UNASSIGNED).strip()
            if resolved != UNASSIGNED and resolved != expected:
                wrong_owner.append({"where": where, "resolved_owner": resolved, "expected_owner": expected})
        expected_date = item.get("expected_due_date")
        if expected_date:
            dates["compared"] += 1
            if (row.get("resolved_due_date") or "") == expected_date:
                dates["agree"] += 1
            else:
                dates["differ"].append(
                    {"where": where, "due_as_said": row.get("due_as_said", ""),
                     "resolved": row.get("resolved_due_date") or None, "expected": expected_date}
                )

    reference_total = len(known)
    extracted_total = len(sheet)
    recall = len(matched_refs) / reference_total if reference_total else None
    extras_rate = len(extras) / extracted_total if extracted_total else 0.0
    per_transcript = []
    for set_id, block in blocks.items():
        refs = {item["ref"] for item in block["action_items"]}
        entry = extracted.get(set_id, {})
        per_transcript.append(
            {
                "transcript": set_id,
                "status": entry.get("status"),
                "reference_items": len(refs),
                "matched": len(refs & matched_refs),
                "extracted_items": len(entry.get("action_items", [])),
                "extras": sum(1 for extra in extras if extra["where"].startswith(f"{set_id} ")),
                "reference_decisions": len(block.get("decisions", [])),
                "extracted_decisions": len(entry.get("decisions", [])),
            }
        )
    not_ready = [set_id for set_id in blocks if extracted.get(set_id, {}).get("status") != "Ready"]
    return {
        "reference_items": reference_total,
        "matched_reference_items": len(matched_refs),
        "recall": recall,
        "recall_met": recall is not None and recall >= RECALL_FLOOR,
        "extracted_items": extracted_total,
        "extras": len(extras),
        "extras_rate": extras_rate,
        "extras_met": extras_rate <= EXTRAS_CEILING,
        "items_with_a_named_owner": owner_checked,
        "wrong_owner": wrong_owner,
        "attribution_met": not wrong_owner,
        "met": bool(recall is not None and recall >= RECALL_FLOOR and extras_rate <= EXTRAS_CEILING
                    and not wrong_owner and not not_ready),
        "transcripts_without_a_ready_summary": not_ready,
        "missed": sorted(
            (
                {"ref": ref, "transcript": known[ref][0], "description": known[ref][1].get("description", "")}
                for ref in set(known) - matched_refs
            ),
            key=lambda miss: miss["ref"],
        ),
        "extra_items": extras,
        "due_dates": dates,
        "per_transcript": per_transcript,
    }


def results_markdown(result: dict, run: dict, reference: dict) -> str:
    def percent(value):
        return "n/a" if value is None else f"{value * 100:.1f}%"

    def verdict(flag):
        return "met" if flag else "NOT met"

    usage = run.get("usage") or {}
    lines = [
        f"# Objective 04 result: {'MET' if result['met'] else 'NOT MET'}",
        "",
        f"Set: {run.get('set')} · database `{run.get('database')}` · {run.get('ai_provider')} / "
        f"`{run.get('chat_model')}` · commit `{run.get('commit')}` · reference: {reference.get('status', '')}",
        "",
        "| Criterion | Bar | Result | |",
        "|---|---|---|---|",
        f"| Reference action items extracted | at least 80% | {result['matched_reference_items']} of "
        f"{result['reference_items']} ({percent(result['recall'])}) | {verdict(result['recall_met'])} |",
        f"| Extracted items absent from the reference | at most 10% | {result['extras']} of "
        f"{result['extracted_items']} ({percent(result['extras_rate'])}) | {verdict(result['extras_met'])} |",
        f"| Named owners given to the wrong person | none | {len(result['wrong_owner'])} of "
        f"{result['items_with_a_named_owner']} checked | {verdict(result['attribution_met'])} |",
        "",
    ]
    if result["transcripts_without_a_ready_summary"]:
        lines += [f"**No ready summary for:** {', '.join(result['transcripts_without_a_ready_summary'])}. "
                  "The objective is not met while any transcript has none.", ""]
    lines += ["| Transcript | Reference items | Matched | Extracted | Extras | Decisions (reference / extracted) |",
              "|---|---|---|---|---|---|"]
    for row in result["per_transcript"]:
        lines.append(
            f"| {row['transcript']} | {row['reference_items']} | {row['matched']} | {row['extracted_items']} | "
            f"{row['extras']} | {row['reference_decisions']} / {row['extracted_decisions']} |"
        )
    lines += ["", "## Reference items not extracted", ""]
    lines += [f"- **{miss['ref']}**: {miss['description']}" for miss in result["missed"]] or ["None."]
    lines += ["", "## Extracted items absent from the reference", ""]
    lines += [f"- **{extra['where']}**: {extra['description']}" for extra in result["extra_items"]] or ["None."]
    lines += ["", "## Owners given to the wrong person", ""]
    lines += [
        f"- **{wrong['where']}**: stored as {wrong['resolved_owner']}; the reference says {wrong['expected_owner']}"
        for wrong in result["wrong_owner"]
    ] or ["None."]
    dates = result["due_dates"]
    lines += ["", "## Due dates (reported, not scored)", "",
              f"{dates['agree']} of {dates['compared']} matched items with a reference date resolved to it."]
    lines += [
        f"- **{entry['where']}**: \"{entry['due_as_said']}\" resolved to {entry['resolved']}; the reference says {entry['expected']}"
        for entry in dates["differ"]
    ]
    lines += ["", "## Spend", "",
              f"{usage.get('attempts')} summarisation attempt(s): {usage.get('prompt_tokens')} prompt and "
              f"{usage.get('completion_tokens')} completion tokens, {usage.get('cost_usd')} USD at "
              f"{usage.get('prices_per_million_tokens')} per million tokens. Embedding calls are billed "
              "separately and are not counted.", ""]
    return "\n".join(lines)


def read_sheet(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    sheet_parser = commands.add_parser("sheet", help="write the adjudication sheet for a run")
    score_parser = commands.add_parser("score", help="score a completed adjudication sheet")
    for sub in (sheet_parser, score_parser):
        sub.add_argument("--run", required=True, type=Path)
        sub.add_argument("--reference", required=True, type=Path)
    sheet_parser.add_argument("--out", required=True, type=Path)
    score_parser.add_argument("--sheet", required=True, type=Path)
    score_parser.add_argument("--out-dir", required=True, type=Path)
    arguments = parser.parse_args(argv)

    run = json.loads(arguments.run.read_text(encoding="utf-8"))
    reference = json.loads(arguments.reference.read_text(encoding="utf-8"))
    if arguments.command == "sheet":
        rows = build_sheet(run, reference)
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        with arguments.out.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SHEET_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"{len(rows)} extracted item(s) written to {arguments.out}. Fill in 'decision' on every row.")
        return 0

    try:
        result = score(run, reference, read_sheet(arguments.sheet))
    except SheetError as exc:
        print(exc)
        return 2
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    (arguments.out_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (arguments.out_dir / "results.md").write_text(results_markdown(result, run, reference), encoding="utf-8")
    print(f"Objective 04: {'MET' if result['met'] else 'NOT MET'}. Results in {arguments.out_dir}.")
    return 0 if result["met"] else 1


if __name__ == "__main__":
    sys.exit(main())
