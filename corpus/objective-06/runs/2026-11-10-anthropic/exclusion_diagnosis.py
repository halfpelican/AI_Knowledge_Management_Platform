"""Why the cycle kept or left out each seeded no-answer ask, read through the cycle's own decision.

Read-only, after the cycle. For each of the thirty's asks that reached a no-answer (the eight
unanswerable and the six permission-only), this embeds the question with the shipped
``embed_question``, ranks it over the cycle's own Administrator scope
(``apps.retrieval.gaps._AdministratorScope``), and asks the cycle's own decision
(``_question_explained_by_permissions``, D-108's rule as of 333be14) whether the row is left out.
It reports the top-ranked passages with their sources, scores and visible_to_roles, and the best
passage the asker may read.

**Voyage's jitter (0.00047, runs/2026-11-10/voyage-frozen/).** Each question is embedded
DRAWS times, and the report gives, per draw, the top passage, the decision, and the margin: the
top passage's score minus the best score of a passage on the other side of the readability line.
A decision whose margin is wider than twice the jitter on every draw cannot have been made or
broken by it.

It writes nothing to the database, calls no Claude model, and refuses unless the provider, the
embedding model, the width and the database are this run's. Each embedding is one Voyage call.

Usage, in PowerShell, with the run's DATABASE_URL set in the shell::

    & $py corpus\\objective-06\\runs\\2026-11-10-anthropic\\exclusion_diagnosis.py `
        --seed corpus\\objective-06\\runs\\2026-11-10-anthropic\\seed\\seed.json `
        --out corpus\\objective-06\\runs\\2026-11-10-anthropic\\exclusion_diagnosis.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]  # corpus/objective-06/runs/<this folder>/<this file>
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

EXPECTED_DATABASE = "kmp_obj0506_anthropic_20261110"
EXPECTED = (("AI_PROVIDER", "anthropic"), ("VOYAGE_MODEL", "voyage-4"), ("EMBEDDING_DIMENSION", 1024))
ACCOUNTS = {"Administrator": "corpus.admin@example.com", "Employee": "corpus.employee@example.com"}
DRAWS = 3
JITTER = 0.00047
TOP = 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.out.exists():
        print(f"REFUSED: {arguments.out} already exists")
        return 2

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from apps.documents.models import ContentChunk, Document
    from apps.meetings.models import Meeting
    from apps.retrieval import gaps
    from apps.retrieval.models import QueryLog
    from apps.retrieval.query_embedding import embed_question
    from apps.retrieval.ranking import rank
    from apps.retrieval.scoping import effective_roles

    database = str(settings.DATABASES["default"]["NAME"])
    problems = [f"settings.{name} is {getattr(settings, name)!r}, not {value!r}"
                for name, value in EXPECTED if getattr(settings, name) != value]
    if not settings.VOYAGE_API_KEY:
        problems.append("settings.VOYAGE_API_KEY is empty")  # never printed
    if database != EXPECTED_DATABASE:
        problems.append(f"the database is {database!r}, not {EXPECTED_DATABASE!r}")
    if problems:
        print("REFUSED: " + "; ".join(problems))
        return 2
    print(f"database: {database}; voyage-4 at 1024; {DRAWS} draws per question")

    titles = {str(d.pk): d.title for d in Document.objects.all()}
    titles.update({str(m.pk): m.title for m in Meeting.objects.all()})
    chunk_source = {str(c.pk): titles.get(str(c.source_id), "?") for c in ContentChunk.objects.all()}
    users = {role: get_user_model().objects.select_related("role").get(email=email) for role, email in ACCOUNTS.items()}
    seed = json.loads(arguments.seed.read_text(encoding="utf-8"))
    scope = gaps._AdministratorScope()

    report = []
    for result in seed["results"]:
        if result["via"] != "ask" or result.get("answered") or result["kind"] == "answerable":
            continue
        user = users[result["role"]]
        row = QueryLog.objects.select_related("user__role").filter(user=user, question=result["query"]).order_by("-answered_at").first()
        asker_roles = set(effective_roles(user.role.role_name))
        entry = {"id": result["id"], "kind": result["kind"], "role": result["role"], "question": result["query"],
                 "no_answer_reason": row.no_answer_reason if row else None,
                 "in_gap_log": bool(row and getattr(row, "gap_item", None)) if row else None, "draws": []}
        for _ in range(DRAWS):
            embedding = embed_question(result["query"])
            chunks, roles = scope.for_model(embedding.model)
            ranked = rank(chunks, embedding.vectors[0])
            left_out = gaps._question_explained_by_permissions(row, embedding, scope)
            readable = [p for p in ranked if set(roles[p.chunk_id]) & asker_roles]
            unreadable = [p for p in ranked if not (set(roles[p.chunk_id]) & asker_roles)]
            top = ranked[0]
            top_readable = bool(set(roles[top.chunk_id]) & asker_roles)
            other_side = unreadable if top_readable else readable
            margin = (top.score - other_side[0].score) if other_side else None
            entry["draws"].append({
                "left_out": left_out,
                "top": [{"source": chunk_source.get(p.chunk_id, "?"), "score": round(p.score, 4),
                         "visible_to_roles": list(roles[p.chunk_id]),
                         "readable_by_asker": bool(set(roles[p.chunk_id]) & asker_roles)} for p in ranked[:TOP]],
                "best_readable": {"source": chunk_source.get(readable[0].chunk_id, "?"), "score": round(readable[0].score, 4),
                                  "rank": ranked.index(readable[0]) + 1} if readable else None,
                "margin_to_other_side": round(margin, 4) if margin is not None else None,
            })
        decisions = {d["left_out"] for d in entry["draws"]}
        margins = [d["margin_to_other_side"] for d in entry["draws"] if d["margin_to_other_side"] is not None]
        entry["decision_stable_across_draws"] = len(decisions) == 1
        entry["margin_min"] = min(margins) if margins else None
        entry["margin_wider_than_twice_jitter"] = bool(margins) and min(margins) > 2 * JITTER
        report.append(entry)
        first = entry["draws"][0]
        print(f"{entry['id']} {entry['role']:<13} {entry['kind']:<15} path {entry['no_answer_reason'] or '?':<22} "
              f"left out {sorted(decisions)}  top {first['top'][0]['source']!r} {first['top'][0]['score']} "
              f"readable {first['top'][0]['readable_by_asker']}  best readable {first['best_readable']['score'] if first['best_readable'] else None} "
              f"(rank {first['best_readable']['rank'] if first['best_readable'] else None})  margin min {entry['margin_min']}")

    arguments.out.write_text(json.dumps({"database": database, "draws": DRAWS, "jitter": JITTER,
                                         "rule": "D-108 as of 333be14: the top-ranked passage over the Administrator's scope decides",
                                         "asks": report}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {arguments.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
