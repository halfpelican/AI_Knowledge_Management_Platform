import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchMeeting } from '../api/meetings.js'
import Button from '../components/Button.jsx'
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
 * A meeting outside the caller's scope answers 404, exactly as an id that names
 * nothing does, and both render the same message. The screen never distinguishes
 * "no such meeting" from "not yours to read" (CLAUDE.md §6, invariant 1).
 */
export default function MeetingDetail() {
  const { meetingId } = useParams()
  // Stable per id: the hook's effect re-reads when the route parameter changes
  // and not on every render.
  const loader = useCallback(({ signal }) => fetchMeeting(meetingId, { signal }), [meetingId])
  const { data: meeting, loading, error, reload } = useApiResource(loader)
  useDocumentTitle(meeting?.title ?? 'Meeting transcript')

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

  return (
    <div className="repository-page">
      <h1>{meeting.title}</h1>
      <p>
        <Link to="/meetings">Back to meetings</Link>
      </p>

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

      <h2 id="transcript-heading">{TEXT.transcriptHeading}</h2>
      <p className="data-table__meta">{TEXT.transcriptVerbatim}</p>
      {/* tabIndex 0 so a keyboard user can scroll the block, and a labelled
          region so a screen reader announces what it is before reading it. */}
      <pre className="transcript" role="region" aria-labelledby="transcript-heading" tabIndex={0}>
        {meeting.transcript_text}
      </pre>
    </div>
  )
}
