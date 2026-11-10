# The threshold on Voyage: the score phase (D-113)

**Date:** 10 November 2026 · **Database:** `kmp_voyage_20261110` · **Set:** `dev-set-v2.json`

## What was run

D-113 asks for the threshold to be re-derived on development material before the `anthropic`
provider is relied on. This is the first half of that: the scores, and the rule applied to them.
The end-to-end comparison waits for Claude.

- **The database** is the 1 November snapshot of Objective 02's corpus, re-indexed with Voyage
  (PR #71). It holds 43 chunks of `voyage-4` at 1024 wide, with `input_type` "document" (D-116).
- **The script** is `threshold_scores_voyage.py`, a copy of
  `runs/2026-11-08/threshold_scores.py`, which measured FLM for D-101 and D-102. It changes only
  where FLM was named: the database, the provider, and the FLM version gate. The measurement and
  both derivations are the 8 November code.
- **The procedure** is the same as 8 November on v2:
  - 40 runs: 32 expect an answer and 8 do not;
  - each question embedded three times, through Voyage with `input_type` "query";
  - the shipped retrieval, `embed_question` → `candidate_chunks` → `rank` → `partial_matches`;
  - offers unfloored;
  - read-only, with no generation.
- **The rule** is D-101's, fixed in advance, with the same margin `m = 0.006`.
  - **T:** decline the most no-answer runs with margin (top score ≤ T − m), keeping every
    answerable run (its lowest expected-source score ≥ T + m). On a tie, take the middle.
  - **F:** at least the highest partial match offered to a run that path A declines, plus m, and
    at most T − m.

## Files

| File | What |
|---|---|
| `threshold_scores_voyage.py` | the script |
| `scores_v2_voyage.json` | every run's ranked list, top score, expected-source score and offers, per repeat |
| `scores_v2_voyage_console.txt` | the run's console |
| `derive_margin_v2_voyage.txt` | the margin rule's derivation |
| `derive_v2_voyage.txt` | the per-run table, and the rule without a margin |

## Result: T = 0.2687, F = 0.2468

| | FLM, 8 November (D-102) | **Voyage, 10 November** |
|---|---|---|
| lowest answerable expected-source score | 0.280 (u07) | **0.297** (u07) |
| no-answer runs declinable with margin | 1 of 8 | **4 of 8** |
| the rule's T | 0.24 | **0.2687** |
| the rule's F | 0.206 | **0.2468**, which satisfies F ≤ T − m |
| no-answer runs outscoring an answerable run | 5 | **3** (u32 for the Employee, u33, u37) |
| "parental leave" (u37) outscores | 22 answerable runs | **20** |

- **The tie interval** is [0.246720, 0.290776], with a middle of 0.268748. The value is 0.028 from
  the highest declined no-answer run (u34, 0.240720) and 0.028 from the lowest answerable run
  (u07, 0.296776).
- **Path A declines** u30 and u31 for the Employee, u34 and u36. Their best partial match is u34's
  D10 at 0.240720, so F is 0.2468.
- **Not declinable with margin:** u35 (0.287), u32 for the Employee (0.310), u33 (0.371) and u37
  (0.498). These reach generation, which must decline them.
- **Ranking:** every answerable run ranks its expected source first, 32 of 32, in every repeat.
- **The current 0.30 does not fit Voyage.** It loses u07, an answerable run, before generation,
  while declining 5 no-answer runs. The rule's 0.2687 loses none and declines 4.
- **Drift:** Voyage's query vectors barely move between calls. 17 of the 40 runs had identical
  vectors, and the largest spread in a run's top score was 0.000925, against D-40's FLM drift of
  about 0.003 that set m.

## What this does not settle

- **End to end.** D-102 found that the rule's value did worse end to end on FLM than 0.30 did.
  So the same comparison is owed here: T 0.2687 with F 0.2468, against 0.30 with no floor, on v2,
  with Sonnet and the cap of 6. It needs Claude, whose credits arrive on Sunday.
- **The scores still overlap.** Three no-answer runs score above an answerable one, and u37 sits
  at 0.498. Generation and verification still have to decline those (D-102's conclusion), on
  either provider.
- **Wiring.** `RELEVANCE_THRESHOLD` is a single value in `apps/core/constants.py`, and it is an
  `embed-gemma` value. Giving Voyage its own value is a decision, taken with the end-to-end result.
- **Contamination.** As D-101's note records, v2 was written after the frozen results were seen,
  so the frozen thirty does not independently test any threshold chosen from it.
