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
 * search screen only. tests/headerSearchField.test.jsx walks the routes for it.
 *
 * Since D-139 it also holds FR-10's clause about these results: a document's summary
 * and key points "shown beneath the title in search results". The same block on the
 * document page is tests/documentSummary.test.jsx's.
 *
 * The whole application is rendered, signed in, with the real auth provider.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { ROLES, SEARCH_MAXIMUM_LENGTH, TEXT } from '../src/constants.js'
import { formatDate } from '../src/utils/dates.js'
import { serveApi } from './fakeApi.js'
import { hidingCauses, rulesMatching } from './stylesheets.js'

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

/** The upper bound's refusal (D-79's note of 10 November 2026), written out likewise. */
const TOO_LONG = 'A search term can be at most 500 characters.'

/** The client's text for a rate-limit 429 on a screen that does not name its own. */
const RATE_LIMITED = 'Too many requests in a short time. Please wait and try again.'

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

describe("The search limits: a term's upper bound and the per-user rate (D-79's note of 10 November 2026)", () => {
  it('refuses a term over the maximum typed into the address without sending it', async () => {
    // Nothing answers /api/search, so a request for it fails the test.
    const answered = serveApi({ 'GET /api/auth/me': { body: EMPLOYEE } })
    renderApp(`/search?q=${'a'.repeat(SEARCH_MAXIMUM_LENGTH + 1)}`)

    const refusal = (await screen.findByText(TEXT.searchFailed)).closest('[role="alert"]')
    expect(refusal.textContent).toContain(TOO_LONG)
    expect(searches(answered)).toEqual([])
  })

  it('searches a term at the maximum', async () => {
    const longest = 'a'.repeat(SEARCH_MAXIMUM_LENGTH)
    const answered = serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/search': { body: searchReply(longest, [], []) },
    })
    renderApp(`/search?q=${longest}`)

    expect(await screen.findByText(TEXT.searchResultsFor(longest))).toBeTruthy()
    expect(searches(answered)).toEqual([`?q=${longest}`])
  })

  it('says the rate was reached when the server throttles a search, and offers to try again', async () => {
    serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/search': {
        status: 429,
        body: { detail: 'Request was throttled. Expected available in 20 seconds.' },
        headers: { 'Retry-After': '20' },
      },
    })
    renderApp('/search?q=leave')

    const notice = (await screen.findByText(TEXT.searchFailed)).closest('[role="alert"]')
    expect(notice.textContent).toContain(RATE_LIMITED)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
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

/* ---- FR-10: the summary and key points beneath the title (D-139) ----------- */

/**
 * FR-10 Front-End: "Each document displays a short summary and a list of key points,
 * shown beneath the title in search results so users can judge relevance before
 * opening the file." And its Validation: a long document is never "summarised from a
 * fragment without the user being told". NFR-15 marks both as AI content.
 *
 * What a summary says, how many key points there are, and which results carry one are
 * the server's, and pytest's. These tests defend what only the screen can: where the
 * summary sits, that it is marked, that the user is told when it covers part of a
 * document, and that a result without one looks as it did before the field.
 */

/** NFR-15's mark, written out, so a change to its words fails here. */
const SUGGESTED_BY_AI = 'Suggested by AI'

/** FR-10's sentence for a summary of part of a document, written out likewise. */
const SUMMARY_TRUNCATED = 'This summary covers only the first part of the document.'

/** The key points' visible name, which is also the list's accessible name. */
const KEY_POINTS_NAME = 'Key points'

const LEAVE_SUMMARY = 'Sets out how staff accrue annual leave and how a request for it is approved.'

const LEAVE_KEY_POINTS = ['Four weeks of annual leave a year for full-time staff.', 'A manager approves each request.']

/** A document result as `GET /api/search` sends it since D-139, carrying a summary. */
function summarised(overrides = {}) {
  return {
    ...LEAVE_POLICY,
    snippet_ai_generated: false,
    summary: LEAVE_SUMMARY,
    key_points: LEAVE_KEY_POINTS,
    summary_truncated: false,
    ...overrides,
  }
}

/** The search screen for "leave", once the reply's results are on it. */
async function searchedFor(documents, meetings = []) {
  serveApi({
    'GET /api/auth/me': { body: EMPLOYEE },
    'GET /api/search': { body: searchReply('leave', documents, meetings) },
  })
  renderApp('/search?q=leave')
  await screen.findByRole('heading', { level: 2, name: TEXT.searchResultsFor('leave') })
}

/** One result's article, found by its title's link. */
function resultOf(result) {
  return screen.getByRole('link', { name: result.title }).closest('article')
}

/** Whether `later` comes after `earlier` in the document, and is not inside it. */
function comesAfter(earlier, later) {
  return earlier.compareDocumentPosition(later) === Node.DOCUMENT_POSITION_FOLLOWING
}

/** The classes of a result's own children, in order: the shape of the result. */
function shapeOf(item) {
  return Array.from(item.children, (child) => child.className)
}

/** Every element of `block`, itself included, that the keyboard could stop on. */
function tabStopsIn(block) {
  return [block, ...block.querySelectorAll('*')].filter((element) =>
    element.matches('a[href], button, input, select, textarea, summary, [tabindex], [contenteditable]'),
  )
}

/** The selectors of the rules that match `element` and declare a border of any kind but its radius. */
function borderRulesOn(element) {
  return rulesMatching(element)
    .filter((rule) => rule.declarations.some((declaration) => /^border(?!-radius)/.test(declaration.property)))
    .map((rule) => rule.selector)
}

describe('FR-10: a document’s summary and key points are shown beneath its title in search results (D-139)', () => {
  it('shows the summary and each key point in the result, in the order title, summary, key points, snippet', async () => {
    await searchedFor([summarised(), PAYROLL_GUIDE])
    const item = resultOf(LEAVE_POLICY)

    const title = within(item).getByRole('heading', { level: 4, name: LEAVE_POLICY.title })
    const summary = within(item).getByText(LEAVE_SUMMARY)
    const points = within(item).getByRole('list', { name: KEY_POINTS_NAME })
    const snippet = within(item).getByText(LEAVE_POLICY.snippet)
    expect(within(points).getAllByRole('listitem').map((point) => point.textContent)).toEqual(LEAVE_KEY_POINTS)

    expect(comesAfter(title, summary), 'the summary is beneath the title').toBe(true)
    expect(comesAfter(summary, points), 'the key points follow the summary').toBe(true)
    expect(comesAfter(points, snippet), 'the snippet follows the key points').toBe(true)
    // The department and date still close the result.
    expect(comesAfter(snippet, item.querySelector('time'))).toBe(true)

    // The summary is that result's alone: the one beside it, which carries none, shows none.
    const other = resultOf(PAYROLL_GUIDE)
    expect(other.textContent).not.toContain(LEAVE_SUMMARY)
    expect(within(other).queryByRole('list')).toBeNull()
  })

  it('marks the summary and its key points as AI content: the mark is inside their block and ahead of them, and the snippet is outside it', async () => {
    await searchedFor([summarised(), PAYROLL_GUIDE])
    const item = resultOf(LEAVE_POLICY)

    const summary = within(item).getByText(LEAVE_SUMMARY)
    const block = summary.closest('.ai-content')
    expect(block, 'the summary is inside the AI boundary').toBeTruthy()
    const mark = within(item).getByText(SUGGESTED_BY_AI)
    expect(block.contains(mark)).toBe(true)
    expect(comesAfter(mark, summary), 'the mark is read before the summary').toBe(true)
    expect(block.contains(within(item).getByRole('list', { name: KEY_POINTS_NAME }))).toBe(true)
    // What the block is, in words, beside the mark.
    expect(mark.parentElement.textContent).toBe(`${SUGGESTED_BY_AI} ${TEXT.documentSummaryProvenance}`)
    // The snippet is the document's own passage, so it is not inside the AI boundary.
    expect(block.contains(within(item).getByText(LEAVE_POLICY.snippet))).toBe(false)
    // One mark, on the one result with AI content; and the block is nothing to tab to.
    expect(screen.getAllByText(SUGGESTED_BY_AI, { exact: false })).toHaveLength(1)
    expect(tabStopsIn(block)).toEqual([])
    // jsdom applies no stylesheet, so the two cues are held to the CSS on disk: no
    // rule hides the mark or the summary, and the block's only border is the dashed
    // one every AI surface takes from `ai-content` (tests/aiGeneratedMark.test.jsx).
    expect(hidingCauses(mark)).toEqual([])
    expect(hidingCauses(summary)).toEqual([])
    expect(borderRulesOn(block)).toEqual(['.ai-content'])
  })

  it.each([
    ['an empty summary', { summary: '', key_points: [], summary_truncated: false }],
    // A reply from before the fields carries none of the three.
    ['no summary field at all', {}],
    // Key points and the flag are a summary's: without one, neither is shown.
    ['an empty summary beside key points', { summary: '', key_points: LEAVE_KEY_POINTS, summary_truncated: true }],
    ['a summary that is not a string', { summary: null, key_points: null, summary_truncated: null }],
    // White space says nothing, so it is no summary: never a marked block with nothing to read.
    ['a summary of only white space', { summary: ' \n\t  ', key_points: LEAVE_KEY_POINTS, summary_truncated: true }],
  ])('renders a result with %s as it always has: no summary block, no mark and no list', async (_case, fields) => {
    await searchedFor([{ ...LEAVE_POLICY, ...fields }])
    const item = resultOf(LEAVE_POLICY)

    expect(item.querySelector('.document-summary')).toBeNull()
    expect(item.querySelector('.ai-content')).toBeNull()
    expect(within(item).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
    expect(within(item).queryByRole('list')).toBeNull()
    expect(item.textContent).not.toContain(KEY_POINTS_NAME)
    expect(item.textContent).not.toContain(SUMMARY_TRUNCATED)
    // The result as it was before FR-10's summary: its title, its snippet, its metadata.
    expect(shapeOf(item)).toEqual(['search-result__title', 'search-result__snippet', 'search-result__meta'])
    expect(within(item).getByText(LEAVE_POLICY.snippet).parentElement).toBe(item)
  })

  it('still marks a meeting’s snippet that is from its AI-generated summary, and gives the meeting no summary block', async () => {
    // Every meeting carries "", [] and false; this one's snippet is its FR-16 summary's.
    const meeting = { ...HR_SYNC, snippet_ai_generated: true, summary: '', key_points: [], summary_truncated: false }
    await searchedFor([], [meeting])
    const item = resultOf(meeting)

    expect(item.querySelector('.document-summary')).toBeNull()
    expect(within(item).queryByRole('list')).toBeNull()
    const snippet = within(item).getByText(meeting.snippet)
    const block = snippet.closest('.ai-content')
    expect(block.contains(within(item).getByText(SUGGESTED_BY_AI))).toBe(true)
    expect(block.textContent).toContain(TEXT.aiSummarySnippet)
    expect(item.textContent).not.toContain(TEXT.documentSummaryProvenance)
    expect(within(item).getAllByText(SUGGESTED_BY_AI, { exact: false })).toHaveLength(1)
    // The marked snippet is the result's second child, as it was before FR-10's summary.
    expect(shapeOf(item)).toEqual(['search-result__title', 'search-result__ai ai-content', 'search-result__meta'])
  })

  it.each([
    ['says so when summary_truncated is true', { summary_truncated: true }, true],
    ['does not say so when summary_truncated is false', { summary_truncated: false }, false],
    // A reply without the flag has none, which is false.
    ['does not say so when summary_truncated is absent', { summary_truncated: undefined }, false],
    ['does not say so when summary_truncated is not a boolean', { summary_truncated: 'true' }, false],
  ])('a summary that covers only the first part of a document: %s', async (_case, fields, told) => {
    await searchedFor([summarised(fields)])
    const item = resultOf(LEAVE_POLICY)

    // The summary is shown either way; only the sentence depends on the flag.
    const block = within(item).getByText(LEAVE_SUMMARY).closest('.ai-content')
    const sentence = within(item).queryByText(SUMMARY_TRUNCATED)
    expect(sentence !== null).toBe(told)
    if (told) expect(block.contains(sentence), 'said with the summary it is about').toBe(true)
    expect(TEXT.documentSummaryTruncated).toBe(SUMMARY_TRUNCATED)
  })

  it('draws a summary cut short where a reader can see it: no stylesheet hides the sentence that says so, the key points’ name or a key point', async () => {
    // jsdom applies no stylesheet, so this is held to the CSS on disk (tests/stylesheets.js),
    // against every rule that matches inside a search result and its ancestors.
    await searchedFor([summarised({ summary_truncated: true })])
    const block = resultOf(LEAVE_POLICY).querySelector('.document-summary')

    const items = within(block).getAllByRole('listitem')
    expect(items).toHaveLength(LEAVE_KEY_POINTS.length)
    for (const element of [within(block).getByText(SUMMARY_TRUNCATED), within(block).getByText(KEY_POINTS_NAME), ...items]) {
      expect(hidingCauses(element)).toEqual([])
    }
  })

  it('renders five key points as five list items, in the order they were sent', async () => {
    const five = ['First point.', 'Second point.', 'Third point.', 'Fourth point.', 'Fifth point.']
    await searchedFor([summarised({ key_points: five })])

    const points = within(resultOf(LEAVE_POLICY)).getByRole('list', { name: KEY_POINTS_NAME })
    expect(points.tagName).toBe('UL')
    const items = within(points).getAllByRole('listitem')
    expect(items).toHaveLength(5)
    expect(items.map((point) => point.textContent)).toEqual(five)
    expect(items.every((point) => point.tagName === 'LI' && point.parentElement === points)).toBe(true)
  })

  it.each([
    ['no key points', []],
    ['key points that are not a list', 'A manager approves each request.'],
    ['only key points that say nothing', ['', '   ', null]],
  ])('shows a summary that came with %s without an empty list', async (_case, keyPoints) => {
    await searchedFor([summarised({ key_points: keyPoints })])
    const item = resultOf(LEAVE_POLICY)

    expect(within(item).getByText(LEAVE_SUMMARY).closest('.ai-content')).toBeTruthy()
    expect(within(item).queryByRole('list')).toBeNull()
    expect(within(item).queryByRole('listitem')).toBeNull()
    expect(item.textContent).not.toContain(KEY_POINTS_NAME)
  })

  it('leaves out a key point that says nothing, and keeps the rest in order', async () => {
    // The server refuses a reply with a blank key point; the screen draws no empty bullet either way.
    await searchedFor([summarised({ key_points: ['First point.', '', '   ', null, 'Second point.'] })])

    const points = within(resultOf(LEAVE_POLICY)).getByRole('list', { name: KEY_POINTS_NAME })
    expect(within(points).getAllByRole('listitem').map((point) => point.textContent)).toEqual([
      'First point.',
      'Second point.',
    ])
  })

  it('renders a summary and a key point holding markup as the characters they are', async () => {
    // The model's words about a file anyone may have uploaded: untrusted, and never HTML.
    const markup = '<img src="x" onerror="alert(1)"> Leave <b>rules</b>'
    const point = '<a href="https://example.com">Read more</a>'
    await searchedFor([summarised({ summary: markup, key_points: [point] })])
    const item = resultOf(LEAVE_POLICY)

    const block = within(item).getByText(markup).closest('.ai-content')
    expect(within(block).getByRole('listitem').textContent).toBe(point)
    expect(block.querySelector('img, b, a')).toBeNull()
  })
})
