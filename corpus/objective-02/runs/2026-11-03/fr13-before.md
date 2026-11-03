# FR-13 end to end, the "before": 3 November 2026

Step 5 of the user's post-M6 order. D-86's measurement of FR-13, run before anything changes
answer generation (step 7). `docs/measurement-runbook.md` step 12, under D-86 and D-87. The
measured reason D-91 waited for.

## What ran

| | Thread run (12a) | HTTP check (12b) |
|---|---|---|
| Script | `scripts/citation_harness.py --threads` | `scripts/conversation_http_check.py` |
| When (local, +11:00) | 22:15:59 to 22:24:52, 8.7 minutes | 22:25:32 to 22:27:19 |
| Server | none, in-process (D-85 §4) | Waitress 3.0.2, 24 threads, `DEBUG` off, observed; started fresh at 22:25:10 |
| Exit | **1**: schema conformance 92.5%, below 95% | **0**: WIRED 3 of 3, 0 leaks |
| Record | `threads.json`, console in `threads.txt` | `http_check.json`, console in `http_check.txt` |

Both runs recorded:

- **Commit** `2f65a8e` (main after #46), with no uncommitted tracked changes;
- **FLM** v0.9.39 (CLI and server), and `check_flm.py`'s gate passing in each run;
- **Dump** `3bf98403354dbabceb54052b99b45a25f5f39d4fd685cca1e07233aa1e166f59`;
- **Database** `kmp_obj02_20261101`. The corpus gate found exactly the manifest's 25 items: 20
  indexed documents and 5 meetings, in 43 chunks. The other 3 documents are the manifest's
  deliberate failures, with no chunks;
- **Thread set** `corpus/objective-02/threads.json`, SHA-256 `acfe3d47…aee87`, frozen 1 November,
  scored by rule version 2.

**Conditions.**

- **The laptop was kept quiet,** by the user's agreement, and no agent was running.
- **The alpha was stopped** from 22:15:47 to 22:27:40, so the HTTP check could have port 8000.
  Both times are lines in `Documents\KMP-alpha-deployments.txt`.
- **Nothing was measured on the alpha.**

## Deviations from the runbook, all recorded

- **The evidence folder is dated by the day of the run, 2026-11-03.** The database, media and logs
  are the 1 November ones (`C:\kmp-measurement\2026-11-01`). The runbook's step 1 block derives
  both from one date, so it was not pasted as written; every variable it sets was set to the same
  value by hand. The user chose this folder.
- **Both runs were launched from Git Bash, with the same environment variables,** not from a
  PowerShell window. The measurement server was started in its own PowerShell window, from a
  script equal to steps 1 and 5. It also checks the database name before starting Waitress.
- **`PYTHONIOENCODING=utf-8`** was set, so each console could be kept as a UTF-8 file.

## The users table changed after the snapshot

- **2 November, step 1 (D-89):** the 21 load-test accounts' passwords were made unusable. The rows
  are kept.
- **3 November, 11:25:31Z, for the HTTP check:** `corpus.admin@example.com` and
  `corpus.employee@example.com` were given throwaway passwords. They were set from environment
  variables in the run's own shell, shown to the user once, and are recorded nowhere. Until then
  nobody knew those accounts' passwords.
- **The HTTP check's sign-ins** wrote sessions, the two accounts' last-login times and audit lines.
  Its asks wrote 3 conversations, 6 `QueryLog` rows and their citations. None is a retrieval
  candidate, and the corpus is unchanged.

## Disclosed: these threads were run before, informally

**The 1 November screen ran these threads already** (D-91,
`corpus/demo/screening-2026-11-01.json`):

- with history only;
- on `kmp_demo_screen`, a different corpus, with D21 and T06 added;
- with its per-trial verdicts not stored.

**This is the first run on the corpus the set is frozen against,** all three of D-86's ways.
Nothing was tuned between the two runs, and the set was not edited.

## Results

### The thread run, per way (scoring rule v2)

| Way | Answered, where expected | Expected-answer match | Not answered, where none expected | First-attempt conformance | Out of scope |
|---|---|---|---|---|---|
| First turn (11) | 10/11 | 7/11 | — | 11/11 | 0 |
| With history (11) | 8/9 | **1/9** | 0/2 | 11/11 | 0 |
| Cold (11) | 4/9 | 1/9 | 2/2 | 4/5 | 0 |
| Spelled out (11) | 7/9 | 3/9 | 1/2 | 11/11 | 0 |

- **Schema conformance, every response:** 37/40 (92.5%). The three failures are one run, t04 cold.
  Every attempt gave a statement with an empty `chunk_id`, so that run was unavailable after 3
  attempts (NFR-19's rule). That is the harness's exit 1.
- **Fabricated identifiers:** 0, in every way.

### Per follow-up

| Thread, role | Turn 1 | With history | Cold | Spelled out | The harness's reading |
|---|---|---|---|---|---|
| t01, Employee | correct | not correct | not correct | **correct** | not resolved with history |
| t02, Employee | correct | not correct | not correct | not correct | a retrieval or generation limit, not history |
| t03, Employee | **not correct** | not correct | no answer (path A) | declined (path B) | a retrieval or generation limit, not history |
| t04, Employee | correct | not correct | unavailable | not correct | a retrieval or generation limit, not history |
| t05, Employee | declined | declined | no answer (path A) | **correct** | not resolved with history |
| t06, Administrator | correct | not correct | no answer (path A) | not correct | a retrieval or generation limit, not history |
| t06, Employee (no-answer expected) | correct | answered: not correct | no answer: correct | answered: not correct | "answered by a role that cannot see the source's item": checked below, **not a leak** |
| t07, Administrator | not correct | not correct | no answer (path A) | declined (path B) | a retrieval or generation limit, not history |
| t07, Employee (no-answer expected) | not correct | answered: not correct | no answer: correct | declined: correct | the same check, **not a leak** |
| t08, Employee (topic change) | correct | correct | correct | correct | cold-answerable: proves nothing about history |
| t09, Employee (previous answer) | correct | not correct | not correct | not correct | **expected to fail** (D-86 decision 2), and failed |

**Scoping was not shown for t06 or t07:** neither of the Administrator's follow-ups was correct,
so there was no answer to withhold from the Employee.

### The HTTP check

- **WIRED for all three:** t03 and t04 as the Employee, and t06 as the Administrator. The server's
  second-turn `QueryLog` row supplied exactly what `compose(follow-up, [first question])` retrieves
  in-process, and not what the follow-up alone retrieves.
- **No leak**, and the asks were at least 7.89 s apart.
- **All three second turns were answered, and none was correct:**
  - t03 restated turn 1;
  - t04 restated turn 1, then listed records-management duties;
  - t06 restated turn 1.

### The two "check for a leak" readings: not leaks

The Employee's follow-ups in t06 and t07 should get no answer, because their sources are
Administrator-only: T02 for t06, and D09 for t07.

| Thread | What the Employee's reply said | Where the text is from | Cited as | The restricted fact |
|---|---|---|---|---|
| t06 | "Suppliers are reviewed annually against price, delivery performance and quality." | D12, chunk `db6d9ae4`, stamped `['Employee', 'Administrator']` | D05, which the Employee may read | "three suppliers… almost half" (T02): **absent** |
| t07 | "A weekly update will be published on the intranet until the move is complete." | D20, chunk `f75351f0`, stamped `['Employee', 'Administrator']` | T01, which the Employee may read | "Project Atlas… knowledge platform" (D09): **absent** |

- **No out-of-scope passage reached any prompt:** the harness counted 0 in every way.
- **Each reply restates the first turn,** from material the Employee may read. So the failure is
  answering when it should not, the same one D-91 recorded from the screen, and not a leak.

## What it shows about FR-13

- **The history is wired.** It changes what is retrieved, both in-process and through the server
  (3 of 3 WIRED). With history, the expected source ranked first for t01, t02, t03, t04 and t05.
- **Follow-ups that rely on the earlier turn are still not answered.** With history, 1 of 9
  answerable follow-ups matched, and that one is t08, which is cold-answerable.
- **The reply mostly restates the first turn.** Of the 9 answered with-history runs other than
  t08, 7 open with the first turn's answer (t01, t03, t04, t06 in both roles, t07 in both roles).
  The 1 November screen saw the same.
- **Spelled out, 3 of 9 matched.**
  - **Where spelling the question out works but history does not:** t01 and t05. History is where
    those two fail. t05's first turn was declined, so it is confounded.
  - **Where spelling it out fails too:** t02, t03, t04, t06 (Administrator), t07 (Administrator) and
    t09. The limit is not history alone.
    - In t02 and t04, the source was supplied at rank 1, and the reply was still not correct, so
      the limit is generation. t04's reply mentions logbooks, which are in D19, but it cites D04,
      and it leaves out the odometer.
    - In t06 as the Administrator, T02 ranked third and was not supplied, so the limit is
      retrieval.
- **FR-13 stays partial.** The thread is retained and re-scoped every turn (D-91). The follow-ups
  it exists for are not answered correctly on this model and prompt.

## Seen here, for step 7, not counted

- **A false statement passed citation verification.** t03's first turn, in both runs: "Lantern
  Grove Supplies is the preferred vendor for catering."
  - The cited chunk lists Lantern Grove Supplies for stationery, and Ridgeline Catering for
    catering.
  - Verification checks that the cited ID was supplied (invariant 5). Whether the passage supports
    the statement is the conceded limit.
- **Statements are cited to the wrong supplied passage.** In each case below, the statement's text
  comes from a different supplied chunk than the one cited. Every cited ID was supplied, so each
  passes verification:
  - t01 with history: D01's accrual sentence, cited to D10;
  - t04 with history: D19's driver rule cited to D04, and a D04 sentence cited to D19;
  - t06 with history: D12's review sentence, cited to D05;
  - t07 (Employee) with history: D20's sentence, cited to T01;
  - t09 spelled out: a room-booking rule, cited to D05.

  These were not counted across the run.
- **One run gave no conforming response in 3 attempts:** t04 cold, each with an empty `chunk_id`.
