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
