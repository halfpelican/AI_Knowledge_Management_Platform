# Load tests: NFR-08 and NFR-09 (k6)

| Script | Measures | Accounts |
|---|---|---|
| `nfr08_query_p90.js` | p90 of `POST /api/ask`, answered replies only, 5 VUs sharing 100 asks. Limit 4,000 ms. | `loadtest01`–`loadtest05` |
| `nfr09_concurrency.js` | p90 of asks and uploads with 20 concurrent users, against a one-user baseline. At most 25% worse. | load phase `loadtest01`–`loadtest20`, baseline `loadtest21` |
| `common.js` | Logins, pacing, the ask request, and the validity gate. | |

Every virtual user (VU) logs in its own Employee account, and VU *n* uses account *n* (D-82).
The baseline gets its own account, so its uploads have their own hourly budget. Both scripts are
paced so that no account goes over D-79's limits, and any 429 makes the run INVALID.

## Before every run

1. **Commit what you are measuring.** The results record the commit SHA, and a SHA names a
   commit, not uncommitted changes.
2. **Create the accounts.** This only needs doing once. Running it again resets their passwords.
   The password comes from the environment and is never stored in the repo (D-82 rule 6).

   ```powershell
   $env:LOAD_TEST_PASSWORD = '<a password that meets FR-01 rules>'
   .venv\Scripts\python.exe manage.py create_load_test_users --count 21
   ```

   This creates `loadtest01@example.com` … `loadtest21@example.com`, all Employees. With
   `DEBUG` off, as the Waitress alpha runs (D-64), the command refuses unless you also pass
   `--i-know-this-is-local`.
3. **Restart the server** (stop and start whatever serves `BASE_URL`). Do this before *each* run,
   including between NFR-08 and NFR-09. The throttle counters and the in-flight slots live in that
   one process's memory (D-79), so a restart is what makes them start empty. Without one, an
   earlier run's logins, asks or uploads still count, and the run can hit a 429.
4. **Do not log in from a browser on this machine while `setup()` runs.** The login limit is
   20 a minute per address, and the browser shares 127.0.0.1 with k6.
5. FLM is serving, as for any ask.

## Running

From the repository root, because the results are written to `tests/load/results/` relative to the
current directory:

```powershell
$sha = git rev-parse HEAD
k6 run -e TEST_PASSWORD=$env:LOAD_TEST_PASSWORD -e GIT_SHA=$sha `
       -e AI_PROVIDER=flm -e FLM_CHAT_MODEL=gemma3:4b `
       tests/load/nfr08_query_p90.js

# restart the server, then:
$sha = git rev-parse HEAD
k6 run -e TEST_PASSWORD=$env:LOAD_TEST_PASSWORD -e GIT_SHA=$sha `
       -e AI_PROVIDER=flm -e FLM_CHAT_MODEL=gemma3:4b `
       tests/load/nfr09_concurrency.js
```

NFR-08 takes a few minutes: at least 140 s of asks, plus about 30 s of setup. NFR-09 takes 32–37
minutes, because the load phase starts 20 minutes after setup ends whenever the baseline finishes.

| `-e` variable | Required | Meaning |
|---|---|---|
| `TEST_PASSWORD` | yes | The accounts' password. It must equal `LOAD_TEST_PASSWORD`. |
| `GIT_SHA` | yes | The commit under test, 7–40 hex digits. Without it the script refuses to start. |
| `AI_PROVIDER`, `FLM_CHAT_MODEL` | no | Recorded in the results, `not recorded` if absent. k6 also reads them from the shell's environment. |
| `BASE_URL` | no | Default `http://localhost:8000`. |
| `TEST_EMAIL_PREFIX`, `TEST_EMAIL_DOMAIN` | no | Defaults `loadtest` and `example.com`, which give `loadtest01@example.com`. The command only creates that scheme, so change these only for accounts made some other way. |
| `VUS`, `ITERATIONS` | no | NFR-08 only, defaults 5 and 100. VU *n* needs account *n*. |
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
`nfr09_summary.json`. The verdict is one of these:

- **INVALID RUN**: the run does not count, whatever it measured. `invalid_reasons` says why, one
  line per cause:
  - **Any 429** (D-82 rule 5). `throttled_429` splits the count into `rate_limit` and
    `ask_in_flight`. A rate-limit 429 means an account went over D-79 or D-26: was the server
    restarted? An `ask_in_flight` 429 follows an ask that k6 gave up on at 300 s while the server
    was still answering it. Each 429 is also printed as it happens, naming the account.
  - **A validity threshold not met:** `http_req_failed` over 1% for asks (and for uploads in
    NFR-09), or `checks` under 99%.
  - **No commit SHA.** The script refuses to start without one, so this should not happen.
  - **No responses recorded at all.**

  INVALID is decided first. A run that hit a 429 is INVALID even if it also has no data.
- **NO DATA**: the run was valid, but there was nothing to measure. For NFR-08, no reply was
  answered. That is what a corpus embedded with a different model than the query produces (R10).
- **PASS** / **FAIL**: a valid run, measured against the limit. Latency is never a validity
  reason. A slow valid run is a FAIL.

The 429 gate and the verdict live in the JSON. k6's exit code reflects only its thresholds, which
include NFR-08's latency limit and leave out the 429 count. Read the verdict, not the exit code.

If `setup()` stops (a login 429, a wrong password, an account that is not an Employee), the
console says why, and k6 may write no results file for that run. A file already in `results/` can
then be from an earlier run, so check its `commit_sha` and `finished_at`. A wrong password stops at the first account, so it costs one
failed attempt on `loadtest01` and none on the others (FR-02 locks after five).

## What these scripts do not handle

- **NFR-09's uploads stay in the database.** One run uploads up to 50 + 20 × 58 = 1,210 TXT
  documents as Employees, with department `LoadTest`. Nothing removes them. The baseline's uploads
  also grow the corpus before the load phase asks anything.
- **The ask timeout (300 s) is shorter than the server's worst case**, so an abandoned ask can still
  be holding the account's in-flight slot. The run is then INVALID twice over: the timeout counts
  against `http_req_failed`, and the next ask is an `ask_in_flight` 429.
- **The server's limits are copied, not read.** `common.js` holds 20/min, 10/min and 60/hour as
  copies of `apps/core/constants.py`. If a rate changes there, change it here too, and the pacing
  checks follow.
