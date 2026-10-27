import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { reprocessDocument, uploadDocument } from '../api/documents.js'
import useAuth from '../auth/useAuth.js'
import Button from '../components/Button.jsx'
import FileDropZone from '../components/FileDropZone.jsx'
import Notice from '../components/Notice.jsx'
import ProgressBar from '../components/ProgressBar.jsx'
import SelectInput from '../components/SelectInput.jsx'
import TextInput from '../components/TextInput.jsx'
import { DOCUMENT_STATUS, TEXT, VALIDATION } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
// The per-code mapping lives outside this file so it can be run without a test
// runner (D-25); D-51's suppressed retry is one of its rules.
import { failureFor } from '../utils/uploadFailure.js'
import { FILE_INPUT_ACCEPT, screenFile, titleFromFilename } from '../utils/uploads.js'
import { rolesForVisibility, VISIBILITY_EVERYONE, visibilityOptionsFor } from '../utils/visibility.js'
import './Upload.css'

/** Row states. Each drives one visible status and one set of actions. */
const READY = 'ready' // chosen, not yet sent
const REJECTED = 'rejected' // refused client-side; never transferred
const UPLOADING = 'uploading' // bytes in flight, determinate bar
const PROCESSING = 'processing' // transfer done, server extracting and indexing
const DONE = 'done' // 201
const FAILED = 'failed' // the server refused it or could not process it
// D-79's ingestion limit was reached: this file got the 429, or was still queued
// behind the one that did. Nothing was stored and nothing is wrong with the file,
// so it stays in the queue, keeps its title field, and the Upload button sends it
// again. Neither failed nor invalid, and styled as neither.
const LIMITED = 'limited'

let nextRowId = 0

const sizeFormat = new Intl.NumberFormat('en-AU', { maximumFractionDigits: 1 })

/** Human file size. Decimal MB, matching the 50 MB ceiling the server applies. */
function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} bytes`
  if (bytes < 1024 * 1024) return `${sizeFormat.format(bytes / 1024)} KB`
  return `${sizeFormat.format(bytes / (1024 * 1024))} MB`
}

/** Visible state text for a row, before the server has recorded a status. */
const STATUS_TEXT = {
  [READY]: 'Ready to upload',
  [REJECTED]: 'Not uploaded',
  [UPLOADING]: TEXT.uploadTransferring,
  [PROCESSING]: TEXT.uploadProcessing,
  [DONE]: DOCUMENT_STATUS.indexed,
  [FAILED]: 'Failed',
  [LIMITED]: TEXT.uploadLimitedStatus,
}

/** The rows the Upload button sends: chosen and not sent, or held back by the limit. */
function isPending(row) {
  return row.state === READY || row.state === LIMITED
}

/**
 * One queued file.
 *
 * FR-08: "Each file shows a progress indicator and an individual progress bar
 * during upload." The bar belongs to the row, and so does the outcome: the
 * status, the message and the retry action all sit beside the file they concern.
 */
export function UploadRow({ row, onTitleChange, onRetry, onRemove, titleRef }) {
  const busy = row.state === UPLOADING || row.state === PROCESSING
  const statusText = STATUS_TEXT[row.state]

  return (
    <li className="upload-row">
      <p className="upload-row__file">
        <span className="upload-row__name">{row.file.name}</span>{' '}
        <span className="upload-row__size">{formatSize(row.file.size)}</span>
      </p>

      {/* A title is required per file (FR-08). Defaulted from the filename so the
          common case is one click, and editable because a filename is rarely the
          title anyone would search for. */}
      {row.state === REJECTED ? null : (
        <TextInput
          label={`Title for ${row.file.name}`}
          value={row.title}
          error={row.titleError}
          disabled={busy}
          required
          // React 19 passes `ref` to a function component as an ordinary prop,
          // so TextInput's `...rest` puts it on the input itself. That is what
          // lets focus move to the first row missing a title.
          ref={titleRef}
          onChange={(event) => onTitleChange(row.id, event.target.value)}
        />
      )}

      {busy ? (
        <ProgressBar
          label={
            row.state === PROCESSING
              ? `Processing ${row.file.name}`
              : `Upload progress for ${row.file.name}`
          }
          // Indeterminate once the last byte has gone: the server is extracting,
          // chunking and embedding, and reports nothing until it answers.
          value={row.state === UPLOADING ? row.progress : null}
          valueText={row.state === PROCESSING ? TEXT.uploadProcessing : undefined}
        />
      ) : null}

      <p className="upload-row__status">
        <span className={`upload-status upload-status--${row.state}`}>
          {/* The status the server recorded, in its own vocabulary, once there is
              one; before that, the state of the transfer. */}
          {row.document?.status ?? statusText}
        </span>
        {row.message ? <span className="upload-row__message">{row.message}</span> : null}
      </p>

      <div className="upload-row__actions">
        {row.retryable ? (
          <Button variant="secondary" onClick={() => onRetry(row.id)} disabled={busy}>
            {TEXT.uploadRetry}
          </Button>
        ) : null}
        {busy ? null : (
          <Button
            variant="secondary"
            aria-label={`${TEXT.uploadRemove} ${row.file.name}`}
            onClick={() => onRemove(row.id)}
          >
            {TEXT.uploadRemove}
          </Button>
        )}
      </div>
    </li>
  )
}

/**
 * FR-08 document upload.
 *
 * A drag-and-drop area and a file picker feed one queue; each row carries its
 * own title, its own progress bar and its own outcome. Uploads run one at a time
 * so a queue of large files does not compete for the connection, and so the
 * row that is moving is the one the progress bar belongs to.
 *
 * Format and size are checked before any transfer begins, which FR-08 requires
 * ("rejected immediately client-side"), and both checks are conveniences: the
 * server decides on the file signature and on the bytes it actually received,
 * and its answer — 415, 413, 409, 403, 400 or the 422 that carries FR-08's
 * "Processing failed. Please try again" — is shown against that file's row
 * (CLAUDE.md §6, invariant 4).
 *
 * **A 429 is not the file's answer, and the queue does not treat it as one**
 * (D-79). The ingestion limit is the user's, shared by upload, meeting ingestion
 * and reprocess, and the server checks it before it validates the file. So when one
 * file gets a 429, the queue stops: every later file would get the same answer, and
 * each of them would be sent in full to get it. That file, and every file still
 * queued behind it, says the upload limit has been reached, that it was not stored,
 * and when uploading can resume, from `Retry-After`. Each keeps its title field
 * and stays in the queue, and pressing Upload again sends it as a new upload,
 * because there is nothing stored to reprocess. None is marked failed or invalid.
 * Files already sent keep the outcome they had.
 */
export default function Upload() {
  useDocumentTitle('Upload documents')
  const { user } = useAuth()
  const [rows, setRows] = useState([])
  const [department, setDepartment] = useState('')
  const [visibility, setVisibility] = useState(VISIBILITY_EVERYONE)
  const [busy, setBusy] = useState(false)
  // Single polite live region: row status changes are announced here once, rather
  // than every row being its own live region and talking over the others.
  const [announcement, setAnnouncement] = useState('')
  // Focus goes to the first row missing a title when the queue will not send.
  const titleRefs = useRef(new Map())

  const visibilityOptions = visibilityOptionsFor(user?.role)
  const pending = rows.filter(isPending)

  function updateRow(id, changes) {
    setRows((current) => current.map((row) => (row.id === id ? { ...row, ...changes } : row)))
  }

  function announce(name, message) {
    setAnnouncement(TEXT.statusAnnouncement(name, message))
  }

  /** Files from the picker or from a drop. Screened before anything is sent. */
  function handleFiles(files) {
    const added = files.map((file) => {
      const rejection = screenFile(file)
      nextRowId += 1
      return {
        id: `row-${nextRowId}`,
        file,
        title: titleFromFilename(file.name),
        titleError: null,
        // FR-08: an unsupported format (or an oversized file) is refused here and
        // never transferred. It stays in the queue so the reason is visible.
        state: rejection ? REJECTED : READY,
        message: rejection,
        progress: 0,
        document: null,
        retryable: false,
      }
    })
    setRows((current) => [...current, ...added])
    const rejected = added.find((row) => row.state === REJECTED)
    if (rejected) announce(rejected.file.name, rejected.message)
  }

  /**
   * Sends one file. Resolves to the message of D-79's ingestion limit when the
   * server answered 429, so the queue can stop and say the same of the files behind
   * it, and to null for every other outcome.
   */
  async function send(row) {
    updateRow(row.id, {
      state: UPLOADING,
      progress: 0,
      message: null,
      titleError: null,
      document: null,
      retryable: false,
    })
    try {
      const stored = await uploadDocument(
        {
          file: row.file,
          title: row.title.trim(),
          department: department.trim(),
          visibleToRoles: rolesForVisibility(visibility),
        },
        {
          onProgress: (percent) =>
            updateRow(row.id, {
              progress: percent,
              state: percent >= 100 ? PROCESSING : UPLOADING,
            }),
        },
      )
      // 201, in one of two shapes. "Indexed" is FR-08's own word for the success
      // status; "Partially indexed" means some passages did not make it into the
      // index, and saying so plainly is the honest version of a green tick.
      const partial = stored?.status === DOCUMENT_STATUS.partiallyIndexed
      const message = partial ? TEXT.uploadPartiallyIndexed : TEXT.uploadIndexed
      updateRow(row.id, { state: DONE, document: stored, message, progress: 100 })
      announce(row.file.name, stored?.status ?? message)
      return null
    } catch (error) {
      const failure = failureFor(error)
      updateRow(row.id, {
        // The limit stored nothing and found nothing wrong with the file: queued,
        // not failed (see LIMITED).
        state: failure.limited ? LIMITED : FAILED,
        message: failure.message,
        titleError: failure.titleError ?? null,
        document: failure.document ?? null,
        retryable: Boolean(failure.retryable),
      })
      announce(row.file.name, failure.message)
      return failure.limited ? failure.message : null
    }
  }

  async function handleUpload() {
    // A title per file is required, so the queue does not start and then stop
    // halfway through on a 400 the form could have caught.
    const missing = pending.filter((row) => !row.title.trim())
    if (missing.length > 0) {
      setRows((current) =>
        current.map((row) =>
          missing.some((candidate) => candidate.id === row.id)
            ? { ...row, titleError: VALIDATION.documentTitleRequired }
            : row,
        ),
      )
      titleRefs.current.get(missing[0].id)?.focus()
      return
    }

    setBusy(true)
    // Sequential: `pending` was read before the first await, and each send()
    // updates only its own row, so the queue is not re-derived mid-flight.
    for (const [index, row] of pending.entries()) {
      const limit = await send(row)
      if (limit) {
        // D-79: the limit is the user's, so every file still queued behind this one
        // would get the same 429. None of them is sent, and each says what its row
        // above says, because the same is true of it: not stored, and when uploading
        // can resume. Only the 429'd file is announced, once.
        const unsent = new Set(pending.slice(index + 1).map((candidate) => candidate.id))
        setRows((current) =>
          current.map((candidate) =>
            unsent.has(candidate.id) ? { ...candidate, state: LIMITED, message: limit, retryable: false } : candidate,
          ),
        )
        break
      }
    }
    setBusy(false)
  }

  async function handleRetry(id) {
    const row = rows.find((candidate) => candidate.id === id)
    if (!row) return
    setBusy(true)
    // A row that reached the server carries the document it stored, so the retry
    // re-runs ingestion against that stored original rather than sending the
    // file a second time (D-32). A row with no document never arrived at all —
    // a network failure — so for that one there is nothing on the server to
    // reprocess and the file itself is sent again.
    if (row.document?.doc_id) await reprocess(row)
    else await send(row)
    setBusy(false)
  }

  async function reprocess(row) {
    updateRow(row.id, { state: PROCESSING, message: TEXT.uploadProcessing, progress: 100 })
    try {
      const stored = await reprocessDocument(row.document.doc_id)
      const partial = stored?.status === DOCUMENT_STATUS.partiallyIndexed
      const message = partial ? TEXT.uploadPartiallyIndexed : TEXT.uploadIndexed
      updateRow(row.id, { state: DONE, document: stored, message, progress: 100 })
      announce(row.file.name, stored?.status ?? message)
    } catch (error) {
      // A 429 here re-ran nothing (D-79): the document is still stored at the status
      // it had, which the row goes on showing, with the retry still offered and the
      // limit's sentence saying when it can be pressed again.
      const failure = failureFor(error, { reprocess: true })
      updateRow(row.id, {
        state: FAILED,
        message: failure.message,
        // The document is kept from the failed response where there is one, so a
        // second retry still knows which document to reprocess.
        document: failure.document ?? row.document,
        retryable: Boolean(failure.retryable),
      })
      announce(row.file.name, failure.message)
    }
  }

  function handleRemove(id) {
    titleRefs.current.delete(id)
    setRows((current) => current.filter((row) => row.id !== id))
  }

  function registerTitleRef(id) {
    return (element) => {
      if (element) titleRefs.current.set(id, element)
      else titleRefs.current.delete(id)
    }
  }

  return (
    <div className="upload-page">
      <h1>Upload documents</h1>
      <p>
        Add documents to the knowledge base. Each file is extracted, split into passages and indexed as it
        arrives, so the status below is the real outcome rather than a receipt. Everything that has been
        uploaded is in the <Link to="/documents">document repository</Link>.
      </p>

      <FileDropZone
        label="Choose files"
        hint={TEXT.uploadDropHint}
        accept={FILE_INPUT_ACCEPT}
        multiple
        disabled={busy}
        onFiles={handleFiles}
      />

      <fieldset className="upload-options">
        <legend>Applies to every file in this queue</legend>
        <TextInput
          label="Department (optional)"
          value={department}
          disabled={busy}
          onChange={(event) => setDepartment(event.target.value)}
        />
        {/* One option means no choice to make, so an Employee is told the scope
            instead of being given a select with a single entry. Narrowing the
            options is usability; the server re-checks the list it is sent
            (CLAUDE.md §6, invariant 4). */}
        {visibilityOptions.length > 1 ? (
          <SelectInput
            label="Visible to"
            hint={TEXT.visibilityHint}
            options={visibilityOptions}
            value={visibility}
            disabled={busy}
            onChange={(event) => setVisibility(event.target.value)}
          />
        ) : (
          <p className="upload-options__note">{TEXT.visibilityFixed}</p>
        )}
      </fieldset>

      <h2 id="upload-queue-heading">Files</h2>
      {rows.length === 0 ? (
        <Notice variant="info">{TEXT.uploadQueueEmpty}</Notice>
      ) : (
        <ul className="upload-queue" aria-labelledby="upload-queue-heading">
          {rows.map((row) => (
            <UploadRow
              key={row.id}
              row={row}
              titleRef={registerTitleRef(row.id)}
              onTitleChange={(id, title) => updateRow(id, { title, titleError: null })}
              onRetry={handleRetry}
              onRemove={handleRemove}
            />
          ))}
        </ul>
      )}

      <div className="upload-page__actions">
        <Button loading={busy} disabled={busy || pending.length === 0} onClick={handleUpload}>
          {busy ? 'Uploading…' : `Upload ${pending.length} ${pending.length === 1 ? 'file' : 'files'}`}
        </Button>
      </div>

      {/* Status changes are announced once, politely. The same text is on screen
          against each row, so nothing here is available only to a screen reader
          and nothing on screen is unavailable to one (WCAG 2.1 SC 1.1.1). */}
      <p className="visually-hidden" role="status" aria-live="polite">
        {announcement}
      </p>
    </div>
  )
}
