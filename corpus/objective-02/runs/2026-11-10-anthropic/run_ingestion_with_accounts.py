"""Objective 02 on anthropic: the run's two accounts and the ingestion, with passwords held in memory only.

docs/measurement-runbook.md steps 4, 6 and 7, adapted as PR #82's FLM re-time did them:

- **Step 4, the Administrator,** by ``manage.py createsuperuser --noinput``, called in this process
  with the password in this process's environment for that call only. No load-test accounts are
  made here; NFR-08 makes its own and retires them afterwards (D-89).
- **Step 6, the Employee,** through FR-01's own route, ``POST /api/auth/register``, on the running
  server.
- **Step 7, the ingestion:** this folder's ``ingest_objective02_anthropic.py``, as a child process.
  Only its environment carries the four ``KMP_CORPUS_*`` values.

**The passwords** come from the ``secrets`` module (a CSPRNG). They are checked against the
configured password validators, and never printed or written anywhere. When this process ends,
nobody can sign in as either account.

**The server's database.** A successful sign-in with these passwords can only happen on the
database this process created them in. So before anything is written through the server, this
process signs in through it as the new Administrator, which shows that the server is using the
run's database. The ingestion's own two sign-ins show it again.

**It refuses before making anything** unless:
- the server answers ``/api/`` with a 401;
- the connected database is the one named, and not a protected one;
- it holds no user yet;
- the provider settings are the run's.

Afterwards it prints, read-only, the models the server's rows record: each chunk's embedding model
and width, and each analysis's chat model.

Usage, in PowerShell, with the run's environment set and the server started in its own window::

    & $py corpus\\objective-02\\runs\\2026-11-10-anthropic\\run_ingestion_with_accounts.py `
        --output-dir corpus\\objective-02\\runs\\2026-11-10-anthropic\\ingestion
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import string
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[3]  # corpus/objective-02/runs/<this folder>
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
INGEST_COPY = HERE / "ingest_objective02_anthropic.py"

EXPECTED_DATABASE = "kmp_obj02_anthropic_20261110"
PROTECTED = frozenset({"kmp", "kmp_demo_20261101", "kmp_obj02_20261101", "kmp_obj0506_20261101",
                       "kmp_voyage_20261110", "kmp_anthropic", "postgres", "template0", "template1"})
EXPECTED_SETTINGS = (("AI_PROVIDER", "anthropic"), ("ANTHROPIC_MODEL", "claude-haiku-5-5"),
                     ("VOYAGE_MODEL", "voyage-4"), ("EMBEDDING_DIMENSION", 1024))
ADMIN_EMAIL, ADMIN_NAME = "corpus.admin@example.com", "Corpus Administrator"
EMPLOYEE_EMAIL, EMPLOYEE_NAME = "corpus.employee@example.com", "Corpus Employee"
SPECIALS = "!#%*+-=?@^_"  # no quote, backslash, dollar or backtick: nothing a shell could reinterpret


def run_database_url() -> str:
    """.env's DATABASE_URL with the database name swapped. Never printed."""
    for line in (REPOSITORY_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return re.sub(r"/[^/]+$", f"/{EXPECTED_DATABASE}", line.split("=", 1)[1].strip())
    raise SystemExit("no DATABASE_URL in .env")


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()

    problem = server_answers(arguments.base_url)
    if problem:
        print(f"REFUSED: {problem}. Nothing was made.")
        return 2

    os.environ["DATABASE_URL"] = run_database_url()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.password_validation import validate_password
    from django.core.management import call_command

    User = get_user_model()
    database = str(settings.DATABASES["default"]["NAME"])
    problems = [f"settings.{name} is {getattr(settings, name)!r}, not {value!r}"
                for name, value in EXPECTED_SETTINGS if getattr(settings, name) != value]
    if database != EXPECTED_DATABASE or database.lower() in PROTECTED:
        problems.append(f"the connected database is {database!r}, not {EXPECTED_DATABASE!r}")
    elif User.objects.exists():
        problems.append(f"{database} already holds {User.objects.count()} user(s); this run makes the first two")
    if problems:
        print("REFUSED: " + "; ".join(problems) + ". Nothing was made.")
        return 2
    print(f"database {database}: empty of users; provider anthropic, claude-haiku-5-5, voyage-4 at 1024")

    admin_password, employee_password = new_password(), new_password()
    validate_password(admin_password, user=User(email=ADMIN_EMAIL, name=ADMIN_NAME))
    validate_password(employee_password, user=User(email=EMPLOYEE_EMAIL, name=EMPLOYEE_NAME))

    # Step 4: createsuperuser --noinput reads the password from this variable, for this call only.
    os.environ["DJANGO_SUPERUSER_PASSWORD"] = admin_password
    try:
        call_command("createsuperuser", interactive=False, email=ADMIN_EMAIL, name=ADMIN_NAME)
    finally:
        del os.environ["DJANGO_SUPERUSER_PASSWORD"]
    admin = User.objects.select_related("role").get(email=ADMIN_EMAIL)
    print(f"step 4: {ADMIN_EMAIL} made by createsuperuser --noinput, role {admin.role.role_name}")

    # Before anything is written through the server: sign in through it as that Administrator.
    # The password exists only in this database, so a 200 shows the server reads this database.
    login = urllib.request.Request(
        arguments.base_url.rstrip("/") + "/api/auth/login",
        data=json.dumps({"email": ADMIN_EMAIL, "password": admin_password}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(login, timeout=30) as response:
            status, body = response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        status, body = exc.code, {}
    if status != 200 or body.get("role") != "Administrator":
        print(f"STOPPED: the server did not sign in {ADMIN_EMAIL} ({status}), so it is not serving "
              f"{database}. Only the Administrator was made, in {database}; nothing was sent through the server.")
        return 1
    print(f"the server signed in {ADMIN_EMAIL} (200, Administrator): it serves {database}")

    # Step 6: FR-01's own path, on the server.
    request = urllib.request.Request(
        arguments.base_url.rstrip("/") + "/api/auth/register",
        data=json.dumps({"name": EMPLOYEE_NAME, "email": EMPLOYEE_EMAIL, "password": employee_password}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, body = response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        status, body = exc.code, {}
    if status != 201 or body.get("role") != "Employee":
        print(f"STOPPED: registering {EMPLOYEE_EMAIL} answered {status}, role {body.get('role')!r}")
        return 1
    print(f"step 6: {EMPLOYEE_EMAIL} registered through POST /api/auth/register: 201, role Employee")

    # Step 7: the ingestion, with the credentials in the child's environment only.
    child_environment = dict(os.environ, PYTHONUNBUFFERED="1",
                             KMP_CORPUS_ADMIN_EMAIL=ADMIN_EMAIL, KMP_CORPUS_ADMIN_PASSWORD=admin_password,
                             KMP_CORPUS_EMPLOYEE_EMAIL=EMPLOYEE_EMAIL, KMP_CORPUS_EMPLOYEE_PASSWORD=employee_password)
    del admin_password, employee_password
    print(f"step 7: {INGEST_COPY.name} --output-dir {arguments.output_dir}", flush=True)
    code = subprocess.run([sys.executable, str(INGEST_COPY), "--base-url", arguments.base_url,
                           "--output-dir", str(arguments.output_dir)], env=child_environment).returncode
    del child_environment
    print(f"step 7 ended with exit code {code}")

    # Read-only: what the server's rows say it used.
    from apps.documents.models import ContentChunk, Document, DocumentAnalysis
    from apps.meetings.models import Meeting

    print("chunks by (source type, embedding model, width):",
          dict(Counter(ContentChunk.objects.values_list("source_type", "embedding_model", "embedding_dimension"))))
    print("document analyses by model:", dict(Counter(DocumentAnalysis.objects.values_list("model", flat=True))))
    print("documents by status:", dict(Counter(Document.objects.values_list("status", flat=True))))
    print("meetings by status:", dict(Counter(Meeting.objects.values_list("status", flat=True))))
    print("users:", User.objects.count())
    return code


if __name__ == "__main__":
    sys.exit(main())
