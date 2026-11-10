/**
 * FR-10's tag administration (NIT3004; D-119 finding 5): the clauses only the
 * interface can satisfy.
 *
 * FR-10's taxonomy clause, "Tags are deactivated rather than deleted where content
 * still references them, preserving historical classification", and its CRUD line,
 * which gives Tags "Delete" (docs/api-contract.md, "Tag administration"). What is
 * defended here is what the screen shows, keeps, withholds and sends:
 *
 * - every tag in the server's order, with its name, dimension, active or retired
 *   state, and its count labelled as the documents and meetings carrying it; the
 *   name rendered as text;
 * - one action per row, behind a confirmation that says what will happen, one
 *   DELETE per confirmation, and the row then as the reply says: retired on a 200,
 *   gone on a 204 or a 404, each with its notice;
 * - a 403 (every action withdrawn), a failure, and the empty, loading and failed
 *   states;
 * - the route and its link offered to an Administrator only.
 *
 * Usability only, and these tests claim nothing more. Deciding between deactivating
 * and deleting, the count, the order and `manage_tags` on every request are the
 * server's, and pytest's.
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
import { ROLES, TEXT } from '../src/constants.js'
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

  it('shows a loading state, then a failed read in fixed words, and Try again reads the list again', async () => {
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
    held.release({ status: 500, body: { detail: backendText } })

    const alert = (await screen.findByText(TEXT.tagsLoadFailed)).closest('[role="alert"]')
    expect(alert.textContent).toContain(messageForStatus(500))
    expect(document.body.textContent).not.toContain(backendText)
    fireEvent.click(screen.getByRole('button', { name: TEXT.uploadRetry }))

    await screen.findByRole('rowheader', { name: PURCHASING.tag_name })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(listReads(answered)).toHaveLength(2)
  })

  it('renders only the not-permitted notice when the list itself answers 403', async () => {
    serveApi(routes({ 'GET /api/tags': { status: 403, body: { detail: 'Not permitted.' } } }))
    renderTags()

    expect(await screen.findByText(TEXT.notPermitted)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(within(screen.getByRole('main')).queryAllByRole('button')).toEqual([])
  })
})

describe('FR-10, FR-06: tag administration is an Administrator’s only, in the interface', () => {
  it('offers an Employee no link to it, and sends one who types its address to the 403 page without reading the tags', async () => {
    // Nothing answers GET /api/tags: had the page rendered, its read would reach
    // tests/setup.js's refusal and fail this test whatever it asserted.
    const answered = serveApi({ 'GET /api/auth/me': { body: EMPLOYEE } })
    const location = renderTags()

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.accessDeniedTitle })).toBeTruthy()
    expect(location.location.pathname).toBe('/403')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByRole('button', { name: 'Log out' })).toBeTruthy()
    expect(within(nav).queryByRole('link', { name: TEXT.tagsHeading })).toBeNull()
    expect(answered.map((request) => request.path)).toEqual(['/api/auth/me'])
  })

  it('offers an Administrator the link beside Role management and the knowledge-gap log, and renders the page at its address', async () => {
    serveApi(routes())
    const location = renderTags()

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.tagsHeading })).toBeTruthy()
    await screen.findByRole('rowheader', { name: PURCHASING.tag_name })
    expect(location.location.pathname).toBe('/admin/tags')
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
