/**
 * FR-06's interface half, and FR-05's "entirely hidden and inaccessible to non-admin
 * roles (button and route do not render)".
 *
 * - FR-06: "UI elements (buttons, menu items, routes) are conditionally rendered based
 *   on the role embedded in the user's session token."
 * - FR-06: "Unauthorised navigation attempts (e.g., manually typing an admin URL)
 *   redirect to a '403 – Access Denied' page."
 *
 * Usability only, and these tests claim nothing more: the server refuses an Employee
 * on every protected route whatever the interface shows (CLAUDE.md §6, invariant 4),
 * and that is pytest's dual-role matrix. What is defended here is that the screen
 * neither offers an Employee the admin screen nor renders it when its address is
 * typed, and that the 403 page says nothing about what was asked for.
 *
 * The whole application is rendered with the real auth provider and the real guards
 * (src/auth/RequireAuth.jsx, src/auth/RequireRole.jsx).
 */
import { render, screen, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { ROLES } from '../src/constants.js'
import { serveApi } from './fakeApi.js'

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

const ADMINISTRATOR = {
  id: 'user-administrator',
  name: 'Ada Administrator',
  email: 'ada@example.com',
  role: ROLES.administrator,
  created_at: '2026-09-12T10:00:00+10:00',
}

/** FR-06's page title, written out so a change to it fails here. */
const ACCESS_DENIED = '403 – Access Denied'

/** The router's current location, as the probe below last saw it. */
const probe = { location: null }

function LocationProbe() {
  const location = useLocation()
  // A layout effect, so the location is current before a `findBy…` waiting on the
  // same commit resolves (a passive effect runs a task later).
  useLayoutEffect(() => {
    probe.location = location
  })
  return null
}

function renderApp(path) {
  probe.location = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  )
}

function primaryNav() {
  return screen.getByRole('navigation', { name: 'Primary' })
}

describe('FR-05, FR-06: the role management screen is an Administrator\'s only', () => {
  it('offers an Employee no Role management link, and sends one who types /admin/roles to the 403 page without reading the user list', async () => {
    // Nothing answers /api/users or /api/roles: had the screen rendered, its reads
    // would reach tests/setup.js's refusal and fail this test whatever it asserted.
    const answered = serveApi({ 'GET /api/auth/me': { body: EMPLOYEE } })
    renderApp('/admin/roles')

    expect(await screen.findByRole('heading', { level: 1, name: ACCESS_DENIED })).toBeTruthy()
    expect(probe.location.pathname).toBe('/403')
    // Signed in, and offered no way to the screen.
    expect(within(primaryNav()).getByRole('button', { name: 'Log out' })).toBeTruthy()
    expect(within(primaryNav()).queryByRole('link', { name: 'Role management' })).toBeNull()
    // The page says only that permission is lacking: not which screen, not whether it exists.
    const main = screen.getByRole('main')
    expect(main.textContent).toContain('You do not have permission to view this page.')
    expect(main.textContent).not.toMatch(/role management|admin\/roles|users/i)
    expect(document.body.textContent).not.toMatch(/role management/i)
    expect(within(main).getByRole('link', { name: 'Return to the home page' }).getAttribute('href')).toBe('/')
    expect(answered.map((request) => request.path)).toEqual(['/api/auth/me'])
  })

  it('offers an Administrator the Role management link, and renders the screen at /admin/roles', async () => {
    const answered = serveApi({
      'GET /api/auth/me': { body: ADMINISTRATOR },
      'GET /api/users': { body: [ADMINISTRATOR, EMPLOYEE] },
      'GET /api/roles': {
        body: [
          { role_id: 'role-employee', name: ROLES.employee, description: '', permissions: [] },
          { role_id: 'role-administrator', name: ROLES.administrator, description: '', permissions: [] },
        ],
      },
    })
    renderApp('/admin/roles')

    expect(await screen.findByRole('heading', { level: 1, name: 'Role management' })).toBeTruthy()
    await screen.findByLabelText(`Role for ${EMPLOYEE.name}`)
    expect(probe.location.pathname).toBe('/admin/roles')
    expect(within(primaryNav()).getByRole('link', { name: 'Role management' }).getAttribute('href')).toBe('/admin/roles')
    expect(screen.queryByRole('heading', { name: ACCESS_DENIED })).toBeNull()
    expect(answered.filter((request) => request.path === '/api/users')).toHaveLength(1)
  })

  it('sends a visitor with no session to sign in, not to the 403 page', async () => {
    // No session is the server's 401, not its 403, and the screen keeps the same split.
    serveApi({ 'GET /api/auth/me': { status: 401, body: { detail: 'Authentication credentials were not provided.' } } })
    renderApp('/admin/roles')

    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
    expect(probe.location.pathname).toBe('/login')
    expect(screen.queryByRole('heading', { name: ACCESS_DENIED })).toBeNull()
  })
})
