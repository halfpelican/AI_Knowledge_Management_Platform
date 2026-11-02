# Demonstration script: the twelve M6 requirements on the alpha

Stage 5 item 9. This walks all twelve MUST-HAVE requirements, in the gate's order, on the
deployed alpha (`docs/alpha-deployment.md`, D-64, D-88). It is also item 8's live end-to-end
pass: both roles, real files, the real corpus.

- **The alpha:** `http://127.0.0.1:8000`, served by Waitress from the `KMP_Prototype-alpha`
  worktree, on the database `kmp_demo_20261101` (Objective 02's corpus, restored from item 6's
  measured snapshot).
- **Every question below was screened before the walk** (D-40): its scores, and three runs of
  each through the shipped pipeline. [The screen](#the-d-40-screen) has the figures, and
  `corpus/demo/screening-2026-11-01.json` has every number.

## Before the walk

**The conditions D-40 sets, not only its decision:**

1. **Do not re-index, reprocess or delete anything** from the first question until the last one.
   - A re-index or a reprocess moves vectors.
   - A delete removes candidates.
   - Either can move a passage across `RELEVANCE_THRESHOLD`, and change an answer that was screened.
   - The walk's only delete is the optional last step, after every question has been asked.
2. **Ask only the screened questions, worded exactly as written here.** A rephrased question is an
   unscreened question.
3. **The same question can still answer differently on two runs** (D-40, open). If it happens, say
   so. Both outcomes are honest, and the no-answer is a legitimate reply.

**The D-35 screen recording.** Start recording the screen before step 1 (Windows: `Win+Alt+R`
with the Xbox Game Bar, or OBS), and keep it.

- **It is the demonstration's insurance** if the NPU fails on the day, and it must exist before
  any re-index.
- **If this walk is the recording,** the walk itself must not re-index.

**The checks, on the day:**

- **FLM is serving and `scripts/check_flm.py` passes.** These are steps 2 and 4 of
  `docs/alpha-deployment.md`.
- **The server runs from `C:\kmp-demo\2026-11-01\start-alpha.ps1`, in its own window.** It printed
  `Django will connect to: kmp_demo_20261101`.
- **`Documents\KMP-alpha-deployments.txt`'s last line** names the commit that is running, with
  `dirty=False`.
- **The five smoke checks pass** (step 8).
- **Nothing else is serving.** No `manage.py runserver` on port 8000, and no `npm run dev` on
  `localhost:5173` or `5174`. Check that `Server: waitress` answers on 8000. On 2 November the
  alpha's window had been closed and a dev server held port 8000, so the first attempt at FR-01 ran
  against `kmp` (`docs/stage-5-item-8-walk.md`). Keep the alpha's window open for the whole walk.

**Two browser windows, both on `http://127.0.0.1:8000`.** Cookies are per host, so use the same
host in both windows.

| Window | Who | Account |
|---|---|---|
| **A**, a normal window | the Administrator | `corpus.admin@example.com`, with the password the user set (D-88) |
| **B**, a private window | the Employee | registered in FR-01 below. Choose the password at the time and write it nowhere. |

**Files, from any checkout at or after this commit:**

| For | File |
|---|---|
| FR-08, the upload | `corpus/demo/D21_bicycle_end_of_trip_facilities.docx` |
| FR-09, the transcript | `corpus/demo/T06_sustainability_working_group.txt` |
| FR-08, refused by signature | `corpus/objective-02/invalid/I01_annual_report_2026.pdf`, a PNG named `.pdf` |
| FR-08, refused as a duplicate | `corpus/objective-02/invalid/B01_duplicate_of_D03_renamed.pdf`, D03's bytes |
| FR-08, too large (optional) | made on the day, outside every checkout, as shown below |

```powershell
$f = [IO.File]::Create('C:\kmp-demo\2026-11-01\oversized.pdf'); $f.SetLength(52428801); $f.Close()
```

## The walk

Each step names the clause it shows. "Expected" is what the screen showed. Where the interface
words a message, the message is quoted.

### FR-01 · Registration (window B)

1. **Register** (`/register`). Name `Demo Employee`, email `demo.employee@example.com`, and a
   password that is too weak, such as `password`.
   - **Expected:** refused, with the reason under the password field. The rules are at least 8
     characters, with an uppercase letter, a digit and a special character.
2. **Register again** with a password that meets the rules.
   - **Expected:** the account is created as an **Employee**, and registration starts no session
     (D-23), so the next screen is sign-in.
3. **Optional: register `corpus.employee@example.com` again.**
   - **Expected:** refused under the email field.

### FR-02 · Login (window B)

1. **Sign in with the wrong password, once.**
   - **Expected:** "Invalid email or password.", which does not say which half was wrong.
   - Five failures lock the account for 15 minutes (FR-03, not in the gate). Do not show it.
2. **Sign in with the right password.**
   - **Expected:** the Employee's dashboard, and the navigation shows `Signed in as` the name
     registered in FR-01.
3. **In window A, sign in as `corpus.admin@example.com`.**
   - **Expected:** the Administrator's dashboard, and `Role management` in the navigation.

### FR-04 · Logout and session management (window B)

1. **Log out** from the navigation.
   - **Expected:** the sign-in page.
2. **Press Back, or open `http://127.0.0.1:8000/dashboard` directly.**
   - **Expected:** sent back to sign-in, because the session is gone on the server, not only in the
     page.
3. **Sign in again as the Employee** for the rest of the walk.
4. **Say it:** a session expires after 60 idle minutes (the inactivity expiry, saved on every
   request). It is not shown live.

### FR-05 · Role management (window A)

1. **Open `Role management`.** It lists every account with its role.
2. **Change `Corpus Employee`'s role to Administrator, and save. Then change it back to Employee,
   and save.**
   - **Expected:** each change is saved, and shown on the list.
   - Each change is written to the audit log (`C:\kmp-demo\2026-11-01\logs\audit.log`). Open it if
     asked.
3. **Do not change `Demo Employee`'s role.** The walk relies on it being an Employee from here on.

### FR-06 · RBAC enforced server-side (window B)

1. **Open `http://127.0.0.1:8000/admin/roles`.**
   - **Expected:** the access-denied page. That is the interface, which is usability, not security.
2. **Open `http://127.0.0.1:8000/api/users` in the same window.** The browser sends the
   Employee's session.
   - **Expected:** a JSON **403** from the server, naming the missing permission. This is the
     enforcement: the server refuses whatever the page shows.
3. **Open the same address in a third, signed-out window.**
   - **Expected:** a JSON **401**.
4. **Say it:** every protected route is tested from both roles (23 of 23 endpoints), and the audit
   trail D-57 to D-61 found no route across the permission boundary.

### FR-08 · Document upload, extraction and indexing (window B)

1. **Open `Upload` and choose `D21_bicycle_end_of_trip_facilities.docx`.**
   - Department: `Operations`.
   - Visible to: an Employee is not offered a choice. The page shows a note, because the only
     scope an Employee may upload to is both roles (D-29). An Administrator would see a select.
   - Upload.
   - **Expected:** it ends **Indexed**. Text was extracted from the DOCX, chunked and embedded in
     the same request, and the record and its vectors commit together.
   - **The document's title is the file name,** `D21_bicycle_end_of_trip_facilities`, unless it is
     edited in the queue row before uploading. The title does not affect the screen.
   - **The drop zone gives no feedback when a file is chosen.** The browser's own "No file chosen"
     label comes back, and the row appears under **Files**, which may be below the fold. This is a
     usability finding for item 7.
2. **Choose `I01_annual_report_2026.pdf`.**
   - **Expected: 415.** A PDF's name over a PNG's bytes, refused by the file's signature.
3. **Choose `B01_duplicate_of_D03_renamed.pdf`.**
   - **Expected: 409**, "A duplicate document already exists.". The bytes are D03's.
4. **Optional: choose `oversized.pdf`** (50 MB + 1 byte).
   - **Expected:** refused as too large, before anything is stored.
5. **Optional: choose any file of another type,** such as a `.png`.
   - **Expected:** refused in the page, naming the four accepted formats (PDF, DOCX, XLSX, TXT;
     D-15).

None of the refusals adds a chunk, so none affects the screened questions.

### FR-09 · Meeting transcript ingestion (window B)

1. **Open `Meetings`.**
   - Title: `Sustainability Working Group`.
   - Meeting date: `2026-10-29`.
   - Transcript file: `T06_sustainability_working_group.txt`.
   - Attendees: optional, and picked from existing accounts (FR-20's participation record).
     Leave them empty, or pick `Demo Employee`. They do not change the transcript's chunks, and
     they never grant access (invariant 3: meetings are scoped by role, never by attendance).
     Typed names are refused, because the route takes account ids.
   - Visible to: leave it unchosen. Submit.
   - **Expected:** stored and **Indexed**.
2. **Open the meeting.**
   - **Expected:** its details and the transcript.

The screen ingested both files exactly as steps FR-08.1 and FR-09.1 do, the same bytes through the
same routes. Every question below was screened with them in place.

### FR-11 · Permission-aware retrieval scoping (both windows)

1. **Window B, `Ask`:** "Who is the sponsor of Project Atlas?"
   - **Expected:** "This question cannot be answered from the available knowledge base."
   - Nothing above the threshold is readable by an Employee, so generation is not called (path A).
   - The answer comes from D09, which is Administrator-only. That document reached neither the
     ranking nor the model, and the reply does not reveal that it exists.
2. **Window A, the same question.**
   - **Expected:** answered, citing **Project Atlas Kickoff Brief** (D09).
3. **Existence is not disclosed.**
   - In window A, open D09 from `Documents`, and copy its address (`/documents/<id>`).
   - Open that address in window B.
   - **Expected:** the same "not found" as an address that never existed.
4. **Window B, `Documents`:** D09, D15 and D16 are not listed. Window A lists them.

### FR-12 · Knowledge search and answer generation, with verified citations (window B)

1. **Search,** with the search field in the page header, or at `/search`: `asset tag`.
   - **Expected:** one result, **Asset Inventory Melbourne Office** (D14), with a snippet showing
     the phrase. Checked on the screening database.
   - **Not the repository's "filter by title" field.** That is FR-15's, and it matches titles only.
     FR-12's search reads the passages, and it writes a `SearchLog` row.
2. **`Ask`:** "How quickly do we have to acknowledge a customer complaint?"
   - **Expected:** answered, with a numbered citation to **Customer Complaints Procedure** (D06).
   - Open the citation: it leads to the cited passage's document.
   - Every statement carries a citation that was checked against the passages actually supplied
     (invariant 5).
3. **`Ask`:** "How much did the latest penetration test cost?"
   - **Expected:** the fixed no-answer, with no generation (path A). Nothing in the corpus answers
     it, and no statement without a citation is ever shown (invariant 6).
4. **`Ask`:** "How many bicycles can the secure bike cage hold?"
   - **Expected:** answered, **40**, citing the guide uploaded in FR-08
     (`D21_bicycle_end_of_trip_facilities`). Upload to answer, end to end.
5. **`Ask`:** "When will single-use cups be removed from the office kitchens?"
   - **Expected:** answered, **1 March 2027**, citing the meeting ingested in FR-09.

### FR-13 · Conversational assistant, permission re-checked per turn (both windows)

1. **Window B, a new conversation, two turns** (thread t08, the topic change):
   - "What was the customer satisfaction score last quarter?"
     - **Expected:** 86 percent, citing the **Customer Success Retrospective**.
   - Then: "Where are the first aid kits kept?"
     - **Expected:** at reception and on every floor, citing the **Health and Safety Induction
       Guide**.
   - The thread keeps its history, and a new topic in the same thread is answered on its own
     terms.
2. **Window B, another new conversation:**
   - "What was the customer satisfaction score last quarter?"
     - **Expected:** answered as before.
   - Then: "Who is the sponsor of Project Atlas?"
     - **Expected:** the fixed no-answer.
3. **Window A, the same two turns.**
   - **Expected:** the first is answered as before. The second is answered: "The sponsor of Project
     Atlas is the chief operating officer", citing **Project Atlas Kickoff Brief** (D09).
   - **This is the clause.** In the same kind of thread, with the same history, the permission is
     checked again on every turn, for whoever asks.
4. **Reopen a thread from `Your conversations`, or from the dashboard's recent questions** (D-77).
   - **Expected:** the turns come back in order.
5. **Do not ask a follow-up that needs the earlier turn to make sense,** such as "Is there a limit
   on how much of it I can save up?". The screen found the model answering the earlier question
   again in 7 of the 9 frozen threads, the same way on all three runs.
   - [What the screen found](#what-the-screen-found-that-the-walk-avoids) has the details.
   - If an assessor asks for one, say so plainly. FR-13's thread measurement (D-86) comes after
     the gate.

### FR-14 · Dashboard overview (both windows)

1. **Window B, `Dashboard`.**
   - **Expected:** recent documents (D21 at the top), recent meetings (the sustainability group's),
     indexed totals, and **Your recent questions**, each opening its conversation.
2. **Window A, `Dashboard`.**
   - **Expected:** larger totals.
   - The Employee's totals leave out Administrator-only items, and nothing on the Employee's
     dashboard reveals that they exist.

### FR-15 · Document repository and filtered browsing (window B unless stated)

1. **`Documents`:** the repository, filtered by department, type, date and tags.
2. **Two filters narrowing** (D-74): topic `people`.
   - **Expected:** D01, D07, D08 and D13.
   - Add process `onboarding`.
   - **Expected:** D08 and D13.
3. **The empty state** (D-74): open
   `http://127.0.0.1:8000/documents?project=supplier%20review&topic=safety`.
   - **Expected:** "No documents match these filters", with both filters shown as active.
   - **Why the address and not the facets:** the facets narrow as values are picked. Choose
     `supplier review`, and `safety` is no longer offered, so D-74's pair cannot be clicked
     together. The repository keeps its filters in the address, so a link reaches the 204. A title
     filter that matches nothing, such as `zzz`, shows the same state.
4. **Facets disclose nothing** (D-74): the Project values offered to the Employee do not include
   `atlas`.
   - Window A's do. `atlas` is used only on D09 and D15.
5. **Open a document,** for example D21.
   - **Expected:** its details and its extracted content (D-63).
   - Download the original, which is FR-15's scoped download (D-75).
6. **Optional, and only now, after every question: window A deletes D21** (D-73).
   - **Expected:** it is gone from both windows' lists.
   - This is the walk's only delete, and nothing is asked after it.

## The D-40 screen

The screen ran on `kmp_demo_screen`, a scratch database restored from the same snapshot, with the
same checks as D-88. The steps:

1. Score every question below, as the role that asks it.
   - Thread turns are composed as the pipeline composes them, using the shipped `embed_question`,
     `rank` and the harness's candidate set.
   - What is recorded: the top score, how many passages are admitted, and every candidate within
     0.005 of `RELEVANCE_THRESHOLD` (0.30).
2. Upload D21 and T06 through the real routes, as an Employee, exactly as FR-08.1 and FR-09.1 do.
3. Score again.
4. Ask each question three times through `answer_question`, the shipped pipeline.

**The rule.**

- **Where an answer is expected:** the top score is at least 0.35, and no candidate is within 0.005
  of the threshold.
- **Where a no-answer is expected:** either the top score is at most 0.28 (path A, so generation is
  never called), or the no-answer came on all three runs.
- **Every question:** the same outcome on all three runs.

| Step | Question | Role | Top score (its source) | Admitted | Nearest to 0.30 | Three runs |
|---|---|---|---|---|---|---|
| FR-11.1 | Who is the sponsor of Project Atlas? | Employee | 0.1930 (Asset Inventory) | 0 | 0.1930 | the no-answer, path A, every run |
| FR-11.2 | the same | Administrator | 0.5019 (Project Atlas Kickoff Brief) | 2 | 0.3235 | "The sponsor is the chief operating officer." [D09], every run |
| FR-12.2 | How quickly do we have to acknowledge a customer complaint? | Employee | 0.6181 (Customer Complaints Procedure) | 3 | 0.2944 | "…acknowledged within one working day…" [D06], every run |
| FR-12.3 | How much did the latest penetration test cost? | Employee | 0.2526 (Procurement Guidelines) | 0 | 0.2526 | the no-answer, path A, every run |
| FR-12.4 | How many bicycles can the secure bike cage hold? | Employee | 0.4584 (the uploaded guide) | 1 | 0.1713 | "The secure bike cage holds 40 bicycles on two-tier racks." [D21], every run |
| FR-12.5 | When will single-use cups be removed from the office kitchens? | Employee | 0.5501 (the ingested meeting) | 2 | 0.2936 | "Single-use cups go from every kitchen on 1 March 2027." [T06], every run |
| FR-13.1, turn 1 | What was the customer satisfaction score last quarter? | Employee | 0.5251 (Customer Success Retrospective) | 1 | 0.2871 | "Our satisfaction score rose to eighty-six percent.", every run |
| FR-13.1, turn 2 | Where are the first aid kits kept? | Employee | 0.4290 (Customer Success Retrospective) | 2 | 0.2907 | "First aid kits are kept at reception and on every floor." [D03], every run |
| FR-13.2, turn 2 | Who is the sponsor of Project Atlas? (after turn 1) | Employee | 0.4100 (Customer Success Retrospective) | 1 | 0.2288 | the no-answer, every run (path B: the model was called and nothing survived verification) |
| FR-13.3, turn 2 | the same | Administrator | 0.4318 (Project Atlas Kickoff Brief) | 3 | 0.3088 | "The sponsor of Project Atlas is the chief operating officer." [D09], every run |

- **The scores are from the second and third passes,** with both uploads in place, as the walk
  has them.
- **Every row clears the rule.** No candidate for any question sits within 0.005 of the threshold.
- **FR-13.2's Employee turn passes on the rule's second limb.** It is path B, and the no-answer
  came on all three runs.

### What the screen found that the walk avoids

- **Follow-ups that need the earlier turn fail.** In 7 of the 9 frozen threads (t01, t02, t03,
  t04, t06, t07, t09), the second turn restated the first turn's answer, or answered wrongly, the
  same way on all three runs. t05's second turn found its phrase but cited another transcript.
  - **Only t08 passes both turns.** It is the topic change, whose second question stands on its
    own.
  - **The prompt does label the earlier questions as context,** with "The question to answer:"
    before the new one (`apps/ai/prompting.py`). This is the 4B model's behaviour, measured
    tonight.
  - **It is not tuned here.** FR-13's thread run (D-86) is the measurement, and it comes after the
    gate.
- **Citations that do not support their statement were seen,** the limitation invariant 5
  concedes. Several first turns cited another source for a correct sentence. For example, D20's
  "A weekly update will be published on the intranet until the move is complete" was cited to the
  Health and Safety Induction Guide.
  - None of the walk's questions does this. Each cites the source its sentence comes from, on
    every run.
- **The query embedding varies by about 0.003 run to run.** The same question against the same
  chunks scored 0.4988, then 0.4995, then 0.5019. That is more than D-40's 1e-4, and just inside
  the 0.005 band. A question with a passage in the band would be a coin-toss.
- **The meeting route takes attendees as account ids.** The screen's first upload, with names,
  was a 400. FR-09.1 says to pick attendees from accounts, or to leave them empty.

The files are:

- `corpus/demo/screening-2026-11-01.json`: every score and every run's statements;
- `corpus/demo/D21_bicycle_end_of_trip_facilities.docx` and
  `corpus/demo/T06_sustainability_working_group.txt`: the uploads.

`kmp_demo_screen` is left in place as the screen's database, and nothing points at it.

**D-40's figure, re-read over Objective 02** (the brief asked for it after item 6): **3.2%**, which is 4 of the 124 passages admitted across the thirty's 34 runs
within 0.005 above the threshold. It was "about 6%" on the six-chunk corpus.

## The numbers worth having ready

- **Dual-role coverage:** 23 of 23 protected endpoints exercised from both an Employee and an
  Administrator session.
  - **The caveat:** the matrix counts a route as covered when a passing test reached it from that
    role. That is weaker than CLAUDE.md §8's "tested from both roles", which means every clause
    from both.
- **The thirty questions** (item 6, `corpus/objective-02/runs/2026-11-01/harness.json`):
  - schema conformance 100% (32/32), first attempt 100%;
  - fabricated identifiers 0% (0/27 statements). Verification strips any it finds;
  - out-of-scope chunks in any prompt or answer: 0.
- **p90 against NFR-08's 4 s** (`corpus/objective-02/runs/2026-11-01/nfr08-runs.md`):
  - 1 user: 51 s, answered only;
  - 5 users: a valid FAIL, with the 90th percentile a 503, and 277 s answered only;
  - this is a local-model baseline on one NPU (D-35, `docs/ai-provider.md` §7);
  - NFR-09 was not run, and its failure is a prediction, not a result.
- **The permission boundary:** every audit so far found no route across it (D-57 to D-61).

## The answers worth having ready

- **Can a citation point at a passage that does not support its statement? Yes.**
  - Verification checks that the identifier was supplied, not that the passage supports the
    statement. Invariant 5 concedes this by design.
  - Tonight's screen saw it, as [above](#what-the-screen-found-that-the-walk-avoids).
  - Item 9a's measurement of it comes after the gate.
- **Does the same question always answer the same way? No.** D-40 is open, and its trigger is
  unidentified. These questions were screened for it.
- **Does the assistant follow a conversation?** It keeps the thread and re-checks permission on
  every turn. A follow-up that only makes sense with the earlier turn is not reliable on this
  model: 7 of the 9 frozen threads failed it in the screen. Say so, and do not claim more.
  FR-13's thread measurement comes after the gate.
- **What is not verified by any test?** Give D-62's list, not "the front end is tested".
- **Where does the build fall short of a clause on purpose?** Each is a deviation with a reason,
  never a tick:
  - D-45: there is no input sanitiser. The defence is parameterised SQL, React's escaping and the
    prompt's delimiter.
  - D-42: earlier questions are passed to the model, not earlier answers.
- **Why does one question fail at generation?** Item 6 found "How are records managed and
  retained?" cut off before its JSON closed, three times, at one user and at five. It is not one
  of the questions here.

## Afterwards

- **The walk leaves its accounts, questions, uploads and threads in `kmp_demo_20261101`.**
- **Restoring the snapshot again (D-88) resets all of it.** Do that only before a new set of
  demonstration threads is built, never between building them and showing them.
