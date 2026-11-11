# NFR-08, Objective 03's p90, on the anthropic provider, 10–11 November 2026: Claude Haiku 5.5 and Voyage at five users

**The result: a valid FAIL.** Run 6 measured a p90 of **4,673 ms against NFR-08's 4,000 ms** at five
concurrent users.
- That is over 24 answered replies, with no 503, no 429 and no queueing in Waitress.
- FLM's valid FAIL was **350,407 ms** (after-030, 8 November), so anthropic is about 75 times
  faster and still about 0.7 s over the target.

**Two earlier runs were measured and are not counted.**
- Run 1 measured 5,210 ms, and run 5 4,130 ms. Both are FAILs by k6's own figures, with k6's
  validity checks passing.
- Both were recorded INVALID by D-87's closing check, because the check could not see the
  listening socket on this laptop.
- Run 6 is the one valid record. It is valid because, before it, the user approved a change to
  how the copied tooling finds the listener; it is disclosed below. D-87's rules did not change.

`nfr08_summary.json` is run 6's summary, as `run.ps1`'s finalise step wrote it.
`nfr08_summary_run1.json` and `nfr08_summary_run5.json` are the two INVALID runs'.

## How it ran

| | |
|---|---|
| database | `kmp_obj02_anthropic_20261110`, item 3's fresh database (`objective-02-anthropic.md`), dump `6e514170…e6fc`. NFR-08 writes no document, meeting or chunk, so it needs no restore between runs (runbook step 11) |
| server | Waitress 3.0.2, `--listen=127.0.0.1:8000 --threads=24`, `DEBUG` off, started by the user in their own window with the run's environment. It was restarted before every run that reached k6 (D-87) |
| provider | `anthropic`: `claude-haiku-5-5` (D-121) for generation and `voyage-4` at 1024 for the question embeddings. D-120's 0.2687 and 0.2468. The user checked the Anthropic Console's rate limits first and found them above the load: about 27 calls and 165K input tokens in a minute |
| load | k6 v2.3.0, through `load/`: copies of `tests/load/run.ps1`, `common.js` and `nfr08_query_p90.js`, changed where FLM is named (each `.diff` beside it). 5 VUs share 25 iterations at a 7 s floor, after 5 logins and 2 warm-up asks, over the ten Employee questions of `common.js`. This is D-84's design, unchanged |
| the provider gate | `load/provider_gate.py`, in place of `flm version` and `check_flm.py`. It checks the configuration, both keys (never printed), the database and D-120's values, then makes a health call and one 1024-wide Voyage probe. It passed before every run |
| accounts | `loadtest01` to `05`, made or reset by `run_nfr08_with_accounts.py` with a CSPRNG throwaway password held only in memory, and retired after every run: unusable password, rows kept (D-89). k6 receives the password as `run.ps1` passes it, as an `-e` argument for the length of the run |
| commits | `0d4dd85` for runs 1 to 5. `154915c` for run 6, which adds the run-folder `load/server_record.py`. No uncommitted tracked changes for any run |

## The six attempts

| Run | When (local, 11 Nov) | Driver run from | Pre-flight | k6 | Closing check | Recorded | p90 | Answered | 503 / 429 | Claude |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 00:42–00:44 | this session | READY | ran | no listener found | **INVALID** | 5,210 ms | 23 of 25 | 0 / 0 | $0.0236 |
| 2 | 09:21–09:23 | the user's window | refused 3 times: no listener found | not started | — | not run | — | — | — | none |
| 3 | 10:00–10:02 | the user's window | READY, then the user stopped that invocation after 2 logins; the driver's next attempt was refused by the restart check | 0 asks | — | INVALID (0 asks) | — | — | — | none |
| 4 | 10:37–10:38 | the user's window | refused 3 times: no listener found | not started | — | not run | — | — | — | none |
| 5 | 10:43–10:45 | the user's window | READY | ran | no listener found | **INVALID** | 4,130 ms | 24 of 25 | 0 / 0 | $0.0235 |
| 6 | 13:14–13:16 | the user's window | READY | ran | **pid 46608, the same** | **valid FAIL** | **4,673 ms** | 24 of 25 | 0 / 0 | $0.0238 |

- **Only run 6 counts** (D-87).
- **Runs 1 and 5 are listed because they were measured.** k6's own validity checks passed, and
  the same Waitress PID served throughout each:
  - Win32_Process shows the listening PID alive from before the run's window until after it
    (`nfr08/run1/`, `nfr08/run5/`);
  - Waitress's log has no "Serving on" line inside either window.

  They bracket run 6's figure, at 4.1 to 5.2 s.
- **Each run's console, attempts log and Waitress log** are under `nfr08/run1/` to `nfr08/run6/`.
  The stopped invocation's summary is `nfr08/run3/interrupted_k6_summary.json`.

## Why runs 1 to 5 failed the check, and what changed for run 6

**The fault.** On this laptop (Windows 11, build 26300) the operating system's TCP table reported
Waitress's listening socket on 127.0.0.1:8000 with the wrong state, on and off, even while idle
and answering HTTP (`nfr08/run2/socket_table.txt`, `nfr08/run5/server_after_run.txt`):
- CIM showed state 0, which is undefined, or 1 (Closed), where 2 is Listen;
- `netstat -ano` showed no line, or CLOSED.

`scripts/server_record.py` finds the listener with `Get-NetTCPConnection -State Listen`, so it
found nothing. The listener's own row was always there: local 127.0.0.1:8000, remote port 0,
owned by the Waitress PID. Only its state was wrong. The Voyage session also traced run 4's
refusals to a period when another session's `runserver` had bound port 8000 that morning; that is
its finding, and it was not verified here.

**The change, approved by the user before run 6 (`154915c`).** It is a departure from the brief's
rule that copies change only where FLM is named, and it is disclosed as one.
- `load/server_record.py` is a copy of `scripts/server_record.py`, and the copied `run.ps1` calls
  it for both the pre-flight and the closing check. Its `listening_process` keeps the original
  lookup, then:
  - falls back to `netstat -ano` for one LISTENING PID;
  - then falls back to the port's own remote-port-0 row whatever state the OS reports. The row
    counts only when exactly one live PID with a readable command line owns it, which excludes
    PID 0, PID 4 and stale rows. This step was approved after netstat was seen reporting the
    serving socket as CLOSED;
  - retries every 10 s for up to about 60 s.

  Each try is printed in the console.
- **D-87's rule is unchanged.** The same PID must be listening before and after the run. A
  different PID, two candidates, or a "Serving on" line inside the window still invalidates. Only
  a lookup that found nothing stops being read as a different server.
- **Run 6 used the port-row fallback for both checks.** Both found pid 46608 with state 0 reported
  (`nfr08/run6/console.txt`).
- `scripts/server_record.py` on main is unchanged. Any measured run on this laptop with main's
  tooling, FLM's included, can meet the same fault.

## Beside FLM

| | FLM, after-030 (8 November) | **anthropic, run 6 (11 November)** |
|---|---|---|
| commit; database and dump | `19c98a8`; `kmp_obj02_20261101`, `3bf98403` | `154915c`; `kmp_obj02_anthropic_20261110`, `6e514170` |
| generation; embeddings | gemma3:4b on the NPU; embed-gemma | claude-haiku-5-5; voyage-4 |
| server | Waitress 3.0.2, 24 threads, `DEBUG` off | the same |
| verdict | valid FAIL | valid FAIL |
| p90 with 503s, against 4,000 ms | 350,407 ms | **4,673 ms** |
| p90, answered only; all replies | 350,407 ms; 350,407 ms | 4,673 ms; 4,670 ms |
| answered | 25 of 25 | 24 of 25 |
| 503s; 429s; queueing in Waitress | 0; 0; none | 0; 0; none |

**On FLM, one NPU answered one question at a time,** so five users queued for it (D-95). On
anthropic nothing queued, and the time is the generation itself:
- run 6's 27 generation calls took 1.6 to 4.8 s, with a median of 2.1 s;
- every call parsed on its first attempt, with no retry;
- the slowest calls are the questions with about 8,000 input tokens and about 1,000 output tokens,
  thinking included at effort `"low"` (D-115);
- those calls, plus embedding, retrieval and HTTP, set the p90.

**The unanswered ask** in runs 1, 5 and 6 is always "How do I make a complaint?". Haiku declined it
at generation (path B, an empty statement list, nothing rejected): 2 of 2 times in run 1, 1 of 2 in
run 5 and 1 of 2 in run 6. FLM answered it. NFR-08's p90 counts answered replies and 503s, so the
decline does not enter the figure. It is an FR-12 observation, recorded rather than fixed.

## What this result does not show

- **The p90's spread across runs.** There is one valid run. The two measured INVALID runs, at 4.1
  and 5.2 s, suggest it sits near the target and moves run to run.
- **Whether a setting would bring it under 4 s.** No other effort, cap or model was tried.
- **NFR-09**, twenty users. It was not run.
- **A single-user baseline on this provider.** The summary's 8.9 s is FLM's, which the k6 script
  reports as written. It was not measured on anthropic.
- **The account tier under a heavier load.** The limits cleared this load, and no provider 429 was
  seen.

## Spend

| | |
|---|---|
| Claude (Haiku 5.5) | runs 1, 5 and 6: 81 calls, 495,610 tokens in and 42,718 out, about **$0.071** in all, summed from the server's attempts log (`nfr08/run*/attempts.log`). Runs 2, 3 and 4 made no Claude calls |
| Voyage (voyage-4) | 81 question embeddings in those runs, plus each provider gate's probe. Within Voyage's free allowance |
