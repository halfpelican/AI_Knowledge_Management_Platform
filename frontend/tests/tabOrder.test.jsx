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
