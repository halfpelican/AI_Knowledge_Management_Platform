/**
 * D-79 on the Ask screen (FR-12, FR-13): the two 429s `POST /api/ask` can answer,
 * and the rate 429 on the create that precedes a first question (D-80).
 *
 * The bodies are the contract's (docs/api-contract.md, "Stage 5 item 5"): the
 * in-flight 429 is `{"detail": "...", "code": "ask_in_flight"}` with no
 * `Retry-After`, and a rate 429 is DRF's `{"detail": "Request was throttled. ..."}`
 * with a `Retry-After` in seconds. Whether the server sends them, and when, is
 * pytest's. What these defend is what only the screen can get right: which text is
 * shown for which body, that the question survives, and that nothing is added.
 *
 * Assertions on effect-driven work are made in `waitFor`; the probe records in a
 * layout effect (tests/askThread.test.jsx says why).
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import Ask from '../src/pages/Ask.jsx'
import { CONVERSATION, answeredReply, serveApi, storedAnsweredTurn } from './fakeApi.js'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

/** A thread with one stored turn, as `GET /api/conversations/{id}` returns it. */
const X = {
  conversation_id: '6f1c2a54-0000-4000-8000-00000000000a',
  title: 'How much annual leave do I get?',
  last_updated_at: '2026-10-02T09:00:00Z',
}
const X_STATEMENT = 'Full-time staff accrue four weeks of annual leave a year.'

/** The thread a first question creates. */
const NEW = CONVERSATION

const QUESTION = 'Does unused annual leave carry over?'
const LIVE_STATEMENT = answeredReply().statements[0].text

/** The contract's in-flight body, word for word. */
const IN_FLIGHT = { detail: 'Your previous question is still being answered.', code: 'ask_in_flight' }

/** A rate 429 as DRF sends it: its own body, and `Retry-After` in seconds. */
function throttled(seconds) {
  return {
    status: 429,
    body: { detail: `Request was throttled. Expected available in ${seconds} seconds.` },
    headers: { 'Retry-After': String(seconds) },
  }
}

/** The texts these 429s must never be shown as. */
const AI_UNAVAILABLE = 'The AI service is currently unavailable. Please try again shortly.'
const LOGIN_THROTTLED = 'Too many attempts. Please wait a minute and try again.'

function threadXRoutes(extra = {}) {
  return {
    'GET /api/conversations': { body: [X] },
    [`GET /api/conversations/${X.conversation_id}`]: {
      body: {
        ...X,
        turns: [
          storedAnsweredTurn({
            question: X.title,
            statements: [{ position: 1, text: X_STATEMENT, chunk_id: 'chunk-x' }],
            sources: [
              {
                source_type: 'document',
                source_id: 'doc-x',
                title: 'Leave policy',
                date: '2026-08-01',
                passages: [{ chunk_id: 'chunk-x', text: 'Four weeks a year.' }],
              },
            ],
          }),
        ],
      },
    },
    ...extra,
  }
}

/* ---- Rendering ----------------------------------------------------------- */

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

/* ---- Helpers ------------------------------------------------------------- */

function questionField() {
  return screen.getByLabelText(TEXT.askFieldLabel)
}

function askButton() {
  return screen.getByRole('button', { name: TEXT.askSubmit })
}

/** Types the question and sends it, once the screen will take one. */
async function ask(question = QUESTION) {
  fireEvent.change(questionField(), { target: { value: question } })
  await waitFor(() => expect(askButton().disabled).toBe(false))
  fireEvent.click(askButton())
}

function requests(answered, method, path) {
  return answered.filter((request) => request.method === method && request.path === path)
}

/** The notice above the question field, found by its title. */
async function noticeTitled(title) {
  const heading = await screen.findByText(title)
  return heading.closest('.notice')
}

/** Every turn on screen. */
function turnCount() {
  return screen.queryAllByText(`${TEXT.askQuestionLabel}:`).length
}

/** Lets anything a landed reply set off finish before looking for what must not have happened. */
async function letLateWorkLand() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50))
  })
}

/* ---- The in-flight 429 --------------------------------------------------- */

describe('D-79: a 429 while the previous question is still being answered', () => {
  it('shows its own text, not the AI-unavailable notice or login\'s text, keeps the question and adds no turn', async () => {
    // Reached here as after Back to a thread whose ask is still pending: the screen
    // remounted, so it does not know, and the server answers at once.
    const answered = serveApi(threadXRoutes({ 'POST /api/ask': { status: 429, body: IN_FLIGHT } }))
    renderAsk(`/ask?c=${X.conversation_id}`)
    await screen.findByText(X_STATEMENT)

    await ask()
    const notice = await noticeTitled(TEXT.askInFlightTitle)

    expect(notice.textContent).toContain(TEXT.askInFlight)
    expect(notice.classList.contains('notice--unavailable')).toBe(false)
    expect(document.body.textContent).not.toContain(TEXT.askUnavailableTitle)
    expect(document.body.textContent).not.toContain(AI_UNAVAILABLE)
    expect(document.body.textContent).not.toContain(LOGIN_THROTTLED)
    expect(document.body.textContent).not.toContain(TEXT.askRateLimitedTitle)
    // It promises no time: the reply carried none.
    expect(notice.textContent).not.toMatch(/\d+ (second|minute)/)

    await letLateWorkLand()
    expect(questionField().value).toBe(QUESTION)
    expect(turnCount()).toBe(1)
    expect(screen.queryByText(TEXT.noAnswerReady)).toBeNull()
    expect(requests(answered, 'POST', '/api/ask')[0].body).toEqual({
      question: QUESTION,
      conversation_id: X.conversation_id,
    })
  })

  it('is told apart from a rate 429 by `code` alone: same status, the same detail, different bodies', async () => {
    // Both bodies carry the in-flight detail word for word; only `code` differs. A
    // screen reading `detail` would show the same notice twice.
    let sent = 0
    serveApi(
      threadXRoutes({
        'POST /api/ask': () => {
          sent += 1
          return sent === 1
            ? { status: 429, body: IN_FLIGHT }
            : { status: 429, body: { detail: IN_FLIGHT.detail }, headers: { 'Retry-After': '20' } }
        },
      }),
    )
    renderAsk(`/ask?c=${X.conversation_id}`)
    await screen.findByText(X_STATEMENT)

    await ask()
    expect((await noticeTitled(TEXT.askInFlightTitle)).textContent).toContain(TEXT.askInFlight)

    await ask()
    const rate = await noticeTitled(TEXT.askRateLimitedTitle)
    expect(rate.textContent).toContain(TEXT.askRateLimited('in 20 seconds'))
    expect(screen.queryByText(TEXT.askInFlightTitle)).toBeNull()
    expect(questionField().value).toBe(QUESTION)
    expect(turnCount()).toBe(1)
  })
})

/* ---- The rate 429 -------------------------------------------------------- */

describe('D-79: a rate 429 on POST /api/ask', () => {
  it('says when the user can ask again, from Retry-After, keeps the question, and the retry reuses the empty thread', async () => {
    let sent = 0
    const answered = serveApi({
      'GET /api/conversations': { body: [] },
      'POST /api/conversations': { status: 201, body: NEW },
      'POST /api/ask': () => {
        sent += 1
        return sent === 1 ? throttled(42) : { body: answeredReply() }
      },
    })
    renderAsk('/ask')
    await screen.findByText(TEXT.noConversations)

    await ask()
    const notice = await noticeTitled(TEXT.askRateLimitedTitle)

    expect(notice.textContent).toContain(TEXT.askRateLimited('in 42 seconds'))
    expect(notice.textContent).not.toContain('Request was throttled')
    expect(document.body.textContent).not.toContain(LOGIN_THROTTLED)
    expect(document.body.textContent).not.toContain(TEXT.askInFlightTitle)
    expect(document.body.textContent).not.toContain(AI_UNAVAILABLE)
    await letLateWorkLand()
    expect(questionField().value).toBe(QUESTION)
    expect(turnCount()).toBe(0)

    // Nothing was recorded, so the thread created for it is still empty and is
    // where the retry goes: one create, and both asks name it.
    fireEvent.click(askButton())
    expect(await screen.findByText(LIVE_STATEMENT)).toBeTruthy()
    expect(requests(answered, 'POST', '/api/conversations')).toHaveLength(1)
    expect(requests(answered, 'POST', '/api/ask').map((request) => request.body.conversation_id)).toEqual([
      NEW.conversation_id,
      NEW.conversation_id,
    ])
  })

  it('keeps the empty thread as the place to go back to: a new topic started from another thread returns to it, and no second thread is made', async () => {
    // src/utils/threads.js `unusedThreadAfterFailure`: a 429 wrote nothing, as a 503
    // writes nothing, so the thread its question created is still empty. Leaving it
    // for X and starting a new topic goes back into it instead of creating another.
    let sent = 0
    const answered = serveApi(
      threadXRoutes({
        'POST /api/conversations': { status: 201, body: NEW },
        'POST /api/ask': () => {
          sent += 1
          return sent === 1 ? throttled(42) : { body: answeredReply() }
        },
      }),
    )
    const probe = renderAsk('/ask')
    const openX = await screen.findByRole('button', { name: TEXT.conversationOpen(X.title) })

    await ask()
    await noticeTitled(TEXT.askRateLimitedTitle)
    await waitFor(() => expect(probe.location.search).toBe(`?c=${NEW.conversation_id}`))
    await waitFor(() => expect(openX.disabled).toBe(false))

    fireEvent.click(openX)
    expect(await screen.findByText(X_STATEMENT)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: TEXT.newTopic }))
    await waitFor(() => expect(probe.location.search).toBe(`?c=${NEW.conversation_id}`))

    await ask()
    expect(await screen.findByText(LIVE_STATEMENT)).toBeTruthy()
    expect(requests(answered, 'POST', '/api/conversations')).toHaveLength(1)
    expect(requests(answered, 'POST', '/api/ask').map((request) => request.body.conversation_id)).toEqual([
      NEW.conversation_id,
      NEW.conversation_id,
    ])
  })
})

describe('D-79, D-80: a 429 on the create that precedes a first question', () => {
  it('shows the rate wording, keeps the question, sends no ask, and the next attempt creates the thread it asks in', async () => {
    const SECOND = { ...NEW, conversation_id: '6f1c2a54-0000-4000-8000-0000000000c2' }
    let created = 0
    const answered = serveApi({
      'GET /api/conversations': { body: [] },
      'POST /api/conversations': () => {
        created += 1
        return created === 1 ? throttled(7) : { status: 201, body: SECOND }
      },
      'POST /api/ask': { body: { ...answeredReply(), conversation: SECOND } },
    })
    const probe = renderAsk('/ask')
    await screen.findByText(TEXT.noConversations)

    await ask()
    const notice = await noticeTitled(TEXT.askRateLimitedTitle)

    expect(notice.textContent).toContain(TEXT.askRateLimited('in 7 seconds'))
    expect(document.body.textContent).not.toContain(LOGIN_THROTTLED)
    await letLateWorkLand()
    expect(questionField().value).toBe(QUESTION)
    expect(requests(answered, 'POST', '/api/ask')).toHaveLength(0)
    // Nothing was created, so the address names no thread.
    expect(probe.location.search).toBe('')

    fireEvent.click(askButton())
    expect(await screen.findByText(LIVE_STATEMENT)).toBeTruthy()
    expect(requests(answered, 'POST', '/api/conversations')).toHaveLength(2)
    const asks = requests(answered, 'POST', '/api/ask')
    expect(asks).toHaveLength(1)
    expect(asks[0].body).toEqual({ question: QUESTION, conversation_id: SECOND.conversation_id })
    await waitFor(() => expect(probe.location.search).toBe(`?c=${SECOND.conversation_id}`))
  })
})
