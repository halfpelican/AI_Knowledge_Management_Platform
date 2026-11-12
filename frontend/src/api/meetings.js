/**
 * Meeting transcript endpoints (FR-09 ingest, list and detail, the meeting delete
 * beside FR-15's document delete, and FR-16's summary and action items), per
 * docs/api-contract.md. Thin wrappers over the one API client; no fetch and no
 * XMLHttpRequest here.
 */
import { ApiError, del, get, patch, post, requestWithStatus, upload } from './client.js'

/**
 * Any signed-in user. 200 [meeting object without `transcript_text`], newest
 * first, scoped by `visible_to_roles`. The list carries no transcript bodies;
 * the detail route below serves the full text.
 */
export function listMeetings(options = {}) {
  return get('/meetings', options)
}

/**
 * One meeting **with** `transcript_text` — FR-09: "once processed, the stored
 * transcript is then viewable in full" — and `can_delete`, whether the caller's
 * role holds `manage_meetings`. Only the detail carries `can_delete`, not the
 * list, and it decides only whether the screen offers the control (CLAUDE.md §6,
 * invariant 4).
 *
 * 404 both for an id that names nothing and for a meeting outside the caller's
 * scope, so a refusal does not confirm that the id names something real
 * (CLAUDE.md §6, invariant 1).
 */
export function fetchMeeting(meetingId, options = {}) {
  return get(`/meetings/${encodeURIComponent(meetingId)}`, options)
}

/**
 * `DELETE /api/meetings/{id}` — the meeting delete (docs/api-contract.md,
 * "Meeting deletion"). Session plus `manage_meetings`, which is
 * Administrator-only.
 *
 * 204 with no body: the meeting, its attendee records, its chunks and its tag
 * links are gone, in one transaction. 404 for an unknown meeting or one outside
 * the caller's scope, checked **before** the permission and with the same body,
 * so the code never says whether a meeting the caller cannot see exists; 403 for
 * a meeting in scope and a role without `manage_meetings`; 401 for no session.
 *
 * The server checks the permission on every call whatever the screen showed
 * (CLAUDE.md §6, invariant 4).
 */
export function deleteMeeting(meetingId, options = {}) {
  return del(`/meetings/${encodeURIComponent(meetingId)}`, options)
}

/**
 * FR-09 ingestion: "users can upload a transcript file or paste transcript text
 * directly into a form, associating it with a meeting title, date, and
 * attendees".
 *
 * Exactly one of `transcriptText` and `file` carries the transcript. Supplying
 * both is 400 rather than a silent preference — whichever the server picked, the
 * other would be discarded without the user knowing which — so the form offers
 * one or the other and this function sends whichever it was given. Pasted text
 * goes as JSON; a file goes as multipart, through the same `upload()` helper the
 * document screen uses.
 *
 * 201 with the meeting object; 400 a missing title or date, a future date, a
 * transcript below the minimum length, neither text nor file, both, an
 * unreadable file, or an attendee who is not a registered user; 403 the role
 * lacks `contribute_content`; 422 the transcript was stored but could not be
 * indexed (NFR-20: a failed AI step never discards the source); 429 past the
 * per-user ingestion rate it shares with document upload and reprocess, with a
 * `Retry-After` in seconds, which stores nothing (D-79); and a 429 with `code`
 * `ingestion_in_flight` (src/api/ingestion.js) and no `Retry-After` while another
 * ingestion of this user's is still being processed, after the 400 and the 403,
 * which stores nothing either (D-85).
 *
 * `attendees` is a list of user ids. They are a participation record and never
 * an access control (D-16, CLAUDE.md §6, invariant 3): scoping is
 * `visibleToRoles`, exactly as for a document.
 */
export function ingestMeeting(
  { title, meetingDate, transcriptText, file, attendees = [], visibleToRoles },
  options = {},
) {
  if (file) {
    const body = new FormData()
    body.append('title', title)
    body.append('meeting_date', meetingDate)
    body.append('file', file)
    for (const attendee of attendees) body.append('attendees', attendee)
    if (visibleToRoles) for (const role of visibleToRoles) body.append('visible_to_roles', role)
    return upload('/meetings', body, options)
  }

  const body = { title, meeting_date: meetingDate, transcript_text: transcriptText }
  if (attendees.length > 0) body.attendees = attendees
  // Omitted means both roles (D-29), so the key is absent rather than null.
  if (visibleToRoles) body.visible_to_roles = visibleToRoles
  return post('/meetings', body, options)
}

/* ---- FR-16 meeting summary and action items (D-125) ---------------------- */

/*
 * The summary state, which both summary routes return at every status code they
 * answer (docs/api-contract.md, "NIT3004 — FR-16"):
 *
 *   {status, queued_for_retry, summary, action_items, can_edit}
 *
 * - `status` is the latest run's, "Processing", "Ready" or "Unavailable"
 *   (src/constants.js SUMMARY_STATUS), or null where no summary was ever requested.
 * - `queued_for_retry` is NFR-20's flag on that run: "Unavailable" with it true is
 *   waiting for the hourly retry.
 * - `summary` is the latest **Ready** summary, or null. It is never a failed one
 *   (UC-04: "in the failed state it is never presented to a user"), and while a
 *   Regenerate runs, and after one fails, it is still the previous Ready summary,
 *   so `status` and `summary` can differ. It carries `narrative`, `decisions` and
 *   `highlights`, each a list of `{text, passages}` whose numbers are keys of its
 *   `passages` object, plus `model`, `generated_at`, `input_truncated`,
 *   `passages_sent`, `passages_total` and `action_items_extracted`.
 * - `action_items` is the meeting's items in panel order, each `{action_item_id,
 *   description, owner: {id, name} | null, owner_name, due_date, due_text, passages,
 *   origin, edited, created_at, updated_at}`.
 * - `can_edit` is whether the caller's role holds `contribute_content`: a hint for
 *   showing the controls. Every write checks the permission itself (CLAUDE.md §6,
 *   invariant 4).
 *
 * Every route resolves the meeting through the caller's scope first, so a meeting
 * the caller cannot see and one that does not exist are the same 404 (invariant 1).
 * The four writes then need `contribute_content`: 403 for a role without it.
 */

/**
 * The code both summary routes answer when the transcript is under the server's
 * minimum length (FR-16: "422 Unprocessable Entity where the transcript is too
 * short to summarise"). The body is the summary state all the same, with a
 * `detail`, because the Action Items panel still needs the items.
 */
export const SUMMARY_TOO_SHORT_STATUS = 422

/** Whether a 422's body is the summary state, and not some other refusal's. */
function isSummaryState(body) {
  return Boolean(body) && typeof body === 'object' && Array.isArray(body.action_items)
}

/**
 * A summary route's answer as `{status, state}`: the HTTP code beside the summary
 * state, because the codes mean different things. 200 is a settled state, 202 a run
 * in flight or queued for its retry, and 422 a transcript too short to summarise.
 *
 * The status comes from `requestWithStatus`, as FR-10's tag routes read theirs. The
 * 422 is the one code the client throws that is an answer here rather than a
 * failure: its body is the same state, kept on `ApiError.details`, so it is handed
 * back in the same shape. Its `detail` is never read: the screen has its own copy
 * of that sentence (src/constants.js `summaryTooShort`). Any other failure, and a
 * 422 that does not carry the state, is thrown as it came.
 */
async function summaryAnswer(send) {
  try {
    const { status, data } = await send()
    return { status, state: data }
  } catch (caught) {
    if (
      caught instanceof ApiError &&
      caught.status === SUMMARY_TOO_SHORT_STATUS &&
      isSummaryState(caught.details)
    ) {
      return { status: SUMMARY_TOO_SHORT_STATUS, state: caught.details }
    }
    throw caught
  }
}

/**
 * `GET /api/meetings/{id}/summary` — FR-16's Summary and Action Items panels.
 * Session and a meeting in scope; it runs nothing and is not throttled, because the
 * page asks it again while a run is in flight.
 *
 * Resolves to `{status, state}`: 200 with the summary state when nothing is
 * pending; 202 with the same body while a run is "Processing" or queued for its
 * automatic retry; 422 with the same body where the transcript is too short to
 * summarise. Throws for 401 and 404, and for a request that never arrived.
 *
 * @param {string} meetingId
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<{status: number, state: object|null}>}
 */
export function fetchMeetingSummary(meetingId, options = {}) {
  return summaryAnswer(() =>
    requestWithStatus(`/meetings/${encodeURIComponent(meetingId)}/summary`, { ...options, method: 'GET' }),
  )
}

/**
 * `POST /api/meetings/{id}/summary` — FR-16's "Regenerate Summary" button, and
 * "Generate Summary" where the meeting has none. Session plus `contribute_content`.
 *
 * Resolves to `{status, state}`: 202 with the summary state, `status`
 * "Processing", for a run started or for the one already in flight for this
 * meeting; 422 with the same body where the transcript is too short, when nothing
 * was started. The run itself happens after the answer, so there is no 503 here:
 * a failed run is "Unavailable" in a later read.
 *
 * Throws for 401; 404; 403 without the permission; and 429 past the per-user
 * "ingestion" rate it shares with upload, meeting ingestion, reprocess and
 * classify, with a `Retry-After` in seconds (`error.retryAfter`, D-79). The server
 * reads no body, and an empty object is sent, as the other body-less POSTs send.
 *
 * @param {string} meetingId
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<{status: number, state: object|null}>}
 */
export function requestMeetingSummary(meetingId, options = {}) {
  return summaryAnswer(() =>
    requestWithStatus(`/meetings/${encodeURIComponent(meetingId)}/summary`, {
      ...options,
      method: 'POST',
      body: {},
    }),
  )
}

/**
 * `POST /api/meetings/{id}/action-items` — FR-16: "manually add items the
 * extraction missed". Session plus `contribute_content`.
 *
 * 201 with the action item object, whose `origin` is "user". Only `description`
 * is required; an owner and a due date are sent only when one was chosen. 400
 * `{"description": [...]}` for a blank one or one over the server's length,
 * `{"owner_id": [...]}` for an id that names no user, `{"due_date": [...]}`;
 * 401; 404; 403.
 *
 * @param {string} meetingId
 * @param {{description: string, ownerId?: string|null, dueDate?: string|null}} item
 *   `ownerId` is a user's id from `GET /api/users/directory`; `dueDate` is
 *   `YYYY-MM-DD`.
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function addActionItem(meetingId, { description, ownerId, dueDate }, options = {}) {
  const body = { description }
  if (ownerId) body.owner_id = ownerId
  if (dueDate) body.due_date = dueDate
  return post(`/meetings/${encodeURIComponent(meetingId)}/action-items`, body, options)
}

/**
 * `PATCH /api/meetings/{id}/action-items/{item_id}` — FR-16: each item's
 * "description, suggested owner and due date, all editable". Session plus
 * `contribute_content`.
 *
 * Only the fields given are sent: one left `undefined` is unchanged, and `null`
 * clears the owner (unassigned) or the date. 200 with the updated item; an
 * extracted item is then `edited`, which NFR-15's mark shows and which keeps it
 * through a Regenerate. 400 as `addActionItem`, and `{"non_field_errors": [...]}`
 * for a body with none of the three, which is why the screen sends nothing when
 * nothing changed. 404 for the meeting, or for an `item_id` that is not one of
 * this meeting's, with the same body; 403; 401.
 *
 * @param {string} meetingId
 * @param {string} itemId
 * @param {{description?: string, ownerId?: string|null, dueDate?: string|null}} changes
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function updateActionItem(meetingId, itemId, { description, ownerId, dueDate } = {}, options = {}) {
  const body = {}
  if (description !== undefined) body.description = description
  if (ownerId !== undefined) body.owner_id = ownerId
  if (dueDate !== undefined) body.due_date = dueDate
  return patch(
    `/meetings/${encodeURIComponent(meetingId)}/action-items/${encodeURIComponent(itemId)}`,
    body,
    options,
  )
}

/**
 * `DELETE /api/meetings/{id}/action-items/{item_id}` — FR-16's delete. 204 with no
 * body; 404 as `updateActionItem`; 403; 401. The confirmation FR-16 requires is
 * the page's: a confirmed request is all the server can see.
 */
export function deleteActionItem(meetingId, itemId, options = {}) {
  return del(
    `/meetings/${encodeURIComponent(meetingId)}/action-items/${encodeURIComponent(itemId)}`,
    options,
  )
}
