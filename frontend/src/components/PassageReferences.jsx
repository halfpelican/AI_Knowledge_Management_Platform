import { Fragment } from 'react'
import { TEXT } from '../constants.js'
import { passageText } from '../utils/passages.js'
// The marker and the panel it opens are FR-12's citation and its source passage:
// one pattern for a reference that expands to the text behind it (NFR-14).
import './Answer.css'

/** The id of the panel that shows passage `number` for the element `idPrefix` names. */
function panelIdFor(idPrefix, number) {
  return `${idPrefix}-passage-${number}`
}

/**
 * FR-16's passage references (UC-04: "Every element of the summary carries a
 * reference to the passage of the transcript it was drawn from"), in two parts
 * that the caller places: the markers go inline, after the element's text, and the
 * panels go after the block that holds it, because a passage is a block and a
 * paragraph cannot contain one.
 *
 * It works as the answer view's citation does (src/components/Answer.jsx). The
 * marker is a real button, so the keyboard reaches it and it announces its state
 * through `aria-expanded`; the panel it controls is always in the DOM and hidden,
 * so `aria-controls` always resolves. The visible `[2]` is `aria-hidden` and the
 * accessible name is "Transcript passage 2", the text equivalent for what would
 * otherwise be read as a bare bracket (WCAG 2.1 SC 1.1.1, SC 2.4.6).
 *
 * Where the summary does not carry a passage's text, which an action item kept
 * through a Regenerate can meet (docs/api-contract.md, the action item's
 * `passages`), the number is plain text and not a control that opens nothing.
 *
 * The passage is the transcript's own words, so it carries no AI mark (NFR-15):
 * what is marked is the sentence that cites it.
 *
 * @param {object} props
 * @param {string} props.idPrefix Unique per element: ids must not collide across a panel.
 * @param {number[]} props.numbers The element's passage numbers (src/utils/passages.js).
 * @param {Record<string, string>|null|undefined} props.passages The summary's `passages`.
 * @param {Set<string>} props.open The open panel ids (src/hooks/usePassagePanels.js).
 * @param {(panelId: string) => void} props.onToggle
 */
export function PassageMarkers({ idPrefix, numbers, passages, open, onToggle }) {
  return numbers.map((number) => {
    const panelId = panelIdFor(idPrefix, number)
    const label = TEXT.transcriptPassage(number)
    return (
      <Fragment key={number}>
        {' '}
        {passageText(passages, number) !== null ? (
          <button
            type="button"
            className="citation"
            aria-expanded={open.has(panelId)}
            aria-controls={panelId}
            onClick={() => onToggle(panelId)}
          >
            <span aria-hidden="true">[{number}]</span>
            <span className="visually-hidden">{label}</span>
          </button>
        ) : (
          <span className="citation citation--plain">
            <span aria-hidden="true">[{number}]</span>
            <span className="visually-hidden">{label}</span>
          </span>
        )}
      </Fragment>
    )
  })
}

/**
 * The panels the markers above open, one per passage whose text the summary
 * carries. A passage is a whole chunk of the transcript, so it scrolls rather than
 * pushing the page away, in a labelled region the keyboard can reach and scroll
 * (WCAG 2.1 SC 2.1.1), as the citation's passage does.
 *
 * The text is the transcript's: untrusted input, rendered as a text child and
 * never as HTML.
 *
 * @param {object} props As `PassageMarkers`, without `onToggle`.
 */
export function PassagePanels({ idPrefix, numbers, passages, open }) {
  return numbers.map((number) => {
    const text = passageText(passages, number)
    if (text === null) return null
    const panelId = panelIdFor(idPrefix, number)
    return (
      <div key={number} id={panelId} className="citation-panel" hidden={!open.has(panelId)}>
        <p className="citation-panel__label" id={`${panelId}-label`}>
          {TEXT.transcriptPassage(number)}
        </p>
        <blockquote
          className="citation-panel__passage"
          role="region"
          aria-labelledby={`${panelId}-label`}
          tabIndex={0}
        >
          {text}
        </blockquote>
      </div>
    )
  })
}
