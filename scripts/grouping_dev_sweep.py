"""Choose GAP_GROUPING_THRESHOLD on the development paraphrase set (D-109).

Embeds every item of corpus/objective-06/dev-paraphrases.json the way FR-19's cycle embeds a
question or a search term (``apps.retrieval.query_embedding.embed_question``: embed-gemma with the
query prefix, D-38), then applies the rule D-109 fixed before the run:

    positives are the within-subject pairs, negatives every cross-subject pair. If the lowest
    positive similarity exceeds the highest negative, the threshold is their midpoint; otherwise
    it is the value with the best pairwise F1 (a tie goes to the higher value). The gap between
    the two, against D-40's drift of 0.003, is reported either way.

It then simulates the centroid grouping D-109 describes, in the set's order, at the chosen value,
and reports how many entries form and whether any mixes subjects. The six hard pairs (same
document or shared vocabulary) are reported on their own.

Nothing is written to any database: the embedding provider is the only thing called. The record
carries the commit, the FLM version and the set's hash (D-84), and FLM must be v0.9.39 (D-83).

Usage, in PowerShell, with FLM serving::

    .venv\\Scripts\\python.exe scripts\\grouping_dev_sweep.py --out-dir corpus\\objective-06\\runs\\<date>\\grouping-sweep
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for entry in (str(REPOSITORY_ROOT / "scripts"), str(REPOSITORY_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import check_flm  # noqa: E402
import measurement_record  # noqa: E402

DEV_SET = REPOSITORY_ROOT / "corpus" / "objective-06" / "dev-paraphrases.json"
DRIFT = 0.003  # D-40's measured query-vector drift


def normalised_mean(vectors: list[list[float]]) -> list[float]:
    total = [sum(values) for values in zip(*vectors)]
    norm = math.sqrt(sum(v * v for v in total)) or 1.0
    return [v / norm for v in total]


def best_f1(positives: list[float], negatives: list[float]) -> dict:
    values = sorted(set(positives) | set(negatives))
    candidates = [(a + b) / 2 for a, b in zip(values, values[1:])] or values
    best = {"threshold": None, "f1": -1.0}
    for t in candidates:
        tp = sum(1 for s in positives if s >= t)
        fp = sum(1 for s in negatives if s >= t)
        fn = len(positives) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        if f1 > best["f1"] or (f1 == best["f1"] and t > (best["threshold"] or -1)):
            best = {"threshold": t, "f1": f1, "precision": precision, "recall": recall,
                    "true_positives": tp, "false_positives": fp, "false_negatives": fn}
    return best


def simulate(items: list[dict], threshold: float, cosine) -> list[dict]:
    """D-109's greedy centroid grouping, in the set's order."""
    gaps: list[dict] = []
    for item in items:
        best, best_sim = None, -2.0
        for gap in gaps:
            sim = cosine(item["vector"], gap["centroid"])
            if sim > best_sim:
                best, best_sim = gap, sim
        if best is not None and best_sim >= threshold:
            best["members"].append(item)
            best["centroid"] = normalised_mean([m["vector"] for m in best["members"]])
        else:
            gaps.append({"subject": item["text"], "members": [item], "centroid": item["vector"]})
    return gaps


def provider_record(settings) -> dict:
    """The configuration this result belongs to (D-113): the provider, its chat model and its
    embedding model. A value tuned, or a result measured, on one configuration does not carry
    over to another, so every record names its own."""
    provider = settings.AI_PROVIDER
    if provider == "anthropic":
        return {"ai_provider": provider, "chat_model": settings.ANTHROPIC_MODEL,
                "embedding_model": settings.VOYAGE_MODEL}
    return {"ai_provider": provider, "chat_model": settings.FLM_CHAT_MODEL,
            "embedding_model": settings.FLM_EMBED_MODEL}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, required=True)
    arguments = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings

    from apps.retrieval.query_embedding import embed_question
    from apps.retrieval.ranking import cosine_similarity

    if arguments.out_dir.exists() and any(arguments.out_dir.iterdir()):
        print(f"REFUSED: {arguments.out_dir} already holds files; a run never overwrites a record")
        return 2
    print("FLM gate: scripts/check_flm.py's checks (D-83)")
    checks = check_flm.run_checks(settings.FLM_BASE_URL, settings.FLM_API_KEY, settings.FLM_CHAT_MODEL, settings.FLM_EMBED_MODEL)
    if not check_flm.checks_passed(checks):
        print("REFUSED: FLM checks failed")
        return 2
    version = check_flm.flm_version(settings.FLM_BASE_URL, settings.FLM_API_KEY)
    if version.problems():
        print("REFUSED: " + "; ".join(version.problems()))
        return 2

    dev = json.loads(DEV_SET.read_text(encoding="utf-8"))
    items = []
    model = None
    for subject in dev["subjects"]:
        for position, entry in enumerate(subject["items"]):
            result = embed_question(entry["text"])
            model = result.model
            items.append({"subject": subject["id"], "label": subject["subject"], "text": entry["text"],
                          "via": entry["via"], "vector": result.vectors[0]})
            print(f"  embedded {subject['id']}.{position + 1}: {entry['text']}")

    positives, negatives, pairs = [], [], []
    for a, b in itertools.combinations(items, 2):
        sim = cosine_similarity(a["vector"], b["vector"])
        same = a["subject"] == b["subject"]
        (positives if same else negatives).append(sim)
        pairs.append({"a": a["text"], "b": b["text"], "a_subject": a["subject"], "b_subject": b["subject"],
                      "same_subject": same, "similarity": round(sim, 6)})

    lowest_positive, highest_negative = min(positives), max(negatives)
    separates = lowest_positive > highest_negative
    if separates:
        threshold = (lowest_positive + highest_negative) / 2
        choice = {"rule": "midpoint", "threshold": threshold}
    else:
        f1 = best_f1(positives, negatives)
        threshold = f1["threshold"]
        choice = {"rule": "best pairwise F1", **f1}
    gap = lowest_positive - highest_negative
    choice.update({"separates": separates, "lowest_positive": lowest_positive, "highest_negative": highest_negative,
                   "gap": gap, "drift": DRIFT, "gap_exceeds_twice_drift": gap > 2 * DRIFT,
                   "threshold_rounded": round(threshold, 4)})

    hard = []
    for pair in dev.get("hard_negatives", []):
        sims = [p["similarity"] for p in pairs if {p["a_subject"], p["b_subject"]} == {pair["a"], pair["b"]}]
        hard.append({**pair, "max_similarity": max(sims), "above_threshold": max(sims) >= threshold})
    worst_positive = sorted((p for p in pairs if p["same_subject"]), key=lambda p: p["similarity"])[:5]
    worst_negative = sorted((p for p in pairs if not p["same_subject"]), key=lambda p: -p["similarity"])[:5]

    gaps = simulate(items, round(threshold, 4), cosine_similarity)
    simulation = [{"subject": g["subject"], "count": len(g["members"]),
                   "subjects": sorted({m["subject"] for m in g["members"]}),
                   "members": [m["text"] for m in g["members"]]} for g in gaps]
    mixed = [g for g in simulation if len(g["subjects"]) > 1]
    split = sorted({m["subject"] for g in gaps for m in g["members"]} - {g["subjects"][0] for g in simulation if len(g["subjects"]) == 1 and g["count"] == 3})

    record = measurement_record.run_record(dump_sha256=None, database="none: nothing is read from or written to a database",
                                           flm=version.as_record())
    record["configuration"] = provider_record(settings)
    record.update({"kind": "Objective 06 development sweep for GAP_GROUPING_THRESHOLD (D-109)",
                   "dev_set": str(DEV_SET.relative_to(REPOSITORY_ROOT)), "dev_set_sha256": measurement_record.file_sha256(DEV_SET),
                   "embedding_model": model, "items": len(items), "positive_pairs": len(positives), "negative_pairs": len(negatives),
                   "finished_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")})
    summary = {"choice": choice, "hard_negatives": hard, "lowest_positive_pairs": worst_positive,
               "highest_negative_pairs": worst_negative,
               "simulation_at_threshold": {"entries": len(simulation), "expected_entries": len(dev["subjects"]),
                                           "mixed_entries": len(mixed), "subjects_not_in_one_entry_of_three": split,
                                           "entries": simulation}}
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    (arguments.out_dir / "grouping-sweep.json").write_text(
        json.dumps({"record": record, "summary": summary, "pairs": pairs}, indent=2), encoding="utf-8")

    lines = ["# Development sweep for GAP_GROUPING_THRESHOLD (D-109)", "",
             f"Commit {record['commit_sha'][:7]}" + (" (uncommitted tracked changes)" if record["uncommitted_tracked_changes"] else "")
             + f", FLM {version.summary()}, embedding model {model}, {len(items)} items, {len(positives)} positive and {len(negatives)} negative pairs.", "",
             f"- Lowest within-subject similarity: {lowest_positive:.4f}",
             f"- Highest cross-subject similarity: {highest_negative:.4f}",
             f"- Separates: {separates}; gap {gap:+.4f} against D-40's drift of {DRIFT}",
             f"- **Threshold by D-109's rule ({choice['rule']}): {round(threshold, 4)}**", "",
             "## Hard pairs", "", "| a | b | why | max similarity | above threshold |", "|---|---|---|---|---|"]
    lines += [f"| {h['a']} | {h['b']} | {h['why']} | {h['max_similarity']:.4f} | {h['above_threshold']} |" for h in hard]
    lines += ["", "## Lowest within-subject pairs", ""] + [f"- {p['similarity']:.4f}: \"{p['a']}\" / \"{p['b']}\"" for p in worst_positive]
    lines += ["", "## Highest cross-subject pairs", ""] + [f"- {p['similarity']:.4f}: \"{p['a']}\" / \"{p['b']}\"" for p in worst_negative]
    lines += ["", f"## Centroid grouping simulated at {round(threshold, 4)}", "",
              f"{len(simulation)} entries for {len(dev['subjects'])} subjects; {len(mixed)} mixed; subjects not grouped as one entry of three: {split or 'none'}.", "",
              "| Entry subject | Count | Subjects |", "|---|---|---|"]
    lines += [f"| {g['subject']} | {g['count']} | {', '.join(g['subjects'])} |" for g in simulation]
    (arguments.out_dir / "grouping-sweep.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[2:8]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
