/**
 * FR-12: "Where no sufficiently relevant content is retrieved, the interface states
 * plainly that it cannot answer from the available knowledge base and does not present
 * a speculative answer. Any partially related items found are offered, clearly
 * labelled as partial matches."
 *
 * The label is on the Ask screen's no-answer state, where `POST /api/ask` carries
 * `partial_matches` (docs/api-contract.md); the keyword search screen has no partial
 * matches. What is offered, and that it is in the asker's scope, are the server's
 * (D-56, pytest's); the no-answer copy itself is tests/ask.test.jsx's. Defended here:
 * the items are offered under a label naming them partial matches, as links to read
 * and never as passage text, and the label appears only where there is something under
 * it and never beside an answer.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import Ask from '../src/pages/Ask.jsx'
import { formatDate } from '../src/utils/dates.js'
import { CONVERSATION, NO_ANSWER_MESSAGE, answeredReply, noAnswerReply, serveApi } from './fakeApi.js'

const QUESTION = 'What is the parental leave entitlement?'

const PARENTAL_GUIDANCE = {
  source_type: 'document',
  source_id: 'doc-7',
  title: 'Parental leave guidance',
  date: '2026-07-14T11:30:00+10:00',
}

const HR_REVIEW = {
  source_type: 'meeting',
  source_id: 'meeting-3',
  title: 'HR policy review',
  date: '2026-08-02',
}

function renderAsk() {
  return render(
    <MemoryRouter initialEntries={['/ask']}>
      <Ask />
    </MemoryRouter>,
  )
}

/** Asks one question against `reply` and waits for its turn to render. */
async function askAgainst(reply) {
  serveApi({
    'GET /api/conversations': { body: [] },
    'POST /api/conversations': { status: 201, body: CONVERSATION },
    'POST /api/ask': { body: reply },
  })
  renderAsk()
  await screen.findByText(TEXT.noConversations)
  fireEvent.change(screen.getByLabelText(TEXT.askFieldLabel), { target: { value: QUESTION } })
  fireEvent.click(screen.getByRole('button', { name: TEXT.askSubmit }))
  return (await screen.findByText(`${TEXT.askQuestionLabel}:`)).closest('section')
}

/** Any region on the page whose name calls its contents partial matches. */
function partialMatchRegions() {
  return screen.queryAllByRole('region', { name: /partial match/i })
}

describe('FR-12: partially related items, labelled as partial matches', () => {
  it('offers them under the no-answer statement, labelled as partial matches and as not an answer, each a link to its source with its type and date and no passage text', async () => {
    // The contract's entries carry no passage text. One is given a snippet here, as if
    // it had leaked, so that "no passage text" is a property of the screen as well.
    const leaked = 'Primary carers receive eighteen weeks of paid parental leave.'
    const reply = { ...noAnswerReply(), partial_matches: [{ ...PARENTAL_GUIDANCE, snippet: leaked }, HR_REVIEW] }
    await askAgainst(reply)

    await screen.findByText(NO_ANSWER_MESSAGE)
    const regions = partialMatchRegions()
    expect(regions).toHaveLength(1)
    const offered = regions[0]
    expect(within(offered).getByRole('heading').textContent).toMatch(/^partial matches$/i)
    expect(offered.textContent).toMatch(/not an answer/i)

    const items = within(offered).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    for (const [item, match, href, type] of [
      [items[0], PARENTAL_GUIDANCE, '/documents/doc-7', 'Document'],
      [items[1], HR_REVIEW, '/meetings/meeting-3', 'Meeting'],
    ]) {
      expect(within(item).getByRole('link', { name: match.title }).getAttribute('href')).toBe(href)
      expect(item.textContent).toContain(`Type: ${type}`)
      expect(item.querySelector('time').textContent).toBe(formatDate(match.date))
    }

    expect(document.body.textContent).not.toContain(leaked)
    // A no-answer is not an answer: no answer heading, no Sources panel, nothing cited.
    expect(screen.queryByRole('heading', { name: TEXT.answerHeading })).toBeNull()
    expect(screen.queryByRole('heading', { name: TEXT.sourcesHeading })).toBeNull()
  })

  it('shows no partial-matches label when the reply offers none, and never beside an answer', async () => {
    const thread = await askAgainst(noAnswerReply())
    await within(thread).findByText(NO_ANSWER_MESSAGE)
    expect(partialMatchRegions()).toEqual([])
    expect(thread.textContent).not.toMatch(/partial match/i)
  })

  it('does not offer partial matches beside an answer, even where a reply carried some', async () => {
    // The contract sends [] with every answered reply. Were a reply ever to carry
    // items, setting unadmitted material beside cited statements would present it as
    // though it supported the answer, so the answered state has no place for them.
    const reply = { ...answeredReply(), partial_matches: [PARENTAL_GUIDANCE] }
    const thread = await askAgainst(reply)
    await within(thread).findByText('Annual leave accrues at four weeks a year.')
    expect(partialMatchRegions()).toEqual([])
    expect(screen.queryByRole('link', { name: PARENTAL_GUIDANCE.title })).toBeNull()
  })
})
