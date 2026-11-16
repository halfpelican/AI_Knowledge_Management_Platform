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
>
> **Amended 13 November 2026,** after FR-03 was built (D-130). The changes:
>
> - a new section, [FR-03 · Account lockout interface](#fr-03--account-lockout-interface-nit3004-windows-a-and-b),
>   after FR-02. It shows the remaining-attempts warning, the countdown and an Administrator's
>   release. FR-03 is NIT3004 and not one of the twelve;
> - FR-02 step 4 says what a build that includes D-130 shows instead of its 3 November text.
>
> **None of this is on either alpha:** neither the FLM alpha at `8598d19` nor, since D-131, the
> Anthropic alpha at `6e1efd1`. It holds only on a build that includes D-130.
>
> **Amended 14 November 2026,** after the alpha moved to Anthropic (D-131). This script was
> written for the FLM alpha and walked on it: `8598d19`, on `kmp_demo_20261101`. Every line below
> that names them describes that alpha, which is kept. Since 13 November 2026 the alpha runs
> `6e1efd1` on the anthropic provider, on a new database, `kmp_alpha_20261113`. So, before a walk
> on it:
>
> - **Screen the walk's questions again.** They were screened on EmbeddingGemma's vectors only
>   (`corpus/demo/screening-2026-11-01.json`, D-40), and Voyage's scores differ.
> - **Check, rather than assume, the steps that waited on a redeploy,** such as FR-04's logged-out
>   confirmation. `6e1efd1` has D-97's fix, but nobody has walked it on the new alpha.
> - **The FR-10 lines describe `8598d19`, which had no classification.** On `6e1efd1` each document
>   is classified at upload. On the new database FR-10 holds 15 provisional tags, which FR-15's
>   views leave out until someone confirms them (D-105, D-131).
>
> **Amended 15 November 2026,** for the Anthropic alpha, after its questions were screened again
> (D-40, D-131). The script now describes the alpha that serves: `6e1efd1` on the anthropic
> provider, on `kmp_alpha_20261113`. The 14 November note's three conditions:
>
> - **The questions are screened again,** on a copy of the alpha's database with its own code
>   (`corpus/demo/screening-2026-11-15-anthropic/`). Every question had its expected outcome and
>   source on all three runs. Three rows fail the band clause, and whether to accept them or to
>   replace those questions is open.
> - **The steps that waited on a redeploy are rewritten for `6e1efd1`,** FR-04's logged-out notice
>   among them. They are read from the code and its tests, and nobody has walked them here yet.
> - **The FR-10 lines describe classification at upload,** in FR-08 and FR-15. FR-16's summary and
>   the disabled recording option (FR-09) and FR-19's gap panel (FR-14) are named where they
>   appear. All are NIT3004, not among the twelve.
>
> Also changed:
>
> - the alpha, the checks on the day, the Administrator's password, and the paths under
>   `C:\kmp-demo\2026-11-13`;
> - FR-06's count is 43 of 43, and its audit trail names the reviews made since;
> - FR-15 step 1 said the repository was filtered by type and date. Type and date are sorts, on
>   either alpha (D-72);
> - the numbers and answers worth having ready, which now give `anthropic`'s figures first, with
>   FLM's beside them: the thirty questions, NFR-08, the 503 that was FLM's;
> - the deviations' lines about the alpha, and "Afterwards".
>
> What describes the FLM alpha stays where it is history, and says so: the 1 November screen, and
> FR-13's FLM measurements. **Nobody has walked this script on the Anthropic alpha yet.**
>
> **Amended 14 November 2026 on FR-20's branch, and merged after the amendment above,** for
> FR-20 (D-132). The changes:
>
> - a walk of the knowledge map is added after FR-15's. FR-20 is a COULD requirement and is not one
>   of the twelve;
> - **that walk was written from the build's tests and its contract and has not been walked on the
>   alpha.** The alpha must first be redeployed and migrated, and `GET /api/roles` checked
>   (`docs/alpha-deployment.md`, step 11).
>
> **Amended 16 November 2026,** for the knowledge map's second view (D-138). The changes:
>
> - FR-20's walk gains steps 8 to 12, the view of claims and the passages they cite;
> - **those steps are written from the build's tests and its contract and have not been
>   walked on the alpha,** as steps 1 to 7 have not.

Stage 5 item 9. This walks all twelve MUST-HAVE requirements, in the gate's order, on the
deployed alpha (`docs/alpha-deployment.md`, D-64, D-88, D-131). It is also item 8's live
end-to-end pass: both roles, real files, the real corpus.

- **The alpha:** `http://127.0.0.1:8000`, served by Waitress from the `KMP_Prototype-alpha`
  worktree at `6e1efd1`, on the anthropic provider: Claude Haiku 5.5, and Voyage `voyage-4` at
  1024. Its database is `kmp_alpha_20261113`. It was built on 13 November from Objective 02's
  corpus through the alpha's own server, not restored from a snapshot (D-131).
- **Every question below was screened again for this alpha on 15 November** (D-40). The screen
  ran on a copy of its database with its own code: each question's scores, and three runs of each
  through the shipped pipeline. [The screen](#the-d-40-screen) has the figures, including three
  rows that fail its band clause, and `corpus/demo/screening-2026-11-15-anthropic/` has every
  number.
- **The FLM alpha,** `8598d19` on `kmp_demo_20261101`, is kept and is no longer served. The
  1 November walk ran on it, and `docs/stage-5-item-8-walk.md` records it.

## Before the walk

**The conditions D-40 sets, not only its decision:**

1. **Do not re-index, reprocess or delete anything** from the first question until the last one.
   - A re-index or a reprocess embeds the chunks again. Voyage is not bit-for-bit repeatable: the
     same question has scored up to 0.0012 apart on two passes (D-126's note of 12 November).
   - A delete removes candidates.
   - Either can move a passage across `voyage-4`'s threshold, 0.2687, or its partial-match floor,
     0.2468 (D-120), and change an answer that was screened.
   - The walk's only delete is the optional last step, after every question has been asked.
   - **T06's upload adds candidates of its own.** FR-16 summarises the stored transcript in a
     background thread, and indexes the summary as the meeting's passages (D-125). Leave a minute
     between FR-09 and FR-12.5, as the walk's order does.
   - **Do not press Generate or Regenerate Summary during the walk.** A run replaces the meeting's
     summary passages (D-125). The hourly summary retry runs a failed summary again, so a T06
     summary that failed at FR-09 can appear in the middle of the walk.
2. **Ask only the screened questions, worded exactly as written here.** A rephrased question is an
   unscreened question.
3. **The same question can still answer differently on two runs** (D-40, open). If it happens, say
   so. Both outcomes are honest, and the no-answer is a legitimate reply. On `anthropic` both halves
   can vary: Voyage's scores, as above, and Claude, which is called with no temperature (D-115).

**The screen recording (D-35, D-98).** Start recording the screen before step 1, and keep it.

- **Use OBS Studio, with a Display Capture source,** so that both browser windows land in one
  file. Xbox Game Bar (`Win+Alt+R`) records only the window that had focus when it started, so
  every switch between window A and window B is lost.
- **Set OBS's Base (Canvas) Resolution to the screen's own,** and Fit the capture to it (Ctrl+F).
  With a 1920×1080 canvas on the laptop's 3840×2400 screen, only the top-left quarter is
  recorded.
- **Keep the file under 2 GB,** for Dropbox. 3,000 kbps at 30 fps comes to about 23 MB a minute.
- **Use a crash-safe format** (OBS's Hybrid MP4), and keep the laptop plugged in and awake. A
  standby or a restart takes Docker and the database down with it, and a restart stops the
  alpha's server (D-98). FLM takes no part (`docs/alpha-deployment.md`, step 2).

- **It is the demonstration's insurance** if the network, Anthropic or Voyage fails on the day.
  Every question, upload and summary calls one or both. When those calls fail, including at a
  rate limit or once the month's credit has run out, the ask answers NFR-19's 503 and the Ask
  screen says the AI service is unavailable (D-113, D-118). It must exist before any re-index.
- **If this walk is the recording,** the walk itself must not re-index.

**The checks, on the day:**

- **Docker Desktop is running, with the database up** (`docker compose up -d`, as
  `docs/alpha-deployment.md`'s "Before you start" says). `serve-alpha.ps1` reads the database's
  name from the settings without connecting to it, so a database that is down does not stop it
  from starting.
- **The provider answers.** There is nothing to start (step 2 of `docs/alpha-deployment.md`). From
  the alpha's worktree, with its venv, `manage.py check --deploy` reports exactly the four HTTPS
  warnings and no `ai.W001` (step 4). Its probe lists Anthropic's models and embeds one string
  with Voyage. It makes no generation call, so it cannot show how much of the month's credit is
  left.
- **The server runs from `C:\kmp-demo\2026-11-13\serve-alpha.ps1`, in its own window.** It prints
  `Django will connect to: kmp_alpha_20261113`, and refuses to start on any other name. Unlike the
  FLM alpha's `start-alpha.ps1`, it prints no commit. Waitress writes to
  `C:\kmp-demo\2026-11-13\logs\waitress.log`, whose last line then reads
  `Serving on http://127.0.0.1:8000`.
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
| **A**, a normal window | the Administrator | `corpus.admin@example.com`, with the password set before the walk (below) |
| **B**, a private window | the Employee | registered in FR-01 below. Choose the password at the time and write it nowhere. |

**Set the Administrator's password before the walk.** `kmp_alpha_20261113`'s two accounts were made
with passwords generated in memory and never shown or stored, so nobody can sign in as either until
one is set (D-131). From the alpha's worktree, with its venv and `.env`, run
`manage.py changepassword corpus.admin@example.com` (`docs/alpha-deployment.md`, "Building the
database (once)").

**Files, from any checkout at or after this commit:**

| For | File |
|---|---|
| FR-08, the upload | `corpus/demo/D21_bicycle_end_of_trip_facilities.docx` |
| FR-09, the transcript | `corpus/demo/T06_sustainability_working_group.txt` |
| FR-08, refused by signature | `corpus/objective-02/invalid/I01_annual_report_2026.pdf`, a PNG named `.pdf` |
| FR-08, refused as a duplicate | `corpus/objective-02/invalid/B01_duplicate_of_D03_renamed.pdf`, D03's bytes |
| FR-08, too large (optional) | made on the day, outside every checkout, as shown below |

```powershell
$f = [IO.File]::Create('C:\kmp-demo\2026-11-13\oversized.pdf'); $f.SetLength(52428801); $f.Close()
```

## The walk

Each step names the clause it shows. Where the interface words a message, the message is quoted.
"Expected" is one of two things:

- **for a question,** what the 15 November screen showed on a copy of this alpha's database;
- **for a screen,** what the alpha's code at `6e1efd1` shows, read from the code, its tests and the
  screen's route replies. FR-04's notice, FR-09's summary panels, FR-14's gap panel and FR-15's
  Classification section are among these. Nobody has walked this alpha yet, so check each one.

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
     message. That is **FR-02's**, not FR-03's (D-25). FR-03 adds the warning, the countdown, the
     administrator release and the `LoginAttempts` record, and makes the policy a `.env` setting
     (D-130). **Never lock `corpus.admin@example.com` or the demonstration accounts.** Show it with
     its own account, in step 4.
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
   - **On a build that includes D-130, the screen says more** (13 November 2026). The server's
     answers are the same, a 401 or a 403. Since FR-03:
     - the third and fourth failures add the remaining-attempts warning;
     - the fifth disables Sign in and starts a countdown;
     - the right password's message names an administrator.

     The FR-03 section below walks it. The walk can replace this step: it uses the same throwaway
     account and the same server answers.

### FR-03 · Account lockout interface (NIT3004, windows A and B)

**Only on a build that includes D-130.** FR-03 is a SHOULD for NIT3004, not one of the twelve. The
lock itself is FR-02's, above. FR-03 adds:

- the warning;
- the countdown;
- the Administrator's release;
- the `LoginAttempts` record.

Use a throwaway account registered through FR-01, with a password used nowhere else.

- **Never lock `corpus.admin@example.com`,** which window A is signed in with.
- **Window A could not release that lock.** FR-03 forbids an Administrator from releasing their own
  lock, so only another Administrator or the 15-minute wait would end it.

1. **In window B, sign in to the throwaway account with a wrong password, four times.**
   - **Expected:** "Invalid email or password." each time.
   - After the third, the subtle line "2 attempts remaining before temporary lockout" appears.
   - After the fourth, "1 attempt remaining before temporary lockout" appears.
   - The first two show the banner only (D-130 decision 2).
2. **A fifth wrong password.**
   - **Expected:** Sign in is disabled.
   - "Try again in 15:00" counts down beside it.
   - The banner adds: "Too many failed sign-in attempts. If this address has an account, it may be
     locked for up to 15 minutes, and an administrator can unlock it sooner."
3. **Say why the page words it that way, or show it with an address that has no account.**
   - The page counts its own attempts, and the server's 401 is the same whether or not the address
     is registered.
   - So the warning and the countdown appear identically for an address nobody registered.
   - A failed sign-in never confirms an account or a lock (D-130 decision 1, UC-02 E1).
4. **Reload the page, and sign in with the right password.**
   - **Expected:** "This account is temporarily locked after too many failed sign-in attempts. Try
     again when the timer ends, or ask an administrator to unlock it."
   - The countdown runs from the time the lock really has left (the 403's `retry_after`). Only the
     right password gets this message.
   - **Stop at one attempt.** Every attempt during the lock is counted, and past ten in all even the
     right password gets the 401 (D-26).
5. **In window A, open `Role management`.**
   - **Expected:** the throwaway account's Account column reads "Locked until" the time, with an
     **Unlock** button. Every other row reads "Active".
6. **Press Unlock.**
   - **Expected:** a dialog, "Unlock <name>'s account?". It gives when the lock began, from which
     address, and until when. It says the password is not changed, and asks you to check that the
     request really comes from that person.
   - **Say it:** on this loopback alpha every source address is `127.0.0.1`. The "distributed
     attempt" evidence FR-03 promises cannot be shown here (D-130, security finding L4).
7. **Press `Unlock account`.**
   - **Expected:** "<name>'s account is unlocked.", and the row reads "Active".
   - The release is recorded in `LoginAttempts` with the Administrator, the account and the time,
     beside the lockout row.
8. **In window B, reload the page, then sign in with the right password.**
   - **Reload first.** The release reaches the server, not a sign-in page that is already open. That
     page keeps its own countdown, and says "If an administrator has unlocked the account, reload
     this page to sign in." (the pre-PR security review, finding 1).
   - **Expected:** the dashboard, without waiting out the 15 minutes.
9. **Say it, don't show it:** an Administrator's own locked row has no Unlock button.
   - **Where the list holds another Administrator,** that row says "Another administrator can unlock
     your account."
   - **Where it holds none,** it says "No other administrator can unlock your account. It unlocks at
     <time>." Nobody can release that lock (D-130's residue). The corpus scripts create only one
     Administrator, `corpus.admin@example.com`. Whether the alpha's database holds another was not
     checked.
   - **The server's side:** it refuses a release of one's own account with a 403 whether or not it
     is locked, and refuses an Employee before it looks the account up. Both are pytest's (D-130).

### FR-04 · Logout and session management (window B)

1. **Log out** from the navigation.
   - **Expected:** the sign-in page, with the notice "Logged out" and "You’ve been logged out."
     (D-97).
   - **The fix is in the alpha's build, `6e1efd1`,** and the front-end suite tests it
     (`authNotices.test.jsx`, `logout.test.jsx`). Nobody has walked it on this alpha yet, so check
     that it appears, and say so if it does not. The FLM alpha at `8598d19` does not show it
     (`docs/stage-5-item-8-walk.md`, 3 November notes).
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
   - Each change is written to the audit log, `C:\kmp-demo\2026-11-13\logs\audit.log`. The file
     is created by the first change, so it is not there before this step. Open it if asked.
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
4. **Say it:** every protected route is tested from both roles: 43 of 43 protected endpoints on
   the alpha's build, against 23 on `8598d19`. The matrix is generated from the routes
   (`apps/api/tests/dual_role_matrix.py`). D-131's full run reports 43 of 43 on routes and views
   identical to `6e1efd1`'s.
   - **The audit trail D-57 to D-61** found no route across the permission boundary on the six
     routes it walked: `/api/ask`, `/api/search`, `/api/conversations*`, `/api/documents/{id}`,
     `/api/meetings/{id}` and reprocess.
   - **Most features added since had security reviews of their own,** each recorded in its entry:
     - FR-10's tag corrections (the review of `84b5771`, D-105's note of 10 November, night). It
       found that an Employee could learn whether Administrator-only material carried a tag, and
       that was fixed there. No review is recorded for FR-10's `classify` and `classification`
       routes;
     - FR-19's three routes and the dashboard's gap panel (D-107's note of 10 November). An
       Employee reaches none of them;
     - recording transcription's two (D-123, 11 November). Its finding on request bodies is D-124;
     - FR-16's summary and action-item routes (D-125's note of 13 November). It found no path to
       an Administrator-only meeting's summary, its action items or its existence.
   - **The four FR-14 and FR-15 routes** (`GET /api/dashboard`, `GET /api/documents/browse`,
     `GET /api/documents/{id}/download` and `DELETE /api/documents/{id}`) have leakage tests. No
     audit has walked them, apart from FR-19's review of the dashboard's gap panel, and none is
     recorded for D-99's meeting delete. Item 11, the final security pass over the alpha, has not
     run: the records name only its early pass (D-114's note).

### FR-08 · Document upload, extraction and indexing (window B)

1. **Open `Upload` and choose `D21_bicycle_end_of_trip_facilities.docx`.**
   - **The drop zone says what was added:** "Added D21_bicycle_end_of_trip_facilities.docx to the
     queue below.", inside the zone, and the row appears under **Files**. Usability findings 1
     and 2 were closed in Stage 5 item 7 (`docs/usability-findings.md`,
     `frontend/tests/dropZone.test.jsx`).
   - Department: `Operations`.
   - Visible to: an Employee is not offered a choice. The page shows a note, because the only
     scope an Employee may upload to is both roles (D-29). An Administrator would see a select.
   - Upload.
   - **Expected:** it ends **Indexed**. Text was extracted from the DOCX, chunked and embedded in
     the same request, and the record and its vectors commit together.
   - **The document's title is the file name,** `D21_bicycle_end_of_trip_facilities`, unless it is
     edited in the queue row before uploading. The title does not move the screen's scores:
     `voyage-4` embeds a passage without its title (`apps/ai/prefixes.py`).
   - **FR-10 classifies it in the same request** (D-104, D-105; NIT3004, not one of the twelve),
     between extraction and chunking, in a savepoint of its own. A failure there leaves it
     unclassified and still Indexed (invariant 8). The upload page does not show the result.
     D21's page does (FR-15 step 5).
   - **The department typed here stays** (D-105's note of 10 November). FR-10 fills only a blank
     one. A suggestion that is not one of the known departments is discarded. A known one below
     0.72, or a known one that differs, is held for a person to accept. A matching one at or above
     0.72 is shown as the person's. On the 15 November screen's upload, FR-10 suggested
     `Operations` at 0.7, and it was held.
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
   - Meeting title: `Sustainability Working Group`.
   - Meeting date: `2026-10-29`.
   - How are you supplying the transcript?: `Upload a transcript file`. Then choose
     `T06_sustainability_working_group.txt`. The zone says "Chosen:
     T06_sustainability_working_group.txt" (usability finding 2).
   - **`Transcribe a meeting recording` is off on this alpha** (D-123; NIT3004). Chosen, it says
     "Transcription is not enabled here" and offers no picker. Recording transcription stays off
     unless `.env` sets `TRANSCRIPTION_PROVIDER=flm` (`docs/alpha-deployment.md` steps 2 and 4).
     Leave it unchosen.
   - Attendees: optional, and picked from existing accounts (FR-20's participation record).
     Choose a person under `Add an attendee` and press `Add`. Each is listed with its own
     `Remove`, and no modifier keys are needed (usability finding 5). Leave them empty, as the
     screen did, or add `Demo Employee`. They do not change the transcript's chunks or its
     summary's, and they never grant access (invariant 3: meetings are scoped by role, never by
     attendance). There is nowhere to type a name: the route takes account ids.
   - Visible to: an Employee is not offered a choice. The page shows "Content you add is visible
     to everyone in the organisation." (D-29).
   - Press `Add transcript`.
   - **Expected:** "Sustainability Working Group was stored and indexed.", and the list shows it
     **Indexed**.
   - **FR-16 then writes the meeting's summary in the background** (D-125; NIT3004, not one of
     the twelve). The server starts the run once the ingestion has committed, in a thread of its
     own. The hourly task only retries a summary that failed, and on this alpha it has found its
     queue empty on every run (`C:\kmp-demo\2026-11-13\meeting-summaries.log`). The corpus's five
     summaries took 2.6 to 4.1 s each when this database was built.
2. **Open the meeting** (`View the transcript`).
   - **Expected:** its details, then FR-16's **Summary** and **Action Items**, then the
     transcript.
     - The summary is marked "Suggested by AI", with "Model: claude-haiku-5-5" and the date it
       was generated. Each sentence, decision and highlight has a reference that opens its
       transcript passage.
     - While the run is still going, the panel says "The summary is being generated. It will
       appear here when it is ready."
     - Each action item's owner reads "Unassigned", with the name the transcript gave beside it,
       such as "Named in the meeting: “Daniel”". An owner is matched only among the meeting's
       recorded attendees who can read it (D-125's note of 13 November), and none of the walk's
       attendees is named in T06.
   - **Wait for the summary before FR-12.5.** The screen asked the cups question with T06's
     summary indexed, and the summary was its top candidate, at 0.6380. The transcript's best
     was 0.5895.
   - **The walk's summary is a new generation,** so its wording, and its score for that
     question, can differ from the screen's.
   - **If Claude cannot be reached when T06 is stored,** the run fails and is queued, and the panel
     reads "The summary is not available yet. The transcript is stored and searchable, and the
     summary will be tried again automatically." The hourly task retries it. FR-12.5 would then be
     asked without the summary, a state the screen did not score.
   - **Do not press `Regenerate Summary`.** A new run replaces the summary's indexed passage,
     the kind of change D-40's first condition rules out.

The 15 November screen ingested both files as steps FR-08.1 and FR-09.1 do, the same bytes through
the same routes, as an Employee, on a copy of this alpha's database with the alpha's code
(`corpus/demo/screening-2026-11-15-anthropic/`). T06's summary was written before it scored, so
every question below was screened with D21, T06 and T06's summary in place.

### FR-11 · Permission-aware retrieval scoping (both windows)

1. **Window B, `Ask`:** "Who is the sponsor of Project Atlas?"
   - **Expected:** "This question cannot be answered from the available knowledge base."
   - Nothing above the threshold is readable by an Employee, so generation is not called (path A).
   - No partial match is offered. The Employee's best passage scored 0.1517 in the screen, below
     `voyage-4`'s floor of 0.2468 (D-120).
   - The answer comes from D09, which is Administrator-only. That document reached neither the
     ranking nor the model, and the reply does not reveal that it exists.
2. **Window A, the same question.**
   - **Expected:** answered, citing **Project Atlas Kickoff Brief** (D09). The wording varied from
     run to run in the screen, and the source did not.
3. **Existence is not disclosed.**
   - In window A, open D09 from `Documents`, and copy its address (`/documents/<id>`).
   - Open that address in window B.
   - **Expected:** the same "not found" as an address that never existed.
4. **Window B, `Documents`:** D09, D15 and D16 are not listed. Window A lists them.

### FR-12 · Knowledge search and answer generation, with verified citations (window B)

1. **Search,** with the search field in the page header, or at `/search`: `asset tag`.
   - **Expected:** one result, **Asset Inventory Melbourne Office** (D14), with a snippet showing
     the phrase. Checked on 15 November on the copy of this alpha's database, with FR-16's
     summaries present. The keyword search does not use the AI provider.
   - **Not the repository's "filter by title" field.** That is FR-15's, and it matches titles only.
     FR-12's search reads the passages, and it writes a `SearchLog` row.
2. **`Ask`:** "How quickly do we have to acknowledge a customer complaint?"
   - **Expected:** answered, with a numbered citation to **Customer Complaints Procedure** (D06).
   - Open the citation: it leads to the cited passage's document.
   - Every statement carries a citation that was checked against the passages actually supplied
     (invariant 5).
   - **This question fails D-40's band clause** ([the screen](#the-d-40-screen)): weak passages of
     the Records Management Handbook sit within 0.005 of the threshold. It got the same statement
     and citation on every run.
3. **`Ask`:** "How much did the latest penetration test cost?"
   - **Expected:** the fixed no-answer, with no generation (path A), and no partial match. Nothing
     in the corpus answers it, and no statement without a citation is ever shown (invariant 6).
4. **`Ask`:** "How many bicycles can the secure bike cage hold?"
   - **Expected:** answered, **40**, citing the guide uploaded in FR-08
     (`D21_bicycle_end_of_trip_facilities`). Upload to answer, end to end.
5. **`Ask`:** "When will single-use cups be removed from the office kitchens?"
   - **Expected:** answered, **1 March 2027**, citing the meeting ingested in FR-09.
   - **The citation can be to the meeting's AI summary.** FR-16 summarises T06 when it is stored,
     and indexes the summary as a passage of the meeting (D-125). In the screen it ranked first,
     above the transcript. Claude writes a new summary at each ingestion, so the walk's will not be
     word for word the screen's.
   - **This question fails D-40's band clause** ([the screen](#the-d-40-screen)): a weak passage
     sits within 0.005 of the threshold. It was answered and cited the same way on every run.

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
     - **Expected:** the fixed no-answer, with the **Customer Success Retrospective** offered as a
       partial match.
     - This is path B. The joined questions admit two of the retrospective's passages, so Claude is
       asked, and no statement survives. The partial match is a meeting the Employee may read, and
       nothing in the reply names D09 or the sponsor.
3. **Window A, the same two turns.**
   - **Expected:** the first is answered as before. The second is answered: "The sponsor of Project
     Atlas is the chief operating officer", citing **Project Atlas Kickoff Brief** (D09).
   - **The first turn, asked as the Administrator, fails D-40's band clause**
     ([the screen](#the-d-40-screen)): the Security Incident Debrief's summary sits within 0.005 of
     the threshold. It was answered and cited the same way on every run.
   - **What this shows:** the same history, in two roles, and the second turn's scope differs
     by role.
   - **That the scope is re-evaluated on every turn is evidenced by test, not by this walk.**
     Two sessions holding two roles cannot show a role changing mid-thread.
     `apps/api/tests/test_fr11_scoping.py:610` changes the role between turns, from Employee to
     Administrator, and the next turn takes the new scope. `:635` does the reverse.
4. **Reopen a thread from `Your conversations`, or from the dashboard's recent questions** (D-77).
   - **Expected:** the turns come back in order.
5. **Do not ask a follow-up that needs the earlier turn to make sense,** such as "Is there a limit
   on how much of it I can save up?". None was screened on this alpha.
   - **On this alpha's provider, `anthropic`, such follow-ups resolved in the measurement.** With
     history, 9 of 9 frozen follow-ups matched on each of three draws (D-112's note of
     12 November). That was measured on another database, and it is not yet the auditor's
     verdict: FR-13 stays INCOMPLETE until Stage 5 item 10 reads it.
   - **On the FLM alpha they did not.** In the 1 November screen's three clean cases (t01, t04,
     and t06 as the Administrator), such a follow-up was not correct on any trial (D-91). With
     history, 1 of 9 frozen follow-ups matched on the FLM alpha's code (3 November), and 2, 3 and
     2 of 9 on `main` (8 and 9 November). D-112 accepts the clause as partial for NIT3003 on the FLM
     build, a recorded deviation.
     [What the screen found](#what-the-screen-found-that-the-walk-avoids) has the details.
   - If an assessor asks for one, say so plainly, and say which build is running.

### FR-14 · Dashboard overview (both windows)

1. **Window B, `Dashboard`.**
   - **Expected:** recent documents (D21 at the top), recent meetings (the sustainability group's),
     indexed totals, and **Your recent questions**, each opening its conversation.
2. **Window A, `Dashboard`.**
   - **Expected:** larger totals.
   - The Employee's totals leave out Administrator-only items, and nothing on the Employee's
     dashboard reveals that they exist.
   - **The Administrator's dashboard also has FR-19's `Knowledge gaps` panel** (D-107; NIT3004,
     not one of the twelve). The Employee's has none: the server sends it only to a role holding
     `review_knowledge_gaps`.
     - **Expected:** `Open entries` 0, and "No open entries to show." Neither cycle on this alpha
       up to 16 November, at 14:42 on 15 November and 09:23 on 16 November, added an entry
       (`C:\kmp-demo\2026-11-13\knowledge-gaps.log`).
     - **Say it, if asked:** the walk's no-answers are considered at the next cycle, daily at
       02:00 (`docs/alpha-deployment.md` step 9), or when an Administrator presses **Run
       aggregation now** on the knowledge-gap page. A question whose best passage over the
       Administrator's scope clears 0.2687 and is one the asker cannot read is left out (D-108,
       D-126), so the Employee's Atlas question (FR-11.1) is not expected there. A rehearsal on
       this alpha would leave its own.

### FR-15 · Document repository and filtered browsing (window B unless stated)

1. **`Documents`:** the repository. Browse it by Department, Project, Process and Topic, each
   value with its count, filter it by title, and sort it by title, type, uploader, upload date or
   status (D-72). Type and date are sorts, not filters. FR-10's document type is shown only on a
   document's page (step 5).
2. **Two filters narrowing** (D-74): topic `people`.
   - **Expected:** D01, D07, D08 and D13.
   - Add process `onboarding`.
   - **Expected:** D08 and D13.
   - **The tags are D-74's, seeded on this alpha's database as on the FLM alpha's:** 14 tags and
     48 links (`corpus/objective-02/runs/2026-11-13-alpha-anthropic/tags/seed.txt`). FR-10's 15
     held suggestions are not counted (D-105). Were all 15 confirmed, steps 2 to 4 would still
     show the same documents.
   - **If D21 is listed too,** FR-10 applied `people` to it at upload, at or above 0.72. Say so.
     The 15 November screen did not record D21's tags.
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
   - **Above the extracted content, FR-10's `Classification` section** (D-104, D-105; NIT3004,
     not one of the twelve). Every AI value is marked as one. The 15 November screen's upload of
     D21 gave:
     - document type `Procedure`, "Suggested by AI, 80% confidence";
     - department `Operations`, "Awaiting your confirmation. The AI suggested Operations, 70%
       confidence." The typed department stays, and the matching suggestion is held below 0.72.

     A new upload is a new classification, so the walk's values can differ. Its tags were not
     recorded. If classification failed at upload, D21 is still Indexed, and the section reads
     "Not classified yet." with Classify now.
   - **The Employee is offered FR-10's Confirm and Edit controls here.** Confirming a held tag
     makes it a tag in the facets and filters, which is why this step comes after steps 2 to 4.
   - **On a build with #102** (D-129), a department has a threshold of its own, 0.30. A
     matching suggestion at 0.7 then reads "Given by a person. The AI’s suggestion matched it,
     70% confidence." The alpha has not been redeployed with it.
6. **Optional, and only now, after every question: window A deletes D21** (D-73).
   - **Expected:** it is gone from both windows' lists.
   - This is the walk's only delete, and nothing is asked after it.

### FR-20 · Knowledge map (NIT3004, both windows)

Not one of the twelve. Written from the build's tests and contract (D-132), and **not yet walked on
the alpha**: the alpha needs the build that holds FR-20, `migrate`, and step 11 of
`docs/alpha-deployment.md`. The names below are the Objective 02 corpus's.

1. **Window B, `Knowledge map`** (the link after `Ask`).
   - **Expected:** a line counting what is shown ("… documents · … meetings · … tags · …
     contributors shown"), a legend, the map in three columns (Contributors, Documents and
     meetings, Tags), a "Selected" panel that says nothing is selected, and under them the table
     view: **Items** and **Relationships**.
   - The legend gives each type its shape and colour beside its word: a document is a square, a
     meeting a circle, a tag a diamond, a contributor a triangle.
   - **Whether a notice says the view is partial depends on the database.** The corpus's manifest
     alone gives a whole map of 34 items for an Employee and 41 for an Administrator, under the
     cap of 50. The demonstration's own uploads, their tags and the stored upload refusals add to
     that. If the map is over 50, the notice reads "The map holds at most 50 items at a time.
     Select an item to see what is connected to it.", which is the cap doing its work.
2. **Select a document,** for example `Employee Leave Policy 2026`.
   - **Expected:** the address gains `focus_type=document` and its `focus_id`. The panel lists its
     **Tags** (`Project: policy refresh`, `Topic: people`) and **Uploaded by**. The map now holds
     the document, those, and the documents that share them.
   - **Expected:** the notice "This view stops 2 steps from the selected item." It shows because
     the items on the edge of the view have connections of their own beyond it.
3. **Select it again:** the node now marked "Selected", or "Open the document" in the panel.
   - **Expected:** the document's own page. The browser's Back returns to the map with the
     selection still made, because the selection is in the address.
4. **Select a tag,** `Topic: people`.
   - **Expected:** the panel lists the documents **carrying this tag**.
   - "Open documents tagged people" opens the repository filtered by that topic: FR-15 step 2's
     list.
5. **Select a contributor,** for example `Demo Employee`.
   - **Expected:** the documents they **uploaded**, and any meeting they **attended**: the
     sustainability group's, if FR-09 step 1 picked them as an attendee.
   - **Expected:** "A contributor has no page of their own, so there is nothing to open." A
     contributor is shown by name only: no address and no role (D-132).
6. **The table view,** by keyboard: "Skip to the table view", then Tab.
   - **Expected:** every column heading is a button. Sort **Items** by "Connections shown", then
     again for the other direction. **Relationships** reads across each row, with the type named
     at each end: "Contributor: Demo Employee", "uploaded", "Document: …"; and "Document: …",
     "is tagged", "Tag: Topic: people".
   - The two tables hold the same items and lines as the map above them (NFR-17).
7. **Scope, in both windows** (invariant 1): "Show the whole map" in each.
   - **Expected:** window A's map holds the Administrator-only documents and the tag
     `Project: atlas`, which only D09 and D15 carry. Window B's holds neither, and its counts are
     smaller.
   - Nothing in window B says that anything is left out, and a tag or a person known only through
     an Administrator-only item is not there at all.
8. **The second view, window B:** "Show claims and passages", the link straight after "Skip to the
   table view" (D-138).
   - **Expected:** the address gains `view=evidence`. A line counts what is shown ("… claims · …
     passages shown"), the legend gives a claim a square and a passage a circle, and the map has
     two columns, Claims and Passages. Under them, **Items** and **Relationships**, the second
     with a "Times admitted" column.
   - **The claims are the statements of the answers given so far on this database:** FR-12's and
     FR-13's steps above, and anything asked before the walk. A line is heavier where the same
     statement was admitted from the same passage more than once.
   - **If it reads "No claims yet …",** no answer on this database can be shown to this role. A
     reprocess or a re-index since the last answer does that: it replaces the passages the
     claims cited.
9. **Select a claim.**
   - **Expected:** the pane is headed "Claim review". It shows the claim's text, "Admitted in …
     answers.", **Supported by** with its passages, **First admitted** and **Last admitted**. A
     claim resting on one passage is tagged "Single source".
   - **Expected:** "A claim has no page of its own, so there is nothing to open." The question
     that was asked, and who asked it, are nowhere on the screen.
10. **Select a passage,** for example one under **Supported by**.
    - **Expected:** its **Source** (the document or the meeting), and **Cited by** with the claims
      that rest on it.
    - Select it again, or "Open the document": the document's own page. The browser's Back returns
      to the view with the selection still made.
11. **Scope, in both windows** (invariant 1): the same view in window A.
    - **Expected:** window A holds claims from the Administrator's own answers that drew on
      Administrator-only passages. Window B holds none of them.
    - **That includes a claim citing a passage both roles read,** when its answer was also
      generated from a passage the Employee cannot read. The statement may carry what that
      passage said, so the Employee is not shown it (D-138, rule 2).
12. **"Show documents, meetings, tags and contributors"** returns to the first view, with nothing
    selected.

**What this walk cannot show, and what does.**

- **The node cap, reliably.** Whether the alpha's map passes 50 items depends on what has been
  uploaded to it (step 1). `apps/api/tests/test_knowledge_map.py` shows the cut and the reason
  the reply gives for it, whatever the database holds.
- **The 403.** Both roles hold `view_knowledge_map`. The same file takes it away from each role
  and asserts the 403.
- **Attendance is not access.** The demonstration's one ingested meeting is visible to both roles.
  The same file records an Employee on an Administrator-only meeting and asserts that their map
  holds neither the meeting nor the line.
- **A screen reader, and a narrow window.** NFR-17's NVDA or VoiceOver run and the 320 px reflow
  are owed in a browser by a person (`docs/accessibility.md`, sections 8 and 9).
- **The second view's three scoping rules, one at a time.** A walk shows their result.
  `apps/api/tests/test_evidence_map.py` shows each rule on its own, from both roles.
- **What the mock-up shows and the build does not:** unsupported claims, "Open the … answers",
  "Add a source", the review queue, "Owner" and the two filters. D-138 gives the reason for each.

## The D-40 screen

### On the Anthropic alpha, 15 November 2026

The walk's questions were screened again for this alpha, at Benjamin's request, before this script
was changed for it. The record is `corpus/demo/screening-2026-11-15-anthropic/`: its `README.md`,
`screening.json` with every score and every run's statements, and `screen_anthropic.py`, which ran
it.

- **The database:** `kmp_alpha_screen_20261115`, a `pg_dump` of the alpha's `kmp_alpha_20261113`.
  Before anything ran, it was checked to hold the same 48 chunks, with the same identifiers and
  embeddings, the same two accounts and the same 43 migrations. The live alpha was not touched.
- **The code:** the alpha's own commit, `6e1efd1`. Retrieval and generation are the same on `main`
  at `f82fb1a`, except the generation parser (#106, #107).
- **The provider:** anthropic, with Claude Haiku 5.5 and `voyage-4` at 1024, as the alpha has it.

The steps were the 1 November screen's:

1. Score every question below, as the role that asks it, with the shipped `compose`,
   `embed_question`, `candidate_chunks`, `rank`, `admit` and `partial_matches`.
2. Upload D21 and T06 through the real routes, as an Employee, exactly as FR-08.1 and FR-09.1 do.
   D21's title is its file name, and its department is `Operations`.
3. Score again.
4. Ask each question three times through `answer_question`, each run in a conversation of its own,
   as the Ask screen does.
5. Score a third time.

**The rule** is D-40's, with its margins measured from `voyage-4`'s own threshold, T = 0.2687
(D-120). The 1 November margins were measured from 0.30.

- **Where an answer is expected:** the top score is at least T + 0.05 (0.3187), and no candidate is
  within 0.005 of T.
- **Where a no-answer is expected:** either the top score is at most T − 0.02 (0.2487), which is
  path A, or the no-answer came on all three runs.
- **Every question:** the same outcome on all three runs.

| Step | Question | Role | Top score (its source) | Admitted | Within 0.005 of T | Three runs | Rule |
|---|---|---|---|---|---|---|---|
| FR-11.1 | Who is the sponsor of Project Atlas? | Employee | 0.1517 (Weekly Operations Standup) | 0 | none | the no-answer, path A, every run | passes |
| FR-11.2 | the same | Administrator | 0.4270 (Project Atlas Kickoff Brief) | 2 | none | answered, citing **Project Atlas Kickoff Brief** (D09), every run | passes |
| FR-12.2 | How quickly do we have to acknowledge a customer complaint? | Employee | 0.5857 (Customer Complaints Procedure) | 14 | Records Management Handbook: 0.2733, 0.2725, 0.2675 | "Every complaint is logged, acknowledged within one working day and investigated fairly." [D06], every run | **fails the band clause** |
| FR-12.3 | How much did the latest penetration test cost? | Employee | 0.2305 (Weekly Operations Standup's summary) | 0 | none | the no-answer, path A, every run | passes |
| FR-12.4 | How many bicycles can the secure bike cage hold? | Employee | 0.5193 (the uploaded D21) | 1 | none | answered, **40**, citing D21, every run | passes |
| FR-12.5 | When will single-use cups be removed from the office kitchens? | Employee | 0.6380 (T06's summary; its transcript scores 0.5895) | 4 | Office Relocation Announcement 0.2726, Vendor Register 2026 0.2661 | answered, **1 March 2027**, citing the meeting, every run | **fails the band clause** |
| FR-13.1, turn 1 | What was the customer satisfaction score last quarter? | Employee | 0.5061 (Customer Success Retrospective) | 3 | none | answered, **86 percent**, citing the retrospective, every run | passes |
| FR-13.1, turn 2 | Where are the first aid kits kept? | Employee | 0.3683 (Customer Success Retrospective) | 4 | none | "First aid kits are kept at reception and on every floor." [D03], every run | passes |
| FR-13.2, turn 2 | Who is the sponsor of Project Atlas? (after turn 1) | Employee | 0.3771 (Customer Success Retrospective) | 2 | none | the no-answer, path B, every run, offering the retrospective as a partial match | passes, on the second limb |
| FR-13.3, turn 1 | What was the customer satisfaction score last quarter? | Administrator | 0.5061 (Customer Success Retrospective) | 3 | Security Incident Debrief's summary, 0.2658 | answered, citing the retrospective, every run | **fails the band clause** |
| FR-13.3, turn 2 | Who is the sponsor of Project Atlas? (after turn 1) | Administrator | 0.3797 (Project Atlas Kickoff Brief) | 5 | none | "The sponsor of Project Atlas is the chief operating officer." [D09], every run | passes |

- **The scores are from the second and third passes,** with both uploads in place, as the walk has
  them.
- **Every question had its expected outcome on all three runs,** and every answer cited the
  expected source on every run. Where the table quotes a statement, its wording was the same on all
  three runs. Elsewhere the wording varied and the facts and sources did not.
- **Three rows fail the band clause:** FR-12.2, FR-12.5 and FR-13.3's first turn.
  - In each, a passage that is not the cited source sits within 0.005 of the threshold. Whether it
    is admitted can change which passages reach the model.
  - The cited source sits far above it: 0.5857, 0.6380 and 0.5061.
  - **Whether to accept them, or to replace those questions, is open.** It is the user's call.
- **`voyage-4`'s scores barely moved.** No row's top score changed by more than 0.0004 between
  passes. D-126's note of 12 November records up to 0.0012 between two passes elsewhere.
  EmbeddingGemma's was about 0.003, which is what the 0.005 band was set against.
- **FR-12.5's top candidate is T06's FR-16 summary,** written when T06 is ingested and indexed as an
  AI-generated passage of the meeting (D-125).
  - Claude writes a new summary at every ingestion and takes no sampling parameters (D-115), so the
    walk's summary will not be the screen's.
  - The transcript's own passage scores 0.5895, far above the threshold, whatever the summary says.
- **The keyword search** for `asset tag`, through `/api/search` as the Employee, gave one result,
  Asset Inventory Melbourne Office, with the summaries present.
- **FR-13 on this build is measured by the thread draws** (D-112's note of 12 November). The screen
  asks only the walk's turns: t08, and t08's first turn followed by the sponsor question. It
  does not ask t01 to t07 or t09.

`kmp_alpha_screen_20261115` is left in place as this screen's database, and nothing points at it.

### On the FLM alpha, 1 November 2026

This is the screen the 1 November walk relied on. It describes the FLM alpha, `8598d19` on
`kmp_demo_20261101`, with EmbeddingGemma's vectors and a threshold of 0.30.

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

#### What the screen found that the walk avoids

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

- **Dual-role coverage:** 43 of 43 protected endpoints exercised from both an Employee and an
  Administrator session, on routes and views identical to the alpha's build (D-131's full run).
  The FLM alpha's build had 23.
  - **The caveat:** the matrix counts a route as covered when a passing test reached it from that
    role. That is weaker than CLAUDE.md §8's "tested from both roles", which means every clause
    from both.
- **The thirty questions, on this alpha's provider** (Claude Haiku 5.5 and `voyage-4`, on
  `kmp_voyage_20261110` at `e04aab1`: `corpus/objective-02/runs/2026-11-10/haiku/harness.txt`):
  - schema conformance 100% (31/31), first attempt 100%;
  - fabricated identifiers 0% (0/28 statements). Verification strips any it finds;
  - out-of-scope chunks in any prompt or answer: 0.
  - **On the FLM alpha's provider** (item 6, `corpus/objective-02/runs/2026-11-01/harness.json`):
    100% (32/32), 0% (0/27), and 0.
- **p90 against NFR-08's 4 s, at five users:**
  - **on `anthropic`:** a valid FAIL at 4,673 ms, over 24 answered replies with no 503 and no 429
    (`corpus/objective-02/runs/2026-11-10-anthropic/nfr08-anthropic.md`, run 6). Two runs that were
    measured and recorded INVALID gave 4.1 and 5.2 s. No single-user figure was measured there;
  - **on FLM:** a valid FAIL, with the 90th percentile a 503, and 277 s answered only, and 51 s at
    one user (`corpus/objective-02/runs/2026-11-01/nfr08-runs.md`). That is a local-model baseline
    on one NPU (D-35, `docs/ai-provider.md` §7);
  - NFR-09 was not run on either, and its failure is a prediction, not a result.
- **The permission boundary:** the audits D-57 to D-61 found no route across it on the six routes
  they walked (`/api/ask`, `/api/search`, `/api/conversations*`, `/api/documents/{id}`,
  `/api/meetings/{id}` and reprocess). The routes added since, and the reviews they had, are in
  FR-06 step 4.

## The answers worth having ready

- **Can a citation point at a passage that does not support its statement? Yes.**
  - Verification checks that the identifier was supplied, not that the passage supports the
    statement. Invariant 5 concedes this by design.
  - The 1 November screen saw it on the FLM alpha, as
    [above](#what-the-screen-found-that-the-walk-avoids). The 15 November screen did not check for
    it: it records each statement's source, not whether the passage supports it.
  - Stage 4's item 9a measured three such mis-citations (`docs/flm-baseline.md`, "three
    mis-citations"). Stage 5's item 9a is the leakage tests, which is a different item.
- **Does the same question always answer the same way? No.** D-40 is open, and its trigger is
  unidentified. These questions were screened for it, on this alpha on 15 November: each had the
  same outcome and source on all three runs, and the wording of some answers varied.
- **Does the assistant follow a conversation?** It keeps the thread, and its scope is re-checked
  on every turn, which is tested (`test_fr11_scoping.py:610` and `:635`). A follow-up that only
  makes sense with the earlier turn did not resolve in the 1 November screen's clean cases, on the
  FLM alpha (D-91). **FR-13 was partial at the gate.** Say so, and do not claim more.
  - **On this alpha's provider, `anthropic`,** 9 of 9 matched on each of three draws. That is a
    measurement on another database, and the auditor has not read it yet (D-112's note of
    12 November). No follow-up of that kind was screened on this alpha.
  - **On the FLM alpha's build,** with history, 1 of 9 frozen follow-ups matched on its code, and
    2, 3 and 2 of 9 on `main`. D-112 accepts the clause as partial for NIT3003 on FLM.
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
      knowledge-gap log, recording transcription (D-123), since 13 November FR-03's warning,
      countdown and Unlock control (D-130), and since 14 November FR-20's knowledge map with its
      table view (D-132);
    - **across screens:** the 429 and 503 messages, the tab order, the text equivalents, the
      focus ring and colour contrast, the production build and the same-origin client.
- **Where does the build fall short of a clause on purpose?** Each is a deviation with a reason,
  never a tick. Each was checked against its entry on 2 November. D-42's and D-112's were checked
  again on 12 November, and D-33's, D-56's and D-69's against `main` that night. On 15 November
  their lines about the alpha were rewritten for the Anthropic alpha. The rest were not checked
  again.
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
    - **That holds on the FLM alpha's build, `8598d19`,** which has no classification.
    - **On this alpha's build, `6e1efd1`, and on `main`, FR-10 is built, so the hand-off is not
      deferred there** (D-104, D-105).
      `_classify` in `apps/ingestion/documents.py` runs between storing the extracted text and
      chunking, in a savepoint of its own. A failure is logged and leaves the document
      unclassified, its status unchanged. The upload's 201 carries `classification`, or null.
  - **D-33 §2 (FR-09):** a 422 when every chunk fails to embed, which FR-09's Responses clause
    does not list. The transcript is kept (invariant 8).
  - **D-42 (FR-13):** earlier questions are passed to the model, not earlier answers. Its
    boundary is contradicted by the 1 November screen (D-42's dated note, D-91). On FLM,
    follow-ups whose referent is in the earlier question mostly did not resolve either. On
    `anthropic`, this alpha's provider, they resolved on every draw, and a referent that is only
    in an earlier answer is still never passed (D-42's note of 12 November).
  - **D-43 (FR-13):** a conversation's `Update` is its title on create and the time of its last
    turn. There is no rename route and no `PATCH`.
  - **D-112 (FR-13):** the follow-up clause, "…so that pronouns and abbreviated references
    resolve correctly", is accepted as partial for NIT3003 on the FLM build. With history, 2, 3
    and 2 of the 9 frozen follow-ups matched on `main` (8 and 9 November), against 6 of 9 spelled
    out, and the FLM alpha's code matched 1 of 9 (3 November). The reason D-112 gives: on several
    threads the right passage was supplied at rank 1, and generation answered from "the
    turn-1-adjacent passage". Options 1 and 2 (D-103) and option 3 (D-111) were measured and not
    adopted. On the default build, `anthropic`, which this alpha runs, it is not admitted as a
    deviation: there the resolving half measured 9 of 9 on each of three draws, and counts only
    when the auditor reads it as met (`M6-BUILD-PROMPT.md`'s Done line, amended 12 November).
  - **D-45 (FR-12):** there is no input sanitiser. The defence is parameterised SQL, React's
    escaping and the prompt's delimiter.
  - **D-56 (FR-12):** on the FLM build, the FLM alpha's included, partial matches have no
    relevance floor. The acknowledgement is recorded.
    - **Step 7 owed the floor (D-93) and set none.** At 0.30 the margin rule cannot set one, and
      retrieval scores did not separate answerable from unanswerable questions in users' wording
      (D-102).
    - **On the default build, `anthropic`, which this alpha runs,** a near miss is offered as a
      partial match only at or above 0.2468 on `voyage-4` (D-120).
    - D-120 records D-56 as narrowed on Voyage, and still open on EmbeddingGemma.
  - **D-69 (FR-14):** the dashboard does not read KnowledgeGaps. That is deferred with FR-19, and
    it holds on the FLM alpha's build.
    - **On this alpha's build, `6e1efd1`, and on `main`, FR-19 is built and the deferral has
      ended** (D-69's note of 10 November, D-107). An Administrator's dashboard shows the number
      of Open knowledge gaps and the top entries.
    - An Employee's payload keeps its keys, because `review_knowledge_gaps` is the
      Administrator's alone.
  - **D-70 (FR-14):** the department filter narrows documents only. Meetings have no department.
  - **D-72 (FR-15):** Department comes from the documents' column, not from ContentTags. That is
    a deliberate departure from FR-15's server clause.
- **Why does one question fail at generation?** On the FLM alpha, "How are records managed and
  retained?" (from `tests/load/common.js`, not one of the thirty) gave a 503 twice at one user and
  three times at five users.
  - **On `anthropic` it did not.** NFR-08's run 6 asked `common.js`'s ten questions with no 503,
    and every generation call parsed on its first attempt. There the unanswered one was "How do I
    make a complaint?": Haiku declined it at generation (path B), 1 of 2 times in run 6
    (`nfr08-anthropic.md`). It is not one of the walk's questions.
  - **At five users,** the attempt log shows every failed attempt was a reply that stopped
    before its JSON closed.
  - **At one user,** the cause was not logged, so the same failure there is inferred, not
    observed.
  - Step 7 observed it on FLM, logging each attempt's `finish_reason` and token count before
    anything changed. It is not one of the questions here.

## Afterwards

- **The walk leaves its accounts, questions, uploads and threads in `kmp_alpha_20261113`,** with
  D21's FR-10 classification and T06's FR-16 summary. The next knowledge-gap cycle considers the
  walk's unanswered questions (`docs/alpha-deployment.md`, step 9).
- **There is no snapshot to restore.** `kmp_alpha_20261113` was built, not restored (D-131). Its
  one copy, `kmp_alpha_screen_20261115`, was made with `pg_dump` for the 15 November screen, and
  it now holds that screen's uploads and questions. No dump file, hash or media copy is recorded.
- **Building it again resets its rows** (`docs/alpha-deployment.md`, "Redeploying"), and needs the
  user's approval. Do that only before a new set of demonstration threads is built, never between
  building them and showing them.
  - **A rebuild is a new draw, not a copy.** Claude classifies the documents and summarises the
    meetings again, and its output varies (D-115). The summaries are passages retrieval ranks
    (D-125), so the questions are screened again on the rebuilt database.
  - **Both accounts get new passwords nobody knows,** so the Administrator's is set again.
  - **The walk's upload stays in the media folder.** Nothing in the build steps clears
    `C:\kmp-demo\2026-11-13\media`. D-88's restores replaced the media tree as well.
- **The FLM alpha's `kmp_demo_20261101` is untouched,** and D-88's snapshot still resets it.
