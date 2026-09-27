import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, messageForStatus } from '../api/client.js'
import { listDocuments, reprocessDocument } from '../api/documents.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import { TEXT } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
import { canReprocess, statusMessageFor } from '../utils/documentStatus.js'
import './Repository.css'

/** The roles a document is visible to, as the server recorded them. */
function formatVisibility(roles) {
  return Array.isArray(roles) ? roles.join(', ') : ''
}

/**
 * The repository table as a pure view.
 *
 * FR-15's filtered browsing — the filters, the search box and the sorting — is
 * Stage 5. This is the plain list it builds on, and nothing here anticipates it:
 * a filter control that filtered nothing would be a promise the screen does not
 * keep.
 *
 * The one action a row carries is FR-08's retry, on a document `canReprocess`
 * admits — every status but "Indexed", which has nothing to redo, and "Too large
 * to index", which would stop at the same point on every press (D-51). Those two
 * rows still say where they stand; the sentence goes with the status and not with
 * the button. It belongs here and not only in the upload queue: the queue is in
 * memory, so before this column existed a document left at "Indexing failed"
 * had no route back once the tab was closed. `retryingId` is the doc_id whose
 * reprocess is in flight; while one is running the rest are disabled, so a
 * queue of retries cannot be started by clicking down the column.
 */
export function DocumentTable({ documents, retryingId, onRetry }) {
  if (documents.length === 0) {
    return <Notice variant="info">{TEXT.noDocuments}</Notice>
  }

  const busy = retryingId !== null

  return (
    <div className="table-scroll" role="region" aria-labelledby="documents-heading" tabIndex={0}>
      <table className="data-table">
        <caption className="visually-hidden">Documents in the knowledge base</caption>
        <thead>
          <tr>
            <th scope="col">Title</th>
            <th scope="col">Type</th>
            <th scope="col">Status</th>
            <th scope="col">Uploaded</th>
            <th scope="col">Department</th>
            <th scope="col">Visible to</th>
            <th scope="col">
              <span className="visually-hidden">Action</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {documents.map((record) => {
            const retryable = canReprocess(record.status)
            // Asked separately from the action: "Too large to index" is explained
            // on the row and offered no button (D-51).
            const message = statusMessageFor(record.status)
            const retrying = retryingId === record.doc_id
            return (
              <tr key={record.doc_id}>
                <th scope="row" className="data-table__title">
                  {record.title}
                </th>
                <td className="data-table__type">{String(record.file_type ?? '').toUpperCase()}</td>
                <td className="data-table__status">
                  {/* The status the server recorded, in its own words and never
                      in colour alone. A status that is not "Indexed" carries the
                      sentence for that status (D-32), so the difference between
                      a retry that can work, one that cannot, and one that is not
                      offered at all is on the screen rather than discovered by
                      pressing the button. The sentence is tied to the status and
                      not to the action: the row with no action is the one that
                      most needs explaining. */}
                  {record.status}
                  {message ? <span className="data-table__message">{message}</span> : null}
                </td>
                <td className="data-table__meta">
                  <time dateTime={record.uploaded_at}>{formatDate(record.uploaded_at)}</time>
                </td>
                <td>{record.department || '—'}</td>
                <td className="data-table__meta">{formatVisibility(record.visible_to_roles)}</td>
                <td className="data-table__action">
                  {retryable ? (
                    <Button
                      variant="secondary"
                      loading={retrying}
                      disabled={busy}
                      // Each button names its own document. A column of controls
                      // all called "Try again" tells a screen reader user which
                      // action it is and not which row (WCAG 2.1 SC 2.4.6).
                      aria-label={TEXT.documentRetryLabel(record.title)}
                      onClick={() => onRetry(record)}
                    >
                      {retrying ? TEXT.uploadProcessing : TEXT.uploadRetry}
                    </Button>
                  ) : null}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/**
 * The document repository (FR-08's list and its retry; the foundation FR-15
 * builds filtered browsing on in Stage 5).
 *
 * The list the API returns is already scoped to the caller's role, and the
 * screen shows exactly what it was sent: no count of what was filtered out, no
 * note that there is more, nothing that discloses the existence of material
 * outside the user's scope (CLAUDE.md §6, invariant 1). An empty list and a list
 * emptied by scoping look the same here because they are the same answer. The
 * 404 a retry can receive is handled the same way, since it is the answer both
 * for a document that never existed and for one the caller may not see.
 */
export default function DocumentRepository() {
  useDocumentTitle('Documents')
  const { data, loading, error, reload, setData } = useApiResource(listDocuments)
  const documents = data ?? []
  // The doc_id whose reprocess is in flight, or null. One at a time.
  const [retryingId, setRetryingId] = useState(null)
  const [notice, setNotice] = useState(null)
  // One polite live region for the whole list, rather than one per row: the
  // outcome of a retry is announced once, in the same words the row shows.
  const [announcement, setAnnouncement] = useState('')
  // Where focus goes when the button that had it disappears, which is what a
  // successful retry does to the row it ran on.
  const headingRef = useRef(null)

  /** Replaces one row with the document the server just described. */
  function replaceRow(updated) {
    if (!updated?.doc_id) return
    setData((current) =>
      (current ?? []).map((record) => (record.doc_id === updated.doc_id ? updated : record)),
    )
  }

  function announce(title, status) {
    // The same words the row shows, which now includes the status that is
    // explained without being offered an action (D-51). Announcing the bare
    // status for that one would leave a screen reader user with the single fact
    // the sentence exists to qualify.
    const message = statusMessageFor(status)
    const detail = message ? `${status}. ${message}` : status
    setAnnouncement(TEXT.statusAnnouncement(title, detail))
  }

  /**
   * FR-08's "Processing failed. Please try again" action, from the list.
   *
   * The row is refreshed from what came back rather than from what was hoped
   * for: the 201 carries the document now "Indexed" or "Partially indexed", and
   * the 422 carries it still failed — which is what a file with no text layer
   * will always answer.
   */
  async function handleRetry(record) {
    setRetryingId(record.doc_id)
    setNotice(null)
    try {
      const updated = await reprocessDocument(record.doc_id)
      // Whatever the server says the status is now, never an assumed "Indexed".
      const status = updated?.status ?? record.status
      replaceRow(updated)
      announce(record.title, status)
      // The button is about to unmount, so focus is moved somewhere deliberate
      // instead of being dropped on the document body.
      if (!canReprocess(status)) headingRef.current?.focus()
    } catch (caught) {
      handleRetryError(caught, record)
    } finally {
      setRetryingId(null)
    }
  }

  function handleRetryError(caught, record) {
    if (!(caught instanceof ApiError)) {
      setNotice({ title: TEXT.documentReprocessFailed, text: messageForStatus() })
      return
    }
    switch (caught.status) {
      case 422: {
        // It failed again. The body still carries the document, so the row shows
        // the status the server has now recorded and the sentence that goes with
        // it, and the action stays for every status but the one a further press
        // cannot change — a reprocess can come back "Too large to index", and the
        // button withdraws for the same reason it is never offered (D-51).
        const status = caught.details?.status ?? record.status
        replaceRow(caught.details)
        announce(record.title, status)
        // Same as the success path: the button that had focus is unmounting, so
        // focus is moved somewhere deliberate rather than dropped on the body.
        if (!canReprocess(status)) headingRef.current?.focus()
        return
      }
      case 409:
        // Already indexed, or a copy was indexed while this list sat open.
        setNotice({ title: TEXT.documentReprocessFailed, text: TEXT.documentAlreadyIndexed })
        reload()
        return
      case 404:
        setNotice({ title: TEXT.documentReprocessFailed, text: TEXT.documentNotFound })
        reload()
        return
      case 403:
        setNotice({ title: TEXT.documentReprocessFailed, text: TEXT.documentReprocessNotPermitted })
        return
      default:
        // Fixed, user-facing text from the API client. Never a backend string.
        setNotice({ title: TEXT.documentReprocessFailed, text: caught.message })
    }
  }

  let body
  if (loading) {
    body = <p role="status">{TEXT.loadingDocuments}</p>
  } else if (error && error.status === 403) {
    body = <NotPermitted />
  } else if (error) {
    body = (
      <>
        <Notice variant="error" title={TEXT.documentsLoadFailed}>
          {error.message}
        </Notice>
        <div className="repository-page__actions">
          <Button variant="secondary" onClick={reload}>
            {TEXT.uploadRetry}
          </Button>
        </div>
      </>
    )
  } else {
    body = (
      <>
        {notice ? (
          <Notice variant="error" title={notice.title}>
            {notice.text}
          </Notice>
        ) : null}
        <DocumentTable documents={documents} retryingId={retryingId} onRetry={handleRetry} />
      </>
    )
  }

  return (
    <div className="repository-page">
      <h1 id="documents-heading" ref={headingRef} tabIndex={-1}>
        Documents
      </h1>
      <p>
        Everything you are permitted to see, newest first. <Link to="/upload">Upload a document</Link> to add
        to it.
      </p>
      {body}
      {/* The same words the row shows, announced once. Nothing here is available
          only to a screen reader and nothing on screen is unavailable to one
          (WCAG 2.1 SC 1.1.1). */}
      <p className="visually-hidden" role="status" aria-live="polite">
        {announcement}
      </p>
    </div>
  )
}
