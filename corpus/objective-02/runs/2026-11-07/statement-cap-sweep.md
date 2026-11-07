# The statement cap, swept over the development set: 7 November 2026

Step 7, phase 2a, of the user's post-M6 order. It builds the user's decisions of 7 November, which
the coordinator records as D-100:

1. Ask for at most N statements, and enforce it. A reply that hits the ceiling or breaks the cap
   makes the next attempt ask for fewer.
2. Successful attempts go to their own log file (`ATTEMPTS_LOG_PATH`).
3. The phase 1 scripts stay in this folder as provenance.

N is chosen here from a new development set, `corpus/objective-02/dev-set.json`, and from
nothing else. The frozen sets (`questions.json`, `threads.json`) were neither read for tuning nor
edited (D-93).

**The choice: N = 6.** The rule was zero ceiling hits and zero 503s first, then the best
expected-answer match, then the smaller N on a tie.

- N3 and N6 had zero of both.
- N4 and N5 each had one 503.
- N6 matched 15 of 24 and N3 matched 13 of 24.

The caveats are under "What it does not show".

## What ran

| | |
|---|---|
| When (local, +11:00) | baseline 20:11:51–20:41:19; N3 20:49:14–21:03:29; N4 21:03:40–21:22:33; N5 21:22:46–21:43:13; N6 21:43:25–22:03:10. One at a time, never in parallel |
| Code, baseline | `ed769c8` (phase 1, PR #54), unchanged: no cap in the prompt, identical retries |
| Code, N3–N6 | this commit's working tree. Each sweep sets `apps.ai.generation.MAXIMUM_STATEMENTS` to N in its own process, the one name the loop reads the first attempt's cap from. The providers pass every attempt's cap explicitly to the prompt and the parser, so `MAXIMUM_STATEMENTS` in `apps/core/constants.py` (4 while the sweeps ran, 6 in the commit) did not affect them. Since the sweeps, two lines changed: that constant, with its comment, and one docstring sentence in `apps/ai/generation.py` naming the attempt sequence. Every other product file is byte-identical to what the sweeps ran, checked by SHA-256 against the backups taken before them |
| FLM | v0.9.39, CLI and server, `check_flm.py` passing before every sweep (`statement-cap-sweep/check_flm_*.txt`) |
| Database | `kmp_obj02_20261101`: 43 chunks, unchanged. Each ask ran inside a transaction that was rolled back. Rows before and after every sweep: `QueryLog` 83, `AnswerCitation` 199, `Conversation` 3, `ContentChunk` 43 |
| How | `sweep_statement_cap.py`: the shipped `answer_question`, in-process. Employee runs are asked as `loadtest01`, Administrator runs as `corpus.admin` |
| Set | `corpus/objective-02/dev-set.json`, SHA-256 `19a0639a…6286f`, the same file for all five sweeps |
| Overlap | Two short targeted pytest runs (19 s and 13 s) and a `makemigrations --check` ran during the baseline and N3 sweeps. Nothing else ran beside any sweep |

## The development set

28 questions, 31 runs: the three scoped questions are asked once per role.

| Kind | Questions | Runs | Expected |
|---|---|---|---|
| ordinary, Employee | 20 | 20 | an answer |
| ordinary, Administrator | 1 (d23, D09) | 1 | an answer |
| scoped, both roles | 3 (d11 T05, d21 D16, d22 T02) | 6 | the Administrator an answer, the Employee none |
| no-answer | 4 (d24–d26 Employee, d27 Administrator) | 4 | none |

- **Required by the order:**
  - both onboarding questions the alpha was asked (d01, d02);
  - "How are records managed and retained?" (d03);
  - the IT acceptable-use question (d04).
- **Most answerable questions ask for a summary or a procedure,** because the cap is about long
  answers.
- **Sources:** 22 of the 25 corpus items are a source. D12, D14 and D15 are not.
- **How a summary is scored.** `accepted` may list other key facts of the answer, and a summary
  matches when it states any one of them, cited to an expected source. That is weaker than the
  frozen set's matching, and the file says so.

**Overlap with the frozen sets: none found** (`dev_set_overlap.py`, output in
`dev_set_overlap.txt`).

- **What was compared:** each of the 28 questions against all 56 frozen questions: 30 from
  `questions.json`, and 26 turns and spelled-out forms from `threads.json`. That is 1,568 pairs.
- **Three ways:** an exact match; content-word Jaccard and difflib's ratio; and the cosine
  between the two embeddings, each embedded through the shipped query path.
- **Flag thresholds, set in advance:** exact, Jaccard ≥ 0.5, difflib ≥ 0.8, or cosine ≥ 0.90.
- **Flagged: 0.**
- **The highest values:**
  - cosine 0.781, d28 "Summarise the rules for using a fleet vehicle." against t04's "Who is
    allowed to drive the fleet vehicles?";
  - Jaccard 0.333, d23 against s01, both about Project Atlas;
  - difflib 0.629, d25 against n03.
- **The harness can read the file:** its own validator, `scripts/question_set.py`, reports no
  problems.

## Results

| | baseline | N3 | N4 | N5 | N6 |
|---|---|---|---|---|---|
| attempts that hit the ceiling | 8 | 0 | 0 | 0 | 0 |
| 503s | 2 | 0 | 1 | 1 | 0 |
| cap violations | – | 0 | 0 | 0 | 0 |
| answered, where expected | 21/24 | 24/24 | 23/24 | 23/24 | 24/24 |
| no answer, where expected | 6/7 | **3/7** | **3/7** | **3/7** | 5/7 |
| expected-answer match, cited to an expected source | 9/24 | 13/24 | 14/24 | 15/24 | **15/24** |
| expected phrase anywhere in the answer | 17/24 | 19/24 | 20/24 | 19/24 | 20/24 |
| citations of an item the role may not read | 0 | 0 | 0 | 0 | 0 |
| completion tokens per attempt, median / max | 109 / 800 | 208 / 259 | 283 / 369 | 347 / 415 | 245 / 507 |
| seconds per attempt, median / max | 23.3 / 117.4 | 30.9 / 42.7 | 39.7 / 53.1 | 48.6 / 61.7 | 33.2 / 75.3 |
| seconds per ask, median / max | 19.9 / 350.7 | 30.6 / 43.2 | 39.5 / 154.8 | 35.3 / 163.7 | 31.7 / 75.7 |
| most statements in one answer | 9 | 3 | 4 | 5 | 6 |

The per-run matrix is in `statement-cap-sweep/sweep_table.txt`, from `sweep_table.py`.

## What was observed

- **The cap ended the ceiling hits and the length 503s.**
  - In the baseline, 8 attempts reached 800 of 800 tokens: d03's three, d06's three and d04's
    first two. d03 and d06 were 503s; d04 was answered on attempt 3, at 746 tokens.
  - Under every cap, no attempt passed 507 tokens, and every reply held to its cap.
  - d03, the phase 1 question, was answered and matched under all four caps.
- **The two 503s under N4 and N5 were malformed JSON, not length.**
  - N4, d09: `}),`, a stray `)` after an object, at about 330 tokens.
  - N5, d28: the last object was never closed before `]`, at about 390 tokens. The parser calls
    that "unbalanced JSON object", the same words it uses for a reply cut off at the ceiling.
  - Neither was a ceiling hit or a cap violation, so by the user's rule the cap stayed the same.
    All three attempts repeated the malformation.
- **The reduced retry never fired in a capped sweep.** No capped attempt hit the ceiling or broke
  its cap, so no attempt asked for fewer. The wording is shown below, and its behaviour by the
  tests, not by these runs.
- **More wrong answers where none was expected.** The baseline declined 6 of 7 such runs. N3, N4
  and N5 declined 3 of 7, and N6 5 of 7.
  - The extra answers are statements from loosely related items an Employee may read. Under N3,
    for example, d21 (Employee) got T04's retrospective, d24 got D01's leave accrual, and d25 got
    D20's move notice. d11 (Employee) was answered with T01's standup content, mostly cited to D02,
    under every setting, the baseline included. That wrong answer grew with the cap: 1 statement
    in the baseline, 6 under N6.
  - They are not leaks: no answer cited an item its role may not read.
  - This rule did not weigh it; it is recorded for the decision.
- **Wrong-passage citations account for much of the gap between the last two match rows.** The
  right sentence is cited to another supplied item. In the baseline, d16's D17 etiquette was cited
  to D04, d23's D09 phases to D15, and d18's D01 approval rule to D06. The match row counts these
  as misses; the phrase row does not.
- **What the cap did not fix.** d02, d04, d08, d13, d16, d18, d19 and d21 (Administrator) missed
  under every setting.
  d01 and d02, the onboarding questions, were answered from template sentences in the baseline and
  N3, though D08 ranked first. d01 matched from N4 up; d02 never did.

## How each attempt's request changes

Only the user prompt's closing line changes, and only after a ceiling hit or a cap violation. With
N = 6:

| Attempt | Asks for | The user prompt ends |
|---|---|---|
| 1 | 6 | `Give at most 6 statements. Reply with the JSON object only, using only the chunk_id values above.` |
| 2, after a ceiling hit or a cap violation | 3 | `Give at most 3 statements. Reply with …` |
| 3, after another | 1 | `Give at most 1 statement. Reply with …` |
| after any other failure | unchanged | as the attempt before |

The system prompt gains rule 8: "Give no more statements than the number stated after the
question. If more could be written, keep the ones that answer the question most directly."

## What it does not show

- **One pass per setting.** Phase 1 showed the same prompt can give different replies. So a single
  503 in 31 runs does not separate N4 or N5 from N3 or N6. The malformations behind them are not
  tied to length and could occur at any N. N6 is chosen by the rule as written, on this one pass.
- **Whether the reduced retry recovers a reply in practice.** It was not triggered.
- **Whether the no-answer regression comes from the cap sentence or from rule 8.** Not isolated.
- **Anything about the frozen sets.** They were not run.
