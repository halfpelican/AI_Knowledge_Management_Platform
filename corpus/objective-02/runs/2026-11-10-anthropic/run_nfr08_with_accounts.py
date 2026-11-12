"""NFR-08 on anthropic: five load-test accounts with a throwaway password held in memory, the copied run.ps1, then the accounts retired.

D-89, and docs/measurement-runbook.md steps 4 and 11, on item 3's database
kmp_obj02_anthropic_20261110 (dump 6e514170).

**The accounts.** ``manage.py create_load_test_users --count 5 --i-know-this-is-local`` is called
in this process.
- ``LOAD_TEST_PASSWORD`` is set for that call and for the child below, and nowhere else.
- Five accounts, because NFR-08's five VUs log in as loadtest01 to loadtest05 (D-82 rule 1).
  NFR-09's twenty are not made.
- The password comes from the ``secrets`` module and is checked against the password validators.
  It holds no double quote, which run.ps1 refuses.
- It is never printed or written. k6 receives it the way run.ps1 passes it: an ``-e`` argument on
  k6's command line, for the length of the run.

**The run** is this folder's ``load/run.ps1``, a copy of tests/load/run.ps1 with a provider gate. It
gets ``-Test nfr08``, the dump hash, the venv's python, this run folder as ``-ResultsDir`` and the
run's Waitress log.

**One retry rule.** In this tool environment, ``Get-NetTCPConnection`` sometimes finds no listener
for a server that is serving (item 3's ``setup/`` observations show it both ways, minutes apart).
The pre-flight then refuses, because the listening process and its thread count were not observed.
When every refusal is of that kind, the copy is run again, up to three times in all. A server that
is truly down also fails the Server-header and DEBUG checks, which are made over HTTP, so it is
never retried. Any other refusal ends the run. Nothing is sent to k6 before the pre-flight passes.

**Afterwards, whatever happened,** the five accounts' passwords are made unusable and their rows
kept, as D-89 did on the FLM measurement database. Their QueryLog rows point at them with PROTECT.

Usage, in PowerShell, with the run's environment set and the server restarted in its own window::

    & $py corpus\\objective-02\\runs\\2026-11-10-anthropic\\run_nfr08_with_accounts.py
"""

from __future__ import annotations

import os
import re
import secrets
import string
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[3]  # corpus/objective-02/runs/<this folder>
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
RUN_COPY = HERE / "load" / "run.ps1"

EXPECTED_DATABASE = "kmp_obj02_anthropic_20261110"
DUMP_SHA256 = "6e514170055c685f32f839a22f3a3d2f7571e98ea69bb2b58150d770ec9fe6fc"  # item 3's snapshot
WAITRESS_LOG = r"C:\kmp-measurement\2026-11-10-obj02-anthropic\logs\waitress.log"
BASE_URL = "http://127.0.0.1:8000"
ACCOUNTS = 5  # NFR-08's five VUs (D-84 decision 3), one account each (D-82 rule 1)
ATTEMPTS = 3
# The pre-flight's words when the socket lookup finds no listener for a server that is answering:
# the process is then named from no command line, and its thread count is not observed.
FLAKES = ("is not observed (nothing is listening on port", "thread count was not observed")
SPECIALS = "!#%*+-=?@^_"  # no double quote (run.ps1 refuses one), backslash, dollar or backtick


def run_database_url() -> str:
    """.env's DATABASE_URL with the database name swapped. Never printed."""
    for line in (REPOSITORY_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return re.sub(r"/[^/]+$", f"/{EXPECTED_DATABASE}", line.split("=", 1)[1].strip())
    raise SystemExit("no DATABASE_URL in .env")


def new_password() -> str:
    pool = string.ascii_letters + string.digits + SPECIALS
    characters = [secrets.choice(string.ascii_uppercase), secrets.choice(string.ascii_lowercase),
                  secrets.choice(string.digits), secrets.choice(SPECIALS)]
    characters += [secrets.choice(pool) for _ in range(20)]
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def run_copy(environment: dict) -> tuple[int, list[str]]:
    """One run of the copied run.ps1, echoed line by line. Returns its exit code and its lines."""
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUN_COPY),
               "-Test", "nfr08", "-DbDumpSha256", DUMP_SHA256, "-Python", sys.executable,
               "-ResultsDir", str(HERE), "-WaitressLog", WAITRESS_LOG, "-BaseUrl", BASE_URL]
    child = subprocess.Popen(command, cwd=str(REPOSITORY_ROOT), env=environment,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = []
    for raw in child.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        print(line, flush=True)
        lines.append(line)
    return child.wait(), lines


def only_the_lookup_flake(lines: list[str]) -> bool:
    """True when every pre-flight refusal is the lookup's. A server that is truly down also fails
    the Server-header and DEBUG checks, which are made over HTTP, so it is never retried."""
    refusals = [line for line in lines if line.startswith("REFUSED: ") and "preflight exited" not in line]
    return bool(refusals) and all(any(flake in line for flake in FLAKES) for line in refusals)


def main() -> int:
    try:
        urllib.request.urlopen(BASE_URL + "/api/", timeout=10)
        print("REFUSED: /api/ answered an anonymous caller with 2xx, not 401. Nothing was made.")
        return 2
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            print(f"REFUSED: /api/ answered {exc.code}, not 401. Nothing was made.")
            return 2
    except OSError as exc:
        print(f"REFUSED: nothing answered at {BASE_URL} ({type(exc).__name__}): restart the server first. Nothing was made.")
        return 2

    os.environ["DATABASE_URL"] = run_database_url()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.password_validation import validate_password
    from django.core.management import call_command

    database = str(settings.DATABASES["default"]["NAME"])
    if database != EXPECTED_DATABASE:
        print(f"REFUSED: connected to {database!r}, not {EXPECTED_DATABASE!r}. Nothing was made.")
        return 2
    User = get_user_model()
    emails = [f"loadtest{number:02d}@example.com" for number in range(1, ACCOUNTS + 1)]

    password = new_password()
    validate_password(password, user=User(email=emails[0], name="Load Test 01"))
    code, attempt = 2, 0
    try:
        os.environ["LOAD_TEST_PASSWORD"] = password
        call_command("create_load_test_users", count=ACCOUNTS, i_know_this_is_local=True)
        environment = dict(os.environ, PYTHONUNBUFFERED="1")
        del os.environ["LOAD_TEST_PASSWORD"]
        del password
        while attempt < ATTEMPTS:
            attempt += 1
            print(f"\n=== the copied run.ps1, attempt {attempt} of {ATTEMPTS} ===", flush=True)
            code, lines = run_copy(environment)
            if code == 2 and only_the_lookup_flake(lines) and attempt < ATTEMPTS:
                print("The pre-flight refused only because the listener was not found; trying again in 10 s.", flush=True)
                time.sleep(10)
                continue
            break
        del environment
    finally:
        os.environ.pop("LOAD_TEST_PASSWORD", None)
        retired = 0
        for user in User.objects.filter(email__in=emails):
            user.set_unusable_password()
            user.save(update_fields=["password"])
            retired += 1
        usable = sum(1 for user in User.objects.filter(email__in=emails) if user.has_usable_password())
        print(f"\nD-89: {retired} load-test account(s) retired, rows kept; {usable} with a usable password")
    print(f"the copied run.ps1 ended with exit code {code} after {attempt} attempt(s)")
    return code


if __name__ == "__main__":
    sys.exit(main())
