"""D-127's development check on real threads: does the cycle leave out a follow-up whose answer the asker cannot read?

D-108 fixed its check on development material before any frozen run: scoped questions should be
left out, no-answer questions kept. D-127 changed how a conversation follow-up is decided (the
composed string retrieval ranked, and the follow-up's own wording), and was verified on designed
vectors only. This runs the same kind of check on real threads, with voyage-4's real embeddings.

**The material:** ``corpus/objective-02/dev-threads.json``, a development set (D-93), never a test
set. Each thread has an opener and a follow-up.

- **Scoped threads** (t28, t29, t37) have an opener an Employee can be answered on and a
  follow-up whose answer is only in Administrator-only material. Asked as the Employee, the
  follow-up's row should be LEFT OUT: a permission boundary, not a documentation gap. Asked as the
  Administrator, it should be kept if it went unanswered; that is reported for information.
- **Every other thread** is about material the Employee can read. Its follow-up, asked as the
  Employee, should be KEPT if it went unanswered; that is reported for information, as D-108's check
  reports its ordinary questions.

**How:** inside one database transaction, each follow-up is written as an unanswered ``QueryLog`` row
in its own conversation, after its opener as an answered turn. Then the cycle itself runs:
``apps.retrieval.gaps.run_cycle``, the shipped code, with the pipeline's own query embedding. A row
is "left out" when the cycle wrote no item for it. Then the transaction is rolled back, so the
database is left exactly as it was: no row, no gap, no cycle. ``gaps.embed_question`` is wrapped,
in this process only, to record each text the cycle embedded and its vector, so the report can show
each string's top passage; the wrapper returns what the real function returns.

Any zero-result search already in the database falls in the cycle's window too, and would be
embedded if kept. The cycle kept none on either pass (``searches_considered`` 0).

It refuses unless the provider is ``anthropic`` with voyage-4 at 1024, both keys are present (never
printed), and the database is kmp_followups_20261112. It calls no Claude model.

**Before it will run on a fresh restore** of kmp_anthropic's snapshot, the copy's empty
``knowledge_gaps.embedding`` must be ``vector(1024)``: the snapshot's is 768 (D-117's note of 12
November 2026). For both passes the session altered it by hand, on kmp_followups_20261112 alone, by
21:50:05 on 12 November, when the table held no row. That was the session's decision: the user had
approved the copy and this check, not the statement::

    alter table knowledge_gaps alter column embedding type vector(1024)

This docstring was corrected on 13 November 2026, after both passes. The code is as it ran at
``4c36a38``.

Usage, in PowerShell, from the repository root, with the run's DATABASE_URL set::

    & $py corpus\\objective-06\\runs\\2026-11-12-anthropic\\thread-exclusion-check\\thread_exclusion_check.py `
        --dump-sha256 8e79cb377965075dd322d2fb098780cc0d45bc4fdfb5eb5f05d6c59628765a70 --out-dir <folder>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]  # corpus/objective-06/runs/<run>/<this folder>/<this file>
for entry in (str(REPOSITORY_ROOT / "scripts"), str(REPOSITORY_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import measurement_record  # noqa: E402

EXPECTED_DATABASE = "kmp_followups_20261112"
THREADS = REPOSITORY_ROOT / "corpus" / "objective-02" / "dev-threads.json"
ACCOUNTS = {"Employee": "corpus.employee@example.com", "Administrator": "corpus.admin@example.com"}


class Rollback(Exception):
    """Raised at the end of the transaction, so nothing the check wrote is kept."""


def gate(settings) -> list[str]:
    problems = []
    if settings.AI_PROVIDER != "anthropic":
        problems.append(f"AI_PROVIDER is {settings.AI_PROVIDER!r}, not 'anthropic'")
    if settings.VOYAGE_MODEL != "voyage-4":
        problems.append(f"VOYAGE_MODEL is {settings.VOYAGE_MODEL!r}, not 'voyage-4'")
    if int(settings.EMBEDDING_DIMENSION) != 1024:
        problems.append(f"EMBEDDING_DIMENSION is {settings.EMBEDDING_DIMENSION}, not 1024")
    for name in ("VOYAGE_API_KEY", "ANTHROPIC_API_KEY"):
        if not getattr(settings, name, ""):
            problems.append(f"{name} is not set")
    database = str(settings.DATABASES["default"]["NAME"])
    if database != EXPECTED_DATABASE:
        problems.append(f"the database is {database!r}, not {EXPECTED_DATABASE!r}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dump-sha256", required=True, help="SHA-256 of the dump the database was restored from")
    arguments = parser.parse_args()
    if arguments.out_dir.exists() and any(arguments.out_dir.iterdir()):
        print(f"REFUSED: {arguments.out_dir} already holds files. Nothing was run.")
        return 2

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import transaction
    from django.utils import timezone as django_timezone

    from apps.core.constants import EFFECTIVE_ROLES
    from apps.retrieval import gaps
    from apps.retrieval.models import Conversation, KnowledgeGap, KnowledgeGapCycle, KnowledgeGapItem, QueryLog
    from apps.retrieval.ranking import admit, rank

    database = str(settings.DATABASES["default"]["NAME"])
    measurement_record.refuse_protected_database(database)
    problems = gate(settings)
    if problems:
        print("REFUSED: " + "; ".join(problems) + ". Nothing was run.")
        return 2
    print(f"Provider gate: PASS (anthropic, voyage-4 at 1024, both keys present; database {database})")
    before = {"query_logs": QueryLog.objects.count(), "conversations": Conversation.objects.count(),
              "gaps": KnowledgeGap.objects.count(), "items": KnowledgeGapItem.objects.count(),
              "cycles": KnowledgeGapCycle.objects.count()}

    # The corpus's own two accounts, as Objective 06's seeding uses them. A role is checked too, so
    # an account whose role was changed cannot stand in for another.
    users = {role: get_user_model().objects.filter(email=email, role__role_name=role).first()
             for role, email in ACCOUNTS.items()}
    if not all(users.values()):
        print(f"REFUSED: no account with the expected role for {[r for r, u in users.items() if u is None]}. "
              "Nothing was run.")
        return 2

    threads = json.loads(THREADS.read_text(encoding="utf-8"))["threads"]
    asks = []  # (thread, role)
    for thread in threads:
        asks.append((thread, "Employee"))
        if thread["role"] == "both":
            asks.append((thread, "Administrator"))

    recorded: dict[str, object] = {}
    real_embed_question = gaps.embed_question

    def recording_embed_question(text: str):
        result = real_embed_question(text)
        recorded[text] = result
        return result

    gaps.embed_question = recording_embed_question
    results = []
    try:
        with transaction.atomic():
            now = django_timezone.now()
            rows = []
            for index, (thread, role) in enumerate(asks):
                user = users[role]
                conversation = Conversation.objects.create(user=user, title=f"{thread['id']} as {role}")
                opener, follow_up = thread["turns"][0]["question"], thread["turns"][-1]["question"]
                asked = now - timedelta(hours=2, minutes=len(asks) - index)
                first = QueryLog.objects.create(user=user, conversation=conversation, question=opener,
                                                answered=True, answer_text="An answer.")
                second = QueryLog.objects.create(user=user, conversation=conversation, question=follow_up,
                                                 answered=False, answer_text=None, no_answer_reason="no_relevant_passage")
                QueryLog.objects.filter(pk=first.pk).update(answered_at=asked)
                QueryLog.objects.filter(pk=second.pk).update(answered_at=asked + timedelta(seconds=30))
                rows.append((thread, role, opener, follow_up, second.pk))
            cycle = gaps.run_cycle()
            in_log = set(KnowledgeGapItem.objects.filter(query__isnull=False).values_list("query_id", flat=True))
            scope = gaps._AdministratorScope()
            for thread, role, opener, follow_up, pk in rows:
                composed = f"{opener} {follow_up}"
                strings = {}
                for label, text in (("composed", composed), ("own wording", follow_up)):
                    embedding = recorded.get(text)
                    by_the_cycle = embedding is not None
                    if embedding is None:
                        # Not embedded by the cycle, because the composed string already left the row
                        # out. Embedded here for the report only, outside the cycle.
                        embedding = real_embed_question(text)
                    chunks, roles = scope.for_model(embedding.model)
                    ranked = rank(chunks, embedding.vectors[0])
                    admitted = admit(ranked, embedding_model=embedding.model)
                    asker = set(EFFECTIVE_ROLES[role])
                    top = admitted[0] if admitted else None
                    readable = bool(set(roles[top.chunk_id]) & asker) if top else None
                    strings[label] = {
                        "embedded_by_the_cycle": by_the_cycle,
                        "admitted": len(admitted),
                        "top_ranked_score": round(ranked[0].score, 4) if ranked else None,
                        "top_admitted_score": round(top.score, 4) if top else None,
                        "top_admitted_readable_by_asker": readable,
                        # What threshold-first (voyage-4's rule) decides on this string alone: derived
                        # here for the report, not by the cycle.
                        "alone_this_string_would": "left out" if readable is False else "kept",
                    }
                outcome = "kept" if pk in in_log else "left out"
                if thread["kind"] == "scoped" and role == "Employee":
                    expected = "left out"
                elif thread["kind"] == "scoped":
                    expected = "kept"
                else:
                    expected = "kept if unanswered"
                judged = thread["kind"] == "scoped" and role == "Employee"
                results.append({
                    "thread": thread["id"], "kind": thread["kind"], "asked_as": role,
                    "opener": opener, "follow_up": follow_up,
                    "sources": [turn.get("sources") for turn in thread["turns"]],
                    "outcome": outcome, "expected": expected,
                    "as_expected": (outcome == expected) if judged else None,
                    "composed": strings["composed"], "own_wording": strings["own wording"],
                })
                mark = {True: "ok  ", False: "MISS", None: "info"}[results[-1]["as_expected"]]
                c, o = strings["composed"], strings["own wording"]
                print(f"  {mark} {thread['id']} {thread['kind']:<15} as {role:<13} -> {outcome:<8} "
                      f"composed: admitted {c['admitted']}, top {c['top_admitted_score']}, readable "
                      f"{c['top_admitted_readable_by_asker']} | own{'' if o['embedded_by_the_cycle'] else ' (report only)'}: "
                      f"admitted {o['admitted']}, top {o['top_admitted_score']}, readable {o['top_admitted_readable_by_asker']}"
                      f" | {follow_up[:55]}")
            cycle_record = {"queries_considered": cycle.queries_considered, "searches_considered": cycle.searches_considered,
                            "entries_created": cycle.entries_created, "entries_updated": cycle.entries_updated}
            raise Rollback
    except Rollback:
        pass
    finally:
        gaps.embed_question = real_embed_question

    after = {"query_logs": QueryLog.objects.count(), "conversations": Conversation.objects.count(),
             "gaps": KnowledgeGap.objects.count(), "items": KnowledgeGapItem.objects.count(),
             "cycles": KnowledgeGapCycle.objects.count()}
    judged = [r for r in results if r["as_expected"] is not None]
    summary = {
        "scoped_employee": {"total": len(judged), "left_out": sum(1 for r in judged if r["outcome"] == "left out"),
                            "misses": [r["thread"] for r in judged if not r["as_expected"]]},
        "scoped_administrator_kept": [r["thread"] for r in results if r["kind"] == "scoped" and r["asked_as"] == "Administrator" and r["outcome"] == "kept"],
        "other_employee_left_out": [r["thread"] for r in results if r["kind"] != "scoped" and r["outcome"] == "left out"],
        # Derived from each string's top admitted passage, for comparison only: what deciding on one
        # string alone would have done, for the scoped follow-ups asked as the Employee.
        "scoped_employee_left_out_by_the_composed_string_alone": [
            r["thread"] for r in judged if r["composed"]["alone_this_string_would"] == "left out"],
        "scoped_employee_left_out_by_the_own_wording_alone": [
            r["thread"] for r in judged if r["own_wording"]["alone_this_string_would"] == "left out"],
        "passes": all(r["as_expected"] for r in judged),
        "voyage_texts_embedded": len(recorded),
        "the_cycle": cycle_record,
        "database_before": before, "database_after": after, "unchanged": before == after,
    }
    record = measurement_record.run_record(dump_sha256=arguments.dump_sha256, database=database, flm=None)
    record.update({"kind": "D-127's development check on real threads", "configuration": {
        "ai_provider": settings.AI_PROVIDER, "embedding_model": settings.VOYAGE_MODEL,
        "embedding_dimension": int(settings.EMBEDDING_DIMENSION)},
        "threads_file": {THREADS.name: measurement_record.file_sha256(THREADS)},
        "users": {role: user.email for role, user in users.items()},
        "finished_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")})
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    (arguments.out_dir / "thread-exclusion-check.json").write_text(
        json.dumps({"record": record, "summary": summary, "results": results}, indent=2), encoding="utf-8")
    print(f"- Scoped follow-ups asked as the Employee, left out: {summary['scoped_employee']['left_out']} of "
          f"{summary['scoped_employee']['total']}; misses: {summary['scoped_employee']['misses'] or 'none'}")
    print(f"- Scoped follow-ups asked as the Administrator, kept: {summary['scoped_administrator_kept']}")
    print(f"- Other follow-ups asked as the Employee, left out (for information): {summary['other_employee_left_out'] or 'none'}")
    print(f"- {'PASS' if summary['passes'] else 'FAIL'}; database unchanged: {summary['unchanged']}; "
          f"texts embedded: {summary['voyage_texts_embedded']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
