# D-40's screen of the walk's questions, on the Anthropic alpha's build (15 November 2026)

The demonstration script's questions were screened on 1 November on the FLM alpha
(`corpus/demo/screening-2026-11-01.json`, EmbeddingGemma's vectors). Since D-131 the alpha runs
the anthropic provider, so Benjamin asked on 15 November for the screen to be run again there
before the script is changed for that alpha.

## What ran

- **The database:** `kmp_alpha_screen_20261115`, a `pg_dump` of the alpha's
  `kmp_alpha_20261113`, made for this screen. Before anything ran, the copy was checked to hold
  the alpha's rows: 23 documents, 5 meetings, 48 chunks with the same `chunk_id`s and embeddings,
  2 accounts, 43 migrations, and no `query_log` rows. The live alpha was not touched.
- **The code:** the alpha's own commit, `6e1efd1`, from `git archive`. Retrieval and generation
  are the same on `main` at `f82fb1a`, except the generation parser (#106, #107).
- **The provider:** anthropic, `claude-haiku-5-5` for generation and classification, `voyage-4`
  at 1024 for embeddings. The settings are the alpha's own, read by name from its `.env`. The keys
  were read from the main checkout's `.env` into the process and are written nowhere.
- **`SUMMARY_RUNNER=inline`.** The alpha uses the default, `thread`. Both write FR-16's summary of
  T06 when it is ingested. Inline only waits for it, so the scores cannot race it. The walk asks
  about T06 minutes after FR-09.
- **The script:** `screen_anthropic.py`. It runs the 1 November screen's steps:
  1. it scores every walk question, as the role that asks it, with the shipped `compose`,
     `embed_question`, `candidate_chunks`, `rank`, `admit` and `partial_matches`;
  2. it uploads D21 and T06 through the real routes, as `corpus.employee@example.com`, as FR-08.1
     and FR-09.1 do. D21 is titled with its file name, with the department `Operations`. T06 has
     no attendees and no visibility chosen;
  3. it scores again;
  4. it asks each question three times through `answer_question`, each run in a conversation of
     its own;
  5. it scores a third time.
- **The rule** is D-40's, with its margins measured from `voyage-4`'s own threshold, T = 0.2687
  (D-120):
  - where an answer is expected, the top score is at least T + 0.05 (0.3187), and no candidate is
    within 0.005 of T;
  - where a no-answer is expected, either the top score is at most T − 0.02 (0.2487), which is
    path A, or the no-answer came on all three runs;
  - every question has the same outcome on all three runs.
- **The files:**
  - `screening.json` holds every score, every candidate within the band, every partial match and
    every run's statements with their sources;
  - `run.log` is the console. Its one warning is WhiteNoise finding no `frontend/dist` in the
    archive. That is the built page, which the screen does not use.

## What it found

| Step | Question | Role | Top score (its source) | Admitted | Within 0.005 of T | Three runs | Rule |
|---|---|---|---|---|---|---|---|
| FR-11.1 | Who is the sponsor of Project Atlas? | Employee | 0.1517 (Weekly Operations Standup) | 0 | none | the no-answer, path A, every run | passes |
| FR-11.2 | the same | Administrator | 0.4270 (Project Atlas Kickoff Brief) | 2 | none | answered, citing Project Atlas Kickoff Brief, every run | passes |
| FR-12.2 | How quickly do we have to acknowledge a customer complaint? | Employee | 0.5857 (Customer Complaints Procedure) | 14 | Records Management Handbook, at 0.2733, 0.2725 and 0.2675 | answered, citing Customer Complaints Procedure, every run, with the same statement | **fails the band clause** |
| FR-12.3 | How much did the latest penetration test cost? | Employee | 0.2305 (Weekly Operations Standup's summary) | 0 | none | the no-answer, path A, every run | passes |
| FR-12.4 | How many bicycles can the secure bike cage hold? | Employee | 0.5193 (the uploaded D21) | 1 | none | answered, 40, citing D21, every run | passes |
| FR-12.5 | When will single-use cups be removed from the office kitchens? | Employee | 0.6380 (T06's FR-16 summary; its transcript 0.5895) | 4 | Office Relocation Announcement 0.2726, Vendor Register 2026 0.2661 | answered, 1 March 2027, citing the meeting, every run | **fails the band clause** |
| FR-13.1, turn 1 | What was the customer satisfaction score last quarter? | Employee | 0.5061 (Customer Success Retrospective) | 3 | none | answered, 86 percent, citing the retrospective, every run | passes |
| FR-13.1, turn 2 | Where are the first aid kits kept? | Employee | 0.3683 (Customer Success Retrospective) | 4 | none | answered, citing Health and Safety Induction Guide, every run | passes |
| FR-13.2, turn 2 | Who is the sponsor of Project Atlas? (after turn 1) | Employee | 0.3771 (Customer Success Retrospective) | 2 | none | the no-answer, path B, every run, offering the retrospective as a partial match | passes, on the second limb |
| FR-13.3, turn 1 | What was the customer satisfaction score last quarter? | Administrator | 0.5061 (Customer Success Retrospective) | 3 | Security Incident Debrief's summary, 0.2658 | answered, citing the retrospective, every run | **fails the band clause** |
| FR-13.3, turn 2 | Who is the sponsor of Project Atlas? (after turn 1) | Administrator | 0.3797 (Project Atlas Kickoff Brief) | 5 | none | answered, citing Project Atlas Kickoff Brief, every run | passes |

- **Every question had the outcome it was expected to have on all three runs,** answered or not,
  and every answer cited the expected source on every run.
- **Three rows fail the band clause,** FR-12.2, FR-12.5 and FR-13.3's first turn. In each, a
  passage that is not the cited source scores within 0.005 of the threshold. Whether it is
  admitted can change which passages reach the model. The cited source sits far above the
  threshold in all three: 0.5857, 0.6380 and 0.5061.
- **`voyage-4`'s scores barely moved.** No row's top score changed by more than 0.0004 between
  the second and third passes, nor between the first and second, uploads aside. The 1 November
  screen saw about 0.003 on EmbeddingGemma, which is what the 0.005 band was set against.
- **The keyword search** for `asset tag`, through `/api/search` as the Employee, gave one result,
  Asset Inventory Melbourne Office, as on 1 November.
- **The uploads:**
  - D21 answered 201 and was Indexed. FR-10 classified it at upload. The type was `Procedure`,
    applied at 0.8. The department was the user's `Operations`, with the model's matching
    suggestion held as provisional at 0.7;
  - T06 answered 201 and was Indexed. FR-16 wrote its summary, which is indexed as an
    AI-generated passage (D-125) and is the top candidate for the cups question.
- **Statements varied in wording from run to run,** for FR-11.2, FR-12.4, FR-12.5 and FR-13.2's
  first turn. Their facts and sources did not.

## Not covered

- **The other threads of the 1 November screen,** t01 to t07 and t09. The walk does not ask them.
  FR-13 on anthropic is measured by the thread draws (D-112's notes).
- **The walk itself.** This is the screen, not a walk. Nobody has walked the script on the
  Anthropic alpha.
- **A copy is not the alpha.** The alpha's database stays as it was, and a walk adds its own
  rows to it.

`kmp_alpha_screen_20261115` is left in place as this screen's database, and nothing points at it.
