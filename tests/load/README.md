# Load tests: NFR-08 and NFR-09 (k6)

| File | What it is | Accounts |
|---|---|---|
| `run.ps1` | **How every run starts.** Refuses to start k6 unless `scripts/check_flm.py` passes, then records the commit, the FLM version and the snapshot hash (D-83, D-84). | |
| `nfr08_query_p90.js` | p90 of `POST /api/ask`, answered replies only, 5 VUs sharing 100 asks. Limit 4,000 ms. Objective 03's p90 (D-84 decision 3). | `loadtest01`–`loadtest05` |
| `nfr09_concurrency.js` | p90 of asks and uploads with 20 concurrent users, against a one-user baseline. At most 25% worse. | load phase `loadtest01`–`loadtest20`, baseline `loadtest21` |
| `common.js` | Logins, pacing, the ask request, the run record and the validity gate. | |

Every virtual user (VU) logs in its own Employee account, and VU *n* uses account *n* (D-82).
The baseline gets its own account, so its uploads have their own hourly budget. Both scripts are
paced so that no account goes over D-79's limits, and any 429 makes the run INVALID.

## Run order for item 6 (D-84)

The measurement database is a fresh one holding exactly Objective 02's corpus, with its own
`DATABASE_URL`, `MEDIA_ROOT`, `AUDIT_LOG_PATH` and `ERROR_LOG_PATH`. It is ingested and
snapshotted before anything is measured. That part is not this folder's: the item 6 runbook
(`docs/measurement-runbook.md`) covers it. These steps start once the snapshot exists and its
SHA-256 is recorded.

1. **The thirty questions run first, or the snapshot is restored first.** NFR-09 uploads a
   kitchen-roster document every round, and those uploads become retrieval candidates for the
   questions. D-84 puts the questions before either load test.
2. **Restart the server**, then run **NFR-08 at 5 users** through `run.ps1`. Five is fixed by
   D-84 decision 3, before the run, so leave `VUS` unset.
3. **Restart the server again**, then run **NFR-09** through `run.ps1`, as a separate run.
4. **After NFR-09 the database is no longer the snapshot.** It holds up to 1,210 `LoadTest`
   uploads. Restore the snapshot before measuring anything else on it, including a second NFR-08
   run, and pass the same hash.

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
4. **Restart the server** (stop and start whatever serves `BASE_URL`). Do this before *each* run,
   including between NFR-08 and NFR-09. The throttle counters and the in-flight slots live in that
   one process's memory (D-79), so a restart is what makes them start empty. Without one, an
   earlier run's logins, asks or uploads still count, and the run can hit a 429. `run.ps1` cannot
   check this.
5. **Do not log in from a browser on this machine while `setup()` runs.** The login limit is
   20 a minute per address, and the browser shares 127.0.0.1 with k6.
6. **FLM v0.9.39 is serving** (`flm serve gemma3:4b --embed 1`), and `FLM_BASE_URL` in this shell
   names the same FLM as the server's. `check_flm.py` reads the shell's environment, not `.env`.
   Both default to `http://127.0.0.1:8625/v1`.

## Running

It works from any directory; the paths below are from the repository root. It was tested in
Windows PowerShell 5.1, the laptop's own, and not in PowerShell 7. The laptop's `RemoteSigned`
policy runs it as it is.

```powershell
$env:LOAD_TEST_PASSWORD = '<the accounts password>'
$env:AI_PROVIDER = 'flm'; $env:FLM_CHAT_MODEL = 'gemma3:4b'   # recorded in the results, optional
$hash = (Get-FileHash <the snapshot dump file> -Algorithm SHA256).Hash

# restart the server, then:
.\tests\load\run.ps1 -Test nfr08 -DbDumpSha256 $hash

# restart the server, then:
.\tests\load\run.ps1 -Test nfr09 -DbDumpSha256 $hash
```

In a second worktree, which has no `.venv` of its own, add
`-Python <main checkout>\.venv\Scripts\python.exe`.

NFR-08 takes a few minutes: at least 140 s of asks, plus about 30 s of setup. NFR-09 takes 32–37
minutes, because the load phase starts 20 minutes after setup ends whenever the baseline finishes.
`check_flm.py` runs before either. Its first chat call can include loading the model, and it
allows that call 180 s.

### What `run.ps1` does

It stops at the first failure, prints `REFUSED: <why>` and `k6 was not started`, and exits 2:

1. **The arguments.** `-DbDumpSha256` must be 64 hex digits. `LOAD_TEST_PASSWORD` must be set.
   The venv's python, `scripts/check_flm.py`, `flm`, `git` and `k6` must all exist. It never falls
   back to the `python` on `PATH`: on this laptop that is an interpreter without the project's
   environment.
2. **`flm version`.** Anything but **v0.9.39** is refused (D-83 decision 1). From v1.0.4 the
   embeddings are noise, and a build that is sound but embeds differently would not match the
   snapshot's vectors, which `check_flm.py` cannot see.
3. **`scripts/check_flm.py`**, with the venv's python. It must exit 0 *and* print its
   `RESULT: PASS` line. An exit code alone is not trusted, because an interpreter that ran
   nothing also exits 0.
4. **`git rev-parse HEAD`**, and `git status` for uncommitted changes to tracked files.

Then it runs k6 from the repository root, so the results land in `tests/load/results/`, with:

| `-e` variable | From |
|---|---|
| `GIT_SHA` | `git rev-parse HEAD` |
| `GIT_TRACKED_CHANGES` | `none` or `present`, from `git status` |
| `FLM_VERSION` | `flm version`, such as `v0.9.39` |
| `FLM_CHECK_PASSED_AT`, `FLM_CHECK_URL` | when `check_flm.py` passed, and the URL its `RESULT: PASS` line names |
| `DB_DUMP_SHA256` | `-DbDumpSha256`, in lower case |
| `TEST_PASSWORD` | `$env:LOAD_TEST_PASSWORD`. The printed command shows `***` |
| `BASE_URL` | `-BaseUrl`, only if given |

Any other exit code is k6's own. It does not carry the verdict (see below).

### Running k6 without `run.ps1`

Without `run.ps1`, the scripts still refuse to start unless `GIT_SHA`, `FLM_VERSION` and
`DB_DUMP_SHA256` are given, so a run cannot go unrecorded. Without the gate's record, though, the
run is **INVALID**, because nothing shows `check_flm.py` passed. Use this only to debug the
scripts.

| `-e` variable | Required | Meaning |
|---|---|---|
| `TEST_PASSWORD` | yes | The accounts' password. It must equal `LOAD_TEST_PASSWORD`. |
| `GIT_SHA` | yes | The commit under test, 7–40 hex digits. |
| `FLM_VERSION` | yes | As `flm version` prints it, with the `v`: `v0.9.39`. |
| `DB_DUMP_SHA256` | yes | The snapshot's SHA-256, 64 hex digits. |
| `FLM_CHECK_PASSED_AT`, `FLM_CHECK_URL`, `GIT_TRACKED_CHANGES` | set by `run.ps1` | Without `FLM_CHECK_PASSED_AT` the run is INVALID. |
| `AI_PROVIDER`, `FLM_CHAT_MODEL` | no | Recorded in the results, `not recorded` if absent. k6 also reads them from the shell's environment. |
| `BASE_URL` | no | Default `http://localhost:8000`. |
| `TEST_EMAIL_PREFIX`, `TEST_EMAIL_DOMAIN` | no | Defaults `loadtest` and `example.com`, which give `loadtest01@example.com`. The command only creates that scheme, so change these only for accounts made some other way. |
| `VUS`, `ITERATIONS` | no | NFR-08 only, defaults 5 and 100. VU *n* needs account *n*. Objective 03 is 5 VUs (D-84). |
| `BASELINE_ITERATIONS` | no | NFR-09 only, default 50, at most 60 (the baseline account's uploads in an hour). |

`TEST_EMAIL`, `GIT_COMMIT` and `ROLE` are no longer read. The first two make the scripts refuse to
start, with a message saying what replaced them. The role is checked at login instead: every
account must log in as an Employee, or `setup()` stops.

## Pacing, and why each number is what it is

DRF's throttle is a sliding window. It stamps a request when the view runs, and with more VUs than
Waitress's 4 default threads, that can be well after k6 sent it. So spacing the *sends* W/N apart
is not enough. A late stamp on the first request of a window lets the (N+1)th land inside it.
Because a VU sends nothing until its previous reply is back, a start-to-start spacing of at least
**W/(N−1)** keeps any N+1 consecutive requests more than W apart at the server, however late any
one of them is stamped (`common.js`, `minimumSpacingSeconds`). Each script checks its numbers
against this when it loads, and refuses to start if one is short.

| What | Limit | Needed | Used | Result |
|---|---|---|---|---|
| Logins in `setup()`, 127.0.0.1 | 20/min per address (D-26) | ≥ 60/19 = 3.16 s | 3.5 s | 21 logins span 70 s; any 21 consecutive are > 66.5 s apart |
| NFR-08 iteration floor | 10 asks/min per user (D-79) | ≥ 60/9 = 6.67 s | 7 s | any 11 asks > 63 s apart |
| NFR-09 round floor, both phases | 10 asks/min; 60 uploads/hour per user | ≥ 6.67 s for asks; ≤ 60 uploads | 10.5 s | ≤ 58 uploads per load account in 600 s; 50 for the baseline account |

- **6 s for NFR-08 is not enough.** At 6 s, eleven no-answer asks span exactly 60 s at the
  client. The 11th is then a 429 as soon as the first was stamped even slightly late.
- **10 s for NFR-09 is the limit itself.** In a 600 s phase, a floor *f* starts at most
  ⌊600/*f*⌋ + 1 rounds, counting both ends. At 10 s, that is 60 uploads, the limit, and the 61st
  round falls due at the 600 s mark. Only k6's refusal to start an iteration once the duration is
  up keeps it out. At 10.5 s the most is 58, and the 59th would fall due 9 s after the phase ends.
- The warm-up asks come from account 01 and are paced at the same floor, because they count
  against its ask rate.
- **`setupTimeout`** is computed from these numbers, not left at k6's 60 s default, which 21
  logins at 3.5 s already exceed. Worst case: every login runs to its 30 s timeout and every
  warm-up ask to its 300 s, plus 60 s. That is 810 s for NFR-08 and 1290 s for NFR-09. Typical
  setups take about 30 s and 92 s.
- **Sessions** expire after 60 idle minutes. A load-phase account in NFR-09 is idle from its login
  until the load phase starts, at most 1290 s + 20 min = 41.5 min.

## Reading the result

Each run prints a summary and writes `tests/load/results/nfr08_summary.json` or
`nfr09_summary.json`.

### NFR-08's summary (D-84 decision 3)

In this order:

| Field | Meaning |
|---|---|
| `p90_answered_ms` against `limit_ms` (4000) | **The NFR-08 number.** p90 over answered replies only, end to end over HTTP. `answered_samples` is how many. |
| `p90_all_replies_ms` | p90 over every valid reply, answered or not. A no-answer reply skips generation, so this reads lower. |
| `answered_percent`, `asks_measured` | Answered replies as a share of all measured asks, failed ones included as not answered. |
| `single_user_baseline` | **8,900 ms, not measured by this run.** It is the p90 of 50 single generation calls, timed in-process: one user, sequential, the six-chunk corpus, with the history block (`docs/flm-baseline.md`, Stage 4 item 9a). It leaves out the question's embedding, retrieval and HTTP, so even one user over HTTP would read above it. It shows the scale, and is not the same measure. |
| `commit_sha`, `uncommitted_tracked_changes` | The checkout `run.ps1` ran in. |
| `flm_version`, `flm_check` | The FLM build, and when `check_flm.py` passed, and against which URL. `flm_check` is `null` when the run did not go through `run.ps1`. |
| `db_dump_sha256` | The snapshot the run started from, as given. |

**A miss on 4 s is expected, and it is not a failure of the test.** The single-user generation
p90 is already 8.90 s, and one NPU answers one question at a time, so five users queue. A valid
run that misses reads `FAIL`, because NFR-08's 4 s was not met. It is then recorded as a
decision, as the risk register says, as a local-model baseline rather than a dropped NFR
(D-84 decision 3, `docs/ai-provider.md` §7).

### The verdict

One of these, in both scripts:

- **INVALID RUN**: the run does not count, whatever it measured. `invalid_reasons` says why, one
  line per cause:
  - **Any 429** (D-82 rule 5). `throttled_429` splits the count into `rate_limit` and
    `ask_in_flight`. A rate-limit 429 means an account went over D-79 or D-26: was the server
    restarted? An `ask_in_flight` 429 follows an ask that k6 gave up on at 300 s while the server
    was still answering it. Each 429 is also printed as it happens, naming the account.
  - **A validity threshold not met:** `http_req_failed` over 1% for asks (and for uploads in
    NFR-09), or `checks` under 99%.
  - **No record that `check_flm.py` passed:** the run did not go through `run.ps1` (D-83
    decision 3).
  - **No commit SHA, FLM version or snapshot hash.** The scripts refuse to start without them, so
    this should not happen.
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
  instead (run order, step 4). The baseline's uploads also grow the corpus before the load phase
  asks anything.
- **The ask timeout (300 s) is shorter than the server's worst case**, so an abandoned ask can still
  be holding the account's in-flight slot. The run is then INVALID twice over: the timeout counts
  against `http_req_failed`, and the next ask is an `ask_in_flight` 429.
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
  - The gate's record is an environment variable, and anyone can type it. It guards against
    forgetting the check, not against getting round it on purpose. The same goes for `-Python`.
  - `run.ps1` depends on `check_flm.py`'s `RESULT: PASS` line. If that wording changes, `run.ps1`
    refuses every run until it is changed to match. It fails closed.
- **The ten load-test questions are `common.js`'s own**, not Objective 03's thirty. They are
  Employee questions on D01–D07, D10, D11 and T01 of Objective 02's corpus.
