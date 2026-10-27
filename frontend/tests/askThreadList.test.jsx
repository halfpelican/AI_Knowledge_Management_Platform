/**
 * D-80 on the Ask screen (FR-13): `GET /api/conversations` leaves out a thread
 * nobody has asked anything in, and the screen shows the list exactly as sent.
 *
 * The list route here behaves as D-80's server does: it lists the thread a first
 * question created only once a turn has landed in it. The filter itself is the
 * server's and is tested in pytest. What only the screen can get right is that it
 * adds no entry of its own for the empty thread it is showing, and that once the
 * first turn lands it re-reads the list and marks that thread as current, for
 * assistive technology as well as visually (`aria-current`).
 *
 * Assertions on effect-driven work are made in `waitFor`; the probe records in a
 * layout effect (tests/askThread.test.jsx says why).
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import Ask from '../src/pages/Ask.jsx'
import { CONVERSATION, answeredReply, serveApi } from './fakeApi.js'

/** A thread with a turn in it, so the list is never empty and "current" has a rival. */
const Y = {
  conversation_id: '6f1c2a54-0000-4000-8000-00000000000b',
  title: 'Who signs off a supplier review?',
  last_updated_at: '2026-10-01T09:00:00Z',
}

/** The thread a first question creates, titled "New conversation" until a turn lands (D-43). */
const NEW = CONVERSATION

const QUESTION = 'Does unused annual leave carry over?'
const LIVE_STATEMENT = answeredReply().statements[0].text

/** NEW once its first turn has landed: renamed from the question (D-43), and now listed (D-80). */
const NEW_WITH_TURN = { ...NEW, title: QUESTION, last_updated_at: '2026-10-21T09:00:00Z' }

/**
 * `GET /api/conversations` and `POST /api/ask` as D-80's server answers them: the
 * list holds NEW only after an ask has landed in it. `firstAsk` answers the first
 * question; every later one is answered.
 */
function d80Routes({ firstAsk, extra = {} }) {
  let landed = false
  let sent = 0
  return {
    'GET /api/conversations': () => ({ body: landed ? [NEW_WITH_TURN, Y] : [Y] }),
    'POST /api/ask': () => {
      sent += 1
      const reply = sent === 1 ? firstAsk : { body: { ...answeredReply(), conversation: NEW_WITH_TURN } }
      if ((reply.status ?? 200) === 200) landed = true
      return reply
    },
    ...extra,
  }
}

const probe = { location: null }

function LocationProbe() {
  const location = useLocation()
  useLayoutEffect(() => {
    probe.location = location
  })
  return null
}

function renderAsk(path) {
  probe.location = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/ask" element={<Ask />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
  return probe
}

function threadList() {
  return screen.getByRole('complementary', { name: TEXT.conversationsHeading })
}

function openButton(title) {
  return within(threadList()).queryByRole('button', { name: TEXT.conversationOpen(title) })
}

function askButton() {
  return screen.getByRole('button', { name: TEXT.askSubmit })
}

function listReads(answered) {
  return answered.filter((request) => request.method === 'GET' && request.path === '/api/conversations')
}

describe('D-80: an empty active thread is not in the list, and its first turn puts it there, marked current', () => {
  it('lists nothing for the thread a failed first question created, then lists it as current once a turn lands', async () => {
    const answered = serveApi(
      d80Routes({
        firstAsk: { status: 503, body: { detail: 'Service unavailable.' } },
        extra: { 'POST /api/conversations': { status: 201, body: NEW } },
      }),
    )
    const probe = renderAsk('/ask')
    await waitFor(() => expect(openButton(Y.title)).toBeTruthy())

    fireEvent.change(screen.getByLabelText(TEXT.askFieldLabel), { target: { value: QUESTION } })
    fireEvent.click(askButton())
    await screen.findByText(TEXT.askUnavailableTitle)

    // The empty thread is on screen and in the address, and not in the list: the
    // screen added no entry of its own, under either title it could have used.
    await waitFor(() => expect(probe.location.search).toBe(`?c=${NEW.conversation_id}`))
    expect(openButton(NEW.title)).toBeNull()
    expect(openButton(QUESTION)).toBeNull()
    expect(within(threadList()).queryAllByRole('button')).toHaveLength(1)
    expect(within(threadList()).queryByText(TEXT.conversationCurrent, { exact: false })).toBeNull()
    expect(openButton(Y.title).getAttribute('aria-current')).toBeNull()
    const readsBeforeTurn = listReads(answered).length

    // The question stayed in the field; sent again, it lands in the same thread.
    await waitFor(() => expect(askButton().disabled).toBe(false))
    fireEvent.click(askButton())
    expect(await screen.findByText(LIVE_STATEMENT)).toBeTruthy()

    await waitFor(() => expect(listReads(answered).length).toBeGreaterThan(readsBeforeTurn))
    await waitFor(() => expect(openButton(QUESTION)?.getAttribute('aria-current')).toBe('true'))
    expect(within(openButton(QUESTION)).getByText(TEXT.conversationCurrent, { exact: false })).toBeTruthy()
    expect(openButton(Y.title).getAttribute('aria-current')).toBeNull()
  })

  it('marks nothing current for an empty thread the address names, and marks it once its first turn lands', async () => {
    // A reload of, or a return to, a thread whose first question failed (D-77): the
    // server still returns it by id, with no turns, and does not list it.
    const answered = serveApi(
      d80Routes({
        firstAsk: { body: { ...answeredReply(), conversation: NEW_WITH_TURN } },
        extra: { [`GET /api/conversations/${NEW.conversation_id}`]: { body: { ...NEW, turns: [] } } },
      }),
    )
    renderAsk(`/ask?c=${NEW.conversation_id}`)
    await waitFor(() => expect(openButton(Y.title)).toBeTruthy())
    await waitFor(() => expect(screen.getByRole('button', { name: TEXT.newTopic }).disabled).toBe(false))

    expect(screen.getByText(TEXT.threadEmpty)).toBeTruthy()
    expect(openButton(NEW.title)).toBeNull()
    expect(within(threadList()).queryAllByRole('button', { current: true })).toHaveLength(0)

    fireEvent.change(screen.getByLabelText(TEXT.askFieldLabel), { target: { value: QUESTION } })
    await waitFor(() => expect(askButton().disabled).toBe(false))
    fireEvent.click(askButton())
    expect(await screen.findByText(LIVE_STATEMENT)).toBeTruthy()

    await waitFor(() => expect(openButton(QUESTION)?.getAttribute('aria-current')).toBe('true'))
    // Asked in the thread the address named; nothing was created.
    const asks = answered.filter((request) => request.method === 'POST' && request.path === '/api/ask')
    expect(asks.map((request) => request.body.conversation_id)).toEqual([NEW.conversation_id])
  })
})
