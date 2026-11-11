"""What kmp_voyage_20261110 holds, read only: the corpus, and the rows earlier runs wrote through a server.

The harness's corpus gate checks the chunks against the manifest. This prints the rest, so the
write-up can say what the copy held before the draws and what the HTTP check added: the counts,
the chunks' recorded embedding model and dimension, each day's QueryLog rows, and whether the
two corpus accounts' password hashes are the ones this script saw before (a SHA-256 of each hash,
cut to 12 characters: enough to compare two readings, and nothing a password could be found
from).

It reads the database and writes nothing to it. It calls no provider. Usage, from anywhere:
    python state_check.py
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[4]  # corpus/objective-02/runs/2026-11-11/<this folder>
DATABASE = "kmp_voyage_20261110"
ACCOUNTS = ("corpus.admin@example.com", "corpus.employee@example.com")

for line in (REPOSITORY_ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        os.environ["DATABASE_URL"] = re.sub(r"/[^/]+$", f"/{DATABASE}", line.split("=", 1)[1].strip())
os.environ["AI_PROVIDER"] = "anthropic"
os.environ["EMBEDDING_DIMENSION"] = "1024"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
sys.path.insert(0, str(REPOSITORY_ROOT))

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.sessions.models import Session  # noqa: E402

from apps.documents.models import ContentChunk, Document  # noqa: E402
from apps.meetings.models import Meeting  # noqa: E402
from apps.retrieval.models import AnswerCitation, Conversation, QueryLog  # noqa: E402


def main() -> int:
    database = str(settings.DATABASES["default"]["NAME"])
    if database != DATABASE:
        raise SystemExit(f"refusing: connected to {database!r}, not {DATABASE!r}")
    print(f"{DATABASE}, read at {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
    chunks = Counter(ContentChunk.objects.values_list("embedding_model", "embedding_dimension"))
    print(f"documents        : {Document.objects.count()}")
    print(f"meetings         : {Meeting.objects.count()}")
    print(f"content chunks   : {sum(chunks.values())}  " + ", ".join(
        f"{count} as {model} at {dimension}" for (model, dimension), count in sorted(chunks.items())))
    print(f"conversations    : {Conversation.objects.count()}")
    print(f"query log rows   : {QueryLog.objects.count()}")
    by_day = Counter(stamp.astimezone().date().isoformat()
                     for stamp in QueryLog.objects.values_list("answered_at", flat=True))
    for day, count in sorted(by_day.items()):
        print(f"                   {count} answered on {day} (local date)")
    print(f"answer citations : {AnswerCitation.objects.count()}")
    print(f"sessions         : {Session.objects.count()}")
    User = get_user_model()
    print(f"accounts         : {User.objects.count()}")
    for email in ACCOUNTS:
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            print(f"                   {email}: NOT FOUND")
            continue
        mark = hashlib.sha256(user.password.encode("utf-8")).hexdigest()[:12]
        last = user.last_login.astimezone().isoformat(timespec="seconds") if user.last_login else "never"
        print(f"                   {email}: password-hash mark {mark}, usable {user.has_usable_password()}, "
              f"last login {last}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
