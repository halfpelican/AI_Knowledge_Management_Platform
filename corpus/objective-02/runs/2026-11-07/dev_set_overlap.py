"""Step 7 phase 2a (7 November 2026): does corpus/objective-02/dev-set.json overlap the frozen sets?

Compares every dev-set question with every question in questions.json and every turn of
threads.json (its question and, where present, its spelled_out form), three ways:

1. exact, after collapsing whitespace and folding case;
2. lexical: Jaccard similarity of content words (stopwords dropped, a light plural/suffix
   strip) and difflib's character ratio;
3. semantic: cosine similarity of the two questions' embeddings, each embedded through the
   shipped query path (apps/ai/prefixes.py's query prefix, the configured FLM model).

A pair is FLAGGED if it is exact, or Jaccard >= 0.5, or difflib >= 0.8, or cosine >= 0.90.
The thresholds are this check's, stated in advance; the top pairs are printed whatever they
score, so a reader can judge the near misses. Also validates the dev set with the harness's
own loader (scripts/question_set.py), so it is known the harness can read it.

Read-only. Talks to the database only through settings (none is read) and to FLM only to
embed. Usage, from the worktree root, with DATABASE_URL and FLM_BASE_URL set as for the runs:

    python corpus/objective-02/runs/2026-11-07/dev_set_overlap.py
"""

from __future__ import annotations

import difflib
import json
import math
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

import question_set  # noqa: E402  (scripts/question_set.py)

import apps.ai  # noqa: E402
from apps.ai.prefixes import query_text  # noqa: E402
from apps.core.constants import (  # noqa: E402
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
)

ROLES = (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME)  # as scripts/citation_harness.py names them

STOPWORDS = set(
    "a an the of to in on for and or is are was were be been do does did i we our my me you your "
    "it its this that these those what which who whom how when where why can could should would will "
    "with at by from about as into than then there their they them have has had any each per after "
    "before so if not no all".split()
)
JACCARD_FLAG, DIFFLIB_FLAG, COSINE_FLAG = 0.5, 0.8, 0.90


def normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def stem(word: str) -> str:
    for suffix in ("ing", "es", "ed", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def content_words(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z0-9]+", normalise(text)) if w not in STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def main() -> int:
    dev_payload, dev = question_set.load(REPO / "corpus/objective-02/dev-set.json")
    problems = question_set.problems(
        dev, minimum_length=MINIMUM_QUESTION_LENGTH, maximum_length=MAXIMUM_QUESTION_LENGTH, roles=ROLES
    )
    print(f"dev set: {len(dev)} questions, {len(question_set.expand_runs(dev, ROLES))} runs; "
          f"harness validation problems: {problems or 'none'}")
    print(f"dev set status: {dev_payload.get('status', '')[:60]}...")

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
          f"{len(frozen) - len(questions)} from threads.json)")

    service = apps.ai.get_ai_service()
    dev_texts = [q["question"] for q in dev]
    frozen_texts = [text for _, text in frozen]
    vectors = service.embed([query_text(t) for t in dev_texts + frozen_texts]).vectors
    dev_vectors, frozen_vectors = vectors[: len(dev_texts)], vectors[len(dev_texts):]

    pairs = []
    for i, q in enumerate(dev):
        for j, (label, text) in enumerate(frozen):
            pairs.append({
                "dev": q["id"], "dev_question": q["question"], "frozen": label, "frozen_question": text,
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
        print(f"  FLAGGED {p['dev']} vs {p['frozen']}: {p}")
    for key in ("jaccard", "difflib", "cosine"):
        print(f"\ntop 5 by {key}:")
        for p in sorted(pairs, key=lambda p: -p[key])[:5]:
            print(f"  {p[key]:.3f}  {p['dev']} {p['dev_question']!r}  vs  {p['frozen']} {p['frozen_question']!r}")
    print("\nper dev question, its nearest frozen question by cosine:")
    for q in dev:
        best = max((p for p in pairs if p["dev"] == q["id"]), key=lambda p: p["cosine"])
        print(f"  {q['id']} {best['cosine']:.3f} (Jaccard {best['jaccard']:.2f}, difflib {best['difflib']:.2f}) "
              f"vs {best['frozen']}: {best['frozen_question']!r}")
    return 1 if (problems or flagged) else 0


if __name__ == "__main__":
    sys.exit(main())
