# Objective 04, development run of 13 November 2026

**This is not the objective's result.** It is one more draw of the development set (`X01`, `X02`,
`T01`–`T06`), scored against `corpus/objective-04/dev/reference.json`, which Claude wrote. The
objective is measured on the ten frozen transcripts against a reference written by people.

## Why it was run

The security review of 12 November changed two things a summary run depends on (D-125's third
note):

- **The prompt** now states every limit the parser enforces, and what to do when a meeting reached
  more than it may list.
- **Owners** are matched only among the meeting's recorded attendees whose role can read it.
  Before, a full name was matched against every user.

The draws of 11 November (`../2026-11-11/`) ran on the old prompt and the old owner rule, so this
draw checks the new ones on the same eight meetings.

## What was run

- **Provider:** `anthropic`, Claude Haiku 5.5 for the summary and Voyage `voyage-4` for
  embeddings, on `kmp_fr16`, the database the earlier draws used. Its summaries of 11 November had
  been dropped with the migration's regeneration, so this run is each meeting's first run in that
  database. The meetings and their attendees are the ones ingested on 11 November.
- **`dev-4`:** `objective04_run.py --set development --regenerate` at commit `8a2eec1`.

| Draw | Reference items extracted (bar: at least 80%) | Extras (bar: at most 10%) | Wrong owners (bar: none) | Due dates agreeing | Summarisation spend |
|---|---|---|---|---|---|
| `dev-4` | 39 of 39 (100%) | 5 of 44 (11.4%) | 0 of 43 | 19 of 19 | $0.0051 |

All eight summaries were ready on the first attempt: 18,873 prompt and 6,427 completion tokens at
$0.10 and $0.50 per million. Voyage's embedding calls are billed separately and are not counted.

## What it shows

- **The owner rule cost nothing here.** Every matched item whose reference owner is a user was
  given to that user, and every item the reference holds unassigned was stored unassigned. The
  five extras given to a user went to the person the transcript names.
- **The extras bar was missed by one item.** Earlier draws were 2.6%, 9.3% and 5.1%.
  - Four of the five extras are the finer splits the earlier draws showed:
    - the weekend on-call cover as two items, where the reference records a decision (`T01`);
    - the February reminder apart from the announcement (`T06`);
    - installing the refill stations apart from getting the quotes (`T06`).
  - The fifth is new: "create the new starter's account" (`T01`). That is a plan reported as in
    hand, which the prompt's rule 7 already says is not an action item, and the reference's note
    says the same.
- **Whether the prompt change moved the extras cannot be told from one draw.** The draws of 11
  November already ranged from 2.6% to 9.3% on one prompt. The prompt was not changed in response
  to this draw: tightening it is a decision for the team, made on the development set and never
  on the frozen one (D-93).

## How it was adjudicated

As on 11 November. Claude read every row of `adjudication.csv` against the reference and the
transcripts. Every pairing the script proposed was confirmed. The five rows with no proposal were
decided "none", each with `owner_ok` "yes". The command was
`adjudicate_dev.py ... T01:2=none:yes T01:3=none:yes T01:8=none:yes T06:2=none:yes T06:5=none:yes`.
One reader decided the pairings, and nobody checked them.
