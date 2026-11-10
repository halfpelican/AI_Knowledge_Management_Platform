import { useCallback, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { deleteDocument, documentDownloadUrl, fetchDocument } from '../api/documents.js'
import Button from '../components/Button.jsx'
import Classification from '../components/Classification.jsx'
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
 * The detail's `tags` — the names in each of the three dimensions, sorted, each
 * once, held suggestions excluded — rebuilt from `tag_details` after an FR-10
 * action changed the links. The contract defines `tags` in exactly those terms
 * (docs/api-contract.md, FR-15), so the metadata above the classification
 * section keeps agreeing with it without a second read of the document.
 */
function tagsFrom(tagDetails) {
  const tags = Object.fromEntries(TAG_DIMENSIONS.map(([dimension]) => [dimension, []]))
  for (const link of Array.isArray(tagDetails) ? tagDetails : []) {
    if (link.provisional === true) continue
    const dimension = String(link.dimension ?? '').toLowerCase()
    if (!(dimension in tags) || typeof link.name !== 'string') continue
    if (!tags[dimension].includes(link.name)) tags[dimension].push(link.name)
  }
  for (const names of Object.values(tags)) names.sort()
  return tags
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
 * **The download link is a plain `<a download>` to the scoped download route**
 * (D-75), never to a `/media/` path, which nothing serves. It sends no request
 * through the API client: the browser follows it with the session cookie, as it
 * does any same-origin link (D-21). The `download` attribute, which browsers
 * honour only on a same-origin address, keeps a failure — an expired session's
 * 401, a document deleted or narrowed out of scope since this view loaded — in
 * the browser's downloads instead of navigating the tab to raw JSON. It is
 * offered on every document whatever its status and whatever `can_delete` says,
 * because the original is stored whether or not it was indexed, and reading it
 * needs nothing beyond scope.
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
  const { data: record, loading, error, reload, setData } = useApiResource(loader)
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

  /**
   * FR-10's section reports what one of its routes returned — the
   * classification, the tag links, the effective department — and the record
   * takes it. When the links changed, `tags` is rebuilt from them so the
   * metadata list above stays the same list the server would send.
   */
  function applyClassificationChange(patch) {
    setData((current) => {
      if (!current) return current
      const next = { ...current, ...patch }
      if (Array.isArray(patch.tag_details)) next.tags = tagsFrom(patch.tag_details)
      return next
    })
  }

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

      {/* The document's actions. FR-15's download link comes first and is always
          there: it points at the scoped download route and never at the stored
          file's path (D-75). It is a link, because following it is the browser's
          job, and it takes the secondary button's look so the row reads as one set
          of actions. The delete control follows it when the detail allows. */}
      <div className="repository-page__actions document-detail__actions">
        <a className="btn btn--secondary" href={documentDownloadUrl(record.doc_id)} download>
          {TEXT.documentDownload}
        </a>
        {canDelete ? (
          <Button variant="secondary" onClick={() => setConfirming(true)}>
            {TEXT.documentDelete}
          </Button>
        ) : null}
      </div>

      {/* FR-10: the AI-suggested type, department and tags, each marked as such
          and confirmable, editable or removable in one action (D-104, D-105). The
          department it shows is the record's own field, the effective one. */}
      <Classification
        docId={record.doc_id}
        classification={record.classification ?? null}
        tagDetails={record.tag_details ?? []}
        department={record.department ?? ''}
        onChange={applyClassificationChange}
      />

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
