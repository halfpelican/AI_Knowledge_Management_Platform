"""Step 7 phase 1 (7 November 2026): observe generation attempts, in-process, without writing rows.

Runs the shipped pipeline, ``apps.retrieval.pipeline.answer_question``, the way NFR-08's
k6 runs asked (an Employee, loadtest01, no conversation), against the measurement database
``kmp_obj02_20261101``. Each ask runs inside ``transaction.atomic()`` and is rolled back, so
no QueryLog, AnswerCitation or Conversation row survives; the counts are checked before and
after.

What it records, per attempt:

- the shipped attempt log's own line (apps/ai/attempt_log.py), read from the
  ``apps.ai.attempts`` logger lowered to INFO, so parsed attempts are seen as well as failed;
- beside it, from a wrapper around ``FLMService._chat_once`` that records and changes
  nothing: the reply text, its SHA-256, the reported finish_reason and token counts, the
  max_tokens sent, and a SHA-256 of the messages sent, so identical prompts can be told
  apart from different ones.

Imports no AI vendor SDK (CLAUDE.md section 4): the wrapper is around apps.ai's own method.
Never prints DATABASE_URL. Usage, from the worktree root:

    python observe_generation.py --out <folder>
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

REPO = Path(r"C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype-step4")
DATABASE = "kmp_obj02_20261101"
FLM_URL = "http://127.0.0.1:8625/v1"
ACCOUNT = "loadtest01@example.com"  # Employee, as tests/load/common.js requires

FAILING = "How are records managed and retained?"  # tests/load/common.js QUESTIONS[3]
COMPARE = [
    "What is the leave policy for annual leave?",  # QUESTIONS[0]
    "What are the rules for acceptable use of IT equipment?",  # QUESTIONS[1]
    "How do I make a complaint?",  # QUESTIONS[5]
]

LINE = re.compile(
    r"generation attempt (?P<number>\d+) of (?P<of>\d+) (?P<result>failed|parsed) after "
    r"(?P<seconds>[\d.]+) s \[finish_reason=(?P<finish_reason>\S+) "
    r"completion_tokens=(?P<completion_tokens>\S+) prompt_tokens=(?P<prompt_tokens>\S+) "
    r"max_tokens=(?P<max_tokens>\S+)\] \(account [^)]*\): (?P<rest>.*)"
)


def database_url() -> str:
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            value = line.split("=", 1)[1].strip()
            return re.sub(r"/[^/]+$", f"/{DATABASE}", value)
    raise SystemExit("no DATABASE_URL in .env")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--failing-runs", type=int, default=10)
    parser.add_argument("--compare-runs", type=int, default=3)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "server_logs"
    logs.mkdir(exist_ok=True)

    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ["DATABASE_URL"] = database_url()
    os.environ["DEBUG"] = "False"
    os.environ["FLM_BASE_URL"] = FLM_URL
    os.environ["AI_PROVIDER"] = "flm"
    # The error, audit and Waitress files go to the scratch folder, not the worktree's logs/.
    os.environ["ERROR_LOG_PATH"] = str(logs / "errors.log")
    os.environ["AUDIT_LOG_PATH"] = str(logs / "audit.log")
    os.environ["WAITRESS_LOG_PATH"] = str(logs / "waitress.log")
    sys.path.insert(0, str(REPO))
    os.chdir(REPO)

    # The FLM gate (D-83), before anything is asked.
    gate = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_flm.py")],
        capture_output=True, text=True, timeout=600, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    (out / "check_flm.txt").write_text(gate.stdout + gate.stderr, encoding="utf-8")
    if gate.returncode != 0 or not any(l.startswith("RESULT: PASS") for l in gate.stdout.splitlines()):
        print("check_flm.py did not pass; nothing asked", flush=True)
        return 2

    import django

    django.setup()

    from django.contrib.auth import get_user_model
    from django.db import connection, transaction

    from apps.ai import attempt_log
    from apps.ai.base import ProviderUnavailable
    from apps.ai.flm import FLMService
    from apps.documents.models import ContentChunk
    from apps.retrieval.models import AnswerCitation, Conversation, QueryLog
    from apps.retrieval.pipeline import answer_question
    from apps.retrieval.scoping import permission_scope

    if connection.settings_dict["NAME"] != DATABASE:
        print(f"refusing: connected to {connection.settings_dict['NAME']!r}", flush=True)
        return 2

    user = get_user_model().objects.get(email=ACCOUNT)
    role = permission_scope(user)
    if role != "Employee":
        print(f"refusing: {ACCOUNT} is {role!r}, not Employee", flush=True)
        return 2

    def counts():
        return {
            "query_log": QueryLog.objects.count(),
            "answer_citation": AnswerCitation.objects.count(),
            "conversation": Conversation.objects.count(),
            "content_chunk": ContentChunk.objects.count(),
        }

    before = counts()

    # The shipped attempt log, read at INFO.
    lines: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record):
            lines.append(record)

    attempts_logger = logging.getLogger(attempt_log.ATTEMPT_LOGGER_NAME)
    attempts_logger.setLevel(logging.INFO)
    collector = Collect(level=logging.INFO)
    attempts_logger.addHandler(collector)
    verbatim = logging.FileHandler(out / "attempts.log", encoding="utf-8")
    verbatim.setLevel(logging.INFO)
    verbatim.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    attempts_logger.addHandler(verbatim)

    # What each call sent and got back, recorded beside the shipped line; nothing is changed.
    calls: list[dict] = []
    original_chat_once = FLMService._chat_once

    def recording_chat_once(self, messages, *, max_tokens):
        entry = {
            "messages_sha256": sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False)),
            "max_tokens_sent": max_tokens,
        }
        started = time.perf_counter()
        try:
            reply = original_chat_once(self, messages, max_tokens=max_tokens)
        except Exception as exc:
            entry.update(seconds=round(time.perf_counter() - started, 1), call_error=f"{type(exc).__name__}: {exc}")
            calls.append(entry)
            raise
        entry.update(
            seconds=round(time.perf_counter() - started, 1),
            finish_reason=reply.finish_reason,
            completion_tokens=reply.completion_tokens,
            prompt_tokens=reply.prompt_tokens,
            text_chars=len(reply.text),
            text_sha256=sha256(reply.text),
            text=reply.text,
        )
        calls.append(entry)
        return reply

    FLMService._chat_once = recording_chat_once

    plan = []
    half = args.failing_runs // 2
    plan += [("failing", FAILING)] * half
    plan += [("compare", q) for q in COMPARE]
    plan += [("failing", FAILING)] * (args.failing_runs - half)
    for _ in range(max(args.compare_runs - 1, 0)):
        plan += [("compare", q) for q in COMPARE]

    results_path = out / "attempts.jsonl"
    print(f"{datetime.now().isoformat(timespec='seconds')} start: {len(plan)} asks as {ACCOUNT} ({role})", flush=True)
    for ask_number, (kind, question) in enumerate(plan, start=1):
        lines.clear()
        calls.clear()
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        started = time.perf_counter()
        outcome: dict
        try:
            with transaction.atomic():
                with attempt_log.account(user.pk):
                    result = answer_question(question=question, user=user)
                outcome = {
                    "status": 200,
                    "answered": result.answered,
                    "no_answer_reason": result.no_answer_reason,
                    "verified_statements": len(result.verified_statements),
                    "rejected_count": result.rejected_count,
                    "supplied_chunk_ids": [p.chunk_id for p in result.passages],
                }
                transaction.set_rollback(True)  # write nothing
        except ProviderUnavailable as exc:
            outcome = {"status": 503, "detail": str(exc)}
        elapsed = round(time.perf_counter() - started, 1)

        attempts = []
        for index, record in enumerate(r for r in lines if r.getMessage().startswith("generation attempt")):
            message = record.getMessage()
            parsed = LINE.fullmatch(message)
            attempt = {"level": record.levelname, "line": message}
            if parsed:
                fields = parsed.groupdict()
                attempt.update(
                    number=int(fields["number"]),
                    outcome="parsed" if fields["result"] == "parsed" else (
                        "schema-violation" if fields["rest"].startswith("SchemaViolation: ") else "call-failed"
                    ),
                    detail=fields["rest"],
                    finish_reason=fields["finish_reason"],
                    completion_tokens=fields["completion_tokens"],
                    prompt_tokens=fields["prompt_tokens"],
                    max_tokens=fields["max_tokens"],
                    seconds=float(fields["seconds"]),
                )
            if index < len(calls):
                attempt["call"] = calls[index]
            attempts.append(attempt)

        row = {
            "ask": ask_number,
            "kind": kind,
            "question": question,
            "started_at": started_at,
            "seconds": elapsed,
            "outcome": outcome,
            "attempts": attempts,
            "unmatched_calls": len(calls) - len(attempts),
        }
        with results_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        summary = ", ".join(
            f"{a.get('number')}:{a.get('outcome')}/{a.get('finish_reason')}/{a.get('completion_tokens')}" for a in attempts
        )
        print(f"{datetime.now().isoformat(timespec='seconds')} ask {ask_number} {kind} {outcome['status']} "
              f"{elapsed}s [{summary}]", flush=True)

    after = counts()
    (out / "counts.json").write_text(json.dumps({"before": before, "after": after}, indent=1), encoding="utf-8")
    print(f"counts before {before} after {after} unchanged={before == after}", flush=True)
    FLMService._chat_once = original_chat_once
    return 0 if before == after else 1


if __name__ == "__main__":
    sys.exit(main())
