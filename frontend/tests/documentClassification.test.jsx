/**
 * FR-10's classification section of the document detail view, rendered against a
 * faked `GET /api/documents/{id}` carrying `classification`, `tag_details` and
 * `tag_options`, and the FR-10 actions, a person applying a tag among them (D-104,
 * D-105 and its dated note of 10 November 2026, night; docs/api-contract.md).
 *
 * Each test defends one clause only the interface can satisfy — what the screen
 * shows, withholds or offers. The threshold, the scheme rule, who may confirm,
 * the scoped-first 404 and the 403 are the server's and are tested in pytest;
 * nothing here stands in for them. The screen decides nothing about a
 * suggestion: it shows the outcome the server recorded, in words.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { NETWORK_ERROR_STATUS, messageForStatus } from '../src/api/client.js'
import { TAG_NAME_MAXIMUM_LENGTH, TEXT, VALIDATION } from '../src/constants.js'
import DocumentDetail from '../src/pages/DocumentDetail.jsx'
import { TOPIC_ALREADY_OFFERED_MESSAGE, heldResponse, serveApi } from './fakeApi.js'

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

/**
 * A classification whose type and department were both applied. The confidences
 * are arbitrary: the screen applies no threshold of its own (D-106's is the
 * server's) and shows the outcome the server recorded.
 */
function classificationOf(overrides = {}) {
  return {
    doc_type: 'Policy',
    doc_type_outcome: 'applied',
    department_outcome: 'applied',
    // A run wrote its suggestion into a blank department (D-119 finding 10).
    department_applied_by: 'ai',
    machine_doc_type: 'Policy',
    machine_doc_type_confidence: 0.92,
    machine_department: 'Human Resources',
    machine_department_confidence: 0.81,
    user_edited: false,
    proposed_topics: [],
    classified_at: '2026-11-09T10:00:00+11:00',
    model: 'gemma3:4b',
    input_truncated: false,
    ...overrides,
  }
}

/** An AI tag applied at or above the threshold, not yet confirmed. */
const AI_TAG = {
  content_tag_id: 'ct-ai',
  dimension: 'Project',
  name: 'policy refresh',
  applied_by: 'ai',
  confirmed: false,
  provisional: false,
  confidence: 0.88,
}

/** A tag a person applied. */
const PERSON_TAG = {
  content_tag_id: 'ct-person',
  dimension: 'Topic',
  name: 'people',
  applied_by: 'user',
  confirmed: true,
  provisional: false,
  confidence: null,
}

/** An AI tag a person has confirmed. */
const CONFIRMED_AI_TAG = {
  content_tag_id: 'ct-confirmed',
  dimension: 'Process',
  name: 'leave requests',
  applied_by: 'ai',
  confirmed: true,
  provisional: false,
  confidence: 0.74,
}

/** An AI tag below the threshold: held, and not among the document's tags. */
const HELD_TAG = {
  content_tag_id: 'ct-held',
  dimension: 'Process',
  name: 'onboarding',
  applied_by: 'ai',
  confirmed: false,
  provisional: true,
  confidence: 0.55,
}

/** The detail object: the document, FR-15's three fields, and FR-10's two. */
function detailOf(overrides = {}) {
  return {
    ...LEAVE,
    extracted_text: 'Employees may request annual leave.',
    tags: { project: [], process: [], topic: [] },
    can_delete: false,
    classification: null,
    tag_details: [],
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

/** The classification section. */
function section() {
  return screen.getByRole('region', { name: TEXT.classificationHeading })
}

/** One assignment — the type or the department — as the section shows it: its value and its provenance. */
function assignment(term) {
  const dt = Array.from(section().querySelectorAll('dt')).find((element) => element.textContent === term)
  const dd = dt.nextElementSibling
  return {
    value: dd.querySelector('.classification__value').textContent,
    provenance: dd.querySelector('.classification__provenance')?.textContent ?? '',
  }
}

/** Every value the section shows as the document's — never a held suggestion. */
function shownValues() {
  return Array.from(section().querySelectorAll('.classification__value'), (element) => element.textContent)
}

/** One dimension's group of the document's tags. */
function tagGroup(label) {
  return screen.getByRole('region', { name: label })
}

/** The group of held suggestions, or null when nothing is held. */
function heldGroup() {
  return screen.queryByRole('region', { name: TEXT.suggestedTagsHeading })
}

/** The metadata list's value for one term — FR-15's rendering above the section. */
function metadata(term) {
  const dt = Array.from(document.querySelector('dl.record-meta').querySelectorAll('dt')).find(
    (element) => element.textContent === term,
  )
  return dt.nextElementSibling.textContent
}

/** A click as a browser makes one: the button takes focus, then is clicked. */
function press(element) {
  element.focus()
  fireEvent.click(element)
}

/** The requests sent to one route, in order. */
function requestsTo(answered, method, path) {
  return answered.filter((request) => request.method === method && request.path === path)
}

/**
 * FR-10's fixed list of types, read from the one place the server defines it
 * (apps/core/constants.py DOCUMENT_TYPES) rather than copied, so the edit form's
 * list cannot drift from the list the server validates against without this
 * file failing — the same rule tests/fakeApi.js applies to NO_ANSWER_MESSAGE.
 */
function serverDocumentTypes() {
  const source = readFileSync(join(import.meta.dirname, '..', '..', 'apps', 'core', 'constants.py'), 'utf8')
  const match = source.match(/^DOCUMENT_TYPES = \(([^)]*)\)\s*$/m)
  if (!match) throw new Error('DOCUMENT_TYPES not found in apps/core/constants.py')
  return [...match[1].matchAll(/"([^"\r\n]+)"/g)].map((literal) => literal[1])
}

/* ---- The type and the department ----------------------------------------- */

describe('FR-10: the type and department are shown with their provenance in words', () => {
  it('marks an applied type and department as suggested by AI, each with its confidence', async () => {
    await renderDetail(detailOf({ classification: classificationOf() }))

    const type = assignment(TEXT.classificationFieldType)
    expect(type.value).toBe('Policy')
    expect(type.provenance).toContain(TEXT.classificationSuggestedByAI)
    expect(type.provenance).toContain(TEXT.classificationConfidence(92))

    const department = assignment(TEXT.classificationFieldDepartment)
    expect(department.value).toBe('Human Resources')
    expect(department.provenance).toContain(TEXT.classificationSuggestedByAI)
    expect(department.provenance).toContain(TEXT.classificationConfidence(81))

    // Applied is not confirmed: the suggestions are still open to a person.
    expect(screen.getByRole('button', { name: TEXT.classificationConfirmAll })).toBeTruthy()
    expect(screen.getByRole('button', { name: TEXT.classificationEdit })).toBeTruthy()
    expect(screen.queryByText(TEXT.classificationNone)).toBeNull()
  })

  it('shows a provisional type as awaiting confirmation, and the document’s type as not yet assigned', async () => {
    await renderDetail(
      detailOf({
        classification: classificationOf({
          doc_type: null,
          doc_type_outcome: 'provisional',
          machine_doc_type: 'Report',
          machine_doc_type_confidence: 0.62,
        }),
      }),
    )

    const type = assignment(TEXT.classificationFieldType)
    expect(type.value).toBe(TEXT.classificationNotAssigned)
    expect(type.provenance).toContain(TEXT.classificationAwaiting)
    expect(type.provenance).toContain(TEXT.classificationSuggestion('Report'))
    expect(type.provenance).toContain(TEXT.classificationConfidence(62))
    // The held suggestion is named beside the value and is nowhere shown as the value.
    expect(shownValues()).not.toContain('Report')
  })

  it('says a confirmed type was confirmed by a person, keeping the machine’s suggestion beside it', async () => {
    await renderDetail(
      detailOf({
        classification: classificationOf({
          doc_type: 'Procedure',
          doc_type_outcome: 'confirmed',
          department_outcome: 'confirmed',
          machine_doc_type: 'Report',
          machine_doc_type_confidence: 0.7,
          user_edited: true,
        }),
      }),
    )

    const type = assignment(TEXT.classificationFieldType)
    expect(type.value).toBe('Procedure')
    expect(type.provenance).toContain(TEXT.classificationConfirmed)
    expect(type.provenance).not.toContain(TEXT.classificationSuggestedByAI)
    expect(type.provenance).toContain(TEXT.classificationSuggestion('Report'))
    // Nothing left to confirm; editing is still offered.
    expect(screen.queryByRole('button', { name: TEXT.classificationConfirmAll })).toBeNull()
    expect(screen.getByRole('button', { name: TEXT.classificationEdit })).toBeTruthy()
  })

  it('says a discarded department suggestion was outside the known departments, and shows the document’s own', async () => {
    await renderDetail(
      detailOf({
        department: 'Human Resources',
        classification: classificationOf({
          department_outcome: 'discarded',
          machine_department: 'Payroll',
          machine_department_confidence: 0.9,
        }),
      }),
    )

    const department = assignment(TEXT.classificationFieldDepartment)
    expect(department.value).toBe('Human Resources')
    expect(department.provenance).toBe(TEXT.classificationDiscardedDepartment('Payroll'))
    expect(shownValues()).not.toContain('Payroll')
  })
})

describe('D-119 finding 6: the notice that only the opening of a long document was read (D-104)', () => {
  it('says so when the classification has input_truncated true', async () => {
    await renderDetail(detailOf({ classification: classificationOf({ input_truncated: true }) }))

    expect(within(section()).getByText(TEXT.classificationTruncated)).toBeTruthy()
  })

  it('says nothing about it when input_truncated is false', async () => {
    await renderDetail(detailOf({ classification: classificationOf({ input_truncated: false }) }))

    // The assignments rendered, so the notice's absence is not a section that never drew.
    expect(assignment(TEXT.classificationFieldType).value).toBe('Policy')
    expect(within(section()).queryByText(TEXT.classificationTruncated)).toBeNull()
  })
})

describe('D-119 finding 10: whose department it is, from department_applied_by', () => {
  it('says an applied department a person gave, which the AI’s suggestion matched, is the person’s and not "Suggested by AI"', async () => {
    await renderDetail(detailOf({ classification: classificationOf({ department_applied_by: 'user' }) }))

    const department = assignment(TEXT.classificationFieldDepartment)
    expect(department.value).toBe('Human Resources')
    expect(department.provenance).toBe(
      `${TEXT.classificationGivenByPerson}. ${TEXT.classificationSuggestionMatched}, ${TEXT.classificationConfidence(81)}.`,
    )
    expect(department.provenance).not.toContain(TEXT.classificationSuggestedByAI)
    // The type beside it was the machine's, and still says so: the field is the department's alone.
    expect(assignment(TEXT.classificationFieldType).provenance).toBe(
      `${TEXT.classificationSuggestedByAI}, ${TEXT.classificationConfidence(92)}`,
    )
  })

  it.each([
    ['"ai", a run having written it into a blank department', 'ai'],
    ['null, as on a classification recorded before the field', null],
  ])('keeps "Suggested by AI" on an applied department whose department_applied_by is %s', async (_case, appliedBy) => {
    await renderDetail(detailOf({ classification: classificationOf({ department_applied_by: appliedBy }) }))

    const department = assignment(TEXT.classificationFieldDepartment)
    expect(department.provenance).toBe(`${TEXT.classificationSuggestedByAI}, ${TEXT.classificationConfidence(81)}`)
    expect(department.provenance).not.toContain(TEXT.classificationGivenByPerson)
  })
})

describe('FR-10: confirming and editing the type and department', () => {
  it('Confirm sends one request with an empty body, and the view updates from the reply', async () => {
    const after = classificationOf({
      doc_type: 'Report',
      doc_type_outcome: 'confirmed',
      department_outcome: 'confirmed',
      machine_doc_type: 'Report',
      machine_doc_type_confidence: 0.62,
      machine_department: 'Finance',
      machine_department_confidence: 0.6,
      user_edited: true,
    })
    const answered = await renderDetail(
      detailOf({
        department: '',
        classification: classificationOf({
          doc_type: null,
          doc_type_outcome: 'provisional',
          department_outcome: 'provisional',
          machine_doc_type: 'Report',
          machine_doc_type_confidence: 0.62,
          machine_department: 'Finance',
          machine_department_confidence: 0.6,
        }),
      }),
      { [`POST ${DOC}/classification`]: { body: { classification: after, department: 'Finance' } } },
    )
    expect(assignment(TEXT.classificationFieldType).value).toBe(TEXT.classificationNotAssigned)
    expect(assignment(TEXT.classificationFieldDepartment).value).toBe(TEXT.documentNotRecorded)

    const confirm = screen.getByRole('button', { name: TEXT.classificationConfirmAll })
    press(confirm)
    // Pressed again before the reply, as an impatient user does: still one request.
    fireEvent.click(confirm)

    await waitFor(() => expect(assignment(TEXT.classificationFieldType).value).toBe('Report'))
    expect(assignment(TEXT.classificationFieldType).provenance).toContain(TEXT.classificationConfirmed)
    // The confirm wrote the held department into a blank one, and the page shows the
    // department the reply carries, in the section and in the metadata list above it.
    expect(assignment(TEXT.classificationFieldDepartment).value).toBe('Finance')
    expect(metadata(TEXT.documentFieldDepartment)).toBe('Finance')
    expect(screen.getByRole('status').textContent).toBe(TEXT.classificationConfirmedAll)
    expect(screen.queryByRole('button', { name: TEXT.classificationConfirmAll })).toBeNull()

    expect(requestsTo(answered, 'POST', `${DOC}/classification`)).toEqual([
      { method: 'POST', path: `${DOC}/classification`, search: '', body: {} },
    ])
  })

  it('Edit sends the chosen type and department in one request, placing a 400 under the field it names', async () => {
    let attempts = 0
    const refusal = 'Choose a type from the list.'
    const after = classificationOf({
      doc_type: 'Meeting Paper',
      doc_type_outcome: 'confirmed',
      department_outcome: 'confirmed',
      user_edited: true,
    })
    const answered = await renderDetail(detailOf({ classification: classificationOf() }), {
      [`POST ${DOC}/classification`]: () => {
        attempts += 1
        return attempts === 1
          ? { status: 400, body: { doc_type: [refusal] } }
          : { body: { classification: after, department: 'Finance' } }
      },
    })

    press(screen.getByRole('button', { name: TEXT.classificationEdit }))
    const select = screen.getByLabelText(TEXT.classificationFieldType)
    // The form starts from the document's own values.
    expect(select.value).toBe('Policy')
    expect(screen.getByLabelText(TEXT.classificationFieldDepartment).value).toBe('Human Resources')

    fireEvent.change(select, { target: { value: 'Meeting Paper' } })
    fireEvent.change(screen.getByLabelText(TEXT.classificationFieldDepartment), { target: { value: ' Finance ' } })
    fireEvent.click(screen.getByRole('button', { name: TEXT.classificationSave }))

    // The 400: under the field, as a field error, and the form stays open.
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.classificationCheckFields)
    const invalid = screen.getByLabelText(TEXT.classificationFieldType)
    expect(invalid.getAttribute('aria-invalid')).toBe('true')
    const describedBy = invalid.getAttribute('aria-describedby').split(' ')
    const errorText = describedBy.map((id) => document.getElementById(id)?.textContent ?? '').join(' ')
    expect(errorText).toContain(refusal)
    expect(assignment(TEXT.classificationFieldType).value).toBe('Policy')

    fireEvent.click(screen.getByRole('button', { name: TEXT.classificationSave }))
    await waitFor(() => expect(assignment(TEXT.classificationFieldType).value).toBe('Meeting Paper'))
    expect(assignment(TEXT.classificationFieldType).provenance).toContain(TEXT.classificationConfirmed)
    expect(assignment(TEXT.classificationFieldDepartment).value).toBe('Finance')
    expect(metadata(TEXT.documentFieldDepartment)).toBe('Finance')
    expect(screen.queryByLabelText(TEXT.classificationFieldType)).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()

    // Both attempts carried both values, trimmed, in the contract's names.
    const sent = { doc_type: 'Meeting Paper', department: 'Finance' }
    expect(requestsTo(answered, 'POST', `${DOC}/classification`).map((request) => request.body)).toEqual([sent, sent])
  })
})

/**
 * D-105's note of 10 November: Human Resources is already on the document, and
 * the AI suggests Finance. The department stays, and the suggestion is held
 * for a person to accept, at 97% as at any confidence.
 */
function heldDepartmentDetail(overrides = {}) {
  return detailOf({
    department: 'Human Resources',
    classification: classificationOf({
      department_outcome: 'provisional',
      machine_department: 'Finance',
      machine_department_confidence: 0.97,
    }),
    ...overrides,
  })
}

describe('D-105, 10 November: a department already on the document stays current while a different suggestion waits', () => {
  it('shows the document’s department as current and the suggestion as awaiting confirmation, then after Confirm the department the server stored', async () => {
    const confirmed = classificationOf({
      doc_type_outcome: 'confirmed',
      department_outcome: 'confirmed',
      machine_department: 'Finance',
      machine_department_confidence: 0.97,
      user_edited: true,
    })
    const answered = await renderDetail(heldDepartmentDetail(), {
      [`POST ${DOC}/classification`]: { body: { classification: confirmed, department: 'Finance' } },
    })

    const before = assignment(TEXT.classificationFieldDepartment)
    expect(before.value).toBe('Human Resources')
    expect(before.provenance).toContain(TEXT.classificationAwaiting)
    expect(before.provenance).toContain(`${TEXT.classificationSuggestion('Finance')}, ${TEXT.classificationConfidence(97)}`)
    // What Confirm will do to the department on screen, said before it is pressed.
    expect(before.provenance).toContain(TEXT.classificationConfirmReplaces('Human Resources', 'Finance'))
    expect(shownValues()).not.toContain('Finance')
    expect(metadata(TEXT.documentFieldDepartment)).toBe('Human Resources')

    press(screen.getByRole('button', { name: TEXT.classificationConfirmAll }))

    await waitFor(() => expect(assignment(TEXT.classificationFieldDepartment).value).toBe('Finance'))
    expect(assignment(TEXT.classificationFieldDepartment).provenance).toBe(TEXT.classificationConfirmed)
    expect(metadata(TEXT.documentFieldDepartment)).toBe('Finance')
    expect(requestsTo(answered, 'POST', `${DOC}/classification`).map((request) => request.body)).toEqual([{}])
  })

  it.each([
    ['the department already on the document, not the different suggestion', 'Human Resources', 'Human Resources'],
    ['the held suggestion when the document has no department', '', 'Finance'],
  ])('Edit starts the department field from %s', async (_case, onDocument, expected) => {
    await renderDetail(heldDepartmentDetail({ department: onDocument }))

    press(screen.getByRole('button', { name: TEXT.classificationEdit }))
    expect(screen.getByLabelText(TEXT.classificationFieldDepartment).value).toBe(expected)
  })
})

describe('the department after a confirm is the one the reply carries (docs/api-contract.md, FR-10)', () => {
  it('shows the department the reply carries, even where the page would have worked out another', async () => {
    // Another session confirmed Operations after this page loaded, so this confirm
    // found nothing held and changed nothing, and the reply says Operations.
    // Worked out from the outcome, as the page did before the reply carried a
    // department, it would have read Finance, the suggestion on screen.
    const confirmed = classificationOf({
      doc_type_outcome: 'confirmed',
      department_outcome: 'confirmed',
      machine_department: 'Finance',
      machine_department_confidence: 0.97,
      user_edited: true,
    })
    await renderDetail(heldDepartmentDetail(), {
      [`POST ${DOC}/classification`]: { body: { classification: confirmed, department: 'Operations' } },
    })

    press(screen.getByRole('button', { name: TEXT.classificationConfirmAll }))

    await waitFor(() => expect(assignment(TEXT.classificationFieldDepartment).value).toBe('Operations'))
    expect(metadata(TEXT.documentFieldDepartment)).toBe('Operations')
    expect(shownValues()).not.toContain('Finance')
    // The machine's value is still named beside the person's, as FR-10 keeps it.
    expect(assignment(TEXT.classificationFieldDepartment).provenance).toContain(TEXT.classificationSuggestion('Finance'))
  })

  it('falls back, for a reply without department from a server before 10 November, to the department the confirm stored', async () => {
    const confirmed = classificationOf({
      doc_type_outcome: 'confirmed',
      department_outcome: 'confirmed',
      machine_department: 'Finance',
      machine_department_confidence: 0.6,
      user_edited: true,
    })
    await renderDetail(
      detailOf({
        department: '',
        classification: classificationOf({
          department_outcome: 'provisional',
          machine_department: 'Finance',
          machine_department_confidence: 0.6,
        }),
      }),
      // The reply as it was before 10 November: `{classification}` alone. Not the
      // contract now; it is here only to defend the fallback.
      { [`POST ${DOC}/classification`]: { body: { classification: confirmed } } },
    )
    expect(assignment(TEXT.classificationFieldDepartment).value).toBe(TEXT.documentNotRecorded)

    press(screen.getByRole('button', { name: TEXT.classificationConfirmAll }))

    await waitFor(() => expect(assignment(TEXT.classificationFieldDepartment).value).toBe('Finance'))
    expect(metadata(TEXT.documentFieldDepartment)).toBe('Finance')
  })
})

describe('FR-10 validation: the type is selected from a fixed list rather than generated freely', () => {
  it('offers exactly the server’s DOCUMENT_TYPES, in its order, as a select and not a free-text field', async () => {
    await renderDetail(detailOf({ classification: classificationOf() }))

    press(screen.getByRole('button', { name: TEXT.classificationEdit }))
    const select = screen.getByLabelText(TEXT.classificationFieldType)
    expect(select.tagName).toBe('SELECT')
    const types = serverDocumentTypes()
    // Not vacuous: FR-10 names four.
    expect(types).toHaveLength(4)
    expect(Array.from(select.options, (option) => option.value)).toEqual(types)
    expect(Array.from(select.options, (option) => option.textContent)).toEqual(types)
  })
})

/* ---- Tags ---------------------------------------------------------------- */

describe('FR-10: tags applied automatically are distinguished from those applied by a person', () => {
  it('labels a machine’s tag, a person’s tag and a confirmed machine tag differently, in words', async () => {
    await renderDetail(
      detailOf({
        tags: { project: ['policy refresh'], process: ['leave requests'], topic: ['people'] },
        classification: classificationOf(),
        tag_details: [AI_TAG, PERSON_TAG, CONFIRMED_AI_TAG],
      }),
    )

    const ai = within(tagGroup(TEXT.documentFieldProject))
    expect(ai.getByText(AI_TAG.name)).toBeTruthy()
    expect(ai.getByText(`${TEXT.tagSuggestedByAI}, ${TEXT.classificationConfidence(88)}`)).toBeTruthy()
    expect(ai.getByRole('button', { name: TEXT.tagConfirmLabel(AI_TAG.name) })).toBeTruthy()
    expect(ai.getByRole('button', { name: TEXT.tagRemoveLabel(AI_TAG.name) })).toBeTruthy()

    const person = within(tagGroup(TEXT.documentFieldTopic))
    expect(person.getByText(PERSON_TAG.name)).toBeTruthy()
    expect(person.getByText(TEXT.tagAddedByPerson)).toBeTruthy()
    expect(person.queryByText(TEXT.tagSuggestedByAI, { exact: false })).toBeNull()
    // Nothing to confirm on a person's tag; it can still be removed in one action.
    expect(person.queryByRole('button', { name: TEXT.tagConfirmLabel(PERSON_TAG.name) })).toBeNull()
    expect(person.getByRole('button', { name: TEXT.tagRemoveLabel(PERSON_TAG.name) })).toBeTruthy()

    const confirmed = within(tagGroup(TEXT.documentFieldProcess))
    expect(confirmed.getByText(`${TEXT.tagConfirmedAI}, ${TEXT.classificationConfidence(74)}`)).toBeTruthy()
    expect(confirmed.queryByRole('button', { name: TEXT.tagConfirmLabel(CONFIRMED_AI_TAG.name) })).toBeNull()

    // The distinction is carried by a class as well, for the border — and never only by it.
    expect(ai.getByText(AI_TAG.name).closest('li').className).toContain('tag--ai')
    expect(person.getByText(PERSON_TAG.name).closest('li').className).toContain('tag--user')
    expect(heldGroup()).toBeNull()
  })

  it('renders a tag name as text, never as HTML', async () => {
    const hostile = '<img src="x" onerror="window.__fr10Injected = true"><b>people</b>'
    await renderDetail(
      detailOf({
        classification: classificationOf(),
        tag_details: [{ ...PERSON_TAG, name: hostile }],
      }),
    )

    expect(within(tagGroup(TEXT.documentFieldTopic)).getByText(hostile)).toBeTruthy()
    expect(document.querySelectorAll('img, b')).toHaveLength(0)
    expect(window.__fr10Injected).toBeUndefined()
  })

  it('lists a provisional tag under the suggestions awaiting confirmation, and never among the document’s tags', async () => {
    await renderDetail(
      detailOf({
        tags: { project: [], process: [], topic: [] },
        classification: classificationOf(),
        tag_details: [HELD_TAG],
      }),
    )

    // Not a Process tag of the document.
    const process = within(tagGroup(TEXT.documentFieldProcess))
    expect(process.getByText(TEXT.documentNoTags)).toBeTruthy()
    expect(process.queryByText(HELD_TAG.name)).toBeNull()
    expect(metadata(TEXT.documentFieldProcess)).toBe(TEXT.documentNoTags)

    // Under the suggestions, with its dimension named, Confirm and Reject.
    const held = within(heldGroup())
    expect(held.getByText(HELD_TAG.name)).toBeTruthy()
    expect(held.getByText(TEXT.documentFieldProcess)).toBeTruthy()
    expect(held.getByText(`${TEXT.tagSuggestedByAI}, ${TEXT.classificationConfidence(55)}`)).toBeTruthy()
    expect(held.getByRole('button', { name: TEXT.tagConfirmLabel(HELD_TAG.name) })).toBeTruthy()
    expect(held.getByRole('button', { name: TEXT.tagRejectLabel(HELD_TAG.name) })).toBeTruthy()
    expect(held.queryByRole('button', { name: TEXT.tagRemoveLabel(HELD_TAG.name) })).toBeNull()
  })

  it('Confirm and Reject on a tag each send one request and update the section from the reply', async () => {
    const answered = await renderDetail(
      detailOf({
        tags: { project: ['policy refresh'], process: [], topic: [] },
        classification: classificationOf(),
        tag_details: [AI_TAG, HELD_TAG],
      }),
      {
        [`POST ${DOC}/tags/${AI_TAG.content_tag_id}/confirm`]: { body: { ...AI_TAG, confirmed: true } },
        [`DELETE ${DOC}/tags/${HELD_TAG.content_tag_id}`]: { status: 204 },
      },
    )

    const confirm = within(tagGroup(TEXT.documentFieldProject)).getByRole('button', {
      name: TEXT.tagConfirmLabel(AI_TAG.name),
    })
    press(confirm)
    fireEvent.click(confirm)

    await waitFor(() =>
      expect(
        within(tagGroup(TEXT.documentFieldProject)).getByText(
          `${TEXT.tagConfirmedAI}, ${TEXT.classificationConfidence(88)}`,
        ),
      ).toBeTruthy(),
    )
    expect(
      within(tagGroup(TEXT.documentFieldProject)).queryByRole('button', { name: TEXT.tagConfirmLabel(AI_TAG.name) }),
    ).toBeNull()
    expect(screen.getByRole('status').textContent).toBe(TEXT.tagConfirmed(AI_TAG.name))

    press(within(heldGroup()).getByRole('button', { name: TEXT.tagRejectLabel(HELD_TAG.name) }))
    await waitFor(() => expect(heldGroup()).toBeNull())
    expect(screen.queryByText(HELD_TAG.name)).toBeNull()
    expect(screen.getByRole('status').textContent).toBe(TEXT.tagRejected(HELD_TAG.name))
    // The confirmed tag is still the document's.
    expect(within(tagGroup(TEXT.documentFieldProject)).getByText(AI_TAG.name)).toBeTruthy()

    expect(requestsTo(answered, 'POST', `${DOC}/tags/${AI_TAG.content_tag_id}/confirm`)).toHaveLength(1)
    expect(requestsTo(answered, 'DELETE', `${DOC}/tags/${HELD_TAG.content_tag_id}`)).toHaveLength(1)
    expect(answered.filter((request) => request.method !== 'GET')).toHaveLength(2)
  })

  it('a proposed new Topic value can be confirmed, which makes it a tag, or rejected', async () => {
    const proposed = [
      { value: 'wellbeing', confidence: 0.6 },
      { value: 'retention', confidence: 0.5 },
    ]
    const newTag = {
      content_tag_id: 'ct-new',
      dimension: 'Topic',
      name: 'wellbeing',
      applied_by: 'ai',
      confirmed: true,
      provisional: false,
      confidence: 0.6,
    }
    const answered = await renderDetail(
      detailOf({
        tags: { project: [], process: [], topic: ['people'] },
        classification: classificationOf({ proposed_topics: proposed }),
        tag_details: [PERSON_TAG],
      }),
      {
        [`POST ${DOC}/proposed-topics/confirm`]: {
          body: {
            classification: classificationOf({ proposed_topics: [proposed[1]] }),
            tag_details: [PERSON_TAG, newTag],
          },
        },
        [`POST ${DOC}/proposed-topics/reject`]: {
          body: { classification: classificationOf({ proposed_topics: [] }), tag_details: [PERSON_TAG, newTag] },
        },
      },
    )

    // Proposed, not a tag: in the suggestions, labelled as a new topic, and not in Topic.
    const held = within(heldGroup())
    expect(held.getByText('wellbeing')).toBeTruthy()
    expect(held.getAllByText(TEXT.proposedTopicLabel, { exact: false })).toHaveLength(2)
    expect(within(tagGroup(TEXT.documentFieldTopic)).queryByText('wellbeing')).toBeNull()
    expect(metadata(TEXT.documentFieldTopic)).toBe('people')

    press(held.getByRole('button', { name: TEXT.proposedTopicConfirmLabel('wellbeing') }))
    await waitFor(() => expect(within(tagGroup(TEXT.documentFieldTopic)).getByText('wellbeing')).toBeTruthy())
    expect(within(heldGroup()).queryByText('wellbeing')).toBeNull()
    expect(metadata(TEXT.documentFieldTopic)).toBe('people, wellbeing')
    expect(screen.getByRole('status').textContent).toBe(TEXT.proposedTopicConfirmed('wellbeing'))

    press(within(heldGroup()).getByRole('button', { name: TEXT.proposedTopicRejectLabel('retention') }))
    await waitFor(() => expect(heldGroup()).toBeNull())
    expect(screen.queryByText('retention')).toBeNull()
    expect(screen.getByRole('status').textContent).toBe(TEXT.proposedTopicRejected('retention'))

    expect(requestsTo(answered, 'POST', `${DOC}/proposed-topics/confirm`).map((request) => request.body)).toEqual([
      { value: 'wellbeing' },
    ])
    expect(requestsTo(answered, 'POST', `${DOC}/proposed-topics/reject`).map((request) => request.body)).toEqual([
      { value: 'retention' },
    ])
  })
})

/* ---- Classify now -------------------------------------------------------- */

describe('FR-10: a document that has never been classified', () => {
  it('says so, and "Classify now" shows a busy state until the reply, then the result', async () => {
    const classify = heldResponse()
    const answered = await renderDetail(detailOf(), { [`POST ${DOC}/classify`]: classify.route })

    expect(screen.getByText(TEXT.classificationNone)).toBeTruthy()
    expect(section().querySelectorAll('dl')).toHaveLength(0)

    const button = screen.getByRole('button', { name: TEXT.classifyNow })
    press(button)
    fireEvent.click(button)

    // Busy: the button says so and is marked so, and the wait is announced.
    const busy = await screen.findByRole('button', { name: TEXT.classifying })
    expect(busy.getAttribute('aria-busy')).toBe('true')
    expect(screen.getByRole('status').textContent).toBe(TEXT.classifyingStatus)
    expect(screen.queryByText(TEXT.classificationNone)).toBeTruthy()

    classify.release({
      body: { classification: classificationOf(), tag_details: [AI_TAG], department: LEAVE.department },
    })

    await waitFor(() => expect(assignment(TEXT.classificationFieldType).value).toBe('Policy'))
    expect(screen.queryByText(TEXT.classificationNone)).toBeNull()
    expect(screen.queryByRole('button', { name: TEXT.classifyNow })).toBeNull()
    expect(screen.getByRole('button', { name: TEXT.classificationConfirmAll })).toBeTruthy()
    expect(within(tagGroup(TEXT.documentFieldProject)).getByText(AI_TAG.name)).toBeTruthy()
    // The metadata list above took the new links as well.
    expect(metadata(TEXT.documentFieldProject)).toBe(AI_TAG.name)
    expect(screen.getByRole('status').textContent).toBe(TEXT.classifyDone)
    expect(requestsTo(answered, 'POST', `${DOC}/classify`)).toHaveLength(1)
  })

  it('shows the department the classify reply carries, filling a blank one, beside the AI label', async () => {
    // A run fills a blank department with an applied suggestion (D-105), and the
    // reply says what the department now is.
    const answered = await renderDetail(detailOf({ department: '' }), {
      [`POST ${DOC}/classify`]: {
        body: {
          classification: classificationOf({ machine_department: 'Finance', machine_department_confidence: 0.97 }),
          tag_details: [],
          department: 'Finance',
        },
      },
    })
    expect(metadata(TEXT.documentFieldDepartment)).toBe(TEXT.documentNotRecorded)

    fireEvent.click(screen.getByRole('button', { name: TEXT.classifyNow }))

    await waitFor(() => expect(assignment(TEXT.classificationFieldDepartment).value).toBe('Finance'))
    expect(assignment(TEXT.classificationFieldDepartment).provenance).toBe(
      `${TEXT.classificationSuggestedByAI}, ${TEXT.classificationConfidence(97)}`,
    )
    expect(metadata(TEXT.documentFieldDepartment)).toBe('Finance')
    expect(requestsTo(answered, 'POST', `${DOC}/classify`)).toHaveLength(1)
  })

  it('keeps the department as it was when a classify reply carries none, as from a server before the field', async () => {
    await renderDetail(detailOf({ department: 'Human Resources' }), {
      // The classify reply before the field: `{classification, tag_details}`. Not the
      // contract now; it is here only to defend the fallback.
      [`POST ${DOC}/classify`]: { body: { classification: classificationOf(), tag_details: [] } },
    })

    fireEvent.click(screen.getByRole('button', { name: TEXT.classifyNow }))

    await waitFor(() => expect(assignment(TEXT.classificationFieldType).value).toBe('Policy'))
    expect(assignment(TEXT.classificationFieldDepartment).value).toBe('Human Resources')
    expect(metadata(TEXT.documentFieldDepartment)).toBe('Human Resources')
  })

  it('says in words that there was no text to classify on a 422, never showing the backend text', async () => {
    const backendText = 'No text was extracted for document doc-1 (ExtractedContent missing).'
    await renderDetail(detailOf(), { [`POST ${DOC}/classify`]: { status: 422, body: { detail: backendText } } })

    fireEvent.click(screen.getByRole('button', { name: TEXT.classifyNow }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.classifyFailedTitle)
    expect(alert.textContent).toContain(TEXT.classifyNoText)
    expect(document.body.textContent).not.toContain(backendText)
    // Still unclassified, and the action is still there.
    expect(screen.getByText(TEXT.classificationNone)).toBeTruthy()
    expect(screen.getByRole('button', { name: TEXT.classifyNow })).toBeTruthy()
  })

  it('shows NFR-19’s notice at once on a 503, with what became of the record', async () => {
    const backendText = 'FLM unreachable after 3 attempts: ConnectionRefusedError'
    await renderDetail(detailOf(), { [`POST ${DOC}/classify`]: { status: 503, body: { detail: backendText } } })

    fireEvent.click(screen.getByRole('button', { name: TEXT.classifyNow }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('AI service unavailable')
    expect(alert.textContent).toContain(messageForStatus(503))
    expect(alert.textContent).toContain(TEXT.classifyNotDone)
    expect(document.body.textContent).not.toContain(backendText)
    expect(screen.getByRole('button', { name: TEXT.classifyNow })).toBeTruthy()
    expect(screen.queryByRole('button', { name: TEXT.classifying })).toBeNull()
  })

  it('names when to try again on the ingestion 429, from Retry-After', async () => {
    await renderDetail(detailOf(), {
      [`POST ${DOC}/classify`]: { status: 429, body: { detail: 'Request was throttled.' }, headers: { 'Retry-After': '120' } },
    })

    fireEvent.click(screen.getByRole('button', { name: TEXT.classifyNow }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.classifyLimitReached(TEXT.retryInMinutes(2)))
    expect(document.body.textContent).not.toContain('Request was throttled.')
  })
})

/* ---- Refusals ------------------------------------------------------------ */

describe('FR-10: a 403 and a 404 on an action', () => {
  it('a 403 withdraws every control and says the role may not change classifications', async () => {
    const backendText = 'You do not have permission to perform this action.'
    await renderDetail(
      detailOf({
        tags: { project: ['policy refresh'], process: [], topic: ['people'] },
        classification: classificationOf({ proposed_topics: [{ value: 'wellbeing', confidence: 0.6 }] }),
        tag_details: [AI_TAG, PERSON_TAG, HELD_TAG],
      }),
      { [`POST ${DOC}/tags/${AI_TAG.content_tag_id}/confirm`]: { status: 403, body: { detail: backendText } } },
    )
    expect(within(section()).getAllByRole('button').length).toBeGreaterThan(5)

    press(screen.getByRole('button', { name: TEXT.tagConfirmLabel(AI_TAG.name) }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.classificationNotPermitted)
    expect(document.body.textContent).not.toContain(backendText)
    // Every control in the section, not only the one pressed.
    expect(within(section()).queryAllByRole('button')).toEqual([])
    // The record and its labels stay: reading needs no permission beyond scope.
    expect(assignment(TEXT.classificationFieldType).value).toBe('Policy')
    expect(within(tagGroup(TEXT.documentFieldProject)).getByText(AI_TAG.name)).toBeTruthy()
    expect(within(tagGroup(TEXT.documentFieldTopic)).getByText(TEXT.tagAddedByPerson)).toBeTruthy()
    expect(within(heldGroup()).getByText(HELD_TAG.name)).toBeTruthy()
    expect(within(heldGroup()).getByText('wellbeing')).toBeTruthy()
  })

  it('a 404 says the record could not be found, as the delete path does, and nothing more', async () => {
    await renderDetail(
      detailOf({ classification: classificationOf(), tag_details: [AI_TAG] }),
      { [`DELETE ${DOC}/tags/${AI_TAG.content_tag_id}`]: { status: 404, body: { detail: 'Not found.' } } },
    )

    fireEvent.click(screen.getByRole('button', { name: TEXT.tagRemoveLabel(AI_TAG.name) }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.documentRecordNotFound)
    expect(document.body.textContent).not.toContain('Not found.')
    expect(document.body.textContent).not.toMatch(/permi/i)
  })
})

/* ---- A person adds a tag (FR-10's provenance clause, UC-09 A3) ----------- */

/*
 * `tag_options` as the detail carries it (docs/api-contract.md, NIT3004 FR-10):
 * all three keys, each list sorted by name. A `tag_id` is the Tag's own id, not a
 * link's `content_tag_id`.
 */
const BRIDGE = { tag_id: 'tag-bridge', tag_name: 'bridge maintenance' }
const REFRESH = { tag_id: 'tag-refresh', tag_name: 'policy refresh' }
const ONBOARDING = { tag_id: 'tag-onboarding', tag_name: 'onboarding' }
const PURCHASING = { tag_id: 'tag-purchasing', tag_name: 'purchasing' }
const BUDGET = { tag_id: 'tag-budget', tag_name: 'budget planning' }

function optionsOf(overrides = {}) {
  return { Project: [BRIDGE, REFRESH], Process: [ONBOARDING, PURCHASING], Topic: [BUDGET], ...overrides }
}

/** A link the apply route made: a person's, confirmed, with no confidence (the contract's 201). */
function personLink(contentTagId, dimension, name) {
  return {
    content_tag_id: contentTagId,
    dimension,
    name,
    applied_by: 'user',
    confirmed: true,
    provisional: false,
    confidence: null,
  }
}

/** The add-a-tag part of the section, or null while it is not offered. */
function addSection() {
  return screen.queryByRole('region', { name: TEXT.tagAddHeading })
}

/** The form that applies a tag the document offers. */
function chooser() {
  return within(screen.getByRole('form', { name: TEXT.tagChooseLegend }))
}

/** The form that applies a new Topic by name. */
function topicForm() {
  return within(screen.getByRole('form', { name: TEXT.tagNewTopicLegend }))
}

/** The names a select offers, in order. */
function offeredNames(select) {
  return Array.from(select.options, (option) => option.textContent)
}

/** What the section's live region says: the latest outcome. */
function announcement() {
  return section().querySelector('.classification__announcement').textContent
}

/** Everything that describes a field to assistive technology: its hint and its error. */
function descriptionOf(field) {
  return (field.getAttribute('aria-describedby') ?? '')
    .split(' ')
    .map((id) => document.getElementById(id)?.textContent ?? '')
    .join(' ')
}

/** The detail's GET answered with `first` once, and with `later` on every read after it. */
function detailReads(first, later) {
  let reads = 0
  return () => {
    reads += 1
    return { body: reads === 1 ? first : later }
  }
}

describe('FR-10 (UC-09 A3): a person adds a tag the document offers, or a new topic', () => {
  it('offers each dimension’s tags from tag_options, sends the chosen one by tag_id, announces the 201, and offers what the options read again say', async () => {
    const before = detailOf({
      tags: { project: ['policy refresh'], process: [], topic: [] },
      classification: classificationOf(),
      tag_details: [AI_TAG],
      tag_options: optionsOf(),
    })
    // The second read of the detail: a Topic another session added meanwhile.
    const after = { ...before, tag_options: optionsOf({ Topic: [BUDGET, { tag_id: 'tag-safety', tag_name: 'site safety' }] }) }
    const answered = await renderDetail(before, {
      [`GET ${DOC}`]: detailReads(before, after),
      [`POST ${DOC}/tags`]: {
        status: 201,
        body: { tag_details: [AI_TAG, personLink('ct-purchasing', 'Process', PURCHASING.tag_name)] },
      },
    })

    const dimension = chooser().getByLabelText(TEXT.tagDimensionLabel)
    expect(Array.from(dimension.options, (option) => option.value)).toEqual(['Project', 'Process', 'Topic'])
    expect(offeredNames(chooser().getByLabelText(TEXT.tagChooseLabel))).toEqual([BRIDGE.tag_name, REFRESH.tag_name])

    fireEvent.change(dimension, { target: { value: 'Process' } })
    const tag = chooser().getByLabelText(TEXT.tagChooseLabel)
    expect(offeredNames(tag)).toEqual([ONBOARDING.tag_name, PURCHASING.tag_name])
    fireEvent.change(tag, { target: { value: PURCHASING.tag_id } })
    press(chooser().getByRole('button', { name: TEXT.tagAddLabel(PURCHASING.tag_name) }))

    await waitFor(() => expect(announcement()).toBe(TEXT.tagApplied(PURCHASING.tag_name)))
    // The new link as the reply lists it, marked as a person's, and in the metadata above.
    const process = within(tagGroup(TEXT.documentFieldProcess))
    expect(process.getByText(PURCHASING.tag_name)).toBeTruthy()
    expect(process.getByText(TEXT.tagAddedByPerson)).toBeTruthy()
    expect(metadata(TEXT.documentFieldProcess)).toBe(PURCHASING.tag_name)
    // One request in the contract's form, then one read of the detail for its options.
    expect(requestsTo(answered, 'POST', `${DOC}/tags`).map((request) => request.body)).toEqual([
      { tag_id: PURCHASING.tag_id },
    ])
    expect(requestsTo(answered, 'GET', DOC)).toHaveLength(2)
    // The chooser now offers what that read said.
    fireEvent.change(chooser().getByLabelText(TEXT.tagDimensionLabel), { target: { value: 'Topic' } })
    expect(offeredNames(chooser().getByLabelText(TEXT.tagChooseLabel))).toEqual([BUDGET.tag_name, 'site safety'])
  })

  it('announces a 200, a tag already on the document, in other words than a 201', async () => {
    // "onboarding" is held as a suggestion; applying it confirms it, which is the 200.
    const confirmed = { ...HELD_TAG, confirmed: true, provisional: false }
    const answered = await renderDetail(
      detailOf({ classification: classificationOf(), tag_details: [HELD_TAG], tag_options: optionsOf() }),
      { [`POST ${DOC}/tags`]: { status: 200, body: { tag_details: [confirmed] } } },
    )

    fireEvent.change(chooser().getByLabelText(TEXT.tagDimensionLabel), { target: { value: 'Process' } })
    press(chooser().getByRole('button', { name: TEXT.tagAddLabel(ONBOARDING.tag_name) }))

    await waitFor(() => expect(announcement()).toBe(TEXT.tagAlreadyApplied(ONBOARDING.tag_name)))
    expect(announcement()).not.toBe(TEXT.tagApplied(ONBOARDING.tag_name))
    // The suggestion is among the document's tags now, as the reply lists it.
    expect(heldGroup()).toBeNull()
    expect(
      within(tagGroup(TEXT.documentFieldProcess)).getByText(`${TEXT.tagConfirmedAI}, ${TEXT.classificationConfidence(55)}`),
    ).toBeTruthy()
    expect(requestsTo(answered, 'POST', `${DOC}/tags`).map((request) => request.body)).toEqual([
      { tag_id: ONBOARDING.tag_id },
    ])
  })

  it('sends a new topic single-spaced as {dimension: "Topic", tag_name}, announces the name stored, clears the field, and offers it from the options read again', async () => {
    const before = detailOf({ classification: classificationOf(), tag_details: [], tag_options: optionsOf() })
    const reforecast = { tag_id: 'tag-reforecast', tag_name: 'budget reforecast' }
    const after = { ...before, tag_options: optionsOf({ Topic: [BUDGET, reforecast] }) }
    const answered = await renderDetail(before, {
      [`GET ${DOC}`]: detailReads(before, after),
      [`POST ${DOC}/tags`]: {
        status: 201,
        body: { tag_details: [personLink('ct-reforecast', 'Topic', reforecast.tag_name)] },
      },
    })

    const field = topicForm().getByLabelText(TEXT.tagNewTopicLabel)
    fireEvent.change(field, { target: { value: '  Budget \t  Reforecast  ' } })
    press(topicForm().getByRole('button', { name: TEXT.tagNewTopicAdd }))

    // In the server's lower case, from the reply, as the list beside it shows it.
    await waitFor(() => expect(announcement()).toBe(TEXT.tagApplied(reforecast.tag_name)))
    expect(field.value).toBe('')
    expect(within(tagGroup(TEXT.documentFieldTopic)).getByText(reforecast.tag_name)).toBeTruthy()
    expect(requestsTo(answered, 'POST', `${DOC}/tags`).map((request) => request.body)).toEqual([
      { dimension: 'Topic', tag_name: 'Budget Reforecast' },
    ])
    fireEvent.change(chooser().getByLabelText(TEXT.tagDimensionLabel), { target: { value: 'Topic' } })
    expect(offeredNames(chooser().getByLabelText(TEXT.tagChooseLabel))).toEqual([BUDGET.tag_name, reforecast.tag_name])
  })

  it('refuses an empty name, and one longer than TAG_NAME_MAXIMUM_LENGTH once single-spaced, beside the field and before any request', async () => {
    const answered = await renderDetail(detailOf({ classification: classificationOf(), tag_options: optionsOf() }), {
      [`POST ${DOC}/tags`]: { status: 201, body: { tag_details: [] } },
    })
    const field = () => topicForm().getByLabelText(TEXT.tagNewTopicLabel)
    const add = () => topicForm().getByRole('button', { name: TEXT.tagNewTopicAdd })
    const posts = () => requestsTo(answered, 'POST', `${DOC}/tags`)

    fireEvent.change(field(), { target: { value: '  \t ' } })
    press(add())
    await waitFor(() => expect(document.activeElement).toBe(field()))
    expect(field().getAttribute('aria-invalid')).toBe('true')
    expect(descriptionOf(field())).toContain(VALIDATION.tagNameRequired)

    fireEvent.change(field(), { target: { value: 'x'.repeat(TAG_NAME_MAXIMUM_LENGTH + 1) } })
    press(add())
    await waitFor(() => expect(descriptionOf(field())).toContain(VALIDATION.tagNameTooLong))
    expect(field().getAttribute('aria-invalid')).toBe('true')
    expect(posts()).toEqual([])

    // The bound as the name is sent: inclusive, after single-spacing, and in characters
    // rather than UTF-16 units, as the server's len() counts.
    const accepted = [
      'x'.repeat(TAG_NAME_MAXIMUM_LENGTH),
      `a${' '.repeat(TAG_NAME_MAXIMUM_LENGTH)}b`,
      '😀'.repeat(TAG_NAME_MAXIMUM_LENGTH),
    ]
    for (const [index, typed] of accepted.entries()) {
      fireEvent.change(field(), { target: { value: typed } })
      press(add())
      await waitFor(() => expect(posts()).toHaveLength(index + 1))
      await waitFor(() => expect(field().value).toBe(''))
    }
    expect(posts().map((request) => request.body.tag_name)).toEqual([
      'x'.repeat(TAG_NAME_MAXIMUM_LENGTH),
      'a b',
      '😀'.repeat(TAG_NAME_MAXIMUM_LENGTH),
    ])
  })

  it('on a 409 shows its sentence and selects the Topic it names in the chooser, with focus on its Add, so one press applies it', async () => {
    let posts = 0
    const answered = await renderDetail(
      detailOf({ classification: classificationOf(), tag_details: [], tag_options: optionsOf() }),
      {
        [`POST ${DOC}/tags`]: () => {
          posts += 1
          return posts === 1
            ? { status: 409, body: { detail: TOPIC_ALREADY_OFFERED_MESSAGE, tag_id: BUDGET.tag_id } }
            : { status: 201, body: { tag_details: [personLink('ct-budget', 'Topic', BUDGET.tag_name)] } }
        },
      },
    )

    fireEvent.change(topicForm().getByLabelText(TEXT.tagNewTopicLabel), { target: { value: 'Budget Planning' } })
    press(topicForm().getByRole('button', { name: TEXT.tagNewTopicAdd }))

    const add = await chooser().findByRole('button', { name: TEXT.tagAddLabel(BUDGET.tag_name) })
    await waitFor(() => expect(document.activeElement).toBe(add))
    expect(chooser().getByLabelText(TEXT.tagDimensionLabel).value).toBe('Topic')
    expect(chooser().getByLabelText(TEXT.tagChooseLabel).value).toBe(BUDGET.tag_id)
    expect(within(addSection()).getByRole('status').textContent).toBe(
      `${TEXT.tagAlreadyOffered} ${TEXT.tagAlreadyOfferedSelected}`,
    )
    // Nothing was added, nothing failed, and the options held had the tag: no second read.
    expect(within(tagGroup(TEXT.documentFieldTopic)).queryByText(BUDGET.tag_name)).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(requestsTo(answered, 'GET', DOC)).toHaveLength(1)

    fireEvent.click(add)

    await waitFor(() => expect(announcement()).toBe(TEXT.tagApplied(BUDGET.tag_name)))
    expect(within(tagGroup(TEXT.documentFieldTopic)).getByText(BUDGET.tag_name)).toBeTruthy()
    expect(within(addSection()).queryByRole('status')).toBeNull()
    expect(requestsTo(answered, 'POST', `${DOC}/tags`).map((request) => request.body)).toEqual([
      { dimension: 'Topic', tag_name: 'Budget Planning' },
      { tag_id: BUDGET.tag_id },
    ])
  })

  it('on a 409 naming a tag the options held here lack, reads them again first and then selects it, showing the client’s sentence and never the body’s', async () => {
    const before = detailOf({ classification: classificationOf(), tag_details: [], tag_options: optionsOf() })
    const wellbeing = { tag_id: 'tag-wellbeing', tag_name: 'wellbeing' }
    const after = { ...before, tag_options: optionsOf({ Topic: [BUDGET, wellbeing] }) }
    const backendText = 'IntegrityError: duplicate key value violates unique constraint "tags_unique_name_per_dimension"'
    const answered = await renderDetail(before, {
      [`GET ${DOC}`]: detailReads(before, after),
      [`POST ${DOC}/tags`]: { status: 409, body: { detail: backendText, tag_id: wellbeing.tag_id } },
    })

    fireEvent.change(topicForm().getByLabelText(TEXT.tagNewTopicLabel), { target: { value: 'Wellbeing' } })
    press(topicForm().getByRole('button', { name: TEXT.tagNewTopicAdd }))

    const add = await chooser().findByRole('button', { name: TEXT.tagAddLabel(wellbeing.tag_name) })
    await waitFor(() => expect(document.activeElement).toBe(add))
    expect(chooser().getByLabelText(TEXT.tagChooseLabel).value).toBe(wellbeing.tag_id)
    expect(requestsTo(answered, 'GET', DOC)).toHaveLength(2)
    expect(within(addSection()).getByRole('status').textContent).toContain(TEXT.tagAlreadyOffered)
    expect(document.body.textContent).not.toContain(backendText)
  })

  it.each([
    {
      field: 'tag_id',
      form: 'the chooser',
      message: "Choose a tag from this document's tag options.",
      control: () => chooser().getByLabelText(TEXT.tagChooseLabel),
      submit: () => press(chooser().getByRole('button', { name: TEXT.tagAddLabel(BRIDGE.tag_name) })),
    },
    {
      field: 'tag_name',
      form: 'the new topic',
      message: 'Ensure this field has no more than 255 characters.',
      control: () => topicForm().getByLabelText(TEXT.tagNewTopicLabel),
      submit: () => {
        fireEvent.change(topicForm().getByLabelText(TEXT.tagNewTopicLabel), { target: { value: 'site safety' } })
        press(topicForm().getByRole('button', { name: TEXT.tagNewTopicAdd }))
      },
    },
  ])('places a 400 on $field beside its field in $form, and moves focus to it', async ({ field, message, control, submit }) => {
    await renderDetail(detailOf({ classification: classificationOf(), tag_options: optionsOf() }), {
      [`POST ${DOC}/tags`]: { status: 400, body: { [field]: [message] } },
    })

    submit()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.classificationCheckFields)
    await waitFor(() => expect(document.activeElement).toBe(control()))
    expect(control().getAttribute('aria-invalid')).toBe('true')
    expect(descriptionOf(control())).toContain(message)
    expect(announcement()).toBe('')
  })

  it('says a dimension offers nothing rather than showing an empty list, and offers no Add there', async () => {
    await renderDetail(
      detailOf({ classification: classificationOf(), tag_options: { Project: [], Process: [PURCHASING], Topic: [] } }),
    )

    expect(chooser().getByText(TEXT.tagChooseNone(TEXT.documentFieldProject))).toBeTruthy()
    expect(chooser().queryByLabelText(TEXT.tagChooseLabel)).toBeNull()
    expect(chooser().queryByRole('button')).toBeNull()
    fireEvent.change(chooser().getByLabelText(TEXT.tagDimensionLabel), { target: { value: 'Process' } })
    expect(chooser().getByRole('button', { name: TEXT.tagAddLabel(PURCHASING.tag_name) })).toBeTruthy()
    // A new topic can still be typed.
    expect(topicForm().getByRole('button', { name: TEXT.tagNewTopicAdd })).toBeTruthy()
  })

  it('renders an offered tag’s name as text, never as HTML', async () => {
    const hostile = '<img src="x" onerror="window.__fr10OptionInjected = true"><b>bridge</b>'
    await renderDetail(
      detailOf({
        classification: classificationOf(),
        tag_options: optionsOf({ Project: [{ tag_id: 'tag-hostile', tag_name: hostile }] }),
      }),
    )

    expect(chooser().getByLabelText(TEXT.tagChooseLabel).options[0].textContent).toBe(hostile)
    expect(chooser().getByRole('button', { name: TEXT.tagAddLabel(hostile) })).toBeTruthy()
    expect(document.querySelectorAll('img, b')).toHaveLength(0)
    expect(window.__fr10OptionInjected).toBeUndefined()
  })
})

describe('FR-10: the add control’s refusals', () => {
  it('is offered on a document never classified, and goes with every other control on a 403', async () => {
    const backendText = "Your role does not hold the 'contribute_content' permission."
    await renderDetail(detailOf({ tag_options: optionsOf() }), {
      [`POST ${DOC}/tags`]: { status: 403, body: { detail: backendText } },
    })
    expect(screen.getByText(TEXT.classificationNone)).toBeTruthy()
    expect(addSection()).toBeTruthy()

    press(chooser().getByRole('button', { name: TEXT.tagAddLabel(BRIDGE.tag_name) }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.classificationNotPermitted)
    expect(document.body.textContent).not.toContain(backendText)
    expect(addSection()).toBeNull()
    expect(screen.queryByLabelText(TEXT.tagNewTopicLabel)).toBeNull()
    expect(within(section()).queryAllByRole('button')).toEqual([])
  })

  it.each([
    {
      failure: 'a 404',
      route: { status: 404, body: { detail: 'No Document matches the given query.' } },
      text: TEXT.documentRecordNotFound,
    },
    {
      failure: 'a network failure',
      route: () => {
        throw new TypeError('Failed to fetch')
      },
      text: messageForStatus(NETWORK_ERROR_STATUS),
    },
  ])('answers $failure with the panel’s own failure notice, adds nothing and keeps the controls', async ({ route, text }) => {
    await renderDetail(detailOf({ classification: classificationOf(), tag_options: optionsOf() }), {
      [`POST ${DOC}/tags`]: route,
    })

    fireEvent.change(topicForm().getByLabelText(TEXT.tagNewTopicLabel), { target: { value: 'site safety' } })
    press(topicForm().getByRole('button', { name: TEXT.tagNewTopicAdd }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.classificationFailed)
    expect(alert.textContent).toContain(text)
    expect(document.body.textContent).not.toContain('No Document matches')
    expect(within(tagGroup(TEXT.documentFieldTopic)).queryByText('site safety')).toBeNull()
    // What was typed stays, so the attempt can be made again.
    expect(topicForm().getByLabelText(TEXT.tagNewTopicLabel).value).toBe('site safety')
    expect(addSection()).toBeTruthy()
  })
})

describe('FR-10’s 409 sentence', () => {
  it('is word for word the server’s TOPIC_ALREADY_OFFERED_MESSAGE (apps/api/views.py)', () => {
    expect(TEXT.tagAlreadyOffered).toBe(TOPIC_ALREADY_OFFERED_MESSAGE)
  })
})
