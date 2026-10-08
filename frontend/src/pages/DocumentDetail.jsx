import { useCallback, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { deleteDocument, fetchDocument } from '../api/documents.js'
import Button from '../components/Button.jsx'
import Dialog from '../components/Dialog.jsx'
import Notice from '../components/Notice.jsx'
import { TEXT } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
import './Repository.css'

/** The three tag dimensions the detail carries, with their labels (D-72). */
const TAG_DIMENSIONS = [
  ['project', TEXT.documentFieldProject],
  ['process', TEXT.documentFieldProcess],
  ['topic', TEXT.documentFieldTopic],
]

/**
 * The repository address to go back to: the one the list was reached by, which
 * the list passes as router state on each title, or the bare list when the view
 * was opened another way — a citation, the dashboard, a bookmark. Only a query
 * string is accepted, and it is always put under `/documents`, so the state can
 * never send the user anywhere but the repository.
 */
function repositoryPathFrom(state) {
  const from = state?.from
  return typeof from === 'string' && from.startsWith('?') ? `/documents${from}` : '/documents'
}

/** A document's tag names in one dimension, as the server sent them, or none. */
function tagsIn(tags, dimension) {
  const names = tags?.[dimension]
  return Array.isArray(names) ? names : []
}

/**
 * FR-15's detail view: "selecting a document opens a detail view showing its
 * metadata, extracted content, and a download link", and deletion that "requires
 * confirmation and is available only to users holding the appropriate
 * permission". It is also where a document citation lands (D-46).
 *
 * **Extracted content is rendered as text.** It is a document's whole extracted
 * text (D-63), untrusted input from whoever uploaded the file, so it goes into
 * the page as a React text child and never through `dangerouslySetInnerHTML`;
 * the line breaks are kept by CSS (`white-space: pre-wrap`), not by turning them
 * into markup. Its empty state is keyed on `extracted_text` being null — the
 * document has no extracted content — and not on the status, because which
 * statuses leave text behind is a fact of the ingestion path (D-63).
 *
 * **The delete control is shown only when the detail says `can_delete`**, and it
 * asks for confirmation before sending anything. That is usability; the server
 * checks `manage_documents` on every delete whatever this screen showed
 * (CLAUDE.md §6, invariant 4). A 204 returns to the repository at the filters the
 * user came from.
 *
 * A document outside the caller's scope answers 404, exactly as an id that names
 * nothing does, and both render the same message. The screen never distinguishes
 * "no such document" from "not yours to read" (CLAUDE.md §6, invariant 1).
 */
export default function DocumentDetail() {
  const { docId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const listPath = repositoryPathFrom(location.state)
  // Stable per id: the hook's effect re-reads when the route parameter changes
  // and not on every render.
  const loader = useCallback(({ signal }) => fetchDocument(docId, { signal }), [docId])
  // Named `record`, not `document`: a local called `document` would shadow the
  // browser global inside every line of this component.
  const { data: record, loading, error, reload } = useApiResource(loader)
  useDocumentTitle(record?.title ?? 'Document')

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
        <p role="status">{TEXT.loadingDocument}</p>
      </div>
    )
  }

  if (error || !record) {
    // A 200 with no body is not something the contract allows; it is handled with
    // the 404 so the render below can read the record without guarding each field.
    const notFound = !record || error?.status === 404
    return (
      <div className="repository-page">
        <h1>Document</h1>
        <Notice variant="error" title={notFound ? TEXT.documentNotFoundTitle : TEXT.documentLoadFailed}>
          {notFound ? TEXT.documentRecordNotFound : error.message}
        </Notice>
        <div className="repository-page__actions">
          {notFound ? null : (
            <Button variant="secondary" onClick={reload}>
              {TEXT.uploadRetry}
            </Button>
          )}
          <Link to={listPath}>{TEXT.documentBackToList}</Link>
        </div>
      </div>
    )
  }

  const canDelete = record.can_delete === true && !deleteRefused
  const extractedText = record.extracted_text
  const hasText = typeof extractedText === 'string' && extractedText.length > 0

  async function confirmDelete() {
    if (deleteInFlight.current) return
    deleteInFlight.current = true
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteDocument(record.doc_id)
      // Replace, so Back from the list does not return to a record that is gone.
      navigate(listPath, { replace: true, state: { deleted: record.title } })
    } catch (caught) {
      deleteInFlight.current = false
      setDeleting(false)
      setConfirming(false)
      if (caught instanceof ApiError && caught.status === 403) {
        setDeleteRefused(true)
        setDeleteError(TEXT.documentDeleteNotPermitted)
      } else if (caught instanceof ApiError && caught.status === 404) {
        // Gone, or now outside the caller's scope: one message for both.
        setDeleteError(TEXT.documentRecordNotFound)
      } else {
        // Fixed, user-facing text from the API client. Never a backend string.
        setDeleteError(
          caught instanceof ApiError ? caught.message : messageForStatus(NETWORK_ERROR_STATUS),
        )
      }
    }
  }

  return (
    <div className="repository-page document-detail">
      <h1 ref={headingRef} tabIndex={-1}>
        {record.title}
      </h1>
      <p>
        <Link to={listPath}>{TEXT.documentBackToList}</Link>
      </p>

      {deleteError ? (
        <Notice variant="error" title={TEXT.documentDeleteFailed}>
          {deleteError}
        </Notice>
      ) : null}

      <dl className="record-meta">
        <dt>{TEXT.documentFieldType}</dt>
        <dd>{String(record.file_type ?? '').toUpperCase()}</dd>
        <dt>{TEXT.documentFieldUploader}</dt>
        <dd>{record.uploaded_by || TEXT.documentNotRecorded}</dd>
        <dt>{TEXT.documentFieldUploaded}</dt>
        <dd>
          <time dateTime={record.uploaded_at}>{formatDate(record.uploaded_at)}</time>
        </dd>
        <dt>{TEXT.documentFieldStatus}</dt>
        <dd>{record.status}</dd>
        <dt>{TEXT.documentFieldDepartment}</dt>
        <dd>{record.department || TEXT.documentNotRecorded}</dd>
        {/* The scope that decides who can read it, as the server recorded it. */}
        <dt>{TEXT.documentFieldVisibleTo}</dt>
        <dd>{(record.visible_to_roles ?? []).join(', ')}</dd>
        {/* The tags by dimension (D-72, D-74). Department is the field above. */}
        {TAG_DIMENSIONS.map(([dimension, label]) => {
          const names = tagsIn(record.tags, dimension)
          return [
            <dt key={`${dimension}-term`}>{label}</dt>,
            <dd key={`${dimension}-value`}>{names.length > 0 ? names.join(', ') : TEXT.documentNoTags}</dd>,
          ]
        })}
      </dl>

      {/* The document's actions. Stage 5 item 2a adds FR-15's download link here,
          first in this row, pointing at the scoped download route and never at
          the stored file's path. Nothing is rendered for it until that route
          exists. */}
      {canDelete ? (
        <div className="repository-page__actions document-detail__actions">
          <Button variant="secondary" onClick={() => setConfirming(true)}>
            {TEXT.documentDelete}
          </Button>
        </div>
      ) : null}

      <h2 id="extracted-content-heading">{TEXT.documentExtractedHeading}</h2>
      {hasText ? (
        <>
          <p className="document-detail__note">{TEXT.documentExtractedNote}</p>
          {/* A text child, so React escapes it: markup in the document's text is
              shown as the characters it is and creates no element. tabIndex 0 so
              a keyboard user can scroll the block, and a labelled region so a
              screen reader announces what it is before reading it. */}
          <div
            className="extracted-text"
            role="region"
            aria-labelledby="extracted-content-heading"
            tabIndex={0}
          >
            {extractedText}
          </div>
        </>
      ) : (
        <Notice variant="info">{TEXT.documentExtractedEmpty}</Notice>
      )}

      {confirming ? (
        <Dialog
          title={TEXT.documentDeleteConfirm(record.title)}
          confirmLabel={TEXT.documentDelete}
          busyLabel={TEXT.documentDeleting}
          cancelLabel={TEXT.documentDeleteCancel}
          busy={deleting}
          returnFocusRef={headingRef}
          onConfirm={confirmDelete}
          onCancel={() => {
            if (!deleting) setConfirming(false)
          }}
        >
          <p>{TEXT.documentDeleteBody}</p>
        </Dialog>
      ) : null}
    </div>
  )
}
