import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ApiError } from '../api/client.js'
import { INGESTION_IN_FLIGHT_CODE } from '../api/ingestion.js'
import { ingestMeeting, listMeetings } from '../api/meetings.js'
import { listUserDirectory } from '../api/users.js'
import useAuth from '../auth/useAuth.js'
import AttendeePicker from '../components/AttendeePicker.jsx'
import Button from '../components/Button.jsx'
import FileDropZone from '../components/FileDropZone.jsx'
import Notice from '../components/Notice.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import RecordingTranscriber from '../components/RecordingTranscriber.jsx'
import SelectInput from '../components/SelectInput.jsx'
import TextAreaInput from '../components/TextAreaInput.jsx'
import TextInput from '../components/TextInput.jsx'
import { TEXT, TRANSCRIPT_SOURCE } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { appendToDraft, draftFilename } from '../utils/audio.js'
import { formatDate, todayIsoDate } from '../utils/dates.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import { whenToRetry } from '../utils/retryAfter.js'
import { FILE_INPUT_ACCEPT } from '../utils/uploads.js'
import { validateMeetingIngestion } from '../utils/validation.js'
import { rolesForVisibility, VISIBILITY_EVERYONE, visibilityOptionsFor } from '../utils/visibility.js'
import './Repository.css'
import './Meetings.css'

/** The API's own field names, so a 400's `details` lands under the right control. */
const FIELDS = ['title', 'meeting_date', 'transcript_text', 'file', 'attendees', 'visible_to_roles']

const EMPTY_FORM = { title: '', meeting_date: '', transcript_text: '' }

/** How long a saved draft's download address lives after the click, in milliseconds. */
const DRAFT_DOWNLOAD_REVOKE_MS = 1000

/**
 * Save `text` as a UTF-8 text file named `filename`, from the page itself: the
 * draft of a transcribed recording, so a person can keep it, or carry it to a host
 * without transcription and add it there as a transcript file (D-123).
 */
function saveTextFile(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revoked a moment later, not at once: some browsers cancel a download whose address is revoked
  // straight after the click, and this button is the way to keep a draft (invariant 8).
  setTimeout(() => URL.revokeObjectURL?.(url), DRAFT_DOWNLOAD_REVOKE_MS)
}

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
 * visibility scope, exactly as for a document. That is why every signed-in user
 * gets a real attendee control — FR-09's Front-End clause gives the association
 * to any user, and an Employee naming an Administrator as an attendee grants
 * that Administrator nothing they did not already have.
 *
 * The picker reads GET /api/users/directory: name and address, no role (D-34).
 * FR-05's GET /api/users stays Administrator-only, because it carries the role
 * each person holds and this form has no use for one. The server decides what
 * any of this may do (invariant 4).
 *
 * **Another source, a meeting recording (D-123).** RecordingTranscriber
 * turns it into draft text a segment at a time, and the draft is kept here, apart
 * from the pasted text, so switching source never loses it. The transcriber stays
 * mounted, hidden, once the option has been opened, so a run paused or stopped
 * there can still resume after a look at another source; the requirements audit
 * of 11 November found that leaving the option lost the decoded recording, and
 * choosing the file again then transcribed its start a second time. It is added only once
 * a person ticks that they reviewed it: Whisper mishears names, numbers and dates,
 * and on 6 November one misheard date became a cited wrong answer three times out
 * of three. What is added is the draft's text, sent exactly as pasted text is,
 * through FR-09's own route; the recording itself never leaves the browser. The
 * server cannot tell a reviewed transcript from a pasted one, so this screen is
 * where the review is enforced, and the front-end suite holds it.
 */
export default function Meetings() {
  useDocumentTitle('Meeting transcripts')
  const { user } = useAuth()
  const location = useLocation()
  // A successful delete returns here with the title it removed (MeetingDetail).
  const deletedTitle = typeof location.state?.deleted === 'string' ? location.state.deleted : null
  const meetingsResource = useApiResource(listMeetings)
  const meetings = meetingsResource.data ?? []

  // Everyone who could be named as having taken part, which is every signed-in
  // user and is read the same way whatever role is asking.
  //
  // A failure here is not this screen's failure: the transcript can still be
  // ingested without attendees, so the list simply stays empty and the form says
  // so rather than showing a control that cannot be filled.
  const directory = useApiResource(listUserDirectory)
  const candidates = directory.data ?? []

  const [values, setValues] = useState(EMPTY_FORM)
  const [source, setSource] = useState(TRANSCRIPT_SOURCE.text)
  const [file, setFile] = useState(null)
  const [attendees, setAttendees] = useState([])
  const [visibility, setVisibility] = useState(VISIBILITY_EVERYONE)
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  // D-123: the recording's draft, whether a person has reviewed it, whether
  // a run is going, and a key that gives the transcriber a fresh start once its
  // draft has been added.
  const [recordingDraft, setRecordingDraft] = useState('')
  const [draftReviewed, setDraftReviewed] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [transcriberKey, setTranscriberKey] = useState(0)
  // Set once the recording option is first chosen, so the transcriber is mounted (and asks the
  // server whether transcription is available) only for someone who wants it.
  const [recordingOpened, setRecordingOpened] = useState(false)
  const reviewId = useId()
  // The error summary. Focus moves here when a submission is refused, so a
  // keyboard user is taken to the reason instead of being left on the button.
  const errorSummaryRef = useRef(null)
  const headingRef = useRef(null)

  // New machine text has not been reviewed, so a tick given before it arrived is taken back: a
  // run stopped, ticked and resumed would otherwise carry its later segments in unread (the
  // security review of 11 November, finding 4).
  const appendToRecordingDraft = useCallback((text) => {
    setRecordingDraft((draft) => appendToDraft(draft, text))
    setDraftReviewed(false)
  }, [])

  // A draft not yet added is work the person would lose by closing the tab, so
  // the browser asks first. It cannot ask on a move within the app, which leaves
  // this form and its draft behind; the draft can be saved as a text file.
  useEffect(() => {
    if (!recordingDraft.trim()) return undefined
    function warn(event) {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [recordingDraft])

  useEffect(() => {
    if (formError) errorSummaryRef.current?.focus()
  }, [formError])

  // Arriving from a delete: the dialogue and the button that opened it are gone,
  // so focus starts at the top of the list it returned to, with the notice under
  // the heading.
  useEffect(() => {
    if (deletedTitle) headingRef.current?.focus()
  }, [deletedTitle])

  const visibilityOptions = visibilityOptionsFor(user?.role)

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
  }

  /**
   * Switching source clears the other half, so both can never be submitted. A
   * recording's draft is kept apart and is not cleared: it is a person's work,
   * and it is submitted only from the recording option.
   */
  function handleSourceChange(next) {
    if (next === TRANSCRIPT_SOURCE.recording) setRecordingOpened(true)
    setSource(next)
    setFile(null)
    setValues((current) => ({ ...current, transcript_text: '' }))
    setFieldErrors((current) => ({ ...current, transcript_text: undefined, file: undefined, reviewed: undefined }))
  }

  function resetForm() {
    setValues(EMPTY_FORM)
    setFile(null)
    setAttendees([])
    setFieldErrors({})
    if (source === TRANSCRIPT_SOURCE.recording) {
      // The draft was added (or stored, on a 422): it is no longer unsaved work.
      setRecordingDraft('')
      setDraftReviewed(false)
      setTranscriberKey((key) => key + 1)
    }
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
    if (error.status === 429) {
      // Two kinds, told apart by `code` alone; `detail` is never read. D-85's: another
      // upload, transcript or reprocess of this user's is still being processed, which
      // names no time because the reply carries none. Otherwise D-79's ingestion
      // limit, shared with document upload and reprocess, checked before the body is
      // validated, which says when from `Retry-After`. Neither stored anything: the
      // form keeps what was entered, nothing is marked against a field, and the list
      // is not re-read.
      setFormError(
        error.code === INGESTION_IN_FLIGHT_CODE
          ? TEXT.meetingInFlight
          : TEXT.meetingLimitReached(whenToRetry(error.retryAfter)),
      )
      return
    }
    const extracted = extractFieldErrors(error, FIELDS)
    setFieldErrors(extracted.fieldErrors)
    setFormError(extracted.formError ?? TEXT.meetingRejected)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setNotice(null)
    const fromRecording = source === TRANSCRIPT_SOURCE.recording
    const clientErrors = validateMeetingIngestion({
      title: values.title,
      meetingDate: values.meeting_date,
      transcriptText: fromRecording ? recordingDraft : values.transcript_text,
      source,
      file,
      reviewed: draftReviewed,
      transcribing,
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
        // Exactly one of these reaches the API (src/api/meetings.js). A
        // recording's reviewed draft goes as pasted text does (D-123).
        transcriptText:
          source === TRANSCRIPT_SOURCE.text
            ? values.transcript_text
            : fromRecording
              ? recordingDraft
              : undefined,
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

  /**
   * FR-09's attendee association, offered to every role.
   *
   * The directory returns a name and an address and no role (D-34), so that is
   * what an option shows: nothing here sorts, groups or labels by standing in
   * the organisation, and there is no field to do it with. The hint says what
   * naming someone does and does not do, because an Employee can now name an
   * Administrator and it has to be plain that this grants nothing (D-16,
   * CLAUDE.md §6, invariant 3).
   */
  let attendeeControl
  if (directory.loading) {
    attendeeControl = (
      <p className="meeting-form__note" role="status">
        {TEXT.loadingAttendees}
      </p>
    )
  } else if (candidates.length > 0) {
    // One person at a time into a visible list, no modifier keys (usability
    // finding 5: the Ctrl+click listbox this replaces lost selections silently).
    attendeeControl = (
      <AttendeePicker
        legend="Attendees (optional)"
        hint={TEXT.attendeesHint}
        options={candidates}
        value={attendees}
        error={fieldErrors.attendees}
        disabled={submitting}
        onChange={setAttendees}
      />
    )
  } else {
    // Nobody to choose from — the read failed, or it came back empty. Either way
    // the transcript is still the point and can still be added, which is what
    // the note says instead of leaving an empty control on the form.
    attendeeControl = (
      <p className="meeting-form__note">
        {TEXT.attendeesUnavailable} {TEXT.attendeesHint}
      </p>
    )
  }

  return (
    <div className="repository-page">
      <h1 ref={headingRef} tabIndex={-1}>
        Meeting transcripts
      </h1>
      {deletedTitle ? <Notice variant="info">{TEXT.meetingsDeleted(deletedTitle)}</Notice> : null}

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
              { value: TRANSCRIPT_SOURCE.recording, label: TEXT.meetingSourceRecording },
            ].map((option) => (
              <div className="meeting-form__choice" key={option.value}>
                <input
                  type="radio"
                  id={`transcript-source-${option.value}`}
                  name="transcript-source"
                  value={option.value}
                  checked={source === option.value}
                  // Held while a recording is being transcribed: leaving the option
                  // would end the run, though never the draft.
                  disabled={submitting || transcribing}
                  onChange={() => handleSourceChange(option.value)}
                />
                <label htmlFor={`transcript-source-${option.value}`}>{option.label}</label>
              </div>
            ))}
          </fieldset>

          {/* Kept mounted once opened, hidden while another source is chosen, so a paused run
              keeps its decoded recording and its place. Hidden, it takes no page-wide drop. */}
          {recordingOpened ? (
            <div hidden={source !== TRANSCRIPT_SOURCE.recording}>
              <RecordingTranscriber
                key={transcriberKey}
                active={source === TRANSCRIPT_SOURCE.recording}
                disabled={submitting}
                onText={appendToRecordingDraft}
                onBusyChange={setTranscribing}
              />
            </div>
          ) : null}

          {source === TRANSCRIPT_SOURCE.recording ? (
            <>
              {recordingDraft.trim() ? (
                <Notice variant="info" title={TEXT.draftReviewTitle}>
                  {TEXT.draftReviewNotice}
                </Notice>
              ) : null}
              {/* Shown once there is something to show in it, a run filling it, or
                  a refusal to say against it; an empty box beside a server with
                  transcription off would offer a place for text that cannot come. */}
              {recordingDraft || transcribing || fieldErrors.transcript_text ? (
                <TextAreaInput
                  label={TEXT.draftLabel}
                  name="recording_draft"
                  rows={12}
                  hint={TEXT.draftHint}
                  value={recordingDraft}
                  error={fieldErrors.transcript_text}
                  // Read-only while segments are still arriving, so an edit is never
                  // overtaken by the next one; editable as soon as the run ends.
                  readOnly={transcribing}
                  disabled={submitting}
                  onChange={(event) => {
                    setRecordingDraft(event.target.value)
                    setFieldErrors((current) => ({ ...current, transcript_text: undefined }))
                  }}
                />
              ) : null}
              {recordingDraft.trim() ? (
                <>
                  <div className="field">
                    <div className="meeting-form__review">
                      <input
                        type="checkbox"
                        id={reviewId}
                        checked={draftReviewed}
                        disabled={submitting || transcribing}
                        aria-invalid={fieldErrors.reviewed ? true : undefined}
                        aria-describedby={fieldErrors.reviewed ? `${reviewId}-error` : undefined}
                        onChange={(event) => {
                          setDraftReviewed(event.target.checked)
                          setFieldErrors((current) => ({ ...current, reviewed: undefined }))
                        }}
                      />
                      <label htmlFor={reviewId}>{TEXT.draftReviewed}</label>
                    </div>
                    {fieldErrors.reviewed ? (
                      <p id={`${reviewId}-error`} className="field__error">
                        <span className="visually-hidden">Error: </span>
                        {fieldErrors.reviewed}
                      </p>
                    ) : null}
                  </div>
                  <div className="meeting-form__draft-actions">
                    {/* Enabled while segments are still arriving too: what is saved is the
                        draft as it stands, and keeping it is the point (invariant 8). */}
                    <Button
                      variant="secondary"
                      onClick={() => saveTextFile(recordingDraft, draftFilename(values.title))}
                    >
                      {TEXT.draftSave}
                    </Button>
                  </div>
                </>
              ) : null}
            </>
          ) : source === TRANSCRIPT_SOURCE.text ? (
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
            // The zone states the chosen file itself (usability finding 2), and the
            // whole page takes a dropped file while it is shown (finding 3).
            <FileDropZone
              label="Transcript file"
              hint={TEXT.uploadDropHint}
              accept={FILE_INPUT_ACCEPT}
              disabled={submitting}
              disabledReason={TEXT.meetingFileBusy}
              error={fieldErrors.file}
              status={file ? TEXT.meetingFileChosen(file.name) : TEXT.meetingFileNone}
              pageDrop
              onFiles={(files) => {
                setFile(files[0])
                setFieldErrors((current) => ({ ...current, file: undefined }))
              }}
            />
          )}

          {attendeeControl}

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
            <Button type="submit" loading={submitting} disabled={submitting || transcribing}>
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
