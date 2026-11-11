# The frozen thirty's three anthropic draws, scored for FR-12

Written by `score_thirty.py` from the Objectives 05/06 session's committed seed records and QueryLog exports, by `../plan.md`'s rule. Generated, not edited by hand.

Consistency checks: none failed.

## Per draw

| Draw | Seeded at | Unanswerable asks: no-answer (A / B, none proposed / B, all rejected) | Permission-only asks: no-answer (A / B) | Answerable asks: answered with citations, none rejected | Searches as expected | Claude calls, tokens in / out, US$ |
|---|---|---|---|---|---|---|
| 1 | `c3ac5b0` | 8 of 8 (6 / 2 / 0) | 6 of 6 (4 / 2) | 7 of 7 | 9 of 9 | 11, 34,403 / 932, 0.0039 |
| 2 | `462e8e9` | 8 of 8 (6 / 2 / 0) | 6 of 6 (4 / 2) | 7 of 7 | 9 of 9 | 11, 34,403 / 795, 0.0038 |
| 3 | `462e8e9` | 8 of 8 (6 / 2 / 0) | 6 of 6 (4 / 2) | 7 of 7 | 9 of 9 | 11, 34,403 / 860, 0.0039 |
| **total** | | **24 of 24** (18 / 6 / 0) | **18 of 18** (12 / 6) | **21 of 21** | 27 of 27 | 33, 103,209 / 2,587, 0.0116 |

## Per ask, beside FLM's 10 November seeding

A: no passage cleared voyage-4's 0.2687, so generation was not called. B: generation ran and no statement survived. Retrieved is the number of passages the row records.

| Id | Kind | Role | anthropic, outcome in each draw | rejected_count | Retrieved | FLM (embed-gemma, gemma3:4b) |
|---|---|---|---|---|---|---|
| A01 | answerable | Employee | answered, all 3 | 0 | 4 | answered |
| A02 | answerable | Employee | answered, all 3 | 0 | 6 | answered |
| A03 | answerable | Employee | answered, all 3 | 0 | 2 | answered |
| A04 | answerable | Employee | answered, all 3 | 0 | 7 | answered |
| A05 | answerable | Administrator | answered, all 3 | 0 | 2 | answered |
| A06 | answerable | Administrator | answered, all 3 | 0 | 5 | answered |
| A07 | answerable | Employee | answered, all 3 | 0 | 3 | answered |
| U01 | unanswerable | Employee | A, all 3 | null | 0 | no-answer |
| U02 | unanswerable | Administrator | A, all 3 | null | 0 | no-answer |
| U04 | unanswerable | Employee | B, none proposed, all 3 | 0 | 1 | no-answer |
| U05 | unanswerable | Administrator | B, none proposed, all 3 | 0 | 1 | no-answer |
| U07 | unanswerable | Employee | A, all 3 | null | 0 | no-answer |
| U08 | unanswerable | Administrator | A, all 3 | null | 0 | no-answer |
| U10 | unanswerable | Employee | A, all 3 | null | 0 | no-answer |
| U11 | unanswerable | Administrator | A, all 3 | null | 0 | no-answer |
| P01 | permission-only | Employee | A, all 3 | null | 0 | no-answer |
| P02 | permission-only | Employee | A, all 3 | null | 0 | no-answer |
| P04 | permission-only | Employee | A, all 3 | null | 0 | answered |
| P06 | permission-only | Employee | A, all 3 | null | 0 | no-answer |
| P07 | permission-only | Employee | B, none proposed, all 3 | 0 | 2 | answered |
| P08 | permission-only | Employee | B, none proposed, all 3 | 0 | 1 | no-answer |

## Searches

| Id | Kind | Role | result_count in each draw | FLM |
|---|---|---|---|---|
| A08 | answerable | Employee | 1, 1, 1 | 1 |
| A09 | answerable | Administrator | 1, 1, 1 | 1 |
| A10 | answerable | Employee | 1, 1, 1 | 1 |
| U03 | unanswerable | Administrator | 0, 0, 0 | 0 |
| U06 | unanswerable | Employee | 0, 0, 0 | 0 |
| U09 | unanswerable | Employee | 0, 0, 0 | 0 |
| U12 | unanswerable | Employee | 0, 0, 0 | 0 |
| P03 | permission-only | Employee | 0, 0, 0 | 0 |
| P05 | permission-only | Employee | 0, 0, 0 | 0 |
