# Stage 5 clause audit

Every clause of the requirements Stage 5 owns, ticked against what is in the repository.
`M6-BUILD-PROMPT.md` requires it **before either requirement's first line of code**:
"enumerate FR-14's and FR-15's clauses exhaustively and tick each against what exists —
every MUST, every front-end line". `docs/stage-4-clause-audit.md` is the worked example,
and the clauses here are quoted from the proposal (`proposal.txt`, FR-14 and FR-15), not
from the brief's summary of them.

Each requirement is enumerated twice: **before** its first line of code, against what
existed then, and **after**, against what was built. The "before" table is kept as written,
because it is the record of what the item started from.

**How to read the states.** ✅ built and tested. ⚠️ partly built, with the shortfall named.
❌ not built. 🔧 deliberately not built, with a numbered decision recording why. ❓ waiting
on a decision that is not yet settled, which is named.

---

## FR-14 — Dashboard Overview (MUST)

The proposal's framing sentence, which governs how the panels are read: "The dashboard is
the platform's entry point after login, presenting a summary of recent documents, meetings,
indexed content, and recent questions in a single view. It exists to orient the user rather
than to hold functionality of its own: each panel is a route into the module that owns it."

### Before item 3 — 6 October 2026, at `5e2a8a3`

#### Front-End

| # | Clause | State | What exists |
|---|---|---|---|
| 1 | Landing page shown after login | ❌ | FR-02's login sends an Administrator to `/admin` and an Employee to `/dashboard` (`DASHBOARD_PATHS`, `frontend/src/constants.js`). Both routes render the `<Home />` placeholder (`frontend/src/App.jsx`). The brief requires the dashboard on both, whichever role signs in first |
| 2 | …presenting summary panels: recent documents | ❌ | No panel. The full list exists: `GET /api/documents`, scoped, newest first |
| 3 | …recent meetings | ❌ | No panel. The full list exists: `GET /api/meetings`, scoped, newest met first |
| 4 | …total indexed items | ❌ ❓ | Nothing counts indexed items. **What is counted is not settled**: see the open questions below |
| 5 | …and recent questions asked | ❌ | No panel. `QueryLog` holds every question; nothing returns a user's own recent questions as a list. `GET /api/conversations` lists threads, not questions |
| 6 | Each panel links through to its full view | ❌ | The full views exist: `/documents`, `/meetings`, `/ask`. Nothing links to them from a dashboard |
| 7 | Panels display a loading state while data is retrieved | ❌ | — |
| 8 | Dashboard content is filterable by date range | ❌ ❓ | D-65 settles how a date range is validated (inclusive, `date_from` ≤ `date_to`). **Which date each panel filters on is not settled** |
| 9 | …and by team/department | ❌ ❓ | Only documents carry a department (D-09). **How the filter treats meetings and questions, which have none, is not settled** |
| 10 | …and content is restricted to items the user's role permits them to see | ⚠️ | The predicate exists: `scoped_documents()` and `scoped_meetings()`, item 1, with D-66's reading. Nothing on a dashboard uses it yet |

#### Server-End

| # | Clause | State | What exists |
|---|---|---|---|
| 11 | A single endpoint aggregates counts and recent items across the content tables in one request rather than issuing separate calls per panel | ❌ | No endpoint |
| 12 | Validation: a valid session is required | ⚠️ | `IsAuthenticated` is the global default (invariant 4), so any new route inherits it; no route exists to inherit it |
| 13 | Validation: role and department are used to filter the aggregation | ❌ ❓ | Role: the scoped helpers. Department: D-65 says how the parameter is read (shape-only, never checked against the database), not what it filters |
| 14 | Business logic: counts are computed after permission filtering, consistent with FR-11, so that a total never reveals the existence of inaccessible content | ❌ | The pattern exists in search (counts are properties over scoped rows). Nothing counts for a dashboard |
| 15 | Responses: 200 OK with a summary JSON payload | ❌ | — |
| 16 | Responses: 401 Unauthorised where the session is invalid | ⚠️ | Inherited from the authentication class every route uses (`apps/api/authentication.py`) |

#### Database

| Clause | State | What exists |
|---|---|---|
| CRUD: Documents, Meetings, ContentChunks, QueryLog (Read) | ❌ | The tables exist; nothing reads them for a dashboard |
| CRUD: KnowledgeGaps (Read) | ❌ 🔧 | The table does not exist. `docs/schema-v1.md` §2 defers it to NIT3004 with FR-19 and Objective 06 (13 November). The brief requires that to be recorded as a decision before the auditor records it as a gap |

#### Readings the brief settles, to be recorded as decisions

- **"Content is restricted to items the user's role permits" is role scoping, not attendance
  scoping**, for documents, meetings and totals (D-16, invariant 3).
- **Recent questions are the requesting user's own `QueryLog` rows, and the question only.**
  Role scoping would show one user's questions to another; `QueryLog.answer_text` was
  generated under the role held at the time and may now cite material outside the reader's
  scope (D-48's instance 3), and `QueryLog.answered` is a column D-48's instance 7 says must
  be re-derived, not trusted.
- **The department filter offers only departments present on content the user may see.**
  A department used only on restricted documents would disclose them by being offered.
- **KnowledgeGaps is deferred** with FR-19.

#### Open questions — asked before any code, and settled the same day

- **Q1.** Department filter and the panels that have no department: meetings and the user's
  own questions. **Settled, D-70:** "team/department" means department. It narrows documents
  only, the screen says so, and the indexed total is shown split by type.
- **Q2.** What "total indexed items" counts. **Settled, D-70:** documents and meetings whose
  status is `Indexed`. `ContentChunks` is deliberately not read, because atomic ingestion makes
  the status reflect the chunks.
- **Q3.** Which date each panel's date range applies to, and whether it narrows the total.
  **Settled, D-70:** each type filters on its own date (`uploaded_at`, `meeting_date`,
  `answered_at`), timestamps by Melbourne date, and the total is narrowed per type.

The readings above are recorded as D-68 (recent questions) and D-69 (KnowledgeGaps).

#### Related, not FR-14's own clauses

- **FR-02**: "On success, user is redirected to a role-specific dashboard (e.g.,
  Administrator → Admin Console; Employee → Knowledge Dashboard)." Both routes exist; item 3
  gives each the dashboard.
- **NFR-10**: "The main dashboard … must fully load within 2 seconds under normal network
  conditions." Not tested by item 3. One endpoint (clause 11) is what makes it achievable.

### After item 3 — 6 October 2026, on `feat/FR-14-dashboard`

Built by the django-backend agent (`GET /api/dashboard`) and the react-frontend agent (the
screen), working in parallel against the contract, and reviewed and committed by the
coordinating session. Backend tests are in `apps/api/tests/test_dashboard.py`; front-end tests
are in `frontend/tests/dashboard.test.jsx`.

#### Front-End

| # | Clause | State | Evidence |
|---|---|---|---|
| 1 | Landing page shown after login | ✅ | `/dashboard` and `/admin` both render `Dashboard`, and a signed-in `/` redirects to the role's path. Front end: `renders the dashboard at $path for an $user.role` (Employee and Administrator, both routes and `/`) |
| 2 | Recent documents panel | ✅ | Up to `DASHBOARD_RECENT_ITEMS`, newest first. Backend: `test_the_recent_lists_are_capped_and_newest_first_and_the_figures_are_not` |
| 3 | Recent meetings panel | ✅ | The same test, for meetings |
| 4 | Total indexed items | ✅ | Status `Indexed` only, split by type with the sum (D-70). Backend: `test_indexed_totals_count_only_status_indexed_split_by_type`. Front end: `shows the documents figure, the meetings figure and their sum, each as the server sent it` |
| 5 | Recent questions asked | ✅ | The caller's own rows, question only (D-68). Backend: `test_recent_questions_are_only_the_callers_own`, `test_recent_questions_carry_the_question_only`. Front end: `renders the question and when it was asked, and nothing that looks like an answer` |
| 6 | Each panel links through to its full view | ✅ | Front end: `links each panel heading, each figure and each item to the module that owns it`. A recent question links to `/ask`, not to its thread, until item 4a |
| 7 | Panels display a loading state while data is retrieved | ✅ | One request for the page, and `role="status"` text in every panel. Front end: `shows every panel loading until the one request answers, then its content`, `shows the loading state again when a filter is applied, not the previous reply` |
| 8 | Filterable by date range | ✅ | Each type by its own date, inclusive, timestamps by Melbourne date (D-70). Backend: `test_the_date_range_is_inclusive_at_both_ends`, `test_a_timestamp_is_compared_by_its_melbourne_date_not_its_utc_date`, `test_meetings_filter_on_meeting_date_not_on_when_they_were_recorded`, `test_questions_filter_on_answered_at_and_an_unanswered_one_is_still_listed`. Front end: `shows the active range and department the server applied`, `refuses a start date after the end date before sending anything` |
| 9 | …and by team/department | ✅ | Department narrows documents only, and the screen says so (D-70). Backend: `test_department_narrows_documents_and_their_figure_only`. Front end: `states next to the department control that it applies to documents only`. Filter state lives in the URL: `restores the filters and re-sends the same request after following a panel link and pressing Back` |
| 10 | Content restricted to items the user's role permits | ✅ | Server-side only, so the screen filters nothing. Backend: `test_administrator_only_rows_are_absent_for_an_employee_and_present_for_the_administrator`, `test_an_employee_only_row_is_in_the_administrators_payload`, `test_a_row_the_callers_role_may_not_read_is_absent_from_every_panel`, and `apps/api/tests/test_source_rows_fail_closed.py`'s `api/dashboard GET` probe, with its Administrator mirror |

#### Server-End

| # | Clause | State | Evidence |
|---|---|---|---|
| 11 | One endpoint aggregates counts and recent items in one request | ✅ | `DashboardView`. Front end: the landing tests assert exactly one dashboard request per page load |
| 12 | A valid session is required | ✅ | Backend: `test_an_anonymous_request_is_401`. The dual-role matrix covers `/api/dashboard` from both roles |
| 13 | Role and department filter the aggregation | ✅ | Role through `scoped_documents` and `scoped_meetings` (D-53, D-66); department per row 9. Query parameters pass `DashboardQuerySerializer` (D-65). Backend: `test_a_malformed_parameter_is_400_keyed_on_its_name`, `test_a_reversed_range_names_the_rule_under_the_end_date`, `test_an_empty_parameter_is_not_applied`, `test_the_boundary_values_are_accepted` |
| 14 | Counts computed after permission filtering, so a total never reveals inaccessible content | ✅ | Every count is `.count()` over the scoped, filtered querysets. Backend: `test_an_employees_payload_is_byte_identical_with_and_without_restricted_rows` (four filter shapes), `test_departments_never_offers_one_found_only_on_restricted_documents`, `test_an_unknown_and_a_restricted_only_department_give_the_same_payload` |
| 15 | 200 with a summary JSON payload | ✅ | Backend: `test_the_payload_has_exactly_the_contracts_keys`, `test_an_empty_dashboard_is_200_with_empty_lists_and_zero_counts` |
| 16 | 401 where the session is invalid | ✅ | Row 12 |

#### Database

| Clause | State | Evidence |
|---|---|---|
| Documents, Meetings, QueryLog (Read) | ✅ | `DashboardView` |
| ContentChunks (Read) | 🔧 | Deliberately not read: atomic ingestion makes a source's status reflect its chunks (D-70) |
| KnowledgeGaps (Read) | 🔧 | Deferred with FR-19 (D-69) |

#### Not covered by item 3

- **NFR-10's two-second load** is not measured.
- **A recent question's link to its own thread** waits on item 4a's `/ask?c=<id>`.
- **`useApiResource`.** The front-end agent built its own request hook, because the shared one
  keeps showing the previous reply while a new one loads. That defect also affects `Search` today,
  and it is not fixed here.
- **`formatDate`** reads a date-only string as UTC midnight, so a host west of UTC would show
  meeting and filter dates a day early. The alpha host is Melbourne (D-64), so the alpha is not
  affected. Not changed here.
- **`/admin` carries no role guard.** An Employee who types it sees their own scoped dashboard
  (D-70's clarification).
