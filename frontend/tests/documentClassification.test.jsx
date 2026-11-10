/**
 * FR-10's classification section of the document detail view, rendered against a
 * faked `GET /api/documents/{id}` carrying `classification` and `tag_details`,
 * and the six FR-10 actions (D-104, D-105; docs/api-contract.md).
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
import { messageForStatus } from '../src/api/client.js'
import { TEXT } from '../src/constants.js'
import DocumentDetail from '../src/pages/DocumentDetail.jsx'
import { heldResponse, serveApi } from './fakeApi.js'

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
