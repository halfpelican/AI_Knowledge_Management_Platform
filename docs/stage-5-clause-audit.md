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

---

## FR-15 — Document Repository and Filtered Browsing (MUST)

The clauses, quoted from the proposal (`proposal.txt`, FR-15). The download link is Stage 5
item 2a and is enumerated here because the clause is FR-15's; item 2a ticks it.

### Before item 2 — 6 October 2026, at `c98735d`

#### Front-End

| # | Clause | State | What exists |
|---|---|---|---|
| 1 | A list view of documents showing title, type, uploader, upload date, and status | ⚠️ | `DocumentRepository.jsx` lists title, type, status, upload date, department and visible-to from `GET /api/documents`. The response carries `uploaded_by`, but **the table does not show the uploader** |
| 2 | …with sorting | ❌ | The order is fixed: newest first |
| 3 | …and text filtering | ❌ | — |
| 4 | A browse mode allowing navigation by Department, Project, Process or Topic without composing a query | ❌ | `Tag` and `ContentTag` exist (documents 0003, with dimensions `Department`, `Project`, `Process`, `Topic`), but **the development database holds no tags**: nothing writes them until FR-10 (Objective 05, 13 November). `Documents.department` is a column (D-09) |
| 5 | Filters combine | ❌ | — |
| 6 | …with item counts shown against each available value | ❌ | — |
| 7 | Selecting a document opens a detail view showing its metadata | ⚠️ | `DocumentDetail.jsx` at `/documents/:docId` (D-46) shows type, status, uploaded, department, visible to and uploaded by. The list's titles do not link to it |
| 8 | …extracted content | ❌ | Not returned. D-63 restores it, read from `ExtractedContent.extracted_text` |
| 9 | …and a download link | ❌ | No download route exists. Item 2a |
| 10 | Deletion requires confirmation | ❌ | No deletion |
| 11 | …and is available only to users holding the appropriate permission | ❌ | `manage_documents` is not seeded. Settled on 5 October: accounts 0005, Administrator only. D-66 puts every Employee-only document in an Administrator's scope, so none is undeletable |

#### Server-End

| # | Clause | State | What exists |
|---|---|---|---|
| 12 | Handles retrieval, filtering, and deletion of document records | ⚠️ | Retrieval only: the list and detail routes |
| 13 | Executes filtered queries against ContentTags returning matching items with counts per remaining filter value | ❌ | — |
| 14 | Validation: the requesting user must hold manage_documents to delete | ❌ | — |
| 15 | Validation: a document ID must resolve to an existing record | ✅ | `GET /api/documents/{id}` answers 404 for an unknown id and for one outside the caller's scope, by one query (D-46) |
| 16 | The list is filtered to documents the user's role permits, by the same rule as FR-11 | ✅ | `scoped_documents()`, item 1 and D-66 |
| 17 | Counts are computed after that filter, so a count never discloses inaccessible content | ❌ | No counts exist. D-65 governs how filter values are read: shape only, never looked up |
| 18 | Deleting a document also removes its extracted content, embeddings and tag links, so that deleted material cannot subsequently be surfaced through search | ❌ | `ExtractedContent` cascades by FK. **`ContentChunk` and `ContentTag` have no FK (D-07), so `document.delete()` alone leaves the chunks embedded, stamped and retrievable.** `AnswerCitation.chunk` is `SET_NULL` since D-67, so deleting chunks no longer destroys citations |
| 19 | Responses: 200 OK with the document list or detail | ✅ | Both routes |
| 20 | 204 No Content for a filter combination with no accessible matches | ❌ | No filters exist |
| 21 | 403 Forbidden without permission | ❌ | No deletion |
| 22 | 404 Not Found for an unknown document | ✅ | Clause 15 |

#### Database

| Clause | State | What exists |
|---|---|---|
| Documents (Read, Delete) | ⚠️ | Read only |
| ExtractedContent, ContentChunks, ContentTags (Delete, cascade) | ❌ | Clause 18 |
| Tags (Read) | ❌ | Nothing reads them |
| Meetings (Read) | ❓ | Named in the CRUD line with no clause that uses it: FR-15's views and filters are about documents. Recorded rather than guessed at |

#### Readings the brief settles

- **The values a filter offers, and their counts, come from the documents the caller may see,
  never from the `Tag` table.** A tag or department used only on restricted documents would
  otherwise disclose them by being offered (invariant 1).
- **Delete is scoped-first.** Resolve through `scoped_documents()` (404 outside scope, D-46),
  then check `manage_documents` (403). The other order would tell a caller whether a document
  they cannot see exists.
- **Deletion removes the chunks (by `source_type` and `source_id`), the `ContentTag` rows and
  the document in one transaction (invariant 9).** The stored file is removed in
  `transaction.on_commit`, so a rolled-back delete keeps it.
- **Extracted content is read from `ExtractedContent` through the same scoped lookup as the
  detail view, never reassembled from chunks, and rendered as text, never HTML.** A document
  with no `ExtractedContent` row shows a stated empty state, keyed on the row existing.
- **Filter state lives in the URL query string**, so Back from a detail view lands on the same
  filters.
- **Browse needs tags on the demonstration corpus, seeded with `applied_by="user"`**, and that is
  recorded as a decision.

### After item 2 — 7 October 2026, on `feat/FR-15-document-repository`

Built by the django-backend agent (browse, the detail fields, deletion, `accounts 0005`) and the
react-frontend agent (the repository and detail screens), in parallel against the contract. The
coordinating session reviewed both diffs and committed them. The first attempt of both agents
stopped on a usage limit; the backend wrote nothing, and the frontend's two partial API edits were
reviewed and kept. Backend tests are in `apps/api/tests/test_document_browse.py`,
`test_document_detail_fields.py`, `test_document_delete.py`, `apps/documents/tests/test_deletion.py`
and `apps/accounts/tests/test_manage_documents_seed.py`. Front-end tests are in
`frontend/tests/documentRepository.test.jsx`.

#### Front-End

| # | Clause | State | Evidence |
|---|---|---|---|
| 1 | A list view showing title, type, uploader, upload date, and status | ✅ | The repository reads `GET /api/documents/browse`. Front end: `shows each column FR-15 names, including the uploader, and links each title to its detail view` |
| 2 | …with sorting | ✅ | Five sort keys, both directions, newest first by default (D-72). Backend: `test_every_sort_key_in_both_directions`, `test_the_default_sort_is_newest_first`, `test_the_primary_key_breaks_a_tie_in_either_direction`. Front end: `sorts from the column headings, writing the sort to the address and the request` |
| 3 | …and text filtering | ✅ | Title, with D-71's whitespace collapsing. Backend: `test_the_text_filter_matches_a_title_that_wraps_a_line`, `test_the_text_filter_treats_like_wildcards_as_characters`. Front end: `writes the title filter to the address and the request when it is submitted` |
| 4 | Browse by Department, Project, Process or Topic without composing a query | ✅ 🔧 | Each dimension lists its values with counts. Department comes from the documents column, not ContentTags, a deliberate departure (D-72). The demonstration corpus is tagged by D-74's script. Front end: `lists each dimension with the counts the server sent, and choosing values updates the address and the request` |
| 5 | Filters combine | ✅ | AND across dimensions (D-72). Backend: `test_filters_combine_with_and` |
| 6 | …with item counts shown against each available value | ✅ | Each dimension's counts exclude its own filter and apply every other. Backend: `test_each_dimensions_counts_exclude_its_own_filter_and_apply_every_other`, `test_the_text_and_status_filters_narrow_every_facet`, `test_a_document_linked_to_the_same_tag_twice_is_counted_once` |
| 7 | Selecting a document opens a detail view showing its metadata | ✅ | Titles link to `/documents/:docId`; metadata and tags by dimension. Front end: `shows the metadata and the tags by dimension`. Filters survive the round trip: `lands on the same address, the same controls and the same request after opening a document and going Back` |
| 8 | …extracted content | ✅ | From `ExtractedContent`, never reassembled from chunks; rendered as text; an empty state keyed on `null` (D-63, D-73). Backend: `test_extracted_text_is_the_rows_text_not_the_chunks`, `test_extracted_text_is_null_when_the_document_has_no_row`. Front end: `shows markup in the extracted text as the characters it is, and creates no element from it`, `shows the stated empty state when extracted_text is null, keyed on the null and not on the status` |
| 9 | …and a download link | ❌ | Stage 5 item 2a. The detail view marks where it goes and renders nothing |
| 10 | Deletion requires confirmation | ✅ | Front end: `asks for confirmation before sending anything, and Cancel sends no DELETE`, `sends exactly one DELETE on confirm, then returns to the repository at the filters the user came from` |
| 11 | …and is available only to users holding the appropriate permission | ✅ | The control shows only when `can_delete` is true; the server checks on every delete. Backend: `test_can_delete_is_true_for_an_administrator_and_false_for_an_employee`, `test_can_delete_follows_the_roles_permission_not_the_role_name`. Front end: `offers no delete control when can_delete is false`, `says so when the server refuses the delete with a 403, and withdraws the control` |

#### Server-End

| # | Clause | State | Evidence |
|---|---|---|---|
| 12 | Handles retrieval, filtering, and deletion of document records | ✅ | `apps/api/repository.py` (one scoped query for the list and browse), `DocumentBrowseView`, `DocumentDetailView.delete`, `apps/documents/deletion.py`. Backend: `test_get_api_documents_is_still_a_bare_list_built_by_the_same_query` |
| 13 | Filtered queries against ContentTags, with counts per remaining filter value | ✅ 🔧 | Project, Process and Topic query `ContentTag` rows restricted to the scoped, filtered documents; Department is the column (D-72). Values never come from `Tag` alone. Backend: `test_a_tag_value_used_only_on_restricted_documents_is_never_offered` |
| 14 | The user must hold manage_documents to delete | ✅ | `accounts 0005`, Administrator only (D-73). Backend: `test_an_employee_gets_403_on_a_document_in_scope_and_nothing_is_deleted`, `test_an_administrator_without_the_permission_gets_403`, and the seed tests in `test_manage_documents_seed.py` |
| 15 | A document ID must resolve to an existing record | ✅ | Backend: `test_unknown_and_out_of_scope_are_both_404_and_never_403`, checked before the permission |
| 16 | The list is filtered to documents the role permits, as in FR-11 | ✅ | Backend: `test_administrator_only_documents_are_absent_for_an_employee_and_present_for_the_administrator`, `test_an_employee_only_document_is_in_the_administrators_browse` (D-66), `test_a_document_the_callers_role_may_not_read_is_absent_from_documents_and_facets`, `test_a_role_change_takes_effect_on_the_next_request`, and the `api/documents/browse GET` probe in `test_source_rows_fail_closed.py` |
| 17 | Counts computed after that filter, so a count never discloses inaccessible content | ✅ | Backend: `test_an_employees_browse_payload_is_byte_identical_with_and_without_restricted_documents_and_tags` (seven filter shapes), `test_an_unknown_and_a_restricted_only_value_give_the_same_204` |
| 18 | Deleting a document removes its extracted content, embeddings and tag links, so deleted material cannot be surfaced through search | ✅ | One transaction, the file on commit (D-73). Backend: `test_an_administrator_deletes_a_document_and_everything_derived_from_it`, `test_after_a_delete_search_finds_nothing_and_a_question_only_it_answered_takes_path_a`, `test_a_citation_of_a_deleted_chunk_survives_with_its_chunk_null` (D-67), and `test_deletion.py`'s rollback, file-on-commit and lock tests |
| 19 | 200 with the document list or detail | ✅ | Backend: `test_the_payload_has_exactly_the_contracts_keys`, `test_an_unfiltered_empty_repository_is_200_with_empty_lists`, `test_the_detail_is_the_list_object_plus_exactly_the_three_detail_fields` |
| 20 | 204 for a filter combination with no accessible matches | ✅ | Only when a filter is set; `sort` alone never (D-72). Backend: `test_a_filter_that_matches_nothing_is_204_with_no_body`, `test_sort_alone_is_never_204`, `test_a_filter_on_an_empty_repository_is_204`. Front end: `on a filtered address opened directly, shows the empty state, the filters from the address and Clear filters, and assumes no facets`, `drops the facets an earlier reply carried when a later one is a 204` |
| 21 | 403 without permission | ✅ | Row 14 |
| 22 | 404 for an unknown document | ✅ | Row 15. Front end: `shows a 404 as not found, never which kind, with a way back to the repository` |

#### Database

| Clause | State | Evidence |
|---|---|---|
| Documents (Read, Delete) | ✅ | Rows 12 and 18 |
| ExtractedContent, ContentChunks, ContentTags (Delete, cascade) | ✅ | Row 18. `ExtractedContent` goes by its foreign key; the chunks and tag links go by source in the same transaction (D-07) |
| Tags (Read) | ✅ | Through `ContentTag`, for the facets and the detail's tags; never offered on its own |
| Meetings (Read) | ❓ | Still no clause uses it. Recorded, not interpreted |

#### Not covered by item 2

- **The download link and route.** Item 2a.
- **Paging.** Browse returns every match. Fine at the corpus size, not at scale.
- **Hand-typed tag values in a URL** filter correctly but do not show their facet button as pressed
  (D-72's note).
- **Reads of `ContentTag` and `ExtractedContent`** go through scoped documents, as the tests
  assert, but the D-53 scan does not watch those models.
- **No browser check.** The screens are tested in jsdom only. Narrow widths and keyboard order are
  item 7's.

### After item 2a — 14 October 2026, on `feat/FR-15-document-download`

Built by the django-backend agent (the route, the error file, the never-cache middleware) and the
react-frontend agent (the link), in parallel against D-75, D-76 and the contract, which were
committed first. The coordinating session reviewed both and committed them. The backend agent was
stopped by a usage limit while deliberate break (a) was applied. The coordinating session found
the break still in place, restored it, and resumed the agent, which confirmed the file matched its
snapshot byte for byte.

Only FR-15's ninth clause changes. Every other row of the item 2 table above stands.

| # | Clause | State | Evidence |
|---|---|---|---|
| 9 | …and a download link | ✅ | `GET /api/documents/{id}/download` (D-75), linked from the detail view as `<a href download>`, on every document in every status. **Backend** (`apps/api/tests/test_document_download.py`, every test from both roles): `test_each_format_downloads_as_the_stored_original_byte_for_byte`, `test_a_download_is_named_and_typed_by_its_signature_not_by_its_uploaded_name` (`Q3_budget.vbs` and `invoice.html` uploaded through the real API download as `.txt`), `test_an_administrator_only_document_is_an_employees_unknown_id_and_the_administrators_file`, `test_unknown_and_out_of_scope_are_one_404_from_both_roles`, `test_a_document_downloads_in_every_status`, `test_the_stored_file_is_not_served_at_its_media_url`, the three missing-file tests, and the `Accept` tests. Also the `api/documents/<uuid:pk>/download GET` probe in `test_source_rows_fail_closed.py`. **Front end** (`documentRepository.test.jsx`): `links to exactly the download route for this document, with an empty download attribute`, one test per status, `puts no /media/ address anywhere on the detail view`, `is left to the browser: a click is not intercepted and sends nothing through the API client` |

The server-end clauses this route also answers to:

| Clause | State | Evidence |
|---|---|---|
| 15. A document ID must resolve to an existing record | ✅ | A blank or missing file is the same 404, with the same body, logged to `logs/errors.log` (D-75). An out-of-scope document logs nothing at ERROR even when its file is missing |
| 16. Filtered to documents the role permits, as in FR-11 | ✅ | Through `scoped_document_or_404`, which the detail view and the delete share. A download can consult only the document's stamp; it agrees with chunk-level retrieval while the cascade holds (D-75) |
| 22. 404 for an unknown document | ✅ | `test_unknown_and_out_of_scope_are_one_404_from_both_roles` |

Beside the clause, from D-76: every `/api/` response is marked never-cache, tested across
`enumerate_endpoints()` for anonymous, Employee and Administrator sessions, including 401, 403,
404 and CSRF refusals (`apps/api/tests/test_never_cache.py`). The error file is tested in
`apps/core/tests/test_logging_config.py`.

#### Not covered by item 2a

- **No real-browser check.** jsdom cannot download, so how Chrome, Firefox and Safari present a
  failed download (a 401 or 404 on a `download` link) is unverified. Some may save the JSON body as
  a file. Worth one manual check in item 8's live run.
- **A cross-origin API base.** Browsers ignore `download` on a cross-origin address, so a failure
  would replace the tab with JSON. D-21 keeps the API same-origin.
- **Reprocess's HTML 500 on a missing file, and the `SuspiciousFileOperation` 400**, are item 5's
  (D-75's notes).
