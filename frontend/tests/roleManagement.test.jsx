/**
 * FR-05's role management screen: the clauses only the interface can satisfy.
 *
 * - "Admin-only screen listing all users assigned with their role."
 * - "Confirmation dialogue is shown before the role change is applied: 'Change Jane
 *   Doe's role to Admin?'."
 * - "Table updates in real time on confirmation."
 *
 * The fourth, "entirely hidden and inaccessible to non-admin roles (button and route
 * do not render)", is tests/accessDenied.test.jsx's, with FR-06's redirect. The server's
 * half (the 403 for an Employee, the refusal of an Administrator's own demotion, the
 * audit row, the role taking effect on the next request) is pytest's.
 *
 * The whole application is rendered at /admin/roles, signed in as an Administrator.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { ROLES } from '../src/constants.js'
import { serveApi } from './fakeApi.js'

const ADMINISTRATOR = {
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

/** `GET /api/roles`: ids the screen sends, names the users carry. */
const ROLE_LIST = [
  { role_id: 'role-employee', name: ROLES.employee, description: 'Default role', permissions: [] },
  { role_id: 'role-administrator', name: ROLES.administrator, description: 'Full management', permissions: [] },
]

function routes(extra = {}) {
  return {
    'GET /api/auth/me': { body: ADMINISTRATOR },
    'GET /api/users': { body: [ADMINISTRATOR, JANE, ERIN] },
    'GET /api/roles': { body: ROLE_LIST },
    ...extra,
  }
}

function renderRoles() {
  render(
    <MemoryRouter initialEntries={['/admin/roles']}>
      <App />
    </MemoryRouter>,
  )
}

/** The role a row shows, as its select displays it. */
function roleShownFor(name) {
  return screen.getByLabelText(`Role for ${name}`).selectedOptions[0].textContent
}

function choose(name, roleName) {
  const roleId = ROLE_LIST.find((role) => role.name === roleName).role_id
  fireEvent.change(screen.getByLabelText(`Role for ${name}`), { target: { value: roleId } })
}

function saveButton(name) {
  return screen.getByRole('button', { name: `Save role for ${name}` })
}

function patches(answered) {
  return answered.filter((request) => request.method === 'PATCH')
}

describe('FR-05: every user with their role, and a confirmation before any change', () => {
  it("lists every user with their role, asks \"Change Jane Doe's role to Administrator?\" before sending anything, and Cancel sends nothing", async () => {
    const answered = serveApi(routes())
    renderRoles()

    await screen.findByLabelText('Role for Jane Doe')
    const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(rows.map((row) => within(row).getByRole('rowheader').textContent)).toEqual([
      ADMINISTRATOR.name,
      JANE.name,
      ERIN.name,
    ])
    for (const user of [ADMINISTRATOR, JANE, ERIN]) {
      expect(roleShownFor(user.name)).toBe(user.role)
      expect(screen.getByText(user.email)).toBeTruthy()
      // Nothing to save until a different role is chosen.
      expect(saveButton(user.name).disabled).toBe(true)
    }

    choose(JANE.name, ROLES.administrator)
    expect(saveButton(JANE.name).disabled).toBe(false)
    fireEvent.click(saveButton(JANE.name))

    const dialog = await screen.findByRole('dialog')
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(within(dialog).getByRole('heading').textContent).toBe("Change Jane Doe's role to Administrator?")
    expect(patches(answered)).toEqual([])

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(patches(answered)).toEqual([])
    expect(screen.queryByText(/role is now/)).toBeNull()
  })

  it('on confirmation sends one PATCH carrying the role id, and the row shows the role the server stored without re-reading the list', async () => {
    const answered = serveApi(
      routes({ 'PATCH /api/users/user-jane/role': { body: { ...JANE, role: ROLES.administrator } } }),
    )
    renderRoles()

    await screen.findByLabelText('Role for Jane Doe')
    choose(JANE.name, ROLES.administrator)
    fireEvent.click(saveButton(JANE.name))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Change role' }))

    await screen.findByText("Jane Doe's role is now Administrator.")
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(roleShownFor(JANE.name)).toBe(ROLES.administrator)
    // Saved, so nothing is left to save on that row; the other rows are as they were.
    expect(saveButton(JANE.name).disabled).toBe(true)
    expect(roleShownFor(ERIN.name)).toBe(ROLES.employee)
    expect(patches(answered).map((request) => [request.path, request.body])).toEqual([
      ['/api/users/user-jane/role', { role_id: 'role-administrator' }],
    ])
    expect(answered.filter((request) => request.path === '/api/users')).toHaveLength(1)
  })
})

describe('FR-05: a change the server refuses', () => {
  it("refuses an Administrator's own demotion in words of its own, and puts the row back to the role it has", async () => {
    const answered = serveApi(
      routes({
        'PATCH /api/users/user-ada/role': {
          status: 403,
          body: { detail: 'You cannot remove your own Administrator role.' },
        },
      }),
    )
    renderRoles()

    await screen.findByLabelText('Role for Ada Administrator')
    choose(ADMINISTRATOR.name, ROLES.employee)
    fireEvent.click(saveButton(ADMINISTRATOR.name))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading').textContent).toBe("Change Ada Administrator's role to Employee?")
    fireEvent.click(within(dialog).getByRole('button', { name: 'Change role' }))

    // The client's own sentence, which says what to do instead; the server's detail
    // (apps/api/views.py SELF_DEMOTION_MESSAGE) is only its first half.
    const refusal = (await screen.findByText('Change refused')).closest('[role="alert"]')
    expect(refusal.textContent).toContain(
      'You cannot remove your own Administrator role. Ask another Administrator to change it for you.',
    )
    await waitFor(() => expect(roleShownFor(ADMINISTRATOR.name)).toBe(ROLES.administrator))
    // Still the table, not the not-permitted notice an Employee would get.
    expect(screen.queryByText('Not permitted')).toBeNull()
    expect(screen.getByRole('table')).toBeTruthy()
    expect(patches(answered)).toHaveLength(1)
  })
})
