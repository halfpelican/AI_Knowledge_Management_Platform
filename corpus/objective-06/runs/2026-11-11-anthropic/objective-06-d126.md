# D-126 on voyage-4, 11 November 2026: the exclusion rule changed, D-108's check re-run, and Objective 06's draws 2 and 3

**The result: on the rule D-126 ships for voyage-4, D-108's development check passes, 15 of 15.
Objective 06's draws 2 and 3 meet all three clauses.** Draw 1 ran on the rank-one rule
(`../2026-11-10-anthropic/`): it failed clause 1 at 11 of 12, and the same check failed 13 of 15.

**Read this as a confirmation of the shipped code, not an independent test.** D-126 was chosen
partly because of the frozen thirty, as D-126 records. Draw 1 remains the thirty's one independent
cycle on this configuration.

## What changed

- **The rule** (`b854288`, D-126). For a question embedded by voyage-4, FR-19's permission
  exclusion is now *threshold-first*, D-108's rule as first written:
  - rank over the Administrator's scope;
  - if nothing reaches voyage-4's own threshold (0.2687, D-120), nobody could have been answered,
    and the row is a gap;
  - otherwise the top admitted passage decides: restricted means left out, readable means a gap.
- **Any other model keeps rank-one,** embed-gemma included (`GAP_EXCLUSION_RULE_BY_MODEL`,
  `gaps.exclusion_rule`).
- **Tests** (`b854288`, `14d9629`), in `apps/retrieval/tests/test_knowledge_gaps.py`. D-126 names
  each test with the deliberate breaks of `gaps.py` under which it fails. Two of them carry the
  thirty's shapes:
  - U01's: a restricted best match under the threshold is a gap;
  - P02's: a restricted answer between voyage-4's threshold and EmbeddingGemma's is left out.
- **The full suite** on the tree of `14d9629`: 3,286 passed, with dual-role coverage of 38 of 38
  protected endpoints.

## The two rules that pass, on the development questions

D-108 says the margin rule is chosen when its check fails. `exclusion-rule-exploration/` holds the
read-only script that compared the candidates on voyage-4, before the user chose:

| | rank-one | margin rule, m = 0.0939 | threshold-first |
|---|---|---|---|
| scoped questions left out | u30, u31, u32, d11, d21, d22 | the same six | the same six |
| no-answer questions left out | **u36, d27** | none | none |
| D-108's check | fails | passes | passes |

- **The margins.** A margin is the restricted top passage's score less the best readable one's.
  The scoped questions' margins run from 0.1218 (d21) to 0.2734 (u30). The no-answer questions
  with a restricted top passage are u36 (0.0124) and d27 (0.0659). The midpoint of 0.0659 and
  0.1218 is 0.0939, and the gap between them is 0.056, about 119 times Voyage's jitter.
- **Two runs.** `first-run.json` is the run the options were put with, from the session's
  scratchpad. `console.txt` and `rows.json` are the same script run again from its committed copy
  (`4d1e301`), because the first run's console was not kept. They agree to within Voyage's
  jitter: d21's margin reads 0.1218 in one and 0.1219 in the other.
- **The development questions do not choose between the two passing rules.** The thirty do, by
  arithmetic on #86's diagnosis: P02's margin is 0.0448, under 0.0939, so the margin rule would
  keep P02 in the log. D-126 records that the choice used this.

## D-108's development check on the new rule

Run twice, on this branch at `462e8e9`, with the copy in `exclusion-dev-check-threshold-first/`.
The copy was changed only where FLM was named, and its `.diff` sits beside it. It writes nothing and
calls no Claude model. Both passes gave the same outcome for every question.

| | rank-one (`../2026-11-10-anthropic/exclusion-dev-check-voyage/`) | **threshold-first, as shipped** |
|---|---|---|
| scoped questions left out | 6 of 6 | 6 of 6 |
| no-answer questions kept | 7 of 9 (u36 and d27 left out) | **9 of 9** |
| the check | fails | **passes** |
| ordinary questions kept (for information) | 46 of 50 | 46 of 50 (u07, u28, u29 and d23 left out, as on FLM) |

u36 and d27 are now kept. Their top-ranked passages, 0.230 and 0.238, are Administrator-only, but
under 0.2687, so nothing is admitted for anyone.

**The record's `relevance_threshold` field reads 0.3, and that is not the value the decision used.**
The script writes the constant for models the map does not list. The decision it calls admits at
voyage-4's own 0.2687 (`ranking.admit`, D-120). No development question's restricted top passage
falls between the two values, so this check cannot show which was used. P02 does, on the draws
below: at 0.2812 it was left out, and at 0.30 it would have been kept.

## Objective 06's draws 2 and 3

The user asked for two more draws, three in all, as D-110's note asks for this provider, with the
new draws on the D-126 rule.

**How each ran:**
1. **Export, then clear.** `reset_objective06_draw.py` exported the previous draw's rows to
   `draw-N/export.json`: every seeded query's outcome, including `no_answer_reason` and
   `rejected_count`, and the gap log. It then cleared that draw's seeded rows and the gap tables,
   with every count checked first. Draw 1's rows were exported before they were cleared.
2. **Seed.** The thirty went through the shipped `answer_question` and `search`, with the seeding
   copy (`seed_objective06_queries_anthropic.py` and its `.diff`).
3. **One cycle,** with `manage.py aggregate_knowledge_gaps`.
4. **Verify,** with the shipped `objective06_verify.py`.

The commit was `462e8e9`, with no uncommitted tracked changes. The database was
`kmp_obj0506_anthropic_20261110`, as for draw 1.

| | Draw 1 (rank-one, `c3ac5b0`) | **Draw 2 (D-126, `462e8e9`)** | **Draw 3 (D-126, `462e8e9`)** |
|---|---|---|---|
| answerable asks answered | 7 of 7 | 7 of 7 | 7 of 7 |
| unanswerable asks: path A / path B | 6 / 2 (U04, U05) | 6 / 2 (U04, U05) | 6 / 2 (U04, U05) |
| permission-only asks: path A / path B | 4 / 2 (P07, P08) | 4 / 2 (P07, P08) | 4 / 2 (P07, P08) |
| identifiers rejected | none | none | none |
| **clause 1**, unanswerable queries in the log | **11 of 12 (U01 left out)** | **12 of 12** | **12 of 12** |
| **clause 2**, one entry per subject, count accurate | met; salary 2 | **met; four entries of 3** | **met; four entries of 3** |
| **clause 3**, no permission-only query in the log | met | **met** | **met** |
| answerable queries in the log | none | none | none |
| Claude | 11 calls, $0.0039 | 11 calls, $0.0038 | 11 calls, $0.0039 |

- **Generation behaved the same on all three draws.** The same asks were answered, the same four
  no-answers went through generation and were declined, and no citation was rejected. On these asks
  Haiku's single-draw outcome was stable over three draws. D-110's note was asking about exactly
  that.
- **The one difference is the rule.** U01's top-ranked passage, 0.197 and Administrator-only, is
  under 0.2687, so threshold-first keeps it and the salary subject's entry counts all three of its
  queries.
- **P02 stays out under D-126.** Its Administrator-only answer scores 0.2812, above 0.2687.
- **All six permission-only asks exercise the exclusion here:** P01, P02, P04, P06, P07 and P08
  each reached a no-answer on every draw. On FLM, P04 and P07 were answered from readable
  material and did not (D-110's "Not covered").

## What this does not show

- **An independent test of D-126.** The check above was already known to pass when D-126 was
  chosen, and the choice also used the thirty's U01 and P02 (D-126, a departure from D-93).
- **The cost of threshold-first.** A permission-only question whose restricted answer scores under
  0.2687 would be kept, and its wording would reach the gap log. Neither the development set nor
  the thirty has one: their restricted answers score from 0.2812 (P02) to 0.56 (u32). So the
  rule's margin on this set is 0.0125, about 27 times Voyage's jitter, and its size beyond this
  corpus is unmeasured. FLM's P02 fell exactly there, at 0.2977 to 0.2983 against 0.30 (D-108's
  evening note), which is why embed-gemma keeps rank-one.
- **embed-gemma under either rule.** Nothing was measured on FLM for this change.
- **FR-12's declines.** These exports serve the FR-12 decline session's per-draw scoring, in its
  own pull request.
- **More than three draws, and Sonnet.** Neither was run.

## Spend

| | |
|---|---|
| Claude (Haiku 5.5) | draws 2 and 3: 22 calls, 68,806 tokens in and 1,655 out, about **$0.0077** (`draw-N/seed/seed.json`, `record.claude_usage`). The checks, cycles and exports call no Claude model |
| Voyage (voyage-4) | the checks' 65 question embeddings twice, the exploration's 65 twice, and each draw's 21 seeding and 18 cycle embeddings. A cycle embeds all 14 unanswered questions before the exclusion decides, plus the 4 surviving search terms. Within Voyage's free allowance |

## Files

- `seed_objective06_queries_anthropic.py` and `.diff`, `exclusion-dev-check-threshold-first/`
  (the copy, its `.diff`, and `pass-1/`, `pass-2/`), and `reset_objective06_draw.py`. All three
  were committed before they ran (`462e8e9`).
- `exclusion-rule-exploration/`: the script, `first-run.json`, and the re-run's `console.txt` and
  `rows.json`.
- `draw-1/export.json`: draw 1's rows, exported from the database before draw 2's clear. Draw 1's
  seeding, cycle and verification are in `../2026-11-10-anthropic/` (#86). The export names a
  scratchpad path for draw 1's seed record. That was a copy of #86's `seed/seed.json`, taken
  because this branch was cut before #86 merged. Its SHA-256 in the export, `955bddb9…`, is the
  committed file's.
- `draw-2/` and `draw-3/`: each draw's seed record, console and attempts log, its cycle console, its
  verification, and its export.
