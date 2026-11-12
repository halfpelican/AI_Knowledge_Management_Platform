# The five harness draws of `pre-measurement-asks.json`, scored for FR-12

Written by `score_draws.py` from the committed `draw-*/harness.json`, by `../plan.md`'s rule.
Generated, not edited by hand.

## Per draw

| Draw | Commit | Unanswerable: no-answer (A / B, none proposed / B, all rejected) | Permission-only: no-answer (A / B) | Statements proposed / verified | Leaks | Claude calls, tokens in / out, US$ |
|---|---|---|---|---|---|---|
| draw-1 | `3cd0726` | 8 of 8 (1 / 7 / 0) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 158, 0.0034 |
| draw-2 | `3cd0726` | 8 of 8 (1 / 7 / 0) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 169, 0.0034 |
| draw-3 | `3cd0726` | 8 of 8 (1 / 7 / 0) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 147, 0.0034 |
| draw-4 | `3cd0726` | 8 of 8 (1 / 7 / 0) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 81, 0.0034 |
| draw-5 | `3cd0726` | 8 of 8 (1 / 7 / 0) | 6 of 6 (4 / 2) | 0 / 0 | 0 | 9, 33,268 / 81, 0.0034 |
| **total** | | **40 of 40** (5 / 35 / 0) | **30 of 30** (20 / 10) | | 0 | 45, 166,340 / 636, 0.0170 |

## Per ask, beside FLM's 8 November pre-measurement

Top in-scope score over the asking role's readable chunks; voyage-4's threshold is 0.2687, embed-gemma's 0.30. Outcomes: A, no passage cleared the threshold; B, generation was called and no statement survived; answered, a cited statement survived.

| Id | Kind | Role | voyage-4 top score, min to max over the draws | Passages admitted | anthropic, outcome in each draw | embed-gemma top score | FLM, both runs |
|---|---|---|---|---|---|---|---|
| U01 | unanswerable | Employee | 0.4052 to 0.4052 | 9 | B, none proposed, all 5 | 0.3457 | answered (D08) |
| U02 | unanswerable | Employee | 0.3139 to 0.3139 | 3 | B, none proposed, all 5 | 0.3284 | B, none proposed |
| U04 | unanswerable | Employee | 0.3626 to 0.3626 | 6 | B, none proposed, all 5 | 0.3273 | answered (D10) |
| U05 | unanswerable | Administrator | 0.3894 to 0.3894 | 8 | B, none proposed, all 5 | 0.3191 | answered (D02) |
| U07 | unanswerable | Employee | 0.3834 to 0.3834 | 5 | B, none proposed, all 5 | 0.4146 | answered (D20) |
| U08 | unanswerable | Administrator | 0.3380 to 0.3382 | 2 | B, none proposed, all 5 | 0.3324 | answered (D01) |
| U10 | unanswerable | Employee | 0.2172 to 0.2177 | 0 | A, all 5 | 0.2498 | A |
| U11 | unanswerable | Administrator | 0.3872 to 0.3872 | 1 | B, none proposed, all 5 | 0.4079 | answered (D01) |
| P01 | permission-only | Employee | 0.2454 to 0.2454 | 0 | A, all 5 | 0.2862 | A |
| P02 | permission-only | Employee | 0.2364 to 0.2364 | 0 | A, all 5 | 0.2751 | A |
| P04 | permission-only | Employee | 0.2456 to 0.2456 | 0 | A, all 5 | 0.3873 | answered (D04) |
| P06 | permission-only | Employee | 0.2116 to 0.2122 | 0 | A, all 5 | 0.2587 | A |
| P07 | permission-only | Employee | 0.3067 to 0.3067 | 2 | B, none proposed, all 5 | 0.3590 | answered (D05) |
| P08 | permission-only | Employee | 0.3022 to 0.3022 | 1 | B, none proposed, all 5 | 0.2631 | A |

## Leaks

None.
