/**
 * FR-10's department list (D-129): the departments the AI may suggest for a document,
 * the scheme's fourth dimension beside Project, Process and Topic, kept by an
 * Administrator on the Tags page. Thin wrappers over the one API client; no fetch and no
 * XMLHttpRequest here.
 *
 * Every route needs a session **and** `manage_tags`, which accounts 0008 gives the
 * Administrator alone: 401 without a session, 403 for a role that lacks the code,
 * checked before anything else on the request, as on `/api/tags`. The screen that calls
 * these is offered to an Administrator only, and that is usability: the server checks
 * the code on every request whatever the interface showed (CLAUDE.md §6, invariant 4).
 *
 * The list supplies the AI's choices and nothing else. `Documents.department` stays the
 * one field FR-14 and FR-15 read (D-72), and the upload form still takes any department,
 * so nothing here changes a document.
 */
import { get, requestWithStatus } from './client.js'

/**
 * `GET /api/departments` — every department in the list, active or retired, ordered by
 * name without regard to case. The order is the server's, and the screen keeps it.
 *
 * 200 with a list of `{department_id, name, active, item_count}`, `[]` for none, no
 * pagination. `item_count` is the number of documents whose department is that name. It
 * is not scoped, because the one role that may ask reads every document (D-66). 401; 403.
 *
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function listDepartments(options = {}) {
  return get('/departments', options)
}

/**
 * `POST /api/departments` — an Administrator adds a department to the list. Body
 * `{name}`; the server trims the name and single-spaces it, and keeps its case.
 *
 * - 201 with the new entry, `{department_id, name, active: true, item_count}`. It is
 *   vocabulary: offered to the AI for every document, whatever the document's audience.
 *   `item_count` need not be 0, since the upload form takes any department.
 * - 200 with the entry, active again, for the name of a retired department. This is the
 *   one way a retired department comes back.
 * - 409 `{detail, department_id}` for the name of an active department, compared without
 *   regard to case, and for a concurrent add of the same name; nothing is changed.
 *   `error.details.department_id` is that department.
 * - 400 `{name: [...]}` for a blank name or one over 255 characters.
 * - 429 past the `tagging` limit, which adding a tag counts against too, with
 *   `error.retryAfter`.
 * - 403 without `manage_tags`; 401.
 *
 * @param {{name: string}} department
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<{reactivated: boolean, department: object|null}>} `reactivated` is the
 *   200; `department` is the reply's entry, whichever of the two it was.
 */
export async function createDepartment({ name }, options = {}) {
  const { status, data } = await requestWithStatus('/departments', { ...options, method: 'POST', body: { name } })
  return { reactivated: status === 200, department: data && typeof data === 'object' ? data : null }
}

/**
 * `DELETE /api/departments/{id}` — the user's decision of 13 November 2026: "Retiring
 * keeps the department on its documents".
 *
 * 200 with the entry, now `active: false`, when any document has the department: it is
 * retired, stays on those documents and in FR-14's and FR-15's filters, and the AI no
 * longer suggests it; 200 again for one already retired that documents still have. 204,
 * no body, when no document has it: it is deleted. 404 `{"detail": "No Department
 * matches the given query."}` for an id naming none; 403 before the id is looked at;
 * 401.
 *
 * @param {string} departmentId
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<{deleted: true} | {deleted: false, department: object|null}>}
 *   `deleted` is the 204; otherwise `department` is the 200's entry.
 */
export async function deleteDepartment(departmentId, options = {}) {
  const { status, data } = await requestWithStatus(`/departments/${encodeURIComponent(departmentId)}`, {
    ...options,
    method: 'DELETE',
  })
  return status === 204 ? { deleted: true } : { deleted: false, department: data }
}
