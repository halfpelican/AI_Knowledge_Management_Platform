"""D-113 (10 November 2026): could a server that ignored history have supplied the composed set?

A WIRED verdict says turn two's supplied passages equal what compose(follow-up, [first]) retrieves
and differ from what the bare follow-up retrieves. On FLM the same string embeds to the same
vector, so that settled it. Voyage jitters by up to 0.00047 per score (two passes over the frozen
thirty, ../voyage-frozen/), so this asks the remaining question: how far would the bare
follow-up's ranking have to move for its supplied set to become the composed one?

For each thread in http_check.json it embeds the bare follow-up once more, as that thread's role,
and ranks the candidates with the pipeline's own functions. A supplied set is a prefix of the
admitted ranking, so for the bare follow-up to supply the composed set, every passage only the
composed set holds must be admitted and must outrank every passage only the bare set holds. The
shift needed is the larger of:

- the threshold minus the lowest bare-follow-up score among the composed-only passages, and
- the highest bare-follow-up score among the bare-only passages minus that same lowest score.

Two scores can move apart by at most twice the jitter, so a shift wider than 2 x 0.00047 cannot
come from the jitter: a server that ignored the history could not have supplied the composed set.

Read-only: it embeds three strings through Voyage and reads chunks. Usage, from anywhere:
    python history_effect.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[4]
DATABASE = "kmp_voyage_20261110"
JITTER = 0.00047  # the largest top-score difference between two passes, ../voyage-frozen/

for line in (REPOSITORY_ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        os.environ["DATABASE_URL"] = re.sub(r"/[^/]+$", f"/{DATABASE}", line.split("=", 1)[1].strip())
os.environ["AI_PROVIDER"] = "anthropic"
os.environ["EMBEDDING_DIMENSION"] = "1024"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
sys.path.insert(0, str(REPOSITORY_ROOT))

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from apps.retrieval.conversation import compose  # noqa: E402
from apps.retrieval.query_embedding import embed_question  # noqa: E402
from apps.retrieval.ranking import rank, relevance_threshold  # noqa: E402
from apps.retrieval.scoping import candidate_chunks  # noqa: E402


def main() -> int:
    if settings.DATABASES["default"]["NAME"] != DATABASE or settings.AI_PROVIDER != "anthropic":
        raise SystemExit("refusing: not the anthropic provider on the Voyage copy")
    record = json.loads((HERE / "http_check.json").read_text(encoding="utf-8"))
    print(f"jitter bound: two scores move apart by at most 2 x {JITTER} = {2 * JITTER:.5f}\n")
    for thread in record["threads"]:
        role = thread["role"]
        follow_up = thread["questions"][1]
        composed = set(thread["in_process"]["with_history"])
        bare = set(thread["in_process"]["cold"])
        only_composed, only_bare = composed - bare, bare - composed

        embedding = embed_question(compose(follow_up, []).for_retrieval)
        threshold = relevance_threshold(embedding.model)
        candidates = list(candidate_chunks(role_name=role, embedding_model=embedding.model))
        scores = {p.chunk_id: p.score for p in rank(candidates, embedding.vectors[0])}
        # A candidate outside the TOP_K-capped ranking scores no higher than its last entry.
        floor_score = min(scores.values()) if scores else 0.0
        lowest_composed = min((scores.get(c, floor_score) for c in only_composed), default=None)
        needed = []
        if lowest_composed is not None:
            needed.append(threshold - lowest_composed)
            if only_bare:
                needed.append(max(scores.get(c, floor_score) for c in only_bare) - lowest_composed)
        shift = max(needed) if needed else None
        verdict = ("the sets are equal: history changed nothing retrieval shows" if not only_composed and not only_bare
                   else "cannot come from the jitter" if shift is not None and shift > 2 * JITTER
                   else "WITHIN THE JITTER: the verdict does not separate history from jitter")
        print(f"{thread['thread']} as {role}: verdict {thread['verdict']}")
        print(f"  composed set {len(composed)}, bare follow-up's set {len(bare)}; "
              f"composed only {len(only_composed)}, bare only {len(only_bare)}")
        if lowest_composed is not None:
            print(f"  lowest bare-follow-up score among the composed-only passages: {lowest_composed:.4f} "
                  f"(threshold {threshold})")
        print(f"  shift needed for a history-blind server to supply the composed set: "
              f"{'n/a' if shift is None else f'{shift:.4f}'} -> {verdict}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
