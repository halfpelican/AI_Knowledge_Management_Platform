import { Link } from 'react-router-dom'
import { TEXT } from '../constants.js'
import { formatDate } from '../utils/dates.js'
import { sourceLinkFor, sourceTypeLabel } from '../utils/sources.js'
import AiMark from './AiMark.jsx'
import './SearchResults.css'

/**
 * One FR-12 search result: "its title, the matching passage as a snippet, its
 * department, and its date". Those four and nothing else, plus the link the type
 * and identifier make possible.
 *
 * No score, no rank number and no "relevance": this path does not compute one.
 * Results arrive ordered by recency and are rendered in the order they arrived,
 * because an order presented as relevance that was not computed from relevance is
 * what FR-12 rejects on its other path.
 *
 * **A snippet from a meeting's AI-generated summary is said to be one** (NFR-15;
 * D-125, choice 1). A meeting found through its summary alone shows the summary's
 * words as its snippet, and the result then arrives with `snippet_ai_generated:
 * true`. The snippet is bounded as AI content is everywhere and carries the mark,
 * "Suggested by AI", with a sentence saying it is not the transcript's own text.
 * **Only the flag decides**: nothing in the snippet says what it is, and nothing
 * here reads it to find out. A reply from before the field has no flag, which is
 * false, and such a result renders exactly as it always has.
 */
export function SearchResultItem({ result }) {
  const link = sourceLinkFor(result)
  const hasSnippet = Boolean(result.snippet)
  const aiSnippet = hasSnippet && result.snippet_ai_generated === true

  return (
    <article className="search-result">
      <h4 className="search-result__title">
        {link ? <Link to={link.to}>{result.title}</Link> : result.title}
      </h4>
      {aiSnippet ? (
        // The mark first, so it is read before the words it is about.
        <div className="search-result__ai ai-content">
          <p className="search-result__provenance">
            <AiMark /> {TEXT.aiSummarySnippet}
          </p>
          <p className="search-result__snippet">{result.snippet}</p>
        </div>
      ) : (
        // A source may match on its title alone and hold no indexed passage, in
        // which case the snippet is empty and the note says why. Nothing is
        // invented to fill the space.
        <p className={hasSnippet ? 'search-result__snippet' : 'search-result__snippet search-result__snippet--none'}>
          {hasSnippet ? result.snippet : TEXT.searchSnippetUnavailable}
        </p>
      )}
      <p className="search-result__meta">
        <span className="search-result__meta-item">
          <span className="visually-hidden">Type: </span>
          {sourceTypeLabel(result.source_type)}
        </span>
        {/* A meeting has no department and a document may have none. An em dash
            shows the column is blank rather than that the value is "Meeting". */}
        <span className="search-result__meta-item">
          <span className="visually-hidden">Department: </span>
          {result.department || '—'}
        </span>
        <span className="search-result__meta-item">
          <span className="visually-hidden">Date: </span>
          <time dateTime={result.date}>{formatDate(result.date)}</time>
        </span>
      </p>
    </article>
  )
}

/**
 * One of FR-12's two groups — "results grouped by type (Documents and Meetings)
 * with a count per group".
 *
 * A group with nothing in it still renders, with its count of zero and a line
 * saying so. A group that vanished would make the same screen look different for
 * reasons the reader cannot see, and the count is the server's own post-filter
 * number: it describes what this caller can see and no wider figure exists in the
 * reply (CLAUDE.md §6, invariant 1). There is no "showing n of m" anywhere here
 * because there is nothing to put in the m.
 *
 * @param {object} props
 * @param {string} props.heading
 * @param {string} props.headingId
 * @param {{count?: number, results?: object[]}} props.group
 * @param {string} props.emptyMessage
 */
export function SearchResultGroup({ heading, headingId, group, emptyMessage }) {
  const results = group?.results ?? []
  const count = group?.count ?? results.length

  return (
    <section className="search-group" aria-labelledby={headingId}>
      <h3 id={headingId} className="search-group__heading">
        {heading}{' '}
        <span className="search-group__count">{TEXT.searchGroupCount(count)}</span>
      </h3>
      {results.length === 0 ? (
        <p className="search-group__empty">{emptyMessage}</p>
      ) : (
        <ul className="search-group__list">
          {results.map((result) => (
            <li key={`${result.source_type}:${result.source_id}`}>
              <SearchResultItem result={result} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
