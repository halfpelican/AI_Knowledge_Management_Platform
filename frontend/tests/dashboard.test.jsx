/**
 * The FR-14 dashboard, rendered against a faked `GET /api/dashboard`
 * (docs/api-contract.md, "Stage 5 — FR-14, FR-15 / FR-14 — dashboard").
 *
 * Each test defends one clause only the interface can satisfy — what the screen
 * shows, withholds or offers. Scoping, counting after permission filtering and
 * the 401 are the server's and are tested in pytest; nothing here stands in for
 * them, and the screen filters nothing itself.
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { useEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { dashboardPathForRole, ROLES, TEXT } from '../src/constants.js'
import Dashboard from '../src/pages/Dashboard.jsx'
import { formatDate } from '../src/utils/dates.js'
import { serveApi } from './fakeApi.js'

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
  title: 'Q3 Planning Sync',
  meeting_date: '2026-07-28',
  status: 'Indexed',
  created_at: '2026-09-21T10:00:00+10:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: ['erin@example.com'],
}

const QUESTION = {
  question: 'How is annual leave accrued?',
  asked_at: '2026-09-14T10:02:11+10:00',
  conversation_id: null,
}

/** The contract's 200, with one of each item and totals that tell the three figures apart. */
function dashboardPayload(overrides = {}) {
  return {
    filters: { date_from: null, date_to: null, department: null },
    departments: ['Finance', 'Human Resources', 'Operations'],
    indexed_totals: { documents: 4, meetings: 2, total: 6 },
    recent_documents: [DOCUMENT],
    recent_meetings: [MEETING],
    recent_questions: [QUESTION],
    ...overrides,
  }
}

/** The contract's 200 when the caller can see nothing and has asked nothing. */
function emptyPayload() {
  return {
    filters: { date_from: null, date_to: null, department: null },
    departments: [],
    indexed_totals: { documents: 0, meetings: 0, total: 0 },
    recent_documents: [],
    recent_meetings: [],
    recent_questions: [],
  }
}

/** A dashboard route that echoes the filters it was sent, as the server's `filters` does. */
function echoingDashboard(url) {
  const param = (key) => url.searchParams.get(key) || null
  return {
    body: dashboardPayload({
      filters: { date_from: param('date_from'), date_to: param('date_to'), department: param('department') },
    }),
  }
}

/** The query string of every dashboard request, in order. */
function dashboardQueries(answered) {
  return answered.filter((request) => request.path === '/api/dashboard').map((request) => request.search)
}

/** Heading, and the loading text each panel shows while the request is in flight. */
const PANELS = [
  [TEXT.dashboardDocumentsHeading, TEXT.dashboardLoadingDocuments],
  [TEXT.dashboardMeetingsHeading, TEXT.dashboardLoadingMeetings],
  [TEXT.dashboardTotalsHeading, TEXT.dashboardLoadingTotals],
  [TEXT.dashboardQuestionsHeading, TEXT.dashboardLoadingQuestions],
]

function panel(heading) {
  return screen.getByRole('region', { name: heading })
}

/** Each indexed-total figure by its label: `{Documents: '4', ...}`. */
function figures(region) {
  return Object.fromEntries(
    Array.from(region.querySelectorAll('dt')).map((term) => [term.textContent, term.nextElementSibling.textContent]),
  )
}

/** The dashboard page alone, at a path under /dashboard. */
function renderDashboard(path = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
      </Routes>
    </MemoryRouter>,
  )
}

/** The router's current location and its Back, as the probe below last saw them. */
const probe = { location: null, back: null }

/** Exposes the router's location and Back to the test, from inside the router. */
function HistoryProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => {
    probe.location = location
    probe.back = () => navigate(-1)
  })
  return null
}

/** The whole application at a path: the real routes, the real auth provider. */
function renderApp(path) {
  probe.location = null
  probe.back = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <HistoryProbe />
    </MemoryRouter>,
  )
  return probe
}

/** True where nothing on the path from the node to the root hides it. */
function isOnScreen(node) {
  for (let current = node; current; current = current.parentElement) {
    if (current.hidden || current.classList?.contains('visually-hidden')) return false
  }
  return true
}

describe('FR-14: the landing page after login', () => {
  it.each([
    { path: '/dashboard', user: EMPLOYEE },
    { path: '/admin', user: ADMINISTRATOR },
    { path: '/', user: EMPLOYEE },
    { path: '/', user: ADMINISTRATOR },
  ])('renders the dashboard at $path for an $user.role', async ({ path, user }) => {
    // FR-02 sends an Employee to /dashboard and an Administrator to /admin, and
    // both have to land on the dashboard (D-70). A signed-in user reaching / is
    // sent to theirs rather than shown a placeholder.
    const answered = serveApi({
      'GET /api/auth/me': { body: user },
      'GET /api/dashboard': { body: dashboardPayload() },
    })
    const probe = renderApp(path)

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })).toBeTruthy()
    await screen.findByText(DOCUMENT.title)
    expect(probe.location.pathname).toBe(path === '/' ? dashboardPathForRole(user.role) : path)
    expect(document.body.textContent).not.toMatch(/under construction|alpha build/i)
    expect(dashboardQueries(answered)).toEqual([''])
  })

  it('offers an anonymous visitor sign-in and registration at /, without a placeholder', async () => {
    const answered = serveApi({ 'GET /api/auth/me': { status: 401, body: { detail: 'Not signed in.' } } })
    renderApp('/')

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.homeHeading })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'create an account' }).getAttribute('href')).toBe('/register')
    expect(document.body.textContent).not.toMatch(/under construction|alpha build/i)
    // No dashboard request for a visitor with no session.
    expect(dashboardQueries(answered)).toEqual([])
  })
})

describe('FR-14: panels show a loading state while data is retrieved', () => {
  it('shows every panel loading until the one request answers, then its content', async () => {
    let release
    const gate = new Promise((resolve) => {
      release = resolve
    })
    const answered = serveApi({
      'GET /api/dashboard': async () => {
        await gate
        return { body: dashboardPayload() }
      },
    })
    renderDashboard()

    // Words in a status region in each panel, not a spinner alone (WCAG 2.1 SC 1.1.1).
    for (const [heading, loadingText] of PANELS) {
      expect(within(panel(heading)).getByRole('status').textContent).toBe(loadingText)
    }

    release()
    await screen.findByText(DOCUMENT.title)

    for (const [heading] of PANELS) {
      expect(within(panel(heading)).queryByRole('status')).toBeNull()
    }
    expect(within(panel(TEXT.dashboardMeetingsHeading)).getByText(MEETING.title)).toBeTruthy()
    expect(within(panel(TEXT.dashboardQuestionsHeading)).getByText(QUESTION.question)).toBeTruthy()
    expect(figures(panel(TEXT.dashboardTotalsHeading))[TEXT.dashboardTotalsDocuments]).toBe('4')
    // FR-14's Server-End clause: one request for the whole page, never one per panel.
    expect(answered.map((request) => request.path)).toEqual(['/api/dashboard'])
  })

  it('shows the loading state again when a filter is applied, not the previous reply', async () => {
    // The first reply is let straight through; the one for the new filter is held.
    let gate = Promise.resolve()
    let release
    serveApi({
      'GET /api/dashboard': async (url) => {
        await gate
        return echoingDashboard(url)
      },
    })
    renderDashboard()
    await screen.findByText(DOCUMENT.title)

    gate = new Promise((resolve) => {
      release = resolve
    })
    fireEvent.change(screen.getByLabelText(TEXT.dashboardDepartment), { target: { value: 'Finance' } })
    fireEvent.click(screen.getByRole('button', { name: TEXT.dashboardApplyFilters }))

    // A reply for the old filters, left on screen under the new one, would be the
    // panels claiming to show something they do not.
    for (const [heading, loadingText] of PANELS) {
      expect(within(panel(heading)).getByRole('status').textContent).toBe(loadingText)
    }
    expect(screen.queryByText(DOCUMENT.title)).toBeNull()

    release()
    expect(await screen.findByText(TEXT.dashboardDepartmentApplied('Finance'))).toBeTruthy()
    expect(screen.getByText(DOCUMENT.title)).toBeTruthy()
  })
})

describe('FR-14: each panel links through to its full view', () => {
  it('links each panel heading, each figure and each item to the module that owns it', async () => {
    serveApi({ 'GET /api/dashboard': { body: dashboardPayload() } })
    renderDashboard()
    await screen.findByText(DOCUMENT.title)

    const href = (region, name) => within(region).getByRole('link', { name }).getAttribute('href')
    const documents = panel(TEXT.dashboardDocumentsHeading)
    const meetings = panel(TEXT.dashboardMeetingsHeading)
    const totals = panel(TEXT.dashboardTotalsHeading)
    const questions = panel(TEXT.dashboardQuestionsHeading)

    expect(href(documents, TEXT.dashboardDocumentsHeading)).toBe('/documents')
    expect(href(documents, DOCUMENT.title)).toBe(`/documents/${DOCUMENT.doc_id}`)
    expect(href(meetings, TEXT.dashboardMeetingsHeading)).toBe('/meetings')
    expect(href(meetings, MEETING.title)).toBe(`/meetings/${MEETING.meeting_id}`)
    expect(href(totals, TEXT.dashboardTotalsDocuments)).toBe('/documents')
    expect(href(totals, TEXT.dashboardTotalsMeetings)).toBe('/meetings')
    expect(href(questions, TEXT.dashboardQuestionsHeading)).toBe('/ask')
  })
})

describe('D-70: the indexed total, split by type', () => {
  it('shows the documents figure, the meetings figure and their sum, each as the server sent it', async () => {
    serveApi({
      'GET /api/dashboard': {
        // A sum the screen could not have produced by adding, so the test can tell
        // the server's `total` from one computed here.
        body: dashboardPayload({ indexed_totals: { documents: 4, meetings: 2, total: 6 } }),
      },
    })
    renderDashboard()
    await screen.findByText(DOCUMENT.title)

    expect(figures(panel(TEXT.dashboardTotalsHeading))).toEqual({
      [TEXT.dashboardTotalsDocuments]: '4',
      [TEXT.dashboardTotalsMeetings]: '2',
      [TEXT.dashboardTotalsSum]: '6',
    })
  })
})

describe('D-70: the filters say what they do', () => {
  it('states next to the department control that it applies to documents only', async () => {
    serveApi({ 'GET /api/dashboard': { body: dashboardPayload() } })
    renderDashboard()
    await screen.findByText(DOCUMENT.title)

    const select = screen.getByLabelText(TEXT.dashboardDepartment)
    const describedBy = select.getAttribute('aria-describedby').split(' ')
    const note = describedBy.map((id) => document.getElementById(id)).find((node) => node?.textContent === TEXT.dashboardDepartmentHint)
    expect(note).toBeTruthy()
    expect(isOnScreen(note)).toBe(true)
    // The offered departments are the server's list, plus "All departments", and nothing else.
    expect(Array.from(select.options).map((option) => option.textContent)).toEqual([
      TEXT.dashboardAllDepartments,
      'Finance',
      'Human Resources',
      'Operations',
    ])
  })

  it('shows "All dates" when no range is applied', async () => {
    serveApi({ 'GET /api/dashboard': { body: dashboardPayload() } })
    renderDashboard()
    await screen.findByText(DOCUMENT.title)

    const active = screen.getByText(TEXT.dashboardActiveDates).closest('p')
    expect(within(active).getByText(TEXT.dashboardAllDates)).toBeTruthy()
    expect(within(active).getByText(TEXT.dashboardAllDepartments)).toBeTruthy()
  })

  it('shows the active range and department the server applied', async () => {
    serveApi({ 'GET /api/dashboard': echoingDashboard })
    renderDashboard('/dashboard?date_from=2026-09-01&date_to=2026-09-30&department=Finance')
    await screen.findByText(DOCUMENT.title)

    const active = screen.getByText(TEXT.dashboardActiveDates).closest('p')
    expect(
      within(active).getByText(TEXT.dashboardRangeBetween(formatDate('2026-09-01'), formatDate('2026-09-30'))),
    ).toBeTruthy()
    expect(within(active).getByText(TEXT.dashboardDepartmentApplied('Finance'))).toBeTruthy()
  })
})

describe('D-61 gap 3: the filters live in the address', () => {
  it('restores the filters and re-sends the same request after following a panel link and pressing Back', async () => {
    const answered = serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/dashboard': echoingDashboard,
      'GET /api/documents': { body: [] },
    })
    const probe = renderApp('/dashboard')
    await screen.findByText(DOCUMENT.title)

    fireEvent.change(screen.getByLabelText(TEXT.dashboardDateFrom), { target: { value: '2026-09-01' } })
    fireEvent.change(screen.getByLabelText(TEXT.dashboardDateTo), { target: { value: '2026-09-30' } })
    fireEvent.change(screen.getByLabelText(TEXT.dashboardDepartment), { target: { value: 'Finance' } })
    fireEvent.click(screen.getByRole('button', { name: TEXT.dashboardApplyFilters }))

    const filtered = '?date_from=2026-09-01&date_to=2026-09-30&department=Finance'
    await screen.findByText(TEXT.dashboardDepartmentApplied('Finance'))
    expect(probe.location.search).toBe(filtered)
    expect(dashboardQueries(answered)).toEqual(['', filtered])

    // Into the module the panel owns, and back again.
    const documents = panel(TEXT.dashboardDocumentsHeading)
    fireEvent.click(within(documents).getByRole('link', { name: TEXT.dashboardDocumentsHeading }))
    await screen.findByRole('heading', { level: 1, name: 'Documents' })
    expect(probe.location.pathname).toBe('/documents')

    act(() => probe.back())
    await screen.findByText(TEXT.dashboardDepartmentApplied('Finance'))

    expect(probe.location.pathname).toBe('/dashboard')
    expect(probe.location.search).toBe(filtered)
    expect(screen.getByLabelText(TEXT.dashboardDateFrom).value).toBe('2026-09-01')
    expect(screen.getByLabelText(TEXT.dashboardDateTo).value).toBe('2026-09-30')
    expect(screen.getByLabelText(TEXT.dashboardDepartment).value).toBe('Finance')
    expect(dashboardQueries(answered)).toEqual(['', filtered, filtered])
  })
})

describe('FR-14 filter validation', () => {
  it('refuses a start date after the end date before sending anything', async () => {
    const answered = serveApi({ 'GET /api/dashboard': { body: dashboardPayload() } })
    renderDashboard()
    await screen.findByText(DOCUMENT.title)

    fireEvent.change(screen.getByLabelText(TEXT.dashboardDateFrom), { target: { value: '2026-09-30' } })
    fireEvent.change(screen.getByLabelText(TEXT.dashboardDateTo), { target: { value: '2026-09-01' } })
    fireEvent.click(screen.getByRole('button', { name: TEXT.dashboardApplyFilters }))

    expect(await screen.findByText(TEXT.dashboardRangeInverted)).toBeTruthy()
    const dateTo = screen.getByLabelText(TEXT.dashboardDateTo)
    expect(dateTo.getAttribute('aria-invalid')).toBe('true')
    expect(document.activeElement).toBe(dateTo)
    expect(dashboardQueries(answered)).toEqual([''])
  })

  it('refuses an inverted range typed into the address without sending it', async () => {
    const answered = serveApi({ 'GET /api/dashboard': { body: dashboardPayload() } })
    renderDashboard('/dashboard?date_from=2026-09-30&date_to=2026-09-01')

    // Once in the alert above the panels, once under the control.
    expect(await screen.findAllByText(TEXT.dashboardRangeInverted)).toHaveLength(2)
    expect(screen.getByRole('alert').textContent).toContain(TEXT.dashboardLoadFailed)
    expect(dashboardQueries(answered)).toEqual([])
  })

  it("shows a 400's message under the control it names", async () => {
    const message = 'Enter a valid date.'
    serveApi({ 'GET /api/dashboard': { status: 400, body: { date_from: [message] } } })
    renderDashboard('/dashboard?date_from=2026-02-30')

    expect(await screen.findByText(message)).toBeTruthy()
    const dateFrom = screen.getByLabelText(TEXT.dashboardDateFrom)
    expect(dateFrom.getAttribute('aria-invalid')).toBe('true')
    const description = dateFrom
      .getAttribute('aria-describedby')
      .split(' ')
      .map((id) => document.getElementById(id)?.textContent ?? '')
      .join(' ')
    expect(description).toContain(message)
    expect(screen.getByRole('alert').textContent).toContain(TEXT.dashboardLoadFailed)
  })
})

describe('FR-14 empty and failed states', () => {
  it('renders each panel empty, and zero in each figure, for an empty payload', async () => {
    serveApi({ 'GET /api/dashboard': { body: emptyPayload() } })
    renderDashboard()

    expect(await screen.findByText(TEXT.dashboardNoDocuments)).toBeTruthy()
    expect(within(panel(TEXT.dashboardDocumentsHeading)).getByText(TEXT.dashboardNoDocuments)).toBeTruthy()
    expect(within(panel(TEXT.dashboardMeetingsHeading)).getByText(TEXT.dashboardNoMeetings)).toBeTruthy()
    expect(within(panel(TEXT.dashboardQuestionsHeading)).getByText(TEXT.dashboardNoQuestions)).toBeTruthy()
    expect(figures(panel(TEXT.dashboardTotalsHeading))).toEqual({
      [TEXT.dashboardTotalsDocuments]: '0',
      [TEXT.dashboardTotalsMeetings]: '0',
      [TEXT.dashboardTotalsSum]: '0',
    })
    // Empty is an ordinary state, not an error.
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('renders an error notice for a failed request, never the backend text, and retries', async () => {
    let attempts = 0
    const backendText = 'Traceback (most recent call last): relation "documents" does not exist'
    serveApi({
      'GET /api/dashboard': () => {
        attempts += 1
        return attempts === 1 ? { status: 500, body: { detail: backendText } } : { body: dashboardPayload() }
      },
    })
    renderDashboard()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.dashboardLoadFailed)
    expect(document.body.textContent).not.toContain(backendText)
    for (const [heading] of PANELS) {
      expect(within(panel(heading)).getByText(TEXT.dashboardPanelUnavailable)).toBeTruthy()
    }

    fireEvent.click(screen.getByRole('button', { name: TEXT.uploadRetry }))
    expect(await screen.findByText(DOCUMENT.title)).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('D-68: recent questions are the question only', () => {
  /** The questions panel's markup for a payload carrying the given question rows. */
  async function questionsPanelFor(rows) {
    serveApi({ 'GET /api/dashboard': { body: dashboardPayload({ recent_questions: rows }) } })
    const { unmount } = renderDashboard()
    await screen.findByText(DOCUMENT.title)
    const html = panel(TEXT.dashboardQuestionsHeading).innerHTML
    unmount()
    return html
  }

  it('renders the question and when it was asked, and nothing that looks like an answer', async () => {
    // The row as if a regression had put QueryLog's other columns on the wire. The
    // panel must render it byte-for-byte as it renders the contract's row: no
    // answer text, no answered or unanswered marker, no reason.
    const answerText = 'Annual leave accrues at four weeks a year.'
    const leaking = {
      ...QUESTION,
      answer_text: answerText,
      answered: true,
      no_answer_reason: 'no_passage_above_threshold',
      rejected_count: 2,
      retrieved_chunk_ids: ['chunk-a'],
    }

    const clean = await questionsPanelFor([QUESTION])
    const withAnswer = await questionsPanelFor([leaking])

    expect(withAnswer).toBe(clean)
    expect(withAnswer).not.toContain(answerText)
    expect(clean).toContain(QUESTION.question)
    expect(clean).toContain(`datetime="${QUESTION.asked_at}"`)
    expect(clean).not.toMatch(/answer|cited|citation|source/i)
  })
})
