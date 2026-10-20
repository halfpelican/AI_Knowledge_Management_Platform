import { useState } from 'react'
import { Link } from 'react-router-dom'
import { TEXT } from '../constants.js'
import { formatDate } from '../utils/dates.js'
import { sourceLinkFor, sourceTypeLabel } from '../utils/sources.js'
import { TURN_STATE, turnStateOf } from '../utils/turns.js'
import Notice from './Notice.jsx'
import './Answer.css'

/**
 * FR-12's answer presentation: numbered inline citations, each expanding to its
 * source passage, and the Sources panel beside them.
 *
 * Two rules govern this whole file.
 *
 * **Invariant 6 — there is no interface state that shows an uncited factual
 * statement.** Nothing here can create one: the only statements rendered are the
 * ones the reply carried, every one of which arrived with a `chunk_id` because the
 * API has no field for a statement without one. There is no greyed-out variant, no
 * disclosure holding withheld text, no count of what was removed, and no
 * "confidence" of any kind — `no_answer_reason` and `rejected_count` are
 * record-only and never reach the browser at all.
 *
 * **The number is the server's `position`, never the array index.** FR-12 asks for
 * numbered inline citations, and the number stored on the `AnswerCitation` row is
 * the number the reader saw. Rendering from the index would make the two agree
 * only by accident.
 */

/** The passage behind each cited chunk, and which source it came from. */
function passageIndex(sources) {
  const index = new Map()
  for (const source of sources ?? []) {
    for (const passage of source.passages ?? []) {
      if (passage?.chunk_id) index.set(passage.chunk_id, { source, passage })
    }
  }
  return index
}

/** The source line shared by an expanded citation and the Sources panel. */
function SourceLine({ source }) {
  const link = sourceLinkFor(source)
  return (
    <p className="answer-source__line">
      <span className="answer-source__title">{source.title}</span>{' '}
      <span className="answer-source__meta">
        <span className="visually-hidden">Type: </span>
        {sourceTypeLabel(source.source_type)}
        {' · '}
        <span className="visually-hidden">Date: </span>
        <time dateTime={source.date}>{formatDate(source.date)}</time>
      </span>
      {link ? (
        <>
          {' '}
          <Link to={link.to}>{link.label}</Link>
        </>
      ) : null}
    </p>
  )
}

/**
 * One verified statement and its citation.
 *
 * The marker is a real button, so it is reachable by keyboard and announces its
 * state through `aria-expanded`; the panel it controls is always in the DOM and
 * hidden, so `aria-controls` always resolves to something. The visible `[1]` is
 * `aria-hidden` and the accessible name is the sentence "Source for statement 1",
 * which is the text equivalent for a marker that would otherwise be read as a
 * bare bracket (WCAG 2.1 SC 1.1.1, SC 2.4.6).
 *
 * A live turn and a reopened one both carry their passages (D-78), so this
 * expands on either. Where a cited passage is nonetheless absent — D-53's
 * fail-closed read drops a source whose own row the reader may not read, on a
 * live reply and on a reopened turn alike — the number is plain text rather than a
 * control that expands nothing. The statement is still cited; what is missing is
 * the passage, and saying so is better than either inventing one or dropping the
 * citation number the reader was given.
 */
function CitedStatement({ idPrefix, statement, found }) {
  const [open, setOpen] = useState(false)
  const panelId = `${idPrefix}-citation-${statement.position}`

  return (
    <div className="answer__statement">
      <p className="answer__text">
        {statement.text}{' '}
        {found ? (
          <button
            type="button"
            className="citation"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((current) => !current)}
          >
            <span aria-hidden="true">[{statement.position}]</span>
            <span className="visually-hidden">{TEXT.citationToggleLabel(statement.position)}</span>
          </button>
        ) : (
          <span className="citation citation--plain">
            <span aria-hidden="true">[{statement.position}]</span>
            <span className="visually-hidden">{TEXT.citationToggleLabel(statement.position)}</span>
          </span>
        )}
      </p>
      <div id={panelId} className="citation-panel" hidden={!open || !found}>
        {found ? (
          <>
            <p className="citation-panel__label" id={`${panelId}-label`}>
              {TEXT.citationPassageHeading}
            </p>
            {/* A passage is a whole chunk and can run to thousands of characters, so
                it scrolls rather than pushing the rest of the thread off the screen.
                A scrollable box needs to be reachable by keyboard to be scrollable
                at all, which is what the labelled region and tabIndex are for — the
                same pattern the stored transcript uses (WCAG 2.1 SC 2.1.1). */}
            <blockquote
              className="citation-panel__passage"
              role="region"
              aria-labelledby={`${panelId}-label`}
              tabIndex={0}
            >
              {found.passage.text}
            </blockquote>
            <SourceLine source={found.source} />
          </>
        ) : null}
      </div>
    </div>
  )
}

/**
 * The answer itself: FR-12's "written answer with numbered inline citations".
 *
 * The statements arrive as a list and the interface places the markers — the
 * server composes no prose, because a single string with "[1]" spliced into it
 * cannot be re-checked against anything afterwards.
 *
 * @param {object} props
 * @param {string} props.idPrefix Unique per turn: ids must not collide across a thread.
 * @param {{position: number, text: string, chunk_id: string}[]} props.statements
 * @param {object[]} [props.sources] Consulted sources, whose nested passages are
 *   what a citation expands to. A live and a reopened turn both carry them (D-78).
 */
export function AnswerBody({ idPrefix, statements, sources }) {
  const index = passageIndex(sources)
  const headingId = `${idPrefix}-answer-heading`

  return (
    <section className="answer" aria-labelledby={headingId}>
      <h3 id={headingId}>{TEXT.answerHeading}</h3>
      {statements.map((statement) => (
        <CitedStatement
          key={statement.position}
          idPrefix={idPrefix}
          statement={statement}
          found={index.get(statement.chunk_id) ?? null}
        />
      ))}
    </section>
  )
}

/**
 * FR-12's Sources panel: "lists every item consulted with its date, allowing the
 * user to judge how current the underlying material is".
 *
 * Consulted, which is a wider set than cited — a panel listing only what a
 * surviving statement happened to cite would misdescribe what the answer was
 * drawn from. No similarity score is shown, because none is sent: a relevance
 * number is a tuning signal for the team, and displaying it would present
 * relevance as a fact about the answer.
 */
export function SourcesPanel({ idPrefix, sources }) {
  const headingId = `${idPrefix}-sources-heading`
  const items = sources ?? []
  if (items.length === 0) return null

  return (
    <section className="answer-sources" aria-labelledby={headingId}>
      <h3 id={headingId}>{TEXT.sourcesHeading}</h3>
      <p className="answer-sources__intro">{TEXT.sourcesIntro}</p>
      <ul className="answer-sources__list">
        {items.map((source) => (
          <li key={`${source.source_type}:${source.source_id}`} className="answer-source">
            <SourceLine source={source} />
            <p className="answer-source__passages">{TEXT.sourcePassageCount((source.passages ?? []).length)}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

/**
 * FR-12: "Any partially related items found are offered, clearly labelled as
 * partial matches."
 *
 * **These come off the reply.** `POST /api/ask` carries `partial_matches` on every
 * reply — the items its own ranked, permission-scoped candidates found, whatever
 * their similarity score — so this component renders a field rather than deriving
 * one. Until item 10a it was built in the browser from `GET /api/search` on one
 * word plucked out of the question; that heuristic is deleted, not left unused,
 * along with the extra request and the extra `SearchLog` row per no-answer.
 *
 * Everything offered is in the caller's scope by construction: the candidate set
 * was restricted in the query before it was ranked (CLAUDE.md §6, invariant 1).
 *
 * **No snippet, and that is the whole shape of the reply, not a choice made here.**
 * An entry carries `source_type`, `source_id`, `title` and `date` and there is no
 * field for passage text: under a heading that has just said the question cannot be
 * answered, a fragment of source text would read as a partial answer — invariant 6
 * by a side door — and the reader is meant to open the item and judge it rather
 * than take a line of it on trust. No score either, for the reason the Sources
 * panel gives.
 *
 * `department` is rendered where a caller supplies one, which the ask reply does
 * not: it carries source identity, title and date only. A search result does carry
 * one, and a blank department is already a case this line handles.
 */
export function PartialMatches({ idPrefix, results }) {
  const headingId = `${idPrefix}-partial-heading`
  if (!results || results.length === 0) return null

  return (
    <section className="partial-matches" aria-labelledby={headingId}>
      <h3 id={headingId}>{TEXT.partialMatchesHeading}</h3>
      <p className="partial-matches__intro">{TEXT.partialMatchesIntro}</p>
      <ul className="partial-matches__list">
        {results.map((result) => {
          const link = sourceLinkFor(result)
          return (
            <li key={`${result.source_type}:${result.source_id}`}>
              {link ? <Link to={link.to}>{result.title}</Link> : result.title}{' '}
              <span className="partial-matches__meta">
                <span className="visually-hidden">Type: </span>
                {sourceTypeLabel(result.source_type)}
                {result.department ? ` · ${result.department}` : ''}
                {' · '}
                <span className="visually-hidden">Date: </span>
                <time dateTime={result.date}>{formatDate(result.date)}</time>
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/**
 * What one turn of a thread shows below its question: the answer, or one of the two
 * states that are not an answer.
 *
 * **Three states, and the middle one is the security property** (Stage 4 item 1c).
 * `src/utils/turns.js` carries the argument in full; the short form is:
 *
 * - `answered` — the statements, each with its citation, and the Sources panel
 *   beside them. The same on a live turn and a reopened one, which carries the
 *   sources it consulted that the reader may still see (D-78).
 * - `noAnswer` — the corpus had nothing to answer from. **A turn re-scoped away
 *   from this reader arrives here too and is indistinguishable from it**, because a
 *   notice that something was removed is itself a disclosure that material exists
 *   which this role may not read (CLAUDE.md §6, invariant 1). Nothing in this
 *   branch may ever be made conditional on which of the two it is; the server does
 *   not send the difference.
 * - `provenanceRemoved` — the turn WAS answered and none of its citations still
 *   points at a chunk that exists, because a reprocess, a re-index or FR-15's
 *   deletion removed them (D-67). Its own title and message, and **no statements
 *   and no Sources panel**: a statement without its citation is what invariant 6
 *   forbids, and there is nothing here to grey out, hold behind a disclosure or
 *   count.
 *
 * The provenance state is NOT given the no-answer copy, which says the question
 * cannot be answered from the available knowledge base. That sentence is false of a
 * turn whose material is still indexed, and a reader who believes it stops asking a
 * question the system can answer.
 *
 * Rendered here rather than inline in the Ask screen so that the three states can
 * be exercised on their own. Before D-62 this layer had no test runner, and these
 * three were hand-verified by rendering this component from a script against
 * bodies captured from the API. Each is now rendered in frontend/tests/.
 *
 * @param {object} props
 * @param {object} props.turn one entry of the screen's `turns` list
 */
export function TurnBody({ turn }) {
  const state = turnStateOf(turn)

  if (state === TURN_STATE.answered) {
    return (
      <>
        <AnswerBody idPrefix={turn.key} statements={turn.statements} sources={turn.sources} />
        <SourcesPanel idPrefix={turn.key} sources={turn.sources} />
      </>
    )
  }

  if (state === TURN_STATE.provenanceRemoved) {
    return (
      <Notice variant="info" title={TEXT.provenanceRemovedTitle}>
        {turn.message}
      </Notice>
    )
  }

  return (
    <>
      {/* No answer. Stated plainly, as an outcome and not an error, with no answer
          frame around it and no fragment in it. The two no-answer paths are
          byte-identical in the reply and nothing here tries to tell them apart
          (invariant 7), as nothing here can tell a re-scoped turn from either. */}
      <Notice variant="info" title={TEXT.noAnswerTitle}>
        {turn.message}
      </Notice>
      <PartialMatches idPrefix={turn.key} results={turn.partialMatches} />
    </>
  )
}
