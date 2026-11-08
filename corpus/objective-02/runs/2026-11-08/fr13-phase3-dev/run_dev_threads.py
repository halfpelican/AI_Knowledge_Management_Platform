"""Step 7 phase 3: the dev thread set, four ways. TUNING RUNS, not a measurement (D-93).

Four configurations of the two phase-3 changes, each over every run of
corpus/objective-02/dev-threads.json (56 runs: 14 thread-and-role pairs, the first turn
and three ways per follow-up):

    main     the 8 November main: old conversational block, the composed join alone
    option1  the prompt change alone: new block, the join alone
    option2  the retrieval change alone: old block, join AND follow-up, best score
    both     the shipped phase-3 code: new block, both texts, best score

Everything measured is the harness's own: ``citation_harness.measure`` (which embeds
through apps/retrieval/query_embedding.py and ranks with apps/retrieval/ranking.py),
``thread_observation`` and ``thread_set.score``. The configurations differ ONLY in
(a) the two prompt constants, patched to their pre-phase-3 values for main/option2 —
``build_conversational_question`` reads the module globals at call time — and (b) whether
``measure`` is handed one retrieval text or the context's two. ``main`` therefore
reproduces today's main exactly: one text through ``rank_by_best`` of one vector IS the
old ``rank``, byte for byte.

Gates: check_flm.py's checks, the database name, and the corpus-matches-manifest check.
Reads only; the harness's functions write nothing. Console goes to the caller; one JSON
record per configuration lands beside this script.

Usage: python run_dev_threads.py [--configs main option1 option2 both] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
SCRATCH_LOGS = Path(os.environ.get("TEMP", ".")) / "kmp_fr13_phase3_dev_logs"
SCRATCH_LOGS.mkdir(parents=True, exist_ok=True)
DATABASE = "kmp_obj02_20261101"

for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        os.environ["DATABASE_URL"] = re.sub(r"/[^/]+$", f"/{DATABASE}", line.split("=", 1)[1].strip())
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DEBUG="False", AI_PROVIDER="flm",
                  FLM_BASE_URL="http://127.0.0.1:8625/v1",
                  ERROR_LOG_PATH=str(SCRATCH_LOGS / "errors.log"),
                  AUDIT_LOG_PATH=str(SCRATCH_LOGS / "audit.log"),
                  WAITRESS_LOG_PATH=str(SCRATCH_LOGS / "waitress.log"),
                  ATTEMPTS_LOG_PATH=str(SCRATCH_LOGS / "attempts.log"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
os.chdir(REPO)

import django  # noqa: E402

django.setup()

import check_flm  # noqa: E402
import citation_harness as harness  # noqa: E402
import thread_set  # noqa: E402

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402

import apps.ai.prompting as prompting  # noqa: E402
from apps.ai import get_ai_service  # noqa: E402
from apps.core.constants import RELEVANCE_THRESHOLD  # noqa: E402

THREADS = REPO / "corpus/objective-02/dev-threads.json"

# The pre-phase-3 strings, verbatim from apps/ai/prompting.py at 711fcda (origin/main,
# 8 November 2026), so main and option2 prompt exactly what main prompts.
OLD_HEADING = (
    "Earlier questions in this conversation, oldest first. They are provided as context "
    "only, so that a pronoun or an abbreviated reference in the question below can be "
    "resolved. They are NOT passages: they carry no chunk_id, they are not a source of "
    "facts, and nothing in them may be cited."
)
OLD_LEAD_IN = "The question to answer: "

CONFIGS = {
    "main": {"prompt": "old", "retrieval": "single"},
    "option1": {"prompt": "new", "retrieval": "single"},
    "option2": {"prompt": "old", "retrieval": "max2"},
    "both": {"prompt": "new", "retrieval": "max2"},
}
NEW_HEADING, NEW_LEAD_IN = prompting.PRIOR_QUESTIONS_HEADING, prompting.QUESTION_LEAD_IN


def git(*arguments) -> str:
    return subprocess.run(["git", *arguments], capture_output=True, text=True, cwd=REPO).stdout.strip()


def rule_numbers(summary: dict) -> dict:
    """The adoption rule's numbers, read off the per-way summary. Fixed before any run."""
    per_way = summary["per_way"]
    declines = [0, 0]
    for way in thread_set.WAYS:
        got, of = per_way[way]["not_answered_where_expected"]
        declines[0] += got
        declines[1] += of
    return {
        "with_history_match": per_way[thread_set.WITH_HISTORY]["expected_answer_match"],
        "first_turn_match": per_way[thread_set.FIRST_TURN]["expected_answer_match"],
        "spelled_out_match": per_way[thread_set.SPELLED_OUT]["expected_answer_match"],
        "cold_match": per_way[thread_set.COLD]["expected_answer_match"],
        "correct_declines": declines,
        "schema_conformance": summary["schema_conformance"],
        "out_of_scope": summary["out_of_scope_total"],
    }


def run_config(name: str, runs, chunks, sources, service, limit: int) -> dict:
    configuration = CONFIGS[name]
    # The one prompt toggle: the globals build_conversational_question reads at call time.
    prompting.PRIOR_QUESTIONS_HEADING = OLD_HEADING if configuration["prompt"] == "old" else NEW_HEADING
    prompting.QUESTION_LEAD_IN = OLD_LEAD_IN if configuration["prompt"] == "old" else NEW_LEAD_IN
    chosen = runs[:limit] if limit else runs
    results, scored = [], []
    started = time.perf_counter()
    print(f"\n===== configuration {name}: prompt={configuration['prompt']} "
          f"retrieval={configuration['retrieval']}, {len(chosen)} run(s) =====", flush=True)
    for position, run in enumerate(chosen, start=1):
        composed = harness.compose(run["question"], run["prior"])
        if configuration["retrieval"] == "single":
            texts = [composed.for_retrieval]
        else:
            texts = list(composed.retrieval_texts)
        result = harness.QuestionResult(
            question_id=run["run_id"], kind=run["kind"], role=run["role"],
            question=run["question"], expects_answer=run["expects_answer"],
            base_id=run["thread_id"], source=list(run["sources"]), expected_answer=None,
        )
        result.prompt_question = composed.for_prompt
        harness.measure(result, texts, chunks, service, RELEVANCE_THRESHOLD, sources, time.perf_counter())
        score = thread_set.score(run, harness.thread_observation(result, chunks, sources))
        results.append(result)
        scored.append(score)
        print(f"[{position}/{len(chosen)}] {run['run_id']:<34} {score['outcome']:<16} "
              f"match={'yes' if score['expected_answer_match'] else 'no '} "
              f"correct={'yes' if score['correct'] else 'no '} leaks={len(score['leaks'])} "
              f"({result.seconds:.1f}s)", flush=True)
    elapsed = time.perf_counter() - started

    summary = thread_set.summarise(scored)
    responses = [a for r in results for a in r.attempts if a["outcome"] != "call-failed"]
    summary["schema_conformance"] = [sum(a["outcome"] == "parsed" for a in responses), len(responses)]
    numbers = rule_numbers(summary)
    print(f"\n{name}: with-history match {numbers['with_history_match']}, first-turn "
          f"{numbers['first_turn_match']}, spelled-out {numbers['spelled_out_match']}, cold "
          f"{numbers['cold_match']}, declines {numbers['correct_declines']}, schema "
          f"{numbers['schema_conformance']}, out-of-scope {numbers['out_of_scope']}; "
          f"{elapsed / 60:.1f} min", flush=True)

    record = {
        "configuration": name,
        "prompt": configuration["prompt"],
        "retrieval": configuration["retrieval"],
        "heading_used": prompting.PRIOR_QUESTIONS_HEADING,
        "lead_in_used": prompting.QUESTION_LEAD_IN,
        "tuning_run": "DEV SET (D-93): tuned on, never a test; no frozen set was run here",
        "commit_sha": git("rev-parse", "HEAD"),
        "uncommitted_tracked_changes": bool(git("status", "--porcelain", "--untracked-files=no")),
        "database": DATABASE,
        "thread_set": str(THREADS.relative_to(REPO)),
        "thread_set_sha256": thread_set.file_sha256(THREADS),
        "constants": {"RELEVANCE_THRESHOLD": RELEVANCE_THRESHOLD},
        "elapsed_seconds": elapsed,
        "rule_numbers": numbers,
        "summary": summary,
        "runs": [harness.thread_run_record(run, result, score, sources)
                 for run, result, score in zip(chosen, results, scored)],
    }
    out = HERE / f"dev_{name}.json"
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"record written to {out}", flush=True)
    return numbers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="+", default=list(CONFIGS), choices=list(CONFIGS))
    parser.add_argument("--limit", type=int, default=0)
    arguments = parser.parse_args()

    if connection.settings_dict["NAME"] != DATABASE:
        print(f"refusing: connected to {connection.settings_dict['NAME']!r}")
        return 2
    checks = check_flm.run_checks(settings.FLM_BASE_URL, settings.FLM_API_KEY,
                                  settings.FLM_CHAT_MODEL, settings.FLM_EMBED_MODEL)
    if not check_flm.checks_passed(checks):
        print("refusing: check_flm.py's checks did not pass")
        return 2
    version = check_flm.flm_version(settings.FLM_BASE_URL, settings.FLM_API_KEY)
    print(f"FLM {version.summary()}")

    payload, threads, readable = harness.load_thread_set(THREADS)
    runs = thread_set.expand_runs(threads, harness.ROLES, readable)
    chunks = harness.load_corpus()
    manifest_items = json.loads((REPO / payload["manifest"]).read_text(encoding="utf-8"))["items"]
    sources = harness.index_sources(chunks, manifest_items)
    mismatch = harness.corpus_problems(chunks, sources, manifest_items, settings.FLM_EMBED_MODEL)
    for problem in mismatch:
        print(f"CORPUS: {problem}")
    if mismatch:
        print("refusing: the indexed corpus is not exactly the manifest's")
        return 2
    print(f"dev threads: {len(threads)} thread(s), {len(runs)} run(s) per configuration; "
          f"set sha256 {thread_set.file_sha256(THREADS)[:16]}")

    service = get_ai_service()
    table = {}
    for name in arguments.configs:
        table[name] = run_config(name, runs, chunks, sources, service, arguments.limit)
    # Leave the live globals as the shipped code defines them.
    prompting.PRIOR_QUESTIONS_HEADING, prompting.QUESTION_LEAD_IN = NEW_HEADING, NEW_LEAD_IN

    print("\n===== four-way table (expected-answer match; declines are correct declines) =====")
    for name, numbers in table.items():
        print(f"{name:<8} with-history {numbers['with_history_match']}  first-turn "
              f"{numbers['first_turn_match']}  spelled-out {numbers['spelled_out_match']}  "
              f"cold {numbers['cold_match']}  declines {numbers['correct_declines']}  "
              f"schema {numbers['schema_conformance']}  out-of-scope {numbers['out_of_scope']}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
