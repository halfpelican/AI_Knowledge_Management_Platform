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

## End to end: the rule's value does at least as well as 0.30, and better on one run

This is D-102's comparison, run the same day once the user had loaded API credit. It used
`threshold_floor_e2e_voyage.py`, the 8 November script changed only where FLM was named.
- **Questions:** every run of v2 went through the shipped `answer_question`, as the run's role.
- **Generation:** Claude Sonnet 5.5 (D-115), with the cap of 6.
- **Nothing written:** each ask ran inside a transaction that was rolled back, and the row counts
  matched before and after.
- **Values:** both were patched in this process only (`--patch-threshold`, `--patch-floor`). The
  code still holds 0.30 and 0.0.

The evidence is in `e2e/`, with the console output in `e2e_T3000_console.txt` and
`e2e_T2687_console.txt`.

| v2, 40 runs | FLM 0.30, no floor (D-102) | FLM 0.24 / 0.206 (D-102) | Voyage 0.30, no floor | **Voyage 0.2687 / 0.2468** |
|---|---|---|---|---|
| answered where expected | 29/32 | 30/32 | 31/32 | **32/32** |
| declined where no answer is expected | 7/8 | 3/8 | 8/8 (5 before generation, 3 by it) | **8/8** (4 before generation, 4 by it) |
| match with an expected source | 22/32 | 15/32 | 31/32 | **32/32** |
| 503s / schema violations / out-of-scope citations | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | **0 / 0 / 0** |
| seconds per ask, median / max | 16.1 / 54.8 | 16.9 / 54.6 | 2.8 / 6.8 | **2.6 / 6.9** |
| passages supplied per answer, median / max | 5 (D-101) | — | 2 / 11 | **3.5 / 11** |

- **The one difference is u07,** an answerable run whose expected source scores 0.2968. At 0.30 it
  is declined before generation. At 0.2687 it is answered and matched.
- **Claude declined every no-answer run that reached it,** u37 ("parental leave", top 0.498)
  included. That is D-102's conclusion holding: generation and verification do the declining that
  scores cannot.
- **The floor stops unrelated offers.** At 0.30 with no floor, all 8 no-answer runs were offered
  the five nearest items, down to 0.12. At F 0.2468, the 4 runs declined before generation were
  offered nothing. The 4 declined by generation were offered only items at or above the floor.
  No answerable run lost an offer to the floor, because none ended in no answer. On FLM, the
  margin rule could not set a floor at all (D-102), and D-56's gap stayed open.
- **Spend:** 34 and 36 Claude calls; 93,900 and 125,432 tokens in, 7,529 and 7,781 out. That is
  about $0.26 and $0.33 at $2 / $10 per million, under a cent per call.

## What this does not settle

- **Adoption and wiring:** settled as D-120 on 10 November. The user adopted 0.2687 / 0.2468 for
  `voyage-4` as values of the embedding model (`RELEVANCE_THRESHOLD_BY_MODEL`,
  `PARTIAL_MATCH_FLOOR_BY_MODEL`). EmbeddingGemma keeps 0.30 with no floor.
- **The test sets.** Once a value is chosen, the frozen thirty, the threads, the HTTP check and
  NFR-08 run on it, as D-101's "after" did on FLM.
- **The scores still overlap.** Three no-answer runs score above an answerable one. Generation
  declined them here, on a small set.
- **Contamination.** As D-101's note records, v2 was written after the frozen results were seen,
  so the frozen thirty does not independently test any threshold chosen from it.
