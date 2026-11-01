# NFR-08 runs, 1 November 2026

Objective 03's p90 at five users (D-84 decision 3). Every run here uses the same setup:

- **Database:** `kmp_obj02_20261101`, dump SHA-256
  `3bf98403354dbabceb54052b99b45a25f5f39d4fd685cca1e07233aa1e166f59`.
- **FLM:** v0.9.39, gated by `scripts/check_flm.py`.
- **Server:** Waitress 3.0.2, 24 threads, `DEBUG` off, restarted before each run (D-85, D-87).
- **Who runs it:** Benjamin Morovan, through `tests/load/run.ps1`.

Times are local (+11:00) unless they end in Z.

| Run | VUs / asks | Commit | Result file | Verdict |
|---|---|---|---|---|
| 1 | 5 / 100 | `b8d8304` | `nfr08_summary.run1-invalid-5vu.json` | **INVALID**, kept as a finding |
| 2 | 1 / 20 | `945fd02` | `nfr08_summary.run2-baseline-1vu.json` | **INVALID** under the old rule (two 503s); answered-only p90 51,206 ms |
| 3 | 5 / 25 | `eed8249` | `nfr08_summary.json` | **Valid, FAIL:** 3 × 503, answered-only p90 276,689 ms |

## Run 1: 5 VUs, 100 asks, INVALID

- **When:** the k6 window ran from 14:47:33 to 15:11:38. Server pid 51708, started at 08:24:41.
- **The file:** renamed from `nfr08_summary.json` so the later runs cannot overwrite it. The
  bytes are unchanged.
- **What it measured:**
  - 28 of 100 asks answered;
  - p90 of the answered asks 251,469 ms against 4,000 ms, from 28 samples (all replies: the
    same 28);
  - 67 `ask_in_flight` 429s and no rate-limit 429;
  - no Waitress queueing in the window.
- **Why it is INVALID:**
  - k6's ask timeout was 300 s. The server's in-flight slot lasts up to 2,775 s:
    `ASK_SLOT_TIMEOUT_SECONDS`, which is 300 s × 3 generation attempts + 1,875 s for the
    question's embedding.
  - k6 abandoned asks the server was still answering. Each such account's next asks were then
    refused with `ask_in_flight` until the server finished.
  - Any 429 invalidates a run (D-82 rule 5), and the failed requests also broke the
    `http_req_failed` threshold.

### Timed-out and retried generation attempts: what the records show

The user asked for this check before any rerun.

**What is recorded, and what is not.**

- **No generation attempt is recorded by the live server.**
  - Attempts are reported only through `on_attempt`, which the harness uses and the view does not.
  - Nothing under `apps/ai/` logs.
  - When `/api/ask` answers 503, the view discards the exception, whose message is the only place
    that names the cause. `errors.log` gets only Django's "Service Unavailable: /api/ask" line.
- **`errors.log`:** two 503s, at 14:59:27.278 (+713.7 s after the window opened) and at
  15:09:52.126 (+1,338.5 s).
  - A 503 from `/api/ask` means one of three things: generation failed three attempts, the
    question's embedding failed three attempts (up to 600 s each), or one embedding reply could
    not be used as a query vector, which is not retried.
- **QueryLog:** 33 rows from the load-test accounts in the window, all answered, with
  `rejected_count` 0. The per-account rows are in `nfr08_run1_querylog.json`.
  - 2 of the rows are loadtest01's warm-ups, so 31 are measured asks. k6 received 28 of them, so
    the server finished 3 asks that k6 had already abandoned.
  - One of the 3 is loadtest01's row at +1,471.0 s, written after k6 had finished at +1,444.4 s.
  - **The 100 asks:** 28 answered and received, 67 refused with 429, 3 abandoned and answered
    later, and the 2 503s.
- **The rows carry only an end time,** and each account has one ask in flight at a time. So the
  gap between an account's consecutive rows is an upper bound on how long its later ask spent in
  the server.

**What follows from that.**

- **The 503 at +1,338.5 s was loadtest05's.**
  - At that moment every other account had an ask in flight, by their rows.
  - loadtest05's previous ask ended at +775.2 s, so this one spent at most 563 s in the server.
  - Three generation timeouts would take at least 900 s, and three embedding timeouts at least
    1,800 s. **So it did not fail on timeouts alone.** Either two or more generation attempts
    failed another way (a reply that broke the schema, or an FLM error such as a refused
    connection, a 5xx, or a 200 carrying an error body), or the embedding failed by error or gave
    an unusable reply.
- **The 503 at +713.7 s was loadtest01's or loadtest02's.**
  - If loadtest01's, it spent at most 65 s in the server, with no timeouts.
  - If loadtest02's, at most 355 s, with at most one generation timeout.
  - Only loadtest02's fits the count of 28 + 67 + 5 at the 7 s pacing. That is modelled, not
    observed.
  - Either way, it did not fail on timeouts alone.
- **The asks k6 abandoned and the server then answered** each spent more than 300 s in the
  server. Their upper bounds are 484 s (loadtest01's, ending +1,132.7 s), 338 s (loadtest01's,
  ending +1,471.0 s) and 304 s (loadtest02's, ending +1,165.3 s).
  - An answered ask over 300 s means either a generation attempt failed and was retried, or the
    question's embedding waited at FLM, which serves both. **The records cannot tell which.**
- **Conclusion.** Requests did fail during the run, and they did not fail by timing out alone:
  each of the two 503s had at least two failures that were not timeouts. **How many generation
  attempts timed out and were retried cannot be counted from `errors.log` or QueryLog,** because
  neither records an attempt.

## Run 2: the single-user end-to-end baseline (1 VU, 20 asks)

- **Why:** the 8.90 s baseline (`docs/flm-baseline.md`, Stage 4 item 9a) times one generation
  call in-process, with no embedding, retrieval or HTTP. This run measures the same path NFR-08
  measures, at one user, so run 3 has a like-for-like comparison.
- **How:**
  - the same script through `run.ps1`, with `$env:VUS = '1'` and `$env:ITERATIONS = '20'` set
    in that window and removed afterwards;
  - account `loadtest01`;
  - the server restarted first, at 15:30:02, from `945fd02`.
- **Reading it:**
  - It is its own result, not the gate's number. Its 4 s verdict is expected to read FAIL.
  - The `single_user_baseline` field it writes still names the 8.90 s generation-only figure.
    This run's own p90 is the end-to-end one.

## Run 3: NFR-08 again at 5 VUs, 25 asks

These changes were recorded before the run started, at the user's instruction of 1 November 2026.

1. **`ASK_TIMEOUT_S`: 300 s → 2,835 s,** which is the slot's 2,775 s plus 60 s.
   - **Why:** so k6 never abandons an ask whose slot is still held, which is what invalidated
     run 1. The 60 s covers k6's clock starting before the server takes the slot.
   - `ASK_SLOT_TIMEOUT_S` in `tests/load/common.js` copies the server's value.
     `apps/api/tests/test_load_test_timeout_agreement.py` holds the two equal, and it failed
     when the copy was broken either way.
2. **`maxDuration`: 45 m → `ceil(ITERATIONS / VUS) × (ASK_TIMEOUT_S + ITERATION_FLOOR_S)`.**
   That is 5 × 2,842 s = 14,210 s (3 h 56 m 50 s), as `k6 inspect` reports.
   - **Why:** at `maxDuration` k6 interrupts any ask still in flight, which abandons it just as a
     timeout does. 45 m was shorter than one ask's new timeout.
   - **Why this bound holds:** each VU starts its next iteration as soon as one ends, and none
     lasts longer than `ASK_TIMEOUT_S + ITERATION_FLOOR_S`. So every iteration has started and
     finished inside the bound.
   - **It is a ceiling, not the run's length.** A run whose asks come back takes minutes.
3. **`ITERATIONS`: 100 → 25.**
   - **Why:** so it fits the gate day. At run 1's answered p90 of 251 s, 25 asks shared by 5
     users are about 5 rounds, roughly 21 minutes plus setup.
4. **Concurrency stays 5** (D-84 decision 3).
5. **A 503 is scored as a miss, not treated as a harness failure** (D-82's later note of
   1 November).
   - **Why:** NFR-08 is an answer within 4 s for 90% of requests, and a 503 is a request that got
     no answer within 4 s. A 429 or a timeout means the harness failed; a 503 means the system
     failed (NFR-19's designed response), which is a result.
   - **How:** each 503 goes into the p90 sample ranked slower than any answered reply, and is
     counted on its own as `server_503`. The verdict's p90 is `p90_ms`.
   - **When it was decided:** after run 1 showed two 503s in 100 asks. Under the old rule, one
     503 in 25 asks would have invalidated run 3.
   - **Run 1 is not re-scored.**
6. **Failed provider attempts are logged** (`apps/ai/attempt_log.py`).
   - **What:** each failed generation or question-embedding attempt, with its cause, its seconds
     and the account, and each 503's cause. They are WARNINGs on `apps.ai.attempts` in
     `C:\kmp-measurement\2026-11-01\logs\errors.log`.
   - **Why:** run 1's logs could not say whether attempts timed out and were retried.
   - **Effect on the comparison:** run 3 is on a later commit than run 2. The server code differs
     only by this logging.

**Still INVALID, as before:** any 429, a k6 timeout or any other status besides 200 and the
documented 503, a `checks` rate of 99% or less, or a missing SHA.

**Unchanged:**

- the 7 s iteration floor and the 3.5 s login spacing;
- accounts `loadtest01` to `loadtest05`.

## Results

Run 1 is written up above.

### Run 2: INVALID under the rule it ran under

- **The run:**
  - commit `945fd02`, with a clean tree at the pre-flight;
  - server pid 15752, started at 15:30:02;
  - k6 window from 16:18:12 to 16:30:46;
  - the file is `nfr08_summary.run2-baseline-1vu.json`.
- **What it measured:**
  - 18 of 20 asks answered;
  - answered-only p90 **51,206 ms** from 18 samples (all replies: the same 18), at one user,
    end to end;
  - no 429 and no Waitress queueing.
- **Why it is INVALID:** two 503s, at 16:23:06 and 16:28:53. Under the rule at `945fd02` they failed
  the `http_req_failed` and `checks` thresholds.
  - Like run 1, it is not re-scored.
  - Under the new rule, 2 misses in 20 asks would put the 90th-percentile request on a 503.
- **QueryLog** (20 rows from `loadtest01`, all answered: the 2 warm-ups and the 18). At one user
  each ask starts when the previous reply arrives, so the gap between rows is close to the ask's
  time in the server:
  - The 18 answered asks took 8 to 57 s.
  - Each 503 came at most 177 s after the previous reply. That is about 59 s per attempt for three
    attempts, **not timeouts**.
- **The two 503s were the same question.** Measured asks 3 and 13 are both `QUESTIONS[3]`, "How are
  records managed and retained?", because `tests/load/common.js` cycles its 10 questions by
  iteration.
  - Both slow answered asks (56.9 s and 51.0 s) were `QUESTIONS[1]`.
  - So the failure follows the question, not the load. That is likely because generation runs at
    temperature 0, so a retry repeats the same reply.
  - `945fd02` logs no cause. Run 3 logs it.
- **What this predicts for run 3.**
  - 25 shared iterations ask `QUESTIONS[3]` three times (iterations 3, 13 and 23).
  - If it fails each time, that is 3 misses in 25 (12%). The 90th-percentile request is then a
    503, so run 3 reads FAIL on that alone, whatever the latencies.
  - **Nothing was changed for it:** not the question set, nor the generation settings.

### Run 3: valid, FAIL

- **The run:**
  - commit `eed8249`, with a clean tree;
  - server pid 53900, started at 16:47:14;
  - k6 window from 18:19:58 to 18:40:29;
  - the file is `nfr08_summary.json`.
- **What it measured:**
  - 22 of 25 asks answered and 3 got a 503, so 0 invalid reasons;
  - `p90_ms` is `null`, because the 90th-percentile request was a 503 (25 samples);
  - answered-only p90 **276,689 ms** (22 samples), against 51,206 ms at one user in run 2;
  - no 429, no unexpected status, and no Waitress queueing.
- **QueryLog:** 24 rows in the window, all answered: the 2 warm-ups and the 22.
- **The attempt log** is `nfr08_run3_attempts.log` in this folder: the window's lines from the error
  file.
  - **13 failed generation attempts, every one a `SchemaViolation`:** "unbalanced JSON object in
    the response", a reply that stopped before its JSON closed. 9 were in the three 503s and 4
    in asks answered on attempt 3. With the three 503 lines, that is 16 lines from
    `apps.ai.attempts`.
  - **No timeouts, no FLM errors and no failed embeddings.**
  - **The 3 503s** are three schema violations each: loadtest04 at 18:27:57, loadtest03 at
    18:33:37 and loadtest01 at 18:40:28.
  - **4 more failed attempts were in asks that were then answered on attempt 3:** loadtest02's
    first two and loadtest04's second ask's first two. They count among the 22 answered, and their
    time includes the two discarded generations.
  - **How long a failed attempt took:**
    - 55.8 to 58.6 s with little else running, as in run 2 (about 59 s each);
    - 106.8 to 174.5 s while other asks were generating.
- **Matching the prediction.** Three 503s match the three times `QUESTIONS[3]` was asked. The log
  names no question, by design, so this matches by count; it is not observed.

### What the attempt log confirms about the cause, and what it does not

- **Confirmed: one model on one NPU shares its time across concurrent asks.** This is the
  consequence of D-35.
  - The same failing generation took about 58 s alone and up to 174.5 s with others running.
  - The answered-only p90 grew from 51 s at one user to 277 s at five, about 5.4 times.
  - The log cannot tell whether FLM serves requests strictly one at a time or interleaves them.
    Either way the throughput is fixed and divided among the asks.
- **Not the cause of the 503s: queueing.**
  - No attempt timed out at five users.
  - Every failure was a reply that stopped before its JSON closed.
  - The same failure happened at one user in run 2.
  - The steady 56 to 59 s per attempt when uncontended fits a reply running to
    `GENERATION_MAX_TOKENS` (800). That is the likely reading. The reply's `finish_reason` is not
    logged, so it is not observed.
- **An addition to the cause: the discarded attempts took NPU time from everyone.**
  - The 13 failed attempts at about 58 s each, uncontended, come to roughly 750 s of NPU time.
    That is an estimate from the uncontended per-attempt time, not a measurement. Their
    wall-clock time, shared with other asks, was longer.
  - So a large share of the run's NPU time went to replies that were then thrown away, which
    raises every answered ask's time too.
- **Not tuned tonight.** NFR-08 is not in the M6 gate.

## NFR-09: not run on 1 November 2026

**Decided by the user, on the evidence of runs 2 and 3.** NFR-09 allows at most 25% degradation at
20 users, and at 5 users NFR-08's answered-only p90 is already about +440% over one user (277 s
against 51 s). A run would also take well over the README's 32 to 37 minutes.

**The expected failure is a prediction, not a result.**

- **At 20 users,** each ask would wait behind up to 19 others.
- **Per-attempt times would pass the 300 s attempt timeout.** At 5 users, failing attempts already
  took up to 174.5 s. So most asks would likely end in 503 after three attempts, and the run would
  mostly measure timeouts.
- **It may be worse than that.** FLM may still generate a request that Django has abandoned, so
  retries would add work to the queue rather than recover from it. The attempt log cannot show
  that directly. It is a possibility, not an observation.
