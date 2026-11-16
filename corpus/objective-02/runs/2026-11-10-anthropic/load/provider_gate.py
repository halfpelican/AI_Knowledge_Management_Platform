"""The provider gate for the copied run.ps1 (D-113), in place of `flm version` and scripts/check_flm.py.

FLM takes no part when the anthropic provider is measured, so the copied run.ps1 runs this instead.
It reads this window's Django settings, which the run's environment sets with the same block the
server's window ran with, and checks that:

- AI_PROVIDER is anthropic, ANTHROPIC_MODEL claude-haiku-5-5 (D-121), VOYAGE_MODEL voyage-4 and
  EMBEDDING_DIMENSION 1024;
- both keys are present (their values are never printed);
- the database is kmp_obj02_anthropic_20261110, and not a protected one;
- voyage-4's threshold and floor are D-120's 0.2687 and 0.2468.

Then it asks the provider itself, as check_flm.py asks FLM:
- ``AnthropicService.health()``, a model listing that spends no tokens;
- one Voyage embedding of a probe string, which must come back 1024 wide from voyage-4.

Prints ``PROVIDER GATE: PASS`` and exits 0, or ``PROVIDER GATE: REFUSED: ...`` and exits 2.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]  # corpus/objective-02/runs/<run>/load/<this file>
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

EXPECTED_DATABASE = "kmp_obj02_anthropic_20261110"
PROTECTED = frozenset({"kmp", "kmp_demo_20261101", "kmp_obj02_20261101", "kmp_obj0506_20261101",
                       "kmp_voyage_20261110", "kmp_anthropic", "postgres", "template0", "template1"})
EXPECTED_SETTINGS = (("AI_PROVIDER", "anthropic"), ("ANTHROPIC_MODEL", "claude-haiku-5-5"),
                     ("VOYAGE_MODEL", "voyage-4"), ("EMBEDDING_DIMENSION", 1024))
EXPECTED_THRESHOLD, EXPECTED_FLOOR = 0.2687, 0.2468  # D-120, for voyage-4
PROBE_TEXT = "embedding dimension probe"


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings

    from apps.ai import get_ai_service
    from apps.ai.base import ProviderUnavailable
    from apps.retrieval.partial_matches import partial_match_floor
    from apps.retrieval.ranking import relevance_threshold

    database = str(settings.DATABASES["default"]["NAME"])
    problems = [f"settings.{name} is {getattr(settings, name)!r}, not {value!r}"
                for name, value in EXPECTED_SETTINGS if getattr(settings, name) != value]
    for name in ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY"):
        if not getattr(settings, name):
            problems.append(f"settings.{name} is empty")  # the value itself is never printed
    if database.lower() in PROTECTED or database != EXPECTED_DATABASE:
        problems.append(f"the database is {database!r}, not {EXPECTED_DATABASE!r}")
    if relevance_threshold(settings.VOYAGE_MODEL) != EXPECTED_THRESHOLD:
        problems.append(f"voyage-4's threshold is {relevance_threshold(settings.VOYAGE_MODEL)}, not {EXPECTED_THRESHOLD}")
    if partial_match_floor(settings.VOYAGE_MODEL) != EXPECTED_FLOOR:
        problems.append(f"voyage-4's floor is {partial_match_floor(settings.VOYAGE_MODEL)}, not {EXPECTED_FLOOR}")
    print(f"configuration: {settings.AI_PROVIDER}, {settings.ANTHROPIC_MODEL}, {settings.VOYAGE_MODEL} at "
          f"{settings.EMBEDDING_DIMENSION}; database {database}")

    if not problems:
        service = get_ai_service()
        health = service.health()
        print(f"health: {'available' if health.available else 'NOT available'}")
        if not health.available:
            problems.append(f"the Anthropic API is not available: {health.detail}")
        try:
            result = service.embed([PROBE_TEXT])
            print(f"embedding probe: {result.model}, {result.dimension} wide")
            if result.model != "voyage-4" or result.dimension != 1024:
                problems.append(f"the probe came back from {result.model} at {result.dimension}, not voyage-4 at 1024")
        except ProviderUnavailable as exc:
            problems.append(f"Voyage did not embed the probe: {exc}")

    if problems:
        print("PROVIDER GATE: REFUSED: " + "; ".join(problems))
        return 2
    print("PROVIDER GATE: PASS (anthropic, claude-haiku-5-5, voyage-4 at 1024, both keys present, "
          f"D-120's values, database {database})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
