# Load tests: NFR-08 and NFR-09 (k6)

| File | What it is | Accounts |
|---|---|---|
| `run.ps1` | **How every run starts.** Refuses to start k6 unless `scripts/check_flm.py` passes and `scripts/server_record.py preflight` observes D-85's server: Waitress at 24 threads, `DEBUG` off, restarted since the last run. Records the commit, the FLM version, the snapshot hash and every observed value. After k6, copies Waitress's queueing in the run's window into the results (D-83, D-84, D-85, D-87). | |
| `nfr08_query_p90.js` | p90 of `POST /api/ask` over answered replies and 503s, each 503 a miss, 5 VUs sharing 25 asks (100 before 1 November 2026). Limit 4,000 ms. Objective 03's p90 (D-84 decision 3). | `loadtest01`–`loadtest05` |
| `nfr09_concurrency.js` | p90 of asks and uploads with 20 concurrent users, against a one-user baseline. At most 25% worse. | load phase `loadtest01`–`loadtest20`, baseline `loadtest21` |
| `common.js` | Logins, pacing, the ask request, the run record and the validity gate. | |

Every virtual user (VU) logs in its own Employee account, and VU *n* uses account *n* (D-82).
The baseline gets its own account, so its uploads have their own hourly budget. Both scripts are
paced so that no account goes over D-79's limits, and any 429 makes the run INVALID.

## Run order for item 6 (D-84, D-87)

The measurement database is a fresh one holding exactly Objective 02's corpus, with its own
`DATABASE_URL`, `MEDIA_ROOT`, `AUDIT_LOG_PATH`, `ERROR_LOG_PATH` and `WAITRESS_LOG_PATH`. It is
ingested and snapshotted before anything is measured. That part is not this folder's: the item 6
runbook (`docs/measurement-runbook.md`) covers it, and it is the authority on the order. These
steps start once the snapshot exists and its SHA-256 is recorded.

D-87 decision 1 settles the order: the thirty questions, NFR-08, FR-13's thread run, the HTTP
check, then NFR-09. Two of those are this folder's:

1. **The thirty questions run first, or the snapshot is restored first.** NFR-09 uploads a
   kitchen-roster document every round, and those uploads become retrieval candidates for the
   questions.
2. **Restart Waitress** ([The server](#the-server-d-85-d-87)), then run **NFR-08 at 5 users**
   through `run.ps1`. Five is fixed by D-84 decision 3, before the run, so leave `VUS` unset.
   On 1 November 2026 a single-user end-to-end baseline ran before the rerun, as its own result
   (`VUS=1`, `ITERATIONS=20`), because the 8.90 s baseline times generation alone
   (`corpus/objective-02/runs/2026-11-01/nfr08-runs.md`).
3. FR-13's thread run and the HTTP check come next (the runbook's step 12). The HTTP check goes
   through the server, so Waitress is restarted before it.
4. **Restart Waitress again**, then run **NFR-09** through `run.ps1`, last.
5. **After NFR-09 the database is no longer the snapshot.** It holds up to 1,210 `LoadTest`
   uploads. Restore the snapshot before measuring anything else on it, including a second NFR-08
   run, and pass the same hash.

`run.ps1` refuses a run whose server was not restarted after the last run recorded in
`tests/load/results` or in `-ResultsDir`, so pass the run folder as `-ResultsDir`. Then the
restart after the HTTP check is checked as well, because its `http_check.json` is in that folder.

## The server (D-85, D-87)

The measured run is served by Waitress with 24 threads, under `DEBUG=False`, writing its own log:

```powershell
$env:DEBUG = 'False'                                  # .env sets DEBUG=True; the shell's value wins
$env:WAITRESS_LOG_PATH = "$root\logs\waitress.log"    # beside errors.log (D-87 decision 3)
waitress-serve --listen=127.0.0.1:8000 --threads=24 --max-request-body-size=54525952 config.wsgi:application
```

- **Where it runs.** From the repository root, in its own PowerShell window, with the measurement
  database's environment set first (`docs/measurement-runbook.md` step 1: `DATABASE_URL`,
  `MEDIA_ROOT`, `AUDIT_LOG_PATH`, `ERROR_LOG_PATH`, `WAITRESS_LOG_PATH`, `DEBUG=False`).
  `waitress-serve.exe` is in the venv's `Scripts` folder. Without the venv activated, call it by
  that path: `.venv\Scripts\waitress-serve.exe`. In a second worktree, use the main checkout's.
- **`DEBUG=False` has to be set in the shell.** The repo's `.env` sets `DEBUG=True`, and a server
  started from a window without the override runs in debug. `run.ps1` refuses that run (below).
- **Restart it before each run through HTTP**: NFR-08, the HTTP check and NFR-09 (D-87 decision
  1). Ctrl+C in its window, then the same command again. Waitress runs one process, and the
  throttle counters and in-flight slots live in its memory (D-79), so stopping it empties them.
  Without a restart, an earlier run's logins, asks or uploads still count, and the run can hit
  a 429.
- **`--threads=24` is set explicitly.** Waitress's default is 4, which NFR-08's five users
  already exceed. 24 is NFR-09's 20 users plus 4 for everything else (D-85 decision 3).
- **`--max-request-body-size=54525952` caps any request body** (D-124), 2 MB over the 50 MB
  upload limit, where Waitress's default is 1 GB. No load-test request comes near it, and the
  pre-flight does not check it.
- **What `run.ps1` observes before k6 starts** (D-87 decision 2), with
  `scripts/server_record.py preflight`. It refuses unless each holds:
  - **Waitress, from the listening process.** The process listening on `-BaseUrl`'s port is
    looked up (`Get-NetTCPConnection`, `Win32_Process`), and its command line must start
    Waitress. A server named only by a header, or nothing listening, is refused.
    - **Windows can report a serving socket's state wrongly** (D-87's notes of 11 and 12 November
      2026), so the lookup does not rely on the Listen row alone. On every try it also reads
      netstat's LISTENING PIDs and the port's own socket rows (remote port 0), whatever state is
      reported.
    - **A second process on the port means nothing is taken,** readable or not, and so does a
      netstat or port-row lookup that could not be read. The Listen row is taken only when both
      were read and neither shows another process; otherwise a process is taken only when both
      were read, it alone holds the port, and its command line can be read. Two servers can listen
      on one address and port on Windows, and netstat shows both.
    - **It tries again every 10 s, for about a minute,** before it gives up. Each try is printed,
      and the pre-flight prints which lookup found the process (`found by`). When it gives up, its
      note says what it saw. With netstat or the port's rows unread, it says that whether anything
      holds the port is not known. Otherwise, having seen a process it could not take, it says so.
      It says that nothing is listening only when netstat and the port's rows were both read and
      neither saw a process.
  - **24 threads, from that command line.** A command line with no `--threads` reads as 4,
    Waitress's default, and is refused as 4, not as "unknown". With `-OverrideServerThreads`,
    the observed count must equal `-ServerThreads`.
  - **`Server: waitress`** on both replies it asks for.
  - **`DEBUG` off.** `GET /api/__preflight_not_a_route__` must come back as handler404's JSON
    404, `{"detail": "Not found."}`. Under `DEBUG`, Django serves its HTML debug page instead,
    which says `DEBUG = True`. Anything else, an HTML 400 for a disallowed `Host` included, is
    "not confirmed off" and refused.
  - **The server's start, from Waitress's log.** The last `Serving on` line for the port, with a
    timestamp, no earlier than the listening process's own start. One from before it means the
    log is not this server's (a different `WAITRESS_LOG_PATH` in the two windows), and is
    refused.
  - **Restarted since the last run.** That start must be later than the end of every run
    recorded in `tests/load/results` and `-ResultsDir`. A run's end is when its `*.json` was
    last written, or its `finished_at` if later.
- **What is recorded, and how it is known** (D-85 decision 4, D-87 decision 2). The results JSON
  keeps the observed values as `server`, `server_version`, `server_threads`, `server_pid`,
  `server_debug`, `server_started_at` and `previous_run`, and what was stated as
  `server_stated`. `server_sources` says where each came from:
  - **The server and the thread count** are read from the listening process's command line.
  - **The version** is the Waitress installed in the venv that command line runs from (its
    `Scripts\waitress-serve.exe`). Where no venv can be read from it, it is the one installed
    beside `-Python`, and the source says so. The version in `-Python`'s venv is the stated one.
  - The whole pre-flight record, command line included, is added as `server_preflight` after k6
    exits.
- **Also observed: the `Server` header at login.** Waitress names itself in a `Server`
  response header, `waitress`. Django's `runserver` sends `WSGIServer/0.2 CPython/…`. Every login
  in `setup()` keeps the header it came back with, and the JSON records them as
  `server_observed`. If any login came back with no header, or with a server whose name (the
  part before any `/`) is not `SERVER`, the run is **INVALID**, and `setup()` says so on the
  console straight after the logins, so the run can be stopped before it spends half an hour.
  This catches a server that changed between the pre-flight and the logins.
  - k6 hands `setup()`'s return value to `handleSummary()` as `data.setup_data`, and that is
    how the header reaches the record. If a k6 build ever leaves `setup_data` out, every run
    reads INVALID with the reason "k6 passed no setup_data to handleSummary()" rather than
    passing unchecked. No real k6 has run these scripts on this laptop yet, so that case has
    been simulated, not seen.

## Before every run

1. **Commit what you are measuring.** The results record the commit SHA, and a SHA names a
   commit, not uncommitted changes. `run.ps1` warns if tracked files have changes and records
   `uncommitted_tracked_changes: true`. Run the server from the same checkout. Nothing can check
   which commit the server is running.
2. **k6 is installed** and on `PATH`. `run.ps1` refuses without it.
3. **Create the accounts in the measurement database.** The command writes to whatever
   `DATABASE_URL` it sees, and a value set in the shell wins over `.env`. Without it set, the
   accounts land in `kmp`. Running the command again resets their passwords. A restored snapshot
   may not contain them, so run it again after a restore. The password comes from the
   environment and is never stored in the repo (D-82 rule 6).

   ```powershell
   $env:DATABASE_URL = '<the measurement database URL>'
   $env:LOAD_TEST_PASSWORD = '<a password that meets FR-01 rules>'
   .venv\Scripts\python.exe manage.py create_load_test_users --count 21
   ```

   This creates `loadtest01@example.com` … `loadtest21@example.com`, all Employees. With
   `DEBUG` off, as the Waitress alpha runs (D-64), the command refuses unless you also pass
   `--i-know-this-is-local`. The password must not contain a double quote: Windows PowerShell 5.1
   cannot pass one to k6 intact, so `run.ps1` refuses it.
4. **Waitress is installed in the venv, and restarted** with D-85's command, `DEBUG=False` and
   `WAITRESS_LOG_PATH` set in its window ([The server](#the-server-d-85-d-87)). Do this before
   *each* run through HTTP, including before the HTTP check between NFR-08 and NFR-09. `run.ps1`
   refuses a server it does not observe as Waitress at 24 threads with `DEBUG` off, or that
   started before the last run recorded in `tests/load/results` and `-ResultsDir` ended.
5. **This window names the same Waitress log as the server's.** Set `$env:WAITRESS_LOG_PATH` to
   the same path, as the runbook's step 1 block does, or pass `-WaitressLog`. With neither,
   `run.ps1` refuses.
6. **Do not log in from a browser on this machine while `setup()` runs.** The login limit is
   20 a minute per address, and the browser shares 127.0.0.1 with k6.
7. **FLM v0.9.39 is serving** (`flm serve gemma3:4b --embed 1`), and `FLM_BASE_URL` in this shell
   names the same FLM as the server's. `check_flm.py` reads the shell's environment, not `.env`.
   Both default to `http://127.0.0.1:8625/v1`.

## Running

It works from any directory; the paths below are from the repository root. It was tested in
Windows PowerShell 5.1, the laptop's own, and not in PowerShell 7. The laptop's `RemoteSigned`
policy runs it as it is.

```powershell
$env:LOAD_TEST_PASSWORD = '<the accounts password>'
$env:AI_PROVIDER = 'flm'; $env:FLM_CHAT_MODEL = 'gemma3:4b'   # recorded in the results, optional
$env:WAITRESS_LOG_PATH = '<the path the server window set>'   # the runbook's step 1 block sets it
$hash = (Get-FileHash <the snapshot dump file> -Algorithm SHA256).Hash

# restart Waitress (--threads=24, DEBUG=False), then:
.\tests\load\run.ps1 -Test nfr08 -DbDumpSha256 $hash -ResultsDir $runs

# the thread run, then restart Waitress and run the HTTP check (the runbook's step 12)

# restart Waitress (--threads=24, DEBUG=False), then:
.\tests\load\run.ps1 -Test nfr09 -DbDumpSha256 $hash -ResultsDir $runs
```

In a second worktree, which has no `.venv` of its own, add
`-Python <main checkout>\.venv\Scripts\python.exe`. `-ServerThreads` defaults to 24; pass it only
if Waitress was started with another count, and then `-OverrideServerThreads` too. `-BaseUrl`
defaults to `http://127.0.0.1:8000`, D-85's `--listen`, and must be a server on this machine.

`-ResultsDir` is the run folder: the summary is copied there, and every `*.json` in it counts as
an earlier run for the restart check. It must exist already. Without it, only
`tests/load/results` is read, which holds the k6 summaries but not the HTTP check's record.

NFR-08's floor alone makes it at least 140 s of asks, plus about 30 s of setup. Expect much
longer: one NPU answers the asks one at a time, so the run takes roughly the answered asks times
one generation. 80 answered asks at 8.9 s, the single-user p90, is about 12 minutes. That is an
estimate, not a measurement.

NFR-09 takes 32–37 minutes, because the load phase starts 20 minutes after setup ends whenever the
baseline finishes. `check_flm.py` runs before either. Its first chat call can include loading the
model, and it allows that call 180 s.

### What `run.ps1` does

It stops at the first failure, prints `REFUSED: <why>` and `k6 was not started`, and exits 2:

1. **The arguments.** `-DbDumpSha256` must be 64 hex digits. `-ServerThreads` must be a whole
   number, and 24 unless `-OverrideServerThreads` is given (D-85). `-BaseUrl` must be
   `http://host:port`. `LOAD_TEST_PASSWORD` must be set. A Waitress log must be named, by
   `-WaitressLog` or `$env:WAITRESS_LOG_PATH`, and exist. `-ResultsDir`, if given, must exist.
   The venv's python, `scripts/check_flm.py`, `scripts/server_record.py`, `flm`, `git` and `k6`
   must all exist. It never falls back to the `python` on `PATH`: on this laptop that is an
   interpreter without the project's environment.
2. **Waitress's version in `-Python`'s venv**, read with `importlib.metadata` in isolated mode
   (`-I`), so a `PYTHONPATH` cannot supply a Waitress the venv lacks. Refused if Waitress is not
   installed there (D-85). This is the stated version, recorded beside the observed one.
3. **`flm version`.** Anything but **v0.9.39** is refused (D-83 decision 1). From v1.0.4 the
   embeddings are noise, and a build that is sound but embeds differently would not match the
   snapshot's vectors, which `check_flm.py` cannot see. There is no override.
4. **`scripts/check_flm.py`**, with the venv's python. It must exit 0 *and* print its
   `RESULT: PASS` line. An exit code alone is not trusted, because an interpreter that ran
   nothing also exits 0. It is still the first check that reaches anything outside this
   window: everything before it is local.
5. **`scripts/server_record.py preflight`** (D-87 decisions 1 and 2). It sends two GETs, to
   `/api/` and to `/api/__preflight_not_a_route__`, and looks up the listening process. It
   refuses on any of the conditions in [The server](#the-server-d-85-d-87), each on its own
   `REFUSED:` line. Like `check_flm.py`, it must exit 0 *and* print `PREFLIGHT: READY`. Then
   `run.ps1` checks the values it wrote again itself: `waitress`, the thread count, `DEBUG off`
   and a server start. A broken pre-flight cannot pass them through alone; the wrapper
   scenarios show that each of the two layers refuses on its own.
6. **`git rev-parse HEAD`**, and `git status` for uncommitted changes to tracked files.

Then it runs k6 from the repository root, so the results land in `tests/load/results/`, with:

| `-e` variable | From |
|---|---|
| `GIT_SHA` | `git rev-parse HEAD` |
| `GIT_TRACKED_CHANGES` | `none` or `present`, from `git status` |
| `FLM_VERSION` | `flm version`, such as `v0.9.39` |
| `FLM_CHECK_PASSED_AT`, `FLM_CHECK_URL` | when `check_flm.py` passed, and the URL its `RESULT: PASS` line names |
| `DB_DUMP_SHA256` | `-DbDumpSha256`, in lower case |
| `SERVER`, `SERVER_THREADS`, `SERVER_THREADS_SOURCE`, `SERVER_PID` | observed: the listening process's command line |
| `SERVER_VERSION`, `SERVER_VERSION_SOURCE` | observed: the Waitress in the venv that command line runs from, and how it was found |
| `SERVER_DEBUG` | observed: `off` |
| `SERVER_STARTED_AT` | observed: the last `Serving on` line in Waitress's log |
| `PREVIOUS_RUN_FILE`, `PREVIOUS_RUN_ENDED_AT` | the latest run record in the results folders, or `none` |
| `SERVER_OBSERVED_BY` | `scripts/server_record.py preflight, run by tests/load/run.ps1` |
| `SERVER_STATED`, `SERVER_THREADS_STATED`, `SERVER_VERSION_STATED`, `SERVER_VERSION_READ_FROM` | stated: `waitress`, `-ServerThreads`, and the Waitress in `-Python`'s venv, with that python |
| `WAITRESS_LOG` | the Waitress log's path |
| `TEST_PASSWORD` | `$env:LOAD_TEST_PASSWORD`. The printed command shows `***` |
| `BASE_URL` | `-BaseUrl`, default `http://127.0.0.1:8000` |

A value with a double quote, or ending in a backslash, cannot reach k6 intact from Windows
PowerShell 5.1, and is refused.

**After k6 exits**, `scripts/server_record.py finalise` reads Waitress's log again (D-87
decision 3). It writes into `tests/load/results/<test>_summary.json`:

- `waitress_log`: the run's window (from just before k6 started to just after it exited), every
  `Task queue depth` line timestamped inside it, the deepest, and how many fell before or after
  it. Lines with no timestamp are kept apart, not placed. With none inside the window,
  `queue_depth` reads `none in the run's window`.
- `server_at_end`: the process listening when the run ended, whether it is the one observed
  before it, and which lookup found it (`found_by`, `lookup`).
- `server_preflight`: the whole pre-flight record, command line, DEBUG probe and refusals
  included.

It marks the run **INVALID** if a `Serving on` line for the port falls inside the window (the
server started again during the run), or if another process, or none, is listening at the end.
With `-ResultsDir`, it copies the summary there.

**Exit codes.** 2: refused, k6 not started. 3: k6 ran, but finalise found no summary from this
run (its `finished_at` is outside the window, or there is no file) or could not write it. The
run is then not recorded, and an older summary is left untouched. Any other code is k6's own. It
does not carry the verdict (see below).

### Running k6 without `run.ps1`

Without `run.ps1`, the scripts still refuse to start unless `GIT_SHA`, `FLM_VERSION`,
`DB_DUMP_SHA256`, `SERVER`, `SERVER_VERSION` and `SERVER_THREADS` are given, so a run cannot go
unrecorded. Without the gate's record, though, the run is **INVALID**, because nothing shows
`check_flm.py` passed. Without `SERVER_OBSERVED_BY` it is INVALID a second time, because nothing
observed the server, confirmed `DEBUG` off or checked the restart (D-87 decision 2). Use this only
to debug the scripts.

| `-e` variable | Required | Meaning |
|---|---|---|
| `TEST_PASSWORD` | yes | The accounts' password. It must equal `LOAD_TEST_PASSWORD`. |
| `GIT_SHA` | yes | The commit under test, 7–40 hex digits. |
| `FLM_VERSION` | yes | As `flm version` prints it, with the `v`: `v0.9.39`. |
| `DB_DUMP_SHA256` | yes | The snapshot's SHA-256, 64 hex digits. |
| `SERVER` | yes | The server's name, `waitress` for D-85's run. |
| `SERVER_VERSION` | yes | Its version, such as `3.0.2`. Recorded as passed. |
| `SERVER_THREADS` | yes | The `--threads` it was started with, a whole number. Recorded as passed, "NOT observed". |
| `FLM_CHECK_PASSED_AT`, `FLM_CHECK_URL`, `GIT_TRACKED_CHANGES`, `SERVER_VERSION_READ_FROM` | set by `run.ps1` | Without `FLM_CHECK_PASSED_AT` the run is INVALID. |
| `SERVER_OBSERVED_BY`, `SERVER_DEBUG` and the rest of the observed and stated values above | set by `run.ps1` | Without `SERVER_OBSERVED_BY` the run is INVALID; with it, so is any `SERVER_DEBUG` but `off`. |
| `AI_PROVIDER`, `FLM_CHAT_MODEL` | no | Recorded in the results, `not recorded` if absent. k6 also reads them from the shell's environment. |
| `BASE_URL` | no | Default `http://localhost:8000`. `run.ps1` always passes it. |
| `TEST_EMAIL_PREFIX`, `TEST_EMAIL_DOMAIN` | no | Defaults `loadtest` and `example.com`, which give `loadtest01@example.com`. The command only creates that scheme, so change these only for accounts made some other way. |
| `VUS`, `ITERATIONS` | no | NFR-08 only, defaults 5 and 25. VU *n* needs account *n*. Objective 03 is 5 VUs (D-84). |
| `BASELINE_ITERATIONS` | no | NFR-09 only, default 50, at most 60 (the baseline account's uploads in an hour). |

`TEST_EMAIL`, `GIT_COMMIT` and `ROLE` are no longer read. The first two make the scripts refuse to
start, with a message saying what replaced them. The role is checked at login instead: every
account must log in as an Employee, or `setup()` stops.

## Pacing, and why each number is what it is

DRF's throttle is a sliding window. It stamps a request when the view runs, which is after k6 sent
it. So spacing the *sends* W/N apart is not enough. If the first request of a window is stamped
later than the (N+1)th, the (N+1)th lands inside the window and is a 429. Because a VU sends
nothing until its previous reply is back, a start-to-start spacing of at least **W/(N−1)** keeps
any N+1 consecutive requests more than W apart at the server, however late any one of them is
stamped (`common.js`, `minimumSpacingSeconds`). Each script checks its numbers against this when
it loads, and refuses to start if one is short.

**The bound does not depend on the thread count**, so D-85's 24 threads change none of the numbers
below. This section was first written for Waitress's default of 4, where five or twenty VUs meant
requests waiting for a thread and stamps seconds late. At 24 threads, with at most 20 VUs, no
request waits for a thread. A stamp is still late by the time Waitress takes to read the whole
request before handing it to a thread, and by the middleware and session lookup before the view.
That should be milliseconds, though nobody has measured it, and it differs between requests. Any
difference is enough at W/N: in the Node harness's model, stamp delays of up to 20 ms already
gave 429s at a 6 s floor, and delays of up to 5 ms did not. 7 s gave none at delays of up to 1 s.

| What | Limit | Needed | Used | Result |
|---|---|---|---|---|
| Logins in `setup()`, 127.0.0.1 | 20/min per address (D-26) | ≥ 60/19 = 3.16 s | 3.5 s | 21 logins span 70 s; any 21 consecutive are > 66.5 s apart |
| NFR-08 iteration floor | 10 asks/min per user (D-79) | ≥ 60/9 = 6.67 s | 7 s | any 11 asks > 63 s apart |
| NFR-09 round floor, both phases | 10 asks/min; 60 uploads/hour per user | ≥ 6.67 s for asks; ≤ 60 uploads | 10.5 s | ≤ 58 uploads per load account in 600 s; 50 for the baseline account |

- **6 s for NFR-08 is not enough, at 24 threads as at 4.** At 6 s, eleven no-answer asks span
  60 s at the client, plus the 1 ms per ask that `paceFrom` adds. The 11th is then a 429 as soon
  as the first was stamped about 10 ms later after its send than the 11th was.
- **10 s for NFR-09 is the limit itself.** In a 600 s phase, a floor *f* starts at most
  ⌊600/*f*⌋ + 1 rounds, counting both ends. At 10 s, that is 60 uploads, the limit, and the 61st
  round falls due at the 600 s mark. Only k6's refusal to start an iteration once the duration is
  up keeps it out. At 10.5 s the most is 58, and the 59th would fall due 9 s after the phase ends.
- The warm-up asks come from account 01 and are paced at the same floor, because they count
  against its ask rate.
- **`setupTimeout`** is computed from these numbers, not left at k6's 60 s default, which 21
  logins at 3.5 s already exceed. Worst case: every login runs to its 30 s timeout and every
  warm-up ask to its 2,835 s, plus 60 s. That is 5,880 s for NFR-08 and 6,360 s for NFR-09
  (810 s and 1,290 s while the ask timeout was 300 s). Typical setups take about 30 s and 92 s.
  `setup()` is one VU sending one request at a time, so the thread count does not change these
  either.
- **Sessions** expire after 60 idle minutes. A load-phase account in NFR-09 is idle from its login
  until the load phase starts: about 92 s + 20 min typically. At the worst-case setup it is
  6,360 s + 20 min, past the expiry. That bound was 41.5 min before the ask timeout grew on
  1 November 2026, and NFR-09 has not been revisited for it.

## Reading the result

Each run prints a summary and writes `tests/load/results/nfr08_summary.json` or
`nfr09_summary.json`.

### NFR-08's summary (D-84 decision 3)

In this order:

| Field | Meaning |
|---|---|
| `p90_ms` against `limit_ms` (4000) | **The NFR-08 number,** since 1 November 2026. p90 over answered replies and 503s, end to end over HTTP. Each 503 is a miss: a request with no answer within 4 s, ranked slower than any answered reply (D-82's note). `null` with `p90_falls_on_a_503: true` when the 90th-percentile request was a 503. `p90_samples` is how many. |
| `server_503` | How many measured asks got the server's documented 503. A 503 is the system failing, NFR-19's designed response, so it is a result and does not invalidate the run. A 429, a k6 timeout or any other status is the harness failing, and does (`unexpected_status`). |
| `p90_answered_ms` | p90 over answered replies alone, without the 503s: how NFR-08's first run on 1 November was reported, which is not re-scored. `answered_samples` is how many. |
| `p90_all_replies_ms` | p90 over every 200 reply, answered or not. A no-answer reply skips generation, so this reads lower. |
| `answered_percent`, `asks_measured` | Answered replies as a share of all measured asks, failed ones included as not answered. |
| `single_user_baseline` | **8,900 ms, not measured by this run.** It is the p90 of 50 single generation calls, timed in-process: one user, sequential, the six-chunk corpus, with the history block (`docs/flm-baseline.md`, Stage 4 item 9a). It leaves out the question's embedding, retrieval and HTTP, so even one user over HTTP would read above it. It shows the scale, and is not the same measure. |
| `commit_sha`, `uncommitted_tracked_changes` | The checkout `run.ps1` ran in. |
| `flm_version`, `flm_check` | The FLM build, and when `check_flm.py` passed, and against which URL. `flm_check` is `null` when the run did not go through `run.ps1`. |
| `db_dump_sha256` | The snapshot the run started from, as given. |
| `server`, `server_version`, `server_threads`, `server_pid`, `server_debug`, `server_sources` | The server, its version, its thread count, its pid and `DEBUG`, as the pre-flight observed them, and how each was known ([The server](#the-server-d-85-d-87)). Without `run.ps1`, as passed, and `server_sources` says so. |
| `server_stated` | What was stated beside them: `waitress`, `-ServerThreads`, and the Waitress in `-Python`'s venv. `null` when nothing was observed. |
| `server_started_at`, `previous_run` | The server's start, from Waitress's `Serving on` line, and the run record it had to be later than (D-87 decision 1). |
| `server_observed` | The `Server` header values the logins came back with, how many logins, how many had none, and `matches_server`. `null` when it was not recorded. |
| `waitress_log` | Added after k6: the run's window and the `Task queue depth` lines inside it, or `none in the run's window` (D-87 decision 3). If it still reads `not added`, the finalise step did not run. |
| `server_at_end` | Added after k6: the pid listening when the run ended, `same_process`, and which lookup found it (`found_by`, `lookup`). |
| `server_preflight` | Added after k6: the whole pre-flight record, with the command line and the DEBUG probe's status, content type and reason. |
| `throttled_429` | `total`, then `rate_limit`, `ask_in_flight`, `ingestion_in_flight` and `unrecognised`. Any non-zero makes the run INVALID. |

**A miss on 4 s is expected, and it is not a failure of the test.** The single-user generation
p90 is already 8.90 s, and one NPU answers one question at a time, so five users queue. A valid
run that misses reads `FAIL`, because NFR-08's 4 s was not met. It is then recorded as a
decision, as the risk register says, as a local-model baseline rather than a dropped NFR
(D-84 decision 3, `docs/ai-provider.md` §7).

### The verdict

One of these, in both scripts:

- **INVALID RUN**: the run does not count, whatever it measured. `invalid_reasons` says why, one
  line per cause:
  - **Any 429** (D-82 rule 5). Each is counted by what the server put in it, and each kind present
    gets its own line, so the cause is named rather than guessed. Each 429 is also printed as it
    happens, with its kind, account, code and Retry-After.

    | `throttled_429` kind | How it is told | What it means |
    |---|---|---|
    | `rate_limit` | DRF's throttle body: no `code`, and a `Retry-After` header | An account went over D-79's or D-26's rate. Was the server restarted, and was nobody logging in from a browser here? |
    | `ask_in_flight` | `"code": "ask_in_flight"`, no `Retry-After` (D-79) | An account asked while its previous ask was still being answered: an ask k6 gave up on at its timeout that the server was still answering. Since 1 November 2026 the timeout outlasts the server's slot, so this should not happen. |
    | `ingestion_in_flight` | `"code": "ingestion_in_flight"`, no `Retry-After` (D-85) | An account uploaded while its previous upload was still being processed: an upload k6 gave up on at its timeout that the server was still ingesting. |
    | `unrecognised` | anything else: another code, or no code and no `Retry-After` | Not a kind these scripts know. It is the total less the other three, so no 429 goes uncounted. |

    A restart prevents only the first kind. The two in-flight kinds come from k6's own timeouts.
  - **The `Server` header at login is missing, or names another server than `SERVER`**, or was
    not recorded at all ([The server](#the-server-d-85-d-87)). This checks which software
    answered, not its version or its thread count.
  - **The server was not observed before the run** (no `SERVER_OBSERVED_BY`: it did not go
    through `run.ps1`), or **`DEBUG` was not confirmed off** (D-87 decision 2).
  - Added by `run.ps1` after k6 exits (D-87 decisions 1 and 3): **Waitress started again during
    the run**, **another process, or none, was listening at its end**, or **Waitress's log could
    not be read after it**.
  - **A validity threshold not met:** `http_req_failed` over 1% for asks (and for uploads in
    NFR-09), or `checks` under 99%.
  - **No record that `check_flm.py` passed:** the run did not go through `run.ps1` (D-83
    decision 3).
  - **No commit SHA, FLM version, snapshot hash, server, server version or thread count.** The
    scripts refuse to start without them, so this should not happen.
  - **No responses recorded at all.**

  INVALID is decided first. A run that hit a 429 is INVALID even if it also has no data.
- **NO DATA**: the run was valid, but there was nothing to measure. For NFR-08, no reply was
  answered. That is what a corpus embedded with a different model than the query produces (R10),
  and what noisy FLM embeddings produce (D-83).
- **PASS** / **FAIL**: a valid run, measured against the limit. Latency is never a validity
  reason. A slow valid run is a FAIL.

The 429 gate and the verdict live in the JSON. k6's exit code reflects only its thresholds, which
include NFR-08's latency limit and leave out the 429 count and the gate's record. Read the
verdict, not the exit code.

If `setup()` stops (a login 429, a wrong password, an account that is not an Employee), the
console says why, and k6 may write no results file for that run. A file already in `results/` can
then be from an earlier run, so check its `commit_sha` and `finished_at`. A wrong password stops
at the first account, so it costs one failed attempt on `loadtest01` and none on the others
(FR-02 locks after five).

## What these scripts do not handle

- **NFR-09's uploads stay in the database.** One run uploads up to 50 + 20 × 58 = 1,210 TXT
  documents as Employees, with department `LoadTest`. Nothing removes them. Restore the snapshot
  instead (run order, step 5). The baseline's uploads also grow the corpus before the load phase
  asks anything.
- **The ask timeout outlasts the server's in-flight slot** (2,775 s + 60 s, since 1 November 2026).
  It was 300 s, shorter than the server's worst case, and NFR-08's first run on 1 November was
  INVALID for it: k6 abandoned asks the server was still answering, and each account's next asks
  were `ask_in_flight` 429s, 67 of them (D-82's dated note). `ASK_SLOT_TIMEOUT_S` in `common.js`
  copies the server's value, and `apps/api/tests/test_load_test_timeout_agreement.py` holds the
  copy equal. NFR-08's `maxDuration` is derived from it. NFR-09's phase durations were not
  revisited: an ask still running when a phase ends is interrupted after k6's graceful stop.
- **The upload timeout (300 s) has the same shape.** An upload k6 abandons keeps the account's
  ingestion slot until the server finishes it, because that slot has no timeout (D-85). The
  account's next upload, about 10 s later, is then an `ingestion_in_flight` 429, and so is each
  one after it until the ingestion ends.
- **At 24 threads the queue for the NPU is inside the server.** Every VU's ask is in the view at
  once, so FLM is sent one request per VU at a time, twenty in NFR-09's load phase, where 4
  threads let at most four through. Nothing has measured FLM taking twenty at once. The waiting
  now counts against each generation attempt's own 300 s timeout, and an attempt that times out
  is retried, which adds work for the asks behind it. The NPU has the same work either way, so
  the average wait should not change, but the slowest asks now depend on the order FLM serves
  requests in, which is not known. No number here changes for it. NFR-08's first run on
  1 November 2026 measured it at 5 users: answered asks had a p90 of 251 s
  (`corpus/objective-02/runs/2026-11-01/nfr08-runs.md`).
- **The server's limits are copied, not read.** `common.js` holds 20/min, 10/min and 60/hour as
  copies of `apps/core/constants.py`. If a rate changes there, change it here too, and the pacing
  checks follow.
- **What the gate does not establish:**
  - `flm version` reports the installed `flm.exe`. If FLM was upgraded after `flm serve` started,
    the running server can be a different build. `check_flm.py` tests the running server's
    behaviour, so a noisy build still fails, but the version recorded would be wrong. Restart
    `flm serve` after any reinstall.
  - `check_flm.py` checks the FLM at the shell's `FLM_BASE_URL`, not necessarily the one the
    server uses.
  - `DB_DUMP_SHA256` is recorded as given. Nothing checks the database against it.
  - **The thread count is read from the command line, not from inside Waitress** (D-87). A
    Waitress started some other way than `waitress-serve` (its own script calling `serve()`)
    has no `--threads` to read, and is refused as not observed.
  - **The version is the package installed in the server's venv**, read from its metadata. It
    is not asked of the running process, so a venv whose Waitress was changed after the server
    started would be recorded wrongly. Restart the server after any `uv pip sync`.
  - **The restart is shown, not proved** (D-87). The check is that the log's last `Serving on`
    is later than every run record in `tests/load/results` and `-ResultsDir`. A run that left no
    record there (the ingestion writes its own folder, the HTTP check writes where `--out`
    points) is invisible to it, and so is a folder not passed as `-ResultsDir`. A record is
    dated by when its file was last written; copying it with `Copy-Item` keeps that date, but
    editing and saving it later moves it.
  - **Nothing checks the HTTP check's own restart.** `run.ps1` gates NFR-08 and NFR-09 only.
  - **`DEBUG` is read from one unmatched path.** A deployment whose `handler404` changed would
    read as "not confirmed off" and be refused, rather than pass.
  - The gate's record is an environment variable, and anyone can type it. It guards against
    forgetting the check, not against getting round it on purpose. The same goes for `-Python`.
  - `run.ps1` depends on `check_flm.py`'s `RESULT: PASS` line. If that wording changes, `run.ps1`
    refuses every run until it is changed to match. It fails closed.
- **The ten load-test questions are `common.js`'s own**, not Objective 03's thirty. They are
  Employee questions on D01–D07, D10, D11 and T01 of Objective 02's corpus.
