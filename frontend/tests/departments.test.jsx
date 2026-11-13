/**
 * FR-10's department list on the Tags page (D-129, the user's decision of 13 November
 * 2026): the clauses only the interface can satisfy.
 *
 * The user decided three things, and the list is where an Administrator meets them: the
 * Tags page's list is the department scheme the classifier reads; the upload field stays
 * free text; and retiring keeps a department on its documents, while a department no
 * document has is deleted. What is defended here is what the section shows, keeps,
 * withholds and sends:
 *
 * - every department in the server's order with its name, its state and how many
 *   documents use it, the name rendered as text, and the three sentences that say what
 *   the list is for;
 * - one action per row, Retire or Delete as the list says the server will do, behind a
 *   confirmation that gives both outcomes, one DELETE per confirmation, and the row then
 *   as the reply says: retired on a 200, gone on a 204 or a 404;
 * - the form that adds a department: what it says before anything is added, what it
 *   sends (its capitals kept), and the 201, the 200 (a retired one brought back), the
 *   409, the 400, the 429 and the 403, each as the page shows it;
 * - a 403, on either list or any action, withdrawing every control on the page;
 * - the empty, loading and failed states, and the keyboard reaching every control;
 * - the section offered to an Administrator only.
 *
 * Usability only, and these tests claim nothing more. Retiring or deleting, the count,
 * the order, whether a name is a duplicate, which departments the classifier is offered,
 * and `manage_tags` on every request are the server's, and pytest's.
 *
 * The whole application is rendered at /admin/tags with the real auth provider and
 * guards, against a faked API (tests/fakeApi.js).
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { messageForStatus } from '../src/api/client.js'
import { DEPARTMENT_NAME_MAXIMUM_LENGTH, ROLES, TEXT, VALIDATION } from '../src/constants.js'
import { heldResponse, serveApi } from './fakeApi.js'
import { tabThrough } from './keyboard.js'
import { hidingCauses } from './stylesheets.js'

const ADMINISTRATOR = {
  id: 'user-administrator',
  name: 'Ada Administrator',
  email: 'ada@example.com',
  role: ROLES.administrator,
  created_at: '2026-09-12T10:00:00+10:00',
}

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

/** One tag, so the tags' own form, table and action are on the page beside the departments. */
const PURCHASING = { tag_id: 'tag-0001', dimension: 'Process', tag_name: 'purchasing', active: true, item_count: 4 }

/* The department entry of the contract: four fields and no others. */

/** Used by no document, so its action is Delete. Lower case, as someone typed it on upload. */
const FACILITIES = { department_id: 'dept-0001', name: 'facilities', active: true, item_count: 0 }
/** Used by twelve documents, so its action is Retire. */
const FINANCE = { department_id: 'dept-0002', name: 'Finance', active: true, item_count: 12 }
const HUMAN_RESOURCES = { department_id: 'dept-0003', name: 'Human Resources', active: true, item_count: 7 }
/** Retired already and still on three documents: Delete, the only change left to it. */
const LEGAL = { department_id: 'dept-0004', name: 'Legal', active: false, item_count: 3 }

/**
 * The contract's order: by name without regard to case. Not an order the screen would
 * reach by sorting on name with case (capitals first would put "facilities" last), or on
 * count, or on state.
 */
const SERVER_ORDER = [FACILITIES, FINANCE, HUMAN_RESOURCES, LEGAL]

function routes(extra = {}) {
  return {
    'GET /api/auth/me': { body: ADMINISTRATOR },
    'GET /api/tags': { body: [PURCHASING] },
    'GET /api/departments': { body: SERVER_ORDER },
    ...extra,
  }
}

/** The router's current location, as the probe below last saw it. */
const probe = { location: null }

function LocationProbe() {
  const location = useLocation()
  // A layout effect, so the location is current before a findBy waiting on the same
  // commit resolves (a passive effect runs a task later).
  useLayoutEffect(() => {
    probe.location = location
  })
  return null
}

function renderTags(path = '/admin/tags') {
  probe.location = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  )
  return probe
}

/** The Departments section, or null while it is not on the page. */
function section() {
  return screen.queryByRole('region', { name: TEXT.departmentsHeading })
}

function sectionShown() {
  return screen.findByRole('region', { name: TEXT.departmentsHeading })
}

function sectionHeading() {
  return screen.getByRole('heading', { level: 2, name: TEXT.departmentsHeading })
}

/** The Departments section once its table shows `department`. */
async function listShown(department = FINANCE) {
  await within(await sectionShown()).findByRole('rowheader', { name: department.name })
}

function departmentTable() {
  return within(section()).getByRole('table', { name: TEXT.departmentsTableCaption })
}

function tagTable() {
  return screen.getByRole('table', { name: TEXT.tagsTableCaption })
}

/** The name of each department row, in document order. */
function namesShown() {
  return within(departmentTable())
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getByRole('rowheader').textContent)
}

/** A row's data cells after its name: state, count, then the action. */
function cellsOf(department) {
  return within(within(section()).getByRole('rowheader', { name: department.name }).closest('tr')).getAllByRole(
    'cell',
  )
}

function retireButton(department) {
  return screen.queryByRole('button', { name: TEXT.departmentRetireLabel(department.name) })
}

function deleteButton(department) {
  return screen.queryByRole('button', { name: TEXT.departmentDeleteLabel(department.name) })
}

function tagDeleteButton() {
  return screen.queryByRole('button', { name: TEXT.tagDeleteLabel(PURCHASING.dimension, PURCHASING.tag_name) })
}

function deletes(answered) {
  return answered.filter((request) => request.method === 'DELETE')
}

function departmentReads(answered) {
  return answered.filter((request) => request.method === 'GET' && request.path === '/api/departments')
}

function tagReads(answered) {
  return answered.filter((request) => request.method === 'GET' && request.path === '/api/tags')
}

function creates(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/departments')
}

/** Presses the row action named `name` as a person does, and returns the dialogue it opens. */
async function openConfirmation(name) {
  const button = await screen.findByRole('button', { name })
  button.focus()
  fireEvent.click(button)
  return screen.findByRole('dialog')
}

function confirmIn(dialog, label) {
  return within(dialog).getByRole('button', { name: label })
}

/** The add-a-department part of the section, or null while it is not offered. */
function createSection() {
  return screen.queryByRole('region', { name: TEXT.departmentCreateHeading })
}

function nameField() {
  return within(createSection()).getByLabelText(TEXT.departmentCreateNameLabel)
}

function addButton() {
  return within(createSection()).getByRole('button', { name: TEXT.departmentCreateAdd })
}

/** Everything that describes a field to assistive technology: its hint, its error and anything else named. */
function descriptionOf(field) {
  return (field.getAttribute('aria-describedby') ?? '')
    .split(' ')
    .map((id) => document.getElementById(id)?.textContent ?? '')
    .join(' ')
}

/** Once the form is offered, types `name` and presses Add department, as a person does. */
async function addDepartment(name) {
  await screen.findByRole('region', { name: TEXT.departmentCreateHeading })
  fireEvent.change(nameField(), { target: { value: name } })
  const add = addButton()
  add.focus()
  fireEvent.click(add)
}

/** `GET /api/departments` answered with `first` once, and with `later` on every read after it. */
function listReadsAnswer(first, later) {
  let reads = 0
  return () => {
    reads += 1
    return reads === 1 ? { body: first } : later
  }
}

describe('D-129: the department list, as the server sent it', () => {
  it('lists every department in the server’s order with its name, its state and how many documents use it, in a section of its own after the tags', async () => {
    const answered = serveApi(routes())
    renderTags()

    await listShown()
    expect(namesShown()).toEqual(SERVER_ORDER.map((department) => department.name))
    expect(within(departmentTable()).getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      TEXT.departmentsColumnName,
      TEXT.departmentsColumnState,
      TEXT.departmentsColumnItems,
      TEXT.departmentsColumnAction,
    ])
    expect(TEXT.departmentsColumnItems).toMatch(/documents/i)
    for (const department of SERVER_ORDER) {
      const [state, count] = cellsOf(department)
      expect(state.textContent).toBe(department.active ? TEXT.departmentStateActive : TEXT.departmentStateRetired)
      expect(count.textContent).toBe(String(department.item_count))
    }
    // After the tags' list, under a heading at the level of theirs.
    const tagsList = screen.getByRole('heading', { level: 2, name: TEXT.tagsListHeading })
    expect(tagsList.compareDocumentPosition(sectionHeading()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // One read of each list, and nothing sent.
    expect(answered.map((request) => `${request.method} ${request.path}`).sort()).toEqual([
      'GET /api/auth/me',
      'GET /api/departments',
      'GET /api/tags',
    ])
  })

  it('offers Retire for an active department documents use, and Delete for one no document uses or one already retired, each named with its department', async () => {
    // A count that did not arrive is read as in use: the outcome that keeps it on documents.
    const operations = { department_id: 'dept-0009', name: 'Operations', active: true }
    serveApi(routes({ 'GET /api/departments': { body: [...SERVER_ORDER, operations] } }))
    renderTags()

    await listShown()
    const offered = [
      [FACILITIES, deleteButton, TEXT.departmentDelete],
      [FINANCE, retireButton, TEXT.departmentRetire],
      [HUMAN_RESOURCES, retireButton, TEXT.departmentRetire],
      [LEGAL, deleteButton, TEXT.departmentDelete],
      [operations, retireButton, TEXT.departmentRetire],
    ]
    for (const [department, button, word] of offered) {
      const [, , action] = cellsOf(department)
      // One action per row, named with the department after the visible word.
      expect(within(action).getAllByRole('button')).toEqual([button(department)])
      expect(button(department).textContent).toBe(word)
    }
    expect(cellsOf(operations)[1].textContent).toBe('—')
  })

  it('renders a department name holding markup as the characters it is, in the table and the confirmation, and creates no element from it', async () => {
    const hostile = '<img src="x" onerror="window.__departmentsInjected = true"><b>Finance</b>'
    serveApi(routes({ 'GET /api/departments': { body: [{ ...FINANCE, name: hostile }] } }))
    renderTags()

    const name = await within(await sectionShown()).findByRole('rowheader', { name: hostile })
    expect(name.textContent).toBe(hostile)
    expect(name.children).toHaveLength(0)
    expect(departmentTable().querySelectorAll('b, img')).toHaveLength(0)

    const dialog = await openConfirmation(TEXT.departmentRetireLabel(hostile))
    expect(within(dialog).getByRole('heading', { name: TEXT.departmentRetireConfirm(hostile) })).toBeTruthy()
    expect(dialog.querySelectorAll('b, img')).toHaveLength(0)
    expect(window.__departmentsInjected).toBeUndefined()
  })

  it('says what the list is for: the AI assigns only listed departments, the upload form accepts any, and a retired one stays on its documents while the AI no longer assigns it', async () => {
    serveApi(routes())
    renderTags()

    const region = within(await sectionShown())
    expect(region.getByRole('heading', { level: 2, name: TEXT.departmentsHeading })).toBeTruthy()
    expect(region.getByText(TEXT.departmentsSuggestNote)).toBeTruthy()
    expect(TEXT.departmentsSuggestNote).toMatch(/AI assigns a department to a document only from this list/)
    expect(region.getByText(TEXT.departmentsUploadNote)).toBeTruthy()
    expect(TEXT.departmentsUploadNote).toMatch(/upload form still accepts any department/)
    expect(region.getByText(TEXT.departmentsRetiredNote)).toBeTruthy()
    expect(TEXT.departmentsRetiredNote).toMatch(/retired department stays on the documents that have it/)
    expect(TEXT.departmentsRetiredNote).toMatch(/AI no longer assigns it/)
  })

  it('says before anything is added that a new department is offered for every document, and that adding a retired one’s name brings it back', async () => {
    serveApi(routes())
    renderTags()

    await sectionShown()
    const create = within(await screen.findByRole('region', { name: TEXT.departmentCreateHeading }))
    expect(within(section()).getByRole('region', { name: TEXT.departmentCreateHeading })).toBeTruthy()
    expect(create.getByRole('heading', { level: 3, name: TEXT.departmentCreateHeading })).toBeTruthy()
    expect(create.getByText(TEXT.departmentCreateScope)).toBeTruthy()
    expect(TEXT.departmentCreateScope).toMatch(/any document, whatever its audience/)
    expect(TEXT.departmentCreateScope).toMatch(/name of a retired department brings it back/)
    expect(nameField().tagName).toBe('INPUT')
    expect(addButton().getAttribute('type')).toBe('submit')
    // Someone who tabs straight to the name hears the scope as well as the hint.
    expect(descriptionOf(nameField())).toContain(TEXT.departmentCreateNameHint)
    expect(descriptionOf(nameField())).toContain(TEXT.departmentCreateScope)
  })
})

describe('D-129: the empty, loading and failed states', () => {
  it('says the list is empty as an ordinary state, and still offers the form', async () => {
    serveApi(routes({ 'GET /api/departments': { body: [] } }))
    renderTags()

    const empty = await within(await sectionShown()).findByText(TEXT.noDepartments)
    expect(empty.closest('[role="status"]')).toBeTruthy()
    expect(within(section()).queryByRole('table')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(createSection()).toBeTruthy()
  })

  it('shows a loading state, then a failed read in fixed words with a retry of its own, offering the form only once the list is read', async () => {
    const held = heldResponse()
    const backendText = 'relation "departments" does not exist'
    let reads = 0
    const answered = serveApi(
      routes({
        'GET /api/departments': () => {
          reads += 1
          return reads === 1 ? held.route() : { body: SERVER_ORDER }
        },
      }),
    )
    renderTags()

    const loadingLine = await within(await sectionShown()).findByText(TEXT.loadingDepartments)
    expect(loadingLine.getAttribute('role')).toBe('status')
    expect(createSection()).toBeNull()
    held.release({ status: 500, body: { detail: backendText } })

    const alert = (await within(section()).findByText(TEXT.departmentsLoadFailed)).closest('[role="alert"]')
    expect(alert.textContent).toContain(messageForStatus(500))
    expect(document.body.textContent).not.toContain(backendText)
    expect(createSection()).toBeNull()
    // A failed read is not a refusal: the tags keep their action.
    await waitFor(() => expect(tagDeleteButton()).toBeTruthy())
    const retry = within(section()).getByRole('button', { name: TEXT.departmentsRetryLabel })
    expect(retry.textContent).toBe(TEXT.uploadRetry)
    fireEvent.click(retry)

    await within(section()).findByRole('rowheader', { name: FINANCE.name })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(departmentReads(answered)).toHaveLength(2)
    expect(tagReads(answered)).toHaveLength(1)
    expect(createSection()).toBeTruthy()
  })
})

describe('D-129: Retire versus Delete — "Retiring keeps the department on its documents"', () => {
  it.each([
    {
      action: 'Retire',
      department: FINANCE,
      label: TEXT.departmentRetireLabel,
      title: TEXT.departmentRetireConfirm,
      body: TEXT.departmentRetireBody,
      confirm: TEXT.departmentRetireConfirmLabel,
      says: [/stays on the documents that have it/, /AI no longer assigns it/, /it is deleted instead/],
    },
    {
      action: 'Delete',
      department: FACILITIES,
      label: TEXT.departmentDeleteLabel,
      title: TEXT.departmentDeleteConfirm,
      body: TEXT.departmentDeleteBody,
      confirm: TEXT.departmentDeleteConfirmLabel,
      says: [/no document has this department, it is deleted/, /kept on those documents as a retired department/],
    },
  ])(
    'asks before $action, saying both outcomes, and Cancel sends nothing and returns focus to the row',
    async ({ department, label, title, body, confirm, says }) => {
      const answered = serveApi(routes())
      renderTags()

      const dialog = await openConfirmation(label(department.name))

      expect(within(dialog).getByRole('heading', { name: title(department.name) })).toBeTruthy()
      expect(within(dialog).getByText(body)).toBeTruthy()
      for (const words of says) expect(body).toMatch(words)
      expect(confirmIn(dialog, confirm)).toBeTruthy()
      fireEvent.click(within(dialog).getByRole('button', { name: TEXT.departmentActionCancel }))

      await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
      await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: label(department.name) })))
      expect(deletes(answered)).toEqual([])
    },
  )

  it('on a 200 shows the row retired, as the reply has it, with a polite notice that it stays on its documents, and focus back on the row', async () => {
    const answered = serveApi(
      routes({ [`DELETE /api/departments/${FINANCE.department_id}`]: { body: { ...FINANCE, active: false } } }),
    )
    renderTags()

    fireEvent.click(
      confirmIn(await openConfirmation(TEXT.departmentRetireLabel(FINANCE.name)), TEXT.departmentRetireConfirmLabel),
    )

    const notice = await within(await sectionShown()).findByText(TEXT.departmentRetired(FINANCE.name))
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(TEXT.departmentRetired(FINANCE.name)).toMatch(/stays on them, and the AI no longer assigns it/)
    expect(cellsOf(FINANCE)[0].textContent).toBe(TEXT.departmentStateRetired)
    // Still listed, where it was. Retired now, so a deletion is what is left to it.
    expect(namesShown()).toEqual(SERVER_ORDER.map((department) => department.name))
    expect(retireButton(FINANCE)).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(deleteButton(FINANCE)))
    expect(deletes(answered).map((request) => request.path)).toEqual([`/api/departments/${FINANCE.department_id}`])
    // Updated from the reply, not by reading the list again.
    expect(departmentReads(answered)).toHaveLength(1)
  })

  it('on a 204 takes the row away with a notice that it was deleted, and puts focus on the Departments heading', async () => {
    const answered = serveApi(routes({ [`DELETE /api/departments/${FACILITIES.department_id}`]: { status: 204 } }))
    renderTags()

    fireEvent.click(
      confirmIn(await openConfirmation(TEXT.departmentDeleteLabel(FACILITIES.name)), TEXT.departmentDeleteConfirmLabel),
    )

    const notice = await screen.findByText(TEXT.departmentDeleted(FACILITIES.name))
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(within(section()).queryByRole('rowheader', { name: FACILITIES.name })).toBeNull()
    expect(namesShown()).toEqual([FINANCE, HUMAN_RESOURCES, LEGAL].map((department) => department.name))
    await waitFor(() => expect(document.activeElement).toBe(sectionHeading()))
    expect(deletes(answered).map((request) => request.path)).toEqual([`/api/departments/${FACILITIES.department_id}`])
  })

  it('on a 404 takes the row away with a notice that the department no longer exists, never in the server’s words', async () => {
    const detail = 'No Department matches the given query.'
    serveApi(routes({ [`DELETE /api/departments/${LEGAL.department_id}`]: { status: 404, body: { detail } } }))
    renderTags()

    fireEvent.click(
      confirmIn(await openConfirmation(TEXT.departmentDeleteLabel(LEGAL.name)), TEXT.departmentDeleteConfirmLabel),
    )

    const notice = await screen.findByText(TEXT.departmentGone(LEGAL.name))
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(namesShown()).toEqual([FACILITIES, FINANCE, HUMAN_RESOURCES].map((department) => department.name))
    expect(document.body.textContent).not.toContain(detail)
    await waitFor(() => expect(document.activeElement).toBe(sectionHeading()))
  })

  it('sends one DELETE for presses made while the first is still in flight, and says it is busy', async () => {
    const held = heldResponse()
    const answered = serveApi(routes({ [`DELETE /api/departments/${FINANCE.department_id}`]: held.route }))
    renderTags()
    const confirm = confirmIn(
      await openConfirmation(TEXT.departmentRetireLabel(FINANCE.name)),
      TEXT.departmentRetireConfirmLabel,
    )

    // A double press whose second lands before React has rendered the first.
    act(() => {
      fireEvent.click(confirm)
      fireEvent.click(confirm)
    })
    await waitFor(() => expect(confirm.getAttribute('aria-busy')).toBe('true'))
    expect(confirm.textContent).toBe(TEXT.departmentRetiring)
    fireEvent.click(confirm)
    expect(deletes(answered)).toHaveLength(1)

    held.release({ body: { ...FINANCE, active: false } })
    expect(await screen.findByText(TEXT.departmentRetired(FINANCE.name))).toBeTruthy()
    expect(deletes(answered)).toHaveLength(1)
  })

  it('says a failed retire failed, in the client’s words and never the server’s, and leaves the row as it was', async () => {
    const backendText = 'Traceback (most recent call last): IntegrityError on "departments"'
    serveApi(
      routes({ [`DELETE /api/departments/${FINANCE.department_id}`]: { status: 500, body: { detail: backendText } } }),
    )
    renderTags()

    fireEvent.click(
      confirmIn(await openConfirmation(TEXT.departmentRetireLabel(FINANCE.name)), TEXT.departmentRetireConfirmLabel),
    )

    const alert = (await within(await sectionShown()).findByText(TEXT.departmentRetireFailed)).closest('[role="alert"]')
    expect(alert.textContent).toContain(messageForStatus(500))
    expect(document.body.textContent).not.toContain(backendText)
    expect(cellsOf(FINANCE)[0].textContent).toBe(TEXT.departmentStateActive)
    expect(retireButton(FINANCE)).toBeTruthy()
  })
})

/* ---- Adding a department ------------------------------------------------- */

/**
 * The entry a 201 carries: the name as stored, its capitals kept, active, and the two
 * documents that already had it from the upload form, which takes any department.
 */
const CUSTOMER_SERVICE = { department_id: 'dept-0005', name: 'Customer Service', active: true, item_count: 2 }

/** The server's wording of its 409, which the page never shows. */
const DUPLICATE_DETAIL = 'A department with this name already exists.'

describe('D-129: an Administrator adds a department', () => {
  it('on a 201 reads the list again and shows it in the server’s order, clears the name, and announces the department as stored, politely', async () => {
    const after = [CUSTOMER_SERVICE, ...SERVER_ORDER]
    const answered = serveApi(
      routes({
        'GET /api/departments': listReadsAnswer(SERVER_ORDER, { body: after }),
        'POST /api/departments': { status: 201, body: CUSTOMER_SERVICE },
      }),
    )
    renderTags()

    await addDepartment('  Customer \t  Service ')

    const notice = await within(await sectionShown()).findByText(TEXT.departmentCreated(CUSTOMER_SERVICE.name))
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    await waitFor(() => expect(namesShown()).toEqual(after.map((department) => department.name)))
    expect(cellsOf(CUSTOMER_SERVICE).map((cell) => cell.textContent).slice(0, 2)).toEqual([
      TEXT.departmentStateActive,
      '2',
    ])
    expect(nameField().value).toBe('')
    expect(document.activeElement).toBe(addButton())
    // One request in the contract's form: trimmed and single-spaced, its capitals kept.
    expect(creates(answered).map((request) => request.body)).toEqual([{ name: 'Customer Service' }])
    expect(departmentReads(answered)).toHaveLength(2)
  })

  it('on a 201 whose list cannot be read again places the new department by name without regard to case, and still announces it without a failure', async () => {
    const grounds = { department_id: 'dept-0006', name: 'Grounds', active: true, item_count: 0 }
    serveApi(
      routes({
        'GET /api/departments': listReadsAnswer(SERVER_ORDER, { status: 500, body: { detail: 'database is locked' } }),
        'POST /api/departments': { status: 201, body: grounds },
      }),
    )
    renderTags()

    await addDepartment('Grounds')

    expect(await screen.findByText(TEXT.departmentCreated(grounds.name))).toBeTruthy()
    // After "Finance" and before "Human Resources"; by code point, capitals first, it would lead.
    expect(namesShown()).toEqual(['facilities', 'Finance', 'Grounds', 'Human Resources', 'Legal'])
    expect(screen.queryByRole('alert')).toBeNull()
    expect(document.body.textContent).not.toContain('database is locked')
  })

  it('on a 200 brings a retired department back: the row shows it active, the name clears, and the notice says it was brought back, not added', async () => {
    const back = { ...LEGAL, active: true }
    const answered = serveApi(
      routes({
        'GET /api/departments': listReadsAnswer(SERVER_ORDER, { body: [FACILITIES, FINANCE, HUMAN_RESOURCES, back] }),
        'POST /api/departments': { status: 200, body: back },
      }),
    )
    renderTags()

    await addDepartment('legal')

    const notice = await within(await sectionShown()).findByText(TEXT.departmentReactivated(LEGAL.name))
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(TEXT.departmentReactivated(LEGAL.name)).toMatch(/brought back/)
    expect(screen.queryByText(TEXT.departmentCreated(LEGAL.name))).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(cellsOf(LEGAL)[0].textContent).toBe(TEXT.departmentStateActive)
    expect(namesShown()).toEqual(SERVER_ORDER.map((department) => department.name))
    // Active again with documents, so Retire is what is offered for it now.
    expect(retireButton(LEGAL)).toBeTruthy()
    expect(nameField().value).toBe('')
    expect(creates(answered).map((request) => request.body)).toEqual([{ name: 'legal' }])
    expect(departmentReads(answered)).toHaveLength(2)
  })

  it('on a 200 whose list cannot be read again shows the department active in its own row, from the reply', async () => {
    serveApi(
      routes({
        'GET /api/departments': listReadsAnswer(SERVER_ORDER, { status: 500, body: { detail: 'database is locked' } }),
        'POST /api/departments': { status: 200, body: { ...LEGAL, active: true } },
      }),
    )
    renderTags()

    await addDepartment('Legal')

    expect(await screen.findByText(TEXT.departmentReactivated(LEGAL.name))).toBeTruthy()
    // One row for it, where it was: not a second one beside the retired one.
    expect(namesShown()).toEqual(SERVER_ORDER.map((department) => department.name))
    expect(cellsOf(LEGAL)[0].textContent).toBe(TEXT.departmentStateActive)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('on a 409 names the department already in the list as the list spells it, keeps what was typed, and never shows the reply’s detail', async () => {
    const answered = serveApi(
      routes({
        'POST /api/departments': {
          status: 409,
          body: { detail: DUPLICATE_DETAIL, department_id: HUMAN_RESOURCES.department_id },
        },
      }),
    )
    renderTags()

    await addDepartment('human  resources')

    const notice = await within(await sectionShown()).findByText(TEXT.departmentCreateExists(HUMAN_RESOURCES.name))
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(document.body.textContent).not.toContain(DUPLICATE_DETAIL)
    expect(nameField().value).toBe('human  resources')
    // Nothing was added, and the list, read again, is as it was.
    expect(namesShown()).toEqual(SERVER_ORDER.map((department) => department.name))
    expect(departmentReads(answered)).toHaveLength(2)
    expect(creates(answered).map((request) => request.body)).toEqual([{ name: 'human resources' }])
  })

  it('on a 409 naming a department the list held here lacks, one added since, reads the list again, names it from there and shows its row, as text', async () => {
    // Another Administrator's department, or one seeded from a document: untrusted, rendered as text.
    const added = {
      department_id: 'dept-0007',
      name: '<img src="x" onerror="window.__departmentCreateInjected = true">Grounds',
      active: true,
      item_count: 0,
    }
    const after = [FACILITIES, FINANCE, added, HUMAN_RESOURCES, LEGAL]
    const answered = serveApi(
      routes({
        'GET /api/departments': listReadsAnswer(SERVER_ORDER, { body: after }),
        'POST /api/departments': { status: 409, body: { detail: DUPLICATE_DETAIL, department_id: added.department_id } },
      }),
    )
    renderTags()

    await addDepartment('grounds')

    expect(await screen.findByText(TEXT.departmentCreateExists(added.name))).toBeTruthy()
    expect(namesShown()).toEqual(after.map((department) => department.name))
    expect(document.querySelectorAll('main img')).toHaveLength(0)
    expect(window.__departmentCreateInjected).toBeUndefined()
    expect(departmentReads(answered)).toHaveLength(2)
  })

  it('places a 400 on name beside the field, with focus on it, and adds nothing', async () => {
    const message = 'Ensure this field has no more than 255 characters.'
    const answered = serveApi(routes({ 'POST /api/departments': { status: 400, body: { name: [message] } } }))
    renderTags()

    await addDepartment('Site Safety')

    const alert = await within(await sectionShown()).findByRole('alert')
    expect(alert.textContent).toContain(TEXT.departmentCreateFailed)
    expect(alert.textContent).toContain(TEXT.classificationCheckFields)
    await waitFor(() => expect(document.activeElement).toBe(nameField()))
    expect(nameField().getAttribute('aria-invalid')).toBe('true')
    expect(descriptionOf(nameField())).toContain(message)
    expect(nameField().value).toBe('Site Safety')
    expect(namesShown()).toEqual(SERVER_ORDER.map((department) => department.name))
    // A refusal is not a change: the list is not read again.
    expect(departmentReads(answered)).toHaveLength(1)
  })

  it('refuses an empty name, and one too long once single-spaced, beside the field and before any request', async () => {
    const answered = serveApi(routes({ 'POST /api/departments': { status: 201, body: CUSTOMER_SERVICE } }))
    renderTags()

    await addDepartment('  \t ')
    await waitFor(() => expect(document.activeElement).toBe(nameField()))
    expect(nameField().getAttribute('aria-invalid')).toBe('true')
    expect(descriptionOf(nameField())).toContain(VALIDATION.departmentNameRequired)

    await addDepartment('x'.repeat(DEPARTMENT_NAME_MAXIMUM_LENGTH + 1))
    await waitFor(() => expect(descriptionOf(nameField())).toContain(VALIDATION.departmentNameTooLong))
    expect(nameField().getAttribute('aria-invalid')).toBe('true')
    expect(creates(answered)).toEqual([])

    // Within the limit once single-spaced, so it is sent, single-spaced, capitals kept.
    await addDepartment(`Customer${' '.repeat(DEPARTMENT_NAME_MAXIMUM_LENGTH)}Service`)
    await waitFor(() => expect(creates(answered)).toHaveLength(1))
    expect(creates(answered)[0].body).toEqual({ name: 'Customer Service' })
  })

  it('names the shared tagging limit on a 429, with when to try again, and keeps the name and the form', async () => {
    serveApi(
      routes({
        'POST /api/departments': {
          status: 429,
          body: { detail: 'Request was throttled.' },
          headers: { 'Retry-After': '42' },
        },
      }),
    )
    renderTags()

    await addDepartment('Site Safety')

    const alert = await within(await sectionShown()).findByRole('alert')
    expect(alert.textContent).toContain(TEXT.departmentCreateFailed)
    expect(alert.textContent).toContain(TEXT.departmentLimitReached(TEXT.retryInSeconds(42)))
    expect(TEXT.departmentLimitReached(TEXT.retryLater)).toMatch(/limit on adding tags and departments/)
    expect(document.body.textContent).not.toContain('Request was throttled.')
    expect(nameField().value).toBe('Site Safety')
    expect(addButton()).toBeTruthy()
    expect(namesShown()).toEqual(SERVER_ORDER.map((department) => department.name))
  })

  it('sends one POST for presses made while the first is still in flight, and says it is busy', async () => {
    const held = heldResponse()
    const answered = serveApi(routes({ 'POST /api/departments': held.route }))
    renderTags()
    await screen.findByRole('region', { name: TEXT.departmentCreateHeading })
    fireEvent.change(nameField(), { target: { value: 'Customer Service' } })
    const add = addButton()

    // A double press whose second lands before React has rendered the first.
    act(() => {
      fireEvent.click(add)
      fireEvent.click(add)
    })
    await waitFor(() => expect(add.getAttribute('aria-busy')).toBe('true'))
    expect(add.textContent).toBe(TEXT.departmentAdding)
    fireEvent.click(add)
    expect(creates(answered)).toHaveLength(1)

    held.release({ status: 201, body: CUSTOMER_SERVICE })
    expect(await screen.findByText(TEXT.departmentCreated(CUSTOMER_SERVICE.name))).toBeTruthy()
    expect(creates(answered)).toHaveLength(1)
    expect(add.getAttribute('aria-busy')).toBeNull()
  })
})

describe('D-129: a 403 withdraws every control on the page', () => {
  it('on an add refused with a 403, withdraws every action, the tags’ and the form with them, says why, and puts focus on the Departments heading', async () => {
    const detail = "Your role does not hold the 'manage_tags' permission."
    const answered = serveApi(routes({ 'POST /api/departments': { status: 403, body: { detail } } }))
    renderTags()

    await addDepartment('Site Safety')

    const alert = (await within(await sectionShown()).findByText(TEXT.departmentsNotPermitted)).closest(
      '[role="alert"]',
    )
    expect(alert.textContent).toContain(TEXT.notPermittedTitle)
    expect(createSection()).toBeNull()
    expect(within(screen.getByRole('main')).queryAllByRole('button')).toEqual([])
    // The tags' form and action column went too: their routes ask for the same code.
    expect(screen.queryByRole('region', { name: TEXT.tagCreateHeading })).toBeNull()
    expect(within(tagTable()).queryByRole('columnheader', { name: TEXT.tagsColumnAction })).toBeNull()
    expect(within(departmentTable()).queryByRole('columnheader', { name: TEXT.departmentsColumnAction })).toBeNull()
    expect(namesShown()).toEqual(SERVER_ORDER.map((department) => department.name))
    expect(document.body.textContent).not.toContain(detail)
    await waitFor(() => expect(document.activeElement).toBe(sectionHeading()))
    expect(creates(answered)).toHaveLength(1)
  })

  it('on a retire refused with a 403, withdraws every action on the page, leaves the row as it was, and returns focus to the Departments heading', async () => {
    const detail = "Your role does not hold the 'manage_tags' permission."
    serveApi(routes({ [`DELETE /api/departments/${FINANCE.department_id}`]: { status: 403, body: { detail } } }))
    renderTags()

    fireEvent.click(
      confirmIn(await openConfirmation(TEXT.departmentRetireLabel(FINANCE.name)), TEXT.departmentRetireConfirmLabel),
    )

    const alert = (await within(await sectionShown()).findByText(TEXT.departmentsNotPermitted)).closest(
      '[role="alert"]',
    )
    expect(alert.textContent).toContain(TEXT.notPermittedTitle)
    expect(within(screen.getByRole('main')).queryAllByRole('button')).toEqual([])
    expect(within(departmentTable()).queryByRole('columnheader', { name: TEXT.departmentsColumnAction })).toBeNull()
    expect(within(tagTable()).queryByRole('columnheader', { name: TEXT.tagsColumnAction })).toBeNull()
    expect(cellsOf(FINANCE)[0].textContent).toBe(TEXT.departmentStateActive)
    expect(document.body.textContent).not.toContain(detail)
    await waitFor(() => expect(document.activeElement).toBe(sectionHeading()))
  })

  it('withdraws the department controls too when a tag’s delete is refused with a 403', async () => {
    serveApi(
      routes({
        [`DELETE /api/tags/${PURCHASING.tag_id}`]: { status: 403, body: { detail: 'Not permitted.' } },
      }),
    )
    renderTags()
    await listShown()

    const tagDelete = await screen.findByRole('button', {
      name: TEXT.tagDeleteLabel(PURCHASING.dimension, PURCHASING.tag_name),
    })
    tagDelete.focus()
    fireEvent.click(tagDelete)
    fireEvent.click(confirmIn(await screen.findByRole('dialog'), TEXT.tagDeleteConfirmLabel))

    await screen.findByText(TEXT.tagsNotPermitted)
    expect(TEXT.tagsNotPermitted).toMatch(/tags or departments/)
    expect(createSection()).toBeNull()
    expect(within(section()).queryAllByRole('button')).toEqual([])
    expect(within(departmentTable()).queryByRole('columnheader', { name: TEXT.departmentsColumnAction })).toBeNull()
    expect(namesShown()).toEqual(SERVER_ORDER.map((department) => department.name))
  })

  it('renders the not-permitted notice in the Departments section when the department list answers 403, and withdraws the tags’ actions with it', async () => {
    serveApi(routes({ 'GET /api/departments': { status: 403, body: { detail: 'Not permitted.' } } }))
    renderTags()

    expect(await within(await sectionShown()).findByText(TEXT.notPermitted)).toBeTruthy()
    await screen.findByRole('rowheader', { name: PURCHASING.tag_name })
    expect(within(section()).queryByRole('table')).toBeNull()
    expect(createSection()).toBeNull()
    // The tags were read, and stay listed without any action: the same code is missing.
    expect(screen.queryByRole('region', { name: TEXT.tagCreateHeading })).toBeNull()
    expect(within(tagTable()).queryByRole('columnheader', { name: TEXT.tagsColumnAction })).toBeNull()
    expect(within(screen.getByRole('main')).queryAllByRole('button')).toEqual([])
  })

  it('shows no Departments section when the tags’ own read answers 403, so the page says it is not permitted once', async () => {
    const held = heldResponse()
    serveApi(
      routes({
        'GET /api/tags': { status: 403, body: { detail: 'Not permitted.' } },
        'GET /api/departments': held.route,
      }),
    )
    renderTags()

    // The department list is still unanswered, so this notice is the tags' own.
    expect(await screen.findByText(TEXT.notPermitted)).toBeTruthy()
    expect(section()).toBeNull()
    await act(async () => {
      held.release({ status: 403, body: { detail: 'Not permitted.' } })
    })
    expect(section()).toBeNull()
    expect(screen.getAllByText(TEXT.notPermitted)).toHaveLength(1)
    expect(screen.queryByRole('heading', { name: TEXT.departmentsHeading })).toBeNull()
  })
})

describe('D-129: the keyboard reaches every control', () => {
  it('reaches every department control by Tab, in reading order after the tags’, and none is hidden while it has focus', async () => {
    serveApi(routes())
    renderTags()
    await listShown()
    await screen.findByRole('rowheader', { name: PURCHASING.tag_name })

    const stops = tabThrough() // throws on a trap
    const inSection = stops.filter((stop) => section().contains(stop))
    expect(inSection).toEqual([
      nameField(),
      addButton(),
      // The table's scroll region, so a narrow screen can scroll it by keyboard.
      departmentTable().closest('.table-scroll'),
      deleteButton(FACILITIES),
      retireButton(FINANCE),
      retireButton(HUMAN_RESOURCES),
      deleteButton(LEGAL),
    ])
    expect(stops.indexOf(tagDeleteButton())).toBeLessThan(stops.indexOf(nameField()))
    for (const stop of inSection) {
      stop.focus()
      expect(hidingCauses(stop)).toEqual([])
    }
  })
})

describe('D-129, FR-06: the Departments section is an Administrator’s only, in the interface', () => {
  it('gives an Employee no Departments section: one who types the address is sent to the 403 page without the department list being read', async () => {
    // Nothing answers GET /api/departments: had the section rendered, its read would
    // reach tests/setup.js's refusal and fail this test whatever it asserted.
    const answered = serveApi({ 'GET /api/auth/me': { body: EMPLOYEE } })
    const location = renderTags()

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.accessDeniedTitle })).toBeTruthy()
    expect(location.location.pathname).toBe('/403')
    expect(section()).toBeNull()
    expect(screen.queryByRole('heading', { name: TEXT.departmentsHeading })).toBeNull()
    expect(screen.queryByRole('button', { name: TEXT.departmentCreateAdd })).toBeNull()
    expect(answered.map((request) => request.path)).toEqual(['/api/auth/me'])
  })
})
