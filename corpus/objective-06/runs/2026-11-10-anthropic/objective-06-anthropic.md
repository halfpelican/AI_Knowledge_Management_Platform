# Objective 06 on the anthropic provider, 10 November 2026: voyage-4 and Claude Haiku 5.5 on the frozen thirty

**The result: clauses 2 and 3 are met. Clause 1 is not, at 11 of 12.** U01 ("Will my salary rise
with inflation?", asked by the Employee) is genuinely unanswerable and reached a no-answer, but D-108's
exclusion left it out of the log. Its best match across the whole corpus is a weak one, and it is
Administrator-only.

This is the frozen thirty's one independent cycle on this configuration. Nothing was changed between
the seeding, the cycle and the verification. On FLM, the independent first cycle missed clause 3
instead, on P02. A second cycle there, informed by the first, met all three after the exclusion rule
was changed (D-108's and D-110's notes). The rule that left U01 out is that changed rule.

**D-108's development check fails on voyage-4.** It should have run on this configuration before
the thirty, and did not. Run afterwards with the user's approval, it fails at 13 of 15: two of its
nine no-answer questions are left out in the same way as U01. On FLM it passed 15 of 15. Whether
the rule changes for voyage-4 is the user's decision.

## How it ran

| | |
|---|---|
| commits | `c3ac5b0`, the seeding copy, committed before it ran: main at `a9934eb` (PR #81, D-122) plus the copy. The cycle and the verification ran at the same commit. `f8ddea8` adds the read-only diagnosis below. No uncommitted tracked changes |
| configuration | provider `anthropic`, chat model `claude-haiku-5-5` (D-121), embedding model `voyage-4` at 1024 |
| values in force | retrieval threshold 0.2687 and partial-match floor 0.2468 for voyage-4 (D-120); grouping threshold 0.5054 for voyage-4 (D-122); D-108's exclusion as of `333be14`, where the top-ranked passage over the Administrator's scope decides whether or not it clears the threshold |
| database | `kmp_obj0506_anthropic_20261110`, made for Objective 05 on the same provider, as FLM's run shared `kmp_obj0506_20261101`. It is dump `3bf98403…6f59`, restored `--into` a new database, migrated at 1024 (so `knowledge_gaps.embedding` is `vector(1024)`), and re-indexed by voyage-4 into 43 chunks. Its setup consoles are under `corpus/objective-05/runs/2026-11-10-anthropic/setup/`, on `feat/FR-10-objective05-anthropic` |
| before the seeding | no question logs; the snapshot's 50 earlier search logs, 5 of them zero-result Employee searches for Administrator-only phrases; no gap rows. Objective 05's classification rows and tag links, which FR-19 does not read |
| the thirty | `corpus/objective-06/queries.json`, frozen (D-110), SHA-256 `e40a589c…1462`, the committed file D-110's note records |
| seeding | `seed_objective06_queries_anthropic.py`, a copy of `scripts/seed_objective06_queries.py` changed only where FLM was named (`.diff` beside it). Its provider gate replaces the FLM gate, and it tallies Claude's tokens. Each query went through the shipped `answer_question` or `search` as its user, in process (`seed/`) |
| cycle | `manage.py aggregate_knowledge_gaps`, once: 7 questions and 4 searches entered the log, 4 entries created (`cycle/`). The cycle's "considered" counts are of the items that entered, after the exclusion |
| verification | `scripts/objective06_verify.py`, as shipped (`verification/`, console in `verify-console.txt`). Its first line names an FLM version because that script records any reachable FLM server; FLM took no part, and its `configuration` names the provider |
| diagnosis | `exclusion_diagnosis.py`, read-only. It runs each no-answer ask through the cycle's own `_AdministratorScope` and `_question_explained_by_permissions`, three Voyage embeddings each (`exclusion_diagnosis.txt`, `.json`) |

## What the seeding produced

| Kind | Asks | Searches |
|---|---|---|
| answerable | 7 of 7 answered, no identifier rejected | 3 of 3 with results |
| genuinely unanswerable | 8 of 8 no-answer. Six were declined before generation (path A). U04 and U05 went to generation (path B), and Haiku declined both with an empty statement list | 4 of 4 with no result |
| permission-only | 6 of 6 no-answer. P01, P02, P04 and P06 took path A. P07 and P08 took path B: readable passages cleared 0.2687 (0.3067 and 0.3016), and Haiku declined both | 2 of 2 with no result |

- **The screening's path-A guarantee did not hold on Voyage, as D-110's note expected.** U04 and U05
  reached generation through the Fleet Vehicle Usage Notes passage, at 0.289 and 0.293 against
  0.2687.
- **Generation declined every such ask.** All four path-B rows have `rejected_count` 0 and
  9 completion tokens: an empty list, not stripped citations (`seed/attempts.log`).
- **On FLM, P04 and P07 were answered from readable material.** On Haiku both reached a no-answer.

## Clause 1: "every genuinely unanswerable query and zero-result search must appear in the log within one aggregation cycle"

**Not met: 11 of 12.** The four zero-result searches and seven of the eight unanswerable asks are in
the log. U01 is not. It reached a no-answer (path A), so FR-12's decline weakness (D-102) is not the
cause, and the verifier's second reading ("for every query that reached a no-answer") is not met
either.

**Why: D-108's rank-one rule decided against it** (`exclusion_diagnosis.txt`):

| | Source | Score | Readable by the Employee |
|---|---|---|---|
| U01's top-ranked passage over the Administrator's scope | Project Budget Tracker FY27 (D15) | 0.197 | no, Administrator-only |
| the best passage the Employee may read | rank 2 | 0.1875 | yes |

- **Both are far below the 0.2687 threshold.** Nobody could have been answered, and the question is a
  documentation gap by any reading. Because the top-ranked passage is restricted, the rule reads the
  row as a permission boundary and leaves it out.
- **This is the known cost D-108's evening note names:** "a genuine gap whose weak best match happens
  to be a restricted passage is left out". The note adds that neither the development questions nor
  the frozen thirty's unanswerable asks had that shape on FLM, "so its size is unmeasured". On
  Voyage's vectors, U01 has it.
- **Not Voyage's jitter.** The margin between the restricted top passage and the best readable one
  is 0.0095, about eight times the largest pass-to-pass difference seen in this evidence, 0.0012,
  and the row was left out on all three draws. (Corrected on 12 November: this read "about twenty
  times the 0.00047 jitter", and 0.00047 was not a bound. D-126's note of that day.)
- **For information, not a run:** under D-108's rule as first written, these scores would keep U01.
  That rule admits at the threshold, here voyage-4's 0.2687, then decides on the top admitted
  passage, and nothing clears 0.2687 for anyone. It would still leave out P02, whose restricted top
  passage scores 0.2812. This is arithmetic on the diagnosis's scores, not a run of that code.
- **The subject still reached the log.** U02, the Administrator's wording, and U03, the search
  term, formed its entry with a count of 2. The seeded third occurrence never entered.
- **A property of the rule, not a fault in this run.** The cycle applied D-108's rule as shipped,
  which decides on the top-ranked passage even below the threshold (its evening note). Voyage's
  scores for out-of-corpus questions are low across the board, so for a genuine gap the top-ranked
  passage is a weak match that can fall on restricted material. The development check below, run
  afterwards, shows the same shape twice more.

## Clause 2: "differently worded questions on a single subject must group into one entry with an accurate occurrence count"

**Met.** Every subject's items that entered the log formed one entry, and each entry's count equals
its items. All four entries are voyage-4's, grouped at 0.5054:

| Entry (the first member's wording) | Count | Items |
|---|---|---|
| Does everything stop over Christmas? | 3 | 3 |
| Is jury duty paid? | 3 | 3 |
| Is there a corporate credit card I can be issued with? | 3 | 3 |
| Are salaries indexed to inflation? | 2 | 2 |

The salary entry's 2 is accurate for what entered the log. It is not the subject's three seeded
queries, because of clause 1's miss.

## Clause 3: "no query returning nothing on permission grounds may appear in the log at all"

**Met.** None of the six permission-only asks is in the log, and neither are the two permission-only
searches or the five earlier Employee searches. Each permission-only ask's top-ranked passage is
Administrator-only, with margins of 0.045 (P02) to 0.257 (P04), all far wider than the jitter.

P02 is left out on this first cycle; FLM's first cycle kept it under the rule as first built. Its
top-ranked passage is the Administrator-only Atlas brief, which scores 0.2812 on Voyage. On
embed-gemma it scored 0.2977 to 0.2983, under that model's 0.30.

**Controls:** no answerable query entered the log.

## Beside FLM's runs

| | FLM, cycle 1 (`ce886e7`) | FLM, cycle 2 (`333be14`) | **anthropic, this cycle (`c3ac5b0`)** |
|---|---|---|---|
| status | the independent test; D-108's rule as first built | informed by cycle 1; the rank-one rule | the independent test on this configuration; the rank-one rule |
| models | embed-gemma, gemma3:4b | the same | voyage-4, claude-haiku-5-5 |
| retrieval threshold; grouping threshold | 0.30; 0.5256 | 0.30; 0.5256 | 0.2687 (floor 0.2468); 0.5054 |
| unanswerable asks reaching a no-answer (path A / B) | 8 of 8 (8 / 0) | cycle 1's seeded logs | 8 of 8 (6 / 2) |
| permission-only asks reaching a no-answer | 4 of 6 | cycle 1's seeded logs | 6 of 6 |
| clause 1 | 12 of 12, met | 12 of 12, met | **11 of 12, not met (U01)** |
| clause 2 | 4 entries of 3, met | 4 entries of 3, met | 3 entries of 3 and 1 of 2, met |
| clause 3 | P02 in the log, not met | none, met | **none, met** |
| answerable queries in the log | none | none | none |

**What changes between the columns besides the provider:** the exclusion rule (cycle 1's against
the other two), every threshold, and the seeded logs themselves, because the anthropic column was
seeded through Haiku and Voyage. The anthropic and FLM cycle 2 columns run the same rule, but on
different vectors.

## D-108's development check on voyage-4, run afterwards

D-108's and D-110's notes say D-108's check (`scripts/exclusion_dev_check.py`, D-108's known-risk
paragraph) is repeated on the new configuration before the thirty are run there. It was not, and
the cycle above went ahead without it. That was this session's oversight, not a decision: both
notes were read before the run, and their order was not acted on. The FR-19 work already done on
this provider is the grouping sweep (#81), not this check.

On 11 November, with the user's approval, the check was run afterwards
(`exclusion-dev-check-voyage/`).
- **What ran:** a copy of the script changed only where FLM was named, with its `.diff`
  (`9527cd7`), on this database. It writes nothing and calls no Claude model.
- **Twice, because Voyage jitters.** Both passes gave the same outcome for every question. Their
  top scores differ by up to 0.0012 (d18, 0.5271 and 0.5259). (Corrected on 12 November: this read
  "scores no more than 0.0004 apart", which the two passes' own files contradict.)

| D-108's development check | FLM, embed-gemma (`../2026-11-10/exclusion-dev-check-2/`) | **anthropic, voyage-4** |
|---|---|---|
| scoped questions left out | 6 of 6 | 6 of 6 |
| no-answer questions kept | 9 of 9 | **7 of 9** |
| the check | passes | **fails** |
| ordinary questions kept (for information) | 46 of 50 | 46 of 50 |

- **The two misses have U01's shape.** u36 ("how many people did we hire last year?") and d27
  ("What salary does the head of digital services earn?") have no answer anywhere. Their
  top-ranked passages score 0.230 and 0.238, far under the 0.2687 threshold, and both are
  Administrator-only, so the rule leaves both out.
- **The ordinary questions left out are as on FLM:** u07, the known false exclusion, and u28, u29
  and d23, whose sources are Administrator-only.
- **What D-108 says follows a failed check:** "the margin rule is chosen on the same material
  before the thirty are run". The thirty have already run on this configuration, so any such
  choice now would be informed by their result. Whether to change the rule for voyage-4, and how,
  is the user's decision. Nothing is changed here.

## What this result does not show

- **A check of the exclusion on Voyage made in time.** The development check above came after the
  thirty's cycle. It explains the cycle's miss but did not precede it.
- **The outcome over repeated seedings.** This is one draw. D-110's note says that on `anthropic`
  the seeding is repeated and reported per draw, because Claude's generation is not deterministic.
  The exclusion decided on embeddings alone, and U01's was stable over three of them. The two path-B
  declines and the answered asks rest on single generations.
- **A rate for the false-exclusion cost.** On voyage-4 it hit one of the thirty's eight
  unanswerable asks and two of the development set's nine no-answer questions. On FLM it hit none
  of either, and met the same shape once among the ordinary questions (u07). That is three cases
  in seventeen on Voyage: enough to show the cost is real, not to measure it.
- **FR-12's decline on unscreened wordings.** The eight asks were screened on embed-gemma's scores.
  Two cleared Voyage's threshold and Haiku declined both, which is two cases, not a measure of
  D-102's open finding. D-110's acceptance test for a decline fix, an unscreened re-run, was not run.
- **Whether the seven answerable asks were answered correctly.** The seeding records that they were
  answered, which is all Objective 06 needs, not what they said.

## Spend

| | |
|---|---|
| Claude (Haiku 5.5) | the seeding: 11 calls (the seven answered asks and the four path-B declines), 34,403 tokens in and 932 out, about **$0.0039** (`seed/seed.json`, `record.claude_usage`). The cycle and the diagnosis call no Claude model |
| Voyage (voyage-4) | the seeding's 21 question embeddings, the cycle's 18 (14 questions and 4 search terms), the diagnosis's 42, and the development check's 65 twice. Within Voyage's free allowance |

## Files

- `seed_objective06_queries_anthropic.py` and `.diff`: the copy, committed before it ran (`c3ac5b0`).
- `seed/`: the seeding record, its console, and the run's 11 generation attempts. These carry token
  counts and timings and quote nothing of the replies.
- `cycle/console.txt`: the cycle's counts.
- `verification/`: the shipped verifier's record and table.
- `exclusion_diagnosis.py`, `.txt` and `.json`: why each no-answer ask was kept or left out,
  three draws each.
- `exclusion-dev-check-voyage/`: D-108's development check, run afterwards. The copy and its
  `.diff` (`9527cd7`), with the two passes' records (`pass-1/`, `pass-2/`) and consoles.
