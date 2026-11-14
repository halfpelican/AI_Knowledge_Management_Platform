/**
 * FR-03's release of a lock, on Role management (D-130): the clauses only the
 * interface can satisfy.
 *
 * - "An Administrator viewing a locked account can release the lock immediately, so a
 *   locked-out user has a route forward." Benjamin's decision 3 puts the control in the
 *   Role management table, in an Account column that says which accounts are locked.
 * - "An Administrator cannot release a lock on their own account": the signed-in
 *   Administrator's own locked row offers no Unlock button, and says who can.
 * - The release is confirmed first, in the existing dialogue, which says when and from
 *   where the lock began, that the password is not changed ("releasing a lock restores
 *   the ability to attempt authentication and nothing more"), and asks the Administrator
 *   to check who is asking (the security review, finding L3). Nothing is sent before
 *   the confirmation.
 * - The 200, 409, 404 and 403 of `POST /api/users/{id}/unlock` each leave the screen
 *   telling the truth, and a role change keeps the row's lock (the security review, Q5).
 *
 * The server's half (the 403 for an Employee and for the requester's own account, the
 * 404, the 409, the release row, the password and sessions untouched) is pytest's. An
 * Employee never reaching this screen is tests/accessDenied.test.jsx's.
 *
 * The clock is faked from a fixed instant, `Date` and `setTimeout` only, and moves on
 * with real time as well, so the Testing Library's own waiting still runs. The screen
 * says times of day in the machine's time zone, so an expected time is formatted here
 * as the screen formats one (en-AU, short), not written out. jsdom applies no
 * stylesheet, so the badge's border and colour are not seen here: what is asserted is
 * that a lock is said in words.
 *
 * The whole application is rendered at /admin/roles, signed in as an Administrator,
 * mocked at `fetch` through tests/fakeApi.js.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App.jsx'
import { ROLES, TEXT } from '../src/constants.js'
import { serveApi } from './fakeApi.js'

/** Where the faked clock starts. */
const NOW = new Date('2026-11-13T10:30:00+11:00')

/** An ISO timestamp `minutes` after NOW, or before it where negative. */
function minutesFromNow(minutes) {
  return new Date(NOW.getTime() + minutes * 60 * 1000).toISOString()
}

/** The user object as login and `GET /api/auth/me` return it, without `lock`. */
const ADA = {
  id: 'user-ada',
  name: 'Ada Administrator',
  email: 'ada@example.com',
  role: ROLES.administrator,
  created_at: '2026-09-12T10:00:00+10:00',
}

const JANE = {
  id: 'user-jane',
  name: 'Jane Doe',
  email: 'jane.doe@company.com',
  role: ROLES.employee,
  created_at: '2026-09-20T10:00:00+10:00',
}

const ERIN = {
  id: 'user-erin',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-21T10:00:00+10:00',
}

/** A second Administrator, who could release Ada's lock. */
const ABE = {
  id: 'user-abe',
  name: 'Abe Admin',
  email: 'abe@example.com',
  role: ROLES.administrator,
  created_at: '2026-09-15T10:00:00+10:00',
}

const SAM = {
  id: 'user-sam',
  name: 'Sam Sato',
  email: 'sam@example.com',
  role: ROLES.employee,
  created_at: '2026-09-22T10:00:00+10:00',
}

/** Jane's lock: set by a lockout three minutes ago from 203.0.113.42, ending in twelve. */
const JANE_LOCK = { locked_until: minutesFromNow(12), locked_at: minutesFromNow(-3), source_ip: '203.0.113.42' }

/** A user as `GET /api/users` lists them for a holder of release_account_locks. */
function listed(user, lock = null) {
  return { ...user, lock }
}

/** `GET /api/roles`: ids the screen sends, names the users carry. */
const ROLE_LIST = [
  { role_id: 'role-employee', name: ROLES.employee, description: 'Default role', permissions: [] },
  { role_id: 'role-administrator', name: ROLES.administrator, description: 'Full management', permissions: [] },
]

const UNLOCK_JANE = 'POST /api/users/user-jane/unlock'

beforeEach(() => {
  vi.useFakeTimers({ now: NOW, shouldAdvanceTime: true, toFake: ['setTimeout', 'clearTimeout', 'Date'] })
})

afterEach(() => {
  vi.useRealTimers()
})

/**
 * Signed in as Ada, at /admin/roles. `users` is the list, or a route answering each read
 * of it in turn; `extra` adds routes.
 */
function serveRoles(users, extra = {}) {
  const answered = serveApi({
    'GET /api/auth/me': { body: ADA },
    'GET /api/users': typeof users === 'function' ? users : { body: users },
    'GET /api/roles': { body: ROLE_LIST },
    ...extra,
  })
  render(
    <MemoryRouter initialEntries={['/admin/roles']}>
      <App />
    </MemoryRouter>,
  )
  return answered
}

/** A route answering the first read of the list with `first` and every later one with `later`. */
function listThen(first, later) {
  let reads = 0
  return () => {
    reads += 1
    return { body: reads === 1 ? first : later }
  }
}

/** A time of day as the screen says one: en-AU, short, in the machine's time zone. */
function timeOfDay(iso) {
  return new Intl.DateTimeFormat('en-AU', { timeStyle: 'short' }).format(new Date(iso))
}

/** The row for `name`, or undefined where the table has none. */
function rowFor(name) {
  return within(screen.getByRole('table'))
    .getAllByRole('row')
    .find((row) => within(row).queryByRole('rowheader')?.textContent === name)
}

/** The Account column's cell in `name`'s row. */
function accountCell(name) {
  const headers = within(screen.getByRole('table')).getAllByRole('columnheader')
  const column = headers.findIndex((header) => header.textContent === 'Account')
  expect(column, 'the table has an Account column').toBeGreaterThan(-1)
  return rowFor(name).children[column]
}

function unlockButton(name) {
  return screen.queryByRole('button', { name: `Unlock ${name}'s account` })
}

function posts(answered) {
  return answered.filter((request) => request.method === 'POST')
}

function reads(answered, path) {
  return answered.filter((request) => request.method === 'GET' && request.path === path)
}

/** The row says the account is locked until `lock` ends, offers its Unlock button, and nothing else does. */
function expectLockedRow(user, lock) {
  const cell = accountCell(user.name)
  expect(cell.textContent).toContain(`Locked until ${timeOfDay(lock.locked_until)}`)
  const button = within(cell).getByRole('button', { name: `Unlock ${user.name}'s account` })
  expect(button.textContent).toBe('Unlock')
  expect(button.disabled).toBe(false)
}

function expectActiveRow(user) {
  const cell = accountCell(user.name)
  expect(cell.textContent).toBe('Active')
  expect(within(cell).queryByRole('button')).toBeNull()
}

/** Opens the confirmation for releasing `user`'s lock, and returns the dialogue. */
async function openUnlock(user) {
  fireEvent.click(await screen.findByRole('button', { name: `Unlock ${user.name}'s account` }))
  return screen.findByRole('dialog', { name: `Unlock ${user.name}'s account?` })
}

/** Opens the confirmation for `user` and confirms it. */
async function unlock(user) {
  const dialog = await openUnlock(user)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Unlock account' }))
}

describe('FR-03: the Account column says which accounts are locked', () => {
  it('shows a live lock as "Locked until" its end with an Unlock button named for the account, and "Active" for no lock and for a lock that has ended', async () => {
    serveRoles([
      listed(ADA),
      listed(JANE, JANE_LOCK),
      listed(ERIN),
      listed(SAM, { locked_until: minutesFromNow(-1), locked_at: minutesFromNow(-16), source_ip: '198.51.100.7' }),
    ])

    await screen.findByLabelText('Role for Jane Doe')
    expect(screen.getByRole('columnheader', { name: 'Account' })).toBeTruthy()

    expectLockedRow(JANE, JANE_LOCK)
    expectActiveRow(ERIN)
    // Its lock has ended, so it reads as unlocked, with nothing to release.
    expectActiveRow(SAM)
    expectActiveRow(ADA)
    const offered = screen.getAllByRole('button', { name: /^Unlock / })
    expect(offered).toHaveLength(1)
    expect(offered[0]).toBe(unlockButton(JANE.name))
  })

  it('says nothing about locks for a list that carries no lock, as a requester without release_account_locks is served', async () => {
    serveRoles([ADA, JANE, ERIN])

    await screen.findByLabelText('Role for Jane Doe')
    for (const user of [ADA, JANE, ERIN]) expect(accountCell(user.name).textContent).toBe('')
    expect(screen.queryByRole('button', { name: /^Unlock / })).toBeNull()
  })
})

describe("FR-03: the signed-in Administrator's own locked row", () => {
  it('shows the lock and that another administrator can unlock it, with no Unlock button on that row, where the list holds another Administrator', async () => {
    const adaLock = { locked_until: minutesFromNow(9), locked_at: minutesFromNow(-6), source_ip: '192.0.2.10' }
    serveRoles([listed(ADA, adaLock), listed(ABE), listed(JANE, JANE_LOCK)])

    await screen.findByLabelText('Role for Jane Doe')
    const own = accountCell(ADA.name)
    expect(own.textContent).toContain(`Locked until ${timeOfDay(adaLock.locked_until)}`)
    expect(own.textContent).toContain('Another administrator can unlock your account.')
    expect(within(own).queryByRole('button')).toBeNull()
    expect(unlockButton(ADA.name)).toBeNull()
    // The rule is the own row's: another locked account still offers its button.
    expectLockedRow(JANE, JANE_LOCK)
  })

  it('says when the lock ends, and promises no release, where the list holds no other Administrator', async () => {
    const adaLock = { locked_until: minutesFromNow(9), locked_at: minutesFromNow(-6), source_ip: '192.0.2.10' }
    serveRoles([listed(ADA, adaLock), listed(JANE, JANE_LOCK)])

    await screen.findByLabelText('Role for Jane Doe')
    const own = accountCell(ADA.name)
    expect(own.textContent).toContain(`Locked until ${timeOfDay(adaLock.locked_until)}`)
    // Nobody could release it: FR-03 forbids one's own, and there is no other Administrator
    // (the pre-PR security review, finding 2).
    expect(own.textContent).toContain(
      `No other administrator can unlock your account. It unlocks at ${timeOfDay(adaLock.locked_until)}.`,
    )
    expect(own.textContent).not.toContain('Another administrator can unlock your account.')
    expect(within(own).queryByRole('button')).toBeNull()
  })
})

describe('FR-03: Unlock asks first, and sends nothing until it is confirmed', () => {
  it("asks \"Unlock Jane Doe's account?\" with when and where the lock began, that the password is unchanged and to check who is asking, and sends nothing before Confirm or for Cancel", async () => {
    // Served, so a release sent too early would be answered rather than refused.
    const answered = serveRoles([listed(ADA), listed(JANE, JANE_LOCK), listed(ERIN)], {
      [UNLOCK_JANE]: { body: listed(JANE) },
    })

    const dialog = await openUnlock(JANE)
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(within(dialog).getByRole('heading').textContent).toBe("Unlock Jane Doe's account?")
    const body = dialog.textContent
    expect(body).toContain(
      `Locked at ${timeOfDay(JANE_LOCK.locked_at)} from 203.0.113.42, until ${timeOfDay(JANE_LOCK.locked_until)}.`,
    )
    expect(body).toMatch(/Their password is not changed\./)
    expect(body).toMatch(/Check that the request to unlock really comes from Jane Doe\./)
    expect(posts(answered)).toEqual([])

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(posts(answered)).toEqual([])
    expectLockedRow(JANE, JANE_LOCK)
    expect(screen.queryByText("Jane Doe's account is unlocked.")).toBeNull()
  })

  it('says only when the lock ends where the list has no record of when or from where it began', async () => {
    const oldLock = { locked_until: minutesFromNow(5), locked_at: null, source_ip: null }
    serveRoles([listed(ADA), listed(JANE, oldLock)])

    const dialog = await openUnlock(JANE)
    const lines = within(dialog).getAllByText(/^Locked /)
    expect(lines.map((line) => line.textContent)).toEqual([`Locked until ${timeOfDay(oldLock.locked_until)}.`])
    expect(dialog.textContent).not.toMatch(/Locked at|null|undefined/)
  })
})

describe("FR-03: the screen after the server's answer to an unlock", () => {
  it("on 200 sends one POST with no body, shows the row as Active without its button, and says \"Jane Doe's account is unlocked.\"", async () => {
    const answered = serveRoles([listed(ADA), listed(JANE, JANE_LOCK), listed(ERIN)], {
      [UNLOCK_JANE]: { body: listed(JANE) },
    })

    await unlock(JANE)

    await screen.findByText("Jane Doe's account is unlocked.")
    expect(screen.queryByRole('dialog')).toBeNull()
    expectActiveRow(JANE)
    expect(unlockButton(JANE.name)).toBeNull()
    expect(posts(answered).map((request) => [request.path, request.body])).toEqual([
      ['/api/users/user-jane/unlock', undefined],
    ])
    // From the reply, not from reading the list again.
    expect(reads(answered, '/api/users')).toHaveLength(1)
  })

  it('on 409 says the account is no longer locked and reads the list again', async () => {
    const answered = serveRoles(
      listThen([listed(ADA), listed(JANE, JANE_LOCK), listed(ERIN)], [listed(ADA), listed(JANE), listed(ERIN)]),
      { [UNLOCK_JANE]: { status: 409, body: { detail: 'This account is not locked.' } } },
    )

    await unlock(JANE)

    await screen.findByText('That account is no longer locked. The list has been reloaded.')
    await waitFor(() => expect(reads(answered, '/api/users')).toHaveLength(2))
    await waitFor(() => expectActiveRow(JANE))
    expect(unlockButton(JANE.name)).toBeNull()
    expect(posts(answered)).toHaveLength(1)
  })

  it('on 404 says the list is stale and reads it again', async () => {
    const answered = serveRoles(
      listThen([listed(ADA), listed(JANE, JANE_LOCK), listed(ERIN)], [listed(ADA), listed(ERIN)]),
      { [UNLOCK_JANE]: { status: 404, body: { detail: 'No User matches the given query.' } } },
    )

    await unlock(JANE)

    await screen.findByText(TEXT.roleChangeStale)
    await waitFor(() => expect(reads(answered, '/api/users')).toHaveLength(2))
    await waitFor(() => expect(rowFor(JANE.name)).toBeUndefined())
    expect(rowFor(ERIN.name)).toBeDefined()
    expect(posts(answered)).toHaveLength(1)
  })

  it('on 403 shows the not-permitted view in place of the table, and reads who is signed in again', async () => {
    const answered = serveRoles([listed(ADA), listed(JANE, JANE_LOCK), listed(ERIN)], {
      [UNLOCK_JANE]: { status: 403, body: { detail: 'You do not have permission to perform this action.' } },
    })

    await unlock(JANE)

    await screen.findByText('Not permitted')
    expect(screen.getByText('You do not have permission to view this page.')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
    await waitFor(() => expect(reads(answered, '/api/auth/me')).toHaveLength(2))
  })
})

describe('FR-03: a role change keeps the lock', () => {
  it("keeps a locked account's lock and its Unlock button through a role change, whose reply carries no lock", async () => {
    const answered = serveRoles([listed(ADA), listed(JANE, JANE_LOCK), listed(ERIN)], {
      'PATCH /api/users/user-jane/role': { body: { ...JANE, role: ROLES.administrator } },
    })

    await screen.findByLabelText('Role for Jane Doe')
    fireEvent.change(screen.getByLabelText('Role for Jane Doe'), { target: { value: 'role-administrator' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save role for Jane Doe' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Change role' }))

    await screen.findByText("Jane Doe's role is now Administrator.")
    expect(screen.getByLabelText('Role for Jane Doe').selectedOptions[0].textContent).toBe(ROLES.administrator)
    expectLockedRow(JANE, JANE_LOCK)
    expect(reads(answered, '/api/users')).toHaveLength(1)
  })
})

describe('FR-03: a lock that ends while the screen is open', () => {
  it("reads Active once a lock's end passes, and the next lock's in turn, without reading the list again", async () => {
    const erinLock = { locked_until: minutesFromNow(20), locked_at: minutesFromNow(5), source_ip: '198.51.100.7' }
    const answered = serveRoles([listed(ADA), listed(JANE, JANE_LOCK), listed(ERIN, erinLock)])

    await screen.findByRole('button', { name: "Unlock Jane Doe's account" })
    // The timer for the soonest lock is set by an effect React runs a task after the
    // table is drawn; a clock moved before it exists moves past nothing.
    await act(async () => {})
    expect(vi.getTimerCount(), "the soonest lock's timer is set").toBe(1)

    await act(async () => {
      vi.advanceTimersByTime(11 * 60 * 1000)
    })
    expectLockedRow(JANE, JANE_LOCK)

    await act(async () => {
      vi.advanceTimersByTime(61 * 1000)
    })
    expectActiveRow(JANE)
    expectLockedRow(ERIN, erinLock)

    await act(async () => {})
    expect(vi.getTimerCount(), "the next lock's timer is set").toBe(1)
    await act(async () => {
      vi.advanceTimersByTime(8 * 60 * 1000)
    })
    expectActiveRow(ERIN)
    expect(screen.queryByRole('button', { name: /^Unlock / })).toBeNull()
    expect(reads(answered, '/api/users')).toHaveLength(1)
  })
})
