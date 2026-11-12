# Demonstration script: the twelve M6 requirements on the alpha

> **Amended 2 November 2026,** after item 10 (D-90). The changes:
>
> - the lockout is FR-02's and is shown, with a throwaway account (D-25);
> - FR-13's wording is corrected (D-91), and its per-turn claim is cited to its tests;
> - the full list of recorded deviations, including the sentence D-33 owes;
> - a current list of what the front-end suite does not cover;
> - D-61's six routes restored;
> - "item 9a" corrected to Stage 4's.
>
> The 1 November walk followed the earlier text, and `docs/stage-5-item-8-walk.md` records it as it was.
>
> **Amended 3 November 2026,** after step 3's lockout walk. The changes:
>
> - FR-02 step 4's expectations are corrected. The 2 November text said the fifth wrong password,
>   and every attempt after it, shows the locked-account message. Only the right password shows
>   it, and only for the first five attempts during a lock (D-25, D-26);
> - FR-04 step 1 says the "You've been logged out" confirmation does not appear (a defect, found
>   at step 6 and confirmed in the walk's 3 November note). The fix is merged (D-97), but the
>   alpha still runs `8598d19`, so the step holds until the alpha is redeployed.
>
> **Amended 7 November 2026,** after the D-35 recording (D-98): Xbox Game Bar records only the
> window that had focus when it started, so the recording advice now names OBS's Display Capture.
>
> **Amended 12 November 2026,** after FR-13 was measured on both providers (D-112 and its notes).
> The changes:
>
> - FR-13's step 5, the screen's notes and the answer on conversations said its measurement "comes
>   after the gate" or "is step 5's". It was made on 3 November and since, and they now say what it
>   found on each provider;
> - the deviations list names D-112, with its reason and numbers, as D-112 requires, and D-42's
>   entry says how its boundary fared on each provider;
> - the re-scoping tests are cited at `test_fr11_scoping.py:610` and `:635`, where they begin on
>   `main` at `a668a08`. The earlier text cited `:608` and `:633`.
>
> The alpha still runs FLM at `8598d19`, so step 5's advice stands for a walk on it.
>
> **Amended 12 November 2026, later,** after #95 and D-94's notes of 12 November. The changes:
>
> - "What is not verified by any test?" is derived again from `frontend/tests`. The 2 November
>   list named as untested screens that have been tested since, from Register to Search. It now
>   names the clauses still untested, then what is tested;
> - the same list says what the stylesheet checks reach. The tab-order test fails if a
>   stylesheet rule hides any keyboard stop on the screens it walks, the header search field and
>   the Ask link among them.
>
> **Amended 12 November 2026 (night),** after the deviations list was checked against `main`. The
> changes:
>
> - D-33 §1's, D-56's and D-69's entries now say what holds on the alpha's build and what holds
>   on `main`. On `main`, FR-10 and FR-19 are built and `voyage-4` has a partial-match floor
>   (D-104, D-105, D-107, D-120). Their 2 November text is true of the alpha only.

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

**The D-35 screen recording.** Start recording the screen before step 1, and keep it.

- **Use OBS Studio, with a Display Capture source,** so that both browser windows land in one
  file. Xbox Game Bar (`Win+Alt+R`) records only the window that had focus when it started, so
  every switch between window A and window B is lost.
- **Set OBS's Base (Canvas) Resolution to the screen's own,** and Fit the capture to it (Ctrl+F).
  With a 1920×1080 canvas on the laptop's 3840×2400 screen, only the top-left quarter is
  recorded.
- **Keep the file under 2 GB,** for Dropbox. 3,000 kbps at 30 fps comes to about 23 MB a minute.
- **Use a crash-safe format** (OBS's Hybrid MP4), and keep the laptop plugged in and awake. A
  standby or a restart takes Docker, the database and FLM down with it (D-98).

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
   - Five failures lock the account for 15 minutes, and a locked account gets a 403 with its own
     message. That is **FR-02's**, not FR-03's (D-25). FR-03 adds only the warning, the countdown
     and the administrator release. **Never lock `corpus.admin@example.com` or the demonstration
     accounts.** Show it with its own account, in step 4.
2. **Sign in with the right password.**
   - **Expected:** the Employee's dashboard, and the navigation shows `Signed in as` the name
     registered in FR-01.
3. **In window A, sign in as `corpus.admin@example.com`.**
   - **Expected:** the Administrator's dashboard, and `Role management` in the navigation.
4. **The lockout, with a throwaway account.** Register a new account through FR-01, with a
   password used nowhere else.
   - **Sign in with a wrong password five times.**
     - **Expected:** "Invalid email or password." each time (a 401). The fifth locks the account
       for 15 minutes, and nothing on the screen says so.
   - **Sign in with the right password.**
     - **Expected:** "This account is temporarily locked after too many failed sign-in attempts.
       Please try again later." (a 403). Only the right password shows it. A wrong password during
       the lock is still the ordinary 401, so the lock is never confirmed to someone who knows
       only the address.
   - **Stop after one or two attempts.** Every attempt during the lock is counted. Past ten in
     all, even the right password gets the 401 until the lock expires (D-26).
   - **After 15 minutes, sign in with the right password.**
     - **Expected:** the dashboard. The lock is never extended, so the wait is 15 minutes from the
       fifth failure. Leave this until the end of the walk, or say it rather than wait.

### FR-04 · Logout and session management (window B)

1. **Log out** from the navigation.
   - **Expected:** the sign-in page.
   - **Do not claim the confirmation on the alpha at `8598d19`.** FR-04 asks for "You've been
     logged out", and that build does not show it: a known defect (`docs/stage-5-item-8-walk.md`,
     3 November notes). Say so if asked. It is fixed on `main` (D-97). On an alpha redeployed from
     a commit that includes the fix, expect the "Logged out" notice, and check that it appears.
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
4. **Say it:** every protected route is tested from both roles (23 of 23 endpoints). The audit
   trail D-57 to D-61 found no route across the permission boundary on the six routes it walked:
   `/api/ask`, `/api/search`, `/api/conversations*`, `/api/documents/{id}`,
   `/api/meetings/{id}` and reprocess. The four FR-14 and FR-15 routes added since
   (`GET /api/dashboard`, `GET /api/documents/browse`, `GET /api/documents/{id}/download` and
   `DELETE /api/documents/{id}`) have leakage tests, but no audit has walked them until item
   11.

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
   - **What this shows:** the same history, in two roles, and the second turn's scope differs
     by role.
   - **That the scope is re-evaluated on every turn is evidenced by test, not by this walk.**
     Two sessions holding two roles cannot show a role changing mid-thread.
     `apps/api/tests/test_fr11_scoping.py:610` changes the role between turns, from Employee to
     Administrator, and the next turn takes the new scope. `:635` does the reverse.
4. **Reopen a thread from `Your conversations`, or from the dashboard's recent questions** (D-77).
   - **Expected:** the turns come back in order.
5. **Do not ask a follow-up that needs the earlier turn to make sense,** such as "Is there a limit
   on how much of it I can save up?".
   - In the screen's three clean cases (t01, t04, and t06 as the Administrator), such a
     follow-up was not correct on any trial (D-91). The replies varied across trials in t04.
   - **FR-13 is partial at the gate** (D-91).
   - [What the screen found](#what-the-screen-found-that-the-walk-avoids) has the details.
   - **The measurement since agrees, on the alpha's build.** On FLM, with history, 1 of 9 frozen
     follow-ups matched on the alpha's code (3 November), and 2, 3 and 2 of 9 on `main` (8 and
     9 November). D-112 accepts the clause as partial for NIT3003, a recorded deviation.
   - **On the default build it is different.** On `anthropic` (D-122), 9 of 9 matched on each of
     three draws (D-112's note of 12 November). That is a measurement, not yet the auditor's
     verdict, and the alpha does not run that build.
   - If an assessor asks for one, say so plainly, and say which build is running.

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

- **Follow-ups that need the earlier turn did not resolve.** Rescored with the frozen rule
  (version 2), from the stored statements, with nothing re-run (D-91):
  - **The clean cases:** in the three threads whose first turn was correct on every trial and
    whose follow-up expected an answer (t01, t04, and t06 as the Administrator), the follow-up
    was not correct on any trial. t04's replies varied from trial to trial; t01's and t06's
    did not.
  - **Confounded:** t02, t03, t05 and t07. A first turn that was not correct says nothing
    about history.
  - **A different failure:** t06 and t07 as the Employee expected a no-answer, and were answered
    from material the Employee may read. That is no leak.
  - **Only t08 is correct on both turns.** It is the topic change, whose second question stands
    on its own.
  - **t09 failed, as predicted** (D-86 decision 2).
  - **The prompt labels the earlier questions as context,** with "The question to answer:"
    before the new one (`apps/ai/prompting.py`). Whether the failure was the model's or the
    prompt's was not known on 1 November. Step 5's cold and spelled-out runs split it on
    3 November: for t01 and t05 history was the limit, and for t02, t03, t04, t06 and t07 asked
    by the Administrator, and t09, generation or retrieval limited it as well (D-91's note).
  - **It is not tuned here.** FR-13's thread run (D-86) is the measurement. Options 1 and 2
    (D-103) and option 3 (D-111) were measured on FLM and not adopted, and D-112 accepts the
    clause as partial for NIT3003. On `anthropic`, see FR-13's step 5 above.
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
- **The permission boundary:** the audits D-57 to D-61 found no route across it on the six routes
  they walked (`/api/ask`, `/api/search`, `/api/conversations*`, `/api/documents/{id}`,
  `/api/meetings/{id}` and reprocess). The four FR-14 and FR-15 routes have leakage tests, but no
  audit has walked them until item 11.

## The answers worth having ready

- **Can a citation point at a passage that does not support its statement? Yes.**
  - Verification checks that the identifier was supplied, not that the passage supports the
    statement. Invariant 5 concedes this by design.
  - Tonight's screen saw it, as [above](#what-the-screen-found-that-the-walk-avoids).
  - Stage 4's item 9a measured three such mis-citations (`docs/flm-baseline.md`, "three
    mis-citations"). Stage 5's item 9a is the leakage tests, which is a different item.
- **Does the same question always answer the same way? No.** D-40 is open, and its trigger is
  unidentified. These questions were screened for it.
- **Does the assistant follow a conversation?** It keeps the thread, and its scope is re-checked
  on every turn, which is tested (`test_fr11_scoping.py:610` and `:635`). A follow-up that only
  makes sense with the earlier turn did not resolve in the screen's clean cases (D-91). **FR-13 is
  partial at the gate.** Say so, and do not claim more.
  - **On the alpha's build, FLM,** the measurement agrees: with history, 1 of 9 frozen follow-ups
    matched on the alpha's code, and 2, 3 and 2 of 9 on `main`. D-112 accepts the clause as
    partial for NIT3003.
  - **On the default build, `anthropic`,** 9 of 9 matched on each of three draws. That is a
    measurement, and the auditor has not read it yet (D-112's note of 12 November).
  - **On both,** earlier answers are never passed (D-42).
- **What is not verified by any test?** Give this list, derived from `frontend/tests` on
  12 November. It supersedes D-62's and the one this script gave on 2 November. The record, clause
  by clause, is `docs/stage-5-front-end-clauses.md` for FR-01 to FR-09 and FR-12's search half, and
  `docs/stage-5-clause-audit.md` for FR-11 to FR-15.
  - **Not tested in the front-end suite:**
    - **FR-06:** the visibility choice the Upload and Meetings screens offer an Administrator,
      and the fixed note they show an Employee in its place (`visibilityOptionsFor`);
    - **FR-08:** the sentence the repository shows beside a document whose processing failed,
      for any of its statuses (`statusMessageFor`). The Try again action is tested;
    - **FR-09:** the stored transcript shown in full. The meeting's page is rendered with its
      transcript, and `meetingDelete.test.jsx` checks part of the text, not all of it;
    - **FR-12:** the note on a search result that matched on its title and has no passage to
      show (`TEXT.searchSnippetUnavailable`);
    - **whether a thing can be seen, beyond what the stylesheet checks reach.** jsdom applies no
      stylesheet and lays nothing out, so no test sees a page laid out, and a rule that hid an
      element would pass every test except where a test reads the stylesheets as text
      (`tests/stylesheets.js`). Those tests check that no rule hides:
      - every keyboard stop on the screens `tabOrder.test.jsx` walks: sign-in, and, as an
        Employee, the dashboard, documents, upload, meetings and Ask. The header search field
        and the Ask link are among those stops;
      - the skip link, the Ask screen's acknowledgement line, and the drop zone's status and
        label.
  - **Tested:**
    - **every route, as an Employee and as an Administrator,** for the Ask link and the header
      search field (`askNavLink.test.jsx`, `headerSearchField.test.jsx`);
    - **registration and sign-in:** the password rules and the submit gate, the locked-account
      message, the show-password toggle, the submit lock and the role landing;
    - **logout** and its confirmation, **role management**, the **403 page**, and the
      **RequireAuth** and **RequireRole** guards;
    - **upload:** the format refusal, each file's progress, and the queue and its retry;
    - **meetings:** the processing indicator, the attendees and deletion;
    - **search:** the two-character minimum, the upper bound and the grouping;
    - **the Ask screen and its threads:** citations, the Sources panel, the no-answer state and
      partial matches;
    - **the dashboard**, and **the repository** with its detail view;
    - **NIT3004's screens:** FR-10's classification and tag administration, FR-19's
      knowledge-gap log, and recording transcription (D-123);
    - **across screens:** the 429 and 503 messages, the tab order, the text equivalents, the
      focus ring and colour contrast, the production build and the same-origin client.
- **Where does the build fall short of a clause on purpose?** Each is a deviation with a reason,
  never a tick. Each was checked against its entry on 2 November. D-42's and D-112's were checked
  again on 12 November, and D-33's, D-56's and D-69's against `main` that night. The rest were not
  checked again.
  - **D-15 (FR-08):** four upload formats, PDF, DOCX, XLSX and TXT, not the six FR-08's upload
    area names. DOC and XLS have no parser.
  - **D-25 (FR-02):** the session carries no role. The role is re-read on every request, so a
    role change takes effect without re-login. The literal clause is not met; its purpose is
    exceeded.
  - **D-33 §1 (FR-08), the sentence D-33 owes this script:** FR-08's classification hand-off is
    deferred with FR-10, which is NIT3004 work. When FR-10 is built, §7.8 step 4 goes between
    `ExtractedContent` and chunking in `ingest_and_index_document()`, and it must be unable to
    fail the document — a classification failure marks it unclassified and never revokes
    indexed status (`CLAUDE.md` invariant 8).
    - **That holds on the alpha's build, `8598d19`,** which has no classification.
    - **On `main`, FR-10 is built, so the hand-off is not deferred there** (D-104, D-105).
      `_classify` in `apps/ingestion/documents.py` runs between storing the extracted text and
      chunking, in a savepoint of its own. A failure is logged and leaves the document
      unclassified, its status unchanged. The upload's 201 carries `classification`, or null.
  - **D-33 §2 (FR-09):** a 422 when every chunk fails to embed, which FR-09's Responses clause
    does not list. The transcript is kept (invariant 8).
  - **D-42 (FR-13):** earlier questions are passed to the model, not earlier answers. Its
    boundary is contradicted by the 1 November screen (D-42's dated note, D-91). On FLM,
    follow-ups whose referent is in the earlier question mostly did not resolve either. On
    `anthropic` they resolved on every draw, and a referent that is only in an earlier answer is
    still never passed (D-42's note of 12 November).
  - **D-43 (FR-13):** a conversation's `Update` is its title on create and the time of its last
    turn. There is no rename route and no `PATCH`.
  - **D-112 (FR-13):** the follow-up clause, "…so that pronouns and abbreviated references
    resolve correctly", is accepted as partial for NIT3003 on the FLM build. With history, 2, 3
    and 2 of the 9 frozen follow-ups matched on `main` (8 and 9 November), against 6 of 9 spelled
    out, and the alpha's code matched 1 of 9 (3 November). The reason D-112 gives: on several
    threads the right passage was supplied at rank 1, and generation answered from "the
    turn-1-adjacent passage". Options 1 and 2 (D-103) and option 3 (D-111) were measured and not
    adopted. On the default build, `anthropic`, it is not admitted as a deviation: there the
    resolving half measured 9 of 9 on each of three draws, and counts only when the auditor reads
    it as met (`M6-BUILD-PROMPT.md`'s Done line, amended 12 November).
  - **D-45 (FR-12):** there is no input sanitiser. The defence is parameterised SQL, React's
    escaping and the prompt's delimiter.
  - **D-56 (FR-12):** on the FLM build, the alpha's included, partial matches have no relevance
    floor. The acknowledgement is recorded.
    - **Step 7 owed the floor (D-93) and set none.** At 0.30 the margin rule cannot set one, and
      retrieval scores did not separate answerable from unanswerable questions in users' wording
      (D-102).
    - **On the default build, `anthropic`,** a near miss is offered as a partial match only at or
      above 0.2468 on `voyage-4` (D-120).
    - D-120 records D-56 as narrowed on Voyage, and still open on EmbeddingGemma.
  - **D-69 (FR-14):** the dashboard does not read KnowledgeGaps. That is deferred with FR-19, and
    it holds on the alpha's build.
    - **On `main`, FR-19 is built and the deferral has ended** (D-69's note of 10 November,
      D-107). An Administrator's dashboard shows the number of Open knowledge gaps and the top
      entries.
    - An Employee's payload keeps its keys, because `review_knowledge_gaps` is the
      Administrator's alone.
  - **D-70 (FR-14):** the department filter narrows documents only. Meetings have no department.
  - **D-72 (FR-15):** Department comes from the documents' column, not from ContentTags. That is
    a deliberate departure from FR-15's server clause.
- **Why does one question fail at generation?** "How are records managed and retained?" (from
  `tests/load/common.js`, not one of the thirty) gave a 503 twice at one user and three times at
  five users.
  - **At five users,** the attempt log shows every failed attempt was a reply that stopped
    before its JSON closed.
  - **At one user,** the cause was not logged, so the same failure there is inferred, not
    observed.
  - Step 7 observes it, logging each attempt's `finish_reason` and token count before anything
    changes. It is not one of the questions here.

## Afterwards

- **The walk leaves its accounts, questions, uploads and threads in `kmp_demo_20261101`.**
- **Restoring the snapshot again (D-88) resets all of it.** Do that only before a new set of
  demonstration threads is built, never between building them and showing them.
