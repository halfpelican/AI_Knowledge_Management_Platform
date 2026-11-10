"""Step 7 phase 4: the dev thread set, main vs option 3, means over 3 draws. TUNING (D-93).

The adoption rule, fixed BEFORE any run (the user's phase-4 brief, 9 November 2026):

- Two arms over corpus/objective-02/dev-threads.json (19 threads, 22 thread-and-role
  pairs, 88 runs with cold):
      main     today's shipped retrieval: the composed join embedded, no rewrite call
      option3  the phase-4 code as committed (48c20cf): resolve_retrieval_text() — the
               model's standalone rewrite embedded, the join on any failure
- THREE DRAWS PER ARM of with-history, spelled-out, first-turn and the decline guards;
  cold ONCE per arm (draw 1 only), diagnostic. Draws alternate arms so FLM drift lands
  evenly.
- Adopt option 3 only if its MEAN with-history expected-answer match exceeds main's by
  MORE THAN 2 runs, with no guard arm's mean (first-turn, spelled-out, correct declines)
  lower by more than 1 run, schema conformance intact, and 0 out-of-scope anywhere.
- D-103's variance band stands behind the rule: single-pass deltas of ±1–2 runs on sets
  this size are noise, which is why the rule compares means.

Both arms run the HARNESS'S OWN functions (measure, thread_observation, thread_set.score)
over the same loaded corpus. The arms differ in exactly one line: what produces the
retrieval text for a with-history run. option3 calls the shipped
``apps.retrieval.pipeline.resolve_retrieval_text`` — the function POST /api/ask and
``citation_harness --threads`` run — timed per call, with the rewrite text and the
fallback cause recorded per run. main embeds ``compose().for_retrieval`` directly, which
is byte-for-byte the pre-phase-4 path (a passthrough, no model call, no patching of
shipped code). The generation prompt is compose()'s block in both arms: phase 4 does not
touch prompting.

One invocation = one arm, one draw, so scripts/check_flm.py gates EVERY run (D-83) and
each draw has its own record. Reads only; DATABASE_URL is swapped in this process's
environment and never printed. Console goes to the caller; one JSON record per draw
lands beside this script as ``dev_<arm>_draw<n>.json``.

Usage: python run_dev_threads.py --arm {main,option3} --draw {1,2,3} [--limit N]
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
SCRATCH_LOGS = Path(os.environ.get("TEMP", ".")) / "kmp_fr13_phase4_dev_logs"
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

from apps.ai import get_ai_service  # noqa: E402
from apps.core.constants import RELEVANCE_THRESHOLD  # noqa: E402
from apps.retrieval.pipeline import resolve_retrieval_text  # noqa: E402

THREADS = REPO / "corpus/objective-02/dev-threads.json"
ARMS = ("main", "option3")


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
    numbers = {
        "with_history_match": per_way[thread_set.WITH_HISTORY]["expected_answer_match"],
        "first_turn_match": per_way[thread_set.FIRST_TURN]["expected_answer_match"],
        "spelled_out_match": per_way[thread_set.SPELLED_OUT]["expected_answer_match"],
        "correct_declines": declines,
        "schema_conformance": summary["schema_conformance"],
        "out_of_scope": summary["out_of_scope_total"],
    }
    if per_way[thread_set.COLD]["runs"]:
        numbers["cold_match"] = per_way[thread_set.COLD]["expected_answer_match"]
    return numbers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--draw", required=True, type=int, choices=(1, 2, 3))
    parser.add_argument("--limit", type=int, default=0)
    arguments = parser.parse_args()
    out = HERE / f"dev_{arguments.arm}_draw{arguments.draw}.json"
    if out.exists():
        print(f"refusing: {out} exists, and a draw is never overwritten")
        return 2

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
    if arguments.draw != 1:
        # Cold runs once per arm, on draw 1 (the fixed rule): diagnostic, no history, no
        # rewrite, so repeated draws of it would measure only generation variance.
        runs = [run for run in runs if run["way"] != thread_set.COLD]
    if arguments.limit:
        runs = runs[: arguments.limit]
    chunks = harness.load_corpus()
    manifest_items = json.loads((REPO / payload["manifest"]).read_text(encoding="utf-8"))["items"]
    sources = harness.index_sources(chunks, manifest_items)
    mismatch = harness.corpus_problems(chunks, sources, manifest_items, settings.FLM_EMBED_MODEL)
    for problem in mismatch:
        print(f"CORPUS: {problem}")
    if mismatch:
        print("refusing: the indexed corpus is not exactly the manifest's")
        return 2
    print(f"arm {arguments.arm}, draw {arguments.draw}: {len(runs)} run(s); dev set sha256 "
          f"{thread_set.file_sha256(THREADS)[:16]}", flush=True)

    service = get_ai_service()
    results, scored, rewrites = [], [], []
    started = time.perf_counter()
    for position, run in enumerate(runs, start=1):
        composed = harness.compose(run["question"], run["prior"])
        rewrite_note = ""
        rewrite_seconds = None
        if arguments.arm == "option3":
            resolve_started = time.perf_counter()
            resolved = resolve_retrieval_text(question=run["question"], context=composed)
            rewrite_seconds = time.perf_counter() - resolve_started
            retrieval_text, rewrite = resolved.text, resolved.rewrite
            if run["prior"]:
                rewrites.append({"run_id": run["run_id"], "used": rewrite is not None,
                                 "seconds": round(rewrite_seconds, 2), "rewrite": rewrite})
                rewrite_note = (f" rewrite={'used' if rewrite is not None else 'FELL BACK'}"
                                f" ({rewrite_seconds:.1f}s)")
        else:
            # main: the pre-phase-4 retrieval, byte for byte — the join, no model call.
            retrieval_text, rewrite = composed.for_retrieval, None
        result = harness.QuestionResult(
            question_id=run["run_id"], kind=run["kind"], role=run["role"],
            question=run["question"], expects_answer=run["expects_answer"],
            base_id=run["thread_id"], source=list(run["sources"]), expected_answer=None,
        )
        result.prompt_question = composed.for_prompt
        result.retrieval_rewrite = rewrite
        harness.measure(result, retrieval_text, chunks, service, RELEVANCE_THRESHOLD,
                        sources, time.perf_counter())
        score = thread_set.score(run, harness.thread_observation(result, chunks, sources))
        results.append(result)
        scored.append(score)
        print(f"[{position}/{len(runs)}] {run['run_id']:<34} {score['outcome']:<16} "
              f"match={'yes' if score['expected_answer_match'] else 'no '} "
              f"correct={'yes' if score['correct'] else 'no '} leaks={len(score['leaks'])} "
              f"({result.seconds:.1f}s){rewrite_note}", flush=True)
    elapsed = time.perf_counter() - started

    summary = thread_set.summarise(scored)
    responses = [a for r in results for a in r.attempts if a["outcome"] != "call-failed"]
    summary["schema_conformance"] = [sum(a["outcome"] == "parsed" for a in responses), len(responses)]
    with_history = [r for r, s in zip(results, scored) if s["way"] == thread_set.WITH_HISTORY]
    summary["rewrites_used"] = [sum(r.retrieval_rewrite is not None for r in with_history),
                                len(with_history)]
    numbers = rule_numbers(summary)
    rewrite_times = [entry["seconds"] for entry in rewrites if entry["used"]]
    print(f"\n{arguments.arm} draw {arguments.draw}: with-history "
          f"{numbers['with_history_match']}, first-turn {numbers['first_turn_match']}, "
          f"spelled-out {numbers['spelled_out_match']}, declines {numbers['correct_declines']}, "
          f"schema {numbers['schema_conformance']}, out-of-scope {numbers['out_of_scope']}; "
          f"rewrites used {summary['rewrites_used']}"
          + (f", rewrite seconds min/median/max "
             f"{min(rewrite_times):.1f}/{sorted(rewrite_times)[len(rewrite_times)//2]:.1f}/"
             f"{max(rewrite_times):.1f}" if rewrite_times else "")
          + f"; {elapsed / 60:.1f} min", flush=True)

    record = {
        "arm": arguments.arm,
        "draw": arguments.draw,
        # 0 is a full draw; anything else is a smoke or partial run, never rule evidence.
        "limit": arguments.limit,
        "tuning_run": "DEV SET (D-93): tuned on, never a test; no frozen set was run here",
        "adoption_rule": "means over 3 draws per arm; adopt only if option3's mean "
                         "with-history match exceeds main's by MORE THAN 2 runs, no guard "
                         "arm's mean lower by more than 1, conformance intact, 0 out-of-scope; "
                         "cold once per arm, diagnostic",
        "commit_sha": git("rev-parse", "HEAD"),
        "uncommitted_tracked_changes": bool(git("status", "--porcelain", "--untracked-files=no")),
        "database": DATABASE,
        "flm_version": version.as_record(),
        "thread_set": str(THREADS.relative_to(REPO)),
        "thread_set_sha256": thread_set.file_sha256(THREADS),
        "constants": {"RELEVANCE_THRESHOLD": RELEVANCE_THRESHOLD},
        "elapsed_seconds": elapsed,
        "rule_numbers": numbers,
        "rewrites": rewrites,
        "summary": summary,
        "runs": [harness.thread_run_record(run, result, score, sources)
                 for run, result, score in zip(runs, results, scored)],
    }
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"record written to {out}", flush=True)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
