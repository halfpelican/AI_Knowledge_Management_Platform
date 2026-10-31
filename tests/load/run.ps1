<#
.SYNOPSIS
    Runs one k6 load test, only after scripts/check_flm.py has passed (D-83) and the server
    has been observed to be D-85's, with DEBUG off and restarted since the last run (D-87).

.DESCRIPTION
    In order, stopping at the first failure, before k6 is started:
      1. checks the arguments, LOAD_TEST_PASSWORD, the Waitress log, -ResultsDir, and that
         python, flm, k6 and the two scripts exist; -ServerThreads must be D-85's 24 unless
         -OverrideServerThreads is given;
      2. reads the Waitress version installed in -Python's venv, and refuses if Waitress is
         not installed there (D-85 decisions 2 and 4);
      3. runs `flm version`, and refuses anything but the pinned version (D-83 decision 1);
      4. runs scripts/check_flm.py with the venv's python, and stops unless it exits 0
         AND prints its "RESULT: PASS" line (D-83 decision 3);
      5. runs scripts/server_record.py preflight, which observes the server at -BaseUrl, and
         refuses unless (D-87 decisions 1 and 2):
           - the process listening on the port is Waitress with --threads=24 on its command
             line (no --threads is Waitress's default, 4), or with the count -ServerThreads
             states when -OverrideServerThreads is given;
           - its replies name Waitress in their Server header;
           - an unmatched /api/ path gets handler404's JSON 404, so DEBUG is off;
           - Waitress's log has a timestamped "Serving on" line for the port, no earlier than
             the listening process's own start;
           - that start is later than the end of the last run recorded in
             tests/load/results and -ResultsDir, so the server was restarted since;
      6. reads the commit with `git rev-parse HEAD`;
    then runs k6 from the repository root with the run's record as -e variables: the commit,
    the FLM version and the gate's result, the snapshot hash, and the server as OBSERVED
    (name, version, thread count, pid, DEBUG, start), with what was stated beside it.

    After k6 exits, it runs scripts/server_record.py finalise, which writes into
    tests/load/results/<test>_summary.json every pre-flight observation and Waitress's
    "Task queue depth" lines from the run's window (or that there were none), marks the run
    INVALID if Waitress started again during it or another process is listening at the end,
    and copies the summary to -ResultsDir.

    Exit code 2 means the run was refused and k6 was not started. Exit code 3 means k6 ran
    but its summary could not be given the observations (k6 wrote no summary for this run,
    or the merge failed): the run is not recorded. Any other code is k6's own, and k6's exit
    code does not carry the run's verdict: read the summary.

    Usage and run order: tests/load/README.md and docs/measurement-runbook.md.

.PARAMETER Test
    nfr08 (p90 at 5 users, Objective 03) or nfr09 (degradation at 20 users).

.PARAMETER DbDumpSha256
    The SHA-256 of the database snapshot the run starts from, 64 hex digits (D-84).
    Recorded as given; nothing here checks the database against it.

.PARAMETER Python
    The venv's python.exe. Default: .venv\Scripts\python.exe in this checkout. A
    second worktree has no .venv of its own, so pass the main checkout's. It runs
    check_flm.py and server_record.py, and the stated Waitress version is read from it.

.PARAMETER ServerThreads
    The --threads the operator started Waitress with. Default 24, D-85's value. It is the
    statement; the pre-flight observes the count from the listening process's command line
    and refuses unless it is 24, or, with -OverrideServerThreads, this count.

.PARAMETER OverrideServerThreads
    Accept a thread count other than 24. The run is then recorded at the observed count,
    which must equal -ServerThreads, and it is not D-85's measured run.

.PARAMETER BaseUrl
    The server, as http://host:port. Default http://127.0.0.1:8000, D-85's --listen. Passed
    to k6 as BASE_URL, and observed by the pre-flight. Only a server on this machine can be
    observed, so any other host is refused.

.PARAMETER WaitressLog
    Waitress's log file, the one the server writes because WAITRESS_LOG_PATH named it in
    the server's window (D-87 decision 3). Without it, $env:WAITRESS_LOG_PATH in this window
    is used; with neither, the run is refused. A relative path is read from the repository
    root, as the server reads it.

.PARAMETER ResultsDir
    The folder this run's evidence is kept in, beside the earlier runs': the runbook's run
    folder. The summary is copied there after the run. Every *.json in it, and in
    tests/load/results, counts as an earlier run's record for the restart check, so it must
    already exist.

.EXAMPLE
    .\tests\load\run.ps1 -Test nfr08 -DbDumpSha256 <64 hex digits> -ResultsDir $runs
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('nfr08', 'nfr09')]
    [string] $Test,

    [Parameter(Mandatory = $true)]
    [string] $DbDumpSha256,

    [string] $Python = '',

    # A string, not [int], so a bad value is refused here with exit 2 rather than
    # failing PowerShell's parameter binding with a different code.
    [string] $ServerThreads = '24',

    [switch] $OverrideServerThreads,

    [string] $BaseUrl = '',

    [string] $WaitressLog = '',

    [string] $ResultsDir = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# D-83 decision 1. A different version is a decision and a full re-index first,
# not an edit to this line.
$RequiredFlmVersion = 'v0.9.39'

# D-85 decisions 2 and 3: the measured run is served by Waitress with 24 threads.
# These are this script's statement; the pre-flight observes the server against them.
$ServerName = 'waitress'
$D85ServerThreads = 24
$D85BaseUrl = 'http://127.0.0.1:8000'

# config/settings.py reads the server's Waitress log path from this variable (D-87 decision 3).
$WaitressLogVariable = 'WAITRESS_LOG_PATH'

$ScriptFiles = @{ nfr08 = 'nfr08_query_p90.js'; nfr09 = 'nfr09_concurrency.js' }
$RefusedExitCode = 2
$NotRecordedExitCode = 3

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

function Get-UtcStamp {
    return (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ',
                                                  [Globalization.CultureInfo]::InvariantCulture)
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

$threadsText = $ServerThreads.Trim()
if ($threadsText -notmatch '^[1-9][0-9]{0,3}$') {
    Stop-Run ("-ServerThreads must be the --threads Waitress was started with, a whole number " +
              "such as $D85ServerThreads; got '$ServerThreads'.")
}
$threads = [int] $threadsText
if ($threads -ne $D85ServerThreads -and -not $OverrideServerThreads) {
    Stop-Run ("-ServerThreads is $threads, and D-85 measures at --threads=$D85ServerThreads. Restart " +
              "Waitress with --threads=$D85ServerThreads, or, for a run that is deliberately not " +
              'D-85''s, add -OverrideServerThreads.')
}

if ($BaseUrl -eq '') { $BaseUrl = $D85BaseUrl }
if ($BaseUrl -notmatch '^https?://[A-Za-z0-9.\-]+:[0-9]{1,5}$') {
    Stop-Run ("-BaseUrl must be http://host:port, with no path or trailing slash, such as " +
              "$D85BaseUrl; got '$BaseUrl'.")
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

# Waitress's log (D-87 decision 3): named here, or by the same variable the server reads.
if ($WaitressLog -ne '') {
    $waitressLogFrom = '-WaitressLog'
} elseif (-not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($WaitressLogVariable))) {
    $WaitressLog = [Environment]::GetEnvironmentVariable($WaitressLogVariable)
    $waitressLogFrom = "`$env:$WaitressLogVariable"
} else {
    Stop-Run ("no Waitress log is named. Set `$env:$WaitressLogVariable in this window to the path the " +
              "server's window set it to, or pass -WaitressLog. The run copies Waitress's queueing " +
              'from it, and reads the server''s start from it (D-87 decisions 1 and 3).')
}
if (-not [IO.Path]::IsPathRooted($WaitressLog)) {
    # The server resolves a relative path against its working folder, the repository root.
    $WaitressLog = Join-Path $repoRoot $WaitressLog
}
if (-not (Test-Path -LiteralPath $WaitressLog -PathType Leaf)) {
    Stop-Run ("there is no Waitress log at $WaitressLog (from $waitressLogFrom). Waitress writes it " +
              "from its first line, 'Serving on', when $WaitressLogVariable names it in the server's " +
              'window. Was the server started with it set to the same path (docs/measurement-runbook.md step 5)?')
}
$WaitressLog = (Resolve-Path -LiteralPath $WaitressLog).Path

$k6ResultsDir = Join-Path $repoRoot 'tests\load\results'
if ($ResultsDir -ne '') {
    if (-not (Test-Path -LiteralPath $ResultsDir -PathType Container)) {
        # Not created here: a mistyped folder would be empty, and an empty folder holds no
        # earlier run, which would pass the restart check on nothing.
        Stop-Run ("-ResultsDir $ResultsDir is not a folder. It must be the run folder that already " +
                  'holds the earlier runs'' records, which the restart check reads (D-87 decision 1).')
    }
    $ResultsDir = (Resolve-Path -LiteralPath $ResultsDir).Path
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
$serverRecordScript = Join-Path $repoRoot 'scripts\server_record.py'
if (-not (Test-Path -LiteralPath $serverRecordScript -PathType Leaf)) {
    Stop-Run "scripts\server_record.py is not in $repoRoot."
}

$flm = Find-Program 'flm'
if ($null -eq $flm) { Stop-Run 'flm is not on PATH, so its version cannot be recorded.' }
$git = Find-Program 'git'
if ($null -eq $git) { Stop-Run 'git is not on PATH, so the commit cannot be recorded.' }
$k6 = Find-Program 'k6'
if ($null -eq $k6) { Stop-Run 'k6 is not on PATH. Install k6 first (README.md, "Before every run").' }

# --- 2. The stated server: Waitress's version in -Python's venv (D-85) -----------------

$Python = (Resolve-Path -LiteralPath $Python).Path
Write-Step "Waitress's version, from $Python"
# -I: isolated, so PYTHONPATH and the user's site-packages cannot supply a waitress
# the venv does not have. This is the version stated beside the observed one: the
# pre-flight reads the server's own from the venv its command line runs from.
$waitress = Invoke-Native $Python @('-I', '-c', "import importlib.metadata as m; print(m.version('waitress'))")
$waitressText = ($waitress.Lines -join "`n").Trim()
if ($waitress.ExitCode -ne 0) {
    if ($waitressText -match 'PackageNotFoundError') {
        Stop-Run ("Waitress is not installed in the venv whose python is $Python. D-85 serves the " +
                  'measured run with Waitress (requirements.txt pins it): sync that venv with ' +
                  "uv pip sync --python $Python requirements.txt, start the server with " +
                  "waitress-serve, and run this again.")
    }
    Stop-Run "reading Waitress's version with $Python exited $($waitress.ExitCode): $waitressText"
}
if ($waitressText -notmatch '^\d+(\.\d+)+\S*$') {
    Stop-Run "could not read Waitress's version from $Python; it printed '$waitressText'."
}
$statedVersion = $waitressText
Write-Host "stated: $ServerName $statedVersion (installed in that venv), $threads threads (-ServerThreads)"
if ($threads -ne $D85ServerThreads) {
    Write-Host ("WARNING: -OverrideServerThreads: this run is recorded at $threads threads, not D-85's " +
                "$D85ServerThreads. It is not D-85's measured run.") -ForegroundColor Yellow
}

# --- 3. The FLM version (D-83 decision 1) ------------------------------------------

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

# --- 4. The gate: scripts/check_flm.py (D-83 decision 3) ---------------------------

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
$checkedAt = Get-UtcStamp
Write-Host "check_flm.py passed at $checkedAt"

# --- 5. The server, observed (D-87 decisions 1 and 2) ---------------------------------

Write-Step "scripts\server_record.py preflight, for $BaseUrl"
$stem = Join-Path ([IO.Path]::GetTempPath()) ("kmp-$Test-preflight-" + [guid]::NewGuid().ToString('N'))
$preflightFile = "$stem.json"
$preflightEnvFile = "$stem.env"
# --waitress-log-from with "=": its value can be "-WaitressLog", which argparse would
# otherwise read as an option of its own.
$preflightArgs = @('-I', $serverRecordScript, 'preflight', '--base-url', $BaseUrl,
                   '--waitress-log', $WaitressLog, "--waitress-log-from=$waitressLogFrom",
                   '--results-dir', $k6ResultsDir, '--threads-stated', "$threads",
                   '--out', $preflightFile, '--env-out', $preflightEnvFile)
if ($ResultsDir -ne '') { $preflightArgs += @('--results-dir', $ResultsDir) }
if ($OverrideServerThreads) { $preflightArgs += '--override-threads' }
$preflight = Invoke-Native $Python $preflightArgs -Echo
# As with check_flm.py, exit 0 alone is not trusted: it must also print its READY line,
# and write the values below, which are checked again here.
$readyLine = $preflight.Lines | Where-Object { $_ -match '^PREFLIGHT: READY\s*$' } | Select-Object -First 1
$refusedLine = $preflight.Lines | Where-Object { $_ -match '^PREFLIGHT: REFUSED\b' } | Select-Object -First 1
if ($preflight.ExitCode -ne 0 -or $null -eq $readyLine -or $null -ne $refusedLine) {
    Stop-Run ("scripts\server_record.py preflight exited $($preflight.ExitCode) without its READY line. " +
              'Its REFUSED lines above say what was observed (D-87 decision 2).')
}
if (-not (Test-Path -LiteralPath $preflightEnvFile -PathType Leaf) -or
    -not (Test-Path -LiteralPath $preflightFile -PathType Leaf)) {
    Stop-Run 'scripts\server_record.py preflight printed READY but wrote no record.'
}
$observed = @{}
foreach ($line in (Get-Content -LiteralPath $preflightEnvFile -Encoding UTF8)) {
    $at = $line.IndexOf('=')
    if ($at -gt 0) { $observed[$line.Substring(0, $at)] = $line.Substring($at + 1) }
}
function Get-Observed([string] $Name) {
    if ($observed.ContainsKey($Name)) { return $observed[$Name] }
    return ''
}
# The rule again, on the values that go to k6, so that a pre-flight that went wrong
# cannot pass them through.
$observedThreadsText = Get-Observed 'SERVER_THREADS'
if ((Get-Observed 'PREFLIGHT_READY') -ne 'yes') {
    Stop-Run 'the pre-flight record does not say READY.'
}
if ((Get-Observed 'SERVER') -ne $ServerName) {
    Stop-Run "the pre-flight observed the server as '$(Get-Observed 'SERVER')', not $ServerName."
}
if ($observedThreadsText -notmatch '^[1-9][0-9]{0,3}$') {
    Stop-Run "the pre-flight observed no thread count ('$observedThreadsText')."
}
$observedThreads = [int] $observedThreadsText
if ($observedThreads -ne $threads -or ($observedThreads -ne $D85ServerThreads -and -not $OverrideServerThreads)) {
    Stop-Run ("the pre-flight observed $observedThreads threads, and $threads is stated" +
              $(if ($OverrideServerThreads) { '.' } else { " with D-85's $D85ServerThreads required." }))
}
if ((Get-Observed 'SERVER_DEBUG') -ne 'off') {
    Stop-Run "the pre-flight observed DEBUG as '$(Get-Observed 'SERVER_DEBUG')', not off."
}
if ((Get-Observed 'SERVER_STARTED_AT') -eq '') {
    Stop-Run "the pre-flight read no start for the server from Waitress's log."
}
$observedVersion = Get-Observed 'SERVER_VERSION'
$observedVersionSource = Get-Observed 'SERVER_VERSION_SOURCE'
if ($observedVersion -notmatch '^\d+(\.\d+)+\S*$') {
    Stop-Run "the pre-flight read no version for the listening Waitress ('$observedVersion')."
}
if ($observedVersion -ne $statedVersion) {
    Write-Host ("WARNING: the listening Waitress is $observedVersion ($observedVersionSource), and " +
                "-Python's venv has $statedVersion. The observed one is recorded.") -ForegroundColor Yellow
}

# --- 6. The commit ---------------------------------------------------------------

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

# --- 7. k6 -----------------------------------------------------------------------

$k6Env = [ordered]@{
    GIT_SHA                  = $sha
    GIT_TRACKED_CHANGES      = $trackedChanges
    FLM_VERSION              = $flmVersion
    FLM_CHECK_PASSED_AT      = $checkedAt
    FLM_CHECK_URL            = $checkedUrl
    DB_DUMP_SHA256           = $dumpHash
    # Observed by the pre-flight (D-87 decision 2).
    SERVER                   = Get-Observed 'SERVER'
    SERVER_VERSION           = $observedVersion
    SERVER_VERSION_SOURCE    = $observedVersionSource
    SERVER_THREADS           = "$observedThreads"
    SERVER_THREADS_SOURCE    = Get-Observed 'SERVER_THREADS_SOURCE'
    SERVER_PID               = Get-Observed 'SERVER_PID'
    SERVER_DEBUG             = Get-Observed 'SERVER_DEBUG'
    SERVER_STARTED_AT        = Get-Observed 'SERVER_STARTED_AT'
    PREVIOUS_RUN_FILE        = Get-Observed 'PREVIOUS_RUN_FILE'
    PREVIOUS_RUN_ENDED_AT    = Get-Observed 'PREVIOUS_RUN_ENDED_AT'
    SERVER_OBSERVED_BY       = Get-Observed 'SERVER_OBSERVED_BY'
    # Stated, recorded beside the observed.
    SERVER_STATED            = $ServerName
    SERVER_THREADS_STATED    = "$threads"
    SERVER_VERSION_STATED    = $statedVersion
    SERVER_VERSION_READ_FROM = $Python
    WAITRESS_LOG             = $WaitressLog
    TEST_PASSWORD            = $password
    BASE_URL                 = $BaseUrl
}

$k6Args = @('run')
$shown = @('k6', 'run')
foreach ($name in $k6Env.Keys) {
    $value = "$($k6Env[$name])"
    if ($value.Contains('"')) {
        Stop-Run "the value for -e $name contains a double quote, which cannot be passed to k6 intact from Windows PowerShell 5.1."
    }
    if ($value.EndsWith('\')) {
        # A trailing backslash before the quote PowerShell adds would escape it.
        Stop-Run "the value for -e $name ends with a backslash, which cannot be passed to k6 intact: '$value'."
    }
    $k6Args += @('-e', "$name=$value")
    $shownValue = $(if ($name -eq 'TEST_PASSWORD') { '***' } else { $value })
    $shown += @('-e', "$name=$shownValue")
}
$k6Args += $scriptRelative
$shown += $scriptRelative

Write-Step 'k6'
Write-Host ($shown -join ' ')

# From the repository root, because the scripts write tests/load/results/...
# relative to the current directory.
Push-Location -LiteralPath $repoRoot
try {
    $windowStart = Get-UtcStamp
    $global:LASTEXITCODE = -1
    & $k6 @k6Args
    $k6Exit = $global:LASTEXITCODE
    $windowEnd = Get-UtcStamp
} finally {
    Pop-Location
}
Write-Host ''
Write-Host "k6 exited $k6Exit. The run's window: $windowStart to $windowEnd."

# --- 8. Waitress's log for the run's window, into the results (D-87 decision 3) -------

Write-Step "scripts\server_record.py finalise: Waitress's log for the run's window"
$summaryFile = Join-Path $k6ResultsDir "$($Test)_summary.json"
$finaliseArgs = @('-I', $serverRecordScript, 'finalise', '--preflight', $preflightFile,
                  '--summary', $summaryFile, '--window-start', $windowStart, '--window-end', $windowEnd)
if ($ResultsDir -ne '') { $finaliseArgs += @('--copy-to', $ResultsDir) }
$final = Invoke-Native $Python $finaliseArgs -Echo
$finalLine = $final.Lines | Where-Object { $_ -match '^FINALISED: ' } | Select-Object -First 1
if ($final.ExitCode -ne 0 -or $null -eq $finalLine) {
    Write-Host ''
    Write-Host ("NOT RECORDED: k6 ran, but scripts\server_record.py finalise exited $($final.ExitCode) " +
                'without adding the observations to the summary. This run is not a recorded run.') -ForegroundColor Red
    Write-Host "The pre-flight record is kept at $preflightFile." -ForegroundColor Red
    exit $NotRecordedExitCode
}
Remove-Item -LiteralPath $preflightFile, $preflightEnvFile -ErrorAction SilentlyContinue

$where = $(if ($ResultsDir -ne '') { "$summaryFile and $ResultsDir" } else { $summaryFile })
Write-Host ''
Write-Host "k6 exited $k6Exit. The verdict is in $where, not in the exit code."
exit $k6Exit
