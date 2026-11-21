"""Objective 02's sixty-second bound at twenty pages, on anthropic, with D-139's summary at upload (21 November 2026).

D-139 makes an upload summarise a document longer than CLASSIFICATION_INPUT_TOKENS in sections: one
request per section and a final one, where the upload made one classification request before. The
bound was timed at twenty pages on FLM only (../2026-11-10/ingestion-twenty-pages-flm/), with one
request. The user's decision of 21 November 2026: time it once on anthropic with D-139's code, on a
new scratch database.

It repeats that run's method, as its twenty-pages.md records it:

- **The cut:** pages 1 to 20 of D04, corpus/objective-02/documents/D04_records_management_handbook.pdf,
  cut with pypdf. Five copies, identical but for their PDF /Title, so each has its own content hash
  and none is refused 409 as a duplicate. The copies go to ``--copies-dir``, outside every checkout.
- **The upload:** each through POST /api/documents on the running server, with D04's department and
  audience, one after another, timed by scripts/ingest_objective02.py's own ApiSession: the
  wall-clock time of the synchronous request.
- **The account:** an Administrator made for this run by ``createsuperuser --noinput``, its password
  from the ``secrets`` module, held in this process only and never printed or written. Afterwards
  its password is made unusable (D-89), row kept.
- **Classification time** is read from the server's attempts log (ATTEMPTS_LOG_PATH, the same file
  for the server and this process): the lines each upload added, and the seconds they report.

**It refuses before making anything** unless the server answers /api/ with a 401, the connected
database is kmp_obj02_d139_20261121, the provider settings are the run's, and ``--out-dir`` holds
no record.

Usage, in PowerShell, with the run's environment set and the server started in its own window::

    & $py corpus\\objective-02\\runs\\2026-11-21-d139-twenty-pages\\time_twenty_pages.py `
        --base-url http://127.0.0.1:8011 --copies-dir C:\\kmp-measurement\\2026-11-21-obj02-d139\\copies `
        --out-dir corpus\\objective-02\\runs\\2026-11-21-d139-twenty-pages\\run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import string
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[3]  # corpus/objective-02/runs/<this folder>
for extra in (REPOSITORY_ROOT, REPOSITORY_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

EXPECTED_DATABASE = "kmp_obj02_d139_20261121"
PROTECTED = frozenset({
    "kmp", "kmp_demo_20261101", "kmp_obj02_20261101", "kmp_obj0506_20261101", "kmp_voyage_20261110",
    "kmp_anthropic", "kmp_alpha_20261113", "kmp_obj02_anthropic_20261110", "postgres", "template0", "template1",
})
EXPECTED_SETTINGS = (("AI_PROVIDER", "anthropic"), ("ANTHROPIC_MODEL", "claude-haiku-5-5"),
                     ("VOYAGE_MODEL", "voyage-4"), ("EMBEDDING_DIMENSION", 1024))
ADMIN_EMAIL, ADMIN_NAME = "twenty.pages.admin@example.com", "Twenty Pages Administrator"
SPECIALS = "!#%*+-=?@^_"  # no quote, backslash, dollar or backtick: nothing a shell could reinterpret
SOURCE = REPOSITORY_ROOT / "corpus" / "objective-02" / "documents" / "D04_records_management_handbook.pdf"
PAGE_BOUND, BOUND_SECONDS = 20, 60
DEPARTMENT, AUDIENCE = "Legal and Compliance", ("Employee", "Administrator")
ATTEMPT_LINE = re.compile(r"apps\.ai\.attempts (?P<step>.+?) attempt (?P<number>\d+) of (?P<of>\d+) "
                          r"(?P<outcome>\w+) after (?P<seconds>[\d.]+) s")


def new_password() -> str:
    """24 characters from a CSPRNG, with every class FR-01's complexity rule asks for."""
    pool = string.ascii_letters + string.digits + SPECIALS
    characters = [secrets.choice(string.ascii_uppercase), secrets.choice(string.ascii_lowercase),
                  secrets.choice(string.digits), secrets.choice(SPECIALS)]
    characters += [secrets.choice(pool) for _ in range(20)]
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def server_answers(base_url: str) -> str | None:
    """None if /api/ answers 401 (the server is up and refuses an anonymous caller), else why not."""
    try:
        urllib.request.urlopen(base_url.rstrip("/") + "/api/", timeout=10)
    except urllib.error.HTTPError as exc:
        return None if exc.code == 401 else f"/api/ answered {exc.code}, not 401"
    except OSError as exc:
        return f"nothing answered at {base_url} ({type(exc).__name__}): start the server first"
    return "/api/ answered 2xx to an anonymous caller, not 401"


def attempt_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []


def git(*arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=REPOSITORY_ROOT, capture_output=True, text=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--copies-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--copies", type=int, default=5)
    parser.add_argument("--label", default="run", help="goes into each copy's /Title and title")
    arguments = parser.parse_args()

    problem = server_answers(arguments.base_url)
    if problem:
        print(f"REFUSED: {problem}. Nothing was made.")
        return 2
    if arguments.out_dir.exists() and any(arguments.out_dir.iterdir()):
        print(f"REFUSED: {arguments.out_dir} already holds files; a record is never overwritten.")
        return 2
    copies_dir = arguments.copies_dir.resolve()
    if REPOSITORY_ROOT in copies_dir.parents or copies_dir == REPOSITORY_ROOT:
        print("REFUSED: --copies-dir is inside the checkout.")
        return 2
    attempts_log = Path(os.environ.get("ATTEMPTS_LOG_PATH", ""))
    if not os.environ.get("ATTEMPTS_LOG_PATH"):
        print("REFUSED: ATTEMPTS_LOG_PATH is not set; it must be the server's.")
        return 2

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.password_validation import validate_password
    from django.core.management import call_command

    import ingest_objective02 as ingest
    import pypdf
    from apps.core.constants import CLASSIFICATION_INPUT_TOKENS, MAXIMUM_SUMMARY_SECTIONS
    from apps.documents.models import ContentChunk, Document

    User = get_user_model()
    database = str(settings.DATABASES["default"]["NAME"])
    problems = [f"settings.{name} is {getattr(settings, name)!r}, not {value!r}"
                for name, value in EXPECTED_SETTINGS if getattr(settings, name) != value]
    for key in ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY"):
        if not getattr(settings, key, ""):
            problems.append(f"settings.{key} is empty")
    if database != EXPECTED_DATABASE or database.lower() in PROTECTED:
        problems.append(f"the connected database is {database!r}, not {EXPECTED_DATABASE!r}")
    if problems:
        print("REFUSED: " + "; ".join(problems) + ". Nothing was made.")
        return 2
    print(f"database {database}; provider anthropic, claude-haiku-5-5, voyage-4 at 1024")

    # The account: made once, by createsuperuser, with a password only this process holds.
    password = new_password()
    validate_password(password, user=User(email=ADMIN_EMAIL, name=ADMIN_NAME))
    existing = User.objects.filter(email=ADMIN_EMAIL).first()
    if existing is None:
        os.environ["DJANGO_SUPERUSER_PASSWORD"] = password
        try:
            call_command("createsuperuser", interactive=False, email=ADMIN_EMAIL, name=ADMIN_NAME)
        finally:
            del os.environ["DJANGO_SUPERUSER_PASSWORD"]
        print(f"{ADMIN_EMAIL} made by createsuperuser --noinput")
    else:
        existing.set_password(password)
        existing.save(update_fields=["password"])
        print(f"{ADMIN_EMAIL} was here from an earlier run of this driver; given a new password")
    admin = User.objects.get(email=ADMIN_EMAIL)

    try:
        # A 200 with this password shows the server reads this database.
        session = ingest.sign_in(arguments.base_url, ADMIN_EMAIL, password, "Administrator")
        print(f"the server signed in {ADMIN_EMAIL} (200, Administrator): it serves {database}")

        # The cut.
        copies_dir.mkdir(parents=True, exist_ok=True)
        source_bytes = SOURCE.read_bytes()
        reader = pypdf.PdfReader(str(SOURCE))
        copies = []
        for number in range(1, arguments.copies + 1):
            writer = pypdf.PdfWriter()
            for page in reader.pages[:PAGE_BOUND]:
                writer.add_page(page)
            writer.add_metadata({"/Title": f"D04 first {PAGE_BOUND} pages, {arguments.label} copy {number}"})
            path = copies_dir / f"D04_first_{PAGE_BOUND}_pages_{arguments.label}_copy{number}.pdf"
            with open(path, "wb") as handle:
                writer.write(handle)
            data = path.read_bytes()
            copies.append({"copy": number, "file": path.name, "bytes": len(data),
                           "sha256": hashlib.sha256(data).hexdigest(),
                           "pages": len(pypdf.PdfReader(str(path)).pages), "path": path})
        text = "\n".join(page.extract_text() or "" for page in reader.pages[:PAGE_BOUND])
        tokens = len(text.split())

        # The uploads, one after another.
        runs = []
        for copy in copies:
            before = len(attempt_lines(attempts_log))
            fields = [("title", f"Records Management Handbook, first {PAGE_BOUND} pages "
                                f"({arguments.label} copy {copy['copy']})"),
                      ("department", DEPARTMENT)]
            fields += [("visible_to_roles", role) for role in AUDIENCE]
            body, content_type = ingest.multipart(fields, "file", copy["file"], copy["path"].read_bytes(),
                                                  "application/pdf")
            started = datetime.now(timezone.utc).isoformat(timespec="seconds")
            status, response, seconds, note = session.request(
                "POST", "/api/documents", body=body, content_type=content_type)
            new_lines = attempt_lines(attempts_log)[before:]
            attempts = [m.groupdict() for m in map(ATTEMPT_LINE.search, new_lines) if m]
            response = response if isinstance(response, dict) else {}
            classification = response.get("classification") or {}
            document_id = response.get("doc_id")
            chunks = (ContentChunk.objects.filter(source_id=document_id).count()
                      if document_id and Document.objects.filter(pk=document_id).exists() else None)
            run = {
                "copy": copy["copy"], "started_utc": started, "http": status,
                "status": response.get("status"), "chunks": chunks,
                "total_seconds": round(seconds, 1),
                "classification_requests": len(attempts),
                "classification_attempts_not_first": sum(1 for a in attempts if a["number"] != "1"),
                "classification_outcomes": sorted({a["outcome"] for a in attempts}),
                "classification_steps": sorted({a["step"] for a in attempts}),
                "classification_seconds": round(sum(float(a["seconds"]) for a in attempts), 1),
                "classified": bool(classification),
                "summary_characters": len(classification.get("summary") or ""),
                "key_points": len(classification.get("key_points") or []),
                "summary_truncated": classification.get("summary_truncated"),
                "transport_note": note,
            }
            run["the_rest_seconds"] = round(run["total_seconds"] - run["classification_seconds"], 1)
            run["within_bound"] = status == 201 and seconds <= BOUND_SECONDS
            runs.append(run)
            print(f"copy {copy['copy']}: HTTP {status}, {run['status']}, {chunks} chunks, "
                  f"{run['total_seconds']} s total, {run['classification_requests']} classification "
                  f"request(s) in {run['classification_seconds']} s, summary {run['summary_characters']} "
                  f"characters, {run['key_points']} key point(s)")
    finally:
        # D-89: nobody can sign in as this account once the run ends.
        admin.set_unusable_password()
        admin.save(update_fields=["password"])
        print(f"{ADMIN_EMAIL}: password made unusable, row kept")

    for copy in copies:
        del copy["path"]
    record = {
        "what": (f"Objective 02's bound at twenty pages: the first {PAGE_BOUND} pages of D04, uploaded "
                 f"{arguments.copies} times through POST /api/documents, with D-139's classification and "
                 "summary at upload, on anthropic"),
        "bound_seconds": BOUND_SECONDS, "page_bound": PAGE_BOUND,
        "source": {"file": SOURCE.relative_to(REPOSITORY_ROOT).as_posix(),
                   "sha256": hashlib.sha256(source_bytes).hexdigest(), "pages": len(reader.pages)},
        "how_cut": (f"pypdf {pypdf.__version__}: pages 1-{PAGE_BOUND} of the source, one copy each with its "
                    "own /Title metadata, so each has its own content hash"),
        "cut_whitespace_tokens": tokens,
        "sections_expected": min(-(-tokens // CLASSIFICATION_INPUT_TOKENS), MAXIMUM_SUMMARY_SECTIONS),
        "copies": copies, "runs": runs,
        "all_within_bound": all(run["within_bound"] for run in runs),
        "slowest_seconds": max(run["total_seconds"] for run in runs),
        "fastest_seconds": min(run["total_seconds"] for run in runs),
        "base_url": arguments.base_url, "database": database,
        "configuration": {name: getattr(settings, name) for name, _ in EXPECTED_SETTINGS},
        "commit": git("rev-parse", "HEAD"),
        "uncommitted_tracked_files": [line[3:] for line in git("status", "--porcelain", "--untracked-files=no").splitlines()],
        "server": session.last_headers.get("server"),
    }
    arguments.out_dir.mkdir(parents=True, exist_ok=True)
    (arguments.out_dir / "results.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    verdict = "within the bound on every upload" if record["all_within_bound"] else "NOT within the bound on every upload"
    print(f"{verdict}: {record['fastest_seconds']} to {record['slowest_seconds']} s. "
          f"Record: {arguments.out_dir / 'results.json'}")
    return 0 if record["all_within_bound"] else 1


if __name__ == "__main__":
    sys.exit(main())
