import { Link } from 'react-router-dom'
import { listDocuments } from '../api/documents.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import { TEXT } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
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
 */
export function DocumentTable({ documents }) {
  if (documents.length === 0) {
    return <Notice variant="info">{TEXT.noDocuments}</Notice>
  }

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
          </tr>
        </thead>
        <tbody>
          {documents.map((record) => (
            <tr key={record.doc_id}>
              <th scope="row" className="data-table__title">
                {record.title}
              </th>
              <td className="data-table__type">{String(record.file_type ?? '').toUpperCase()}</td>
              <td>{record.status}</td>
              <td className="data-table__meta">
                <time dateTime={record.uploaded_at}>{formatDate(record.uploaded_at)}</time>
              </td>
              <td>{record.department || '—'}</td>
              <td className="data-table__meta">{formatVisibility(record.visible_to_roles)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * The document repository (FR-08's list; the foundation FR-15 builds filtered
 * browsing on in Stage 5).
 *
 * The list the API returns is already scoped to the caller's role, and the
 * screen shows exactly what it was sent: no count of what was filtered out, no
 * note that there is more, nothing that discloses the existence of material
 * outside the user's scope (CLAUDE.md §6, invariant 1). An empty list and a list
 * emptied by scoping look the same here because they are the same answer.
 */
export default function DocumentRepository() {
  useDocumentTitle('Documents')
  const { data, loading, error, reload } = useApiResource(listDocuments)
  const documents = data ?? []

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
            Try again
          </Button>
        </div>
      </>
    )
  } else {
    body = <DocumentTable documents={documents} />
  }

  return (
    <div className="repository-page">
      <h1 id="documents-heading">Documents</h1>
      <p>
        Everything you are permitted to see, newest first. <Link to="/upload">Upload a document</Link> to add
        to it.
      </p>
      {body}
    </div>
  )
}
