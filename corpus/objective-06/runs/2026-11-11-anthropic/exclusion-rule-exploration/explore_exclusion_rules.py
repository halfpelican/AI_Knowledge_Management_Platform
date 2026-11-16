"""Exploration, read-only: what the candidate exclusion rules would do on voyage-4's development questions.

For each question of dev-set-v2.json and dev-set.json, asked as the Employee: rank over the
cycle's Administrator scope, and report the top-ranked passage's score and readability, the best
readable score, and the margin (top restricted minus best readable). The rules compared:
  rank-one         : left out when the top-ranked passage is restricted (shipped, D-108 since 333be14);
  threshold-first  : nothing at or above voyage-4's 0.2687 -> kept; else rank-one on the admitted list
                     (D-108 as first written, at the model's own threshold);
  margin m         : left out when the top-ranked passage is restricted AND it beats the best readable
                     passage by at least m (D-108's named fallback).
Writes nothing. Calls Voyage only. Run from the worktree root with the run's DATABASE_URL set.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402

from apps.core.constants import EFFECTIVE_ROLES  # noqa: E402
from apps.retrieval import gaps  # noqa: E402
from apps.retrieval.query_embedding import embed_question  # noqa: E402
from apps.retrieval.ranking import rank, relevance_threshold  # noqa: E402

assert settings.DATABASES["default"]["NAME"] == "kmp_obj0506_anthropic_20261110", settings.DATABASES["default"]["NAME"]
assert settings.VOYAGE_MODEL == "voyage-4" and settings.AI_PROVIDER == "anthropic"
employee = set(EFFECTIVE_ROLES["Employee"])
scope = gaps._AdministratorScope()
threshold = relevance_threshold("voyage-4")
rows = []
for path in ("corpus/objective-02/dev-set-v2.json", "corpus/objective-02/dev-set.json"):
    for q in json.load(open(path, encoding="utf-8"))["questions"]:
        emb = embed_question(q["question"])
        chunks, roles = scope.for_model(emb.model)
        ranked = rank(chunks, emb.vectors[0])
        readable = [p for p in ranked if set(roles[p.chunk_id]) & employee]
        top = ranked[0]
        top_readable = bool(set(roles[top.chunk_id]) & employee)
        best_readable = readable[0].score if readable else None
        margin = (top.score - best_readable) if (not top_readable and best_readable is not None) else None
        admitted = [p for p in ranked if p.score >= threshold]
        tf_left_out = bool(admitted) and not (set(roles[admitted[0].chunk_id]) & employee)
        rows.append({"id": q["id"], "kind": q["kind"], "top": round(top.score, 4), "top_readable": top_readable,
                     "best_readable": round(best_readable, 4) if best_readable is not None else None,
                     "margin": round(margin, 4) if margin is not None else None,
                     "rank_one_left_out": not top_readable, "threshold_first_left_out": tf_left_out,
                     "question": q["question"][:70]})

def show(kind):
    for r in rows:
        if r["kind"] == kind:
            print(f"  {r['id']:<4} top {r['top']:<7} readable {str(r['top_readable']):<5} best readable {str(r['best_readable']):<7} "
                  f"margin {str(r['margin']):<7} rank-one {'OUT' if r['rank_one_left_out'] else 'kept':<4} "
                  f"threshold-first {'OUT' if r['threshold_first_left_out'] else 'kept':<4} {r['question']}")

print(f"voyage-4 threshold {threshold}")
print("SCOPED (should be left out):"); show("scoped")
print("NO-ANSWER (should be kept):"); show("no-answer")
scoped_margins = [r["margin"] for r in rows if r["kind"] == "scoped" and r["margin"] is not None]
noanswer_margins = [r["margin"] for r in rows if r["kind"] == "no-answer" and r["margin"] is not None]
print(f"\nscoped margins: min {min(scoped_margins) if scoped_margins else None} (all {sorted(scoped_margins)})")
print(f"no-answer margins where the top is restricted: max {max(noanswer_margins) if noanswer_margins else None} (all {sorted(noanswer_margins)})")
if scoped_margins and noanswer_margins and max(noanswer_margins) < min(scoped_margins):
    m = round((max(noanswer_margins) + min(scoped_margins)) / 2, 4)
    print(f"they separate; midpoint m = {m}; gap {round(min(scoped_margins) - max(noanswer_margins), 4)}")
    for name, kinds in (("scoped left out", ("scoped",)), ("no-answer kept", ("no-answer",))):
        pass
    so = sum(1 for r in rows if r["kind"] == "scoped" and r["margin"] is not None and r["margin"] >= m)
    nk = sum(1 for r in rows if r["kind"] == "no-answer" and not (r["margin"] is not None and r["margin"] >= m))
    ordinary_out = [r["id"] for r in rows if r["kind"] == "ordinary" and r["margin"] is not None and r["margin"] >= m]
    print(f"margin rule at m={m}: scoped left out {so}/6, no-answer kept {nk}/9, ordinary left out {ordinary_out}")
tf_s = sum(1 for r in rows if r["kind"] == "scoped" and r["threshold_first_left_out"])
tf_n = sum(1 for r in rows if r["kind"] == "no-answer" and not r["threshold_first_left_out"])
tf_o = [r["id"] for r in rows if r["kind"] == "ordinary" and r["threshold_first_left_out"]]
print(f"threshold-first: scoped left out {tf_s}/6, no-answer kept {tf_n}/9, ordinary left out {tf_o}")
print("ORDINARY left out by rank-one (for information):", [(r["id"], r["top"], r["margin"]) for r in rows if r["kind"] == "ordinary" and r["rank_one_left_out"]])
json.dump(rows, open(os.environ.get("EXPLORE_OUT", "explore_exclusion_rules.json"), "w", encoding="utf-8"), indent=2)
