# FR-13's follow-up clause on Haiku 5.5, with repeated draws: 11 November 2026

The re-audit of 11 November read FR-13's follow-up clause on the default provider as "partial
and unconfirmed": 9/9 with history, but on one draw per model, with no noise band measured on
this provider and no HTTP check on Haiku (D-112's note of 11 November, the verdict's section
(b)). Claude takes no temperature (D-115), so one draw cannot carry "met". The user decided
"record now, draws later", and started this run as a task of its own.

**This file was committed before any call of this run,** so the rule below was fixed before any
result was seen. The results are added below it afterwards, and the rule is not edited then.

**The user chose the rule on 11 November,** from three put to him as a tabbed question:

- this one, which was the recommended choice: the re-audit's bar on every draw, and no follow-up
  missing twice;
- the re-audit's bar as written, with no condition across the draws;
- 9/9 on every draw.

## The configuration under test

The default since D-122, exactly as draw 1 ran it:

- **Generation:** `claude-haiku-5-5`, effort `"low"`, thinking at the model's default, no sampling
  parameters, `CLAUDE_MAX_TOKENS` 16000.
- **Embeddings:** Voyage `voyage-4` at 1024.
- **Values:** D-120's threshold 0.2687 and floor 0.2468, applied by the code, nothing patched.
  `MAXIMUM_STATEMENTS` 6, `MAXIMUM_CONTEXT_TOKENS` 4000, `TOP_K` 25.
- **Database:** `kmp_voyage_20261110`, at dump `80ff46d4…`. Nothing is restored, dropped or
  re-indexed for this run.
- **The set:** `corpus/objective-02/threads.json`, sha256 `acfe3d47…`, scoring rule version 2,
  frozen and unedited.
- **The code:** the answer path is byte-identical from draw 1's commit `e04aab1` to this branch.
  `apps/ai/anthropic.py` gained only transcription (D-123), and `apps/core/constants.py` changed no
  value FR-13 reads.

## The three draws

| | when | commit | record |
|---|---|---|---|
| draw 1 | 10 November | `e04aab1` | `../../2026-11-10/haiku/threads.json` |
| draw 2 | this run | this branch | `../haiku-draw-2/threads.json` |
| draw 3 | this run | this branch | `../haiku-draw-3/threads.json` |

- **Draw 1 is already made:** with history 9/9, 0 leaks, 0 fabricated identifiers. It counts as it
  stands. Its bar was fixed before it too, in `../../2026-11-10/haiku/haiku-round.md` at `0f184ca`,
  and it is the bar below.
- **Draws 2 and 3 use the same tool, unchanged:**
  `../../2026-11-10/haiku/citation_harness_haiku.py`, with `--threads`, the dump hash and a new
  `--out`. Each is 44 runs, in-process, with no server.
- **They run one after the other, once each.**

## The bar for each draw

All three hold, read from the record's own fields, over all 44 runs:

| | bar | field |
|---|---|---|
| 1. with history, expected-answer match | at least 8 of the 9 answerable follow-ups | `summary.per_way["with-history"].expected_answer_match` |
| 2. leaks | 0 | `summary.out_of_scope_total`, and every run's `score.leaks` |
| 3. fabricated identifiers | 0 | each way's `fabricated_identifiers` |

- **This is `haiku-round.md`'s bar,** applied to every draw, as the re-audit suggested. It allows
  one miss in nine because one run is a noisy sample.
- **The two scoped Employee follow-ups** (t06 and t07, which should be declined) are judged by the
  leak bar. An answer there from material the Employee may read is not a leak. It would be reported
  by name as FR-12's decline behaviour (D-110), and it would not fail this rule.
- **An unavailable run** (three failed attempts) is scored as the frozen rule scores it: not
  correct.

## One more condition, across the draws

**No follow-up may miss with history in more than one of the three draws.**

- **Why.** Repeated draws exist to tell noise from a failure that repeats (D-103). A follow-up
  that misses twice in three draws fails more often than it works. Recording "met" over it would
  overstate the result, even if every draw still scored 8/9.
- **t09 is exempt.** Its frozen prediction is that it fails with history, because its referent is
  only in the earlier answer, and answers are never passed (D-42). Its miss is D-42's recorded
  deviation, not the resolving half this rule reads. In draw 1 it matched through retrieval, not
  memory. A t09 miss still uses its draw's one allowed miss.

## The HTTP check on Haiku

One run of `../haiku-http-check/conversation_http_check_haiku.py`, through a freshly started
Waitress (D-85's command, `DEBUG` off), after draw 3. Its bar:

| | bar | Sonnet, 10 November |
|---|---|---|
| verdict | WIRED 3 of 3 | 3 of 3 |
| leaks | 0 | 0 |
| turn two correct, by the frozen rule | at least 2 of 3 | 3 of 3 |

- **WIRED and no leak is the check's own exit rule.** Turn two's score is added because WIRED
  compares only the passages retrieved. Only the reply shows that the history block reached the
  prompt through the server.
- **A MISMATCH is not explained away.** Voyage's scores jitter, and t04's and t06's composed sets
  sit within that jitter of the context cut (`../../2026-11-10/voyage-http-check/voyage-http-check.md`).
  A MISMATCH would be reported with the record's margins and `history_effect.py`'s reading. The
  check would then have fallen short, and what follows is the user's decision.
- **The server record.** `scripts/server_record.py` no longer records process 0 as the listener
  (`6124822`). The listener, its command line and its start are also observed separately, in
  `../haiku-http-check/server_observed.txt`.

## How the result is read

- **If all three draws pass, no follow-up misses twice, and the HTTP check passes:** the resolving
  half of FR-13's follow-up clause ("so that pronouns and abbreviated references resolve
  correctly") is recorded as **met on `anthropic`** (Haiku 5.5 with `voyage-4`), on three draws.
  D-42 stays a recorded deviation: prior questions are passed, never prior answers.
- **If any draw falls short, or a follow-up misses twice:** FR-13's follow-up clause is **partial
  on `anthropic` too**, with the band reported. Whether that is accepted as a deviation is the
  user's decision, as D-112 was for FLM.
- **If the draws pass and the HTTP check falls short:** the draws are recorded with their numbers.
  "Met" is not recorded, and the user decides what follows.
- **Either way this is not an audit verdict.** FR-13 stays INCOMPLETE until `requirements-auditor`
  reads it again. "Reachable from any page" has no front-end test yet, and that is another task.

## The band

Reported whatever the result, by `compare_draws.py`, which was committed with this file:

- **Per way** (first turn, with history, spelled out, cold): the matches in each draw, and their
  range.
- **Per run:** which of the 44 changed outcome or correctness between draws, and whether the
  supplied passages were the same when it did. D-103 measured FLM's band this way.
- **Retrieval:** how many runs were supplied a different set or order of passages, and the largest
  score difference for one passage.

Three draws give this provider's first measured band. They do not bound it.

## What stops the run

- **A gate that refuses, or a run that ends without a record:** stop and report. Nothing is run
  again for a better number.
- **A failed prediction is reported as measured.**
- **Spend:** two thread draws and one HTTP check, about $0.06 of Claude credit, approved by the
  user for this run (D-113). Anything more is asked for first. Voyage's embeddings are on its free
  tokens.

## What a pass would not show

Written now, so it is not softened later:

- **Reliability beyond three draws.**
- **Anything from t08.** It is the topic change, answerable cold by design.
- **That a reference into an earlier answer resolves.** D-42 passes questions only, and no frozen
  follow-up has a referent that is in an answer and in no passage the joined questions retrieve.
- **Abbreviated references** beyond pronouns and demonstratives. No frozen follow-up uses a
  shortened name or an acronym.
- **Threads longer than two turns.**
- **Which model snapshot answered.** The records hold the configured name, `claude-haiku-5-5`, not
  an identifier the API returned. Draw 1 is a day older than draws 2 and 3.

---

## Results, added after the runs (11 November 2026, 19:18–19:25)

**The rule is met.** All three draws pass, no follow-up missed in any draw, and the HTTP check
passed its bar. So the resolving half of FR-13's follow-up clause is read as **met on `anthropic`**
(Haiku 5.5 with `voyage-4`), on three draws. D-42 stays a recorded deviation. Everything above
this line is unchanged since `049fefe`.

- **`compare_console.txt`** holds the tables below, read from the three records by
  `compare_draws.py`, which applies the rule and was committed with it.
- **`draw_details.txt`** holds the details quoted here. `draw_details.py` was written after the
  draws and applies no bar.

### The three draws

| | bar | draw 1 | draw 2 | draw 3 |
|---|---|---|---|---|
| recorded | | 10 Nov, 19:38 | 11 Nov, 19:19 | 11 Nov, 19:21 |
| commit, with no uncommitted tracked change | | `e04aab1` | `bf384b2` | `bf384b2` |
| first turn | | 11/11 | 11/11 | 11/11 |
| **with history** | at least 8/9 | **9/9** | **9/9** | **9/9** |
| spelled out | | 9/9 | 9/9 | 9/9 |
| cold | | 1/9 | 1/9 | 1/9 |
| scoped Employee follow-ups declined, with history | | 2/2 | 2/2 | 2/2 |
| **leaks** | 0 | **0** | **0** | **0** |
| **fabricated identifiers** | 0 | **0** of 59 | **0** of 52 | **0** of 50 |
| schema conformance, unavailable runs | | 37/37, 0 | 37/37, 0 | 37/37, 0 |
| scoping shown, t06 and t07 | | yes, yes | yes, yes | yes, yes |
| **the draw** | | **passes** | **passes** | **passes** |

**A follow-up missed in more than one draw:** none. No follow-up missed in any draw.

- **Every record names the same things:** `kmp_voyage_20261110` at dump `80ff46d4…`,
  `claude-haiku-5-5`, `voyage-4` at 1024, 0.2687 and 0.2468, the thread set `acfe3d47…` and rule
  v2. The 44 questions, retrieval strings and prompts are the same, run for run.
- **Draws 2 and 3 ran in-process,** with `../../2026-11-10/haiku/citation_harness_haiku.py`
  unchanged: no diff from `e04aab1`.

### The readings per follow-up, the same in every draw

| follow-up | kind | reading, draws 1, 2 and 3 | cited, with history |
|---|---|---|---|
| t01, Employee | ordinary | history works | D01 |
| t02, Employee | ordinary | history works | D07 |
| t03, Employee | ordinary | history works | D12 |
| t04, Employee | ordinary | history works | D19 |
| t05, Employee | ordinary | history works | T03 |
| t06, Administrator | scoped | history works | T02 |
| t06, Employee | scoped | not answered by any way | nothing: declined |
| t07, Administrator | scoped | history works | D09 |
| t07, Employee | scoped | not answered by any way | nothing: declined |
| t08, Employee | topic change | cold-answerable: proves nothing about history | D03 |
| t09, Employee | previous answer | history works; the prediction did not hold | D17 |

- **t09 matched in all three draws, through retrieval, not memory.** Its frozen prediction is a
  miss. Each time the joined questions ranked D20 first and admitted D17 third (0.339), and Haiku
  answered from D17, which names the facilities team itself. The earlier answer was never passed
  (D-42).
- **The seven that show pronouns resolving** are t01 to t05, and t06 and t07 asked by the
  Administrator: correct with history and not correct cold, in every draw.

### The band: this provider's first measured one

| way | matches in draws 1, 2, 3 | range | spread |
|---|---|---|---|
| first turn | 11, 11, 11 | 11 to 11 of 11 | 0 |
| with history | 9, 9, 9 | 9 to 9 of 9 | 0 |
| spelled out | 9, 9, 9 | 9 to 9 of 9 | 0 |
| cold | 1, 1, 1 | 1 to 1 of 9 | 0 |

- **No run changed outcome or correctness:** 0 of 44, across the three draws. On FLM, D-103
  measured one of 44 flipping between two draws of identical code, and D-112 records 2/9, 3/9 and
  2/9 with history.
- **The draws are real repeats, not replays.** The verified statements differ in wording or count
  in 21 of the 44 runs: 7 first turns, 5 with history, 6 spelled out and 3 cold. Output tokens
  were 8,958, 8,596 and 8,053. Two of those runs also cite a different set of passages, one
  spelled out and one cold, and none with history.
- **Retrieval moved, and never across a cut.**
  - No run was supplied a different set of passages in any draw.
  - One run was supplied the same set in another order: t09 with history, where two D04 passages
    that score within 0.0001 of each other swapped in draw 3.
  - The largest score difference for one passage was 0.00142 (t02's first turn, between draws 1
    and 3). Between draws 2 and 3, made two minutes apart, it was 0.00086. Both are more than the
    0.00047 and 0.00072 measured on 10 November.
  - In each pair of draws, 22 of the 37 runs that were supplied a passage have exactly the same
    scores.
- **What the band is.** Zero spread over three draws, at the ceiling, on a set of nine. It shows
  that no result here rests on one lucky draw. It does not bound the variation: three draws
  cannot show a miss that happens one time in ten.

### The HTTP check on Haiku (`../haiku-http-check/`)

| | bar | Sonnet, 10 November | **Haiku, 11 November** |
|---|---|---|---|
| verdict | WIRED 3 of 3 | 3 of 3 | **WIRED 3 of 3** |
| leaks | 0 | 0 | **0** |
| turn two correct, by the frozen rule | at least 2 of 3 | 3 of 3 | **3 of 3** |
| smallest gap between asks | | 7.0 s | 7.0 s |
| seconds per ask | | 2.5 to 3.1, after 13.2 | 1.7 to 3.5, after 10.4 |

- **Commit:** `0dd05c6`, with no uncommitted tracked change. Recorded at 19:23:39.
- **t03, as the Employee:** turn two gave Ridgeline Catering's contact, from the vendor register.
- **t04, as the Employee:** the logbook rule, from the fleet notes.
- **t06, as the Administrator:** "three suppliers account for almost half of the organisation's
  spend", from the board risk committee transcript.
- **The server supplied exactly the passages in-process retrieval gives for the composed string,**
  in the same order, in all three threads. Both rows of every thread hold the questions as asked
  (D-42), and each thread reads back with two turns.
- **No verdict here can have come from the jitter.** A history-blind server would need the bare
  follow-up's ranking to move by 0.037 (t03), 0.217 (t04) and 0.222 (t06). The largest score
  difference seen between any two draws is 0.00142, so two scores can move apart by 0.0028.
  `history_effect.py` is a byte-identical copy of 10 November's and still prints the older bound,
  0.00094.
- **The composed sets of t04 and t06 still sit within the jitter of the context cut** (margins
  0.0003 and 0.0004). The server and both in-process passes agreed here, as they did on
  10 November. A future run could still show a MISMATCH there that is jitter.

**The server, observed this time.** Section (c)'s defect 1 did not recur.

- **The record's own server block:** Waitress 3.0.2, read from the venv the command line runs
  from; 24 threads, from `--threads` on that command line; pid 28208, started 08:23:05Z; `DEBUG`
  off. The lookup found the listener, so the guard added at `6124822` was not exercised.
- **`server_observed.txt`,** written before the check: one socket row on port 8000, in state
  Listen, owned by pid 28208; that process's command line; the launcher and the shell that started
  it; and the log's one "Serving on" line, at 19:23:06.
- **`server_settings.txt`,** written by the shell that then started Waitress: the server ran
  `claude-haiku-5-5` on `kmp_voyage_20261110`. The check's record names the model the check
  process was configured with, and the attempt log names no model, so this file is the evidence of
  the server's model.
- **The command** was D-85's as it stands since D-124: `waitress-serve --listen=127.0.0.1:8000
  --threads=24 --max-request-body-size=54525952 config.wsgi:application`.
- **Nothing else was on port 8000.** It had no socket row before the start, and none after the
  server was stopped at 19:24:45.

**The accounts.** `run_http_check_with_accounts.py` set throwaway passwords on
`corpus.admin@example.com` and `corpus.employee@example.com` at 08:23:35Z.

- They were made in memory and passed to the check in its environment. They were never printed or
  written.
- At 08:24:32Z both original hashes were written back, and both read back as the originals.
  `state_before.txt` and `state_after.txt` show the same hash mark for each account.

### What the run wrote

- **To the copy, through the server:** 3 Conversation rows, 6 QueryLog rows and 10 AnswerCitation
  rows, plus 2 sessions and the two accounts' last-login times. None is a retrieval candidate
  (D-86 decision 6).
- **The corpus is unchanged:** 23 documents, 5 meetings and 43 chunks, all `voyage-4` at 1024.
- **The two thread draws wrote nothing** to the database.
- **The copy now holds** 6 conversations and 12 QueryLog rows: six from 10 November's HTTP check
  and six from this one.
- **`snapshot.json`** is a copy of the snapshot record at
  `C:\kmp-measurement\2026-11-10-voyage\snapshot\`. The dump's SHA-256 was recomputed before the
  draws and is the record's, `80ff46d4…`. No snapshot record for this dump was in the repository
  before (section (c), defect 3).

### Spend

| | calls | input tokens | output tokens | about |
|---|---|---|---|---|
| draw 2 | 37 | 188,557 | 8,596 | $0.0232 |
| draw 3 | 37 | 188,557 | 8,053 | $0.0229 |
| the HTTP check | 6 | 30,476 | 1,529 | $0.0038 |
| **this run** | **80** | **407,590** | **18,178** | **$0.050** |

- **Every call parsed on its first attempt.**
- **The counts are the replies' own** for the draws, and the server's attempt log's for the check.
  The Console's figure governs.
- **The approved amount was about $0.06** (D-113). Draw 1 cost $0.0233 on 10 November, so the
  three draws together cost about $0.069.
- **Voyage:** the questions' embeddings are on its free tokens.

### What the result does not show

The list written before the run stands, under "What a pass would not show". To it, from what was
seen:

- **Three cold follow-ups are answered, not declined, in every draw.** t02, t04 and t09 asked cold
  were each answered from another source (D04, D04 and D05), with genuine citations about a
  different referent. All score not correct, as predicted, and no bar is affected. Cold is not a
  path FR-13 uses, because it sends the history. A user can still ask a standalone question that
  vague, and that is FR-12's decline behaviour (D-110), not this clause.
- **The band was measured at the ceiling.** Every way scored the same in every draw. A set this
  small, on which the model does not miss, cannot show how wide the band is on harder follow-ups.
- **Draws 2 and 3 were made two minutes apart, a day after draw 1.** The records hold the
  configured model name, not a snapshot identifier.
- **The lookup that failed on 10 November worked today,** after the laptop restarted at 17:07. So
  this run does not show the guard for process 0 working on a live server. Its two tests do.
- **Nothing was measured on FLM.** D-112's acceptance for the FLM build is unchanged.

### What was not planned

- **The laptop restarted at 17:07,** between this run's preparation and its draws, and Docker
  Desktop was not running. The user approved starting it. The container `kmp_prototype-db-1` was
  started as it was. Nothing was restored, dropped or re-indexed, and `state_before.txt` was read
  after that start.
- **The consoles of draws 2 and 3** (`threads.txt`) were captured in the Windows code page, so the
  dash in each header line is not valid UTF-8. The records (`threads.json`) are unaffected.
- **`origin/main` was merged into the branch** (`9aeb804`) before the rule was committed. It
  brought #88's and #89's run folders and notes, and no change to the answer path.

### Files

- **`haiku-draws/`:** this file; `compare_draws.py` and `compare_console.txt`; `draw_details.py`
  and `draw_details.txt`; `state_check.py`, `state_before.txt` and `state_after.txt`;
  `snapshot.json`.
- **`haiku-draw-2/` and `haiku-draw-3/`:** `threads.json`, the record, and `threads.txt`, the
  console.
- **`haiku-http-check/`:**
  - `conversation_http_check_haiku.py` and its whole diff from 10 November's copy, which is the
    model;
  - `http_check.json` and `http_check.txt`, the record and the check's console;
  - `run_http_check_with_accounts.py` and `driver_console.txt`;
  - `start_server.ps1`, `server_settings.py` and `server_settings.txt`;
  - `observe_listener.py` and `server_observed.txt`;
  - `history_effect.py` and `history_effect.txt`;
  - `attempts.log` and `waitress.log`, copies of the server's two logs. It wrote no `errors.log`
    and no `audit.log`.
- **The server's own logs** stay outside the checkout, in
  `C:\kmp-measurement\2026-11-11-haiku-draws\logs\http-check\`.
