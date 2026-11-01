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
| 2 | 1 / 20 | this record's commit | `nfr08_summary.run2-baseline-1vu.json` | not yet run |
| 3 | 5 / 25 | this record's commit | `nfr08_summary.json` | not yet run |

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
  - the server restarted first;
  - the same commit as run 3.
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

**Unchanged:**

- the 7 s iteration floor and the 3.5 s login spacing;
- accounts `loadtest01` to `loadtest05`;
- the validity rules: any 429 invalidates the run, `http_req_failed{name:ask}` must stay under
  1%, and `checks` must stay over 99%.

**What these changes do not cover.** A 503 is still a failed request. Out of 25 asks, a single 503
is 4%, which fails the `http_req_failed` threshold, so a 503 would make run 3 INVALID. Run 1 had
two 503s in 100 asks.

## Results

Filled in after each run.
