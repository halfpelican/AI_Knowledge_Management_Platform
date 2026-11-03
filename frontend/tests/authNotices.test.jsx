/**
 * What the sign-in page says, and where signing in leads, when the user arrives there
 * from a guarded route. Three symptoms of one race, each from the user's side.
 *
 * 1. FR-04 Front-End: "On activation, user is immediately redirected to the Login page
 *    with a brief confirmation 'You've been logged out'."
 * 2. A request answering 401 mid-session sends the user to sign in with the
 *    session-expired notice (src/auth/AuthProvider.jsx, its docstring and its
 *    `onUnauthorized` listener).
 * 3. Signing in after being sent to sign-in from a guarded route lands on that route:
 *    "A guarded route the user was sent away from still wins, so they land where they
 *    were going" (src/pages/Login.jsx, the success branch).
 *
 * **The race.** Each path clears or sets the signed-in user and navigates in the same
 * breath. React Router 7 applies a navigation inside `startTransition`, so the user
 * change renders first, at the old address, and a redirect rendered there (RequireAuth's
 * to /login, or Login's own to /) replaces the navigation that carried the notice or the
 * destination. Found at post-M6 step 6 (docs/stage-5-front-end-clauses.md, defects 1-3),
 * confirmed by the user in a browser on the alpha on 3 November 2026, and fixed under
 * D-97 with these tests.
 *
 * The fix puts sign-out in one place (AuthProvider's `signOut`), so the last two
 * describes hold the paths around it: a logout the server answers with something other
 * than 200, and a signed-in user opening /login.
 *
 * The whole application is rendered with the real auth provider and the real guards,
 * at a guarded route, and every request is answered through tests/fakeApi.js.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

const EMPTY_DASHBOARD = {
  filters: { date_from: null, date_to: null, department: null },
  departments: [],
  indexed_totals: { documents: 0, meetings: 0, total: 0 },
  recent_documents: [],
  recent_meetings: [],
  recent_questions: [],
}

/** The address bar, as the probe below last saw it. */
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

/** The notice under `title` on the sign-in page, once it is on screen. */
async function signInNotice(title) {
  await screen.findByRole('heading', { level: 1, name: 'Sign in' })
  let notice = null
  await waitFor(() => {
    notice = screen.getByText(title).closest('[role="status"], [role="alert"]')
    expect(notice).not.toBeNull()
  })
  return notice
}

describe('FR-04: logging out from a guarded route', () => {
  it.each([EMPLOYEE, ADMINISTRATOR])(
    'shows an $role the "Logged out" confirmation on the sign-in page',
    async (user) => {
      serveApi({
        'GET /api/auth/me': { body: user },
        'GET /api/dashboard': { body: EMPTY_DASHBOARD },
        'POST /api/auth/logout': { status: 200 },
      })
      renderApp(dashboardPathForRole(user.role))
      await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })

      fireEvent.click(within(primaryNav()).getByRole('button', { name: 'Log out' }))

      const notice = await signInNotice('Logged out')
      expect(notice.getAttribute('role')).toBe('status')
      expect(notice.textContent).toContain(TEXT.loggedOut)
      expect(document.body.textContent).not.toContain(TEXT.sessionExpired)
      expect(within(primaryNav()).queryByRole('button', { name: 'Log out' })).toBeNull()
    },
  )

  it('keeps the "Logged out" confirmation, at /login, once the sign-in page has settled', async () => {
    serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
      'POST /api/auth/logout': { status: 200 },
    })
    renderApp('/dashboard')
    await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })

    fireEvent.click(within(primaryNav()).getByRole('button', { name: 'Log out' }))
    await signInNotice('Logged out')

    // The check above passes the moment the notice is first drawn. Let every effect the
    // sign-in page scheduled run, then look again: a notice drawn once and then cleared
    // is the brief confirmation FR-04 asks for in no useful sense.
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)))
    expect(screen.getByText('Logged out').closest('[role="status"]').textContent).toContain(TEXT.loggedOut)
    expect(probe.location.pathname).toBe('/login')
  })
})

describe('a session that expires on a guarded route', () => {
  it('shows the "Session expired" notice on the sign-in page when a request answers 401', async () => {
    serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
      // The session has gone on the server since the dashboard loaded.
      'GET /api/documents/browse': NOT_SIGNED_IN,
    })
    renderApp('/dashboard')
    await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })

    fireEvent.click(within(primaryNav()).getByRole('link', { name: 'Documents' }))

    const notice = await signInNotice('Session expired')
    expect(notice.getAttribute('role')).toBe('alert')
    expect(notice.textContent).toContain(TEXT.sessionExpired)
    expect(document.body.textContent).not.toContain(TEXT.loggedOut)
    expect(within(primaryNav()).queryByRole('button', { name: 'Log out' })).toBeNull()
  })
})

describe('signing in after being sent to sign in from a guarded route', () => {
  it('lands on the route the user was sent from, not on the dashboard', async () => {
    let signedIn = false
    const answered = serveApi({
      'GET /api/auth/me': () => (signedIn ? { body: EMPLOYEE } : NOT_SIGNED_IN),
      'POST /api/auth/login': () => {
        signedIn = true
        return { body: EMPLOYEE }
      },
      // Answered, so that landing on the dashboard fails on where the user is rather
      // than on an unexpected request.
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
      'GET /api/meetings': { body: [] },
      'GET /api/users/directory': { body: [] },
    })
    renderApp('/meetings')

    // Sent to sign in, with nothing of the meetings screen read.
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: EMPLOYEE.email } })
    expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Correct-Horse-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    // Signed in, on the meetings screen, which stays and loads its list.
    await waitFor(() => expect(within(primaryNav()).getByRole('button', { name: 'Log out' })).toBeTruthy())
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Meeting transcripts'))
    await screen.findByText(TEXT.noMeetings)
    expect(probe.location.pathname).toBe('/meetings')
    expect(answered.filter((request) => request.path === '/api/dashboard')).toEqual([])
  })
})

describe('FR-04: a logout the server answers with something other than 200', () => {
  it('says "Could not sign out" for a 5xx, and does not call it a logout', async () => {
    serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
      'POST /api/auth/logout': { status: 500, body: { detail: 'Internal server error' } },
    })
    renderApp('/dashboard')
    await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })

    fireEvent.click(within(primaryNav()).getByRole('button', { name: 'Log out' }))

    const alert = (await screen.findByText('Could not sign out')).closest('[role="alert"]')
    expect(alert.textContent).toContain('Something went wrong. Please try again.')
    expect(alert.textContent).not.toContain('Internal server error')
    expect(screen.queryByText('Logged out')).toBeNull()
    expect(document.body.textContent).not.toContain(TEXT.loggedOut)
  })

  it('counts a 401 as already signed out, and shows "Logged out", not an error or the expiry notice', async () => {
    serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
      // The session had already gone on the server when Log out was pressed.
      'POST /api/auth/logout': NOT_SIGNED_IN,
    })
    renderApp('/dashboard')
    await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })

    fireEvent.click(within(primaryNav()).getByRole('button', { name: 'Log out' }))

    const notice = await signInNotice('Logged out')
    expect(notice.textContent).toContain(TEXT.loggedOut)
    expect(screen.queryByText('Could not sign out')).toBeNull()
    expect(screen.queryByText('Session expired')).toBeNull()
  })
})

describe('FR-02: a signed-in user who opens /login', () => {
  it.each([
    { user: EMPLOYEE, landing: '/dashboard' },
    { user: ADMINISTRATOR, landing: '/admin' },
  ])("sends an $user.role to $landing, the role's dashboard", async ({ user, landing }) => {
    serveApi({
      'GET /api/auth/me': { body: user },
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
    })
    renderApp('/login')

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })).toBeTruthy()
    expect(probe.location.pathname).toBe(landing)
    expect(screen.queryByRole('heading', { level: 1, name: 'Sign in' })).toBeNull()
  })
})
