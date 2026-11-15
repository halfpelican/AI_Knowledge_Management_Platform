import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { fetchKnowledgeMap } from '../api/knowledgeMap.js'
import { SortHeader } from '../components/Browse.jsx'
import Button from '../components/Button.jsx'
import Notice from '../components/Notice.jsx'
import NotPermitted from '../components/NotPermitted.jsx'
import { KNOWLEDGE_MAP_NODE_TYPE, KNOWLEDGE_MAP_RELATIONSHIP, TEXT } from '../constants.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import {
  ITEM_SORT_FIELDS,
  KNOWLEDGE_MAP_PATH,
  MAP_COLUMNS,
  MAP_GRID_TEMPLATE,
  RELATIONSHIP_SORT_FIELDS,
  SELECTION_KIND,
  connectionGroups,
  countByType,
  displayLabel,
  focusOf,
  gridPlace,
  itemAddress,
  knowledgeMapQuery,
  layoutColumns,
  lineBetween,
  mapAddress,
  nodesOf,
  relationshipWords,
  relationshipsOf,
  selectedNodeOf,
  selectionFromParams,
  sortItems,
  sortRelationships,
  truncationSentence,
  typeText,
  typeWord,
  typedLabel,
} from '../utils/knowledgeMap.js'
// The table style the repository and the meetings list share.
import './Repository.css'
import './KnowledgeMap.css'

/* ---- Shapes -------------------------------------------------------------- */

/**
 * FR-20: "node type distinguished by colour and shape". One shape per type, each a
 * different element or a different outline, so the type survives without colour
 * (SC 1.4.1): a square, a circle, a diamond and a triangle.
 *
 * **The colour is not here.** Each shape carries a class, and KnowledgeMap.css
 * gives that class its fill from a token. A `fill` attribute or an inline style
 * would be seen by neither the contrast sweep nor the tokens-only check, which
 * read the stylesheets (D-132; tests/textEquivalents.test.jsx asserts there is
 * none). The numbers below are geometry inside a 20 by 20 box.
 */
const GLYPHS = {
  [KNOWLEDGE_MAP_NODE_TYPE.document]: (className) => <rect className={className} x="2" y="2" width="16" height="16" />,
  [KNOWLEDGE_MAP_NODE_TYPE.meeting]: (className) => <circle className={className} cx="10" cy="10" r="9" />,
  [KNOWLEDGE_MAP_NODE_TYPE.tag]: (className) => <polygon className={className} points="10,1 19,10 10,19 1,10" />,
  [KNOWLEDGE_MAP_NODE_TYPE.contributor]: (className) => <polygon className={className} points="10,2 19,18 1,18" />,
}

/**
 * A node type's shape. Decoration: `aria-hidden`, because the type is always also
 * a word beside it or in the accessible name (SC 1.1.1).
 */
function NodeShape({ type }) {
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
 * The legend: the four node types, each its shape in its colour beside its word,
 * and what a line means. It lists the vocabulary itself
 * (`KNOWLEDGE_MAP_NODE_TYPE`), through the same `NodeShape` the diagram draws, so
 * the legend and the diagram cannot come to show different shapes.
 *
 * It asks the API for nothing, which is why the component sheet can show it.
 *
 * @param {object} props
 * @param {2|3} [props.headingLevel] The level of its heading: 2 on the page, 3
 *   where it sits under another section's heading, as on the component sheet.
 */
export function KnowledgeMapLegend({ headingLevel = 2 }) {
  const Heading = `h${headingLevel}`
  return (
    <section className="knowledge-map__legend" aria-labelledby="knowledge-map-legend-heading">
      <Heading id="knowledge-map-legend-heading">{TEXT.mapLegendHeading}</Heading>
      <p className="knowledge-map__legend-note">{TEXT.mapLegendTypes}</p>
      <ul className="knowledge-map__legend-list">
        {Object.values(KNOWLEDGE_MAP_NODE_TYPE).map((type) => (
          <li key={type} className="knowledge-map__legend-item">
            <NodeShape type={type} />
            <span>{typeWord(type)}</span>
          </li>
        ))}
      </ul>
      <p className="knowledge-map__legend-item">
        <svg className="knowledge-map__legend-line" viewBox="0 0 40 10" aria-hidden="true" focusable="false">
          <line className="knowledge-map__line" x1="0" y1="5" x2="40" y2="5" />
        </svg>
        <span>{TEXT.mapLegendLine}</span>
      </p>
      <p className="knowledge-map__legend-note">{TEXT.mapLegendSelected}</p>
    </section>
  )
}

/* ---- A node, wherever it is shown ---------------------------------------- */

/** What a second selection of each type opens, in the selected node's own name. */
const SELECT_AGAIN = {
  [KNOWLEDGE_MAP_NODE_TYPE.document]: TEXT.mapSelectAgainDocument,
  [KNOWLEDGE_MAP_NODE_TYPE.meeting]: TEXT.mapSelectAgainMeeting,
  [KNOWLEDGE_MAP_NODE_TYPE.tag]: TEXT.mapSelectAgainTag,
}

/** The count as the server sent it in words, or null for one that did not arrive. */
function connectionsShown(node) {
  return Number.isFinite(node.connection_count) ? TEXT.mapConnectionsShown(node.connection_count) : null
}

/** A click that follows the link here, not one that opens it in another tab or window. */
function isPlainClick(event) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
}

/**
 * One node, as the control that selects it. The same control is used on the
 * diagram, in the Selected panel, in an Items row and at both ends of a
 * Relationships row (UC-11 A1: "Selecting a row has the same effect as selecting a
 * node"), so there is one place that decides where a node leads:
 *
 * - **not selected**: a link to the map's own address with this node as the focus.
 *   The selection lives in the address (D-132), so Back and a reload keep it;
 * - **selected, a document, a meeting or a tag**: a link to the item itself (FR-20:
 *   "selecting again opens the underlying item"), marked `aria-current`, with the
 *   word "Selected" and what a second selection does in its name;
 * - **selected, a contributor**: not a link, because there is nothing to open
 *   (D-132, the user's choice on "selecting again" for a tag and a contributor).
 *   It carries the same mark.
 *
 * Always a native link, or plain text: no key handler and no `role="button"`.
 *
 * `variant` is what the control says. `node`, on the diagram: its shape, its type
 * (for a screen reader, since the shape and the column say it to the eye), its
 * label and its count. `typed`: "Document: Leave policy", where nothing beside it
 * says the type. `name`: the label alone, in the Items table, whose Type column is
 * beside it. A tag's label always carries its dimension.
 *
 * Every label is text from a document, a meeting, a tag or a person's name:
 * untrusted, and rendered as text.
 *
 * @param {object} props
 * @param {object} props.node
 * @param {object|null} props.selected The selected node, or null.
 * @param {'node'|'typed'|'name'} props.variant
 * @param {(focus: {type: string, id: string}) => void} [props.onSelect] Called when a
 *   selection is made from here, before the address changes.
 */
function MapNode({ node, selected, variant, onSelect }) {
  const isSelected = selected?.id === node.id
  const opens = isSelected ? itemAddress(node) : null
  const label = displayLabel(node)
  const count = connectionsShown(node)

  // The punctuation between the parts is for a screen reader, which reads the
  // control as one name: "Document: Leave policy, 3 connections shown, Selected.
  // Select again to open the document." Each space is a text node of its own
  // between two elements, never the first or last character inside one, where an
  // accessible-name computation may trim it.
  const mark = isSelected ? (
    <>
      <span className="visually-hidden">,</span>{' '}
      <span className="knowledge-map__selected-mark">{TEXT.mapSelectedMark}</span>
      {opens && SELECT_AGAIN[node.type] ? (
        <>
          <span className="visually-hidden">.</span>{' '}
          <span className="visually-hidden">{SELECT_AGAIN[node.type]}</span>
        </>
      ) : null}
    </>
  ) : null

  let content
  if (variant === 'node') {
    content = (
      <>
        <NodeShape type={node.type} />
        <span className="knowledge-map__node-text">
          {/* The type, for a screen reader: "Document:". */}
          <span className="visually-hidden">{TEXT.mapTypedLabel(typeWord(node.type), '').trim()}</span>{' '}
          <span className="knowledge-map__node-label">{label}</span>
          {count ? (
            <>
              <span className="visually-hidden">,</span>{' '}
              {/* Text on the surface, never on a fill (D-132). */}
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
          {variant === 'typed' ? typedLabel(node) : label}
        </span>
        {mark}
      </>
    )
  }

  const base = variant === 'node' ? 'knowledge-map__node' : 'knowledge-map__ref'
  const className = isSelected ? `${base} ${base}--selected` : base

  if (!isSelected) {
    const focus = focusOf(node)
    return (
      <Link
        className={className}
        to={mapAddress(focus)}
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
 * FR-20's node-link diagram, as a pure view of the nodes and relationships it is
 * given. It draws exactly those: nothing is added, left out or counted here.
 *
 * Three columns from `layoutColumns`: contributors, then documents and meetings,
 * then tags, one row per node. Two layers:
 *
 * - **the lines**, an SVG under the nodes. `aria-hidden`, with nothing focusable in
 *   it: a line says nothing a screen reader can use, and the Relationships table
 *   says the same thing in rows (NFR-17, SC 1.1.1). Its coordinates are
 *   percentages of the diagram, worked out from the layout, never measured;
 * - **the nodes**, a list of real links over it, in the layout's order (column by
 *   column, top to bottom), so the tab order is the reading order (SC 2.4.3).
 *
 * The whole diagram sits in a labelled, focusable scroll region, as a data table
 * does: at a narrow width it scrolls inside the region and the page does not
 * (SC 1.4.10). Inline style here is position only: the grid's tracks and each
 * node's place. Every colour is a class (KnowledgeMap.css). No zoom, pan, drag or
 * animation.
 *
 * @param {object} props
 * @param {object[]} props.nodes
 * @param {{key: string, relationship: string, source: object, target: object}[]} props.relationships
 * @param {object|null} props.selected
 * @param {string} props.labelledBy The id of the heading that names the region.
 * @param {(focus: object) => void} [props.onSelect]
 */
export function KnowledgeMapDiagram({ nodes, relationships, selected, labelledBy, onSelect }) {
  const layout = layoutColumns(nodes)
  const placeOf = new Map(layout.placed.map((place) => [place.node.id, place]))
  const lines = relationships
    .map((row) => ({
      key: row.key,
      selected: Boolean(selected) && (row.source.id === selected.id || row.target.id === selected.id),
      ...lineBetween(placeOf.get(row.source.id), placeOf.get(row.target.id), layout.rows),
    }))
    // The selected node's lines are drawn last, so no other line is painted over them.
    .sort((first, second) => Number(first.selected) - Number(second.selected))

  return (
    <div className="knowledge-map__scroll" role="region" aria-labelledby={labelledBy} tabIndex={0}>
      <div className="knowledge-map__columns" style={{ gridTemplateColumns: MAP_GRID_TEMPLATE }}>
        {MAP_COLUMNS.map((column, index) => (
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
              className={line.selected ? 'knowledge-map__line knowledge-map__line--selected' : 'knowledge-map__line'}
              x1={line.x1}
              y1={line.y1}
              x2={line.x2}
              y2={line.y2}
            />
          ))}
        </svg>
        <ul className="knowledge-map__nodes" style={{ gridTemplateColumns: MAP_GRID_TEMPLATE }}>
          {layout.placed.map((place) => (
            <li key={place.node.id} className="knowledge-map__cell" style={gridPlace(place)}>
              <MapNode node={place.node} selected={selected} variant="node" onSelect={onSelect} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/* ---- Selected panel ------------------------------------------------------ */

/** A group's heading: the relationship, read from the selected node's end of it. */
const GROUP_HEADINGS = {
  [KNOWLEDGE_MAP_RELATIONSHIP.tagged]: { source: TEXT.mapGroupTags, target: TEXT.mapGroupTagged },
  [KNOWLEDGE_MAP_RELATIONSHIP.uploaded]: { source: TEXT.mapGroupUploaded, target: TEXT.mapGroupUploadedBy },
  [KNOWLEDGE_MAP_RELATIONSHIP.attended]: { source: TEXT.mapGroupAttended, target: TEXT.mapGroupAttendedBy },
}

function groupHeading({ relationship, end }) {
  return GROUP_HEADINGS[relationship]?.[end] ?? relationshipWords(relationship)
}

/** The open action's words for a node that has something to open. */
function openLabel(node) {
  if (node.type === KNOWLEDGE_MAP_NODE_TYPE.document) return TEXT.mapOpenDocument
  if (node.type === KNOWLEDGE_MAP_NODE_TYPE.meeting) return TEXT.mapOpenMeeting
  return TEXT.mapOpenTag(node.label)
}

/**
 * The Selected panel: what is selected, its count, its direct connections grouped
 * by relationship, and the open action (FR-20: "Selecting a node reveals its
 * connections; selecting again opens the underlying item").
 *
 * The connections are the reply's edges that touch the selected node, and each is
 * the same control that selects that node everywhere else. For a contributor the
 * panel says there is nothing to open (D-132, the user's choice on "selecting again"
 * for a tag and a contributor). With nothing selected it says how to select. Its heading takes focus when a selection made on this page
 * has loaded, so a keyboard or screen-reader user lands on the answer to what they
 * just did.
 */
function SelectedPanel({ selected, groups, headingRef, onSelect }) {
  let body
  if (!selected) {
    body = <p>{TEXT.mapSelectedNone}</p>
  } else {
    const opens = itemAddress(selected)
    const count = connectionsShown(selected)
    body = (
      <>
        <p className="knowledge-map__panel-item">
          <NodeShape type={selected.type} />
          <span>
            <span className="knowledge-map__panel-type">{typeText(selected)}</span>{' '}
            {/* Untrusted text, rendered as text. */}
            <strong className="knowledge-map__panel-name">{selected.label}</strong>
          </span>
        </p>
        {count ? <p className="knowledge-map__panel-count">{count}</p> : null}
        {groups.map((group) => (
          <div key={`${group.relationship}:${group.end}`} className="knowledge-map__group">
            <h3>{groupHeading(group)}</h3>
            <ul className="knowledge-map__group-list">
              {group.nodes.map((node) => (
                <li key={node.id}>
                  <MapNode node={node} selected={selected} variant="typed" onSelect={onSelect} />
                </li>
              ))}
            </ul>
          </div>
        ))}
        {opens ? (
          <p>
            <Link to={opens}>{openLabel(selected)}</Link>
          </p>
        ) : null}
        {selected.type === KNOWLEDGE_MAP_NODE_TYPE.contributor ? <p>{TEXT.mapContributorNoPage}</p> : null}
        <p>
          <Link
            to={KNOWLEDGE_MAP_PATH}
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
        {TEXT.mapSelectedHeading}
      </h2>
      {body}
    </section>
  )
}

/* ---- Table view (NFR-17) ------------------------------------------------- */

/**
 * NFR-17's table of nodes: one row per node the reply holds, the unconnected ones
 * included, which no row of relationships could carry. Name is the same control
 * the node is; Type is a word (a tag's with its dimension), so the type does not
 * depend on colour or shape; Connections shown is the server's count, as sent.
 *
 * Every column sorts from its heading: a native button in a `th` that carries
 * `aria-sort` (`SortHeader`). When the view is partial the table's accessible
 * description is the sentence that says so (`describedBy`), so a reader who went
 * straight to the table is told too (UC-11 A2: "alongside the map or table").
 */
function ItemsTable({ nodes, selected, sort, onSort, describedBy, onSelect }) {
  const sortProps = { sort, onSort }
  return (
    <div className="table-scroll" role="region" aria-labelledby="knowledge-map-items-heading" tabIndex={0}>
      <table className="data-table" aria-describedby={describedBy}>
        <caption className="visually-hidden">{TEXT.mapItemsCaption}</caption>
        <thead>
          <tr>
            <SortHeader label={TEXT.mapItemsColumnName} field={ITEM_SORT_FIELDS.name} {...sortProps} />
            <SortHeader label={TEXT.mapItemsColumnType} field={ITEM_SORT_FIELDS.type} {...sortProps} />
            <SortHeader label={TEXT.mapItemsColumnConnections} field={ITEM_SORT_FIELDS.connections} {...sortProps} />
          </tr>
        </thead>
        <tbody>
          {sortItems(nodes, sort).map((node) => (
            <tr key={node.id}>
              <th scope="row" className="data-table__title">
                <MapNode node={node} selected={selected} variant="name" onSelect={onSelect} />
              </th>
              <td>{typeText(node)}</td>
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
 * NFR-17's table of relationships: one row per edge the reply holds, which is one
 * row per line the diagram draws. It reads "from, relationship, to", in words.
 * From and To are the same controls the nodes are and name their type, because
 * nothing else in the row does.
 */
function RelationshipsTable({ relationships, selected, sort, onSort, describedBy, onSelect }) {
  const sortProps = { sort, onSort }
  return (
    <div className="table-scroll" role="region" aria-labelledby="knowledge-map-relationships-heading" tabIndex={0}>
      <table className="data-table" aria-describedby={describedBy}>
        <caption className="visually-hidden">{TEXT.mapRelationshipsCaption}</caption>
        <thead>
          <tr>
            <SortHeader label={TEXT.mapRelationshipsColumnFrom} field={RELATIONSHIP_SORT_FIELDS.from} {...sortProps} />
            <SortHeader
              label={TEXT.mapRelationshipsColumnRelationship}
              field={RELATIONSHIP_SORT_FIELDS.relationship}
              {...sortProps}
            />
            <SortHeader label={TEXT.mapRelationshipsColumnTo} field={RELATIONSHIP_SORT_FIELDS.to} {...sortProps} />
          </tr>
        </thead>
        <tbody>
          {sortRelationships(relationships, sort).map((row) => (
            <tr key={row.key}>
              <th scope="row" className="data-table__title">
                <MapNode node={row.source} selected={selected} variant="typed" onSelect={onSelect} />
              </th>
              <td>{relationshipWords(row.relationship)}</td>
              <td className="data-table__title">
                <MapNode node={row.target} selected={selected} variant="typed" onSelect={onSelect} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ---- The one request ----------------------------------------------------- */

/**
 * The page's single request, re-sent whenever the selection in the address changes.
 *
 * Each reply is kept with the request it answers (`key`), and one that answers an
 * earlier request is never shown as the answer to the current one, as the
 * repository's `useBrowse` does: after a selection the page says it is loading
 * rather than showing the previous map under the new address, and a failed
 * selection leaves no earlier map on screen (UC-11: on failure "No map or table is
 * presented"). Nothing is cached, here or in src/api/knowledgeMap.js.
 *
 * With `query` null there is no request at all: the address holds a selection
 * that is not a well-formed pair, which the server would refuse on every attempt.
 *
 * @param {string|null} query The focus as a query string, `''` for the overview, or null.
 */
function useKnowledgeMap(query) {
  const [attempt, setAttempt] = useState(0)
  const [settled, setSettled] = useState({ key: null, map: null, error: null })
  const key = query === null ? null : `${attempt}?${query}`

  useEffect(() => {
    if (key === null) return undefined
    const controller = new AbortController()
    const { focus } = selectionFromParams(new URLSearchParams(query))
    fetchKnowledgeMap(focus, { signal: controller.signal }).then(
      (map) => {
        if (controller.signal.aborted) return
        setSettled({ key, map, error: null })
      },
      (caught) => {
        // This screen cancelling its own request, because the address moved on.
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

/* ---- The page ------------------------------------------------------------ */

/**
 * FR-20's knowledge map, with NFR-17's table view (NIT3004, D-132): how the
 * documents, meetings, tags and contributors in the reader's scope relate.
 *
 * **The page renders what the server sent.** The nodes, the edges, every
 * connection count and the truncation fields arrive already scoped to the caller's
 * role, then capped, then counted (CLAUDE.md §6, invariant 1; UC-11). Nothing here
 * filters, trims or recounts them, and nothing is a placeholder for something left
 * out. The page derives three things only: the count line, counted from the nodes
 * on screen; the order of the two tables' rows; and where each node is drawn.
 *
 * **The selection lives in the address**: `?focus_type=<type>&focus_id=<uuid>`,
 * the contract's own parameter names. Selecting a node is a link to that address,
 * which is a second request for the walk from that node. Opening an item and
 * pressing Back returns to the same selection (D-61's gap 3). The node marked
 * selected is the one the reply's `focus` names, never the address's own spelling.
 * The two tables' sorts are page state and reset when the page is left.
 *
 * States: loading; a 403 as the not-permitted notice alone; any other failure as
 * an error notice with "Try again"; the empty map, in one sentence that reads the
 * same whether nothing exists or nothing is in the reader's scope (UC-11 E1); and
 * the empty selection, for a focus that names nothing on the reader's map, for an
 * address that is not a well-formed pair (no request is sent) and for the server's
 * 400 (no retry, since the same address would be refused the same way).
 *
 * The route is inside RequireAuth and the navigation offers the link to every
 * signed-in user. Both are usability: the server checks `view_knowledge_map` on
 * every request (CLAUDE.md §6, invariant 4).
 */
export default function KnowledgeMap() {
  useDocumentTitle(TEXT.mapHeading)
  const [params] = useSearchParams()
  const selection = selectionFromParams(params)
  // The identity of the view the address asks for: null where no request is sent.
  const query = selection.kind === SELECTION_KIND.malformed ? null : knowledgeMapQuery(selection.focus)
  const { map, error, loading, retry } = useKnowledgeMap(query)

  const [itemsSort, setItemsSort] = useState('')
  const [relationshipsSort, setRelationshipsSort] = useState('')

  const headingRef = useRef(null)
  const panelHeadingRef = useRef(null)
  const tablesHeadingRef = useRef(null)
  // The view a selection made on this page asked for, until its reply lands. Kept
  // with the query it was set for and spent only on that query's reply, for the
  // reason src/pages/DocumentRepository.jsx gives: an effect still pending from the
  // previous reply runs before the click's own update.
  const pendingFocus = useRef(null)

  useEffect(() => {
    const pending = pendingFocus.current
    if (loading || pending === null || pending !== query) return
    pendingFocus.current = null
    // The link that was followed left the page with the previous reply. Focus goes
    // to the Selected panel's heading, which now says what is selected, or to the
    // page heading where the reply drew no map.
    const target = panelHeadingRef.current ?? headingRef.current
    target?.focus()
  }, [loading, query])

  /** A selection, or a return to the whole map, made from a link on this page. */
  function handleSelect(focus) {
    pendingFocus.current = knowledgeMapQuery(focus)
  }

  /**
   * "Skip to the table view": a native link to the table view's heading, which
   * takes focus so the next Tab is the first table (NFR-17). Focus is moved here
   * rather than by the address's fragment, which would add a history entry between
   * the reader and the selection Back returns to.
   */
  function skipToTables(event) {
    event.preventDefault()
    tablesHeadingRef.current?.focus()
  }

  const nodes = nodesOf(map)
  const emptySelection = (
    <Notice variant="info">
      <p>{TEXT.mapEmptySelection}</p>
      <p>
        <Link
          to={KNOWLEDGE_MAP_PATH}
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
    // Not a well-formed pair, here or by the server's reading. Sending the same
    // address again would be refused the same way, so there is no retry.
    body = emptySelection
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
        </div>
      </>
    )
  } else if (nodes.length === 0) {
    // UC-11 E1. The same reply for an empty knowledge base, a role with nothing in
    // scope and a focus that is not on the reader's map; the page tells the last
    // apart only by its own address, which asked for a selection.
    body = selection.kind === SELECTION_KIND.focus ? emptySelection : <Notice variant="info">{TEXT.mapEmpty}</Notice>
  } else {
    const selected = selectedNodeOf(map)
    const relationships = relationshipsOf(map)
    const truncation = truncationSentence(map, selected)
    const describedBy = truncation ? 'knowledge-map-truncation' : undefined
    const counts = countByType(nodes)
    statusLine = TEXT.mapCountLine([
      TEXT.mapCountDocuments(counts[KNOWLEDGE_MAP_NODE_TYPE.document]),
      TEXT.mapCountMeetings(counts[KNOWLEDGE_MAP_NODE_TYPE.meeting]),
      TEXT.mapCountTags(counts[KNOWLEDGE_MAP_NODE_TYPE.tag]),
      TEXT.mapCountContributors(counts[KNOWLEDGE_MAP_NODE_TYPE.contributor]),
    ])
    body = (
      <>
        {/* Before the skip link, so nobody skips past it (UC-11 A2). */}
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

        {/* Legend, diagram, Selected panel: this order in the DOM, so one column
            stacks them without reordering and the tab order is the same at every
            width. */}
        <div className="knowledge-map__layout">
          <KnowledgeMapLegend />
          {/* Not a named section of its own: the scroll region inside takes the
              heading's name, and two regions called "Map" would be one too many. */}
          <div className="knowledge-map__diagram">
            <h2 id="knowledge-map-diagram-heading">{TEXT.mapDiagramHeading}</h2>
            <KnowledgeMapDiagram
              nodes={nodes}
              relationships={relationships}
              selected={selected}
              labelledBy="knowledge-map-diagram-heading"
              onSelect={handleSelect}
            />
          </div>
          <SelectedPanel
            selected={selected}
            groups={connectionGroups(selected, relationships)}
            headingRef={panelHeadingRef}
            onSelect={handleSelect}
          />
        </div>

        <section className="knowledge-map__tables" aria-labelledby="knowledge-map-tables-heading">
          <h2 id="knowledge-map-tables-heading" ref={tablesHeadingRef} tabIndex={-1}>
            {TEXT.mapTablesHeading}
          </h2>
          <p className="knowledge-map__intro">{TEXT.mapTablesIntro}</p>
          <h3 id="knowledge-map-items-heading">{TEXT.mapItemsHeading}</h3>
          <ItemsTable
            nodes={nodes}
            selected={selected}
            sort={itemsSort}
            onSort={setItemsSort}
            describedBy={describedBy}
            onSelect={handleSelect}
          />
          <h3 id="knowledge-map-relationships-heading">{TEXT.mapRelationshipsHeading}</h3>
          {relationships.length > 0 ? (
            <RelationshipsTable
              relationships={relationships}
              selected={selected}
              sort={relationshipsSort}
              onSort={setRelationshipsSort}
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
      <p className="knowledge-map__intro">{TEXT.mapIntro}</p>
      {/* Always mounted, so the change from "Loading" to the count line is
          announced as well as shown. The count is of the nodes on screen. */}
      <p className="knowledge-map__status" role="status">
        {statusLine}
      </p>
      {body}
    </div>
  )
}
