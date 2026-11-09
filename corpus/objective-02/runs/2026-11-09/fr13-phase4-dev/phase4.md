# Step 7 phase 4: option 3 (the follow-up rewrite), measured and not adopted

**9 November 2026 · branch `feat/FR-13-followup-rewrite` at `48c20cf` · database
`kmp_obj02_20261101` (read-only) · FLM v0.9.39, `check_flm.py` passed before every
run · dev set `corpus/objective-02/dev-threads.json`, 19 threads (t20–t31 of 8
November plus the seven cross-source threads t32–t38), SHA-256
`21200c7238c5d12e8b39edf35c91524f59a253b6e891f0a1698aae7b869ea4ef`.**

## The rule, fixed before any run

Means over **3 draws per arm** (main vs option 3), each draw covering with-history,
spelled-out, first-turn and the decline guards; cold once per arm (draw 1),
diagnostic. Adopt only if option 3's mean with-history expected-answer match exceeds
main's by **more than 2 runs**, no guard arm's mean lower by more than 1, conformance
intact, 0 out-of-scope. Draws alternated arms (main d1, option3 d1, …) so drift lands
evenly. The arms differ in one line: option 3 embeds
`resolve_retrieval_text()`'s string (the shipped phase-4 code); main embeds
`compose().for_retrieval` (the pre-phase-4 path, byte for byte, no model call).

## The result: DO NOT ADOPT

| | with-history (of 19) | first-turn (of 22) | spelled-out (of 19) | correct declines | cold (of 19, once) | schema | out-of-scope |
|---|---|---|---|---|---|---|---|
| main d1 | 10 | 14 | 12 | 5/9 | 11 | 82/82 | 0 |
| main d2 | 9 | 14 | 12 | 2/6 | — | 65/66 | 0 |
| main d3 | 9 | 14 | 12 | 2/6 | — | 65/66 | 0 |
| option3 d1 | 10 | 14 | 12 | 6/9 | 12 | 80/80 | 0 |
| option3 d2 | 10 | 14 | 12 | 3/6 | — | 63/64 | 0 |
| option3 d3 | 10 | 14 | 12 | 3/6 | — | 63/64 | 0 |
| **mean main** | **9.33** | 14.00 | 12.00 | 3.00 | | | |
| **mean option3** | **10.00** | 14.00 | 12.00 | 4.00 | | | |

- **With-history gain +0.67 runs** against the required > 2: inside D-103's ±1–2-run
  band. Not adopted.
- **No guard fell**: first-turn and spelled-out identical to the run; correct declines
  were a mean **+1 better** under option 3 (t37@Employee declined in every option-3
  draw and in none of main's).
- **Conformance**: draws 2–3 each carried exactly one response that conformed on a
  retry — in BOTH arms symmetrically (main 65/66, option3 63/64) — not an option-3
  effect. Draw 1 was 82/82 and 80/80.
- **Out-of-scope 0** in all 462 runs.

## The rewrite mechanism itself worked

- **66 of 66 with-history runs used the rewrite; 0 fallbacks.** The one-field schema
  held every time (100% rewrite conformance on gemma3:4b).
- **Latency per rewrite call:** min 3.2 s, median 4.1 s, p90 5.3 s, max 6.7 s over the
  66 calls. The 120 s `REWRITE_TIMEOUT_SECONDS` never came within an order of
  magnitude of binding; 30–60 s would be ample on this evidence.

## Why the mean moved so little: the rewrite moves WHICH follow-ups resolve

Per thread-and-role, with-history, identical across all three draws unless shown
(Y = expected-answer match, n = answered without the match, d = not answered):

| thread | main | option3 | reading (from the draw-1 run records; draws 2–3 agree) |
|---|---|---|---|
| t22 | nnn | **YYY** | gained. Main's miss was a WRONG-PASSAGE CITATION: the join retrieved D07+D20+D01 and the reply attributed D07's "four weeks written notice" sentence to a D20 chunk (D-102's open wrong-passage problem). The rewrite narrowed the candidates to D07 alone and the citation is right |
| t28@Administrator | nnn | **YYY** | gained: the scoped skills-matrix follow-up resolves for the role that may read it |
| t36 (cross) | nnn | **YYY** | gained: main's join retrieved only turn-1's D08; the rewrite — which in fact kept the pronouns ("the one starting this Monday") — still retrieved T01 alone, because the join's turn-1 nouns were no longer polluting the query |
| t38 (cross) | nnn | **YYY** | gained, same shape: main retrieved D11 first and answered retention; the rewrite's query reached D04's reporting text |
| t23 | YYY | nnn | lost: the rewrite UNDER-RESOLVED — "What happens if a customer changes their mind later?" dropped the consent subject entirely, D11 was never retrieved, and generation answered complaints material (D06/T04) |
| t24 | YYY | nnn | lost, same cause: the rewrite returned the follow-up essentially unchanged ("who checks everyone has actually got out?"), D03 was never retrieved, and D04 filler was supplied |
| t27 | Ynn | nnn | lost its one lucky draw |
| t31 (previous-answer) | YYY | ddd | main matched by ACCIDENT — the join dragged turn 1's material in and the reply happened to carry the phrase; option 3 declines, which is what D-42 and D-86 decision 2 PREDICT for this thread. A match loss under the rule, arguably a correctness gain in kind |
| t37@Employee (cross, scoped) | nnn | ddd | option 3 declines where main answered: the decline-guard improvement |

Four gained (two of them cross-source, one scoped, one a wrong-passage fix), three or
four lost, net +0.67: the rewrite REDISTRIBUTES which follow-ups resolve, and on sets
this size that nets out inside the noise band. Two distinct failure classes sit under
the losses and the remaining misses:

1. **Rewrite under-resolution** (t23, t24; and t32/t35/t36/t38's rewrites kept their
   pronouns too, gaining or losing only by what the un-polluted query then found).
   gemma3:4b frequently returns the follow-up near-verbatim instead of merging the
   referent — rule 5 of the rewrite prompt ("return it unchanged if it stands alone")
   misfires. Prompt-level, fixable, and measurable per run from `rewrites` in each
   draw record.
2. **Generation restating turn-1-adjacent material over a correctly supplied
   passage** (t32, t34, t35 under option 3: the expected source was supplied at RANK 1
   — D13 0.32, D10 0.37, D17 0.44 — and the reply answered from the lower-ranked
   T04/D19/T03 passage instead). This is D-103's "the restatement failure is in
   generation's use of the context", reproduced here with retrieval clean.

## The frozen nine, once, on the decided configuration (main)

Mirroring phase 3's ending: the rule decided main, so the frozen set ran once on the
unchanged shipped path (`../fr13-phase4/run_frozen_main.py`, the real harness in
recorded mode with `resolve_retrieval_text` pinned to the composed-join passthrough —
stated in that file and in its console; the record's `rewrites_used` is 0 of 11,
confirming the pin held). Recorded at commit `48c20cf`, clean tracked tree, dump
`3bf98403...`, the hash phase 3's frozen run carried.

**Result** (`../fr13-phase4/threads.json` / `threads.txt`): with-history match
**2 of 9** - against the byte-identical-main references of 2/9 (8 Nov after), 3/9
(9 Nov phase-3 variance re-run) and now 2/9 again, squarely inside the +/-1-2-run
band: the decided configuration measures as itself. Spelled out 6/9, first-turn 7/11,
cold 1/9 match (5/9 answered), 100% schema conformance (38/38) and 100%
first-attempt, 0 out-of-scope. Read with the dev result: no with-history gain is
claimed, because none cleared the band anywhere.

## Where this leaves FR-13

- FR-13 stays partial (D-91); D-56 stays open.
- The phase-4 code (operation, fallback, `QueryLog.retrieval_rewrite`, measuring-tool
  wiring) is committed at `48c20cf` with its 21 break-tested tests and is one revert
  away in either direction; whether the not-adopted candidate stays on the branch or
  is preserved as a diff like phase 3's is the user's call at the decision record.
- What phase 4 adds to the diagnosis, in two parts: (a) a 4B local model is an
  unreliable REWRITER — 100% schema conformance but frequent near-verbatim returns
  instead of referent merges — so option 3's ceiling here is set by rewrite quality
  before retrieval is even consulted; (b) where the rewrite DID put the right passage
  at rank 1 (t32, t34, t35), generation still answered from the turn-1-adjacent
  passage below it, confirming D-103's generation-side reading with retrieval clean.
  Any further FR-13 attempt has to move one of those two, and the second is the one
  the frozen set keeps measuring.
