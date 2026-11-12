"""Run one Objective 04 set through FR-09 and FR-16, and record what the application stored (D-125).

Objective 04: "Implement AI-generated meeting summaries, and action items from ingested
transcripts", verified against "a reference set of ten transcripts". This script takes the
transcripts of one set in corpus/objective-04/manifest.json (``frozen`` or ``development``) down
the path a user's meeting takes: each is ingested through
``apps.ingestion.meetings.ingest_meeting_transcript`` with its attendees, which requests the
summary, and the summary then runs as it does on the server, through
``apps.meetings.summaries.run_summary``. Nothing is simulated, and this script writes no summary
or action item itself: the rows are the application's.

In process rather than over HTTP, as the other objectives' seeding is: the rows are identical and
no throttle, session or password is involved. ``SUMMARY_RUNNER`` is set to ``inline`` for this
process, so each summary runs here when its ingestion commits rather than in a thread that would
die with the script.

**Which database.** Whatever DATABASE_URL names; the name is printed first and ``kmp`` is refused
(D-84). Use a database made for the run. The roster's users (corpus/objective-04/roster.json) are
created if absent, with unusable passwords: nobody signs in as them, and "resolves to a user on
the system" means one of them.

**A second run on the same database.** A meeting of the set that is already there (same title and
date) is refused, so a set is not ingested twice by accident. ``--regenerate`` instead gives each
existing meeting of the set a new summary run and re-ingests nothing, which is how a prompt change
is tried on the development set.

**The record** (``run.json`` in ``--out-dir``): the database, provider and models, the commit and
any uncommitted tracked files, the SHA-256 of each transcript file, the token counts the provider
reported for every summarisation attempt and what they cost at the stated prices, and per meeting
what ``manage.py summarise_meetings`` records: the run, the summary's elements, and each action
item as stored. scripts/objective04_verify.py reads it.

Usage, in PowerShell::

    $env:DATABASE_URL = "<the measurement database's URL>"
    .venv\\Scripts\\python.exe scripts\\objective04_run.py --set development `
        --out-dir corpus\\objective-04\\runs\\<date>\\dev-1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
for entry in (str(SCRIPTS), str(REPOSITORY_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import measurement_record  # noqa: E402

OBJECTIVE = REPOSITORY_ROOT / "corpus" / "objective-04"
SETS = {"frozen": "frozen_set", "development": "development_set"}

# Anthropic's published first-party prices per million tokens, for prompts of up to 100,000
# tokens, as on 3 November 2026. A model not listed here gets no cost, rather than a guess.
# Voyage's embedding calls are billed separately and are not counted.
PRICES_PER_MILLION_TOKENS = {"claude-haiku-5-5": {"input": 0.10, "output": 0.50}}


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """What the reported tokens cost at the stated prices, or None for a model with none stated."""
    prices = PRICES_PER_MILLION_TOKENS.get(model)
    if prices is None:
        return None
    return round(
        prompt_tokens / 1_000_000 * prices["input"] + completion_tokens / 1_000_000 * prices["output"], 6
    )


def provider_record(settings) -> dict:
    """The configuration this result belongs to (D-113): a result measured on one does not carry over."""
    if settings.AI_PROVIDER == "anthropic":
        return {"ai_provider": "anthropic", "chat_model": settings.ANTHROPIC_MODEL,
                "embedding_model": settings.VOYAGE_MODEL}
    return {"ai_provider": settings.AI_PROVIDER, "chat_model": settings.FLM_CHAT_MODEL,
            "embedding_model": settings.FLM_EMBED_MODEL}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", required=True, choices=sorted(SETS), dest="set_name")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=OBJECTIVE / "manifest.json")
    parser.add_argument("--roster", type=Path, default=OBJECTIVE / "roster.json")
    parser.add_argument("--only", action="append", default=[], metavar="ID",
                        help="one transcript id of the set (repeatable); default: all of them")
    parser.add_argument("--regenerate", action="store_true",
                        help="give each existing meeting of the set a new summary run; ingest nothing")
    arguments = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import connection

    from apps.accounts.models import Role
    from apps.ai.attempt_log import ATTEMPT_LOGGER_NAME
    from apps.ingestion.meetings import ingest_meeting_transcript
    from apps.meetings.management.commands.summarise_meetings import SummarisationUsage, meeting_entry
    from apps.meetings.models import Meeting
    from apps.meetings.summaries import latest_run, request_summary, run_summary

    database = connection.settings_dict["NAME"]
    print(f"database: {database}")
    try:
        measurement_record.refuse_protected_database(database)
    except measurement_record.RecordError as exc:
        print(f"REFUSED: {exc}")
        return 2
    settings.SUMMARY_RUNNER = "inline"

    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    roster = json.loads(arguments.roster.read_text(encoding="utf-8"))
    items = manifest[SETS[arguments.set_name]]
    if arguments.only:
        unknown = sorted(set(arguments.only) - {item["id"] for item in items})
        if unknown:
            print(f"REFUSED: not in the {arguments.set_name} set: {unknown}")
            return 2
        items = [item for item in items if item["id"] in arguments.only]

    User = get_user_model()
    people = {}
    for person in roster["users"]:
        user = User.objects.filter(email=person["email"]).first()
        if user is None:
            user = User(email=person["email"], name=person["name"],
                        role=Role.objects.get(role_name=person["role"]))
            user.set_unusable_password()
            user.save()
        people[person["name"]] = user
    print(f"roster: {len(people)} user(s) present")

    record = {
        "objective": "Objective 04",
        "set": arguments.set_name,
        "mode": "regenerate" if arguments.regenerate else "ingest",
        "database": database,
        **provider_record(settings),
        "commit": None,
        "uncommitted_tracked_files": [],
        "started": datetime.now(timezone.utc).isoformat(),
        "finished": None,
        "usage": None,
        "meetings": [],
    }
    try:
        record["commit"] = measurement_record.git_commit_sha()
        record["uncommitted_tracked_files"] = measurement_record.git_tracked_changes()
    except measurement_record.RecordError as exc:
        record["commit_error"] = str(exc)

    usage = SummarisationUsage()
    attempts_logger = logging.getLogger(ATTEMPT_LOGGER_NAME)
    attempts_logger.addHandler(usage)
    try:
        for item in items:
            path = (arguments.manifest.parent / item["file"]).resolve()
            meeting_date = date.fromisoformat(item["meeting_date"])
            existing = Meeting.objects.filter(title=item["title"], meeting_date=meeting_date).first()
            started = time.perf_counter()
            if arguments.regenerate:
                if existing is None:
                    print(f"REFUSED: {item['id']} is not in this database; run without --regenerate first")
                    return 2
                meeting = existing
                summary, is_new = request_summary(meeting, start=False)
                if is_new:
                    run_summary(summary.pk, claim=summary.retry_runs)
            else:
                if existing is not None:
                    print(f"REFUSED: {item['id']} ({item['title']!r}) is already in this database; "
                          "pass --regenerate to give it a new summary run instead")
                    return 2
                missing = [name for name in item["attendees"] if name not in people]
                if missing:
                    print(f"REFUSED: {item['id']} names attendees who are not on the roster: {missing}")
                    return 2
                outcome = ingest_meeting_transcript(
                    title=item["title"],
                    meeting_date=meeting_date,
                    transcript_text=path.read_text(encoding="utf-8"),
                    visible_to_roles=item["visible_to_roles"],
                    attendees=[people[name] for name in item["attendees"]],
                )
                meeting = outcome.meeting
            seconds = time.perf_counter() - started
            run = latest_run(meeting)
            if run is None:
                print(f"{item['id']}: no summary was requested (the transcript is under the minimum)")
                record["meetings"].append({"set_id": item["id"], "id": str(meeting.pk),
                                           "title": meeting.title, "error": "too_short"})
                continue
            entry = {"set_id": item["id"], "transcript_sha256": file_sha256(path),
                     "meeting_status": meeting.status, **meeting_entry(meeting, run, seconds)}
            record["meetings"].append(entry)
            print(f"{item['id']}: {run.status}"
                  + (f" ({run.failure_reason})" if run.failure_reason else "")
                  + f", {len(entry.get('action_items', []))} action item(s), {seconds:.1f} s")
    finally:
        attempts_logger.removeHandler(usage)

    model = record["chat_model"]
    record["finished"] = datetime.now(timezone.utc).isoformat()
    record["usage"] = {
        "attempts": usage.attempts,
        "attempts_without_reported_tokens": usage.unreported,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "prices_per_million_tokens": PRICES_PER_MILLION_TOKENS.get(model),
        "cost_usd": cost_usd(model, usage.prompt_tokens, usage.completion_tokens),
        "not_counted": "embedding calls (billed by the embedding provider)",
    }
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    out = arguments.out_dir / "run.json"
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    ready = sum(1 for entry in record["meetings"] if entry.get("status") == "Ready")
    print(f"done: {ready} of {len(record['meetings'])} ready; {usage.attempts} summarisation attempt(s), "
          f"{usage.prompt_tokens} prompt + {usage.completion_tokens} completion tokens, "
          f"cost {record['usage']['cost_usd']} USD; record: {out}")
    return 0 if ready == len(record["meetings"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
