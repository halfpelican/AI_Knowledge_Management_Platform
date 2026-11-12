# Objective 04, development runs of 11 November 2026

**These are not the objective's result.** They are three draws of the development set (`X01`,
`X02`, `T01`–`T06`), scored against `corpus/objective-04/dev/reference.json`, which Claude wrote.
The objective is measured on the ten frozen transcripts against a reference written by people,
and that reference does not exist yet (`corpus/objective-04/README.md`).

## What was run

- **Provider:** `anthropic`, Claude Haiku 5.5 (`claude-haiku-5-5`) for the summary and Voyage
  `voyage-4` for embeddings. Database `kmp_fr16`, created for this.
- **`dev-1`:** the eight transcripts ingested through FR-09 with their attendees, each summary
  run automatically after its ingestion, as on the server. It is two invocations merged (`X01`
  alone, then the other seven).
- **`dev-2`, `dev-3`:** a new summary run for each of the same eight meetings
  (`objective04_run.py --regenerate`), which is the Regenerate path.
- **The prompt was the same in all three.** Nothing was tuned between them.

| Draw | Reference items extracted (bar: at least 80%) | Extras (bar: at most 10%) | Wrong owners (bar: none) | Due dates agreeing | Summarisation spend |
|---|---|---|---|---|---|
| `dev-1` | 37 of 39 (94.9%) | 1 of 38 (2.6%) | 0 of 37 | 17 of 18 | $0.0052 |
| `dev-2` | 39 of 39 (100%) | 4 of 43 (9.3%) | 0 of 42 | 18 of 19 | $0.0055 |
| `dev-3` | 37 of 39 (94.9%) | 2 of 39 (5.1%) | 0 of 38 | 18 of 18 | $0.0054 |

All 24 summaries were ready on the first attempt: no malformed reply, no retry. Total
summarisation spend for the three draws was $0.0162 (53,763 prompt and 21,548 completion tokens at
$0.10 and $0.50 per million). Voyage's embedding calls are billed separately and are not counted.

## What the draws show

- **The extras bar is the tight one.** Recall stayed between 94.9% and 100%. Extras ranged from
  2.6% to 9.3%, and `dev-2` came within one item of the 10% ceiling. One run is one draw of a
  model that is not deterministic, so the frozen set's single measurement can land either side of
  that bar for reasons that are noise.
- **Every extra was a finer split of a task the reference holds as one,** or a duty the reference
  holds as a decision:
  - the February reminder listed apart from the announcement it belongs to (`T06`);
  - "install the refill stations by the end of January" apart from getting the quotes (`T06`);
  - the weekend on-call cover listed as two items, where the reference records it as a decision
    (`T01`);
  - "Lena observes the dry run" apart from Tomas leading it (`T01`).

  None was invented: each is something the transcript says. So how finely the people writing the
  frozen reference split tasks will move the extras number as much as the model does.
- **The misses:**
  - `dev-1` listed two tasks agreed as decisions (the Thursday dry run, the alert thresholds) only
    under decisions;
  - `dev-3` missed the contractor's certificate renewal and a team's accessibility list.
- **Owners:** no item was given to the wrong person in any draw. First names resolved to the
  attendee of that name, and outsiders and teams stayed unassigned.
- **Dates:** the one disagreement in `dev-1` was "by end of day tomorrow", which the resolver did
  not read. It was fixed the same day (`apps/meetings/due_dates.py`), and `dev-2` and `dev-3` ran
  with the fix. The one in `dev-2` is an item whose deadline the model left empty.

## How it was adjudicated, and what that is worth

Claude wrote the development reference and decided every pairing, by reading each row of each
sheet. Two cautions:

- **The reference was written after `dev-1`'s output had been read.** It was written from the
  transcripts, and it holds two items `dev-1` missed and treats one of its items as an extra, but
  it is not independent of that output.
- **One reader decided the pairings.** Nobody checked them.

That is good enough to decide whether the prompt needed changing (it was left as it was) and to
see how much a draw moves. It is not evidence for the objective.
