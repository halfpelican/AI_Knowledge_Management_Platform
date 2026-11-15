/**
 * FR-20's knowledge map and NFR-17's table view (NIT3004, D-132): the clauses only
 * the interface can satisfy.
 *
 * FR-20: "A node-link diagram showing documents, meetings, tags, and contributors,
 * with node type distinguished by colour and shape." "Selecting a node reveals its
 * connections; selecting again opens the underlying item." "A tabular equivalent
 * presents the same relationships as sortable rows". NFR-17: "a keyboard-navigable,
 * sortable table view conveying the same nodes and relationships". UC-11 A1:
 * "Selecting a row has the same effect as selecting a node"; A2: "a truncation
 * indicator alongside the map or table"; E1: "an empty map or table rather than an
 * error"; on failure, "No map or table is presented".
 *
 * What is defended here is what the screen shows, keeps, withholds and sends:
 *
 * - the four types, each a different shape with its own fill and its word;
 * - the first selection (the address, the request, the Selected panel) and the
 *   second (what opens), for each type, and the contributor that opens nothing;
 * - a row of either table selecting exactly as a node does;
 * - the served counts, the count line, and the two tables holding exactly the
 *   served nodes and edges;
 * - every column of both tables sorting both ways;
 * - the truncation sentence for each reason, ahead of the skip link and as each
 *   table's description;
 * - loading, failure, 403, the empty map, the empty selection, a 400, and an
 *   address that is not a pair;
 * - addresses built so that any tag name survives, the selected node read from
 *   the reply, and the selection surviving a reload and Back;
 * - where focus goes; untrusted text; the navigation link; the return from sign-in.
 *
 * Usability only, and these tests claim nothing more. Which nodes and edges a role
 * may see, both caps, both truncation fields and every count are the server's, and
 * pytest's (apps/api/tests/test_knowledge_map.py). The fake answers both roles
 * alike: what a server would send each differently plays no part in what is
 * asserted here.
 *
 * What these cannot reach: jsdom applies no stylesheet and lays nothing out, so
 * what is painted where, the reflow at 320 px and what a screen reader says are
 * not asserted here (docs/accessibility.md says who owes them). What is asserted
 * about the drawing is its arithmetic: each node's place on the grid and each
 * line's ends, as the markup states them, and the stylesheet rules that arithmetic
 * relies on, read from disk through tests/stylesheets.js, as the fills are.
 *
 * The whole application is rendered at /knowledge-map with the real routes, guards
 * and auth provider, against a faked API (tests/fakeApi.js). The location is read
 * by a probe in a layout effect and asserted in `waitFor`, as is everything an
 * effect does (tests/dashboard.test.jsx says why).
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { messageForStatus } from '../src/api/client.js'
import {
  KNOWLEDGE_MAP_NODE_TYPE,
  KNOWLEDGE_MAP_RELATIONSHIP,
  KNOWLEDGE_MAP_TRUNCATION_REASON,
  ROLES,
  TEXT,
} from '../src/constants.js'
import { heldResponse, serveApi } from './fakeApi.js'
import { tabTo } from './keyboard.js'
import { colourTokensIn, resolve, rulesMatching } from './stylesheets.js'

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

const ADMINISTRATOR = {
  id: 'user-administrator',
  name: 'Ada Administrator',
  email: 'ada@example.com',
  role: ROLES.administrator,
  created_at: '2026-09-12T10:00:00+10:00',
}

const BOTH_ROLES = [EMPLOYEE, ADMINISTRATOR]

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

const { document: DOCUMENT, meeting: MEETING, tag: TAG, contributor: CONTRIBUTOR } = KNOWLEDGE_MAP_NODE_TYPE
const { tagged: TAGGED, uploaded: UPLOADED, attended: ATTENDED } = KNOWLEDGE_MAP_RELATIONSHIP

/* ---- The map object, in the contract's shape ------------------------------ */

/** A UUID in canonical form, told apart by its last digits. */
function uuid(number) {
  return `0b7c2a54-0000-4000-8000-${String(number).padStart(12, '0')}`
}

/** A node of docs/api-contract.md: the same six keys for every type. */
function node(type, itemId, label, connectionCount, dimension = null) {
  return { id: `${type}:${itemId}`, type, item_id: itemId, label, dimension, connection_count: connectionCount }
}

/** The same node as another view counts it: `connection_count` is per view. */
function counted(original, connectionCount) {
  return { ...original, connection_count: connectionCount }
}

function edge(source, relationship, target) {
  return { source: source.id, target: target.id, relationship }
}

/** The map object: exactly the contract's seven keys. */
function mapObject({ focus = null, nodes = [], edges = [], truncatedBy = null, maximumNodes = 50, maximumDepth = 2 } = {}) {
  return {
    focus: focus ? { type: focus.type, id: focus.item_id } : null,
    nodes,
    edges,
    truncated: truncatedBy !== null,
    truncated_by: truncatedBy,
    maximum_node_count: maximumNodes,
    maximum_traversal_depth: maximumDepth,
  }
}

/** The contract's empty map object. */
const EMPTY_MAP = mapObject()

const LEAVE = node(DOCUMENT, uuid(1), 'Employee Leave Policy 2026', 2)
const BUDGET = node(DOCUMENT, uuid(2), 'Budget Guide', 3)
const SYNC = node(MEETING, uuid(3), 'Q3 Planning Sync', 1)
/** A meeting with no tag and no attendee: a node no relationship row can carry. */
const RETRO = node(MEETING, uuid(4), 'Team Retro', 0)
/** One name in two dimensions: two tags, which must not read as one. */
const TOPIC_PEOPLE = node(TAG, uuid(5), 'people', 2, 'Topic')
const PROJECT_PEOPLE = node(TAG, uuid(6), 'people', 1, 'Project')
const JANE = node(CONTRIBUTOR, uuid(7), 'Jane Doe', 2)
const SAM = node(CONTRIBUTOR, uuid(8), 'Sam Lee', 1)

/**
 * The overview, with its nodes in walk order (a source, its tags, its
 * contributors) and its edges in the contract's order. Not column order, and not
 * an order either table would arrive at by sorting.
 */
const OVERVIEW_NODES = [LEAVE, TOPIC_PEOPLE, JANE, BUDGET, PROJECT_PEOPLE, SAM, SYNC, RETRO]
const OVERVIEW_EDGES = [
  edge(LEAVE, TAGGED, TOPIC_PEOPLE),
  edge(JANE, UPLOADED, LEAVE),
  edge(JANE, ATTENDED, SYNC),
  edge(BUDGET, TAGGED, TOPIC_PEOPLE),
  edge(BUDGET, TAGGED, PROJECT_PEOPLE),
  edge(SAM, UPLOADED, BUDGET),
]
const OVERVIEW = mapObject({ nodes: OVERVIEW_NODES, edges: OVERVIEW_EDGES })

/** The walk from the leave policy: two hops, and something beyond. */
const FOCUS_LEAVE = mapObject({
  focus: LEAVE,
  nodes: [LEAVE, TOPIC_PEOPLE, JANE, counted(BUDGET, 1), SYNC],
  edges: [
    edge(LEAVE, TAGGED, TOPIC_PEOPLE),
    edge(JANE, UPLOADED, LEAVE),
    edge(JANE, ATTENDED, SYNC),
    edge(BUDGET, TAGGED, TOPIC_PEOPLE),
  ],
  truncatedBy: KNOWLEDGE_MAP_TRUNCATION_REASON.depth,
})

const FOCUS_SYNC = mapObject({
  focus: SYNC,
  nodes: [SYNC, JANE, counted(LEAVE, 1)],
  edges: [edge(JANE, UPLOADED, LEAVE), edge(JANE, ATTENDED, SYNC)],
  truncatedBy: KNOWLEDGE_MAP_TRUNCATION_REASON.depth,
})

const FOCUS_TOPIC_PEOPLE = mapObject({
  focus: TOPIC_PEOPLE,
  nodes: [TOPIC_PEOPLE, LEAVE, BUDGET, PROJECT_PEOPLE, counted(JANE, 1), SAM],
  edges: [
    edge(LEAVE, TAGGED, TOPIC_PEOPLE),
    edge(BUDGET, TAGGED, TOPIC_PEOPLE),
    edge(BUDGET, TAGGED, PROJECT_PEOPLE),
    edge(JANE, UPLOADED, LEAVE),
    edge(SAM, UPLOADED, BUDGET),
  ],
  truncatedBy: KNOWLEDGE_MAP_TRUNCATION_REASON.depth,
})

const FOCUS_JANE = mapObject({
  focus: JANE,
  nodes: [JANE, LEAVE, SYNC, counted(TOPIC_PEOPLE, 1)],
  edges: [edge(JANE, UPLOADED, LEAVE), edge(JANE, ATTENDED, SYNC), edge(LEAVE, TAGGED, TOPIC_PEOPLE)],
  truncatedBy: KNOWLEDGE_MAP_TRUNCATION_REASON.depth,
})

/* ---- What the screen should say, worked out here and not by src/ ---------- */

const TYPE_WORD = {
  [DOCUMENT]: TEXT.mapTypeDocument,
  [MEETING]: TEXT.mapTypeMeeting,
  [TAG]: TEXT.mapTypeTag,
  [CONTRIBUTOR]: TEXT.mapTypeContributor,
}

const SELECT_AGAIN = {
  [DOCUMENT]: TEXT.mapSelectAgainDocument,
  [MEETING]: TEXT.mapSelectAgainMeeting,
  [TAG]: TEXT.mapSelectAgainTag,
}

const RELATIONSHIP_WORDS = {
  [TAGGED]: TEXT.mapRelationshipTagged,
  [UPLOADED]: TEXT.mapRelationshipUploaded,
  [ATTENDED]: TEXT.mapRelationshipAttended,
}

/** A node's label on screen: a tag's with its dimension. */
function shown(item) {
  return item.type === TAG ? TEXT.mapTagLabel(item.dimension, item.label) : item.label
}

/** "Document: Employee Leave Policy 2026". */
function typed(item) {
  return TEXT.mapTypedLabel(TYPE_WORD[item.type], shown(item))
}

/** The Items table's Type cell. */
function typeCell(item) {
  return item.type === TAG ? TEXT.mapTagType(item.dimension) : TYPE_WORD[item.type]
}

/** A node's accessible name on the diagram: type, label, "N connections shown". */
function nodeName(item) {
  return `${typed(item)}, ${TEXT.mapConnectionsShown(item.connection_count)}`
}

/** The selected node's name on the diagram: the same, "Selected", and what a second selection does. */
function selectedNodeName(item) {
  return `${nodeName(item)}, ${TEXT.mapSelectedMark}. ${SELECT_AGAIN[item.type]}`
}

/** The address's query for a selection, as `URLSearchParams` writes it. */
function focusSearch(item) {
  return `?focus_type=${item.type}&focus_id=${item.item_id}`
}

function itemsRow(item) {
  return [shown(item), typeCell(item), String(item.connection_count)]
}

function relationshipRow(source, relationship, target) {
  return [typed(source), RELATIONSHIP_WORDS[relationship], typed(target)]
}

/* ---- Serving and rendering ------------------------------------------------ */

/** Every map request a test's table had no reply for. A test that made one fails below. */
const unansweredFocuses = []

afterEach(() => {
  const unanswered = [...unansweredFocuses]
  unansweredFocuses.length = 0
  expect(unanswered, 'a map request this test gave no reply for').toEqual([])
})

/**
 * `GET /api/knowledge-map`, answered from the request's own `focus_id` (`''` for
 * the overview). A reply is a map object, a `{status, body}`, or a function for a
 * held response. Read in lower case, as the server reads a UUID in any spelling.
 */
function mapRoute(replies) {
  return (url) => {
    const id = (url.searchParams.get('focus_id') ?? '').toLowerCase()
    const reply = replies[id]
    if (reply === undefined) {
      unansweredFocuses.push(url.search)
      return { status: 500, body: null }
    }
    if (typeof reply === 'function') return reply(url)
    return 'nodes' in reply ? { body: reply } : reply
  }
}

function serveMap(user, replies, extra = {}) {
  return serveApi({
    'GET /api/auth/me': { body: user },
    'GET /api/knowledge-map': mapRoute(replies),
    ...extra,
  })
}

/** The query string of every map request, in order. */
function mapRequests(answered) {
  return answered.filter((request) => request.path === '/api/knowledge-map').map((request) => request.search)
}

/** The router's location and its navigate function, as the probe below last saw them. */
const probe = { location: null, navigate: null }

function Probe() {
  const location = useLocation()
  const navigate = useNavigate()
  // A layout effect, so both are current before a findBy waiting on the same commit
  // resolves (a passive effect runs a task later).
  useLayoutEffect(() => {
    probe.location = location
    probe.navigate = navigate
  })
  return null
}

function renderMap(path = '/knowledge-map') {
  probe.location = null
  probe.navigate = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <Probe />
    </MemoryRouter>,
  )
  return probe
}

/** Where the router is: the path and the query together. */
function address() {
  return `${probe.location?.pathname}${probe.location?.search}`
}

/* ---- Finding things on the page ------------------------------------------- */

/** The diagram's scroll region, once a map has been drawn. */
function findDiagram() {
  return screen.findByRole('region', { name: TEXT.mapDiagramHeading })
}

function diagram() {
  return screen.getByRole('region', { name: TEXT.mapDiagramHeading })
}

function panel() {
  return screen.getByRole('region', { name: TEXT.mapSelectedHeading })
}

function panelHeading() {
  return screen.getByRole('heading', { level: 2, name: TEXT.mapSelectedHeading })
}

function itemsTable() {
  return screen.getByRole('table', { name: TEXT.mapItemsCaption })
}

function relationshipsTable() {
  return screen.getByRole('table', { name: TEXT.mapRelationshipsCaption })
}

/** Every body row of a table, as the text of its cells. */
function rowsOf(table) {
  return within(table)
    .getAllByRole('row')
    .slice(1)
    .map((row) => [...row.cells].map((cell) => cell.textContent))
}

/** The diagram's link for a node that is not selected. */
function nodeLink(item) {
  return within(diagram()).getByRole('link', { name: nodeName(item) })
}

/** The one thing on the diagram marked as the selection, link or not. */
function selectedOnDiagram() {
  const marked = diagram().querySelectorAll('[aria-current="true"]')
  expect(marked).toHaveLength(1)
  return marked[0]
}

/** The shape drawn inside a node or a legend entry. */
function glyphOf(element) {
  const glyphs = element.querySelectorAll('.knowledge-map__glyph')
  expect(glyphs).toHaveLength(1)
  return glyphs[0]
}

/** What a shape is, apart from its class: its element and, for a polygon, its outline. */
function outlineOf(glyph) {
  return `${glyph.tagName.toLowerCase()} ${glyph.getAttribute('points') ?? ''}`.trim()
}

/** The colour tokens the stylesheets give a rendered element's `fill`. */
function fillTokensOf(element) {
  return rulesMatching(element)
    .flatMap((rule) => rule.declarations)
    .filter((declaration) => declaration.property === 'fill')
    .flatMap((declaration) => colourTokensIn(declaration.value))
}

/** A panel group's links, by the group's heading. */
function groupLinks(heading) {
  const group = within(panel()).getByRole('heading', { level: 3, name: heading }).closest('.knowledge-map__group')
  return within(group)
    .getAllByRole('link')
    .map((link) => link.textContent)
}

/** Where each of a panel group's links leads, by the group's heading. */
function groupHrefs(heading) {
  const group = within(panel()).getByRole('heading', { level: 3, name: heading }).closest('.knowledge-map__group')
  return within(group)
    .getAllByRole('link')
    .map((link) => link.getAttribute('href'))
}

/** The diagram's nodes by label, in the order they are rendered, which is the tab order. */
function diagramOrder() {
  return within(diagram())
    .getAllByRole('listitem')
    .map((cell) => cell.querySelector('.knowledge-map__node-label').textContent)
}

/** Words that would suggest something is kept from the reader. No sentence of the map's may use one. */
const WITHHOLDING = /hidden|withheld|restrict|permi|access|allowed|not shown|omitted|left out|unavailable/i

/**
 * Lets a reply released late, and anything it sets off, finish before a test looks
 * for something that must not have happened (tests/askThread.test.jsx does the
 * same). Inside `act`, so every render and effect queued in the meantime has run.
 */
async function letLateWorkLand() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50))
  })
}

function sortButton(table, label) {
  return within(table).getByRole('button', { name: new RegExp(`^${label}`) })
}

function sortStates(table) {
  return within(table)
    .getAllByRole('columnheader')
    .map((header) => header.getAttribute('aria-sort'))
}

/* ---- Tests ---------------------------------------------------------------- */

describe.each(BOTH_ROLES)('FR-20 knowledge map, as an $role', (user) => {
  describe('FR-20: "node type distinguished by colour and shape"', () => {
    it('draws each of the four types as a different shape with its own class, names its type in a word, and lists the same four in the legend', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      const drawn = {}
      const drawnClass = {}
      for (const item of [LEAVE, SYNC, TOPIC_PEOPLE, JANE]) {
        const link = nodeLink(item)
        // The word: the accessible name begins with the type.
        expect(link.textContent.startsWith(`${TYPE_WORD[item.type]}: `)).toBe(true)
        const glyph = glyphOf(link)
        expect(glyph.classList.contains(`knowledge-map__glyph--${item.type}`)).toBe(true)
        // The shape is decoration for a screen reader, which has the word.
        expect(glyph.closest('svg').getAttribute('aria-hidden')).toBe('true')
        drawn[item.type] = outlineOf(glyph)
        drawnClass[item.type] = glyph.getAttribute('class')
      }
      // A different element, or a different outline, for each: not only a different class.
      expect(drawn[DOCUMENT]).toBe('rect')
      expect(drawn[MEETING]).toBe('circle')
      expect(drawn[TAG]).toMatch(/^polygon /)
      expect(drawn[CONTRIBUTOR]).toMatch(/^polygon /)
      expect(new Set(Object.values(drawn)).size).toBe(4)

      // The words themselves, written out here: each type is called what it is.
      expect(TYPE_WORD).toEqual({
        [DOCUMENT]: 'Document',
        [MEETING]: 'Meeting',
        [TAG]: 'Tag',
        [CONTRIBUTOR]: 'Contributor',
      })

      // The legend: the same four words, each beside the shape the diagram draws for it.
      const legend = screen.getByRole('region', { name: TEXT.mapLegendHeading })
      const entries = within(legend).getAllByRole('listitem')
      expect(entries.map((entry) => entry.textContent)).toEqual(
        Object.values(KNOWLEDGE_MAP_NODE_TYPE).map((type) => TYPE_WORD[type]),
      )
      for (const [index, type] of Object.values(KNOWLEDGE_MAP_NODE_TYPE).entries()) {
        const glyph = glyphOf(entries[index])
        expect(outlineOf(glyph)).toBe(drawn[type])
        // The same class, so the same fill.
        expect(glyph.getAttribute('class')).toBe(drawnClass[type])
      }
      // And what a line means, in words.
      expect(within(legend).getByText(TEXT.mapLegendLine)).toBeTruthy()
    })

    it('gives the four shapes four different fills in the stylesheets, each from one colour token', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      // jsdom applies no stylesheet, so the rules are read from disk and matched
      // against the shapes as rendered: a class with no rule, or four classes
      // sharing a fill, fails here.
      const fills = [LEAVE, SYNC, TOPIC_PEOPLE, JANE].map((item) => fillTokensOf(glyphOf(nodeLink(item))))
      for (const tokens of fills) expect(tokens).toHaveLength(1)
      expect(new Set(fills.map((tokens) => tokens[0])).size).toBe(4)
    })
  })

  describe('FR-20: "Selecting a node reveals its connections; selecting again opens the underlying item"', () => {
    const OPENED = [
      {
        kind: 'a document',
        overviewNode: LEAVE,
        reply: FOCUS_LEAVE,
        groups: [
          [TEXT.mapGroupTags, [TOPIC_PEOPLE]],
          [TEXT.mapGroupUploadedBy, [JANE]],
        ],
        opens: `/documents/${LEAVE.item_id}`,
        // The open action's words, written out here.
        openLabel: 'Open the document',
        destination: {
          [`GET /api/documents/${LEAVE.item_id}`]: { status: 404, body: { detail: 'No Document matches the given query.' } },
        },
      },
      {
        kind: 'a meeting',
        overviewNode: SYNC,
        reply: FOCUS_SYNC,
        groups: [[TEXT.mapGroupAttendedBy, [JANE]]],
        opens: `/meetings/${SYNC.item_id}`,
        openLabel: 'Open the meeting',
        destination: {
          [`GET /api/meetings/${SYNC.item_id}`]: { status: 404, body: { detail: 'No Meeting matches the given query.' } },
          [`GET /api/meetings/${SYNC.item_id}/summary`]: { status: 404, body: { detail: 'No Meeting matches the given query.' } },
        },
      },
      {
        kind: 'a tag',
        overviewNode: TOPIC_PEOPLE,
        reply: FOCUS_TOPIC_PEOPLE,
        groups: [[TEXT.mapGroupTagged, [LEAVE, BUDGET]]],
        opens: '/documents?topic=people',
        openLabel: 'Open documents tagged people',
        destination: { 'GET /api/documents/browse': { status: 204 } },
      },
    ]

    it.each(OPENED)(
      '$kind: the first selection puts it in the address and lists its direct connections; the second opens it',
      async ({ overviewNode, reply, groups, opens, openLabel, destination }) => {
        const answered = serveMap(user, { '': OVERVIEW, [overviewNode.item_id]: reply }, destination)
        renderMap()
        await findDiagram()
        const focused = reply.nodes[0]

        // First selection: a link to the map's own address, holding the focus.
        const first = nodeLink(overviewNode)
        expect(first.getAttribute('href')).toBe(`/knowledge-map${focusSearch(overviewNode)}`)
        expect(first.getAttribute('aria-current')).toBeNull()
        fireEvent.click(first)

        await waitFor(() => expect(address()).toBe(`/knowledge-map${focusSearch(overviewNode)}`))
        await waitFor(() => expect(selectedOnDiagram().textContent).toBe(selectedNodeName(focused)))
        // A second request, for the walk from that node.
        expect(mapRequests(answered)).toEqual(['', focusSearch(overviewNode)])

        // The Selected panel: what it is, its served count, and its direct
        // connections grouped by relationship, each the link that selects that node.
        expect(within(panel()).getByText(overviewNode.label)).toBeTruthy()
        // In words: its type, a tag's with its dimension, and its name.
        expect(panel().querySelector('.knowledge-map__panel-item').textContent).toBe(
          `${typeCell(focused)} ${focused.label}`,
        )
        // And in its type's shape, the one shape the panel draws.
        expect(glyphOf(panel()).getAttribute('class')).toBe(glyphOf(selectedOnDiagram()).getAttribute('class'))
        expect(glyphOf(panel()).classList.contains(`knowledge-map__glyph--${focused.type}`)).toBe(true)
        expect(within(panel()).getByText(TEXT.mapConnectionsShown(focused.connection_count))).toBeTruthy()
        expect(
          within(panel())
            .getAllByRole('heading', { level: 3 })
            .map((heading) => heading.textContent),
        ).toEqual(groups.map(([heading]) => heading))
        for (const [heading, members] of groups) {
          expect(groupLinks(heading)).toEqual(members.map(typed))
          // Each one selects that node: the map's own address, never the item's.
          expect(groupHrefs(heading)).toEqual(members.map((member) => `/knowledge-map${focusSearch(member)}`))
        }

        // Second selection: the same node is now a link to the item itself, on the
        // diagram, in its Items row and as the panel's open action.
        const second = selectedOnDiagram()
        expect(second.tagName).toBe('A')
        expect(second.getAttribute('href')).toBe(opens)
        const row = within(itemsTable()).getByRole('link', { current: true })
        expect(row.getAttribute('href')).toBe(opens)
        expect(row.textContent).toBe(`${shown(focused)}, ${TEXT.mapSelectedMark}. ${SELECT_AGAIN[focused.type]}`)
        expect(within(panel()).getByRole('link', { name: openLabel }).getAttribute('href')).toBe(opens)

        fireEvent.click(second)
        await waitFor(() => expect(address()).toBe(opens))
        await waitFor(() => expect(screen.queryByRole('heading', { level: 1, name: TEXT.mapHeading })).toBeNull())
      },
    )

    it('a contributor: the first selection lists what they uploaded and attended; nothing opens, and the screen says so', async () => {
      const answered = serveMap(user, { '': OVERVIEW, [JANE.item_id]: FOCUS_JANE })
      renderMap()
      await findDiagram()

      fireEvent.click(nodeLink(JANE))

      await waitFor(() => expect(address()).toBe(`/knowledge-map${focusSearch(JANE)}`))
      await waitFor(() =>
        expect(selectedOnDiagram().textContent).toBe(`${nodeName(JANE)}, ${TEXT.mapSelectedMark}`),
      )
      expect(mapRequests(answered)).toEqual(['', focusSearch(JANE)])
      expect(panel().querySelector('.knowledge-map__panel-item').textContent).toBe(`${TEXT.mapTypeContributor} ${JANE.label}`)
      expect(glyphOf(panel()).classList.contains(`knowledge-map__glyph--${CONTRIBUTOR}`)).toBe(true)
      expect(groupLinks(TEXT.mapGroupUploaded)).toEqual([typed(LEAVE)])
      expect(groupLinks(TEXT.mapGroupAttended)).toEqual([typed(SYNC)])
      expect(groupHrefs(TEXT.mapGroupUploaded)).toEqual([`/knowledge-map${focusSearch(LEAVE)}`])
      expect(groupHrefs(TEXT.mapGroupAttended)).toEqual([`/knowledge-map${focusSearch(SYNC)}`])

      // Not a link anywhere: there is nothing for a second selection to open.
      expect(selectedOnDiagram().tagName).toBe('SPAN')
      const page = screen.getByRole('main')
      const links = within(page).getAllByRole('link')
      expect(links.filter((link) => link.textContent.includes(JANE.label))).toEqual([])
      expect(links.filter((link) => /^Open/.test(link.textContent))).toEqual([])
      // The Items row carries the same mark, as text.
      const row = within(itemsTable()).getByRole('rowheader', { name: new RegExp(`^${JANE.label}`) })
      expect(row.querySelector('[aria-current="true"]').tagName).toBe('SPAN')
      // And the panel says why.
      expect(within(panel()).getByText(TEXT.mapContributorNoPage)).toBeTruthy()

      // "Show the whole map" clears the selection.
      const whole = within(panel()).getByRole('link', { name: TEXT.mapShowWhole })
      expect(whole.getAttribute('href')).toBe('/knowledge-map')
      fireEvent.click(whole)
      await waitFor(() => expect(address()).toBe('/knowledge-map'))
      await waitFor(() => expect(within(panel()).getByText(TEXT.mapSelectedNone)).toBeTruthy())
      expect(diagram().querySelectorAll('[aria-current]')).toHaveLength(0)
      expect(mapRequests(answered)).toEqual(['', focusSearch(JANE), ''])
    })

    it('says how to select while nothing is selected, and marks no node', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      expect(within(panel()).getByText(TEXT.mapSelectedNone)).toBeTruthy()
      expect(within(panel()).queryByRole('link')).toBeNull()
      expect(screen.getByRole('main').querySelectorAll('[aria-current="true"]')).toHaveLength(0)
    })
  })

  describe('UC-11 A1: "Selecting a row has the same effect as selecting a node"', () => {
    const ORIGINS = [
      { from: 'the node', find: () => nodeLink(LEAVE) },
      { from: 'its Items row', find: () => within(itemsTable()).getByRole('link', { name: shown(LEAVE) }) },
      {
        from: 'the To end of a Relationships row',
        // The document is the To end of "Jane Doe uploaded …", and a From end elsewhere.
        find: () =>
          within(relationshipsTable())
            .getAllByRole('link', { name: typed(LEAVE) })
            .find((link) => link.closest('td') !== null),
      },
    ]

    it.each(ORIGINS)('selecting the document from $from: the same address, the same request, the same selection', async ({ find }) => {
      const answered = serveMap(user, { '': OVERVIEW, [LEAVE.item_id]: FOCUS_LEAVE })
      renderMap()
      await findDiagram()

      const link = find()
      expect(link.getAttribute('href')).toBe(`/knowledge-map${focusSearch(LEAVE)}`)
      fireEvent.click(link)

      await waitFor(() => expect(address()).toBe(`/knowledge-map${focusSearch(LEAVE)}`))
      await waitFor(() => expect(selectedOnDiagram().textContent).toBe(selectedNodeName(LEAVE)))
      expect(mapRequests(answered)).toEqual(['', focusSearch(LEAVE)])
      expect(groupLinks(TEXT.mapGroupTags)).toEqual([typed(TOPIC_PEOPLE)])
      expect(groupLinks(TEXT.mapGroupUploadedBy)).toEqual([typed(JANE)])
      // Every later control for the selected node now opens it, whichever table it is in.
      expect(within(itemsTable()).getByRole('link', { current: true }).getAttribute('href')).toBe(
        `/documents/${LEAVE.item_id}`,
      )
      for (const end of within(relationshipsTable()).getAllByRole('link', { current: true })) {
        expect(end.getAttribute('href')).toBe(`/documents/${LEAVE.item_id}`)
      }
    })

    it('selecting from the From end of a Relationships row selects that node', async () => {
      const answered = serveMap(user, { '': OVERVIEW, [JANE.item_id]: FOCUS_JANE })
      renderMap()
      await findDiagram()

      // Jane is the From end of two rows; either selects her.
      const ends = within(relationshipsTable()).getAllByRole('link', { name: typed(JANE) })
      expect(ends).toHaveLength(2)
      expect(ends[1].closest('th')).not.toBeNull()
      fireEvent.click(ends[1])

      await waitFor(() => expect(address()).toBe(`/knowledge-map${focusSearch(JANE)}`))
      await waitFor(() =>
        expect(selectedOnDiagram().textContent).toBe(`${nodeName(JANE)}, ${TEXT.mapSelectedMark}`),
      )
      expect(mapRequests(answered)).toEqual(['', focusSearch(JANE)])
    })

    /** Each type, the walk from it, and what a second selection opens: null where nothing does. */
    const SELECTIONS = [
      {
        kind: 'a document',
        item: LEAVE,
        reply: FOCUS_LEAVE,
        opens: `/documents/${LEAVE.item_id}`,
        destination: {
          [`GET /api/documents/${LEAVE.item_id}`]: { status: 404, body: { detail: 'No Document matches the given query.' } },
        },
      },
      {
        kind: 'a meeting',
        item: SYNC,
        reply: FOCUS_SYNC,
        opens: `/meetings/${SYNC.item_id}`,
        destination: {
          [`GET /api/meetings/${SYNC.item_id}`]: { status: 404, body: { detail: 'No Meeting matches the given query.' } },
          [`GET /api/meetings/${SYNC.item_id}/summary`]: { status: 404, body: { detail: 'No Meeting matches the given query.' } },
        },
      },
      {
        kind: 'a tag',
        item: TOPIC_PEOPLE,
        reply: FOCUS_TOPIC_PEOPLE,
        opens: '/documents?topic=people',
        destination: { 'GET /api/documents/browse': { status: 204 } },
      },
      { kind: 'a contributor', item: JANE, reply: FOCUS_JANE, opens: null, destination: {} },
    ]
    /** The two tables, and what a node's control is called in each. */
    const TABLES = [
      { table: 'an Items row', inTable: itemsTable, called: shown },
      { table: 'a Relationships row', inTable: relationshipsTable, called: typed },
    ]

    it.each(SELECTIONS.flatMap((selection) => TABLES.map((table) => ({ ...selection, ...table }))))(
      '$kind from $table: the first selection, focus on the Selected panel, and the second selection from the same table',
      async ({ item, reply, opens, destination, inTable, called }) => {
        const answered = serveMap(user, { '': OVERVIEW, [item.item_id]: reply }, destination)
        renderMap()
        await findDiagram()
        const focused = reply.nodes[0]

        // First selection: every control this table has for the node leads to the
        // map's own address with the node as the focus.
        const controls = within(inTable()).getAllByRole('link', { name: called(item) })
        for (const control of controls) {
          expect(control.getAttribute('href')).toBe(`/knowledge-map${focusSearch(item)}`)
          expect(control.getAttribute('aria-current')).toBeNull()
        }
        controls[0].focus()
        fireEvent.click(controls[0])

        await waitFor(() => expect(address()).toBe(`/knowledge-map${focusSearch(item)}`))
        await waitFor(() =>
          expect(selectedOnDiagram().textContent).toBe(
            opens ? selectedNodeName(focused) : `${nodeName(focused)}, ${TEXT.mapSelectedMark}`,
          ),
        )
        expect(mapRequests(answered)).toEqual(['', focusSearch(item)])
        expect(within(panel()).getByText(item.label)).toBeTruthy()
        // The row that was followed is gone with the overview: focus is on the panel's heading.
        await waitFor(() => expect(document.activeElement).toBe(panelHeading()))

        // Second selection, from the same table: every control it has for the
        // selected node is marked, and opens the item, or is text where nothing opens.
        const marked = [...inTable().querySelectorAll('[aria-current="true"]')]
        expect(marked.length).toBeGreaterThan(0)
        for (const control of marked) expect(control.textContent.startsWith(called(focused))).toBe(true)
        if (opens === null) {
          for (const control of marked) expect(control.tagName).toBe('SPAN')
          expect(
            within(inTable())
              .getAllByRole('link')
              .filter((link) => link.textContent.includes(item.label)),
          ).toEqual([])
          return
        }
        for (const control of marked) {
          expect(control.tagName).toBe('A')
          expect(control.getAttribute('href')).toBe(opens)
        }
        fireEvent.click(marked[0])
        await waitFor(() => expect(address()).toBe(opens))
        await waitFor(() => expect(screen.queryByRole('heading', { level: 1, name: TEXT.mapHeading })).toBeNull())
      },
    )

    it('selecting a connection listed in the Selected panel selects that node, and focus returns to the panel’s heading', async () => {
      const answered = serveMap(user, { '': OVERVIEW, [LEAVE.item_id]: FOCUS_LEAVE, [JANE.item_id]: FOCUS_JANE })
      renderMap()
      await findDiagram()
      fireEvent.click(nodeLink(LEAVE))
      await waitFor(() => expect(selectedOnDiagram().textContent).toBe(selectedNodeName(LEAVE)))
      await waitFor(() => expect(document.activeElement).toBe(panelHeading()))

      // The person who uploaded the policy, as the panel lists them.
      const connection = within(panel()).getByRole('link', { name: typed(JANE) })
      expect(connection.getAttribute('href')).toBe(`/knowledge-map${focusSearch(JANE)}`)
      connection.focus()
      fireEvent.click(connection)

      await waitFor(() => expect(address()).toBe(`/knowledge-map${focusSearch(JANE)}`))
      await waitFor(() =>
        expect(selectedOnDiagram().textContent).toBe(`${nodeName(JANE)}, ${TEXT.mapSelectedMark}`),
      )
      expect(mapRequests(answered)).toEqual(['', focusSearch(LEAVE), focusSearch(JANE)])
      expect(panel().querySelector('.knowledge-map__panel-item').textContent).toBe(`${TEXT.mapTypeContributor} ${JANE.label}`)
      // The link that was followed went with the last view: focus is on the new panel's heading.
      await waitFor(() => expect(document.activeElement).toBe(panelHeading()))
    })
  })

  describe('UC-11: "Connection counts shown against each node", and the count line', () => {
    it('shows the count the server sent on each node and in each Items row, and recounts nothing from the edges', async () => {
      // Counts no page could work out from the two edges served: 7, 4 and 9.
      const policy = counted(LEAVE, 7)
      const jane = counted(JANE, 4)
      const people = counted(TOPIC_PEOPLE, 9)
      serveMap(user, {
        '': mapObject({ nodes: [policy, people, jane, RETRO], edges: [edge(policy, TAGGED, people), edge(jane, UPLOADED, policy)] }),
      })
      renderMap()
      await findDiagram()

      for (const item of [policy, people, jane, RETRO]) {
        expect(within(nodeLink(item)).getByText(TEXT.mapConnectionsShown(item.connection_count))).toBeTruthy()
      }
      expect(TEXT.mapConnectionsShown(1)).toMatch(/shown$/)
      expect(rowsOf(itemsTable())).toEqual([policy, people, jane, RETRO].map(itemsRow))
      expect(rowsOf(itemsTable()).map((row) => row[2])).toEqual(['7', '9', '4', '0'])
    })

    it('shows the served count in the Selected panel, not a count of the lines drawn to the selection', async () => {
      // Two edges touch the policy, and the server says 7.
      const policy = counted(LEAVE, 7)
      const people = counted(TOPIC_PEOPLE, 5)
      const jane = counted(JANE, 4)
      serveMap(user, {
        [LEAVE.item_id]: mapObject({
          focus: policy,
          nodes: [policy, people, jane],
          edges: [edge(policy, TAGGED, people), edge(jane, UPLOADED, policy)],
        }),
      })
      renderMap(`/knowledge-map${focusSearch(LEAVE)}`)
      await findDiagram()

      expect(selectedOnDiagram().textContent).toBe(selectedNodeName(policy))
      expect(panel().querySelector('.knowledge-map__panel-count').textContent).toBe(TEXT.mapConnectionsShown(7))
      expect(panel().textContent).not.toContain(TEXT.mapConnectionsShown(2))
      expect(rowsOf(itemsTable()).map((row) => row[2])).toEqual(['7', '5', '4'])
    })

    const ALPHA = node(TAG, uuid(21), 'alpha', 0, 'Topic')
    const BETA = node(TAG, uuid(22), 'beta', 0, 'Process')
    const GAMMA = node(TAG, uuid(23), 'gamma', 0, 'Project')
    const KIM = node(CONTRIBUTOR, uuid(24), 'Kim Park', 0)
    const LOU = node(CONTRIBUTOR, uuid(25), 'Lou Diaz', 0)
    const HANDBOOK = node(DOCUMENT, uuid(26), 'Staff Handbook', 0)

    it.each([
      {
        what: 'a view with no contributor',
        nodes: [LEAVE, SYNC, RETRO, ALPHA, BETA, GAMMA],
        line: '1 document · 2 meetings · 3 tags · 0 contributors shown',
      },
      {
        // A different number of each type, so no figure can stand in for another.
        what: 'a view with unequal numbers per type',
        nodes: [JANE, LEAVE, ALPHA, SAM, BUDGET, BETA, KIM, HANDBOOK, LOU, SYNC],
        line: '3 documents · 1 meeting · 2 tags · 4 contributors shown',
      },
    ])('counts the line from the served nodes, by type, and states no total: $what', async ({ nodes, line }) => {
      // No edge at all: a line counted from the edges would read nothing but noughts.
      serveMap(user, {
        '': mapObject({ nodes, truncatedBy: KNOWLEDGE_MAP_TRUNCATION_REASON.nodeCount, maximumNodes: nodes.length }),
      })
      renderMap()
      await findDiagram()

      const shownLine = screen.getByText(line)
      expect(shownLine.getAttribute('role')).toBe('status')
      // A partial view, and still nothing like "6 of 40".
      expect(screen.getByRole('main').textContent).not.toMatch(/\d+ of \d+/)
    })

    it('counts the line again for each reply: the overview’s, then the selection’s', async () => {
      serveMap(user, { '': OVERVIEW, [SYNC.item_id]: FOCUS_SYNC })
      renderMap()
      await findDiagram()
      expect(screen.getByText('2 documents · 2 meetings · 2 tags · 2 contributors shown').getAttribute('role')).toBe('status')

      fireEvent.click(nodeLink(SYNC))

      await waitFor(() => expect(selectedOnDiagram().textContent).toBe(selectedNodeName(SYNC)))
      // The walk from the meeting holds the meeting, one person and one document.
      expect(screen.getByText('1 document · 1 meeting · 0 tags · 1 contributor shown').getAttribute('role')).toBe('status')
      expect(screen.queryByText('2 documents · 2 meetings · 2 tags · 2 contributors shown')).toBeNull()
    })
  })

  describe('NFR-17: "a … table view conveying the same nodes and relationships"', () => {
    it('holds exactly the served nodes and edges in the two tables and on the diagram, the unconnected meeting included', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      // One row per node, in the reply's order until a column is sorted.
      expect(rowsOf(itemsTable())).toEqual(OVERVIEW_NODES.map(itemsRow))
      expect(rowsOf(itemsTable())).toContainEqual([RETRO.label, TEXT.mapTypeMeeting, '0'])
      // One row per edge, read "from, relationship, to".
      expect(rowsOf(relationshipsTable())).toEqual([
        relationshipRow(LEAVE, TAGGED, TOPIC_PEOPLE),
        relationshipRow(JANE, UPLOADED, LEAVE),
        relationshipRow(JANE, ATTENDED, SYNC),
        relationshipRow(BUDGET, TAGGED, TOPIC_PEOPLE),
        relationshipRow(BUDGET, TAGGED, PROJECT_PEOPLE),
        relationshipRow(SAM, UPLOADED, BUDGET),
      ])
      // The relationship in the words D-132 gives it, written out here: a person
      // "uploaded" a document and "attended" a meeting; a source "is tagged".
      expect(rowsOf(relationshipsTable()).map((row) => row[1])).toEqual([
        'is tagged',
        'uploaded',
        'attended',
        'is tagged',
        'is tagged',
        'uploaded',
      ])
      // The diagram draws the same: a node each, a line each.
      expect(within(diagram()).getAllByRole('listitem')).toHaveLength(OVERVIEW_NODES.length)
      expect(diagram().querySelectorAll('svg.knowledge-map__lines line')).toHaveLength(OVERVIEW_EDGES.length)

      // Each table is in its own named, focusable region, with its columns as headers.
      for (const [table, heading, columns] of [
        [itemsTable(), TEXT.mapItemsHeading, [TEXT.mapItemsColumnName, TEXT.mapItemsColumnType, TEXT.mapItemsColumnConnections]],
        [
          relationshipsTable(),
          TEXT.mapRelationshipsHeading,
          [TEXT.mapRelationshipsColumnFrom, TEXT.mapRelationshipsColumnRelationship, TEXT.mapRelationshipsColumnTo],
        ],
      ]) {
        const region = table.closest('[role="region"]')
        expect(region.getAttribute('tabindex')).toBe('0')
        expect(within(screen.getByRole('main')).getByRole('region', { name: heading })).toBe(region)
        expect(within(table).getAllByRole('columnheader').map((header) => header.textContent)).toEqual(columns)
      }
    })

    it('reads a tag with its dimension everywhere, so two tags with one name in two dimensions read differently', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      expect(TOPIC_PEOPLE.label).toBe(PROJECT_PEOPLE.label)
      // On the diagram: two nodes, two names.
      expect(nodeLink(TOPIC_PEOPLE)).not.toBe(nodeLink(PROJECT_PEOPLE))
      expect(within(nodeLink(TOPIC_PEOPLE)).getByText('Topic: people')).toBeTruthy()
      expect(within(nodeLink(PROJECT_PEOPLE)).getByText('Project: people')).toBeTruthy()
      // In the Items table: the name and the type both say which.
      expect(rowsOf(itemsTable())).toContainEqual(['Topic: people', 'Tag, Topic', '2'])
      expect(rowsOf(itemsTable())).toContainEqual(['Project: people', 'Tag, Project', '1'])
      // In the Relationships table: each end that is a tag names its dimension.
      const ends = rowsOf(relationshipsTable()).map((row) => row[2])
      expect(ends).toContain('Tag: Topic: people')
      expect(ends).toContain('Tag: Project: people')
    })

    it('says so in a sentence, not an empty table, when the items shown have no line between them', async () => {
      serveMap(user, { '': mapObject({ nodes: [SYNC, RETRO].map((item) => counted(item, 0)) }) })
      renderMap()
      await findDiagram()

      expect(rowsOf(itemsTable())).toEqual([
        [SYNC.label, TEXT.mapTypeMeeting, '0'],
        [RETRO.label, TEXT.mapTypeMeeting, '0'],
      ])
      expect(screen.getByText(TEXT.mapNoRelationships)).toBeTruthy()
      expect(screen.queryByRole('table', { name: TEXT.mapRelationshipsCaption })).toBeNull()
    })

    it('draws no line and no row for an edge whose end is not among the served nodes, and makes no node of it', async () => {
      // Not a reply the contract allows: both ends of every edge are in `nodes`.
      // The page still shows only the nodes it was sent, and the diagram and the
      // Relationships table still hold the same edges as each other.
      const absent = node(TAG, uuid(51), 'payroll', 1, 'Topic')
      const policy = counted(LEAVE, 1)
      const jane = counted(JANE, 1)
      serveMap(user, {
        '': mapObject({ nodes: [policy, jane], edges: [edge(jane, UPLOADED, policy), edge(policy, TAGGED, absent)] }),
      })
      renderMap()
      await findDiagram()

      expect(rowsOf(itemsTable())).toEqual([policy, jane].map(itemsRow))
      expect(rowsOf(relationshipsTable())).toEqual([relationshipRow(jane, UPLOADED, policy)])
      expect(within(diagram()).getAllByRole('listitem')).toHaveLength(2)
      expect(diagram().querySelectorAll('svg.knowledge-map__lines line')).toHaveLength(1)
      const main = screen.getByRole('main')
      expect(main.textContent).not.toContain(absent.label)
      expect(main.innerHTML).not.toContain(absent.item_id)
      expect(screen.getByText('1 document · 0 meetings · 0 tags · 1 contributor shown')).toBeTruthy()
    })
  })

  describe('NFR-17: "sortable"', () => {
    /** Reaches the heading's button by Tab, as a keyboard user does, and activates it. */
    function pressSort(table, label) {
      const button = sortButton(table, label)
      // A native button, which Enter and Space activate without any handler of
      // ours. jsdom does not turn a key into a click, so the activation itself is
      // a click on the element the keyboard reached.
      expect(tabTo(button)).toBe(button)
      expect(button.tagName).toBe('BUTTON')
      expect(button.getAttribute('type')).toBe('button')
      fireEvent.click(button)
      // The control that was pressed keeps the focus, so it can be pressed again.
      expect(document.activeElement).toBe(sortButton(table, label))
    }

    const ITEM_SORTS = [
      {
        column: TEXT.mapItemsColumnName,
        index: 0,
        // By the text the cell shows: a tag reads "Project: people" or "Topic: people",
        // so the two tags named "people" sort under P and under T, where they read,
        // and not side by side under "people" (the audit of 15 November 2026, A3).
        ascending: [BUDGET, LEAVE, JANE, PROJECT_PEOPLE, SYNC, SAM, RETRO, TOPIC_PEOPLE],
      },
      {
        column: TEXT.mapItemsColumnType,
        index: 1,
        ascending: [JANE, SAM, BUDGET, LEAVE, SYNC, RETRO, PROJECT_PEOPLE, TOPIC_PEOPLE],
      },
      {
        column: TEXT.mapItemsColumnConnections,
        index: 2,
        // 0; then the three with 1; then the three with 2; then 3. By label within a count.
        ascending: [RETRO, PROJECT_PEOPLE, SYNC, SAM, LEAVE, JANE, TOPIC_PEOPLE, BUDGET],
      },
    ]

    it.each(ITEM_SORTS)('sorts the Items table by $column, ascending then descending, with aria-sort', async ({ column, index, ascending }) => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()
      const table = itemsTable()
      const expected = (direction) => [0, 1, 2].map((position) => (position === index ? direction : null))

      // The reply's order, and no column claiming a sort, until one is pressed.
      expect(sortStates(table)).toEqual([null, null, null])
      expect(rowsOf(table)).toEqual(OVERVIEW_NODES.map(itemsRow))
      const drawnBefore = diagramOrder()
      const relationshipsBefore = rowsOf(relationshipsTable())

      pressSort(table, column)
      expect(sortStates(table)).toEqual(expected('ascending'))
      expect(rowsOf(table)).toEqual(ascending.map(itemsRow))
      expect(diagramOrder()).toEqual(drawnBefore)

      pressSort(table, column)
      expect(sortStates(table)).toEqual(expected('descending'))
      expect(rowsOf(table)).toEqual([...ascending].reverse().map(itemsRow))

      // Sorting reorders the rows and removes none, and it leaves the other table,
      // the diagram and the address as they were: the sort is the table's own, and
      // the order of the diagram's nodes, which is the tab order, is the reply's.
      expect(rowsOf(table)).toHaveLength(OVERVIEW_NODES.length)
      expect(sortStates(relationshipsTable())).toEqual([null, null, null])
      expect(rowsOf(relationshipsTable())).toEqual(relationshipsBefore)
      expect(diagramOrder()).toEqual(drawnBefore)
      expect(address()).toBe('/knowledge-map')
    })

    it('orders two items that show the same name by their type', async () => {
      // A meeting and a document with one title. The Name column cannot tell them
      // apart, so the type decides ("Document" before "Meeting"), and not the order
      // the reply happens to carry, which is the meeting first. The overview above
      // has no two items showing one name since a tag's name is shown with its
      // dimension (the audit of 15 November 2026, A3), so this is its own map.
      const meeting = node(MEETING, uuid(41), 'Budget Review', 0)
      const paper = node(DOCUMENT, uuid(42), 'Budget Review', 0)
      serveMap(user, { '': mapObject({ nodes: [meeting, paper] }) })
      renderMap()
      await findDiagram()
      const table = itemsTable()
      expect(rowsOf(table)).toEqual([meeting, paper].map(itemsRow))

      pressSort(table, TEXT.mapItemsColumnName)
      expect(sortStates(table)).toEqual(['ascending', null, null])
      expect(rowsOf(table)).toEqual([paper, meeting].map(itemsRow))

      pressSort(table, TEXT.mapItemsColumnName)
      expect(sortStates(table)).toEqual(['descending', null, null])
      expect(rowsOf(table)).toEqual([meeting, paper].map(itemsRow))
    })

    const E1 = relationshipRow(LEAVE, TAGGED, TOPIC_PEOPLE)
    const E2 = relationshipRow(JANE, UPLOADED, LEAVE)
    const E3 = relationshipRow(JANE, ATTENDED, SYNC)
    const E4 = relationshipRow(BUDGET, TAGGED, TOPIC_PEOPLE)
    const E5 = relationshipRow(BUDGET, TAGGED, PROJECT_PEOPLE)
    const E6 = relationshipRow(SAM, UPLOADED, BUDGET)

    const RELATIONSHIP_SORTS = [
      // By the text the From cell shows, which opens with the type ("Contributor: Jane
      // Doe" before "Document: Budget Guide"), then by the To cell's.
      { column: TEXT.mapRelationshipsColumnFrom, index: 0, ascending: [E2, E3, E6, E5, E4, E1] },
      // "attended", "is tagged", "uploaded".
      { column: TEXT.mapRelationshipsColumnRelationship, index: 1, ascending: [E3, E5, E4, E1, E2, E6] },
      { column: TEXT.mapRelationshipsColumnTo, index: 2, ascending: [E6, E2, E3, E5, E4, E1] },
    ]

    it.each(RELATIONSHIP_SORTS)(
      'sorts the Relationships table by $column, ascending then descending, with aria-sort',
      async ({ column, index, ascending }) => {
        serveMap(user, { '': OVERVIEW })
        renderMap()
        await findDiagram()
        const table = relationshipsTable()
        const expected = (direction) => [0, 1, 2].map((position) => (position === index ? direction : null))

        expect(sortStates(table)).toEqual([null, null, null])
        expect(rowsOf(table)).toEqual([E1, E2, E3, E4, E5, E6])
        const drawnBefore = diagramOrder()

        pressSort(table, column)
        expect(sortStates(table)).toEqual(expected('ascending'))
        expect(rowsOf(table)).toEqual(ascending)

        pressSort(table, column)
        expect(sortStates(table)).toEqual(expected('descending'))
        expect(rowsOf(table)).toEqual([...ascending].reverse())

        // The other table and the diagram are as they were.
        expect(sortStates(itemsTable())).toEqual([null, null, null])
        expect(rowsOf(itemsTable())).toEqual(OVERVIEW_NODES.map(itemsRow))
        expect(diagramOrder()).toEqual(drawnBefore)
      },
    )

    it('keeps each table’s sort its own: sorting one leaves the other sorted as it was', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      pressSort(itemsTable(), TEXT.mapItemsColumnName)
      pressSort(relationshipsTable(), TEXT.mapRelationshipsColumnTo)
      pressSort(relationshipsTable(), TEXT.mapRelationshipsColumnTo)

      // Items is still sorted by Name, as it was before the other table was touched.
      expect(sortStates(itemsTable())).toEqual(['ascending', null, null])
      expect(rowsOf(itemsTable())).toEqual(ITEM_SORTS[0].ascending.map(itemsRow))
      expect(sortStates(relationshipsTable())).toEqual([null, null, 'descending'])
      expect(rowsOf(relationshipsTable())).toEqual([...RELATIONSHIP_SORTS[2].ascending].reverse())

      // And the other way about: sorting Items again leaves Relationships as it is.
      pressSort(itemsTable(), TEXT.mapItemsColumnConnections)
      expect(sortStates(itemsTable())).toEqual([null, null, 'ascending'])
      expect(sortStates(relationshipsTable())).toEqual([null, null, 'descending'])
      expect(rowsOf(relationshipsTable())).toEqual([...RELATIONSHIP_SORTS[2].ascending].reverse())
    })

    it('moves the sort to another column when that one is pressed, and names the direction in words', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()
      const table = itemsTable()

      pressSort(table, TEXT.mapItemsColumnName)
      pressSort(table, TEXT.mapItemsColumnType)

      expect(sortStates(table)).toEqual([null, 'ascending', null])
      expect(
        within(table).getByRole('button', {
          name: new RegExp(`^${TEXT.mapItemsColumnType}\\s*, ${TEXT.repositorySortedAscending}$`),
        }),
      ).toBeTruthy()
    })

    it('keeps the selection in the address and drops the sort when the page is left and returned to', async () => {
      serveMap(
        user,
        { '': OVERVIEW, [LEAVE.item_id]: FOCUS_LEAVE },
        { [`GET /api/documents/${LEAVE.item_id}`]: { status: 404, body: { detail: 'No Document matches the given query.' } } },
      )
      renderMap()
      await findDiagram()
      pressSort(itemsTable(), TEXT.mapItemsColumnName)
      expect(sortStates(itemsTable())).toEqual(['ascending', null, null])

      // A selection is another view of the same page: the sort is page state and holds.
      fireEvent.click(nodeLink(LEAVE))
      await waitFor(() => expect(selectedOnDiagram().textContent).toBe(selectedNodeName(LEAVE)))
      expect(sortStates(itemsTable())).toEqual(['ascending', null, null])
      expect(address()).toBe(`/knowledge-map${focusSearch(LEAVE)}`)

      // Leaving the page and coming Back: the selection is in the address and
      // survives; the sort was the page's own and starts again.
      fireEvent.click(selectedOnDiagram())
      await waitFor(() => expect(address()).toBe(`/documents/${LEAVE.item_id}`))
      await waitFor(() => expect(screen.queryByRole('heading', { level: 1, name: TEXT.mapHeading })).toBeNull())
      await act(async () => probe.navigate(-1))
      await findDiagram()
      expect(selectedOnDiagram().textContent).toBe(selectedNodeName(LEAVE))
      expect(sortStates(itemsTable())).toEqual([null, null, null])
      expect(rowsOf(itemsTable())).toEqual(FOCUS_LEAVE.nodes.map((item) => (item.id === LEAVE.id ? [`${shown(item)}, ${TEXT.mapSelectedMark}. ${SELECT_AGAIN[item.type]}`, typeCell(item), String(item.connection_count)] : itemsRow(item))))
    })
  })

  describe('FR-20: "a partial view is not presented as complete"', () => {
    const PARTIAL = [
      {
        kind: 'the overview cut by the node count',
        path: '/knowledge-map',
        key: '',
        reply: mapObject({
          nodes: OVERVIEW_NODES,
          edges: OVERVIEW_EDGES,
          truncatedBy: KNOWLEDGE_MAP_TRUNCATION_REASON.nodeCount,
          maximumNodes: 37,
          maximumDepth: 3,
        }),
        sentence: TEXT.mapTruncatedOverview(37),
        number: '37 items',
      },
      {
        kind: 'a selection cut by the node count',
        path: `/knowledge-map${focusSearch(LEAVE)}`,
        key: LEAVE.item_id,
        reply: { ...FOCUS_LEAVE, truncated_by: KNOWLEDGE_MAP_TRUNCATION_REASON.nodeCount, maximum_node_count: 37, maximum_traversal_depth: 3 },
        sentence: TEXT.mapTruncatedSelection(37),
        number: '37 items',
      },
      {
        kind: 'a selection cut by depth',
        path: `/knowledge-map${focusSearch(LEAVE)}`,
        key: LEAVE.item_id,
        reply: { ...FOCUS_LEAVE, maximum_node_count: 37, maximum_traversal_depth: 3 },
        sentence: TEXT.mapTruncatedDepth(3),
        number: '3 steps',
      },
    ]

    it.each(PARTIAL)(
      '$kind: says so before the skip link, worded from the reply’s own maximum, and as each table’s description',
      async ({ path, key, reply, sentence, number }) => {
        serveMap(user, { [key]: reply })
        renderMap(path)
        await findDiagram()

        // The three sentences differ, and each carries the number the reply sent
        // (37 or 3), which is neither of the server's real caps.
        expect(new Set(PARTIAL.map((partial) => partial.sentence)).size).toBe(3)
        expect(sentence).toContain(number)
        const notice = screen.getByText(sentence)
        expect(notice.closest('[role="status"]')).not.toBeNull()
        // The notice says that sentence and nothing more, and nothing on the page
        // is worded as though something were kept from the reader.
        expect(notice.closest('[role="status"]').textContent).toBe(sentence)
        expect(screen.getByRole('main').textContent).not.toMatch(WITHHOLDING)

        // Ahead of the skip link, so a reader who skips to the tables has passed it.
        const skip = screen.getByRole('link', { name: TEXT.mapSkipToTables })
        expect(notice.compareDocumentPosition(skip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
        expect(notice.compareDocumentPosition(diagram()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

        // And each table is described by the same sentence.
        expect(screen.getByRole('table', { name: TEXT.mapItemsCaption, description: sentence })).toBeTruthy()
        expect(screen.getByRole('table', { name: TEXT.mapRelationshipsCaption, description: sentence })).toBeTruthy()
      },
    )

    it('says nothing of the kind about a whole view, and describes neither table', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      const main = screen.getByRole('main')
      for (const partial of PARTIAL) expect(main.textContent).not.toContain(partial.sentence)
      expect(main.textContent).not.toContain(TEXT.mapTruncatedOther)
      expect(itemsTable().getAttribute('aria-describedby')).toBeNull()
      expect(relationshipsTable().getAttribute('aria-describedby')).toBeNull()
    })

    it('still says a view is partial when the reply’s reason is not one it knows', async () => {
      serveMap(user, { '': { ...OVERVIEW, truncated: true, truncated_by: 'something_new' } })
      renderMap()
      await findDiagram()

      expect(screen.getByText(TEXT.mapTruncatedOther)).toBeTruthy()
      expect(screen.getByRole('table', { name: TEXT.mapItemsCaption, description: TEXT.mapTruncatedOther })).toBeTruthy()
    })

    it('words no sentence so as to suggest that anything is kept from the reader', () => {
      const sentences = [
        TEXT.mapTruncatedOverview(50),
        TEXT.mapTruncatedSelection(50),
        TEXT.mapTruncatedDepth(2),
        TEXT.mapTruncatedOther,
        TEXT.mapEmpty,
        TEXT.mapEmptySelection,
        TEXT.mapSelectedNone,
        TEXT.mapNoRelationships,
        TEXT.mapIntro,
      ]
      for (const sentence of sentences) {
        expect(sentence).not.toMatch(WITHHOLDING)
      }
    })
  })

  describe('the states: UC-11 "No map or table is presented" on failure, and E1’s empty map', () => {
    function nothingDrawn() {
      expect(screen.queryByRole('region', { name: TEXT.mapDiagramHeading })).toBeNull()
      expect(screen.queryByRole('table')).toBeNull()
      expect(screen.queryByRole('region', { name: TEXT.mapSelectedHeading })).toBeNull()
      expect(screen.queryByRole('link', { name: TEXT.mapSkipToTables })).toBeNull()
    }

    it('says it is loading, with neither diagram nor table, until the reply lands', async () => {
      const held = heldResponse()
      serveMap(user, { '': held.route })
      renderMap()

      const loading = await screen.findByText(TEXT.mapLoading)
      expect(loading.getAttribute('role')).toBe('status')
      nothingDrawn()

      await act(async () => held.release({ body: OVERVIEW }))

      await findDiagram()
      expect(screen.queryByText(TEXT.mapLoading)).toBeNull()
      expect(rowsOf(itemsTable())).toHaveLength(OVERVIEW_NODES.length)
    })

    it('shows a failure as an error with the client’s own words and "Try again", which reads again', async () => {
      let attempt = 0
      const answered = serveMap(user, {
        '': () => {
          attempt += 1
          return attempt === 1 ? { status: 500, body: { detail: 'Traceback (most recent call last): boom' } } : { body: OVERVIEW }
        },
      })
      renderMap()

      const title = await screen.findByText(TEXT.mapLoadFailed)
      const alert = title.closest('[role="alert"]')
      expect(alert.textContent).toContain(messageForStatus(500))
      expect(screen.getByRole('main').textContent).not.toMatch(/Traceback|boom/)
      nothingDrawn()

      fireEvent.click(screen.getByRole('button', { name: TEXT.uploadRetry }))

      await findDiagram()
      expect(screen.queryByText(TEXT.mapLoadFailed)).toBeNull()
      expect(mapRequests(answered)).toEqual(['', ''])
    })

    it('shows nothing of the overview while a selection is loading, nor after it has failed', async () => {
      const held = heldResponse()
      const answered = serveMap(user, { '': OVERVIEW, [LEAVE.item_id]: held.route })
      renderMap()
      await findDiagram()

      fireEvent.click(nodeLink(LEAVE))

      // In flight: the earlier reply is not shown under the new address.
      await screen.findByText(TEXT.mapLoading)
      expect(address()).toBe(`/knowledge-map${focusSearch(LEAVE)}`)
      nothingDrawn()

      await act(async () => held.release({ status: 500, body: null }))

      // Failed: still no map and no table from the overview.
      await screen.findByText(TEXT.mapLoadFailed)
      nothingDrawn()
      expect(screen.getByRole('main').textContent).not.toContain(BUDGET.label)
      expect(mapRequests(answered)).toEqual(['', focusSearch(LEAVE)])
      // The link that was followed is gone, so focus is put on the page heading.
      await waitFor(() =>
        expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: TEXT.mapHeading })),
      )
    })

    it.each([
      { late: 'a map', reply: { body: FOCUS_LEAVE } },
      { late: 'a failure', reply: { status: 500, body: null } },
    ])(
      'ignores $late that lands after the address has moved on, and keeps the reply for the address it is at',
      async ({ reply }) => {
        const held = heldResponse()
        const answered = serveMap(user, { [LEAVE.item_id]: held.route, '': OVERVIEW })
        renderMap(`/knowledge-map${focusSearch(LEAVE)}`)
        await screen.findByText(TEXT.mapLoading)

        // The address moves on to the whole map while the selection's reply is on
        // its way. The fake's fetch does not honour an abort, as a reply already
        // on the wire does not: the earlier reply still arrives.
        await act(async () => probe.navigate('/knowledge-map'))
        await findDiagram()
        expect(mapRequests(answered)).toEqual([focusSearch(LEAVE), ''])

        held.release(reply)
        await letLateWorkLand()

        // The whole map is still what is shown, under its own address: the late
        // reply is neither drawn in its place nor allowed to unseat it.
        expect(address()).toBe('/knowledge-map')
        expect(screen.queryByText(TEXT.mapLoading)).toBeNull()
        expect(screen.queryByText(TEXT.mapLoadFailed)).toBeNull()
        expect(rowsOf(itemsTable())).toEqual(OVERVIEW_NODES.map(itemsRow))
        expect(screen.getByRole('main').querySelectorAll('[aria-current="true"]')).toHaveLength(0)
        expect(within(panel()).getByText(TEXT.mapSelectedNone)).toBeTruthy()
        expect(screen.getByText('2 documents · 2 meetings · 2 tags · 2 contributors shown')).toBeTruthy()
        expect(mapRequests(answered)).toEqual([focusSearch(LEAVE), ''])
      },
    )

    it('shows a 403 as the not-permitted notice alone, saying nothing about a map', async () => {
      const answered = serveMap(user, { '': { status: 403, body: { detail: 'You do not have permission to perform this action.' } } })
      renderMap()

      const title = await screen.findByText(TEXT.notPermittedTitle)
      expect(title.closest('[role="alert"]').textContent).toContain(TEXT.notPermitted)
      nothingDrawn()
      expect(screen.queryByRole('button', { name: TEXT.uploadRetry })).toBeNull()
      expect(screen.queryByText(TEXT.mapEmpty)).toBeNull()
      expect(screen.queryByText(TEXT.mapEmptySelection)).toBeNull()
      expect(mapRequests(answered)).toEqual([''])
    })

    it('shows the empty map as one sentence, with no diagram, no table and no error', async () => {
      serveMap(user, { '': EMPTY_MAP })
      renderMap()

      const sentence = await screen.findByText(TEXT.mapEmpty)
      expect(sentence.closest('[role="status"]')).not.toBeNull()
      expect(screen.queryByRole('alert')).toBeNull()
      nothingDrawn()
      expect(screen.queryByText(TEXT.mapEmptySelection)).toBeNull()
    })

    it('shows the empty selection, with the way back to the whole map, for a focus the reply holds nothing for', async () => {
      const unknown = uuid(99)
      const path = `/knowledge-map?focus_type=document&focus_id=${unknown}`
      const answered = serveMap(user, { [unknown]: EMPTY_MAP, '': OVERVIEW })
      renderMap(path)

      const sentence = await screen.findByText(TEXT.mapEmptySelection)
      expect(sentence.closest('[role="status"]')).not.toBeNull()
      expect(screen.queryByRole('alert')).toBeNull()
      expect(screen.queryByText(TEXT.mapEmpty)).toBeNull()
      nothingDrawn()

      const whole = screen.getByRole('link', { name: TEXT.mapShowWhole })
      expect(whole.getAttribute('href')).toBe('/knowledge-map')
      fireEvent.click(whole)

      await findDiagram()
      expect(address()).toBe('/knowledge-map')
      expect(mapRequests(answered)).toEqual([`?focus_type=document&focus_id=${unknown}`, ''])
    })

    it('shows a 400 as the same empty selection, with no retry and none of the server’s words', async () => {
      const answered = serveMap(user, {
        'not-a-uuid': { status: 400, body: { focus_id: ['Must be a valid UUID.'] } },
      })
      renderMap('/knowledge-map?focus_type=document&focus_id=not-a-uuid')

      await screen.findByText(TEXT.mapEmptySelection)
      expect(screen.getByRole('link', { name: TEXT.mapShowWhole }).getAttribute('href')).toBe('/knowledge-map')
      expect(screen.queryByRole('button', { name: TEXT.uploadRetry })).toBeNull()
      expect(screen.queryByRole('alert')).toBeNull()
      expect(screen.getByRole('main').textContent).not.toContain('Must be a valid UUID')
      nothingDrawn()
      expect(mapRequests(answered)).toEqual(['?focus_type=document&focus_id=not-a-uuid'])
    })

    it.each([
      { what: 'a type without an identifier', search: '?focus_type=document' },
      { what: 'an identifier without a type', search: `?focus_id=${uuid(1)}` },
      { what: 'a type with an empty identifier', search: '?focus_type=document&focus_id=' },
      { what: 'a type outside the vocabulary', search: `?focus_type=folder&focus_id=${uuid(1)}` },
    ])('sends no request for $what, and shows the empty selection', async ({ search }) => {
      // No map route is served at all: a request would be refused and fail the test.
      const answered = serveApi({ 'GET /api/auth/me': { body: user } })
      renderMap(`/knowledge-map${search}`)

      await screen.findByText(TEXT.mapEmptySelection)
      expect(screen.getByRole('link', { name: TEXT.mapShowWhole }).getAttribute('href')).toBe('/knowledge-map')
      expect(screen.queryByText(TEXT.mapLoading)).toBeNull()
      nothingDrawn()
      // Settled: nothing was sent, then or a moment later.
      await act(async () => {})
      expect(answered.map((request) => request.path)).toEqual(['/api/auth/me'])
    })

    it('reads two empty parameters as no selection, and asks for the overview', async () => {
      const answered = serveMap(user, { '': OVERVIEW })
      renderMap('/knowledge-map?focus_type=&focus_id=')

      await findDiagram()
      expect(mapRequests(answered)).toEqual([''])
      expect(within(panel()).getByText(TEXT.mapSelectedNone)).toBeTruthy()
    })
  })

  describe('addresses, and the selection that lives in one', () => {
    it('opens the right filter for a tag named "r&d #1 100%", and adds no filter of its own', async () => {
      const awkward = node(TAG, uuid(9), 'r&d #1 100%', 1, 'Topic')
      const answered = serveMap(
        user,
        { [awkward.item_id]: mapObject({ focus: awkward, nodes: [awkward, counted(LEAVE, 1)], edges: [edge(LEAVE, TAGGED, awkward)] }) },
        { 'GET /api/documents/browse': { status: 204 } },
      )
      renderMap(`/knowledge-map${focusSearch(awkward)}`)
      await findDiagram()

      const open = within(panel()).getByRole('link', { name: TEXT.mapOpenTag(awkward.label) })
      const target = new URL(open.getAttribute('href'), 'http://localhost')
      expect(target.pathname).toBe('/documents')
      expect([...target.searchParams.entries()]).toEqual([['topic', 'r&d #1 100%']])
      expect(target.hash).toBe('')
      expect(selectedOnDiagram().getAttribute('href')).toBe(open.getAttribute('href'))

      fireEvent.click(open)

      // The repository asks the API for exactly that topic, and shows it as the filter.
      await waitFor(() => expect(probe.location?.pathname).toBe('/documents'))
      await screen.findByText('r&d #1 100%')
      const browse = answered.filter((request) => request.path === '/api/documents/browse')
      expect(browse).toHaveLength(1)
      expect([...new URLSearchParams(browse[0].search).entries()]).toEqual([['topic', 'r&d #1 100%']])
    })

    it.each(['Project', 'Process', 'Topic'])('opens the repository filtered by %s for a tag in that dimension', async (dimension) => {
      const tag = node(TAG, uuid(10), 'payroll', 1, dimension)
      serveMap(user, {
        [tag.item_id]: mapObject({ focus: tag, nodes: [tag, counted(LEAVE, 1)], edges: [edge(LEAVE, TAGGED, tag)] }),
      })
      renderMap(`/knowledge-map${focusSearch(tag)}`)
      await findDiagram()

      // The filter is the tag's own dimension, in the repository's lower-case spelling.
      const opens = `/documents?${dimension.toLowerCase()}=payroll`
      expect(selectedOnDiagram().getAttribute('href')).toBe(opens)
      expect(within(itemsTable()).getByRole('link', { current: true }).getAttribute('href')).toBe(opens)
      expect(within(panel()).getByRole('link', { name: TEXT.mapOpenTag(tag.label) }).getAttribute('href')).toBe(opens)
    })

    it('sends an identifier typed into the address to the server as one encoded value, and adds no parameter of its own', async () => {
      // Whatever the address holds as `focus_id` is the server's to judge, and it
      // reaches the server as that one value: not as a second `focus_type`, and not
      // cut short at a `#`.
      const written = 'x&focus_type=tag#1 100%'
      const answered = serveMap(user, { [written]: { status: 400, body: { focus_id: ['Must be a valid UUID.'] } } })
      renderMap(`/knowledge-map?focus_type=document&focus_id=${encodeURIComponent(written)}`)

      await screen.findByText(TEXT.mapEmptySelection)
      const requests = mapRequests(answered)
      expect(requests).toHaveLength(1)
      expect([...new URLSearchParams(requests[0]).entries()]).toEqual([
        ['focus_type', 'document'],
        ['focus_id', written],
      ])
    })

    it('marks the node the reply’s focus names when the address spells the identifier in upper case', async () => {
      const upper = LEAVE.item_id.toUpperCase()
      expect(upper).not.toBe(LEAVE.item_id)
      const answered = serveMap(user, { [LEAVE.item_id]: FOCUS_LEAVE })
      renderMap(`/knowledge-map?focus_type=document&focus_id=${upper}`)
      await findDiagram()

      // The reply's focus is canonical; the address is not. The node is still marked.
      expect(selectedOnDiagram().textContent).toBe(selectedNodeName(LEAVE))
      expect(selectedOnDiagram().getAttribute('href')).toBe(`/documents/${LEAVE.item_id}`)
      expect(within(panel()).getByText(LEAVE.label)).toBeTruthy()
      // The identifier went to the server as written; its spelling is the server's to read.
      expect(mapRequests(answered)).toEqual([`?focus_type=document&focus_id=${upper}`])
    })

    it('marks nothing when the reply names no focus, whatever the address says', async () => {
      // Not a reply the contract allows with nodes in it; the page still must not
      // mark a node on its address's word alone.
      serveMap(user, { [LEAVE.item_id]: { ...FOCUS_LEAVE, focus: null } })
      renderMap(`/knowledge-map${focusSearch(LEAVE)}`)
      await findDiagram()

      expect(screen.getByRole('main').querySelectorAll('[aria-current="true"]')).toHaveLength(0)
      expect(within(panel()).getByText(TEXT.mapSelectedNone)).toBeTruthy()
    })

    it('marks the node of the type the reply’s focus names, where a node of another type has the same identifier', async () => {
      // A node is its type and its identifier together, which is what the
      // contract's `id` is. A document and a tag come from different tables, and
      // nothing but chance makes their identifiers differ.
      const shared = uuid(60)
      const policy = node(DOCUMENT, shared, 'Employee Leave Policy 2026', 1)
      const tag = node(TAG, shared, 'people', 1, 'Topic')
      serveMap(user, { [shared]: mapObject({ focus: tag, nodes: [policy, tag], edges: [edge(policy, TAGGED, tag)] }) })
      renderMap(`/knowledge-map${focusSearch(tag)}`)
      await findDiagram()

      // The tag, and only the tag: the document that shares its identifier still selects itself.
      expect(selectedOnDiagram().textContent).toBe(selectedNodeName(tag))
      expect(panel().querySelector('.knowledge-map__panel-item').textContent).toBe('Tag, Topic people')
      expect(nodeLink(policy).getAttribute('href')).toBe(`/knowledge-map${focusSearch(policy)}`)
      expect(itemsTable().querySelectorAll('[aria-current="true"]')).toHaveLength(1)
      expect(groupLinks(TEXT.mapGroupTagged)).toEqual([typed(policy)])
    })

    it('restores the selection from the address on a reload', async () => {
      const answered = serveMap(user, { [LEAVE.item_id]: FOCUS_LEAVE })
      renderMap(`/knowledge-map${focusSearch(LEAVE)}`)
      await findDiagram()

      expect(selectedOnDiagram().textContent).toBe(selectedNodeName(LEAVE))
      expect(groupLinks(TEXT.mapGroupTags)).toEqual([typed(TOPIC_PEOPLE)])
      expect(mapRequests(answered)).toEqual([focusSearch(LEAVE)])
    })

    it('restores the selection when the item it opened is left with Back', async () => {
      const answered = serveMap(
        user,
        { '': OVERVIEW, [LEAVE.item_id]: FOCUS_LEAVE },
        { [`GET /api/documents/${LEAVE.item_id}`]: { status: 404, body: { detail: 'No Document matches the given query.' } } },
      )
      renderMap()
      await findDiagram()
      fireEvent.click(nodeLink(LEAVE))
      await waitFor(() => expect(selectedOnDiagram().textContent).toBe(selectedNodeName(LEAVE)))

      fireEvent.click(selectedOnDiagram())
      await waitFor(() => expect(address()).toBe(`/documents/${LEAVE.item_id}`))
      await waitFor(() => expect(screen.queryByRole('heading', { level: 1, name: TEXT.mapHeading })).toBeNull())

      await act(async () => probe.navigate(-1))

      await waitFor(() => expect(address()).toBe(`/knowledge-map${focusSearch(LEAVE)}`))
      await findDiagram()
      expect(selectedOnDiagram().textContent).toBe(selectedNodeName(LEAVE))
      // Read again for the same selection: nothing was kept from before.
      expect(mapRequests(answered)).toEqual(['', focusSearch(LEAVE), focusSearch(LEAVE)])
    })
  })

  describe('where focus goes', () => {
    it('moves focus to the Selected panel’s heading once a selection made on the page has loaded', async () => {
      serveMap(user, { '': OVERVIEW, [LEAVE.item_id]: FOCUS_LEAVE })
      renderMap()
      await findDiagram()
      const link = nodeLink(LEAVE)
      link.focus()

      fireEvent.click(link)

      await waitFor(() => expect(selectedOnDiagram().textContent).toBe(selectedNodeName(LEAVE)))
      await waitFor(() => expect(document.activeElement).toBe(panelHeading()))
      // A heading that takes focus by script without becoming a tab stop.
      expect(panelHeading().getAttribute('tabindex')).toBe('-1')
    })

    it('leaves focus alone when the page is opened at a selection nobody made on it', async () => {
      serveMap(user, { [LEAVE.item_id]: FOCUS_LEAVE })
      renderMap(`/knowledge-map${focusSearch(LEAVE)}`)
      await findDiagram()
      await act(async () => {})

      expect(document.activeElement).not.toBe(panelHeading())
    })

    it('"Skip to the table view" is a link ahead of the diagram that lands on the table view', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      const skip = screen.getByRole('link', { name: TEXT.mapSkipToTables })
      const heading = screen.getByRole('heading', { level: 2, name: TEXT.mapTablesHeading })
      // A native link to the heading, ahead of the legend and the diagram.
      expect(skip.tagName).toBe('A')
      expect(skip.getAttribute('href')).toBe(`#${heading.id}`)
      const legend = screen.getByRole('region', { name: TEXT.mapLegendHeading })
      expect(skip.compareDocumentPosition(legend) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      expect(skip.compareDocumentPosition(diagram()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

      skip.focus()
      fireEvent.click(skip)

      // Focus is on the table view's heading, which heads the section both tables are in.
      expect(document.activeElement).toBe(heading)
      const section = heading.closest('section')
      expect(section.contains(itemsTable())).toBe(true)
      expect(section.contains(relationshipsTable())).toBe(true)
      // The selection's address is left as it was: no fragment, no history entry.
      expect(address()).toBe('/knowledge-map')
      expect(probe.location.hash).toBe('')
    })
  })

  describe('text from a document, a tag or a person is rendered as text', () => {
    it('renders markup in a title, a tag name and a person’s name as the characters it is, and creates no element from it', async () => {
      const hostile = (word) => `<img src="x" onerror="window.__mapInjected = true"><b>${word}</b>`
      const title = node(DOCUMENT, uuid(31), hostile('title'), 2)
      const tag = node(TAG, uuid(32), hostile('tag'), 1, 'Topic')
      const person = node(CONTRIBUTOR, uuid(33), hostile('person'), 1)
      serveMap(user, {
        [title.item_id]: mapObject({
          focus: title,
          nodes: [title, tag, person],
          edges: [edge(title, TAGGED, tag), edge(person, UPLOADED, title)],
        }),
      })
      renderMap(`/knowledge-map${focusSearch(title)}`)
      await findDiagram()

      const main = screen.getByRole('main')
      expect(main.querySelectorAll('img, b')).toHaveLength(0)
      expect(window.__mapInjected).toBeUndefined()
      // Each appears as written: on the diagram, in both tables and in the panel.
      expect(rowsOf(itemsTable()).map((row) => row[0])).toEqual([
        `${title.label}, ${TEXT.mapSelectedMark}. ${TEXT.mapSelectAgainDocument}`,
        TEXT.mapTagLabel('Topic', tag.label),
        person.label,
      ])
      expect(within(nodeLink(tag)).getByText(TEXT.mapTagLabel('Topic', tag.label))).toBeTruthy()
      expect(within(nodeLink(person)).getByText(person.label)).toBeTruthy()
      expect(panel().querySelector('.knowledge-map__panel-name').textContent).toBe(title.label)
      expect(groupLinks(TEXT.mapGroupTags)).toEqual([typed(tag)])
      expect(groupLinks(TEXT.mapGroupUploadedBy)).toEqual([typed(person)])
    })

    it('renders markup in a selected tag’s name as characters in the panel and in its open action, which still opens that tag', async () => {
      const name = '<img src="x" onerror="window.__mapInjected = true"><b>tag</b>'
      const tag = node(TAG, uuid(34), name, 1, 'Topic')
      serveMap(user, {
        [tag.item_id]: mapObject({ focus: tag, nodes: [tag, counted(LEAVE, 1)], edges: [edge(LEAVE, TAGGED, tag)] }),
      })
      renderMap(`/knowledge-map${focusSearch(tag)}`)
      await findDiagram()

      const main = screen.getByRole('main')
      expect(main.querySelectorAll('img, b')).toHaveLength(0)
      expect(window.__mapInjected).toBeUndefined()
      expect(panel().querySelector('.knowledge-map__panel-name').textContent).toBe(name)
      expect(selectedOnDiagram().textContent).toBe(selectedNodeName(tag))
      // The open action: the name as text in its words, and as one encoded value in its address.
      const open = within(panel()).getByRole('link', { name: TEXT.mapOpenTag(name) })
      expect(open.children).toHaveLength(0)
      const target = new URL(open.getAttribute('href'), 'http://localhost')
      expect(target.pathname).toBe('/documents')
      expect([...target.searchParams.entries()]).toEqual([['topic', name]])
    })

    it('draws two contributors with one name as two nodes and two rows, each selecting its own', async () => {
      const first = node(CONTRIBUTOR, uuid(41), 'Alex Kim', 1)
      const second = node(CONTRIBUTOR, uuid(42), 'Alex Kim', 1)
      serveMap(user, {
        '': mapObject({
          nodes: [LEAVE, first, BUDGET, second].map((item) => counted(item, 1)),
          edges: [edge(first, UPLOADED, LEAVE), edge(second, UPLOADED, BUDGET)],
        }),
      })
      renderMap()
      await findDiagram()

      const nodes = within(diagram()).getAllByRole('link', { name: nodeName(first) })
      expect(nodes.map((link) => link.getAttribute('href'))).toEqual([
        `/knowledge-map${focusSearch(first)}`,
        `/knowledge-map${focusSearch(second)}`,
      ])
      expect(rowsOf(itemsTable()).filter((row) => row[0] === 'Alex Kim')).toHaveLength(2)
      expect(rowsOf(relationshipsTable()).filter((row) => row[0] === typed(first))).toHaveLength(2)
    })
  })

  describe('the diagram is drawn from the data, with nothing measured (D-132)', () => {
    /** An element's inline declarations, by property. Inline style here is position only. */
    function inlineStyle(element) {
      return Object.fromEntries(
        (element.getAttribute('style') ?? '')
          .split(';')
          .map((declaration) => declaration.split(':').map((part) => part.trim()))
          .filter(([property]) => property),
      )
    }

    /** What the stylesheets declare for a rendered element, by property (the last rule wins). */
    function declared(element) {
      return Object.fromEntries(
        rulesMatching(element)
          .flatMap((rule) => rule.declarations)
          .map((declaration) => [declaration.property, declaration.value]),
      )
    }

    it('puts each node in its type’s column, one row each in the reply’s order, and ends every line on the facing edges of its two columns at the middle of its two rows', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      // The grid: a column of nodes, a gutter, a column, a gutter, a column, as
      // shares of the width. The headings and the nodes are on the same tracks.
      const list = within(diagram()).getByRole('list')
      const template = inlineStyle(list)['grid-template-columns']
      expect(template).toBe('minmax(0, 7fr) minmax(0, 3fr) minmax(0, 7fr) minmax(0, 3fr) minmax(0, 7fr)')
      expect(inlineStyle(diagram().querySelector('.knowledge-map__columns'))['grid-template-columns']).toBe(template)
      expect(
        [...diagram().querySelectorAll('.knowledge-map__column-heading')].map((heading) => [
          heading.textContent,
          inlineStyle(heading)['grid-column'],
        ]),
      ).toEqual([
        [TEXT.mapColumnContributors, '1'],
        [TEXT.mapColumnSources, '3'],
        [TEXT.mapColumnTags, '5'],
      ])
      // Where each track begins and ends, worked out from that template alone.
      const shares = [...template.matchAll(/minmax\(0, (\d+)fr\)/g)].map((match) => Number(match[1]))
      const total = shares.reduce((sum, share) => sum + share, 0)
      const edges = shares.reduce((list_, share) => [...list_, list_.at(-1) + share], [0]).map((edge) => `${Number(((edge / total) * 100).toFixed(3))}%`)
      expect(edges).toEqual(['0%', '25.926%', '37.037%', '62.963%', '74.074%', '100%'])

      // The nodes, in the order they are rendered: down the contributors, down
      // the documents and meetings, down the tags; within a column, the reply's
      // order. Each is one cell of the grid.
      expect(
        within(list)
          .getAllByRole('listitem')
          .map((cell) => [
            cell.querySelector('.knowledge-map__node-label').textContent,
            inlineStyle(cell)['grid-column'],
            inlineStyle(cell)['grid-row'],
          ]),
      ).toEqual([
        [JANE.label, '1', '1'],
        [SAM.label, '1', '2'],
        [LEAVE.label, '3', '1'],
        [BUDGET.label, '3', '2'],
        [SYNC.label, '3', '3'],
        [RETRO.label, '3', '4'],
        [shown(TOPIC_PEOPLE), '5', '1'],
        [shown(PROJECT_PEOPLE), '5', '2'],
      ])

      // The lines, one per edge and in the edges' order. Four rows, so the middle
      // of each is 12.5%, 37.5%, 62.5% and 87.5% of the height. A line leaves the
      // right edge of the left node's column and arrives at the left edge of the
      // right node's.
      const [contributorsEnd, sourcesStart, sourcesEnd, tagsStart] = edges.slice(1, 5)
      expect(
        [...diagram().querySelectorAll('svg.knowledge-map__lines line')].map((line) =>
          ['x1', 'y1', 'x2', 'y2'].map((name) => line.getAttribute(name)),
        ),
      ).toEqual([
        [sourcesEnd, '12.5%', tagsStart, '12.5%'], // the leave policy is tagged Topic: people
        [contributorsEnd, '12.5%', sourcesStart, '12.5%'], // Jane uploaded the leave policy
        [contributorsEnd, '12.5%', sourcesStart, '62.5%'], // Jane attended the planning sync
        [sourcesEnd, '37.5%', tagsStart, '12.5%'], // the budget guide is tagged Topic: people
        [sourcesEnd, '37.5%', tagsStart, '37.5%'], // the budget guide is tagged Project: people
        [contributorsEnd, '37.5%', sourcesStart, '37.5%'], // Sam uploaded the budget guide
      ])

      // What that arithmetic relies on in the stylesheet: rows of equal height
      // with no gap between them, and a lines layer that fills the grid of nodes.
      const grid = declared(list)
      expect(grid.display).toBe('grid')
      expect(grid['grid-auto-rows']).toBe('1fr')
      expect(Object.keys(grid).filter((property) => /(^|-)gap$/.test(property))).toEqual([])
      const layer = declared(diagram().querySelector('svg.knowledge-map__lines'))
      expect(layer.position).toBe('absolute')
      expect(layer.inset).toBe('0')
      expect(declared(diagram().querySelector('.knowledge-map__canvas')).position).toBe('relative')
      expect(list.parentElement).toBe(diagram().querySelector('.knowledge-map__canvas'))
    })

    it('draws the selected node’s lines heavier, by class, and after the others', async () => {
      serveMap(user, { [LEAVE.item_id]: FOCUS_LEAVE })
      renderMap(`/knowledge-map${focusSearch(LEAVE)}`)
      await findDiagram()

      // Four edges; two touch the leave policy.
      const lines = [...diagram().querySelectorAll('svg.knowledge-map__lines line')]
      expect(lines.map((line) => line.classList.contains('knowledge-map__line--selected'))).toEqual([
        false,
        false,
        true,
        true,
      ])
      for (const line of lines) expect(line.classList.contains('knowledge-map__line')).toBe(true)
      // The heavier line is a different stroke and a different width in the stylesheet.
      const plain = declared(lines[0])
      const heavy = declared(lines[3])
      expect(colourTokensIn(plain.stroke)).toHaveLength(1)
      expect(colourTokensIn(heavy.stroke)).toHaveLength(1)
      expect(colourTokensIn(heavy.stroke)).not.toEqual(colourTokensIn(plain.stroke))
      expect(parseFloat(resolve(heavy['stroke-width']))).toBeGreaterThan(parseFloat(resolve(plain['stroke-width'])))
      // And the selected node's own outline is heavier too, whether or not it has a line.
      const node = selectedOnDiagram()
      expect(node.classList.contains('knowledge-map__node--selected')).toBe(true)
      const other = declared(nodeLink(counted(BUDGET, 1)))
      expect(other['border-width']).toBeUndefined()
      expect(parseFloat(resolve(declared(node)['border-width']))).toBeGreaterThan(parseFloat(resolve(other.border)))
    })
  })

  describe('the way in', () => {
    it('offers "Knowledge map" in the navigation straight after Ask, ahead of anything an Administrator alone is offered', async () => {
      serveMap(user, { '': OVERVIEW })
      renderMap()
      await findDiagram()

      const navigation = screen.getByRole('navigation', { name: 'Primary' })
      await within(navigation).findByText(`Signed in as ${user.name}`)
      const links = within(navigation).getAllByRole('link')
      const names = links.map((link) => link.textContent)
      const place = names.indexOf(TEXT.mapHeading)
      expect(place).toBe(names.indexOf(TEXT.askNavLabel) + 1)
      expect(names.filter((name) => name === TEXT.mapHeading)).toHaveLength(1)
      expect(links[place].getAttribute('href')).toBe('/knowledge-map')
      expect(links[place].getAttribute('aria-current')).toBe('page')
      if (user.role === ROLES.administrator) {
        // The three Administrator links stay together, after it.
        expect(names.slice(place + 1, place + 4)).toEqual(['Role management', TEXT.gapsHeading, TEXT.tagsHeading])
      } else {
        expect(names).not.toContain('Role management')
      }
      // The page heads itself and names the tab.
      expect(screen.getByRole('heading', { level: 1, name: TEXT.mapHeading })).toBeTruthy()
      await waitFor(() => expect(document.title.startsWith(TEXT.mapHeading)).toBe(true))
    })

    it('returns to the knowledge map after signing in, when it was opened signed out (UC-11 E2, in part)', async () => {
      let signedIn = false
      const answered = serveApi({
        'GET /api/auth/me': () => (signedIn ? { body: user } : NOT_SIGNED_IN),
        'POST /api/auth/login': () => {
          signedIn = true
          return { body: user }
        },
        'GET /api/knowledge-map': mapRoute({ '': OVERVIEW }),
      })
      renderMap('/knowledge-map')

      // Sent to sign in, having asked the map route for nothing.
      fireEvent.change(await screen.findByLabelText('Email'), { target: { value: user.email } })
      expect(probe.location.pathname).toBe('/login')
      expect(mapRequests(answered)).toEqual([])
      fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Correct-Horse-1' } })
      fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

      await findDiagram()
      await waitFor(() => expect(probe.location.pathname).toBe('/knowledge-map'))
      expect(screen.getByRole('heading', { level: 1, name: TEXT.mapHeading })).toBeTruthy()
      expect(mapRequests(answered)).toEqual([''])
    })
  })
})
