/**
 * The route walk: the whole application at every path in src/App.jsx's route table,
 * and at `/`, once as an Employee and once as an Administrator.
 *
 * Two requirements have a clause about every page, and each keeps its own
 * assertions in its own file. Both import the walk from here, so there is one
 * table of cases:
 *
 * - tests/askNavLink.test.jsx, FR-13: "A conversational interface reachable from
 *   any page". The walk was written there on 11 November 2026 and moved here
 *   unchanged the next day.
 * - tests/headerSearchField.test.jsx, FR-12: "A search field available from every
 *   page".
 *
 * This is not a test file: the runner collects `tests/**\/*.test.{js,jsx}`
 * (vite.config.js) and so does not run it.
 *
 * **Each case** says who goes where, which page they end on and at what address.
 * Where the application sends the user on, the case says where: `/`, `/login` and
 * `/register` send a signed-in user to their dashboard, and the three
 * Administrator-only paths send an Employee to `/403`.
 *
 * **Each page** names the routes it asks the API for and no others: a request
 * nothing answers fails the test (tests/setup.js), and a test can hold what was
 * asked against `expectedRequests`. The replies are the same for both roles: what a
 * server would send each differently (scope, `can_delete`) plays no part in what
 * the shell shows.
 *
 * **The walk is held to the route table** by tests/askNavLink.test.jsx :: has a
 * case, as each role, for every path in the route table of src/App.jsx. A route
 * added there without a case here fails that test.
 *
 * What the walk cannot reach, for either file:
 *
 * - **Whether anything can be seen.** jsdom applies no stylesheet. The walk
 *   asserts nothing about the stylesheets; tests/tabOrder.test.jsx does, for the
 *   keyboard stops on the screens it walks.
 * - **An anonymous visitor.** Every case is signed in.
 * - **An address no route matches.** It is not a page, and it is not walked.
 * - **Which roles a new route admits.** The route-table test cannot read a guard
 *   from the source, so it asks for a case as each role and the case says where
 *   that role lands.
 *
 * The location is read by a probe in a layout effect and asserted in `waitFor`
 * (tests/dashboard.test.jsx says why).
 */
import { render, screen, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import App from '../src/App.jsx'
import { ROLES, TEXT } from '../src/constants.js'
import { serveApi, summaryRoute, summaryState } from './fakeApi.js'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

export const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

export const ADMINISTRATOR = {
  id: 'user-administrator',
  name: 'Ada Administrator',
  email: 'ada@example.com',
  role: ROLES.administrator,
  created_at: '2026-09-12T10:00:00+10:00',
}

export const BOTH_ROLES = [EMPLOYEE, ADMINISTRATOR]

/** FR-02's destination for each role, written out so a change to it fails here. */
const HOME = { [ROLES.employee]: '/dashboard', [ROLES.administrator]: '/admin' }

export const DOCUMENT = {
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

/** The term the search page's reply is for. */
export const SEARCH_TERM = 'leave'

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
export const DASHBOARD = {
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
  // navigation, which is why the Ask link is looked for inside the landmark.
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

export const DOCUMENT_DETAIL = {
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

// Since FR-16 the meeting page asks for the meeting's summary as well as the meeting (D-125). The
// walk answers it with a meeting nobody has asked a summary of, and offers no controls, which is
// the same for both roles; the page has settled once the Summary panel says so.
const MEETING_DETAIL = {
  api: {
    [`GET /api/meetings/${MEETING.meeting_id}`]: {
      body: { ...MEETING, transcript_text: 'Alex: the supplier review is due on Friday.', can_delete: false },
    },
    [`GET /api/meetings/${MEETING.meeting_id}/summary`]: summaryRoute(summaryState()),
  },
  async settled() {
    await pageHeading(MEETING.title)
    await screen.findByText(TEXT.summaryNone)
  },
}

// It has a search field of its own, in the page and under the same names as the
// header's, which is why the header's is looked for inside the banner.
export const SEARCH = {
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

export const ASK = {
  api: { 'GET /api/conversations': { body: [CONVERSATION] } },
  async settled() {
    await pageHeading(TEXT.askHeading)
    await screen.findByRole('button', { name: TEXT.conversationOpen(CONVERSATION.title) })
  },
}

// It shows a search field too, as one of the components on the sheet.
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

export const TAGS = {
  api: { 'GET /api/tags': { body: [TAG] } },
  async settled() {
    await pageHeading(TEXT.tagsHeading)
    await screen.findByRole('rowheader', { name: TAG.tag_name })
  },
}

/* ---- The walk ------------------------------------------------------------ */

/** An address without its query string. */
export function pathnameOf(path) {
  return path.split('?')[0]
}

/**
 * `user` goes to `path` and ends on `page`, at `lands`: the same address unless the
 * application sends them on. `who` is for the test's name, which is put together
 * from two short parts because the runner cuts a longer one off.
 */
export function walkCase(user, path, page, lands = pathnameOf(path)) {
  const sentOn = lands === pathnameOf(path) ? '' : `, sent on to ${lands}`
  return { user, path, page, lands, who: `an ${user.role}${sentOn}` }
}

/** A case for each role, at an address either may stay on. */
function asEachRole(path, page) {
  return BOTH_ROLES.map((user) => walkCase(user, path, page))
}

export const WALK = [
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

// The rule is for Fast Refresh, which wants a module with a component in it to
// export nothing but components. Nothing hot-reloads this module: it is test
// support, and `renderApp` below is the component's only user.
// oxlint-disable-next-line react/only-export-components
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
export function renderApp(path) {
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
export function serveSignedIn(user, routes) {
  return serveApi({ 'GET /api/auth/me': { body: user }, ...routes })
}

/** The session check and the page's own routes, as `requested` gives them. */
export function expectedRequests(...pages) {
  return ['GET /api/auth/me', ...pages.flatMap((page) => Object.keys(page.api))].sort()
}

/** Every route asked for, each once, sorted: told apart by what was asked, not by when. */
export function requested(answered) {
  return [...new Set(answered.map((request) => `${request.method} ${request.path}`))].sort()
}

/**
 * The primary navigation, once it shows `user` signed in. A page outside
 * RequireAuth renders before the session check answers, so its heading alone
 * does not show the shell has caught up.
 */
export async function primaryNavigationFor(user) {
  const navigation = await screen.findByRole('navigation', { name: 'Primary' })
  await within(navigation).findByText(`Signed in as ${user.name}`)
  return navigation
}
