# Objective 06 pre-measurement: do the draft thirty's risky asks reach a no-answer?

Run on 8 November 2026, 20:35 to 21:02, in process through `scripts/citation_harness.py` (the shipped
pipeline's own embed, rank, admit, generate and verify; nothing written to any log), from the main
checkout at commit `711fcda`, FLM v0.9.39 with `check_flm.py` passing before each run, on
`kmp_obj0506_20261101` restored from dump `3bf98403…6f59`. Question set:
`corpus/objective-06/pre-measurement-asks.json`, the 8 genuinely unanswerable asks and the 6
permission-only asks of the draft thirty. Three repetitions were planned; runs 1 and 2 completed
(`run1.json`, `run2.json`), run 3 was cut off after the FLM gate when the session ended (`run3.txt`
holds only the gate), so the table below is two runs, which agreed on every question.

**Why this was measured first.** Step 7's "after" (D-102's 8 November note) found the shipped
generation answers questions it should decline. A question that is wrongly answered is logged as
answered and never reaches the gap log, so Objective 06's first clause ("every genuinely unanswerable
query … must appear in the log") can fail for that reason alone.

## Result

| Id | Kind | Role | Top in-scope score | Outcome, both runs | What was cited |
|---|---|---|---|---|---|
| U01 | unanswerable, salary review | Employee | 0.346 | **answered** | D08 (onboarding) |
| U02 | unanswerable, salary review | Employee | 0.328 | no answer, path B (generation declined) | |
| U04 | unanswerable, corporate card | Employee | 0.327 | **answered** | D10 |
| U05 | unanswerable, corporate card | Administrator | 0.319 | **answered** | D02 |
| U07 | unanswerable, christmas shutdown | Employee | 0.415 | **answered** | D20 |
| U08 | unanswerable, christmas shutdown | Administrator | 0.332 | **answered** | D01 |
| U10 | unanswerable, jury duty | Employee | 0.250 | no answer, path A (nothing above 0.30) | |
| U11 | unanswerable, jury duty | Administrator | 0.408 | **answered** | D01 |
| P01 | permission-only, D09 | Employee | 0.286 | no answer, path A | |
| P02 | permission-only, D09 | Employee | 0.275 | no answer, path A | |
| P04 | permission-only, D16 | Employee | 0.387 | **answered** | D04 |
| P06 | permission-only, T02 | Employee | 0.259 | no answer, path A | |
| P07 | permission-only, T02 | Employee | 0.359 | **answered** | D05 |
| P08 | permission-only, T05 | Employee | 0.263 | no answer, path A | |

- **Genuinely unanswerable asks reaching a no-answer: 2 of 8** (U02, U10). Six are answered from
  readable material that does not answer them, with a real, in-scope citation. Every one of the six
  has an in-scope passage scoring between 0.32 and 0.42, so generation is reached, and generation
  answers.
- **Permission-only asks reaching a no-answer: 4 of 6** (P01, P02, P06, P08), all by path A: nothing
  the Employee may read clears 0.30, so these four will exercise FR-19's exclusion rule. P04 and P07 are
  answered from readable documents (D04, D05) that do not answer them; no out-of-scope chunk was
  retrieved for any of the six.
- **The searches** (U03, U06, U09, U12, P03, P05) were not run: keyword search is deterministic, and
  the measurement database's own 50 pre-existing search rows already show the five Employee searches
  for Administrator-only phrases at zero results.
- **Timing:** answered asks took 24 to 71 seconds each (median about 38 s); path-A declines took the
  embedding only.
- **No leak:** `out_of_scope_ids` is empty for every run.

## What this means for the draft thirty

As drafted, the gap log would receive, after one cycle, the four zero-result searches and two asks:
subjects "salary review" (U02 + U03, count 2), "jury duty" (U10 + U12, count 2), "corporate card"
(U06 only) and "christmas shutdown" (U09 only). Six genuinely unanswerable queries would be absent
from the log, not because FR-19 missed them but because FR-12 answered them. Clause 1 would fail on
the set as drafted, whatever FR-19 does. The cause is the open step 7 finding (D-102's note, carried as
an open finding by the item 10 audit), and nothing in this session changes generation.

The pattern in the scores is plain: a wording that shares the corpus's vocabulary ("leave", "office",
"card", "company") pulls an in-scope passage over 0.30 and the model answers from it; a wording
without that overlap (U10, P01, P02, P06, P08) stays under 0.30 and is declined before generation.
