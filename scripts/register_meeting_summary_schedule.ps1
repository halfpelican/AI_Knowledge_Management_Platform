<#
.SYNOPSIS
Registers FR-16's hourly meeting-summary retry in Windows Task Scheduler (D-125, NFR-20).

.DESCRIPTION
NFR-20: a meeting whose AI summary failed must be "flagged for automatic retry". The flag is on the
summary's row; this script registers what does the retrying: `manage.py retry_meeting_summaries`,
run from this checkout with its own .venv and .env, every hour, for the current Windows user. It is
FR-19's pattern (register_knowledge_gap_schedule.ps1), because the stack has no task queue. Run it
once on the host, from the deployment worktree. Running it again replaces the task, which is how
the interval is changed.

Each run reclaims any summary a stopped server left Processing, then runs every queued summary
again, one at a time. A summary leaves the queue when it is Ready or after three queued runs have
failed. A run that finds the queue empty does nothing and exits 0; a run after which a summary is
still unavailable exits 1, so the task's last result shows it. Nothing is lost either way: a failed
run changes only its own row, and the transcript stays stored and searchable.

No password is asked for or stored, so the task runs while this user is logged on. A host that must
run it while logged off needs "Run whether user is logged on or not" set in Task Scheduler by its
owner, where Windows asks for the password; it is never written to a file.

.PARAMETER EveryMinutes
How often to run, in minutes. Default 60.

.PARAMETER LogDirectory
The folder meeting-summaries.log is appended to. Default: this checkout's logs folder.

.PARAMETER TaskName
The task's name in Task Scheduler. Default "KMP meeting summary retry".

.EXAMPLE
.\scripts\register_meeting_summary_schedule.ps1 -LogDirectory C:\kmp-demo\2026-11-01
#>
[CmdletBinding()]
param(
    [ValidateRange(5, 1440)]
    [int]$EveryMinutes = 60,
    [string]$LogDirectory = "",
    [string]$TaskName = "KMP meeting summary retry"
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
$log = Join-Path $LogDirectory "meeting-summaries.log"

# cmd.exe runs the command so that its output can be appended to the log. cmd strips the outer
# pair of quotes, leaving the quoted interpreter path and the quoted log path intact.
$arguments = "/c `"`"$python`" manage.py retry_meeting_summaries >> `"$log`" 2>&1`""
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arguments -WorkingDirectory $root
# One start, repeated without end: -RepetitionDuration is left out, which Task Scheduler reads as
# indefinitely. The first run is at the next whole minute.
$start = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
# A run missed while the machine was off starts when it is next on. A run is stopped ten minutes
# short of the next one, and Task Scheduler never starts a second while one is going, so two runs
# never overlap; a stopped run leaves its summary Processing, which a later run reclaims.
$limit = New-TimeSpan -Minutes ([Math]::Max(5, $EveryMinutes - 10))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit $limit -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "FR-16: retry queued meeting summaries (NFR-20, D-125)." -Force | Out-Null

Write-Output "Registered '$TaskName': every $EveryMinutes minute(s), in $root, appending to $log."
Write-Output "Run the queue now: Start-ScheduledTask -TaskName '$TaskName'"
Write-Output "Remove the task:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
