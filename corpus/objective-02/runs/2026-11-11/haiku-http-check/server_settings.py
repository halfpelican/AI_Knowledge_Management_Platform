"""The settings a process started from start_server.ps1's shell resolves. Names only, never a key or a URL.

start_server.ps1 runs this in the shell it then starts Waitress from, with the same environment,
so what this prints is what the server reads. The check's own record names the model the CHECK
process is configured with, and the attempt log does not name a model, so this file is the
evidence of the model the SERVER generated with. It reads settings and writes one text file.

Usage (by start_server.ps1): python server_settings.py --out server_settings.txt --command "<the server's command>"
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[4]  # corpus/objective-02/runs/2026-11-11/<this folder>
sys.path.insert(0, str(REPOSITORY_ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

EXPECTED = {
    "database": "kmp_voyage_20261110",
    "AI_PROVIDER": "anthropic",
    "ANTHROPIC_MODEL": "claude-haiku-5-5",
    "VOYAGE_MODEL": "voyage-4",
    "EMBEDDING_DIMENSION": 1024,
    "threshold": 0.2687,
    "partial-match floor": 0.2468,
    "DEBUG": False,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--command", required=True, help="the server's command line, as it will be started")
    arguments = parser.parse_args()

    import django

    django.setup()
    from django.conf import settings

    from apps.retrieval.partial_matches import partial_match_floor
    from apps.retrieval.ranking import relevance_threshold

    resolved = {
        "database": str(settings.DATABASES["default"]["NAME"]),
        "AI_PROVIDER": settings.AI_PROVIDER,
        "ANTHROPIC_MODEL": settings.ANTHROPIC_MODEL,
        "VOYAGE_MODEL": settings.VOYAGE_MODEL,
        "EMBEDDING_DIMENSION": settings.EMBEDDING_DIMENSION,
        "threshold": relevance_threshold(settings.VOYAGE_MODEL),
        "partial-match floor": partial_match_floor(settings.VOYAGE_MODEL),
        "DEBUG": settings.DEBUG,
    }
    lines = [
        "The settings a process started from start_server.ps1's shell resolves, read at "
        f"{datetime.now().astimezone().isoformat(timespec='seconds')}, just before Waitress was "
        "started from that shell:",
        "",
    ]
    lines += [f"{name:<20}: {value}" for name, value in resolved.items()]
    lines += [
        f"{'MEDIA_ROOT':<20}: {settings.MEDIA_ROOT}",
        f"{'keys present':<20}: Anthropic {bool(settings.ANTHROPIC_API_KEY)}, Voyage {bool(settings.VOYAGE_API_KEY)}",
        f"{'logs':<20}: {Path(os.environ.get('WAITRESS_LOG_PATH', '')).parent}",
        f"{'command':<20}: {arguments.command}",
    ]
    wrong = [f"{name} is {resolved[name]!r}, not {expected!r}" for name, expected in EXPECTED.items()
             if resolved[name] != expected]
    lines += [""] + ([f"REFUSED: {problem}" for problem in wrong] or ["Every value is the one under test."])
    text = "\n".join(lines) + "\n"
    arguments.out.write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    return 2 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
