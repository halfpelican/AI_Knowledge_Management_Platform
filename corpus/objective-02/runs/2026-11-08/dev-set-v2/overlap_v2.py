"""Step 7 phase 2c (8 November 2026): does dev-set-v2.json overlap the frozen sets?

The phase 2a check (``../../2026-11-07/dev_set_overlap.py``), run on dev-set-v2.json, with the
same comparisons and the same flag thresholds, fixed in advance:

1. exact, after collapsing whitespace and folding case;
2. lexical: Jaccard similarity of content words (the same stopwords and suffix strip) >= 0.5,
   or difflib's character ratio >= 0.8;
3. semantic: cosine of the two questions' embeddings, each through the shipped query path
   (apps/ai/prefixes.py's query prefix, the configured FLM model) >= 0.90.

**One difference, for the contamination the user asked to keep small.** This version prints the
frozen set's IDENTIFIERS and the scores, never a frozen question's text. A flagged dev question
is rewritten without anyone reading the frozen question it resembled.

Read-only. Talks to FLM only to embed. Usage, from anywhere:

    python overlap_v2.py
"""

from __future__ import annotations

import difflib
import json
import math
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SCRATCH_LOGS = Path(os.environ.get("TEMP", ".")) / "kmp_overlap_v2_logs"
SCRATCH_LOGS.mkdir(parents=True, exist_ok=True)
for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        os.environ["DATABASE_URL"] = re.sub(r"/[^/]+$", "/kmp_obj02_20261101", line.split("=", 1)[1].strip())
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings", DEBUG="False", AI_PROVIDER="flm",
                  FLM_BASE_URL="http://127.0.0.1:8625/v1",
                  ERROR_LOG_PATH=str(SCRATCH_LOGS / "errors.log"), AUDIT_LOG_PATH=str(SCRATCH_LOGS / "audit.log"),
                  WAITRESS_LOG_PATH=str(SCRATCH_LOGS / "waitress.log"),
                  ATTEMPTS_LOG_PATH=str(SCRATCH_LOGS / "attempts.log"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "corpus/objective-02/runs/2026-11-07"))
os.chdir(REPO)

import django  # noqa: E402

django.setup()

import question_set  # noqa: E402

import apps.ai  # noqa: E402
from apps.ai.prefixes import query_text  # noqa: E402
from apps.core.constants import (  # noqa: E402
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
)
# The same normalisation, stopwords, stemming and thresholds as phase 2a's check.
from dev_set_overlap import (  # noqa: E402
    COSINE_FLAG,
    DIFFLIB_FLAG,
    JACCARD_FLAG,
    content_words,
    cosine,
    jaccard,
    normalise,
)

ROLES = (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME)


def main() -> int:
    dev_path = REPO / "corpus/objective-02/dev-set-v2.json"
    _, dev = question_set.load(dev_path)
    problems = question_set.problems(
        dev, minimum_length=MINIMUM_QUESTION_LENGTH, maximum_length=MAXIMUM_QUESTION_LENGTH, roles=ROLES
    )
    print(f"dev-set-v2: {len(dev)} questions, {len(question_set.expand_runs(dev, ROLES))} runs, "
          f"SHA-256 {question_set.file_sha256(dev_path)}; harness validation problems: {problems or 'none'}")

    frozen: list[tuple[str, str]] = []
    _, questions = question_set.load(REPO / "corpus/objective-02/questions.json")
    frozen += [(f"questions.json {q['id']}", q["question"]) for q in questions]
    threads = json.loads((REPO / "corpus/objective-02/threads.json").read_text(encoding="utf-8"))["threads"]
    for thread in threads:
        for index, turn in enumerate(thread["turns"]):
            frozen.append((f"threads.json {thread['id']} turn {index + 1}", turn["question"]))
            if turn.get("spelled_out") and turn["spelled_out"] != turn["question"]:
                frozen.append((f"threads.json {thread['id']} turn {index + 1} spelled_out", turn["spelled_out"]))
    print(f"frozen questions compared: {len(frozen)} ({len(questions)} from questions.json, "
          f"{len(frozen) - len(questions)} from threads.json). Their text is not printed.")

    service = apps.ai.get_ai_service()
    dev_texts = [q["question"] for q in dev]
    frozen_texts = [text for _, text in frozen]
    vectors = service.embed([query_text(t) for t in dev_texts + frozen_texts]).vectors
    dev_vectors, frozen_vectors = vectors[: len(dev_texts)], vectors[len(dev_texts):]

    pairs = []
    for i, q in enumerate(dev):
        for j, (label, text) in enumerate(frozen):
            pairs.append({
                "dev": q["id"], "frozen": label,
                "exact": normalise(q["question"]) == normalise(text),
                "jaccard": round(jaccard(content_words(q["question"]), content_words(text)), 3),
                "difflib": round(difflib.SequenceMatcher(None, normalise(q["question"]), normalise(text)).ratio(), 3),
                "cosine": round(cosine(dev_vectors[i], frozen_vectors[j]), 3),
            })
    flagged = [
        p for p in pairs
        if p["exact"] or p["jaccard"] >= JACCARD_FLAG or p["difflib"] >= DIFFLIB_FLAG or p["cosine"] >= COSINE_FLAG
    ]
    print(f"pairs compared: {len(pairs)}; flagged (exact, Jaccard >= {JACCARD_FLAG}, difflib >= "
          f"{DIFFLIB_FLAG} or cosine >= {COSINE_FLAG}): {len(flagged)}")
    for p in flagged:
        print(f"  FLAGGED {p}")
    for key in ("jaccard", "difflib", "cosine"):
        print(f"\ntop 5 by {key}:")
        for p in sorted(pairs, key=lambda p: -p[key])[:5]:
            print(f"  {p[key]:.3f}  {p['dev']}  vs  {p['frozen']}")
    print("\nper dev question, its nearest frozen question by cosine (identifier only):")
    for q in dev:
        best = max((p for p in pairs if p["dev"] == q["id"]), key=lambda p: p["cosine"])
        print(f"  {q['id']} {best['cosine']:.3f} (Jaccard {best['jaccard']:.2f}, difflib {best['difflib']:.2f}) "
              f"vs {best['frozen']}")
    return 1 if (problems or flagged) else 0


if __name__ == "__main__":
    sys.exit(main())
