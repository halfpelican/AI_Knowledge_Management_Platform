# The frozen thirty and the nine threads on Voyage with Claude: 10 November 2026

The two frozen sets, run on the `anthropic` provider with D-120's values, against FLM's
"after" on 8 November (`../../2026-11-08/after-030/`). The user approved the runs after #73
merged (D-113). This is evidence for the provider decision that CLAUDE.md section 4 leaves to
measurement. It is not that decision.

**Shared by every run:**

- **Commit:** `54f15cc` on `feat/FR-12-voyage-frozen-sets`, with no uncommitted tracked changes.
  That is `main` at `20f4375` plus two commits:
  - `8ecb2c6`, the miss-rows fix described below;
  - `54f15cc`, which adds this folder's harness copy.
- **Script:** `citation_harness_voyage.py`, a generated copy of `scripts/citation_harness.py` at
  `8ecb2c6`.
  - It changes only where FLM was named. `citation_harness_voyage.diff` is the whole difference.
  - A provider gate replaces the `check_flm.py` and FLM-version gates. It passed before each run.
- **Provider:**
  - Voyage `voyage-4` at 1024 embeds the questions, with `input_type` "query" (D-116).
  - Claude `claude-sonnet-5-5` generates (D-115).
- **Values:** threshold 0.2687 and partial-match floor 0.2468 for `voyage-4` (D-120), which
  every run applied, recorded per run. `MAXIMUM_STATEMENTS` 6, `TOP_K` 25,
  `MAXIMUM_CONTEXT_TOKENS` 4000.
- **The dump:** `80ff46d482d7d36029060e4afa2646ee9f07683331d35dbdb17b97fb6fc0d1e4`, the Voyage
  copy's own snapshot after its re-index, database `kmp_voyage_20261110`. The corpus gate found
  exactly the manifest's 25 items and 43 chunks, all `voyage-4`.
- **The sets:** both frozen and unedited.
  - `questions.json`, sha256 `9a059d1a…`
  - `threads.json`, sha256 `acfe3d47…`, scoring rule v2
- **Server:** none. Every run was in-process (D-85).
- **The laptop was not kept quiet** as it was for FLM.
  - The scores-only pass ran while this session's test suite was running. It measures scores,
    not time.
  - The two timed runs started after the suite exited at 15:55.
  - Claude's latency is network-bound, and other activity on the laptop was not controlled.

**Held out.** D-120's values were chosen on `dev-set-v2.json` alone, so neither frozen set
informed them. This is therefore a held-out test of the Voyage threshold and floor. FLM's 0.30
is not held out in the same way: D-101's note says the frozen thirty informed it. One
unrecorded two-question scores-only dry run checked the copy's gates first, and it informed
nothing.

## The frozen thirty (`harness.json`, 15:55–15:57, in-process)

`scores.json` is the recorded scores-only pass that came first.

| | FLM, 8 November (0.30 + cap 6) | **Voyage + Claude (0.2687 / 0.2468 + cap 6)** |
|---|---|---|
| ordinary answered correctly (expected answer, expected source) | 19/22 | **22/22** |
| ordinary left unanswered | 0/22 | **0/22** |
| scoped, answered for the role that can see the source | 4/4 | **4/4** |
| scoped, declined for the role that cannot | 1/4 | **4/4** |
| no-answer questions declined | 1/4 | **4/4** |
| runs right, all kinds | 25/34 | **34/34** |
| path A (nothing above the threshold) | 2 | 3 |
| first-attempt conformance | 32/32 | **31/31** |
| fabricated identifiers, leaks | 0 of 56, 0 | **0 of 30, 0** |
| answered question, median / p90 | 21.5 / 26.4 s | **2.5 / 4.5 s** |

**The finding: every run is right.** All 26 runs that expected an answer showed it, and all 8
that expected none were declined.

- **Three declines happened before generation** (path A): s01, s02 and s03 asked by the
  Employee. Their best in-scope scores were 0.152, 0.229 and 0.206.
- **Five were declined by Claude** (path B): s04 asked by the Employee, and n01 to n04. Claude
  was handed passages and proposed no statement each time, so verification removed nothing.
- **No out-of-scope chunk reached any prompt or answer** (invariant 1 holds).

**Where the gain comes from.** The embedder and the generator changed together, with the
threshold. The scores-only pass separates retrieval:

- **The expected source ranked first** in 26 of 26 answerable runs on Voyage, and 25 of 26 on
  FLM (q22 was second).
- **At each configuration's threshold, both admitted all 26 answerable runs.**
- **Voyage sent 5 of the 8 should-decline runs to generation, and FLM sent 6.** Retrieval took
  s02 and s03 out before generation, where FLM had sent them on and gemma3:4b answered. n02
  went the other way: FLM's 0.251 was under 0.30, and Voyage's 0.412 sent it on to Claude,
  which declined.
- **The rest is generation's.** q04, q15 and q17 had the expected source ranked first in both
  configurations. gemma3:4b cited the wrong sentences: the disposal check, a skills table, and
  the moving-day arrangements. Claude cited the answer each time. The five path B declines are
  Claude's too.

## The nine threads (`threads.json`, 15:57–15:59, in-process)

| expected-answer match | FLM, 8 November | **Voyage + Claude** |
|---|---|---|
| first turn | 6/11 | **11/11** |
| with history | 2/9 | **9/9** |
| cold | 1/9 | 1/9 |
| spelled out | 6/9 | **9/9** |
| schema conformance, every response | 100% (38/38) | **100% (37/37)** |
| fabricated identifiers | 4 of 20, all in the cold runs | **0 in every way** |
| out of scope | 0 | **0** |

- **"History works" for every follow-up the rule can read that way:** t01 to t05, t06 and t07
  asked by the Administrator, and t09. FLM got that reading for t04 alone.
  - **t08** is cold-answerable, so it proves nothing about history, as before.
  - **Cold stays at 1 of 9, as predicted.** A follow-up asked cold should mostly fail. Seven
    cold runs took path A.
- **t06 and t07 asked by the Employee were declined in every way.** On 8 November FLM answered
  them from material the Employee may read: no leak, but no decline either.
- **t09's prediction did not hold, and the reading needs care.** Its follow-up, "What do they
  have to approve?", refers to the facilities team. The team is named only in the first
  turn's answer, and history carries questions only.
  - With history, the joined text ("Who do I ask if I have questions about the office move? What
    do they have to approve?") ranked D20, the relocation announcement, first at 0.570.
  - It also admitted D17, the meeting-room booking rules and the turn's expected source, third
    at 0.339. Claude answered from D17's approval rule.
  - So the rule scores it correct, but the earlier answer was not used. Retrieval landed on the
    right topic.

## What the result does not show

- **One run of each set.** Claude takes no sampling parameters (`apps/ai/anthropic.py`), so a
  repeat may differ (D-40's run-to-run variance applies).
- **Both sets are at their ceiling** (34 of 34, 9 of 9). They have no room left to separate a
  better configuration, and the samples are small: 8 should-decline runs and 9 follow-ups.
- **Two components changed at once.** The table compares configurations, the proposal's §9.2
  production pair against the local one. The breakdown above says which part did what, as far
  as the scores-only pass can tell.
- **The times are one sequential in-process run.** They are not NFR-08, which is measured under
  5 VUs through the server and has not been run on this provider.
- **Answers are short:** 1 or 2 statements each, 30 over 26 answers. `MAXIMUM_STATEMENTS` (6)
  never bound, so this says nothing about the cap on Claude.

## The miss-rows fix found before the run (`8ecb2c6`)

- **The bug:** D-120 made the harness's `--threshold` default None, meaning the embedding
  model's own value. `miss_rows` compared each score with that None.
- **The consequence:** every full question-set run with a ranked miss would have raised
  `TypeError` at its end. That would come after every question had been asked and paid for,
  and before the record was written. FLM was affected too.
- **How it was caught:** reading the harness before this run, so nothing was lost. This run
  happened to have no misses.
- **The fix:** each result now records the floor it applied, and both records carry it.

## Spend

| run | Claude calls | input tokens | output tokens | at D-115's $2 / $10 per million |
|---|---|---|---|---|
| the frozen thirty | 31 | 129,232 | 2,444 | about $0.28 |
| the nine threads | 37 | 188,557 | 4,798 | about $0.43 |
| **both** | **68** | | | **about $0.71** |

- **The counts are the replies' own,** tallied by the copy's wrapper. The Console's figure
  governs.
- **Voyage's query embeddings** are on its free tokens and were not tallied: 34 for the
  scores-only pass, 34 for the thirty, 44 for the threads, and the dry run's 2.

## Not done here

Each of these needs the user's go-ahead:

- **The HTTP check through the server.**
- **NFR-08 under load.** Check the Console's rate limits first.
- **The provider decision itself.**

## Files

- `citation_harness_voyage.py`, `citation_harness_voyage.diff`: the copy that ran, and its whole
  difference from the original.
- `scores.json`, `scores.txt`: the recorded scores-only pass.
- `harness.json`, `harness.txt`: the frozen thirty.
- `threads.json`, `threads.txt`: the nine threads.
- `compare_voyage_flm.py`, `compare_console.txt`: the side-by-side tables above, read from both
  folders' records.
- The attempt log stays in `logs/`, which git ignores. It holds 68 lines, every one a
  first-attempt parse, with no warning and no error.
