import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchDocument } from '../api/documents.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import { TEXT } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
import './Repository.css'

/**
 * One document's record — where a document citation lands (D-46, Stage 4 item 10b).
 *
 * FR-12 requires that each citation "links to the source document or meeting".
 * A meeting citation has had `/meetings/{id}` since Stage 3; this is the document
 * half, and it is deliberately the minimum that makes the link true: the record
 * `GET /api/documents/{id}` returns, and nothing else.
 *
 * **It is not FR-15's document screen and does not pretend to be.** FR-15 (Stage
 * 5) owns document presentation — filtered browsing, the metadata panel,
 * permissioned deletion — and will build on this endpoint. Anticipating it here
 * with a control that does nothing would be a promise the screen does not keep,
 * which is the same reason the repository list carries no filters yet.
 *
 * There is no document text on this screen, because the API returns none: a
 * document's passages reach a reader through search and through the assistant's
 * Sources panel, each carrying the passage the answer was built from. `file_path`
 * is never sent to a client, so there is nothing here to download either.
 *
 * A document outside the caller's scope answers 404, exactly as an id that names
 * nothing does, and both render the same message. The screen never distinguishes
 * "no such document" from "not yours to read" (CLAUDE.md §6, invariant 1).
 */
export default function DocumentDetail() {
  const { docId } = useParams()
  // Stable per id: the hook's effect re-reads when the route parameter changes
  // and not on every render.
  const loader = useCallback(({ signal }) => fetchDocument(docId, { signal }), [docId])
  // Named `record`, not `document`: a local called `document` would shadow the
  // browser global inside every line of this component.
  const { data: record, loading, error, reload } = useApiResource(loader)
  useDocumentTitle(record?.title ?? 'Document')

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
        <Notice variant="error" title={notFound ? 'Not found' : TEXT.documentLoadFailed}>
          {notFound ? TEXT.documentRecordNotFound : error.message}
        </Notice>
        <div className="repository-page__actions">
          {notFound ? null : (
            <Button variant="secondary" onClick={reload}>
              Try again
            </Button>
          )}
          <Link to="/documents">Back to documents</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="repository-page">
      <h1>{record.title}</h1>
      <p>
        <Link to="/documents">Back to documents</Link>
      </p>
      <p className="data-table__meta">{TEXT.documentDetailScope}</p>

      <dl className="record-meta">
        <dt>Type</dt>
        <dd>{record.file_type}</dd>
        <dt>Status</dt>
        <dd>{record.status}</dd>
        <dt>Uploaded</dt>
        <dd>
          <time dateTime={record.uploaded_at}>{formatDate(record.uploaded_at)}</time>
        </dd>
        <dt>Department</dt>
        <dd>{record.department || 'Not recorded'}</dd>
        {/* The scope that decides who can read it, shown as the server recorded
            it: this screen is reachable only by a role in this list. */}
        <dt>Visible to</dt>
        <dd>{(record.visible_to_roles ?? []).join(', ')}</dd>
        <dt>Uploaded by</dt>
        <dd>{record.uploaded_by}</dd>
      </dl>
    </div>
  )
}
