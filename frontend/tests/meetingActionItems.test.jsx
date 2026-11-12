/**
 * FR-16's "Action Items" panel on the meeting page (NIT3004, D-125), rendered
 * against a faked `GET /api/meetings/{id}/summary`, `GET /api/users/directory` and
 * the three action-item writes (docs/api-contract.md, "NIT3004 — FR-16 meeting
 * summary and action items").
 *
 * FR-16 Front-End: "An "Action Items" panel lists each extracted item with
 * description, suggested owner and due date, all editable. Users can edit, delete
 * or manually add items the extraction missed; deletion requires confirmation."
 *
 * Each test defends one clause only the interface can satisfy: what a row shows,
 * what a form sends, that a delete waits for its confirmation, and which controls
 * are on the page for whom. How an owner is matched, how a phrase becomes a date,
 * what a Regenerate keeps, who may write and the scoped 404 are the server's and
 * are tested in pytest; nothing here stands in for them. The Summary panel is
 * tests/meetingSummary.test.jsx's, and NFR-15's mark is tests/aiGeneratedMark.test.jsx's.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { NETWORK_ERROR_STATUS, messageForStatus } from '../src/api/client.js'
import { ACTION_ITEM_ORIGIN, ROLES, TEXT, VALIDATION } from '../src/constants.js'
import MeetingDetail from '../src/pages/MeetingDetail.jsx'
import { formatDate } from '../src/utils/dates.js'
import { actionItem, readySummary, serveApi, summaryRoute, summaryState } from './fakeApi.js'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

const MEETING = {
  meeting_id: 'meeting-1',
  title: 'First-quarter review',
  meeting_date: '2026-11-03',
  status: 'Indexed',
  created_at: '2026-11-03T16:00:00+11:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: ['ravi@example.com'],
  transcript_text: 'Ravi: Thanks, everyone. This is the first-quarter review.\nSam: Travel came in at twice its budget.',
  can_delete: false,
}

const DETAIL = `/api/meetings/${MEETING.meeting_id}`
const SUMMARY = `${DETAIL}/summary`
const ITEMS = `${DETAIL}/action-items`
const DIRECTORY_ROUTE = '/api/users/directory'

/** Extracted, with an owner the server matched and a date it worked out. The contract's example. */
const RECONCILE = actionItem()

/** Extracted, with nobody matched and a phrase that fixes no date. */
const BOOK_ROOM = actionItem({
  action_item_id: 'item-2',
  description: 'Book the larger room for the planning day',
  owner: null,
  owner_name: 'the facilities team',
  due_date: null,
  due_text: 'before the move',
  passages: [1],
})

/** Extracted, then changed by a person. */
const SEND_POLICY = actionItem({
  action_item_id: 'item-3',
  description: 'Send the revised travel policy to all staff',
  owner: { id: 'user-sam', name: 'Sam Lee' },
  owner_name: 'Sam',
  due_date: '2026-11-20',
  due_text: '',
  passages: [2],
  edited: true,
})

/** Added by a person: no words from the transcript, and no passages. */
const MINUTES = actionItem({
  action_item_id: 'item-4',
  description: 'Circulate the minutes',
  owner: null,
  owner_name: '',
  due_date: null,
  due_text: '',
  passages: [],
  origin: 'user',
})

/** The directory any session may read: a name and an address, no role (D-34). */
const ALEX = { id: 'user-alex', name: 'Alex Morgan', email: 'alex@example.com' }
const SAM = { id: 'user-sam', name: 'Sam Lee', email: 'sam@example.com' }
const DIRECTORY = [ALEX, SAM]

/** A person as the owner select names them. */
function personLabel(person) {
  return `${person.name} (${person.email})`
}

/** A Ready summary's state holding `items`, read by a role that may write. */
function stateWith(items, overrides = {}) {
  return summaryState({
    status: 'Ready',
    summary: readySummary({ action_items_extracted: items.filter((item) => item.origin === 'ai').length }),
    action_items: items,
    can_edit: true,
    ...overrides,
  })
}

/** What DRF sends with each refusal. The screen must never show it. */
const SERVER_403 = { detail: 'You do not have permission to perform this action.' }
const SERVER_404 = { detail: 'No Meeting matches the given query.' }

/* ---- Rendering ----------------------------------------------------------- */

/** The meeting page against `state`, and the Action Items panel once the state has arrived. */
async function pageWith(state, extraRoutes = {}) {
  const answered = serveApi({
    [`GET ${DETAIL}`]: { body: MEETING },
    [`GET ${SUMMARY}`]: summaryRoute(state),
    [`GET ${DIRECTORY_ROUTE}`]: { body: DIRECTORY },
    ...extraRoutes,
  })
  render(
    <MemoryRouter initialEntries={[`/meetings/${MEETING.meeting_id}`]}>
      <Routes>
        <Route path="/meetings/:meetingId" element={<MeetingDetail />} />
      </Routes>
    </MemoryRouter>,
  )
  const panel = await screen.findByRole('region', { name: TEXT.actionItemsHeading })
  await waitFor(() => expect(within(panel).queryByText(TEXT.loadingActionItems)).toBeNull())
  return { answered, panel }
}

/** One item's row. */
function rowOf(panel, item) {
  return within(panel).getByText(item.description).closest('li')
}

/** Every row's description, in the order the panel shows them. */
function descriptions(panel) {
  return Array.from(panel.querySelectorAll('.action-item__description'), (element) =>
    // The description is the paragraph's own text; its passage markers follow it.
    Array.from(element.childNodes)
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.textContent)
      .join('')
      .trim(),
  )
}

/** One fact of a row, by its term: the value, and what the meeting said, as two strings. */
function fact(row, term) {
  const dt = Array.from(row.querySelectorAll('dt')).find((element) => element.textContent === term)
  const dd = dt.nextElementSibling
  return {
    value: dd.querySelector('.action-item__value').textContent,
    said: dd.querySelector('.action-item__said')?.textContent ?? '',
  }
}

/** The requests sent to one route, in order. */
function requestsTo(answered, method, path) {
  return answered.filter((request) => request.method === method && request.path === path)
}

/** Every write the panel sent, whatever it was. */
function writes(answered) {
  return answered.filter((request) => request.method !== 'GET')
}

/** The live region that says what the last action did. */
function announcement(panel) {
  return panel.querySelector('.action-items__announcement').textContent
}

/** A click as a browser makes one: the button takes focus, then is clicked. */
function press(element) {
  element.focus()
  fireEvent.click(element)
}

/** Opens an item's edit form and waits for the owner's choices, which arrive with the directory. */
async function editing(panel, item) {
  const row = rowOf(panel, item)
  press(within(row).getByRole('button', { name: TEXT.actionItemEditLabel(item.description) }))
  await within(row).findByRole('option', { name: personLabel(SAM) })
  return row
}

/** The three fields of an open form. */
function fields(container) {
  return {
    description: within(container).getByLabelText(TEXT.actionItemDescription),
    owner: within(container).getByLabelText(TEXT.actionItemOwner),
    due: within(container).getByLabelText(TEXT.actionItemDue),
  }
}

/** Opens the add form and waits for the owner's choices. */
async function adding(panel) {
  press(within(panel).getByRole('button', { name: TEXT.actionItemAdd }))
  const form = within(panel).getByRole('form', { name: TEXT.actionItemAddLegend })
  await within(form).findByRole('option', { name: personLabel(SAM) })
  return form
}

/* ---- The vocabulary ------------------------------------------------------- */

describe('FR-16: the origins the panel reads are the ones the server defines', () => {
  it('names "ai" and "user", and no others', () => {
    const source = readFileSync(join(import.meta.dirname, '..', '..', 'apps', 'core', 'constants.py'), 'utf8')
    const match = source.match(/^ACTION_ITEM_ORIGINS = \(([^)]*)\)\s*$/m)
    expect(match, 'ACTION_ITEM_ORIGINS not found in apps/core/constants.py').toBeTruthy()
    const serverValues = [...match[1].matchAll(/"([^"\r\n]+)"/g)].map((literal) => literal[1])
    expect(Object.values(ACTION_ITEM_ORIGIN)).toEqual(serverValues)
  })
})

/* ---- The list ------------------------------------------------------------- */

describe('FR-16: the panel lists each item with its description, owner and due date', () => {
  it('shows each item’s description, its owner and its due date, in the server’s order', async () => {
    const { panel } = await pageWith(stateWith([RECONCILE, BOOK_ROOM, SEND_POLICY, MINUTES]))

    expect(within(panel).getByRole('heading', { level: 2 }).textContent).toBe('Action Items')
    expect(descriptions(panel)).toEqual([
      RECONCILE.description,
      BOOK_ROOM.description,
      SEND_POLICY.description,
      MINUTES.description,
    ])

    const row = rowOf(panel, RECONCILE)
    expect(fact(row, TEXT.actionItemOwner).value).toBe('Alex Morgan')
    const due = row.querySelector('time')
    expect(due.getAttribute('dateTime')).toBe('2026-10-23')
    expect(due.textContent).toBe(formatDate('2026-10-23'))
    expect(fact(row, TEXT.actionItemDue).value).toBe(formatDate('2026-10-23'))
    expect(fact(row, TEXT.actionItemDue).value).not.toBe('')
  })

  it('shows what the meeting itself said of the owner and of the deadline, beside what was recorded', async () => {
    const { panel } = await pageWith(stateWith([RECONCILE]))
    const row = rowOf(panel, RECONCILE)

    expect(fact(row, TEXT.actionItemOwner).said).toBe('Named in the meeting: “Alex”')
    expect(fact(row, TEXT.actionItemDue).said).toBe('Said in the meeting: “next Friday”')
  })

  it('reads "Unassigned" where nobody was matched, with the meeting’s own name for the owner, and that no date is set beside the phrase that fixed none', async () => {
    const { panel } = await pageWith(stateWith([BOOK_ROOM]))
    const row = rowOf(panel, BOOK_ROOM)

    // FR-16: "stored as unassigned rather than attributed to the wrong person".
    expect(fact(row, TEXT.actionItemOwner)).toEqual({
      value: 'Unassigned',
      said: 'Named in the meeting: “the facilities team”',
    })
    // A date is never invented: none is shown, and the phrase is.
    expect(fact(row, TEXT.actionItemDue)).toEqual({
      value: TEXT.actionItemNoDate,
      said: 'Said in the meeting: “before the move”',
    })
    expect(row.querySelector('time')).toBeNull()
  })

  it('says nothing of what the meeting said on an item a person added', async () => {
    const { panel } = await pageWith(stateWith([MINUTES]))
    const row = rowOf(panel, MINUTES)

    expect(fact(row, TEXT.actionItemOwner)).toEqual({ value: 'Unassigned', said: '' })
    expect(fact(row, TEXT.actionItemDue)).toEqual({ value: TEXT.actionItemNoDate, said: '' })
    expect(row.textContent).not.toMatch(/in the meeting/)
  })

  it('renders a description and the meeting’s words as text, never as HTML', async () => {
    const hostile = '<img src="x" onerror="window.__fr16ItemInjected = true"><b>Book</b>'
    const { panel } = await pageWith(
      stateWith([actionItem({ description: hostile, owner: null, owner_name: hostile, due_date: null, due_text: hostile })]),
    )

    expect(descriptions(panel)).toEqual([hostile])
    expect(panel.textContent).toContain(TEXT.actionItemOwnerSaid(hostile))
    expect(panel.textContent).toContain(TEXT.actionItemDueSaid(hostile))
    expect(document.querySelectorAll('img, b')).toHaveLength(0)
    expect(window.__fr16ItemInjected).toBeUndefined()
  })
})

/* ---- Passage references --------------------------------------------------- */

describe('UC-04: an extracted item shows the passage it came from', () => {
  it('opens the transcript passage an item names, with the text the summary carries for it', async () => {
    const { panel } = await pageWith(stateWith([RECONCILE]))
    const row = rowOf(panel, RECONCILE)
    const reference = within(row).getByRole('button', { name: TEXT.transcriptPassage(2) })

    expect(reference.getAttribute('aria-expanded')).toBe('false')
    press(reference)

    expect(reference.getAttribute('aria-expanded')).toBe('true')
    expect(within(row).getByRole('region', { name: TEXT.transcriptPassage(2) }).textContent).toBe(
      readySummary().passages[2],
    )
    // Every number has its text here, so nothing needs explaining.
    expect(panel.textContent).not.toContain(TEXT.passageNumberOnly)
  })

  it('shows the number alone, not a button that opens nothing, for a passage the current summary does not quote, and says why once', async () => {
    // After a Regenerate a kept item still names the transcript's passages, and
    // the new summary's `passages` holds only the ones it cites itself.
    const state = stateWith([RECONCILE, SEND_POLICY])
    state.summary.passages = { 1: readySummary().passages[1] }
    const { panel } = await pageWith(state)

    for (const item of [RECONCILE, SEND_POLICY]) {
      const row = rowOf(panel, item)
      expect(within(row).queryByRole('button', { name: TEXT.transcriptPassage(2) })).toBeNull()
      const number = within(row).getByText('[2]')
      expect(number.closest('button')).toBeNull()
      // Still named for a screen reader, as the citation's plain number is.
      expect(number.parentElement.textContent).toBe(`[2]${TEXT.transcriptPassage(2)}`)
      expect(within(row).queryByRole('region')).toBeNull()
    }
    expect(within(panel).getAllByText(TEXT.passageNumberOnly)).toHaveLength(1)
  })

  it('shows no reference on an item a person added', async () => {
    const { panel } = await pageWith(stateWith([MINUTES]))
    const row = rowOf(panel, MINUTES)

    expect(row.querySelector('.citation')).toBeNull()
    expect(panel.textContent).not.toContain(TEXT.passageNumberOnly)
  })
})

/* ---- Editing -------------------------------------------------------------- */

describe('FR-16: description, owner and due date are all editable', () => {
  it('turns an item into a form holding its description, its owner and its due date, on its first field', async () => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE, BOOK_ROOM]))
    // The people are not read until a form needs them.
    expect(requestsTo(answered, 'GET', DIRECTORY_ROUTE)).toEqual([])

    const row = await editing(panel, RECONCILE)

    const form = within(row).getByRole('form', { name: TEXT.actionItemEditLegend })
    const { description, owner, due } = fields(form)
    expect(description.value).toBe(RECONCILE.description)
    expect(description.required).toBe(true)
    await waitFor(() => expect(document.activeElement).toBe(description))
    // A native select of the directory's people, with "Unassigned".
    expect(owner.tagName).toBe('SELECT')
    expect(Array.from(owner.options, (option) => option.textContent)).toEqual([
      'Unassigned',
      personLabel(ALEX),
      personLabel(SAM),
    ])
    expect(owner.value).toBe(ALEX.id)
    // A native date input.
    expect(due.getAttribute('type')).toBe('date')
    expect(due.value).toBe('2026-10-23')
    // What the meeting said stays in view while its record is changed.
    expect(form.textContent).toContain(TEXT.actionItemOwnerSaid('Alex'))
    expect(form.textContent).toContain(TEXT.actionItemDueSaid('next Friday'))

    expect(requestsTo(answered, 'GET', DIRECTORY_ROUTE)).toHaveLength(1)
    // Opening a form sends no write, and the other row is as it was.
    expect(writes(answered)).toEqual([])
    expect(within(rowOf(panel, BOOK_ROOM)).queryByRole('form')).toBeNull()
  })

  it.each([
    ['the description alone', (f) => fireEvent.change(f.description, { target: { value: 'Reconcile the October card statements' } }), { description: 'Reconcile the October card statements' }],
    ['null for an owner cleared', (f) => fireEvent.change(f.owner, { target: { value: '' } }), { owner_id: null }],
    ['the new owner’s id', (f) => fireEvent.change(f.owner, { target: { value: SAM.id } }), { owner_id: SAM.id }],
    ['null for a date cleared', (f) => fireEvent.change(f.due, { target: { value: '' } }), { due_date: null }],
    ['the new date', (f) => fireEvent.change(f.due, { target: { value: '2026-10-30' } }), { due_date: '2026-10-30' }],
    [
      'all three when all three changed',
      (f) => {
        fireEvent.change(f.description, { target: { value: '  Reconcile both card statements  ' } })
        fireEvent.change(f.owner, { target: { value: '' } })
        fireEvent.change(f.due, { target: { value: '' } })
      },
      // The description as it will be stored: the server trims it, and so does the form.
      { description: 'Reconcile both card statements', owner_id: null, due_date: null },
    ],
  ])('sends a PATCH with only what changed: %s', async (_case, change, body) => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE]), {
      [`PATCH ${ITEMS}/${RECONCILE.action_item_id}`]: { body: { ...RECONCILE, edited: true } },
    })
    const row = await editing(panel, RECONCILE)

    change(fields(row))
    fireEvent.click(within(row).getByRole('button', { name: TEXT.actionItemSave }))

    await waitFor(() => expect(announcement(panel)).toBe(TEXT.actionItemSaved))
    expect(writes(answered)).toEqual([
      { method: 'PATCH', path: `${ITEMS}/${RECONCILE.action_item_id}`, search: '', body },
    ])
  })

  it('replaces the item with the one the reply carries, closes the form, and returns focus to its Edit', async () => {
    const saved = {
      ...RECONCILE,
      description: 'Reconcile the October card statements',
      owner: { id: SAM.id, name: SAM.name },
      due_date: '2026-10-30',
      edited: true,
    }
    const { panel, answered } = await pageWith(stateWith([RECONCILE, BOOK_ROOM]), {
      [`PATCH ${ITEMS}/${RECONCILE.action_item_id}`]: { body: saved },
    })
    const row = await editing(panel, RECONCILE)
    const save = within(row).getByRole('button', { name: TEXT.actionItemSave })
    fireEvent.change(fields(row).description, { target: { value: saved.description } })

    // Pressed twice inside one act, so the second lands before the busy state has
    // rendered. Still one request.
    save.focus()
    act(() => {
      save.click()
      save.click()
    })

    await waitFor(() => expect(announcement(panel)).toBe(TEXT.actionItemSaved))
    expect(requestsTo(answered, 'PATCH', `${ITEMS}/${RECONCILE.action_item_id}`)).toHaveLength(1)
    // The row is the reply's item, every field of it, in the place it had.
    expect(descriptions(panel)).toEqual([saved.description, BOOK_ROOM.description])
    const shown = rowOf(panel, saved)
    expect(within(shown).queryByRole('form')).toBeNull()
    expect(fact(shown, TEXT.actionItemOwner).value).toBe('Sam Lee')
    expect(fact(shown, TEXT.actionItemDue).value).toBe(formatDate('2026-10-30'))
    // The transcript's own words are not the edit's to change, and are still shown.
    expect(fact(shown, TEXT.actionItemOwner).said).toBe(TEXT.actionItemOwnerSaid('Alex'))
    await waitFor(() =>
      expect(document.activeElement).toBe(
        within(shown).getByRole('button', { name: TEXT.actionItemEditLabel(saved.description) }),
      ),
    )
  })

  it('restores the item on Cancel, and sends nothing', async () => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE]))
    const row = await editing(panel, RECONCILE)
    const { description, owner, due } = fields(row)
    fireEvent.change(description, { target: { value: 'Something else entirely' } })
    fireEvent.change(owner, { target: { value: '' } })
    fireEvent.change(due, { target: { value: '' } })

    press(within(row).getByRole('button', { name: TEXT.actionItemCancel }))

    expect(within(row).queryByRole('form')).toBeNull()
    expect(descriptions(panel)).toEqual([RECONCILE.description])
    expect(fact(row, TEXT.actionItemOwner).value).toBe('Alex Morgan')
    expect(fact(row, TEXT.actionItemDue).value).toBe(formatDate('2026-10-23'))
    expect(writes(answered)).toEqual([])
    await waitFor(() =>
      expect(document.activeElement).toBe(
        within(row).getByRole('button', { name: TEXT.actionItemEditLabel(RECONCILE.description) }),
      ),
    )

    // Opened again, the form starts from the item and not from what was abandoned.
    press(within(row).getByRole('button', { name: TEXT.actionItemEditLabel(RECONCILE.description) }))
    expect(fields(row).description.value).toBe(RECONCILE.description)
    expect(fields(row).owner.value).toBe(ALEX.id)
  })

  it('sends nothing when Save is pressed with nothing changed, and says so', async () => {
    // The server answers an empty PATCH 400, and marks nothing; the form does not send one.
    const { panel, answered } = await pageWith(stateWith([RECONCILE]))
    const row = await editing(panel, RECONCILE)

    fireEvent.click(within(row).getByRole('button', { name: TEXT.actionItemSave }))

    await waitFor(() => expect(announcement(panel)).toBe(TEXT.actionItemUnchanged))
    expect(writes(answered)).toEqual([])
    expect(within(row).queryByRole('form')).toBeNull()
    expect(descriptions(panel)).toEqual([RECONCILE.description])
  })

  it('refuses a blank description before sending anything, with the message beside the field', async () => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE]))
    const row = await editing(panel, RECONCILE)
    const { description } = fields(row)

    fireEvent.change(description, { target: { value: '   ' } })
    fireEvent.click(within(row).getByRole('button', { name: TEXT.actionItemSave }))

    expect(within(row).getByText(VALIDATION.actionItemDescriptionRequired)).toBeTruthy()
    expect(description.getAttribute('aria-invalid')).toBe('true')
    expect(document.getElementById(description.getAttribute('aria-describedby')).textContent).toContain(
      VALIDATION.actionItemDescriptionRequired,
    )
    await waitFor(() => expect(document.activeElement).toBe(description))
    expect(writes(answered)).toEqual([])

    // Typing clears the refusal.
    fireEvent.change(description, { target: { value: 'Reconcile' } })
    expect(within(row).queryByText(VALIDATION.actionItemDescriptionRequired)).toBeNull()
  })

  it('shows the server’s 400 messages beside the fields they name, and keeps the form and what was typed', async () => {
    const refusal = {
      description: ['Ensure this field has no more than 1000 characters.'],
      owner_id: ['No user has this id.'],
      due_date: ['Date has wrong format. Use one of these formats instead: YYYY-MM-DD.'],
    }
    const { panel, answered } = await pageWith(stateWith([RECONCILE]), {
      [`PATCH ${ITEMS}/${RECONCILE.action_item_id}`]: { status: 400, body: refusal },
    })
    const row = await editing(panel, RECONCILE)
    fireEvent.change(fields(row).description, { target: { value: 'A much longer description' } })
    fireEvent.change(fields(row).owner, { target: { value: SAM.id } })
    fireEvent.change(fields(row).due, { target: { value: '2026-10-30' } })

    fireEvent.click(within(row).getByRole('button', { name: TEXT.actionItemSave }))

    const alert = await within(panel).findByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.actionItemsFailed}${TEXT.actionItemCheckFields}`)
    const { description, owner, due } = fields(row)
    for (const [field, message] of [
      [description, refusal.description[0]],
      [owner, refusal.owner_id[0]],
      [due, refusal.due_date[0]],
    ]) {
      expect(field.getAttribute('aria-invalid')).toBe('true')
      const described = field.getAttribute('aria-describedby').split(' ').map((id) => document.getElementById(id).textContent)
      expect(described.some((text) => text.includes(message))).toBe(true)
    }
    // Focus goes to the first field refused.
    await waitFor(() => expect(document.activeElement).toBe(description))
    // Nothing was saved: the form is open, with what was typed.
    expect(description.value).toBe('A much longer description')
    expect(owner.value).toBe(SAM.id)
    expect(due.value).toBe('2026-10-30')
    expect(announcement(panel)).toBe('')
    expect(requestsTo(answered, 'PATCH', `${ITEMS}/${RECONCILE.action_item_id}`)).toHaveLength(1)
  })

  it('keeps another row’s unsaved edit when one row is saved', async () => {
    const { panel } = await pageWith(stateWith([RECONCILE, BOOK_ROOM]), {
      [`PATCH ${ITEMS}/${RECONCILE.action_item_id}`]: { body: { ...RECONCILE, description: 'Reconcile both', edited: true } },
    })
    const first = await editing(panel, RECONCILE)
    const second = await editing(panel, BOOK_ROOM)
    fireEvent.change(fields(second).description, { target: { value: 'Book the boardroom instead' } })
    fireEvent.change(fields(first).description, { target: { value: 'Reconcile both' } })

    fireEvent.click(within(first).getByRole('button', { name: TEXT.actionItemSave }))

    await waitFor(() => expect(announcement(panel)).toBe(TEXT.actionItemSaved))
    expect(within(first).queryByRole('form')).toBeNull()
    expect(fields(second).description.value).toBe('Book the boardroom instead')
  })

  it('still saves a description when the list of people could not be read, and says the owner cannot be changed', async () => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE]), {
      [`GET ${DIRECTORY_ROUTE}`]: { status: 500, body: { detail: 'Server Error (500)' } },
      [`PATCH ${ITEMS}/${RECONCILE.action_item_id}`]: { body: { ...RECONCILE, description: 'Reconcile both', edited: true } },
    })
    const row = rowOf(panel, RECONCILE)
    press(within(row).getByRole('button', { name: TEXT.actionItemEditLabel(RECONCILE.description) }))

    expect(await within(row).findByText(TEXT.actionItemOwnerUnavailable, { exact: false })).toBeTruthy()
    // The owner it has is still the one shown, so saving does not unassign it.
    const { description, owner } = fields(row)
    expect(Array.from(owner.options, (option) => option.textContent)).toEqual(['Unassigned', 'Alex Morgan'])
    expect(owner.value).toBe(ALEX.id)
    expect(document.body.textContent).not.toContain('Server Error')

    fireEvent.change(description, { target: { value: 'Reconcile both' } })
    fireEvent.click(within(row).getByRole('button', { name: TEXT.actionItemSave }))

    await waitFor(() => expect(announcement(panel)).toBe(TEXT.actionItemSaved))
    expect(writes(answered)).toEqual([
      { method: 'PATCH', path: `${ITEMS}/${RECONCILE.action_item_id}`, search: '', body: { description: 'Reconcile both' } },
    ])
  })
})

/* ---- Deleting ------------------------------------------------------------- */

describe('FR-16: deletion requires confirmation', () => {
  it('asks first, quoting the item, and sends nothing until it is confirmed; Cancel sends no DELETE', async () => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE, MINUTES]), {
      [`DELETE ${ITEMS}/${RECONCILE.action_item_id}`]: { status: 204 },
    })
    const control = within(rowOf(panel, RECONCILE)).getByRole('button', {
      name: TEXT.actionItemDeleteLabel(RECONCILE.description),
    })

    press(control)

    const dialog = screen.getByRole('dialog', { name: TEXT.actionItemDeleteConfirm })
    expect(dialog.textContent).toContain(`“${RECONCILE.description}”`)
    expect(dialog.textContent).toContain(TEXT.actionItemDeleteBody)
    // Opening the dialogue sends nothing.
    expect(writes(answered)).toEqual([])

    fireEvent.click(within(dialog).getByRole('button', { name: TEXT.actionItemDeleteCancel }))

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(writes(answered)).toEqual([])
    expect(descriptions(panel)).toEqual([RECONCILE.description, MINUTES.description])
    expect(document.activeElement).toBe(control)
  })

  it('sends exactly one DELETE on confirm, and removes the row on its 204', async () => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE, MINUTES]), {
      [`DELETE ${ITEMS}/${RECONCILE.action_item_id}`]: { status: 204 },
    })
    press(within(rowOf(panel, RECONCILE)).getByRole('button', { name: TEXT.actionItemDeleteLabel(RECONCILE.description) }))
    const confirm = within(screen.getByRole('dialog')).getByRole('button', {
      name: TEXT.actionItemDeleteConfirmLabel,
    })

    // Pressed twice inside one act, so the second lands before the busy state has rendered.
    act(() => {
      confirm.click()
      confirm.click()
    })

    await waitFor(() => expect(descriptions(panel)).toEqual([MINUTES.description]))
    expect(writes(answered)).toEqual([
      { method: 'DELETE', path: `${ITEMS}/${RECONCILE.action_item_id}`, search: '', body: undefined },
    ])
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(announcement(panel)).toBe(TEXT.actionItemDeleted)
    // The button that opened the dialogue went with its row: focus goes to the panel's heading.
    await waitFor(() => expect(document.activeElement).toBe(within(panel).getByRole('heading', { level: 2 })))
  })

  it('says an extracted item may be extracted again by a later run, and does not say so of one a person added', async () => {
    const { panel } = await pageWith(stateWith([RECONCILE, MINUTES]))

    press(within(rowOf(panel, RECONCILE)).getByRole('button', { name: TEXT.actionItemDeleteLabel(RECONCILE.description) }))
    expect(screen.getByRole('dialog').textContent).toContain(TEXT.actionItemDeleteAiNote)
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: TEXT.actionItemDeleteCancel }))

    press(within(rowOf(panel, MINUTES)).getByRole('button', { name: TEXT.actionItemDeleteLabel(MINUTES.description) }))
    expect(screen.getByRole('dialog').textContent).toContain(`“${MINUTES.description}”`)
    expect(screen.getByRole('dialog').textContent).not.toContain(TEXT.actionItemDeleteAiNote)
  })
})

/* ---- Adding --------------------------------------------------------------- */

describe('FR-16: a person adds an item the extraction missed', () => {
  it('sends a POST with the description alone when nothing else was chosen, and appends the reply', async () => {
    const created = { ...MINUTES, action_item_id: 'item-9', description: 'Circulate the minutes by Friday' }
    const { panel, answered } = await pageWith(stateWith([RECONCILE]), {
      [`POST ${ITEMS}`]: { status: 201, body: created },
    })
    const form = await adding(panel)
    const { description, owner, due } = fields(form)
    await waitFor(() => expect(document.activeElement).toBe(description))
    expect(description.value).toBe('')
    expect(owner.value).toBe('')
    expect(due.value).toBe('')

    fireEvent.change(description, { target: { value: '  Circulate the minutes by Friday  ' } })
    const submit = within(form).getByRole('button', { name: TEXT.actionItemAdd })
    act(() => {
      submit.click()
      submit.click()
    })

    await waitFor(() => expect(announcement(panel)).toBe(TEXT.actionItemAdded))
    expect(writes(answered)).toEqual([
      { method: 'POST', path: ITEMS, search: '', body: { description: 'Circulate the minutes by Friday' } },
    ])
    // After the items already there, and the form has closed.
    expect(descriptions(panel)).toEqual([RECONCILE.description, created.description])
    expect(within(panel).queryByRole('form')).toBeNull()
    await waitFor(() =>
      expect(document.activeElement).toBe(within(panel).getByRole('button', { name: TEXT.actionItemAdd })),
    )
  })

  it('sends the owner and the due date when they were chosen', async () => {
    const { panel, answered } = await pageWith(stateWith([]), {
      [`POST ${ITEMS}`]: {
        status: 201,
        body: { ...MINUTES, owner: { id: SAM.id, name: SAM.name }, due_date: '2026-11-14' },
      },
    })
    const form = await adding(panel)
    const { description, owner, due } = fields(form)
    fireEvent.change(description, { target: { value: MINUTES.description } })
    fireEvent.change(owner, { target: { value: SAM.id } })
    fireEvent.change(due, { target: { value: '2026-11-14' } })

    fireEvent.click(within(form).getByRole('button', { name: TEXT.actionItemAdd }))

    await waitFor(() => expect(descriptions(panel)).toEqual([MINUTES.description]))
    expect(writes(answered)).toEqual([
      {
        method: 'POST',
        path: ITEMS,
        search: '',
        body: { description: MINUTES.description, owner_id: SAM.id, due_date: '2026-11-14' },
      },
    ])
    expect(fact(rowOf(panel, MINUTES), TEXT.actionItemOwner).value).toBe('Sam Lee')
    // The empty state went with the first item.
    expect(panel.textContent).not.toContain(TEXT.actionItemsNoneRaised)
  })

  it('refuses a blank description, and closes without sending anything on Cancel', async () => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE]))
    const form = await adding(panel)

    fireEvent.click(within(form).getByRole('button', { name: TEXT.actionItemAdd }))
    expect(within(form).getByText(VALIDATION.actionItemDescriptionRequired)).toBeTruthy()
    expect(writes(answered)).toEqual([])

    press(within(form).getByRole('button', { name: TEXT.actionItemCancel }))
    expect(within(panel).queryByRole('form')).toBeNull()
    expect(writes(answered)).toEqual([])
    expect(descriptions(panel)).toEqual([RECONCILE.description])
    await waitFor(() =>
      expect(document.activeElement).toBe(within(panel).getByRole('button', { name: TEXT.actionItemAdd })),
    )
  })

  it('shows the server’s 400 message beside the description, and keeps the form', async () => {
    const refusal = { description: ['Ensure this field has no more than 1000 characters.'] }
    const { panel } = await pageWith(stateWith([]), { [`POST ${ITEMS}`]: { status: 400, body: refusal } })
    const form = await adding(panel)
    fireEvent.change(fields(form).description, { target: { value: 'Too long' } })

    fireEvent.click(within(form).getByRole('button', { name: TEXT.actionItemAdd }))

    expect(await within(form).findByText(refusal.description[0])).toBeTruthy()
    expect(within(panel).getByRole('alert').textContent).toBe(`${TEXT.actionItemsFailed}${TEXT.actionItemCheckFields}`)
    expect(fields(form).description.value).toBe('Too long')
    expect(descriptions(panel)).toEqual([])
  })
})

/* ---- Empty ---------------------------------------------------------------- */

describe('UC-04 A1: an empty action-item section is recorded as empty, not omitted', () => {
  it('says no action items were raised when a Ready summary’s run extracted none', async () => {
    const { panel } = await pageWith(stateWith([]))

    expect(within(panel).getByRole('heading', { level: 2, name: 'Action Items' })).toBeTruthy()
    expect(within(panel).getByText(TEXT.actionItemsNoneRaised)).toBeTruthy()
    expect(TEXT.actionItemsNoneRaised).toMatch(/No action items were raised in this meeting/)
    expect(panel.textContent).not.toContain(TEXT.actionItemsNone)
    expect(within(panel).queryByRole('list')).toBeNull()
    // The extraction can miss one, so adding is still offered.
    expect(within(panel).getByRole('button', { name: TEXT.actionItemAdd })).toBeTruthy()
  })

  it.each([
    ['no summary has been generated', summaryState({ can_edit: true })],
    ['the summary is still being generated', summaryState({ status: 'Unavailable', queued_for_retry: true, can_edit: true })],
    // The run extracted two and both were since deleted: nothing says none were raised.
    ['every extracted item was deleted', summaryState({ status: 'Ready', summary: readySummary({ action_items_extracted: 2 }), can_edit: true })],
  ])('says there are none yet, and not that none were raised, when %s', async (_case, state) => {
    const { panel } = await pageWith(state)

    expect(within(panel).getByText(TEXT.actionItemsNone)).toBeTruthy()
    expect(panel.textContent).not.toContain(TEXT.actionItemsNoneRaised)
  })
})

/* ---- Who is offered the controls ------------------------------------------ */

describe('FR-16: the controls are offered only to a role that may change action items', () => {
  it.each([
    ['false', false],
    ['absent', undefined],
  ])('shows no Edit, Delete or Add when can_edit is %s, and never reads the directory', async (_case, canEdit) => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE, MINUTES], { can_edit: canEdit }))

    // The items are all there to read.
    expect(descriptions(panel)).toEqual([RECONCILE.description, MINUTES.description])
    // The only buttons left are passage references.
    expect(within(panel).queryAllByRole('button').filter((button) => !button.classList.contains('citation'))).toEqual([])
    expect(within(panel).queryByRole('form')).toBeNull()
    // Nor is the Summary panel's button there.
    const summary = screen.getByRole('region', { name: TEXT.summaryHeading })
    expect(within(summary).queryAllByRole('button').filter((button) => !button.classList.contains('citation'))).toEqual([])
    expect(requestsTo(answered, 'GET', DIRECTORY_ROUTE)).toEqual([])
  })

  it.each([
    [
      'an edit',
      { [`PATCH ${ITEMS}/${RECONCILE.action_item_id}`]: { status: 403, body: SERVER_403 } },
      async (panel) => {
        const row = await editing(panel, RECONCILE)
        fireEvent.change(fields(row).description, { target: { value: 'Changed' } })
        press(within(row).getByRole('button', { name: TEXT.actionItemSave }))
      },
    ],
    [
      'a delete',
      { [`DELETE ${ITEMS}/${RECONCILE.action_item_id}`]: { status: 403, body: SERVER_403 } },
      async (panel) => {
        press(within(rowOf(panel, RECONCILE)).getByRole('button', { name: TEXT.actionItemDeleteLabel(RECONCILE.description) }))
        fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: TEXT.actionItemDeleteConfirmLabel }))
      },
    ],
    [
      'an add',
      { [`POST ${ITEMS}`]: { status: 403, body: SERVER_403 } },
      async (panel) => {
        const form = await adding(panel)
        fireEvent.change(fields(form).description, { target: { value: 'One more' } })
        press(within(form).getByRole('button', { name: TEXT.actionItemAdd }))
      },
    ],
  ])('withdraws every control when the server refuses %s with a 403, and says the role may not change action items', async (_case, routes, attempt) => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE, MINUTES]), routes)

    await attempt(panel)

    const alert = await within(panel).findByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.actionItemsFailed}${TEXT.meetingContributionNotPermitted}`)
    expect(TEXT.meetingContributionNotPermitted).toMatch(/may not .*change action items/)
    expect(document.body.textContent).not.toContain(SERVER_403.detail)
    // The role does not hold the permission, whatever the state said: Edit, Delete
    // and Add go, and so does the Summary panel's button, which needs the same one.
    expect(within(panel).queryAllByRole('button').filter((button) => !button.classList.contains('citation'))).toEqual([])
    expect(within(panel).queryByRole('form')).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByRole('button', { name: TEXT.summaryRegenerate })).toBeNull()
    // Nothing was changed, and the items are still there to read.
    expect(descriptions(panel)).toEqual([RECONCILE.description, MINUTES.description])
    expect(writes(answered)).toHaveLength(1)
    // Focus is not left on a control that has gone.
    await waitFor(() => expect(document.activeElement).toBe(within(panel).getByRole('heading', { level: 2 })))
  })
})

/* ---- Failures ------------------------------------------------------------- */

describe('FR-16: a write that fails is said in words, and nothing is shown as changed', () => {
  it('reads the panel again on a 404, and says the item could not be found', async () => {
    // Deleted by someone else, or replaced by a Regenerate, since the panel loaded.
    let gone = false
    const { panel, answered } = await pageWith(stateWith([RECONCILE, MINUTES]), {
      [`GET ${SUMMARY}`]: () => summaryRoute(stateWith(gone ? [MINUTES] : [RECONCILE, MINUTES])),
      [`DELETE ${ITEMS}/${RECONCILE.action_item_id}`]: () => {
        gone = true
        return { status: 404, body: SERVER_404 }
      },
    })

    press(within(rowOf(panel, RECONCILE)).getByRole('button', { name: TEXT.actionItemDeleteLabel(RECONCILE.description) }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: TEXT.actionItemDeleteConfirmLabel }))

    const alert = await within(panel).findByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.actionItemsFailed}${TEXT.actionItemNotFound}`)
    expect(document.body.textContent).not.toContain(SERVER_404.detail)
    // Read again, and the list is the server's.
    await waitFor(() => expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2))
    await waitFor(() => expect(descriptions(panel)).toEqual([MINUTES.description]))
    // Nothing said the role may not write: the controls stay.
    expect(within(panel).getByRole('button', { name: TEXT.actionItemAdd })).toBeTruthy()
  })

  it('reads the panel again when an edit answers 404', async () => {
    const { panel, answered } = await pageWith(stateWith([RECONCILE]), {
      [`PATCH ${ITEMS}/${RECONCILE.action_item_id}`]: { status: 404, body: SERVER_404 },
    })
    const row = await editing(panel, RECONCILE)
    fireEvent.change(fields(row).description, { target: { value: 'Changed' } })

    fireEvent.click(within(row).getByRole('button', { name: TEXT.actionItemSave }))

    expect((await within(panel).findByRole('alert')).textContent).toContain(TEXT.actionItemNotFound)
    await waitFor(() => expect(requestsTo(answered, 'GET', SUMMARY)).toHaveLength(2))
    expect(announcement(panel)).toBe('')
  })

  it('says the server could not be reached when a write never arrives, and keeps the form and what was typed', async () => {
    const { panel } = await pageWith(stateWith([RECONCILE]), {
      [`PATCH ${ITEMS}/${RECONCILE.action_item_id}`]: () => Promise.reject(new TypeError('Failed to fetch')),
    })
    const row = await editing(panel, RECONCILE)
    fireEvent.change(fields(row).description, { target: { value: 'Changed' } })

    fireEvent.click(within(row).getByRole('button', { name: TEXT.actionItemSave }))

    const alert = await within(panel).findByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.actionItemsFailed}${messageForStatus(NETWORK_ERROR_STATUS)}`)
    expect(document.body.textContent).not.toContain('Failed to fetch')
    expect(fields(row).description.value).toBe('Changed')
    expect(announcement(panel)).toBe('')
  })

  it('leaves the row in place when a delete fails, with its controls', async () => {
    const { panel } = await pageWith(stateWith([RECONCILE]), {
      [`DELETE ${ITEMS}/${RECONCILE.action_item_id}`]: { status: 500, body: { detail: 'Server Error (500)' } },
    })
    const control = within(rowOf(panel, RECONCILE)).getByRole('button', {
      name: TEXT.actionItemDeleteLabel(RECONCILE.description),
    })

    press(control)
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: TEXT.actionItemDeleteConfirmLabel }))

    const alert = await within(panel).findByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.actionItemsFailed}Something went wrong. Please try again.`)
    expect(document.body.textContent).not.toContain('Server Error')
    expect(descriptions(panel)).toEqual([RECONCILE.description])
    expect(screen.queryByRole('dialog')).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(control))
  })
})
