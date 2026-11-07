/**
 * Meeting transcript endpoints (FR-09 ingest, list and detail, and the meeting
 * delete beside FR-15's document delete), per docs/api-contract.md. Thin wrappers
 * over the one API client; no fetch and no XMLHttpRequest here.
 */
import { del, get, post, upload } from './client.js'

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
