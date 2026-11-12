# Objective 04 reference set: DRAFT, not frozen

Objective 04 (proposal section 2, due **13 November 2026**):

> Implement AI-generated meeting summaries, and action items from ingested transcripts.
> Verification is against a reference set of ten transcripts for which summaries, action items
> and decisions have been prepared manually in advance: at least 80% of the action items present
> in the reference must be extracted, no more than 10% of extracted items may be items absent
> from the reference, and every extracted item carrying a named owner must either resolve to a
> user on the system or be recorded as unassigned rather than attributed to the wrong person.

**Who writes what (D-125, choice 4).** Claude drafted the transcripts on 11 November 2026. The
**references are written by people**: Benjamin Morovan and Sagarika Dey. They are never generated,
and Claude does not write, edit or suggest any reference answer. Once both of you approve them, the
set is frozen. It is then a test set and never a tuning set (D-93): prompt changes are judged on
the development set only.

## What is here

| File | What it is |
|---|---|
| `transcripts/O01` … `O10` | The ten candidates for the frozen set. Fictional meetings at the corpus's organisation, 300 to 560 words each |
| `dev/X01`, `dev/X02` | The development set, with `T01`–`T05` (`corpus/objective-02/transcripts`) and `T06` (`corpus/demo`). Used for tuning; never measured as the objective |
| `manifest.json` | Each transcript's title, meeting date, attendees and visibility, as FR-09 will ingest them |
| `roster.json` | The 18 users the measurement database holds. "Resolves to a user on the system" means one of these |
| `reference-template.json` | One blank block per frozen transcript, for you to fill in |

## How to write a reference

Read each transcript and fill in its block in `reference-template.json`. Use your own words. Don't
run the system first, and don't look at any output it produces for these ten.

- **`summary`:** two to four sentences saying what the meeting was for and what came out of it.
- **`decisions`:** one string per decision **reached in this meeting**. A decision reported as
  already made elsewhere is your call; say which way you went in `notes`.
- **`highlights`:** optional. The points of discussion worth remembering that are neither
  decisions nor actions.
- **`action_items`:** one object per task **someone commits to, or is asked to do and accepts, in
  this meeting**. Add or remove objects as needed. **An empty list is a valid answer**, and at
  least one transcript is meant to have none.
  - **Not action items:**
    - something already done ("I already did that this morning");
    - something cancelled in the meeting;
    - an idea parked or declined ("maybe in the new year", "let's not");
    - a restatement of an existing plan.
  - `ref`: `O01-A1`, `O01-A2` and so on.
  - `description`: the task, in a few words.
  - `owner_as_said`: who the transcript says will do it, exactly as written ("Alex", "Ms Haddad",
    "the facilities team", "Sam"). Leave it empty if the transcript names nobody.
  - `expected_owner`: the roster user it belongs to, as a full name from `roster.json`, or
    `unassigned`. Write a full name **only when the transcript identifies exactly one roster user**.
    Write `unassigned` for anyone not on the roster, a team or role, two people jointly, a name that
    fits more than one roster user, or no name at all.
  - `due_as_said`: the deadline exactly as said ("next Friday", "by the thirteenth"), or empty.
  - `expected_due_date`: optional, as `YYYY-MM-DD` or null. This is your reading of the phrase from
    the meeting date. It is reported for information only, because Objective 04 does not score
    dates. Leave it null if the phrase gives no date.
  - `evidence`: a short quote from the transcript showing the commitment.
- **`notes`:** any judgement call you made.

**Two people.** One of you writes each block and the other checks it. Where you disagree, agree on
an answer and say so in `notes`. Fill in `prepared_by` and `checked_by`.

**Freezing.** When all ten are complete:

1. Rename the file to `reference.json`.
2. Set `status` to `FROZEN` and `frozen_on` to the date.
3. Commit it.

From then on it changes only by a dated correction recorded in `docs/decisions.md`, never to fit a
result.

## How it will be measured (proposed; please approve or amend before the run)

1. A fresh database holds the roster's users. The script ingests the ten transcripts through FR-09
   with their attendees, and summarises each once on the default `anthropic` provider (Claude
   Haiku 5.5, D-121). It records the extracted items, the model, the time and the spend.
2. **Matching is done by a person, not by the script.** The script writes a sheet that lists each
   transcript's extracted items beside its reference items, with a proposed pairing. A person
   confirms or corrects each pairing.
   - An extracted item matches a reference item when it is the **same task**: the same action on
     the same object. Wording does not matter, and owner and date are scored separately.
   - Each reference item can be matched once. A second extracted item for the same task counts as
     absent from the reference.
3. **The three numbers,** pooled over the ten transcripts:
   - **recall:** reference items matched, divided by all reference items. It must be at least 80%;
   - **extras:** extracted items matching no reference item, divided by all extracted items. It
     must be no more than 10%;
   - **attribution:** extracted items that carry a named owner and whose resolved user differs from
     `expected_owner`. It must be zero. An item stored as unassigned passes.
4. **Reported beside them, not scored:**
   - due dates against `expected_due_date`;
   - decisions recovered;
   - the per-transcript breakdown;
   - every miss and every extra, quoted.

## Development set

`X01`, `X02` and `T01`–`T06` are for checking the prompt and the owner and date rules while the
frozen set is being written. Claude may read their outputs and change the prompt in response. Any
change is recorded with the development result that prompted it.
