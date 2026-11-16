# Stage 5 item 8: the live walk of the twelve gate requirements, 2 November 2026

Item 8 is the end-to-end integration pass across all twelve MUST-HAVE requirements: both roles,
real files, the real corpus. It was walked live on the deployed alpha, following
`docs/demonstration-script.md`.

- **Who:** Benjamin Morovan drove the browser. The coordinating session confirmed each step on
  the server, reading only, from the database, the query and search logs, the audit log and the
  media folder.
- **The alpha:**
  - commit `8598d19`, clean;
  - database `kmp_demo_20261101`;
  - Waitress at 24 threads, `DEBUG` off;
  - FLM v0.9.39, with `check_flm.py` passing before the walk.
  The server was restarted at 13:17:54 (+11:00) from `C:\kmp-demo\2026-11-01\start-alpha.ps1`, and
  the restart is a line in `Documents\KMP-alpha-deployments.txt`.
- **Accounts:**
  - Window A: the Administrator, `corpus.admin@example.com`.
  - Window B: the Employee registered in FR-01, `demo.employee@example.com`, whose display name is
    "Ben Jeff".
- **Times are UTC** unless they end in "local".

**Result: all twelve passed,** each confirmed on the server as well as on screen.

## A false start, not counted

- The alpha's Waitress (pid 17032) had stopped before the walk began. Its log ends at its own
  "Serving on" line (2026-11-01 21:23:25 local), and `errors.log` is empty. Its window had most
  likely been closed.
- The main checkout's `manage.py runserver`, serving `kmp`, had taken port 8000 (12:25:10 local).
  A Vite dev server ran on `localhost:5174`, from the alpha worktree (12:24:29 local).
- So FR-01's first attempt ran against `kmp`, and `corpus.employee@example.com` was registered
  there. The server's 409 for that address on the alpha, and the alpha's database showing no new
  account, are how it was found.
- The user stopped both dev servers, and the alpha was restarted. `docs/demonstration-script.md`
  now checks for this before step 1.

## The twelve

### FR-01 · Registration: PASS

| Step | On screen | On the server |
|---|---|---|
| 1. A weak password | refused | — |
| 2. `demo.employee@example.com`, a valid password | created, then the sign-in page | an Employee, created 02:19:42, `last_login` empty, so no session was started (D-23) |
| 3. `corpus.employee@example.com` again | refused | still exactly one row |

### FR-02 · Login: PASS

| Step | On screen | On the server |
|---|---|---|
| 1. The Employee, a wrong password, once | could not sign in | the attempt counted, and was reset to 0 by the success that followed |
| 2. The Employee, the right password | signed in | `last_login` 02:24:41 |
| 3. The Administrator | "Login failed" three times with an old password, then signed in | the password set on 1 November had reached `kmp_demo_20261101`, since its hash differs from the snapshot's; `failed_attempts` went 3 → 0; `last_login` 02:25:25 |

### FR-04 · Logout and session management: PASS

- Log out leads to the sign-in page.
- Back, and a typed `/dashboard`, both lead back to sign-in.
- `/api/auth/me` answers a JSON 401.
- The 60-minute idle expiry was stated, not shown.

### FR-05 · Role management: PASS

The Administrator changed Corpus Employee to Administrator and back. Both changes are in the audit
log, each with its actor and the old and new roles:

- 02:35:55, Employee → Administrator;
- 02:38:15, Administrator → Employee.

At first the second change was selected but not saved. The audit log showed one change, and the
database still had Corpus Employee as an Administrator, which is how it was caught. The walk ended
with both Employees as Employees.

### FR-06 · RBAC enforced server-side: PASS

| Step | On screen |
|---|---|
| 1. The Employee opens `/admin/roles` | the access-denied page, the interface's guard |
| 2. The Employee opens `/api/users` | the JSON 403 "Your role does not hold the 'manage_roles' permission.", the server's enforcement |
| 3. Signed out, `/api/users` | the JSON 401 "Authentication credentials were not provided." |

### FR-08 · Document upload, extraction and indexing: PASS

| Step | On screen | On the server |
|---|---|---|
| 1. D21, a DOCX, department Operations, as the Employee | Indexed | Indexed, 1 chunk (43 → 44), visible to both roles, uploaded by the Employee |
| 2. I01, a PNG named `.pdf` | "Failed", with its reason | nothing stored |
| 3. B01, D03's bytes | "Failed", with its reason | nothing stored |
| 4. A file of 50 MB + 1 byte | "Failed", with its reason | nothing stored |

### FR-09 · Meeting transcript ingestion: PASS

- **The upload:** T06, through `Meetings`, as the Employee, dated 2026-10-29.
- **On the server:**
  - Indexed, visible to both roles;
  - 1 chunk (44 → 45), from 2,083 characters of transcript;
  - one attendee recorded, as a participation record that grants nothing (invariant 3).

### FR-11 · Permission-aware retrieval scoping: PASS

| Step | On screen | On the server (QueryLog) |
|---|---|---|
| 1. The Employee asks "Who is the sponsor of Project Atlas?" | the fixed no-answer | 02:56:43: `no_relevant_passage` (path A), `rejected_count` NULL (the model was not called), nothing retrieved |
| 2. The Administrator asks the same | answered | 02:57:52: answered, 2 retrieved, 0 rejected, cites Project Atlas Kickoff Brief |
| 3. D09's address, opened in the Employee's window | "That document could not be found." | — |
| 4. The repository | D09, D15 and D16 hidden from the Employee and listed for the Administrator | — |

### FR-12 · Knowledge search and answer generation, with verified citations: PASS

| Step | On screen | On the server |
|---|---|---|
| 1. Search `asset tag` | Asset Inventory Melbourne Office | SearchLog 03:13:45, 1 result. First tried in the repository's title filter (FR-15), which is not this search, then redone from the header |
| 2. "How quickly do we have to acknowledge a customer complaint?" | "Complaints are acknowledged within one working day. [1]" | 03:05:09: answered, 3 retrieved, 0 rejected, cites Customer Complaints Procedure |
| 3. "How much did the latest penetration test cost?" | the fixed no-answer | 03:10:04: path A, the model not called |
| 4. "How many bicycles can the secure bike cage hold?" | "The secure bike cage holds 40 bicycles on two-tier racks. [1]" | 03:10:56: cites `D21_bicycle_end_of_trip_facilities`, word for word the screened sentence |
| 5. "When will single-use cups be removed from the office kitchens?" | "Single-use cups go from every kitchen on 1 March 2027. [1]" | 03:12:13: cites Sustainability Working Group, word for word the screened sentence |

### FR-13 · Conversational assistant, permission re-checked per turn: PASS

| Conversation | Turn 1 | Turn 2 |
|---|---|---|
| The Employee, step 1 | 86% [Customer Success Retrospective] | first aid kits are kept at reception and on every floor [Health and Safety Induction Guide] |
| The Employee, step 2 | 86% | the no-answer: `no_statement_verified` (path B), 0 rejected, as screened |
| The Administrator, step 3 | 86% | "The sponsor of Project Atlas is the chief operating officer." [Project Atlas Kickoff Brief] |

- **Reopening:** step 1's conversation was reopened, with its turns in order.
- **The clause:** the same history, two roles, and the permission checked again on the second turn.
- **An extra turn:** step 1's conversation also has a third turn (03:16:39), the satisfaction
  question asked again before "new conversation" was pressed. It was unscreened, and was answered
  correctly from the same source.

### FR-14 · Dashboard overview: PASS

| Window | Indexed items shown | From the database, by the scoping rule |
|---|---|---|
| The Employee | 22 | 18 documents + 4 meetings |
| The Administrator | 27 | 21 documents + 6 meetings |

- **The difference of 5** is exactly the Administrator-only items: D09, D15, D16, T02 and T05.
- **The Employee's panels** showed recent documents (D21 first), recent meetings (T06) and their
  own recent questions.

### FR-15 · Document repository and filtered browsing: PASS

| Step | On screen | On the server |
|---|---|---|
| 1. The repository and its filters | as expected | — |
| 2. Topic `people`, then add process `onboarding` | 4 documents, then 2 | — |
| 3. The empty state | "No documents match these filters", through `/documents?project=supplier%20review&topic=safety`. See the findings | — |
| 4. Facets disclose nothing | `atlas` not offered to the Employee, offered to the Administrator | — |
| 5. Open D21, download the original | as expected | — |
| 6. The Administrator deletes D21, after every question | gone from both lists | the row is gone, Indexed is back to 20, chunks back to 44, and the stored file is removed from `MEDIA_ROOT` |

## Findings

None of these fails a gate requirement. Each is recorded for whoever picks it up.

1. **The FR-15 empty state can't be picked from the facets.** The facets narrow as values are
   chosen, so D-74's no-match pair (`supplier review` + `safety`) is never offered together.
   - The 204 empty state is still reached, through the address, which the repository keeps its
     filters in.
   - D-74's premise, "both values are offered to an Employee", holds only before either is chosen.
2. **FR-08's drop zone gives no feedback when a file is chosen.** The browser's "No file chosen"
   label comes back (`FileDropZone.jsx:87` clears the input on purpose), and the queue's row may be
   off-screen. For item 7.
3. **An uploaded document's title is its file name** unless edited in the queue row. That is
   correct, but it reads less well in a citation.
4. **D-40 was seen live.** The complaint answer's wording differed from all three screened runs. It
   was the same fact, from the same source.
5. **The deployment can be displaced without anyone noticing.**
   - Nothing stops a dev server taking port 8000 once the alpha's window is closed.
   - A Vite dev server forwards to whatever holds 8000.
   - The script now checks `Server: waitress` before step 1.

## The manual checks earlier items left for item 8

Done after the twelve, on the alpha (`docs/stage-5-clause-audit.md`).

| Check | Left by | Result |
|---|---|---|
| A failed `download` link in a real browser | item 2a | The browser saves nothing. It lists a failed download named `download.json`, with its own reason: "Couldn't download – No file" for a 404 (the document deleted in another window), and "Couldn't download – Needs authorisation" for a 401 (signed out in another tab). The page shows no message of its own. The wording suggests a Chromium browser; the browser was not recorded. |
| Following a citation, then pressing Back, in a real browser | item 2 | As expected. |
| Leaving the Upload screen mid-queue | item 5 | The queued uploads still arrived. **Not checked:** whether an upload sent meanwhile shows the in-flight sentence. |

**The corpus after these checks.**

- They deleted a document and uploaded files. Afterwards the database held the same content as at
  the walk's end: all 20 corpus documents Indexed, 6 meetings, 44 chunks, and 23 stored files.
- So the screened questions still hold.
- Which files the checks used cannot be reconstructed, because deletions are not audit-logged.

**A finding from the first check:** a failed download is reported only by the browser, under a
generic name. That could be addressed after the gate (D-75's route, D-62's front-end list).

## What the walk did not show

- **The 60-minute idle expiry** (FR-04) was stated, not waited out.
- **FR-03's lockout,** which is outside the gate. Three failures were reached, and five were never
  attempted.
- **A follow-up that only makes sense with the earlier turn** (FR-13). The screen found it failing in
  7 of the 9 frozen threads, so the walk avoided it on purpose.
- **Whether a screen recording was made** (D-35) is not recorded here.

## What the alpha holds now

`kmp_demo_20261101` keeps everything the walk did:

- the Employee account `demo.employee@example.com`;
- the questions and conversations;
- the T06 meeting;
- two role changes in the audit log.

D21 was deleted. Restoring the snapshot (D-88) resets all of this. Do it only before a new set of
demonstration threads is built.

## Dated notes

These correct the record without editing it.

### 2 November 2026: the FR-13 PASS is qualified (D-91)

- **What still stands.** The walk showed FR-13's thread, its reopening, and the second turn's
  scope differing by role, and those passed as recorded.
- **What is partial.** FR-13 as a requirement is partial at the gate. A follow-up that needs the
  earlier turn did not resolve in the 1 November screen's clean cases, and the measured reason is
  step 5's.
- **The scope re-evaluation is evidenced by test** (`test_fr11_scoping.py:608` and `:633`), not by
  two sessions in two roles.

### 2 November 2026: corrected wording

- **"The same way on all three runs" was wrong,** for the screen's follow-ups as this record and the
  script repeated it. t04's follow-up replies varied from trial to trial, as did t02's and t09's.
  D-91 gives the rescored counts.
- **"This is the 4B model's behaviour" is withdrawn.** The model was never separated from the
  prompt.

### 2 November 2026: an FR-02 clause was left out (D-25)

- **What was left out.** The walk left out the lockout: five failures lock an account for 15
  minutes, a locked account gets a 403, and the screen shows a distinct message. The script called
  it FR-03; it is FR-02's.
- **Where it is shown instead.** In step 3's extra, recorded walk, with a throwaway account. That
  walk will be noted here.

### 2 November 2026: the D-35 screen recording

**No recording of the 1 November walk was made.** D-35's insurance does not exist yet. Before
anything is re-indexed or the alpha is redeployed, the user records a walk on the alpha (step 7's
precondition).

### 3 November 2026: the lockout walk, step 3 (D-25, D-26): PASS

FR-02's lockout, walked live, as the 2 November note above said it would be.

- **The alpha:** the same deployment, commit `8598d19`, database `kmp_demo_20261101`, Waitress at
  24 threads, `DEBUG` off. The server was not running, and was restarted at 17:21:18 local from
  `start-alpha.ps1`; the restart is a line in `Documents\KMP-alpha-deployments.txt`. FLM v0.9.39,
  with `check_flm.py` passing. Not a measured run.
- **The account:** `lockout.walk@example.com`, "Lockout Walk", an Employee, registered through
  FR-01 at 06:33:06. Its password was a throwaway, shown to the user once and recorded nowhere.
  No other account was used.

| Step | On screen | On the server |
|---|---|---|
| 1. A wrong password, five times | refused | the fifth set `locked_until` to 06:48:23, so the lock began at 06:33:23 (a lock is never extended, `apps/api/views.py:314`) |
| 2. Two more attempts during the lock, one of them the right password | the right password: "This account is temporarily locked after too many failed sign-in attempts. Please try again later." | `failed_attempts` 7: attempts during a lock are counted (D-26), and `last_login` still empty |
| 3. The right password, after the lock expired | the Employee dashboard, "Signed in as Lockout Walk" | `last_login` 06:49:06, 43 seconds after expiry; `failed_attempts` 0; `locked_until` cleared |

- **The demonstration accounts were never locked.** After the walk, `corpus.admin@example.com`,
  `demo.employee@example.com` and `lockout.walk@example.com` all have no failures and no lock.
  `corpus.employee@example.com` has one counted failure, with no lock; this walk did not use it,
  and nothing records where the failure came from.
- **The account stays** in `kmp_demo_20261101`, as the walk's Employee does. Restoring the snapshot
  (D-88) removes it.
- **The script's expectation was wrong, and the server was right.** The 2 November amendment
  to `docs/demonstration-script.md` said the fifth wrong password, and every attempt after it,
  shows the locked-account message. It does not: a wrong password always gets the ordinary 401,
  locked or not, so a lock is never confirmed to someone who only knows the address. Only the
  right password shows the locked message, and only for the first five attempts during a lock
  (D-26's ceiling). The script is corrected.

### 3 November 2026: FR-04's confirmation does not appear

- **What happened.** At the end of step 3's walk, Log out returned to the plain sign-in form, with
  no "You've been logged out" confirmation.
- **What FR-04 asks for:** "On activation, user is immediately redirected to the Login page with a
  brief confirmation 'You've been logged out'." The redirect happens. The confirmation does not.
- **How it was found.** Step 6 found it in the front-end suite: the test asserting it fails against
  `main`, so it was left out and reported (PR #44,
  `docs/stage-5-front-end-clauses.md`, defect 1). This walk confirms it in a browser, against the
  alpha's build.
- **The cause, as step 6 traced it.** Logout clears the user first. The sign-in guard then redirects
  to `/login` itself, and that redirect replaces the logout's, which carries the confirmation.
- **What it changes here.** The FR-04 PASS above stands for what it recorded: the redirect, the
  session gone on the server, and Back refused. The 1 November walk never looked for the
  confirmation. FR-04 is partial until the fix lands, and the fix is the user's decision.

### 3 November 2026: FR-04's confirmation is fixed on `main`, not on the alpha (D-97)

- **What changed.** The user decided to fix the confirmation before step 5, in its own pull
  request. PR #46 merged it, so `main` is now at `2f65a8e`. The session-expired notice, and the
  return to the page the user was sent from, were the same race, and are fixed with it.
- **The evidence is the front-end suite.** `frontend/tests/authNotices.test.jsx` asserts the
  confirmation for both roles. It failed on the earlier `main` in 10 runs out of 10, and passes with
  the fix.
- **The alpha still has the defect.** It runs `8598d19`, which predates the fix, and no browser has
  shown the confirmation yet. Redeploying the alpha waits on the D-35 recording, which is step 7's
  precondition. The first walk on a redeployed alpha should look for the confirmation.

### 6 November 2026: the D-35 recording, partial and accepted (D-98)

- **The recording:** `C:\Users\mozza\Videos\2026-11-06 16-45-32.mp4`, on the laptop, outside every
  checkout, and never committed.
  - 11 minutes 34 seconds, from 16:45:32 to 16:57:06 local; 259 MB.
  - 3840×2400 (the whole screen) at 30 fps, 3,000 kbps video and 128 kbps audio, recorded with OBS
    Studio 33.0.0's Display Capture.
  - SHA-256 `39800f6d869661966b465c109087b2b0bb3e142e7160423541e662d0519a23b7`.
- **The alpha:** `8598d19`, on `kmp_demo_20261101`. Just before the take, it was reset to item
  6's snapshot (D-88's restore, with `corpus.admin`'s password carried over), and `check_flm.py`
  passed.
- **What it shows,** by the server's own timestamps:
  - FR-01: `demo.employee` registered at 16:46:35.
  - FR-05: two role changes, at 16:47:36 and 16:47:41.
  - FR-08: D21 uploaded. It answered the bike-cage question at 16:54:07.
  - FR-09: T06 ingested at 16:51:58.
  - FR-11: Atlas, refused for the Employee and answered for the Administrator, at 16:52.
  - FR-12: the bike-cage and customer-satisfaction answers.
  - FR-13: the second turn scoped by role, at 16:55:34 and 16:55:47. The Employee's second turn
    ended in `no_statement_verified`, not `no_relevant_passage`. It was still a no-answer and not
    a leak, but it took the other path from the identical question at 16:52 (D-40, open).
  - FR-02, FR-04 and FR-06 leave no server trace, so the file itself is the evidence for them.
- **What it does not show:**
  - **The walk went on, unrecorded, until 17:20.** That covers the complaint and single-use cups
    questions, FR-11's penetration-test refusal, D21's deletion with the bike cage refused for
    both roles afterwards, and presumably FR-14 and FR-15.
  - **One question was reworded,** "What was the customer satisfaction last quarter?", which D-40
    counts as unscreened.
  - **No lockout account was made,** so FR-02 step 4 was skipped or described.
- **The takes before it are not evidence.** Game Bar recorded one window only. Then OBS recorded
  only the top-left quarter of the screen, because its canvas was 1920×1080. A standby at 13:59 and
  a restart at 15:59 also took Docker, the database and FLM down. The alpha was reset to the
  snapshot before each take, at the user's request, and each reset is a line in
  `Documents\KMP-alpha-deployments.txt`.
- **The user accepted it as partial.** The platform was demonstrated live in class, so a
  demonstration submission is not required (D-98).

### 12 November 2026: FR-13 since the walk (D-91, D-112)

- **"The measured reason is step 5's"** (the note of 2 November). Step 5 ran on 3 November on the
  alpha's code. With history, 1 of 9 frozen follow-ups matched, and spelled out 3 of 9 (D-91's
  note). D-112 accepts the clause as partial for NIT3003 on the FLM build.
- **The walk and its qualification stay true of the alpha,** which runs FLM at `8598d19`.
- **On the default build, `anthropic` (D-122),** 9 of 9 matched on each of three draws (D-112's
  note of 12 November). The auditor reads that with Stage 5 item 10.
- **The re-scoping tests have moved.** The note of 2 November cites `test_fr11_scoping.py:608` and
  `:633`. On `main` at `a668a08` they begin at `:610` and `:635`.
