"""Step 7 phase 2b (7-8 November 2026): the scores RELEVANCE_THRESHOLD and D-56's floor are chosen from.

Read-only. No generation, no rows written. For every run of corpus/objective-02/dev-set.json,
asked as the role that run names (Employee as loadtest01, Administrator as corpus.admin, the
accounts phase 2a used), it runs the shipped retrieval exactly as ``answer_question`` does for a
one-off question:

    embed_question(question)                       # apps/retrieval/query_embedding.py
    candidate_chunks(role_name, embedding_model)   # apps/retrieval/scoping.py, both FR-11 predicates
    rank(candidates, vector)                       # apps/retrieval/ranking.py, sorted, capped at TOP_K
    partial_matches(ranked)                        # apps/retrieval/partial_matches.py, the real offer path

and records, per run, the whole ranked list (chunk, manifest item, score), the top in-scope score,
the best score among the run's expected sources' passages, and the items ``partial_matches``
returns with the score of each one's first (best) passage in the ranked list.

Each question is embedded ``--repeats`` times (default 3) in separate calls, to record D-40's
small query-vector variation. The derivation in ``--derive`` is then conservative against it:
an answerable run is judged by its LOWEST expected-source score over the repeats, a no-answer run
by its HIGHEST top score.

The rule (the user's, approved in advance, 7 November 2026), applied by ``derive``:

1. RELEVANCE_THRESHOLD: the T that declines the most no-answer runs (no in-scope passage scores
   >= T, so path A) with zero answerable runs lost (none of the run's expected sources' passages
   scores >= T). Ties: the middle of the tied interval. If 0.3 already loses one, nothing that
   loses more.
2. The floor: just above the highest-scoring partial match offered to any no-answer run. If it
   would be at or above T, stop and report.

Imports no AI vendor SDK (CLAUDE.md section 4). Never prints DATABASE_URL. Usage, from anywhere:

    python threshold_scores.py --out <file.json>
    python threshold_scores.py --derive <file.json>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DATABASE = "kmp_obj02_20261101"
FLM_URL = "http://127.0.0.1:8625/v1"
ACCOUNTS = {"Employee": "loadtest01@example.com", "Administrator": "corpus.admin@example.com"}
CURRENT_THRESHOLD = 0.3


def database_url() -> str:
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            value = line.split("=", 1)[1].strip()
            return re.sub(r"/[^/]+$", f"/{DATABASE}", value)
    raise SystemExit("no DATABASE_URL in .env")


def cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def measure(out: Path, repeats: int, set_name: str = "dev-set.json", unfloored: bool = False) -> int:
    scratch_logs = out.parent / "server_logs"
    scratch_logs.mkdir(parents=True, exist_ok=True)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ["DATABASE_URL"] = database_url()
    os.environ["DEBUG"] = "False"
    os.environ["FLM_BASE_URL"] = FLM_URL
    os.environ["AI_PROVIDER"] = "flm"
    os.environ["ERROR_LOG_PATH"] = str(scratch_logs / "errors.log")
    os.environ["AUDIT_LOG_PATH"] = str(scratch_logs / "audit.log")
    os.environ["WAITRESS_LOG_PATH"] = str(scratch_logs / "waitress.log")
    os.environ["ATTEMPTS_LOG_PATH"] = str(scratch_logs / "attempts.log")
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "scripts"))
    os.chdir(REPO)

    gate = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_flm.py")],
        capture_output=True, text=True, timeout=600, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    (out.parent / "check_flm_scores.txt").write_text(gate.stdout + gate.stderr, encoding="utf-8")
    if gate.returncode != 0 or not any(l.startswith("RESULT: PASS") for l in gate.stdout.splitlines()):
        print("check_flm.py did not pass; nothing measured", flush=True)
        return 2

    import django

    django.setup()

    import question_set  # scripts/question_set.py
    from django.contrib.auth import get_user_model
    from django.db import connection

    from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, RELEVANCE_THRESHOLD, TOP_K
    from apps.documents.models import ContentChunk, Document
    from apps.meetings.models import Meeting
    import apps.retrieval.partial_matches as partial_matches_module
    from apps.retrieval.partial_matches import partial_matches
    from apps.retrieval.query_embedding import embed_question
    from apps.retrieval.ranking import cosine_similarity, rank
    from apps.retrieval.scoping import candidate_chunks, permission_scope

    if connection.settings_dict["NAME"] != DATABASE:
        print(f"refusing: connected to {connection.settings_dict['NAME']!r}", flush=True)
        return 2

    # --unfloored (phase 2c): the real offer path with PARTIAL_MATCH_FLOOR lifted, so the offers
    # are the five nearest items whatever their score, as they were before the floor existed
    # (the 7 November measurement ran on code with no floor). Recorded in the output.
    floor_in_code = getattr(partial_matches_module, "PARTIAL_MATCH_FLOOR", None)
    if unfloored and floor_in_code is not None:
        partial_matches_module.PARTIAL_MATCH_FLOOR = float("-inf")
    set_path = REPO / "corpus/objective-02" / set_name
    _, questions = question_set.load(set_path)
    runs = question_set.expand_runs(questions, (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME))
    manifest = json.loads((REPO / "corpus/objective-02/manifest.json").read_text(encoding="utf-8"))
    item_by_title = {i["title"]: i["id"] for i in manifest["items"]}
    titles = {str(d.id): d.title for d in Document.objects.all()}
    titles.update({str(m.id): m.title for m in Meeting.objects.all()})
    item_by_source = {source_id: item_by_title.get(title) for source_id, title in titles.items()}
    item_by_chunk = {str(c.id): item_by_source.get(str(c.source_id)) for c in ContentChunk.objects.all()}

    users = {role: get_user_model().objects.get(email=email) for role, email in ACCOUNTS.items()}
    for role, user in users.items():
        assert permission_scope(user) == role, (role, user.email)

    rows = []
    for index, run in enumerate(runs, start=1):
        role_name = permission_scope(users[run["role"]])
        expected = set(run.get("sources") or ([run["source"]] if run.get("source") else []))
        if not run["expects_answer"]:
            expected = set()
        repeat_rows, vectors = [], []
        for repeat in range(1, repeats + 1):
            embedding = embed_question(run["question"])
            vector = embedding.vectors[0]
            vectors.append(vector)
            candidates = list(candidate_chunks(role_name=role_name, embedding_model=embedding.model))
            ranked = rank(candidates, vector)
            # The expected sources' best over EVERY candidate, uncapped, only to show whether
            # TOP_K cut one: the rule is judged on the ranked list, which is what admit() sees.
            uncapped = [cosine_similarity(vector, list(c.embedding)) for c in candidates
                        if item_by_chunk.get(str(c.id)) in expected]
            offered = partial_matches(ranked)
            first_score = {}
            for passage in ranked:
                first_score.setdefault((passage.source_type, str(passage.source_id)), passage.score)
            expected_scores = [p.score for p in ranked if item_by_chunk.get(p.chunk_id) in expected]
            repeat_rows.append({
                "repeat": repeat,
                "embedding_model": embedding.model,
                "candidates": len(candidates),
                "ranked": [
                    {"chunk": p.chunk_id, "item": item_by_chunk.get(p.chunk_id), "score": round(p.score, 6)}
                    for p in ranked
                ],
                "top": round(ranked[0].score, 6) if ranked else None,
                "top_item": item_by_chunk.get(ranked[0].chunk_id) if ranked else None,
                "expected_best": round(max(expected_scores), 6) if expected_scores else None,
                "expected_best_uncapped": round(max(uncapped), 6) if uncapped else None,
                "expected_ranked_count": len(expected_scores),
                "expected_candidates": sum(1 for c in candidates if item_by_chunk.get(str(c.id)) in expected),
                "partial_matches": [
                    {"item": item_by_source.get(str(m.source_id)), "source_type": m.source_type,
                     "score": round(first_score[(m.source_type, str(m.source_id))], 6)}
                    for m in offered
                ],
            })
        identical = all(v == vectors[0] for v in vectors)
        row = {
            "run": run["run_id"], "role": run["role"], "role_scope": role_name, "kind": run["kind"],
            "question": run["question"], "expects_answer": run["expects_answer"],
            "expected_sources": sorted(expected),
            "vectors_identical": identical,
            "vector_cosine_to_first": [round(cosine(vectors[0], v), 9) for v in vectors],
            "repeats": repeat_rows,
        }
        rows.append(row)
        tops = [r["top"] for r in repeat_rows]
        bests = [r["expected_best"] for r in repeat_rows]
        print(f"{index}/{len(runs)} {run['run_id']} {run['role'][:3]} top={tops} expected_best={bests} "
              f"identical={identical}", flush=True)

    document = {
        "measured": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": DATABASE,
        "set_sha256": question_set.file_sha256(set_path),
        "chunk_count": ContentChunk.objects.count(),
        "top_k": TOP_K,
        "relevance_threshold_in_code": RELEVANCE_THRESHOLD,
        "partial_match_floor_in_code": floor_in_code,
        "offers_unfloored": bool(unfloored),
        "set": set_name,
        "repeats": repeats,
        "runs": rows,
    }
    out.write_text(json.dumps(document, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.name}", flush=True)
    return 0


def derive(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = data["runs"]
    answerable = [r for r in runs if r["expects_answer"]]
    unanswerable = [r for r in runs if not r["expects_answer"]]

    def low_expected(r):
        values = [x["expected_best"] for x in r["repeats"]]
        return None if any(v is None for v in values) else min(values)

    def high_top(r):
        values = [x["top"] for x in r["repeats"] if x["top"] is not None]
        return max(values) if values else None

    print(f"source: {path.name}, measured {data['measured']}, {data['chunk_count']} chunks, "
          f"TOP_K {data['top_k']}, {data['repeats']} embeddings per run, set {data['set_sha256'][:8]}")
    print()
    print("Answerable runs: best score of an expected source's passage in the ranked list (min / max over repeats)")
    for r in sorted(answerable, key=lambda r: (low_expected(r) is None, low_expected(r) or 0)):
        values = [x["expected_best"] for x in r["repeats"]]
        tops = [x["top"] for x in r["repeats"]]
        print(f"  {r['run']:<18} {r['role'][:3]} sources={','.join(r['expected_sources']):<4} "
              f"expected_best min={min(v for v in values if v is not None) if any(v is not None for v in values) else None} "
              f"max={max(v for v in values if v is not None) if any(v is not None for v in values) else None}  "
              f"top={min(tops)}..{max(tops)} top_item={r['repeats'][0]['top_item']}")
    print()
    print("No-answer runs: top in-scope score (min / max over repeats), and the partial matches offered")
    for r in sorted(unanswerable, key=high_top):
        tops = [x["top"] for x in r["repeats"]]
        offered = ", ".join(f"{m['item']} {m['score']:.6f}" for m in r["repeats"][0]["partial_matches"])
        print(f"  {r['run']:<18} {r['role'][:3]} top min={min(tops)} max={max(tops)}  offered (repeat 1): {offered}")
    print()

    lows = sorted((low_expected(r), r["run"]) for r in answerable if low_expected(r) is not None)
    missing = [r["run"] for r in answerable if low_expected(r) is None]
    if missing:
        print(f"ANSWERABLE RUNS WITH NO EXPECTED-SOURCE PASSAGE IN THE RANKED LIST AT ALL: {missing}")
        print("  they are lost at every threshold; counted as lost already and excluded from the bound")
    highs = sorted((high_top(r), r["run"]) for r in unanswerable)

    def lost(t):
        return [run for value, run in lows if value < t] + missing

    def declined(t):
        return [run for value, run in highs if value < t]

    allowed = len(lost(CURRENT_THRESHOLD))
    print(f"At the current {CURRENT_THRESHOLD}: lost {lost(CURRENT_THRESHOLD)}, declined {declined(CURRENT_THRESHOLD)}")
    # The largest T losing no more than `allowed`: the (allowed - len(missing) + 1)-th smallest low.
    k = allowed - len(missing)
    upper, upper_run = lows[k]
    below = [value for value, _ in highs if value < upper]
    lower = max(below) if below else None
    print(f"Upper bound (the lowest answerable expected-source score kept): {upper} ({upper_run})")
    print(f"Declined at the upper bound: {len(declined(upper))} of {len(highs)}: {declined(upper)}")
    if lower is None:
        print("No no-answer run scores below the upper bound: the tie interval runs down to the bottom")
        return 0
    middle = (lower + upper) / 2
    print(f"Tie interval: ({lower}, {upper}]  -> middle {middle:.6f}, margin {(upper - lower) / 2:.6f} each side")
    for t in (round(middle, 2), round(middle, 3), middle):
        print(f"  T={t}: lost {lost(t)}  declined {len(declined(t))}: {declined(t)}")

    print()
    offered_scores = [
        (m["score"], r["run"], m["item"], x["repeat"])
        for r in unanswerable for x in r["repeats"] for m in x["partial_matches"]
    ]
    top_offer = max(offered_scores)
    print(f"Highest-scoring partial match offered to any no-answer run: {top_offer[0]} "
          f"({top_offer[1]}, {top_offer[2]}, repeat {top_offer[3]})")
    return 0


def derive_with_margin(path: Path, m: float) -> int:
    """The user's revised rule (8 November 2026), the same rule with a margin m fixed in advance.

    Added after the measurement; ``measure`` is unchanged, and this reads the same JSON.

    1. T: maximise the no-answer runs declined with margin (top in-scope score <= T - m),
       subject to every answerable run's lowest expected-source score being >= T + m. On a
       tie, the middle of the tied interval.
    2. F: the lowest value with F >= (the highest partial-match score offered to any no-answer
       run path A declines at T) + m, and F <= T - m. If F would exceed T - m, stop.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = data["runs"]
    print(f"source: {path.name}, set {data.get('set', 'dev-set.json')}, measured {data['measured']}, "
          f"offers unfloored: {data.get('offers_unfloored', 'n/a (no floor in code)')}")
    answerable = [r for r in runs if r["expects_answer"]]
    unanswerable = [r for r in runs if not r["expects_answer"]]
    # Phase 2c: an answerable run whose expected source is not in the ranked list at all (beyond
    # TOP_K) has no score; it is lost at every threshold, and the rule cannot keep it.
    missing = [r["run"] for r in answerable if any(x["expected_best"] is None for x in r["repeats"])]
    if missing:
        print(f"ANSWERABLE RUNS WHOSE EXPECTED SOURCE IS NOT IN THE RANKED LIST: {missing}")
        print("  lost at every threshold; the bound is taken over the rest")
    lows = sorted((min(x["expected_best"] for x in r["repeats"]), r["run"]) for r in answerable
                  if r["run"] not in missing)
    highs = sorted((max(x["top"] for x in r["repeats"]), r["run"]) for r in unanswerable)
    print(f"margin m = {m}")
    upper = lows[0][0] - m
    print(f"T <= {lows[0][0]} ({lows[0][1]}) - m = {upper:.6f}")
    declinable = [(value, run) for value, run in highs if value + m <= upper]
    if not declinable:
        print("No no-answer run can be declined with margin: no middle is taken (phase 2c's instruction).")
        print(f"  the lowest no-answer top is {highs[0][0]} ({highs[0][1]}); declining it needs T >= "
              f"{highs[0][0] + m:.6f}, above the bound {upper:.6f}")
        proposal = min(0.30, lows[0][0] - m)
        print(f"Proposed T = min(0.30, {lows[0][0]} - m) = {proposal:.6f}")
        at = [run for value, run in highs if value < proposal]
        print(f"  no-answer runs that would take path A at the proposal: {at or 'none'}")
        if not at:
            print("F: no run is declined at path A, so the rule sets nothing for F.")
        return 0
    lower = max(value for value, _ in declinable) + m
    print(f"Declinable with margin: {len(declinable)} of {len(highs)}: {[run for _, run in declinable]}")
    print(f"Not declinable: {[(run, value) for value, run in highs if value + m > upper]}")
    middle = (lower + upper) / 2
    print(f"Tie interval: [{lower:.6f}, {upper:.6f}] -> middle {middle:.7f}")
    t = round(middle, 4)
    print(f"T = {t} (the middle rounded to the nearest four-place value; |T - middle| = {abs(t - middle):.7f})")
    print(f"  distance to the highest declined no-answer top ({max(declinable)[1]}): {t - max(declinable)[0]:.6f}")
    print(f"  distance to the lowest answerable expected-source score ({lows[0][1]}): {lows[0][0] - t:.6f}")
    path_a = [r for r in runs if max(x["top"] for x in r["repeats"]) < t]
    if not path_a:
        print("F: no run is declined at path A at T, so the rule sets nothing for F.")
        return 0
    offered = [(m_["score"], r["run"], m_["item"]) for r in path_a for x in r["repeats"]
               for m_ in x["partial_matches"]]
    top_offer = max(offered)
    bound = top_offer[0] + m
    f = math.ceil(round(bound * 10_000, 6)) / 10_000
    print(f"Runs path A declines at T: {[r['run'] for r in path_a]}")
    print(f"Highest partial match offered to them: {top_offer[0]} ({top_offer[1]}, {top_offer[2]})")
    print(f"F >= {top_offer[0]} + m = {bound:.6f} -> rounded up to four places: {f}")
    if f > t - m:
        print(f"F <= T - m = {t - m:.4f}: FAILS. The rule sets nothing for F; stop and report.")
        return 0
    print(f"F <= T - m = {t - m:.4f}: holds")
    print(f"  band offered on path A: [{f}, {t}), {t - f:.4f} wide; F is {f - top_offer[0]:.6f} above "
          f"{top_offer[1]}'s {top_offer[2]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--derive")
    parser.add_argument("--margin", type=float, help="with --derive: the revised rule's m")
    parser.add_argument("--set", default="dev-set.json", help="a file in corpus/objective-02/")
    parser.add_argument("--unfloored", action="store_true",
                        help="lift PARTIAL_MATCH_FLOOR for the measurement (phase 2c)")
    args = parser.parse_args()
    if args.derive and args.margin is not None:
        return derive_with_margin(Path(args.derive), args.margin)
    if args.derive:
        return derive(Path(args.derive))
    return measure(Path(args.out), args.repeats, args.set, args.unfloored)


if __name__ == "__main__":
    sys.exit(main())
