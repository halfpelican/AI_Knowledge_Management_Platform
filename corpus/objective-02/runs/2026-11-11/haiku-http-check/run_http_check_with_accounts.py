"""FR-13's HTTP check on Haiku: throwaway passwords on the two corpus accounts, the check, then the original hashes written back.

The check signs in as corpus.admin@example.com and corpus.employee@example.com, and nobody holds
their passwords. So, as ../../2026-11-10/voyage-http-check/voyage-http-check.md did on 10 November:

- **Before the check,** each account's password hash is read and kept in this process's memory. A
  throwaway password is made with the ``secrets`` module, checked against the password validators,
  and set. It is passed to the check in its environment (the four ``KMP_CORPUS_*`` variables) and
  nowhere else. It is never printed or written.
- **The check** is this folder's ``conversation_http_check_haiku.py``, run as a child process. Its
  console goes to ``http_check.txt`` as it is printed, and its record to ``http_check.json``.
- **Afterwards, whatever happened,** both original hashes are written back and read again. The
  throwaway passwords then no longer work, and neither does any session made with them: Django's
  session hash follows the password hash, and the API uses Django sessions (D-21).

It writes to kmp_voyage_20261110 only: the two password hashes, twice each. It refuses any other
database, and it refuses before touching anything unless a server answers at the base URL.

Usage, with the server started fresh by start_server.ps1:
    python run_http_check_with_accounts.py
"""

from __future__ import annotations

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
REPOSITORY_ROOT = HERE.parents[4]  # corpus/objective-02/runs/2026-11-11/<this folder>
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

EXPECTED_DATABASE = "kmp_voyage_20261110"
DUMP_SHA256 = "80ff46d482d7d36029060e4afa2646ee9f07683331d35dbdb17b97fb6fc0d1e4"  # the copy's snapshot
BASE_URL = "http://127.0.0.1:8000"
CHECK = HERE / "conversation_http_check_haiku.py"
RECORD = HERE / "http_check.json"
CONSOLE = HERE / "http_check.txt"
ACCOUNTS = {  # role: (email, the check's two variables)
    "Administrator": ("corpus.admin@example.com", "KMP_CORPUS_ADMIN_EMAIL", "KMP_CORPUS_ADMIN_PASSWORD"),
    "Employee": ("corpus.employee@example.com", "KMP_CORPUS_EMPLOYEE_EMAIL", "KMP_CORPUS_EMPLOYEE_PASSWORD"),
}
SPECIALS = "!#%*+-=?@^_"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%SZ")


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


def main() -> int:
    if RECORD.exists() or CONSOLE.exists():
        print(f"REFUSED: {RECORD.name} or {CONSOLE.name} exists, and a record is never overwritten. Nothing was changed.")
        return 2
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(BASE_URL + "/api/", timeout=10)
        print("REFUSED: /api/ answered an anonymous caller with 2xx, not 401. Nothing was changed.")
        return 2
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            print(f"REFUSED: /api/ answered {exc.code}, not 401. Nothing was changed.")
            return 2
    except OSError as exc:
        print(f"REFUSED: nothing answered at {BASE_URL} ({type(exc).__name__}): start the server first. Nothing was changed.")
        return 2

    os.environ["DATABASE_URL"] = run_database_url()
    os.environ["AI_PROVIDER"] = "anthropic"
    os.environ["EMBEDDING_DIMENSION"] = "1024"
    os.environ["ANTHROPIC_MODEL"] = "claude-haiku-5-5"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.password_validation import validate_password

    database = str(settings.DATABASES["default"]["NAME"])
    if database != EXPECTED_DATABASE:
        print(f"REFUSED: connected to {database!r}, not {EXPECTED_DATABASE!r}. Nothing was changed.")
        return 2
    User = get_user_model()
    users = {role: User.objects.filter(email__iexact=email).first() for role, (email, _, _) in ACCOUNTS.items()}
    missing = [ACCOUNTS[role][0] for role, user in users.items() if user is None]
    if missing:
        print(f"REFUSED: no account {', '.join(missing)} in {database}. Nothing was changed.")
        return 2
    originals = {role: user.password for role, user in users.items()}

    code = 2
    environment = dict(os.environ, PYTHONUNBUFFERED="1")
    try:
        for role, user in users.items():
            email, email_variable, password_variable = ACCOUNTS[role]
            password = new_password()
            validate_password(password, user=user)
            user.set_password(password)
            user.save(update_fields=["password"])
            environment[email_variable] = email
            environment[password_variable] = password
            del password
        print(f"throwaway passwords set on {len(users)} account(s) at {now()}", flush=True)

        command = [sys.executable, str(CHECK), "--dump-sha256", DUMP_SHA256, "--out", str(RECORD)]
        child = subprocess.Popen(command, cwd=str(REPOSITORY_ROOT), env=environment,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with CONSOLE.open("w", encoding="utf-8", newline="\n") as console:
            for raw in child.stdout:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                print(line, flush=True)
                console.write(line + "\n")
                console.flush()
        code = child.wait()
    finally:
        del environment
        restored = 0
        for role, user in users.items():
            user.password = originals[role]
            user.save(update_fields=["password"])
            restored += 1
        same = sum(1 for role, user in users.items()
                   if User.objects.get(pk=user.pk).password == originals[role])
        print(f"\noriginal password hashes written back on {restored} account(s) at {now()}; "
              f"{same} of {len(users)} read back as the original")
    print(f"the check ended with exit code {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
