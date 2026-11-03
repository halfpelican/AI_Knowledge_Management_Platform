/**
 * FR-12's search half, at the interface.
 *
 * - "A search field available from every page, returning results grouped by type
 *   (Documents and Meetings) with a count per group. Each result shows its title, the
 *   matching passage as a snippet, its department, and its date."
 * - Validation: "queries shorter than two characters are rejected client-side".
 *
 * The counts are the server's, computed after permission filtering (FR-11), and the
 * screen renders them as they arrive; that they disclose nothing is pytest's. The
 * minimum's agreement with the server's `MINIMUM_SEARCH_LENGTH` is
 * apps/api/tests/test_front_end_constants_agreement.py. This file does not test
 * "available from every page": the field is used here from the dashboard and the
 * search screen only.
 *
 * The whole application is rendered, signed in, with the real auth provider.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { ROLES, TEXT } from '../src/constants.js'
import { formatDate } from '../src/utils/dates.js'
import { serveApi } from './fakeApi.js'

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

const EMPTY_DASHBOARD = {
  filters: { date_from: null, date_to: null, department: null },
  departments: [],
  indexed_totals: { documents: 0, meetings: 0, total: 0 },
  recent_documents: [],
  recent_meetings: [],
  recent_questions: [],
}

/** FR-12's refusal, naming the minimum, written out so a change to it fails here. */
const TOO_SHORT = 'Enter at least 2 characters to search.'

const LEAVE_POLICY = {
  source_type: 'document',
  source_id: 'doc-1',
  title: 'Leave policy 2026',
  snippet: 'Full-time staff accrue four weeks of annual leave per year.',
  department: 'Human Resources',
  date: '2026-08-01T10:00:00+10:00',
}

const PAYROLL_GUIDE = {
  source_type: 'document',
  source_id: 'doc-2',
  title: 'Payroll guide',
  snippet: 'Leave loading is paid with the first pay run of December.',
  department: 'Finance',
  date: '2026-06-15T09:00:00+10:00',
}

const HR_SYNC = {
  source_type: 'meeting',
  source_id: 'meeting-1',
  title: 'HR planning sync',
  snippet: 'Sam: the leave calendar for Q4 goes out on Monday.',
  department: '',
  date: '2026-07-28',
}

function searchReply(term, documents, meetings) {
  return {
    query: term,
    documents: { count: documents.length, results: documents },
    meetings: { count: meetings.length, results: meetings },
    total_count: documents.length + meetings.length,
  }
}

/** The router's current location, as the probe below last saw it. */
const probe = { location: null }

function LocationProbe() {
  const location = useLocation()
  // A layout effect, so the location is current before a `findBy…` waiting on the
  // same commit resolves (a passive effect runs a task later).
  useLayoutEffect(() => {
    probe.location = location
  })
  return null
}

function renderApp(path) {
  probe.location = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  )
}

function searches(answered) {
  return answered.filter((request) => request.path === '/api/search').map((request) => request.search)
}

/** One of the two groups, found by its heading's leading words. */
function group(heading) {
  return screen.getByRole('region', { name: new RegExp(`^${heading} `) })
}

describe('FR-12: queries shorter than two characters are rejected client-side', () => {
  it('refuses one character from the header field with a message naming the minimum, sends nothing, and searches at two', async () => {
    const answered = serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
      'GET /api/search': (url) => ({ body: searchReply(url.searchParams.get('q'), [], []) }),
    })
    renderApp('/dashboard')
    await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })

    const header = screen.getByRole('search', { name: TEXT.searchNavLabel })
    const field = within(header).getByLabelText(TEXT.searchFieldLabel)
    fireEvent.change(field, { target: { value: 'a' } })
    fireEvent.click(within(header).getByRole('button', { name: TEXT.searchSubmit }))

    expect(within(header).getByText(TOO_SHORT)).toBeTruthy()
    expect(field.getAttribute('aria-invalid')).toBe('true')
    expect(probe.location.pathname).toBe('/dashboard')

    // Typing clears the refusal; two characters is the minimum, and is searched.
    fireEvent.change(field, { target: { value: 'ab' } })
    expect(within(header).queryByText(TOO_SHORT)).toBeNull()
    fireEvent.click(within(header).getByRole('button', { name: TEXT.searchSubmit }))

    await screen.findByRole('heading', { level: 2, name: TEXT.searchResultsFor('ab') })
    expect(probe.location.pathname).toBe('/search')
    expect(probe.location.search).toBe('?q=ab')
    expect(searches(answered)).toEqual(['?q=ab'])
  })

  it('refuses a one-character term typed into the address without sending it', async () => {
    // Nothing answers /api/search, so a request for it fails the test.
    const answered = serveApi({ 'GET /api/auth/me': { body: EMPLOYEE } })
    renderApp('/search?q=x')

    const refusal = (await screen.findByText(TEXT.searchFailed)).closest('[role="alert"]')
    expect(refusal.textContent).toContain(TOO_SHORT)
    expect(screen.queryByText(TEXT.searchResultsFor('x'))).toBeNull()
    expect(searches(answered)).toEqual([])
  })
})

describe('FR-12: results grouped by type, with a count per group', () => {
  it('puts documents and meetings in their own groups, each headed by its count, each result with its title, snippet, department and date', async () => {
    const answered = serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/search': { body: searchReply('leave', [LEAVE_POLICY, PAYROLL_GUIDE], [HR_SYNC]) },
    })
    renderApp('/search?q=leave')

    await screen.findByRole('heading', { level: 2, name: TEXT.searchResultsFor('leave') })
    const documents = group(TEXT.searchDocumentsHeading)
    const meetings = group(TEXT.searchMeetingsHeading)
    expect(within(documents).getByRole('heading', { level: 3 }).textContent).toBe('Documents 2 results')
    expect(within(meetings).getByRole('heading', { level: 3 }).textContent).toBe('Meeting transcripts 1 result')

    expect(within(documents).getAllByRole('article').map((item) => within(item).getByRole('heading').textContent)).toEqual([
      LEAVE_POLICY.title,
      PAYROLL_GUIDE.title,
    ])
    expect(within(meetings).getAllByRole('article').map((item) => within(item).getByRole('heading').textContent)).toEqual([
      HR_SYNC.title,
    ])

    for (const [region, result, href, department] of [
      [documents, LEAVE_POLICY, '/documents/doc-1', 'Human Resources'],
      [documents, PAYROLL_GUIDE, '/documents/doc-2', 'Finance'],
      [meetings, HR_SYNC, '/meetings/meeting-1', '—'],
    ]) {
      const item = within(region).getByRole('link', { name: result.title }).closest('article')
      expect(within(item).getByRole('link', { name: result.title }).getAttribute('href')).toBe(href)
      expect(item.textContent).toContain(result.snippet)
      expect(item.textContent).toContain(`Department: ${department}`)
      expect(item.querySelector('time').getAttribute('dateTime')).toBe(result.date)
      expect(item.querySelector('time').textContent).toBe(formatDate(result.date))
    }

    expect(screen.getByText('3 results for leave.')).toBeTruthy()
    expect(searches(answered)).toEqual(['?q=leave'])
  })

  it('keeps both groups on screen at a count of zero when nothing matched, and says so plainly rather than as an error', async () => {
    serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/search': { body: searchReply('quarterly', [], []) },
    })
    renderApp('/search?q=quarterly')

    await screen.findByRole('heading', { level: 2, name: TEXT.searchResultsFor('quarterly') })
    const documents = group(TEXT.searchDocumentsHeading)
    const meetings = group(TEXT.searchMeetingsHeading)
    expect(within(documents).getByRole('heading', { level: 3 }).textContent).toBe('Documents 0 results')
    expect(within(meetings).getByRole('heading', { level: 3 }).textContent).toBe('Meeting transcripts 0 results')
    expect(documents.textContent).toContain(TEXT.searchGroupEmptyDocuments)
    expect(meetings.textContent).toContain(TEXT.searchGroupEmptyMeetings)
    expect(screen.queryAllByRole('article')).toHaveLength(0)

    await waitFor(() => expect(screen.getByText(TEXT.searchNothingMatched('quarterly'))).toBeTruthy())
    expect(screen.getByText(TEXT.searchNothingMatched('quarterly')).closest('[role="status"]')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
