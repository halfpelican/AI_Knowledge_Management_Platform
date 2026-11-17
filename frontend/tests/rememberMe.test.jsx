/**
 * D-137's "Remember me" on FR-02's sign-in: the clauses only the interface can satisfy.
 *
 * - **What the sign-in sends** (docs/api-contract.md, "FR-04 — account self-service"):
 *   ticked, `remember: true`; unticked, nothing that asks for the seven days. The
 *   contract makes `remember` optional and false when absent, and calls an unticked
 *   sign-in "a sign-in without `remember`", so the page sends none.
 * - **It is controlled:** the box shows what the page will send, it starts unticked, and
 *   a failed attempt leaves it as it was, as it leaves the address.
 * - **Its hint is honest:** it says the session on this device lasts until it goes
 *   REMEMBERED_SESSION_DAYS without use, and that the box is not for a shared computer.
 *   The checkbox is described by the hint and named by #119's label alone.
 *
 * What the server does with `remember` (seven days, sliding with use, both roles) is
 * pytest's, apps/api/tests/test_fr04_remember_me.py. That the client's seven equals the
 * server's is apps/api/tests/test_front_end_constants_agreement.py.
 *
 * The whole application is rendered at /login with the real auth provider, mocked at
 * `fetch` through tests/fakeApi.js.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { REMEMBERED_SESSION_DAYS, ROLES, SIGN_IN_TEXT, TEXT } from '../src/constants.js'
import { serveApi } from './fakeApi.js'

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
  picture: null,
}

const ADMINISTRATOR = {
  id: 'user-administrator',
  name: 'Ada Administrator',
  email: 'ada@example.com',
  role: ROLES.administrator,
  created_at: '2026-09-12T10:00:00+10:00',
  picture: null,
}

const PASSWORD = 'Correct-Horse-1'

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

/** Login's 401, the same for an unknown address and a wrong password (D-02). */
const INVALID = { status: 401, body: { detail: 'Invalid email or password.' } }

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

function renderLogin() {
  probe.location = null
  render(
    <MemoryRouter initialEntries={['/login']}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  )
}

/**
 * Signed out, and `user` signed in by whichever attempt `replies` lets through: each
 * attempt takes the next reply, and an attempt past the list is a success.
 */
function serveSignIn(user, replies = []) {
  let signedIn = false
  let attempt = 0
  return serveApi({
    'GET /api/auth/me': () => (signedIn ? { body: user } : NOT_SIGNED_IN),
    'POST /api/auth/login': () => {
      const reply = replies[attempt]
      attempt += 1
      if (reply) return reply
      signedIn = true
      return { body: user }
    },
    // FR-03: after a failed attempt the page asks for the running lockout policy (D-130).
    'GET /api/auth/lockout-policy': { body: { lockout_threshold: 5, lockout_duration_seconds: 900 } },
    'GET /api/dashboard': { body: EMPTY_DASHBOARD },
  })
}

function rememberBox() {
  return screen.getByRole('checkbox', { name: 'Remember me on this device' })
}

async function fillIn(email) {
  fireEvent.change(await screen.findByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: PASSWORD } })
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

/** The body of every sign-in the page sent, in order. */
function signIns(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/auth/login').map((request) => request.body)
}

describe('D-137: the "Remember me" checkbox and its hint', () => {
  it('is an unticked checkbox named by #119\'s label alone, described by a hint that names the days without use and the shared computer', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderLogin()
    await screen.findByRole('heading', { level: 1, name: 'Sign in' })

    const box = rememberBox()
    expect(box.type).toBe('checkbox')
    expect(box.checked).toBe(false)

    // Described by the hint, and by nothing else.
    const described = (box.getAttribute('aria-describedby') ?? '').split(/\s+/).filter(Boolean)
    expect(described).toHaveLength(1)
    const hint = document.getElementById(described[0])
    expect(hint.textContent).toBe(SIGN_IN_TEXT.rememberHint)
    expect(hint.textContent).toContain(`${REMEMBERED_SESSION_DAYS} days without use`)
    expect(hint.textContent).toContain('on this device')
    expect(hint.textContent).toContain('Do not tick it on a shared computer.')
    // The hint is on screen, not only in the accessibility tree, and is not part of
    // the label: the box keeps #119's name exactly.
    expect(hint.closest('label')).toBeNull()
    expect(hint.classList.contains('visually-hidden')).toBe(false)
    // #119's email hint is kept.
    expect(screen.getByText("We'll use this to sign you in.")).toBeTruthy()
  })
})

describe('D-137: the sign-in sends the box as it is', () => {
  it.each([
    { user: EMPLOYEE, landing: '/dashboard' },
    { user: ADMINISTRATOR, landing: '/admin' },
  ])('sends remember: true when the box is ticked, as $user.role, and lands on $landing', async ({ user, landing }) => {
    const answered = serveSignIn(user)
    renderLogin()

    await fillIn(user.email)
    fireEvent.click(rememberBox())
    // Controlled: the box shows the state the page will send.
    expect(rememberBox().checked).toBe(true)
    submit()

    expect(await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })).toBeTruthy()
    await waitFor(() => expect(probe.location.pathname).toBe(landing))
    expect(signIns(answered)).toEqual([{ email: user.email, password: PASSWORD, remember: true }])
  })

  it.each([
    { how: 'left unticked', clicks: 0 },
    { how: 'ticked and then unticked', clicks: 2 },
  ])('asks for no remembered session when the box is $how', async ({ clicks }) => {
    const answered = serveSignIn(EMPLOYEE)
    renderLogin()

    await fillIn(EMPLOYEE.email)
    for (let click = 0; click < clicks; click += 1) fireEvent.click(rememberBox())
    expect(rememberBox().checked).toBe(false)
    submit()

    await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })
    const [body] = signIns(answered)
    expect(signIns(answered)).toHaveLength(1)
    expect(body.email).toBe(EMPLOYEE.email)
    expect(body.password).toBe(PASSWORD)
    // Absent, or false: either is FR-04's 60 minutes (the contract). Never true.
    expect(body.remember ?? false).toBe(false)
  })

  it('keeps the box ticked through a failed attempt, so the next attempt still asks to be remembered', async () => {
    const answered = serveSignIn(EMPLOYEE, [INVALID])
    renderLogin()

    await fillIn(EMPLOYEE.email)
    fireEvent.click(rememberBox())
    submit()

    // The 401's banner, the password cleared as ever, and the box as the person left it.
    await screen.findByText('Could not sign in')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' }).disabled).toBe(false))
    expect(screen.getByLabelText('Password').value).toBe('')
    expect(rememberBox().checked).toBe(true)

    fireEvent.change(screen.getByLabelText('Password'), { target: { value: PASSWORD } })
    submit()

    await screen.findByRole('heading', { level: 1, name: TEXT.dashboardHeading })
    expect(signIns(answered)).toEqual([
      { email: EMPLOYEE.email, password: PASSWORD, remember: true },
      { email: EMPLOYEE.email, password: PASSWORD, remember: true },
    ])
  })
})
