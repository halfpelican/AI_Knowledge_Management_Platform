/**
 * FR-20's knowledge map (D-132): the page's pure helpers. The addresses, the
 * column layout, the words for a node, and the two tables' sorting.
 *
 * Nothing here imports React or fetches, and nothing here decides what the map
 * holds. The nodes, the edges, every connection count and both truncation fields
 * arrive already scoped to the caller's role, capped and counted by the server
 * (CLAUDE.md §6, invariant 1; docs/api-contract.md, "NIT3004 — FR-20"). These
 * functions arrange and name what was sent. The only things derived are the ones
 * D-132 lists: the count line, the two sorts, and where each node is drawn.
 */
import { TAG_OPTION_DIMENSIONS } from '../api/documents.js'
import {
  KNOWLEDGE_MAP_NODE_TYPE,
  KNOWLEDGE_MAP_RELATIONSHIP,
  KNOWLEDGE_MAP_TRUNCATION_REASON,
  TEXT,
} from '../constants.js'

/* ---- Addresses ----------------------------------------------------------- */

/** The route the page is mounted at (src/App.jsx). */
export const KNOWLEDGE_MAP_PATH = '/knowledge-map'

/** The two parameters a selection is, in the address and in the API query alike. */
export const FOCUS_TYPE_PARAM = 'focus_type'
export const FOCUS_ID_PARAM = 'focus_id'

const NODE_TYPES = Object.values(KNOWLEDGE_MAP_NODE_TYPE)

/** What the address asks for: the overview, a selection, or a pair that is not one. */
export const SELECTION_KIND = {
  overview: 'overview',
  focus: 'focus',
  malformed: 'malformed',
}

/**
 * The selection an address holds (D-132, "The screen": an unselected node links to
 * the map's own address "with the selection in it").
 *
 * - Neither parameter, or both empty: the overview. The contract reads an empty
 *   value as an absent one, so the address does too.
 * - Both, with a `focus_type` in the vocabulary: a selection. The identifier is
 *   passed on as written. The server accepts a UUID in any spelling and answers
 *   in the canonical one, so the identifier's shape is its to judge: a second
 *   copy of that rule here could come to disagree with it, and a 400 is shown as
 *   the same empty selection anyway.
 * - Anything else (one without the other, or a type outside the vocabulary):
 *   malformed. The page shows the empty selection and sends no request, because
 *   the server would refuse it the same way on every attempt.
 *
 * @param {URLSearchParams} params
 * @returns {{kind: string, focus: {type: string, id: string}|null}}
 */
export function selectionFromParams(params) {
  const type = params.get(FOCUS_TYPE_PARAM) ?? ''
  const id = params.get(FOCUS_ID_PARAM) ?? ''
  if (!type && !id) return { kind: SELECTION_KIND.overview, focus: null }
  if (!type || !id || !NODE_TYPES.includes(type)) return { kind: SELECTION_KIND.malformed, focus: null }
  return { kind: SELECTION_KIND.focus, focus: { type, id } }
}

/**
 * The query string for a focus, without its `?`, or `''` for the overview. Built
 * with `URLSearchParams`, so whatever an identifier holds is encoded (the design
 * review's security finding F9). The same string is the API's query, the address's
 * query and the identity of the request the page is showing.
 *
 * @param {{type: string, id: string}|null} focus
 */
export function knowledgeMapQuery(focus) {
  if (!focus) return ''
  const params = new URLSearchParams()
  params.set(FOCUS_TYPE_PARAM, focus.type)
  params.set(FOCUS_ID_PARAM, focus.id)
  return params.toString()
}

/** The map's own address for a focus, or for the whole map with none. */
export function mapAddress(focus = null) {
  const query = knowledgeMapQuery(focus)
  return query ? `${KNOWLEDGE_MAP_PATH}?${query}` : KNOWLEDGE_MAP_PATH
}

/** The focus that selects `node`: its type and the row's own identifier. */
export function focusOf(node) {
  return { type: node.type, id: node.item_id }
}

/**
 * A click that follows a link here, not one that opens it in another tab or window:
 * the main button, with no modifier key. Both views of the map ask it before they
 * note that a selection was made on the page.
 */
export function isPlainClick(event) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
}

/** The repository's filter parameter for each tag dimension: `Topic` is `topic`. */
const TAG_FILTER_PARAMS = Object.fromEntries(
  TAG_OPTION_DIMENSIONS.map((dimension) => [dimension, dimension.toLowerCase()]),
)

/**
 * Where "selecting again opens the underlying item" goes (FR-20; D-132, the user's
 * choice on it for a tag and a contributor), or null where there is nothing to open:
 *
 * - a document: its detail page;
 * - a meeting: its meeting page;
 * - a tag: FR-15's repository filtered by that tag, `/documents?<dimension, lower
 *   case>=<name>`. Built with `URLSearchParams`, so a name such as "r&d #1 100%"
 *   opens that filter and adds none of its own;
 * - a contributor: null. The proposal defines no page for a person.
 *
 * @param {{type: string, item_id: string, label: string, dimension: string|null}} node
 * @returns {string|null}
 */
export function itemAddress(node) {
  switch (node.type) {
    case KNOWLEDGE_MAP_NODE_TYPE.document:
      return `/documents/${encodeURIComponent(node.item_id)}`
    case KNOWLEDGE_MAP_NODE_TYPE.meeting:
      return `/meetings/${encodeURIComponent(node.item_id)}`
    case KNOWLEDGE_MAP_NODE_TYPE.tag: {
      const param = TAG_FILTER_PARAMS[node.dimension]
      if (!param) return null
      const params = new URLSearchParams()
      params.set(param, node.label)
      return `/documents?${params.toString()}`
    }
    default:
      return null
  }
}

/* ---- What the reply holds ------------------------------------------------ */

/** A reply's list under `key`, or an empty one where it did not arrive as a list. */
export function listOf(map, key) {
  return Array.isArray(map?.[key]) ? map[key] : []
}

/** The nodes of a reply, as sent. */
export function nodesOf(map) {
  return listOf(map, 'nodes')
}

/**
 * The selected node: the returned node the reply's own `focus` names, or null.
 * Never read from the address (the contract: "The page marks the selected node
 * from this, not from its own address"), so an identifier typed in upper case
 * still marks the node the server found.
 */
export function selectedNodeOf(map) {
  const focus = map?.focus
  if (!focus) return null
  return nodesOf(map).find((node) => node.type === focus.type && node.item_id === focus.id) ?? null
}

/**
 * Every edge of a reply with its two nodes beside it, in the reply's order. The
 * contract puts both ends of every edge in `nodes`; an edge whose end is not there
 * is left out here, once, so the diagram and the Relationships table are given one
 * list and can never hold different edges.
 *
 * @returns {{key: string, relationship: string, source: object, target: object}[]}
 */
export function relationshipsOf(map) {
  const byId = new Map(nodesOf(map).map((node) => [node.id, node]))
  const rows = []
  for (const edge of listOf(map, 'edges')) {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) continue
    rows.push({ key: `${edge.source}|${edge.relationship}|${edge.target}`, relationship: edge.relationship, source, target })
  }
  return rows
}

/**
 * How many of each type the reply holds, for the count line. Counted from the
 * nodes on screen and from nothing else: the server sends no total, and the line
 * must never suggest one (D-132).
 *
 * @returns {Record<string, number>} keyed by node type
 */
export function countByType(nodes) {
  const counts = Object.fromEntries(NODE_TYPES.map((type) => [type, 0]))
  for (const node of nodes) {
    if (node.type in counts) counts[node.type] += 1
  }
  return counts
}

/**
 * The selected node's direct connections, grouped by relationship and by which end
 * of it the selected node is: the edges of the reply that touch it, and no others.
 * Relationships come in the vocabulary's order, and within a group the nodes come
 * in the reply's order.
 *
 * @returns {{relationship: string, end: 'source'|'target', nodes: object[]}[]}
 */
export function connectionGroups(selected, relationships) {
  if (!selected) return []
  const groups = []
  for (const relationship of Object.values(KNOWLEDGE_MAP_RELATIONSHIP)) {
    for (const end of ['source', 'target']) {
      const other = end === 'source' ? 'target' : 'source'
      const nodes = relationships
        .filter((row) => row.relationship === relationship && row[end].id === selected.id)
        .map((row) => row[other])
      if (nodes.length > 0) groups.push({ relationship, end, nodes })
    }
  }
  return groups
}

/**
 * The sentence that says a view is partial, or null for a whole one (FR-20:
 * "truncation is reported to the interface so that a partial view is not presented
 * as complete"; UC-11 A2). Which sentence is the reply's `truncated_by` and
 * whether the view has a selection, and both numbers are the reply's own maximums:
 * the page holds no copy of either cap (CLAUDE.md §5).
 *
 * A truncated reply with a reason outside the vocabulary, or without its maximum,
 * is still said to be partial, in words that name no number.
 *
 * @param {object} map the reply
 * @param {object|null} selected `selectedNodeOf(map)`
 * @returns {string|null}
 */
export function truncationSentence(map, selected) {
  if (map?.truncated !== true) return null
  const { truncated_by: reason, maximum_node_count: maximumNodes, maximum_traversal_depth: maximumDepth } = map
  if (reason === KNOWLEDGE_MAP_TRUNCATION_REASON.nodeCount && Number.isFinite(maximumNodes)) {
    return selected ? TEXT.mapTruncatedSelection(maximumNodes) : TEXT.mapTruncatedOverview(maximumNodes)
  }
  if (reason === KNOWLEDGE_MAP_TRUNCATION_REASON.depth && Number.isFinite(maximumDepth)) {
    return TEXT.mapTruncatedDepth(maximumDepth)
  }
  return TEXT.mapTruncatedOther
}

/* ---- Words --------------------------------------------------------------- */

const TYPE_WORDS = {
  [KNOWLEDGE_MAP_NODE_TYPE.document]: TEXT.mapTypeDocument,
  [KNOWLEDGE_MAP_NODE_TYPE.meeting]: TEXT.mapTypeMeeting,
  [KNOWLEDGE_MAP_NODE_TYPE.tag]: TEXT.mapTypeTag,
  [KNOWLEDGE_MAP_NODE_TYPE.contributor]: TEXT.mapTypeContributor,
}

/** A node type in a word, or the type as sent for one these do not name. */
export function typeWord(type) {
  return TYPE_WORDS[type] ?? String(type ?? '')
}

/**
 * What a node is called on screen. A tag is called by its dimension and its name
 * ("Topic: people"), because a name is unique only within a dimension and two
 * tags named alike would otherwise read as one (D-132, departure 5).
 */
export function displayLabel(node) {
  if (node.type === KNOWLEDGE_MAP_NODE_TYPE.tag && node.dimension) {
    return TEXT.mapTagLabel(node.dimension, node.label)
  }
  return String(node.label ?? '')
}

/**
 * What a From or To cell, or a connection in the Selected panel, calls a node: its
 * type in a word, then what it is called ("Tag: Topic: people"). Nothing else in
 * such a row names the type. The Relationships table sorts on this text.
 */
export function typedLabel(node) {
  return TEXT.mapTypedLabel(typeWord(node.type), displayLabel(node))
}

/** The Items table's Type cell: the type in a word, a tag's with its dimension. */
export function typeText(node) {
  if (node.type === KNOWLEDGE_MAP_NODE_TYPE.tag && node.dimension) return TEXT.mapTagType(node.dimension)
  return typeWord(node.type)
}

const RELATIONSHIP_WORDS = {
  [KNOWLEDGE_MAP_RELATIONSHIP.tagged]: TEXT.mapRelationshipTagged,
  [KNOWLEDGE_MAP_RELATIONSHIP.uploaded]: TEXT.mapRelationshipUploaded,
  [KNOWLEDGE_MAP_RELATIONSHIP.attended]: TEXT.mapRelationshipAttended,
}

/** A relationship in words, read "from, relationship, to". */
export function relationshipWords(relationship) {
  return RELATIONSHIP_WORDS[relationship] ?? String(relationship ?? '')
}

/* ---- The column layout --------------------------------------------------- */

/**
 * The three columns, left to right: contributors, then documents and meetings,
 * then tags. Every edge joins neighbouring columns (a contributor to a source, a
 * source to a tag), so no line crosses a column of nodes.
 */
export const MAP_COLUMNS = [
  { key: 'contributors', heading: TEXT.mapColumnContributors },
  { key: 'sources', heading: TEXT.mapColumnSources },
  { key: 'tags', heading: TEXT.mapColumnTags },
]

const COLUMN_OF_TYPE = {
  [KNOWLEDGE_MAP_NODE_TYPE.contributor]: 0,
  [KNOWLEDGE_MAP_NODE_TYPE.document]: 1,
  [KNOWLEDGE_MAP_NODE_TYPE.meeting]: 1,
  [KNOWLEDGE_MAP_NODE_TYPE.tag]: 2,
}

/**
 * The grid the diagram is drawn on: a column of nodes, a gutter the lines cross,
 * a column, a gutter, a column. The shares are parts of the diagram's width, and
 * they are stated once, here: the grid's tracks and the ends of every line are
 * both worked out from them, so a line always ends on the edge of its node.
 */
const NODE_TRACK_SHARE = 7
const GUTTER_TRACK_SHARE = 3
const TOTAL_SHARE = MAP_COLUMNS.length * NODE_TRACK_SHARE + (MAP_COLUMNS.length - 1) * GUTTER_TRACK_SHARE

/** `grid-template-columns` for the diagram. `minmax(0, …)` keeps a long word from widening its track. */
export const MAP_GRID_TEMPLATE = MAP_COLUMNS.flatMap((_, column) =>
  column === 0
    ? [`minmax(0, ${NODE_TRACK_SHARE}fr)`]
    : [`minmax(0, ${GUTTER_TRACK_SHARE}fr)`, `minmax(0, ${NODE_TRACK_SHARE}fr)`],
).join(' ')

/**
 * Where every node is drawn, from the data alone: jsdom measures nothing, and a
 * layout that is a function of the reply draws the same map every time.
 *
 * Each node goes in its type's column, and within a column the nodes keep the
 * reply's order, one row each. **`placed` lists the nodes column by column, top to
 * bottom**, and the page renders its links in that order, so the tab order is the
 * reading order: down the contributors, then down the documents and meetings, then
 * down the tags (D-132; the design review's audit finding F-06). The reply's own
 * order is walk order, which would jump between columns on every source.
 *
 * A type outside the vocabulary, which the server never sends, is drawn with the
 * sources so that the diagram still holds every node the tables hold.
 *
 * @param {object[]} nodes the reply's nodes, in its order
 * @returns {{placed: {node: object, column: number, row: number}[], rows: number}}
 */
export function layoutColumns(nodes) {
  const columns = MAP_COLUMNS.map(() => [])
  for (const node of nodes) columns[COLUMN_OF_TYPE[node.type] ?? 1].push(node)
  const placed = columns.flatMap((members, column) => members.map((node, row) => ({ node, column, row })))
  return { placed, rows: Math.max(0, ...columns.map((members) => members.length)) }
}

/** The inline grid position of a placed node: position only, never colour. */
export function gridPlace({ column, row }) {
  return { gridColumn: column * 2 + 1, gridRow: row + 1 }
}

/** A fraction of the diagram as a percentage, to three places. */
export function percent(fraction) {
  return `${Number((fraction * 100).toFixed(3))}%`
}

/** The left and right edges of a column of nodes, as fractions of the diagram's width. */
function columnEdges(column) {
  const left = (column * (NODE_TRACK_SHARE + GUTTER_TRACK_SHARE)) / TOTAL_SHARE
  return { left, right: left + NODE_TRACK_SHARE / TOTAL_SHARE }
}

/**
 * The two ends of the line between two placed nodes, as percentages of the
 * diagram: from the facing edge of one node's column to the facing edge of the
 * other's, each at the middle of its row. The rows are equal in height
 * (KnowledgeMap.css), so the middle of row `r` of `rows` is `(r + 0.5) / rows`.
 *
 * @returns {{x1: string, y1: string, x2: string, y2: string}}
 */
export function lineBetween(first, second, rows) {
  const [left, right] = first.column <= second.column ? [first, second] : [second, first]
  const sameColumn = left.column === right.column
  const middle = (place) => percent((place.row + 0.5) / Math.max(rows, 1))
  return {
    x1: percent(columnEdges(left.column).right),
    y1: middle(left),
    x2: percent(sameColumn ? columnEdges(right.column).right : columnEdges(right.column).left),
    y2: middle(right),
  }
}

/* ---- Sorting the two tables ---------------------------------------------- */

/*
 * The sort is the page's own (D-132): the server's order is walk order, and
 * NFR-17 asks for "sortable" rows. It reorders the rows the reply holds and
 * removes none. `sort` is written as `SortHeader` writes it: a field for
 * ascending, the field after `-` for descending, `''` for the reply's order.
 */

/** The Items table's sortable fields, in column order. */
export const ITEM_SORT_FIELDS = { name: 'name', type: 'type', connections: 'connections' }

/** The Relationships table's sortable fields, in column order. */
export const RELATIONSHIP_SORT_FIELDS = { from: 'from', relationship: 'relationship', to: 'to' }

const collator = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true })

/** Two texts in reading order: case and accents ignored, and "passage 2" before "passage 10". */
export function compareText(first, second) {
  return collator.compare(String(first ?? ''), String(second ?? ''))
}

/**
 * A Name cell's order: by the text the cell shows, then by type in words. A tag is
 * shown as its dimension and its name, so "Topic: people" sorts under T, where it
 * reads (D-132's dated note of 15 November 2026, the audit's finding A3).
 */
function compareNodes(first, second) {
  return compareText(displayLabel(first), displayLabel(second)) || compareText(typeText(first), typeText(second))
}

/** A From or To cell's order: by the text the cell shows, which opens with the type. */
function compareTyped(first, second) {
  return compareText(typedLabel(first), typedLabel(second))
}

function countOf(node) {
  return Number.isFinite(node.connection_count) ? node.connection_count : 0
}

const ITEM_COMPARATORS = {
  [ITEM_SORT_FIELDS.name]: compareNodes,
  [ITEM_SORT_FIELDS.type]: (first, second) =>
    compareText(typeText(first), typeText(second)) || compareText(first.label, second.label),
  [ITEM_SORT_FIELDS.connections]: (first, second) => countOf(first) - countOf(second) || compareNodes(first, second),
}

const RELATIONSHIP_COMPARATORS = {
  [RELATIONSHIP_SORT_FIELDS.from]: (first, second) =>
    compareTyped(first.source, second.source) || compareTyped(first.target, second.target),
  [RELATIONSHIP_SORT_FIELDS.relationship]: (first, second) =>
    compareText(relationshipWords(first.relationship), relationshipWords(second.relationship)) ||
    compareTyped(first.source, second.source) ||
    compareTyped(first.target, second.target),
  [RELATIONSHIP_SORT_FIELDS.to]: (first, second) =>
    compareTyped(first.target, second.target) || compareTyped(first.source, second.source),
}

/**
 * `rows` in the order `sort` names. Rows that compare equal keep the reply's order
 * ascending (the sort is stable), and descending is ascending reversed. With no
 * sort, or a field the table does not have, the rows are returned as given.
 */
export function sorted(rows, sort, comparators) {
  if (!sort) return rows
  const descending = sort.startsWith('-')
  const compare = comparators[descending ? sort.slice(1) : sort]
  if (!compare) return rows
  const ascending = [...rows].sort(compare)
  return descending ? ascending.reverse() : ascending
}

/** The Items table's rows: the reply's nodes, in the order `sort` names. */
export function sortItems(nodes, sort) {
  return sorted(nodes, sort, ITEM_COMPARATORS)
}

/** The Relationships table's rows: `relationshipsOf`'s, in the order `sort` names. */
export function sortRelationships(relationships, sort) {
  return sorted(relationships, sort, RELATIONSHIP_COMPARATORS)
}
