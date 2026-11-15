# Objective 04, the frozen set, run of 15 November 2026

**This is the objective's measurement. Objective 04 is NOT MET, on attribution:** two owners were
given to the wrong person, where the bar is none. Recall and extras were both met. A person
completed the adjudication sheet on 15 November, and it was scored the same day. D-125's dated
note of 15 November records the result and its causes.

| Criterion | Bar | Result | |
|---|---|---|---|
| Reference action items extracted | at least 80% | 48 of 50 (96.0%) | met |
| Extracted items absent from the reference | at most 10% | 3 of 51 (5.9%) | met |
| Named owners given to the wrong person | none | 2 of 47 | **NOT met** |

- **`O01-A4`: two rules Claude wrote disagree.** The application gives a lone first name to the one
  attendee who has it, and the reference's writing instructions say a first name two roster users
  share is `unassigned`. It is not a model error.
- **`O07-A8`: a model error.** The model named one person where the reference records two people
  jointly.
- **Details:** `frozen/results.md` quotes the misses, the extras and the owners, and
  `frozen/results.json` holds the numbers. Nothing was changed in response (D-93).

## What was run

- **The reference:** `corpus/objective-04/reference.json`, written and checked by Benjamin Morovan and
  Sagarika Dey and frozen on 15 November 2026 (`06bfe73`).
- **The method:** the README's "How it is measured", approved by Benjamin on 15 November.
- **The run:**
  - the ten frozen transcripts (`O01`–`O10`) were ingested through FR-09 with their attendees;
  - each was summarised once, automatically after its ingestion, as on the server;
  - command: `scripts/objective04_run.py --set frozen`, at commit `06bfe73`, with no uncommitted
    tracked changes.
- **Database:** `kmp_obj04_frozen_20261115`, made empty for this run and migrated. It holds the
  roster's 18 users.
- **Provider:** `anthropic`, Claude Haiku 5.5 (`claude-haiku-5-5`) for the summaries and Voyage
  `voyage-4` for embeddings.
- **Result of the run:**
  - all ten summaries were ready on the first attempt;
  - 51 action items were extracted;
  - 25,890 prompt and 8,328 completion tokens cost $0.0068 at $0.10 and $0.50 per million. Voyage's
    embedding calls are billed separately and are not counted.
- The prompt and the code were not changed for this run, and nothing will be changed in response to
  it (D-93).

## How the sheet was completed

(What the person was asked to do, kept as the record of the method.)

`frozen/adjudication.csv` has one row per extracted item.

- **The proposal.** `proposed_ref` is the script's guess by word overlap: a convenience, not a
  decision.
- **`decision`:** fill it in on every row, with the reference `ref` the item is the same task as
  (the same action on the same object, whatever the wording), or `none`. Each `ref` may be used
  once; a second item for the same task is `none`.
- **`owner_ok`:** fill it in, `yes` or `no`, only where `decision` is `none` and `resolved_owner`
  names a user, since no reference item says who that should have been.
- **`notes`:** optional.
- **Saving.** Save it as **CSV UTF-8** (in Excel, "CSV UTF-8 (Comma delimited)"). Plain "CSV" can
  damage the quotation marks and dashes in the descriptions.

Then it is scored with:

    .venv\Scripts\python.exe scripts\objective04_verify.py score --run corpus\objective-04\runs\2026-11-15\frozen\run.json --reference corpus\objective-04\reference.json --sheet corpus\objective-04\runs\2026-11-15\frozen\adjudication.csv --out-dir corpus\objective-04\runs\2026-11-15\frozen

**The scorer refuses the sheet** while:
- any `decision` is blank;
- a `decision` names a `ref` the reference does not hold;
- two rows claim the same `ref`.
