"""D-129's tag and department threshold: D-106's rule, unchanged, on the tag and department suggestions.

Committed before any classification it is applied to, with the approved reference
(corpus/objective-05/dev-documents/tag-reference.json), as D-106 fixed its rule before its run.

**What is scored.** Every suggestion INSIDE the scheme that the sweep in this folder recorded:

- a department in the scheme's departments, right when it is in the document's reference list;
- a Project, Process or Topic tag whose normalised value is in the scheme's list for its dimension,
  right when it is in the document's reference list for that dimension.

A value OUTSIDE the scheme is not scored. It is discarded (a department, Project or Process value) or
proposed (a Topic) whatever its confidence, so no threshold decides it (D-129). Its count is reported
for information.

**The rule** is D-106's, as fixed before its first run and kept unchanged by the user: the threshold T
that maximises (right assignments with confidence at or above T) + (wrong ones below T); a tie goes
to the higher value; then T is capped at the lowest confidence seen on a right assignment minus 0.05.
If no T beats applying everything, the confidences do not separate right from wrong; that is
reported, and T is the lowest confidence seen on a right assignment.

It is not re-implemented here: ``choose_threshold`` in scripts/classification_dev_sweep.py is called
on the pairs, adapted to the field names it reads, so the code that chose 0.95 and 0.72 chooses this.

The pooled result is the one the user approved: one threshold for tags and departments together.
The two kinds are also reported apart, for information only.

Usage, from the worktree root::

    .venv\\Scripts\\python.exe corpus\\objective-05\\runs\\2026-11-13-tag-threshold\\tag_threshold_rule.py `
        --sweep corpus\\objective-05\\runs\\2026-11-13-tag-threshold\\sweep\\dev-sweep.json `
        --out-dir corpus\\objective-05\\runs\\2026-11-13-tag-threshold\\threshold
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]  # corpus/objective-05/runs/<this folder>/<this file>
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from classification_dev_sweep import choose_threshold  # noqa: E402  D-106's rule, unchanged

REFERENCE = REPOSITORY_ROOT / "corpus" / "objective-05" / "dev-documents" / "tag-reference.json"
DIMENSIONS = ("Project", "Process", "Topic")


def normalise(value: str) -> str:
    """Tag-name equality, as apps/documents/models.py normalise_tag_name defines it."""
    return " ".join((value or "").split()).lower()


def score(observations: list[dict], reference: dict) -> dict:
    scheme = reference["scheme"]
    departments = set(scheme["departments"])
    tags = {d: {normalise(v) for v in scheme[d]} for d in DIMENSIONS}
    by_id = {entry["id"]: entry for entry in reference["documents"]}
    pairs = {"department": [], "tag": []}
    outside = {"department": 0, "tag": 0}
    missing = set()
    for o in observations:
        entry = by_id.get(o["id"])
        if entry is None:
            missing.add(o["id"])
            continue
        department = (o.get("department") or "").strip()
        confidence = o.get("department_confidence")
        if department in departments and confidence is not None:
            pairs["department"].append((float(confidence), department in entry["department"]))
        elif department:
            outside["department"] += 1
        for t in o.get("tags") or []:
            dimension, value = t.get("dimension"), normalise(t.get("value"))
            if dimension in tags and value in tags[dimension]:
                right = value in {normalise(v) for v in entry[dimension]}
                pairs["tag"].append((float(t["confidence"]), right))
            else:
                outside["tag"] += 1
    return {"pairs": pairs, "outside_scheme": outside, "documents_not_in_reference": sorted(missing)}


def rule(pairs: list[tuple[float, bool]]) -> dict:
    """``choose_threshold`` on (confidence, right) pairs, through the field names it reads."""
    adapted = [{"doc_type_confidence": c, "type_correct": ok} for c, ok in pairs]
    result = choose_threshold(adapted)
    result["right"] = sum(1 for _, ok in pairs if ok)
    result["wrong"] = sum(1 for _, ok in pairs if not ok)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sweep", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.out_dir.exists() and any(arguments.out_dir.iterdir()):
        print(f"REFUSED: {arguments.out_dir} already holds files; a record is never overwritten")
        return 2
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    sweep = json.loads(arguments.sweep.read_text(encoding="utf-8"))
    scored = score(sweep["observations"], reference)
    pooled = scored["pairs"]["department"] + scored["pairs"]["tag"]
    record = {
        "reference": str(REFERENCE.relative_to(REPOSITORY_ROOT)),
        "reference_status": reference.get("status"),
        "sweep": str(arguments.sweep),
        "sweep_record": sweep.get("record", {}),
        "pooled": rule(pooled),
        "departments_only": rule(scored["pairs"]["department"]),
        "tags_only": rule(scored["pairs"]["tag"]),
        "outside_scheme_not_scored": scored["outside_scheme"],
        "documents_not_in_reference": scored["documents_not_in_reference"],
    }
    (arguments.out_dir / "tag-threshold.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    for name in ("pooled", "departments_only", "tags_only"):
        r = record[name]
        print(f"{name}: threshold {r.get('threshold')} (separates: {r.get('separates')}; "
              f"right {r['right']}, wrong {r['wrong']}; lowest right {r.get('lowest_correct')})")
    print(f"outside the scheme, not scored: {record['outside_scheme_not_scored']}")
    if record["documents_not_in_reference"]:
        print(f"WARNING: documents not in the reference: {record['documents_not_in_reference']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
