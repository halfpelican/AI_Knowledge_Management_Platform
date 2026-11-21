# Objective 05 on D-139's prompt, 21 November 2026: Claude Haiku 5.5 on the frozen reference set

**The result: all three clauses are met, on two draws. Clause 1 is 18 of 20 types (90%) against 75%
on each.** On the second draw one wrong type scored above the threshold and was applied, which no
earlier draw on Haiku had shown: see "Second draw" below.

**Why it was run.** D-139 makes the classification request also return a summary and key points, so
the prompt Haiku's thresholds were measured on (0.72 for the type and the tags, D-122; 0.30 for the
department, D-129) is no longer the prompt that ships. The user's decision of 21 November 2026:
Objective 05 is run once on a new scratch database, reported, and nothing is tuned on it.

**Three things qualify it:**

- **It is one draw.** The three draws on the old prompt gave 19, 18 and 18 of 20
  (`../2026-11-10-anthropic/objective-05-anthropic.md`), and this draw's two misses are the old
  prompt's second draw's exactly: D04 Policy at 0.6 and D09 Report at 0.55.
- **It is not an independent test of the prompt,** for the reason the 10 November record gives: the
  type definitions were revised once after FLM's first run on these twenty.
- **The department figures have no earlier run to compare with.** This is the first Objective 05 run
  with the department's own threshold, 0.30, in force (D-129 says none had been run).

## How it ran

| | |
|---|---|
| commit | `186be70`: D-139's AI layer, storage and screens, plus this folder's driver; a clean checkout, no uncommitted tracked changes. The apply layer did not yet store the summary; it applied the classification as before |
| configuration | provider `anthropic`, chat model `claude-haiku-5-5`, embedding model `voyage-4` at 1024. Classification calls no embedding model |
| database | `kmp_obj05_d139_20261121`, new, made under the user's decision above |
| how it was made | `snapshot_measurement_db.py restore --database kmp_obj02_anthropic_20261110 --into kmp_obj05_d139_20261121` from `C:\kmp-measurement\2026-11-10-obj02-anthropic\snapshot`: dump `6e514170…e6fc`, built on `anthropic` from empty on 10 November. The route of 10 November (an FLM snapshot converted) is refused since D-131 |
| before the run | `manage.py migrate` applied accounts 0009–0012, documents 0012–0016 and meetings 0003 (`setup/migrate.txt`); `documents 0015` found the twenty documents and seeded the department list. `manage.py check`: no issues (`setup/check.txt`). The twenty analyses written at upload on 10 November, before any tag existed, were cleared: 20 analysis rows, 0 AI links (`setup/reset_classification.txt`). `seed_objective02_tags.py --scheme-only` created 14 tags and 0 links (`setup/seed_scheme_only.txt`) |
| the run | `../2026-11-10-anthropic/classify_with_usage.py`, unchanged, calling the shipped `classify_documents --all --out`. 20 classified, 0 failed. **26 requests:** one for each of nineteen documents, and seven for D04 (8,357 words: six sections, then the final request). Every request parsed on its first attempt (`classify/attempts.log`, 26 lines). 66,033 tokens in, 11,881 out, about $0.0125 (`classify/claude_usage.json`) |
| the scoring | `scripts/objective05_verify.py`, as shipped, against the frozen `corpus/objective-05/reference.json` (`verification/`, console in `verify-console.txt`) |
| thresholds | 0.72 for the type and the tags, 0.30 for the department, as the record's header states |

## Clause 1: "at least 75% of suggested document types must match the reference"

**18 of 20 (90%): met.** The two misses:

| Id | Title | Reference (fit) | Suggested | Confidence | Outcome |
|---|---|---|---|---|---|
| D04 | Records Management Handbook | Procedure (fair) | Policy | 0.6 | held as provisional |
| D09 | Project Atlas Kickoff Brief | Meeting Paper (weak) | Report | 0.55 | held as provisional |

- **No wrong type was applied.** Both misses scored below 0.72 and were held for a person. Of the
  18 right types, 17 were applied and one was held (D20, 0.7).
- **Both are the old prompt's misses.** D09 missed on all three earlier draws, and D04 on two of
  them, each time with the same answer as here (Report; Policy at 0.6), which is the alternative the
  reference itself records for each. Every other document was typed right, as on every earlier draw.
- **D04 is the one document that takes the sectioned path.** Its final request now carries the six
  section summaries beside the opening, so its type is decided with the whole handbook's summaries in
  view. Its answer and its confidence are what the old prompt gave on two draws of three, so this
  draw shows no change; one draw cannot show there is none.

## Clause 2: "any assignment falling below the configured confidence threshold must be marked provisional and held for confirmation rather than applied"

**Met: no violation.** 34 of 34 assignments below their threshold were held. 52 of 55 at or above it
were applied; the other 3 were held to keep a department the document already had (D03, D14, D15),
which is D-105's rule and not a violation.

## Clause 3: out-of-scheme values

**Met: no violation,** and nothing exercised it: no department, Project, Process or Topic outside the
scheme was suggested on this draw. On each of the three earlier draws one Topic was proposed,
"customer complaints" on D06; on this draw it was not. That is the one difference from the earlier
draws that is not a matter of degree, and one draw does not say whether the new prompt caused it.

## For information

- Tags against the manifest: precision 69.4%, recall 70.8% (earlier draws: 63.3% to 68.9%, and 62.5%
  to 64.6%).
- Types held as provisional: 3, one right and two wrong (earlier draws: 4, 4 and 3).

## Second draw, on the final prompt, 21 November 2026 (`draw-2/`)

**Why a second draw.** After the first, a review of the AI layer had the worked example's summary
reworded: it joined two statements with "because", a cause its text does not state (`f3227f1`).
That changes one line of each system prompt. Every user turn for these twenty documents is byte for
byte what the first draw sent. So the first draw no longer described the prompt that ships, and
the measurement was repeated on it.

**How it ran:** commit `789c05a`, a clean checkout; the same database, scheme, thresholds, command
and verifier. The first draw's 20 analysis rows and 49 AI links were cleared first
(`draw-2/reset.txt`). 26 requests again, every one parsed at its first attempt
(`draw-2/classify/attempts.log`), about $0.013. At this commit the apply layer stores the summary.

| | Draw 1 (`186be70`) | Draw 2 (`789c05a`) |
|---|---|---|
| **clause 1, types matching the reference** | **18 of 20 (90%)** | **18 of 20 (90%)** |
| the misses, with confidence | D04 Policy 0.6, D09 Report 0.55 | D04 Policy **0.8**, D09 Report 0.6 |
| wrong types applied | none | **one: D04** |
| types held as provisional (right / wrong) | 3 (1 / 2) | 4 (3 / 1) |
| clause 2: below threshold held; at or above applied (+ held to keep a department) | 34/34; 52/55 (+3) | 34/34; 48/51 (+3) |
| clause 3: discarded / Topics proposed / out-of-scheme links | 0 / 0 / 0 | 0 / 0 / 0 |
| tags against the manifest: precision, recall (information) | 69.4%, 70.8% | 66.7%, 62.5% |
| Claude | 26 requests, $0.0125 | 26 requests, $0.013 |

- **All three clauses are met on both draws.** The two misses are the same two documents as on every
  draw since 10 November, each with the alternative the reference itself records.
- **A wrong type was applied, for the first time on Haiku.** D04's Policy scored 0.8, above 0.72, so
  it was applied and not held. On the four draws before this one where D04 was missed or right
  (three on the old prompt, one on the new), its type scored 0.6 or 0.7 and was held, and the
  10 November record says "No wrong type was ever applied."
  - No clause is broken by it: clause 2 is about assignments below the threshold, and clause 1 is
    met.
  - **D04 is the one document that takes the sectioned path.** Its final request shows the six
    section summaries beside the opening, which the old prompt never did. That is a plausible cause
    of the higher confidence, and one draw cannot establish it.
  - A person can still change an applied type on the document page, and that edit is kept.
  - Nothing was tuned on it. Whether 0.72 still separates right from wrong on a sectioned document is
    now an open question, on one case.
- **No Topic was proposed on either draw,** where each of the three old-prompt draws proposed one
  ("customer complaints", D06). Two draws make it likely the new prompt is the cause. Clause 3 is
  met either way; its Topic half was not exercised.
- **The right types held** on the second draw are D07 and D10 at 0.7 and D20 at 0.6.
