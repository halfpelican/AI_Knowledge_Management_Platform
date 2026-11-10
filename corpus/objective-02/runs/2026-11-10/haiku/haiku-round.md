# A round on Claude Haiku 5.5: 10 November 2026

The user asked whether Haiku could replace Sonnet 5.5 to save cost without losing performance, and
approved a round, development set first. Haiku 5.5 is $0.10 / $0.50 per million tokens against
Sonnet 5.5's $2 / $10. On the replies measured so far, that is about 0.05¢ a question against
about 1¢.

**This file was committed before any Haiku call,** so the bar below was fixed before any result
was seen. The results are added below it afterwards.

## The configuration under test

- **Generation:** `claude-haiku-5-5`. Only the model changes from D-115's Sonnet runs:
  - effort stays `"low"`;
  - thinking stays at the model's default;
  - there are still no sampling parameters, and `CLAUDE_MAX_TOKENS` stays 16000.
- **The rest is unchanged:**
  - Voyage `voyage-4` at 1024;
  - D-120's threshold 0.2687 and floor 0.2468, applied by the code itself, nothing patched;
  - `MAXIMUM_STATEMENTS` 6;
  - `kmp_voyage_20261110`, at dump `80ff46d4…`.

## Step 1, the decision: `dev-set-v2.json` end to end

The procedure is D-102's, as Sonnet ran it at 0.2687 / 0.2468: all 40 runs, through the shipped
`answer_question`, each in a transaction that is rolled back. The Sonnet run it is compared with is
`../voyage-threshold/e2e/e2e_v2_voyage_T2687_F2468_N6*`.

**Haiku passes step 1 only if all six hold:**

| | bar | Sonnet's result |
|---|---|---|
| 1. answered, where an answer is expected | 32/32 | 32/32 |
| 2. declined, where none is expected | 8/8 | 8/8 |
| 3. expected-answer match, from an expected source | at least 31/32 | 32/32 |
| 4. responses failing the schema, and 503s | 0 and 0 | 0 and 0 |
| 5. fabricated identifiers (statements verification removed) | 0 | 0 |
| 6. out-of-scope citations | 0 | 0 |

Bar 3 allows one miss, because Claude takes no sampling parameters, so one run of each model is a
noisy sample. The others allow none: a lost decline or a fabricated identifier is the failure this
round exists to catch.

**If step 1 fails,** the round stops there. Sonnet stays the default (D-115), and this file records
the result.

## Step 2, the confirmation, only if step 1 passes: the frozen sets

The frozen thirty and the nine threads, held out. They run with the same harness copy as #75,
with the model set to Haiku. Haiku confirms only if all of these hold:

- **The frozen thirty:** at least 33/34 runs right, and 0 leaks. Sonnet scored 34/34.
- **The threads:** with history, at least 8/9 matches; and 0 leaks. Sonnet scored 9/9.
- **Both sets:** 0 fabricated identifiers.

## What follows

- **If both steps pass,** adopting Haiku as the `anthropic` provider's default is the user's
  decision, recorded as D-121.
- **If either fails,** Sonnet stays the default, and the reason is recorded here.
- **Either way, the HTTP check is not part of this round.** It tests FR-13's wiring, which does not
  depend on the model, and #76 has shown it on this provider.

---

## Results, added after the runs (10 November 2026, 19:34–19:40)

**Haiku passed both steps.** Everything above this line is unchanged since `0f184ca`.
`compare_console.txt` holds the side-by-side tables, read from the records by
`compare_haiku_sonnet.py`.

### Step 1, passed (`e2e/`, script `dev_set_e2e_haiku.py`, commit `cfcae92`)

| dev-set-v2, 40 runs | bar | Sonnet 5.5 | **Haiku 5.5** |
|---|---|---|---|
| answered, where an answer is expected | 32/32 | 32/32 | **32/32** |
| declined, where none is expected | 8/8 | 8/8 | **8/8** |
| expected-answer match | at least 31/32 | 32/32 | **32/32** |
| schema violations, 503s | 0, 0 | 0, 0 | **0, 0** |
| fabricated identifiers, out-of-scope citations | 0, 0 | 0, 0 | **0, 0** |
| median seconds per ask | | 2.6 | 2.4 |

- **No run's outcome differs between the two models.**
- **36 of 36 responses parsed first time.**
- **The four declines that reached generation** were Haiku returning an empty statement list, 9
  output tokens each, as Sonnet did.

### Step 2, confirmed (`harness.json`, `threads.json`, script `citation_harness_haiku.py`, commit `e04aab1`)

| | bar | Sonnet 5.5 (#75) | **Haiku 5.5** |
|---|---|---|---|
| frozen thirty: runs right | at least 33/34 | 34/34 | **34/34** |
| frozen thirty: leaks | 0 | 0 | **0** |
| threads: with history | at least 8/9 | 9/9 | **9/9** |
| threads: leaks | 0 | 0 | **0** |
| fabricated identifiers, both sets | 0 | 0 | **0** |
| frozen thirty: answered question, median / p90 | | 2.53 / 4.48 s | 1.69 / 2.41 s |

- **On the frozen thirty, no run is right on one model and wrong on the other.** The 26
  answerable runs are answered from the expected source, and all 8 should-decline runs are
  declined (3 before generation, 5 by the model).
- **The threads:** first turn 11/11 and spelled out 9/9 on both. Cold is 1/9 on both, as
  predicted. The readings per follow-up are identical, including t09's "history works", which is
  retrieval, not memory (`../voyage-frozen/voyage-frozen.md`).

### The one behavioural difference

**t02's follow-up asked cold:** "How often does that get reviewed?", with no earlier turn to say
what "that" is.

- **Sonnet declined.**
- **Haiku answered** with five statements from D04, the records handbook ("reviewed annually",
  and four similar lines). Every citation was genuine, but about a different "that".
- **Both score not correct,** and a cold follow-up is predicted to fail, so no bar is affected.
- **It is still the risk this round was set up to watch:** answering an underspecified question
  instead of declining it. It is a single instance in 118 runs (40 + 34 + 44). Cold is not a path users reach
  with FR-13, which sends the history, but a user can still ask a standalone question this vague.

### Spend

| | Sonnet 5.5 | **Haiku 5.5** |
|---|---|---|
| dev-set-v2 (36 calls) | $0.3287 | **$0.0171** |
| frozen thirty (31 calls) | $0.2829 | **$0.0146** |
| threads (37 calls) | $0.4251 | **$0.0233** |
| **all three** | **$1.04** | **$0.055** |

- **The counts are the replies' own, and the Console's figure governs.**
- **Haiku used slightly more output tokens:** 9,116 against 7,781 on the dev set, with thinking
  counted. At a twentieth of the price, it still costs about 19 times less. That is roughly 0.05¢
  a question against 1¢.

### What the result does not show

- **The sets cannot separate the two models.** Both are at the ceiling on every set, and the
  should-decline runs number 22 across the three sets (8, 8 and 6), so a difference smaller than
  one or two runs cannot show.
- **One run of each set per model.** Claude takes no sampling parameters, so a repeat may differ.
- **FR-10 is not measured.** `ANTHROPIC_MODEL` also selects the model for document
  classification (`classify_document`), and the round did not measure it. Making Haiku the default
  changes classification too, unless the two are given separate settings.
- **NFR-08 has not run on either model,** and neither has the HTTP check on Haiku. The HTTP check
  tests wiring, which the model does not change.

### What follows

Adopting Haiku as the `anthropic` provider's default generation model is the user's decision. If
adopted, it is recorded as D-121, changing `ANTHROPIC_MODEL`'s default in `config/settings.py` and
`.env.example`. Sonnet would stay available by setting `ANTHROPIC_MODEL`.
