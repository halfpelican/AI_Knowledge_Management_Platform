/**
 * Document endpoints (FR-08, and the list FR-15 builds its filtered browsing on
 * in Stage 5), per docs/api-contract.md. Thin wrappers over the one API client;
 * no fetch and no XMLHttpRequest here.
 */
import { get, post, upload } from './client.js'

/**
 * Any signed-in user. 200 [document object], newest first, scoped by
 * `visible_to_roles` — the list never discloses a document outside the caller's
 * scope, not by a row and not by a count (CLAUDE.md §6, invariant 1).
 */
export function listDocuments(options = {}) {
  return get('/documents', options)
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
