# Objective 06's verification, 10 November 2026

**The result: on the first cycle, clauses 1 and 2 are met and clause 3 is not (one permission-only
query in the log). After one disclosed change to the exclusion rule, a second cycle over the same
seeded logs meets all three.** The first cycle is the frozen thirty's one independent test of the
exclusion; the second is informed by it (D-108's and D-110's notes).

## How it ran

| | |
|---|---|
| configuration | provider `flm`, chat model `gemma3:4b`, embedding model `embed-gemma`, FLM v0.9.39, `check_flm.py` passing |
| database | `kmp_obj0506_20261101` (dump `3bf98403…6f59`), with `accounts 0007` and `retrieval 0004` applied first |
| the thirty | `corpus/objective-06/queries.json`, frozen (D-110); SHA-256 of the committed file `e40a589c…1462`, identical in content to the `e78314b7…` D-110 recorded, which was the same file with Windows line endings |
| before the seeding | no question logs; 50 earlier search logs, 5 of them zero-result Employee searches for Administrator-only phrases |
| seeding | `scripts/seed_objective06_queries.py` at `ce886e7`: each query through the shipped `answer_question` or `search` as its user, in process (`seed/`) |
| cycle 1 | `manage.py aggregate_knowledge_gaps` at `ce886e7`, then `scripts/objective06_verify.py` (`cycle/`, `verification/`) |
| cycle 2 | after the rule change, the first cycle's 5 entries, 13 items and 1 cycle record deleted (the seeded logs kept), one cycle at `333be14`, then the same verification (`rerun/`) |

**One false start, recorded:** the first seeding attempt stopped after its first ask (A01) on an
attribute error in the script (`console-aborted-first-attempt.txt`). The pipeline had already logged
A01, so that one row and its two citations were deleted, the script fixed (`ce886e7`), and the thirty
seeded once.

## What the seeding produced

| Kind | Asks | Searches |
|---|---|---|
| answerable | 7 of 7 answered | 3 of 3 with results |
| genuinely unanswerable | 8 of 8 no-answer, every one before generation (path A) | 4 of 4 with no result |
| permission-only | 4 no-answer (P01, P02, P06, P08); 2 answered from readable material (P04, P07, as the pre-measurement found) | 2 of 2 with no result |

P04 and P07 were answered, so they never became unanswered rows; neither reaches the log under either
rule.

## Clause 1: "every genuinely unanswerable query and zero-result search must appear in the log within one aggregation cycle"

**Met on both cycles: 12 of 12.** The eight unanswerable asks and the four zero-result searches each
have an item in the log after one cycle. No answerable query entered the log.

## Clause 2: "differently worded questions on a single subject must group into one entry with an accurate occurrence count"

**Met on both cycles.** Each subject's three queries (two differently worded questions and a search
term) formed one entry with an occurrence count of 3, equal to its number of items:

| Entry (the first member's wording) | Count |
|---|---|
| Does everything stop over Christmas? | 3 |
| Is jury duty paid? | 3 |
| Is there a corporate credit card I can be issued with? | 3 |
| Will my salary rise with inflation? | 3 |

## Clause 3: "no query returning nothing on permission grounds may appear in the log at all"

- **Cycle 1: not met.** P02 ("What gets decided at the Quartz Harbour milestone gate?", asked by the
  Employee) appeared as a fifth entry. Its answer exists only in the Administrator-only Atlas brief,
  but that passage scored 0.2977 to 0.2983 across the Administrator's scope, under
  `RELEVANCE_THRESHOLD` (0.30) and inside D-40's drift of it. The rule as built kept a row when
  nothing cleared the threshold for anyone, so P02 stayed. The other permission cases were left out:
  P01, P06 and P08, the two permission-only searches, and the five earlier Employee searches.
- **The change (the lead's decision, D-108's note):** the exclusion decides on the top-ranked passage
  across the Administrator's scope whether or not it clears the threshold. On D-108's 15 development
  questions it scores 15 of 15, as the old rule did (`exclusion-dev-check-2/`).
- **Cycle 2: met.** No permission-only query and none of the five earlier Employee searches is in the
  log; the four entries above are the whole log.

## Not covered

- The verification ran on the FLM configuration only. On `anthropic` (Voyage embeddings and a
  re-derived threshold) the screening's path-A guarantee does not hold and the exclusion ranks over
  different vectors, so the objective would be verified again there (D-110's note).
- Clause 1's screening: the eight unanswerable asks were screened on retrieval scores (D-110). An
  unscreened wording near the corpus's subject matter is usually answered by FR-12 instead of
  declined, and so would not reach the log (D-102's open finding).
