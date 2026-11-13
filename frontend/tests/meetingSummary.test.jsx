/**
 * FR-16's "Summary" panel on the meeting page (NIT3004, D-125), rendered against a
 * faked `GET /api/meetings/{id}` and `GET` and `POST /api/meetings/{id}/summary`
 * (docs/api-contract.md, "NIT3004 — FR-16 meeting summary and action items").
 *
 * Each test defends one clause only the interface can satisfy: what the panel
 * shows in each state of the summary, what it never shows, when it asks again and
 * when it stops, and what its one button reads and does. What a run does, the
 * minimum length, the retry queue, who may start a run, the scoped 404 and the 403
 * are the server's and are tested in pytest; nothing here stands in for them. The
 * Action Items panel is tests/meetingActionItems.test.jsx's, and NFR-15's mark
 * across every surface is tests/aiGeneratedMark.test.jsx's.
 *
 * The tests that watch the page ask again run on a faked `setTimeout`, moved by
 * hand, and use no `findBy…` or `waitFor`, which wait on timers themselves.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NETWORK_ERROR_STATUS, messageForStatus } from '../src/api/client.js'
import MeetingSummary from '../src/components/MeetingSummary.jsx'
import { MEETING_SUMMARY_POLL_MS, ROLES, SUMMARY_STATUS, TEXT } from '../src/constants.js'
import MeetingDetail from '../src/pages/MeetingDetail.jsx'
import { formatDate } from '../src/utils/dates.js'
import {
  SUMMARY_TOO_SHORT_MESSAGE,
  actionItem,
  heldResponse,
  readySummary,
  serveApi,
  summaryRoute,
  summaryState,
  summaryTooShortRoute,
} from './fakeApi.js'
import { tabbable } from './keyboard.js'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

/** The meeting detail the page reads first. */
const MEETING = {
  meeting_id: 'meeting-1',
  title: 'First-quarter review',
  meeting_date: '2026-11-03',
  status: 'Indexed',
  created_at: '2026-11-03T16:00:00+11:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: ['ravi@example.com'],
  transcript_text: 'Ravi: Thanks, everyone. This is the first-quarter review.\nSam: Travel came in at twice its budget.',
  can_delete: false,
}

const DETAIL = `/api/meetings/${MEETING.meeting_id}`
const SUMMARY = `${DETAIL}/summary`

/** A run in flight, with nothing Ready before it. */
const PROCESSING = summaryState({ status: 'Processing', can_edit: true })
/** A Ready summary and the item its run extracted. */
const READY = summaryState({ status: 'Ready', summary: readySummary(), action_items: [actionItem()], can_edit: true })
/** A failed run waiting for the hourly retry (NFR-20), and one whose retries are spent. */
const QUEUED = summaryState({ status: 'Unavailable', queued_for_retry: true, can_edit: true })
const SPENT = summaryState({ status: 'Unavailable', queued_for_retry: false, can_edit: true })

/** What DRF sends with each refusal. The screen must never show it. */
const SERVER_403 = { detail: 'You do not have permission to perform this action.' }
const SERVER_404 = { detail: 'No Meeting matches the given query.' }
const SERVER_429 = { detail: 'Request was throttled. Expected available in 45 seconds.' }

/* ---- Rendering ----------------------------------------------------------- */

/** The meeting page at its path, against the detail and whatever routes a test adds. */
function renderPage(routes) {
  const answered = serveApi({ [`GET ${DETAIL}`]: { body: MEETING }, ...routes })
  const view = render(
    <MemoryRouter initialEntries={[`/meetings/${MEETING.meeting_id}`]}>
      <Routes>
        <Route path="/meetings/:meetingId" element={<MeetingDetail />} />
      </Routes>
    </MemoryRouter>,
  )
  return { answered, ...view }
}

/** The panel, once its own read has answered. */
async function summaryPanel() {
  const panel = await screen.findByRole('region', { name: TEXT.summaryHeading })
  await waitFor(() => expect(within(panel).queryByText(TEXT.loadingSummary)).toBeNull())
  return panel
}

/** The page with the summary route answering `state`, and the panel once it has. */
async function pageShowing(state, extraRoutes = {}) {
  const view = renderPage({ [`GET ${SUMMARY}`]: summaryRoute(state), ...extraRoutes })
  return { ...view, panel: await summaryPanel() }
}

/** The requests sent to one route, in order. */
function requestsTo(answered, method, path) {
  return answered.filter((request) => request.method === method && request.path === path)
}

/** The panel's one button, whichever of its two labels it has, or null. */
function summaryButton(panel) {
  return (
    within(panel).queryByRole('button', { name: TEXT.summaryGenerate }) ??
    within(panel).queryByRole('button', { name: TEXT.summaryRegenerate })
  )
}

/** The live region that says where the summary stands. */
function standing(panel) {
  return panel.querySelector('.meeting-summary__standing')
}

/** A click as a browser makes one: the button takes focus, then is clicked. */
function press(element) {
  element.focus()
  fireEvent.click(element)
}

/* ---- The faked clock, for the tests that watch the page ask again --------- */

afterEach(() => {
  vi.useRealTimers()
})

/** Only the timer the page's own waiting uses is faked; replies and renders run as ever. */
function fakeTheClock() {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
}

/** Lets everything already in motion finish: replies, the renders they cause, the effects after those. */
async function settle() {
  for (let round = 0; round < 6; round += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
  }
}

/** Moves the faked clock on, then lets what that set off finish. */
async function advance(milliseconds) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds)
  })
  await settle()
}

/** A summary route that answers each read with the next of `states`, then goes on answering the last. */
function inTurn(states) {
  let reads = 0
  return () => {
    const state = states[Math.min(reads, states.length - 1)]
    reads += 1
    return summaryRoute(state)
  }
}

/* ---- The vocabulary and the one server sentence --------------------------- */

describe('FR-16: what the panel reads the state by is what the server sends', () => {
  it('names the three statuses the server defines, and no others', () => {
    const source = readFileSync(join(import.meta.dirname, '..', '..', 'apps', 'core', 'constants.py'), 'utf8')
    const match = source.match(/^SUMMARY_STATUS_VALUES = \(([^)]*)\)\s*$/m)
    expect(match, 'SUMMARY_STATUS_VALUES not found in apps/core/constants.py').toBeTruthy()
    const serverValues = [...match[1].matchAll(/"([^"\r\n]+)"/g)].map((literal) => literal[1])
    expect(Object.values(SUMMARY_STATUS)).toEqual(serverValues)
  })

  it("holds the server's own sentence for a transcript too short to summarise, word for word", () => {
    // The screen shows its copy and never the reply's `detail`; this is what keeps
    // the copy the server's sentence (apps/api/views.py).
    expect(TEXT.summaryTooShort).toBe(SUMMARY_TOO_SHORT_MESSAGE)
  })
})

/* ---- The states ---------------------------------------------------------- */

describe('FR-16: the Summary panel says where the summary stands', () => {
  it('says no summary has been generated yet, and offers "Generate Summary" to a role that may', async () => {
    const { panel, answered } = await pageShowing(summaryState({ can_edit: true }))

    expect(within(panel).getByRole('heading', { level: 2 }).textContent).toBe('Summary')
    expect(standing(panel).textContent).toBe(TEXT.summaryNone)
    expect(within(panel).getByRole('button', { name: 'Generate Summary' }).disabled).toBe(false)
    expect(within(panel).queryByRole('button', { name: TEXT.summaryRegenerate })).toBeNull()
    // Offering it sends nothing.
    expect(requestsTo(answered, 'POST', SUMMARY)).toEqual([])
  })

  it("shows the server's sentence for a transcript too short to summarise, with no button, and leaves the action items usable", async () => {
    renderPage({ [`GET ${SUMMARY}`]: summaryTooShortRoute(summaryState({ can_edit: true })) })
    const summary = await summaryPanel()

    expect(standing(summary).textContent).toBe(SUMMARY_TOO_SHORT_MESSAGE)
    // Nothing can be generated from it, so nothing offers to, whatever the role.
    expect(summaryButton(summary)).toBeNull()
    expect(within(summary).queryByRole('alert')).toBeNull()

    // The 422 carries the same state, and the other panel is fed from it.
    const items = screen.getByRole('region', { name: TEXT.actionItemsHeading })
    expect(within(items).getByText(TEXT.actionItemsNone)).toBeTruthy()
    expect(within(items).getByRole('button', { name: TEXT.actionItemAdd }).disabled).toBe(false)
  })

  it('says the summary is not available yet, that the transcript is stored and searchable, and that it will be retried', async () => {
    const { panel } = await pageShowing(QUEUED)

    // UC-04 E1 and NFR-20, in words.
    expect(standing(panel).textContent).toBe(TEXT.summaryPendingRetry)
    expect(TEXT.summaryPendingRetry).toMatch(/not available yet/)
    expect(TEXT.summaryPendingRetry).toMatch(/stored and searchable/)
    expect(TEXT.summaryPendingRetry).toMatch(/tried again automatically/)
    // A designed outcome, not an error.
    expect(within(panel).queryByRole('alert')).toBeNull()
    expect(within(panel).getByRole('button', { name: TEXT.summaryGenerate }).disabled).toBe(false)
  })

  it('says the summary could not be generated once its retries are spent, and that the transcript is stored and searchable', async () => {
    const { panel } = await pageShowing(SPENT)

    expect(standing(panel).textContent).toBe(TEXT.summaryUnavailable)
    expect(TEXT.summaryUnavailable).toMatch(/could not be generated/)
    expect(TEXT.summaryUnavailable).toMatch(/stored and searchable/)
    expect(TEXT.summaryUnavailable).not.toMatch(/automatically/)
    expect(within(panel).getByRole('button', { name: TEXT.summaryGenerate }).disabled).toBe(false)
  })

  it('keeps the previous summary on screen after a Regenerate failed, and offers to regenerate again', async () => {
    const { panel } = await pageShowing({ ...SPENT, summary: readySummary() })

    expect(standing(panel).textContent).toBe(TEXT.summaryRegenerateUnavailable)
    expect(panel.textContent).toContain(readySummary().narrative[0].text)
    expect(within(panel).getByRole('button', { name: 'Regenerate Summary' }).disabled).toBe(false)
    expect(within(panel).queryByRole('button', { name: TEXT.summaryGenerate })).toBeNull()
  })

  it('shows a Ready summary: the narrative as one paragraph in order, then the decisions and the highlights as lists', async () => {
    const { panel } = await pageShowing(READY)
    const summary = readySummary()

    // One paragraph, its sentences in the order they came.
    const narrative = panel.querySelector('.meeting-summary__narrative')
    expect(narrative.tagName).toBe('P')
    expect(panel.querySelectorAll('.meeting-summary__narrative')).toHaveLength(1)
    const [first, second] = summary.narrative.map((sentence) => narrative.textContent.indexOf(sentence.text))
    expect(first).toBeGreaterThanOrEqual(0)
    expect(second).toBeGreaterThan(first)

    const decisions = within(panel).getByRole('heading', { level: 3, name: 'Decisions' }).nextElementSibling
    expect(decisions.tagName).toBe('UL')
    expect(within(decisions).getAllByRole('listitem')).toHaveLength(1)
    expect(decisions.textContent).toContain(summary.decisions[0].text)

    const highlights = within(panel).getByRole('heading', { level: 3, name: 'Highlights' }).nextElementSibling
    expect(highlights.tagName).toBe('UL')
    expect(highlights.textContent).toContain(summary.highlights[0].text)

    // Nothing more to say about where it stands: the summary speaks for itself.
    expect(standing(panel).textContent).toBe('')
    expect(within(panel).getByRole('button', { name: 'Regenerate Summary' }).disabled).toBe(false)
  })

  it('leaves out Decisions and Highlights when the summary has none, rather than heading an empty list', async () => {
    const { panel } = await pageShowing({ ...READY, summary: readySummary({ decisions: [], highlights: [] }) })

    expect(panel.textContent).toContain(readySummary().narrative[0].text)
    expect(within(panel).queryByRole('heading', { level: 3 })).toBeNull()
    expect(within(panel).queryByRole('list')).toBeNull()
  })

  it('shows the model that wrote the summary and the date it was generated', async () => {
    const { panel } = await pageShowing(READY)
    const summary = readySummary()

    const provenance = panel.querySelector('.meeting-summary__provenance')
    expect(provenance.textContent).toContain(TEXT.summaryModel(summary.model))
    expect(provenance.textContent).toContain('claude-haiku-5-5')
    const generated = provenance.querySelector('time')
    expect(generated.getAttribute('dateTime')).toBe(summary.generated_at)
    expect(generated.textContent).toBe(formatDate(summary.generated_at))
    expect(generated.textContent).not.toBe('')
  })

  it('says how much of the transcript a truncated summary covers, and nothing of the kind otherwise', async () => {
    const whole = await pageShowing(READY)
    expect(whole.panel.textContent).not.toMatch(/covers/)
    whole.unmount()

    const { panel } = await pageShowing({
      ...READY,
      summary: readySummary({ input_truncated: true, passages_sent: 8, passages_total: 20 }),
    })
    expect(within(panel).getByText('This summary covers the first 8 of 20 passages of the transcript.')).toBeTruthy()
  })
})

/* ---- Passage references --------------------------------------------------- */

describe('UC-04: every element of the summary carries a reference to the passage it was drawn from', () => {
  it('gives every sentence, decision and highlight a reference for each passage it names', async () => {
    const { panel } = await pageShowing(READY)

    // Two sentences naming [1] and [1, 2], a decision naming [2], a highlight naming [1].
    const one = within(panel).getAllByRole('button', { name: TEXT.transcriptPassage(1) })
    const two = within(panel).getAllByRole('button', { name: TEXT.transcriptPassage(2) })
    expect(one).toHaveLength(3)
    expect(two).toHaveLength(2)

    const narrative = panel.querySelector('.meeting-summary__narrative')
    expect(within(narrative).getAllByRole('button')).toHaveLength(3)
    for (const entry of within(panel).getAllByRole('listitem')) {
      expect(within(entry).getAllByRole('button').length).toBeGreaterThan(0)
    }
  })

  it('opens the passage a reference names, from a real button the keyboard reaches, and closes it again', async () => {
    const { panel } = await pageShowing(READY)
    const passages = readySummary().passages
    const decision = within(panel).getByText(readySummary().decisions[0].text).closest('li')
    const reference = within(decision).getByRole('button', { name: TEXT.transcriptPassage(2) })

    // A button, in the tab order, whose bracket is decoration and whose name says which passage.
    expect(reference.tagName).toBe('BUTTON')
    expect(reference.getAttribute('type')).toBe('button')
    expect(tabbable()).toContain(reference)
    expect(within(reference).getByText('[2]').getAttribute('aria-hidden')).toBe('true')

    // Closed: the passage is in the page, hidden, and the button points at it.
    expect(reference.getAttribute('aria-expanded')).toBe('false')
    const controlled = document.getElementById(reference.getAttribute('aria-controls'))
    expect(controlled.hidden).toBe(true)
    expect(within(decision).queryByRole('region', { name: TEXT.transcriptPassage(2) })).toBeNull()

    press(reference)
    expect(reference.getAttribute('aria-expanded')).toBe('true')
    const passage = within(decision).getByRole('region', { name: TEXT.transcriptPassage(2) })
    expect(passage.textContent).toBe(passages[2])
    // A scrolling region the keyboard can reach, as the citation's passage is.
    expect(tabbable()).toContain(passage)
    // Opening one opens no other: the same passage under another element stays shut.
    expect(within(panel).getAllByRole('region', { name: TEXT.transcriptPassage(2) })).toHaveLength(1)
    expect(document.activeElement).toBe(reference)

    press(reference)
    expect(reference.getAttribute('aria-expanded')).toBe('false')
    expect(controlled.hidden).toBe(true)
  })

  it('opens a narrative sentence’s passage under the paragraph, with the text the summary carries for it', async () => {
    const { panel } = await pageShowing(READY)
    const narrative = panel.querySelector('.meeting-summary__narrative')
    const [first] = within(narrative).getAllByRole('button', { name: TEXT.transcriptPassage(1) })

    press(first)

    const passage = within(panel).getByRole('region', { name: TEXT.transcriptPassage(1) })
    expect(passage.textContent).toBe(readySummary().passages[1])
    // A block cannot sit inside the paragraph, so it follows it.
    expect(narrative.contains(passage)).toBe(false)
    expect(narrative.compareDocumentPosition(passage) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows no sentence, decision or highlight that names no passage', async () => {
    // The server sends none ("an element that named none is not here"). This is the
    // reply as if a regression had sent some, and the panel must not show them.
    const unreferenced = 'The team will certainly exceed its targets next year.'
    const { panel } = await pageShowing({
      ...READY,
      summary: readySummary({
        // `summary_text` is the narrative joined, so the stray sentence is in it too.
        summary_text: `The team reviewed the first quarter. ${unreferenced}`,
        narrative: [
          { text: 'The team reviewed the first quarter.', passages: [1] },
          { text: unreferenced, passages: [] },
        ],
        decisions: [{ text: `Decided: ${unreferenced}` }],
        highlights: [{ text: `Noted: ${unreferenced}`, passages: ['2'] }],
      }),
    })

    expect(panel.textContent).toContain('The team reviewed the first quarter.')
    expect(document.body.textContent).not.toContain(unreferenced)
    expect(within(panel).queryByRole('heading', { level: 3 })).toBeNull()
  })

  it('renders the summary’s text as text, never as HTML', async () => {
    const hostile = '<img src="x" onerror="window.__fr16Injected = true"><b>frozen</b>'
    const { panel } = await pageShowing({
      ...READY,
      summary: readySummary({
        narrative: [{ text: hostile, passages: [1] }],
        decisions: [{ text: hostile, passages: [1] }],
        highlights: [],
        passages: { 1: hostile },
      }),
    })

    press(within(panel.querySelector('.meeting-summary__narrative')).getByRole('button'))

    expect(panel.querySelector('.meeting-summary__narrative').textContent).toContain(hostile)
    expect(within(panel).getByRole('region', { name: TEXT.transcriptPassage(1) }).textContent).toBe(hostile)
    expect(document.querySelectorAll('img, b')).toHaveLength(0)
    expect(window.__fr16Injected).toBeUndefined()
  })
})

/* ---- A failed run is never shown ------------------------------------------ */

describe('UC-04: a failed summary is never presented to a user', () => {
  it('renders nothing of a failed run, even where a reply carried one', async () => {
    // The body never carries a failed run's text: `summary` is the latest Ready
    // one or null. This is the reply as if a regression had put a draft in it, and
    // the panel must render it exactly as it renders the reply without one.
    const draft = 'The meeting agreed to double the travel budget.'
    const leaking = {
      ...SPENT,
      failure_reason: 'no_verified_narrative',
      failed_summary: { summary_text: draft, narrative: [{ text: draft, passages: [1] }] },
      draft: { summary: [{ text: draft, passages: [1] }] },
    }

    const clean = await pageShowing(SPENT)
    const cleanHtml = clean.panel.innerHTML
    clean.unmount()

    const { panel } = await pageShowing(leaking)
    expect(document.body.textContent).not.toContain(draft)
    expect(document.body.textContent).not.toContain('no_verified_narrative')
    // Ids differ from one render to the next; nothing else may.
    const withoutIds = (html) => html.replace(/ (id|for|aria-labelledby|aria-controls|aria-describedby)="[^"]*"/g, '')
    expect(withoutIds(panel.innerHTML)).toBe(withoutIds(cleanHtml))
    expect(panel.querySelector('.meeting-summary__content')).toBeNull()
  })
})

/* ---- The button ----------------------------------------------------------- */

describe('FR-16: the button starts a run, and is offered only to a role that may', () => {
  it.each([
    ['no summary yet', summaryState()],
    ['a Ready summary', { ...READY, can_edit: false }],
    ['a run waiting for its retry', { ...QUEUED, can_edit: false }],
    ['a run whose retries are spent', { ...SPENT, can_edit: false }],
    ['a state that says nothing of can_edit', (({ can_edit: _dropped, ...rest }) => rest)(READY)],
  ])('offers no button without can_edit: %s', async (_case, state) => {
    const { panel, answered } = await pageShowing(state)

    expect(within(panel).queryAllByRole('button').filter((button) => /generate/i.test(button.textContent))).toEqual([])
    expect(summaryButton(panel)).toBeNull()
    // The hint about what regenerating replaces goes with the button it explains.
    expect(panel.textContent).not.toContain(TEXT.summaryRegenerateHint)
    expect(requestsTo(answered, 'POST', SUMMARY)).toEqual([])
  })

  it('sends one POST for "Generate Summary", and then shows the run as in flight', async () => {
    fakeTheClock()
    const { answered } = renderPage({
      [`GET ${SUMMARY}`]: inTurn([summaryState({ can_edit: true }), PROCESSING]),
      [`POST ${SUMMARY}`]: { status: 202, body: PROCESSING },
    })
    await settle()
    const panel = screen.getByRole('region', { name: TEXT.summaryHeading })
    const button = within(panel).getByRole('button', { name: 'Generate Summary' })

    // Pressed twice, as an impatient user does, inside one act, so the second
    // press lands before the busy state has rendered. Still one request.
    button.focus()
    act(() => {
      button.click()
      button.click()
    })
    await settle()

    expect(requestsTo(answered, 'POST', SUMMARY)).toEqual([
      { method: 'POST', path: SUMMARY, search: '', body: {} },
    ])
    expect(standing(panel).textContent).toBe(TEXT.summaryProcessing)
    // Disabled while the run is in flight, and focus is not left on it.
    expect(within(panel).getByRole('button', { name: 'Generate Summary' }).disabled).toBe(true)
    expect(document.activeElement).toBe(within(panel).getByRole('heading', { level: 2 }))

    // The 202 starts the asking: one read when the page opened, and now another.
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(1)
    await advance(MEETING_SUMMARY_POLL_MS)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2)
  })

  it('reads "Regenerate Summary" when a Ready summary exists, sends the same POST, and keeps that summary on screen while the new one runs', async () => {
    fakeTheClock()
    const regenerating = { ...READY, status: 'Processing' }
    const { answered } = renderPage({
      [`GET ${SUMMARY}`]: inTurn([READY, regenerating]),
      [`POST ${SUMMARY}`]: { status: 202, body: regenerating },
    })
    await settle()
    const panel = screen.getByRole('region', { name: TEXT.summaryHeading })
    expect(within(panel).queryByRole('button', { name: TEXT.summaryGenerate })).toBeNull()
    // What pressing it replaces is said beside it, before it is pressed.
    expect(within(panel).getByText(TEXT.summaryRegenerateHint)).toBeTruthy()

    press(within(panel).getByRole('button', { name: 'Regenerate Summary' }))
    await settle()

    expect(requestsTo(answered, 'POST', SUMMARY)).toHaveLength(1)
    // The previous summary, under a line saying a new one is on its way.
    expect(standing(panel).textContent).toBe(TEXT.summaryRegenerating)
    expect(panel.textContent).toContain(readySummary().narrative[0].text)
    expect(panel.textContent).toContain(readySummary().decisions[0].text)
    expect(
      standing(panel).compareDocumentPosition(panel.querySelector('.meeting-summary__content')) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(within(panel).getByRole('button', { name: 'Regenerate Summary' }).disabled).toBe(true)
  })

  it('withdraws every control behind the permission on a 403, in both panels, and says so', async () => {
    const { panel, answered } = await pageShowing(READY, {
      [`POST ${SUMMARY}`]: { status: 403, body: SERVER_403 },
    })
    const items = screen.getByRole('region', { name: TEXT.actionItemsHeading })
    expect(within(items).getAllByRole('button').length).toBeGreaterThan(0)

    press(within(panel).getByRole('button', { name: TEXT.summaryRegenerate }))

    const alert = await within(panel).findByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.summaryRequestFailed}${TEXT.meetingContributionNotPermitted}`)
    expect(document.body.textContent).not.toContain(SERVER_403.detail)
    // The role does not hold the permission, whatever the state said: the button
    // goes, and so do the action items' controls, which need the same one.
    expect(summaryButton(panel)).toBeNull()
    expect(within(items).queryAllByRole('button').filter((button) => !button.classList.contains('citation'))).toEqual([])
    // The summary itself is still there, and focus is not left on nothing.
    expect(panel.textContent).toContain(readySummary().narrative[0].text)
    await waitFor(() => expect(document.activeElement).toBe(within(panel).getByRole('heading', { level: 2 })))
    expect(requestsTo(answered, 'POST', SUMMARY)).toHaveLength(1)
  })

  it('says when to try again on a 429, from Retry-After, and leaves the button in place', async () => {
    const { panel } = await pageShowing(SPENT, {
      [`POST ${SUMMARY}`]: { status: 429, body: SERVER_429, headers: { 'Retry-After': '45' } },
    })

    press(within(panel).getByRole('button', { name: TEXT.summaryGenerate }))

    const alert = await within(panel).findByRole('alert')
    expect(alert.textContent).toBe(
      `${TEXT.summaryRequestFailed}${TEXT.summaryLimitReached(TEXT.retryInSeconds(45))}`,
    )
    expect(document.body.textContent).not.toContain(SERVER_429.detail)
    // Nothing was started, and nothing says the role may not: the button stays.
    expect(standing(panel).textContent).toBe(TEXT.summaryUnavailable)
    expect(within(panel).getByRole('button', { name: TEXT.summaryGenerate }).disabled).toBe(false)
  })

  it('shows the too-short sentence when the POST answers 422, and takes the button away', async () => {
    const { panel } = await pageShowing(summaryState({ can_edit: true }), {
      [`POST ${SUMMARY}`]: summaryTooShortRoute(summaryState({ can_edit: true })),
    })

    press(within(panel).getByRole('button', { name: TEXT.summaryGenerate }))

    await waitFor(() => expect(standing(panel).textContent).toBe(SUMMARY_TOO_SHORT_MESSAGE))
    expect(summaryButton(panel)).toBeNull()
    // It is an answer, not a failure: said in the live region, with no alert.
    expect(within(panel).queryByRole('alert')).toBeNull()
  })

  it('says the server could not be reached when the POST never arrives', async () => {
    const { panel } = await pageShowing(summaryState({ can_edit: true }), {
      [`POST ${SUMMARY}`]: () => Promise.reject(new TypeError('Failed to fetch')),
    })

    press(within(panel).getByRole('button', { name: TEXT.summaryGenerate }))

    const alert = await within(panel).findByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.summaryRequestFailed}${messageForStatus(NETWORK_ERROR_STATUS)}`)
    expect(document.body.textContent).not.toContain('Failed to fetch')
    expect(within(panel).getByRole('button', { name: TEXT.summaryGenerate }).disabled).toBe(false)
  })

  it('reads the panel again on a 404, and says the meeting could not be found in the page’s own words', async () => {
    let gone = false
    const { panel, answered } = await pageShowing(summaryState({ can_edit: true }), {
      [`GET ${SUMMARY}`]: () => (gone ? { status: 404, body: SERVER_404 } : summaryRoute(summaryState({ can_edit: true }))),
      [`POST ${SUMMARY}`]: () => {
        gone = true
        return { status: 404, body: SERVER_404 }
      },
    })

    press(within(panel).getByRole('button', { name: TEXT.summaryGenerate }))

    await waitFor(() => expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2))
    await waitFor(() => expect(summaryButton(panel)).toBeNull())
    const alert = within(panel).getByRole('alert')
    expect(alert.textContent).toContain(TEXT.meetingNotFound)
    expect(document.body.textContent).not.toContain(SERVER_404.detail)
    // The transcript the page already read is not taken away by it.
    expect(screen.getByRole('region', { name: TEXT.transcriptHeading }).textContent).toContain('first-quarter review')
  })
})

/* ---- Asking again --------------------------------------------------------- */

describe('FR-16: the page asks again while a run is Processing, and only then', () => {
  it('says the summary is being generated in a polite live region, asks again every interval, and stops once the run has settled', async () => {
    fakeTheClock()
    const { answered } = renderPage({ [`GET ${SUMMARY}`]: inTurn([PROCESSING, PROCESSING, READY]) })
    await settle()
    const panel = screen.getByRole('region', { name: TEXT.summaryHeading })

    // The wait is said, in a status region, which is polite by its role.
    expect(standing(panel).getAttribute('role')).toBe('status')
    expect(standing(panel).textContent).toBe(TEXT.summaryProcessing)
    expect(panel.querySelector('.meeting-summary__content')).toBeNull()
    expect(within(panel).getByRole('button', { name: TEXT.summaryGenerate }).disabled).toBe(true)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(1)

    // Not before the interval is up.
    await advance(MEETING_SUMMARY_POLL_MS - 1)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(1)
    await advance(1)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2)
    expect(standing(panel).textContent).toBe(TEXT.summaryProcessing)

    // The third read finds it Ready: the summary appears, and its arrival is said.
    await advance(MEETING_SUMMARY_POLL_MS)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(3)
    expect(panel.textContent).toContain(readySummary().narrative[0].text)
    expect(standing(panel).textContent).toBe(TEXT.summaryReady)
    expect(within(panel).getByRole('button', { name: TEXT.summaryRegenerate }).disabled).toBe(false)
    // The Action Items panel is fed by the same read.
    expect(screen.getByRole('region', { name: TEXT.actionItemsHeading }).textContent).toContain(actionItem().description)

    // Settled: nothing asks again, however long the page stays open.
    await advance(MEETING_SUMMARY_POLL_MS * 10)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(3)
  })

  it('says what became of a run it was waiting on when that run fails', async () => {
    fakeTheClock()
    const { answered } = renderPage({ [`GET ${SUMMARY}`]: inTurn([PROCESSING, QUEUED]) })
    await settle()
    const panel = screen.getByRole('region', { name: TEXT.summaryHeading })

    await advance(MEETING_SUMMARY_POLL_MS)

    expect(standing(panel).textContent).toBe(TEXT.summaryPendingRetry)
    expect(panel.querySelector('.meeting-summary__content')).toBeNull()
    // Queued for the hourly retry: it answers 202 too, and is not asked about again.
    await advance(MEETING_SUMMARY_POLL_MS * 10)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2)
  })

  it.each([
    ['waiting for its hourly retry (202)', QUEUED],
    ['unavailable with its retries spent (200)', SPENT],
    ['ready (200)', READY],
    ['never requested (200)', summaryState({ can_edit: true })],
  ])('does not ask again for a summary that is %s', async (_case, state) => {
    fakeTheClock()
    const { answered } = renderPage({ [`GET ${SUMMARY}`]: summaryRoute(state) })
    await settle()
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(1)

    await advance(MEETING_SUMMARY_POLL_MS * 10)

    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(1)
  })

  it('stops asking when the page is left', async () => {
    fakeTheClock()
    const { answered, unmount } = renderPage({ [`GET ${SUMMARY}`]: summaryRoute(PROCESSING) })
    await settle()
    await advance(MEETING_SUMMARY_POLL_MS)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2)

    unmount()
    await advance(MEETING_SUMMARY_POLL_MS * 10)

    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2)
  })

  it('stops asking about one meeting when the panel is given another', async () => {
    fakeTheClock()
    const other = '/api/meetings/meeting-2/summary'
    const answered = serveApi({
      [`GET ${SUMMARY}`]: summaryRoute(PROCESSING),
      [`GET ${other}`]: summaryRoute(summaryState({ can_edit: true })),
    })
    const { rerender } = render(<MeetingSummary meetingId={MEETING.meeting_id} />)
    await settle()
    expect(screen.getByRole('region', { name: TEXT.summaryHeading }).textContent).toContain(TEXT.summaryProcessing)

    rerender(<MeetingSummary meetingId="meeting-2" />)
    await settle()
    // The other meeting's state, and none of the first's.
    const panel = screen.getByRole('region', { name: TEXT.summaryHeading })
    expect(standing(panel).textContent).toBe(TEXT.summaryNone)

    await advance(MEETING_SUMMARY_POLL_MS * 10)

    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(1)
    expect(requestsTo(answered, 'GET', other)).toHaveLength(1)
  })

  it('stops asking and says so when a check fails, rather than leaving "being generated" on screen, and resumes on Try again', async () => {
    fakeTheClock()
    let reads = 0
    const { answered } = renderPage({
      [`GET ${SUMMARY}`]: () => {
        reads += 1
        // The first read and the retry answer; the check between them never arrives.
        if (reads === 2) return Promise.reject(new TypeError('Failed to fetch'))
        return summaryRoute(reads < 4 ? PROCESSING : READY)
      },
    })
    await settle()
    const panel = screen.getByRole('region', { name: TEXT.summaryHeading })

    await advance(MEETING_SUMMARY_POLL_MS)

    const alert = within(panel).getByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.summaryCheckFailed}${messageForStatus(NETWORK_ERROR_STATUS)}`)
    expect(document.body.textContent).not.toContain('Failed to fetch')
    expect(standing(panel).textContent).toBe('')
    await advance(MEETING_SUMMARY_POLL_MS * 10)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2)

    fireEvent.click(within(panel).getByRole('button', { name: TEXT.uploadRetry }))
    await settle()

    // Read again, still in flight, so the asking is back.
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(3)
    expect(within(panel).queryByRole('alert')).toBeNull()
    expect(standing(panel).textContent).toBe(TEXT.summaryProcessing)
    await advance(MEETING_SUMMARY_POLL_MS)
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(4)
    expect(panel.textContent).toContain(readySummary().narrative[0].text)
  })
})

/* ---- The transcript does not wait on the summary --------------------------- */

describe('NFR-20: the transcript is on the page whatever the summary does', () => {
  it('shows the transcript while the summary is still being read', async () => {
    const slow = heldResponse()
    renderPage({ [`GET ${SUMMARY}`]: slow.route })

    const transcript = await screen.findByRole('region', { name: TEXT.transcriptHeading })
    expect(transcript.textContent).toBe(MEETING.transcript_text)
    const panel = screen.getByRole('region', { name: TEXT.summaryHeading })
    expect(within(panel).getByRole('status').textContent).toBe(TEXT.loadingSummary)
    expect(screen.getByRole('region', { name: TEXT.actionItemsHeading }).textContent).toContain(TEXT.loadingActionItems)

    slow.release(summaryRoute(READY))
    await waitFor(() => expect(panel.textContent).toContain(readySummary().narrative[0].text))
    expect(screen.getByRole('region', { name: TEXT.transcriptHeading }).textContent).toBe(MEETING.transcript_text)
  })

  it.each([
    ['answers 500', { status: 500, body: { detail: 'Server Error (500)' } }, 'Something went wrong. Please try again.'],
    ['never arrives', () => Promise.reject(new TypeError('Failed to fetch')), messageForStatus(NETWORK_ERROR_STATUS)],
  ])('keeps the transcript and the record on the page when the summary read %s, and offers to try again', async (_case, failing, message) => {
    let fail = true
    const { answered } = renderPage({
      [`GET ${SUMMARY}`]: (url) => (fail ? (typeof failing === 'function' ? failing(url) : failing) : summaryRoute(READY)),
    })

    const panel = await summaryPanel()
    const alert = within(panel).getByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.summaryLoadFailed}${message}`)
    expect(document.body.textContent).not.toContain('Server Error')
    expect(document.body.textContent).not.toContain('Failed to fetch')

    // Everything the meeting's own read brought is still there.
    expect(screen.getByRole('heading', { level: 1, name: MEETING.title })).toBeTruthy()
    expect(screen.getByRole('region', { name: TEXT.transcriptHeading }).textContent).toBe(MEETING.transcript_text)
    // The other panel says once that it has nothing, and points at the reason.
    const items = screen.getByRole('region', { name: TEXT.actionItemsHeading })
    expect(items.textContent).toContain(TEXT.actionItemsUnavailable)
    expect(within(items).queryByRole('alert')).toBeNull()
    expect(within(items).queryAllByRole('button')).toEqual([])

    fail = false
    fireEvent.click(within(panel).getByRole('button', { name: TEXT.uploadRetry }))

    await waitFor(() => expect(panel.textContent).toContain(readySummary().narrative[0].text))
    expect(within(panel).queryByRole('alert')).toBeNull()
    expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2)
  })

  it('says the meeting could not be found when the summary read answers 404, and offers nothing to retry', async () => {
    renderPage({ [`GET ${SUMMARY}`]: { status: 404, body: SERVER_404 } })

    const panel = await summaryPanel()
    expect(within(panel).getByRole('alert').textContent).toBe(`${TEXT.documentNotFoundTitle}${TEXT.meetingNotFound}`)
    expect(document.body.textContent).not.toContain(SERVER_404.detail)
    expect(within(panel).queryAllByRole('button')).toEqual([])
  })
})
