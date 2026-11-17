/**
 * NFR-14: "identical UI elements must behave identically across modules". FR-02's
 * "Show password" toggle is how the app's password fields behave: sign-in,
 * registration and the reset page all use components/PasswordInput.jsx. The Profile
 * page's three were plain password inputs with no toggle (FEA-3, the requirements
 * audit of PR #119), so a user changing their password could not check what they had
 * typed, although every other form that takes the same input lets them.
 *
 * - **The sweep**: on every screen with a password field, each one has a toggle beside
 *   it, a button that names the field it controls and carries its state in
 *   `aria-pressed`. A new password field without one fails here.
 * - **The Profile page's three**, as each role: each toggle is named for its field, as
 *   the reset page names its two; pressing it shows that field's password and no other,
 *   keeps what was typed, and pressing it again hides it.
 *
 * The toggle's own behaviour, where focus stays and what a screen reader hears, is
 * tests/login.test.jsx's, on the component every one of these fields uses.
 */
import { fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PROFILE_TEXT } from '../src/constants.js'
import { serveApi } from './fakeApi.js'
import { BOTH_ROLES, primaryNavigationFor, renderApp, serveSignedIn } from './routeWalk.jsx'

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

/** Every screen with a password field, as it opens. */
const SCREENS = [
  {
    what: 'sign-in, to a visitor',
    path: '/login',
    serve: () => serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN }),
    settled: () => screen.findByRole('heading', { level: 1, name: 'Sign in' }),
  },
  {
    what: 'registration, to a visitor',
    path: '/register',
    serve: () => serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN }),
    settled: () => screen.findByRole('heading', { level: 1, name: 'Create an account' }),
  },
  {
    what: 'the reset page, from its link',
    path: '/reset-password?uid=MQ&token=cz5ooz-0a1',
    serve: () => serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN }),
    settled: () => screen.findByLabelText('New password'),
  },
  ...BOTH_ROLES.map((user) => ({
    what: `the Profile page, as an ${user.role}`,
    path: '/profile',
    serve: () => serveSignedIn(user, {}),
    settled: async () => {
      await screen.findByRole('heading', { level: 1, name: PROFILE_TEXT.heading })
      await primaryNavigationFor(user)
    },
  })),
]

/** The toggle that controls `input`: a button naming it in aria-controls, with a pressed state. */
function toggleFor(input) {
  return [...document.querySelectorAll('button[aria-controls]')].find(
    (button) => button.getAttribute('aria-controls') === input.id,
  )
}

describe('NFR-14 and FEA-3: every password field has FR-02’s Show toggle, the Profile page’s included', () => {
  it.each(SCREENS)('gives each password field on $what a toggle beside it', async ({ path, serve, settled }) => {
    serve()
    renderApp(path)
    await settled()

    const fields = [...document.querySelectorAll('input[type="password"]')]
    expect(fields.length, 'the screen has a password field').toBeGreaterThan(0)
    for (const field of fields) {
      const name = field.labels?.[0]?.textContent ?? field.name
      const toggle = toggleFor(field)
      expect(toggle, `"${name}" has a Show toggle`).toBeDefined()
      expect(toggle.getAttribute('aria-pressed'), `"${name}"'s toggle starts unpressed`).toBe('false')
      // Beside its field: in the same field group, as PasswordInput puts it.
      expect(toggle.closest('.field'), `"${name}"'s toggle sits in its field`).toBe(field.closest('.field'))
    }
  })
})

describe('FEA-3: the Profile page’s three password fields, each with its own toggle', () => {
  const FIELDS = [
    [PROFILE_TEXT.currentPasswordLabel, PROFILE_TEXT.showCurrentPassword],
    [PROFILE_TEXT.newPasswordLabel, PROFILE_TEXT.showNewPassword],
    [PROFILE_TEXT.confirmPasswordLabel, PROFILE_TEXT.showConfirmedPassword],
  ]

  it.each(BOTH_ROLES)('as an $role, each toggle shows its own field’s password, keeps what was typed, and hides it again', async (user) => {
    serveSignedIn(user, {})
    renderApp('/profile')
    await screen.findByRole('heading', { level: 1, name: PROFILE_TEXT.heading })
    const form = screen.getByLabelText(PROFILE_TEXT.currentPasswordLabel).closest('form')

    // Named for its field, as the reset page names its two: three different names.
    expect(new Set(FIELDS.map(([, toggleName]) => toggleName)).size).toBe(3)
    for (const [label, toggleName] of FIELDS) {
      const field = screen.getByLabelText(label)
      fireEvent.change(field, { target: { value: `${label}-Typed-1!` } })
      const toggle = within(form).getByRole('button', { name: toggleName })
      expect(toggle.getAttribute('aria-controls')).toBe(field.id)
      expect(field.type).toBe('password')

      fireEvent.click(toggle)
      expect(field.type).toBe('text')
      expect(toggle.getAttribute('aria-pressed')).toBe('true')
      expect(field.value).toBe(`${label}-Typed-1!`)
      // Only its own field: the other two stay hidden.
      for (const [otherLabel] of FIELDS.filter(([other]) => other !== label)) {
        expect(screen.getByLabelText(otherLabel).type, `${otherLabel} stays hidden`).toBe('password')
      }

      fireEvent.click(toggle)
      expect(field.type).toBe('password')
      expect(toggle.getAttribute('aria-pressed')).toBe('false')
    }
  })
})
