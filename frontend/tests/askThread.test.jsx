/**
 * FR-13's "retaining the thread", with FR-12's citation link (D-61's gap 3), as
 * D-77 settles it: the address is the only source of truth for the active thread.
 * `/ask?c=<id>` names it, and `/ask` with no `c` names none.
 *
 * The Ask screen is rendered at its real path inside a MemoryRouter, beside a stub
 * where a document citation leads, with a probe that exposes the location and Back.
 * The stub is deliberately not the document screen: these tests are about what Ask
 * does when it is left and returned to, not about what it is left for.
 *
 * Each test defends one named property. Assertions on work an effect does — a
 * request sent, the location, focus — are made in `waitFor`, because `findBy…`
 * resolves on a commit and React runs passive effects a task later (found on PR
 * #29). Where the property is that something does NOT happen, the test first lets
 * any late work land (`letLateWorkLand`) and then looks.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { APP_TITLE, TEXT } from '../src/constants.js'
import Ask from '../src/pages/Ask.jsx'
import { CONVERSATION, answeredReply, heldResponse, serveApi } from './fakeApi.js'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

const X = {
  conversation_id: '6f1c2a54-0000-4000-8000-00000000000a',
  title: 'How much annual leave do I get?',
  last_updated_at: '2026-10-02T09:00:00Z',
}

const Y = {
  conversation_id: '6f1c2a54-0000-4000-8000-00000000000b',
  title: 'Who signs off a supplier review?',
  last_updated_at: '2026-10-01T09:00:00Z',
}

/** The thread a first question creates (`POST /api/conversations`). */
const NEW = CONVERSATION

// Each thread's one stored statement, so a turn on screen can be told by its text.
const X_STATEMENT = 'Full-time staff accrue four weeks of annual leave a year.'
const Y_STATEMENT = 'A supplier review is signed off by the finance lead.'
/** The statement of a live answer (`POST /api/ask`). */
const LIVE_STATEMENT = answeredReply().statements[0].text

const QUESTION = 'Does unused annual leave carry over?'

/** One stored turn, as `GET /api/conversations/{id}` returns it: no passages. */
function storedTurn(question, statement) {
  return {
    question,
    answered: true,
    asked_at: '2026-10-01T09:00:00Z',
    message: null,
    statements: [{ position: 1, text: statement, chunk_id: 'chunk-stored' }],
  }
}

/** A thread read with one stored turn, whose question is the thread's title. */
function threadRead(thread, statement) {
  return { body: { ...thread, turns: [storedTurn(thread.title, statement)] } }
}

/** The list and the two stored threads; `extra` adds routes or replaces these. */
function routes(extra = {}) {
  return {
    'GET /api/conversations': { body: [X, Y] },
    [`GET /api/conversations/${X.conversation_id}`]: threadRead(X, X_STATEMENT),
    [`GET /api/conversations/${Y.conversation_id}`]: threadRead(Y, Y_STATEMENT),
    ...extra,
  }
}

/** The create a first question sends. */
const CREATE = { 'POST /api/conversations': { status: 201, body: NEW } }

/* ---- Rendering ----------------------------------------------------------- */

/** The router's location, Back, Forward and a navigation, as the probe last saw them. */
const probe = { location: null, back: null, forward: null, go: null }

/** Exposes the router's location and history to the test, from inside the router. */
function HistoryProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  // A layout effect, not a passive one: it runs inside the commit that rendered this
  // location, before a `findBy…` waiting on that commit can resolve. A passive effect
  // runs a task later, so an assertion straight after `findBy…` could read the old
  // location (tests/documentRepository.test.jsx).
  useLayoutEffect(() => {
    probe.location = location
    probe.back = () => navigate(-1)
    probe.forward = () => navigate(1)
    probe.go = (to) => navigate(to)
  })
  return null
}

/** Where a document citation leads, standing in for the document screen. */
function SourceStub() {
  const { docId } = useParams()
  return <h1>{`Source ${docId}`}</h1>
}

/** An entry before the Ask screen, so a test can show that Back skips one. */
function StartStub() {
  return <h1>Start</h1>
}

/** The Ask screen at its real path, with a history to go Back and Forward through. */
function renderAsk(entries) {
  probe.location = null
  probe.back = null
  probe.forward = null
  probe.go = null
  render(
    <MemoryRouter initialEntries={entries}>
      <Routes>
        <Route path="/start" element={<StartStub />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/documents/:docId" element={<SourceStub />} />
      </Routes>
      <HistoryProbe />
    </MemoryRouter>,
  )
  return probe
}

/* ---- Helpers ------------------------------------------------------------- */

/** Every read of one thread, in order. */
function threadReads(answered, thread) {
  return answered.filter(
    (request) => request.method === 'GET' && request.path === `/api/conversations/${thread.conversation_id}`,
  )
}

/** Every read of the conversation list. */
function listReads(answered) {
  return answered.filter((request) => request.method === 'GET' && request.path === '/api/conversations')
}

/** Every question sent. */
function asks(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/ask')
}

function openButton(thread) {
  return screen.getByRole('button', { name: TEXT.conversationOpen(thread.title) })
}

function questionField() {
  return screen.getByLabelText(TEXT.askFieldLabel)
}

/** The list has loaded and is offering its threads. */
async function listOffers(thread) {
  await waitFor(() => expect(openButton(thread).disabled).toBe(false))
}

/**
 * A click as a browser makes one: the button takes focus, then is clicked.
 * `fireEvent.click` alone moves no focus, which would make an assertion about where
 * focus goes meaningless.
 */
function press(element) {
  element.focus()
  fireEvent.click(element)
}

/** Types a question and sends it. */
function ask(question) {
  fireEvent.change(questionField(), { target: { value: question } })
  fireEvent.click(screen.getByRole('button', { name: TEXT.askSubmit }))
}

/** Expands the live turn's first citation and follows its source link. */
async function followCitation() {
  const [marker] = await screen.findAllByRole('button', { name: TEXT.citationToggleLabel(1) })
  fireEvent.click(marker)
  const panel = document.getElementById(marker.getAttribute('aria-controls'))
  fireEvent.click(within(panel).getByRole('link', { name: TEXT.viewDocument }))
}

/**
 * Lets a reply released late, and anything it sets off, finish before a test looks
 * for something that must not have happened. Inside `act`, so every render and
 * effect queued in the meantime has run by the time it resolves.
 */
async function letLateWorkLand() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50))
  })
}

/* ---- Reading ------------------------------------------------------------- */

describe('D-77 rule 1: the thread the address names is read from the server', () => {
  it('shows the turns of the thread named in the address on mount, and marks it current', async () => {
    const answered = serveApi(routes())
    renderAsk([`/ask?c=${X.conversation_id}`])

    expect(await screen.findByText(X_STATEMENT)).toBeTruthy()
    expect(threadReads(answered, X)).toHaveLength(1)
    expect(threadReads(answered, Y)).toHaveLength(0)
    await waitFor(() => expect(openButton(X).getAttribute('aria-current')).toBe('true'))
    expect(openButton(Y).getAttribute('aria-current')).toBeNull()
  })

  it('sends no read for a thread the screen itself has just written to the address, so its live turn stays', async () => {
    const answered = serveApi(
      routes({
        ...CREATE,
        'POST /api/ask': { body: answeredReply() },
        // Served, so that a read nobody should send renders rather than being
        // refused: its stored turn has no passages and would replace the live one.
        [`GET /api/conversations/${NEW.conversation_id}`]: threadRead({ ...NEW, title: QUESTION }, LIVE_STATEMENT),
      }),
    )
    const probe = renderAsk(['/ask'])
    await listOffers(X)

    ask(QUESTION)
    expect(await screen.findByText(LIVE_STATEMENT)).toBeTruthy()
    await waitFor(() => expect(probe.location.search).toBe(`?c=${NEW.conversation_id}`))
    await letLateWorkLand()

    expect(threadReads(answered, NEW)).toHaveLength(0)
    // Still the live turn: its citation expands, which a stored turn's cannot.
    expect(screen.getByRole('button', { name: TEXT.citationToggleLabel(1) })).toBeTruthy()
  })

  it('does not let a slow read for Y replace X after Back to X', async () => {
    const yRead = heldResponse()
    const answered = serveApi(routes({ [`GET /api/conversations/${Y.conversation_id}`]: yRead.route }))
    const probe = renderAsk([`/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)
    await listOffers(Y)

    press(openButton(Y))
    await waitFor(() => expect(threadReads(answered, Y)).toHaveLength(1))
    act(() => probe.back())
    await waitFor(() => expect(probe.location.search).toBe(`?c=${X.conversation_id}`))

    yRead.release(threadRead(Y, Y_STATEMENT))
    await letLateWorkLand()

    expect(screen.queryByText(Y_STATEMENT)).toBeNull()
    expect(screen.getByText(X_STATEMENT)).toBeTruthy()
    expect(screen.queryByText(TEXT.loadingConversation)).toBeNull()
    // X stayed on screen throughout, so it was not read again.
    expect(threadReads(answered, X)).toHaveLength(1)
  })

  it('shows an empty thread when the address comes to name none, and keeps the draft', async () => {
    serveApi(routes())
    const probe = renderAsk(['/ask', `/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)
    fireEvent.change(questionField(), { target: { value: 'A draft not yet sent' } })

    act(() => probe.back())
    await waitFor(() => expect(screen.queryByText(X_STATEMENT)).toBeNull())

    expect(probe.location.search).toBe('')
    expect(screen.getByText(TEXT.threadEmpty)).toBeTruthy()
    expect(questionField().value).toBe('A draft not yet sent')
    expect(openButton(X).getAttribute('aria-current')).toBeNull()
  })
})

/* ---- Following a citation ------------------------------------------------ */

describe("D-61's gap 3: a citation followed in the same tab, then Back", () => {
  it('re-reads the thread from the server and shows its turn', async () => {
    const answered = serveApi(
      routes({
        ...CREATE,
        'POST /api/ask': { body: answeredReply() },
        [`GET /api/conversations/${NEW.conversation_id}`]: threadRead({ ...NEW, title: QUESTION }, LIVE_STATEMENT),
      }),
    )
    const probe = renderAsk(['/ask'])
    await listOffers(X)
    ask(QUESTION)

    await followCitation()
    expect(await screen.findByRole('heading', { name: 'Source doc-1' })).toBeTruthy()
    expect(probe.location.pathname).toBe('/documents/doc-1')
    expect(threadReads(answered, NEW)).toHaveLength(0)

    act(() => probe.back())
    await waitFor(() => expect(threadReads(answered, NEW)).toHaveLength(1))

    expect(probe.location.pathname).toBe('/ask')
    expect(probe.location.search).toBe(`?c=${NEW.conversation_id}`)
    expect(await screen.findByText(LIVE_STATEMENT)).toBeTruthy()
    // From the read, not from anything kept: a stored turn's citation does not
    // expand yet (item 4b), and the screen says so.
    expect(screen.queryByRole('button', { name: TEXT.citationToggleLabel(1) })).toBeNull()
    expect(screen.getByText(TEXT.threadReopenedNote)).toBeTruthy()
  })
})

/* ---- Writing ------------------------------------------------------------- */

describe('D-77 rule 3: the first question replaces the address it was asked from', () => {
  it('names the created thread in the address before the answer, dropping q, and replaces the entry rather than pushing one', async () => {
    const reply = heldResponse()
    const answered = serveApi(routes({ ...CREATE, 'POST /api/ask': reply.route }))
    const probe = renderAsk(['/start', `/ask?q=${encodeURIComponent(QUESTION)}`])

    // Prefilled from the search screen's link, and not sent for the user.
    expect(questionField().value).toBe(QUESTION)
    await listOffers(X)
    expect(asks(answered)).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: TEXT.askSubmit }))

    // The question is in flight and unanswered, and the address already names its
    // thread, with nothing else in it.
    await waitFor(() => expect(probe.location.search).toBe(`?c=${NEW.conversation_id}`))
    expect(probe.location.pathname).toBe('/ask')
    expect(asks(answered)).toHaveLength(1)
    expect(screen.queryByText(LIVE_STATEMENT)).toBeNull()

    reply.release({ body: answeredReply() })
    expect(await screen.findByText(LIVE_STATEMENT)).toBeTruthy()

    // Replaced, not pushed: Back goes to the entry before Ask, not to an empty /ask.
    act(() => probe.back())
    await waitFor(() => expect(probe.location.pathname).toBe('/start'))
  })
})

describe('D-77 rule 2: switching threads adds a history entry', () => {
  it('re-reads X when Back leaves a thread reopened from the list', async () => {
    const answered = serveApi(routes())
    const probe = renderAsk([`/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)
    await listOffers(Y)

    press(openButton(Y))
    expect(await screen.findByText(Y_STATEMENT)).toBeTruthy()
    expect(probe.location.search).toBe(`?c=${Y.conversation_id}`)
    expect(screen.queryByText(X_STATEMENT)).toBeNull()

    act(() => probe.back())
    await waitFor(() => expect(threadReads(answered, X)).toHaveLength(2))

    expect(probe.location.search).toBe(`?c=${X.conversation_id}`)
    expect(await screen.findByText(X_STATEMENT)).toBeTruthy()
    expect(screen.queryByText(Y_STATEMENT)).toBeNull()
  })

  it('adds no entry and sends no read when the thread already open is chosen again', async () => {
    const answered = serveApi(routes())
    const probe = renderAsk(['/start', `/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)
    await listOffers(X)
    const entry = probe.location.key

    press(openButton(X))
    await letLateWorkLand()

    expect(threadReads(answered, X)).toHaveLength(1)
    expect(probe.location.key).toBe(entry)
    act(() => probe.back())
    await waitFor(() => expect(probe.location.pathname).toBe('/start'))
  })

  it('adds an entry for Start a new topic, so Back returns to the thread it cleared', async () => {
    const answered = serveApi(routes())
    const probe = renderAsk([`/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)

    press(screen.getByRole('button', { name: TEXT.newTopic }))
    await waitFor(() => expect(probe.location.search).toBe(''))
    expect(probe.location.pathname).toBe('/ask')
    expect(screen.queryByText(X_STATEMENT)).toBeNull()

    act(() => probe.back())
    await waitFor(() => expect(threadReads(answered, X)).toHaveLength(2))
    expect(probe.location.search).toBe(`?c=${X.conversation_id}`)
    expect(await screen.findByText(X_STATEMENT)).toBeTruthy()
  })

  it('writes nothing for Start a new topic when the screen shows no turns, and still acknowledges it', async () => {
    serveApi(routes())
    const probe = renderAsk(['/start', '/ask'])
    await listOffers(X)
    const entry = probe.location.key

    press(screen.getByRole('button', { name: TEXT.newTopic }))
    await letLateWorkLand()

    expect(probe.location.key).toBe(entry)
    expect(screen.getByText(TEXT.threadNew)).toBeTruthy()
    expect(document.activeElement).toBe(questionField())
    act(() => probe.back())
    await waitFor(() => expect(probe.location.pathname).toBe('/start'))
  })

  it('writes nothing for Start a new topic on an empty thread the address names, so it is not left behind', async () => {
    // A reload of, or a return to, a thread whose first question failed: the address
    // names it and the server has no turns for it. It already is a new topic.
    serveApi(routes({ [`GET /api/conversations/${NEW.conversation_id}`]: { body: { ...NEW, turns: [] } } }))
    const probe = renderAsk(['/start', `/ask?c=${NEW.conversation_id}`])
    await waitFor(() => expect(screen.getByRole('button', { name: TEXT.newTopic }).disabled).toBe(false))
    expect(screen.getByText(TEXT.threadEmpty)).toBeTruthy()
    const entry = probe.location.key

    press(screen.getByRole('button', { name: TEXT.newTopic }))
    await letLateWorkLand()

    expect(probe.location.key).toBe(entry)
    expect(probe.location.search).toBe(`?c=${NEW.conversation_id}`)
    expect(screen.getByText(TEXT.threadNew)).toBeTruthy()
    expect(document.activeElement).toBe(questionField())
  })
})

/* ---- Replies that land late ---------------------------------------------- */

describe('D-77 rule 4: a reply for a thread the address no longer names is dropped', () => {
  it('shows a reply for X that lands after Back to Y neither in Y nor in the address', async () => {
    const reply = heldResponse()
    const answered = serveApi(routes({ 'POST /api/ask': reply.route }))
    const probe = renderAsk([`/ask?c=${Y.conversation_id}`, `/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)

    ask(QUESTION)
    await waitFor(() => expect(asks(answered)).toHaveLength(1))
    expect(asks(answered)[0].body).toEqual({ question: QUESTION, conversation_id: X.conversation_id })

    act(() => probe.back())
    expect(await screen.findByText(Y_STATEMENT)).toBeTruthy()
    const listReadsBefore = listReads(answered).length

    reply.release({ body: { ...answeredReply(), conversation: X } })
    // Handled: the question is no longer in flight, and the list is re-read because
    // X's title and time changed on the server.
    await waitFor(() => expect(screen.getByRole('button', { name: TEXT.askSubmit })).toBeTruthy())
    await waitFor(() => expect(listReads(answered)).toHaveLength(listReadsBefore + 1))
    await letLateWorkLand()

    expect(screen.queryByText(LIVE_STATEMENT)).toBeNull()
    expect(screen.getByText(Y_STATEMENT)).toBeTruthy()
    expect(probe.location.search).toBe(`?c=${Y.conversation_id}`)
    expect(screen.queryByText(TEXT.answerReady(1, 1))).toBeNull()
    expect(questionField().value).toBe(QUESTION)
  })
})

describe('D-77 rule d: a navigation away while a question is in flight is not undone when it lands', () => {
  it('stays where the reader went when the thread is created after they left', async () => {
    const create = heldResponse()
    serveApi(routes({ 'POST /api/conversations': create.route, 'POST /api/ask': { body: answeredReply() } }))
    const probe = renderAsk(['/ask'])
    await listOffers(X)

    ask(QUESTION)
    // Away by the navigation's own kind of link, before the thread exists.
    act(() => probe.go('/documents/doc-1'))
    expect(await screen.findByRole('heading', { name: 'Source doc-1' })).toBeTruthy()

    create.release({ status: 201, body: NEW })
    await letLateWorkLand()

    expect(probe.location.pathname).toBe('/documents/doc-1')
    expect(screen.getByRole('heading', { name: 'Source doc-1' })).toBeTruthy()
  })

  it('stays on a citation followed while the next question was in flight', async () => {
    const second = heldResponse()
    let questionsSent = 0
    serveApi(
      routes({
        ...CREATE,
        'POST /api/ask': () => {
          questionsSent += 1
          return questionsSent === 1 ? { body: answeredReply() } : second.route()
        },
      }),
    )
    const probe = renderAsk(['/ask'])
    await listOffers(X)
    ask(QUESTION)
    await screen.findByText(LIVE_STATEMENT)

    ask('What is the notice period for taking leave?')
    await waitFor(() => expect(questionsSent).toBe(2))
    await followCitation()
    expect(await screen.findByRole('heading', { name: 'Source doc-1' })).toBeTruthy()

    // A 404 for the thread asked in is the reply after which the screen writes the
    // address (rule 5), so it is the one that could pull the reader back.
    second.release({ status: 404, body: { detail: 'Not found.' } })
    await letLateWorkLand()

    expect(probe.location.pathname).toBe('/documents/doc-1')
    expect(screen.getByRole('heading', { name: 'Source doc-1' })).toBeTruthy()
  })
})

/* ---- A thread that is not there ------------------------------------------ */

describe('D-77 rule 5: a c that answers 404 is replaced with /ask', () => {
  it('ends at /ask with the notice still showing, and Back skips the dead address', async () => {
    const answered = serveApi({
      'GET /api/conversations': { body: [X] },
      'GET /api/conversations/not-a-thread': { status: 404, body: { detail: 'Not found.' } },
    })
    const probe = renderAsk(['/start', '/ask?c=not-a-thread'])

    await waitFor(() => expect(probe.location.search).toBe(''))
    expect(probe.location.pathname).toBe('/ask')
    await letLateWorkLand()

    const notice = screen.getByRole('alert')
    expect(notice.textContent).toContain(TEXT.conversationLoadFailed)
    expect(notice.textContent).toContain(TEXT.conversationNotFound)
    // The list is re-read, as after any 404 for a thread.
    expect(listReads(answered)).toHaveLength(2)

    act(() => probe.back())
    await waitFor(() => expect(probe.location.pathname).toBe('/start'))
  })

  it('keeps the notice when a thread opened from the list answers 404, and Back returns to the thread before it', async () => {
    const GONE = {
      conversation_id: '6f1c2a54-0000-4000-8000-00000000000f',
      title: 'A conversation no longer there',
      last_updated_at: '2026-09-30T09:00:00Z',
    }
    serveApi(
      routes({
        'GET /api/conversations': { body: [X, GONE] },
        [`GET /api/conversations/${GONE.conversation_id}`]: { status: 404, body: { detail: 'Not found.' } },
      }),
    )
    const probe = renderAsk([`/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)
    await listOffers(GONE)

    press(openButton(GONE))
    await waitFor(() => expect(probe.location.search).toBe(''))
    await letLateWorkLand()

    // The address naming no thread did not clear the notice the 404 put up.
    expect(screen.getByRole('alert').textContent).toContain(TEXT.conversationNotFound)
    expect(screen.queryByText(X_STATEMENT)).toBeNull()

    act(() => probe.back())
    await waitFor(() => expect(probe.location.search).toBe(`?c=${X.conversation_id}`))
    expect(await screen.findByText(X_STATEMENT)).toBeTruthy()
  })
})

/* ---- Rules D-77 left to the implementation ------------------------------- */

describe('D-77 rule 6: the tab title is static', () => {
  it('keeps the tab title "Ask" when the thread changes', async () => {
    serveApi(routes())
    renderAsk([`/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)
    await listOffers(Y)

    press(openButton(Y))
    await screen.findByText(Y_STATEMENT)
    await letLateWorkLand()

    expect(document.title).toBe(`Ask - ${APP_TITLE}`)
  })
})

describe('D-77, focus: only a click in the list moves it', () => {
  it('focuses the last turn of a thread opened from the list, and moves nothing for a read the address asked for', async () => {
    serveApi(routes())
    const probe = renderAsk([`/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)
    await letLateWorkLand()
    expect(document.activeElement).toBe(document.body)

    press(openButton(Y))
    const yTurn = (await screen.findByText(Y_STATEMENT)).closest('article')
    await waitFor(() => expect(document.activeElement).toBe(yTurn))

    act(() => probe.back())
    await screen.findByText(X_STATEMENT)
    await letLateWorkLand()
    expect(document.activeElement).toBe(document.body)
  })

  it('does not spend a click\'s focus on a later read of that thread the address asked for', async () => {
    const yRead = heldResponse()
    serveApi(routes({ [`GET /api/conversations/${Y.conversation_id}`]: yRead.route }))
    const probe = renderAsk([`/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)
    await listOffers(Y)

    // Chosen, then left before its read lands, then returned to by Forward.
    press(openButton(Y))
    await waitFor(() => expect(probe.location.search).toBe(`?c=${Y.conversation_id}`))
    act(() => probe.back())
    await waitFor(() => expect(probe.location.search).toBe(`?c=${X.conversation_id}`))
    act(() => probe.forward())
    await waitFor(() => expect(probe.location.search).toBe(`?c=${Y.conversation_id}`))

    yRead.release(threadRead(Y, Y_STATEMENT))
    const yTurn = (await screen.findByText(Y_STATEMENT)).closest('article')
    await letLateWorkLand()

    expect(document.activeElement).not.toBe(yTurn)
  })
})

describe('D-77, while a thread is read: nothing is asked into or cleared from it', () => {
  it('disables Ask and Start a new topic until the thread is on screen', async () => {
    const yRead = heldResponse()
    serveApi(routes({ [`GET /api/conversations/${Y.conversation_id}`]: yRead.route }))
    renderAsk([`/ask?c=${X.conversation_id}`])
    await screen.findByText(X_STATEMENT)
    await listOffers(Y)
    fireEvent.change(questionField(), { target: { value: QUESTION } })
    expect(screen.getByRole('button', { name: TEXT.askSubmit }).disabled).toBe(false)

    press(openButton(Y))
    expect(await screen.findByText(TEXT.loadingConversation)).toBeTruthy()
    expect(screen.getByRole('button', { name: TEXT.askSubmit }).disabled).toBe(true)
    expect(screen.getByRole('button', { name: TEXT.newTopic }).disabled).toBe(true)
    expect(openButton(X).disabled).toBe(true)

    yRead.release(threadRead(Y, Y_STATEMENT))
    await screen.findByText(Y_STATEMENT)
    expect(screen.getByRole('button', { name: TEXT.askSubmit }).disabled).toBe(false)
    expect(screen.getByRole('button', { name: TEXT.newTopic }).disabled).toBe(false)
  })
})
