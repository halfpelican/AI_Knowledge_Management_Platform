# Front-end clauses: FR-01, FR-02, FR-04, FR-05, FR-06, FR-08, FR-09 and FR-12's search half

Post-M6 step 6, 2 November 2026, on `test/FR-01-front-end-clauses`. Item 10's audit, finding S1:
"§8 condition 2 is met for FR-14, FR-15 and most of FR-12 and FR-13, and nowhere else. The UI-only
clauses of FR-01, FR-02, FR-04, FR-05, FR-06, FR-08, FR-09 and FR-12's search half have no
front-end test." `CLAUDE.md` §8 condition 2 (D-62): a clause only the interface can satisfy, meaning
what a screen shows, withholds or offers, is tested in the front-end suite, and an API test does not
stand in for it.

**Where the clause text comes from.** `docs/stage-4-clause-audit.md` and
`docs/stage-5-clause-audit.md` quote FR-11 to FR-15 only. The FR-01 to FR-09 clauses below are
quoted from the proposal's text (`proposal.txt`, which sits untracked in the main checkout and is
not in the repository), Front-End section of each requirement. Server-End clauses are listed only
where they name the client ("rejected client-side").

**How to read the states.** ✅ new: a test added at this step. ✅: a test that already existed.
⚠️: partly covered, with the shortfall named. ❌: not covered, with the reason. Every test added at
this step was run against a deliberate break of the product code it defends and seen to fail. The
breaks are listed in this step's commit message. A test that already existed is cited as it stands,
and was not re-broken here.

**What jsdom cannot see.** No stylesheet is applied. A test sees what the markup shows, hides
(`hidden`, `.visually-hidden`) or offers. It does not see an element hidden by CSS, a meter's
colour, or the indeterminate bar's animation.

---

## FR-01 — User registration

| # | Clause | State | Test |
|---|---|---|---|
| 1 | "User fills a registration form — full name, email, password, confirm password." | ✅ new | `register.test.jsx` :: shows each password rule met or unmet as the password is typed, and keeps Create account disabled until every client-side check passes |
| 2 | "Real-time password strength validation — password strength meter shown as user types (e.g., 'must contain 1 uppercase letter, 1 number, 1 special character, minimum 8 characters')" | ✅ new | Same test. The band in words and each rule's met or unmet state after each keystroke, including that a space is not a special character. The meter bar's width is a style and is not asserted |
| 3 | "…the submit button remains disabled until all client-side checks pass." | ✅ new | Same test. Disabled until the name, the address format, the password policy and the confirmation all pass, and closed again by each on its own. An Enter-key submit while invalid sends nothing |
| 4 | "On success, the user is directed to the login page with a confirmation message." | ✅ new | `register.test.jsx` :: on success, goes to the login page with a confirmation and the email filled in, having sent name, email and password only |
| 5 | "On failure, (e.g., email already registered), an inline error message appears under the relevant field." | ✅ new | `register.test.jsx` :: puts a 409 under the email field and not in a banner, and a 400's message under its own field |

## FR-02 — User login

| # | Clause | State | Test |
|---|---|---|---|
| 1 | "Login form — email and password fields." | ✅ | Exercised by label in `login.test.jsx` (new) and `authThrottle.test.jsx` :: shows login's fixed text for a 429 on sign-in… No test asserts the form's field set on its own |
| 2 | "'Show password' toggle icon." | ❌ | **Not covered.** Outside this step's list. `PasswordInput.jsx`'s toggle (`aria-pressed`, the input's `type`) has no test on any screen |
| 3 | "On submit, 'Login' button disables and shows a loading indicator, preventing a second submission." | ❌ | **Not covered.** Outside this step's list. A held `POST /api/auth/login` would show it |
| 4 | "On success, user is redirected to a role-specific dashboard (e.g., Administrator → Admin Console; Employee → Knowledge Dashboard)." | ✅ new | `login.test.jsx` :: signs an unlocked $user.role in with the right password and lands on $landing (Employee `/dashboard`, Administrator `/admin`). Added as the happy path the locked-account message contrasts with. **The landing is decided by Login's `<Navigate to="/">` and Home's role redirect, not by Login's own `navigate` call** (see "Defects and observations", item 3). `dashboard.test.jsx` :: renders the dashboard at $path for an $user.role covers what each path renders, not the redirect |
| 5 | "On failure, an inline error banner appears — 'invalid email or password'." | ✅ new | `login.test.jsx` :: shows the invalid-credentials banner for a 401 and a different, locked-account message for the 403, disclosing nothing and staying on sign-in |
| 6 | "Where the account is locked and the submitted password was correct, a distinct message is shown." | ✅ new | Same test. Whether the password was correct is the server's decision (FR-03's messaging rule, pytest's). The screen's part is a message distinct from the 401's, which names no account detail and is not the server's prose |

## FR-04 — Logout and session management

| # | Clause | State | Test |
|---|---|---|---|
| 1 | "A 'Logout' control visible in navigation for all authenticated roles." | ✅ new | `logout.test.jsx` :: offers Log out in the navigation to an $role, and on activation sends one logout and lands on sign-in, signed out (Employee and Administrator) |
| 2a | "On activation, user is immediately redirected to the Login page…" | ✅ new | Same test. Failure path: `logout.test.jsx` :: says it could not sign out when the logout request fails, and does not call it a logout |
| 2b | "…with a brief confirmation 'You've been logged out'." | ❌ **defect** | **The shipped screen does not show it.** A test asserting it fails against `main`, so it is left out, and the defect is reported rather than fixed (item 1 below) |

## FR-05 — Role management

| # | Clause | State | Test |
|---|---|---|---|
| 1 | "Admin-only screen listing all users assigned with their role." | ✅ new | `roleManagement.test.jsx` :: lists every user with their role, asks "Change Jane Doe's role to Administrator?" before sending anything, and Cancel sends nothing. "Admin-only" is row 4 |
| 2 | "Confirmation dialogue is shown before the role change is applied: 'Change Jane Doe's role to Admin?'." | ✅ new | Same test. The dialogue is modal and names the change, using the role's own name ("Administrator"). Nothing is sent before it is confirmed, and Cancel sends nothing |
| 3 | "Table updates in real time on confirmation." | ✅ new | `roleManagement.test.jsx` :: on confirmation sends one PATCH carrying the role id, and the row shows the role the server stored without re-reading the list. Failure path: refuses an Administrator's own demotion in words of its own, and puts the row back to the role it has |
| 4 | "This screen is entirely hidden and inaccessible to non-admin roles (button and route do not render)." | ✅ new | `accessDenied.test.jsx` :: offers an Employee no Role management link, and sends one who types /admin/roles to the 403 page without reading the user list. Also :: offers an Administrator the Role management link, and renders the screen at /admin/roles |

## FR-06 — RBAC enforcement (the interface's half)

| # | Clause | State | Test |
|---|---|---|---|
| 1 | "UI elements (buttons, menu items, routes) are conditionally rendered based on the role embedded in the user's session token." | ⚠️ | **Menu item and route:** `accessDenied.test.jsx`, both tests above (new). **Button:** `documentRepository.test.jsx` :: offers no delete control when can_delete is false, and :: says so when the server refuses the delete with a 403, and withdraws the control. That control follows the server's `can_delete`, not the role name. **Not covered:** the Upload and Meetings screens offer an Administrator a visibility choice and an Employee a fixed note (`visibilityOptionsFor`), and no test renders either screen as an Administrator. The clause is tested for the elements named, not for every role-conditional element |
| 2 | "Unauthorised navigation attempts (e.g., manually typing an admin URL) redirect to a '403 – Access Denied' page." | ✅ new | `accessDenied.test.jsx` :: offers an Employee no Role management link, and sends one who types /admin/roles to the 403 page… The 403 page says only that permission is lacking. With no session, the same address goes to sign-in instead: :: sends a visitor with no session to sign in, not to the 403 page. `/admin/roles` is the only role-guarded route. `/admin` is not guarded by design (D-70's clarification) |

The server's half (401 and 403 on every protected route, from both roles) is pytest's dual-role
matrix. Nothing here stands in for it.

## FR-08 — Document upload

| # | Clause | State | Test |
|---|---|---|---|
| 1 | "A drag-and-drop or file-picker upload area accepting PDF, DOCX, DOC, XLSX, XLS, and TXT." (four formats, D-15) | ✅ new | `uploadFormatsAndProgress.test.jsx` :: refuses a file whose extension is not one of the four the moment it is chosen or dropped, naming the four, and queues the four it accepts. Covers the picker and the drop, the four accepted, DOC and XLS refused. The picker alone was already exercised by `uploadQueue.test.jsx` and `ingestionLimits.test.jsx` |
| 2 | "Each file shows a progress indicator and an individual progress bar during upload." | ✅ new | `uploadFormatsAndProgress.test.jsx` :: gives the file being sent its own bar while its bytes go, then a processing indicator until the server answers, and none once it has. Determinate at 0% and 30% (`aria-valuenow`), then indeterminate while the server processes, one bar per file, and the bar withdrawn after a refusal. The fill width and the animation are CSS and are not seen |
| 3 | "Unsupported formats are rejected immediately client-side with a message (E.g., File type not supported. Accepted formats: PDF, DOCX, XLSX)." | ✅ new | The row 1 test, with the message written out. Plus :: sends a file the client accepts on its name, and shows the server's signature refusal against its row: the client check is a convenience, and the 415 is shown against the file |
| 4 | "Once processing completes an 'Indexed' status appears against the document; if extraction fails, a 'Processing failed. Please try again' action is shown." | ⚠️ | ✅ for the status and the action: `uploadQueue.test.jsx` :: withdraws Try again once the retry has indexed the document… (a 422 row offers Try again; after the retry its status reads Indexed), :: holds a queued file's title and Remove until the queue finishes… (Indexed), and `documentStatus.test.js` :: does not offer the retry for "Too large to index". **Thin:** no screen test asserts the "Processing failed…" sentence for each status (D-32's per-status wording), only the button |

## FR-09 — Meeting transcript ingestion

| # | Clause | State | Test |
|---|---|---|---|
| 1 | "Users can upload a transcript file or paste transcript text directly into a form, associating it with a meeting title, date, and attendees." | ⚠️ | Paste and file, with title and date: `meetingProcessing.test.jsx` :: shows it while a text / file transcript is ingested… (new), and `ingestionLimits.test.jsx`'s FR-09 tests (paste, the 429 paths). **Not covered:** attendees. No test chooses an attendee and checks it is sent. Outside this step's list |
| 2 | "A processing indicator is shown while ingestion runs." | ✅ new | `meetingProcessing.test.jsx` :: shows it while a text transcript is ingested, holds the form, and withdraws it when the server answers; the same for a file; and :: withdraws it when the transcript is stored but cannot be indexed, and says so |
| 3 | "Once processed, the stored transcript is then viewable in full." | ❌ | **Not covered.** The new test asserts only that the success notice links to `/meetings/<id>`. Nothing renders `MeetingDetail.jsx` and checks the transcript in full. Outside this step's list |

## FR-12 — the search half

| # | Clause | State | Test |
|---|---|---|---|
| 1 | "A search field available from every page…" | ⚠️ | `search.test.jsx` uses the header field on `/dashboard` and the field on `/search` (new). It does not test "every page". The field is in the shell (`App.jsx` `HeaderSearch`), so it is on every signed-in route by construction, but no test walks the routes. Outside this step's list |
| 2 | "…returning results grouped by type (Documents and Meetings) with a count per group." | ✅ new | `search.test.jsx` :: puts documents and meetings in their own groups, each headed by its count, each result with its title, snippet, department and date. Failure path: :: keeps both groups on screen at a count of zero when nothing matched, and says so plainly rather than as an error |
| 3 | "Each result shows its title, the matching passage as a snippet, its department, and its date." | ✅ new | The first grouping test. The "matched on its title, no passage" note for an empty snippet is not tested |
| 4 | "queries shorter than two characters are rejected client-side" (Server-End, Validation) | ✅ new | `search.test.jsx` :: refuses one character from the header field with a message naming the minimum, sends nothing, and searches at two, and :: refuses a one-character term typed into the address without sending it |
| 5 | "Any partially related items found are offered, clearly labelled as partial matches." | ✅ new | `partialMatches.test.jsx` :: offers them under the no-answer statement, labelled as partial matches and as not an answer, each a link to its source with its type and date and no passage text, :: shows no partial-matches label when the reply offers none…, :: does not offer partial matches beside an answer, even where a reply carried some. **This clause is on the Ask screen**, where `POST /api/ask` carries `partial_matches`. The keyword search screen has none. It sits in FR-12's answer half, and the step's brief listed it under Search |

---

## Server constants the front end copies (finding S4)

`apps/api/tests/test_front_end_constants_agreement.py` reads `frontend/src/constants.js` as text,
as `test_in_flight_codes_agreement.py` does, and holds every export that copies a value of
`apps/core/constants.py`:

| Client export | Server constant | Held as |
|---|---|---|
| `SEARCH_MINIMUM_LENGTH` | `MINIMUM_SEARCH_LENGTH` | equal |
| `QUESTION_MINIMUM_LENGTH` | `MINIMUM_QUESTION_LENGTH` | equal |
| `QUESTION_MAXIMUM_LENGTH` | `MAXIMUM_QUESTION_LENGTH` | equal |
| `MAX_UPLOAD_BYTES` | `MAX_UPLOAD_BYTES` | equal |
| `MAX_UPLOAD_LABEL` | `MAX_UPLOAD_BYTES` | the ceiling in whole MB |
| `ACCEPTED_EXTENSIONS` | `ACCEPTED_EXTENSIONS` | the same four, none twice |
| `ACCEPTED_FORMATS_LABEL` | `ACCEPTED_FORMATS` | the same four, none twice |
| `DOCUMENT_STATUS` | `DOCUMENT_STATUS_VALUES` | every value, once |
| `ROLES` | `ROLE_NAMES` | every value, once |
| `SOURCE_TYPE` | `SOURCE_TYPES` | every value, once |

**Not held by it:**

- `TEXT.noAnswerFallback` and `TEXT.provenanceRemovedFallback`, which the front-end suite already
  holds against `apps/core/constants.py`.
- Two copied texts whose originals are not in `apps/core/constants.py`:
  - `TEXT.dashboardRangeInverted`, whose original is `apps/api/serializers.py`
    `DATE_RANGE_REVERSED_MESSAGE`.
  - The four formats inside `VALIDATION.fileTypeUnsupported`, whose original is
    `apps/api/views.py` `UNSUPPORTED_FORMAT_MESSAGE`.
- The literal "50 MB" in `apps/api/views.py` `FILE_TOO_LARGE_MESSAGE` (S4's third place). That
  is the server restating its own constant and is an open item, not this step's.
- The password policy in `frontend/src/utils/password.js`. It is already held by
  `apps/accounts/tests/test_password_policy_agreement.py`.

---

## Defects and observations found by this step

None is fixed here. Fixing them is react-frontend's work, under a decision the user makes.

1. **FR-04's "You've been logged out" confirmation is never shown after logging out from a
   route behind RequireAuth, which is every screen a signed-in user works on.**
   - The sequence:
     - `src/App.jsx:41` awaits `logout()`.
     - `src/auth/AuthProvider.jsx:86-87` clears the user in a `finally`.
     - `src/App.jsx:42` then navigates to `/login` with `state: {reason: 'signed-out'}`.
   - React Router 7 applies a location update inside `startTransition` (MemoryRouter at
     `react-router/dist/development/chunk-BV7QT456.mjs:7068`, BrowserRouter at `:10509`).
     Clearing the user is an ordinary update, so React renders it first, while the router
     still shows the old address.
   - `src/auth/RequireAuth.jsx:20-21` therefore renders `<Navigate to="/login" state={{from}}>`
     at the old address. That navigation comes last, so it replaces the logout's.
   - `/login` arrives with `{from: '/dashboard'}` and no `reason`. `src/pages/Login.jsx:94`
     reads `arrival` as undefined, and the notice at `:22` never renders.
   - The evidence was gathered in jsdom with MemoryRouter:
     - Logging out from `/dashboard` lands on `/login` with `{from: "/dashboard"}` and no notice.
     - Logging out from `/components`, the one route outside RequireAuth, lands with
       `{reason: "signed-out"}` and shows the notice.
   - BrowserRouter wraps its updates the same way, so the browser is expected to behave
     alike. This was not checked in a browser.
   - Item 8's live walk recorded "Log out leads to the sign-in page", and the demonstration
     script expects only that, so neither looked for the confirmation.
2. **The session-expired notice is lost the same way.**
   - When a request answers 401 on a guarded route, `AuthProvider.jsx:63-64` clears the user
     and navigates with `reason: 'expired'`.
   - RequireAuth's redirect replaces that navigation, and `/login` shows no notice. Observed
     with `GET /api/dashboard` answering 401.
   - This is not an FR clause. AuthProvider's own docstring claims the notice.
3. **Login never returns the user to the guarded route they were sent from.**
   - `src/pages/Login.jsx:117-119` intends that "A guarded route the user was sent away from
     still wins". In practice, a user sent to `/login` from `/meetings` lands on `/dashboard`.
   - `login()` sets the user before Login's own `navigate` commits.
     `Login.jsx:100` then renders `<Navigate to="/" replace />`, and `src/pages/Home.jsx`
     redirects by role. That last navigation wins, so Login's `navigate` target never decides
     the landing.
   - FR-02's clause, a role-specific dashboard, is still met, by Home.
   - This is why deliberate break B6, which changed Login's `navigate` target, was not caught.
     B6b and B6c broke the mechanism that does decide the landing, and both were caught.
4. **Observation, not a clause failure.** On a logout that fails with a 5xx or a network
   error, `AuthProvider.logout`'s `finally` still clears the user.
   - The page shows "Could not sign out" above the sign-in form while the server session may
     still be live, and a reload would sign the user back in.
   - The new failure-path test asserts only the "Could not sign out" notice, not where the
     page goes.

## Left uncovered, in one place

| Requirement | Clause | Why |
|---|---|---|
| FR-02 | "Show password" toggle | Outside this step's list |
| FR-02 | Login button disables and shows a loading indicator | Outside this step's list |
| FR-04 | The "You've been logged out" confirmation | A defect: the screen does not show it (item 1) |
| FR-06 | Role-conditional elements other than the role management link, its route and the delete control | Outside this step's list. The visibility choice on Upload and Meetings is the obvious one |
| FR-08 | The "Processing failed…" sentence for each status | Thin: the action is tested, the per-status wording is not |
| FR-09 | Attendee association | Outside this step's list |
| FR-09 | The stored transcript viewable in full | Outside this step's list |
| FR-12 | The search field "from every page" | Outside this step's list. Tested on two pages, not walked across the routes |
