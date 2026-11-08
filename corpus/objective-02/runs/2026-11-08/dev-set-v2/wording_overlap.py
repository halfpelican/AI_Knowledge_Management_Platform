"""Step 7 phase 2c: how much of each question's wording comes from its expected source?

For every answerable run of a development set, the share of the question's content words that
also appear in its expected source's best-ranked passage:

    overlap = |content(question) & content(passage)| / |content(question)|

"Content words" and the matching are phase 2a's overlap check's (``content_words`` in
``../../2026-11-07/dev_set_overlap.py``): lower-cased alphanumeric tokens, its stopword list
dropped, a light suffix strip (-ing, -es, -ed, -s on words over four letters). The passage is the
expected source's highest-scoring passage for that run, read from the scores JSON that
threshold_scores.py wrote, and its text is read from kmp_obj02_20261101 (read-only).

It prints the per-run values and the distribution for each set given. Usage:

    python wording_overlap.py <scores_v1.json> <scores_v2.json>
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SCRATCH_LOGS = Path(os.environ.get("TEMP", ".")) / "kmp_wording_overlap_logs"
SCRATCH_LOGS.mkdir(parents=True, exist_ok=True)
for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        os.environ["DATABASE_URL"] = re.sub(r"/[^/]+$", "/kmp_obj02_20261101", line.split("=", 1)[1].strip())
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DEBUG="False", AI_PROVIDER="flm",
                  ERROR_LOG_PATH=str(SCRATCH_LOGS / "errors.log"), AUDIT_LOG_PATH=str(SCRATCH_LOGS / "audit.log"),
                  WAITRESS_LOG_PATH=str(SCRATCH_LOGS / "waitress.log"),
                  ATTEMPTS_LOG_PATH=str(SCRATCH_LOGS / "attempts.log"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "corpus/objective-02/runs/2026-11-07"))
os.chdir(REPO)

import django  # noqa: E402

django.setup()
from django.db import connection  # noqa: E402

from apps.documents.models import ContentChunk  # noqa: E402
from dev_set_overlap import content_words  # noqa: E402  phase 2a's definition


def quartiles(values: list[float]) -> str:
    q = statistics.quantiles(values, n=4, method="inclusive")
    return (f"n {len(values)}, min {min(values):.2f}, Q1 {q[0]:.2f}, median {statistics.median(values):.2f}, "
            f"Q3 {q[2]:.2f}, max {max(values):.2f}, mean {statistics.mean(values):.2f}, "
            f"zero overlap {sum(1 for v in values if v == 0)}")


def main() -> int:
    assert connection.settings_dict["NAME"] == "kmp_obj02_20261101"
    text_by_chunk = {str(c.id): c.chunk_text for c in ContentChunk.objects.all()}
    summaries = []
    for path in sys.argv[1:]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        name = data.get("set", "dev-set.json")
        rows = []
        for run in data["runs"]:
            if not run["expects_answer"]:
                continue
            ranked = run["repeats"][0]["ranked"]
            expected = set(run["expected_sources"])
            passage = next((p for p in ranked if p["item"] in expected), None)
            words = content_words(run["question"])
            if passage is None:
                rows.append((run["run"], None, run["question"], sorted(words), []))
                continue
            shared = words & content_words(text_by_chunk[passage["chunk"]])
            rows.append((run["run"], len(shared) / len(words) if words else 0.0, run["question"],
                         sorted(words), sorted(shared)))
        print(f"== {name} ({Path(path).name})")
        for run_id, share, question, words, shared in rows:
            shown = "n/a (expected source not ranked)" if share is None else f"{share:.2f}"
            print(f"  {run_id:<18} {shown}  {question!r}  shared: {shared}")
        values = [share for _, share, *_ in rows if share is not None]
        summary = quartiles(values)
        print(f"  distribution: {summary}")
        summaries.append((name, summary))
    print()
    for name, summary in summaries:
        print(f"{name}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
