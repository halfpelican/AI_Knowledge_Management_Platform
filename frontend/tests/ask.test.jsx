/**
 * The Ask screen (FR-12, FR-13), rendered whole against a faked API.
 *
 * Each test defends one named property. None of them is coverage of the screen.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import Ask from '../src/pages/Ask.jsx'
import { CONVERSATION, NO_ANSWER_MESSAGE, answeredReply, noAnswerReply, serveApi } from './fakeApi.js'

const QUESTION = 'How much annual leave do I get?'

function renderAsk() {
  return render(
    <MemoryRouter initialEntries={['/ask']}>
      <Ask />
    </MemoryRouter>,
  )
}

/** The routes one question needs: the list, the lazily created thread, the ask. */
function routesForOneQuestion(askRoute) {
  return {
    'GET /api/conversations': { body: [] },
    'POST /api/conversations': { status: 201, body: CONVERSATION },
    'POST /api/ask': askRoute,
  }
}

/** Types a question and sends it, then waits for the screen to settle on a turn or a failure. */
async function askOnce(question = QUESTION) {
  await screen.findByText(TEXT.noConversations)
  fireEvent.change(screen.getByLabelText(TEXT.askFieldLabel), { target: { value: question } })
  fireEvent.click(screen.getByRole('button', { name: TEXT.askSubmit }))
}

/** The thread section's markup once a turn has rendered in it. */
async function threadAfterAsking(reply) {
  serveApi(routesForOneQuestion({ body: reply }))
  const { unmount } = renderAsk()
  await askOnce()
  const thread = (await screen.findByText(`${TEXT.askQuestionLabel}:`)).closest('section')
  const html = thread.innerHTML
  unmount()
  return html
}

/** True where nothing on the path from the node to the root hides it. */
function isOnScreen(node) {
  for (let current = node; current; current = current.parentElement) {
    if (current.hidden || current.classList?.contains('visually-hidden')) return false
  }
  return true
}

describe('invariant 6: no interface state shows an uncited statement', () => {
  it('renders nothing at all for a rejected statement', async () => {
    // A reply cannot carry a rejected statement: the API has no field for one
    // (src/api/ask.js). This is the reply as if a regression had put one there,
    // with the record-only fields beside it, and the screen must render it
    // byte-for-byte as it renders the reply without them — no greyed-out text, no
    // "withheld" panel, no count of what was removed.
    const rejected = 'Staff may carry over unlimited leave indefinitely.'
    const leaking = {
      ...answeredReply(),
      rejected_statements: [{ position: 2, text: rejected, chunk_id: 'chunk-fabricated' }],
      rejected_count: 1,
      no_answer_reason: 'no_verified_statements',
    }

    const clean = await threadAfterAsking(answeredReply())
    const withRejection = await threadAfterAsking(leaking)

    expect(withRejection).not.toContain(rejected)
    expect(withRejection).toBe(clean)
    expect(clean).toContain(answeredReply().statements[0].text)
  })
})

describe('FR-12 no-answer state', () => {
  it('renders NO_ANSWER_MESSAGE, identically on path A and path B', async () => {
    // Path A (nothing passed the threshold) and path B (nothing survived
    // verification) are byte-identical on the wire and are told apart only in
    // QueryLog.no_answer_reason (invariant 7). Path B is given the record-only
    // fields here, as if they had leaked, so that "identical" is a property of the
    // screen and not only of the server.
    const pathA = noAnswerReply()
    const pathB = { ...noAnswerReply(), no_answer_reason: 'no_verified_statements', rejected_count: 2 }

    const renderedA = await threadAfterAsking(pathA)
    const renderedB = await threadAfterAsking(pathB)

    expect(renderedA).toContain(NO_ANSWER_MESSAGE)
    expect(renderedA).toContain(TEXT.noAnswerTitle)
    expect(renderedB).toBe(renderedA)
    // The copy used when a reply somehow carries no message says the same thing,
    // so the no-answer state has one wording whichever way it is reached.
    expect(TEXT.noAnswerFallback).toBe(NO_ANSWER_MESSAGE)
  })

  it('renders a turn re-scoped away from the reader as the no-answer state', async () => {
    // A stored turn that WAS answered from material this role may no longer read.
    // The server re-scopes it on read (D-48) and sends it exactly as a turn that was
    // never answered — no provenance_removed key, no count. The screen must show
    // the no-answer state: not blank, and not a notice that anything was removed,
    // since that notice would disclose that restricted material exists (invariant 1).
    const rescoped = { question: QUESTION, answered: false, asked_at: '2026-09-20T10:00:00Z', message: NO_ANSWER_MESSAGE, statements: [] }
    const thread = { ...CONVERSATION, title: QUESTION, turns: [rescoped] }
    serveApi({
      'GET /api/conversations': { body: [{ ...CONVERSATION, title: QUESTION }] },
      [`GET /api/conversations/${CONVERSATION.conversation_id}`]: { body: thread },
    })
    renderAsk()

    fireEvent.click(await screen.findByRole('button', { name: TEXT.conversationOpen(QUESTION) }))
    const turn = (await screen.findByText(`${TEXT.askQuestionLabel}:`)).closest('article')

    expect(within(turn).getByText(TEXT.noAnswerTitle)).toBeTruthy()
    expect(within(turn).getByText(NO_ANSWER_MESSAGE)).toBeTruthy()
    expect(turn.textContent).not.toContain(TEXT.provenanceRemovedTitle)
    expect(turn.textContent).not.toMatch(/remov|withh|restrict|permission|hidden/i)
  })
})

describe('NFR-19', () => {
  it('renders the AI-unavailable notice on a 503', async () => {
    serveApi(routesForOneQuestion({ status: 503, body: { detail: 'Service unavailable.' } }))
    renderAsk()
    await askOnce()

    const notice = (await screen.findByText(TEXT.askUnavailableTitle)).closest('[role="alert"]')
    expect(notice).toBeTruthy()
    expect(notice.textContent).toContain('The AI service is currently unavailable. Please try again shortly.')
    expect(notice.textContent).toContain(TEXT.askNotRecorded)
    // The question is kept, because no QueryLog row was written and it can be sent again.
    expect(screen.getByLabelText(TEXT.askFieldLabel).value).toBe(QUESTION)
  })
})

describe('usability finding 1', () => {
  it('acknowledges an arriving answer visibly, not only to assistive technology', async () => {
    serveApi(routesForOneQuestion({ body: answeredReply() }))
    renderAsk()
    await askOnce()

    const acknowledgement = await screen.findByText(TEXT.answerReady(1, 1))
    expect(acknowledgement.getAttribute('role')).toBe('status')
    expect(isOnScreen(acknowledgement)).toBe(true)
  })
})
