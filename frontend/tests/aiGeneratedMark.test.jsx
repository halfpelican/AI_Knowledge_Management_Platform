/**
 * NFR-15, at the interface: "All AI-generated content (summaries, action items,
 * extracted knowledge) must be visually distinguished from human-authored content
 * using one consistent convention, such as an AI-generated badge, applied
 * system-wide."
 *
 * The convention is FR-10's: the words "Suggested by AI" beside the content, and a
 * dashed boundary as a second cue (src/components/AiMark.jsx). FR-10's own
 * surfaces are tests/documentClassification.test.jsx's. This file holds the
 * surfaces FR-16 added (D-125): the Summary panel, each action item, and a
 * passage of a meeting's summary where FR-12 shows a source passage or a search
 * snippet. And it holds the convention to being one: the same words from one
 * constant, and the same boundary from one token.
 *
 * The mark is asserted by its words, as FR-10's tests assert theirs, because a
 * mark a screen reader cannot read is not a mark. The boundary is asserted from
 * the stylesheets on disk, since jsdom applies none (tests/stylesheets.js).
 *
 * Which content is AI content is the server's to say, in a field of the reply.
 * Each test here that shows a mark also shows that the field alone decides it.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AnswerBody } from '../src/components/Answer.jsx'
import { SearchResultGroup } from '../src/components/SearchResults.jsx'
import { ROLES, TEXT } from '../src/constants.js'
import Ask from '../src/pages/Ask.jsx'
import MeetingDetail from '../src/pages/MeetingDetail.jsx'
import Search from '../src/pages/Search.jsx'
import {
  CONVERSATION,
  actionItem,
  answeredReply,
  readySummary,
  serveApi,
  storedAnsweredTurn,
  summaryRoute,
  summaryState,
} from './fakeApi.js'
import { resolve, styleRules, tokens } from './stylesheets.js'

/** The mark, written out, so a change to its words fails here. */
const SUGGESTED_BY_AI = 'Suggested by AI'

/* ---- One convention ------------------------------------------------------- */

/** The one rule with exactly this selector, as property → value. */
function declarationsOf(selector) {
  const rules = styleRules().filter((rule) => rule.selectors.includes(selector))
  expect(rules, `one rule for ${selector}`).toHaveLength(1)
  return Object.fromEntries(rules[0].declarations.map((declaration) => [declaration.property, declaration.value]))
}

describe('NFR-15: one consistent convention, not one per screen', () => {
  it('says it in the same words on every surface, from one constant', () => {
    expect(TEXT.aiSuggested).toBe(SUGGESTED_BY_AI)
    // FR-10's type and department, and FR-10's tags.
    expect(TEXT.classificationSuggestedByAI).toBe(TEXT.aiSuggested)
    expect(TEXT.tagSuggestedByAI).toBe(TEXT.aiSuggested)
    // A person's later hand in it is said after the same words, on both.
    expect(TEXT.tagConfirmedAI).toBe(`${SUGGESTED_BY_AI}, confirmed by a person`)
    expect(TEXT.aiSuggestedEdited).toBe(`${SUGGESTED_BY_AI}, edited by a person`)
    // And what a person wrote reads the same on a tag and on an action item.
    expect(TEXT.addedByPerson).toBe(TEXT.tagAddedByPerson)
    expect(TEXT.addedByPerson).not.toContain('AI')
  })

  it('bounds AI content the same way on every surface, from one token', () => {
    expect(tokens()['--border-style-ai']).toBe('dashed')

    // FR-10's tag, FR-16's summary and action items, and a summary passage in an
    // answer: each takes its style from the token, and none writes its own.
    const fromToken = [
      ['.tag--ai', 'border-style'],
      ['.citation-panel__passage--ai', 'border-style'],
      ['.ai-content', 'border'],
    ]
    for (const [selector, property] of fromToken) {
      const value = declarationsOf(selector)[property]
      expect(value, `${selector} { ${property} }`).toContain('var(--border-style-ai)')
      expect(resolve(value)).toContain('dashed')
    }
    // The same line FR-10's tags are drawn with, in width and colour.
    const tag = declarationsOf('.tag').border
    expect(resolve(declarationsOf('.ai-content').border)).toBe(resolve(tag).replace('solid', 'dashed'))
    // A person's content is bounded by that line too, solid.
    expect(resolve(declarationsOf('.person-content').border)).toBe(resolve(tag))
    expect(resolve(declarationsOf('.tag--user')['border-style'])).toBe('solid')
  })

  it('draws the words as FR-10 draws its tags’ provenance', () => {
    const mark = styleRules().find((rule) => rule.selectors.includes('.ai-mark'))
    expect(mark.selectors).toContain('.person-mark')
    const declared = Object.fromEntries(mark.declarations.map((declaration) => [declaration.property, declaration.value]))
    expect(declared).toEqual(declarationsOf('.tag__provenance'))
  })
})

/* ---- FR-16's own surfaces ------------------------------------------------- */

const MEETING = {
  meeting_id: 'meeting-1',
  title: 'First-quarter review',
  meeting_date: '2026-11-03',
  status: 'Indexed',
  created_at: '2026-11-03T16:00:00+11:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: [],
  transcript_text: 'Ravi: Thanks, everyone. This is the first-quarter review.',
  can_delete: false,
}

const DETAIL = `/api/meetings/${MEETING.meeting_id}`
const SUMMARY = `${DETAIL}/summary`
const ITEMS = `${DETAIL}/action-items`

const EXTRACTED = actionItem()
const EDITED = actionItem({
  action_item_id: 'item-2',
  description: 'Send the revised travel policy to all staff',
  edited: true,
})
const BY_HAND = actionItem({
  action_item_id: 'item-3',
  description: 'Circulate the minutes',
  owner: null,
  owner_name: '',
  due_date: null,
  due_text: '',
  passages: [],
  origin: 'user',
})

/** The meeting page against `state`, once both panels have it. */
async function meetingPage(state, extraRoutes = {}) {
  const answered = serveApi({
    [`GET ${DETAIL}`]: { body: MEETING },
    [`GET ${SUMMARY}`]: summaryRoute(state),
    'GET /api/users/directory': { body: [] },
    ...extraRoutes,
  })
  render(
    <MemoryRouter initialEntries={[`/meetings/${MEETING.meeting_id}`]}>
      <Routes>
        <Route path="/meetings/:meetingId" element={<MeetingDetail />} />
      </Routes>
    </MemoryRouter>,
  )
  const summary = await screen.findByRole('region', { name: TEXT.summaryHeading })
  await waitFor(() => expect(within(summary).queryByText(TEXT.loadingSummary)).toBeNull())
  return { answered, summary, items: screen.getByRole('region', { name: TEXT.actionItemsHeading }) }
}

function rowOf(panel, item) {
  return within(panel).getByText(item.description).closest('li')
}

describe('NFR-15: the summary is marked as AI content', () => {
  it('carries the mark inside the summary’s own boundary, before the text it marks', async () => {
    const { summary } = await meetingPage(summaryState({ status: 'Ready', summary: readySummary() }))

    const mark = within(summary).getByText(SUGGESTED_BY_AI)
    const content = mark.closest('.meeting-summary__content')
    expect(content, 'the mark is on the summary itself').toBeTruthy()
    expect(content.classList.contains('ai-content')).toBe(true)
    // Every word of the summary is inside the block the mark and the boundary are on.
    for (const element of [...readySummary().narrative, ...readySummary().decisions, ...readySummary().highlights]) {
      expect(content.textContent).toContain(element.text)
    }
    const narrative = content.querySelector('.meeting-summary__narrative')
    expect(mark.compareDocumentPosition(narrative) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // Once, on the summary: its sentences are not each marked again.
    expect(within(summary).getAllByText(SUGGESTED_BY_AI, { exact: false })).toHaveLength(1)
  })

  it('marks the previous summary still, while a new one is being generated', async () => {
    const { summary } = await meetingPage(summaryState({ status: 'Unavailable', summary: readySummary() }))

    expect(within(summary).getByText(SUGGESTED_BY_AI).closest('.ai-content')).toBeTruthy()
  })

  it.each([
    ['no summary has been generated', summaryState()],
    ['the run failed', summaryState({ status: 'Unavailable', queued_for_retry: true })],
  ])('shows no mark where there is no AI content to mark: %s', async (_case, state) => {
    const { summary, items } = await meetingPage(state)

    expect(within(summary).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
    expect(summary.querySelector('.ai-content')).toBeNull()
    expect(within(items).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
  })

  it('does not mark the transcript passage a reference opens: those are the meeting’s own words', async () => {
    const { summary } = await meetingPage(summaryState({ status: 'Ready', summary: readySummary() }))
    const narrative = summary.querySelector('.meeting-summary__narrative')

    fireEvent.click(within(narrative).getAllByRole('button', { name: TEXT.transcriptPassage(1) })[0])

    const passage = within(summary).getByRole('region', { name: TEXT.transcriptPassage(1) })
    expect(passage.classList.contains('citation-panel__passage--ai')).toBe(false)
    expect(passage.getAttribute('aria-describedby')).toBeNull()
    expect(within(passage.parentElement).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
  })
})

describe('NFR-15: each action item says whose it is', () => {
  it('marks an extracted item, marks an edited one as edited by a person, and gives a person’s item no AI mark', async () => {
    const { items } = await meetingPage(
      summaryState({ status: 'Ready', summary: readySummary(), action_items: [EXTRACTED, EDITED, BY_HAND] }),
    )

    // `origin` "ai": the mark, and the boundary AI content has.
    const extracted = rowOf(items, EXTRACTED)
    expect(within(extracted).getByText(SUGGESTED_BY_AI)).toBeTruthy()
    expect(extracted.classList.contains('ai-content')).toBe(true)
    expect(extracted.classList.contains('person-content')).toBe(false)

    // `edited`: still the AI's, and a person's hand in it is said.
    const edited = rowOf(items, EDITED)
    expect(within(edited).getByText('Suggested by AI, edited by a person')).toBeTruthy()
    expect(within(edited).queryByText(SUGGESTED_BY_AI)).toBeNull()
    expect(edited.classList.contains('ai-content')).toBe(true)

    // `origin` "user": no AI mark, and what FR-10 says of a tag a person applied.
    const byHand = rowOf(items, BY_HAND)
    expect(within(byHand).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
    expect(within(byHand).getByText('Added by a person')).toBeTruthy()
    expect(byHand.classList.contains('person-content')).toBe(true)
    expect(byHand.classList.contains('ai-content')).toBe(false)

    // One mark per item, and none on the panel as a whole.
    expect(within(items).getAllByText(SUGGESTED_BY_AI, { exact: false })).toHaveLength(2)
  })

  it('reads the mark from origin and edited, not from what the item says', async () => {
    // A person's item that talks about AI, and an extracted one that does not.
    const aboutAi = { ...BY_HAND, description: 'Suggested by AI: review the summary tool' }
    const { items } = await meetingPage(
      summaryState({ status: 'Ready', summary: readySummary(), action_items: [EXTRACTED, aboutAi] }),
    )

    const byHand = rowOf(items, aboutAi)
    expect(byHand.querySelector('.ai-mark')).toBeNull()
    expect(within(byHand).getByText(TEXT.addedByPerson)).toBeTruthy()
    expect(byHand.classList.contains('person-content')).toBe(true)
    expect(rowOf(items, EXTRACTED).querySelector('.ai-mark').textContent).toBe(SUGGESTED_BY_AI)
  })

  it('changes an extracted item’s mark to the edited form once an edit has been saved', async () => {
    const saved = { ...EXTRACTED, description: 'Reconcile the October card statements', edited: true }
    const { items } = await meetingPage(
      summaryState({ status: 'Ready', summary: readySummary(), action_items: [EXTRACTED], can_edit: true }),
      { [`PATCH ${ITEMS}/${EXTRACTED.action_item_id}`]: { body: saved } },
    )
    const row = rowOf(items, EXTRACTED)
    expect(within(row).getByText(SUGGESTED_BY_AI)).toBeTruthy()

    fireEvent.click(within(row).getByRole('button', { name: TEXT.actionItemEditLabel(EXTRACTED.description) }))
    fireEvent.change(within(row).getByLabelText(TEXT.actionItemDescription), { target: { value: saved.description } })
    fireEvent.click(within(row).getByRole('button', { name: TEXT.actionItemSave }))

    expect(await within(row).findByText(TEXT.aiSuggestedEdited)).toBeTruthy()
    expect(within(row).queryByText(SUGGESTED_BY_AI)).toBeNull()
  })

  it('marks an item added by hand as a person’s, from the reply that created it', async () => {
    const { items } = await meetingPage(
      summaryState({ status: 'Ready', summary: readySummary(), action_items: [EXTRACTED], can_edit: true }),
      { [`POST ${ITEMS}`]: { status: 201, body: BY_HAND } },
    )

    fireEvent.click(within(items).getByRole('button', { name: TEXT.actionItemAdd }))
    const form = within(items).getByRole('form', { name: TEXT.actionItemAddLegend })
    fireEvent.change(within(form).getByLabelText(TEXT.actionItemDescription), { target: { value: BY_HAND.description } })
    fireEvent.click(within(form).getByRole('button', { name: TEXT.actionItemAdd }))

    // The row, not the form's own field, which holds the same words until it closes.
    const added = (
      await within(items).findByText(BY_HAND.description, { selector: '.action-item__description' })
    ).closest('li')
    expect(within(added).getByText(TEXT.addedByPerson)).toBeTruthy()
    expect(within(added).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
    expect(added.classList.contains('person-content')).toBe(true)
  })

  it('marks the record that a meeting raised no action items, which is the summary’s finding', async () => {
    const { items } = await meetingPage(
      summaryState({ status: 'Ready', summary: readySummary({ action_items_extracted: 0 }), action_items: [] }),
    )

    const sentence = within(items).getByText(TEXT.actionItemsNoneRaised, { exact: false })
    expect(sentence.textContent).toBe(`${SUGGESTED_BY_AI} ${TEXT.actionItemsNoneRaised}`)
    expect(sentence.classList.contains('ai-content')).toBe(true)
  })

  it('does not mark the empty list of a meeting with no summary: nothing there is the AI’s', async () => {
    const { items } = await meetingPage(summaryState())

    const sentence = within(items).getByText(TEXT.actionItemsNone)
    expect(sentence.textContent).toBe(TEXT.actionItemsNone)
    expect(within(items).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
    expect(sentence.classList.contains('ai-content')).toBe(false)
  })
})

/* ---- FR-12's answer -------------------------------------------------------- */

describe('NFR-15: an answer is marked as AI content', () => {
  it('carries the mark under its heading, inside the dashed boundary, and is described by it', () => {
    render(
      <MemoryRouter>
        <AnswerBody idPrefix="turn" statements={[STATEMENT]} sources={[]} />
      </MemoryRouter>,
    )

    const answer = screen.getByRole('region', { name: TEXT.answerHeading })
    const mark = within(answer).getByText(SUGGESTED_BY_AI)
    expect(answer.classList.contains('ai-content')).toBe(true)
    expect(answer.getAttribute('aria-describedby')).toBe(mark.id)
    // The mark comes before the statements it is about.
    const statement = within(answer).getByText(STATEMENT.text)
    expect(mark.compareDocumentPosition(statement) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('takes its boundary from the one token every AI surface reads', () => {
    expect(declarationsOf('.ai-content').border).toContain('var(--border-style-ai)')
  })
})

/* ---- A summary passage in an answer ---------------------------------------- */

const STATEMENT = { position: 1, text: 'Discretionary travel is frozen until 31 January.', chunk_id: 'chunk-summary' }

/** A meeting source with the one passage the statement cites, as the ask reply sends it. */
function meetingSource(passage) {
  return {
    source_type: 'meeting',
    source_id: MEETING.meeting_id,
    title: MEETING.title,
    date: MEETING.meeting_date,
    passages: [{ chunk_id: STATEMENT.chunk_id, ...passage }],
  }
}

/** A summary passage's text: the summary's own sentences, one to a line, and nothing added. */
const SUMMARY_PASSAGE_TEXT =
  'The team reviewed the first quarter. It froze discretionary travel until January.\nDiscretionary travel is frozen until 31 January.'

/** The answer for `passage`, with its one citation opened. */
function openedCitation(passage) {
  render(
    <MemoryRouter>
      <AnswerBody idPrefix="turn" statements={[STATEMENT]} sources={[meetingSource(passage)]} />
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole('button', { name: TEXT.citationToggleLabel(1) }))
  return screen.getByRole('region', { name: TEXT.citationPassageHeading })
}

describe('NFR-15: a passage of a meeting’s AI-generated summary is marked where an answer shows it', () => {
  it('marks a passage whose ai_generated is true, in words that say it is from the summary and not the transcript', () => {
    const passage = openedCitation({ text: SUMMARY_PASSAGE_TEXT, ai_generated: true })
    const panel = passage.closest('.citation-panel')

    expect(within(panel).getByText(SUGGESTED_BY_AI)).toBeTruthy()
    expect(panel.textContent).toContain(TEXT.aiSummaryPassage)
    expect(TEXT.aiSummaryPassage).toMatch(/AI-generated summary/)
    expect(TEXT.aiSummaryPassage).toMatch(/not from its transcript/)
    // The boundary AI content has, and the passage is still the passage.
    expect(passage.classList.contains('citation-panel__passage--ai')).toBe(true)
    expect(passage.textContent).toBe(SUMMARY_PASSAGE_TEXT)
    // A screen reader that lands on the passage is told before it reads it.
    const described = document.getElementById(passage.getAttribute('aria-describedby'))
    expect(described.textContent).toBe(`${SUGGESTED_BY_AI} ${TEXT.aiSummaryPassage}`)
    // And the mark is ahead of the text for everyone else.
    expect(described.compareDocumentPosition(passage) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it.each([
    ['false', { ai_generated: false }],
    // A reply from before the field carries none, which is false.
    ['absent', {}],
    ['not a boolean', { ai_generated: 'true' }],
  ])('shows no mark on a passage whose ai_generated is %s', (_case, flag) => {
    const passage = openedCitation({ text: 'Ravi: so the decision is that discretionary travel is frozen.', ...flag })
    const panel = passage.closest('.citation-panel')

    expect(within(panel).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
    expect(panel.textContent).not.toContain(TEXT.aiSummaryPassage)
    expect(passage.classList.contains('citation-panel__passage--ai')).toBe(false)
    expect(passage.getAttribute('aria-describedby')).toBeNull()
  })

  it('goes by the flag alone, never by words in the passage', () => {
    // A transcript in which someone says the words is not AI content...
    const spoken = 'AI-generated summary of the meeting "First-quarter review": Suggested by AI, said Sam, laughing.'
    const transcript = openedCitation({ text: spoken, ai_generated: false })
    expect(within(transcript.closest('.citation-panel')).queryByText(SUGGESTED_BY_AI)).toBeNull()
    expect(transcript.classList.contains('citation-panel__passage--ai')).toBe(false)
    expect(transcript.textContent).toBe(spoken)
  })

  it('marks a flagged passage whose text says nothing of being a summary', () => {
    // ...and a summary passage is its own sentences with nothing added, so the
    // flag is the only thing that says what it is (docs/api-contract.md).
    const plain = 'Travel was twice its budget.'
    const passage = openedCitation({ text: plain, ai_generated: true })

    expect(plain).not.toMatch(/AI|summary/i)
    expect(within(passage.closest('.citation-panel')).getByText(SUGGESTED_BY_AI)).toBeTruthy()
    expect(passage.classList.contains('citation-panel__passage--ai')).toBe(true)
  })

  it('carries the flag from a live reply to the screen', async () => {
    const reply = {
      ...answeredReply(),
      statements: [STATEMENT],
      sources: [meetingSource({ text: SUMMARY_PASSAGE_TEXT, ai_generated: true })],
    }
    serveApi({
      'GET /api/conversations': { body: [] },
      'POST /api/conversations': { status: 201, body: CONVERSATION },
      'POST /api/ask': { body: reply },
    })
    render(
      <MemoryRouter initialEntries={['/ask']}>
        <Ask />
      </MemoryRouter>,
    )
    await screen.findByText(TEXT.noConversations)
    fireEvent.change(screen.getByLabelText(TEXT.askFieldLabel), { target: { value: 'What was decided about travel?' } })
    fireEvent.click(screen.getByRole('button', { name: TEXT.askSubmit }))

    fireEvent.click(await screen.findByRole('button', { name: TEXT.citationToggleLabel(1) }))

    const passage = screen.getByRole('region', { name: TEXT.citationPassageHeading })
    expect(within(passage.closest('.citation-panel')).getByText(SUGGESTED_BY_AI)).toBeTruthy()
    expect(passage.closest('.citation-panel').textContent).toContain(TEXT.aiSummaryPassage)
  })

  it('carries the flag from a reopened conversation to the screen', async () => {
    const question = 'What was decided about travel?'
    const thread = {
      ...CONVERSATION,
      title: question,
      turns: [
        storedAnsweredTurn({
          question,
          statements: [STATEMENT],
          sources: [meetingSource({ text: SUMMARY_PASSAGE_TEXT, ai_generated: true })],
        }),
      ],
    }
    serveApi({
      'GET /api/conversations': { body: [{ ...CONVERSATION, title: question }] },
      [`GET /api/conversations/${CONVERSATION.conversation_id}`]: { body: thread },
    })
    render(
      <MemoryRouter initialEntries={['/ask']}>
        <Ask />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: TEXT.conversationOpen(question) }))

    fireEvent.click(await screen.findByRole('button', { name: TEXT.citationToggleLabel(1) }))

    const passage = screen.getByRole('region', { name: TEXT.citationPassageHeading })
    expect(within(passage.closest('.citation-panel')).getByText(SUGGESTED_BY_AI)).toBeTruthy()
  })
})

/* ---- A summary snippet in a search result ---------------------------------- */

/** A meeting result as `GET /api/search` sends it. */
function meetingResult(overrides = {}) {
  return {
    source_type: 'meeting',
    source_id: MEETING.meeting_id,
    title: MEETING.title,
    snippet: 'It froze discretionary travel until January.',
    snippet_ai_generated: false,
    department: '',
    date: MEETING.meeting_date,
    ...overrides,
  }
}

/** The one result, rendered in its group. */
function shownResult(result) {
  render(
    <MemoryRouter>
      <SearchResultGroup
        heading={TEXT.searchMeetingsHeading}
        headingId="group-meetings"
        group={{ count: 1, results: [result] }}
        emptyMessage={TEXT.searchGroupEmptyMeetings}
      />
    </MemoryRouter>,
  )
  return screen.getByRole('article')
}

describe('NFR-15: a snippet from a meeting’s AI-generated summary is marked in the search results', () => {
  it('marks a result whose snippet_ai_generated is true, with the snippet inside the boundary and the mark ahead of it', () => {
    const result = meetingResult({ snippet_ai_generated: true })
    const item = shownResult(result)

    const mark = within(item).getByText(SUGGESTED_BY_AI)
    expect(item.textContent).toContain(TEXT.aiSummarySnippet)
    expect(TEXT.aiSummarySnippet).toMatch(/AI-generated summary/)
    expect(TEXT.aiSummarySnippet).toMatch(/not from its transcript/)
    const snippet = within(item).getByText(result.snippet)
    const block = snippet.closest('.ai-content')
    expect(block, 'the snippet is inside the AI boundary').toBeTruthy()
    expect(block.contains(mark)).toBe(true)
    expect(mark.compareDocumentPosition(snippet) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // The result is otherwise the result it always was: one link to the meeting, its type and date.
    expect(within(item).getByRole('link', { name: result.title }).getAttribute('href')).toBe('/meetings/meeting-1')
    expect(item.querySelector('time').getAttribute('dateTime')).toBe(result.date)
  })

  it.each([
    ['false', { snippet_ai_generated: false }],
    // A reply from before the field carries none, which is false.
    ['absent', { snippet_ai_generated: undefined }],
    ['not a boolean', { snippet_ai_generated: 1 }],
  ])('shows no mark on a result whose snippet_ai_generated is %s, and renders it as it always has', (_case, flag) => {
    const result = meetingResult(flag)
    const item = shownResult(result)

    expect(within(item).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
    expect(item.textContent).not.toContain(TEXT.aiSummarySnippet)
    expect(item.querySelector('.ai-content')).toBeNull()
    // The snippet is the article's own paragraph, as before FR-16.
    const snippet = within(item).getByText(result.snippet)
    expect(snippet.className).toBe('search-result__snippet')
    expect(snippet.parentElement).toBe(item)
  })

  it('goes by the flag alone, never by words in the snippet', () => {
    // The transcript's own words, which happen to mention an AI summary.
    const spoken = meetingResult({ snippet: 'Sam: the AI-generated summary of the meeting was suggested by AI.' })
    const item = shownResult(spoken)

    expect(within(item).queryByText(SUGGESTED_BY_AI)).toBeNull()
    expect(item.querySelector('.ai-content')).toBeNull()
    expect(item.textContent).toContain(spoken.snippet)
  })

  it('marks nothing where a result has no snippet to mark', () => {
    // Matched on its title alone: the note in the snippet's place is the page's own.
    const item = shownResult(meetingResult({ snippet: '', snippet_ai_generated: true }))

    expect(within(item).getByText(TEXT.searchSnippetUnavailable)).toBeTruthy()
    expect(within(item).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
    expect(item.querySelector('.ai-content')).toBeNull()
  })

  it('carries the flag from the search reply to the screen, on the result it belongs to and no other', async () => {
    const fromSummary = meetingResult({ snippet_ai_generated: true })
    const fromTranscript = meetingResult({
      source_id: 'meeting-2',
      title: 'Travel policy working group',
      snippet: 'Sam: travel is the line that worries me.',
    })
    serveApi({
      'GET /api/search': {
        body: {
          query: 'travel',
          documents: { count: 0, results: [] },
          meetings: { count: 2, results: [fromSummary, fromTranscript] },
          total_count: 2,
        },
      },
    })
    render(
      <MemoryRouter initialEntries={['/search?q=travel']}>
        <Search />
      </MemoryRouter>,
    )

    const marked = (await screen.findByRole('link', { name: fromSummary.title })).closest('article')
    const unmarked = screen.getByRole('link', { name: fromTranscript.title }).closest('article')
    expect(within(marked).getByText(SUGGESTED_BY_AI)).toBeTruthy()
    expect(marked.textContent).toContain(TEXT.aiSummarySnippet)
    expect(within(unmarked).queryByText(SUGGESTED_BY_AI, { exact: false })).toBeNull()
    expect(screen.getAllByText(SUGGESTED_BY_AI)).toHaveLength(1)
  })
})
