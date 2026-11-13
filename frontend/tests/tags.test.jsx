/**
 * FR-10's tag administration (NIT3004; D-119 finding 5; D-128): the clauses only the
 * interface can satisfy.
 *
 * FR-10's taxonomy clause, "Tags are deactivated rather than deleted where content
 * still references them, preserving historical classification", and its CRUD line,
 * which gives Tags "Create" and "Delete" (docs/api-contract.md, "Tag
 * administration"). What is defended here is what the screen shows, keeps, withholds
 * and sends:
 *
 * - every tag in the server's order, with its name, dimension, active or retired
 *   state, and its count labelled as the documents and meetings carrying it; the
 *   name rendered as text;
 * - one action per row, behind a confirmation that says what will happen, one
 *   DELETE per confirmation, and the row then as the reply says: retired on a 200,
 *   gone on a 204 or a 404, each with its notice;
 * - a 403 (every action withdrawn), a failure, and the empty, loading and failed
 *   states;
 * - D-128's form that adds a value: what it says before anything is added, what it
 *   sends, and the 201, the 409 (an active tag and a retired one told apart by the
 *   list), the 400, the 429 and the 403, each as the page shows it;
 * - the route, its link and the form offered to an Administrator only.
 *
 * Usability only, and these tests claim nothing more. Deciding between deactivating
 * and deleting, the count, the order, whether a name is a duplicate and `manage_tags`
 * on every request are the server's, and pytest's.
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
import { ROLES, TAG_NAME_MAXIMUM_LENGTH, TEXT, VALIDATION } from '../src/constants.js'
import { heldResponse, serveApi } from './fakeApi.js'

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

/* The tag entry of docs/api-contract.md: five fields and no others. */

const PURCHASING = { tag_id: 'tag-0001', dimension: 'Process', tag_name: 'purchasing', active: true, item_count: 4 }
/** Referenced by no applied link: a count of 0, which does not promise a deletion. */
const BRIDGE = { tag_id: 'tag-0002', dimension: 'Project', tag_name: 'bridge maintenance', active: true, item_count: 0 }
/** Retired already, and still on two sources. */
const LEGACY = { tag_id: 'tag-0003', dimension: 'Project', tag_name: 'legacy rollout', active: false, item_count: 2 }
const BUDGET = { tag_id: 'tag-0004', dimension: 'Topic', tag_name: 'budget planning', active: true, item_count: 1 }

/**
 * The contract's order: by dimension (Process, Project, Topic), then by name. Not
 * an order the screen would arrive at by sorting on name or on count.
 */
const SERVER_ORDER = [PURCHASING, BRIDGE, LEGACY, BUDGET]

function routes(extra = {}) {
  return {
    'GET /api/auth/me': { body: ADMINISTRATOR },
    'GET /api/tags': { body: SERVER_ORDER },
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

function pageHeading() {
  return screen.getByRole('heading', { level: 1, name: TEXT.tagsHeading })
}

/** The name of each body row, in document order. */
function namesShown() {
  return within(screen.getByRole('table'))
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getByRole('rowheader').textContent)
}

/** A row's data cells after its name: dimension, state, count, then the action. */
function cellsOf(tag) {
  return within(screen.getByRole('rowheader', { name: tag.tag_name }).closest('tr')).getAllByRole('cell')
}

function deleteButton(tag) {
  return screen.queryByRole('button', { name: TEXT.tagDeleteLabel(tag.dimension, tag.tag_name) })
}

function deletes(answered) {
  return answered.filter((request) => request.method === 'DELETE')
}

function listReads(answered) {
  return answered.filter((request) => request.method === 'GET' && request.path === '/api/tags')
}

/** Opens a row's confirmation and returns the dialogue. */
async function openConfirmation(tag) {
  const button = await screen.findByRole('button', { name: TEXT.tagDeleteLabel(tag.dimension, tag.tag_name) })
  button.focus()
  fireEvent.click(button)
  return screen.findByRole('dialog')
}

function confirmIn(dialog) {
  return within(dialog).getByRole('button', { name: TEXT.tagDeleteConfirmLabel })
}

/** D-128's add-a-value part of the page, or null while it is not offered. */
function createSection() {
  return screen.queryByRole('region', { name: TEXT.tagCreateHeading })
}

function dimensionSelect() {
  return within(createSection()).getByLabelText(TEXT.tagDimensionLabel)
}

function nameField() {
  return within(createSection()).getByLabelText(TEXT.tagCreateNameLabel)
}

function addButton() {
  return within(createSection()).getByRole('button', { name: TEXT.tagCreateAdd })
}

function creates(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/tags')
}

/** Everything that describes a field to assistive technology: its hint, its error and anything else named. */
function descriptionOf(field) {
  return (field.getAttribute('aria-describedby') ?? '')
    .split(' ')
    .map((id) => document.getElementById(id)?.textContent ?? '')
    .join(' ')
}

/**
 * Once the form is offered, chooses `dimension`, types `name` and presses Add, as a
 * person does: the button takes focus, then is clicked.
 */
async function addValue(dimension, name) {
  await screen.findByRole('region', { name: TEXT.tagCreateHeading })
  fireEvent.change(dimensionSelect(), { target: { value: dimension } })
  fireEvent.change(nameField(), { target: { value: name } })
  const add = addButton()
  add.focus()
  fireEvent.click(add)
}

/** `GET /api/tags` answered with `first` once, and with `later` on every read after it. */
function listReadsAnswer(first, later) {
  let reads = 0
  return () => {
    reads += 1
    return reads === 1 ? { body: first } : later
  }
}

describe('FR-10: the tags, as the server sent them', () => {
  it('lists every tag in the server’s order with its name, dimension, state and its count labelled as the documents and meetings carrying it, and one Delete per row', async () => {
    const answered = serveApi(routes())
    renderTags()

    await screen.findByRole('rowheader', { name: PURCHASING.tag_name })
    expect(namesShown()).toEqual(SERVER_ORDER.map((tag) => tag.tag_name))
    const table = screen.getByRole('table', { name: TEXT.tagsTableCaption })
    expect(within(table).getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      TEXT.tagsColumnName,
      TEXT.tagsColumnDimension,
      TEXT.tagsColumnState,
      TEXT.tagsColumnItems,
      TEXT.tagsColumnAction,
    ])
    expect(TEXT.tagsColumnItems).toMatch(/documents and meetings/i)
    for (const tag of SERVER_ORDER) {
      const [dimension, state, count, action] = cellsOf(tag)
      expect(dimension.textContent).toBe(tag.dimension)
      expect(state.textContent).toBe(tag.active ? TEXT.tagStateActive : TEXT.tagStateRetired)
      expect(count.textContent).toBe(String(tag.item_count))
      // One action per row, the retired tag's included: it may still be deletable.
      expect(within(action).getAllByRole('button')).toEqual([deleteButton(tag)])
      expect(deleteButton(tag).textContent).toBe(TEXT.tagDelete)
    }
    // One read, and nothing sent.
    expect(answered.map((request) => `${request.method} ${request.path}`)).toEqual([
      'GET /api/auth/me',
      'GET /api/tags',
    ])
  })

  it('renders a tag name holding markup as the characters it is, and creates no element from it', async () => {
    const hostile = '<img src="x" onerror="window.__tagsInjected = true"><b>bridge</b>'
    const tag = { ...BRIDGE, tag_name: hostile }
    serveApi(routes({ 'GET /api/tags': { body: [tag] } }))
    renderTags()

    const name = await screen.findByRole('rowheader', { name: hostile })
    expect(name.textContent).toBe(hostile)
    expect(name.children).toHaveLength(0)
    expect(screen.getByRole('table').querySelectorAll('b, img')).toHaveLength(0)
    expect(window.__tagsInjected).toBeUndefined()
    expect(deleteButton(tag)).toBeTruthy()
  })
})

describe('FR-10: "deactivated rather than deleted where content still references them"', () => {
  it('asks for confirmation first, saying both outcomes, and Cancel sends nothing and returns focus to the row', async () => {
    const answered = serveApi(routes())
    renderTags()

    const dialog = await openConfirmation(BRIDGE)

    expect(within(dialog).getByRole('heading', { name: TEXT.tagDeleteConfirm('Project', BRIDGE.tag_name) })).toBeTruthy()
    expect(within(dialog).getByText(TEXT.tagDeleteBody)).toBeTruthy()
    expect(TEXT.tagDeleteBody).toMatch(/deleted/)
    expect(TEXT.tagDeleteBody).toMatch(/deactivated/)
    fireEvent.click(within(dialog).getByRole('button', { name: TEXT.tagDeleteCancel }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(deleteButton(BRIDGE)))
    expect(deletes(answered)).toEqual([])
  })

  it('on a 200 shows the row retired, as the reply has it, with a notice that it was deactivated because content still references it', async () => {
    const answered = serveApi(
      routes({ [`DELETE /api/tags/${BRIDGE.tag_id}`]: { body: { ...BRIDGE, active: false } } }),
    )
    renderTags()

    fireEvent.click(confirmIn(await openConfirmation(BRIDGE)))

    const notice = await screen.findByText(TEXT.tagDeactivated(BRIDGE.tag_name))
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(cellsOf(BRIDGE)[1].textContent).toBe(TEXT.tagStateRetired)
    // Still listed, where it was, and its action still offered.
    expect(namesShown()).toEqual(SERVER_ORDER.map((tag) => tag.tag_name))
    await waitFor(() => expect(document.activeElement).toBe(deleteButton(BRIDGE)))
    expect(deletes(answered).map((request) => request.path)).toEqual([`/api/tags/${BRIDGE.tag_id}`])
    // Updated from the reply, not by reading the list again.
    expect(listReads(answered)).toHaveLength(1)
  })

  it('on a 204 takes the row away with a notice that the tag was deleted, and puts focus on the heading', async () => {
    const answered = serveApi(routes({ [`DELETE /api/tags/${BRIDGE.tag_id}`]: { status: 204 } }))
    renderTags()

    fireEvent.click(confirmIn(await openConfirmation(BRIDGE)))

    const notice = await screen.findByText(TEXT.tagDeleted(BRIDGE.tag_name))
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(screen.queryByRole('rowheader', { name: BRIDGE.tag_name })).toBeNull()
    expect(namesShown()).toEqual([PURCHASING, LEGACY, BUDGET].map((tag) => tag.tag_name))
    await waitFor(() => expect(document.activeElement).toBe(pageHeading()))
    expect(deletes(answered)).toHaveLength(1)
  })

  it('on a 404 takes the row away with a notice that the tag no longer exists', async () => {
    serveApi(
      routes({
        [`DELETE /api/tags/${LEGACY.tag_id}`]: { status: 404, body: { detail: 'No Tag matches the given query.' } },
      }),
    )
    renderTags()

    fireEvent.click(confirmIn(await openConfirmation(LEGACY)))

    const notice = await screen.findByText(TEXT.tagGone(LEGACY.tag_name))
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(screen.queryByRole('rowheader', { name: LEGACY.tag_name })).toBeNull()
    expect(namesShown()).toEqual([PURCHASING, BRIDGE, BUDGET].map((tag) => tag.tag_name))
    expect(document.body.textContent).not.toContain('No Tag matches the given query.')
    await waitFor(() => expect(document.activeElement).toBe(pageHeading()))
  })

  it('sends one DELETE for presses made while the first is still in flight, and says it is busy', async () => {
    const held = heldResponse()
    const answered = serveApi(routes({ [`DELETE /api/tags/${BRIDGE.tag_id}`]: held.route }))
    renderTags()
    const dialog = await openConfirmation(BRIDGE)
    const confirm = confirmIn(dialog)

    // A double press whose second lands before React has rendered the first.
    act(() => {
      fireEvent.click(confirm)
      fireEvent.click(confirm)
    })
    await waitFor(() => expect(confirm.getAttribute('aria-busy')).toBe('true'))
    expect(confirm.textContent).toBe(TEXT.tagDeleting)
    fireEvent.click(confirm)
    expect(deletes(answered)).toHaveLength(1)

    held.release({ status: 204 })
    expect(await screen.findByText(TEXT.tagDeleted(BRIDGE.tag_name))).toBeTruthy()
    expect(deletes(answered)).toHaveLength(1)
  })

  it('withdraws every action and says the role may not manage tags when the server refuses with a 403', async () => {
    const detail = "Your role does not hold the 'manage_tags' permission."
    const answered = serveApi(routes({ [`DELETE /api/tags/${BRIDGE.tag_id}`]: { status: 403, body: { detail } } }))
    renderTags()

    fireEvent.click(confirmIn(await openConfirmation(BRIDGE)))

    const alert = (await screen.findByText(TEXT.tagsNotPermitted)).closest('[role="alert"]')
    expect(alert.textContent).toContain(TEXT.notPermittedTitle)
    expect(within(screen.getByRole('main')).queryAllByRole('button')).toEqual([])
    // The tags already read stay as they were, without an action column.
    expect(namesShown()).toEqual(SERVER_ORDER.map((tag) => tag.tag_name))
    expect(within(screen.getByRole('table')).queryByRole('columnheader', { name: TEXT.tagsColumnAction })).toBeNull()
    expect(document.body.textContent).not.toContain(detail)
    expect(deletes(answered)).toHaveLength(1)
    await waitFor(() => expect(document.activeElement).toBe(pageHeading()))
  })

  it('says a failed delete failed, in the client’s words and never the server’s, and leaves the row as it was', async () => {
    const backendText = 'Traceback (most recent call last): IntegrityError on "content_tags"'
    serveApi(routes({ [`DELETE /api/tags/${BRIDGE.tag_id}`]: { status: 500, body: { detail: backendText } } }))
    renderTags()

    fireEvent.click(confirmIn(await openConfirmation(BRIDGE)))

    const alert = (await screen.findByText(TEXT.tagDeleteFailed)).closest('[role="alert"]')
    expect(alert.textContent).toContain(messageForStatus(500))
    expect(document.body.textContent).not.toContain(backendText)
    expect(cellsOf(BRIDGE)[1].textContent).toBe(TEXT.tagStateActive)
    expect(deleteButton(BRIDGE)).toBeTruthy()
  })
})

describe('FR-10 tag administration: the empty, loading and failed states', () => {
  it('says there are no tags for an empty list, as an ordinary state', async () => {
    serveApi(routes({ 'GET /api/tags': { body: [] } }))
    renderTags()

    const empty = await screen.findByText(TEXT.noTags)
    expect(empty.closest('[role="status"]')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows a loading state, then a failed read in fixed words, and Try again reads the list again, offering the add form only once the list is read', async () => {
    const held = heldResponse()
    const backendText = 'relation "tags" does not exist'
    let reads = 0
    const answered = serveApi(
      routes({
        'GET /api/tags': () => {
          reads += 1
          return reads === 1 ? held.route() : { body: SERVER_ORDER }
        },
      }),
    )
    renderTags()

    expect((await screen.findByText(TEXT.loadingTags)).getAttribute('role')).toBe('status')
    // D-128's form waits for the list, which is how a 409 is told apart.
    expect(createSection()).toBeNull()
    held.release({ status: 500, body: { detail: backendText } })

    const alert = (await screen.findByText(TEXT.tagsLoadFailed)).closest('[role="alert"]')
    expect(alert.textContent).toContain(messageForStatus(500))
    expect(document.body.textContent).not.toContain(backendText)
    expect(createSection()).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: TEXT.uploadRetry }))

    await screen.findByRole('rowheader', { name: PURCHASING.tag_name })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(listReads(answered)).toHaveLength(2)
    expect(createSection()).toBeTruthy()
  })

  it('renders only the not-permitted notice when the list itself answers 403', async () => {
    serveApi(routes({ 'GET /api/tags': { status: 403, body: { detail: 'Not permitted.' } } }))
    renderTags()

    expect(await screen.findByText(TEXT.notPermitted)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(within(screen.getByRole('main')).queryAllByRole('button')).toEqual([])
  })
})

/* ---- D-128: an Administrator adds a value -------------------------------- */

/** The entry a 201 carries: the name as the server stores it, active, carried by nothing yet. */
const HARBOUR = { tag_id: 'tag-0005', dimension: 'Project', tag_name: 'harbour upgrade', active: true, item_count: 0 }

/** A value a classify run created after the page read the list (D-128): a grown Topic. */
const ASSET_REGISTER = { tag_id: 'tag-0006', dimension: 'Topic', tag_name: 'asset register', active: true, item_count: 1 }

/** The server's wording of its 409 (apps/api/views.py), which the page never shows. */
const DUPLICATE_DETAIL = 'A tag with this name already exists in this dimension. A retired tag is not added again here.'

describe('D-128: an Administrator adds a tag value', () => {
  it('says the value is offered for every document whatever its audience, and what the AI does with values outside the list, before anything is added', async () => {
    serveApi(routes())
    renderTags()

    const section = within(await screen.findByRole('region', { name: TEXT.tagCreateHeading }))
    expect(section.getByRole('heading', { level: 2, name: TEXT.tagCreateHeading })).toBeTruthy()
    // The scope, plainly: every document, whatever its audience, so any reader sees the name.
    expect(section.getByText(TEXT.tagCreateScope)).toBeTruthy()
    expect(TEXT.tagCreateScope).toMatch(/every document, whatever its audience/)
    expect(TEXT.tagCreateScope).toMatch(/to everyone who tags a document, and to the AI when it classifies one/)
    // The AI adds values itself, and a retired one can come back that way.
    expect(section.getByText(TEXT.tagCreateAiNote)).toBeTruthy()
    // D-129: the AI adds no value of its own; a new topic waits for a person, and a
    // project or process outside the list is discarded (Objective 05 clause 3).
    expect(TEXT.tagCreateAiNote).toMatch(/does not add values of its own/)
    expect(TEXT.tagCreateAiNote).toMatch(/waits for a person to confirm it/)
    expect(TEXT.tagCreateAiNote).toMatch(/project or process outside the list is discarded/)
    expect(TEXT.tagCreateAiNote).toMatch(/retired topic comes back only if a person/)
    // The form: a dimension from the three tag dimensions, a name, and Add.
    expect(Array.from(dimensionSelect().options, (option) => [option.value, option.textContent])).toEqual([
      ['Project', TEXT.documentFieldProject],
      ['Process', TEXT.documentFieldProcess],
      ['Topic', TEXT.documentFieldTopic],
    ])
    expect(nameField().tagName).toBe('INPUT')
    expect(addButton().getAttribute('type')).toBe('submit')
    // Someone who tabs straight to the name hears the scope as well as the hint.
    expect(descriptionOf(nameField())).toContain(TEXT.tagCreateNameHint)
    expect(descriptionOf(nameField())).toContain(TEXT.tagCreateScope)
  })

  it('on a 201 reads the list again and shows it in the server’s order, clears the name, keeps the dimension and announces the value as stored', async () => {
    // The second read: the new value where the server orders it, and a value a classify
    // run added meanwhile, which only a read of the list could show.
    const after = [PURCHASING, BRIDGE, HARBOUR, LEGACY, ASSET_REGISTER, BUDGET]
    const answered = serveApi(
      routes({
        'GET /api/tags': listReadsAnswer(SERVER_ORDER, { body: after }),
        'POST /api/tags': { status: 201, body: HARBOUR },
      }),
    )
    renderTags()

    await addValue('Project', '  Harbour \t  Upgrade ')

    const notice = await screen.findByText(TEXT.tagCreated(TEXT.documentFieldProject, HARBOUR.tag_name))
    // Polite: a status, not an alert.
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    await waitFor(() => expect(namesShown()).toEqual(after.map((tag) => tag.tag_name)))
    expect(cellsOf(HARBOUR).map((cell) => cell.textContent).slice(0, 3)).toEqual([
      TEXT.documentFieldProject,
      TEXT.tagStateActive,
      '0',
    ])
    expect(nameField().value).toBe('')
    expect(dimensionSelect().value).toBe('Project')
    // One request in the contract's form, trimmed and single-spaced, then one read.
    expect(creates(answered).map((request) => request.body)).toEqual([{ dimension: 'Project', tag_name: 'Harbour Upgrade' }])
    expect(listReads(answered)).toHaveLength(2)
  })

  it('on a 201 whose list cannot be read again places the new value by dimension and name, and still announces it without a failure', async () => {
    const cable = { tag_id: 'tag-0007', dimension: 'Project', tag_name: 'cable survey', active: true, item_count: 0 }
    serveApi(
      routes({
        'GET /api/tags': listReadsAnswer(SERVER_ORDER, { status: 500, body: { detail: 'database is locked' } }),
        'POST /api/tags': { status: 201, body: cable },
      }),
    )
    renderTags()

    await addValue('Project', 'Cable Survey')

    expect(await screen.findByText(TEXT.tagCreated(TEXT.documentFieldProject, cable.tag_name))).toBeTruthy()
    // Between the two Projects it sorts between: Process, then Project, then Topic.
    expect(namesShown()).toEqual(['purchasing', 'bridge maintenance', 'cable survey', 'legacy rollout', 'budget planning'])
    expect(screen.queryByRole('alert')).toBeNull()
    expect(document.body.textContent).not.toContain('database is locked')
  })

  it.each([
    { state: 'an active one', existing: BRIDGE, typed: 'Bridge  Maintenance', text: TEXT.tagCreateExists },
    { state: 'a retired one', existing: LEGACY, typed: 'LEGACY rollout', text: TEXT.tagCreateExistsRetired },
  ])(
    'on a 409 naming $state, says so by its dimension and name from the list, keeps what was typed, and never shows the reply’s detail',
    async ({ existing, typed, text }) => {
      const answered = serveApi(
        routes({ 'POST /api/tags': { status: 409, body: { detail: DUPLICATE_DETAIL, tag_id: existing.tag_id } } }),
      )
      renderTags()

      await addValue(existing.dimension, typed)

      const notice = await screen.findByText(text(TEXT.documentFieldProject, existing.tag_name))
      expect(notice.closest('[role="status"]')).toBeTruthy()
      // The two cases are told apart: the active one is not called retired, and the
      // retired one is.
      const other = text === TEXT.tagCreateExists ? TEXT.tagCreateExistsRetired : TEXT.tagCreateExists
      expect(screen.queryByText(other(TEXT.documentFieldProject, existing.tag_name))).toBeNull()
      expect(document.body.textContent).not.toContain(DUPLICATE_DETAIL)
      expect(nameField().value).toBe(typed)
      // Nothing was added, and the list, read again, is as it was.
      expect(namesShown()).toEqual(SERVER_ORDER.map((tag) => tag.tag_name))
      expect(listReads(answered)).toHaveLength(2)
      expect(creates(answered)).toHaveLength(1)
    },
  )

  it('on a 409 naming a value the list held here lacks, one a classify run added since, reads the list again, names it from there and shows its row, as text', async () => {
    // A value the AI derived from a document's text: untrusted, rendered as text.
    const added = { ...ASSET_REGISTER, tag_name: '<img src="x" onerror="window.__tagCreateInjected = true">asset register' }
    const after = [PURCHASING, BRIDGE, LEGACY, added, BUDGET]
    const answered = serveApi(
      routes({
        'GET /api/tags': listReadsAnswer(SERVER_ORDER, { body: after }),
        'POST /api/tags': { status: 409, body: { detail: DUPLICATE_DETAIL, tag_id: added.tag_id } },
      }),
    )
    renderTags()

    await addValue('Topic', 'asset register')

    expect(await screen.findByText(TEXT.tagCreateExists(TEXT.documentFieldTopic, added.tag_name))).toBeTruthy()
    expect(namesShown()).toEqual(after.map((tag) => tag.tag_name))
    expect(document.querySelectorAll('main img')).toHaveLength(0)
    expect(window.__tagCreateInjected).toBeUndefined()
    expect(listReads(answered)).toHaveLength(2)
  })

  it.each([
    { field: 'tag_name', message: 'Ensure this field has no more than 255 characters.', control: () => nameField() },
    { field: 'dimension', message: '"Department" is not a valid choice.', control: () => dimensionSelect() },
  ])('places a 400 on $field beside its field, with focus on it, and adds nothing', async ({ field, message, control }) => {
    const answered = serveApi(routes({ 'POST /api/tags': { status: 400, body: { [field]: [message] } } }))
    renderTags()

    await addValue('Topic', 'site safety')

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.tagCreateFailed)
    expect(alert.textContent).toContain(TEXT.classificationCheckFields)
    await waitFor(() => expect(document.activeElement).toBe(control()))
    expect(control().getAttribute('aria-invalid')).toBe('true')
    expect(descriptionOf(control())).toContain(message)
    expect(nameField().value).toBe('site safety')
    expect(namesShown()).toEqual(SERVER_ORDER.map((tag) => tag.tag_name))
    // A refusal is not a change: the list is not read again.
    expect(listReads(answered)).toHaveLength(1)
  })

  it('refuses an empty name, and one too long once single-spaced, beside the field and before any request', async () => {
    const answered = serveApi(routes({ 'POST /api/tags': { status: 201, body: HARBOUR } }))
    renderTags()

    await addValue('Project', '  \t ')
    await waitFor(() => expect(document.activeElement).toBe(nameField()))
    expect(nameField().getAttribute('aria-invalid')).toBe('true')
    expect(descriptionOf(nameField())).toContain(VALIDATION.tagValueRequired)

    await addValue('Project', 'x'.repeat(TAG_NAME_MAXIMUM_LENGTH + 1))
    await waitFor(() => expect(descriptionOf(nameField())).toContain(VALIDATION.tagValueTooLong))
    expect(nameField().getAttribute('aria-invalid')).toBe('true')
    expect(creates(answered)).toEqual([])

    // Within the limit once single-spaced, so it is sent.
    await addValue('Project', `harbour${' '.repeat(TAG_NAME_MAXIMUM_LENGTH)}upgrade`)
    await waitFor(() => expect(creates(answered)).toHaveLength(1))
    expect(creates(answered)[0].body).toEqual({ dimension: 'Project', tag_name: 'harbour upgrade' })
  })

  it('names the tagging limit on a 429, with when to try again, and keeps the name and the form', async () => {
    serveApi(
      routes({
        'POST /api/tags': { status: 429, body: { detail: 'Request was throttled.' }, headers: { 'Retry-After': '42' } },
      }),
    )
    renderTags()

    await addValue('Topic', 'site safety')

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.tagCreateFailed)
    expect(alert.textContent).toContain(TEXT.tagLimitReached(TEXT.retryInSeconds(42)))
    expect(document.body.textContent).not.toContain('Request was throttled.')
    expect(nameField().value).toBe('site safety')
    expect(addButton()).toBeTruthy()
    expect(namesShown()).toEqual(SERVER_ORDER.map((tag) => tag.tag_name))
  })

  it('on a 403 withdraws every action, the form with them, says the role may not manage tags, and puts focus on the heading', async () => {
    const detail = "Your role does not hold the 'manage_tags' permission."
    const answered = serveApi(routes({ 'POST /api/tags': { status: 403, body: { detail } } }))
    renderTags()

    await addValue('Topic', 'site safety')

    const alert = (await screen.findByText(TEXT.tagsNotPermitted)).closest('[role="alert"]')
    expect(alert.textContent).toContain(TEXT.notPermittedTitle)
    expect(TEXT.tagsNotPermitted).toMatch(/added/)
    expect(createSection()).toBeNull()
    expect(within(screen.getByRole('main')).queryAllByRole('button')).toEqual([])
    expect(within(screen.getByRole('table')).queryByRole('columnheader', { name: TEXT.tagsColumnAction })).toBeNull()
    expect(namesShown()).toEqual(SERVER_ORDER.map((tag) => tag.tag_name))
    expect(document.body.textContent).not.toContain(detail)
    await waitFor(() => expect(document.activeElement).toBe(pageHeading()))
    expect(creates(answered)).toHaveLength(1)
  })

  it('sends one POST for presses made while the first is still in flight, and says it is busy', async () => {
    const held = heldResponse()
    const answered = serveApi(routes({ 'POST /api/tags': held.route }))
    renderTags()
    await screen.findByRole('region', { name: TEXT.tagCreateHeading })
    fireEvent.change(nameField(), { target: { value: 'harbour upgrade' } })
    const add = addButton()

    // A double press whose second lands before React has rendered the first.
    act(() => {
      fireEvent.click(add)
      fireEvent.click(add)
    })
    await waitFor(() => expect(add.getAttribute('aria-busy')).toBe('true'))
    expect(add.textContent).toBe(TEXT.tagAdding)
    fireEvent.click(add)
    expect(creates(answered)).toHaveLength(1)

    held.release({ status: 201, body: HARBOUR })
    expect(await screen.findByText(TEXT.tagCreated(TEXT.documentFieldProject, HARBOUR.tag_name))).toBeTruthy()
    expect(creates(answered)).toHaveLength(1)
    expect(add.getAttribute('aria-busy')).toBeNull()
  })
})

describe('FR-10, FR-06: tag administration is an Administrator’s only, in the interface', () => {
  it('offers an Employee no link to it, and sends one who types its address to the 403 page without reading the tags or offering the add form', async () => {
    // Nothing answers GET /api/tags or POST /api/tags: had the page rendered, its read
    // would reach tests/setup.js's refusal and fail this test whatever it asserted.
    const answered = serveApi({ 'GET /api/auth/me': { body: EMPLOYEE } })
    const location = renderTags()

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.accessDeniedTitle })).toBeTruthy()
    expect(location.location.pathname).toBe('/403')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByRole('button', { name: 'Log out' })).toBeTruthy()
    expect(within(nav).queryByRole('link', { name: TEXT.tagsHeading })).toBeNull()
    // D-128's form is on the Administrator's page and nowhere else.
    expect(createSection()).toBeNull()
    expect(screen.queryByRole('button', { name: TEXT.tagCreateAdd })).toBeNull()
    expect(answered.map((request) => request.path)).toEqual(['/api/auth/me'])
  })

  it('offers an Administrator the link beside Role management and the knowledge-gap log, and renders the page at its address with the add form', async () => {
    serveApi(routes())
    const location = renderTags()

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.tagsHeading })).toBeTruthy()
    await screen.findByRole('rowheader', { name: PURCHASING.tag_name })
    expect(location.location.pathname).toBe('/admin/tags')
    expect(within(createSection()).getByRole('button', { name: TEXT.tagCreateAdd })).toBeTruthy()
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    const names = within(nav)
      .getAllByRole('link')
      .map((link) => link.textContent)
    expect(names.indexOf(TEXT.gapsHeading)).toBe(names.indexOf('Role management') + 1)
    expect(names.indexOf(TEXT.tagsHeading)).toBe(names.indexOf(TEXT.gapsHeading) + 1)
    const link = within(nav).getByRole('link', { name: TEXT.tagsHeading })
    expect(link.getAttribute('href')).toBe('/admin/tags')
    expect(link.getAttribute('aria-current')).toBe('page')
  })
})
