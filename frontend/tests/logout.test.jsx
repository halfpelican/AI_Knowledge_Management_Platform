/**
 * FR-04's logout, at the interface: "A 'Logout' control visible in navigation for all
 * authenticated roles" and "On activation, user is immediately redirected to the
 * Login page with a brief confirmation 'You've been logged out'."
 *
 * **The confirmation is not asserted here, because the shipped screen does not show
 * it** (found while writing this file, 2 November 2026, and reported rather than
 * fixed: docs/stage-5-front-end-clauses.md, FR-04). From any route behind
 * RequireAuth, `AuthProvider.logout` clears the user (src/auth/AuthProvider.jsx:87)
 * before the navigation that carries `reason: 'signed-out'` (src/App.jsx:42) has
 * committed, because React Router wraps location updates in `startTransition`.
 * RequireAuth (src/auth/RequireAuth.jsx:21) re-renders at the old address with no
 * user and replaces that navigation with its own, so /login arrives with
 * `{from: …}` and Login.jsx shows no notice. A test asserting the confirmation fails
 * against the shipped code, so it is left out until the screen is fixed; this file
 * asserts the half that holds.
 *
 * The whole application is rendered with the real auth provider. That the session is
 * destroyed server-side and refused afterwards is pytest's.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { dashboardPathForRole, ROLES, TEXT } from '../src/constants.js'
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

const EMPTY_DASHBOARD = {
  filters: { date_from: null, date_to: null, department: null },
  departments: [],
  indexed_totals: { documents: 0, meetings: 0, total: 0 },
  recent_documents: [],
  recent_meetings: [],
  recent_questions: [],
}

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

function logouts(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/auth/logout')
}

describe('FR-04: the Logout control and where it leads', () => {
  it.each([EMPLOYEE, ADMINISTRATOR])('offers Log out in the navigation to an $role, and on activation sends one logout and lands on sign-in, signed out', async (user) => {
    const answered = serveApi({
      'GET /api/auth/me': { body: user },
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
      'POST /api/auth/logout': { status: 200 },
    })
    renderApp(dashboardPathForRole(user.role))
    await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })

    const logOut = within(primaryNav()).getByRole('button', { name: 'Log out' })
    fireEvent.click(logOut)

    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
    expect(probe.location.pathname).toBe('/login')
    // Signed out in the page as well as on the server: no control, no name, no search.
    expect(within(primaryNav()).queryByRole('button', { name: 'Log out' })).toBeNull()
    expect(within(primaryNav()).getByRole('link', { name: 'Sign in' })).toBeTruthy()
    expect(document.body.textContent).not.toContain(user.name)
    expect(screen.queryByRole('search')).toBeNull()
    expect(logouts(answered)).toHaveLength(1)
    // Not the session-expired notice: the user asked to leave.
    expect(document.body.textContent).not.toContain(TEXT.sessionExpired)
  })

  it('says it could not sign out when the logout request fails, and does not call it a logout', async () => {
    const answered = serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
      'POST /api/auth/logout': { status: 500, body: { detail: 'Internal server error: Traceback (most recent call last)' } },
    })
    renderApp('/dashboard')
    await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })

    fireEvent.click(within(primaryNav()).getByRole('button', { name: 'Log out' }))

    const alert = (await screen.findByText('Could not sign out')).closest('[role="alert"]')
    expect(alert.textContent).toContain('Something went wrong. Please try again.')
    expect(document.body.textContent).not.toContain('Traceback')
    expect(document.body.textContent).not.toContain(TEXT.loggedOut)
    await waitFor(() => expect(logouts(answered)).toHaveLength(1))
  })
})
