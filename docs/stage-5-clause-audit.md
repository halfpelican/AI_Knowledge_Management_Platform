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

> **Closed on 20 October 2026, outside a numbered item:** a recent question's link to its own
> thread. Row 6's "until item 4a" is answered. A question asked in a thread links to
> `/ask?c=<id>`, and a one-off question stays plain text (D-70's note). Front end
> (`dashboard.test.jsx`): `links a question with a conversation_id to exactly /ask?c=<that id>,
> named by the question`, `renders a one-off question (conversation_id null) as plain text, with
> no link`, `encodes a thread id the address could not carry as it is`.

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

---

## Carried from Stage 4: FR-13's thread and FR-12's citation link

Stage 4's closing audit (D-61) found that the active thread was lost on any navigation, including
a citation's own same-tab link (its gap 3). Item 4a owns that gap. The clauses are quoted from
`docs/stage-4-clause-audit.md`, whose rows stand as written. Only the rows item 4a changes are
shown here.

### After item 4a — 15 October 2026, on `fix/FR-13-retain-thread`

Built by the react-frontend agent against D-77, which was committed first. The coordinating
session reviewed it and committed it. The agent stalled once while running its deliberate breaks.
Before resuming it, the coordinating session found no break applied: `Ask.jsx` matched the agent's
backup, and every break's original text was present exactly once.

| Requirement | Clause | Stage 4 | After 4a | Evidence |
|---|---|---|---|---|
| FR-13 | A conversational interface reachable from any page, retaining the thread so follow-ups need not restate the subject | ⚠️ | ⚠️ | **The thread now survives navigation, Back and a reload**, because the address names it (D-77). **Still ⚠️ for D-42:** prior answers are never passed, so a follow-up that refers into the previous answer does not resolve. That was conceded at Stage 4 and item 4a does not change it. Front end (`askThread.test.jsx`): `re-reads the thread from the server and shows its turn`, `shows the turns of the thread named in the address on mount, and marks it current`, `sends no read for a thread the screen itself has just written to the address, so its live turn stays`, `names the created thread in the address before the answer, dropping q, and replaces the entry rather than pushing one` |
| FR-13 | Previous conversations listed and reopenable; the active thread can be cleared to begin a new topic | ⚠️ | ⚠️ | **Reopening and clearing now add a history entry**, so Back returns to the thread before. **Still ⚠️ for D-61's gap 4:** a reopened thread's citations can't expand and it has no Sources panel, which is item 4b's. Front end: `re-reads X when Back leaves a thread reopened from the list`, `adds no entry and sends no read when the thread already open is chosen again`, `adds an entry for Start a new topic, so Back returns to the thread it cleared`, `writes nothing for Start a new topic when the screen shows no turns, and still acknowledges it`, `writes nothing for Start a new topic on an empty thread the address names, so it is not left behind`, `ends at /ask with the notice still showing, and Back skips the dead address` |
| FR-12 | 5. …and links to the source document or meeting | ✅ | ✅ | **Following the link no longer loses the thread.** Back re-reads it from the server. The thread comes back with its statements and citation numbers, which stay inert until item 4b. Front end: `re-reads the thread from the server and shows its turn`, `stays on a citation followed while the next question was in flight` |

Guards D-77 requires, each with a test that a deliberate break failed: a slow read can't land after
Back (`does not let a slow read for Y replace X after Back to X`), a reply for a thread the address
no longer names is dropped (`shows a reply for X that lands after Back to Y neither in Y nor in the
address`), and the tab title stays "Ask" (`keeps the tab title "Ask" when the thread changes`).

#### Not covered by item 4a

- **A re-read thread's citations stay inert** until item 4b (D-61's gap 4).
- **Partial matches on a re-read turn.** No route returns a past turn's candidates.
- **Where the reader was.** Back lands at the top of the screen, not at the citation followed.
- **The draft question** doesn't survive leaving the screen.
- **A read failure other than 404** leaves the screen on the previous thread while the address
  names the one that failed (D-77's note).
- **A reply or read 404 landing in the one render between a Back and its commit** is judged
  against the old address (D-77's note).
- **The dashboard's recent questions** still link to `/ask`, not to their threads. That is a
  front-end follow-up to D-70 that no Stage 5 item names.
- **No real-browser check.** The tests run in jsdom through `MemoryRouter`. Following a citation
  and pressing Back in a real browser is worth one manual check in item 8's live run.

### After item 4b — 20 October 2026, on `fix/FR-12-reopened-citations`

Built in parallel against D-78 and the contract, which were committed first. The django-backend
agent built the server half and the react-frontend agent the screen. The coordinating session
reviewed both and committed them. Item 4b closes D-61's gap 4. FR-12's citation rows were ✅ at
Stage 4 for the live reply only; D-61 found all three inert on a reopened turn.

| Requirement | Clause | Before 4b | After 4b | Evidence |
|---|---|---|---|---|
| FR-12 | 4. Each citation expands to display the source passage | ✅ live, inert reopened | ✅ | **Backend:** `test_a_reopened_turns_sources_are_the_live_replys_sources` (both roles; a reopened turn's `sources` equal the live reply's, byte for byte). **Front end:** `expands a reopened turn's citation to its passage and links to its document or meeting`, `re-reads the thread from the server and shows its turn, whose citation expands and links to its source` |
| FR-12 | 5. …and links to the source document or meeting | ✅ live, none reopened | ✅ | The same two front-end tests assert the link by `href`, to a document and to a meeting |
| FR-12 | The Sources panel lists every item consulted, with its date | ✅ live, none reopened | ✅ | **Consulted, not cited (D-78, D-44).** Backend: `test_an_uncited_consulted_passage_is_in_the_reopened_panel`, `test_a_consulted_but_uncited_document_deleted_is_gone_from_the_reopened_panel` (the real `DELETE`), `test_both_roles_lose_a_consulted_source_moved_out_of_their_scope`, `test_a_demoted_reader_loses_a_consulted_source_they_may_no_longer_see_without_a_trace`, `test_an_unstamped_consulted_passage_is_shown_to_nobody`. Front end: `shows a reopened turn its Sources panel, listing a consulted item no statement cited` |
| FR-13 | Previous conversations listed and reopenable; the active thread can be cleared to begin a new topic | ⚠️ | ✅ | **A reopened turn renders as a live one.** Its citations expand and link, and it has its Sources panel. The note saying they couldn't is gone (`shows no note setting a reopened thread apart from a live one`). Reopening and clearing are item 4a's rows |

**Invariant 1, on the reopen path.** The rule that keeps a re-scoped turn byte for byte a
never-answered one now covers `sources` too:

- `test_a_re_scoped_turn_renders_exactly_as_a_never_answered_one` was strengthened so that the
  re-scoped turn consulted a passage the demoted reader can still read.
- `test_a_path_b_turn_reopens_identical_to_a_path_a_turn` checks the two no-answer paths still
  reopen identically, with the path-B row holding its supplied ids.
- `test_a_turn_stored_unanswered_never_has_its_retrieved_ids_read` checks that a path-B turn's ids
  appear in no SQL.
- `test_one_chunk_query_serves_every_turns_citations_and_sources` checks there is one scope query
  per thread.

**The provenance-removed state**, which D-62 recorded as untested at the interface, now has its
front-end test: `shows its own title and message, no statement, no Sources panel and not the
no-answer copy`. Server side: `test_a_provenance_removed_turn_carries_no_sources_though_a_consulted_passage_is_readable`.

FR-13's first row stays ⚠️ for D-42, as after item 4a. Item 4b does not change it.

#### Not covered by item 4b

- **Partial matches on a reopened no-answer turn.** Nothing records them.
- **A source dropped by D-53's fail-closed read** leaves its citation as a plain number, as on the
  live reply. This is tested: `keeps a citation's number as plain text where its passage did not
  arrive`.
- **The cost of a thread read.** A four-turn thread went from 11 queries to 20, and nothing sets a
  budget for it.
- **The front end doesn't filter `sources` on a no-answer turn.** It relies on the server sending
  `[]`, which is tested server-side, and on that branch never rendering a panel, which is not
  tested on the screen.

---

## Stage 4's deferred fixes, after item 5 — 26–27 October 2026, on `fix/FR-12-throttle-and-bounds`

Item 5 is not a clause enumeration. It closes the fixes Stage 4 deferred, and this section names
each one with its evidence, so the stage audit can find them.

| Deferred from | What | State | Evidence |
|---|---|---|---|
| D-49 | `POST /api/ask` and the ingestion POSTs were unthrottled; one ask could hold a worker for minutes | ✅ D-79 | `test_throttles.py` (each scope past its rate; ingestion one budget across three routes; creating threads; `X-Forwarded-For` not trusted), `test_ask_in_flight.py` (one ask in flight, freed after a 503 and an exception). Front end: `askLimits.test.jsx`, `ingestionLimits.test.jsx`, `authThrottle.test.jsx` |
| D-50 | PDF decompression bombs, open for PDF | ✅ D-81, with a stated residue | `apps/ingestion/tests/test_pdf_bounds.py` (each bound, with its fixture proven parsed first), `test_pdf_bomb_upload.py` (both roles), the meeting route's bound test |
| D-58, D-61's gap 12 | Empty conversations outlived the session that made them | ✅ D-80 | `test_an_empty_thread_is_absent_from_the_list_but_its_address_still_reads_it`, `test_a_thread_is_listed_once_its_first_turn_lands_answered_or_not`, `test_a_thread_whose_every_turn_is_re_scoped_stays_listed`. Front end: `askThreadList.test.jsx` |
| D-75's notes | Reprocess answered an HTML 500 for a missing file; a path outside the media folder gave a 400 | ✅ | `test_reprocessing_a_document_whose_file_is_gone_from_disk_is_a_422_and_is_logged`, `test_reprocessing_a_file_path_outside_the_media_folder_is_a_422_and_is_logged`, `test_a_file_path_outside_the_media_folder_is_the_out_of_scope_404_and_is_logged` |
| PR #30 | NFR-08 and NFR-09 load tests, which would collide with the new limits | Ready, never run | D-82. The k6 scripts were run only in a Node simulation; k6 is not installed |

#### Not covered by item 5

- **Many users at once** can still hold every Waitress thread. The in-flight slot is per user.
- **The question's embedding has no timeout of its own** (D-79's note), so one ask can take about
  46 minutes in the worst case.
- **The PDF residue.** One page is bounded only by the caps times about 67 in memory, and the time
  worst case is about 75 s. Encrypted PDFs are untested.
- **Load-test cleanup.** One NFR-09 run leaves up to 1,210 documents behind.
- **Objective 03** has not been run against these limits.

---

## The Upload screen's findings, after item 6 — 28 October 2026, on `fix/FR-12-remeasure-objective-02`

Item 6 measures; it is not a clause enumeration. Building D-85's screens found four defects on
FR-08's Upload screen (D-85's built note). Three are fixed before the measured run (D-85's
follow-up note), and the fourth is left for item 8.

| Found | State | Evidence |
|---|---|---|
| A file removed from the queue while it ran was still uploaded, and an Employee could not delete it afterwards (D-73) | ✅ | Front end (`uploadQueue.test.jsx`): `holds a queued file's title and Remove until the queue finishes, then an edit and a removal both take effect` |
| A queued file's title edited while the queue ran was ignored | ✅ | The same test |
| A successful retry still offered "Try again", which answered 409 | ✅ | `withdraws Try again once the retry has indexed the document, as an upload that succeeds first time offers none` |
| The client's copies of the in-flight codes could drift from the server's | ✅ | **Backend** (`apps/api/tests/test_in_flight_codes_agreement.py`): `test_the_clients_copy_of_each_in_flight_code_equals_the_one_the_server_sends`, once per code, and `test_every_code_the_client_exports_is_a_server_constant_with_the_same_value` |

#### Not covered after item 6

- **Leaving the Upload screen mid-queue doesn't stop the queue.** The remaining files are still
  sent, and their outcomes are shown nowhere, because the screen is gone. Until they finish, the
  user's next upload, transcript or reprocess gets D-85's in-flight 429. Worth one manual check in
  item 8's live run: start a queue of three files, open the repository while the first is still
  processing, and confirm that all three arrive and that an upload sent meanwhile shows the
  in-flight sentence.
- **A Remove pressed in the same instant as Upload**, before the screen re-renders, would still be
  uploaded. The hold is the `disabled` attribute (D-85's follow-up note).

## After item 10 (2 November 2026)

Item 10's audit returned INCOMPLETE (D-90), and the user's decisions of 2 November answer it.
This section records what changes in this audit's rows. The rows above stay as written on their
day.

| Requirement | Clause | Before | After item 10 | Evidence |
|---|---|---|---|---|
| FR-13 | A conversational interface reachable from any page, retaining the thread so follow-ups need not restate the subject | ⚠️ for D-42 | ⚠️ **for the screen's reason, pending step 5** | The 1 November screen, rescored with the frozen rule: in the three clean cases (t01, t04, and t06 as the Administrator), a follow-up whose referent is named in the first question was not correct on any trial (D-91). That contradicts D-42's boundary (D-42's dated note). The measured reason is step 5's run: history, cold and spelled out, then the HTTP check. Until then, this row rests on an informal look, not a measurement |
| FR-02 | Five failed attempts lock the account for 15 minutes; a locked account gets 403 and a distinct message | not walked | ⚠️ **left out of the 1 November walk** | The script called the lockout FR-03, and the walk followed it (D-25's dated note; item 10's H2). The server side is tested (`test_login.py`). The front-end message is step 6's (D-94), and the live demonstration is step 3's extra recorded walk |

- **The lockout is FR-02's** (D-25). `CLAUDE.md:185` is corrected.
- **FR-13's per-turn re-scoping is evidenced by test,** not by the walk:
  `apps/api/tests/test_fr11_scoping.py:608` (a promotion between turns takes effect on the next
  turn) and `:633` (a demotion between turns takes effect on the next turn). Two sessions in two
  roles show the scope differing. They cannot show it being re-evaluated.

## After step 3 (3 November 2026)

Step 3's lockout walk on the alpha, recorded in `docs/stage-5-item-8-walk.md`'s 3 November notes.
The rows above stay as written on their day.

| Requirement | Clause | Before | After step 3 | Evidence |
|---|---|---|---|---|
| FR-02 | Five failed attempts lock the account for 15 minutes; a locked account gets 403 and a distinct message | ⚠️ left out of the 1 November walk | ✅ **walked live** | A throwaway account: five wrong passwords locked it; the right password during the lock showed the locked-account message; the right password after expiry signed in and reset the counters. The front-end message's test is step 6's (`login.test.jsx`, PR #44) |
| FR-04 | "…redirected to the Login page with a brief confirmation 'You've been logged out'" | ✅ in the 1 November walk, which recorded the redirect only | ❌ **the confirmation does not appear** | Found by step 6 in the front-end suite (PR #44, defect 1), and confirmed in a browser at the end of step 3's walk. The redirect, and the session ending on the server, still stand. The fix is the user's decision |

## After the FR-04 fix (3 November 2026)

PR #46, D-97. The rows above stay as written on their day.

| Requirement | Clause | Before | After the fix | Evidence |
|---|---|---|---|---|
| FR-04 | "…redirected to the Login page with a brief confirmation 'You've been logged out'" | ❌ the confirmation does not appear | ✅ **on `main`, by test**; not yet shown in a browser | `frontend/tests/authNotices.test.jsx` asserts the confirmation for both roles. It failed on the earlier `main` in 10 runs out of 10, and passes with the fix. The alpha runs `8598d19`, from before the fix, until it is redeployed after the D-35 recording |

## After step 5 (3 November 2026)

FR-13's "before": D-86's measurement, run at `2f65a8e` on `kmp_obj02_20261101`
(`corpus/objective-02/runs/2026-11-03/fr13-before.md`). The rows above stay as written on their day.

| Requirement | Clause | Before | After step 5 | Evidence |
|---|---|---|---|---|
| FR-13 | A conversational interface reachable from any page, retaining the thread so follow-ups need not restate the subject | ⚠️ for the screen's reason, pending step 5 (an informal look) | ⚠️ **partial, measured** | **Wired:** the history changes what is retrieved, both in-process and through the server (HTTP check: WIRED 3 of 3, 0 leaks). **Not answered:** with history, 1 of 9 answerable follow-ups matched, and that one (t08) is cold-answerable. Spelled out, 3 of 9 matched; cold, 1 of 9. 7 of the 9 other answered with-history replies restate the first turn. Where spelling the question out works and history does not (t01, t05), history is the limit. Where spelling it out fails too (t02, t03, t04, t06 and t07 as the Administrator, t09), the limit is generation or retrieval as well. t09 failed, as D-86 decision 2 expected. Out-of-scope passages: 0 in every run. The two Employee follow-ups that should get no answer (t06, t07) were answered by restating the first turn, from material the Employee may read: not a leak |

## After the re-audit (11 November 2026)

FR-13, re-audited after D-122 made `anthropic` the default provider: one `requirements-auditor`
run, read only, at `bd95f92`, over every FR-13 clause. Its verdict is INCOMPLETE, and D-112's dated
note of 11 November records it verbatim. No measurement was made for it. `main` has since moved to
`23e6e65`, by #85 and #86, which add only run folders under `corpus/objective-05/` and
`corpus/objective-06/`. The rows above stay as written on their day.

| Requirement | Clause | Before | After the re-audit | Evidence |
|---|---|---|---|---|
| FR-13 | A conversational interface reachable from any page, retaining the thread so follow-ups need not restate the subject | ⚠️ partial, measured (after step 5) | ⚠️ **partial on both providers, each for its own reason; and "reachable from any page" has no front-end test** | **`flm`, the offline alternative: partial, the deviation D-112 accepted for NIT3003.** With history, 2 of 9, 3 of 9 and 2 of 9 on `main` run on FLM (`corpus/objective-02/runs/2026-11-08/after-030/`, `runs/2026-11-09/fr13-phase3/` and `runs/2026-11-09/fr13-phase4/`). Spelled out, 6 of 9 each time. 0 leaks. The deployed alpha (`8598d19`) runs the answer path measured in "After step 5", 1 of 9. **`anthropic`, the default since D-122: partial and unconfirmed, so not recorded as met.** With history, 9 of 9 on Claude Haiku 5.5 (`runs/2026-11-10/haiku/threads.json`, at `e04aab1`) and 9 of 9 on Sonnet 5.5 (`runs/2026-11-10/voyage-frozen/threads.json`, at `54f15cc`). Each model ran once. On both: spelled out 9 of 9, cold 1 of 9, first turn 11 of 11, 0 leaks and 0 fabricated identifiers. Through the server, on Sonnet only: WIRED 3 of 3, with turn two correct 3 of 3 (`runs/2026-11-10/voyage-http-check/`, at `58b9c27`). No noise band has been measured on this provider. D-115 says FLM's band is not carried over to it, and D-112 says the same of its acceptance. **What the 9 of 9 does not show:** t08 is cold-answerable. t09 matched because the joined questions retrieved D17, which names the facilities team itself; the earlier answer was not used (D-42). **"Reachable from any page":** the link is built (`frontend/src/App.jsx:72`), and no test in `frontend/tests` asserts it (§8 condition 2, D-62) |
| FR-13 | Maintains conversation context per session and passes prior turns alongside the new question so that pronouns and abbreviated references resolve correctly | ⚠️ at Stage 4, for D-42 (`docs/stage-4-clause-audit.md:86`); not restated in this file | ⚠️ **declined in part on both providers (D-42); whether references resolve differs by provider** | **Prior questions only, on both providers (D-42).** `apps/retrieval/conversation.py:164-168` reads each earlier turn's `question`, and no answer re-enters a prompt. No frozen follow-up has a referent that is only in an earlier answer and in no passage the joined questions retrieve, so that cost is untested on both. **"So that pronouns and abbreviated references resolve correctly":** by provider, as in this table's Front-End row. The frozen follow-ups use pronouns and demonstratives. None uses a shortened name or an acronym, and no thread is longer than two turns. **"Per session"** is read as per conversation: the history is read from `QueryLog` by conversation and by user, so it outlives a login session |
| FR-13 | Database: Conversations (Create, Read, Update); QueryLog (Create) | ⚠️ at Stage 4: Update has no mutating verb (D-43) | ⚠️ **unchanged, as a recorded deviation (D-43); the re-audit read the operations as satisfied** | The re-audit's words: "Satisfied as database operations. There is no client rename route (D-43)". The title is derived from the first question, and `last_updated_at` moves on every turn (`apps/retrieval/query_log.py:294-299`). Tests: `apps/api/tests/test_conversations.py:137`, `:150`, `:161`, `:172` and `:228`. Stage 4's row expected an auditor to flag the missing `PATCH`, and this one did not. The state stays ⚠️ because the demonstration script presents D-43 as a deviation, never a tick |

- **Every other FR-13 clause was read as satisfied, as it stood before:**
  - previous conversations listed and reopenable, and the active thread cleared for a new topic
    (✅ since item 4b);
  - context truncated to `MAXIMUM_CONVERSATION_TURNS`;
  - FR-11's scope re-evaluated on every turn;
  - a fresh retrieval on every turn;
  - generation and citation verification following FR-12 unchanged;
  - the 200 with the answer and the updated conversation state.

  Those from the truncation to the 200 were ✅ at Stage 4 (`docs/stage-4-clause-audit.md:87-91`).
  The re-audit's clause table, with each clause's code and tests, is in D-112's note.
- **The re-scoping tests have moved.** "After item 10" cites
  `apps/api/tests/test_fr11_scoping.py:608` and `:633`. At `bd95f92` the same tests begin at `:610`
  and `:635`.
- **Decided by the user on 11 November** (D-112's note):
  - **The draws come later, as a task of their own:** two further Haiku draws of the frozen nine,
    and one HTTP check on Haiku, with the pass rule committed before the first draw. Until they are
    read, the `anthropic` cells above stand as written.
  - **The records the verdict lists as stale are fixed in a follow-up pull request.**
- **Not owned yet:** the front-end test for the Ask link.
- **Stage 5's exit criterion** (`M6-BUILD-PROMPT.md`'s Done line) admits FR-13's deviation "on the
  FLM build" only. Its wording is the user's, and it is not changed here.

#### Not covered by the re-audit

- **No new measurement.** It read the records of 3, 8, 9 and 10 November, and ran no suite,
  server, database or provider.
- **Haiku through the server.** The HTTP check on this provider ran on Sonnet.
- **A reference into an earlier answer,** on either provider. No frozen follow-up tests it.
- **A shortened name or an acronym** as the reference, and **a thread longer than two turns.**
- **The suites were not run by the auditor.** CI was green on `bd95f92` (run 42932385814).
- **Which database the deployed alpha serves.** The auditor read no `.env`, and checked the alpha's
  commit only.
