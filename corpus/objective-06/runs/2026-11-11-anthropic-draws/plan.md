# FR-12's decline weakness on anthropic: the plan and the scoring rule, committed before any draw

Written on 11 November 2026, before the first draw. It is not edited after a draw has run. Anything
that turns out differently is recorded in the write-up, beside this plan.

## What D-110 names, and who runs which half

D-110 names the acceptance test for any future decline fix as "an unscreened re-run of the draft's
original eight wordings (`pre-measurement-asks.json`) and of these thirty". Its 10 November note says
that on `anthropic` the thirty become an unscreened test, and that the seeding is repeated and
reported per draw, because Claude's generation is not deterministic (D-115).

| Half | Who runs it | How | Draws |
|---|---|---|---|
| `corpus/objective-06/pre-measurement-asks.json`: the 8 original unanswerable wordings and the 6 permission-only asks | this branch | `pre-measurement-asks/citation_harness_fr12_declines.py`, a copy of D-121's Haiku harness changed only where its database is named (`.diff` beside it), on `kmp_fr12_declines_20261111` | 5 (the user's decision, 11 November) |
| `corpus/objective-06/queries.json`, the frozen thirty (SHA-256 `e40a589c…1462`) | the Objectives 05/06 session: #86's draw 1, and two more draws it owns (the user asked it on 11 November) | the seeding copy of `scripts/seed_objective06_queries.py`, through the shipped `answer_question` and `search` | 3. This branch scores them from that session's committed records and per-draw QueryLog exports, and runs no seeding of its own (the user's decision, 11 November) |

## The database for the harness half

`kmp_fr12_declines_20261111` is a NEW database, made with
`scripts/snapshot_measurement_db.py restore --database kmp_anthropic --into kmp_fr12_declines_20261111`
from `C:\kmp-dev\kmp_anthropic\snapshot` (dump `8e79cb37…`). That is the 1 November corpus
re-indexed by voyage-4 into 43 chunks (D-122). Its media go into a new
`C:\kmp-measurement\2026-11-11-fr12-declines\media`. `kmp_anthropic` itself is not touched. Before
the first draw, the chunks are checked as voyage-4 at 1024. The harness's own corpus gate also
checks them against `corpus/objective-02/manifest.json`.

The harness reads the database and never writes to it. So every draw starts from the same state,
and nothing is restored between draws.

## Each draw

    .venv\Scripts\python.exe corpus\objective-06\runs\2026-11-11-anthropic-draws\pre-measurement-asks\citation_harness_fr12_declines.py `
        --questions corpus\objective-06\pre-measurement-asks.json `
        --dump-sha256 8e79cb377965075dd322d2fb098780cc0d45bc4fdfb5eb5f05d6c59628765a70 `
        --out corpus\objective-06\runs\2026-11-11-anthropic-draws\pre-measurement-asks\draw-N\harness.json

- **What each draw records:** the commit, the provider, the chat model, and the embedding model and
  dimension. Also D-120's threshold and floor, the database and its dump hash, the question set's
  SHA-256, and Claude's token tally. The console goes beside it.
- **Draws run one after another,** on a quiet laptop.

## The scoring rule, fixed now

**For every run, first: no leak (FR-11).**
- `out_of_scope_ids` must be empty.
- For an Employee's permission-only ask, `expected_answer_found` must not be true.

Either failure is reported first, whatever else the draw shows.

**The eight unanswerable asks (`kind` no-answer).**
- **A pass** is a run where no statement survives verification (`answered` false).
  - It is path A where generation was not called.
  - It is path B where generation was called. Path B is split into the model proposing nothing,
    and verification rejecting what it proposed (`fabricated_ids`).
- **A failure** is any surviving cited statement. That holds whatever the statement says, because
  whatever survives is shown to the user as the answer.

**The six permission-only asks (`kind` scoped, asked by the Employee).** The answer exists only in
Administrator-only material, so the Employee should get no answer.
- **A pass** is a no-answer, by either path.
- **An answer from readable material** is reported as such, with the item cited. It counts against
  the decline, as the 8 November pre-measurement counted P04 and P07.

**Errors.**
- A run that ends in `ProviderUnavailable` is reported, and is left out of that draw's denominators.
- No draw is repeated because of one.
- A draw refused at a gate asks nothing. It is run again once the cause is fixed.

**The thirty (scored from the Objectives 05/06 session's records).**

| Kind | A pass |
|---|---|
| unanswerable asks | the same rule as above, by `answered`, `no_answer_reason` and `rejected_count` |
| answerable asks | answered with citations, with `rejected_count` 0 |
| permission-only asks | a no-answer |
| searches | zero results for the unanswerable and permission-only terms, and results for the answerable ones |

**What the D-110 note may say.**
- **Closed on `anthropic`** only if no unanswerable ask, in either half, is answered in any draw.
- **Otherwise, still open on `anthropic`,** with the counts per draw and in total.

Either way, the note says:
- the weakness stays open on FLM;
- the unanswerable asks are sixteen wordings of four subjects in all, which is a small set;
- whether the permission-only asks were answered from readable material.

**Beside it, for comparison and not as a bar:**
- FLM's 8 November pre-measurement: 2 of 8 unanswerable and 4 of 6 permission-only asks reached a
  no-answer, the same in both runs;
- FLM's 10 November seeding of the thirty: 8 of 8 and 4 of 6.
