# The relevance threshold and D-56's floor, set from the development set: 7-8 November 2026

Step 7, phase 2b, of the user's post-M6 order. It sets two values in `apps/core/constants.py`
from `corpus/objective-02/dev-set.json` alone, and nothing else.

| | `RELEVANCE_THRESHOLD` | `PARTIAL_MATCH_FLOOR` (new, D-56's floor) |
|---|---|---|
| Before | 0.3 | none: the five nearest items, however weak |
| The literal rule (commit `3c839bb`), **set aside** | 0.4472 | 0.4458 |
| **The margin rule (shipped)** | **0.4231** | **0.4036** |

**Why there are two.** The first rule was applied exactly, and the user then set its values aside
on 8 November:

- **Both margins were below the query-vector drift D-40 recorded**, about 0.003, which phase 1
  also saw move mid-run. The threshold's margin was 0.0015 and the floor's 0.000085.
- **Its floor sat only 0.0014 under its threshold.** That all but retired FR-12's partial matches
  on path A.

The user approved the same rule with a margin, **m = 0.006** (twice D-40's drift), fixed before
any new run. The scores did not change: both choices come from one measurement.

The frozen sets (`questions.json`, `threads.json`) were neither read for tuning nor edited (D-93).
The work crossed midnight, so this folder is dated 8 November. The scores were measured at 23:57 on
7 November. The end-to-end passes ran on the morning of 8 November.

## The two rules

**The order, word for word:** "Choose the D-56 floor, and any threshold change, from the dev set
alone."

**The literal rule (approved 7 November):**

1. **`RELEVANCE_THRESHOLD`:** the value that declines the most no-answer runs without losing any
   answerable one.
   - **Declines** a no-answer run: at T, no in-scope passage scores at least T, so path A applies
     and generation is never invoked.
   - **Loses** an answerable run: at T, none of that run's expected sources' passages scores at
     least T.
   - Ties: the middle of the tied interval. If 0.3 already loses an answerable run, choose nothing
     that loses more.
2. **The floor:** the lowest value at which no no-answer run is offered unrelated partial matches,
   just above the highest-scoring partial match offered to any no-answer run. If it would be at or
   above the threshold, stop.

**The margin rule (approved 8 November), m = 0.006:**

1. **T:** maximise the no-answer runs declined at path A with margin (top in-scope score ≤ T − m),
   subject to every answerable run's lowest expected-source score being ≥ T + m. On a tie, the
   middle of the tied interval.
2. **F:** the lowest value with F ≥ (the highest partial-match score offered to any no-answer run
   that path A declines at the new T) + m, and F ≤ T − m, so that a real band of partial matches
   survives below the threshold. If F would exceed T − m, stop.
3. **The no-answer runs above T** reach generation. Report what they get, and count each as
   declined or not.

## How the scores were measured

| | |
|---|---|
| When | 7 November 2026, 23:57 (+11:00) |
| Script | `threshold_scores.py`, read-only: no generation, no rows written |
| Code | `7e3845d` unchanged, the phase 2a tip, equal in tree to `origin/main` `6be6288` (PR #55): `RELEVANCE_THRESHOLD` 0.3 and no floor. Neither phase 2b commit existed yet |
| Path | The shipped retrieval, as `answer_question` runs it for a one-off question: `embed_question` → `candidate_chunks(role, model)` → `rank` → `partial_matches(ranked)`, the real offer path. Each offered item's score is its first (best) passage's score in that ranked list |
| Roles | As each run names: the Employee as `loadtest01`, the Administrator as `corpus.admin`, the accounts phase 2a used. `permission_scope` was checked for both |
| FLM | v0.9.39, CLI and server. `check_flm.py` passed first (`check_flm_scores.txt`) |
| Database | `kmp_obj02_20261101`, 43 chunks. Candidates: 38 for the Employee, 43 for the Administrator |
| Set | `dev-set.json`, SHA-256 `19a0639a…6286f`, the file phase 2a used |
| D-40 | Each question was embedded 3 times, in separate calls. **All 93 vectors were identical to their run's first,** so the top-score spread was 0.000000. Both derivations are still conservative: an answerable run is judged by its lowest score over the repeats, a no-answer run by its highest |
| TOP_K | 25 binds: it is below both candidate counts. It never cut an expected source: in every answerable run, the expected source's best passage ranked first |

**The files:**

- `threshold_scores.json`: the raw output, every run's whole ranked list (chunk, manifest item,
  score) for each repeat.
- `threshold_scores_derive.txt`: the literal rule, printed by `threshold_scores.py --derive`.
- `threshold_scores_derive_margin.txt`: the margin rule, printed by `--derive … --margin 0.006`.
  That option was added after the measurement; `measure` is unchanged.
- `threshold_table.py`: prints the tables below from the JSON, at either rule's values.

**Re-running `threshold_scores.py` on this code will not reproduce the "before the floor"
offers.** It calls the shipped `partial_matches`, which now applies the floor.

## Every score used

### Answerable runs (24)

The column used is the best score of a passage of an expected source in the ranked list. In every
run that passage also ranked first. "Admitted" counts passages at or above each threshold, before
the context budget.

| run | role | expected source | its best score | top item | admitted at 0.3 / 0.4472 / 0.4231 |
|---|---|---|---|---|---|
| d17 | Employee | D18 | **0.448714** | D18 | 1 / 1 / 1 |
| d21@Administrator | Administrator | D16 | 0.469345 | D16 | 3 / 1 / 1 |
| d22@Administrator | Administrator | T02 | 0.483432 | T02 | 1 / 1 / 1 |
| d18 | Employee | D01 | 0.506587 | D01 | 11 / 1 / 1 |
| d19 | Employee | D01 | 0.515170 | D01 | 2 / 1 / 1 |
| d08 | Employee | D07 | 0.526700 | D07 | 6 / 2 / 2 |
| d15 | Employee | D11 | 0.534027 | D11 | 19 / 1 / 1 |
| d20 | Employee | D13 | 0.543487 | D13 | 2 / 1 / 1 |
| d12 | Employee | T03 | 0.564212 | T03 | 1 / 1 / 1 |
| d11@Administrator | Administrator | T05 | 0.583942 | T05 | 4 / 1 / 1 |
| d23 | Administrator | D09 | 0.594494 | D09 | 2 / 1 / 1 |
| d03 | Employee | D04 | 0.595959 | D04 | 20 / 19 / 19 |
| d13 | Employee | T04 | 0.599559 | T04 | 5 / 1 / 3 |
| d01 | Employee | D08 | 0.605865 | D08 | 6 / 1 / 2 |
| d14 | Employee | T01 | 0.614274 | T01 | 3 / 1 / 1 |
| d10 | Employee | D10 | 0.628999 | D10 | 2 / 1 / 1 |
| d07 | Employee | D06 | 0.633837 | D06 | 2 / 1 / 1 |
| d02 | Employee | D08 | 0.643146 | D08 | 11 / 2 / 2 |
| d16 | Employee | D17 | 0.649443 | D17 | 5 / 1 / 1 |
| d05 | Employee | D03 | 0.651671 | D03 | 12 / 2 / 2 |
| d28 | Employee | D19 | 0.670014 | D19 | 6 / 1 / 1 |
| d04 | Employee | D02 | 0.678356 | D02 | 23 / 1 / 1 |
| d09 | Employee | D20 | 0.709477 | D20 | 9 / 1 / 1 |
| d06 | Employee | D05 | 0.718767 | D05 | 21 / 1 / 1 |

No answerable run is lost at 0.3, at 0.4472, or at 0.4231 with the margin (0.4231 + 0.006 =
0.4291, below d17's 0.448714).

### No-answer runs (7)

The column used is the top in-scope score. Before the floor, each run was offered the five items in
the last column but one. These are the real offer path's output, with each item's best score.

| run | role | top score | declined at 0.3 | declined at 0.4472 | declined at 0.4231 with margin | offered before the floor (item score) | offered at 0.4036 |
|---|---|---|---|---|---|---|---|
| d22@Employee | Employee | 0.250707 | yes | yes | yes | D05 0.250707; D04 0.238189; T03 0.210895; T01 0.193208; D17 0.190302 | none |
| d27 | Administrator | 0.270264 | yes | yes | yes | D04 0.270264; D15 0.254218; D16 0.241790; D01 0.235657; D12 0.230814 | none |
| d11@Employee | Employee | 0.339343 | no | yes | yes | T01 0.339343; D02 0.310289; D08 0.292167; D04 0.278571; T03 0.257940 | none |
| d21@Employee | Employee | 0.390036 | no | yes | yes | D06 0.390036; T04 0.343443; T01 0.286846; D18 0.255977; D13 0.245434 | none |
| d24 | Employee | **0.397550** | no | yes | yes | D01 0.397550; D10 0.297211; D08 0.286551; D05 0.280163; D06 0.270541 | none |
| d26 | Employee | 0.439129 | no | yes | **no** (reaches generation) | D01 0.439129; D03 0.376840; D02 0.375677; D07 0.349547; D05 0.292846 | D01 0.439129, only on path B |
| d25 | Employee | 0.445715 | no | yes | **no** (reaches generation) | D20 0.445715; D01 0.316821; D03 0.289582; D14 0.288633; D17 0.276240 | D20 0.445715, only on path B |

## The literal rule's choice, set aside: 0.4472 and 0.4458

Committed in `3c839bb`, with its own end-to-end pass in `e2e/`.

- **The threshold:**
  - 0.3 lost nothing.
  - The tie interval was **(0.445715, 0.448714]**: it declines 7 of 7 and loses 0 of 24.
  - Its middle, 0.4472145, was written as **0.4472**: 0.001485 above d25 and 0.001514 below d17.
- **The floor:**
  - All 7 no-answer runs took path A, so all 7 real offers counted.
  - The highest was d25's D20, at 0.445715. The smallest four-place value above it is
    **0.4458**, a margin of 0.000085.
  - It was 0.0014 under the threshold, so path A could offer only items in [0.4458, 0.4472).
- **Why the user set it aside:**
  - **Both margins are inside the drift.** D-40 recorded query-vector drift of about 0.003,
    which phase 1 saw move mid-run. A margin of 0.0015, or of 0.000085, does not survive that.
  - **The floor nearly retired the offer.** A 0.0014 band under the threshold leaves FR-12's
    partial matches on path A in name only.

## The margin rule's choice: 0.4231 and 0.4036

From `threshold_scores_derive_margin.txt`:

### `RELEVANCE_THRESHOLD` = 0.4231

- **The bound from the answerable side:** d17's 0.448714 − m = **0.442714.**
- **Which no-answer runs can be declined with margin:** those with top + m ≤ 0.442714. That is 5
  of 7: d22@Employee, d27, d11@Employee, d21@Employee and d24.
  - **d26** (0.439129 + m = 0.445129) and **d25** (0.445715 + m = 0.451715) cannot be declined by
    any T that keeps d17 with margin.
- **The tie interval:** every T in **[0.397550 + m, 0.442714] = [0.403550, 0.442714]** declines
  those 5 and keeps all 24.
- **The middle:** 0.423132.
- **The rounding:** **0.4231**, to the nearest four places, a change of 0.000032.
- **The margins at 0.4231:**
  - **0.025550** above d24's 0.397550, the highest declined no-answer run. That is 0.019550 more
    than m.
  - **0.025614** below d17's 0.448714, the lowest answerable run. That is 0.019614 more than m.

### `PARTIAL_MATCH_FLOOR` = 0.4036

- **The runs path A declines at 0.4231:** d22@Employee, d27, d11@Employee, d21@Employee and d24.
  Their tops are all below 0.4231.
- **The highest partial match offered to them:** d24's D01, at 0.397550.
- **The lower bound:** 0.397550 + m = 0.403550.
- **The rounding:** rounded **up** to four places, it is **0.4036**, so that the bound holds.
  That puts F **0.006050** above D01.
- **The upper bound:** T − m = 0.4171. 0.4036 ≤ 0.4171, so the stop does not apply. F is 0.0135
  under that ceiling.
- **The band on path A:** items in **[0.4036, 0.4231)**, 0.0195 wide, against 0.0014 under the
  literal rule. On path B, every admitted item clears the floor.

### What d25 and d26 got

Both scored above 0.4231, so both reached generation. Each was supplied the one passage at or
above the threshold. **Both were answered, wrongly. Neither is counted as declined.**

| run | question | supplied | outcome | statements, with the item each cites |
|---|---|---|---|---|
| d25 | Is there staff parking at the new office building? | D20 (0.445715) | **answered**, 1 statement | [D20] "The Melbourne office will relocate to a new building on the other side of the river." |
| d26 | What is the policy on smoking at work? | D01 (0.439129) | **answered**, 4 statements | [D01] "Employee Leave Policy 2026 sets out the leave entitlements…"; [D01] "Leave requests are submitted through the human resources portal at least two weeks before…"; [D01] "Periods of high operational demand… may limit the number of people who can be away at once."; [D01] "Where employee leave policy 2026 affects customers or the public…" |

- **No leak.** D20 and D01 are both items an Employee may read.
- **Every citation passed verification.** Each cites the passage it was supplied, and set
  membership cannot judge whether a passage supports a statement (invariant 5, conceded). So
  `rejected_count` was 0 and the reply was an answer.
- **Phase 2a under the cap of 6** sent both runs to path B: the model declined, with
  `rejected_count` 0. At 0.3, d25 had 2 passages admitted (D20 and D01) and d26 had 4, not one.

## What each rule bought, and what it cost

These are the margin rule's shipped values. The literal rule's are given where they differ.

**The threshold, 0.4231.**

- **Bought:**
  - 5 of 7 no-answer runs are declined at path A with margin, against 2 at 0.3. Generation is
    never called for them.
  - d11@Employee and d21@Employee, which phase 2a's cap of 6 answered with loosely related
    statements, are among them. That part of phase 2a's trade-off is resolved.
  - Every answerable run keeps its expected source with 0.0256 to spare.
- **Cost:**
  - **d25 and d26 reach generation and were answered wrongly** (above). The literal rule's
    0.4472 declined them, but only 0.0015 from d17.
  - So the "declined where expected" row is 5/7, as in phase 2a, but it is a different two that
    fail.
  - **More passages again in a few prompts.** d01 and d13 admit a second and third item at
    0.4231 that 0.4472 excluded.
  - **d13 lost its match.** It was supplied T04, T03 and T01, and cited T04's actions to T03.
    That is phase 2a's wrong-passage citation, back where a second item came in.
- **Not measured, so not claimed:**
  - Questions worded differently from these 31, the frozen sets, and FR-13 follow-ups. A
    follow-up embeds its earlier questions too, so it scores differently.
  - D-37 found answerable questions down to 0.219 on the September corpus. A real question scoring
    between 0.30 and 0.4231 now gets the no-answer reply where it used to be answered.
  - `docs/demonstration-script.md`'s D-40 screen accepted an expected answer at a top score of
    0.35 or more, against 0.30. Its questions were not re-scored, because its database and the
    frozen sets are outside this phase.

**The floor, 0.4036.**

- **Bought:**
  - No no-answer run that path A declines is offered a partial match. Before, each was offered
    five items, at scores from 0.190 to 0.398.
  - A 0.0195 band under the threshold remains for path A to offer from.
- **Cost, as the rule asks it reported:** an answerable run that ends in no-answer, and would have
  been offered a partial match pointing at its expected source without the floor.
  - **None in either pass.** No answerable run ended in no-answer.
  - Every expected source scores at least 0.448714, above either floor.
- **The band was not exercised on this set.** No run took path A with a top score inside
  [0.4036, 0.4231), and no run took path B. So no partial match was offered anywhere in the
  margin pass. The band exists, but nothing here shows it in use.
- **Two costs neither rule counted:**
  1. **An empty offer now says path A ran.**
     - Path B admitted something at or above the threshold, which is above the floor, so a path-B
       reply's offer is never empty.
     - So `partial_matches: []` on a no-answer reply implies path A. Before the floor, that was
       true only when the caller's scope held nothing rankable.
     - A non-empty offer is consistent with either path.
     - This tells the caller nothing about material outside their scope, because the candidate set
       is scoped in the query (invariant 1). But it narrows item 7's byte-identical replies.
     - `apps/retrieval/partial_matches.py` and `docs/api-contract.md` say so.
  2. **d25's D20 is arguably related** to parking at the new office: it is the relocation notice.
     Under the margin values it is not offered to d25 at all: d25 is answered from it instead.

## End to end

### What ran

| | first pass: `3c839bb`'s values | **margin pass: this commit's values** |
|---|---|---|
| Folder | `e2e/` | `e2e-margin/` |
| When (+11:00), 8 November | 07:09:41–07:22:52 | 09:57:20–10:11:56 |
| Values in force | T 0.4472, F 0.4458, cap 6 | **T 0.4231, F 0.4036, cap 6** |
| Product files, SHA-256 before and after the pass | `constants.py` `dbd58490…`, `partial_matches.py` `4c2e61bf…`, `pipeline.py` `24f10a41…`, `ranking.py` `e32a36b8…` | `constants.py` `0bea38c0…`, `partial_matches.py` `4c2e61bf…`, `pipeline.py` `fdd0fa3a…`, `ranking.py` `e32a36b8…` |
| FLM | v0.9.39, `check_flm.py` passed first | v0.9.39, `check_flm.py` passed first |
| Rows (`QueryLog`, `AnswerCitation`, `Conversation`, `ContentChunk`) | 83, 199, 3, 43 before and after | 83, 199, 3, 43 before and after |

**Both passes:**

- **Script:** `threshold_floor_e2e.py`, which refuses to run unless the code's values equal the
  ones expected.
- **Path:** the shipped `answer_question`, in-process, each ask in a transaction that was rolled
  back, as phase 2a's accounts.
- **Recording:** a wrapper around `pipeline.rank` recorded the ranked list and changed nothing.
  The partial matches are the reply's own.
- **Scoring:** phase 2a's `summarise`.
- **Isolation:** nothing else ran beside either pass. The breaks and every pytest ran before or
  after.

### The table

| | phase 2a, cap 6 (T 0.3, no floor) | `3c839bb` (T 0.4472, F 0.4458) | **this commit (T 0.4231, F 0.4036)** |
|---|---|---|---|
| attempts that hit the ceiling | 0 | 0 | **0** |
| 503s | 0 | 0 | **0** |
| cap violations | 0 | 0 | **0** |
| answered, where expected | 24/24 | 24/24 | **24/24** |
| no answer, where expected | 5/7 (d11@E, d21@E answered) | 7/7, all path A | **5/7** (d25, d26 answered) |
| of which path A / path B | 2 / 3 | 7 / 0 | **5 / 0** |
| expected-answer match, cited to an expected source | 15/24 | 24/24 | **23/24** (d13 missed) |
| expected phrase anywhere in the answer | 20/24 | 24/24 | **24/24** |
| citations of an item the role may not read | 0 | 0 | **0** |
| generation attempts | 29 | 24 | **26**, all parsed on attempt 1 |
| completion tokens per attempt, median / max | 245 / 507 | 380 / 473 | **362 / 487** |
| seconds per attempt, median / max | 33.2 / 75.3 | 38.9 / 50.4 | **39.0 / 55.1** |
| seconds per ask, median / max | 31.7 / 75.7 | 23.5 / 50.7 | **25.7 / 55.4** |
| most statements in one answer | 6 | 6 | **6** |
| partial matches offered to no-answer runs | 5 runs × 5 items, 0.190–0.446 (inferred) | none | **none** |
| floor's cost (answerable runs losing an expected-source offer) | – | none | **none** |

**Phase 2a's partial matches are inferred, not recorded.** Its sweep did not record them. The runs
that ended in no-answer under its cap of 6 were d22@Employee, d27, d24, d25 and d26. Retrieval was
bit-identical across repeats tonight, on the same database, so each would have been offered the
five items in the no-answer table.

### Per run, margin pass

| run | expects | outcome | reason | supplied items | match | offered | without the floor |
|---|---|---|---|---|---|---|---|
| d01 | answer | answered | - | D03, D08 | yes | none | (answered) |
| d02 | answer | answered | - | D03, D08 | yes | none | (answered) |
| d03 | answer | answered | - | D04 (8 passages) | yes | none | (answered) |
| d04 | answer | answered | - | D02 | yes | none | (answered) |
| d05 | answer | answered | - | D03, D08 | yes | none | (answered) |
| d06 | answer | answered | - | D05 | yes | none | (answered) |
| d07 | answer | answered | - | D06 | yes | none | (answered) |
| d08 | answer | answered | - | D02, D07 | yes | none | (answered) |
| d09 | answer | answered | - | D20 | yes | none | (answered) |
| d10 | answer | answered | - | D10 | yes | none | (answered) |
| d11@Administrator | answer | answered | - | T05 | yes | none | (answered) |
| d11@Employee | none | no answer | no_relevant_passage | - | - | none | T01 0.339343; D02 0.310289; D08 0.292167; D04 0.278571; T03 0.257940 |
| d12 | answer | answered | - | T03 | yes | none | (answered) |
| d13 | answer | answered | - | T01, T03, T04 | **no** | none | (answered) |
| d14 | answer | answered | - | T01 | yes | none | (answered) |
| d15 | answer | answered | - | D11 | yes | none | (answered) |
| d16 | answer | answered | - | D17 | yes | none | (answered) |
| d17 | answer | answered | - | D18 | yes | none | (answered) |
| d18 | answer | answered | - | D01 | yes | none | (answered) |
| d19 | answer | answered | - | D01 | yes | none | (answered) |
| d20 | answer | answered | - | D13 | yes | none | (answered) |
| d21@Administrator | answer | answered | - | D16 | yes | none | (answered) |
| d21@Employee | none | no answer | no_relevant_passage | - | - | none | D06 0.390036; T04 0.343443; T01 0.286846; D18 0.255977; D13 0.245434 |
| d22@Administrator | answer | answered | - | T02 | yes | none | (answered) |
| d22@Employee | none | no answer | no_relevant_passage | - | - | none | D05 0.250707; D04 0.238189; T03 0.210895; T01 0.193208; D17 0.190302 |
| d23 | answer | answered | - | D09 | yes | none | (answered) |
| d24 | none | no answer | no_relevant_passage | - | - | none | D01 0.397550; D10 0.297211; D08 0.286551; D05 0.280163; D06 0.270541 |
| d25 | none | **answered** | - | D20 | - | none | (answered) |
| d26 | none | **answered** | - | D01 | - | none | (answered) |
| d27 | none | no answer | no_relevant_passage | - | - | none | D04 0.270264; D15 0.254218; D16 0.241790; D01 0.235657; D12 0.230814 |
| d28 | answer | answered | - | D19 | yes | none | (answered) |

Every status was 200. `threshold_table.py threshold_scores.json e2e-margin/e2e_T4231_F4036_N6.jsonl
--threshold 0.4231 --floor 0.4036 --margin 0.006` prints this table, and the same command on
`e2e/e2e_T4472_F4458_N6.jsonl` prints the first pass's. In the first pass, every answerable run
matched, and d25 and d26 were path-A no-answers.

### What was observed

- **The no-answer runs follow the threshold, not generation.** All five declined runs were
  declined at path A, and path B occurred in neither pass.
  - The two runs above the threshold were answered from the single loosely related passage they
    were given.
  - With one passage and an instruction to answer only from it, the model wrote what the passage
    says.
- **The match rate stayed high, with one miss.**
  - 23/24, against phase 2a's 15/24, on the dev set's weaker match test: a summary matches when it
    states any one key fact.
  - The likely cause is the same as the first pass's: most prompts carry only the expected source.
  - d13 is the exception, with three items supplied and T04's facts cited to T03.
- **No retry fired.** All 26 generation calls parsed on attempt 1, so the reduced retry (D-100)
  is still shown only by the tests.

## What it does not show

- **One development set of 31 runs.** The margin rule keeps 0.0256 from a run on each side. That
  is about 8 times D-40's drift, on these 31 questions only.
- **One end-to-end pass per setting.** Phase 1 showed the same prompt can give different replies.
  The no-answer half depends only on retrieval, which was deterministic tonight.
- **Anything about the frozen sets.** They were not run. They measure this; they did not tune it.
- **The partial-match band in use.** No run in either pass was offered a partial match.
- **That the results were not shaped by the choice.** T was chosen to keep every answerable run's
  expected source admitted, on these runs, so "answered where expected" is partly a consequence of
  the rule. The match row is not: neither rule looked at answers.
