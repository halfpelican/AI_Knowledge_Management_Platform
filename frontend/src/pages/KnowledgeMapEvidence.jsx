import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { fetchEvidenceMap } from '../api/knowledgeMap.js'
import AiMark from '../components/AiMark.jsx'
import { SortHeader } from '../components/Browse.jsx'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import { EVIDENCE_MAP_NODE_TYPE, SOURCE_TYPE, TEXT } from '../constants.js'
import useArrivalFocus from '../hooks/useArrivalFocus.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { formatDate } from '../utils/dates.js'
import {
  CITATION_SORT_FIELDS,
  EVIDENCE_COLUMNS,
  EVIDENCE_GRID_TEMPLATE,
  EVIDENCE_ITEM_SORT_FIELDS,
  MAP_VIEW,
  citationLine,
  citationsOf,
  citedWith,
  claimReview,
  countEvidence,
  evidenceAddress,
  evidenceItemAddress,
  evidenceLabel,
  evidenceRelationshipWords,
  evidenceSelectionFromParams,
  evidenceTypeWord,
  evidenceTypedLabel,
  isAiPassage,
  layoutEvidence,
  lineWeight,
  sortCitations,
  sortEvidenceItems,
  sourceLabel,
  viewAddress,
} from '../utils/evidenceMap.js'
import {
  SELECTION_KIND,
  focusOf,
  gridPlace,
  isPlainClick,
  knowledgeMapQuery,
  nodesOf,
  selectedNodeOf,
  truncationSentence,
} from '../utils/knowledgeMap.js'
// The table style the repository and the meetings list share, and the map's own.
import './Repository.css'
import './KnowledgeMap.css'

/* ---- The switch between the two views ------------------------------------ */

/** What the switch to each view says: the view it leads to. */
const SWITCH_LABELS = {
  [MAP_VIEW.evidence]: TEXT.evidenceSwitchToClaims,
  [MAP_VIEW.relationships]: TEXT.evidenceSwitchToMap,
}

/**
 * The link from one view of the knowledge map to the other (D-138). A real link
 * with the button's look, to the other view's address with nothing selected: a
 * selection is a node of one view and names nothing in the other, so switching
 * drops it. Each view renders it straight after "Skip to the table view".
 *
 * A plain click also tells the page which view it leads to (`onSwitch`), so that
 * view can put focus on its heading once it has settled
 * (src/hooks/useArrivalFocus.js). The link itself is removed with the view it was
 * followed from.
 *
 * @param {object} props
 * @param {string} props.to The view the link leads to, one of `MAP_VIEW`.
 * @param {(view: string) => void} [props.onSwitch] Called with `to` when the link is followed here.
 */
export function KnowledgeMapSwitch({ to, onSwitch }) {
  return (
    <Link
      className="btn btn--secondary"
      to={viewAddress(to)}
      onClick={(event) => {
        if (isPlainClick(event)) onSwitch?.(to)
      }}
    >
      {SWITCH_LABELS[to]}
    </Link>
  )
}

/* ---- Shapes -------------------------------------------------------------- */

/**
 * One shape per type, each a different element, so the type survives without
 * colour (SC 1.4.1): a claim is a square and a passage is a circle, as in the
 * proposal's Figure 8.7. The colour is not here: each shape carries a class, and
 * KnowledgeMap.css gives that class its fill from a token, as the first view's do.
 */
const GLYPHS = {
  [EVIDENCE_MAP_NODE_TYPE.claim]: (className) => <rect className={className} x="2" y="2" width="16" height="16" />,
  [EVIDENCE_MAP_NODE_TYPE.passage]: (className) => <circle className={className} cx="10" cy="10" r="9" />,
}

/** A node type's shape. Decoration: `aria-hidden`, because the type is always also a word. */
function EvidenceShape({ type }) {
  const glyph = GLYPHS[type]
  if (!glyph) return null
  return (
    <svg className="knowledge-map__shape" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      {glyph(`knowledge-map__glyph knowledge-map__glyph--${type}`)}
    </svg>
  )
}

/* ---- Legend -------------------------------------------------------------- */

/**
 * The legend: the two node types, each its shape in its colour beside its word,
 * and what a line and its weight mean. It lists the vocabulary itself
 * (`EVIDENCE_MAP_NODE_TYPE`) through the shape the diagram draws, and its sample
 * lines carry the three classes the diagram's lines do.
 */
function EvidenceLegend() {
  return (
    <section className="knowledge-map__legend" aria-labelledby="knowledge-map-legend-heading">
      <h2 id="knowledge-map-legend-heading">{TEXT.mapLegendHeading}</h2>
      <p className="knowledge-map__legend-note">{TEXT.mapLegendTypes}</p>
      <ul className="knowledge-map__legend-list">
        {Object.values(EVIDENCE_MAP_NODE_TYPE).map((type) => (
          <li key={type} className="knowledge-map__legend-item">
            <EvidenceShape type={type} />
            <span>{evidenceTypeWord(type)}</span>
          </li>
        ))}
      </ul>
      <p className="knowledge-map__legend-item">
        {/* Three sample lines, lightest first, in the classes the diagram draws with. */}
        <svg className="knowledge-map__legend-line" viewBox="0 0 40 24" aria-hidden="true" focusable="false">
          <line className="knowledge-map__line knowledge-map__line--light" x1="0" y1="4" x2="40" y2="4" />
          <line className="knowledge-map__line knowledge-map__line--medium" x1="0" y1="12" x2="40" y2="12" />
          <line className="knowledge-map__line knowledge-map__line--heavy" x1="0" y1="20" x2="40" y2="20" />
        </svg>
        <span>{TEXT.evidenceLegendLine}</span>
      </p>
      <p className="knowledge-map__legend-note">{TEXT.evidenceLegendSelected}</p>
    </section>
  )
}

/* ---- A node, wherever it is shown ---------------------------------------- */

/** What a second selection of a passage opens, in the selected node's own name, by its source's type. */
const SELECT_AGAIN = {
  [SOURCE_TYPE.document]: TEXT.mapSelectAgainDocument,
  [SOURCE_TYPE.meeting]: TEXT.mapSelectAgainMeeting,
}

/** The open action's words for a selected passage, by its source's type. */
const OPEN_SOURCE = {
  [SOURCE_TYPE.document]: TEXT.mapOpenDocument,
  [SOURCE_TYPE.meeting]: TEXT.mapOpenMeeting,
}

/** The count as the server sent it in words, or null for one that did not arrive. */
function connectionsShown(node) {
  return Number.isFinite(node.connection_count) ? TEXT.mapConnectionsShown(node.connection_count) : null
}

/**
 * One node, as the control that selects it: on the diagram, in the pane, in an
 * Items row and at both ends of a Relationships row, as the first view's `MapNode`
 * is. One place decides where a node leads:
 *
 * - **not selected**: a link to this view's own address with the node as the focus;
 * - **selected, a passage**: a link to the page of the document or the meeting the
 *   passage is from, marked `aria-current`, with the word "Selected" and what a
 *   second selection does in its name;
 * - **selected, a claim**: not a link, because a claim has no page of its own
 *   (D-138). It carries the same mark.
 *
 * Always a native link, or plain text. `variant` is what the control says, as in
 * the first view: `node` on the diagram, `typed` where nothing beside it says the
 * type, `name` in the Items table.
 *
 * **A passage that is AI-generated content says so in every variant** (NFR-15):
 * the one mark, "Suggested by AI" (src/components/AiMark.jsx), after its label and
 * inside the control, so it is part of the control's name too.
 *
 * A claim's label is a statement from an answer and a passage's holds a document's
 * or a meeting's title: untrusted, and rendered as text.
 *
 * @param {object} props
 * @param {object} props.node
 * @param {object|null} props.selected The selected node, or null.
 * @param {'node'|'typed'|'name'} props.variant
 * @param {(focus: {type: string, id: string}) => void} [props.onSelect]
 */
function EvidenceNode({ node, selected, variant, onSelect }) {
  const isSelected = selected?.id === node.id
  const opens = isSelected ? evidenceItemAddress(node) : null
  const again = opens ? SELECT_AGAIN[node.detail?.source_type] : null
  const count = connectionsShown(node)
  const ai = isAiPassage(node)

  // The punctuation between the parts is for a screen reader, which reads the
  // control as one name. Each space is a text node of its own between two
  // elements, as in the first view's node.
  const aiMark = ai ? (
    <>
      <span className="visually-hidden">,</span>{' '}
      <AiMark />
    </>
  ) : null
  const mark = isSelected ? (
    <>
      <span className="visually-hidden">,</span>{' '}
      <span className="knowledge-map__selected-mark">{TEXT.mapSelectedMark}</span>
      {again ? (
        <>
          <span className="visually-hidden">.</span>{' '}
          <span className="visually-hidden">{again}</span>
        </>
      ) : null}
    </>
  ) : null

  let content
  if (variant === 'node') {
    content = (
      <>
        <EvidenceShape type={node.type} />
        <span className="knowledge-map__node-text">
          {/* The type, for a screen reader: "Claim:". */}
          <span className="visually-hidden">{TEXT.mapTypedLabel(evidenceTypeWord(node.type), '').trim()}</span>{' '}
          <span className="knowledge-map__node-label">{evidenceLabel(node)}</span>
          {aiMark}
          {count ? (
            <>
              <span className="visually-hidden">,</span>{' '}
              <span className="knowledge-map__node-count">{count}</span>
            </>
          ) : null}
          {mark}
        </span>
      </>
    )
  } else {
    content = (
      <>
        <span className="knowledge-map__ref-label">
          {variant === 'typed' ? evidenceTypedLabel(node) : evidenceLabel(node)}
        </span>
        {aiMark}
        {mark}
      </>
    )
  }

  const base = variant === 'node' ? 'knowledge-map__node' : 'knowledge-map__ref'
  const className = [
    base,
    isSelected ? `${base}--selected` : '',
    // The dashed boundary AI content has everywhere, as a second cue beside the words.
    ai && variant === 'node' ? 'knowledge-map__node--ai' : '',
  ]
    .filter(Boolean)
    .join(' ')

  if (!isSelected) {
    const focus = focusOf(node)
    return (
      <Link
        className={className}
        to={evidenceAddress(focus)}
        onClick={(event) => {
          if (isPlainClick(event)) onSelect?.(focus)
        }}
      >
        {content}
      </Link>
    )
  }
  if (opens) {
    return (
      <Link className={className} to={opens} aria-current="true">
        {content}
      </Link>
    )
  }
  return (
    <span className={className} aria-current="true">
      {content}
    </span>
  )
}

/* ---- Diagram ------------------------------------------------------------- */

/**
 * The node-link diagram, as a pure view of the nodes and citations it is given:
 * two columns from `layoutEvidence`, claims then passages, one row per node. Its
 * structure and its classes are the first view's diagram's: the lines in an
 * `aria-hidden` SVG under the nodes, with nothing focusable in it, and the nodes as
 * a list of real links over it, in the layout's order, inside a labelled, focusable
 * scroll region. Inline style is position only.
 *
 * **A line's weight is how often its pairing was admitted** (`weight`), in one of
 * three classes (`lineWeight`). The number itself is the Relationships table's
 * "Times admitted", so the weight is never the only place it is said (SC 1.1.1).
 * The selected node's lines keep the first view's mark, the `--selected` class,
 * and are drawn last.
 *
 * @param {object} props
 * @param {object[]} props.nodes
 * @param {{key: string, source: object, target: object, weight: number}[]} props.citations
 * @param {object|null} props.selected
 * @param {string} props.labelledBy The id of the heading that names the region.
 * @param {(focus: object) => void} [props.onSelect]
 */
function EvidenceDiagram({ nodes, citations, selected, labelledBy, onSelect }) {
  const layout = layoutEvidence(nodes)
  const placeOf = new Map(layout.placed.map((place) => [place.node.id, place]))
  const lines = citations
    .map((row) => ({
      key: row.key,
      weight: lineWeight(row.weight),
      selected: Boolean(selected) && (row.source.id === selected.id || row.target.id === selected.id),
      ...citationLine(placeOf.get(row.source.id), placeOf.get(row.target.id), layout.rows),
    }))
    // The selected node's lines are drawn last, so no other line is painted over them.
    .sort((first, second) => Number(first.selected) - Number(second.selected))

  return (
    <div className="knowledge-map__scroll" role="region" aria-labelledby={labelledBy} tabIndex={0}>
      <div className="knowledge-map__columns" style={{ gridTemplateColumns: EVIDENCE_GRID_TEMPLATE }}>
        {EVIDENCE_COLUMNS.map((column, index) => (
          <p key={column.key} className="knowledge-map__column-heading" style={{ gridColumn: index * 2 + 1 }}>
            {column.heading}
          </p>
        ))}
      </div>
      <div className="knowledge-map__canvas">
        <svg className="knowledge-map__lines" aria-hidden="true" focusable="false">
          {lines.map((line) => (
            <line
              key={line.key}
              className={[
                'knowledge-map__line',
                `knowledge-map__line--${line.weight}`,
                line.selected ? 'knowledge-map__line--selected' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              x1={line.x1}
              y1={line.y1}
              x2={line.x2}
              y2={line.y2}
            />
          ))}
        </svg>
        <ul className="knowledge-map__nodes" style={{ gridTemplateColumns: EVIDENCE_GRID_TEMPLATE }}>
          {layout.placed.map((place) => (
            <li key={place.node.id} className="knowledge-map__cell" style={gridPlace(place)}>
              <EvidenceNode node={place.node} selected={selected} variant="node" onSelect={onSelect} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/* ---- The pane: Claim review ---------------------------------------------- */

/** A group of the pane: a heading, then the nodes under it, each the control that selects it. */
function PaneGroup({ heading, nodes, selected, onSelect }) {
  if (nodes.length === 0) return null
  return (
    <div className="knowledge-map__group">
      <h3>{heading}</h3>
      <ul className="knowledge-map__group-list">
        {nodes.map((node) => (
          <li key={node.id}>
            <EvidenceNode node={node} selected={selected} variant="typed" onSelect={onSelect} />
          </li>
        ))}
      </ul>
    </div>
  )
}

/** What is selected: its shape, its type in a word and its label, as text. */
function PaneItem({ node }) {
  return (
    <p className="knowledge-map__panel-item">
      <EvidenceShape type={node.type} />
      <span>
        <span className="knowledge-map__panel-type">{evidenceTypeWord(node.type)}</span>{' '}
        {/* Untrusted text, rendered as text. */}
        <strong className="knowledge-map__panel-name">{evidenceLabel(node)}</strong>
      </span>
    </p>
  )
}

/**
 * The Claim review (D-138, the user's third decision): a summary of the selected
 * claim, from the claim's own `detail` and the reply's edges, with nothing counted
 * here.
 *
 * - the claim's text;
 * - "Single source" where `passage_count` is 1;
 * - "Admitted in N answers", from `answer_count`, and for a single-source claim
 *   admitted more than once, that every one of them rests on the same passage;
 * - "Supported by": the claim's passages in this view, each the control that
 *   selects it;
 * - when it was first and last admitted;
 * - that a claim has no page of its own, where the first view offers its open action.
 */
function ClaimReview({ claim, passages, onSelect }) {
  const review = claimReview(claim)
  // Each date as the app writes dates elsewhere, and left out where it is not a date.
  const dates = [
    [TEXT.evidenceFirstAdmitted, review.firstAdmittedAt],
    [TEXT.evidenceLastAdmitted, review.lastAdmittedAt],
  ].filter(([, iso]) => formatDate(iso))
  return (
    <>
      <PaneItem node={claim} />
      {review.singleSource ? (
        <p>
          <span className="knowledge-map__flag">{TEXT.evidenceSingleSource}</span>
        </p>
      ) : null}
      {review.answerCount !== null ? (
        <p className="knowledge-map__review">
          {TEXT.evidenceAdmittedIn(review.answerCount)}
          {review.sameSource ? ` ${TEXT.evidenceSameSource}` : ''}
        </p>
      ) : null}
      <PaneGroup heading={TEXT.evidenceSupportedBy} nodes={passages} selected={claim} onSelect={onSelect} />
      {dates.length > 0 ? (
        <dl className="knowledge-map__facts">
          {dates.map(([term, iso]) => (
            <div key={term} className="knowledge-map__fact">
              <dt>{term}</dt>
              <dd>
                <time dateTime={iso}>{formatDate(iso)}</time>
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      <p>{TEXT.evidenceClaimNoPage}</p>
    </>
  )
}

/**
 * The pane for a selected passage: its label, its source's type and title, the AI
 * mark and what it means where the passage is AI-generated content (NFR-15), the
 * claims in this view that cite it, and the action that opens its source.
 */
function PassageDetail({ passage, claims, onSelect }) {
  const opens = evidenceItemAddress(passage)
  const source = sourceLabel(passage)
  const sourceType = passage.detail?.source_type
  return (
    <>
      <PaneItem node={passage} />
      {source ? (
        <dl className="knowledge-map__facts">
          <div className="knowledge-map__fact">
            <dt>{TEXT.evidenceSource}</dt>
            {/* A title is untrusted text, rendered as text. */}
            <dd>{source}</dd>
          </div>
        </dl>
      ) : null}
      {isAiPassage(passage) ? (
        <p className="knowledge-map__panel-ai">
          {/* The mark alone where the passage's source is not a meeting: the sentence is about a meeting's summary. */}
          <AiMark />
          {sourceType === SOURCE_TYPE.meeting ? ` ${TEXT.aiSummaryPassage}` : ''}
        </p>
      ) : null}
      <PaneGroup heading={TEXT.evidenceCitedBy} nodes={claims} selected={passage} onSelect={onSelect} />
      {opens && OPEN_SOURCE[sourceType] ? (
        <p>
          <Link to={opens}>{OPEN_SOURCE[sourceType]}</Link>
        </p>
      ) : null}
    </>
  )
}

/**
 * The right-hand pane. Headed "Claim review" for a selected claim, and "Selected"
 * for a selected passage or for nothing, when it says how to select. Its heading
 * takes focus when a selection made on this page has loaded, as the first view's
 * Selected panel's does.
 */
function EvidencePane({ selected, connected, headingRef, onSelect }) {
  const isClaim = selected?.type === EVIDENCE_MAP_NODE_TYPE.claim
  let body
  if (!selected) {
    body = <p>{TEXT.evidenceSelectedNone}</p>
  } else {
    body = (
      <>
        {isClaim ? (
          <ClaimReview claim={selected} passages={connected} onSelect={onSelect} />
        ) : (
          <PassageDetail passage={selected} claims={connected} onSelect={onSelect} />
        )}
        <p>
          <Link
            to={evidenceAddress()}
            onClick={(event) => {
              if (isPlainClick(event)) onSelect?.(null)
            }}
          >
            {TEXT.mapShowWhole}
          </Link>
        </p>
      </>
    )
  }

  return (
    <section className="knowledge-map__panel" aria-labelledby="knowledge-map-selected-heading">
      <h2 id="knowledge-map-selected-heading" ref={headingRef} tabIndex={-1}>
        {isClaim ? TEXT.evidenceClaimReviewHeading : TEXT.mapSelectedHeading}
      </h2>
      {body}
    </section>
  )
}

/* ---- Table view (NFR-17) ------------------------------------------------- */

/**
 * The table of nodes: one row per claim and passage the reply holds. Name is the
 * same control the node is, with the AI mark where the node carries it; Type is a
 * word; Connections shown is the server's count, as sent. Every column sorts from
 * its heading, a native button in a `th` that carries `aria-sort` (`SortHeader`).
 * When the view is partial the table's description is the sentence that says so.
 */
function EvidenceItemsTable({ nodes, selected, sort, onSort, describedBy, onSelect }) {
  const sortProps = { sort, onSort }
  return (
    <div className="table-scroll" role="region" aria-labelledby="knowledge-map-items-heading" tabIndex={0}>
      <table className="data-table" aria-describedby={describedBy}>
        <caption className="visually-hidden">{TEXT.evidenceItemsCaption}</caption>
        <thead>
          <tr>
            <SortHeader label={TEXT.mapItemsColumnName} field={EVIDENCE_ITEM_SORT_FIELDS.name} {...sortProps} />
            <SortHeader label={TEXT.mapItemsColumnType} field={EVIDENCE_ITEM_SORT_FIELDS.type} {...sortProps} />
            <SortHeader
              label={TEXT.mapItemsColumnConnections}
              field={EVIDENCE_ITEM_SORT_FIELDS.connections}
              {...sortProps}
            />
          </tr>
        </thead>
        <tbody>
          {sortEvidenceItems(nodes, sort).map((node) => (
            <tr key={node.id}>
              <th scope="row" className="data-table__title">
                <EvidenceNode node={node} selected={selected} variant="name" onSelect={onSelect} />
              </th>
              <td>{evidenceTypeWord(node.type)}</td>
              <td className="knowledge-map__figure">
                {Number.isFinite(node.connection_count) ? node.connection_count : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * The table of relationships: one row per edge the reply holds, which is one row
 * per line the diagram draws. It reads "from, relationship, to", in words, and
 * then "Times admitted": the edge's `weight` as a number, which the diagram shows
 * only as the line's weight. From and To are the same controls the nodes are.
 */
function CitationsTable({ citations, selected, sort, onSort, describedBy, onSelect }) {
  const sortProps = { sort, onSort }
  return (
    <div className="table-scroll" role="region" aria-labelledby="knowledge-map-relationships-heading" tabIndex={0}>
      <table className="data-table" aria-describedby={describedBy}>
        <caption className="visually-hidden">{TEXT.evidenceRelationshipsCaption}</caption>
        <thead>
          <tr>
            <SortHeader label={TEXT.mapRelationshipsColumnFrom} field={CITATION_SORT_FIELDS.from} {...sortProps} />
            <SortHeader
              label={TEXT.mapRelationshipsColumnRelationship}
              field={CITATION_SORT_FIELDS.relationship}
              {...sortProps}
            />
            <SortHeader label={TEXT.mapRelationshipsColumnTo} field={CITATION_SORT_FIELDS.to} {...sortProps} />
            <SortHeader label={TEXT.evidenceColumnTimesAdmitted} field={CITATION_SORT_FIELDS.weight} {...sortProps} />
          </tr>
        </thead>
        <tbody>
          {sortCitations(citations, sort).map((row) => (
            <tr key={row.key}>
              <th scope="row" className="data-table__title">
                <EvidenceNode node={row.source} selected={selected} variant="typed" onSelect={onSelect} />
              </th>
              <td>{evidenceRelationshipWords(row.relationship)}</td>
              <td className="data-table__title">
                <EvidenceNode node={row.target} selected={selected} variant="typed" onSelect={onSelect} />
              </td>
              <td className="knowledge-map__figure">{Number.isFinite(row.weight) ? row.weight : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ---- The one request ----------------------------------------------------- */

/**
 * The view's single request, re-sent whenever the selection in the address changes.
 * The rule is the first view's (`useKnowledgeMap` in src/pages/KnowledgeMap.jsx),
 * for the second view's route: each reply is kept with the request it answers, and
 * one that answers an earlier request is never shown as the answer to the current
 * one, so a failed selection leaves no earlier map on screen. Nothing is cached.
 *
 * With `query` null there is no request at all: the address holds a selection that
 * is not a well-formed pair.
 *
 * @param {string|null} query The focus as a query string, `''` for the overview, or null.
 */
function useEvidenceMap(query) {
  const [attempt, setAttempt] = useState(0)
  const [settled, setSettled] = useState({ key: null, map: null, error: null })
  const key = query === null ? null : `${attempt}?${query}`

  useEffect(() => {
    if (key === null) return undefined
    const controller = new AbortController()
    const { focus } = evidenceSelectionFromParams(new URLSearchParams(query))
    fetchEvidenceMap(focus, { signal: controller.signal }).then(
      (map) => {
        if (controller.signal.aborted) return
        setSettled({ key, map, error: null })
      },
      (caught) => {
        // This view cancelling its own request, because the address moved on.
        if (caught?.name === 'AbortError' || controller.signal.aborted) return
        const error =
          caught instanceof ApiError
            ? caught
            : new ApiError(NETWORK_ERROR_STATUS, messageForStatus(NETWORK_ERROR_STATUS))
        setSettled({ key, map: null, error })
      },
    )
    return () => controller.abort()
  }, [key, query])

  const retry = useCallback(() => setAttempt((current) => current + 1), [])

  const current = key !== null && settled.key === key
  return {
    map: current ? settled.map : null,
    error: current ? settled.error : null,
    loading: key !== null && !current,
    retry,
  }
}

/* ---- The view ------------------------------------------------------------ */

/**
 * The knowledge map's second view (D-138): claims joined to the passages they cite,
 * after the proposal's Figure 8.7. At `/knowledge-map?view=evidence`, reached by
 * the switch beside "Skip to the table view" and by nothing in the navigation.
 *
 * **The view renders what the server sent**, as the first view does. The claims,
 * the passages, every count, every weight and date and the truncation fields
 * arrive already scoped to the caller's role, then capped, then counted
 * (CLAUDE.md §6, invariant 1). Nothing here filters, trims or recounts them. The
 * view derives the count line, the order of the two tables' rows and where each
 * node is drawn, and nothing else.
 *
 * **The selection lives in the address**, beside `view`:
 * `?view=evidence&focus_type=<claim|passage>&focus_id=<id>`. Selecting a node is a
 * link to that address, which is a second request for the walk from that node. The
 * node marked selected is the one the reply's `focus` names. A selected passage
 * links to its source's page; a selected claim opens nothing, and the pane, the
 * Claim review, says so.
 *
 * In the mock-up and not built, each for its own reason (D-138). Unsupported
 * claims: a statement that fails verification is never stored. "Open the N
 * answers": it would show other people's questions. "Add a source", the review
 * queue and "Owner": no record lies behind any of them. The two filters: neither
 * view of the map has filters.
 *
 * States, as the first view has them: loading; a 403 as the not-permitted notice
 * alone; any other failure as an error notice with "Try again"; the empty view, in
 * a sentence that names nothing that is kept from the reader, as the first view's
 * does not; and the empty selection, for a focus that names nothing in the
 * reader's view, for an address that is not a well-formed pair (no request is
 * sent) and for the server's 400. Every state that draws no map but the 403 and
 * loading also offers the switch back: this view is reached only by the switch, so
 * it never leaves a reader without the way out.
 *
 * The server checks `view_knowledge_map` on every request (invariant 4).
 *
 * @param {object} props
 * @param {(view: string) => void} props.onSwitch Tells the page a switch to `view` was made here.
 * @param {(view: string) => boolean} props.takeArrival Whether a switch led to `view`; asking spends it.
 */
export default function KnowledgeMapEvidence({ onSwitch, takeArrival }) {
  useDocumentTitle(TEXT.mapHeading)
  const [params] = useSearchParams()
  const selection = evidenceSelectionFromParams(params)
  // The identity of the request the address asks for: null where none is sent.
  const query = selection.kind === SELECTION_KIND.malformed ? null : knowledgeMapQuery(selection.focus)
  const { map, error, loading, retry } = useEvidenceMap(query)

  const [itemsSort, setItemsSort] = useState('')
  const [citationsSort, setCitationsSort] = useState('')

  const headingRef = useRef(null)
  const paneHeadingRef = useRef(null)
  const tablesHeadingRef = useRef(null)
  // The request a selection made on this page asked for, until its reply lands:
  // kept with its query and spent only on that query's reply, as the first view's is.
  const pendingFocus = useRef(null)

  useEffect(() => {
    const pending = pendingFocus.current
    if (loading || pending === null || pending !== query) return
    pendingFocus.current = null
    // The link that was followed left the page with the previous reply. Focus goes
    // to the pane's heading, or to the page heading where the reply drew no map.
    const target = paneHeadingRef.current ?? headingRef.current
    target?.focus()
  }, [loading, query])

  // Arriving here by the switch: focus goes to the page heading once the view has settled.
  useArrivalFocus(takeArrival, MAP_VIEW.evidence, !loading, headingRef)

  /** A selection, or a return to the whole view, made from a link on this page. */
  function handleSelect(focus) {
    pendingFocus.current = knowledgeMapQuery(focus)
  }

  /** "Skip to the table view": moves focus to the table view's heading, as the first view does. */
  function skipToTables(event) {
    event.preventDefault()
    tablesHeadingRef.current?.focus()
  }

  const nodes = nodesOf(map)
  const backToMap = <KnowledgeMapSwitch to={MAP_VIEW.relationships} onSwitch={onSwitch} />
  const emptySelection = (
    <Notice variant="info">
      <p>{TEXT.mapEmptySelection}</p>
      <p>
        <Link
          to={evidenceAddress()}
          onClick={(event) => {
            if (isPlainClick(event)) handleSelect(null)
          }}
        >
          {TEXT.mapShowWhole}
        </Link>
      </p>
    </Notice>
  )

  let statusLine = ''
  let body = null
  if (query === null || error?.status === 400) {
    // Not a well-formed pair, here or by the server's reading: no retry.
    body = (
      <>
        {emptySelection}
        <p className="knowledge-map__switch">{backToMap}</p>
      </>
    )
  } else if (loading) {
    statusLine = TEXT.mapLoading
  } else if (error?.status === 403) {
    body = <NotPermitted />
  } else if (error) {
    body = (
      <>
        <Notice variant="error" title={TEXT.mapLoadFailed}>
          {error.message}
        </Notice>
        <div className="knowledge-map__actions">
          <Button variant="secondary" onClick={retry}>
            {TEXT.uploadRetry}
          </Button>
          {backToMap}
        </div>
      </>
    )
  } else if (nodes.length === 0) {
    // The same reply for no claims at all and for a focus that is not in the
    // reader's view; the page tells them apart only by its own address.
    body = (
      <>
        {selection.kind === SELECTION_KIND.focus ? emptySelection : <Notice variant="info">{TEXT.evidenceEmpty}</Notice>}
        <p className="knowledge-map__switch">{backToMap}</p>
      </>
    )
  } else {
    const selected = selectedNodeOf(map)
    const citations = citationsOf(map)
    const truncation = truncationSentence(map, selected)
    const describedBy = truncation ? 'knowledge-map-truncation' : undefined
    const counts = countEvidence(nodes)
    statusLine = TEXT.mapCountLine([
      TEXT.evidenceCountClaims(counts[EVIDENCE_MAP_NODE_TYPE.claim]),
      TEXT.evidenceCountPassages(counts[EVIDENCE_MAP_NODE_TYPE.passage]),
    ])
    body = (
      <>
        {/* Before the skip link, so nobody skips past it. */}
        {truncation ? (
          <Notice variant="info">
            <span id="knowledge-map-truncation">{truncation}</span>
          </Notice>
        ) : null}
        <p className="knowledge-map__skip">
          <a href="#knowledge-map-tables-heading" onClick={skipToTables}>
            {TEXT.mapSkipToTables}
          </a>
        </p>
        <p className="knowledge-map__switch">{backToMap}</p>

        {/* Legend, diagram, pane: this order in the DOM, as in the first view. */}
        <div className="knowledge-map__layout">
          <EvidenceLegend />
          <div className="knowledge-map__diagram">
            <h2 id="knowledge-map-diagram-heading">{TEXT.evidenceDiagramHeading}</h2>
            <EvidenceDiagram
              nodes={nodes}
              citations={citations}
              selected={selected}
              labelledBy="knowledge-map-diagram-heading"
              onSelect={handleSelect}
            />
          </div>
          <EvidencePane
            selected={selected}
            connected={citedWith(selected, citations)}
            headingRef={paneHeadingRef}
            onSelect={handleSelect}
          />
        </div>

        <section className="knowledge-map__tables" aria-labelledby="knowledge-map-tables-heading">
          <h2 id="knowledge-map-tables-heading" ref={tablesHeadingRef} tabIndex={-1}>
            {TEXT.mapTablesHeading}
          </h2>
          <p className="knowledge-map__intro">{TEXT.mapTablesIntro}</p>
          <h3 id="knowledge-map-items-heading">{TEXT.mapItemsHeading}</h3>
          <EvidenceItemsTable
            nodes={nodes}
            selected={selected}
            sort={itemsSort}
            onSort={setItemsSort}
            describedBy={describedBy}
            onSelect={handleSelect}
          />
          <h3 id="knowledge-map-relationships-heading">{TEXT.mapRelationshipsHeading}</h3>
          {citations.length > 0 ? (
            <CitationsTable
              citations={citations}
              selected={selected}
              sort={citationsSort}
              onSort={setCitationsSort}
              describedBy={describedBy}
              onSelect={handleSelect}
            />
          ) : (
            <p>{TEXT.mapNoRelationships}</p>
          )}
        </section>
      </>
    )
  }

  return (
    <div className="knowledge-map">
      <h1 id="knowledge-map-heading" ref={headingRef} tabIndex={-1}>
        {TEXT.mapHeading}
      </h1>
      <p className="knowledge-map__intro">{TEXT.evidenceIntro}</p>
      {/* Always mounted, so the change from "Loading" to the count line is announced. */}
      <p className="knowledge-map__status" role="status">
        {statusLine}
      </p>
      {body}
    </div>
  )
}
