import { useCallback } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { searchKnowledge } from '../api/search.js'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import SearchField from '../components/SearchField.jsx'
import { SearchResultGroup } from '../components/SearchResults.jsx'
import { QUESTION_MAXIMUM_LENGTH, TEXT } from '../constants.js'
import useApiResource from '../hooks/useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { searchTermError } from '../utils/validation.js'
import './Repository.css'
import './Search.css'

/**
 * FR-12 keyword search: "results grouped by type (Documents and Meetings) with a
 * count per group. Each result shows its title, the matching passage as a
 * snippet, its department, and its date."
 *
 * The term lives in the URL, so a search is a place: it can be linked to, gone
 * back to, and reloaded, and the field at the top of the page always shows what
 * the results below are for. The same `SearchField` sits in the application
 * header on every page, which is where FR-12's "available from every page" is
 * met; this page's copy is for refining a term without going back to the header.
 *
 * Three things this screen does not do, all for the same reason (CLAUDE.md §6,
 * invariant 1): it shows no total other than the counts the server computed after
 * permission filtering, it never says or implies that anything was withheld, and
 * nothing matching looks different from nothing existing — because to this screen
 * they are the same answer.
 *
 * Nothing matched is an ordinary empty state. It is not an error, it is not
 * styled as one, and it offers the question path instead, which is the other half
 * of FR-12.
 */
export default function Search() {
  const [params] = useSearchParams()
  // Exactly what was in the URL, untrimmed: the server matches and logs the term
  // character for character, so the screen must not quietly search for something
  // else (src/api/search.js).
  const term = params.get('q') ?? ''
  const hasTerm = params.get('q') !== null
  const refusal = hasTerm ? searchTermError(term) : null
  const askable = refusal === null && hasTerm

  useDocumentTitle(askable ? `Search: ${term}` : 'Search')

  // A term too short is refused client-side (FR-12) and no request is made. The
  // loader still exists so the hook has one stable function; it resolves to null,
  // which is the same "nothing to show" the no-term case renders.
  const loader = useCallback(
    ({ signal }) => (searchTermError(term) === null ? searchKnowledge(term, { signal }) : Promise.resolve(null)),
    [term],
  )
  const { data, loading, error, reload } = useApiResource(loader)

  const total = data?.total_count ?? 0

  let body
  if (!hasTerm || term.length === 0) {
    body = <p className="search-page__prompt">{TEXT.searchPrompt}</p>
  } else if (refusal) {
    // Reachable by typing a URL; the header field refuses the same term before it
    // gets this far. The server refuses it too, with a 400.
    body = (
      <Notice variant="error" title={TEXT.searchFailed}>
        {refusal}
      </Notice>
    )
  } else if (loading) {
    body = <p role="status">{TEXT.searching}</p>
  } else if (error) {
    body = (
      <>
        <Notice variant="error" title={TEXT.searchFailed}>
          {error.message}
        </Notice>
        <div className="repository-page__actions">
          <Button variant="secondary" onClick={reload}>
            Try again
          </Button>
        </div>
      </>
    )
  } else if (data) {
    body = (
      <>
        <h2 className="search-page__results-heading">{TEXT.searchResultsFor(term)}</h2>
        {/* The visible acknowledgement, which is also the live region: the count
            lands where the reader is looking and is announced once, rather than
            being announced to assistive technology alone (usability finding 1). */}
        <p className="search-page__summary" role="status" aria-live="polite">
          {TEXT.searchTotalAnnouncement(term, total)}
        </p>
        {total === 0 ? (
          <Notice variant="info" title={TEXT.searchNothingMatched(term)}>
            {TEXT.searchNothingMatchedHint}
          </Notice>
        ) : null}
        {/* Both groups always render, each with its count, including a group with
            nothing in it: FR-12 asks for a count per group, and a group that
            disappeared would make one search look structurally unlike another. */}
        <SearchResultGroup
          heading={TEXT.searchDocumentsHeading}
          headingId="search-group-documents"
          group={data.documents}
          emptyMessage={TEXT.searchGroupEmptyDocuments}
        />
        <SearchResultGroup
          heading={TEXT.searchMeetingsHeading}
          headingId="search-group-meetings"
          group={data.meetings}
          emptyMessage={TEXT.searchGroupEmptyMeetings}
        />
      </>
    )
  } else {
    body = <p className="search-page__prompt">{TEXT.searchPrompt}</p>
  }

  return (
    <div className="repository-page search-page">
      <h1>{TEXT.searchHeading}</h1>
      <SearchField id="search-page-q" initialTerm={term} hint={TEXT.searchHint} className="search-page__field" />
      {/* FR-12's other path, offered rather than assumed. The question field has
          its own bounds, so a term too long to be a question is not sent as one. */}
      {askable && term.length <= QUESTION_MAXIMUM_LENGTH ? (
        <p className="search-page__ask">
          <Link to={`/ask?q=${encodeURIComponent(term)}`}>{TEXT.searchAskInstead}</Link>
        </p>
      ) : null}
      {body}
    </div>
  )
}
