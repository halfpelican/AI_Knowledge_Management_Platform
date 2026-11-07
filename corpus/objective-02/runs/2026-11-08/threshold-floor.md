# The relevance threshold and D-56's floor, set from the development set: 7-8 November 2026

Step 7, phase 2b, of the user's post-M6 order. It sets two values in `apps/core/constants.py`
from `corpus/objective-02/dev-set.json` alone, by a rule the user approved before anything was
measured:

- **`RELEVANCE_THRESHOLD`: 0.3 → 0.4472.**
- **`PARTIAL_MATCH_FLOOR`, new: 0.4458.** This is D-56's missing floor. A partial match is offered
  only if its source's best passage reaches it.

The frozen sets (`questions.json`, `threads.json`) were neither read for tuning nor edited (D-93).
The run crossed midnight, so this folder is dated 8 November. The scores were measured at 23:57 on
7 November, and the end-to-end pass ran on the morning of 8 November.

## The rule, as approved

> "Choose the D-56 floor, and any threshold change, from the dev set alone."

1. **`RELEVANCE_THRESHOLD`:** the value that declines the most no-answer runs without losing any
   answerable one.
   - **Declines** a no-answer run: at T, no in-scope passage scores at least T, so path A applies
     and generation is never invoked.
   - **Loses** an answerable run: at T, none of that run's expected sources' passages scores at
     least T.
   - Ties: the middle of the tied interval.
   - If 0.3 already loses an answerable run, choose nothing that loses more.
2. **The partial-match floor:** the lowest value at which no no-answer run is offered unrelated
   partial matches. That is just above the highest-scoring partial match offered to any no-answer
   run, taken from the real offer path. Report the cost. If the floor would have to be at or above
   the threshold, stop and report.

## How the scores were measured

| | |
|---|---|
| When | 7 November 2026, 23:57 (+11:00) |
| Script | `threshold_scores.py`, read-only: no generation, no rows written |
| Code | `7e3845d` unchanged, the phase 2a tip, equal in tree to `origin/main` `6be6288` (PR #55): `RELEVANCE_THRESHOLD` 0.3 and no floor. This commit's constants did not exist yet |
| Path | The shipped retrieval, as `answer_question` runs it for a one-off question: `embed_question` → `candidate_chunks(role, model)` → `rank` → `partial_matches(ranked)`, the real offer path. The score of each offered item is its first (best) passage's score in that ranked list |
| Roles | As each run names: the Employee as `loadtest01`, the Administrator as `corpus.admin`, the accounts phase 2a used. `permission_scope` was checked for both |
| FLM | v0.9.39, CLI and server. `check_flm.py` passed first (`check_flm_scores.txt`) |
| Database | `kmp_obj02_20261101`, 43 chunks. Candidates: 38 for the Employee, 43 for the Administrator |
| Set | `dev-set.json`, SHA-256 `19a0639a…6286f`, the file phase 2a used |
| D-40 | Each question was embedded 3 times, in separate calls. **All 93 vectors were identical to their run's first,** so the top-score spread was 0.000000. The derivation is still conservative against variation: an answerable run is judged by its lowest score over the repeats, a no-answer run by its highest |
| TOP_K | 25 binds: it is below both candidate counts. It never cut an expected source: in every answerable run, the expected source's best passage ranked first |

The raw output is `threshold_scores.json`: every run's whole ranked list, with chunk, manifest item
and score, for each repeat. `threshold_scores_derive.txt` is the derivation, printed by
`threshold_scores.py --derive`. `threshold_table.py` prints the tables below from the JSON.

**Re-running `threshold_scores.py` on this commit will not reproduce the "before the floor"
offers.** It calls the shipped `partial_matches`, which now applies the floor.

## Every score used

### Answerable runs (24)

The column used is the best score of a passage of an expected source in the ranked list. In every
run that passage also ranked first.

| run | role | expected source | its best score | top item | lost at 0.3 | lost at 0.4472 | admitted at 0.3 / at 0.4472 |
|---|---|---|---|---|---|---|---|
| d17 | Employee | D18 | **0.448714** | D18 | no | no | 1 / 1 |
| d21@Administrator | Administrator | D16 | 0.469345 | D16 | no | no | 3 / 1 |
| d22@Administrator | Administrator | T02 | 0.483432 | T02 | no | no | 1 / 1 |
| d18 | Employee | D01 | 0.506587 | D01 | no | no | 11 / 1 |
| d19 | Employee | D01 | 0.515170 | D01 | no | no | 2 / 1 |
| d08 | Employee | D07 | 0.526700 | D07 | no | no | 6 / 2 |
| d15 | Employee | D11 | 0.534027 | D11 | no | no | 19 / 1 |
| d20 | Employee | D13 | 0.543487 | D13 | no | no | 2 / 1 |
| d12 | Employee | T03 | 0.564212 | T03 | no | no | 1 / 1 |
| d11@Administrator | Administrator | T05 | 0.583942 | T05 | no | no | 4 / 1 |
| d23 | Administrator | D09 | 0.594494 | D09 | no | no | 2 / 1 |
| d03 | Employee | D04 | 0.595959 | D04 | no | no | 20 / 19 |
| d13 | Employee | T04 | 0.599559 | T04 | no | no | 5 / 1 |
| d01 | Employee | D08 | 0.605865 | D08 | no | no | 6 / 1 |
| d14 | Employee | T01 | 0.614274 | T01 | no | no | 3 / 1 |
| d10 | Employee | D10 | 0.628999 | D10 | no | no | 2 / 1 |
| d07 | Employee | D06 | 0.633837 | D06 | no | no | 2 / 1 |
| d02 | Employee | D08 | 0.643146 | D08 | no | no | 11 / 2 |
| d16 | Employee | D17 | 0.649443 | D17 | no | no | 5 / 1 |
| d05 | Employee | D03 | 0.651671 | D03 | no | no | 12 / 2 |
| d28 | Employee | D19 | 0.670014 | D19 | no | no | 6 / 1 |
| d04 | Employee | D02 | 0.678356 | D02 | no | no | 23 / 1 |
| d09 | Employee | D20 | 0.709477 | D20 | no | no | 9 / 1 |
| d06 | Employee | D05 | 0.718767 | D05 | no | no | 21 / 1 |

### No-answer runs (7)

The column used is the top in-scope score. Before the floor, each run was offered the five items in
the next column. These are the real offer path's output, with each item's best score.

| run | role | top score | declined at 0.3 | declined at 0.4472 | offered before the floor (item score) | offered at 0.4458 |
|---|---|---|---|---|---|---|
| d22@Employee | Employee | 0.250707 | yes | yes | D05 0.250707; D04 0.238189; T03 0.210895; T01 0.193208; D17 0.190302 | none |
| d27 | Administrator | 0.270264 | yes | yes | D04 0.270264; D15 0.254218; D16 0.241790; D01 0.235657; D12 0.230814 | none |
| d11@Employee | Employee | 0.339343 | no | yes | T01 0.339343; D02 0.310289; D08 0.292167; D04 0.278571; T03 0.257940 | none |
| d21@Employee | Employee | 0.390036 | no | yes | D06 0.390036; T04 0.343443; T01 0.286846; D18 0.255977; D13 0.245434 | none |
| d24 | Employee | 0.397550 | no | yes | D01 0.397550; D10 0.297211; D08 0.286551; D05 0.280163; D06 0.270541 | none |
| d26 | Employee | 0.439129 | no | yes | D01 0.439129; D03 0.376840; D02 0.375677; D07 0.349547; D05 0.292846 | none |
| d25 | Employee | **0.445715** | no | yes | D20 0.445715; D01 0.316821; D03 0.289582; D14 0.288633; D17 0.276240 | none |

## The choice

### `RELEVANCE_THRESHOLD` = 0.4472

- **Does 0.3 already lose an answerable run?** No. The lowest expected-source score is d17's
  0.448714, so nothing is lost at any T up to and including 0.448714.
- **Most declined with none lost.** Declines only grow with T, so the most is reached at T =
  0.448714. Every no-answer run's top score is below that (the highest is d25's 0.445715), so
  **all 7 are declined.** At 0.3, 2 were (d22@Employee, d27).
- **The tied interval:** every T in **(0.445715, 0.448714]** declines 7 and loses 0.
- **The middle:** 0.4472145, written as **0.4472.** The rounding moves it by 0.0000145.
  - Margin below, to d25's 0.445715: **0.001485.**
  - Margin above, to d17's 0.448714: **0.001514.**
- **The margin is narrow.** It is 0.0015 each side, on 31 runs. It is about 15 times D-40's
  recorded variation of about 1e-4. Tonight there was no variation at all across 93 embeddings.
- **A check:** 0.45 would lose d17, and 0.445 would admit d25.

### `PARTIAL_MATCH_FLOOR` = 0.4458

- **Which no-answer runs are offered partial matches at the new threshold.** All 7 take path A
  (their tops are below 0.4472), and path A always carries the offer. So every no-answer run's
  real offer counts. The same 7 lists would count under any reading of "offered", since a
  no-answer run reaching generation and then path B carries the same list.
- **The highest-scoring partial match offered to any no-answer run:** d25's D20, at 0.445715.
  That is also the highest no-answer top score, because an offer's first item is the run's top.
- **Just above it, at the threshold's four places:** **0.4458.** The margin is 0.000085.
- **Is it at or above the threshold?** No. It is 0.0014 below 0.4472, so the rule's stop does not
  apply. **But it is close.**
  - On path A, an item is now offered only if its best passage scores in **[0.4458, 0.4472).**
    That band is 0.0014 wide.
  - On path B, every admitted item clears the floor, so it is still offered.
  - So on this corpus, the partial matches FR-12 describes will appear almost only on path B. On
    the development set, **no run is offered anything on path A.**

## What each rule bought, and what it cost

**The threshold.**

- **Bought:**
  - All 7 no-answer runs are declined at path A, against 2 at 0.3. Generation is never called for
    them.
  - **This resolves phase 2a's trade-off.** Under the cap of 6, d11@Employee and d21@Employee were
    answered with loosely related statements. Both are now declined before generation.
- **Cost on the development set: none lost, by the rule's definition.**
- **The other effect: far fewer passages reach the prompt.**
  - At 0.4472, 20 of the 24 answerable runs admit exactly one passage, their expected source's.
    d02, d05 and d08 admit 2. d03 admits 19, all of them D04's, and the context budget supplies 8
    of them.
  - At 0.3 the median admitted was 5.
  - An answer now has less material to draw on, and less material to cite wrongly. The end-to-end
    pass below shows what that did.
- **Not measured, so not claimed:**
  - Questions worded differently from these 31, the frozen sets, and FR-13 follow-ups. A
    follow-up embeds the earlier questions too (`conversation_context`), so it scores
    differently.
  - D-37 found answerable questions down to 0.219 on the September corpus. A real question that
    scores between 0.30 and 0.4472 now gets the no-answer reply where it used to be answered.
  - `docs/demonstration-script.md`'s D-40 screen accepted an expected answer at a top score of
    0.35 or more, against 0.30. Its questions were not re-scored. Its database and the frozen sets
    are outside this phase.

**The floor.**

- **Bought:** no no-answer run is offered any partial match. Before, each of the 7 was offered
  five items, at scores from 0.190 to 0.446.
- **Cost, as the rule asks it reported:** an answerable run that ends in no-answer, and would have
  been offered a partial match pointing at its expected source without the floor.
  - In the end-to-end pass: **none.** No answerable run ended in no-answer, so none was offered
    anything, with the floor or without it.
  - It would have been zero even if one had: every expected source scores at least 0.448714,
    above the floor.
- **Two costs the rule did not count:**
  1. **d25's D20 is arguably related.** The question asks about parking at the new office, and
     D20 is the office relocation notice (the dev set's note: "D20 announces the move and says
     nothing about parking"). The rule treats every partial match offered to a no-answer run as
     unrelated, so the floor removes it.
  2. **An empty offer now says path A ran.**
     - Path B always admitted something at or above the threshold, which is above the floor, so a
       path-B reply's offer is never empty.
     - So `partial_matches: []` on a no-answer reply now implies path A. Before the floor, that
       was true only when the caller's scope held nothing rankable.
     - A non-empty offer is still consistent with either path.
     - This tells the caller nothing about material outside their scope, because the candidate set
       was scoped in the query (invariant 1). But it narrows the "byte-identical replies" property
       item 7 built.
     - `apps/retrieval/partial_matches.py` and `docs/api-contract.md` now say so.

## End to end, at the new values

### What ran

| | |
|---|---|
| When (+11:00) | 8 November 2026, 07:09:41–07:22:52. Nothing else ran beside it: the deliberate breaks had finished, and no pytest ran until it was over |
| Code | this commit's working tree. `threshold_floor_e2e.py` refuses to run unless `RELEVANCE_THRESHOLD` is 0.4472, `PARTIAL_MATCH_FLOOR` 0.4458 and the generation loop's `MAXIMUM_STATEMENTS` 6, all read from the code, with nothing patched. The four product files the pass imports from retrieval were SHA-256-checked before it and after it: `constants.py` `dbd58490…`, `partial_matches.py` `4c2e61bf…`, `pipeline.py` `24f10a41…`, `ranking.py` `e32a36b8…` |
| How | the shipped `answer_question`, in-process, each ask inside a transaction rolled back. The accounts were phase 2a's. A wrapper around `pipeline.rank` recorded the ranked list it returned and changed nothing. The partial matches are the reply's own (`outcome.partial_matches`) |
| FLM | v0.9.39. `check_flm.py` passed first (`e2e/check_flm_T4472_F4458_N6.txt`) |
| Database | `kmp_obj02_20261101`. Rows before and after: `QueryLog` 83, `AnswerCitation` 199, `Conversation` 3, `ContentChunk` 43, unchanged |
| Set | `dev-set.json`, SHA-256 `19a0639a…6286f` |
| Scoring | phase 2a's own `summarise`, imported from `../2026-11-07/sweep_statement_cap.py`, so the columns compare like with like |

### Against phase 2a's cap-of-6 row

| | phase 2a, cap 6 (threshold 0.3, no floor) | **phase 2b (threshold 0.4472, floor 0.4458, cap 6)** |
|---|---|---|
| attempts that hit the ceiling | 0 | **0** |
| 503s | 0 | **0** |
| cap violations | 0 | **0** |
| answered, where expected | 24/24 | **24/24** |
| no answer, where expected | 5/7 | **7/7**, all by path A |
| expected-answer match, cited to an expected source | 15/24 | **24/24** |
| expected phrase anywhere in the answer | 20/24 | **24/24** |
| citations of an item the role may not read | 0 | **0** |
| generation attempts | 29 | **24**, all parsed on attempt 1 |
| completion tokens per attempt, median / max | 245 / 507 | **380 / 473** |
| seconds per attempt, median / max | 33.2 / 75.3 | **38.9 / 50.4** |
| seconds per ask, median / max | 31.7 / 75.7 | **23.5 / 50.7** |
| most statements in one answer | 6 | **6** |
| path-B no-answers | 3 (d24, d25, d26) | **0** |
| partial matches offered to no-answer runs | 5 runs × 5 items, scores 0.190–0.446 (see below) | **none** |

**Phase 2a's partial matches are inferred, not recorded.** Its sweep did not record them. The
runs that ended in no-answer under the cap of 6 were d22@Employee and d27 (path A) and d24, d25 and
d26 (path B). Retrieval tonight was bit-identical across repeats, on the same database. So each of
those runs would have been offered the five items in the no-answer table above. d11@Employee and
d21@Employee were answered, so they were offered nothing.

**The floor's cost, as the rule asks it reported: none.** No answerable run ended in no-answer.

### Per run

| run | expects | status | outcome | reason | supplied items | match | offered (item score) | without the floor |
|---|---|---|---|---|---|---|---|---|
| d01 | answer | 200 | answered | - | D08 | yes | none | (answered: none offered) |
| d02 | answer | 200 | answered | - | D03, D08 | yes | none | (answered: none offered) |
| d03 | answer | 200 | answered | - | D04 | yes | none | (answered: none offered) |
| d04 | answer | 200 | answered | - | D02 | yes | none | (answered: none offered) |
| d05 | answer | 200 | answered | - | D03, D08 | yes | none | (answered: none offered) |
| d06 | answer | 200 | answered | - | D05 | yes | none | (answered: none offered) |
| d07 | answer | 200 | answered | - | D06 | yes | none | (answered: none offered) |
| d08 | answer | 200 | answered | - | D02, D07 | yes | none | (answered: none offered) |
| d09 | answer | 200 | answered | - | D20 | yes | none | (answered: none offered) |
| d10 | answer | 200 | answered | - | D10 | yes | none | (answered: none offered) |
| d11@Administrator | answer | 200 | answered | - | T05 | yes | none | (answered: none offered) |
| d11@Employee | none | 200 | no answer | no_relevant_passage | - | - | none | T01 0.339343; D02 0.310289; D08 0.292167; D04 0.278571; T03 0.257940 |
| d12 | answer | 200 | answered | - | T03 | yes | none | (answered: none offered) |
| d13 | answer | 200 | answered | - | T04 | yes | none | (answered: none offered) |
| d14 | answer | 200 | answered | - | T01 | yes | none | (answered: none offered) |
| d15 | answer | 200 | answered | - | D11 | yes | none | (answered: none offered) |
| d16 | answer | 200 | answered | - | D17 | yes | none | (answered: none offered) |
| d17 | answer | 200 | answered | - | D18 | yes | none | (answered: none offered) |
| d18 | answer | 200 | answered | - | D01 | yes | none | (answered: none offered) |
| d19 | answer | 200 | answered | - | D01 | yes | none | (answered: none offered) |
| d20 | answer | 200 | answered | - | D13 | yes | none | (answered: none offered) |
| d21@Administrator | answer | 200 | answered | - | D16 | yes | none | (answered: none offered) |
| d21@Employee | none | 200 | no answer | no_relevant_passage | - | - | none | D06 0.390036; T04 0.343443; T01 0.286846; D18 0.255977; D13 0.245434 |
| d22@Administrator | answer | 200 | answered | - | T02 | yes | none | (answered: none offered) |
| d22@Employee | none | 200 | no answer | no_relevant_passage | - | - | none | D05 0.250707; D04 0.238189; T03 0.210895; T01 0.193208; D17 0.190302 |
| d23 | answer | 200 | answered | - | D09 | yes | none | (answered: none offered) |
| d24 | none | 200 | no answer | no_relevant_passage | - | - | none | D01 0.397550; D10 0.297211; D08 0.286551; D05 0.280163; D06 0.270541 |
| d25 | none | 200 | no answer | no_relevant_passage | - | - | none | D20 0.445715; D01 0.316821; D03 0.289582; D14 0.288633; D17 0.276240 |
| d26 | none | 200 | no answer | no_relevant_passage | - | - | none | D01 0.439129; D03 0.376840; D02 0.375677; D07 0.349547; D05 0.292846 |
| d27 | none | 200 | no answer | no_relevant_passage | - | - | none | D04 0.270264; D15 0.254218; D16 0.241790; D01 0.235657; D12 0.230814 |
| d28 | answer | 200 | answered | - | D19 | yes | none | (answered: none offered) |

"Without the floor" is the five nearest distinct sources of the ranked list the pipeline produced
in this pass. It matches the scores measurement exactly.

### What was observed

- **Every answerable run matched, including the ones that never had.** d02, d04, d08, d13, d16,
  d18, d19 and d21@Administrator missed under every phase 2a setting. All matched here.
  - The likely cause is the narrower prompt, though one pass cannot isolate it. 21 of 24 runs
    supplied passages of the expected source and nothing else (20 supplied one passage, d03
    supplied 8 of D04's), so there was no other item to cite wrongly. Phase 2a's wrong-passage
    citations needed a second supplied item.
  - **d08 still cites the second item it was given.** Three of its six statements cite D02,
    supplied at 0.455544. It matched on its D07 statements.
- **The match test is the development set's weaker one.** A summary matches when it states any
  one of `accepted`'s key facts, cited to an expected source. The dev set says so itself. 24/24
  does not mean 24 complete answers.
- **Path B did not occur.** Every no-answer was path A, so `no_statement_verified`, the project's
  quality signal, was zero on this set.
- **No retry fired.** All 24 generation calls parsed on attempt 1, so the reduced retry (D-100)
  is still shown only by the tests.
- **Answers got longer per attempt and faster per ask.** The median attempt rose from 245 to 380
  completion tokens: more runs filled the cap of 6 from one passage. The slowest ask fell from
  75.7 s to 50.7 s. The median ask fell from 31.7 s to 23.5 s, because the 7 no-answer runs now
  take 0.3 s with no generation.

## What it does not show

- **One development set of 31 runs.** The threshold sits 0.0015 from a run on each side. A
  different wording of d17 or d25 could cross it.
- **One end-to-end pass.** Phase 1 showed that the same prompt can give different replies, so
  24/24 is one sample. The no-answer half (7/7) depends only on retrieval, which was
  deterministic tonight.
- **That the results were not tuned in by the choice itself.** T was chosen to keep every
  answerable run's expected source admitted, on these runs, so the "answered where expected"
  row is partly a consequence of the rule. The match row is not: the rule never looked at answers.
- **Anything about the frozen sets.** They were not run. They measure this; they did not tune it.
- **Live variation.** D-40's query-vector variation did not appear tonight. It has before, at
  about 1e-4 (and 4.3e-4 once, in September).
- **The floor's behaviour beyond this corpus.** Its band below the threshold is 0.0014 wide, so
  on path A it will rarely offer anything.
