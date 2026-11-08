# Development set v2, in users' wording, and the threshold and floor re-chosen on it: 8 November 2026

Step 7, phase 2c, of the user's post-M6 order. The work, in order:

1. rebuild the development set in users' wording (`corpus/objective-02/dev-set-v2.json`);
2. re-choose `RELEVANCE_THRESHOLD` and `PARTIAL_MATCH_FLOOR` on it alone, by phase 2b's margin
   rule (m = 0.006);
3. run it end to end against a 0.30 baseline.

**The values, in order:**

| | `RELEVANCE_THRESHOLD` | `PARTIAL_MATCH_FLOOR` |
|---|---|---|
| phase 2b, on `dev-set.json` (on `main`, `a53c5de`) | 0.4231 | 0.4036 |
| phase 2c, on `dev-set-v2.json` (`2ea9e95`), not shipped | 0.2400 | 0.2060 |
| **shipped, by the user's decision (see "What ships")** | **0.30** (D-37's) | **0.0**: none, D-56 open |

**Read this first: on dev-set-v2, the rule's values do worse end to end than the 0.30 baseline.**

| | 0.30, no floor | 0.24 / 0.206 |
|---|---|---|
| no-answer runs declined | 7 of 8 | 3 of 8 |
| expected-answer matches | 22 of 32 | 15 of 32 |
| answered where expected | 29 of 32 | 30 of 32 |

Lowering the threshold admits more passages. The model then cites the wrong items more often, and
it answers no-answer questions from loosely related ones. The rule could not see that, because it
weighs scores, not answers. The values were committed (`2ea9e95`) as the brief asked, with this
result beside them, for the user to decide.

## What ships

**The user's decision (8 November 2026): `RELEVANCE_THRESHOLD = 0.30`, D-37's value, with the cap
of 6. The floor is set by the same margin rule at T = 0.30, from dev-set-v2's measured scores
alone, with no new model runs.**

- **0.4231**, chosen on `dev-set.json`, lost answerable questions on users' wording: 14 of
  dev-set-v2's 32 score below it, and the frozen thirty's after put seven on path A.
- **0.24**, the margin rule on dev-set-v2, did worse end to end than 0.30 (the table above).
- **So 0.30 ships, and generation, now capped, carries most of the declining.**
- **The answers at 0.30 are those of the baseline pass** in `dev-set-v2/e2e-baseline/`. A floor
  changes only the partial-match offer, so that pass stands for them.

**The floor's derivation (m = 0.006):**

1. **The runs path A declines at 0.30** (top score below 0.30), from `dev-set-v2/scores_v2.json`:
   - u30@Employee: 0.199907;
   - u31@Employee: 0.287538;
   - **u07: 0.287909, answerable** (its top item D18 outranks D02);
   - **u24: 0.292898, answerable** (its top item D20 outranks T03).
2. **The highest partial match offered to any of them** is u24's D20, at 0.292898.
3. **F ≥ 0.292898 + 0.006 = 0.298898**, which rounds up to 0.2989.
4. **F ≤ T − m = 0.294.** 0.2989 exceeds 0.294, so **the rule cannot set a floor.**

**So no floor is set:** `PARTIAL_MATCH_FLOOR = 0.0`, and **D-56 stays open.** This is D-56's
behaviour before phase 2b: the five nearest in-scope items are offered beside a no-answer, whatever
their score. 0.0 differs from "none" only in not offering a negative-cosine passage, which no
development run's offer had.

**What a different reading would have done.** Counting only the no-answer runs, as phase 2b's
wording did, the highest offer is u31@Employee's T01 at 0.287538. That gives F ≥ 0.293538, or
0.2936, under the ceiling. It would also remove the offers pointing u07 and u24 at their expected
sources: D02 at 0.280085 and T03 at 0.291925, each ranked second. The brief's wording ("any
dev-set-v2 run that path A declines") decided it, and the alternative's cost points the same way.

**What no floor does to partial matches, from the scores alone:**

- **Every dev-set-v2 no-answer run that ends in no-answer is still offered its five nearest
  items.**
  - **u30@Employee and u31@Employee** take path A at 0.30 on every pass, so they are always
    offered:
    - u30@E: D04 0.199907; T03 0.187338; T01 0.177938; D14 0.147205; D11 0.133782.
    - u31@E: T01 0.287538; T03 0.262941; D14 0.249229; D05 0.202338; T04 0.193479.
  - **The other six reach generation** and are offered their five nearest only if they end on path
    B. Their lists are the no-answer table's, with scores from 0.200248 to 0.487314.
  - In the 0.30 pass, u32@E, u33, u34, u35 and u36 ended on path B and were offered theirs. u37 was
    answered and was offered nothing.
  - **Unrelated items are therefore still offered to questions the corpus cannot answer.** That is
    D-56's open gap, unchanged.
- **The floor's cost to answerable runs: none.** No floor removes nothing.
  - u07 and u24 (path A at 0.30) are offered their expected sources, D02 and T03, second in each
    list.
  - u17, which ended on path B in the 0.30 pass, is offered D14, its expected source, first.

**The evidence for this section:**

- the scores in `dev-set-v2/scores_v2.json`;
- the answers in `dev-set-v2/e2e-baseline/`.

## Why v2, and the contamination it carries

- **Why.** The step 7 "after" on the frozen thirty (`after/`, PR #57, run on `a53c5de` with 0.4231)
  put seven answerable questions on path A, where 1 November had two. Their right source was
  retrieved, but it scored 0.33 to 0.42, under 0.4231.
- **The diagnosis.** `dev-set.json`'s questions were written from the documents and share their
  wording, so they score higher than questions phrased as users ask them.
- **The user's decision:** rebuild the dev set in users' wording, and re-choose.

**The contamination is disclosed, and the coordinator records it as a D-101 note.** The frozen
set has now informed this choice, so it no longer tests the threshold independently. It was kept
as small as possible:

- `questions.json`, `threads.json` and the after's per-question results were not read. Nor was
  D-101's text, in case it quotes them.
- The only contact with the frozen sets is the automated overlap check below. It was changed to
  print frozen **identifiers** and scores, never frozen text.
- No question was aimed at the seven documents the after found missing. Which documents they were
  was not read. The questions are spread across the corpus, one or two per item, all 25 items
  covered.

## The development set

`corpus/objective-02/dev-set-v2.json`, SHA-256 `cb7e2815…1efd`: 37 questions, 40 runs. The
harness's validator (`scripts/question_set.py`) reports no problems.

| Kind | Questions | Runs | Expected |
|---|---|---|---|
| ordinary, Employee | 27 | 27 | an answer |
| ordinary, Administrator | 2 (u28 D15/T02, u29 T02) | 2 | an answer |
| scoped, both roles | 3 (u30 D09, u31 D16, u32 T05) | 6 | the Administrator an answer, the Employee none |
| no-answer | 5 (u33–u35 and u37 Employee, u36 Administrator) | 5 | none |
| **total** | **37** | **40** | **32 answerable, 8 no-answer** |

**How the questions were written:**

- **From the goal, as a person would type it.** "how long do we have to hang on to old invoices and
  finance paperwork?", "can I take the company car home over the weekend?". No sentence or
  distinctive phrase is lifted from a document.
- **Some vague or indirect:** u01, u07, u17, u25, u27, u29.
- **Some with typos or shorthand:** u02 "new hire here", u06 "im sick tmrw, do i need a drs
  note?", u09 "hw many quotes", u12 "wfh", u19 "forgot my pw", u26 "30 ppl".
- **Required by the order:**
  - the two onboarding questions, u01 and u02;
  - records retention, u03;
  - IT equipment, u04.
- **One hard no-answer:** u37, "how do I apply for parental leave?". D01 covers annual, personal
  and carer's leave, and says nothing about parental leave.
- **`expected_answer` and `accepted` are the documents' words for the fact,** because they are
  matched against the answer, not the question. As in `dev-set.json`, an answer matches when it
  states any one key fact, cited to an expected source. That is the weaker test, and the file says
  so.

### How much each question borrows from its source

`dev-set-v2/wording_overlap.py` measures, for every answerable run, the share of the question's
content words that also appear in its expected source's best-ranked passage. "Content words" uses
phase 2a's overlap-check definition: stopwords dropped and a light suffix strip.

| set | n | min | Q1 | median | Q3 | max | mean | questions sharing no content word |
|---|---|---|---|---|---|---|---|---|
| `dev-set.json` | 24 | 0.25 | 0.50 | **0.67** | 0.80 | 1.00 | **0.64** | 0 |
| `dev-set-v2.json` | 32 | 0.00 | 0.20 | **0.33** | 0.52 | 1.00 | **0.39** | 4 |

**The v2 overlap is clearly lower: the median is halved.**

- **The v2 questions at the top** share only the words that name the subject: u18 "book / meeting /
  room", u25 "customers / cancelling", u32 "phishing / test".
- **Per-run values** are in `dev-set-v2/wording_overlap.txt`.

### Overlap with the frozen sets

`dev-set-v2/overlap_v2.py` is phase 2a's check with the same thresholds, fixed in advance:

- exact match;
- content-word Jaccard ≥ 0.5;
- difflib ratio ≥ 0.8;
- embedding cosine ≥ 0.90, each question embedded through the shipped query path.

Each of the 37 questions was compared with all 56 frozen questions and turns: 2,072 pairs.

- **First run: 1 flagged.** The first u35, "can i bring my dog into the office?", scored cosine
  0.937 against `questions.json n04`.
  - It was replaced by a question on another subject, without `n04` being read.
  - The first output is `dev-set-v2/overlap_v2_first.txt`.
- **Final run: 0 flagged** (`dev-set-v2/overlap_v2.txt`). The highest values:
  - cosine 0.812, u32 vs `s04`;
  - Jaccard 0.444, u32 vs `s04`;
  - difflib 0.727, u09 vs `q06`.

  Phase 2a's v1 maximum cosine was 0.781.

## The scores

| | |
|---|---|
| When | 8 November 2026, 12:46 (v2) and 12:47 (`dev-set.json`, re-measured), +11:00 |
| Script | `threshold_scores.py --set dev-set-v2.json --unfloored`: the 7 November measurement, with two options added. `--set` chooses the file. `--unfloored` lifts the floor in this process, so the offers are the five nearest items whatever their score, as on 7 November, before the floor existed |
| Code | `6d0948b` (PR #57's branch, on `a53c5de`): `RELEVANCE_THRESHOLD` 0.4231, which does not affect scores |
| FLM | v0.9.39. `check_flm.py` passed first |
| Database | `kmp_obj02_20261101`, 43 chunks. Read-only |
| D-40 | 3 embeddings per question. All 120 vectors were identical to their run's first |
| TOP_K | never cut an expected source |

**Drift between sessions, observed:**

- `dev-set.json`, re-measured 13 hours after the 7 November measurement, kept every top item, but
  its top scores moved by up to **0.0021** (median 0.0005).
- The end-to-end passes moved some v2 scores by up to about 0.0008 from the scores pass.

This is the D-40 drift the margin is for. Repeats within one process were bit-identical.

### Answerable runs (32)

The column used is the best score of a passage of an expected source.

| run | role | expected source | best score | top item | lost at 0.30 | lost at 0.24 with margin | admitted at 0.30 / 0.24 |
|---|---|---|---|---|---|---|---|
| u07 | Employee | D02 | **0.280085** | D18 | yes | no | 0 / 3 |
| u27 | Employee | D03 | 0.290746 | D18 | yes | no | 2 / 5 |
| u24 | Employee | T03 | 0.291925 | D20 | yes | no | 0 / 2 |
| u06 | Employee | D01 | 0.324485 | D01 | no | no | 1 / 4 |
| u25 | Employee | T04 | 0.337682 | D06 | no | no | 2 / 3 |
| u21 | Employee | D19 | 0.356691 | D01 | no | no | 5 / 10 |
| u20 | Employee | D18 | 0.368519 | D18 | no | no | 1 / 2 |
| u31@Administrator | Administrator | D16 | 0.370348 | D16 | no | no | 1 / 4 |
| u23 | Employee | T01 | 0.373679 | T01 | no | no | 4 / 16 |
| u08 | Employee | D03 | 0.399020 | D03 | no | no | 1 / 2 |
| u05 | Employee | D01 | 0.405014 | D01 | no | no | 2 / 5 |
| u09 | Employee | D05 | 0.409976 | D05 | no | no | 1 / 2 |
| u03 | Employee | D04 | 0.417940 | D04 | no | no | 16 / 25 |
| u15 | Employee | D12 | 0.422220 | D12 | no | no | 1 / 2 |
| u19 | Employee | D18 | 0.431728 | D18 | no | no | 2 / 3 |
| u04 | Employee | D02 | 0.438368 | D02 | no | no | 6 / 9 |
| u01 | Employee | D08 | 0.452521 | D08 | no | no | 6 / 20 |
| u12 | Employee | D07 | 0.462550 | D07 | no | no | 2 / 8 |
| u32@Administrator | Administrator | T05 | 0.463229 | T05 | no | no | 2 / 6 |
| u26 | Employee | D17 | 0.467124 | D17 | no | no | 1 / 3 |
| u11 | Employee | D07 | 0.479480 | D07 | no | no | 5 / 10 |
| u13 | Employee | D10 | 0.483003 | D10 | no | no | 1 / 6 |
| u16 | Employee | D13 | 0.497091 | D13 | no | no | 3 / 15 |
| u29 | Administrator | T02 | 0.505390 | T02 | no | no | 3 / 9 |
| u28 | Administrator | D15, T02 | 0.508161 | D15 | no | no | 4 / 13 |
| u10 | Employee | D06 | 0.516239 | D06 | no | no | 3 / 4 |
| u14 | Employee | D11 | 0.539445 | D11 | no | no | 8 / 25 |
| u30@Administrator | Administrator | D09 | 0.576957 | D09 | no | no | 2 / 2 |
| u18 | Employee | D17 | 0.581175 | D17 | no | no | 1 / 6 |
| u02 | Employee | D08 | 0.606785 | D08 | no | no | 8 / 24 |
| u22 | Employee | D20 | 0.630030 | D20 | no | no | 4 / 14 |
| u17 | Employee | D14 | 0.682126 | D14 | no | no | 7 / 19 |

**The diagnosis holds on v2.**

- 14 of the 32 answerable runs score below 0.4231, so phase 2b's threshold would lose them.
- 3 score below 0.30, so even D-37's threshold would lose them.
- In 5 runs another item outranks the expected source: u07, u21, u24, u25 and u27.

### No-answer runs (8)

The column used is the top in-scope score. The offers are the real offer path's output with the
floor lifted.

| run | role | top score | declined at 0.30 | declined at 0.24 with margin | offered before the floor (item score) |
|---|---|---|---|---|---|
| u30@Employee | Employee | **0.199907** | yes | **yes** | D04 0.199907; T03 0.187338; T01 0.177938; D14 0.147205; D11 0.133782 |
| u31@Employee | Employee | 0.287538 | yes | no | T01 0.287538; T03 0.262941; D14 0.249229; D05 0.202338; T04 0.193479 |
| u35 | Employee | 0.300608 | no | no | D01 0.300608; D03 0.298701; D18 0.256061; D07 0.247936; D17 0.246659 |
| u34 | Employee | 0.322682 | no | no | D01 0.322682; D10 0.272332; D07 0.248718; D05 0.225349; D03 0.200248 |
| u32@Employee | Employee | 0.329578 | no | no | D02 0.329578; T01 0.271614; D18 0.263776; D20 0.260252; D08 0.237874 |
| u36 | Administrator | 0.338991 | no | no | T04 0.338991; D16 0.320987; D01 0.270889; D08 0.259853; T05 0.253295 |
| u33 | Employee | 0.346883 | no | no | D18 0.346883; D02 0.338625; D17 0.259467; D03 0.256507; D14 0.211862 |
| u37 | Employee | 0.487314 | no | no | D01 0.487314; D07 0.265677; D10 0.262258; D03 0.256027; D20 0.240693 |

**No threshold separates the two on v2.** Five no-answer runs (u35, u34, u32@E, u36 and u33) score
above three answerable ones (u07, u27, u24), and u37 scores above 22 of the 32. That is D-37's
finding, more starkly.

## The rule, applied (m = 0.006)

From `dev-set-v2/derive_margin_v2.txt` (`threshold_scores.py --derive … --margin 0.006`):

- **The bound from the answerable side:** u07's 0.280085 − m = **0.274085.**
- **Declinable with margin** (top + m ≤ 0.274085): **1 of 8, u30@Employee** (0.199907).
  - The next lowest, u31@Employee at 0.287538, already scores above u07.
- **The tie interval:** [0.199907 + m, 0.274085] = **[0.205907, 0.274085].**
- **The middle:** 0.239996, rounded to the nearest four places: **T = 0.2400**, a change of
  0.000004.
- **The margins:** **0.040093** above u30@Employee and **0.040085** below u07.
- **The fallback did not apply.** It takes effect only if no run can be declined, and one can, so
  the middle was taken.
- **The floor:**
  - The runs path A declines at 0.24 are u30@Employee alone. Its highest offer is D04, at
    0.199907.
  - 0.199907 + m = 0.205907, rounded **up** to four places: **F = 0.2060**, 0.006093 above D04.
  - The ceiling is T − m = 0.2340, and 0.2060 is under it, so the stop does not apply.
  - The band on path A is [0.2060, 0.2400), 0.0340 wide.
  - **The floor rests on one declined run.**

## End to end

Two passes over dev-set-v2, the same code but for the two values, each ask rolled back, with the
cap of 6.

| | baseline | new values |
|---|---|---|
| Folder | `dev-set-v2/e2e-baseline/` | `dev-set-v2/e2e-new/` |
| When (+11:00) | 12:48:02–12:59:59 | 13:01:23–13:14:58 |
| Values used | **T 0.30, no floor**: reassigned in the process (`--patch-threshold 0.3 --patch-floor=-inf`) over code holding 0.4231 / 0.4036 | **T 0.24, F 0.206**, from the code, nothing patched |
| Product files, SHA-256 before = after | `constants.py` `0bea38c0…`, `partial_matches.py` `4c2e61bf…`, `pipeline.py` `fdd0fa3a…`, `ranking.py` `e32a36b8…` | `constants.py` `9d71dac9…`, `partial_matches.py` `4c2e61bf…`, `pipeline.py` `23bde325…`, `ranking.py` `e32a36b8…` |

**Both passes:**

- `check_flm.py` passed first.
- Rows were unchanged: `QueryLog` 83, `AnswerCitation` 199, `Conversation` 3, `ContentChunk` 43.
- The script was `threshold_floor_e2e.py --set dev-set-v2.json`, scored with phase 2a's
  `summarise`.

| | **0.30, cap 6, no floor** | **0.24 / 0.206, cap 6** |
|---|---|---|
| attempts that hit the ceiling | 0 | 0 |
| 503s | 0 | 0 |
| cap violations | 0 | 0 |
| answered, where expected | 29/32 | 30/32 |
| answerable runs ending in no-answer | u07, u24 (path A); u17 (path B) | u05, u13 (path B) |
| **no answer, where expected** | **7/8**: path A 2, path B 5 | **3/8**: path A 1, path B 2 |
| no-answer runs answered (wrongly) | u37 (cites D01) | u31@E (D14), u32@E (D18), u34 (D07, D10), u35 (D18), u37 (D07) |
| **expected-answer match, cited to an expected source** | **22/32** | **15/32** |
| expected phrase anywhere in the answer | 23/32 | 21/32 |
| citations of an item the role may not read | 0 | 0 |
| generation attempts | 36 | 39 |
| completion tokens per attempt, median / max | 144.5 / 514 | 134 / 484 |
| seconds per attempt, median / max | 16.1 / 54.5 | 16.6 / 53.0 |
| seconds per ask, median / max | 16.1 / 54.8 | 16.9 / 54.6 |
| most statements in one answer | 6 | 6 |
| partial matches offered to no-answer runs | 7 runs × 5 items, 0.134–0.347 | 2 runs × 5 items (u33, u36, path B), 0.212–0.347; none to u30@E |
| floor's cost (an answerable run losing an expected-source offer) | – | none: u05 and u13 were offered their expected source first |

**What the comparison shows:**

- **More passages, worse answers.** At 0.24 most prompts carry several items: u01 and u02 carry 11
  each, u11 and u21 carry 10, u17 carries 13.
  - **Wrong-passage citations grew.** u06, u11, u21, u22, u28 and u31@Administrator matched at
    0.30 and not at 0.24, each citing another supplied item (u22 cites D01, u28 D05, u31@Admin
    T01 and T03).
  - **u05 and u13 ended in path B.** The model declined with the right passage in front of it, and
    others beside it.
- **Wrong answers to no-answer questions.**
  - At 0.30, six no-answer runs reached generation. The model declined five, with 13-token empty
    replies (u32@E, u33, u34, u35 and u36), and answered u37.
  - At 0.24, seven reached generation. The model declined only u33 and u36. It answered u32@E,
    u34 and u35, which it had declined at 0.30, and also u31@E (path A at 0.30) and u37, each
    from whatever loosely related passages were supplied.
  - There was no leak: every cited item is one the role may read.
- **What 0.24 gained:** u07 and u24, path A at 0.30, were answered, and u24 matched. u17, path B at
  0.30, was answered, though without a match.
- **One pass each.** Phase 1 showed the same prompt can give different replies, so one pass does
  not settle a 7-point match difference. The direction is consistent across runs, though:
  admitting more lowered the match rate in phase 2b's d13 as well.

### Per run, at the new values

| run | expects | outcome | reason | supplied items | match | offered |
|---|---|---|---|---|---|---|
| u01 | answer | answered | - | 11 items | - | - |
| u02 | answer | answered | - | 11 items | - | - |
| u03 | answer | answered | - | D04 | yes | - |
| u04 | answer | answered | - | 9 items | - | - |
| u05 | answer | **no answer** | no_statement_verified | - | - | D01 0.406139; D10 0.328730; D08 0.253969; D04 0.248926; D14 0.243803 |
| u06 | answer | answered | - | 4 items | - | - |
| u07 | answer | answered | - | 3 items | - | - |
| u08 | answer | answered | - | D03 and 1 more | yes | - |
| u09 | answer | answered | - | D05 and 1 more | yes | - |
| u10 | answer | answered | - | 4 items | - | - |
| u11 | answer | answered | - | 10 items | - | - |
| u12 | answer | answered | - | 8 items | yes | - |
| u13 | answer | **no answer** | no_statement_verified | - | - | D10 0.483003; D01 0.299430; D06 0.262868; D03 0.256479; D05 0.255973 |
| u14 | answer | answered | - | 9 items | yes | - |
| u15 | answer | answered | - | D12 and 1 more | yes | - |
| u16 | answer | answered | - | 10 items | - | - |
| u17 | answer | answered | - | 13 items | - | - |
| u18 | answer | answered | - | 6 items | yes | - |
| u19 | answer | answered | - | 3 items | yes | - |
| u20 | answer | answered | - | 2 items | yes | - |
| u21 | answer | answered | - | 10 items | - | - |
| u22 | answer | answered | - | 11 items | - | - |
| u23 | answer | answered | - | 8 items | yes | - |
| u24 | answer | answered | - | 2 items | yes | - |
| u25 | answer | answered | - | 3 items | yes | - |
| u26 | answer | answered | - | 3 items | yes | - |
| u27 | answer | answered | - | 5 items | - | - |
| u28 | answer | answered | - | 10 items | - | - |
| u29 | answer | answered | - | 9 items | - | - |
| u30@Administrator | answer | answered | - | 2 items | yes | - |
| u30@Employee | none | no answer | no_relevant_passage | - | - | none |
| u31@Administrator | answer | answered | - | 4 items | - | - |
| u31@Employee | none | **answered** | - | 3 items | - | - |
| u32@Administrator | answer | answered | - | 6 items | yes | - |
| u32@Employee | none | **answered** | - | 4 items | - | - |
| u33 | none | no answer | no_statement_verified | - | - | D18 0.346883; D02 0.338625; D17 0.259467; D03 0.256507; D14 0.211862 |
| u34 | none | **answered** | - | 3 items | - | - |
| u35 | none | **answered** | - | 5 items | - | - |
| u36 | none | no answer | no_statement_verified | - | - | T04 0.338991; D16 0.320987; D01 0.270889; D08 0.259853; T05 0.253295 |
| u37 | none | **answered** | - | 5 items | - | - |

"Supplied items" counts the passages the context budget sent. The full per-run tables for both
passes, with every supplied item, are printed by:

    threshold_table.py dev-set-v2/scores_v2.json dev-set-v2/e2e-new/e2e_v2_T2400_F2060_N6.jsonl --threshold 0.24 --floor 0.206 --margin 0.006

and the same command on the baseline's file.

## The old `dev-set.json` at the new values (scores only)

Re-measured at 12:47 (`dev-set-v2/scores_v1.json`), and read at T 0.24, F 0.206, m 0.006:

| | at 0.4231 / 0.4036 (phase 2b) | at 0.30 | **at 0.24 / 0.206** |
|---|---|---|---|
| answerable runs lost (of 24) | 0 | 0 | **0** |
| no-answer runs declined at path A (of 7) | 5 | 2 | **0** |
| passages admitted, answerable median (range) | 1 (1–19) | 5 (1–23) | **17 (1–25)**; 9 runs reach TOP_K's 25 |

- **At 0.24, every one of `dev-set.json`'s no-answer runs reaches generation.** Its lowest top
  score is d22@Employee's 0.250362.
- **Phase 2b showed what happens there.** With one loosely related passage the model answered; with
  several, at 0.30, it mostly declined. That outcome rests on generation, not on the threshold.

## What it does not show

- **One development set of 40 runs, drafted by one agent.** Users' wording is imitated, not
  sampled.
- **One end-to-end pass per setting.**
- **Anything independent about the frozen sets.** They informed this choice (D-101's note), so a
  re-run of the after measures the threshold on data that shaped it.
- **A better threshold.** The rule's objective (decline with margin, lose nothing with margin)
  yields 0.24 here, and the end-to-end pass says 0.24 is worse than 0.30 on this set. The rule did
  not ask which threshold gives the best answers, and nothing here chooses one.

## Deliberate breaks

The procedure was phase 2b's: back up the product file to `<name>.floor.orig`, break, run the 13
new tests, restore, and check by SHA-256. Every restore was identical (`constants.py`
`9d71dac9…`, `partial_matches.py` `4c2e61bf…`).

| break | edit | new tests failing |
|---|---|---|
| B1 | floor check removed | P1 P3 L1 L3 L4 A1 |
| B2 | `<` → `<=` | P2 |
| B3 | partial_matches floors at 0.24 | P1 P2 P4 L3 |
| B4 | T = 0.30 (above u07's 0.280085) | C1 L2 |
| B5 | T = 0.4231 (phase 2b's) | C1 L2 |
| B6 | T = 0.20 (under u30@E + m) | C1 C3 P4 L3 |
| B7 | F = 0.1999 (below u30@E's D04) | C2 P3 L1 A1 |
| B8 | F = 0.2059 (floor edge, under + m) | C2 |
| B9 | F = 0.2341 (floor edge, over T − m) | C2 C3 |
| B10 | F = 0.4036 (phase 2b's) | C2 C3 P4 L3 |
| B11 | F = 0 | C2 P3 L1 L4 A1 |
| B12 | T = `Decimal('0.24')`, constants tests alone | C1 C3 |

Every new test failed under at least one break.
