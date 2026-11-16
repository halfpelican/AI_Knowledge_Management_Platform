# Objective 05's verification, 10 November 2026: the first run on the frozen reference set

**The result: clause 1 is not met (12 of 20 types, 60%, against 75%); clauses 2 and 3 are met.** This
is the frozen reference set's first and only independent use (D-106, D-93).

## How it ran

| | |
|---|---|
| commit | `aee5374` (FR-10 merged with main `dbcbb43`), no uncommitted tracked changes |
| configuration | provider `flm`, chat model `gemma3:4b`, embedding model `embed-gemma` (classification calls no embedding) |
| FLM | v0.9.39, `scripts/check_flm.py` passing before the run |
| database | `kmp_obj0506_20261101`, restored on 8 November from dump `3bf98403…6f59` |
| before the run | `manage.py migrate` applied `documents 0008` (FR-10) and `accounts 0006` (D-99's `manage_meetings`, which postdates the snapshot); `seed_objective02_tags.py --scheme-only` created the 14 tag values with no links |
| the run | `manage.py classify_documents --all`: the 20 documents with status Indexed, one classification each, 8.3 to 30.4 s per document, 0 failed (`classify/`) |
| the scoring | `scripts/objective05_verify.py` against `corpus/objective-05/reference.json` (SHA-256 `763e9a62…68e`, frozen 8 November) and the manifest (`verification/`) |
| threshold | `CLASSIFICATION_CONFIDENCE_THRESHOLD` 0.95 (D-106) |

## Clause 1: "at least 75% of suggested document types must match the reference"

**12 of 20 (60%): not met.** The eight misses:

| Id | Title | Reference (fit) | Suggested | What it shows |
|---|---|---|---|---|
| D03 | Health and Safety Induction Guide | Procedure (fair; alternative Policy) | Policy | an instructive guide called Policy, the reference's own alternative |
| D10 | Expense Claims Guide | Procedure (fair; alternative Policy) | Policy | the same |
| D12 | Vendor Register 2026 | Report (fair) | Policy | a spreadsheet register |
| D15 | Project Budget Tracker FY27 | Report (strong) | Procedure | a spreadsheet tracker |
| D16 | Team Roster and Skills Matrix | Report (fair) | Policy | a spreadsheet matrix |
| D13 | Training Schedule Q4 | Report (weak) | Meeting Paper | a schedule |
| D17 | Meeting Room Booking Rules | Policy (strong) | Meeting Paper | a title containing "Meeting" |
| D20 | Office Relocation Announcement | Report (weak; alternative Procedure) | Meeting Paper | an announcement |

- **Three shapes the development set did not contain.** All three spreadsheet documents were missed.
  The development Reports (X06 to X08) were narrative reports with findings, and none was a register
  or a tracker. Three documents became Meeting Paper; the type definitions added on 9 November
  (`b40dc0f`) say a Meeting Paper "usually names the meeting or the decision sought", and these name a
  meeting room, a training session and a move weekend. Two instructive guides took the alternative
  the reference itself names.
- **The confidence gave no warning:** every miss scored 0.95, the same as most hits. Only D14 (Report,
  correct) scored below the threshold (0.85) and was held. This is D-106's finding again, on the test
  set: on gemma3:4b the type's confidence does not separate right from wrong.
- **Counting the reference's recorded alternatives would give 14 of 20 (70%)**, still under 75%. The
  frozen rule counts the reference column only.
- **By the reference's fit:** 6 of 8 strong, 4 of 8 fair and 2 of 4 weak matched. The strong misses
  are D15 and D17.

## Clause 2: "any assignment falling below the configured confidence threshold must be marked provisional and held for confirmation rather than applied"

**Met: 48 of 48 assignments below 0.95 were held as provisional, and 27 of 27 at or above it were
applied.** Held: 1 type (D14), 15 departments and 32 of the 38 AI tag links; none was written to the
document or shown as a tag. Applied: 19 types, 2 departments (D08 and D10, each equal to the uploader's,
so nothing was written) and 6 tag links. Every department on the twenty stayed the uploader's (D-105's
note of 10 November).

## Clause 3: "suggested values falling outside the established scheme must be discarded in the Department, Project and Process dimensions while being proposed for confirmation in the Topic dimension only"

**Met.** Three departments outside the scheme were discarded ("Health and Safety", "Customer
Experience", "Fleet"); six Project or Process values outside the scheme were discarded and kept only in
`discarded_suggestions`; two Topic values outside the scheme were proposed for confirmation and created
nothing; no out-of-scheme value was linked to any document.

## For information

- **Departments:** the model's department matched the manifest's on 13 of 20 documents (the others
  are marked "differs" in `verification.md`). Department is not in the 75%.
- **Tags against the manifest:** precision 63.2%, recall 50.0% of the AI-suggested links.
- **Timing:** 8.3 to 30.4 s per classification, one attempt each.
