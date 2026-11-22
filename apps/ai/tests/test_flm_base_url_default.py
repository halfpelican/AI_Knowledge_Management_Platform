"""The address FLM is looked for at is written in four places, and they must agree (D-142).

The port moved from 52625, FLM's own default, to 8625 on 22 September 2026, to leave a range
Windows reserves for Hyper-V. Three commits of that day moved it: 6d36036 in ``.env.example``, CI,
``README.md`` and ``docs/ai-provider.md``, f1c882d in ``CLAUDE.md`` and 7fc12db in
``scripts/check_flm.py``. None changed ``config/settings.py``'s default. So the default disagreed
with ``.env.example`` and with every document: an installation whose ``.env`` had no
``FLM_BASE_URL`` line looked for FLM on 52625, and not on the port the project documents.
The review of 22 November 2026 found it. These tests read the four places as text, because a
default is what applies when nothing is set, and a running test's settings have already been
through the environment (``conftest.py`` sets ``FLM_BASE_URL`` for every test).
"""
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DOCUMENTED = "http://127.0.0.1:8625/v1"


def read(*parts: str) -> str:
    return REPOSITORY_ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_the_settings_default_is_the_documented_address():
    match = re.search(r'^FLM_BASE_URL = env\.str\("FLM_BASE_URL", default="([^"]+)"\)$',
                      read("config", "settings.py"), re.MULTILINE)

    assert match is not None, "config/settings.py no longer reads FLM_BASE_URL this way"
    assert match.group(1) == DOCUMENTED


def test_the_example_settings_file_names_the_same_address():
    match = re.search(r"^FLM_BASE_URL=(\S+)$", read(".env.example"), re.MULTILINE)

    assert match is not None, ".env.example has no FLM_BASE_URL line"
    assert match.group(1) == DOCUMENTED


def test_the_flm_check_script_defaults_to_the_same_address():
    match = re.search(r'^DEFAULT_BASE_URL = "([^"]+)"$', read("scripts", "check_flm.py"), re.MULTILINE)

    assert match is not None, "scripts/check_flm.py has no DEFAULT_BASE_URL"
    assert match.group(1) == DOCUMENTED


def test_claude_md_section_4_names_the_same_address():
    text = read("CLAUDE.md")
    section_4 = text[text.index("\n## 4. "):text.index("\n## 5. ")]

    assert f"FLM_BASE_URL={DOCUMENTED}" in section_4


def test_no_file_that_configures_the_project_still_names_the_old_port():
    """52625 may be named where a document explains FLM's own default, never as a value in use."""
    for parts in (("config", "settings.py"), (".env.example",), ("scripts", "check_flm.py")):
        values = [line for line in read(*parts).splitlines()
                  if "52625" in line and not line.lstrip().startswith("#")]
        assert values == [], f"{'/'.join(parts)} still sets the old port: {values}"
