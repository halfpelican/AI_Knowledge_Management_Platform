# Objective 05's re-run, 10 November 2026: after one disclosed revision, informed by the first run

**The result: clause 1 is still not met (14 of 20, 70%, against 75%); clauses 2 and 3 are met.** This
run is **not** an independent test. The revision it measures was made after, and because of, the first
run on the frozen reference set (`../objective-05.md`: 12 of 20, 60%), by the lead's decision of 10
November. That 60% stays the independent result (D-106's note).

## What changed between the runs

- **One revision of the type definitions** (`caf9e22`): a Report includes data laid out as a register,
  inventory, schedule, roster, tracker or table, and announcements; a Procedure is steps,
  instructions or a guide to follow; a document is not a Meeting Paper because its title or subject
  mentions a meeting, a room, a session or an event.
- **Seven new development documents** of the first run's failing shapes, X12 to X18, none of them the
  twenty. On them, the third development sweep (`../dev-sweep-3/`) matched only 7 of 21: the register
  and the guide were fixed, while a roster, an announcement and a rules document whose title mentions
  meetings were still called Meeting Paper. The first twelve stayed at 35 of 35, and
  `CLASSIFICATION_CONFIDENCE_THRESHOLD` stayed 0.95 by D-106's rule.
- **Nothing else.** The same database, scheme, threshold and command. The first run's 20 analysis rows
  and 38 AI tag links were deleted first, after their counts were checked, so that this run's links
  are its own.

## How it ran

| | |
|---|---|
| commit | `caf9e22`, no uncommitted tracked changes |
| configuration | provider `flm`, chat model `gemma3:4b` (FLM v0.9.39, `check_flm.py` passing) |
| database | `kmp_obj0506_20261101` (dump `3bf98403…6f59`), migrations as for the first run |
| the run | `manage.py classify_documents --all`: 20 classified, 0 failed (`classify/`) |
| the scoring | `scripts/objective05_verify.py` against the frozen `corpus/objective-05/reference.json` (`verification/`) |

## Clause 1: 14 of 20 (70%), not met

| Id | Reference (fit) | First run | Re-run |
|---|---|---|---|
| D03 | Procedure (fair; alternative Policy) | Policy | **Procedure** (fixed) |
| D12 | Report (fair) | Policy | **Report** (fixed; held at 0.85) |
| D17 | Policy (strong) | Meeting Paper | **Policy** (fixed) |
| D04 | Procedure (fair; alternative Policy) | Procedure | Policy (**new miss**) |
| D10 | Procedure (fair; alternative Policy) | Policy | Policy |
| D13 | Report (weak) | Meeting Paper | Procedure (held at 0.85) |
| D15 | Report (strong) | Procedure | Procedure (held at 0.85) |
| D16 | Report (fair) | Policy | Procedure |
| D20 | Report (weak; alternative Procedure) | Meeting Paper | Meeting Paper |

- **Three fixed and one lost,** a net gain of two. Of the five spreadsheet documents, D12 became a
  Report, D14 stayed one, and D13, D15 and D16 were called Procedure; the revision's Report wording
  reached only the register.
- **Three types scored 0.85 and were held as provisional,** one right (D12) and two wrong (D13, D15),
  against one in the first run (D14, right). Every other type, right or wrong, scored 0.95.
- **For information only, not the rule:** counting the reference's recorded alternatives would give
  16 of 20. The frozen rule counts the reference column, and the alternatives were recorded and not
  taken (D-106).

## Clause 2: met

47 of 47 assignments below 0.95 were held as provisional, and 25 of 25 at or above it were applied.
No department on the twenty was changed.

## Clause 3: met

One department outside the scheme was discarded ("Fleet Vehicle"), six Project or Process values outside
the scheme were discarded, two Topic values outside the scheme were proposed for confirmation, and no
out-of-scheme value was linked.

## For information

Tags against the manifest: precision 57.6%, recall 39.6% (the first run's: 63.2% and 50.0%).
