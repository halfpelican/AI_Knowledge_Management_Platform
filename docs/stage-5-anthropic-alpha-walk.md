# The walk on the Anthropic alpha: the twelve, 19 November 2026

The twelve gate requirements were walked live on the Anthropic alpha on 19 November 2026, in the final demonstration, and recorded on screen. The closing audit (D-140) found that no such walk was recorded, and that FR-04's "You've been logged out" had never been shown on any alpha. This record answers both.

- **Who:** the team, as its final demonstration. The presenters' script divides the scenes between Benjamin Morovan and Sagarika Dey. The coordinating session read the server's side afterwards, on 19 and 22 November, reading only: the alpha's database, its audit log and its outbox.
- **The alpha:**
  - commit `e92b801`, clean: both of the deployment record's lines, 18 and 19 November, read `dirty=False`;
  - database `kmp_alpha_20261113`, on the anthropic provider: Claude Haiku 5.5, and Voyage `voyage-4` at 1024;
  - Waitress 3.0.2, 24 threads, `DEBUG` off, on `127.0.0.1:8000`;
  - redeployed on 18 November (D-131's dated note of 22 November), and restarted on the same build on 19 November at 09:53.
- **FLM takes no part** in this alpha (`docs/alpha-deployment.md`, step 2), so `scripts/check_flm.py` does not apply.
- **The script:** `docs/demonstration-script.md`, and the presenters' scene-by-scene version of it, a Claude Doc titled "Final demonstration video script".
- **The recordings:**
  - screen recordings made between 13:17 and 14:46;
  - cut by scene into 15 files, `Scene_01.mp4` to `Scene_13.mp4`, with scenes 6 and 12 in two parts;
  - an edited video with scene titles, made from them.

  They are kept outside git. On 22 November the 15 scene files sat untracked in the alpha worktree's `corpus/demo`, and they must move out of it before the next redeploy, whose step 1 requires a clean checkout.
- **Times** are AEDT, from the database and the audit log.

## What the server recorded

| Requirement | What the walk did | The server's trace, 19 November |
|---|---|---|
| FR-01 | Registered a throwaway account | `lockout.demo@example.com`, created at 13:35. No other account was created that day |
| FR-02 | Signed in, in both roles | `corpus.admin@example.com` last signed in at 13:31, and `corpus.employee@example.com` at 13:40 (read at 15:00 that day) |
| FR-03 | Locked the throwaway account with five failures; the Administrator released it | `login_attempts`: a `lockout` at 13:38 and a `release` at 13:39 |
| FR-05 | Changed Corpus Employee's role, then changed it back | `audit.log`: two `role_changed` events by `corpus.admin`, at 13:31:50 and 13:32:02 |
| FR-08, FR-10 | Uploaded D21 | `D21_bicycle_end_of_trip_facilities` (DOCX), Indexed, at 13:44 |
| FR-09, FR-16 | Stored T06's transcript | `Sustainability Working Group`, Indexed, at 13:51, with its summary `Ready` |
| FR-12 | Keyword search | one `search_logs` row |
| FR-11, FR-12, FR-13 | The screened questions, in both roles | 14 `query_log` rows, 14:08 to 14:22, below |
| FR-19 | Ran an aggregation cycle | one knowledge-gap cycle |
| D-137 | Uploaded profile pictures | two accounts' pictures set |

**The questions, from `query_log`:**

| Time | Role | Question | Outcome | Matches the screen? |
|---|---|---|---|---|
| 14:08, 14:09 | Employee | "Who is the sponsor of Project Atlas?", asked twice | no answer, `no_relevant_passage` (path A) | Yes |
| 14:09 | Administrator | the same | answered: the chief operating officer | Yes |
| 14:10 | Employee | "How quickly do we have to acknowledge a customer complaint?" | answered | Answered, as screened. The citation was not checked here |
| 14:11 | Employee | "How much did the latest penetration cost?" | no answer, `no_relevant_passage` (path A) | The expected outcome, but **the wording was not the screened one**, which reads "penetration test cost" (D-40, condition 2) |
| 14:11 | Employee | "How many bicycles can the secure bike cage hold?" | answered: 40 | Yes, from the upload two scenes earlier |
| 14:11 | Employee | "When will single-use cups be removed from the office kitchens?" | answered: 1 March 2027 | Yes |
| 14:17, 14:21 | Employee | "What was the customer satisfaction score last quarter?", in two conversations | answered: eighty-six percent | Yes |
| 14:18 | Employee | "Where are the first aid kits kept?" | answered: at reception | Yes |
| 14:21 | Employee | "Who is the sponsor of Project Atlas?", as the second turn | no answer, `no_statement_verified` (path B) | Yes: the partial-match case FR-13 step 2 expects |
| 14:22 | Administrator | the satisfaction question, twice, then the Atlas question | answered: eighty-six percent; the chief operating officer | Yes |

## What only the screen shows

These leave no trace on the server, beyond a deleted session row or nothing at all. The recordings and Benjamin's account are the evidence, and the front-end suite tests the behaviour behind each.

- **FR-04's confirmation (D-97).** After logging out, the sign-in page reads "Logged out" and "You've been logged out.". Benjamin shared a screenshot of it on 22 November: the alpha's sign-in page, signed out, in #119's layout with "Remember me on this device". This is the first alpha to show it: the FLM alpha at `8598d19` predates the fix (`docs/stage-5-item-8-walk.md`). The test is `authNotices.test.jsx`.
- **The screen-only results of the other requirements:**
  - FR-06's access-denied page, its JSON 403 and its 401;
  - FR-01's refusal of a weak password;
  - FR-14's two dashboards;
  - FR-15's facets, filters and empty state;
  - FR-20's two views.

## What differed from the script

- **Window B used `corpus.employee@example.com`,** whose password Benjamin set on 19 November, rather than registering `demo.employee@example.com`. FR-01 was shown with the throwaway account.
- **The penetration-test question was asked without "test".** It got the expected no-answer, but that wording was not screened.
- **No password-reset email was written during the walk.** The first request used an address with no account, which by design gets the same reply and sends nothing (D-137). The email path was checked separately at 15:00 with `test@example.com`, and a reset email reached the outbox. The outbox holds nothing else from 19 November.

## Not covered

- **The recordings were not reviewed by the coordinating session,** which cannot watch video. Each scene's screen-only result rests on them and on Benjamin's account.
- **The walk ran on `e92b801`.** `825d69f`, with FR-10's document summaries and their migration (D-139), is not deployed.
- **NFR-17's screen-reader run, NFR-16's 320 px reflow and its axe run** are still owed by a person (`docs/accessibility.md`).
