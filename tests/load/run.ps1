<#
.SYNOPSIS
    Runs one k6 load test, and only after scripts/check_flm.py has passed (D-83).

.DESCRIPTION
    In order, stopping at the first failure, before k6 is started:
      1. checks the arguments, LOAD_TEST_PASSWORD, and that python, flm and k6 exist;
      2. runs `flm version`, and refuses anything but the pinned version (D-83 decision 1);
      3. runs scripts/check_flm.py with the venv's python, and stops unless it exits 0
         AND prints its "RESULT: PASS" line (D-83 decision 3);
      4. reads the commit with `git rev-parse HEAD`;
    then runs k6 from the repository root with -e GIT_SHA, -e FLM_VERSION and
    -e DB_DUMP_SHA256, plus the gate's result, which the scripts write into the
    results JSON.

    Exit code 2 means the run was refused and k6 was not started. Any other code is
    k6's own, and k6's exit code does not carry the run's verdict: read
    tests/load/results/<test>_summary.json.

    The server must be restarted before each run (D-82 rule 7, D-84 decision 3).
    This script cannot check that; a run on a server that was not restarted can hit
    a 429, which makes it INVALID.

    Usage and run order: tests/load/README.md.

.PARAMETER Test
    nfr08 (p90 at 5 users, Objective 03) or nfr09 (degradation at 20 users).

.PARAMETER DbDumpSha256
    The SHA-256 of the database snapshot the run starts from, 64 hex digits (D-84).
    Recorded as given; nothing here checks the database against it.

.PARAMETER Python
    The venv's python.exe. Default: .venv\Scripts\python.exe in this checkout. A
    second worktree has no .venv of its own, so pass the main checkout's.

.PARAMETER BaseUrl
    Passed to k6 as BASE_URL. Without it the scripts use http://localhost:8000.

.EXAMPLE
    .\tests\load\run.ps1 -Test nfr08 -DbDumpSha256 <64 hex digits>
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('nfr08', 'nfr09')]
    [string] $Test,

    [Parameter(Mandatory = $true)]
    [string] $DbDumpSha256,

    [string] $Python = '',

    [string] $BaseUrl = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# D-83 decision 1. A different version is a decision and a full re-index first,
# not an edit to this line.
$RequiredFlmVersion = 'v0.9.39'

$ScriptFiles = @{ nfr08 = 'nfr08_query_p90.js'; nfr09 = 'nfr09_concurrency.js' }
$RefusedExitCode = 2

function Stop-Run([string] $Message) {
    Write-Host ''
    Write-Host "REFUSED: $Message" -ForegroundColor Red
    Write-Host 'k6 was not started.' -ForegroundColor Red
    exit $RefusedExitCode
}

function Write-Step([string] $Message) {
    Write-Host ''
    Write-Host "== $Message" -ForegroundColor Cyan
}

# Runs a native program and returns its exit code and its output lines, stdout and
# stderr together. Under 'Stop', Windows PowerShell 5.1 turns a native program's
# redirected stderr into a terminating error, so the call runs under 'Continue'.
# The caller has already resolved $Exe, so a missing program cannot leave a stale
# $LASTEXITCODE behind: it is preset to -1 regardless.
function Invoke-Native([string] $Exe, [string[]] $Arguments, [switch] $Echo) {
    $global:LASTEXITCODE = -1
    $lines = & {
        $ErrorActionPreference = 'Continue'
        & $Exe @Arguments 2>&1
    } | ForEach-Object {
        $line = "$_"
        if ($Echo) { Write-Host $line }
        $line
    }
    $exitCode = $global:LASTEXITCODE
    # No output at all leaves $lines $null, and @($null) is one $null element.
    if ($null -eq $lines) { $lines = @() }
    return @{ ExitCode = $exitCode; Lines = @($lines) }
}

function Find-Program([string] $Name) {
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $command) { return $null }
    return $command.Source
}

# --- 1. Arguments and programs: cheap checks first, before the slow FLM check -----

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$scriptRelative = 'tests/load/' + $ScriptFiles[$Test]
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $scriptRelative) -PathType Leaf)) {
    Stop-Run "$scriptRelative is not in $repoRoot."
}

$dumpHash = $DbDumpSha256.Trim().ToLowerInvariant()
if ($dumpHash -notmatch '^[0-9a-f]{64}$') {
    Stop-Run ("-DbDumpSha256 must be the snapshot's SHA-256, 64 hex digits; got '$DbDumpSha256'. " +
              'In PowerShell: (Get-FileHash <dump file> -Algorithm SHA256).Hash')
}

$password = $env:LOAD_TEST_PASSWORD
if ([string]::IsNullOrEmpty($password)) {
    Stop-Run ('Set $env:LOAD_TEST_PASSWORD to the password the load-test accounts were created ' +
              'with (manage.py create_load_test_users).')
}
if ($password.Contains('"')) {
    # Windows PowerShell 5.1 does not escape a double quote inside an argument it
    # passes to a native program, so k6 would receive a different password.
    Stop-Run 'LOAD_TEST_PASSWORD contains a double quote, which cannot be passed to k6 intact from Windows PowerShell 5.1.'
}

if ($Python -eq '') {
    $Python = Join-Path $repoRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    # Never fall back to whatever `python` is on PATH: on this laptop that is an
    # interpreter without the project's environment.
    Stop-Run "the venv's python is not at $Python. Pass -Python <path to the venv's python.exe>."
}
$checkScript = Join-Path $repoRoot 'scripts\check_flm.py'
if (-not (Test-Path -LiteralPath $checkScript -PathType Leaf)) {
    Stop-Run "scripts\check_flm.py is not in $repoRoot."
}

$flm = Find-Program 'flm'
if ($null -eq $flm) { Stop-Run 'flm is not on PATH, so its version cannot be recorded.' }
$git = Find-Program 'git'
if ($null -eq $git) { Stop-Run 'git is not on PATH, so the commit cannot be recorded.' }
$k6 = Find-Program 'k6'
if ($null -eq $k6) { Stop-Run 'k6 is not on PATH. Install k6 first (README.md, "Before every run").' }

# --- 2. The FLM version (D-83 decision 1) ------------------------------------------

Write-Step 'flm version'
$version = Invoke-Native $flm @('version') -Echo
if ($version.ExitCode -ne 0) {
    Stop-Run "flm version exited $($version.ExitCode)."
}
$versionText = $version.Lines -join ' '
if ($versionText -notmatch '\bv(\d+\.\d+\.\d+\S*)') {
    Stop-Run "could not read a version from flm version's output: '$versionText'."
}
$flmVersion = 'v' + $Matches[1]
if ($flmVersion -ne $RequiredFlmVersion) {
    Stop-Run ("FLM is $flmVersion; the measurement runs need $RequiredFlmVersion (D-83 decision 1). " +
              'From v1.0.4 its embeddings are noise, and a build whose vectors differ from the ' +
              "snapshot's needs a full re-index first.")
}
Write-Host "FLM version: $flmVersion (the pinned version)"

# --- 3. The gate: scripts/check_flm.py (D-83 decision 3) ---------------------------

Write-Step "scripts\check_flm.py, with $Python"
Write-Host ('FLM_BASE_URL = ' + $(if ($env:FLM_BASE_URL) { $env:FLM_BASE_URL } else { "(not set: check_flm.py's default)" }))
# -u: unbuffered, so the checks print as they run rather than all at the end.
$check = Invoke-Native $Python @('-u', $checkScript) -Echo
if ($check.ExitCode -ne 0) {
    Stop-Run "scripts\check_flm.py exited $($check.ExitCode). FLM is not fit to measure (D-83 decision 3)."
}
# Exit 0 alone is not trusted: an interpreter that ran nothing also exits 0. The
# script prints this line only when every check passed.
$passLine = $check.Lines | Where-Object { $_ -match '^RESULT: PASS\b' } | Select-Object -First 1
$failLine = $check.Lines | Where-Object { $_ -match '^RESULT: FAIL\b' } | Select-Object -First 1
if ($null -eq $passLine -or $null -ne $failLine) {
    Stop-Run ('scripts\check_flm.py exited 0 but did not print "RESULT: PASS", so the check is ' +
              'treated as not passed. If its output format changed, change this test with it.')
}
$checkedUrl = ''
if ($passLine -match '\bagainst\s+(\S+?)\)?\s*$') { $checkedUrl = $Matches[1] }
$checkedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
Write-Host "check_flm.py passed at $checkedAt"

# --- 4. The commit ---------------------------------------------------------------

Write-Step 'git rev-parse HEAD'
$head = Invoke-Native $git @('-C', $repoRoot, 'rev-parse', 'HEAD')
$sha = ($head.Lines -join '').Trim()
if ($head.ExitCode -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') {
    Stop-Run "git rev-parse HEAD did not return a commit: '$sha'."
}
$status = Invoke-Native $git @('-C', $repoRoot, 'status', '--porcelain', '--untracked-files=no')
if ($status.ExitCode -ne 0) {
    Stop-Run "git status exited $($status.ExitCode)."
}
$changed = @($status.Lines | Where-Object { $_.Trim() -ne '' })
if ($changed.Count -gt 0) {
    $trackedChanges = 'present'
    Write-Host "WARNING: tracked files have uncommitted changes, so $sha does not fully name what is run:" -ForegroundColor Yellow
    $changed | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
} else {
    $trackedChanges = 'none'
}
Write-Host "commit: $sha"

# --- 5. k6 -----------------------------------------------------------------------

$k6Env = [ordered]@{
    GIT_SHA             = $sha
    GIT_TRACKED_CHANGES = $trackedChanges
    FLM_VERSION         = $flmVersion
    FLM_CHECK_PASSED_AT = $checkedAt
    FLM_CHECK_URL       = $checkedUrl
    DB_DUMP_SHA256      = $dumpHash
    TEST_PASSWORD       = $password
}
if ($BaseUrl -ne '') { $k6Env['BASE_URL'] = $BaseUrl }

$k6Args = @('run')
$shown = @('k6', 'run')
foreach ($name in $k6Env.Keys) {
    $k6Args += @('-e', "$name=$($k6Env[$name])")
    $value = $(if ($name -eq 'TEST_PASSWORD') { '***' } else { $k6Env[$name] })
    $shown += @('-e', "$name=$value")
}
$k6Args += $scriptRelative
$shown += $scriptRelative

Write-Step 'k6'
Write-Host 'Was the server restarted before this run? This script cannot tell (D-82 rule 7).' -ForegroundColor Yellow
Write-Host ($shown -join ' ')

# From the repository root, because the scripts write tests/load/results/...
# relative to the current directory.
Push-Location -LiteralPath $repoRoot
try {
    $global:LASTEXITCODE = -1
    & $k6 @k6Args
    $k6Exit = $global:LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ''
Write-Host "k6 exited $k6Exit. The verdict is in tests/load/results/$($Test)_summary.json, not in the exit code."
exit $k6Exit
