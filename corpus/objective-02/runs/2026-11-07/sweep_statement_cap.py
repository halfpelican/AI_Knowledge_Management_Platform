"""Step 7 phase 2a (7 November 2026): the statement cap, swept over the development set.

Asks every run of corpus/objective-02/dev-set.json through the shipped pipeline,
``apps.retrieval.pipeline.answer_question``, in-process, against kmp_obj02_20261101, each ask
inside ``transaction.atomic()`` and rolled back, so nothing is committed. Employee runs are
asked as loadtest01, Administrator runs as corpus.admin.

``--cap N`` sets the cap for this process by assigning ``apps.ai.generation.MAXIMUM_STATEMENTS``,
the one name the attempt loop reads its first attempt's cap from. Without ``--cap`` nothing is
patched: run on the code before the cap existed, that is the baseline ("no cap").

Per attempt it records the shipped attempt log's own line (apps/ai/attempt_log.py, the logger
lowered to INFO), and beside it, from a wrapper around ``FLMService._chat_once`` that records
and changes nothing: the reply text, the tail of the user prompt (where the cap is stated) and
the reported token counts. Per run: the outcome, the verified statements with the manifest item
each cites, and the scores below.

Scores, per run:
- ceiling hit: an attempt whose completion_tokens >= the max_tokens it sent;
- 503: three attempts without a conforming reply;
- answered where expected / not answered where none expected (a 503 is neither);
- expected-answer match: expected_answer or an accepted phrase (scripts/question_set.py
  matching_form) found in the verified statements that cite one of the run's expected
  sources. A phrase in a statement citing anything else does not count.

Imports no AI vendor SDK. Never prints DATABASE_URL. Usage, from the worktree root, with
DATABASE_URL, FLM_BASE_URL and the log paths set as for the phase 1 run:

    python sweep_statement_cap.py --label N4 --cap 4 --out <folder>
    python sweep_statement_cap.py --summarise <folder>/sweep_*.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DATABASE = "kmp_obj02_20261101"
ACCOUNTS = {"Employee": "loadtest01@example.com", "Administrator": "corpus.admin@example.com"}

LINE = re.compile(
    r"generation attempt (?P<number>\d+) of (?P<of>\d+) (?P<result>failed|parsed) after "
    r"(?P<seconds>[\d.]+) s \[finish_reason=(?P<finish_reason>\S+) "
    r"completion_tokens=(?P<completion_tokens>\S+) prompt_tokens=(?P<prompt_tokens>\S+) "
    r"max_tokens=(?P<max_tokens>[^\s\]]+)(?: max_statements=(?P<max_statements>[^\s\]]+))?\] "
    r"\(account [^)]*\): (?P<rest>.*)"
)


def as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def summarise(rows: list[dict]) -> dict:
    attempts = [a for r in rows for a in r["attempts"]]
    tokens = [a["completion_tokens"] for a in attempts if isinstance(a.get("completion_tokens"), int)]
    attempt_seconds = [a["seconds"] for a in attempts if isinstance(a.get("seconds"), (int, float))]
    ask_seconds = [r["seconds"] for r in rows]
    expected = [r for r in rows if r["expects_answer"]]
    unexpected = [r for r in rows if not r["expects_answer"]]
    return {
        "runs": len(rows),
        "attempts": len(attempts),
        "ceiling_hits": sum(1 for a in attempts if a.get("ceiling_hit")),
        "server_503": sum(1 for r in rows if r["status"] == 503),
        "cap_violations": sum(1 for a in attempts if "more than the" in (a.get("detail") or "")),
        "schema_violations": sum(1 for a in attempts if a.get("outcome") == "schema-violation"),
        "answered_where_expected": f"{sum(1 for r in expected if r['answered'])}/{len(expected)}",
        "no_answer_where_expected": f"{sum(1 for r in unexpected if r['status'] == 200 and not r['answered'])}/{len(unexpected)}",
        "expected_answer_match": f"{sum(1 for r in expected if r['match'])}/{len(expected)}",
        "phrase_anywhere": f"{sum(1 for r in expected if r['phrase_anywhere'])}/{len(expected)}",
        "out_of_scope_citations": sum(r["out_of_scope"] for r in rows),
        "completion_tokens_median": statistics.median(tokens) if tokens else None,
        "completion_tokens_max": max(tokens) if tokens else None,
        "attempt_seconds_median": round(statistics.median(attempt_seconds), 1) if attempt_seconds else None,
        "attempt_seconds_max": max(attempt_seconds) if attempt_seconds else None,
        "ask_seconds_median": round(statistics.median(ask_seconds), 1) if ask_seconds else None,
        "ask_seconds_max": max(ask_seconds) if ask_seconds else None,
        "statements_per_answer_max": max((len(r["verified"]) for r in rows), default=0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label")
    parser.add_argument("--cap", type=int)
    parser.add_argument("--out")
    parser.add_argument("--summarise", nargs="*")
    args = parser.parse_args()

    if args.summarise:
        for path in args.summarise:
            rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
            print(Path(path).name, json.dumps(summarise(rows)))
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "scripts"))
    os.chdir(REPO)

    gate = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_flm.py")],
        capture_output=True, text=True, timeout=600, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    (out / f"check_flm_{args.label}.txt").write_text(gate.stdout + gate.stderr, encoding="utf-8")
    if gate.returncode != 0 or not any(l.startswith("RESULT: PASS") for l in gate.stdout.splitlines()):
        print("check_flm.py did not pass; nothing asked", flush=True)
        return 2

    import django

    django.setup()

    import question_set  # scripts/question_set.py
    from django.contrib.auth import get_user_model
    from django.db import connection, transaction

    # Everything the pipeline will import, imported now: nothing is loaded from disk mid-run.
    import apps.ai.flm  # noqa: F401
    import apps.ai.generation
    import apps.ai.prompting  # noqa: F401
    import apps.ai.schema  # noqa: F401
    from apps.ai import attempt_log
    from apps.ai.base import ProviderUnavailable
    from apps.ai.flm import FLMService
    from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME
    from apps.documents.models import ContentChunk, Document
    from apps.meetings.models import Meeting
    from apps.retrieval.models import AnswerCitation, Conversation, QueryLog
    from apps.retrieval.pipeline import answer_question
    from apps.retrieval.scoping import permission_scope

    if connection.settings_dict["NAME"] != DATABASE:
        print(f"refusing: connected to {connection.settings_dict['NAME']!r}", flush=True)
        return 2

    code_has_cap = hasattr(apps.ai.generation, "MAXIMUM_STATEMENTS")
    if args.cap is not None:
        if not code_has_cap:
            print("refusing: --cap given but this code has no MAXIMUM_STATEMENTS", flush=True)
            return 2
        apps.ai.generation.MAXIMUM_STATEMENTS = args.cap
    cap_in_force = getattr(apps.ai.generation, "MAXIMUM_STATEMENTS", None)

    roles = (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME)
    set_path = REPO / "corpus/objective-02/dev-set.json"
    _, questions = question_set.load(set_path)
    runs = question_set.expand_runs(questions, roles)
    manifest = json.loads((REPO / "corpus/objective-02/manifest.json").read_text(encoding="utf-8"))
    item_by_title = {i["title"]: i for i in manifest["items"]}
    titles = {str(d.id): d.title for d in Document.objects.all()}
    titles.update({str(m.id): m.title for m in Meeting.objects.all()})
    item_by_chunk = {}
    for chunk in ContentChunk.objects.all():
        item = item_by_title.get(titles.get(str(chunk.source_id)))
        item_by_chunk[str(chunk.id)] = item["id"] if item else None
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
    verbatim = logging.FileHandler(out / f"sweep_{args.label}.log", encoding="utf-8")
    verbatim.setLevel(logging.INFO)
    verbatim.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    attempts_logger.addHandler(verbatim)

    calls: list[dict] = []
    original = FLMService._chat_once

    def recording(self, messages, *rest, **kwargs):
        user_prompt = next((m["content"] for m in messages if m["role"] == "user"), "")
        entry = {"prompt_tail": user_prompt[-260:],
                 "messages_sha256": hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()}
        try:
            reply = original(self, messages, *rest, **kwargs)
        except Exception as exc:
            entry["call_error"] = f"{type(exc).__name__}: {exc}"
            calls.append(entry)
            raise
        entry.update(text=reply.text, finish_reason=reply.finish_reason,
                     completion_tokens=reply.completion_tokens, prompt_tokens=reply.prompt_tokens)
        calls.append(entry)
        return reply

    FLMService._chat_once = recording

    results = out / f"sweep_{args.label}.jsonl"
    results.write_text("", encoding="utf-8")
    meta = {"label": args.label, "cap": cap_in_force, "code_has_cap": code_has_cap, "runs": len(runs),
            "set_sha256": question_set.file_sha256(set_path),
            "started": datetime.now().astimezone().isoformat(timespec="seconds")}
    print(json.dumps(meta), flush=True)
    for index, run in enumerate(runs, start=1):
        lines.clear()
        calls.clear()
        user = users[run["role"]]
        started = time.perf_counter()
        status, outcome = 200, None
        try:
            with transaction.atomic():
                with attempt_log.account(user.pk):
                    outcome = answer_question(question=run["question"], user=user)
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

        verified = []
        if outcome is not None:
            for statement in outcome.verified_statements:
                verified.append({"text": statement.text, "chunk_id": statement.chunk_id,
                                 "item": item_by_chunk.get(statement.chunk_id)})
        expected_sources = set(run.get("sources") or ([run["source"]] if run.get("source") else []))
        cited_text = " ".join(v["text"] for v in verified if v["item"] in expected_sources)
        all_text = " ".join(v["text"] for v in verified)
        found = question_set.matching_form(run.get("expected_answer"), run.get("accepted"), cited_text) \
            if run["expects_answer"] else None
        anywhere = question_set.matching_form(run.get("expected_answer"), run.get("accepted"), all_text) \
            if run["expects_answer"] else None
        out_of_scope = sum(1 for v in verified if v["item"] and run["role"] not in roles_by_item.get(v["item"], set())
                           and not (run["role"] == ADMINISTRATOR_ROLE_NAME))
        row = {
            "label": args.label, "cap": cap_in_force, "run": run["run_id"], "role": run["role"],
            "kind": run["kind"], "question": run["question"], "expects_answer": run["expects_answer"],
            "status": status, "answered": bool(outcome and outcome.answered),
            "no_answer_reason": outcome.no_answer_reason if outcome else None,
            "rejected_count": outcome.rejected_count if outcome else None,
            "supplied": [p.chunk_id for p in outcome.passages] if outcome else None,
            "verified": verified, "match": found is not None, "matched_form": found,
            "phrase_anywhere": anywhere is not None, "out_of_scope": out_of_scope,
            "seconds": seconds, "attempts": attempts, "detail": detail if status == 503 else None,
        }
        with results.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        brief = ", ".join(f"{a.get('number')}:{a.get('outcome')}/{a.get('completion_tokens')}/cap{a.get('max_statements')}"
                          for a in attempts)
        print(f"{datetime.now().isoformat(timespec='seconds')} {index}/{len(runs)} {run['run_id']} {status} "
              f"answered={row['answered']} match={row['match']} {seconds}s [{brief}]", flush=True)

    FLMService._chat_once = original
    after = counts()
    rows = [json.loads(l) for l in results.read_text(encoding="utf-8").splitlines() if l.strip()]
    summary = {**meta, "finished": datetime.now().astimezone().isoformat(timespec="seconds"),
               "counts_before": before, "counts_after": after, **summarise(rows)}
    (out / f"sweep_{args.label}_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 0 if before == after else 1


if __name__ == "__main__":
    sys.exit(main())
