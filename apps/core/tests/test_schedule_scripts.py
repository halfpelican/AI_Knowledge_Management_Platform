"""Both schedule scripts register a task that runs on battery (D-107's note of 15 November 2026).

Task Scheduler's defaults hold a task while the machine is on battery and stop one that is unplugged
mid-run. On 15 November 2026 the alpha's laptop was on battery, and both of its tasks sat queued with
no log written. The text test beside each script pins the two switches in its call. This test reads
the conditions from the settings object the script builds, so it shows what the switches do as well
as that they are there.

It never runs a script. PowerShell's own parser finds the statements that assign ``$limit`` and
``$settings``, and only those are evaluated, so nothing can be registered. (A first version ran the
script with ``Register-ScheduledTask`` replaced by a function, and the module's own command was
found first and registered a real task.) The test also checks that the registration passes that
``$settings``.

It needs Windows PowerShell and its ``ScheduledTasks`` module, so it is skipped anywhere else, CI's
Linux runner included.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ("register_knowledge_gap_schedule.ps1", "register_meeting_summary_schedule.ps1")
POWERSHELL = shutil.which("powershell.exe") if sys.platform == "win32" else None

SETTINGS_OF = r"""
param([string]$Script)
$ErrorActionPreference = 'Stop'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$assignments = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
    $node.Left.VariablePath.UserPath -in @('limit', 'settings')
}, $true))
$built = @($assignments | Where-Object { $_.Left.VariablePath.UserPath -eq 'settings' })
if ($built.Count -ne 1) { throw "Expected one assignment to `$settings, found $($built.Count)." }
$registrations = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -eq 'Register-ScheduledTask'
}, $true))
if ($registrations.Count -ne 1) { throw "Expected one Register-ScheduledTask, found $($registrations.Count)." }
if ($registrations[0].Extent.Text -notmatch '-Settings\s+\$settings\b') {
    throw 'Register-ScheduledTask is not passed $settings.'
}
$EveryMinutes = 60
foreach ($assignment in $assignments) { Invoke-Expression $assignment.Extent.Text }
$settings |
    Select-Object DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable |
    ConvertTo-Json -Compress
"""


def built_settings(name: str, folder: Path) -> dict:
    """The conditions of the settings object the script builds and registers."""
    reader = folder / "settings_of.ps1"
    reader.write_text(SETTINGS_OF, encoding="utf-8")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(reader), str(ROOT / "scripts" / name)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell's ScheduledTasks module")
@pytest.mark.parametrize("name", SCRIPTS)
def test_the_registered_task_runs_on_battery(name, tmp_path):
    settings = built_settings(name, tmp_path)
    assert settings["DisallowStartIfOnBatteries"] is False
    assert settings["StopIfGoingOnBatteries"] is False
    assert settings["StartWhenAvailable"] is True
