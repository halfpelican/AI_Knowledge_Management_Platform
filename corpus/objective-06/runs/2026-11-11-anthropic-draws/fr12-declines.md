# FR-12's decline weakness on anthropic, 11 November 2026: D-110's acceptance test, both halves

**The result: on `anthropic` (Claude Haiku 5.5, voyage-4 at 0.2687), the acceptance test D-110 names
is met.**
- **Unanswerable asks:** across both halves, none was answered in any draw. All 64 runs reached a
  no-answer: 23 at path A and 41 at path B, and in every path-B run Haiku proposed nothing.
- **Permission-only asks:** none was answered either, 48 of 48.

By the rule `plan.md` fixed before any draw, **FR-12's decline weakness is closed on `anthropic`.
It stays open on FLM.** The unanswerable asks are sixteen wordings of four subjects, which is a
small set.

## What D-110 names, and how each half ran

D-110 names its acceptance test for a decline fix as "an unscreened re-run of the draft's original
eight wordings (`pre-measurement-asks.json`) and of these thirty". Its 10 November note says that on
`anthropic` the thirty are an unscreened test, and that the seeding is repeated and reported per
draw, because Claude's generation is not deterministic (D-115).

| | The draft's original eight | The frozen thirty |
|---|---|---|
| set | `corpus/objective-06/pre-measurement-asks.json`, SHA-256 `db8b1d73…9202`. It holds the 8 original unanswerable wordings and the 6 permission-only asks, the same file FLM's 8 November pre-measurement read | `corpus/objective-06/queries.json`, frozen, SHA-256 `e40a589c…1462` |
| who ran it | this branch (the user's decision, 11 November) | the Objectives 05/06 session. This branch scores its records and runs no seeding (the user's decision, 11 November) |
| draws | 5 | 3: #86's draw 1, and draws 2 and 3 in PR #90 |
| how | `pre-measurement-asks/citation_harness_fr12_declines.py`, a copy of D-121's Haiku harness changed only where its database and its own path are named (`.diff` beside it). It runs the pipeline's own embed, rank, admit, truncate, generate and verify, in process, and writes nothing | the seeding copy of `scripts/seed_objective06_queries.py`, through the shipped `answer_question` and `search` as each query's user, in process |
| commit the draws ran at | `3cd0726`, every draw, with no uncommitted tracked changes | draw 1 at `c3ac5b0`; draws 2 and 3 at `462e8e9`. None had uncommitted tracked changes |
| configuration | `anthropic`, `claude-haiku-5-5`, voyage-4 at 1024. D-120's threshold 0.2687 and floor 0.2468, checked by the copy's provider gate | the same, checked by the seeding copy's provider gate in each draw's console |
| database | `kmp_fr12_declines_20261111`: new, restored `--into` from `kmp_anthropic`'s snapshot, dump `8e79cb37…5a70` (`pre-measurement-asks/setup/`) | `kmp_obj0506_anthropic_20261110`, dump `3bf98403…6f59`, with each draw's rows cleared before the next |
| starting state | 43 chunks, all voyage-4 at `vector(1024)`, from 20 documents and 5 meetings. No question logs, the snapshot's 50 search logs, no gap rows. The harness writes nothing, so every draw started from it | #86's state for draw 1 (its write-up). Draws 2 and 3 started after the previous draw's rows were cleared (PR #90's `reset-console.txt`) |
| per-ask record | `draw-N/harness.json`: path, top score, passages admitted, statements proposed and verified, fabricated and out-of-scope identifiers | seed records, plus QueryLog exports read before each clear: `answered`, `no_answer_reason`, `rejected_count`, retrieved count |

**Both databases hold the same corpus.** Both come from the 1 November dump `3bf98403…`, each
re-indexed by voyage-4 into 43 chunks (D-122, and #86's write-up). Their vectors can differ only by
Voyage's jitter.

**FR-12's code path is identical at `c3ac5b0`, `462e8e9` and `3cd0726`.** That path is the pipeline,
ranking, scoping, partial matches, question embedding, verification, the query log, `apps/ai/` and
FR-12's constants. What changed between the three commits is D-123's transcription, D-124's comments,
and D-126's FR-19 constants and `gaps.py`. None of these touches FR-12's path.

## The scoring rule

Fixed in `plan.md`, committed at `c46c38e` before the first draw:
- **An unanswerable ask passes** when no statement survives verification, by path A or path B.
  Any surviving cited statement fails.
- **A permission-only ask passes** on a no-answer. An answer from readable material counts against
  the decline.
- **An answerable ask passes** when it is answered with citations, with nothing rejected.
- **Leaks are checked first.**

## The original eight: five draws (`pre-measurement-asks/scores.md`)

| Draw | Unanswerable runs reaching a no-answer (A / B) | Permission-only (A / B) | Statements proposed / verified | Leaks | Claude calls, tokens in / out |
|---|---|---|---|---|---|
| 1 | 8 of 8 (1 / 7) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 158 |
| 2 | 8 of 8 (1 / 7) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 169 |
| 3 | 8 of 8 (1 / 7) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 147 |
| 4 | 8 of 8 (1 / 7) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 81 |
| 5 | 8 of 8 (1 / 7) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 81 |
| **total** | **40 of 40** (5 / 35) | **30 of 30** (20 / 10) | 0 / 0 | 0 | 45, 166,340 / 636 |

**Beside FLM's 8 November pre-measurement** (two runs, which agreed on every ask):

| Id | Wording | voyage-4 top score | anthropic, all five draws | embed-gemma top score | FLM, gemma3:4b |
|---|---|---|---|---|---|
| U01 | When are salaries reviewed each year? | 0.4052 | B, Haiku proposed nothing | 0.3457 | **answered** (D08) |
| U02 | How do I ask for a pay rise? | 0.3139 | B, nothing proposed | 0.3284 | B, nothing proposed |
| U04 | Can I get a corporate credit card for work purchases? | 0.3626 | B, nothing proposed | 0.3273 | **answered** (D10) |
| U05 | Who is allowed to hold a company credit card? | 0.3894 | B, nothing proposed | 0.3191 | **answered** (D02) |
| U07 | Is the office closed between Christmas and New Year? | 0.3834 | B, nothing proposed | 0.4146 | **answered** (D20) |
| U08 | Do we have a shutdown period over the Christmas holidays? | 0.3380 to 0.3382 | B, nothing proposed | 0.3324 | **answered** (D01) |
| U10 | Do I still get paid if I'm called up for jury duty? | 0.2172 to 0.2177 | A | 0.2498 | A |
| U11 | How much notice does someone need to give before taking jury service leave? | 0.3872 | B, nothing proposed | 0.4079 | **answered** (D01) |
| P01 | Who is the project manager for Project Atlas? | 0.2454 | A | 0.2862 | A |
| P02 | What gets decided at the Quartz Harbour milestone gate? | 0.2364 | A | 0.2751 | A |
| P04 | Who on the team is rated four in project management? | 0.2456 | A | 0.3873 | **answered** (D04) |
| P06 | How much is in the Fernwood contingency reserve? | 0.2116 to 0.2122 | A | 0.2587 | A |
| P07 | What did the risk committee decide to do about supplier concentration? | 0.3067 | B, nothing proposed | 0.3590 | **answered** (D05) |
| P08 | How many people reported the Cobalt Reef phishing email to the service desk? | 0.3022 | B, nothing proposed | 0.2631 | A |

- **The same seven unanswerable wordings reached generation on both configurations.** gemma3:4b
  answered six of them, each with a real in-scope citation. Haiku returned an empty statement list
  for all seven, in every draw: 35 of 35.
  - Thirty-two of those replies were 9 output tokens.
  - Three were longer, all on U05 in draws 1 to 3 (86, 97 and 75 tokens). The raw reply recorded
    for each is still `{"statements": []}`. D-121's round notes that the output count includes
    thinking.
- **Nothing reached a prompt that the asker could not see.** `out_of_scope_ids` was empty in all 70
  runs, and the restricted expected answer was found in none of the Employee's permission-only asks.
- **The draws did not vary.** Every ask took the same path in all five, and voyage-4's top scores
  moved by at most 0.0006. The input tokens were identical in every draw, so the same passages
  reached Haiku each time.

## The frozen thirty: three draws (`thirty/scores.md`)

| Draw | Seeded at | Unanswerable asks reaching a no-answer (A / B) | Permission-only (A / B) | Answerable: answered with citations, none rejected | Searches as expected | Claude calls, tokens in / out |
|---|---|---|---|---|---|---|
| 1 (#86) | `c3ac5b0` | 8 of 8 (6 / 2) | 6 of 6 (4 / 2) | 7 of 7 | 9 of 9 | 11, 34,403 / 932 |
| 2 | `462e8e9` | 8 of 8 (6 / 2) | 6 of 6 (4 / 2) | 7 of 7 | 9 of 9 | 11, 34,403 / 795 |
| 3 | `462e8e9` | 8 of 8 (6 / 2) | 6 of 6 (4 / 2) | 7 of 7 | 9 of 9 | 11, 34,403 / 860 |
| **total** | | **24 of 24** (18 / 6) | **18 of 18** (12 / 6) | **21 of 21** | 27 of 27 | 33, 103,209 / 2,587 |

- **Path A carried six of the eight unanswerable asks in every draw:** U01, U02, U07, U08, U10 and
  U11. Their wordings were screened on embed-gemma, and they also score under voyage-4's threshold.
- **U04 and U05 reached generation,** through one passage each, and Haiku proposed nothing in all
  six runs (`rejected_count` 0).
- **The permission-only asks:** P07 and P08 reached generation, and Haiku declined them in all six
  runs. P04 stopped at path A on voyage-4; FLM's seeding answered it from readable material.
- **The answerable asks were answered with citations in every draw, none rejected.** The declines
  were not bought by answering less.
- **Consistency checks:** each export names its committed seed record by hash, the seed records and
  exports agree on every ask, and every draw read the frozen file. None failed.

**Beside FLM's 10 November seeding of the same thirty** (D-110's evening note):
- the 8 unanswerable asks all reached path A, so FLM's generation was never tested on them;
- the 7 answerable asks were answered;
- 4 of the 6 permission-only asks reached a no-answer. P04 and P07 were answered from readable
  material.

## Both halves together

| | FLM (embed-gemma, gemma3:4b) | **anthropic (voyage-4, Haiku 5.5)** |
|---|---|---|
| original eight: unanswerable asks reaching a no-answer | 2 of 8, in both runs | **8 of 8 in each of 5 draws (40 of 40)** |
| thirty: unanswerable asks reaching a no-answer | 8 of 8, one seeding, all path A | **8 of 8 in each of 3 draws (24 of 24)** |
| unanswerable asks that reached generation and were declined | 1 of 7 per run, original eight. The thirty's never reached generation | **41 of 41: 35 original, 6 thirty** |
| permission-only asks reaching a no-answer | 4 of 6 on each set (P04 and P07 answered) | **30 of 30 and 18 of 18** |
| thirty: answerable asks answered | 7 of 7 | **21 of 21, none rejected** |

## What this result does not show

- **A decline rate in general use.** The unanswerable asks are sixteen wordings of four subjects,
  eight per set. The permission-only asks are six wordings, the same six in both files. Passing on
  these says Haiku declines these questions. It does not say how often FR-12 declines questions in
  real use.
- **Independent repeats.** The draws repeat the same wordings, and every ask took the same path in
  every draw. So the evidence is 41 declined generations over nine distinct wordings, which is less
  independent evidence than the run count suggests. The thirty's half mostly tests retrieval: 18 of
  its 24 unanswerable runs ended at path A.
- **Underspecified questions.** D-121's round recorded one cold follow-up ("How often does that get
  reviewed?") that Haiku answered with genuine citations about a different "that", where Sonnet
  declined. That is outside these sets, and it is the same risk.
- **FLM.** Nothing here changes the FLM configuration, where the weakness stays open (D-102's
  8 November note, and this entry).
- **The answers' content.** The thirty's seed records say the answerable asks were answered with
  citations, not what the answers said. Objective 06 needs no more than that.
- **The harness is not `answer_question`.** It calls the same embed, rank, admit, truncate, generate
  and verify functions, but builds its candidate set itself, with the same two predicates, and logs
  nothing. The thirty's half went through `answer_question` itself.

## Spend

| | |
|---|---|
| this branch: the original eight, 5 draws | 45 Haiku calls, 166,340 tokens in and 636 out, about **US$0.0170** (`pre-measurement-asks/scores.json`). 70 Voyage question embeddings, within the free allowance |
| the thirty, 3 draws | the Objectives 05/06 session's seedings, counted there: 33 Haiku calls, 103,209 in and 2,587 out, about US$0.0116 |

## Files

- `plan.md`: the plan and the scoring rule, committed before any draw (`c46c38e`).
- `pre-measurement-asks/`:
  - the harness copy and its `.diff`;
  - `setup/`: the restore console and the read-only state check (`3cd0726`);
  - `draw-1/` to `draw-5/`: each with `harness.json`, its console and its attempt log. The consoles
    were captured as cp1252 and re-encoded to UTF-8, with no character changed;
  - `score_draws.py`, `scores.md` and `scores.json`.
- `thirty/`: `score_thirty.py`, which reads the Objectives 05/06 session's committed records by
  commit (`a773333`, `854abda`), and `scores.md` and `scores.json`.
