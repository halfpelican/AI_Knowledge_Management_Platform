# Step 7's "after", on the shipped values: 8 November 2026

The frozen thirty, NFR-08, FR-13's nine threads and the HTTP check, run on `main` after step 7
merged. That build has `RELEVANCE_THRESHOLD` 0.30, no partial-match floor, and `MAXIMUM_STATEMENTS`
6 (D-100, D-102). The order follows D-87 and `docs/measurement-runbook.md`: the thirty in-process,
NFR-08 on a fresh server, the threads with the server stopped, then the HTTP check on a fresh server.

**Shared by every run:**

- **Commit:** `19c98a8`, with no uncommitted tracked changes.
- **FLM:** v0.9.39, with `check_flm.py` passing before each run.
- **The dump:** `3bf98403354dbabceb54052b99b45a25f5f39d4fd685cca1e07233aa1e166f59`, database
  `kmp_obj02_20261101`. The corpus gate found exactly the manifest's 25 items.
- **The server, where one was used:** Waitress 3.0.2, 24 threads, `DEBUG` off, observed.
- **The laptop was kept quiet.**

## The frozen thirty (`harness.json`, 17:47–18:00, in-process)

| | 1 November (0.30, no cap) | 8 November, 0.4231 + cap (`../after/`) | **now (0.30 + cap 6)** |
|---|---|---|---|
| ordinary answered correctly (expected answer, expected source) | 16/22 | 16/22 | **19/22** |
| ordinary left unanswered | 1/22 | 6/22 | **0/22** |
| scoped, answered for the role that can see the source | 4/4 | 3/4 | **4/4** |
| scoped, declined for the role that cannot | 3/4 | 4/4 | **1/4** |
| no-answer questions declined | 3/4 | 3/4 | **1/4** |
| path A | 2 | 14 | 2 |
| first-attempt conformance | 32/32 responses | 100% (20/20) | **100% (32/32)** |
| fabricated identifiers, leaks | 0, 0 | 0, 0 | **0, 0** |
| answered question, median / p90 | n/a | 10.5 / 17.4 s | 21.5 / 26.4 s |

**The finding: the cap answers more, and declines less.** Correct declines fell from 6 of 8 to 2 of
8.

- **s02, s03 and s04, asked by the Employee,** and **n01, n03 and n04** were answered from material
  the asker may see, where no answer was expected.
- **No out-of-scope chunk reached any prompt or answer** (invariant 1 holds). But a question whose
  answer the asker may not see, or that the corpus cannot answer, should get the no-answer reply.
- **Phase 2a's first development set hinted at this,** with fewer declines under every cap.
  Phase 2c's users'-wording set did not: 7 of 8 declined at 0.30 with the cap.
- **Whether the cap sentence, rule 8 of the prompt, or run-to-run variance (D-40) causes it** has not
  been isolated.
- **This result is held out for the cap,** which no frozen result informed. For the threshold it is
  not (D-101's note).

## NFR-08 (`nfr08_summary.json`, 18:04–18:30, 5 VUs, 25 asks, fresh server)

| | run 3 (1 November) | **now** |
|---|---|---|
| 503s | 3 | **0** |
| answered | 22/25 | **25/25** |
| p90, with 503s counted as misses | fell on a 503 | **350,407 ms** |
| p90, answered only | 276,689 ms | **350,407 ms** |
| run valid / verdict | valid, FAIL | **valid, FAIL** (the limit is 4,000 ms) |

- **The 503s are gone under load.** That was D-82's cause, removed by the cap (D-100).
- **The answered p90 is slower than run 3's.** All 25 asks were answered and queued on one NPU,
  where run 3's three failures did not contribute to its answered-only p90. Waitress logged no
  queueing in the run's window, so the wait is on the NPU, not in the server.
- **NFR-08 stays a local-model baseline miss** (D-95).
- **The load-test accounts:** they were given a throwaway password for the run only, generated in
  memory and never written, and made unusable again afterwards (D-89): 21 of 21.
- **A first attempt at 18:02 was abandoned** before any ask completed, because the wrapper script
  piped `run.ps1`'s stderr. It left no result. The server was restarted before the valid run.

## FR-13's nine threads (`threads.json`, 18:30–18:53, server stopped)

| expected-answer match | before (3 November) | **now** |
|---|---|---|
| first turn | 7/11 | 6/11 |
| with history | 1/9 | **2/9** |
| cold | 1/9 | 1/9 |
| spelled out | 3/9 | **6/9** |
| schema conformance, every response | 92.5% | **100% (38/38)** |
| out of scope | 0 | **0** |

- **t04's follow-up resolved with history** for the first time ("history works").
- **Follow-ups that need the earlier turn still mostly fail.** Spelled out, twice as many are
  answered, so generation improved more than the use of history did.
- **The cold runs had 4 fabricated identifiers in 20 statements.** Verification removes these before
  an answer is returned (invariant 5). It was 0 before.
- **t06 and t07, asked by the Employee,** were answered, as before, from material the Employee may
  read. This is no leak.

## The HTTP check (`http_check.json`, 18:54–18:58, fresh server)

- **WIRED for all three threads** (t03 and t04 as the Employee, t06 as the Administrator), with 0
  leaks. The asks were at least 12.48 s apart.
- **t04's second turn was answered correctly through the server,** where all three failed on 3
  November.
- **The users table:** throwaway passwords were set for `corpus.admin@example.com` and
  `corpus.employee@example.com` at 07:54:39Z, from environment variables in the run's own shell.
  They were shown to the user once and recorded nowhere.
