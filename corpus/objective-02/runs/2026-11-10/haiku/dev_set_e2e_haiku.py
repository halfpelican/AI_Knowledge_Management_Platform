"""The Haiku round, step 1 (10 November 2026): D-102's end-to-end pass of dev-set-v2 on claude-haiku-5-5.

A copy of runs/2026-11-10/voyage-threshold/threshold_floor_e2e_voyage.py at 0f184ca, changed only where the
model and the threshold's source were named:

- ANTHROPIC_MODEL is set from --model (default claude-haiku-5-5) before Django starts, and checked after.
  The run refuses unless the model, voyage-4, effort "low", MAXIMUM_STATEMENTS 6 and D-120's
  0.2687 / 0.2468 are what the code will use.
- Nothing is patched. Since D-120 the pipeline reads voyage-4's threshold and floor itself, so the
  --expect-* and --patch-* options are gone. The summary records the values in force, the model and the
  effort.

The bar this run is judged against is in haiku-round.md, committed before any Haiku call. The original
docstring follows.

D-113 (10 November 2026): D-102's end-to-end comparison, on the Voyage-indexed copy with Claude.

A copy of corpus/objective-02/runs/2026-11-08/threshold_floor_e2e.py, changed only where FLM was named:
the database is kmp_voyage_20261110, the provider is ``anthropic`` (Voyage embeddings at 1024,
Claude generation, D-115's Sonnet 5.5), the check_flm.py gate is gone, and the recording wrapper
wraps AnthropicService._claude_once instead of FLMService._chat_once. Every ask still goes through
the shipped answer_question inside transaction.atomic() and is rolled back, and the summary is
phase 2a's summarise, so the table compares like with like.

The original docstring follows.

Step 7 phase 2b (8 November 2026): one end-to-end pass of the development set at the new values.

The same pass as phase 2a's (``corpus/objective-02/runs/2026-11-07/sweep_statement_cap.py``),
on the code as it stands: RELEVANCE_THRESHOLD, PARTIAL_MATCH_FLOOR and MAXIMUM_STATEMENTS are all
read from ``apps/core/constants.py`` with NOTHING patched, and the script refuses to run unless
they equal ``--expect-threshold``, ``--expect-floor`` and 6. The defaults, 0.4472 and 0.4458,
are the literal rule's values, which the first pass (``e2e/``, commit 3c839bb) ran at; the margin
rule's pass (``e2e-margin/``) ran with ``--expect-threshold 0.4231 --expect-floor 0.4036``. Every run of
``corpus/objective-02/dev-set.json`` is asked through the shipped ``answer_question``,
in-process, against kmp_obj02_20261101, inside ``transaction.atomic()`` and rolled back, so no
row is committed; the row counts are checked before and after. Employee runs are asked as
loadtest01, Administrator runs as corpus.admin, as in phase 2a.

What it adds to phase 2a's record, per run:

- the partial matches the reply actually carried (``outcome.partial_matches``, the real offer
  path), each with its source's best score, read from the ranked list the pipeline itself
  produced (a wrapper around ``apps.retrieval.pipeline.rank`` that records its return value and
  changes nothing);
- what the offer would have been without the floor (the five nearest distinct sources of that
  same ranked list), so the floor's effect is visible run by run;
- for an answerable run that ended in no-answer, whether the floor removed a partial match
  pointing at one of its expected sources: the floor's cost, as the rule asks it reported.

Scored with phase 2a's own ``summarise`` (imported from its script), so the table compares like
with like. Imports no AI vendor SDK. Never prints DATABASE_URL. Usage, from anywhere:

    python threshold_floor_e2e.py --out <folder>
    python threshold_floor_e2e.py --out <folder> --label T4231_F4036_N6 \\
        --expect-threshold 0.4231 --expect-floor 0.4036

Phase 2c added ``--set`` (a file in corpus/objective-02/, default dev-set.json) and, for its 0.30
baseline over dev-set-v2.json, ``--patch-threshold`` and ``--patch-floor``: they reassign
``apps.retrieval.ranking.RELEVANCE_THRESHOLD`` and ``apps.retrieval.partial_matches.
PARTIAL_MATCH_FLOOR`` in this process only, the two names the pipeline reads at call time, and
the summary records the values used (``threshold_used``, ``floor_used``, ``patched``):

    python threshold_floor_e2e.py --out <folder> --set dev-set-v2.json --label v2_T3000_nofloor_N6 \\
        --expect-threshold 0.4231 --expect-floor 0.4036 --patch-threshold 0.3 --patch-floor=-inf
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]  # one folder deeper than the 8 November script
DATABASE = "kmp_voyage_20261110"
ACCOUNTS = {"Employee": "loadtest01@example.com", "Administrator": "corpus.admin@example.com"}
UNFLOORED_OFFER = 5  # MAXIMUM_PARTIAL_MATCHES, restated only to reconstruct the BEFORE offer

sys.path.insert(0, str(REPO / "corpus/objective-02/runs/2026-11-07"))
from sweep_statement_cap import LINE, as_int, summarise  # noqa: E402  phase 2a's scoring


def database_url() -> str:
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            value = line.split("=", 1)[1].strip()
            return re.sub(r"/[^/]+$", f"/{DATABASE}", value)
    raise SystemExit("no DATABASE_URL in .env")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="v2_haiku_T2687_F2468_N6")
    parser.add_argument("--set", default="dev-set-v2.json", help="a file in corpus/objective-02/")
    parser.add_argument("--model", default="claude-haiku-5-5",
                        help="the Claude model this run sets as ANTHROPIC_MODEL, then checks")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "server_logs"
    logs.mkdir(exist_ok=True)

    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ["DATABASE_URL"] = database_url()
    os.environ["DEBUG"] = "False"
    os.environ["AI_PROVIDER"] = "anthropic"  # Voyage embeddings, Claude generation
    os.environ["EMBEDDING_DIMENSION"] = "1024"
    os.environ["ANTHROPIC_MODEL"] = args.model  # this copy: the model under test
    os.environ["ERROR_LOG_PATH"] = str(logs / "errors.log")
    os.environ["AUDIT_LOG_PATH"] = str(logs / "audit.log")
    os.environ["WAITRESS_LOG_PATH"] = str(logs / "waitress.log")
    os.environ["ATTEMPTS_LOG_PATH"] = str(logs / "attempts.log")
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "scripts"))
    os.chdir(REPO)

    # No FLM gate: FLM takes no part. A refusing or unreachable provider shows as 503 rows.

    import django

    django.setup()

    import question_set  # scripts/question_set.py
    from django.contrib.auth import get_user_model
    from django.db import connection, transaction

    import apps.ai.anthropic  # noqa: F401
    import apps.ai.generation
    import apps.ai.prompting  # noqa: F401
    import apps.ai.schema  # noqa: F401
    import apps.retrieval.pipeline as pipeline
    from apps.ai import attempt_log
    from apps.ai.base import ProviderUnavailable
    from apps.ai.anthropic import AnthropicService
    from apps.core import constants
    from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME
    from apps.documents.models import ContentChunk, Document
    from apps.meetings.models import Meeting
    from apps.retrieval.models import AnswerCitation, Conversation, QueryLog
    from apps.retrieval.scoping import permission_scope

    if connection.settings_dict["NAME"] != DATABASE:
        print(f"refusing: connected to {connection.settings_dict['NAME']!r}", flush=True)
        return 2
    # This copy: D-120's values for voyage-4 are the code's own, so nothing is patched; the model
    # and the effort are checked, not assumed (haiku-round.md).
    from django.conf import settings

    from apps.ai.anthropic import CLAUDE_EFFORT
    from apps.retrieval.partial_matches import partial_match_floor
    from apps.retrieval.ranking import relevance_threshold

    in_force = {
        "RELEVANCE_THRESHOLD": constants.RELEVANCE_THRESHOLD,
        "PARTIAL_MATCH_FLOOR": constants.PARTIAL_MATCH_FLOOR,
        "MAXIMUM_STATEMENTS": apps.ai.generation.MAXIMUM_STATEMENTS,
        "TOP_K": constants.TOP_K,
        "threshold_used": relevance_threshold(settings.VOYAGE_MODEL),
        "floor_used": partial_match_floor(settings.VOYAGE_MODEL),
        "patched": False,
        "chat_model": settings.ANTHROPIC_MODEL,
        "embed_model": settings.VOYAGE_MODEL,
        "effort": CLAUDE_EFFORT,
    }
    expected_values = {"threshold_used": 0.2687, "floor_used": 0.2468, "MAXIMUM_STATEMENTS": 6,
                       "chat_model": args.model, "embed_model": "voyage-4", "effort": "low"}
    for name, value in expected_values.items():
        if in_force[name] != value:
            print(f"refusing: {name} is {in_force[name]!r}, not {value!r}", flush=True)
            return 2

    set_path = REPO / "corpus/objective-02" / args.set
    _, questions = question_set.load(set_path)
    runs = question_set.expand_runs(questions, (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME))
    manifest = json.loads((REPO / "corpus/objective-02/manifest.json").read_text(encoding="utf-8"))
    item_by_title = {i["title"]: i["id"] for i in manifest["items"]}
    titles = {str(d.id): d.title for d in Document.objects.all()}
    titles.update({str(m.id): m.title for m in Meeting.objects.all()})
    item_by_source = {source_id: item_by_title.get(title) for source_id, title in titles.items()}
    item_by_chunk = {str(c.id): item_by_source.get(str(c.source_id)) for c in ContentChunk.objects.all()}
    roles_by_item = {i["id"]: set(i.get("visible_to_roles") or []) for i in manifest["items"]}

    users = {role: get_user_model().objects.get(email=email) for role, email in ACCOUNTS.items()}
    for role, user in users.items():
        assert permission_scope(user) == role, (role, user.email)

    def counts():
        return {"query_log": QueryLog.objects.count(), "answer_citation": AnswerCitation.objects.count(),
                "conversation": Conversation.objects.count(), "content_chunk": ContentChunk.objects.count()}

    before = counts()
    lines: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record):
            lines.append(record)

    attempts_logger = logging.getLogger(attempt_log.ATTEMPT_LOGGER_NAME)
    attempts_logger.setLevel(logging.INFO)
    attempts_logger.addHandler(Collect(level=logging.INFO))
    verbatim = logging.FileHandler(out / f"e2e_{args.label}.log", encoding="utf-8")
    verbatim.setLevel(logging.INFO)
    verbatim.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    attempts_logger.addHandler(verbatim)

    calls: list[dict] = []
    original_chat = AnthropicService._claude_once

    def recording_chat(self, user_prompt, *rest, **kwargs):
        # Claude's call takes the user prompt as a string; the system prompt is a keyword.
        entry = {"prompt_tail": user_prompt[-260:],
                 "messages_sha256": hashlib.sha256(user_prompt.encode()).hexdigest()}
        try:
            reply = original_chat(self, user_prompt, *rest, **kwargs)
        except Exception as exc:
            entry["call_error"] = f"{type(exc).__name__}: {exc}"
            calls.append(entry)
            raise
        entry.update(text=reply.text, finish_reason=reply.finish_reason,
                     completion_tokens=reply.completion_tokens, prompt_tokens=reply.prompt_tokens)
        calls.append(entry)
        return reply

    AnthropicService._claude_once = recording_chat

    # The ranked list the pipeline itself produced, recorded and returned unchanged.
    ranked_seen: list = []
    original_rank = pipeline.rank

    def recording_rank(candidates, vector):
        ranked = original_rank(candidates, vector)
        ranked_seen.append(ranked)
        return ranked

    pipeline.rank = recording_rank

    results = out / f"e2e_{args.label}.jsonl"
    results.write_text("", encoding="utf-8")
    meta = {"label": args.label, **in_force, "runs": len(runs),
            "set_sha256": question_set.file_sha256(set_path),
            "started": datetime.now().astimezone().isoformat(timespec="seconds")}
    print(json.dumps(meta), flush=True)
    for index, run in enumerate(runs, start=1):
        lines.clear()
        calls.clear()
        ranked_seen.clear()
        user = users[run["role"]]
        started = time.perf_counter()
        status, outcome, detail = 200, None, None
        try:
            with transaction.atomic():
                with attempt_log.account(user.pk):
                    outcome = pipeline.answer_question(question=run["question"], user=user)
                transaction.set_rollback(True)  # write nothing
        except ProviderUnavailable as exc:
            status, detail = 503, str(exc)
        seconds = round(time.perf_counter() - started, 1)

        attempts = []
        generation_lines = [r for r in lines if r.getMessage().startswith("generation attempt")]
        for position, record in enumerate(generation_lines):
            match = LINE.fullmatch(record.getMessage())
            attempt = {"level": record.levelname, "line": record.getMessage()}
            if match:
                fields = match.groupdict()
                rest = fields["rest"]
                attempt.update(
                    number=int(fields["number"]),
                    outcome="parsed" if fields["result"] == "parsed" else (
                        "schema-violation" if rest.startswith("SchemaViolation") else "call-failed"),
                    detail=rest,
                    finish_reason=fields["finish_reason"],
                    completion_tokens=as_int(fields["completion_tokens"]),
                    prompt_tokens=as_int(fields["prompt_tokens"]),
                    max_tokens=as_int(fields["max_tokens"]),
                    max_statements=as_int(fields["max_statements"]),
                    seconds=float(fields["seconds"]),
                )
                attempt["ceiling_hit"] = (
                    attempt["completion_tokens"] is not None and attempt["max_tokens"] is not None
                    and attempt["completion_tokens"] >= attempt["max_tokens"]
                )
            if position < len(calls):
                attempt["call"] = calls[position]
            attempts.append(attempt)

        ranked = ranked_seen[-1] if ranked_seen else []
        best = {}
        for passage in ranked:
            best.setdefault((passage.source_type, str(passage.source_id)), passage.score)
        unfloored = []
        for passage in ranked:
            key = (passage.source_type, str(passage.source_id))
            if key not in [(u["source_type"], u["source_id"]) for u in unfloored]:
                unfloored.append({"source_type": key[0], "source_id": key[1],
                                  "item": item_by_source.get(key[1]), "score": round(passage.score, 6)})
            if len(unfloored) == UNFLOORED_OFFER:
                break
        offered = []
        if outcome is not None:
            for m in outcome.partial_matches:
                key = (m.source_type, str(m.source_id))
                offered.append({"item": item_by_source.get(key[1]), "source_type": key[0],
                                "score": round(best[key], 6) if key in best else None})

        verified = []
        if outcome is not None:
            for statement in outcome.verified_statements:
                verified.append({"text": statement.text, "chunk_id": statement.chunk_id,
                                 "item": item_by_chunk.get(statement.chunk_id)})
        expected_sources = set(run.get("sources") or ([run["source"]] if run.get("source") else []))
        if not run["expects_answer"]:
            expected_sources = set()
        cited_text = " ".join(v["text"] for v in verified if v["item"] in expected_sources)
        all_text = " ".join(v["text"] for v in verified)
        found = question_set.matching_form(run.get("expected_answer"), run.get("accepted"), cited_text) \
            if run["expects_answer"] else None
        anywhere = question_set.matching_form(run.get("expected_answer"), run.get("accepted"), all_text) \
            if run["expects_answer"] else None
        out_of_scope = sum(1 for v in verified if v["item"] and run["role"] not in roles_by_item.get(v["item"], set())
                           and not (run["role"] == ADMINISTRATOR_ROLE_NAME))
        out_of_scope_offers = sum(1 for o in offered if o["item"] and run["role"] not in roles_by_item.get(o["item"], set())
                                  and not (run["role"] == ADMINISTRATOR_ROLE_NAME))
        no_answer = status == 200 and outcome is not None and not outcome.answered
        floor_cost = None
        if run["expects_answer"] and no_answer:
            offered_items = {o["item"] for o in offered}
            unfloored_items = {u["item"] for u in unfloored}
            floor_cost = sorted((unfloored_items & expected_sources) - offered_items)
        row = {
            "label": args.label, "cap": in_force["MAXIMUM_STATEMENTS"], "run": run["run_id"], "role": run["role"],
            "kind": run["kind"], "question": run["question"], "expects_answer": run["expects_answer"],
            "status": status, "answered": bool(outcome and outcome.answered),
            "no_answer_reason": outcome.no_answer_reason if outcome else None,
            "rejected_count": outcome.rejected_count if outcome else None,
            "supplied": [p.chunk_id for p in outcome.passages] if outcome else None,
            "supplied_items": [item_by_chunk.get(p.chunk_id) for p in outcome.passages] if outcome else None,
            "top_score": round(ranked[0].score, 6) if ranked else None,
            "top_item": item_by_chunk.get(ranked[0].chunk_id) if ranked else None,
            "partial_matches_offered": offered, "partial_matches_unfloored": unfloored,
            "out_of_scope_offers": out_of_scope_offers, "floor_cost_expected_sources_lost": floor_cost,
            "verified": verified, "match": found is not None, "matched_form": found,
            "phrase_anywhere": anywhere is not None, "out_of_scope": out_of_scope,
            "seconds": seconds, "attempts": attempts, "detail": detail,
        }
        with results.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        brief = ", ".join(f"{a.get('number')}:{a.get('outcome')}/{a.get('completion_tokens')}/cap{a.get('max_statements')}"
                          for a in attempts)
        offers = ", ".join(f"{o['item']} {o['score']}" for o in offered)
        print(f"{datetime.now().isoformat(timespec='seconds')} {index}/{len(runs)} {run['run_id']} {status} "
              f"answered={row['answered']} reason={row['no_answer_reason']} match={row['match']} {seconds}s "
              f"top={row['top_score']} offered=[{offers}] [{brief}]", flush=True)

    AnthropicService._claude_once = original_chat
    pipeline.rank = original_rank
    after = counts()
    rows = [json.loads(l) for l in results.read_text(encoding="utf-8").splitlines() if l.strip()]
    summary = {**meta, "finished": datetime.now().astimezone().isoformat(timespec="seconds"),
               "counts_before": before, "counts_after": after, **summarise(rows)}
    (out / f"e2e_{args.label}_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 0 if before == after else 1


if __name__ == "__main__":
    sys.exit(main())
