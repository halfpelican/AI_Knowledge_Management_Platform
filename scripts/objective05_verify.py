"""Objective 05's verification: the twenty classified documents against the frozen reference set.

Reads the DocumentAnalysis and ContentTag rows `manage.py classify_documents --all` wrote on the
measurement database (D-106) and scores them against corpus/objective-05/reference.json (the type)
and corpus/objective-02/manifest.json (the department and the tags). Writes nothing to the
database. The three clauses of Objective 05, as the proposal words them:

1. "at least 75% of suggested document types must match the reference": machine_doc_type against
   the reference, over all twenty, provisional or not (D-106).
2. "any assignment falling below the configured confidence threshold must be marked provisional
   and held for confirmation rather than applied": every type, department and tag assignment with
   a confidence under its threshold has the provisional outcome (or flag) and its effective field
   was not written; every one at or above it was applied. "The configured confidence threshold" is
   read as one configured threshold per kind of assignment (D-129): the type and the tags are judged
   by ``confidence_threshold(model)``, the department by ``department_threshold(model)``, each the
   classifying model's own, and ``thresholds_used`` records both values per model.
3. "suggested values falling outside the established scheme must be discarded in the Department,
   Project and Process dimensions while being proposed for confirmation in the Topic dimension
   only": out-of-scheme departments carry the discarded outcome, out-of-scheme Project and Process
   values appear only in discarded_suggestions and never as links, and out-of-scheme Topic values
   appear only in proposed_tags and never as links.

**The shipped build meets clause 3 again since D-129** (13 November 2026), which reverses D-128's
creation of values. A Topic value outside the scheme is held in ``DocumentAnalysis.proposed_tags``
(``proposed_topics`` until ``documents 0012``) at any confidence. A Project or Process value is
discarded into ``discarded_suggestions``. No Tag is created. From 12 to 13 November 2026, D-128
created and applied such a value at or above the threshold, and held one in any of the three
dimensions below it. This script still counts any such departure strictly, so a run on a build or
database from that window shows it rather than hiding it. Counted per document:

- a Topic entry of ``proposed_tags`` is ``topic_proposed``, as clause 3 asks;
- a Project or Process entry is ``project_process_proposed`` and a **clause 3 violation**: the
  clause says such a value is discarded;
- an AI link whose Tag is ``grown`` is a value the classifier created outside the seeded scheme,
  counted as ``created_by_classifier`` and recorded as a **clause 3 violation**. On a measurement
  database no person acts, and the scheme is seeded ``--scheme-only``, whose values are never
  grown. Only D-128's creation made a grown tag there, so a grown tag on an AI link can have come
  from nowhere else.

Clause 3 is MET when no such violation is found. PR 85's evidence stands for the build it ran on.
The reference set (corpus/objective-05/reference.json) is frozen and is only read.

Usage, in PowerShell::

    $env:DATABASE_URL = "<the measurement database's URL>"
    .venv\\Scripts\\python.exe scripts\\objective05_verify.py --dump-sha256 <hex> `
        --classify-record corpus\\objective-05\\runs\\<date>\\classify.json `
        --out-dir corpus\\objective-05\\runs\\<date>\\verification
"""

from __future__ import annotations

import argparse
import json
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

REFERENCE = REPOSITORY_ROOT / "corpus" / "objective-05" / "reference.json"
MANIFEST = REPOSITORY_ROOT / "corpus" / "objective-02" / "manifest.json"


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
    parser.add_argument("--dump-sha256", required=True)
    parser.add_argument("--classify-record", type=Path, help="the JSON classify_documents --out wrote, copied into the record")
    arguments = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings

    from apps.core.constants import (
        ASSIGNMENT_OUTCOMES, CLASSIFICATION_CONFIDENCE_THRESHOLD, CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL,
        CLASSIFICATION_DEPARTMENT_CONFIDENCE_THRESHOLD_BY_MODEL, REPOSITORY_TAG_DIMENSIONS, SOURCE_TYPES,
    )
    from apps.documents.classification import confidence_threshold, department_threshold
    from apps.documents.models import ContentTag, Document, DocumentAnalysis, normalise_tag_name

    applied, provisional, discarded, confirmed = ASSIGNMENT_OUTCOMES
    document_source = SOURCE_TYPES[0]
    database = str(settings.DATABASES["default"]["NAME"])
    print(f"database: {database}")
    measurement_record.refuse_protected_database(database)
    if arguments.out_dir.exists() and any(arguments.out_dir.iterdir()):
        print(f"REFUSED: {arguments.out_dir} already holds files")
        return 2

    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    manifest = {item["id"]: item for item in json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]}
    threshold = CLASSIFICATION_CONFIDENCE_THRESHOLD
    version = check_flm.flm_version(settings.FLM_BASE_URL, settings.FLM_API_KEY)
    record = measurement_record.run_record(dump_sha256=arguments.dump_sha256, database=database, flm=version.as_record())
    record["configuration"] = provider_record(settings)
    record.update({
        "kind": "Objective 05 verification (D-106)",
        "reference_set": str(REFERENCE.relative_to(REPOSITORY_ROOT)),
        "reference_set_sha256": measurement_record.file_sha256(REFERENCE),
        "reference_set_status": reference.get("status"),
        "threshold": threshold,
        # D-122: each analysis is judged by its own model's threshold; thresholds_used records them.
        "threshold_by_model": dict(CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL),
        # D-129: a department is judged by its own threshold, this map's value for a listed model
        # and the shared one otherwise.
        "department_threshold_by_model": dict(CLASSIFICATION_DEPARTMENT_CONFIDENCE_THRESHOLD_BY_MODEL),
        "verified_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "classify_record": json.loads(arguments.classify_record.read_text(encoding="utf-8")) if arguments.classify_record else None,
    })

    rows, problems = [], []
    clause2 = {"below_threshold": 0, "below_and_held": 0, "at_or_above": 0, "at_or_above_and_applied": 0,
               "at_or_above_held_to_keep_a_given_department": 0, "violations": []}
    # D-128: project_process_proposed and created_by_classifier count the departures from clause 3,
    # and each one is also recorded as a violation (see the module docstring).
    clause3 = {"department_out_of_scheme": 0, "department_discarded": 0, "project_process_discarded": 0,
               "topic_proposed": 0, "project_process_proposed": 0, "created_by_classifier": 0,
               "out_of_scheme_links": 0, "violations": []}
    tag_hits = tag_suggested = tag_reference = 0
    # {model: {"type_and_tags": ..., "department": ...}}: one threshold per kind of assignment (D-129).
    thresholds_used: dict[str, dict[str, float]] = {}
    record["thresholds_used"] = thresholds_used  # filled per analysis below, before the record is written

    for entry in reference["documents"]:
        item = manifest[entry["id"]]
        documents = list(Document.objects.filter(title=entry["title"]))
        if len(documents) != 1:
            problems.append(f"{entry['id']}: {len(documents)} documents titled {entry['title']!r}")
            continue
        document = documents[0]
        analysis = DocumentAnalysis.objects.filter(document=document).first()
        row = {"id": entry["id"], "title": entry["title"], "reference_type": entry["doc_type"], "fit": entry["fit"],
               "reference_department": item["department"], "reference_tags": item.get("tags") or {}}
        if analysis is None:
            row.update({"classified": False})
            rows.append(row)
            continue
        # D-122: the threshold the apply layer used for this analysis is its model's own, and since
        # D-129 one per kind: the type and the tags use ``threshold``, the department its own.
        threshold = confidence_threshold(analysis.model)
        dept_threshold = department_threshold(analysis.model)
        thresholds_used[analysis.model] = {"type_and_tags": threshold, "department": dept_threshold}
        type_conf = float(analysis.machine_doc_type_confidence) if analysis.machine_doc_type_confidence is not None else None
        dept_conf = float(analysis.machine_department_confidence) if analysis.machine_department_confidence is not None else None
        row.update({
            "classified": True,
            "machine_doc_type": analysis.machine_doc_type, "machine_doc_type_confidence": type_conf,
            "doc_type_outcome": analysis.doc_type_outcome, "effective_doc_type": analysis.doc_type,
            "type_match": analysis.machine_doc_type == entry["doc_type"],
            "machine_department": analysis.machine_department, "machine_department_confidence": dept_conf,
            "department_outcome": analysis.department_outcome, "effective_department": document.department,
            "department_match": analysis.machine_department == item["department"],
            "user_edited": analysis.user_edited, "input_truncated": analysis.input_truncated,
            "proposed_tags": analysis.proposed_tags, "discarded_suggestions": analysis.discarded_suggestions,
            "model": analysis.model,
        })
        # Clause 2 on the type.
        if type_conf is not None and not analysis.user_edited:
            if type_conf < threshold:
                clause2["below_threshold"] += 1
                if analysis.doc_type_outcome == provisional and analysis.doc_type is None:
                    clause2["below_and_held"] += 1
                else:
                    clause2["violations"].append(f"{entry['id']} type {type_conf} < {threshold} but outcome {analysis.doc_type_outcome}, effective {analysis.doc_type}")
            else:
                clause2["at_or_above"] += 1
                if analysis.doc_type_outcome == applied and analysis.doc_type == analysis.machine_doc_type:
                    clause2["at_or_above_and_applied"] += 1
                else:
                    clause2["violations"].append(f"{entry['id']} type {type_conf} >= {threshold} but outcome {analysis.doc_type_outcome}")
        # Clauses 2 and 3 on the department.
        if analysis.department_outcome == discarded:
            clause3["department_out_of_scheme"] += 1
            clause3["department_discarded"] += 1
            if document.department == analysis.machine_department and analysis.machine_department:
                clause3["violations"].append(f"{entry['id']} discarded department was written")
        elif dept_conf is not None and not analysis.user_edited:
            # The department's own threshold (D-129), not the type's and the tags'.
            if dept_conf < dept_threshold:
                clause2["below_threshold"] += 1
                if analysis.department_outcome == provisional:
                    clause2["below_and_held"] += 1
                else:
                    clause2["violations"].append(f"{entry['id']} department {dept_conf} < {dept_threshold} but outcome {analysis.department_outcome}")
            else:
                clause2["at_or_above"] += 1
                if analysis.department_outcome == applied and document.department == analysis.machine_department:
                    clause2["at_or_above_and_applied"] += 1
                elif (analysis.department_outcome == provisional and document.department
                      and document.department != analysis.machine_department):
                    # D-105's note of 10 November: the machine fills only a blank department, so a
                    # different suggestion is held against the department the document already has.
                    clause2["at_or_above_held_to_keep_a_given_department"] += 1
                else:
                    clause2["violations"].append(f"{entry['id']} department {dept_conf} >= {dept_threshold} but outcome {analysis.department_outcome}")
        # Tags: the AI links on this document, with provenance.
        links = list(ContentTag.objects.filter(source_type=document_source, source_id=document.id).select_related("tag"))
        ai_links = [link for link in links if link.applied_by == "ai"]
        row["ai_tags"] = [{"dimension": l.tag.dimension, "name": l.tag.tag_name, "confidence": float(l.confidence) if l.confidence is not None else None,
                           "provisional": l.provisional, "confirmed": l.confirmed,
                           # D-128: a grown tag on a measurement database is one the classifier created.
                           "created_by_classifier": l.tag.grown} for l in ai_links]
        for link in ai_links:
            if link.confidence is None or link.confirmed:
                continue
            conf = float(link.confidence)
            if conf < threshold:
                clause2["below_threshold"] += 1
                clause2["below_and_held"] += int(link.provisional)
                if not link.provisional:
                    clause2["violations"].append(f"{entry['id']} tag {link.tag.tag_name} {conf} < {threshold} not provisional")
            else:
                clause2["at_or_above"] += 1
                clause2["at_or_above_and_applied"] += int(not link.provisional)
                if link.provisional:
                    clause2["violations"].append(f"{entry['id']} tag {link.tag.tag_name} {conf} >= {threshold} provisional")
            if link.tag.dimension not in REPOSITORY_TAG_DIMENSIONS:
                clause3["out_of_scheme_links"] += 1
                clause3["violations"].append(f"{entry['id']} link in dimension {link.tag.dimension}")
        # D-128: an AI link to a grown tag is a value the classifier created outside the seeded
        # scheme (see the module docstring). Clause 3 says such a value is never linked: a Project or
        # Process one is discarded, a Topic one only proposed. Every link counts, whatever its state.
        for link in ai_links:
            if link.tag.grown:
                clause3["created_by_classifier"] += 1
                clause3["violations"].append(
                    f"{entry['id']} {link.tag.dimension} value {link.tag.tag_name!r} created outside the "
                    f"scheme and linked (D-128)"
                )
        for suggestion in analysis.discarded_suggestions or []:
            if suggestion.get("dimension") in ("Project", "Process"):
                clause3["project_process_discarded"] += 1
            else:
                clause3["violations"].append(f"{entry['id']} discarded a {suggestion.get('dimension')} value")
        for proposal in analysis.proposed_tags or []:
            dimension = proposal.get("dimension") if isinstance(proposal, dict) else None
            if dimension == "Topic":
                clause3["topic_proposed"] += 1
            elif dimension in ("Project", "Process"):
                # D-128 holds a Project or Process value below the threshold; clause 3 discards it.
                clause3["project_process_proposed"] += 1
                clause3["violations"].append(
                    f"{entry['id']} {dimension} value {proposal.get('value')!r} proposed, not discarded (D-128)"
                )
            else:
                clause3["violations"].append(f"{entry['id']} proposed a value in dimension {dimension!r}")
        # Tags against the manifest, for information.
        reference_pairs = {(dimension, normalise_tag_name(value)) for dimension, values in (item.get("tags") or {}).items() for value in values}
        suggested_pairs = {(l.tag.dimension, l.tag.tag_name) for l in ai_links}
        tag_reference += len(reference_pairs)
        tag_suggested += len(suggested_pairs)
        tag_hits += len(reference_pairs & suggested_pairs)
        rows.append(row)

    classified = [r for r in rows if r.get("classified")]
    matches = sum(1 for r in classified if r["type_match"])
    summary = {
        "documents": len(rows), "classified": len(classified), "problems": problems,
        "clause_1": {"type_matches": matches, "of": len(rows), "rate_percent": round(100 * matches / len(rows), 1) if rows else None,
                     "passes_75_percent": bool(rows) and matches / len(rows) >= 0.75,
                     "misses": [{"id": r["id"], "reference": r["reference_type"], "suggested": r.get("machine_doc_type"), "fit": r["fit"]}
                                for r in rows if not r.get("type_match")],
                     "department_matches": sum(1 for r in classified if r["department_match"])},
        "clause_2": {**clause2, "passes": not clause2["violations"]},
        "clause_3": {**clause3, "passes": not clause3["violations"]},
        "tags_for_information": {"reference_pairs": tag_reference, "ai_suggested_pairs": tag_suggested, "in_both": tag_hits,
                                 "precision_percent": round(100 * tag_hits / tag_suggested, 1) if tag_suggested else None,
                                 "recall_percent": round(100 * tag_hits / tag_reference, 1) if tag_reference else None},
    }
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    (arguments.out_dir / "verification.json").write_text(json.dumps({"record": record, "rows": rows, "summary": summary}, indent=2, default=str), encoding="utf-8")
    lines = ["# Objective 05 verification (D-106)", "",
             f"Commit {record['commit_sha'][:7]}" + (" (uncommitted tracked changes)" if record["uncommitted_tracked_changes"] else "")
             + f", database {database}, dump {record['dump_sha256'][:8]}…, FLM {version.summary()}, "
             f"thresholds by model, per kind of assignment (D-129) {thresholds_used or {'(none classified)': CLASSIFICATION_CONFIDENCE_THRESHOLD}}.", "",
             "| Id | Reference | Suggested | Conf | Type outcome | Dept suggested | Dept conf | Dept outcome | AI tags (provisional) | Created by classifier | Proposed | Discarded |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r.get("classified"):
            lines.append(f"| {r['id']} | {r['reference_type']} | NOT CLASSIFIED | | | | | | | | | |"); continue
        prov = sum(1 for t in r["ai_tags"] if t["provisional"])
        created = sum(1 for t in r["ai_tags"] if t["created_by_classifier"])
        lines.append(f"| {r['id']} | {r['reference_type']} | {r['machine_doc_type']}{'' if r['type_match'] else ' (miss)'} | {r['machine_doc_type_confidence']} | {r['doc_type_outcome']} | "
                     f"{r['machine_department']}{'' if r['department_match'] else ' (differs)'} | {r['machine_department_confidence']} | {r['department_outcome']} | {len(r['ai_tags'])} ({prov}) | "
                     f"{created} | {len(r['proposed_tags'] or [])} | {len(r['discarded_suggestions'] or [])} |")
    c1, c2, c3 = summary["clause_1"], summary["clause_2"], summary["clause_3"]
    lines += ["", f"**Clause 1:** {c1['type_matches']} of {c1['of']} types match the reference ({c1['rate_percent']}%); 75% {'MET' if c1['passes_75_percent'] else 'NOT MET'}. Misses: {c1['misses']}",
              f"**Clause 2:** {c2['below_and_held']} of {c2['below_threshold']} below-threshold assignments held as provisional; {c2['at_or_above_and_applied']} of {c2['at_or_above']} at or above applied and {c2['at_or_above_held_to_keep_a_given_department']} held to keep a department the document already had; violations: {c2['violations'] or 'none'}.",
              f"**Clause 3:** {'MET' if c3['passes'] else 'NOT MET'}. Departments discarded {c3['department_discarded']}, Project/Process suggestions discarded {c3['project_process_discarded']}, Topic values proposed {c3['topic_proposed']}, "
              f"Project/Process values proposed {c3['project_process_proposed']} and values created by the classifier {c3['created_by_classifier']} (both D-128's departures from the clause), out-of-scheme links {c3['out_of_scheme_links']}; violations: {c3['violations'] or 'none'}.",
              f"Tags against the manifest, for information: precision {summary['tags_for_information']['precision_percent']}%, recall {summary['tags_for_information']['recall_percent']}%."]
    if problems:
        lines += ["", "Problems: " + "; ".join(problems)]
    (arguments.out_dir / "verification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-5:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
