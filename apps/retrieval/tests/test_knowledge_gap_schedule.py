"""FR-19's schedule is committed, daily, and stores no credential (D-107's note of 10 November 2026).

The requirements audit of 10 November found "on a scheduled basis" met only by a command nobody
had scheduled. The user decided on a daily run, registered on the host by a script. Registering it
is the host owner's step, so what the repository can hold, and these tests pin, is the script and
the runbook's instructions: the script runs the aggregation command from the checkout's own venv,
once a day, and never takes a password.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "register_knowledge_gap_schedule.ps1"
RUNBOOK = ROOT / "docs" / "alpha-deployment.md"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_schedule_runs_the_aggregation_command_from_the_checkouts_venv():
    text = script_text()
    assert "manage.py aggregate_knowledge_gaps" in text
    assert ".venv\\Scripts\\python.exe" in text


def test_the_schedule_is_daily():
    text = script_text()
    assert "New-ScheduledTaskTrigger -Daily" in text
    for other in ("-Once", "-Weekly", "-AtLogOn", "-AtStartup", "RepetitionInterval"):
        assert other not in text, other


def test_the_schedule_takes_no_password():
    """The standing rule: no password is asked for, written or stored by the project."""
    text = script_text().lower()
    for credential in ("-password", "get-credential", "securestring", "-userid"):
        assert credential not in text, credential


def test_the_runbook_says_how_to_register_it():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "register_knowledge_gap_schedule.ps1" in text
    assert "manage.py aggregate_knowledge_gaps" in text
