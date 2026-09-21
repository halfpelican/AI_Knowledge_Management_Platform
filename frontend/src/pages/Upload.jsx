import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
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
import { retryMessageFor } from '../utils/documentStatus.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
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

let nextRowId = 0

const sizeFormat = new Intl.NumberFormat('en-AU', { maximumFractionDigits: 1 })

/** Human file size. Decimal MB, matching the 50 MB ceiling the server applies. */
function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} bytes`
  if (bytes < 1024 * 1024) return `${sizeFormat.format(bytes / 1024)} KB`
  return `${sizeFormat.format(bytes / (1024 * 1024))} MB`
}

/**
 * What a failed upload shows against its own row.
 *
 * Every code FR-08 enumerates gets the message for that case, against that file,
 * rather than a page-level banner: in a queue of five files a banner cannot say
 * which one it means. Only the two cases a second attempt could plausibly change
 * are retryable — the 422, which is FR-08's own "Processing failed. Please try
 * again" action, and a request that never reached the server.
 *
 * The 409 does not use `error.message`: the client's generic 409 text is FR-01's
 * duplicate email address, while FR-08's 409 is a document whose *content* has
 * been uploaded before, compared by hash and not by filename.
 */
function failureFor(error) {
  if (!(error instanceof ApiError)) {
    return { message: messageForStatus(NETWORK_ERROR_STATUS), retryable: true }
  }
  switch (error.status) {
    case 422:
      // The body still carries `doc_id` and `status`, so the row can name the
      // document that was stored but could not be indexed (the file is kept —
      // NFR-20, a failed AI step never discards the source). The status also
      // selects the wording: only an "Indexing failed" is a failure that trying
      // again can recover, so the other two say what would actually change the
      // outcome instead of inviting a retry that cannot work (D-32).
      return {
        message: retryMessageFor(error.details?.status),
        retryable: true,
        document: error.details,
      }
    case 415:
      // The signature disagreed with the extension. The same message the
      // client-side check uses, because it is the same refusal on better evidence.
      return { message: VALIDATION.fileTypeUnsupported }
    case 413:
      return { message: VALIDATION.fileTooLarge }
    case 409:
      return { message: TEXT.uploadDuplicate }
    case 403:
      // The role lacks `contribute_content`. The form never offers a scope
      // excluding the uploader's own role, so D-29's 403 is not reachable here.
      return { message: TEXT.uploadNotPermitted }
    case 400: {
      const { fieldErrors } = extractFieldErrors(error, ['title', 'file', 'visible_to_roles'])
      return {
        message: fieldErrors.file ?? fieldErrors.visible_to_roles ?? TEXT.uploadRejected,
        titleError: fieldErrors.title ?? null,
      }
    }
    default:
      return { message: error.message, retryable: error.status === NETWORK_ERROR_STATUS }
  }
}

/** Visible state text for a row, before the server has recorded a status. */
const STATUS_TEXT = {
  [READY]: 'Ready to upload',
  [REJECTED]: 'Not uploaded',
  [UPLOADING]: TEXT.uploadTransferring,
  [PROCESSING]: TEXT.uploadProcessing,
  [DONE]: DOCUMENT_STATUS.indexed,
  [FAILED]: 'Failed',
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
  const pending = rows.filter((row) => row.state === READY)

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
    } catch (error) {
      const failure = failureFor(error)
      updateRow(row.id, {
        state: FAILED,
        message: failure.message,
        titleError: failure.titleError ?? null,
        document: failure.document ?? null,
        retryable: Boolean(failure.retryable),
      })
      announce(row.file.name, failure.message)
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
    for (const row of pending) await send(row)
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
      const failure = failureFor(error)
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
