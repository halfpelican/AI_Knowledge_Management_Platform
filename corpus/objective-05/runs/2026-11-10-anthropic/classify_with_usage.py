"""Objective 05 on the anthropic provider (10 November 2026): the shipped classify_documents, gated and costed.

Not a copy. ``manage.py classify_documents`` names no provider, so it runs unchanged, called
through ``call_command`` with the options the FLM run used (``--all``, ``--out``). This driver adds
only what an anthropic run needs around it, as the copies under
corpus/objective-05/runs/2026-11-10/dev-sweep-haiku/ do:

- **A provider gate**, checked after Django reads its settings and before any document is read:
  AI_PROVIDER anthropic, ANTHROPIC_MODEL claude-haiku-5-5 (D-121), VOYAGE_MODEL voyage-4,
  EMBEDDING_DIMENSION 1024, both keys present (their values are never printed), and the connected
  database is the one named by ``--database`` and not a protected one.
- **A tally of Claude's token usage** (D-113's spend rule), by a wrapper around
  ``AnthropicService._claude_once`` that counts each reply's ``prompt_tokens`` and
  ``completion_tokens`` and returns the reply unchanged. A call that raises (a 429, a refusal)
  returns no counts and is not billed by tokens. It is written to ``claude_usage.json`` beside the
  command's own record, priced at Haiku 5.5's $0.10 / $0.50 per million tokens in / out.

Usage, in PowerShell, with the run's DATABASE_URL, MEDIA_ROOT and log paths set in the shell::

    & $py corpus\\objective-05\\runs\\2026-11-10-anthropic\\classify_with_usage.py `
        --database kmp_obj0506_anthropic_20261110 `
        --out corpus\\objective-05\\runs\\2026-11-10-anthropic\\classify\\classify.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]  # corpus/objective-05/runs/<this folder>/<this file>
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

# The user's never-touch list for this work, and Postgres's own databases.
PROTECTED = frozenset({
    "kmp", "kmp_demo_20261101", "kmp_obj02_20261101", "kmp_obj0506_20261101",
    "kmp_voyage_20261110", "kmp_anthropic", "postgres", "template0", "template1",
})
EXPECTED = (
    ("AI_PROVIDER", "anthropic"),
    ("ANTHROPIC_MODEL", "claude-haiku-5-5"),
    ("VOYAGE_MODEL", "voyage-4"),
    ("EMBEDDING_DIMENSION", 1024),
)
USD_PER_MILLION_IN, USD_PER_MILLION_OUT = 0.10, 0.50  # Claude Haiku 5.5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", required=True, help="the database this run must be connected to")
    parser.add_argument("--out", type=Path, required=True, help="classify_documents' JSON record")
    arguments = parser.parse_args()
    usage_path = arguments.out.with_name("claude_usage.json")
    for path in (arguments.out, usage_path):
        if path.exists():
            print(f"REFUSED: {path} already exists; a record is never overwritten")
            return 2

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    database = str(settings.DATABASES["default"]["NAME"])
    problems = [f"settings.{name} is {getattr(settings, name)!r}, not {expected!r}"
                for name, expected in EXPECTED if getattr(settings, name) != expected]
    for key in ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY"):
        if not getattr(settings, key):
            problems.append(f"settings.{key} is empty")  # its value is never printed
    if database.lower() in PROTECTED:
        problems.append(f"the connected database {database} is protected")
    if database != arguments.database:
        problems.append(f"the connected database is {database}, not {arguments.database}")
    if problems:
        print("REFUSED: " + "; ".join(problems))
        return 2
    print(f"Provider gate: PASS (anthropic, claude-haiku-5-5, voyage-4 at 1024, both keys present; "
          f"database {database})")

    from apps.ai.anthropic import AnthropicService

    usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "replies_without_usage": 0}
    original_claude_once = AnthropicService._claude_once

    def counting_claude_once(self, *args, **kwargs):
        reply = original_claude_once(self, *args, **kwargs)
        usage["calls"] += 1
        if reply.prompt_tokens is None or reply.completion_tokens is None:
            usage["replies_without_usage"] += 1
        usage["input_tokens"] += reply.prompt_tokens or 0
        usage["output_tokens"] += reply.completion_tokens or 0
        return reply

    AnthropicService._claude_once = counting_claude_once
    started = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    try:
        call_command("classify_documents", all=True, out=arguments.out)
    finally:
        AnthropicService._claude_once = original_claude_once
        usage["estimated_usd"] = round((usage["input_tokens"] * USD_PER_MILLION_IN
                                        + usage["output_tokens"] * USD_PER_MILLION_OUT) / 1_000_000, 4)
        usage_path.parent.mkdir(parents=True, exist_ok=True)
        usage_path.write_text(json.dumps({
            "database": database,
            "configuration": {"ai_provider": settings.AI_PROVIDER, "chat_model": settings.ANTHROPIC_MODEL,
                              "embedding_model": settings.VOYAGE_MODEL,
                              "embedding_dimension": settings.EMBEDDING_DIMENSION},
            "started": started,
            "finished": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "prices_usd_per_million": {"input": USD_PER_MILLION_IN, "output": USD_PER_MILLION_OUT},
            "claude_usage": usage,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"Claude usage: {usage} (written to {usage_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
