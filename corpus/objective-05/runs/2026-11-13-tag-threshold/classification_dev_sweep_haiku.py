"""D-129's tag and department threshold (13 November 2026): the classifications for D-106's rule.

A byte-for-byte copy of corpus/objective-05/runs/2026-11-10/dev-sweep-haiku/classification_dev_sweep_haiku.py
except this paragraph, run on the shipped prompt (byte-identical to #85's, D-129). It classifies the
development documents three times each and records every suggestion with its confidence. The tag
and department threshold is chosen from that record by tag_threshold_rule.py in this folder, against
corpus/objective-05/dev-documents/tag-reference.json; both were committed before this ran. Its own
type-threshold choice is printed for information and decides nothing here. Its docstring follows.

D-106's sweep on Claude Haiku 5.5 (10 November 2026): CLASSIFICATION_CONFIDENCE_THRESHOLD for it.

A copy of scripts/classification_dev_sweep.py at 910d1ff, changed only where FLM was named, so that
the rule D-106 fixed runs on the anthropic provider's classification model before that provider
becomes the default (CLAUDE.md section 4: every tuned value is re-derived first):

- AI_PROVIDER is anthropic, ANTHROPIC_MODEL claude-haiku-5-5 (D-121) and EMBEDDING_DIMENSION 1024,
  set before Django starts, so every classification goes through AnthropicService.classify_document.
- The check_flm.py gate and the FLM version are replaced by a provider gate (the provider, the model,
  the Anthropic key present and never printed). The record names the Claude model as its chat model.
- Claude's token usage is tallied by a wrapper around AnthropicService._claude_once that records each
  reply's counts and changes nothing, for the spend report.

D-106's rule, the documents, the scheme, the repetitions and the outputs are the original's. The
original docstring follows.

Choose CLASSIFICATION_CONFIDENCE_THRESHOLD on the development documents (D-106).

Classifies every document in corpus/objective-05/dev-documents/manifest.json, several times
each, against the corpus scheme, through the shipped AI operation ``classify_document``
(D-104), and applies the rule D-106 fixed before the run:

    T is the value that maximises
        (# correct type assignments with confidence >= T) + (# wrong ones with confidence < T),
    a tie going to the higher value; then T is capped at the lowest confidence seen on a
    correct assignment minus MARGIN (0.05). If no T beats the trivial score (every assignment
    applied), the confidences do not separate correct from wrong: that is reported, and T is
    the lowest confidence seen on a correct assignment.

Nothing is written to any database: the documents are read from disk, the scheme is built from
corpus/objective-02/manifest.json (the six departments and fourteen tag values the twenty
reference documents see on kmp_obj0506_20261101), and the output goes to ``--out-dir``. The
run records the commit, the FLM version and the constants, as every measurement does (D-84),
and refuses an FLM other than v0.9.39 (D-83).

Usage, in PowerShell, with FLM serving::

    .venv\\Scripts\\python.exe scripts\\classification_dev_sweep.py --out-dir corpus\\objective-05\\runs\\2026-11-09\\dev-sweep
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]  # corpus/objective-05/runs/<date>/<this folder>
SCRIPTS = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


DEV_MANIFEST = REPOSITORY_ROOT / "corpus" / "objective-05" / "dev-documents" / "manifest.json"
CORPUS_MANIFEST = REPOSITORY_ROOT / "corpus" / "objective-02" / "manifest.json"
MARGIN = 0.05
REQUIRED_FLM = "v0.9.39"


def document_text(path: Path) -> str:
    """The document's text as ingestion would store it: the project's own extractor, by format.

    Since 10 November 2026 (D-106's note), so that a spreadsheet reaches the classifier exactly
    as a reference spreadsheet's ExtractedContent does. The first two sweeps read .txt directly
    and .docx paragraphs with python-docx, which gives the same text for those files.
    """
    from apps.ingestion.extraction import extract_plain_text

    with path.open("rb") as handle:
        return extract_plain_text(handle, path.suffix.lower().lstrip("."))


def corpus_scheme():
    """The scheme the twenty see: DOCUMENT_TYPES, the manifest's departments and tag values."""
    from apps.ai.base import TagScheme
    from apps.core.constants import DOCUMENT_TYPES, REPOSITORY_TAG_DIMENSIONS
    from apps.documents.models import normalise_tag_name

    items = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))["items"]
    departments = sorted({item["department"] for item in items if item.get("kind") == "document" and item.get("department")})
    tags = {dimension: set() for dimension in REPOSITORY_TAG_DIMENSIONS}
    for item in items:
        for dimension, values in (item.get("tags") or {}).items():
            if dimension in tags:
                tags[dimension].update(normalise_tag_name(value) for value in values)
    return TagScheme(
        doc_types=tuple(DOCUMENT_TYPES),
        departments=tuple(departments),
        tags={dimension: tuple(sorted(values)) for dimension, values in tags.items()},
    )


def git(*arguments: str) -> str:
    completed = subprocess.run(["git", "-C", str(REPOSITORY_ROOT), *arguments],
                               capture_output=True, text=True, timeout=30, check=False)
    return completed.stdout.strip()


def choose_threshold(observations: list[dict]) -> dict:
    """D-106's rule over (confidence, correct) pairs for the TYPE assignment."""
    scored = [(float(o["doc_type_confidence"]), bool(o["type_correct"])) for o in observations
              if o.get("doc_type_confidence") is not None]
    correct = [c for c, ok in scored if ok]
    wrong = [c for c, ok in scored if not ok]
    if not correct:
        return {"threshold": None, "separates": False, "reason": "no correct assignment observed"}
    trivial = len(correct)  # T = 0: everything applied
    candidates = sorted({c for c, _ in scored} | {0.0, 1.0})
    best_score, best_t = trivial, 0.0
    table = []
    for t in candidates:
        score = sum(1 for c in correct if c >= t) + sum(1 for c in wrong if c < t)
        table.append({"t": t, "score": score})
        if score > best_score or (score == best_score and t > best_t and score > trivial):
            best_score, best_t = score, t
    lowest_correct = min(correct)
    if best_score <= trivial:
        return {"threshold": round(lowest_correct, 3), "separates": False, "best_score": best_score,
                "trivial_score": trivial, "lowest_correct": lowest_correct,
                "reason": "no threshold beats applying everything: confidences do not separate correct from wrong",
                "table": table}
    capped = min(best_t, lowest_correct - MARGIN)
    return {"threshold": round(capped, 3), "separates": True, "uncapped": best_t, "best_score": best_score,
            "trivial_score": trivial, "lowest_correct": lowest_correct, "margin": MARGIN,
            "highest_wrong": max(wrong) if wrong else None, "table": table}


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
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="first N documents only (a smoke test, not a measurement)")
    arguments = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["AI_PROVIDER"] = "anthropic"  # this copy: Claude classification (D-113)
    os.environ["ANTHROPIC_MODEL"] = "claude-haiku-5-5"  # D-121
    os.environ["EMBEDDING_DIMENSION"] = "1024"
    import django

    django.setup()
    from django.conf import settings

    import apps.ai
    from apps.ai.base import ProviderUnavailable
    from apps.core import constants

    if arguments.out_dir.exists() and any(arguments.out_dir.iterdir()):
        print(f"REFUSED: {arguments.out_dir} already holds files; a run never overwrites a record")
        return 2
    arguments.out_dir.mkdir(parents=True, exist_ok=True)

    # This copy: the provider gate in place of check_flm.py's (FLM takes no part).
    problems = [f"settings.{name} is {getattr(settings, name)!r}, not {expected!r}"
                for name, expected in (("AI_PROVIDER", "anthropic"), ("ANTHROPIC_MODEL", "claude-haiku-5-5"))
                if getattr(settings, name) != expected]
    if not settings.ANTHROPIC_API_KEY:
        problems.append("settings.ANTHROPIC_API_KEY is empty")  # its value is never printed
    if problems:
        print("REFUSED: " + "; ".join(problems))
        return 2
    print("Provider gate: PASS (anthropic, claude-haiku-5-5)")

    # This copy: Claude's token usage, for the spend report; the reply is returned unchanged.
    from apps.ai.anthropic import AnthropicService

    usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    original_claude_once = AnthropicService._claude_once

    def counting_claude_once(self, *args, **kwargs):
        reply = original_claude_once(self, *args, **kwargs)
        usage["calls"] += 1
        usage["input_tokens"] += reply.prompt_tokens or 0
        usage["output_tokens"] += reply.completion_tokens or 0
        return reply

    AnthropicService._claude_once = counting_claude_once

    manifest = json.loads(DEV_MANIFEST.read_text(encoding="utf-8"))
    documents = manifest["documents"][: arguments.limit] if arguments.limit else manifest["documents"]
    scheme = corpus_scheme()
    service = apps.ai.get_ai_service()

    record = {
        "kind": "Objective 05 development sweep for CLASSIFICATION_CONFIDENCE_THRESHOLD (D-106)",
        "recorded_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "commit_sha": git("rev-parse", "HEAD"),
        "uncommitted_tracked_changes": bool(git("status", "--porcelain", "--untracked-files=no")),
        "flm_version": None,  # this copy: FLM takes no part
        "chat_model": settings.ANTHROPIC_MODEL,
        "dev_manifest": str(DEV_MANIFEST.relative_to(REPOSITORY_ROOT)),
        "scheme": {"doc_types": scheme.doc_types, "departments": scheme.departments, "tags": scheme.tags},
        "constants": {
            "CLASSIFICATION_CONFIDENCE_THRESHOLD_before": constants.CLASSIFICATION_CONFIDENCE_THRESHOLD,
            "CLASSIFICATION_INPUT_TOKENS": constants.CLASSIFICATION_INPUT_TOKENS,
            "MAXIMUM_CLASSIFY_ATTEMPTS": constants.MAXIMUM_CLASSIFY_ATTEMPTS,
        },
        "repetitions": arguments.repetitions,
        "database": "none: nothing is read from or written to a database",
    }

    record["configuration"] = provider_record(settings)

    observations: list[dict] = []
    for document in documents:
        path = (DEV_MANIFEST.parent / document["file"]).resolve()
        text = document_text(path)
        for repetition in range(1, arguments.repetitions + 1):
            started = time.perf_counter()
            row = {"id": document["id"], "title": document["title"], "reference_type": document["doc_type"],
                   "repetition": repetition, "words": len(text.split())}
            try:
                result = service.classify_document(document["title"], text, scheme)
            except ProviderUnavailable as exc:
                row.update({"error": str(exc), "seconds": round(time.perf_counter() - started, 1)})
                print(f"  {document['id']} #{repetition}: FAILED {exc}")
            else:
                row.update({
                    "doc_type": result.doc_type.value,
                    "doc_type_confidence": result.doc_type.confidence,
                    "type_correct": result.doc_type.value == document["doc_type"],
                    "department": result.department.value,
                    "department_confidence": result.department.confidence,
                    "department_in_scheme": result.department.value in scheme.departments,
                    "tags": [{"dimension": t.dimension, "value": t.value, "confidence": t.confidence,
                              "in_scheme": t.value in scheme.tags.get(t.dimension, ())} for t in result.tags],
                    "input_truncated": result.input_truncated,
                    "seconds": round(time.perf_counter() - started, 1),
                })
                mark = "ok " if row["type_correct"] else "MISS"
                print(f"  {document['id']} #{repetition}: {mark} {result.doc_type.value} ({result.doc_type.confidence:.2f}) "
                      f"dept {result.department.value} ({result.department.confidence:.2f}) {row['seconds']}s")
            observations.append(row)

    done = [o for o in observations if "error" not in o]
    choice = choose_threshold(done)
    summary = {
        "classifications": len(observations),
        "failed": len(observations) - len(done),
        "type_correct": sum(1 for o in done if o["type_correct"]),
        "type_match_rate": round(100 * sum(1 for o in done if o["type_correct"]) / len(done), 1) if done else None,
        "department_in_scheme": sum(1 for o in done if o["department_in_scheme"]),
        "tags_total": sum(len(o["tags"]) for o in done),
        "tags_out_of_scheme": sum(1 for o in done for t in o["tags"] if not t["in_scheme"]),
        "correct_confidences": sorted(o["doc_type_confidence"] for o in done if o["type_correct"]),
        "wrong_confidences": sorted(o["doc_type_confidence"] for o in done if not o["type_correct"]),
        "seconds_median": round(statistics.median(o["seconds"] for o in done), 1) if done else None,
        "threshold_choice": choice,
    }
    record["claude_usage"] = {**usage, "estimated_usd": round((usage["input_tokens"] * 0.10
                                                               + usage["output_tokens"] * 0.50) / 1_000_000, 4)}
    (arguments.out_dir / "dev-sweep.json").write_text(
        json.dumps({"record": record, "observations": observations, "summary": summary}, indent=2), encoding="utf-8")

    lines = ["# Development sweep for CLASSIFICATION_CONFIDENCE_THRESHOLD (D-106)", "",
             f"Commit {record['commit_sha'][:7]}" + (" (uncommitted tracked changes)" if record["uncommitted_tracked_changes"] else "")
             + f", the anthropic provider ({settings.ANTHROPIC_MODEL}), {arguments.repetitions} repetitions, {len(documents)} documents.", "",
             "| Id | Reference | Rep | Suggested | Confidence | Department | Dept conf | Tags (out of scheme) | s |",
             "|---|---|---|---|---|---|---|---|---|"]
    for o in observations:
        if "error" in o:
            lines.append(f"| {o['id']} | {o['reference_type']} | {o['repetition']} | FAILED | | | | {o['error'][:60]} | {o['seconds']} |")
            continue
        out = sum(1 for t in o["tags"] if not t["in_scheme"])
        lines.append(f"| {o['id']} | {o['reference_type']} | {o['repetition']} | {o['doc_type']}{'' if o['type_correct'] else ' (miss)'} | "
                     f"{o['doc_type_confidence']:.2f} | {o['department']}{'' if o['department_in_scheme'] else ' (out)'} | "
                     f"{o['department_confidence']:.2f} | {len(o['tags'])} ({out}) | {o['seconds']} |")
    lines += ["", f"Type matches: {summary['type_correct']} of {len(done)} ({summary['type_match_rate']}%), failures {summary['failed']}.",
              f"Correct-assignment confidences: {summary['correct_confidences']}",
              f"Wrong-assignment confidences: {summary['wrong_confidences']}", "",
              f"**Threshold by D-106's rule: {choice.get('threshold')}** (separates: {choice.get('separates')}; {choice.get('reason', '')})"]
    (arguments.out_dir / "dev-sweep.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {arguments.out_dir / 'dev-sweep.json'} and dev-sweep.md")
    print(f"threshold by D-106's rule: {choice.get('threshold')} (separates: {choice.get('separates')})")
    print(f"Claude usage: {record['claude_usage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
