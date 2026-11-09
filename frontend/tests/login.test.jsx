/**
 * FR-02's sign-in screen: "Where the account is locked and the submitted password was
 * correct, a distinct message is shown", beside the "invalid email or password"
 * banner it has to be distinct from, and the success it contrasts with: "On success,
 * user is redirected to a role-specific dashboard".
 *
 * Whether the password was correct is the server's to decide: it answers 401 for a
 * wrong password whether or not the account is locked, and 403 `account_locked` only
 * for a locked account given the right one (FR-03's messaging rule, pytest's). What
 * only the screen can get right is that the two answers read differently, that
 * neither discloses the account, and where a success lands.
 *
 * Item 10's early audit (9 November, finding 2) added FR-02's two interface
 * clauses: "On submit, 'Login' button disables and shows a loading indicator,
 * preventing a second submission", observed with the login route held open, and
 * the "'Show password' toggle icon", which tabOrder.test.jsx had only as a tab
 * stop.
 *
 * The whole application is rendered with the real auth provider.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { ROLES, TEXT } from '../src/constants.js'
import { heldResponse, serveApi } from './fakeApi.js'

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

/** FR-02's banner text, written out so a change to it fails here. */
const INVALID_CREDENTIALS = 'Invalid email or password.'

/** The server's 403 body (apps/api/views.py ACCOUNT_LOCKED_MESSAGE and its code). */
const LOCKED = {
  status: 403,
  body: {
    detail: 'This account is temporarily locked after repeated failed sign-ins. Please try again later.',
    code: 'account_locked',
  },
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

async function signIn(email, password) {
  fireEvent.change(await screen.findByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

/** The banner the last attempt produced, once it is on screen. */
async function signInBanner() {
  return (await screen.findByText('Could not sign in')).closest('[role="alert"]')
}

/** Every login attempt the screen actually sent, in order. */
function logins(answered) {
  return answered.filter((request) => request.path === '/api/auth/login')
}

describe('FR-02: a locked account is told so, distinctly', () => {
  it('shows the invalid-credentials banner for a 401 and a different, locked-account message for the 403, disclosing nothing and staying on sign-in', async () => {
    let attempt = 0
    const answered = serveApi({
      'GET /api/auth/me': NOT_SIGNED_IN,
      'POST /api/auth/login': () => {
        attempt += 1
        return attempt === 1 ? { status: 401, body: { detail: INVALID_CREDENTIALS } } : LOCKED
      },
    })
    renderApp('/login')

    await signIn(EMPLOYEE.email, 'Wrong-Horse-1')
    const first = await signInBanner()
    expect(first.textContent).toContain(INVALID_CREDENTIALS)
    expect(first.textContent).not.toMatch(/locked/i)

    // The same address with the right password, on an account the server says is locked.
    await signIn(EMPLOYEE.email, 'Correct-Horse-1')
    await screen.findByText(TEXT.accountLocked)
    const second = await signInBanner()
    expect(second.textContent).toMatch(/locked/i)
    expect(second.textContent).not.toContain(INVALID_CREDENTIALS)
    // The client's own sentence, never the server's prose, and no account detail.
    expect(document.body.textContent).not.toContain(LOCKED.body.detail)
    expect(second.textContent).not.toContain(EMPLOYEE.email)

    // No session came of it: still signing in, the password cleared, /me not re-read.
    expect(probe.location.pathname).toBe('/login')
    expect(screen.getByLabelText('Password').value).toBe('')
    expect(screen.queryByRole('button', { name: 'Log out' })).toBeNull()
    expect(answered.filter((request) => request.path === '/api/auth/me')).toHaveLength(1)
  })

  it.each([
    { user: EMPLOYEE, landing: '/dashboard' },
    { user: ADMINISTRATOR, landing: '/admin' },
  ])('signs an unlocked $user.role in with the right password and lands on $landing', async ({ user, landing }) => {
    let signedIn = false
    const answered = serveApi({
      'GET /api/auth/me': () => (signedIn ? { body: user } : NOT_SIGNED_IN),
      'POST /api/auth/login': () => {
        signedIn = true
        return { body: user }
      },
      'GET /api/dashboard': { body: EMPTY_DASHBOARD },
    })
    renderApp('/login')

    await signIn(user.email, 'Correct-Horse-1')

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })).toBeTruthy()
    expect(probe.location.pathname).toBe(landing)
    expect(screen.queryByText('Could not sign in')).toBeNull()
    expect(answered.filter((request) => request.path === '/api/auth/login').map((request) => request.body)).toEqual([
      { email: user.email, password: 'Correct-Horse-1' },
    ])
  })
})

describe("FR-02: on submit, the 'Login' button disables and shows a loading indicator", () => {
  it('disables the button and shows the loading state in flight, so a second click sends no second POST, and recovers when the answer lands', async () => {
    const attempt = heldResponse()
    const answered = serveApi({
      'GET /api/auth/me': NOT_SIGNED_IN,
      'POST /api/auth/login': attempt.route,
    })
    renderApp('/login')

    await signIn(EMPLOYEE.email, 'Correct-Horse-1')

    // In flight: the button is disabled and busy, its label says what is
    // happening, and the spinner is drawn. (jsdom applies no stylesheet, so
    // what is asserted is the spinner element and the busy state, not the
    // animation.) The enabled "Sign in" button is gone, not merely restyled.
    const busy = await screen.findByRole('button', { name: 'Signing in…' })
    expect(busy.disabled).toBe(true)
    expect(busy.getAttribute('aria-busy')).toBe('true')
    expect(busy.querySelector('.btn__spinner')).not.toBeNull()
    expect(screen.queryByRole('button', { name: 'Sign in' })).toBeNull()
    expect(logins(answered)).toHaveLength(1)

    // "…preventing a second submission": the click the disable exists to stop.
    fireEvent.click(busy)
    expect(logins(answered)).toHaveLength(1)

    attempt.release({ status: 401, body: { detail: INVALID_CREDENTIALS } })

    // Recovered: the answer's banner is up, and the button is back, enabled and
    // quiet, having sent exactly one request for the whole exchange.
    const banner = await signInBanner()
    expect(banner.textContent).toContain(INVALID_CREDENTIALS)
    const recovered = screen.getByRole('button', { name: 'Sign in' })
    expect(recovered.disabled).toBe(false)
    expect(recovered.getAttribute('aria-busy')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Signing in…' })).toBeNull()
    expect(logins(answered)).toHaveLength(1)
  })
})

describe("FR-02: the 'Show password' toggle", () => {
  it('starts hidden, reveals what was typed on press and re-hides it, holding the value and carrying the state in aria-pressed', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderApp('/login')

    const password = await screen.findByLabelText('Password')
    expect(password.type).toBe('password')
    fireEvent.change(password, { target: { value: 'Correct-Horse-1' } })

    // A toggle button with a constant accessible name; aria-pressed carries the
    // state (PasswordInput.jsx — a label that flipped to "Hide" would contradict
    // it). Not pressed while the password is hidden.
    const toggle = screen.getByRole('button', { name: 'Show password', pressed: false })

    fireEvent.click(toggle)
    expect(password.type).toBe('text')
    expect(toggle.getAttribute('aria-pressed')).toBe('true')
    expect(password.value).toBe('Correct-Horse-1')

    fireEvent.click(toggle)
    expect(password.type).toBe('password')
    expect(toggle.getAttribute('aria-pressed')).toBe('false')
    // The same input, the value held across both flips: nothing was re-typed
    // and nothing was lost.
    expect(password.value).toBe('Correct-Horse-1')
    expect(screen.getByLabelText('Password')).toBe(password)

    // A button, not a submit: toggling never sent the form anywhere. No POST
    // route is served, so an accidental submission would also be refused and
    // recorded by tests/setup.js.
    expect(screen.queryByText('Could not sign in')).toBeNull()
  })
})
