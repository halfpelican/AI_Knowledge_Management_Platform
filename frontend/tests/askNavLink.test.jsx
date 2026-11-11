/**
 * FR-13's Front-End clause: "A conversational interface reachable from any page".
 *
 * It is built as the Ask link in the shell's primary navigation (src/App.jsx,
 * `PrimaryNav`), shown while a user is signed in. A requirements re-audit on
 * 11 November 2026 found that nothing under tests/ asserted the link, so the clause
 * had no front-end evidence (CLAUDE.md §8 condition 2). The sibling clause, FR-12's
 * "a search field available from every page", was graded partial for being tested
 * on two pages with no test walking the routes (docs/stage-5-front-end-clauses.md),
 * so this file walks them.
 *
 * What is defended here:
 *
 * - **The walk.** The whole application, with the real routes, guards and auth
 *   provider, is rendered at every path in src/App.jsx's route table, and at `/`,
 *   once as an Employee and once as an Administrator. On the page each ends on,
 *   the navigation landmark named "Primary" holds exactly one link whose accessible
 *   name is `TEXT.askNavLabel`, and its `href` is `/ask`. Where the application
 *   sends the user on, the case says where and asserts it: `/`, `/login` and
 *   `/register` send a signed-in user to their dashboard, and the three
 *   Administrator-only paths send an Employee to `/403`.
 * - **Following the link.** From four of those pages, two for each role, a click on
 *   the link shows the Ask screen at `/ask` in place of the page it was on.
 * - **The route table.** Every `path="…"` in src/App.jsx has a case in the walk as
 *   each role, so a route added there without one fails here.
 *
 * What is not:
 *
 * - **Whether the link can be seen.** jsdom applies no stylesheet. These tests find
 *   the link in the accessibility tree; a CSS rule that hid it, or the navigation,
 *   would not fail them.
 * - **An anonymous visitor.** One is offered no Ask link, by design: RequireAuth
 *   would send them to `/login` (src/App.jsx). This file asserts that neither way.
 * - **An address no route matches.** It is not a page, and it is not walked.
 * - **Following the link from every page.** The link's presence and target are
 *   asserted on every page; the click is made from four.
 * - **Which roles a new route admits.** The route-table test cannot read a guard
 *   from the source, so it asks for a case as each role and the case says where
 *   that role lands.
 * - **The Ask screen itself**, which is tests/ask*.test.jsx's, and everything the
 *   server decides. The replies below are the same for both roles: what a server
 *   would send each differently (scope, `can_delete`) plays no part in the
 *   navigation.
 *
 * Each case's table names the routes its page asks for and no others: a request
 * nothing answers fails the test (tests/setup.js), and so does a route the page
 * never asked for.
 *
 * The location is read by a probe in a layout effect and asserted in `waitFor`
 * (tests/dashboard.test.jsx says why).
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { useLayoutEffect } from 'react'
import { MemoryRouter, matchPath, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { ROLES, TEXT } from '../src/constants.js'
import { serveApi } from './fakeApi.js'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

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

/** FR-02's destination for each role, written out so a change to it fails here. */
const HOME = { [ROLES.employee]: '/dashboard', [ROLES.administrator]: '/admin' }

const DOCUMENT = {
  doc_id: 'doc-1',
  title: 'Leave policy 2026',
  file_type: 'pdf',
  status: 'Indexed',
  uploaded_at: '2026-09-21T10:00:00+10:00',
  department: 'Human Resources',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  file_size_bytes: 14203,
  uploaded_by: 'erin@example.com',
}

const MEETING = {
  meeting_id: 'meeting-1',
  title: 'Q3 planning sync',
  meeting_date: '2026-07-28',
  status: 'Indexed',
  created_at: '2026-09-21T10:00:00+10:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: ['erin@example.com'],
}

const CONVERSATION = {
  conversation_id: '6f1c2a54-0000-4000-8000-000000000001',
  title: 'How much annual leave do I get?',
  last_updated_at: '2026-09-20T10:00:00Z',
}

const SEARCH_TERM = 'leave'

const SEARCH_RESULT = {
  source_type: 'document',
  source_id: DOCUMENT.doc_id,
  title: DOCUMENT.title,
  snippet: 'Full-time staff accrue four weeks of annual leave per year.',
  department: DOCUMENT.department,
  date: DOCUMENT.uploaded_at,
}

const GAP = {
  gap_id: '7d0c3f8a-0000-4000-8000-000000000001',
  subject: 'What is the WFH stipend policy?',
  occurrence_count: 6,
  status: 'Open',
  first_seen_at: '2026-11-02T09:14:00+11:00',
  last_seen_at: '2026-11-09T09:25:00+11:00',
}

const TAG = { tag_id: 'tag-0001', dimension: 'Process', tag_name: 'purchasing', active: true, item_count: 4 }

/* ---- The pages: what each asks the API for on mount, and how it shows it has rendered ---- */

/** The page's own level-1 heading, once it is there. */
function pageHeading(name) {
  return screen.findByRole('heading', { level: 1, name })
}

/**
 * `api` is every route the page requests on mount, beside the session check.
 * `settled` resolves once the page's heading is shown and, where it reads
 * anything, once something from each reply is.
 */
const DASHBOARD = {
  api: {
    'GET /api/dashboard': {
      body: {
        filters: { date_from: null, date_to: null, department: null },
        departments: ['Human Resources'],
        indexed_totals: { documents: 4, meetings: 2, total: 6 },
        recent_documents: [DOCUMENT],
        recent_meetings: [],
        recent_questions: [],
      },
    },
  },
  // Its questions panel links to /ask as well, under another name and outside the
  // navigation, which is why the link is looked for inside the landmark.
  async settled() {
    await pageHeading(TEXT.dashboardHeading)
    await screen.findByRole('link', { name: DOCUMENT.title })
  },
}

const UPLOAD = {
  api: {},
  settled: () => pageHeading('Upload documents'),
}

const DOCUMENTS = {
  api: {
    'GET /api/documents/browse': {
      body: {
        filters: { q: null, status: null, department: null, project: null, process: null, topic: null, sort: '-uploaded_at' },
        facets: { department: [{ value: 'Human Resources', count: 1 }], project: [], process: [], topic: [] },
        documents: [DOCUMENT],
      },
    },
  },
  async settled() {
    await pageHeading(TEXT.repositoryHeading)
    await screen.findByRole('link', { name: DOCUMENT.title })
  },
}

const DOCUMENT_DETAIL = {
  api: {
    [`GET /api/documents/${DOCUMENT.doc_id}`]: {
      body: {
        ...DOCUMENT,
        extracted_text: 'Employees may request annual leave.',
        tags: { project: [], process: [], topic: [] },
        can_delete: false,
        classification: null,
        tag_details: [],
        tag_options: { Project: [], Process: [], Topic: [] },
      },
    },
  },
  // The heading is the document's title, so it is there only once the reply is.
  settled: () => pageHeading(DOCUMENT.title),
}

const MEETINGS = {
  api: {
    'GET /api/meetings': { body: [MEETING] },
    'GET /api/users/directory': { body: [{ id: ADMINISTRATOR.id, name: ADMINISTRATOR.name, email: ADMINISTRATOR.email }] },
  },
  async settled() {
    await pageHeading('Meeting transcripts')
    await screen.findByRole('link', { name: MEETING.title })
    // The attendee picker replaces a loading line once the directory has answered.
    await screen.findByLabelText(TEXT.attendeeAddLabel)
  },
}

const MEETING_DETAIL = {
  api: {
    [`GET /api/meetings/${MEETING.meeting_id}`]: {
      body: { ...MEETING, transcript_text: 'Alex: the supplier review is due on Friday.', can_delete: false },
    },
  },
  settled: () => pageHeading(MEETING.title),
}

const SEARCH = {
  api: {
    'GET /api/search': {
      body: {
        query: SEARCH_TERM,
        documents: { count: 1, results: [SEARCH_RESULT] },
        meetings: { count: 0, results: [] },
        total_count: 1,
      },
    },
  },
  async settled() {
    await pageHeading(TEXT.searchHeading)
    await screen.findByRole('link', { name: SEARCH_RESULT.title })
  },
}

const ASK = {
  api: { 'GET /api/conversations': { body: [CONVERSATION] } },
  async settled() {
    await pageHeading(TEXT.askHeading)
    await screen.findByRole('button', { name: TEXT.conversationOpen(CONVERSATION.title) })
  },
}

const COMPONENT_SHEET = {
  api: {},
  settled: () => pageHeading('Component sheet'),
}

const ACCESS_DENIED = {
  api: {},
  settled: () => pageHeading(TEXT.accessDeniedTitle),
}

const ROLE_MANAGEMENT = {
  api: {
    'GET /api/users': { body: [ADMINISTRATOR, EMPLOYEE] },
    'GET /api/roles': {
      body: [
        { role_id: 'role-employee', name: ROLES.employee, description: 'Default role', permissions: [] },
        { role_id: 'role-administrator', name: ROLES.administrator, description: 'Full management', permissions: [] },
      ],
    },
  },
  async settled() {
    await pageHeading('Role management')
    // The table renders only once both reads have answered.
    await screen.findByLabelText(`Role for ${EMPLOYEE.name}`)
  },
}

const KNOWLEDGE_GAPS = {
  api: { 'GET /api/knowledge-gaps': { body: [GAP] } },
  async settled() {
    await pageHeading(TEXT.gapsHeading)
    await screen.findByText(GAP.subject)
  },
}

const TAGS = {
  api: { 'GET /api/tags': { body: [TAG] } },
  async settled() {
    await pageHeading(TEXT.tagsHeading)
    await screen.findByRole('rowheader', { name: TAG.tag_name })
  },
}

/* ---- The walk ------------------------------------------------------------ */

/** An address without its query string. */
function pathnameOf(path) {
  return path.split('?')[0]
}

/**
 * `user` goes to `path` and ends on `page`, at `lands`: the same address unless the
 * application sends them on. `who` is for the test's name, which is put together
 * from two short parts because the runner cuts a longer one off.
 */
function walkCase(user, path, page, lands = pathnameOf(path)) {
  const sentOn = lands === pathnameOf(path) ? '' : `, sent on to ${lands}`
  return { user, path, page, lands, who: `an ${user.role}${sentOn}` }
}

/** A case for each role, at an address either may stay on. */
function asEachRole(path, page) {
  return BOTH_ROLES.map((user) => walkCase(user, path, page))
}

const WALK = [
  // Both dashboard paths, as each role: neither is guarded by role, so either
  // role can be on either (src/App.jsx).
  ...asEachRole('/dashboard', DASHBOARD),
  ...asEachRole('/admin', DASHBOARD),
  ...asEachRole('/upload', UPLOAD),
  ...asEachRole('/documents', DOCUMENTS),
  ...asEachRole(`/documents/${DOCUMENT.doc_id}`, DOCUMENT_DETAIL),
  ...asEachRole('/meetings', MEETINGS),
  ...asEachRole(`/meetings/${MEETING.meeting_id}`, MEETING_DETAIL),
  ...asEachRole(`/search?q=${SEARCH_TERM}`, SEARCH),
  ...asEachRole('/ask', ASK),
  // Outside RequireAuth: both render before the session check has answered.
  ...asEachRole('/components', COMPONENT_SHEET),
  ...asEachRole('/403', ACCESS_DENIED),
  // Behind RequireRole: the Administrator stays, and an Employee is sent to the
  // 403 page, having asked the API for nothing (tests/accessDenied.test.jsx).
  ...[
    ['/admin/roles', ROLE_MANAGEMENT],
    ['/admin/knowledge-gaps', KNOWLEDGE_GAPS],
    ['/admin/tags', TAGS],
  ].flatMap(([path, page]) => [walkCase(EMPLOYEE, path, ACCESS_DENIED, '/403'), walkCase(ADMINISTRATOR, path, page)]),
  // A signed-in user at any of these is sent on to their dashboard
  // (src/pages/Home.jsx, Login.jsx, Register.jsx).
  ...['/', '/login', '/register'].flatMap((path) =>
    BOTH_ROLES.map((user) => walkCase(user, path, DASHBOARD, HOME[user.role])),
  ),
]

/* ---- Rendering ----------------------------------------------------------- */

/** The router's current location, as the probe below last saw it. */
const probe = { location: null }

function LocationProbe() {
  const location = useLocation()
  // A layout effect, not a passive one: it runs inside the commit that rendered this
  // location, before a `findBy…` waiting on that commit can resolve.
  useLayoutEffect(() => {
    probe.location = location
  })
  return null
}

/** The whole application at a path: the real routes, the real guards, the real auth provider. */
function renderApp(path) {
  probe.location = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  )
  return probe
}

/** Signs `user` in, by answering the session check with them, and serves what a page asks for. */
function serveSignedIn(user, routes) {
  return serveApi({ 'GET /api/auth/me': { body: user }, ...routes })
}

/** The session check and the page's own routes, as `requested` gives them. */
function expectedRequests(...pages) {
  return ['GET /api/auth/me', ...pages.flatMap((page) => Object.keys(page.api))].sort()
}

/** Every route asked for, each once, sorted: told apart by what was asked, not by when. */
function requested(answered) {
  return [...new Set(answered.map((request) => `${request.method} ${request.path}`))].sort()
}

/**
 * The primary navigation, once it shows `user` signed in. A page outside
 * RequireAuth renders before the session check answers, so its heading alone
 * does not show the navigation has caught up.
 */
async function primaryNavigationFor(user) {
  const navigation = await screen.findByRole('navigation', { name: 'Primary' })
  await within(navigation).findByText(`Signed in as ${user.name}`)
  return navigation
}

/** Where every link named `TEXT.askNavLabel` in the navigation goes. */
function askLinkTargets(navigation) {
  return within(navigation)
    .queryAllByRole('link', { name: TEXT.askNavLabel })
    .map((link) => link.getAttribute('href'))
}

/* ---- Tests --------------------------------------------------------------- */

describe('FR-13: the Ask link is in the primary navigation of every page, for each role', () => {
  it.each(WALK)('$path as $who', async ({ user, path, page, lands }) => {
    const answered = serveSignedIn(user, page.api)
    const probe = renderApp(path)

    await page.settled()
    await waitFor(() => expect(probe.location?.pathname).toBe(lands))
    const navigation = await primaryNavigationFor(user)

    // Exactly one, and it goes to the Ask screen.
    expect(askLinkTargets(navigation)).toEqual(['/ask'])
    // The page asked for what its table names: nothing more (tests/setup.js fails
    // the test on a request nothing answers) and nothing less.
    expect(requested(answered)).toEqual(expectedRequests(page))
  })
})

describe('FR-13: the Ask link opens the Ask screen', () => {
  it.each([
    walkCase(EMPLOYEE, '/dashboard', DASHBOARD),
    walkCase(EMPLOYEE, `/documents/${DOCUMENT.doc_id}`, DOCUMENT_DETAIL),
    walkCase(ADMINISTRATOR, '/admin', DASHBOARD),
    walkCase(ADMINISTRATOR, '/admin/tags', TAGS),
  ])('from $path as $who', async ({ user, path, page, lands }) => {
    const answered = serveSignedIn(user, { ...page.api, ...ASK.api })
    const probe = renderApp(path)
    await page.settled()
    await waitFor(() => expect(probe.location?.pathname).toBe(lands))
    const navigation = await primaryNavigationFor(user)

    fireEvent.click(within(navigation).getByRole('link', { name: TEXT.askNavLabel }))

    await waitFor(() => expect(probe.location?.pathname).toBe('/ask'))
    await ASK.settled()
    // The Ask screen with no thread named, in place of the page the link was on.
    expect(probe.location.search).toBe('')
    expect(screen.getAllByRole('heading', { level: 1 }).map((heading) => heading.textContent)).toEqual([TEXT.askHeading])
    expect(requested(answered)).toEqual(expectedRequests(page, ASK))
  })
})

describe('the walk is held to the route table', () => {
  it('has a case, as each role, for every path in the route table of src/App.jsx', () => {
    const source = readFileSync(join(import.meta.dirname, '..', 'src', 'App.jsx'), 'utf8')
    const declared = [...source.matchAll(/\bpath="([^"]+)"/g)].map((match) => match[1])
    // Every `path=` in the file was read. One written another way (`path={…}`)
    // fails here rather than being skipped. The index route has no path, and is
    // walked as `/`.
    expect(declared).toHaveLength(source.match(/\bpath=/g).length)

    for (const user of BOTH_ROLES) {
      const walked = WALK.filter((walk) => walk.user === user).map((walk) => pathnameOf(walk.path))
      const unwalked = declared.filter((pattern) => !walked.some((pathname) => matchPath(`/${pattern}`, pathname)))
      expect(unwalked, `paths in src/App.jsx with no case as an ${user.role}`).toEqual([])
    }
  })
})
