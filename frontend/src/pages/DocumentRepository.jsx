import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import {
  BROWSE_DEFAULT_SORT,
  BROWSE_DIMENSIONS,
  BROWSE_FILTER_KEYS,
  BROWSE_PARAM_KEYS,
  BROWSE_SORT_FIELDS,
  browseDocuments,
  reprocessDocument,
} from '../api/documents.js'
import { ActiveFilterList, FacetGroup, SortHeader } from '../components/Browse.jsx'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import TextInput from '../components/TextInput.jsx'
import { TEXT } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
import { canReprocess, statusMessageFor } from '../utils/documentStatus.js'
import { extractFieldErrors } from '../utils/fieldErrors.js'
import './Repository.css'

/** What each parameter is called on screen, in the active filters and in a 400. */
const PARAM_NAMES = {
  q: TEXT.repositoryFilterNameQ,
  status: TEXT.repositoryFilterNameStatus,
  department: TEXT.repositoryFilterNameDepartment,
  project: TEXT.repositoryFilterNameProject,
  process: TEXT.repositoryFilterNameProcess,
  topic: TEXT.repositoryFilterNameTopic,
  sort: TEXT.repositoryFilterNameSort,
}

/** The heading of each column `sort` accepts, by its field in the contract. */
const SORT_LABELS = {
  title: TEXT.repositoryColumnTitle,
  file_type: TEXT.repositoryColumnType,
  uploaded_by: TEXT.repositoryColumnUploader,
  uploaded_at: TEXT.repositoryColumnUploaded,
  status: TEXT.repositoryColumnStatus,
}

/** Every filter emptied. `sort` is not a filter (D-72), so clearing keeps it. */
const NO_FILTERS = Object.fromEntries(BROWSE_FILTER_KEYS.map((key) => [key, '']))

/* ---- Filters and the URL ------------------------------------------------- */

/**
 * The browse state the address holds: every parameter the route reads, `''`
 * where the address holds none. Trimmed, because the server trims each value
 * and an all-space value is the same as none (docs/api-contract.md).
 */
function stateFromParams(params) {
  return Object.fromEntries(BROWSE_PARAM_KEYS.map((key) => [key, (params.get(key) ?? '').trim()]))
}

/**
 * The address for a browse state: only the parameters carrying a value, in the
 * contract's order, and no `sort` where it is the server's own default. An empty
 * value and an absent one are the same request (the contract), so they are made
 * the same address too, and the string doubles as the identity of the request
 * the screen is showing.
 */
function paramsFromState(state) {
  const params = new URLSearchParams()
  for (const key of BROWSE_PARAM_KEYS) {
    const value = (state[key] ?? '').trim()
    if (!value) continue
    if (key === 'sort' && value === BROWSE_DEFAULT_SORT) continue
    params.set(key, value)
  }
  return params
}

/* ---- The one request ---------------------------------------------------- */

/**
 * The repository's single request, re-sent whenever the address changes.
 *
 * Each reply is kept with the request it answers (`key`), and one that answers
 * an earlier request is never shown as the answer to the current one: after a
 * filter is chosen the list says it is loading rather than showing the previous
 * filter's documents under the new one. The dashboard reads its summary the same
 * way and for the same reason.
 *
 * **The 204.** `browseDocuments` resolves a 204 to `null`, so a settled reply
 * with no body and no error is "this filter combination matches nothing". It
 * carries no facets, and none are borrowed from an earlier reply (D-72): the
 * screen has to work when a filtered address is opened fresh — a bookmark, or
 * Back after a delete — and there is no earlier reply then.
 *
 * `facets` is the last settled reply's: a 200's, or null after a 204 or a
 * failure. While a request is in flight it is still the previous 200's, so the
 * control that was just pressed stays where it was and keeps the keyboard focus
 * instead of vanishing under it. It is replaced or removed the moment the reply
 * lands, so no count outlives the request it came with.
 */
function useBrowse(query) {
  const [attempt, setAttempt] = useState(0)
  const [settled, setSettled] = useState({ key: null, payload: null, error: null })
  const [facets, setFacets] = useState(null)
  const key = `${attempt}?${query}`

  useEffect(() => {
    const controller = new AbortController()
    browseDocuments(stateFromParams(new URLSearchParams(query)), { signal: controller.signal }).then(
      (payload) => {
        if (controller.signal.aborted) return
        setSettled({ key, payload, error: null })
        setFacets(payload ? (payload.facets ?? {}) : null)
      },
      (caught) => {
        // This screen cancelling its own request, because the address moved on.
        if (caught?.name === 'AbortError' || controller.signal.aborted) return
        const error =
          caught instanceof ApiError
            ? caught
            : new ApiError(NETWORK_ERROR_STATUS, messageForStatus(NETWORK_ERROR_STATUS))
        setSettled({ key, payload: null, error })
        setFacets(null)
      },
    )
    return () => controller.abort()
  }, [key, query])

  const retry = useCallback(() => setAttempt((current) => current + 1), [])

  /** Replaces one listed document with what the server just said about it. */
  const replaceDocument = useCallback((updated) => {
    if (!updated?.doc_id) return
    setSettled((current) => {
      if (!current.payload) return current
      const documents = (current.payload.documents ?? []).map((record) =>
        record.doc_id === updated.doc_id ? updated : record,
      )
      return { ...current, payload: { ...current.payload, documents } }
    })
  }, [])

  const current = settled.key === key
  return {
    payload: current ? settled.payload : null,
    error: current ? settled.error : null,
    noMatch: current && settled.error === null && settled.payload === null,
    loading: !current,
    facets,
    retry,
    replaceDocument,
  }
}

/* ---- Text filter --------------------------------------------------------- */

/**
 * FR-15's text filter on the title. A draft until submitted, then written to the
 * address — never filtered as typed, which would add a history entry per key.
 *
 * The draft follows the address: Back, a removed filter or "Clear filters"
 * changes the applied value and the field shows it. Adjusted during render, as
 * `SearchField` does, rather than by remounting on a `key`, because a remount on
 * every submit would throw the keyboard focus off the field just used.
 */
function TitleFilter({ applied, error, onApply }) {
  const [draft, setDraft] = useState(applied)
  const [seen, setSeen] = useState(applied)
  if (applied !== seen) {
    setSeen(applied)
    setDraft(applied)
  }

  function handleSubmit(event) {
    event.preventDefault()
    onApply(draft)
  }

  return (
    <form className="repository-filter" aria-label={TEXT.repositoryFilterFormLabel} noValidate onSubmit={handleSubmit}>
      <TextInput
        label={TEXT.repositoryFilterLabel}
        hint={TEXT.repositoryFilterHint}
        type="search"
        name="q"
        value={draft}
        error={error}
        autoComplete="off"
        onChange={(event) => setDraft(event.target.value)}
        action={
          <Button type="submit" variant="secondary">
            {TEXT.repositoryFilterSubmit}
          </Button>
        }
      />
    </form>
  )
}

/* ---- The table ----------------------------------------------------------- */

/**
 * The repository table as a pure view: FR-15's "title, type, uploader, upload
 * date, and status", with department beside them because it is a browse
 * dimension, and every column FR-15 names sortable from its heading.
 *
 * Each title links to the document's detail view, carrying the address the list
 * was reached by, so the detail view's "Back to documents" returns to these
 * filters as the browser's Back does.
 *
 * The one action a row carries is FR-08's retry, on a document `canReprocess`
 * admits — every status but "Indexed", which has nothing to redo, and "Too large
 * to index", which would stop at the same point on every press (D-51). It sits
 * under the status it acts on rather than in a column of its own at the far
 * right, which a narrow screen scrolls out of view (usability finding 6). Those
 * two rows still say where they stand; the sentence goes with the status and not
 * with the button. `retryingId` is the doc_id whose reprocess is in flight;
 * while one is running the rest are disabled.
 */
export function DocumentTable({ documents, sort, onSort, linkState, retryingId, onRetry, tableRef }) {
  const busy = retryingId !== null
  const sortProps = { sort, onSort }

  return (
    <div className="table-scroll" role="region" aria-labelledby="documents-results-heading" tabIndex={0}>
      <table className="data-table" ref={tableRef}>
        <caption className="visually-hidden">{TEXT.repositoryTableCaption}</caption>
        <thead>
          <tr>
            {/* The contract's sort fields, in its order, which is also the order
                FR-15 names the columns in: title, type, uploader, date, status. */}
            {BROWSE_SORT_FIELDS.map((field) => (
              <SortHeader key={field} label={SORT_LABELS[field]} field={field} {...sortProps} />
            ))}
            <th scope="col">{TEXT.repositoryColumnDepartment}</th>
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
                  {/* Text from the uploader, rendered as text. */}
                  <Link to={`/documents/${encodeURIComponent(record.doc_id)}`} state={linkState}>
                    {record.title}
                  </Link>
                </th>
                <td className="data-table__type">{String(record.file_type ?? '').toUpperCase()}</td>
                <td className="data-table__uploader">{record.uploaded_by}</td>
                <td className="data-table__meta">
                  <time dateTime={record.uploaded_at}>{formatDate(record.uploaded_at)}</time>
                </td>
                <td className="data-table__status">
                  {/* The status the server recorded, in its own words and never
                      in colour alone. A status that is not "Indexed" carries the
                      sentence for that status (D-32), so the difference between
                      a retry that can work, one that cannot, and one that is not
                      offered at all is on the screen rather than discovered by
                      pressing the button. */}
                  {record.status}
                  {message ? <span className="data-table__message">{message}</span> : null}
                  {retryable ? (
                    <span className="data-table__action">
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
                    </span>
                  ) : null}
                </td>
                <td>{record.department || '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ---- The page ------------------------------------------------------------ */

/**
 * FR-15 document repository and filtered browsing, with FR-08's retry on the
 * rows that can use it.
 *
 * **Every filter and the sort live in the address**: `?q=&status=&department=
 * &project=&process=&topic=&sort=`, the contract's own parameter names. A detail
 * view opened from a filtered list and left with Back lands on the same filters
 * and re-sends the same request (D-61's gap 3). Nothing about what is shown is
 * held only in this component.
 *
 * What the screen does not do is filter. The documents, the values offered and
 * every count arrive already scoped to the caller's role (FR-15: "counts are
 * computed after that filter, so a count never discloses inaccessible content";
 * CLAUDE.md §6, invariant 1), and nothing here hides, trims or recounts them. An
 * empty list and a list emptied by scoping look the same because they are the
 * same answer; a 204 says only that these filters match nothing.
 */
export default function DocumentRepository() {
  useDocumentTitle(TEXT.repositoryHeading)
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const applied = stateFromParams(params)
  const query = paramsFromState(applied).toString()
  const sort = applied.sort || BROWSE_DEFAULT_SORT
  const { payload, error, noMatch, loading, facets, retry, replaceDocument } = useBrowse(query)

  // A successful delete returns here with the title it removed (DocumentDetail).
  const deletedTitle = typeof location.state?.deleted === 'string' ? location.state.deleted : null

  // The doc_id whose reprocess is in flight, or null. One at a time.
  const [retryingId, setRetryingId] = useState(null)
  const [notice, setNotice] = useState(null)
  // One polite live region for the whole list, rather than one per row: the
  // outcome of a retry is announced once, in the same words the row shows.
  const [announcement, setAnnouncement] = useState('')
  const headingRef = useRef(null)
  const resultsHeadingRef = useRef(null)
  const tableRef = useRef(null)
  // Where focus goes once the reply to a change made on this screen lands: back
  // to the sort heading that was pressed, or to the results heading when the
  // control that had focus was removed with the old reply — a filter's Remove
  // button, "Clear filters", or a value the new reply no longer offers.
  const pendingFocus = useRef(null)

  const activeFilters = BROWSE_FILTER_KEYS.filter((key) => applied[key]).map((key) => ({
    key,
    name: PARAM_NAMES[key],
    value: applied[key],
  }))

  // Arriving from a delete: the dialogue and the button that opened it are gone,
  // so focus starts at the top of the list it returned to, with the notice under
  // the heading.
  useEffect(() => {
    if (deletedTitle) headingRef.current?.focus()
  }, [deletedTitle])

  useEffect(() => {
    if (loading || !pendingFocus.current) return
    const target = pendingFocus.current
    pendingFocus.current = null
    if (target === 'sort') {
      const button = tableRef.current?.querySelector('th[aria-sort] button')
      if (button) {
        button.focus()
        return
      }
    }
    const active = document.activeElement
    if (!active || active === document.body) resultsHeadingRef.current?.focus()
  }, [loading])

  /**
   * Writes a change to the address, which is what re-sends the request. A change
   * that leaves the request as it is — the same title submitted again — writes
   * nothing, so it adds no history entry for Back to step through.
   */
  function update(changes, focusTarget = 'results') {
    const next = paramsFromState({ ...applied, ...changes })
    if (next.toString() === query) return
    pendingFocus.current = focusTarget
    setNotice(null)
    setParams(next)
  }

  function announce(title, status) {
    // The same words the row shows, including the status that is explained
    // without being offered an action (D-51).
    const message = statusMessageFor(status)
    const detail = message ? `${status}. ${message}` : status
    setAnnouncement(TEXT.statusAnnouncement(title, detail))
  }

  /**
   * FR-08's "Processing failed. Please try again" action, from the list.
   *
   * The row is refreshed from what came back rather than from what was hoped
   * for: the 201 carries the document now "Indexed" or "Partially indexed", and
   * the 422 carries it still failed.
   */
  async function handleRetry(record) {
    setRetryingId(record.doc_id)
    setNotice(null)
    try {
      const updated = await reprocessDocument(record.doc_id)
      const status = updated?.status ?? record.status
      replaceDocument(updated)
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
        // the status the server has now recorded, and the action withdraws for
        // the one status a further press cannot change (D-51).
        const status = caught.details?.status ?? record.status
        replaceDocument(caught.details)
        announce(record.title, status)
        if (!canReprocess(status)) headingRef.current?.focus()
        return
      }
      case 409:
        // Already indexed, or a copy was indexed while this list sat open.
        setNotice({ title: TEXT.documentReprocessFailed, text: TEXT.documentAlreadyIndexed })
        retry()
        return
      case 404:
        // Also the answer for a document now outside the caller's scope; one
        // message covers both (invariant 1).
        setNotice({ title: TEXT.documentReprocessFailed, text: TEXT.documentNotFound })
        retry()
        return
      case 403:
        setNotice({ title: TEXT.documentReprocessFailed, text: TEXT.documentReprocessNotPermitted })
        return
      default:
        // Fixed, user-facing text from the API client. Never a backend string.
        setNotice({ title: TEXT.documentReprocessFailed, text: caught.message })
    }
  }

  // A 400 names the parameter it refused. Only DRF's validation message for that
  // parameter is shown (src/utils/fieldErrors.js); the text filter's goes under
  // its field and the rest, which only an edited address can produce, in the
  // notice.
  const refusal = error?.status === 400 ? extractFieldErrors(error, BROWSE_PARAM_KEYS) : null
  const refusedElsewhere = refusal
    ? BROWSE_PARAM_KEYS.filter((key) => key !== 'q' && refusal.fieldErrors[key])
    : []

  const documents = payload?.documents ?? []

  /* ---- Browse ----------------------------------------------------------- */
  let browseBody
  if (facets) {
    browseBody = (
      <div className="repository-browse__groups">
        {BROWSE_DIMENSIONS.map((dimension) => (
          <FacetGroup
            key={dimension}
            heading={PARAM_NAMES[dimension]}
            values={Array.isArray(facets[dimension]) ? facets[dimension] : []}
            selected={applied[dimension]}
            onChoose={(value) => update({ [dimension]: value })}
          />
        ))}
      </div>
    )
  } else if (loading) {
    browseBody = <p className="repository-browse__state">{TEXT.repositoryLoadingFacets}</p>
  } else if (error) {
    browseBody = <p className="repository-browse__state">{TEXT.repositoryBrowseUnavailable}</p>
  } else {
    browseBody = <p className="repository-browse__state">{TEXT.repositoryBrowseNoMatch}</p>
  }

  /* ---- Results ---------------------------------------------------------- */
  let results = null
  let statusLine = ''
  if (loading) {
    statusLine = TEXT.loadingDocuments
  } else if (error && error.status === 403) {
    results = <NotPermitted />
  } else if (refusal) {
    // Sending the same address again would be refused the same way, so there is
    // no retry: the filter is what has to change.
    results = (
      <Notice variant="error" title={TEXT.documentsLoadFailed}>
        <p>{TEXT.repositoryCheckFilters}</p>
        {refusedElsewhere.length > 0 ? (
          <ul>
            {refusedElsewhere.map((key) => (
              <li key={key}>
                {PARAM_NAMES[key]}: {refusal.fieldErrors[key]}
              </li>
            ))}
          </ul>
        ) : null}
        <p>
          <Link to="/documents">{TEXT.repositoryShowAll}</Link>
        </p>
      </Notice>
    )
  } else if (error) {
    results = (
      <>
        <Notice variant="error" title={TEXT.documentsLoadFailed}>
          {error.message}
        </Notice>
        <div className="repository-page__actions">
          <Button variant="secondary" onClick={retry}>
            {TEXT.uploadRetry}
          </Button>
        </div>
      </>
    )
  } else if (noMatch || (documents.length === 0 && activeFilters.length > 0)) {
    // FR-15's 204. The active filters and "Clear filters" are above, read from
    // the address; nothing here depends on a reply, because there is none.
    results = (
      <Notice variant="info" title={TEXT.repositoryNoMatchTitle}>
        {TEXT.repositoryNoMatch}
      </Notice>
    )
  } else if (documents.length === 0) {
    results = <Notice variant="info">{TEXT.noDocuments}</Notice>
  } else {
    statusLine = TEXT.repositoryResultCount(documents.length)
    results = (
      <>
        {notice ? (
          <Notice variant="error" title={notice.title}>
            {notice.text}
          </Notice>
        ) : null}
        <DocumentTable
          documents={documents}
          sort={sort}
          onSort={(next) => update({ sort: next }, 'sort')}
          linkState={{ from: location.search }}
          retryingId={retryingId}
          onRetry={handleRetry}
          tableRef={tableRef}
        />
      </>
    )
  }

  return (
    <div className="repository-page">
      <h1 id="documents-heading" ref={headingRef} tabIndex={-1}>
        {TEXT.repositoryHeading}
      </h1>
      <p className="repository-page__intro">{TEXT.repositoryIntro}</p>
      <p>
        <Link to="/upload">{TEXT.repositoryUploadLink}</Link>
      </p>
      {deletedTitle ? <Notice variant="info">{TEXT.repositoryDeleted(deletedTitle)}</Notice> : null}

      <TitleFilter applied={applied.q} error={refusal?.fieldErrors.q} onApply={(q) => update({ q })} />
      <ActiveFilterList
        filters={activeFilters}
        onRemove={(key) => update({ [key]: '' })}
        onClear={() => update(NO_FILTERS)}
      />

      <section className="repository-browse" aria-labelledby="browse-heading" aria-busy={loading || undefined}>
        <h2 id="browse-heading">{TEXT.repositoryBrowseHeading}</h2>
        <p className="repository-browse__hint">{TEXT.repositoryBrowseHint}</p>
        {browseBody}
      </section>

      <section
        className="repository-results"
        aria-labelledby="documents-results-heading"
        aria-busy={loading || undefined}
      >
        <h2 id="documents-results-heading" ref={resultsHeadingRef} tabIndex={-1}>
          {TEXT.repositoryResultsHeading}
        </h2>
        {/* Always mounted, so the change from "Loading" to the count is announced
            as well as shown (usability finding 1). */}
        <p className="repository-results__status" role="status">
          {statusLine}
        </p>
        {results}
      </section>

      {/* The same words the row shows, announced once. */}
      <p className="visually-hidden" role="status" aria-live="polite">
        {announcement}
      </p>
    </div>
  )
}
