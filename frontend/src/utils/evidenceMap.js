/**
 * The knowledge map's second view, claims and the passages they cite (D-138): the
 * view's pure helpers. Its addresses, its two-column layout, the words for a node,
 * what the Claim review says, and its two tables' sorting.
 *
 * Nothing here imports React or fetches, and nothing here decides what the view
 * holds. The claims, the passages, every count, every weight, every date and both
 * truncation fields arrive from `GET /api/knowledge-map/evidence` already scoped to
 * the caller's role, capped and counted by the server (CLAUDE.md §6, invariant 1).
 * These functions arrange and name what was sent. What is derived is what the first
 * view derives: the count line, the two sorts, and where each node is drawn.
 *
 * What the two views do alike is src/utils/knowledgeMap.js's, used from here: a
 * reply's nodes and its selected node, a focus and its query string, the truncation
 * sentence, a node's place on the grid, and the sort itself.
 */
import { EVIDENCE_MAP_NODE_TYPE, EVIDENCE_MAP_RELATIONSHIP, SOURCE_TYPE, TEXT } from '../constants.js'
import {
  FOCUS_ID_PARAM,
  FOCUS_TYPE_PARAM,
  ITEM_SORT_FIELDS,
  KNOWLEDGE_MAP_PATH,
  RELATIONSHIP_SORT_FIELDS,
  SELECTION_KIND,
  compareText,
  itemAddress,
  knowledgeMapQuery,
  listOf,
  nodesOf,
  percent,
  sorted,
} from './knowledgeMap.js'

/* ---- Addresses ----------------------------------------------------------- */

/**
 * The map's two views (D-138). `relationships` is the first: documents, meetings,
 * tags and contributors (D-132). `evidence` is the second: claims and passages.
 */
export const MAP_VIEW = {
  relationships: 'relationships',
  evidence: 'evidence',
}

/** The address parameter that names the view. Only the second view is ever written into it. */
const VIEW_PARAM = 'view'

/**
 * The view an address asks for. `/knowledge-map?view=evidence` is the second view.
 * Every other address, with no `view` or with any other value, is the first view,
 * whose own addresses never carry the parameter.
 *
 * @param {URLSearchParams} params
 */
export function viewFromParams(params) {
  return params.get(VIEW_PARAM) === MAP_VIEW.evidence ? MAP_VIEW.evidence : MAP_VIEW.relationships
}

const NODE_TYPES = Object.values(EVIDENCE_MAP_NODE_TYPE)

/**
 * The selection the second view's address holds, by the first view's rules
 * (`selectionFromParams`) for this view's two types:
 *
 * - neither parameter, or both empty: the overview;
 * - both, with a `focus_type` of `claim` or `passage`: a selection. The identifier
 *   is passed on as written. A claim's is 64 hexadecimal digits and a passage's is
 *   a UUID, and that shape is the server's to judge, as the first view leaves it;
 * - anything else: malformed, which includes a type of the first view's. The page
 *   shows the empty selection and sends no request.
 *
 * @param {URLSearchParams} params
 * @returns {{kind: string, focus: {type: string, id: string}|null}}
 */
export function evidenceSelectionFromParams(params) {
  const type = params.get(FOCUS_TYPE_PARAM) ?? ''
  const id = params.get(FOCUS_ID_PARAM) ?? ''
  if (!type && !id) return { kind: SELECTION_KIND.overview, focus: null }
  if (!type || !id || !NODE_TYPES.includes(type)) return { kind: SELECTION_KIND.malformed, focus: null }
  return { kind: SELECTION_KIND.focus, focus: { type, id } }
}

/**
 * The second view's own address for a focus, or for the whole view with none:
 * `/knowledge-map?view=evidence`, then the two parameters a selection is. Built with
 * `URLSearchParams`, as every address of the map is. The API's query is
 * `knowledgeMapQuery(focus)` alone: `view` is the page's and is never sent.
 *
 * @param {{type: string, id: string}|null} [focus]
 */
export function evidenceAddress(focus = null) {
  const params = new URLSearchParams()
  params.set(VIEW_PARAM, MAP_VIEW.evidence)
  for (const [name, value] of new URLSearchParams(knowledgeMapQuery(focus))) params.set(name, value)
  return `${KNOWLEDGE_MAP_PATH}?${params.toString()}`
}

/**
 * Where the switch to `view` leads: that view with nothing selected. A selection is
 * a node of one view and names nothing in the other, so switching drops it.
 */
export function viewAddress(view) {
  return view === MAP_VIEW.evidence ? evidenceAddress() : KNOWLEDGE_MAP_PATH
}

/** The two source types a passage can come from, each with a page of its own. */
const SOURCE_TYPES = Object.values(SOURCE_TYPE)

/**
 * Where selecting a selected node again goes, or null where there is nothing to open:
 *
 * - a passage: the page of the document or the meeting it is a passage of, by the
 *   first view's own route helper (`itemAddress`), which a document and a meeting
 *   have there under the same two names;
 * - a claim: null. A claim is a statement, with no page of its own (D-138).
 *
 * @param {{type: string, detail: object}} node
 * @returns {string|null}
 */
export function evidenceItemAddress(node) {
  if (node.type !== EVIDENCE_MAP_NODE_TYPE.passage) return null
  const type = node.detail?.source_type
  const itemId = node.detail?.source_id
  if (!itemId || !SOURCE_TYPES.includes(type)) return null
  return itemAddress({ type, item_id: itemId })
}

/* ---- What the reply holds ------------------------------------------------ */

/**
 * Every edge of a reply with its two nodes and its weight beside it, in the reply's
 * order. An edge whose end is not among the nodes is left out here, once, so the
 * diagram and the Relationships table are given one list, as `relationshipsOf`
 * does for the first view.
 *
 * @returns {{key: string, relationship: string, source: object, target: object, weight: number}[]}
 */
export function citationsOf(map) {
  const byId = new Map(nodesOf(map).map((node) => [node.id, node]))
  const rows = []
  for (const edge of listOf(map, 'edges')) {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) continue
    rows.push({
      key: `${edge.source}|${edge.relationship}|${edge.target}`,
      relationship: edge.relationship,
      source,
      target,
      weight: edge.weight,
    })
  }
  return rows
}

/**
 * How many claims and how many passages the reply holds, for the count line.
 * Counted from the nodes on screen and from nothing else, as the first view's is.
 *
 * @returns {Record<string, number>} keyed by node type
 */
export function countEvidence(nodes) {
  const counts = Object.fromEntries(NODE_TYPES.map((type) => [type, 0]))
  for (const node of nodes) {
    if (node.type in counts) counts[node.type] += 1
  }
  return counts
}

/**
 * The nodes at the other end of the selected node's citations, in the reply's
 * order: a claim's passages in this view, or the claims in this view that cite a
 * passage. The edges of the reply that touch it, and no others.
 */
export function citedWith(selected, citations) {
  if (!selected) return []
  return citations.flatMap((row) => {
    if (row.source.id === selected.id) return [row.target]
    if (row.target.id === selected.id) return [row.source]
    return []
  })
}

/**
 * What the Claim review says of a claim, read from its `detail` as sent (D-138):
 *
 * - `singleSource`: `passage_count` is 1. The count is of every passage the reader's
 *   role may see behind the claim, which can be more than this view shows, so it is
 *   read from the reply and never counted from the lines drawn;
 * - `answerCount`: `answer_count`, or null where it did not arrive as a number;
 * - `sameSource`: a single-source claim admitted more than once, of which the
 *   review says that every answer rests on the same passage;
 * - `firstAdmittedAt`, `lastAdmittedAt`: the two days, each a calendar day written
 *   `YYYY-MM-DD` with no time of day, as sent.
 */
export function claimReview(claim) {
  const detail = claim?.detail ?? {}
  const answerCount = Number.isFinite(detail.answer_count) ? detail.answer_count : null
  const singleSource = detail.passage_count === 1
  return {
    singleSource,
    answerCount,
    sameSource: singleSource && answerCount !== null && answerCount > 1,
    firstAdmittedAt: detail.first_admitted_at ?? null,
    lastAdmittedAt: detail.last_admitted_at ?? null,
  }
}

/* ---- Line weight --------------------------------------------------------- */

/** The three weights a line is drawn in. Each is a class in KnowledgeMap.css. */
export const LINE_WEIGHT = {
  light: 'light',
  medium: 'medium',
  heavy: 'heavy',
}

/**
 * Where the two heavier weights begin, in times admitted. The drawing's own steps,
 * with no counterpart on the server: the exact number is the Relationships table's
 * "Times admitted".
 */
const MEDIUM_WEIGHT_FROM = 2
const HEAVY_WEIGHT_FROM = 5

/**
 * The weight a line is drawn in for an edge's `weight`, how often its pairing was
 * admitted: light for 1, medium for 2 to 4, heavy for 5 or more. A weight that did
 * not arrive as a number is drawn light.
 */
export function lineWeight(weight) {
  if (!Number.isFinite(weight)) return LINE_WEIGHT.light
  if (weight >= HEAVY_WEIGHT_FROM) return LINE_WEIGHT.heavy
  if (weight >= MEDIUM_WEIGHT_FROM) return LINE_WEIGHT.medium
  return LINE_WEIGHT.light
}

/* ---- Words --------------------------------------------------------------- */

const TYPE_WORDS = {
  [EVIDENCE_MAP_NODE_TYPE.claim]: TEXT.evidenceTypeClaim,
  [EVIDENCE_MAP_NODE_TYPE.passage]: TEXT.evidenceTypePassage,
}

/** A node type in a word, or the type as sent for one these do not name. */
export function evidenceTypeWord(type) {
  return TYPE_WORDS[type] ?? String(type ?? '')
}

/** What a node is called on screen: its label, as sent. */
export function evidenceLabel(node) {
  return String(node.label ?? '')
}

/**
 * What a From or To cell, or a node listed in the pane, calls a node: its type in
 * a word, then its label ("Passage: Staff Handbook · passage 2"). Nothing else in
 * such a row names the type. The Relationships table sorts on this text.
 */
export function evidenceTypedLabel(node) {
  return TEXT.mapTypedLabel(evidenceTypeWord(node.type), evidenceLabel(node))
}

const RELATIONSHIP_WORDS = {
  [EVIDENCE_MAP_RELATIONSHIP.cites]: TEXT.evidenceRelationshipCites,
}

/** A relationship in words, read "from, relationship, to". */
export function evidenceRelationshipWords(relationship) {
  return RELATIONSHIP_WORDS[relationship] ?? String(relationship ?? '')
}

/**
 * Whether a passage is AI-generated content, which the screen says in words
 * wherever the passage's label is shown (NFR-15). Only the reply's flag decides,
 * `detail.ai_generated`: a passage's label is its source's title and its place in
 * the source, and nothing in it says what the passage is.
 */
export function isAiPassage(node) {
  return node.type === EVIDENCE_MAP_NODE_TYPE.passage && node.detail?.ai_generated === true
}

const SOURCE_TYPE_WORDS = {
  [SOURCE_TYPE.document]: TEXT.mapTypeDocument,
  [SOURCE_TYPE.meeting]: TEXT.mapTypeMeeting,
}

/**
 * A passage's source in words, its type then its title ("Document: Staff
 * Handbook"), or null for a passage whose title did not arrive.
 */
export function sourceLabel(passage) {
  const title = passage.detail?.source_title
  if (!title) return null
  const type = passage.detail?.source_type
  return TEXT.mapTypedLabel(SOURCE_TYPE_WORDS[type] ?? String(type ?? ''), title)
}

/* ---- The column layout --------------------------------------------------- */

/**
 * The two columns, left to right: claims, then passages. Every edge joins a claim
 * to a passage, so every line crosses the one gutter between them. `share` is the
 * column's part of the diagram's width: a claim is a sentence, so its column is
 * the wider.
 */
export const EVIDENCE_COLUMNS = [
  { key: 'claims', heading: TEXT.evidenceColumnClaims, share: 5 },
  { key: 'passages', heading: TEXT.evidenceColumnPassages, share: 4 },
]

const COLUMN_OF_TYPE = {
  [EVIDENCE_MAP_NODE_TYPE.claim]: 0,
  [EVIDENCE_MAP_NODE_TYPE.passage]: 1,
}

/**
 * The gutter the lines cross, as a share of the width. The shares are stated once,
 * here and in `EVIDENCE_COLUMNS`: the grid's tracks and the ends of every line are
 * both worked out from them, so a line always ends on the edge of its node.
 */
const GUTTER_SHARE = 3
const TOTAL_SHARE =
  EVIDENCE_COLUMNS.reduce((total, column) => total + column.share, 0) + (EVIDENCE_COLUMNS.length - 1) * GUTTER_SHARE

/** `grid-template-columns` for the diagram: a column of nodes, the gutter, a column. */
export const EVIDENCE_GRID_TEMPLATE = EVIDENCE_COLUMNS.flatMap((column, index) =>
  index === 0
    ? [`minmax(0, ${column.share}fr)`]
    : [`minmax(0, ${GUTTER_SHARE}fr)`, `minmax(0, ${column.share}fr)`],
).join(' ')

/**
 * Where every node is drawn, from the data alone, by the first view's approach
 * (`layoutColumns`): each node in its type's column, the nodes of a column in the
 * reply's order, one row each. **`placed` lists the nodes column by column, top to
 * bottom**, and the page renders its links in that order, so the tab order is the
 * reading order: down the claims, then down the passages.
 *
 * A type outside the vocabulary, which the server never sends, is drawn with the
 * passages so that the diagram still holds every node the tables hold.
 *
 * @param {object[]} nodes the reply's nodes, in its order
 * @returns {{placed: {node: object, column: number, row: number}[], rows: number}}
 */
export function layoutEvidence(nodes) {
  const columns = EVIDENCE_COLUMNS.map(() => [])
  for (const node of nodes) columns[COLUMN_OF_TYPE[node.type] ?? 1].push(node)
  const placed = columns.flatMap((members, column) => members.map((node, row) => ({ node, column, row })))
  return { placed, rows: Math.max(0, ...columns.map((members) => members.length)) }
}

/** The left and right edges of a column of nodes, as fractions of the diagram's width. */
function columnEdges(column) {
  const before = EVIDENCE_COLUMNS.slice(0, column).reduce((total, earlier) => total + earlier.share + GUTTER_SHARE, 0)
  return { left: before / TOTAL_SHARE, right: (before + EVIDENCE_COLUMNS[column].share) / TOTAL_SHARE }
}

/**
 * The two ends of the line between two placed nodes, as percentages of the diagram:
 * from the facing edge of one node's column to the facing edge of the other's, each
 * at the middle of its row. The rows are equal in height (KnowledgeMap.css), so the
 * middle of row `r` of `rows` is `(r + 0.5) / rows`.
 *
 * @returns {{x1: string, y1: string, x2: string, y2: string}}
 */
export function citationLine(first, second, rows) {
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
 * The sort is the page's own, as the first view's is: it reorders the rows the
 * reply holds and removes none. `sort` is written as `SortHeader` writes it.
 */

/** The Items table's sortable fields, in column order: the first view's three. */
export const EVIDENCE_ITEM_SORT_FIELDS = ITEM_SORT_FIELDS

/** The Relationships table's sortable fields, in column order: the first view's three, then the weight. */
export const CITATION_SORT_FIELDS = { ...RELATIONSHIP_SORT_FIELDS, weight: 'weight' }

/** A Name cell's order: by its label, then by type in words. */
function compareNodes(first, second) {
  return (
    compareText(evidenceLabel(first), evidenceLabel(second)) ||
    compareText(evidenceTypeWord(first.type), evidenceTypeWord(second.type))
  )
}

/** A From or To cell's order: by the text the cell shows, which opens with the type. */
function compareTyped(first, second) {
  return compareText(evidenceTypedLabel(first), evidenceTypedLabel(second))
}

/** A count or a weight as a number to order by: nought where it did not arrive as one. */
function numberOf(value) {
  return Number.isFinite(value) ? value : 0
}

const ITEM_COMPARATORS = {
  [EVIDENCE_ITEM_SORT_FIELDS.name]: compareNodes,
  [EVIDENCE_ITEM_SORT_FIELDS.type]: (first, second) =>
    compareText(evidenceTypeWord(first.type), evidenceTypeWord(second.type)) ||
    compareText(evidenceLabel(first), evidenceLabel(second)),
  [EVIDENCE_ITEM_SORT_FIELDS.connections]: (first, second) =>
    numberOf(first.connection_count) - numberOf(second.connection_count) || compareNodes(first, second),
}

function compareEnds(first, second) {
  return compareTyped(first.source, second.source) || compareTyped(first.target, second.target)
}

const CITATION_COMPARATORS = {
  [CITATION_SORT_FIELDS.from]: compareEnds,
  [CITATION_SORT_FIELDS.relationship]: (first, second) =>
    compareText(evidenceRelationshipWords(first.relationship), evidenceRelationshipWords(second.relationship)) ||
    compareEnds(first, second),
  [CITATION_SORT_FIELDS.to]: (first, second) =>
    compareTyped(first.target, second.target) || compareTyped(first.source, second.source),
  // By the number, never by its digits as text: 2 before 10.
  [CITATION_SORT_FIELDS.weight]: (first, second) =>
    numberOf(first.weight) - numberOf(second.weight) || compareEnds(first, second),
}

/** The Items table's rows: the reply's nodes, in the order `sort` names. */
export function sortEvidenceItems(nodes, sort) {
  return sorted(nodes, sort, ITEM_COMPARATORS)
}

/** The Relationships table's rows: `citationsOf`'s, in the order `sort` names. */
export function sortCitations(citations, sort) {
  return sorted(citations, sort, CITATION_COMPARATORS)
}
