/**
 * FR-12 on a REOPENED turn (D-61's gap 4, settled by D-78). A turn read back from
 * `GET /api/conversations/{id}` carries the sources it consulted, so its citations
 * expand to their passages and link to their sources, and its Sources panel shows,
 * as a live turn's do. Also the provenance-removed state, which D-62 recorded as
 * untested.
 *
 * The thread is named in the address and read on mount (D-77), which is how Back
 * from a citation, a reload and a link all reach it. Everything asserted here is
 * rendered in the commit that puts the read's turns on screen, or by a click after
 * it, so nothing waits on a passive effect.
 *
 * Each test defends one named property.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import Ask from '../src/pages/Ask.jsx'
import {
  NO_ANSWER_MESSAGE,
  PROVENANCE_REMOVED_MESSAGE,
  serveApi,
  storedAnsweredTurn,
  storedProvenanceRemovedTurn,
} from './fakeApi.js'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

const THREAD = {
  conversation_id: '6f1c2a54-0000-4000-8000-0000000000c1',
  title: 'How much annual leave do I get?',
  last_updated_at: '2026-10-02T09:00:00Z',
}

const QUESTION = THREAD.title

/** Cited by statement 1, and holding a second passage nothing cited. */
const LEAVE_POLICY = {
  source_type: 'document',
  source_id: 'doc-leave',
  title: 'Leave policy',
  date: '2026-08-01T10:00:00Z',
  passages: [
    { chunk_id: 'chunk-leave-1', text: 'Full-time staff accrue four weeks of annual leave per year.' },
    { chunk_id: 'chunk-leave-2', text: 'Leave requests are approved by the line manager.' },
  ],
}

/** Cited by statement 2. */
const PLANNING_MEETING = {
  source_type: 'meeting',
  source_id: 'meeting-plan',
  title: 'Leave planning meeting',
  date: '2026-07-14T11:30:00Z',
  passages: [{ chunk_id: 'chunk-meeting-1', text: 'The meeting agreed that part-time staff accrue leave pro rata.' }],
}

/** Consulted, and cited by no statement. */
const CARRY_OVER = {
  source_type: 'document',
  source_id: 'doc-carry',
  title: 'Carry-over guidance',
  date: '2026-06-02T09:00:00Z',
  passages: [{ chunk_id: 'chunk-carry-1', text: 'Up to five days of leave may be carried into the next year.' }],
}

const STATEMENTS = [
  { position: 1, text: 'Full-time staff accrue four weeks of leave a year.', chunk_id: 'chunk-leave-1' },
  { position: 2, text: 'Part-time staff accrue leave pro rata.', chunk_id: 'chunk-meeting-1' },
]

/** An answered turn as the thread read sends it: three items consulted, in rank order, two of them cited. */
function answeredTurn() {
  return storedAnsweredTurn({
    question: QUESTION,
    statements: STATEMENTS,
    sources: [LEAVE_POLICY, PLANNING_MEETING, CARRY_OVER],
  })
}

/* ---- Rendering ----------------------------------------------------------- */

/**
 * Serves one thread holding `turn`, renders Ask at that thread's address, and
 * returns the turn's article once the read has put it on screen.
 */
async function reopen(turn) {
  serveApi({
    'GET /api/conversations': { body: [THREAD] },
    [`GET /api/conversations/${THREAD.conversation_id}`]: { body: { ...THREAD, turns: [turn] } },
  })
  render(
    <MemoryRouter initialEntries={[`/ask?c=${THREAD.conversation_id}`]}>
      <Ask />
    </MemoryRouter>,
  )
  return (await screen.findByText(`${TEXT.askQuestionLabel}:`)).closest('article')
}

/** Expands the citation numbered `position` in `turn`, and returns its button and the panel it opened. */
function expandCitation(turn, position) {
  const marker = within(turn).getByRole('button', { name: TEXT.citationToggleLabel(position) })
  expect(marker.getAttribute('aria-expanded')).toBe('false')
  fireEvent.click(marker)
  return { marker, panel: document.getElementById(marker.getAttribute('aria-controls')) }
}

/* ---- Tests --------------------------------------------------------------- */

describe('D-78: a reopened turn renders as a live one', () => {
  it("expands a reopened turn's citation to its passage and links to its document or meeting", async () => {
    const turn = await reopen(answeredTurn())

    const cited = [
      { position: 1, passage: LEAVE_POLICY.passages[0].text, link: TEXT.viewDocument, to: '/documents/doc-leave' },
      { position: 2, passage: PLANNING_MEETING.passages[0].text, link: TEXT.viewMeeting, to: '/meetings/meeting-plan' },
    ]
    for (const { position, passage, link, to } of cited) {
      const { marker, panel } = expandCitation(turn, position)
      expect(marker.getAttribute('aria-expanded')).toBe('true')
      expect(panel.hidden).toBe(false)
      // The passage in its labelled, scrollable region, word for word, and nothing else.
      expect(within(panel).getByRole('region', { name: TEXT.citationPassageHeading }).textContent).toBe(passage)
      expect(within(panel).getByRole('link', { name: link }).getAttribute('href')).toBe(to)
    }
  })

  it('shows a reopened turn its Sources panel, listing a consulted item no statement cited', async () => {
    const turn = await reopen(answeredTurn())

    const panel = within(turn).getByRole('region', { name: TEXT.sourcesHeading })
    const items = within(panel).getAllByRole('listitem')
    // Every item consulted, in the rank order the read sent.
    expect(items).toHaveLength(3)
    expect(within(items[0]).getByText(LEAVE_POLICY.title)).toBeTruthy()
    expect(within(items[1]).getByText(PLANNING_MEETING.title)).toBeTruthy()

    // The third was consulted and cited by nothing, and is listed with its date and link.
    const uncited = items[2]
    expect(STATEMENTS.some((statement) => statement.chunk_id === CARRY_OVER.passages[0].chunk_id)).toBe(false)
    expect(within(uncited).getByText(CARRY_OVER.title)).toBeTruthy()
    expect(uncited.querySelector('time').getAttribute('datetime')).toBe(CARRY_OVER.date)
    expect(within(uncited).getByRole('link', { name: TEXT.viewDocument }).getAttribute('href')).toBe('/documents/doc-carry')
  })

  it('shows no note setting a reopened thread apart from a live one', async () => {
    const turn = await reopen(answeredTurn())

    // The thread's section holds its heading and its turns. The note that used to
    // sit between them said a reopened turn's passages are not shown, and nothing
    // is left on screen for it to be true of.
    const thread = turn.parentElement
    expect([...thread.children].map((child) => child.tagName)).toEqual(['H2', 'ARTICLE'])
  })

  it("keeps a citation's number as plain text where its passage did not arrive", async () => {
    // D-53's fail-closed read can drop the source a cited passage belongs to, on a
    // reopened turn as on a live reply. Here statement 2's meeting was dropped.
    const turn = await reopen(
      storedAnsweredTurn({ question: QUESTION, statements: STATEMENTS, sources: [LEAVE_POLICY, CARRY_OVER] }),
    )

    expect(within(turn).getByRole('button', { name: TEXT.citationToggleLabel(1) })).toBeTruthy()
    // The statement is still shown with its number and that number's text
    // equivalent, as text rather than a control that expands nothing.
    expect(within(turn).getByText(STATEMENTS[1].text)).toBeTruthy()
    expect(within(turn).queryByRole('button', { name: TEXT.citationToggleLabel(2) })).toBeNull()
    expect(within(turn).getByText('[2]')).toBeTruthy()
    expect(within(turn).getByText(TEXT.citationToggleLabel(2))).toBeTruthy()
  })
})

describe('Stage 4 item 1c: the provenance-removed state', () => {
  it('shows its own title and message, no statement, no Sources panel and not the no-answer copy', async () => {
    // The contract's shape, plus a statement and a source the state never carries,
    // as if a regression had sent them, so that "none shown" is the screen's
    // property and not only the fixture's.
    const leaked = 'Staff may carry over unlimited leave indefinitely.'
    const turn = await reopen({
      ...storedProvenanceRemovedTurn({ question: QUESTION }),
      statements: [{ position: 1, text: leaked, chunk_id: 'chunk-leave-1' }],
      sources: [LEAVE_POLICY],
    })

    expect(within(turn).getByText(TEXT.provenanceRemovedTitle)).toBeTruthy()
    expect(within(turn).getByText(PROVENANCE_REMOVED_MESSAGE)).toBeTruthy()

    expect(turn.textContent).not.toContain(leaked)
    expect(within(turn).queryByRole('region', { name: TEXT.answerHeading })).toBeNull()
    expect(within(turn).queryByRole('region', { name: TEXT.sourcesHeading })).toBeNull()
    expect(turn.textContent).not.toContain(LEAVE_POLICY.title)

    // Not "this cannot be answered from the knowledge base", which is a claim about
    // the corpus this state does not make.
    expect(turn.textContent).not.toContain(TEXT.noAnswerTitle)
    expect(turn.textContent).not.toContain(NO_ANSWER_MESSAGE)

    // The copy used when a turn somehow carries no message is the server's own, so
    // the state has one wording whichever way it is reached.
    expect(TEXT.provenanceRemovedFallback).toBe(PROVENANCE_REMOVED_MESSAGE)
  })
})
