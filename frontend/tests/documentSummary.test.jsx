/**
 * FR-10's document summary and key points on the document page (D-139), rendered
 * against a faked `GET /api/documents/{id}` whose `classification` object carries
 * `summary`, `key_points` and `summary_truncated`.
 *
 * - FR-10 Front-End: "Each document displays a short summary and a list of key
 *   points". On this page they sit beneath the title and above the text.
 * - FR-10 Validation: a long document is never "summarised from a fragment without
 *   the user being told".
 * - NFR-15: the summary is AI content and is marked as it.
 *
 * Each test defends a clause only the screen can satisfy: where the summary sits,
 * that it is marked, what is said when there is none, that a run from the page
 * replaces it, and that the user is told when it covers part of a document. What a
 * summary says and when one is written are the server's, and pytest's. The same
 * block in a search result is tests/search.test.jsx's.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import DocumentDetail from '../src/pages/DocumentDetail.jsx'
import { serveApi } from './fakeApi.js'
import { hidingCauses, rulesMatching } from './stylesheets.js'

/* ---- The words, written out, so a change to any of them fails here -------- */

/** NFR-15's mark. */
const SUGGESTED_BY_AI = 'Suggested by AI'

/** The sentence beside the mark: what the block is, and that it is not the document's own text. */
const SUMMARY_PROVENANCE = 'This is a summary of the document, not its own text.'

/** The one line a document with no summary shows. */
const NO_SUMMARY = 'No summary has been generated for this document.'

/** FR-10's sentence for a summary that covers only part of a long document. */
const SUMMARY_TRUNCATED = 'This summary covers only the first part of the document.'

/** The key points' visible name, which is also the list's accessible name. */
const KEY_POINTS_NAME = 'Key points'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

const LEAVE = {
  doc_id: 'doc-1',
  title: 'Leave policy 2026',
  file_type: 'pdf',
  status: 'Indexed',
  uploaded_at: '2026-09-21T10:00:00+10:00',
  department: 'Human Resources',
  visible_to_roles: ['Employee', 'Administrator'],
  file_size_bytes: 14203,
  uploaded_by: 'erin@example.com',
}

const EXTRACTED_TEXT = 'Employees may request annual leave through their manager.'

const SUMMARY = 'Sets out how staff accrue annual leave and how a request for it is approved.'

const KEY_POINTS = ['Four weeks of annual leave a year for full-time staff.', 'A manager approves each request.']

/**
 * A classification as it was before D-139: the type and department applied, and no
 * `summary`, `key_points` or `summary_truncated` key at all.
 */
function classificationBefore(overrides = {}) {
  return {
    doc_type: 'Policy',
    doc_type_outcome: 'applied',
    department_outcome: 'applied',
    department_applied_by: 'ai',
    machine_doc_type: 'Policy',
    machine_doc_type_confidence: 0.92,
    machine_department: 'Human Resources',
    machine_department_confidence: 0.81,
    user_edited: false,
    proposed_tags: [],
    classified_at: '2026-11-21T10:00:00+11:00',
    model: 'claude-haiku-5-5',
    input_truncated: false,
    ...overrides,
  }
}

/** The classification object as the contract sends it since D-139, with a summary. */
function summarised(overrides = {}) {
  return classificationBefore({ summary: SUMMARY, key_points: KEY_POINTS, summary_truncated: false, ...overrides })
}

/** The detail object: the document, FR-15's fields and FR-10's. */
function detailOf(overrides = {}) {
  return {
    ...LEAVE,
    extracted_text: EXTRACTED_TEXT,
    tags: { project: [], process: [], topic: [] },
    can_delete: false,
    classification: null,
    tag_details: [],
    tag_options: { Project: [], Process: [], Topic: [] },
    ...overrides,
  }
}

const DOC = `/api/documents/${LEAVE.doc_id}`

/* ---- Rendering ----------------------------------------------------------- */

/** The detail view at its path, for a document the fake API describes. */
async function renderDetail(detail, extraRoutes = {}) {
  const answered = serveApi({ [`GET ${DOC}`]: { body: detail }, ...extraRoutes })
  render(
    <MemoryRouter initialEntries={[`/documents/${detail.doc_id}`]}>
      <Routes>
        <Route path="/documents/:docId" element={<DocumentDetail />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByRole('heading', { level: 1, name: detail.title })
  return answered
}

/** Whether `later` comes after `earlier` in the document, and is not inside it. */
function comesAfter(earlier, later) {
  return earlier.compareDocumentPosition(later) === Node.DOCUMENT_POSITION_FOLLOWING
}

/** The page's title, and the three things the summary sits above. */
function landmarks() {
  return {
    title: screen.getByRole('heading', { level: 1, name: LEAVE.title }),
    classification: screen.getByRole('region', { name: TEXT.classificationHeading }),
    extractedHeading: screen.getByRole('heading', { level: 2, name: TEXT.documentExtractedHeading }),
    extractedText: screen.getByRole('region', { name: TEXT.documentExtractedHeading }),
  }
}

/** The summary's block, or null when the page shows none. */
function summaryBlock() {
  return document.querySelector('.document-summary')
}

/** Every element of `block`, itself included, that the keyboard could stop on. */
function tabStopsIn(block) {
  return [block, ...block.querySelectorAll('*')].filter((element) =>
    element.matches('a[href], button, input, select, textarea, summary, [tabindex], [contenteditable]'),
  )
}

/** The selectors of the rules that match `element` and declare a border of any kind but its radius. */
function borderRulesOn(element) {
  return rulesMatching(element)
    .filter((rule) => rule.declarations.some((declaration) => /^border(?!-radius)/.test(declaration.property)))
    .map((rule) => rule.selector)
}

/* ---- Where it sits, and its mark ----------------------------------------- */

describe('FR-10: the document page shows the summary and key points beneath the title and above the text (D-139)', () => {
  it('puts the summary, then its key points, after the title and before the classification and the extracted-text heading', async () => {
    await renderDetail(detailOf({ classification: summarised() }))
    const { title, classification, extractedHeading, extractedText } = landmarks()

    const summary = screen.getByText(SUMMARY)
    const points = screen.getByRole('list', { name: KEY_POINTS_NAME })
    expect(points.tagName).toBe('UL')
    expect(within(points).getAllByRole('listitem').map((point) => point.textContent)).toEqual(KEY_POINTS)

    expect(comesAfter(title, summary), 'the summary is beneath the title').toBe(true)
    expect(comesAfter(summary, points), 'the key points follow the summary').toBe(true)
    expect(comesAfter(points, classification), 'the classification follows the key points').toBe(true)
    expect(comesAfter(points, extractedHeading), 'the extracted-text heading follows the key points').toBe(true)
    expect(comesAfter(extractedHeading, extractedText)).toBe(true)
    // The line for a document with none is not shown beside a summary.
    expect(screen.queryByText(NO_SUMMARY)).toBeNull()
  })

  it('marks them as AI content: the mark is inside their block and ahead of them, and the document’s own text is outside it', async () => {
    await renderDetail(detailOf({ classification: summarised() }))

    const summary = screen.getByText(SUMMARY)
    const block = summary.closest('.ai-content')
    expect(block, 'the summary is inside the AI boundary').toBeTruthy()
    expect(block).toBe(summaryBlock())
    const mark = within(block).getByText(SUGGESTED_BY_AI)
    expect(comesAfter(mark, summary), 'the mark is read before the summary').toBe(true)
    // Its words written out, as the mark's are, so a sentence emptied or reworded fails here.
    expect(mark.parentElement.textContent).toBe(`${SUGGESTED_BY_AI} ${SUMMARY_PROVENANCE}`)
    expect(block.contains(screen.getByRole('list', { name: KEY_POINTS_NAME }))).toBe(true)
    // The extracted text is the document's, so it is not inside the AI boundary.
    expect(block.contains(landmarks().extractedText)).toBe(false)
    expect(block.textContent).not.toContain(EXTRACTED_TEXT)
    // It holds no control: nothing in it can take focus, so the tab order is as it was.
    expect(tabStopsIn(block)).toEqual([])
  })

  it('draws them where a reader can see them: no stylesheet hides the mark, the summary, the sentence or a key point, and the block’s one border is the AI convention’s', async () => {
    // jsdom applies no stylesheet, so this is held to the CSS on disk (tests/stylesheets.js).
    await renderDetail(detailOf({ classification: summarised({ summary_truncated: true }) }))
    const block = summaryBlock()

    for (const element of [
      within(block).getByText(SUGGESTED_BY_AI),
      within(block).getByText(SUMMARY),
      within(block).getByText(SUMMARY_TRUNCATED),
      within(block).getByText(KEY_POINTS_NAME),
      ...within(block).getAllByRole('listitem'),
    ]) {
      expect(hidingCauses(element)).toEqual([])
    }
    // The dashed boundary is `ai-content`'s (tests/aiGeneratedMark.test.jsx holds it to
    // the one token). No rule of the block's own, or of the page's, draws another over it.
    expect(borderRulesOn(block)).toEqual(['.ai-content'])
  })

  it('lets a long unbroken string in the summary or a key point wrap inside the block, so the page never scrolls sideways (SC 1.4.10)', async () => {
    // The model's words can hold a string with nowhere to break. Measured in headless
    // Edge at 320 CSS px with the built stylesheet on 21 November 2026, around a
    // 135-character one: with these declarations the page is as wide as its viewport,
    // 305 px; without the summary's it is 1102 px wide, and without the key points',
    // 1126 (docs/accessibility.md, section 10). jsdom lays nothing out, so the rules
    // are read from disk and matched against the rendered elements.
    await renderDetail(detailOf({ classification: summarised() }))
    const block = summaryBlock()

    for (const element of [within(block).getByText(SUMMARY), ...within(block).getAllByRole('listitem')]) {
      const declared = Object.fromEntries(
        rulesMatching(element)
          .flatMap((rule) => rule.declarations)
          .map((declaration) => [declaration.property, declaration.value.trim()]),
      )
      expect(declared['word-break'], element.className || element.tagName).toBe('break-word')
    }
  })

  it('renders five key points as five list items, in the order they were sent', async () => {
    const five = ['First point.', 'Second point.', 'Third point.', 'Fourth point.', 'Fifth point.']
    await renderDetail(detailOf({ classification: summarised({ key_points: five }) }))

    const items = within(screen.getByRole('list', { name: KEY_POINTS_NAME })).getAllByRole('listitem')
    expect(items.map((point) => point.textContent)).toEqual(five)
  })
})

/* ---- No summary ----------------------------------------------------------- */

describe('FR-10: a document with no summary says so in one line (D-139)', () => {
  it.each([
    ['the document was never classified', null],
    ['the classification has an empty summary', summarised({ summary: '', key_points: [] })],
    // A detail from a server before D-139: a classification with none of the three keys.
    ['the classification is from before the field', classificationBefore()],
    // Key points and the flag are a summary's: without one, neither is shown.
    ['an empty summary came beside key points', summarised({ summary: '', summary_truncated: true })],
    // White space says nothing, so it is no summary: never a marked block with nothing to read.
    ['the summary is only white space', summarised({ summary: ' \n\t  ', summary_truncated: true })],
  ])('shows the line, and no summary block, mark or list, when %s', async (_case, classification) => {
    await renderDetail(detailOf({ classification }))
    const { title, classification: section, extractedHeading } = landmarks()

    const line = screen.getByText(NO_SUMMARY)
    expect(screen.getAllByText(NO_SUMMARY)).toHaveLength(1)
    // jsdom applies no stylesheet, so the line is held to the CSS on disk (tests/stylesheets.js).
    expect(hidingCauses(line)).toEqual([])
    expect(comesAfter(title, line), 'the line is beneath the title').toBe(true)
    expect(comesAfter(line, section)).toBe(true)
    expect(comesAfter(line, extractedHeading)).toBe(true)

    expect(summaryBlock()).toBeNull()
    expect(screen.queryByRole('list', { name: KEY_POINTS_NAME })).toBeNull()
    expect(screen.queryByText(KEY_POINTS_NAME)).toBeNull()
    expect(screen.queryByText(SUMMARY_TRUNCATED)).toBeNull()
    // The line is the page's own sentence, not AI content: no mark, no boundary.
    expect(line.closest('.ai-content')).toBeNull()
    expect(screen.queryByText(SUGGESTED_BY_AI)).toBeNull()
    expect(TEXT.documentSummaryNone).toBe(NO_SUMMARY)
  })

  it('shows a summary that came with no key points without an empty list', async () => {
    await renderDetail(detailOf({ classification: summarised({ key_points: [] }) }))

    expect(screen.getByText(SUMMARY).closest('.ai-content')).toBeTruthy()
    expect(summaryBlock().querySelector('ul')).toBeNull()
    expect(screen.queryByText(KEY_POINTS_NAME)).toBeNull()
    expect(screen.queryByText(NO_SUMMARY)).toBeNull()
  })
})

/* ---- A run from the page -------------------------------------------------- */

describe('FR-10: the summary shown is the one the latest reply carries (D-139)', () => {
  it('shows the new summary after "Classify now", in place of the line that said there was none', async () => {
    const answered = await renderDetail(detailOf(), {
      [`POST ${DOC}/classify`]: {
        body: { classification: summarised(), tag_details: [], department: LEAVE.department },
      },
    })
    expect(screen.getByText(NO_SUMMARY)).toBeTruthy()
    expect(summaryBlock()).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: TEXT.classifyNow }))

    const summary = await screen.findByText(SUMMARY)
    expect(summary.closest('.ai-content')).toBe(summaryBlock())
    expect(within(summaryBlock()).getByText(SUGGESTED_BY_AI)).toBeTruthy()
    expect(within(screen.getByRole('list', { name: KEY_POINTS_NAME })).getAllByRole('listitem').map((point) => point.textContent)).toEqual(
      KEY_POINTS,
    )
    await waitFor(() => expect(screen.queryByText(NO_SUMMARY)).toBeNull())
    // Still beneath the title and above the classification that the run just filled.
    const { title, classification } = landmarks()
    expect(comesAfter(title, summary)).toBe(true)
    expect(comesAfter(summary, classification)).toBe(true)
    expect(answered.filter((request) => request.method === 'POST')).toHaveLength(1)
  })

  it('replaces the summary on screen when a reply’s classification carries a new one: the new text is shown and the old is gone', async () => {
    // "Classify now" is offered only for a document never classified, so the page's
    // own way to a new classification object over an old one is the confirm route,
    // whose reply carries the object with its summary as every route does.
    const newSummary = 'Replaces the 2025 policy: leave is now requested in the staff portal.'
    const newPoints = ['Requests are made in the staff portal.']
    await renderDetail(detailOf({ classification: summarised() }), {
      [`POST ${DOC}/classification`]: {
        body: {
          classification: summarised({
            doc_type_outcome: 'confirmed',
            department_outcome: 'confirmed',
            user_edited: true,
            summary: newSummary,
            key_points: newPoints,
            summary_truncated: true,
          }),
          department: LEAVE.department,
        },
      },
    })
    expect(screen.getByText(SUMMARY)).toBeTruthy()
    expect(screen.queryByText(SUMMARY_TRUNCATED)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: TEXT.classificationConfirmAll }))

    expect(await screen.findByText(newSummary)).toBeTruthy()
    await waitFor(() => expect(screen.queryByText(SUMMARY)).toBeNull())
    const items = within(screen.getByRole('list', { name: KEY_POINTS_NAME })).getAllByRole('listitem')
    expect(items.map((point) => point.textContent)).toEqual(newPoints)
    for (const old of KEY_POINTS) expect(screen.queryByText(old)).toBeNull()
    // The flag is the new reply's as well.
    expect(within(summaryBlock()).getByText(SUMMARY_TRUNCATED)).toBeTruthy()
    expect(document.querySelectorAll('.document-summary')).toHaveLength(1)
  })
})

/* ---- A summary of part of a long document ---------------------------------- */

describe('FR-10: the user is told when a summary covers only the first part of a document (D-139)', () => {
  it.each([
    ['says so when summary_truncated is true', { summary_truncated: true }, true],
    ['does not say so when summary_truncated is false', { summary_truncated: false }, false],
    // A classification without the flag has none, which is false.
    ['does not say so when summary_truncated is absent', { summary_truncated: undefined }, false],
    // `input_truncated` is the classifier's flag, about what was read to classify, and is not this one.
    ['does not say so when only input_truncated is true', { summary_truncated: false, input_truncated: true }, false],
  ])('%s', async (_case, fields, told) => {
    await renderDetail(detailOf({ classification: summarised(fields) }))

    // The summary is shown either way; only the sentence depends on the flag.
    const block = screen.getByText(SUMMARY).closest('.ai-content')
    const sentence = screen.queryByText(SUMMARY_TRUNCATED)
    expect(sentence !== null).toBe(told)
    if (told) expect(block.contains(sentence), 'said with the summary it is about').toBe(true)
    expect(TEXT.documentSummaryTruncated).toBe(SUMMARY_TRUNCATED)
  })
})
