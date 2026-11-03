# Stage 5 item 9a: the FR-14 and FR-15 leakage tests, mapped and broken deliberately, 2–3 November 2026

`M6-BUILD-PROMPT.md` item 9a asks for five things:

1. An Employee's dashboard totals and browse-facet counts are identical with and without
   Administrator-only documents in the database.
2. After a delete, a question whose only answer lived in that document returns no-answer, and none
   of its chunks remain.
3. An unknown department and a restricted-only one return the same 204 on FR-15's browse, and the
   same 200 payload on FR-14's dashboard, which lists no 204.
4. An Administrator can delete a document visible only to Employees (D-66).
5. The dual-role matrix stays at 100% with the new routes.

The user's instruction for this step: "Map each of its five bullets to the test that already
covers it, break each one deliberately, and add only what is missing. A test written just to give
9a a commit of its own is a manufactured finding."

Item 10's auditor reported that "all five of 9a's assertions already exist in item 2 and item 3
tests (for example `test_document_delete.py:206`)". This record checks that claim rather than
taking it as given. **Four of the five held. Bullet 2 held only for a document of one chunk**, and
a deliberate break showed what that missed (below). `test_document_delete.py:206` was bullet 4's
test before this commit; it is at line 215 now.

## How each break was made

- **What was broken:** product code only, never a test. Each break is a single, exact,
  once-only text replacement, applied by a script rather than by hand.
- **Restoring:** before any break, the four files that could be touched were copied aside and
  their SHA-256 recorded:
  - `apps/api/views.py`
  - `apps/api/repository.py`
  - `apps/documents/deletion.py`
  - `apps/api/urls.py`
  After every break, all four were copied back and their hashes checked against those
  recorded values, and all four matched every time. This commit changes none of them.
- **Baseline:** on the clean tree, before any break, the four mapped files
  (`test_dashboard.py`, `test_document_browse.py`, `test_document_delete.py`,
  `apps/documents/tests/test_deletion.py`) gave **256 passed**.
- **Line numbers:** given as they are at this commit.

## The five bullets

| # | Covering tests | What they assert, and whether it is the whole bullet | Break applied to product code | Result |
|---|---|---|---|---|
| 1 | `test_dashboard.py::test_an_employees_payload_is_byte_identical_with_and_without_restricted_rows` (L265; no filter, shared department, restricted department, date range) | The Employee's whole dashboard response, as bytes, is unchanged after Administrator-only documents (one Indexed, one Processing), an Administrator-only meeting and the Administrator's own question are added. The totals are inside those bytes. Mirror: the Administrator's payload does change. **Whole bullet, dashboard half.** | **1a.** The documents figure is counted over every document, with the same date and department filters but no scope. **1b.** The same for the meetings figure. | 1a: 3 of the 4 cases fail (`shared-department` passes, see note 1). 1b: all 4 fail. |
| 1 | `test_document_browse.py::test_an_employees_browse_payload_is_byte_identical_with_and_without_restricted_documents_and_tags` (L291; 7 cases) | The Employee's whole browse response (status and bytes) is unchanged after two Administrator-only documents are added. Those documents carry the shared department, a shared project and a shared topic, as well as values of their own. Mirror: the Administrator's response does change. **Whole bullet, browse half.** | **1c.** Tag facet counts leak, but the values do not: the values still come from the scoped documents, and each value's count is taken over every document that carries it. **1d.** The same for the Department facet. | 1c: 5 of the 7 cases fail. 1d: 5 of the 7 cases fail. Both include the unfiltered case, where scope is the only possible difference. The two `restricted-*` cases are 204 before and after, so they have no facets to compare. |
| 1 | Supporting tests, from both roles: `test_dashboard.py` L191 and L233; `test_document_browse.py` L186 and L237 | Absolute figures with the restricted rows present: the Employee sees `{1, 1, 2}`, the Administrator `{2, 2, 4}`, and facet counts are 1 where a leak would make them 2. | (the same breaks) | L191 and L233 fail under 1a and 1b. L186 and L237 fail under 1c. They do not fail under 1d, because no restricted document in their fixtures shares a department with a readable one. |
| 2 | `test_document_delete.py::test_after_a_delete_search_finds_nothing_and_a_question_only_it_answered_takes_path_a` (L317) | From both roles, the question is answered before the delete. After it: `answered` is false, the no-answer message is returned, statements, sources and partial matches are empty, the `QueryLog` reason is path A (`NO_RELEVANT_PASSAGE`), and generation is not called again. **The no-answer half.** | **2a.** `delete_document` leaves every chunk. | Fails, along with every row-level check below. |
| 2 | `test_document_delete.py::test_an_administrator_deletes_a_document_and_everything_derived_from_it` (L178), L199, L215; `apps/documents/tests/test_deletion.py::test_the_document_and_everything_derived_from_it_is_deleted` (L85), and the other tests in that file that check the rows are gone (L96, L132, L148, L170, L183) | No `ContentChunk` row for the document remains, with the document, its extracted content and its tag links. **The chunks half, but only for a document of one chunk:** every fixture in both files gives the document exactly one chunk, at `chunk_index` 0. | **2b.** `delete_document` deletes only the chunk at `chunk_index` 0. | **All 76 tests that reach the delete pass** (`test_document_delete.py`, `test_deletion.py`, `test_never_cache.py`, `test_source_rows_fail_closed.py`). **This was the gap.** |
| 2 | **Added:** `test_document_delete.py::test_after_a_delete_a_question_answered_from_a_later_chunk_takes_path_a_and_no_chunk_remains` (L368) | A document of three chunks, with its only above-threshold passage in the middle one. Before the delete, both roles have the question answered, citing chunk 1. After an Administrator deletes it: both roles get no-answer path A, generation is not called, nothing of the passage or chunk is in the response, and **none of the three chunks remains**. **Whole bullet.** | 2b, 2c and 2a. | **2b:** fails at L403, `answered is False`. The deleted document went on answering from its surviving middle chunk. **2c** (soft delete: chunks re-stamped `[]` rather than deleted): every no-answer assertion passes, and it fails at L414, "no chunk remains". **2a:** fails. |
| 3 | `test_document_browse.py::test_an_unknown_and_a_restricted_only_value_give_the_same_204` (L618; department, project, process and topic, from both roles) | An unknown value and a value found only on a document the caller cannot read both get 204, with the same empty body. **Whole bullet, browse half** (and the three tag dimensions besides). Also `byte_identical[restricted-department]` (L291): the same value is a 204 before the restricted documents exist and after. | **3a.** Browse looks the department up outside scope, and answers 403 instead of 204 when it exists anywhere. | Fails for `department`, from both roles. `byte_identical[restricted-department]` fails too. So does `test_a_filter_that_matches_nothing_is_204_with_no_body[combination]` (L598), because its department exists. |
| 3 | `test_dashboard.py::test_an_unknown_and_a_restricted_only_department_give_the_same_payload` (L365, from both roles) | Both are 200. The parsed payloads are equal once the echoed `filters.department` is removed (see note 3). The documents list is empty and the documents figure is 0. The restricted title is not in the bytes. **Whole bullet, dashboard half.** "Lists no 204" is the asserted 200 here, and also in `test_departments_are_not_narrowed_by_the_active_filters` (L313), where a filter combination matches no document. | **3b.** The dashboard answers 204 when a department filter matches no document: the browse shape, which FR-14 does not list. **3c.** A restricted department that is asked for is added to `departments`, which tells the caller it exists. | 3b fails: L365 from both roles (`204 == 200`), L313 from both roles, `byte_identical[restricted-department]`, and `test_the_boundary_values_are_accepted`. 3c fails: L365 from both roles, and `byte_identical[restricted-department]`. |
| 4 | `test_document_delete.py::test_an_administrator_can_delete_a_document_visible_only_to_employees` (L215) | The Administrator's `DELETE` of a document stamped `[Employee]` gets 204. The document, its extracted content, its chunks and its tag links are all gone. **Whole bullet.** | **4.** The delete resolves the document by the role's own name in `visible_to_roles` (the reading before D-66), instead of `scoped_document_or_404`. | Fails: `404 == 204`. The D-53 static scan (`test_source_rows_fail_closed.py`) fails as well, but only because this break wrote the predicate in `views.py`. L215 is the test that answers for D-66. |
| 5 | The matrix itself (`apps/api/tests/dual_role_matrix.py`) and `test_dual_role_matrix.py` (incl. `test_incomplete_coverage_fails_an_otherwise_green_full_run`, L154) | Every `/api/` route and method is enumerated from the URL conf. A full run fails below 100%. **Both full runs: `23/23` (100.0%)**, with each of the four Stage 5 routes reached from both roles (see "The full suite"). | **5.** A protected route, `GET /api/dashboard/unexercised`, is added to `apps/api/urls.py` with no test. | A partial run reported it `MISSING` from both roles (`17/24`). It was not enforced, because the run was partial (see note 4). Two independent guards also failed: `test_rbac.py::test_the_url_conf_is_exactly_the_contract` and `test_source_rows_fail_closed.py::test_every_route_is_classified_by_whether_it_returns_source_rows`. |

### Notes

1. **Break 1a and the `shared-department` case.** Under 1a, the `shared-department` case of
   L265 passes. The only Administrator-only document in the shared department is "Processing",
   and the indexed figure excludes that status by design (D-70), so a leak in the figure has
   nothing to count there. The other three cases catch 1a, and so do L191, L233 and L365. This is
   not a gap in the bullet. It does mean that case is weaker for totals than for the recent lists.
2. **Breaks 1c and 1d also ignore the other filters** when they count, which is why some filtered
   facet tests fail as well. The unfiltered case of L291 is where the evidence for the bullet
   lies: there, scope is the only difference between the two counts.
3. **"The same 200 payload" on the dashboard** is the same payload apart from `filters.department`,
   which echoes the caller's own value (D-65). The two bodies are not, and should not be, byte for
   byte equal. L365 removes that one key and compares everything else.
4. **Break 5 was shown on a partial run,** where the matrix reports but does not enforce. That a
   full run fails below 100% is tested as a unit (`exit_status_for`, L154). It was not shown
   again by a second full run with the break in place.

## The test added

There is one test, `test_after_a_delete_a_question_answered_from_a_later_chunk_takes_path_a_and_no_chunk_remains`
(`apps/api/tests/test_document_delete.py`, L368), and it is added because of break 2b. Every
existing delete test gives the document a single chunk, so a delete that removed only the first
chunk passed all 76 tests that reach the delete.

What a leftover chunk does is the reason it matters. It keeps its own `visible_to_roles` stamp,
so it is still retrieved. Failing closed on the deleted source row removes it from `sources` and
`partial_matches` but not from what generation is sent (this is the stated boundary in
`test_source_rows_fail_closed.py`'s docstring). So under 2b, an Employee asking the question
after the delete **still got an answer from the deleted document**. A real document longer than
`CHUNK_SIZE` is ingested as several chunks, so this is the normal case and not an edge case.

The test was shown failing under three breaks:

- **2b:** at L403, the answer was still given after the delete;
- **2c:** at L414, chunks remained, while every no-answer assertion passed;
- **2a:** fails.

So each half of the bullet catches a break the other half does not. On the clean tree it passed
eight runs in a row.

To build the three-chunk document, the file's `stored_document` helper gained an optional
`chunks` argument. Without that argument it writes exactly the same rows as before: one chunk at
index 0, and extracted text equal to `text`. The other 13 tests in the file pass unchanged.

Nothing else was added. Bullets 1, 3 and 4 were fully covered and each break was caught.
Bullet 5 is evidence from the full run.

## The full suite

Both runs were full runs, so the matrix was enforced. Both used this commit's tree, on
`test_kmp_step4`.

The first run started at about 20:46 (+11:00) on 2 November, after the test above was last
edited at 20:44. It completed, but the session was then cut off by a usage limit, so the result
was not picked up at the time. The second run was made on 3 November at the coordinating
session's request. It gave the same result:

| Run | Result | Exit |
|---|---|---|
| 1 | `2233 passed in 577.21s (0:09:37)` | 0 |
| 2 | `2233 passed in 1004.76s (0:16:44)` | 0 |

Both include the one test added here. No full run was made on the tree without it, so no "before"
total is claimed.

**Bullet 5**, quoted from both runs:

```
Dual-role coverage: 23/23 protected endpoints exercised from both Employee and Administrator sessions (100.0%)
```

The matrix rows for the routes Stage 5 added (items 2, 2a and 3), from the second run:

```
METHOD  PATH                                NAME                 ANONYMOUS       EMPLOYEE                                     ADMINISTRATOR
GET     /api/documents/browse               document-browse      401 (5 tests)   200,204,400 (93 tests)                       200,204,400 (93 tests)
GET     /api/documents/<uuid:pk>/download   document-download    401 (5 tests)   200,404 (34 tests)                           200,404 (33 tests)
DELETE  /api/documents/<uuid:pk>            document-detail      401 (5 tests)   403,404 (8 tests)                            204,403,404 (15 tests)
GET     /api/dashboard                      dashboard            401 (5 tests)   200,400,500 (40 tests)                       200,400,500 (40 tests)
```

- **The dashboard's `500`** comes from `apps/api/tests/test_production_settings.py`, which forces an
  exception to test the production error handler (`Client(raise_request_exception=False)`). It
  is deliberate, and it predates this item.
- **The `DELETE` row** shows the Employee's 403 and 404, and the Administrator's 204, 403 and
  404, all from passing tests.

**`python manage.py makemigrations --check --dry-run`:** `No changes detected`, exit 0. It
printed two warnings, and neither bears on whether the models and migrations agree:

- the system check reported FLM unreachable, because no server was running and the suite stubs
  the provider;
- Django could not read the migration history from `kmp_step4`, because that database has not
  been created in this worktree.

## Not covered by this item

- **The front-end suite (`npm test` in `frontend/`) was not run in this worktree.** It has no
  `node_modules`, and installing was out of scope for this step. No file under `frontend/`
  changed.
- **9a's five bullets are all server-side.** The interface clauses of FR-14 and FR-15 belong to
  the front-end suite (D-62), and this item does not speak for them.
