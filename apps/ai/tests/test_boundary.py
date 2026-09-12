"""CLAUDE.md section 4: no AI vendor SDK is imported outside apps/ai/."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AI_PACKAGE = ROOT / "apps" / "ai"
VENDOR_IMPORT = re.compile(r"^\s*(import|from)\s+(openai|anthropic|voyageai)\b", re.MULTILINE)


def python_files_outside_the_ai_package():
    for folder in ("apps", "config"):
        for path in (ROOT / folder).rglob("*.py"):
            if AI_PACKAGE not in path.parents:
                yield path
    yield ROOT / "conftest.py"
    yield ROOT / "manage.py"


def test_no_vendor_sdk_import_outside_apps_ai():
    offenders = [
        str(path.relative_to(ROOT))
        for path in python_files_outside_the_ai_package()
        if VENDOR_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"vendor SDK imported outside apps/ai: {offenders}"


def test_the_guard_sees_the_codebase():
    # A guard that scans nothing passes vacuously; make sure it found real files.
    scanned = list(python_files_outside_the_ai_package())
    assert ROOT / "config" / "settings.py" in scanned
    assert ROOT / "apps" / "accounts" / "models.py" in scanned
