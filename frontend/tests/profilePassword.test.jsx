/**
 * #119's password change on the Profile page, wired to D-137's
 * `POST /api/auth/change-password` (docs/api-contract.md, "FR-04 — account
 * self-service", "Changing one's own password").
 *
 * What is defended here, each a clause only the page can satisfy:
 *
 * - **FR-01's client-side rules, as registration applies them.** "The submit button
 *   remains disabled until all client-side checks pass", with the requirements panel
 *   shown as the user types. #119 had its own rule, eight characters, which let a
 *   password through that the server's validators then refused.
 * - **One change at a time (the contract's CHG-3).** "The page keeps its submit
 *   disabled, and sends nothing else, until the change has answered": a request sent
 *   with the session key the change replaces, and answered after it, would sign the
 *   user out.
 * - **Each 400's field errors under their fields**, `current_password`'s included:
 *   the server never answers a wrong current password with a 401, so the page keeps
 *   the user signed in and says so under the field.
 * - **The 429 and the 200**, in the page's words: the contract's 200 message, and a
 *   rate limit that left the password as it was.
 * - **A logout waits for a change in flight (LOG-1, the security review of PR #119).**
 *   The change gives the session a new key once its password hashes are done, whether
 *   or not the old key was logged out meanwhile, and its 200 sets the new key's cookie.
 *   So Log out, pressed in the header while the change is in flight, sends nothing
 *   until the change has answered, whatever the answer, and then one logout, which
 *   carries the new cookie and destroys that session. Sent at once, it would end only
 *   the old key: "You've been logged out" would show over a browser left signed in.
 *
 * What is not: the server's rules (the validators, the equal-password check, which
 * sessions end), which are pytest's; and whether anything can be seen, which
 * tests/tabOrder.test.jsx reads from the stylesheets. Nor a Log out pressed in another
 * tab, which shares the cookie but not this page's state.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PROFILE_TEXT, TEXT, VALIDATION } from '../src/constants.js'
import { heldResponse } from './fakeApi.js'
import { BOTH_ROLES, EMPLOYEE, renderApp, requested, serveSignedIn } from './routeWalk.jsx'

const CURRENT = 'Old-password-1'
const NEW = 'New-password-2!'
const PICTURE = '/api/users/user-employee/picture?v=1794823200123456'

function field(label) {
  return screen.getByLabelText(label)
}

function type(label, value) {
  fireEvent.change(field(label), { target: { value } })
}

/** The message shown under a field, without its visually hidden "Error:" prefix, or null. */
function errorUnder(label) {
  const ids = (field(label).getAttribute('aria-describedby') ?? '').split(/\s+/).filter(Boolean)
  const error = ids.map((id) => document.getElementById(id)).find((element) => element?.classList.contains('field__error'))
  return error ? error.textContent.replace(/^Error: /, '') : null
}

function fillValid() {
  type(PROFILE_TEXT.currentPasswordLabel, CURRENT)
  type(PROFILE_TEXT.newPasswordLabel, NEW)
  type(PROFILE_TEXT.confirmPasswordLabel, NEW)
}

async function openProfile(user = EMPLOYEE, routes = {}) {
  const answered = serveSignedIn(user, routes)
  const probe = renderApp('/profile')
  await screen.findByRole('heading', { level: 1, name: PROFILE_TEXT.heading })
  return { answered, probe }
}

function changes(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/auth/change-password')
}

function logouts(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/auth/logout')
}

function primaryNav() {
  return screen.getByRole('navigation', { name: 'Primary' })
}

/** Long enough for a logout sent at once, or a few tasks later, to have been recorded. */
function aWhile() {
  return new Promise((resolve) => setTimeout(resolve, 50))
}

/**
 * Starts a change that the server holds, then presses the header's Log out, and checks
 * that the press is taken and that no logout is sent while the change is in flight.
 * Returns what the test needs to release the change and look at the outcome.
 */
async function logOutDuringHeldChange(user, extraRoutes = {}) {
  const held = heldResponse()
  const { answered, probe } = await openProfile(user, {
    'POST /api/auth/change-password': held.route,
    'POST /api/auth/logout': { status: 200 },
    ...extraRoutes,
  })
  fillValid()
  fireEvent.click(screen.getByRole('button', { name: PROFILE_TEXT.changePassword }))
  expect(changes(answered)).toHaveLength(1)

  const logOut = within(primaryNav()).getByRole('button', { name: 'Log out' })
  fireEvent.click(logOut)
  // No logout is sent while the change is in flight...
  expect(logouts(answered)).toHaveLength(0)
  // ...but the press is taken, and the header says so...
  await waitFor(() => expect(logOut.textContent).toBe('Signing out…'))
  expect(logOut.disabled).toBe(true)
  // ...and it goes on waiting, however long the change takes.
  await aWhile()
  expect(logouts(answered)).toHaveLength(0)
  expect(logOut.textContent).toBe('Signing out…')
  expect(probe.location.pathname).toBe('/profile')
  return { held, answered, probe }
}

/** Signed out, on the sign-in page with FR-04's confirmation, having sent one logout. */
async function expectLoggedOut({ answered, probe }, user) {
  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  await waitFor(() => expect(probe.location.pathname).toBe('/login'))
  await waitFor(() =>
    expect(screen.getByText('Logged out').closest('[role="status"]').textContent).toContain(TEXT.loggedOut),
  )
  expect(within(primaryNav()).queryByRole('button', { name: 'Log out' })).toBeNull()
  expect(document.body.textContent).not.toContain(user.name)
  expect(logouts(answered)).toHaveLength(1)
  expect(changes(answered)).toHaveLength(1)
}

describe('FR-01: a new password is held to registration’s rules', () => {
  it('shows the requirements beside the new password, and keeps Change password disabled until every check passes', async () => {
    const { answered } = await openProfile()
    const submit = screen.getByRole('button', { name: PROFILE_TEXT.changePassword })
    expect(submit.disabled).toBe(true)
    expect(screen.getByText(PROFILE_TEXT.passwordGate)).toBeTruthy()

    // The requirements panel describes the new password field, as on registration.
    const described = (field(PROFILE_TEXT.newPasswordLabel).getAttribute('aria-describedby') ?? '').split(/\s+/)
    const panel = described.map((id) => document.getElementById(id)).find((element) => element?.classList.contains('password-req__panel'))
    expect(panel, 'the new password is described by the requirements panel').toBeTruthy()
    expect(panel.textContent).toContain('Password strength: Not started.')

    // Eight characters satisfied #119's rule. FR-01's needs an uppercase letter, a
    // number and a special character as well.
    type(PROFILE_TEXT.currentPasswordLabel, CURRENT)
    type(PROFILE_TEXT.newPasswordLabel, 'abcdefgh')
    type(PROFILE_TEXT.confirmPasswordLabel, 'abcdefgh')
    expect(submit.disabled).toBe(true)
    expect(panel.textContent).toContain('Not met: At least 1 uppercase letter')
    expect(panel.textContent).toContain('Not met: At least 1 number')
    expect(panel.textContent).toContain('Not met: At least 1 special character')

    // Every rule met, and the confirmation does not match.
    type(PROFILE_TEXT.newPasswordLabel, NEW)
    expect(panel.textContent).toContain('Password strength: Strong. 4 of 4 requirements met.')
    expect(submit.disabled).toBe(true)
    fireEvent.blur(field(PROFILE_TEXT.confirmPasswordLabel))
    expect(errorUnder(PROFILE_TEXT.confirmPasswordLabel)).toBe(VALIDATION.passwordMismatch)

    // It matches: Change password is offered, and the sentence beside it goes.
    type(PROFILE_TEXT.confirmPasswordLabel, NEW)
    expect(errorUnder(PROFILE_TEXT.confirmPasswordLabel)).toBeNull()
    expect(submit.disabled).toBe(false)
    expect(screen.queryByText(PROFILE_TEXT.passwordGate)).toBeNull()

    // The current password is required too.
    type(PROFILE_TEXT.currentPasswordLabel, '')
    expect(submit.disabled).toBe(true)
    fireEvent.blur(field(PROFILE_TEXT.currentPasswordLabel))
    expect(errorUnder(PROFILE_TEXT.currentPasswordLabel)).toBe(PROFILE_TEXT.currentPasswordRequired)

    // Enter from a field submits a form whatever its button says: nothing is sent.
    fireEvent.submit(submit.closest('form'))
    expect(errorUnder(PROFILE_TEXT.currentPasswordLabel)).toBe(PROFILE_TEXT.currentPasswordRequired)
    expect(requested(answered)).toEqual(['GET /api/auth/me'])
  })
})

describe('D-137: the change, one at a time, and what the page says of its answer', () => {
  it('sends current_password and new_password once, sends nothing else until the change has answered, then shows the 200’s message', async () => {
    const held = heldResponse()
    const user = { ...EMPLOYEE, picture: PICTURE }
    const { answered } = await openProfile(user, {
      'POST /api/auth/change-password': held.route,
      'DELETE /api/users/me/picture': { body: { ...user, picture: null } },
      'POST /api/users/me/picture': { body: user },
    })
    fillValid()
    const submit = screen.getByRole('button', { name: PROFILE_TEXT.changePassword })
    const remove = screen.getByRole('button', { name: PROFILE_TEXT.removeSavedLabel })
    expect(remove.disabled).toBe(false)
    fireEvent.click(submit)

    expect(changes(answered).map((request) => request.body)).toEqual([{ current_password: CURRENT, new_password: NEW }])
    // In flight: Change password disabled and saying so, and nothing else on the page
    // can be sent. Asserted directly, since fireEvent presses a disabled control too.
    await waitFor(() => expect(submit.disabled).toBe(true))
    expect(submit.textContent).toBe(PROFILE_TEXT.changingPassword)
    expect(remove.disabled).toBe(true)
    fireEvent.click(submit)
    fireEvent.submit(submit.closest('form'))
    fireEvent.click(remove)
    // Choosing a picture sends nothing, and it cannot be uploaded until the change answers.
    fireEvent.change(document.querySelector('input[type="file"]'), {
      target: { files: [new File([new Uint8Array(8)], 'me.png', { type: 'image/png' })] },
    })
    const upload = screen.getByRole('button', { name: PROFILE_TEXT.uploadPicture })
    expect(upload.disabled).toBe(true)
    fireEvent.submit(upload.closest('form'))
    expect(requested(answered)).toEqual(['GET /api/auth/me', 'POST /api/auth/change-password'])
    expect(changes(answered)).toHaveLength(1)

    held.release({ body: { detail: 'Your password has been changed.' } })
    const notice = await screen.findByText(`${PROFILE_TEXT.passwordChanged} ${PROFILE_TEXT.passwordChangedSessions}`)
    expect(notice.closest('[role="status"]')).toBeTruthy()
    expect(within(notice.closest('[role="status"]')).getByText(PROFILE_TEXT.passwordChangedTitle)).toBeTruthy()
    // The form is emptied, and the rest of the page is offered again.
    expect(field(PROFILE_TEXT.currentPasswordLabel).value).toBe('')
    expect(field(PROFILE_TEXT.newPasswordLabel).value).toBe('')
    expect(field(PROFILE_TEXT.confirmPasswordLabel).value).toBe('')
    expect(upload.disabled).toBe(false)
    expect(changes(answered)).toHaveLength(1)
    expect(requested(answered)).toEqual(['GET /api/auth/me', 'POST /api/auth/change-password'])
  })

  it('puts every message of a 400 under the field it names, the current password’s included, and the user stays signed in', async () => {
    const { answered, probe } = await openProfile(EMPLOYEE, {
      'POST /api/auth/change-password': {
        status: 400,
        body: {
          current_password: ['Your current password is incorrect.'],
          new_password: ['This password is too common.', 'The password is too similar to the email address.'],
        },
      },
    })
    fillValid()
    fireEvent.click(screen.getByRole('button', { name: PROFILE_TEXT.changePassword }))

    await waitFor(() => expect(errorUnder(PROFILE_TEXT.currentPasswordLabel)).toBe('Your current password is incorrect.'))
    expect(errorUnder(PROFILE_TEXT.newPasswordLabel)).toBe(
      'This password is too common. The password is too similar to the email address.',
    )
    expect(field(PROFILE_TEXT.currentPasswordLabel).getAttribute('aria-invalid')).toBe('true')
    expect(field(PROFILE_TEXT.newPasswordLabel).getAttribute('aria-invalid')).toBe('true')
    // Under the fields, and not in a banner as well.
    expect(screen.queryByText(PROFILE_TEXT.passwordChangeFailed)).toBeNull()
    // A wrong current password is a 400, never a 401: still signed in, on this page.
    expect(probe.location.pathname).toBe('/profile')
    expect(screen.getByRole('heading', { level: 1, name: PROFILE_TEXT.heading })).toBeTruthy()
    expect(requested(answered)).toEqual(['GET /api/auth/me', 'POST /api/auth/change-password'])

    // A message is about the value that was sent: editing the field clears it.
    type(PROFILE_TEXT.currentPasswordLabel, 'Old-password-3')
    expect(errorUnder(PROFILE_TEXT.currentPasswordLabel)).toBeNull()
    expect(errorUnder(PROFILE_TEXT.newPasswordLabel)).not.toBeNull()
  })

  it('says the new password must differ from the current one under the new password, and a 400 naming no field in a banner of the page’s own words', async () => {
    let reply = { status: 400, body: { new_password: ['Your new password must be different from your current password.'] } }
    await openProfile(EMPLOYEE, { 'POST /api/auth/change-password': () => reply })
    fillValid()
    fireEvent.click(screen.getByRole('button', { name: PROFILE_TEXT.changePassword }))
    await waitFor(() =>
      expect(errorUnder(PROFILE_TEXT.newPasswordLabel)).toBe('Your new password must be different from your current password.'),
    )

    // Django's own 400 for a second change read before the first committed (CHG-3).
    reply = { status: 400, body: { detail: 'Bad request.' } }
    type(PROFILE_TEXT.newPasswordLabel, 'Another-password-3!')
    type(PROFILE_TEXT.confirmPasswordLabel, 'Another-password-3!')
    fireEvent.click(screen.getByRole('button', { name: PROFILE_TEXT.changePassword }))
    const banner = await screen.findByRole('alert')
    expect(banner.textContent).toContain(PROFILE_TEXT.passwordChangeFailed)
    expect(banner.textContent).toContain('Some of the information provided is not valid. Please check it and try again.')
    expect(banner.textContent).not.toContain('Bad request')
  })

  it('says a 429 left the password unchanged, and when it can be tried again from Retry-After, never the server’s text', async () => {
    await openProfile(EMPLOYEE, {
      'POST /api/auth/change-password': {
        status: 429,
        body: { detail: 'Request was throttled. Expected available in 120 seconds.' },
        headers: { 'Retry-After': '120' },
      },
    })
    fillValid()
    fireEvent.click(screen.getByRole('button', { name: PROFILE_TEXT.changePassword }))

    const banner = await screen.findByRole('alert')
    expect(banner.textContent).toBe(`${PROFILE_TEXT.passwordChangeFailed}${PROFILE_TEXT.passwordRateLimited('in 2 minutes')}`)
    expect(banner.textContent).toContain('so it was not changed')
    expect(banner.textContent).not.toMatch(/throttled/i)
    // What was typed is still there, to send again later.
    expect(field(PROFILE_TEXT.currentPasswordLabel).value).toBe(CURRENT)
  })
})

describe('LOG-1: Log out pressed while a change is in flight waits for the change’s answer', () => {
  it.each(BOTH_ROLES)(
    'as an $role, sends no logout until the change has answered, then exactly one, and lands on sign-in signed out',
    async (user) => {
      const pressed = await logOutDuringHeldChange(user)

      // The change answers, and its 200 sets the new key's cookie. Only now is the logout
      // sent, so it carries that cookie and destroys the session the change kept.
      pressed.held.release({ body: { detail: 'Your password has been changed.' } })
      await expectLoggedOut(pressed, user)
    },
  )

  it.each([
    {
      answer: 'a 400 refusing it',
      reply: { status: 400, body: { current_password: ['Your current password is incorrect.'] } },
    },
    {
      answer: 'a 429',
      reply: { status: 429, body: { detail: 'Request was throttled.' }, headers: { 'Retry-After': '120' } },
    },
  ])('sends the logout once the change has answered, whatever it answered: $answer', async ({ reply }) => {
    const pressed = await logOutDuringHeldChange(EMPLOYEE)

    // Refused, the change kept the old key, and the logout destroys that one. A refusal
    // does not stop the logout, nor does it say the user could not be signed out.
    pressed.held.release(reply)
    await expectLoggedOut(pressed, EMPLOYEE)
    expect(screen.queryByText('Could not sign out')).toBeNull()
  })
})
