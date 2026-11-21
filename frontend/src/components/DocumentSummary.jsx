import { useId } from 'react'
import { TEXT } from '../constants.js'
import AiMark from './AiMark.jsx'
import './DocumentSummary.css'

/**
 * The key points that say something, in the order they were sent. The server
 * caps how many there are (D-139); nothing here counts them or cuts them.
 */
function shownKeyPoints(keyPoints) {
  return Array.isArray(keyPoints)
    ? keyPoints.filter((point) => typeof point === 'string' && point.trim() !== '')
    : []
}

/**
 * FR-10's document summary and key points (D-139): "Each document displays a
 * short summary and a list of key points, shown beneath the title in search
 * results so users can judge relevance before opening the file."
 *
 * One component for both places a summary is shown, a search result
 * (src/components/SearchResults.jsx) and the document page
 * (src/pages/DocumentDetail.jsx), so the mark, the list and the sentence about a
 * summary cut short are the same on each.
 *
 * **It is AI content and says so first** (NFR-15): the mark, then a sentence
 * saying this is a summary and not the document's own text, inside the dashed
 * boundary the convention gives AI content (`ai-content`, AiMark.css). A summary
 * is AI content by what it is, so no flag is read to decide the mark.
 *
 * **A summary that covers only the first part of a long document says so**
 * (FR-10: never "summarised from a fragment without the user being told"), from
 * `summary_truncated` alone. A reply from before the field carries none, which
 * is false.
 *
 * **Only a summary is shown as one.** With no summary — `""`, absent, or not a
 * string, which is what a document never summarised, every meeting and a reply
 * from before the field all carry — nothing is rendered, or the one line
 * `emptyMessage` gives where the caller wants the absence said. Key points are
 * shown only under a summary, as a real list, and an empty list is not rendered.
 *
 * It holds no control and adds no tab stop. The text is the model's, written
 * from a file anyone may have uploaded: rendered as text children only, never as
 * HTML.
 *
 * @param {object} props
 * @param {string} [props.summary] `summary`, as the reply carries it.
 * @param {string[]} [props.keyPoints] `key_points`, as the reply carries them.
 * @param {boolean} [props.truncated] `summary_truncated`.
 * @param {string} [props.emptyMessage] Said in the summary's place when there is none.
 */
export default function DocumentSummary({ summary, keyPoints, truncated, emptyMessage }) {
  const labelId = useId()

  if (typeof summary !== 'string' || summary.trim() === '') {
    return emptyMessage ? <p className="document-summary__none">{emptyMessage}</p> : null
  }

  const points = shownKeyPoints(keyPoints)

  return (
    <div className="document-summary ai-content">
      {/* The mark first, so it is read before the words it is about. */}
      <p className="document-summary__provenance">
        <AiMark /> {TEXT.documentSummaryProvenance}
      </p>
      {truncated === true ? <p className="document-summary__note">{TEXT.documentSummaryTruncated}</p> : null}
      <p className="document-summary__text">{summary}</p>
      {points.length > 0 ? (
        <>
          <p id={labelId} className="document-summary__points-label">
            {TEXT.documentKeyPoints}
          </p>
          <ul className="document-summary__points" aria-labelledby={labelId}>
            {points.map((point, index) => (
              // The index is the key: the list is one summary's and never reorders.
              <li key={index}>{point}</li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  )
}
