/**
 * FR-01's registration screen: the clauses only the interface can satisfy.
 *
 * - "User fills a registration form — full name, email, password, confirm password."
 * - "Real-time password strength validation — password strength meter shown as user
 *   types … the submit button remains disabled until all client-side checks pass."
 * - "On success, the user is directed to the login page with a confirmation message."
 * - "On failure, (e.g., email already registered), an inline error message appears
 *   under the relevant field."
 *
 * The whole application is rendered at /register with the real auth provider, so the
 * redirect to /login and the notice it arrives with are the ones a user meets. The
 * server's own checks (the 400 and 409 it answers, bcrypt, the default role) are
 * pytest's; that the client's password rules equal the server's is
 * apps/accounts/tests/test_password_policy_agreement.py.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { TEXT } from '../src/constants.js'
import { serveApi } from './fakeApi.js'

/** No session: `GET /api/auth/me` answers 401, as for any visitor. */
const SIGNED_OUT = { 'GET /api/auth/me': { status: 401, body: { detail: 'Authentication credentials were not provided.' } } }

const VALID = {
  name: 'Jane Doe',
  email: 'jane.doe@company.com',
  password: 'Abcdefg1!',
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

function type(label, value) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

function createAccount() {
  return screen.getByRole('button', { name: 'Create account' })
}

/**
 * The requirements panel the password field is described by: the element its
 * aria-describedby names that is not its error message.
 */
function requirementsPanel() {
  const ids = screen.getByLabelText('Password').getAttribute('aria-describedby').split(' ')
  const panel = ids.filter((id) => !id.endsWith('-error')).map((id) => document.getElementById(id))
  expect(panel).toHaveLength(1)
  return panel[0]
}

/** Each rule's line as it reads to a screen reader: "Met: …" or "Not met: …". */
function ruleLines() {
  return within(requirementsPanel())
    .getAllByRole('listitem')
    .map((item) => item.textContent.replace(/^[✓–]/, ''))
}

/** The message rendered under a field, found through the field's own aria-describedby. */
function messageUnder(label) {
  const input = screen.getByLabelText(label)
  const ids = (input.getAttribute('aria-describedby') ?? '').split(' ').filter((id) => id.endsWith('-error'))
  return ids.map((id) => document.getElementById(id)?.textContent ?? '').join('')
}

function registrations(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/auth/register')
}

describe('FR-01: the form, its password meter and its gate', () => {
  it('shows each password rule met or unmet as the password is typed, and keeps Create account disabled until every client-side check passes', async () => {
    // Nothing answers the register route: a form that sent anything here fails the test.
    const answered = serveApi(SIGNED_OUT)
    renderApp('/register')

    // The four fields FR-01 names, the two passwords masked.
    await screen.findByLabelText('Full name')
    expect(screen.getByLabelText('Email').type).toBe('email')
    expect(screen.getByLabelText('Password').type).toBe('password')
    expect(screen.getByLabelText('Confirm password').type).toBe('password')
    expect(createAccount().disabled).toBe(true)

    // The meter follows each keystroke, rule by rule, and says its band in words.
    expect(requirementsPanel().textContent).toContain('Password strength: Not started. 0 of 4 requirements met.')
    type('Password', 'abc')
    expect(requirementsPanel().textContent).toContain('Password strength: Weak. 0 of 4 requirements met.')
    expect(ruleLines()).toEqual([
      'Not met: At least 8 characters',
      'Not met: At least 1 uppercase letter',
      'Not met: At least 1 number',
      'Not met: At least 1 special character, such as ! # ? or $ (a space does not count)',
    ])
    type('Password', 'Abcdefg1')
    expect(requirementsPanel().textContent).toContain('Password strength: Fair. 3 of 4 requirements met.')
    // A space is not a special character, to the meter or to the server.
    type('Password', 'Abcdefg1 ')
    expect(requirementsPanel().textContent).toContain('3 of 4 requirements met.')
    type('Password', VALID.password)
    expect(requirementsPanel().textContent).toContain('Password strength: Strong. 4 of 4 requirements met.')
    expect(ruleLines().every((line) => line.startsWith('Met: '))).toBe(true)

    // A strong password alone does not open the gate: every other check must pass.
    expect(createAccount().disabled).toBe(true)
    type('Full name', VALID.name)
    type('Email', VALID.email)
    expect(createAccount().disabled).toBe(true)
    type('Confirm password', 'Abcdefg1?')
    fireEvent.blur(screen.getByLabelText('Confirm password'))
    expect(createAccount().disabled).toBe(true)
    expect(messageUnder('Confirm password')).toContain('The two passwords do not match.')

    type('Confirm password', VALID.password)
    expect(createAccount().disabled).toBe(false)

    // Each check closes it again on its own.
    type('Email', 'jane.doe@')
    expect(createAccount().disabled).toBe(true)
    type('Email', VALID.email)
    type('Password', 'abcdefg1!')
    type('Confirm password', 'abcdefg1!')
    expect(createAccount().disabled).toBe(true)

    // Enter in a field submits the form without the button; that sends nothing either.
    fireEvent.submit(createAccount().closest('form'))
    expect(registrations(answered)).toEqual([])
  })

  it('on success, goes to the login page with a confirmation and the email filled in, having sent name, email and password only', async () => {
    const answered = serveApi({
      ...SIGNED_OUT,
      'POST /api/auth/register': {
        status: 201,
        body: { id: 'user-jane', name: VALID.name, email: VALID.email, role: 'Employee', created_at: '2026-11-02T09:00:00+11:00' },
      },
    })
    renderApp('/register')

    await screen.findByLabelText('Full name')
    type('Full name', `  ${VALID.name} `)
    type('Email', VALID.email)
    type('Password', VALID.password)
    type('Confirm password', VALID.password)
    fireEvent.click(createAccount())

    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
    expect(probe.location.pathname).toBe('/login')
    const confirmation = screen.getByText('Account created').closest('[role="status"]')
    expect(confirmation.textContent).toContain(TEXT.registered)
    expect(screen.getByLabelText('Email').value).toBe(VALID.email)
    expect(screen.getByLabelText('Password').value).toBe('')

    // The confirmation never leaves the browser, and the name is sent trimmed.
    expect(registrations(answered).map((request) => request.body)).toEqual([
      { name: VALID.name, email: VALID.email, password: VALID.password },
    ])
  })
})

describe('FR-01: a refusal is shown under the field it concerns', () => {
  it("puts a 409 under the email field and not in a banner, and a 400's message under its own field", async () => {
    const SERVER_409 = 'This email address is already registered.'
    let attempt = 0
    serveApi({
      ...SIGNED_OUT,
      'POST /api/auth/register': () => {
        attempt += 1
        if (attempt === 1) return { status: 409, body: { detail: SERVER_409 } }
        return { status: 400, body: { password: ['This password is too similar to the email address.'] } }
      },
    })
    renderApp('/register')

    await screen.findByLabelText('Full name')
    type('Full name', VALID.name)
    type('Email', VALID.email)
    type('Password', VALID.password)
    type('Confirm password', VALID.password)
    fireEvent.click(createAccount())

    // Under the email field, marked invalid, and in no banner above the form.
    await screen.findByText('That email address is already registered.')
    expect(screen.getByLabelText('Email').getAttribute('aria-invalid')).toBe('true')
    expect(messageUnder('Email')).toContain('That email address is already registered.')
    expect(screen.queryByText('Could not create your account')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    // The client's fixed text, never the server's prose.
    expect(document.body.textContent).not.toContain(SERVER_409)
    expect(probe.location.pathname).toBe('/register')
    expect(screen.getByLabelText('Full name').value).toBe(VALID.name)

    // Editing the address withdraws the message about the address that was refused.
    type('Email', 'jane.d@company.com')
    expect(screen.getByLabelText('Email').getAttribute('aria-invalid')).toBeNull()
    expect(messageUnder('Email')).toBe('')

    fireEvent.click(createAccount())
    await screen.findByText('This password is too similar to the email address.')
    expect(messageUnder('Password')).toContain('This password is too similar to the email address.')
    expect(messageUnder('Email')).toBe('')
    expect(screen.queryByText('Could not create your account')).toBeNull()
  })
})
