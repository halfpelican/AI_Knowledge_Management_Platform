import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client.js'
import { ingestMeeting, listMeetings } from '../api/meetings.js'
import { listUsers } from '../api/users.js'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import FileDropZone from '../components/FileDropZone.jsx'
import Notice from '../components/Notice.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import SelectInput from '../components/SelectInput.jsx'
import TextAreaInput from '../components/TextAreaInput.jsx'
import TextInput from '../components/TextInput.jsx'
import { ROLES, TEXT, TRANSCRIPT_SOURCE } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate, todayIsoDate } from '../utils/dates.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { FILE_INPUT_ACCEPT } from '../utils/uploads.js'
import { validateMeetingIngestion } from '../utils/validation.js'
import { rolesForVisibility, VISIBILITY_EVERYONE, visibilityOptionsFor } from '../utils/visibility.js'
import './Repository.css'
import './Meetings.css'

/** The API's own field names, so a 400's `details` lands under the right control. */
const FIELDS = ['title', 'meeting_date', 'transcript_text', 'file', 'attendees', 'visible_to_roles']

const EMPTY_FORM = { title: '', meeting_date: '', transcript_text: '' }

/**
 * The meetings table as a pure view. The transcript body is not here — the list
 * endpoint omits it, and the detail route serves it in full.
 */
export function MeetingTable({ meetings }) {
  if (meetings.length === 0) {
    return <Notice variant="info">{TEXT.noMeetings}</Notice>
  }

  return (
    <div className="table-scroll" role="region" aria-labelledby="meetings-list-heading" tabIndex={0}>
      <table className="data-table">
        <caption className="visually-hidden">Meeting transcripts</caption>
        <thead>
          <tr>
            <th scope="col">Meeting</th>
            <th scope="col">Date</th>
            <th scope="col">Status</th>
            <th scope="col">Attendees</th>
            <th scope="col">Visible to</th>
          </tr>
        </thead>
        <tbody>
          {meetings.map((meeting) => (
            <tr key={meeting.meeting_id}>
              <th scope="row" className="data-table__title">
                <Link to={`/meetings/${meeting.meeting_id}`}>{meeting.title}</Link>
              </th>
              <td className="data-table__meta">
                <time dateTime={meeting.meeting_date}>{formatDate(meeting.meeting_date)}</time>
              </td>
              <td>{meeting.status}</td>
              {/* A participation record, not a permission (D-16). */}
              <td className="data-table__meta">{meeting.attendees?.length ?? 0}</td>
              <td className="data-table__meta">{(meeting.visible_to_roles ?? []).join(', ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * FR-09 meeting transcript ingestion, and the list of what has been ingested.
 *
 * The form takes a title, a date and **either** pasted text or a file, never
 * both, and optionally attendees and a visibility scope. Ingestion is
 * synchronous, so the submit itself is the wait FR-09 asks a processing
 * indicator for.
 *
 * Attendees are a participation record and never an access control (D-16,
 * CLAUDE.md §6, invariant 3): what decides who can read a transcript is the
 * visibility scope, exactly as for a document. The picker is populated from
 * GET /api/users, which is Administrator-only (FR-05), so an Employee gets a
 * note in its place rather than an empty control that cannot be filled. That is
 * usability; the server decides what any of it may do (invariant 4).
 */
export default function Meetings() {
  useDocumentTitle('Meeting transcripts')
  const { user } = useAuth()
  const meetingsResource = useApiResource(listMeetings)
  const meetings = meetingsResource.data ?? []

  // Only an Administrator may read the user list, so only an Administrator asks
  // for it: an Employee requesting it would collect a 403 on every page load.
  const isAdministrator = user?.role === ROLES.administrator
  const loadAttendeeCandidates = useCallback(
    ({ signal }) => (isAdministrator ? listUsers({ signal }) : Promise.resolve([])),
    [isAdministrator],
  )
  // A failure here is not this screen's failure: the transcript can still be
  // ingested without attendees, so the list simply stays empty.
  const candidates = useApiResource(loadAttendeeCandidates).data ?? []

  const [values, setValues] = useState(EMPTY_FORM)
  const [source, setSource] = useState(TRANSCRIPT_SOURCE.text)
  const [file, setFile] = useState(null)
  const [attendees, setAttendees] = useState([])
  const [visibility, setVisibility] = useState(VISIBILITY_EVERYONE)
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  // The error summary. Focus moves here when a submission is refused, so a
  // keyboard user is taken to the reason instead of being left on the button.
  const errorSummaryRef = useRef(null)

  useEffect(() => {
    if (formError) errorSummaryRef.current?.focus()
  }, [formError])

  const visibilityOptions = visibilityOptionsFor(user?.role)

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
  }

  /** Switching source clears the other half, so both can never be submitted. */
  function handleSourceChange(next) {
    setSource(next)
    setFile(null)
    setValues((current) => ({ ...current, transcript_text: '' }))
    setFieldErrors((current) => ({ ...current, transcript_text: undefined, file: undefined }))
  }

  function resetForm() {
    setValues(EMPTY_FORM)
    setFile(null)
    setAttendees([])
    setFieldErrors({})
  }

  function handleFailure(error) {
    if (!(error instanceof ApiError)) {
      setFormError(TEXT.meetingRejected)
      return
    }
    if (error.status === 422) {
      // The transcript was stored; only the indexing failed (NFR-20, invariant
      // 8). It is in the list, so the list is re-read, and the notice says
      // plainly that it will not appear in search.
      setNotice({ variant: 'error', title: 'Stored, but not indexed', text: TEXT.meetingStoredNotIndexed })
      resetForm()
      meetingsResource.reload()
      return
    }
    if (error.status === 403) {
      // The role lacks `contribute_content`. The form never offers a scope
      // excluding the contributor's own role, so D-29's 403 is not reachable.
      setFormError(TEXT.meetingNotPermitted)
      return
    }
    const extracted = extractFieldErrors(error, FIELDS)
    setFieldErrors(extracted.fieldErrors)
    setFormError(extracted.formError ?? TEXT.meetingRejected)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setNotice(null)
    const clientErrors = validateMeetingIngestion({
      title: values.title,
      meetingDate: values.meeting_date,
      transcriptText: values.transcript_text,
      source,
      file,
    })
    setFieldErrors(clientErrors)
    if (Object.keys(clientErrors).length > 0) {
      setFormError(TEXT.checkHighlightedFields)
      return
    }
    setFormError(null)

    setSubmitting(true)
    try {
      const meeting = await ingestMeeting({
        title: values.title.trim(),
        meetingDate: values.meeting_date,
        // Exactly one of these reaches the API (src/api/meetings.js).
        transcriptText: source === TRANSCRIPT_SOURCE.text ? values.transcript_text : undefined,
        file: source === TRANSCRIPT_SOURCE.file ? file : undefined,
        attendees,
        visibleToRoles: rolesForVisibility(visibility),
      })
      setNotice({
        variant: 'info',
        title: 'Transcript stored',
        text: TEXT.meetingIndexed(meeting?.title ?? values.title.trim()),
        meetingId: meeting?.meeting_id,
      })
      resetForm()
      meetingsResource.reload()
    } catch (error) {
      handleFailure(error)
    } finally {
      setSubmitting(false)
    }
  }

  let list
  if (meetingsResource.loading) {
    list = <p role="status">{TEXT.loadingMeetings}</p>
  } else if (meetingsResource.error && meetingsResource.error.status === 403) {
    list = <NotPermitted />
  } else if (meetingsResource.error) {
    list = (
      <>
        <Notice variant="error" title={TEXT.meetingsLoadFailed}>
          {meetingsResource.error.message}
        </Notice>
        <div className="repository-page__actions">
          <Button variant="secondary" onClick={meetingsResource.reload}>
            Try again
          </Button>
        </div>
      </>
    )
  } else {
    list = <MeetingTable meetings={meetings} />
  }

  return (
    <div className="repository-page">
      <h1>Meeting transcripts</h1>

      <section aria-labelledby="meeting-form-heading" className="meeting-form">
        <h2 id="meeting-form-heading">Add a transcript</h2>
        <form onSubmit={handleSubmit} noValidate>
          {/* tabIndex -1 so focus can be moved here; the Notice itself is an
              alert, so the message is announced whether or not focus arrives. */}
          <div ref={errorSummaryRef} tabIndex={-1} className="meeting-form__summary">
            {formError ? (
              <Notice variant="error" title="Could not add the transcript">
                {formError}
              </Notice>
            ) : null}
            {notice ? (
              <Notice variant={notice.variant} title={notice.title}>
                {notice.text}{' '}
                {notice.meetingId ? <Link to={`/meetings/${notice.meetingId}`}>View the transcript</Link> : null}
              </Notice>
            ) : null}
          </div>

          <TextInput
            label="Meeting title"
            name="title"
            value={values.title}
            error={fieldErrors.title}
            disabled={submitting}
            required
            onChange={handleChange}
          />
          <TextInput
            label="Meeting date"
            name="meeting_date"
            type="date"
            // FR-09: the date may not be in the future. The control refuses one
            // and the server refuses one too.
            max={todayIsoDate()}
            value={values.meeting_date}
            error={fieldErrors.meeting_date}
            disabled={submitting}
            required
            onChange={handleChange}
          />

          <fieldset className="meeting-form__source">
            <legend>{TEXT.meetingSourceLegend}</legend>
            {[
              { value: TRANSCRIPT_SOURCE.text, label: TEXT.meetingSourceText },
              { value: TRANSCRIPT_SOURCE.file, label: TEXT.meetingSourceFile },
            ].map((option) => (
              <div className="meeting-form__choice" key={option.value}>
                <input
                  type="radio"
                  id={`transcript-source-${option.value}`}
                  name="transcript-source"
                  value={option.value}
                  checked={source === option.value}
                  disabled={submitting}
                  onChange={() => handleSourceChange(option.value)}
                />
                <label htmlFor={`transcript-source-${option.value}`}>{option.label}</label>
              </div>
            ))}
          </fieldset>

          {source === TRANSCRIPT_SOURCE.text ? (
            <TextAreaInput
              label="Transcript"
              name="transcript_text"
              rows={12}
              hint={TEXT.transcriptVerbatim}
              value={values.transcript_text}
              error={fieldErrors.transcript_text}
              disabled={submitting}
              onChange={handleChange}
            />
          ) : (
            <>
              <FileDropZone
                label="Transcript file"
                hint={TEXT.uploadDropHint}
                accept={FILE_INPUT_ACCEPT}
                disabled={submitting}
                error={fieldErrors.file}
                onFiles={(files) => {
                  setFile(files[0])
                  setFieldErrors((current) => ({ ...current, file: undefined }))
                }}
              />
              {file ? <p className="meeting-form__file">Selected: {file.name}</p> : null}
            </>
          )}

          {candidates.length > 0 ? (
            <SelectInput
              label="Attendees (optional)"
              hint={TEXT.attendeesHint}
              multiple
              size={Math.min(6, candidates.length)}
              options={candidates.map((candidate) => ({
                value: candidate.id,
                label: `${candidate.name} (${candidate.email})`,
              }))}
              value={attendees}
              error={fieldErrors.attendees}
              disabled={submitting}
              onChange={(event) =>
                setAttendees(Array.from(event.target.selectedOptions, (option) => option.value))
              }
            />
          ) : (
            <p className="meeting-form__note">
              {TEXT.attendeesUnavailable} {TEXT.attendeesHint}
            </p>
          )}

          {visibilityOptions.length > 1 ? (
            <SelectInput
              label="Visible to"
              hint={TEXT.visibilityHint}
              options={visibilityOptions}
              value={visibility}
              error={fieldErrors.visible_to_roles}
              disabled={submitting}
              onChange={(event) => setVisibility(event.target.value)}
            />
          ) : (
            <p className="meeting-form__note">{TEXT.visibilityFixed}</p>
          )}

          <div className="repository-page__actions">
            <Button type="submit" loading={submitting} disabled={submitting}>
              {submitting ? 'Processing…' : 'Add transcript'}
            </Button>
          </div>
          {/* FR-09's processing indicator. Ingestion is synchronous — the
              transcript is chunked and embedded inside this request — so the
              wait is real and is announced rather than only spun. */}
          <p role="status" aria-live="polite" className="meeting-form__progress">
            {submitting ? TEXT.meetingProcessing : ''}
          </p>
        </form>
      </section>

      <section aria-labelledby="meetings-list-heading">
        <h2 id="meetings-list-heading">Meetings</h2>
        {list}
      </section>
    </div>
  )
}
