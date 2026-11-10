<#
.SYNOPSIS
Registers FR-19's daily knowledge-gap aggregation in Windows Task Scheduler (D-107's note of
10 November 2026).

.DESCRIPTION
FR-19 aggregates unanswered questions and zero-result searches "on a scheduled basis". By the
user's decision of 10 November 2026 that basis is once a day. This script registers a daily run of
`manage.py aggregate_knowledge_gaps` from this checkout, with its own .venv and .env, for the
current Windows user. Run it once on the host, from the deployment worktree. Running it again
replaces the task, which is how the time is changed.

No password is asked for or stored, so the task runs while this user is logged on. A host that must
run it while logged off needs "Run whether user is logged on or not" set in Task Scheduler by its
owner, where Windows asks for the password; it is never written to a file.

A run that cannot reach the AI provider exits 1 and changes nothing. The next run takes the rows it
missed, because each cycle's window starts at the last committed cycle (D-107).

.PARAMETER At
The time of day to run, 24-hour, local time. Default 02:00.

.PARAMETER LogDirectory
The folder knowledge-gaps.log is appended to. Default: this checkout's logs folder.

.PARAMETER TaskName
The task's name in Task Scheduler. Default "KMP knowledge-gap aggregation".

.EXAMPLE
.\scripts\register_knowledge_gap_schedule.ps1 -LogDirectory C:\kmp-demo\2026-11-01
#>
[CmdletBinding()]
param(
    [string]$At = "02:00",
    [string]$LogDirectory = "",
    [string]$TaskName = "KMP knowledge-gap aggregation"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
foreach ($required in @($python, (Join-Path $root "manage.py"), (Join-Path $root ".env"))) {
    if (-not (Test-Path $required)) {
        throw "Not found: $required. Run this from the deployment worktree, once its .venv and .env exist."
    }
}
if (-not $LogDirectory) {
    $LogDirectory = Join-Path $root "logs"
}
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$log = Join-Path $LogDirectory "knowledge-gaps.log"

# cmd.exe runs the command so that its output can be appended to the log. cmd strips the outer
# pair of quotes, leaving the quoted interpreter path and the quoted log path intact.
$arguments = "/c `"`"$python`" manage.py aggregate_knowledge_gaps >> `"$log`" 2>&1`""
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arguments -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
# A run missed while the machine was off starts when it is next on. Two hours bounds a run whose
# provider hangs; the cycle is one transaction, so a stopped run changes nothing.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "FR-19: one knowledge-gap aggregation cycle a day (D-107)." -Force | Out-Null

Write-Output "Registered '$TaskName': daily at $At, in $root, appending to $log."
Write-Output "Run one cycle now: Start-ScheduledTask -TaskName '$TaskName'"
Write-Output "Remove the task:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
