"""Phase 4's frozen-nine run, ONCE, on the configuration the rule decided: MAIN.

The fixed rule (phase 4, 9 November 2026) did not adopt option 3: its mean with-history
gain over three draws on the dev set was +0.67 runs against the required > 2
(corpus/objective-02/runs/2026-11-09/fr13-phase4-dev/apply_rule.py). The decided
configuration is therefore the unchanged shipped path, and this run mirrors phase 3's
ending (d19a027): the frozen nine on that path, a further variance reference, read
against the ±1-2-run band.

**THE ONE PIN, STATED LOUDLY:** this checkout (48c20cf) carries the not-adopted option-3
code, so ``citation_harness.resolve_retrieval_text`` is rebound FOR THIS PROCESS ONLY to
the pre-phase-4 passthrough — the composed join embedded, no rewrite model call — which
is byte-for-byte main's retrieval (the same passthrough the dev runner's main arm used,
and the same rebinding mechanism the suite's own tests use). Nothing on disk changes;
the harness record carries this commit's SHA, and without this file's note that SHA
would misread as option 3, which is exactly why this wrapper exists and is committed
beside the record.

Everything else is the REAL ``scripts/citation_harness.py --threads`` in recorded mode:
its gates (the dump hash, the database, check_flm, the corpus-vs-manifest check), its
scoring, its record. Reads only. Usage: python run_frozen_main.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
SCRATCH_LOGS = Path(os.environ.get("TEMP", ".")) / "kmp_fr13_phase4_frozen_logs"
SCRATCH_LOGS.mkdir(parents=True, exist_ok=True)
DATABASE = "kmp_obj02_20261101"
# The snapshot the corpus database was restored from: the same hash phase 3's frozen
# run recorded (corpus/objective-02/runs/2026-11-09/fr13-phase3/threads.json).
DUMP_SHA256 = "3bf98403354dbabceb54052b99b45a25f5f39d4fd685cca1e07233aa1e166f59"

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

import citation_harness as harness  # noqa: E402

from apps.retrieval.pipeline import ResolvedRetrieval  # noqa: E402


def main_path_resolve(*, question, context):
    """The pre-phase-4 retrieval, byte for byte: the composed join, no rewrite call."""
    return ResolvedRetrieval(text=context.for_retrieval, rewrite=None)


def main() -> int:
    out = HERE / "threads.json"
    print("CONFIGURATION: MAIN (the rule did not adopt option 3). "
          "resolve_retrieval_text is pinned to the composed-join passthrough for this "
          "process; no rewrite model call will be made.", flush=True)
    harness.resolve_retrieval_text = main_path_resolve
    sys.argv = [
        "citation_harness.py",
        "--threads", str(REPO / "corpus/objective-02/threads.json"),
        "--dump-sha256", DUMP_SHA256,
        "--out", str(out),
    ]
    code = harness.main()
    print("CONFIGURATION WAS MAIN: the composed-join passthrough above was in force for "
          "every run; the record's commit SHA names the branch, not the retrieval path.",
          flush=True)
    return code


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
