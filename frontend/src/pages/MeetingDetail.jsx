import { useCallback, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { deleteMeeting, fetchMeeting } from '../api/meetings.js'
import Button from '../components/Button.jsx'
import Dialog from '../components/Dialog.jsx'
import Notice from '../components/Notice.jsx'
import { TEXT } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
import './Repository.css'

/**
 * One meeting, with its transcript in full — FR-09: "once processed, the stored
 * transcript is then viewable in full".
 *
 * The transcript is rendered in a preformatted block: it is stored verbatim,
 * speaker labels and timestamps included, and parsing them is out of scope for
 * this version (FR-09 says so explicitly). So nothing here splits on a label, a
 * colon or a timestamp, and nothing styles them as structure — the block
 * preserves the line breaks it was given and that is the whole of it. A future
 * version that does parse them would change this file; a version that merely
 * looked as though it had would be worse than one that does not.
 *
 * **The delete control is shown only when the detail says `can_delete`**, and it
 * asks for confirmation before sending anything. Meeting deletion is not in the
 * proposal; the lead asked for it, and it mirrors FR-15's document delete in
 * src/pages/DocumentDetail.jsx (D-99). Showing the control is usability; the
 * server checks `manage_meetings` on every delete whatever this screen showed
 * (CLAUDE.md §6, invariant 4). A 204 returns to the meetings list, which says
 * what was deleted.
 *
 * A meeting outside the caller's scope answers 404, exactly as an id that names
 * nothing does, and both render the same message. The screen never distinguishes
 * "no such meeting" from "not yours to read" (CLAUDE.md §6, invariant 1).
 */
export default function MeetingDetail() {
  const { meetingId } = useParams()
  const navigate = useNavigate()
  // Stable per id: the hook's effect re-reads when the route parameter changes
  // and not on every render.
  const loader = useCallback(({ signal }) => fetchMeeting(meetingId, { signal }), [meetingId])
  const { data: meeting, loading, error, reload } = useApiResource(loader)
  useDocumentTitle(meeting?.title ?? 'Meeting transcript')

  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)
  // The server refused the delete with a 403: the role no longer holds the
  // permission, whatever the detail said when it loaded. The control goes.
  const [deleteRefused, setDeleteRefused] = useState(false)
  // One DELETE per confirmation, even if confirm is pressed again before the
  // busy state has rendered.
  const deleteInFlight = useRef(false)
  const headingRef = useRef(null)

  if (loading) {
    return (
      <div className="repository-page">
        <p role="status">{TEXT.loadingMeeting}</p>
      </div>
    )
  }

  if (error) {
    const notFound = error.status === 404
    return (
      <div className="repository-page">
        <h1>Meeting transcript</h1>
        <Notice variant="error" title={notFound ? 'Not found' : TEXT.meetingLoadFailed}>
          {notFound ? TEXT.meetingNotFound : error.message}
        </Notice>
        <div className="repository-page__actions">
          {notFound ? null : (
            <Button variant="secondary" onClick={reload}>
              Try again
            </Button>
          )}
          <Link to="/meetings">Back to meetings</Link>
        </div>
      </div>
    )
  }

  if (!meeting) {
    // A 200 with no body is not something the contract allows; handled anyway so
    // the render below can read the record without guarding every field.
    return (
      <div className="repository-page">
        <h1>Meeting transcript</h1>
        <Notice variant="error" title="Not found">
          {TEXT.meetingNotFound}
        </Notice>
        <p>
          <Link to="/meetings">Back to meetings</Link>
        </p>
      </div>
    )
  }

  const attendees = meeting.attendees ?? []
  const canDelete = meeting.can_delete === true && !deleteRefused

  async function confirmDelete() {
    if (deleteInFlight.current) return
    deleteInFlight.current = true
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteMeeting(meeting.meeting_id)
      // Replace, so Back from the list does not return to a record that is gone.
      navigate('/meetings', { replace: true, state: { deleted: meeting.title } })
    } catch (caught) {
      deleteInFlight.current = false
      setDeleting(false)
      setConfirming(false)
      if (caught instanceof ApiError && caught.status === 403) {
        setDeleteRefused(true)
        setDeleteError(TEXT.meetingDeleteNotPermitted)
      } else if (caught instanceof ApiError && caught.status === 404) {
        // Gone, or now outside the caller's scope: one message for both, and the
        // one this screen shows for a 404 on load.
        setDeleteError(TEXT.meetingNotFound)
      } else {
        // Fixed, user-facing text from the API client. Never a backend string.
        setDeleteError(
          caught instanceof ApiError ? caught.message : messageForStatus(NETWORK_ERROR_STATUS),
        )
      }
    }
  }

  return (
    <div className="repository-page">
      <h1 ref={headingRef} tabIndex={-1}>
        {meeting.title}
      </h1>
      <p>
        <Link to="/meetings">Back to meetings</Link>
      </p>

      {deleteError ? (
        <Notice variant="error" title={TEXT.meetingDeleteFailed}>
          {deleteError}
        </Notice>
      ) : null}

      <dl className="record-meta">
        <dt>Date</dt>
        <dd>
          <time dateTime={meeting.meeting_date}>{formatDate(meeting.meeting_date)}</time>
        </dd>
        <dt>Status</dt>
        <dd>{meeting.status}</dd>
        <dt>Visible to</dt>
        <dd>{(meeting.visible_to_roles ?? []).join(', ')}</dd>
        {/* Who took part, and nothing more: attendance confers no access, and
            the scope above is what decides who can read this (D-16). */}
        <dt>Attendees</dt>
        <dd>{attendees.length > 0 ? attendees.join(', ') : 'None recorded'}</dd>
      </dl>

      {/* The meeting's one action, where the document detail keeps its actions.
          A meeting has no download, so the row is there only when it has the
          delete control to hold. */}
      {canDelete ? (
        <div className="repository-page__actions meeting-detail__actions">
          <Button variant="secondary" onClick={() => setConfirming(true)}>
            {TEXT.meetingDelete}
          </Button>
        </div>
      ) : null}

      <h2 id="transcript-heading">{TEXT.transcriptHeading}</h2>
      <p className="data-table__meta">{TEXT.transcriptVerbatim}</p>
      {/* tabIndex 0 so a keyboard user can scroll the block, and a labelled
          region so a screen reader announces what it is before reading it. */}
      <pre className="transcript" role="region" aria-labelledby="transcript-heading" tabIndex={0}>
        {meeting.transcript_text}
      </pre>

      {confirming ? (
        <Dialog
          title={TEXT.meetingDeleteConfirm(meeting.title)}
          confirmLabel={TEXT.meetingDelete}
          busyLabel={TEXT.meetingDeleting}
          cancelLabel={TEXT.meetingDeleteCancel}
          busy={deleting}
          returnFocusRef={headingRef}
          onConfirm={confirmDelete}
          onCancel={() => {
            if (!deleting) setConfirming(false)
          }}
        >
          <p>{TEXT.meetingDeleteBody}</p>
        </Dialog>
      ) : null}
    </div>
  )
}
