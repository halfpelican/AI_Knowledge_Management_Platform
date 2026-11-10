/**
 * FR-19's knowledge-gap log: the clauses only the interface can satisfy.
 *
 * FR-19 Front-End: "A list, visible to Administrators, of questions the system could
 * not answer and searches returning no results, grouped by subject with an occurrence
 * count and the ability to mark an entry as addressed." What is defended here is what
 * the screen shows, keeps, withholds and sends:
 *
 * - every entry in the server's order, each with its subject, occurrence count, status
 *   and dates, and the subject rendered as text;
 * - one action per entry, one PATCH per press, and the row updated from the reply;
 * - a 404 (gone, so the list is read again), a 403 (every action withdrawn), and the
 *   empty, loading and failed states;
 * - "Run aggregation now": busy, a summary built only from the reply's own counts, a
 *   re-read, and NFR-19's notice on a 503;
 * - the route and its link offered to an Administrator only.
 *
 * Usability only, and these tests claim nothing more. The server's half — the
 * permission on every route, the order, the grouping, the permission exclusion, the
 * rollback on a 503 — is pytest's (apps/api/tests/test_knowledge_gaps.py and
 * apps/retrieval/tests/). The dashboard's panel is tests/dashboard.test.jsx's.
 *
 * The whole application is rendered at /admin/knowledge-gaps with the real auth
 * provider and guards, against a faked API (tests/fakeApi.js).
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { messageForStatus } from '../src/api/client.js'
import { KNOWLEDGE_GAP_STATUS } from '../src/api/knowledgeGaps.js'
import { ROLES, TEXT } from '../src/constants.js'
import { formatDate } from '../src/utils/dates.js'
import { heldResponse, serveApi } from './fakeApi.js'

const ADMINISTRATOR = {
  id: 'user-administrator',
  name: 'Ada Administrator',
  email: 'ada@example.com',
  role: ROLES.administrator,
  created_at: '2026-09-12T10:00:00+10:00',
}

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

/* The entry object of docs/api-contract.md, FR-19: six fields and no others. */

/** Open, and the most frequent Open entry: first. */
const STIPEND = {
  gap_id: '7d0c3f8a-0000-4000-8000-000000000001',
  subject: 'What is the WFH stipend policy?',
  occurrence_count: 6,
  status: 'Open',
  first_seen_at: '2026-11-02T09:14:00+11:00',
  last_seen_at: '2026-11-09T09:25:00+11:00',
}

/** Open, seen more recently than STIPEND but less often: second. */
const PARKING = {
  gap_id: '7d0c3f8a-0000-4000-8000-000000000002',
  subject: 'How do I claim parking?',
  occurrence_count: 2,
  status: 'Open',
  first_seen_at: '2026-11-05T10:00:00+11:00',
  last_seen_at: '2026-11-10T08:00:00+11:00',
}

/** Addressed, and more frequent than either Open entry: still after both. */
const CARRYOVER = {
  gap_id: '7d0c3f8a-0000-4000-8000-000000000003',
  subject: 'Can I carry over unused leave?',
  occurrence_count: 9,
  status: 'Addressed',
  first_seen_at: '2026-10-20T11:00:00+11:00',
  last_seen_at: '2026-11-08T16:30:00+11:00',
}

/** Addressed, the least frequent: last. */
const STYLE_GUIDE = {
  gap_id: '7d0c3f8a-0000-4000-8000-000000000004',
  subject: 'Where is the brand style guide?',
  occurrence_count: 1,
  status: 'Addressed',
  first_seen_at: '2026-10-28T13:00:00+11:00',
  last_seen_at: '2026-10-28T13:00:00+11:00',
}

/**
 * The contract's order: Open first by count then last seen, then Addressed the same
 * way. No order the screen could compute for itself gives it: by count the list would
 * start with CARRYOVER, by last seen with PARKING, by subject with CARRYOVER, by status
 * name with an Addressed entry, and reversed with STYLE_GUIDE.
 */
const SERVER_ORDER = [STIPEND, PARKING, CARRYOVER, STYLE_GUIDE]

function routes(extra = {}) {
  return {
    'GET /api/auth/me': { body: ADMINISTRATOR },
    'GET /api/knowledge-gaps': { body: SERVER_ORDER },
    ...extra,
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

function renderGaps(path = '/admin/knowledge-gaps') {
  probe.location = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  )
  return probe
}

/** The subject of each body row, in document order. */
function subjectsShown() {
  return within(screen.getByRole('table'))
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getByRole('rowheader').textContent)
}

/** A row's data cells, after its subject: occurrences, status, first seen, last seen, then the action. */
function cellsOf(entry) {
  return within(screen.getByRole('rowheader', { name: entry.subject }).closest('tr')).getAllByRole('cell')
}

function markAddressedButton(entry) {
  return screen.queryByRole('button', { name: TEXT.gapMarkAddressedLabel(entry.subject) })
}

function reopenButton(entry) {
  return screen.queryByRole('button', { name: TEXT.gapReopenLabel(entry.subject) })
}

function listReads(answered) {
  return answered.filter((request) => request.method === 'GET' && request.path === '/api/knowledge-gaps')
}

function patches(answered) {
  return answered.filter((request) => request.method === 'PATCH')
}

function cycles(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/knowledge-gaps/cycles')
}

function pageHeading() {
  return screen.getByRole('heading', { level: 1, name: TEXT.gapsHeading })
}

/** A cycle's 201 (docs/api-contract.md), with four counts the summary can tell apart. */
const CYCLE = {
  cycle_id: '9e2b0d11-0000-4000-8000-000000000001',
  started_at: '2026-11-10T21:40:02+11:00',
  finished_at: '2026-11-10T21:40:05+11:00',
  queries_considered: 4,
  searches_considered: 1,
  entries_created: 2,
  entries_updated: 3,
}

describe('FR-19: the entries, as the server sent them', () => {
  it("lists every entry in the server's order, each with its subject, occurrences, status, first and last seen, and the one action its status allows", async () => {
    const answered = serveApi(routes())
    renderGaps()

    await screen.findByRole('rowheader', { name: STIPEND.subject })
    expect(subjectsShown()).toEqual(SERVER_ORDER.map((entry) => entry.subject))
    // A real table: captioned, with a header for every column.
    const table = screen.getByRole('table', { name: TEXT.gapsTableCaption })
    expect(within(table).getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      TEXT.gapsColumnSubject,
      TEXT.gapsColumnOccurrences,
      TEXT.gapsColumnStatus,
      TEXT.gapsColumnFirstSeen,
      TEXT.gapsColumnLastSeen,
      TEXT.gapsColumnAction,
    ])
    for (const entry of SERVER_ORDER) {
      const [occurrences, status, firstSeen, lastSeen] = cellsOf(entry)
      expect(occurrences.textContent).toBe(String(entry.occurrence_count))
      expect(status.textContent).toBe(entry.status)
      expect(firstSeen.querySelector('time').getAttribute('datetime')).toBe(entry.first_seen_at)
      expect(firstSeen.textContent).toBe(formatDate(entry.first_seen_at))
      expect(lastSeen.querySelector('time').getAttribute('datetime')).toBe(entry.last_seen_at)
      expect(lastSeen.textContent).toBe(formatDate(entry.last_seen_at))
    }
    // "Mark addressed" on an Open entry, "Reopen" on an Addressed one, and never both.
    for (const entry of [STIPEND, PARKING]) {
      expect(markAddressedButton(entry).textContent).toBe(TEXT.gapMarkAddressed)
      expect(reopenButton(entry)).toBeNull()
    }
    for (const entry of [CARRYOVER, STYLE_GUIDE]) {
      expect(reopenButton(entry).textContent).toBe(TEXT.gapReopen)
      expect(markAddressedButton(entry)).toBeNull()
    }
    // One read, and nothing sent.
    expect(answered.map((request) => `${request.method} ${request.path}`)).toEqual([
      'GET /api/auth/me',
      'GET /api/knowledge-gaps',
    ])
  })

  it('renders a subject holding markup as the characters it is, and creates no element from it', async () => {
    // A question a user typed (D-107: the subject is the first member's wording, verbatim).
    const hostile =
      'Is <b>this</b> allowed?<img src="x" onerror="window.__fr19Injected = true">' +
      '<script>window.__fr19Injected = true</script>'
    const entry = { ...STIPEND, subject: hostile }
    serveApi(routes({ 'GET /api/knowledge-gaps': { body: [entry] } }))
    renderGaps()

    const subject = await screen.findByRole('rowheader', { name: hostile })
    expect(subject.textContent).toBe(hostile)
    expect(subject.children).toHaveLength(0)
    expect(screen.getByRole('table').querySelectorAll('b, img, script')).toHaveLength(0)
    expect(window.__fr19Injected).toBeUndefined()
    // Its action's accessible name carries the same characters, as text.
    expect(markAddressedButton(entry)).toBeTruthy()
  })
})

describe('FR-19: "the ability to mark an entry as addressed", and back', () => {
  it('sends one PATCH with {status: "Addressed"} and shows the row as the server stored it, where it was', async () => {
    // The reply as the contract allows it to differ from the request: a cycle that ran
    // while the change waited added an occurrence. The row must show the reply.
    const stored = { ...STIPEND, status: KNOWLEDGE_GAP_STATUS.addressed, occurrence_count: 7, last_seen_at: '2026-11-10T09:00:00+11:00' }
    const answered = serveApi(routes({ [`PATCH /api/knowledge-gaps/${STIPEND.gap_id}`]: { body: stored } }))
    renderGaps()

    fireEvent.click(await screen.findByRole('button', { name: TEXT.gapMarkAddressedLabel(STIPEND.subject) }))

    expect(await screen.findByRole('button', { name: TEXT.gapReopenLabel(STIPEND.subject) })).toBeTruthy()
    expect(markAddressedButton(STIPEND)).toBeNull()
    const [occurrences, status, , lastSeen] = cellsOf(STIPEND)
    expect(status.textContent).toBe('Addressed')
    expect(occurrences.textContent).toBe('7')
    expect(lastSeen.querySelector('time').getAttribute('datetime')).toBe(stored.last_seen_at)
    // Not moved: the order is the server's, and the next read applies it.
    expect(subjectsShown()).toEqual(SERVER_ORDER.map((entry) => entry.subject))
    expect(patches(answered).map((request) => [request.path, request.body])).toEqual([
      [`/api/knowledge-gaps/${STIPEND.gap_id}`, { status: 'Addressed' }],
    ])
    // Updated from the reply, not by reading the list again.
    expect(listReads(answered)).toHaveLength(1)
    // Announced in the words the row now shows.
    await waitFor(() => expect(screen.getByText(TEXT.statusAnnouncement(STIPEND.subject, 'Addressed'))).toBeTruthy())
  })

  it('sends {status: "Open"} for Reopen, and the row offers Mark addressed again', async () => {
    const answered = serveApi(
      routes({
        [`PATCH /api/knowledge-gaps/${CARRYOVER.gap_id}`]: { body: { ...CARRYOVER, status: KNOWLEDGE_GAP_STATUS.open } },
      }),
    )
    renderGaps()

    fireEvent.click(await screen.findByRole('button', { name: TEXT.gapReopenLabel(CARRYOVER.subject) }))

    expect(await screen.findByRole('button', { name: TEXT.gapMarkAddressedLabel(CARRYOVER.subject) })).toBeTruthy()
    expect(reopenButton(CARRYOVER)).toBeNull()
    expect(cellsOf(CARRYOVER)[1].textContent).toBe('Open')
    expect(subjectsShown()).toEqual(SERVER_ORDER.map((entry) => entry.subject))
    expect(patches(answered).map((request) => [request.path, request.body])).toEqual([
      [`/api/knowledge-gaps/${CARRYOVER.gap_id}`, { status: 'Open' }],
    ])
  })

  it('sends one PATCH for presses made while the first is still in flight', async () => {
    const held = heldResponse()
    const answered = serveApi(routes({ [`PATCH /api/knowledge-gaps/${STIPEND.gap_id}`]: held.route }))
    renderGaps()
    const button = await screen.findByRole('button', { name: TEXT.gapMarkAddressedLabel(STIPEND.subject) })

    // A double click whose second press lands before React has rendered the first, so
    // the guard has to hold without the re-render's help.
    act(() => {
      fireEvent.click(button)
      fireEvent.click(button)
    })
    // The row says the change is in flight, and keeps its focusable button.
    await waitFor(() => expect(button.getAttribute('aria-busy')).toBe('true'))
    expect(button.getAttribute('aria-disabled')).toBe('true')
    // A third press, after that render, is refused as well.
    fireEvent.click(button)
    expect(patches(answered)).toHaveLength(1)

    held.release({ body: { ...STIPEND, status: KNOWLEDGE_GAP_STATUS.addressed } })
    expect(await screen.findByRole('button', { name: TEXT.gapReopenLabel(STIPEND.subject) })).toBeTruthy()
    expect(patches(answered)).toHaveLength(1)
  })

  it('says an entry that answers 404 no longer exists, and reads the list again', async () => {
    let reads = 0
    const answered = serveApi(
      routes({
        'GET /api/knowledge-gaps': () => {
          reads += 1
          return { body: reads === 1 ? SERVER_ORDER : [PARKING, CARRYOVER, STYLE_GUIDE] }
        },
        [`PATCH /api/knowledge-gaps/${STIPEND.gap_id}`]: { status: 404, body: { detail: 'Not found.' } },
      }),
    )
    renderGaps()

    fireEvent.click(await screen.findByRole('button', { name: TEXT.gapMarkAddressedLabel(STIPEND.subject) }))

    const alert = (await screen.findByText(TEXT.gapNotFound)).closest('[role="alert"]')
    expect(alert.textContent).toContain(TEXT.gapUpdateFailed)
    // The list as the server now has it.
    await waitFor(() => expect(screen.queryByRole('rowheader', { name: STIPEND.subject })).toBeNull())
    await screen.findByRole('rowheader', { name: PARKING.subject })
    expect(subjectsShown()).toEqual([PARKING, CARRYOVER, STYLE_GUIDE].map((entry) => entry.subject))
    expect(listReads(answered)).toHaveLength(2)
    expect(patches(answered)).toHaveLength(1)
    // The pressed button went with the old table, so focus was put somewhere deliberate.
    expect(document.activeElement).toBe(pageHeading())
  })

  it.each([
    { refused: 'a change', route: `PATCH /api/knowledge-gaps/${STIPEND.gap_id}`, press: TEXT.gapMarkAddressedLabel(STIPEND.subject) },
    { refused: 'an aggregation', route: 'POST /api/knowledge-gaps/cycles', press: TEXT.gapsCycleRun },
  ])('withdraws every action, and says the role may not review the log, when the server refuses $refused with a 403', async ({ route, press }) => {
    const detail = "Your role does not hold the 'review_knowledge_gaps' permission."
    const answered = serveApi(routes({ [route]: { status: 403, body: { detail } } }))
    renderGaps()

    fireEvent.click(await screen.findByRole('button', { name: press }))

    const alert = (await screen.findByText(TEXT.gapsNotPermitted)).closest('[role="alert"]')
    expect(alert).toBeTruthy()
    // No action left on the screen: no row's, and no aggregation.
    expect(within(screen.getByRole('main')).queryAllByRole('button')).toEqual([])
    // The entries already read stay as they were, without an action column.
    expect(subjectsShown()).toEqual(SERVER_ORDER.map((entry) => entry.subject))
    expect(within(screen.getByRole('table')).queryByRole('columnheader', { name: TEXT.gapsColumnAction })).toBeNull()
    expect(document.body.textContent).not.toContain(detail)
    expect(answered.filter((request) => request.method !== 'GET')).toHaveLength(1)
    expect(document.activeElement).toBe(pageHeading())
  })
})

describe('FR-19: "Run aggregation now"', () => {
  it('shows the aggregation running, then what it added, in words from the reply, then reads the list again', async () => {
    const held = heldResponse()
    const ARRIVED = {
      gap_id: '7d0c3f8a-0000-4000-8000-000000000005',
      subject: 'Is there a policy on hot desking?',
      occurrence_count: 3,
      status: 'Open',
      first_seen_at: '2026-11-10T09:30:00+11:00',
      last_seen_at: '2026-11-10T11:00:00+11:00',
    }
    let reads = 0
    const answered = serveApi(
      routes({
        'GET /api/knowledge-gaps': () => {
          reads += 1
          return { body: reads === 1 ? SERVER_ORDER : [STIPEND, ARRIVED, PARKING, CARRYOVER, STYLE_GUIDE] }
        },
        'POST /api/knowledge-gaps/cycles': held.route,
      }),
    )
    renderGaps()
    await screen.findByRole('rowheader', { name: STIPEND.subject })
    const run = screen.getByRole('button', { name: TEXT.gapsCycleRun })

    fireEvent.click(run)

    // Busy, and said to be: the button, and a live region on the screen.
    await waitFor(() => expect(run.getAttribute('aria-busy')).toBe('true'))
    expect(run.getAttribute('aria-disabled')).toBe('true')
    expect(run.textContent).toBe(TEXT.gapsCycleRunning)
    const status = screen.getByText(TEXT.gapsCycleWait)
    expect(status.getAttribute('role')).toBe('status')
    expect(status.getAttribute('aria-live')).toBe('polite')
    // A second press while it runs starts nothing.
    fireEvent.click(run)
    expect(cycles(answered)).toHaveLength(1)
    expect(listReads(answered)).toHaveLength(1)

    held.release({ status: 201, body: CYCLE })

    // Written out, so each count is checked against the field it came from.
    const summary =
      'Aggregation finished. ' +
      'Added to the log: 4 questions that could not be answered and 1 search that returned no results. ' +
      'In the list: 2 new entries started and 3 existing entries updated.'
    expect(await screen.findByText(summary)).toBe(status)
    expect(run.getAttribute('aria-busy')).toBeNull()
    expect(run.textContent).toBe(TEXT.gapsCycleRun)
    // Then the list as the server now has it.
    await screen.findByRole('rowheader', { name: ARRIVED.subject })
    expect(subjectsShown()).toEqual([STIPEND, ARRIVED, PARKING, CARRYOVER, STYLE_GUIDE].map((entry) => entry.subject))
    expect(listReads(answered)).toHaveLength(2)
    expect(cycles(answered).map((request) => request.body)).toEqual([{}])
  })

  it('says only that it finished when the reply does not carry all four counts, and shows no number of its own', async () => {
    const answered = serveApi(
      routes({ 'POST /api/knowledge-gaps/cycles': { status: 201, body: { cycle_id: CYCLE.cycle_id, entries_created: 2 } } }),
    )
    renderGaps()
    await screen.findByRole('rowheader', { name: STIPEND.subject })

    fireEvent.click(screen.getByRole('button', { name: TEXT.gapsCycleRun }))

    const status = await screen.findByText(TEXT.gapsCycleDone)
    expect(status.textContent).toBe(TEXT.gapsCycleDone)
    expect(status.textContent).not.toMatch(/\d/)
    await waitFor(() => expect(listReads(answered)).toHaveLength(2))
    await screen.findByRole('rowheader', { name: STIPEND.subject })
  })

  it("shows NFR-19's notice at once on a 503, in the client's words and never the server's, and reads nothing again", async () => {
    const serverText =
      'The knowledge service is temporarily unavailable, so the aggregation cycle did not run and nothing was changed. Please try again shortly.'
    const answered = serveApi(routes({ 'POST /api/knowledge-gaps/cycles': { status: 503, body: { detail: serverText } } }))
    renderGaps()
    await screen.findByRole('rowheader', { name: STIPEND.subject })

    fireEvent.click(screen.getByRole('button', { name: TEXT.gapsCycleRun }))

    const notice = (await screen.findByText(`${messageForStatus(503)} ${TEXT.gapsCycleNotRun}`)).closest('[role="alert"]')
    expect(notice.className).toContain('notice--unavailable')
    expect(document.body.textContent).not.toContain(serverText)
    // Not a spinner left running: the button is ready again, and nothing says it is busy.
    const run = screen.getByRole('button', { name: TEXT.gapsCycleRun })
    expect(run.getAttribute('aria-busy')).toBeNull()
    expect(screen.queryByText(TEXT.gapsCycleWait)).toBeNull()
    expect(screen.queryByText(TEXT.gapsCycleDone, { exact: false })).toBeNull()
    // The cycle rolled back, so the list is not read again and is as it was.
    expect(listReads(answered)).toHaveLength(1)
    expect(subjectsShown()).toEqual(SERVER_ORDER.map((entry) => entry.subject))
  })
})

describe('FR-19: the empty, loading and failed states', () => {
  it('says no knowledge gaps have been recorded for an empty list, as an ordinary state', async () => {
    serveApi(routes({ 'GET /api/knowledge-gaps': { body: [] } }))
    renderGaps()

    const empty = await screen.findByText(TEXT.noGaps)
    expect(empty.closest('[role="status"]')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    // The aggregation is still offered: it is how the first entries arrive.
    expect(screen.getByRole('button', { name: TEXT.gapsCycleRun })).toBeTruthy()
  })

  it('shows a loading state, then a failed read in fixed words, and Try again reads the list again', async () => {
    const held = heldResponse()
    const backendText = 'Traceback (most recent call last): relation "retrieval_knowledgegap" does not exist'
    let reads = 0
    const answered = serveApi(
      routes({
        'GET /api/knowledge-gaps': () => {
          reads += 1
          return reads === 1 ? held.route() : { body: SERVER_ORDER }
        },
      }),
    )
    renderGaps()

    expect((await screen.findByText(TEXT.loadingGaps)).getAttribute('role')).toBe('status')
    held.release({ status: 500, body: { detail: backendText } })

    const alert = (await screen.findByText(TEXT.gapsLoadFailed)).closest('[role="alert"]')
    expect(alert.textContent).toContain(messageForStatus(500))
    expect(document.body.textContent).not.toContain(backendText)
    fireEvent.click(screen.getByRole('button', { name: TEXT.uploadRetry }))

    await screen.findByRole('rowheader', { name: STIPEND.subject })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(listReads(answered)).toHaveLength(2)
  })

  it('renders only the not-permitted notice when the list itself answers 403', async () => {
    serveApi(routes({ 'GET /api/knowledge-gaps': { status: 403, body: { detail: 'Not permitted.' } } }))
    renderGaps()

    expect(await screen.findByText(TEXT.notPermitted)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(within(screen.getByRole('main')).queryAllByRole('button')).toEqual([])
  })
})

describe("FR-19, FR-06: the log is an Administrator's only, in the interface", () => {
  it('offers an Employee no link to it, and sends one who types its address to the 403 page without reading it', async () => {
    // Nothing answers the knowledge-gap routes: had the screen rendered, its read would
    // reach tests/setup.js's refusal and fail this test whatever it asserted.
    const answered = serveApi({ 'GET /api/auth/me': { body: EMPLOYEE } })
    const probe = renderGaps()

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.accessDeniedTitle })).toBeTruthy()
    expect(probe.location.pathname).toBe('/403')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByRole('button', { name: 'Log out' })).toBeTruthy()
    expect(within(nav).queryByRole('link', { name: TEXT.gapsHeading })).toBeNull()
    // Nothing on the page says the log exists.
    expect(document.body.textContent).not.toMatch(/knowledge.gap/i)
    expect(answered.map((request) => request.path)).toEqual(['/api/auth/me'])
  })

  it('offers an Administrator the link beside Role management, and renders the log at its address', async () => {
    serveApi(routes())
    const probe = renderGaps()

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.gapsHeading })).toBeTruthy()
    await screen.findByRole('rowheader', { name: STIPEND.subject })
    expect(probe.location.pathname).toBe('/admin/knowledge-gaps')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    const names = within(nav)
      .getAllByRole('link')
      .map((link) => link.textContent)
    expect(names.indexOf(TEXT.gapsHeading)).toBe(names.indexOf('Role management') + 1)
    const link = within(nav).getByRole('link', { name: TEXT.gapsHeading })
    expect(link.getAttribute('href')).toBe('/admin/knowledge-gaps')
    expect(link.getAttribute('aria-current')).toBe('page')
  })
})

describe('FR-19: the status vocabulary', () => {
  it('names the two statuses exactly as apps/core/constants.py KNOWLEDGE_GAP_STATUS_VALUES does', () => {
    // Read from the one place the server defines them, so a renamed status fails here
    // rather than leaving every row with no action (D-61's gap 13 is the pattern).
    const source = readFileSync(join(import.meta.dirname, '..', '..', 'apps', 'core', 'constants.py'), 'utf8')
    const match = source.match(/^KNOWLEDGE_GAP_STATUS_VALUES = \(([^)\r\n]*)\)\s*$/m)
    expect(match).toBeTruthy()
    const serverValues = [...match[1].matchAll(/"([^"]*)"/g)].map((literal) => literal[1])
    expect(serverValues).toEqual([KNOWLEDGE_GAP_STATUS.open, KNOWLEDGE_GAP_STATUS.addressed])
  })
})
