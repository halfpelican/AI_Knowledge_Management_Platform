/**
 * Document endpoints (FR-08 upload and retry, FR-10 classification and tags, FR-15
 * browse, detail, download and delete), per docs/api-contract.md. Thin wrappers over
 * the one API client; no
 * fetch and no XMLHttpRequest here.
 */
import { apiUrl, del, get, post, requestWithStatus, upload } from './client.js'

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
 * The address of `GET /api/documents/{id}/download` — FR-15's download link
 * (D-75). An address and not a request: the detail view puts it on a plain
 * `<a download>`, and the browser follows it with the session cookie, as it does
 * for any same-origin link (D-21). Nothing here reads the bytes.
 *
 * Any signed-in user, scoped exactly as `fetchDocument` is, for a document in any
 * status. 200 is the stored original as an attachment, typed and named by the
 * format its signature proved at upload; 404, with one body, for an unknown id,
 * one outside the caller's scope and one whose file is not stored, so the route
 * never says which (CLAUDE.md §6, invariant 1); 401 for no session.
 *
 * This route is the only address a document is downloaded from. Nothing serves
 * `/media/`, and the document object carries no stored path to build one from.
 */
export function documentDownloadUrl(docId) {
  return apiUrl(`/documents/${encodeURIComponent(docId)}/download`)
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
 * "Processing failed. Please try again" action displays; 429 past the per-user
 * ingestion rate, one budget shared with meeting ingestion and reprocess, with a
 * `Retry-After` in seconds (`error.retryAfter`). The rate is checked before the
 * body is validated, so a 429 stores nothing (D-79). A second 429, `code`
 * `ingestion_in_flight` (`error.code`, src/api/ingestion.js) and no `Retry-After`,
 * while another upload, transcript or reprocess of this user's is still being
 * processed; it comes after every refusal above, and stores nothing (D-85).
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
 * which is what a file with no text layer will always do; 429 past the ingestion
 * rate it shares with upload and meeting ingestion (D-79), which re-runs nothing
 * and leaves the document at the status it had; and the same with `code`
 * `ingestion_in_flight` and no `Retry-After` while another ingestion of this
 * user's is still being processed (D-85).
 */
export function reprocessDocument(docId, options = {}) {
  return post(`/documents/${encodeURIComponent(docId)}/reprocess`, {}, options)
}

/* ---- FR-10 classification (D-104, D-105, D-128) -------------------------- */

/*
 * The detail object (`fetchDocument`) carries two more fields since FR-10, read
 * by src/components/Classification.jsx:
 *
 * - `classification` — `null` while the document has never been classified, else
 *   `{doc_type, doc_type_outcome, department_outcome, department_applied_by,
 *   machine_doc_type, machine_doc_type_confidence, machine_department,
 *   machine_department_confidence, user_edited, proposed_tags: [{dimension, value,
 *   confidence}], classified_at, model, input_truncated}`. `proposed_tags` are the
 *   values the AI suggested below the confidence threshold that are not in this
 *   document's scheme, in Project, Process or Topic (D-128): held until a person
 *   confirms or rejects one, `dimension` "Project", "Process" or "Topic" and `value`
 *   the name as the server stores it. A value at or above the threshold is not
 *   proposed: it is applied, and is an AI link in `tag_details` like any other.
 *   `department_applied_by` is
 *   whose value the department is, "user", "ai" or null (D-119 finding 10; null for
 *   no department, or a classification recorded before the field). An outcome is
 *   `applied` (at or above the confidence
 *   threshold and written), `provisional` (below it: held, not the document's type,
 *   and `doc_type` is null; for the department also a suggestion that differs from
 *   a department already on the document, which since 10 November stays until a
 *   person accepts the suggestion, D-105's note), `discarded` (the department
 *   only: outside the known departments, nothing written) or `confirmed` (a person
 *   confirmed or edited it). `doc_type` is the effective type; the effective
 *   department is the document's own `department` field (D-72).
 * - `tag_details` — every tag link, `[{content_tag_id, dimension, name,
 *   applied_by, confirmed, provisional, confidence}]`, `applied_by` "ai" or
 *   "user". A link with `provisional: true` is a held suggestion and is not among
 *   `tags`. A link a person removed is in no read. Nothing in a link, or in a
 *   proposal, says whether its value was new to the database, retired, or carried
 *   by other material that some reader of this document cannot see: a reply that
 *   told them apart would disclose the last two (CLAUDE.md §6, invariant 1). The
 *   screen shows every AI link alike. Since D-129 the classifier creates no value
 *   of its own; a person's confirmation of a proposed Topic does.
 * - `tag_options` — `{Project: [{tag_id, tag_name}], Process: [...], Topic: [...]}`,
 *   the tags a person may apply to this document, which are its own
 *   classification scheme: always all three keys, each sorted by name, tags
 *   already on the document included. It discloses nothing to anyone who may read
 *   the document (CLAUDE.md §6, invariant 1).
 *
 * Every action below needs a session and `contribute_content`, which both roles
 * hold (D-30, D-105). 404 for an unknown id or a document outside the caller's
 * scope, checked before the permission, so a refusal never says whether the id
 * names something (CLAUDE.md §6, invariant 1); 403 for a role without the
 * permission. The screen hides its controls on a 403 and the server checks on
 * every call whatever the screen showed (invariant 4).
 */

/**
 * `POST /api/documents/{id}/classify` — runs FR-10's classification over the
 * document's extracted text, which takes the AI service ten to sixty seconds.
 *
 * 200 `{classification, tag_details, department}`: the first two as the detail
 * carries them, and `department` the document's `department` column after the
 * run, which can fill a blank one (D-105), shown as it is; 422 no
 * text was extracted, so there is nothing to classify (FR-10's own code); 503
 * NFR-19's notice, after `MAXIMUM_CLASSIFY_ATTEMPTS`; 429 past the ingestion
 * rate it shares with upload, meeting ingestion and reprocess (D-79), with a
 * `Retry-After` in seconds.
 */
export function classifyDocument(docId, options = {}) {
  return post(`/documents/${encodeURIComponent(docId)}/classify`, {}, options)
}

/**
 * `POST /api/documents/{id}/classification` — a person confirms or edits the
 * type and the department, in one request.
 *
 * With neither value given the body is empty, `{}`, and the suggestions are
 * confirmed as they stand: a provisional type becomes the document's type and a
 * provisional department is written. With values, those are written instead and
 * marked confirmed; the machine's values are kept beside them (FR-10: "the
 * machine assignment is retained alongside it"). Either way the outcomes read
 * `confirmed` and later reprocessing leaves them alone.
 *
 * 200 `{classification, department}`, where `department` is the document's
 * `department` column after the confirm or edit (D-105's note of 10 November),
 * which the screen shows as it is rather than working it out from the outcome;
 * 400 `{"doc_type": ["..."]}` for a type outside Policy, Procedure, Report and
 * Meeting Paper, or `{"department": ["..."]}`; 404 also for a document that has
 * no classification yet (D-105's build notes: the type of a never-classified
 * document is edited after `classifyDocument`, not instead of it).
 *
 * @param {string} docId
 * @param {{docType?: string, department?: string}} [values] Omitted fields are
 *   not sent, so an empty object confirms.
 */
export function confirmClassification(docId, { docType, department } = {}, options = {}) {
  const body = {}
  if (docType !== undefined) body.doc_type = docType
  if (department !== undefined) body.department = department
  return post(`/documents/${encodeURIComponent(docId)}/classification`, body, options)
}

/**
 * `POST /api/documents/{id}/tags/{content_tag_id}/confirm` — a person confirms
 * one tag link the AI applied or held. 200 with the `tag_details` entry as it now
 * is: `confirmed` true, `provisional` false. A confirmed tag is not altered by
 * later reprocessing (FR-10).
 */
export function confirmTag(docId, contentTagId, options = {}) {
  return post(
    `/documents/${encodeURIComponent(docId)}/tags/${encodeURIComponent(contentTagId)}/confirm`,
    {},
    options,
  )
}

/**
 * `DELETE /api/documents/{id}/tags/{content_tag_id}` — removes one tag link:
 * rejecting a held suggestion and removing an applied tag are the same action
 * (FR-10: "either may be accepted or removed in a single action"). 204, no body.
 */
export function removeTag(docId, contentTagId, options = {}) {
  return del(`/documents/${encodeURIComponent(docId)}/tags/${encodeURIComponent(contentTagId)}`, options)
}

/**
 * The three dimensions a person applies a tag in, as the detail's `tag_options`
 * keys them, in the order the screen offers them. The contract sends all three
 * keys, each list sorted by name (docs/api-contract.md, NIT3004 FR-10). Department
 * is the document's own field, not a tag applied here (D-72).
 */
export const TAG_OPTION_DIMENSIONS = ['Project', 'Process', 'Topic']

/**
 * The one dimension a person may name a new value in, through `applyTag`'s name form,
 * and the one dimension the classifier proposes new values in (`confirmProposedTag`;
 * Objective 05's clause 3, D-129).
 */
export const NEW_TAG_DIMENSION = 'Topic'

/**
 * `POST /api/documents/{id}/tags` — a person applies a tag (FR-10's provenance
 * clause; UC-09 A3; D-105's dated note of 10 November 2026, night).
 *
 * `choice` is exactly one of `{tagId}`, a tag from the detail's `tag_options`, sent
 * as `{"tag_id": ...}`; or `{tagName}`, a new Topic, sent as `{"dimension": "Topic",
 * "tag_name": ...}`, which the server matches after trimming, single-spacing and
 * lower-casing.
 *
 * 201 `{tag_details}` when a new link was made; 200, the same shape, when the tag
 * was already on the document: a held AI link confirmed, a removed one restored, or
 * nothing to change. `tag_details` is the document's whole current list. The reply
 * does not carry `tag_options`, which a new Topic joins: read the detail again.
 *
 * 409 `{detail, tag_id}`: the name is a Topic already in `tag_options`, whose id
 * `error.details.tag_id` is, so the screen can choose it rather than make a
 * duplicate. 400 keyed on `tag_id` (one body for an unknown, inactive or withheld
 * tag, so a refusal never says which), `dimension`, `tag_name` (missing, blank or
 * over 255 characters) or `non_field_errors` (neither form, or both). 404 scoped
 * first; 403 without `contribute_content`; 401.
 *
 * @param {string} docId
 * @param {{tagId: string} | {tagName: string}} choice
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<{created: boolean, body: object|null}>} `created` is the 201.
 */
export async function applyTag(docId, choice, options = {}) {
  const body =
    'tagId' in choice ? { tag_id: choice.tagId } : { dimension: NEW_TAG_DIMENSION, tag_name: choice.tagName }
  const { status, data } = await requestWithStatus(`/documents/${encodeURIComponent(docId)}/tags`, {
    ...options,
    method: 'POST',
    body,
  })
  return { created: status === 201, body: data }
}

/*
 * A value the AI proposed, in `classification.proposed_tags`, is confirmed or
 * rejected by its dimension and its value together (D-128): the same value can be
 * proposed under two dimensions, and each is its own proposal.
 *
 * Both routes are ordered as every action above: session, the scoped 404, then
 * `contribute_content`'s 403, then the body. 400 `{"dimension": [...]}` for a missing
 * dimension or one other than Project, Process and Topic, Department included; 400
 * `{"value": [...]}` for a blank or over-long value. 404, the document's own 404
 * body, also when that value is not proposed under that dimension on this document,
 * as after another session decided it, so the reply never says which.
 */

/**
 * `POST /api/documents/{id}/proposed-tags/confirm`, body `{dimension, value}` — a
 * person confirms a value the AI proposed below the threshold (D-128). The server
 * creates the tag, or brings back one of that name, and links it as the AI's,
 * confirmed. 200 `{classification, tag_details}`: the entry leaves `proposed_tags`
 * and a link appears in `tag_details`.
 *
 * @param {string} docId
 * @param {'Project'|'Process'|'Topic'} dimension The proposal's own dimension.
 * @param {string} value The proposal's value, as `proposed_tags` carries it.
 */
export function confirmProposedTag(docId, dimension, value, options = {}) {
  return post(`/documents/${encodeURIComponent(docId)}/proposed-tags/confirm`, { dimension, value }, options)
}

/**
 * `POST /api/documents/{id}/proposed-tags/reject`, body `{dimension, value}` — drops
 * a proposed value without creating anything (D-128). 200 `{classification,
 * tag_details}`, the entry gone from `proposed_tags`.
 *
 * @param {string} docId
 * @param {'Project'|'Process'|'Topic'} dimension The proposal's own dimension.
 * @param {string} value The proposal's value, as `proposed_tags` carries it.
 */
export function rejectProposedTag(docId, dimension, value, options = {}) {
  return post(`/documents/${encodeURIComponent(docId)}/proposed-tags/reject`, { dimension, value }, options)
}
