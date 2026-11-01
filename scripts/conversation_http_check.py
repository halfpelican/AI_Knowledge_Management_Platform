"""FR-13 through the server: the history a turn reads from QueryLog is wired (D-86 decision 6).

The harness's ``--threads`` mode measures FR-13 in-process, with ``compose()``. This check
proves the other half: that ``POST /api/ask``, given a ``conversation_id``, reads the
thread's earlier question from QueryLog and composes it into turn two. It takes the two or
three threads named in ``threads.json``'s ``http_check``, and for each:

1. ``POST /api/conversations`` as the thread's role;
2. ``POST /api/ask`` with the first question, then with the follow-up, in that thread,
   asks paced at least MINIMUM_ASK_INTERVAL_SECONDS apart and never overlapping (D-79:
   ten asks a minute, and one ask in flight per user);
3. ``GET /api/conversations/{id}``: two turns, holding the questions as asked;
4. the two QueryLog rows, read here through the ORM: the passages the server supplied on
   each turn (``retrieved_chunk_ids``);
5. the same retrieval in this process, through the pipeline's own functions, for the
   follow-up composed WITH the first question and WITHOUT it.

The verdict is WIRED when turn two's supplied passages are the ones the composed string
retrieves and not the ones the bare follow-up retrieves. That is the history, read from
QueryLog, changing what was retrieved, which nothing else in the reply could show. The reply
to turn two is also scored with the frozen scoring rule, and checked for a leak (part 7e).

Usage, with the measurement server and FLM running and the step 1 block of
docs/measurement-runbook.md pasted into the shell::

    $env:KMP_CORPUS_ADMIN_EMAIL = "..."      # the Administrator, as for the ingestion
    $env:KMP_CORPUS_ADMIN_PASSWORD = "..."
    $env:KMP_CORPUS_EMPLOYEE_EMAIL = "..."   # the Employee, as for the ingestion
    $env:KMP_CORPUS_EMPLOYEE_PASSWORD = "..."
    .venv\\Scripts\\python.exe scripts\\conversation_http_check.py ^
        --dump-sha256 <the snapshot's SHA-256> --out <run folder>\\http_check.json

**It refuses (exit 2), with no request sent to the server, when:**

- there is neither a dump hash with ``--out``, nor ``--unrecorded``; or ``--out`` exists;
- the thread set does not validate, or names no http_check threads;
- this process's database is ``kmp``, recorded or not, because this run writes;
- a credential is not set;
- check_flm.py's checks fail, or (recorded) FLM is not v0.9.39;
- (recorded) the indexed corpus is not exactly the manifest's 25 items;
- the server at ``--base-url`` is positively not D-85's Waitress at 24 threads, unless
  ``--any-server``.

It also refuses, after signing in and before any thread is created, when the server's
documents and meetings are not this process's: the server must serve the database these
gates checked. Signing in is the only write before that point.

**What it writes, through the server:** per thread, one Conversation row and two QueryLog
rows, with an answered turn's AnswerCitation rows. None is a retrieval candidate, so no
restore is needed afterwards (D-86 decision 6). Signing in also writes a session, the user's
last login and an audit-log line. Its own record goes to ``--out``. It writes nothing to the
database itself: every ORM call here is a read.

**What it records:** the commit SHA, the FLM version, the dump hash, the database name, the
thread file's SHA-256, the server (scripts/server_record.py: observed process, version and
thread count), the pacing actually achieved, and per thread the replies' statements and
sources, the rows' supplied passages and the in-process comparison.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS_DIRECTORY.parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import measurement_record  # noqa: E402  scripts/measurement_record.py
import server_record  # noqa: E402  scripts/server_record.py
import thread_set  # noqa: E402  scripts/thread_set.py

REFUSED = 2
DEFAULT_THREADS = REPOSITORY_ROOT / "corpus" / "objective-02" / "threads.json"
# D-79: ten asks a minute per user, so six seconds apart is the floor; seven leaves room,
# as the k6 scripts do (tests/load/README.md). Measured start to start, and the next ask
# never starts before the previous reply has arrived: one ask in flight per user.
MINIMUM_ASK_INTERVAL_SECONDS = 7.0
CREDENTIALS = {
    "Administrator": ("KMP_CORPUS_ADMIN_EMAIL", "KMP_CORPUS_ADMIN_PASSWORD"),
    "Employee": ("KMP_CORPUS_EMPLOYEE_EMAIL", "KMP_CORPUS_EMPLOYEE_PASSWORD"),
}

WIRED = "WIRED"
NOT_SHOWN = "WIRED AS FAR AS CAN BE SEEN: the history changed nothing retrieval shows"
NOT_APPLIED = "HISTORY NOT APPLIED"
MISMATCH = "MISMATCH"
FAILED = "FAILED"


class Pacer:
    """Start-to-start spacing for asks. ``wait()`` before each ask; it returns the gap."""

    def __init__(self, interval: float, clock=time.monotonic, sleep=time.sleep):
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self.last_start: float | None = None
        self.gaps: list[float] = []

    def wait(self) -> float | None:
        if self.last_start is not None:
            remaining = self.interval - (self.clock() - self.last_start)
            if remaining > 0:
                self.sleep(remaining)
        now = self.clock()
        gap = None if self.last_start is None else now - self.last_start
        if gap is not None:
            self.gaps.append(gap)
        self.last_start = now
        return gap


NOTHING_SENT = "No request was sent to the server."
# Two since D-87: GET /api/ for the Server header, and server_record's DEBUG probe.
ONE_GET_SENT = "Only two unauthenticated GETs reached the server: /api/ and the DEBUG probe."
NO_THREAD_CREATED = "Only the sign-ins and two list reads reached the server; no thread was created."


def refuse(reasons: list[str], said: str = NOTHING_SENT) -> int:
    print()
    for reason in reasons:
        print(f"REFUSED: {reason}")
    print(said)
    return REFUSED


def credential_problems(environment) -> list[str]:
    missing = [name for pair in CREDENTIALS.values() for name in pair if not environment.get(name)]
    return [f"set {', '.join(missing)} (the accounts the ingestion signed in as)"] if missing else []


def server_database_problems(
    *, served_ids: set[str], local_ids: set[str], base_url: str, database: str
) -> list[str]:
    """Why the server is not serving the database this process gated. Empty if it is.

    ``served_ids`` are the document and meeting ids the server lists to an Administrator,
    who reads everything (D-66); ``local_ids`` are this process's. Ingestion gives every row
    a fresh UUID, so a server on another database lists ids this one does not hold.
    """
    if not served_ids:
        return [f"the server at {base_url} lists no documents or meetings, so it is not serving "
                f"{database}'s corpus"]
    strangers = served_ids - local_ids
    if strangers:
        return [f"the server at {base_url} lists {len(strangers)} document(s) or meeting(s) that "
                f"{database} does not hold: it is serving another database"]
    return []


def leak_problems(body_text: str, forbidden: dict[str, str]) -> list[str]:
    """Scoring rule part 7e: an out-of-scope source's id or title anywhere in a reply body.

    ``forbidden`` maps the source ids the role may not read to their titles.
    """
    found = []
    for source_id, title in forbidden.items():
        if source_id in body_text:
            found.append(f"the id of an out-of-scope source ({source_id}) is in a reply")
        if title and title in body_text:
            found.append(f"the title of an out-of-scope source ({title!r}) is in a reply")
    return found


def verdict(*, server: list[str], with_history: list[str], cold: list[str]) -> str:
    """Turn two's supplied passages on the server, against compose() with and without history.

    Compared as sets: the same strings embed to the same vector on a deterministic FLM
    (check_flm.py's gate), but a score tied at the threshold or the context budget could
    still order differently, so the order is recorded beside the verdict, not decided on.
    """
    served, composed, alone = set(server), set(with_history), set(cold)
    if served == composed and composed != alone:
        return WIRED
    if served == composed:
        return NOT_SHOWN
    if served == alone:
        return NOT_APPLIED
    return MISMATCH


def django_setup():
    """Settings and the ORM, for the gates and the reads. Opens no connection by itself."""
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def sign_in(session_class, base_url: str, email: str, password: str, role: str):
    """(session, problem). The server's own login, so the session is a browser's."""
    session = session_class(base_url)
    status, body, _, note = session.request(
        "POST", "/api/auth/login", json_body={"email": email, "password": password}
    )
    if status != 200 or not isinstance(body, dict):
        return None, f"could not sign in as {email}: HTTP {status} {note or ''}".strip()
    if body.get("role") != role:
        return None, f"{email} signed in with role {body.get('role')!r}, not {role!r}"
    return session, None


def supplied_ids(text: str, role: str) -> list[str]:
    """What POST /api/ask would supply to generation for ``text``: pipeline steps 3 to 7.

    The pipeline's own functions, in its order, read-only. ``text`` is a retrieval string
    from compose(), so this is the server's turn reproduced up to the prompt.
    """
    from apps.retrieval.query_embedding import embed_question
    from apps.retrieval.ranking import admit, rank, truncate_to_context
    from apps.retrieval.scoping import candidate_chunks

    embedding = embed_question(text)
    candidates = candidate_chunks(role_name=role, embedding_model=embedding.model)
    return [p.chunk_id for p in truncate_to_context(admit(rank(candidates, embedding.vectors[0])))]


def summarise_reply(body) -> dict:
    """The parts of an ask reply this record keeps. No passage text."""
    if not isinstance(body, dict):
        return {"body": body}
    return {
        "answered": body.get("answered"),
        "result_count": body.get("result_count"),
        "statements": [{"text": s.get("text"), "chunk_id": s.get("chunk_id")} for s in body.get("statements", [])],
        "sources": [
            {"source_type": s.get("source_type"), "source_id": s.get("source_id"), "title": s.get("title"),
             "chunk_ids": [p.get("chunk_id") for p in s.get("passages", [])]}
            for s in body.get("sources", [])
        ],
        "partial_matches": [m.get("source_id") for m in body.get("partial_matches", [])],
    }


def check_thread(entry, thread, session, user, pacer, context) -> dict:
    """One http_check thread through the server, then the comparison. Never raises on a reply."""
    from apps.retrieval.conversation import compose
    from apps.retrieval.models import QueryLog

    first, follow_up = thread["turns"][0]["question"], thread["turns"][1]["question"]
    role = entry["role"]
    out: dict = {"thread": thread["id"], "role": role, "questions": [first, follow_up], "asks": []}

    status, body, _, note = session.request("POST", "/api/conversations", json_body={})
    if status != 201 or not isinstance(body, dict) or not body.get("conversation_id"):
        out.update(verdict=FAILED, problem=f"POST /api/conversations: HTTP {status} {note or ''}".strip())
        return out
    conversation_id = body["conversation_id"]
    out["conversation_id"] = conversation_id

    bodies = []
    for question in (first, follow_up):
        gap = pacer.wait()
        status, body, seconds, note = session.request(
            "POST", "/api/ask", json_body={"question": question, "conversation_id": conversation_id}
        )
        out["asks"].append({"question": question, "http_status": status, "seconds": round(seconds, 2),
                            "gap_from_previous_ask": None if gap is None else round(gap, 2),
                            "transport_note": note, "server_header": session.last_headers.get("server"),
                            "reply": summarise_reply(body)})
        bodies.append(json.dumps(body) if body is not None else "")
        if status != 200:
            out.update(verdict=FAILED, problem=f"POST /api/ask: HTTP {status}",
                       throttled=status == 429)
            return out

    status, detail, _, _ = session.request("GET", f"/api/conversations/{conversation_id}")
    turns = [turn.get("question") for turn in detail.get("turns", [])] if isinstance(detail, dict) else []
    out["thread_read"] = {"http_status": status, "turn_questions": turns}

    rows = list(QueryLog.objects.filter(conversation_id=conversation_id).order_by("answered_at", "id"))
    out["query_log"] = [
        {"question": row.question, "answered": row.answered, "no_answer_reason": row.no_answer_reason,
         "rejected_count": row.rejected_count, "same_user": row.user_id == user.pk,
         "retrieved_chunk_ids": [str(chunk_id) for chunk_id in row.retrieved_chunk_ids]}
        for row in rows
    ]
    problems = []
    if turns != [first, follow_up]:
        problems.append(f"the thread read back holds {turns}, not the two questions as asked")
    if [row.question for row in rows] != [first, follow_up]:
        problems.append("the QueryLog rows do not hold the two questions as asked (D-42: never composed)")
    if not all(row.user_id == user.pk for row in rows):
        problems.append("a QueryLog row of this thread belongs to another user")
    if problems or len(rows) != 2:
        out.update(verdict=FAILED, problem="; ".join(problems) or f"{len(rows)} QueryLog row(s), not 2")
        return out

    composed, alone = compose(follow_up, [first]), compose(follow_up, [])
    expected = {
        "first_turn": supplied_ids(compose(first, []).for_retrieval, role),
        "with_history": supplied_ids(composed.for_retrieval, role),
        "cold": supplied_ids(alone.for_retrieval, role),
    }
    served = out["query_log"][1]["retrieved_chunk_ids"]
    out["in_process"] = {**expected, "with_history_retrieval_text": composed.for_retrieval}
    out["verdict"] = verdict(server=served, with_history=expected["with_history"], cold=expected["cold"])
    out["same_order_as_compose"] = served == expected["with_history"]
    out["first_turn_matches_a_one_off"] = set(out["query_log"][0]["retrieved_chunk_ids"]) == set(expected["first_turn"])

    # The frozen scoring rule on the reply to turn two (parts 2, 4, 5 and 7e).
    reply = out["asks"][1]["reply"]
    verified = [{"text": s["text"], "chunk_id": s["chunk_id"], "item": context["item_by_chunk"].get(s["chunk_id"])}
                for s in reply.get("statements", [])]
    run = {"run_id": f"{thread['id']}@{role}/http", "thread_id": thread["id"], "kind": thread["kind"],
           "role": role, "way": thread_set.WITH_HISTORY,
           "expects_answer": thread_set.follow_up_expectation(thread, role) == "answer",
           "expected_answer": thread["turns"][1]["expected_answer"], "sources": thread["turns"][1]["sources"],
           "restricted_phrases": [] if all(s in context["readable"][role] for s in thread["turns"][1]["sources"])
           else thread["turns"][1]["expected_answer"]}
    readable_chunks = context["readable_chunks"][role]
    observation = {
        # On the server, generation's outcome is only visible as answered or not.
        "generation_called": bool(served) or bool(verified),
        "parsed": True,
        "first_attempt_parsed": None,
        "proposed": verified,
        "verified": verified,
        "out_of_scope_chunk_ids": [c for c in served if c not in readable_chunks],
        "source_rank": None,
    }
    score = thread_set.score(run, observation)
    score["leaks"] += [leak for text in bodies for leak in leak_problems(text, context["forbidden"][role])]
    out["score"] = {key: score[key] for key in ("answered", "phrase_found", "expected_source_cited",
                                                 "expected_answer_match", "correct", "leaks")}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--threads", type=Path, default=DEFAULT_THREADS, help="the thread set (D-86)")
    parser.add_argument("--base-url", default=os.environ.get("KMP_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--dump-sha256", help="the snapshot's SHA-256; makes the run a recorded one")
    parser.add_argument("--out", type=Path, help="where the record goes (JSON); never overwritten")
    parser.add_argument("--unrecorded", action="store_true", help="not a measurement; still refuses kmp")
    parser.add_argument("--any-server", action="store_true",
                        help="accept a server that is not D-85's Waitress at 24 threads; recorded")
    arguments = parser.parse_args(argv)

    # 1. Recorded, or explicitly not.
    problems = measurement_record.recording_problems(
        dump_sha256=arguments.dump_sha256, unrecorded=arguments.unrecorded, out=arguments.out
    )
    if not problems and arguments.out is not None and arguments.out.exists():
        problems = [f"{arguments.out} exists, and a record is never overwritten"]
    if problems:
        return refuse(problems)
    recorded = not arguments.unrecorded

    django_setup()
    from django.conf import settings

    import check_flm
    import citation_harness as harness  # its gates' helpers; importing it asks nothing

    # 2. The thread set, and the threads this check runs.
    try:
        payload, threads, readable = harness.load_thread_set(arguments.threads)
    except (thread_set.ThreadSetError, OSError, ValueError, KeyError) as exc:
        return refuse([f"{arguments.threads}: {exc}"])
    by_id = {thread["id"]: thread for thread in threads}
    entries = thread_set.http_check_entries(payload)
    print(f"Thread set: {arguments.threads}; HTTP check threads: "
          + ", ".join(f"{e['thread']} as {e['role']}" for e in entries))

    # 3. Never kmp: this run writes, through the server, whether recorded or not.
    database = str(settings.DATABASES["default"].get("NAME", ""))
    try:
        measurement_record.refuse_protected_database(database)
    except measurement_record.RecordError as exc:
        return refuse([str(exc)])

    # 4. The accounts.
    problems = credential_problems(os.environ)
    if problems:
        return refuse(problems)

    # 5. FLM: this process embeds for the comparison, through the same FLM as the server.
    print("FLM gate: scripts/check_flm.py's checks (D-83)")
    checks = check_flm.run_checks(
        settings.FLM_BASE_URL, settings.FLM_API_KEY, settings.FLM_CHAT_MODEL, settings.FLM_EMBED_MODEL
    )
    if not check_flm.checks_passed(checks):
        failed = "; ".join(f"{name}: {status}" for name, status, _ in checks if status != "PASS")
        return refuse([f"scripts/check_flm.py's checks did not pass ({failed})"])
    version = check_flm.flm_version(settings.FLM_BASE_URL, settings.FLM_API_KEY)
    if recorded and version.problems():
        return refuse(version.problems())

    # 6. The corpus this process reads is exactly the manifest's.
    chunks = harness.load_corpus()
    manifest_items = json.loads((REPOSITORY_ROOT / payload["manifest"]).read_text(encoding="utf-8"))["items"]
    sources = harness.index_sources(chunks, manifest_items)
    mismatch = harness.corpus_problems(chunks, sources, manifest_items, settings.FLM_EMBED_MODEL)
    for problem in mismatch:
        print(f"CORPUS: {problem}")
    if mismatch and recorded:
        return refuse(["the indexed corpus is not exactly the manifest's; restore the snapshot "
                       "(docs/measurement-runbook.md)"])

    # 7. The server: observed, and refused only on evidence that it is not D-85's.
    server = server_record.observe(
        arguments.base_url, server_record.fetch_server_header(arguments.base_url.rstrip("/") + "/api/")
    )
    print(f"Server: {server_record.summary(server)}")
    contradictions = server_record.contradicts_d85(server)
    if contradictions and not arguments.any_server:
        return refuse([f"{c}; start it as `{server_record.D85_COMMAND}`, or pass --any-server"
                       for c in contradictions], ONE_GET_SENT)
    for warning in server_record.problems(server):
        print(f"WARNING: {warning}")

    try:
        record = measurement_record.run_record(
            dump_sha256=arguments.dump_sha256, database=database, flm=version.as_record()
        )
    except measurement_record.RecordError as exc:
        if recorded:
            return refuse([f"the run cannot be recorded: {exc}"], ONE_GET_SENT)
        record = {"commit_sha": None, "error": str(exc), "flm_version": version.as_record()}
    record.update({
        "recorded": recorded,
        "base_url": arguments.base_url,
        "server": server,
        "server_gate_waived": bool(contradictions and arguments.any_server),
        "thread_set": str(arguments.threads),
        "thread_set_sha256": thread_set.file_sha256(arguments.threads),
        "thread_set_status": payload.get("status"),
        "scoring_rule_version": payload["scoring_rule"]["version"],
        "minimum_ask_interval_seconds": MINIMUM_ASK_INTERVAL_SECONDS,
    })

    # 8. Sign in, then confirm the server serves this database, before anything is created.
    from django.contrib.auth import get_user_model

    from apps.documents.models import Document
    from apps.meetings.models import Meeting
    from ingest_objective02 import ApiSession

    sessions, users = {}, {}
    for role in sorted({entry["role"] for entry in entries} | {"Administrator"}):
        email, password = (os.environ[name] for name in CREDENTIALS[role])
        session, problem = sign_in(ApiSession, arguments.base_url, email, password, role)
        if problem:
            return refuse([problem], "Only the sign-in attempts reached the server; no thread was created.")
        sessions[role] = session
        users[role] = get_user_model().objects.get(email__iexact=email)
    administrator = sessions["Administrator"]
    _, documents, _, _ = administrator.request("GET", "/api/documents")
    _, meetings, _, _ = administrator.request("GET", "/api/meetings")
    served = {str(d.get("doc_id")) for d in documents or [] if isinstance(d, dict)}
    served |= {str(m.get("meeting_id")) for m in meetings or [] if isinstance(m, dict)}
    local = {str(pk) for pk in Document.objects.values_list("id", flat=True)}
    local |= {str(pk) for pk in Meeting.objects.values_list("id", flat=True)}
    problems = server_database_problems(served_ids=served, local_ids=local,
                                        base_url=arguments.base_url, database=database)
    if problems:
        return refuse(problems, NO_THREAD_CREATED)

    # What each role may not read, for the leak check (part 7e), and each chunk's item.
    forbidden, readable_chunks = {}, {}
    for role in sessions:
        readable_chunks[role] = {str(c.id) for c in chunks if harness.readable_by(c, role)}
        hidden = {str(c.source_id) for c in chunks} - {str(c.source_id) for c in chunks if harness.readable_by(c, role)}
        forbidden[role] = {source_id: sources.title_by_source.get(source_id, "") for source_id in hidden}
    context = {"item_by_chunk": sources.item_by_chunk, "readable": readable,
               "readable_chunks": readable_chunks, "forbidden": forbidden}

    # 9. The threads.
    pacer = Pacer(MINIMUM_ASK_INTERVAL_SECONDS)
    results = []
    for entry in entries:
        thread = by_id[entry["thread"]]
        print(f"\n[{thread['id']} as {entry['role']}] {thread['turns'][0]['question']} / "
              f"{thread['turns'][1]['question']}", flush=True)
        result = check_thread(entry, thread, sessions[entry["role"]], users[entry["role"]], pacer, context)
        results.append(result)
        print(f"  verdict : {result['verdict']}" + (f" ({result['problem']})" if result.get("problem") else ""))
        if "score" in result:
            score = result["score"]
            print(f"  turn 2  : answered {score['answered']}, match {score['expected_answer_match']}, "
                  f"correct {score['correct']}, leaks {len(score['leaks'])}")
        if result.get("throttled"):
            print("  a 429: the pacing or another client asking as this user is wrong; stopping here")
            break

    leaks = sum(len(r.get("score", {}).get("leaks", [])) for r in results)
    wired = sum(r["verdict"] == WIRED for r in results)
    summary = {"threads": len(entries), "checked": len(results), "wired": wired, "leaks": leaks,
               "gaps_between_asks_seconds": [round(g, 2) for g in pacer.gaps],
               "smallest_gap_seconds": round(min(pacer.gaps), 2) if pacer.gaps else None}
    print(f"\nWIRED {wired} of {len(entries)}; leaks {leaks} (must be 0); smallest gap between asks "
          f"{summary['smallest_gap_seconds']} s")
    if arguments.out:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_text(json.dumps({"record": record, "summary": summary, "threads": results},
                                            indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"record written to {arguments.out}")
    return 0 if wired == len(entries) and not leaks else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
