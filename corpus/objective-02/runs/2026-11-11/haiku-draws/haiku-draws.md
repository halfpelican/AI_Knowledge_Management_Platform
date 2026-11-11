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
