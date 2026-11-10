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
