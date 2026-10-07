/**
 * Document endpoints (FR-08 upload and retry, FR-15 browse, detail and delete),
 * per docs/api-contract.md. Thin wrappers over the one API client; no fetch and
 * no XMLHttpRequest here.
 */
import { del, get, post, upload } from './client.js'

/*
 * There is no wrapper for `GET /api/documents`, the bare list. The repository
 * screen was its only reader, and it reads `browseDocuments` below since FR-15;
 * the upload screen never read it. The route stays on the server (D-72) and a
 * wrapper can come back with its first caller.
 */

/* ---- FR-15 browse -------------------------------------------------------- */

/**
 * The browse filters, in the contract's own names and order. They combine with
 * AND, and any one of them set is what makes "nothing matched" a 204 (D-72).
 */
export const BROWSE_FILTER_KEYS = ['q', 'status', 'department', 'project', 'process', 'topic']

/**
 * The four browse dimensions FR-15 names, each with a facet in the reply.
 * Department is the document's column and the other three are tag dimensions
 * (D-72); to the screen they are four facets alike.
 */
export const BROWSE_DIMENSIONS = ['department', 'project', 'process', 'topic']

/** Every query parameter the route reads: the filters, then `sort`, which is not a filter. */
export const BROWSE_PARAM_KEYS = [...BROWSE_FILTER_KEYS, 'sort']

/** The fields `sort` accepts, each ascending as named or descending with a leading `-`. */
export const BROWSE_SORT_FIELDS = ['title', 'file_type', 'uploaded_by', 'uploaded_at', 'status']

/** The server's order when `sort` is absent: newest first (the contract). */
export const BROWSE_DEFAULT_SORT = '-uploaded_at'

/**
 * `GET /api/documents/browse?q=&status=&department=&project=&process=&topic=&sort=`
 * — the repository screen's one request: the filtered, sorted list and the
 * facets to browse it by.
 *
 * 200 `{filters, facets, documents}`, including when no filter is set and
 * nothing is in scope. **204, with no body, when at least one filter is set and
 * nothing in the caller's scope matches**, which this resolves to `null`: a 200
 * always carries an object, so `null` can only mean the 204. A 204 carries no
 * facets, and the screen must not borrow any from an earlier reply (D-72). 400
 * `{"<parameter>": ["..."]}` for a `status` or `sort` outside its vocabulary, a
 * NUL byte or a value over 255 characters (D-65); 401 for no session.
 *
 * Every value and count arrives already scoped to the caller's role (CLAUDE.md
 * §6, invariant 1). An empty value is the same as an absent one (the contract),
 * so only the parameters carrying a value are sent, in the contract's order.
 *
 * @param {Partial<Record<'q'|'status'|'department'|'project'|'process'|'topic'|'sort', string>>} params
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<object|null>} The browse object, or null for the 204.
 */
export async function browseDocuments(params = {}, options = {}) {
  const search = new URLSearchParams()
  for (const key of BROWSE_PARAM_KEYS) {
    if (params[key]) search.set(key, params[key])
  }
  const query = search.toString()
  const body = await get(query ? `/documents/browse?${query}` : '/documents/browse', options)
  return body ?? null
}

/**
 * `DELETE /api/documents/{id}` — FR-15's deletion. Session plus
 * `manage_documents`, which is Administrator-only (D-73).
 *
 * 204 with no body: the document, its extracted content, its chunks and its tag
 * links are gone, in one transaction. 404 for an unknown document or one outside
 * the caller's scope, checked **before** the permission so the code never says
 * whether a document the caller cannot see exists; 403 for a document in scope
 * and a role without `manage_documents`; 401 for no session.
 *
 * The detail's `can_delete` decides only whether the screen offers the control.
 * The server checks the permission on every call whatever the screen showed
 * (CLAUDE.md §6, invariant 4).
 */
export function deleteDocument(docId, options = {}) {
  return del(`/documents/${encodeURIComponent(docId)}`, options)
}

/**
 * One document — FR-15's detail view, and the route a citation links to (D-46,
 * Stage 4 item 10b).
 *
 * Any signed-in user, scoped by `visible_to_roles`. The body is the document
 * object with three detail fields (D-63, D-73):
 *
 * - `extracted_text` — the document's whole extracted text, or `null` where it
 *   has no extracted content. Plain text from the file: untrusted, and rendered
 *   as text, never as HTML. The screen keys its empty state on `null`, not on
 *   the status.
 * - `tags` — `{project: [...], process: [...], topic: [...]}`. Department is the
 *   document's own `department` field (D-72).
 * - `can_delete` — whether the caller's role holds `manage_documents`. It decides
 *   only whether the screen offers the control (CLAUDE.md §6, invariant 4).
 *
 * 404 both for an id that names nothing and for a document outside the caller's
 * scope, so a refusal does not confirm that the id names something real
 * (CLAUDE.md §6, invariant 1).
 */
export function fetchDocument(docId, options = {}) {
  return get(`/documents/${encodeURIComponent(docId)}`, options)
}

/**
 * FR-08 upload. `multipart/form-data`, the one endpoint that is not JSON.
 *
 * 201 with the document object, whose `status` is "Indexed" or "Partially
 * indexed"; 400 an empty title or an unknown role; 403 the role lacks
 * `contribute_content`; 409 a document with the same content already exists;
 * 413 over 50 MB; 415 the file signature is not one of the four accepted
 * formats; 422 the file was stored but nothing could be extracted or indexed —
 * that body still carries `doc_id` and `status`, which is what FR-08's
 * "Processing failed. Please try again" action displays.
 *
 * @param {object} fields
 * @param {File} fields.file
 * @param {string} fields.title Required, non-blank.
 * @param {string} [fields.department]
 * @param {string[]|null} [fields.visibleToRoles] Omitted or null sends no field
 *   at all, which the server reads as both roles (D-29).
 * @param {object} [options]
 * @param {(percent: number) => void} [options.onProgress] 0–100 during transfer.
 * @param {AbortSignal} [options.signal]
 */
export function uploadDocument({ file, title, department, visibleToRoles }, options = {}) {
  const body = new FormData()
  body.append('file', file)
  body.append('title', title)
  if (department) body.append('department', department)
  // A repeated field, one entry per role name, which is how DRF reads a ListField
  // out of multipart. Sent only when a scope was chosen: see D-29 above.
  if (visibleToRoles) for (const role of visibleToRoles) body.append('visible_to_roles', role)
  return upload('/documents', body, options)
}

/**
 * FR-08's "Processing failed. Please try again" action (D-32).
 *
 * Re-runs ingestion against the original already stored under MEDIA_ROOT; it does
 * NOT send the file again. The server kept those bytes when the first attempt
 * failed (CLAUDE.md §6, invariant 8), and a re-upload would create a second row
 * per attempt — three retries would leave three near-identical entries in the
 * repository list.
 *
 * 201 with the document, now "Indexed" or "Partially indexed"; 409 already
 * indexed, or a copy was indexed meanwhile; 422 it failed the same way again,
 * which is what a file with no text layer will always do.
 */
export function reprocessDocument(docId, options = {}) {
  return post(`/documents/${encodeURIComponent(docId)}/reprocess`, {}, options)
}
