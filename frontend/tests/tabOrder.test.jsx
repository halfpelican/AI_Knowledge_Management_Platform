/**
 * Keyboard tab order on the main screens (Stage 5 item 7; NFR-16: "full
 * keyboard operability of all interactive elements", SC 2.1.1, and no trap,
 * SC 2.1.2).
 *
 * The whole application is rendered with the real auth provider, and
 * tests/keyboard.js presses Tab the way a browser does. Each screen asserts
 * four things: the skip link is the first stop; nothing reachable is invisible
 * while it holds focus (tests/stylesheets.js reads the CSS jsdom does not
 * apply); the order runs header before content, in the reading order the
 * screen lays out; and tabbing reaches the end without returning to a visited
 * stop, which would be a trap.
 *
 * No element may carry a positive tabindex: the DOM order is the tab order
 * everywhere, which is what keeps these assertions honest.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { ROLES, TEXT } from '../src/constants.js'
import { actionItem, readySummary, serveApi, summaryRoute, summaryState } from './fakeApi.js'
import { pressTab, stopName, tabThrough } from './keyboard.js'
import { hidingCauses } from './stylesheets.js'

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

const DOCUMENT = {
  doc_id: 'doc-1',
  title: 'Leave policy 2026',
  file_type: 'pdf',
  status: 'Indexing failed',
  uploaded_at: '2026-09-21T10:00:00+10:00',
  department: 'Human Resources',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  file_size_bytes: 14203,
  uploaded_by: 'erin@example.com',
}

const BROWSE = {
  filters: { q: null, status: null, department: null, project: null, process: null, topic: null, sort: '-uploaded_at' },
  facets: { department: [{ value: 'Finance', count: 3 }], project: [], process: [], topic: [] },
  documents: [DOCUMENT],
}

const DASHBOARD = {
  filters: { date_from: null, date_to: null, department: null },
  departments: ['Finance'],
  indexed_totals: { documents: 4, meetings: 2, total: 6 },
  recent_documents: [{ ...DOCUMENT, status: 'Indexed' }],
  recent_meetings: [],
  recent_questions: [],
}

const CONVERSATION_SUMMARY = {
  conversation_id: '6f1c2a54-0000-4000-8000-000000000001',
  title: 'How much annual leave do I get?',
  last_updated_at: '2026-09-20T10:00:00Z',
}

/** The signed-in routes every screen needs, before its own. */
function signedIn(routes = {}) {
  return serveApi({ 'GET /api/auth/me': { body: EMPLOYEE }, ...routes })
}

function renderApp(path) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

/**
 * A stop is allowed to hold focus only while something shows it: the stop
 * itself, or — for the visually hidden file input, whose ring
 * FileDropZone.css draws on its label — the label that names it.
 */
function visibleWhileFocused(stop) {
  if (hidingCauses(stop).length === 0) return true
  if (!stop.id) return false
  const label = document.querySelector(`label[for="${stop.id}"]`)
  return label !== null && hidingCauses(label).length === 0
}

/** Tabs through the whole page, asserting the shared properties, and returns the stops. */
function walk() {
  expect(document.querySelector('[tabindex]:not([tabindex="-1"]):not([tabindex="0"])'), 'a positive tabindex reorders the page').toBeNull()
  const stops = tabThrough() // throws on a trap
  expect(stopName(stops[0]), 'the skip link is the first stop').toBe('Skip to content')
  for (const stop of stops) {
    stop.focus()
    expect(visibleWhileFocused(stop), `an invisible stop is reachable: ${stopName(stop) || stop.outerHTML.slice(0, 80)}`).toBe(true)
  }
  return stops
}

/**
 * Asserts the entries appear among the stops in this relative order. An entry
 * is an exact accessible name (its first occurrence), or an element where one
 * name appears twice on the page.
 */
function expectOrder(stops, entries) {
  const labels = stops.map(stopName)
  const positions = entries.map((entry) =>
    typeof entry === 'string' ? labels.indexOf(entry) : stops.indexOf(entry),
  )
  for (const [index, position] of positions.entries()) {
    const name = typeof entries[index] === 'string' ? entries[index] : stopName(entries[index])
    expect(position, `"${name}" is not a tab stop (stops: ${labels.join(' | ')})`).toBeGreaterThanOrEqual(0)
  }
  for (let i = 1; i < positions.length; i += 1) {
    const name = typeof entries[i] === 'string' ? entries[i] : stopName(entries[i])
    expect(positions[i], `"${name}" comes before its predecessor`).toBeGreaterThan(positions[i - 1])
  }
}

describe('tab order, screen by screen', () => {
  it('sign-in: skip link, navigation, then the form in reading order', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderApp('/login')
    await screen.findByRole('heading', { name: 'Sign in' })

    const stops = walk()
    // "Sign in" names both the navigation link and the submit button, so the
    // button goes in as an element.
    expectOrder(stops, [
      'Skip to content',
      'Home',
      'Email',
      'Password',
      'Show password',
      screen.getByRole('button', { name: 'Sign in' }),
    ])
  })

  it('dashboard: the search field FR-12 puts on every page comes before the navigation, then the filters, then the panels', async () => {
    signedIn({ 'GET /api/dashboard': { body: DASHBOARD } })
    renderApp('/dashboard')
    await screen.findByRole('link', { name: 'Leave policy 2026' })

    const stops = walk()
    expectOrder(stops, [
      'Skip to content',
      TEXT.searchFieldLabel,
      TEXT.dashboardHeading,
      'Log out',
      'From',
      TEXT.dashboardApplyFilters,
      TEXT.dashboardDocumentsHeading,
      'Leave policy 2026',
      TEXT.dashboardQuestionsHeading,
    ])
  })

  it('documents: filter, browse values, then the scrollable results region before the rows inside it', async () => {
    signedIn({ 'GET /api/documents/browse': { body: BROWSE } })
    renderApp('/documents')
    await screen.findByRole('link', { name: 'Leave policy 2026' })

    const stops = walk()
    expectOrder(stops, [
      'Skip to content',
      screen.getByLabelText(TEXT.repositoryFilterLabel),
      screen.getByRole('button', { name: TEXT.repositoryFilterSubmit }),
      screen.getByRole('button', { name: /^Finance/ }),
      TEXT.repositoryColumnTitle,
      'Leave policy 2026',
      TEXT.documentRetryLabel('Leave policy 2026'),
    ])
    // The region that scrolls sideways at narrow widths is itself a stop, ahead
    // of its content, so a keyboard user can scroll it (SC 2.1.1).
    const region = document.querySelector('.table-scroll')
    const titleLink = screen.getByRole('link', { name: 'Leave policy 2026' })
    expect(stops.indexOf(region)).toBeGreaterThan(-1)
    expect(stops.indexOf(region)).toBeLessThan(stops.indexOf(titleLink))
  })

  it('upload: the file picker is reachable first in the form, then the queue options, then the action', async () => {
    signedIn({})
    renderApp('/upload')
    await screen.findByRole('heading', { name: 'Upload documents' })

    const stops = walk()
    expectOrder(stops, ['Skip to content', 'Choose files', 'Department (optional)'])
    expect(stops).toContain(screen.getByLabelText('Choose files'))
    // With nothing queued the Upload button is disabled, and a disabled control
    // is not a stop; the sentence on the button says why it waits.
    const upload = screen.getByRole('button', { name: 'Upload 0 files' })
    expect(upload.disabled).toBe(true)
    expect(stops).not.toContain(upload)
  })

  it('meetings: one stop for the radio group, then the transcript, the attendee picker and the submit', async () => {
    signedIn({
      'GET /api/meetings': { body: [] },
      'GET /api/users/directory': { body: [{ id: 'user-ada', name: 'Ada Admin', email: 'ada@example.com' }] },
    })
    renderApp('/meetings')
    await screen.findByLabelText(TEXT.attendeeAddLabel)

    const stops = walk()
    expectOrder(stops, [
      'Skip to content',
      'Meeting title',
      'Meeting date',
      TEXT.meetingSourceText,
      'Transcript',
      TEXT.attendeeAddLabel,
      'Add transcript',
    ])
    // The radio group takes exactly one press of Tab (arrow keys move within it).
    const radios = stops.filter((stop) => stop.type === 'radio')
    expect(radios).toHaveLength(1)
  })

  it('ask: the question and its actions come before the list of previous conversations, at every width', async () => {
    signedIn({
      'GET /api/conversations': { body: [CONVERSATION_SUMMARY] },
    })
    renderApp('/ask')
    await screen.findByRole('button', { name: TEXT.conversationOpen(CONVERSATION_SUMMARY.title) })
    // Ask stays disabled until the question is long enough (FR-01's gate
    // pattern on FR-12's bounds), and a disabled control is not a stop — so the
    // walk runs with a valid question in the field.
    fireEvent.change(screen.getByLabelText(TEXT.askFieldLabel), {
      target: { value: 'How much annual leave do I get?' },
    })
    await waitFor(() => expect(screen.getByRole('button', { name: TEXT.askSubmit }).disabled).toBe(false))

    const stops = walk()
    // The aside is after the main column in the DOM, so the single-column layout
    // stacks it below without reordering and this order holds at both widths
    // (pages/Ask.css). "Ask" names the navigation link too, so the submit goes
    // in as an element.
    expectOrder(stops, [
      'Skip to content',
      screen.getByLabelText(TEXT.askFieldLabel),
      screen.getByRole('button', { name: TEXT.askSubmit }),
      TEXT.newTopic,
      TEXT.conversationOpen(CONVERSATION_SUMMARY.title),
    ])
  })

  it('shift+tab walks the same stops in reverse', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderApp('/login')
    await screen.findByRole('heading', { name: 'Sign in' })

    const forward = tabThrough()
    const backward = tabThrough({ shift: true })
    expect(backward.map(stopName)).toEqual(forward.map(stopName).reverse())
  })
})

describe('FR-20 / NFR-17: the knowledge map, its diagram and its table view (D-132)', () => {
  const ADMINISTRATOR = {
    id: 'user-administrator',
    name: 'Ada Administrator',
    email: 'ada@example.com',
    role: ROLES.administrator,
    created_at: '2026-09-12T10:00:00+10:00',
  }

  const mapNode = (type, itemId, label, connectionCount, dimension = null) => ({
    id: `${type}:${itemId}`,
    type,
    item_id: itemId,
    label,
    dimension,
    connection_count: connectionCount,
  })
  const POLICY = mapNode('document', '0b7c2a54-0000-4000-8000-000000000001', 'Employee Leave Policy 2026', 2)
  const PEOPLE = mapNode('tag', '0b7c2a54-0000-4000-8000-000000000002', 'people', 1, 'Topic')
  const JANE = mapNode('contributor', '0b7c2a54-0000-4000-8000-000000000003', 'Jane Doe', 2)
  const SYNC = mapNode('meeting', '0b7c2a54-0000-4000-8000-000000000004', 'Q3 Planning Sync', 1)

  // The walk from the policy, in the server's walk order: the source, its tag, its
  // contributor, then what they lead to. Not the order the columns are read in.
  const MAP = {
    focus: { type: POLICY.type, id: POLICY.item_id },
    nodes: [POLICY, PEOPLE, JANE, SYNC],
    edges: [
      { source: POLICY.id, target: PEOPLE.id, relationship: 'tagged' },
      { source: JANE.id, target: POLICY.id, relationship: 'uploaded' },
      { source: JANE.id, target: SYNC.id, relationship: 'attended' },
    ],
    truncated: true,
    truncated_by: 'depth',
    maximum_node_count: 50,
    maximum_traversal_depth: 2,
  }

  it.each([EMPLOYEE, ADMINISTRATOR])(
    'as an $role: the skip link, the nodes column by column, the Selected panel, then each table region ahead of its headings and rows',
    async (user) => {
      serveApi({ 'GET /api/auth/me': { body: user }, 'GET /api/knowledge-map': { body: MAP } })
      renderApp(`/knowledge-map?focus_type=${POLICY.type}&focus_id=${POLICY.item_id}`)
      const diagram = await screen.findByRole('region', { name: TEXT.mapDiagramHeading })
      const panel = screen.getByRole('region', { name: TEXT.mapSelectedHeading })
      const itemsRegion = screen.getByRole('region', { name: TEXT.mapItemsHeading })
      const relationshipsRegion = screen.getByRole('region', { name: TEXT.mapRelationshipsHeading })

      // walk() also asserts that no stop is hidden by markup or by any stylesheet
      // rule, on it or an ancestor, and that nothing carries a positive tabindex.
      const stops = walk()

      // The page in reading order: the header, the link past the diagram, the
      // diagram, the panel, then the two tables.
      expectOrder(stops, [
        'Skip to content',
        TEXT.searchFieldLabel,
        screen.getByRole('link', { name: TEXT.mapHeading }),
        'Log out',
        TEXT.mapSkipToTables,
        diagram,
        panel.querySelector('a'),
        itemsRegion,
        relationshipsRegion,
      ])

      // The diagram adds one stop for its scroll region and one per node, and the
      // nodes come column by column, top to bottom: the contributor, then the
      // document and the meeting, then the tag. The reply's own order would have
      // read the document, the tag, the contributor, the meeting.
      const inDiagram = stops.filter((stop) => diagram.contains(stop))
      expect(inDiagram).toHaveLength(1 + MAP.nodes.length)
      expect(inDiagram[0]).toBe(diagram)
      expect(inDiagram.slice(1).map((stop) => stop.querySelector('.knowledge-map__node-label').textContent)).toEqual([
        JANE.label,
        POLICY.label,
        SYNC.label,
        TEXT.mapTagLabel(PEOPLE.dimension, PEOPLE.label),
      ])
      for (const stop of inDiagram.slice(1)) expect(stop.tagName).toBe('A')
      // Nothing in the lines' layer is a stop.
      expect(stops.filter((stop) => stop.closest('svg') !== null)).toEqual([])

      // The Selected panel: the two connections, the open action, the way back.
      expect(stops.filter((stop) => panel.contains(stop)).map(stopName)).toEqual([
        `${TEXT.mapTypeTag}: ${TEXT.mapTagLabel(PEOPLE.dimension, PEOPLE.label)}`,
        `${TEXT.mapTypeContributor}: ${JANE.label}`,
        TEXT.mapOpenDocument,
        TEXT.mapShowWhole,
      ])

      // Each table's scroll region is itself a stop, ahead of its sort buttons,
      // which are ahead of its rows (SC 2.1.1): three headings, then a link per
      // node in Items and two per line in Relationships.
      for (const [region, links] of [
        [itemsRegion, MAP.nodes.length],
        [relationshipsRegion, MAP.edges.length * 2],
      ]) {
        const inRegion = stops.filter((stop) => region.contains(stop))
        expect(inRegion[0]).toBe(region)
        expect(inRegion.slice(1, 4).map((stop) => stop.tagName)).toEqual(['BUTTON', 'BUTTON', 'BUTTON'])
        expect(inRegion.slice(4).map((stop) => stop.tagName)).toEqual(Array(links).fill('A'))
      }
    },
  )

  it('a selected contributor is not a stop on the diagram: there is nothing for a second selection to open', async () => {
    const map = { ...MAP, focus: { type: JANE.type, id: JANE.item_id }, truncated: false, truncated_by: null }
    signedIn({ 'GET /api/knowledge-map': { body: map } })
    renderApp(`/knowledge-map?focus_type=${JANE.type}&focus_id=${JANE.item_id}`)
    const diagram = await screen.findByRole('region', { name: TEXT.mapDiagramHeading })

    const stops = walk()

    const inDiagram = stops.filter((stop) => diagram.contains(stop))
    // The region and the three other nodes.
    expect(inDiagram).toHaveLength(1 + MAP.nodes.length - 1)
    expect(inDiagram[0]).toBe(diagram)
    expect(inDiagram.slice(1).some((stop) => stop.textContent.includes(JANE.label))).toBe(false)
    expect(diagram.querySelector('[aria-current="true"]').tagName).toBe('SPAN')
  })

  describe('its second view, claims and passages (D-138)', () => {
    const claimNode = (itemId, label, connectionCount, passageCount) => ({
      id: `claim:${itemId}`,
      type: 'claim',
      item_id: itemId,
      label,
      dimension: null,
      connection_count: connectionCount,
      detail: {
        answer_count: 3,
        passage_count: passageCount,
        first_admitted_at: '2026-10-01',
        last_admitted_at: '2026-10-08',
      },
    })
    const passageNode = (itemId, sourceType, sourceTitle, position, connectionCount, aiGenerated) => ({
      id: `passage:${itemId}`,
      type: 'passage',
      item_id: itemId,
      label: `${sourceTitle} · passage ${position}`,
      dimension: null,
      connection_count: connectionCount,
      detail: {
        source_type: sourceType,
        source_id: '0b7c2a54-0000-4000-8000-000000000009',
        source_title: sourceTitle,
        position,
        ai_generated: aiGenerated,
      },
    })
    const ACCRUAL = claimNode('a'.repeat(64), 'Annual leave accrues at four weeks a year.', 1, 1)
    const CARRY_OVER = claimNode('b'.repeat(64), 'Unused leave carries over for twelve months.', 2, 2)
    const HANDBOOK = passageNode('0b7c2a54-0000-4000-8000-000000000005', 'document', 'Staff Handbook', 2, 2, false)
    const SUMMARY = passageNode('0b7c2a54-0000-4000-8000-000000000006', 'meeting', 'Budget Review Meeting', 4, 1, true)

    // The walk from the handbook's passage, in the server's walk order: the passage,
    // the claims that cite it, then their other passage. Not the order the columns
    // are read in.
    const EVIDENCE = {
      focus: { type: HANDBOOK.type, id: HANDBOOK.item_id },
      nodes: [HANDBOOK, ACCRUAL, CARRY_OVER, SUMMARY],
      edges: [
        { source: ACCRUAL.id, target: HANDBOOK.id, relationship: 'cites', weight: 3 },
        { source: CARRY_OVER.id, target: HANDBOOK.id, relationship: 'cites', weight: 1 },
        { source: CARRY_OVER.id, target: SUMMARY.id, relationship: 'cites', weight: 6 },
      ],
      truncated: true,
      truncated_by: 'depth',
      maximum_node_count: 50,
      maximum_traversal_depth: 2,
    }

    it.each([EMPLOYEE, ADMINISTRATOR])(
      'as an $role: the skip link, the switch, the claims then the passages, the pane, then each table region ahead of its headings and rows',
      async (user) => {
        serveApi({ 'GET /api/auth/me': { body: user }, 'GET /api/knowledge-map/evidence': { body: EVIDENCE } })
        renderApp(`/knowledge-map?view=evidence&focus_type=${HANDBOOK.type}&focus_id=${HANDBOOK.item_id}`)
        const diagram = await screen.findByRole('region', { name: TEXT.evidenceDiagramHeading })
        const pane = screen.getByRole('region', { name: TEXT.mapSelectedHeading })
        const itemsRegion = screen.getByRole('region', { name: TEXT.mapItemsHeading })
        const relationshipsRegion = screen.getByRole('region', { name: TEXT.mapRelationshipsHeading })

        // walk() also asserts that no stop is hidden by markup or by any stylesheet
        // rule, on it or an ancestor, and that nothing carries a positive tabindex.
        const stops = walk()

        // The page in reading order: the header, the link past the diagram, the
        // link to the other view, the diagram, the pane, then the two tables.
        expectOrder(stops, [
          'Skip to content',
          TEXT.searchFieldLabel,
          screen.getByRole('link', { name: TEXT.mapHeading }),
          'Log out',
          TEXT.mapSkipToTables,
          TEXT.evidenceSwitchToMap,
          diagram,
          pane.querySelector('a'),
          itemsRegion,
          relationshipsRegion,
        ])
        // The switch is the very next stop after the skip link.
        const names = stops.map(stopName)
        expect(names.indexOf(TEXT.evidenceSwitchToMap)).toBe(names.indexOf(TEXT.mapSkipToTables) + 1)

        // The diagram adds one stop for its scroll region and one per node: down the
        // claims, then down the passages. The reply's own order would have read the
        // handbook's passage first.
        const inDiagram = stops.filter((stop) => diagram.contains(stop))
        expect(inDiagram).toHaveLength(1 + EVIDENCE.nodes.length)
        expect(inDiagram[0]).toBe(diagram)
        expect(inDiagram.slice(1).map((stop) => stop.querySelector('.knowledge-map__node-label').textContent)).toEqual([
          ACCRUAL.label,
          CARRY_OVER.label,
          HANDBOOK.label,
          SUMMARY.label,
        ])
        for (const stop of inDiagram.slice(1)) expect(stop.tagName).toBe('A')
        // Nothing in the lines' layer is a stop.
        expect(stops.filter((stop) => stop.closest('svg') !== null)).toEqual([])

        // The pane for the selected passage: the two claims that cite it, the open
        // action, the way back.
        expect(stops.filter((stop) => pane.contains(stop)).map(stopName)).toEqual([
          `${TEXT.evidenceTypeClaim}: ${ACCRUAL.label}`,
          `${TEXT.evidenceTypeClaim}: ${CARRY_OVER.label}`,
          TEXT.mapOpenDocument,
          TEXT.mapShowWhole,
        ])

        // Each table's scroll region is itself a stop, ahead of its sort buttons,
        // which are ahead of its rows: three headings and a link per node in Items,
        // four headings and two links per line in Relationships.
        for (const [region, headings, links] of [
          [itemsRegion, 3, EVIDENCE.nodes.length],
          [relationshipsRegion, 4, EVIDENCE.edges.length * 2],
        ]) {
          const inRegion = stops.filter((stop) => region.contains(stop))
          expect(inRegion[0]).toBe(region)
          expect(inRegion.slice(1, 1 + headings).map((stop) => stop.tagName)).toEqual(Array(headings).fill('BUTTON'))
          expect(inRegion.slice(1 + headings).map((stop) => stop.tagName)).toEqual(Array(links).fill('A'))
        }
      },
    )

    it('a selected claim is not a stop on the diagram: a claim has no page for a second selection to open', async () => {
      const evidence = { ...EVIDENCE, focus: { type: CARRY_OVER.type, id: CARRY_OVER.item_id }, truncated: false, truncated_by: null }
      signedIn({ 'GET /api/knowledge-map/evidence': { body: evidence } })
      renderApp(`/knowledge-map?view=evidence&focus_type=${CARRY_OVER.type}&focus_id=${CARRY_OVER.item_id}`)
      const diagram = await screen.findByRole('region', { name: TEXT.evidenceDiagramHeading })

      const stops = walk()

      const inDiagram = stops.filter((stop) => diagram.contains(stop))
      // The region and the three other nodes.
      expect(inDiagram).toHaveLength(1 + EVIDENCE.nodes.length - 1)
      expect(inDiagram[0]).toBe(diagram)
      expect(inDiagram.slice(1).some((stop) => stop.textContent.includes(CARRY_OVER.label))).toBe(false)
      expect(diagram.querySelector('[aria-current="true"]').tagName).toBe('SPAN')
    })
  })
})

describe('FR-16: the meeting page with its Summary and Action Items panels', () => {
  it('reaches the regenerate button, every passage reference and every item control, in reading order', async () => {
    const meeting = {
      meeting_id: 'meeting-2',
      title: 'Finance Quarterly Budget Review',
      meeting_date: '2026-10-14',
      status: 'Indexed',
      created_at: '2026-11-11T10:00:00+11:00',
      visible_to_roles: [ROLES.employee, ROLES.administrator],
      attendees: [],
      transcript_text: 'Ravi: Thanks, everyone. This is the first-quarter review.',
      can_delete: false,
    }
    const item = actionItem()
    signedIn({
      [`GET /api/meetings/${meeting.meeting_id}`]: { body: meeting },
      [`GET /api/meetings/${meeting.meeting_id}/summary`]: summaryRoute(
        summaryState({ status: 'Ready', summary: readySummary(), action_items: [item], can_edit: true }),
      ),
      'GET /api/users/directory': { body: [] },
    })
    renderApp(`/meetings/${meeting.meeting_id}`)
    const regenerate = await screen.findByRole('button', { name: TEXT.summaryRegenerate })
    const edit = await screen.findByRole('button', { name: TEXT.actionItemEditLabel(item.description) })
    const remove = screen.getByRole('button', { name: TEXT.actionItemDeleteLabel(item.description) })
    const add = screen.getByRole('button', { name: TEXT.actionItemAdd })

    const stops = walk()

    // Every control of the two panels is a tab stop, and none is reached out of reading order:
    // the summary and its button first, then the item's own controls, then adding another.
    for (const control of [regenerate, edit, remove, add]) {
      expect(stops, `"${stopName(control)}" is not a tab stop`).toContain(control)
    }
    expectOrder(stops, [regenerate, edit, remove, add])
    // UC-04's passage references are real buttons the keyboard reaches: the summary's five
    // (two sentences naming three passages between them, a decision, a highlight) and the item's one.
    const references = stops.filter((stop) => stop.matches('button[aria-expanded]') && /passage/i.test(stopName(stop)))
    expect(references.length).toBe(6)
    // The item's reference sits with the item, between the summary's button and the item's Edit.
    const itemReference = references[references.length - 1]
    expectOrder(stops, [regenerate, itemReference, edit])
  })
})

describe('the confirmation dialogue holds Tab inside itself, and only itself', () => {
  it('cycles confirm and cancel both ways while open', async () => {
    const meeting = {
      meeting_id: 'meeting-1',
      title: 'Q3 Planning Sync',
      meeting_date: '2026-07-28',
      status: 'Indexed',
      created_at: '2026-09-21T10:00:00+10:00',
      visible_to_roles: [ROLES.employee, ROLES.administrator],
      attendees: [],
      transcript_text: 'Ada: the dates hold.',
      can_delete: true,
    }
    signedIn({
      [`GET /api/meetings/${meeting.meeting_id}`]: { body: meeting },
      // The page's own second read since FR-16: no summary, nothing offered.
      [`GET /api/meetings/${meeting.meeting_id}/summary`]: summaryRoute(summaryState()),
    })
    renderApp(`/meetings/${meeting.meeting_id}`)

    const open = await screen.findByRole('button', { name: TEXT.meetingDelete })
    open.focus()
    open.click()
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(document.activeElement).toBe(dialog))

    // The opener behind the dialogue has the same name, so the dialogue is the scope.
    const confirm = within(dialog).getByRole('button', { name: TEXT.meetingDelete })
    const cancel = within(dialog).getByRole('button', { name: TEXT.meetingDeleteCancel })
    expect(pressTab()).toBe(confirm)
    expect(pressTab()).toBe(cancel)
    // Off the end: back to the first control, never out of the dialogue.
    expect(pressTab()).toBe(confirm)
    expect(pressTab({ shift: true })).toBe(cancel)
  })
})
