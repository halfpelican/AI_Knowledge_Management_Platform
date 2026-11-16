# FR-13's HTTP check on Haiku, 11 November 2026: the server, started fresh, as D-85's command.
#
# Runbook step 5, for the Voyage-indexed copy (docs/measurement-runbook.md, "A copy for another
# provider"). Every value is set in this shell, so nothing depends on what .env names:
#   - DATABASE_URL is .env's with only the database name swapped. It is never printed.
#   - MEDIA_ROOT is the copy's own media folder.
#   - AI_PROVIDER, EMBEDDING_DIMENSION and ANTHROPIC_MODEL name the configuration under test.
#   - DEBUG is False (D-87 decision 2: .env sets True, and only the shell overrides it).
#   - The four logs go outside the checkout.
# Before Waitress starts, server_settings.py writes the settings a process in this shell resolves
# to server_settings.txt beside this file, and refuses if one is not the value under test.
#
# Usage, from anywhere:
#   powershell -NoProfile -ExecutionPolicy Bypass -File corpus\objective-02\runs\2026-11-11\haiku-http-check\start_server.ps1

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here '..\..\..\..\..')).Path
$py = 'C:\Users\mozza\Documents\IT_Captone_Project_KMP\KMP_Prototype\KMP_Prototype\.venv\Scripts\python.exe'
$waitress = Join-Path (Split-Path $py) 'waitress-serve.exe'
$db = 'kmp_voyage_20261110'
$copyRoot = 'C:\kmp-measurement\2026-11-10-voyage'            # the copy's media, with its snapshot
$logs = 'C:\kmp-measurement\2026-11-11-haiku-draws\logs\http-check'
$command = 'waitress-serve --listen=127.0.0.1:8000 --threads=24 --max-request-body-size=54525952 config.wsgi:application'
Set-Location $repo

# Runbook step 0.4: nothing else on port 8000. Any socket row on the port refuses, whatever its state.
$rows = @(Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue)
if ($rows.Count -gt 0) {
    Write-Output "REFUSED: port 8000 already has $($rows.Count) socket row(s). Nothing was started."
    exit 2
}

$line = Get-Content (Join-Path $repo '.env') | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
$env:DATABASE_URL = (($line -replace '^DATABASE_URL=', '').Trim()) -replace '/[^/]+$', "/$db"
$env:MEDIA_ROOT = "$copyRoot\media"
$env:AI_PROVIDER = 'anthropic'
$env:EMBEDDING_DIMENSION = '1024'
$env:ANTHROPIC_MODEL = 'claude-haiku-5-5'
$env:DEBUG = 'False'
New-Item -ItemType Directory -Force $logs | Out-Null
$env:ERROR_LOG_PATH = "$logs\errors.log"
$env:AUDIT_LOG_PATH = "$logs\audit.log"
$env:WAITRESS_LOG_PATH = "$logs\waitress.log"
$env:ATTEMPTS_LOG_PATH = "$logs\attempts.log"

& $py (Join-Path $here 'server_settings.py') --out (Join-Path $here 'server_settings.txt') --command $command
if ($LASTEXITCODE -ne 0) { Write-Output 'REFUSED: the settings are not the ones under test. Nothing was started.'; exit 2 }

Write-Output "Starting: $command"
& $waitress --listen=127.0.0.1:8000 --threads=24 --max-request-body-size=54525952 config.wsgi:application
