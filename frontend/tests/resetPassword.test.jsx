/**
 * D-137's reset page at /reset-password, which the emailed link opens: the clauses only
 * the interface can satisfy. D-137's Built note owed it to feat/UI ("a `/reset-password`
 * page ... that posts `uid` and `token` and then removes them from the address bar"),
 * and the final requirements audit's DEP-1 found no front end had it.
 *
 * - **The link's values leave the address at once.** `uid` and `token` are read once and
 *   kept, and the address is replaced with one without them: replaced, so no history
 *   entry keeps the token, and nothing later sends it on in a Referer. Asserted against
 *   jsdom's real `window.location` and `window.history`, through BrowserRouter.
 * - **A link without both values** is the dead-link state, and nothing is sent.
 * - **The new password** is held to FR-01's rules as on registration, with a
 *   confirmation, and Reset password stays disabled until every check passes.
 * - **What the server answers** (docs/api-contract.md, "Resetting a forgotten
 *   password"): the 200's sentence with a link to sign in; the one 400 for a link that
 *   does not work, said in the page's own words with a link to ask for a new one; a
 *   `new_password` 400 under the field, with the form and the link kept; the 429 with
 *   when to try again; anything else in the API client's fixed text.
 * - **FR-02's loading pattern**, focus once an outcome replaces the form, the tab's
 *   title, and the keyboard's way through.
 * - **A reset of the account signed in here** (RST-UI-3): it ends this browser's session
 *   too, so the header stops naming the user, while the page keeps its outcome and says
 *   nothing of an expired session. Another account's reset leaves the session as it was.
 *
 * Whether a link works, what a reset does to sessions and to FR-03's lock, and the
 * order of the server's checks are pytest's (apps/api/tests/test_fr02_password_reset.py).
 *
 * The whole application is rendered with the real auth provider, mocked at `fetch`
 * through tests/fakeApi.js.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { BrowserRouter, MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App.jsx'
import { APP_TITLE, SIGN_IN_TEXT, TEXT, VALIDATION } from '../src/constants.js'
import { heldResponse, serveApi } from './fakeApi.js'
import { stopName, tabThrough } from './keyboard.js'
import { ADMINISTRATOR, BOTH_ROLES, primaryNavigationFor } from './routeWalk.jsx'

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

/** The emailed link's two values: a uid in URL-safe base64 and a Django reset token. */
const LINK = { uid: 'MQ', token: 'cz5ooz-0123456789abcdef0123' }
const LINK_QUERY = `?uid=${LINK.uid}&token=${LINK.token}`

/** A password FR-01's rules accept. */
const NEW_PASSWORD = 'New-Horse-1!'

/** The contract's bodies (docs/api-contract.md, "Resetting a forgotten password"), written out. */
const COMPLETE = { detail: 'Your password has been reset. Sign in with your new password.' }
const DEAD_LINK = {
  status: 400,
  body: { detail: 'This password reset link does not work. It may have expired or been used already; ask for a new one.' },
}
const REFUSED_PASSWORD = { status: 400, body: { new_password: ['This password is too similar to the email address.'] } }

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

function renderAt(path) {
  probe.location = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  )
}

/** Signed out, with the confirm route answering as `reply` says. */
function serveReset(reply) {
  return serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN, 'POST /api/auth/password-reset/confirm': reply })
}

function typeNewPassword(password, confirmation = password) {
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: password } })
  fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: confirmation } })
}

function resetButton() {
  return screen.getByRole('button', { name: 'Reset password' })
}

/** The body of every confirm the page sent, in order. */
function confirms(answered) {
  return answered
    .filter((request) => request.method === 'POST' && request.path === '/api/auth/password-reset/confirm')
    .map((request) => request.body)
}

/** The message rendered under a field, found through the field's own aria-describedby. */
function messageUnder(label) {
  const input = screen.getByLabelText(label)
  const ids = (input.getAttribute('aria-describedby') ?? '').split(' ').filter((id) => id.endsWith('-error'))
  return ids.map((id) => document.getElementById(id)?.textContent ?? '').join('')
}

/** The requirements panel the new password is described by: the element it names that is not its error. */
function requirementsPanel() {
  const ids = screen.getByLabelText('New password').getAttribute('aria-describedby').split(' ')
  const panel = ids.filter((id) => !id.endsWith('-error')).map((id) => document.getElementById(id))
  expect(panel).toHaveLength(1)
  return panel[0]
}

/** A notice by its title, once it is on screen. */
async function noticeTitled(title) {
  return (await screen.findByText(title)).closest('.notice')
}

function heading() {
  return screen.getByRole('heading', { level: 1, name: 'Reset password' })
}

describe('D-137: the link leaves the address bar at once', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    window.history.replaceState(null, '', '/')
  })

  it('reads uid and token once, replaces the address with one without them, adding no history entry, and still posts them', async () => {
    window.history.replaceState(null, '', `/reset-password${LINK_QUERY}`)
    const entries = window.history.length
    const pushState = vi.spyOn(window.history, 'pushState')
    const answered = serveReset({ body: COMPLETE })
    render(
      <BrowserRouter>
        <App />
      </BrowserRouter>,
    )

    await screen.findByLabelText('New password')
    // Out of the address bar, and out of history: the entry was replaced, not added to.
    await waitFor(() => expect(window.location.search).toBe(''))
    expect(window.location.pathname).toBe('/reset-password')
    expect(window.location.href).not.toContain(LINK.token)
    expect(window.history.length).toBe(entries)
    expect(pushState).not.toHaveBeenCalled()

    // Still the form, though the address has lost them: the values were kept.
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    await noticeTitled(SIGN_IN_TEXT.resetDoneTitle)
    expect(confirms(answered)).toEqual([{ uid: LINK.uid, token: LINK.token, new_password: NEW_PASSWORD }])
  })
})

describe('D-137: a link without its values', () => {
  it.each([
    { what: 'no query at all', search: '' },
    { what: 'no token', search: '?uid=MQ' },
    { what: 'no uid', search: '?token=cz5ooz-0a1' },
    { what: 'both empty', search: '?uid=&token=' },
    { what: 'a blank uid', search: '?uid=%20&token=cz5ooz-0a1' },
  ])('shows the dead-link state for $what, offers a new link, and sends nothing', async ({ search }) => {
    // Only the session check is answered: a confirm would fail the test (tests/setup.js).
    const answered = serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderAt(`/reset-password${search}`)

    const notice = await noticeTitled(SIGN_IN_TEXT.resetLinkDeadTitle)
    expect(notice.getAttribute('role')).toBe('alert')
    expect(notice.textContent).toContain(SIGN_IN_TEXT.resetLinkDead)
    expect(screen.getByRole('link', { name: SIGN_IN_TEXT.resetAskAgain }).getAttribute('href')).toBe('/forgot-password')
    expect(screen.queryByLabelText('New password')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Reset password' })).toBeNull()
    // Whatever part of the link it had is out of the address too.
    await waitFor(() => expect(probe.location.search).toBe(''))
    expect(answered.map((request) => `${request.method} ${request.path}`)).toEqual(['GET /api/auth/me'])
  })
})

describe("D-137: the new password, under FR-01's rules", () => {
  it('shows each requirement as the password is typed, and keeps Reset password disabled until every check passes, the confirmation included', async () => {
    // Nothing answers the confirm route: a form that sent anything here fails the test.
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    expect(screen.getByLabelText('New password').type).toBe('password')
    expect(screen.getByLabelText('Confirm new password').type).toBe('password')
    expect(resetButton().disabled).toBe(true)
    expect(screen.getByText(SIGN_IN_TEXT.resetGate)).toBeTruthy()
    expect(requirementsPanel().textContent).toContain('Password strength: Not started. 0 of 4 requirements met.')

    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'abc' } })
    expect(requirementsPanel().textContent).toContain('Password strength: Weak. 0 of 4 requirements met.')
    // A space is not a special character, to the panel or to the server.
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'Abcdefg1 ' } })
    expect(requirementsPanel().textContent).toContain('3 of 4 requirements met.')
    // Confirmed exactly, a password that misses a rule still cannot be sent.
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'Abcdefg1 ' } })
    expect(resetButton().disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: NEW_PASSWORD } })
    expect(requirementsPanel().textContent).toContain('Password strength: Strong. 4 of 4 requirements met.')
    expect(resetButton().disabled).toBe(true)

    // A confirmation that differs is refused, under its field once it has been left.
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'New-Horse-2!' } })
    fireEvent.blur(screen.getByLabelText('Confirm new password'))
    expect(messageUnder('Confirm new password')).toContain(VALIDATION.passwordMismatch)
    expect(resetButton().disabled).toBe(true)

    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: NEW_PASSWORD } })
    expect(messageUnder('Confirm new password')).toBe('')
    expect(resetButton().disabled).toBe(false)
    expect(screen.queryByText(SIGN_IN_TEXT.resetGate)).toBeNull()
  })
})

describe('D-137: what the server answers', () => {
  it("200: shows the server's sentence and a link to sign in; the form is gone and focus is on the heading", async () => {
    const answered = serveReset({ body: COMPLETE })
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    const notice = await noticeTitled(SIGN_IN_TEXT.resetDoneTitle)
    expect(notice.getAttribute('role')).toBe('status')
    expect(notice.querySelector('.notice__body').textContent).toBe(COMPLETE.detail)
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'Sign in' }).getAttribute('href')).toBe('/login')
    expect(screen.queryByLabelText('New password')).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(heading()))
    expect(confirms(answered)).toEqual([{ uid: LINK.uid, token: LINK.token, new_password: NEW_PASSWORD }])
  })

  it.each([
    { what: "the server's other sentence, as sent", body: { detail: 'Done: your new password works from now on.' }, shown: 'Done: your new password works from now on.' },
    { what: 'its own sentence for a 200 without one', body: null, shown: SIGN_IN_TEXT.resetCompleteFallback },
  ])('200: shows $what', async ({ body, shown }) => {
    serveReset({ body })
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    expect((await noticeTitled(SIGN_IN_TEXT.resetDoneTitle)).querySelector('.notice__body').textContent).toBe(shown)
  })

  it('the 400 for a link that does not work: says so in its own words, with a link to ask for a new one, and the form goes', async () => {
    const answered = serveReset(DEAD_LINK)
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    const notice = await noticeTitled(SIGN_IN_TEXT.resetLinkDeadTitle)
    expect(notice.getAttribute('role')).toBe('alert')
    expect(notice.textContent).toContain(SIGN_IN_TEXT.resetLinkDead)
    expect(document.body.textContent).not.toContain(DEAD_LINK.body.detail)
    expect(screen.getByRole('link', { name: SIGN_IN_TEXT.resetAskAgain }).getAttribute('href')).toBe('/forgot-password')
    expect(screen.queryByLabelText('New password')).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(heading()))
    expect(confirms(answered)).toHaveLength(1)
  })

  it("treats DRF's 400 for a uid it could not read as the link not working", async () => {
    serveReset({ status: 400, body: { uid: ['This field may not be blank.'] } })
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    expect(await noticeTitled(SIGN_IN_TEXT.resetLinkDeadTitle)).toBeTruthy()
    expect(document.body.textContent).not.toContain('This field may not be blank.')
    expect(screen.queryByLabelText('New password')).toBeNull()
  })

  it('a new_password 400: the message under the field, the form kept, and a second try sends the same link', async () => {
    let attempt = 0
    const answered = serveReset(() => {
      attempt += 1
      return attempt === 1 ? REFUSED_PASSWORD : { body: COMPLETE }
    })
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    await waitFor(() => expect(messageUnder('New password')).toContain(REFUSED_PASSWORD.body.new_password[0]))
    expect(screen.getByLabelText('New password').getAttribute('aria-invalid')).toBe('true')
    expect(screen.queryByText(SIGN_IN_TEXT.resetLinkDeadTitle)).toBeNull()
    expect(screen.queryByText(SIGN_IN_TEXT.resetFailedTitle)).toBeNull()
    // Editing the password clears the server's message about the one that was sent.
    typeNewPassword('Other-Horse-2#')
    expect(messageUnder('New password')).toBe('')

    fireEvent.click(resetButton())

    await noticeTitled(SIGN_IN_TEXT.resetDoneTitle)
    expect(confirms(answered)).toEqual([
      { uid: LINK.uid, token: LINK.token, new_password: NEW_PASSWORD },
      { uid: LINK.uid, token: LINK.token, new_password: 'Other-Horse-2#' },
    ])
  })

  it("the 429: says when to try again from its Retry-After, never in the server's words, and keeps the form", async () => {
    serveReset({
      status: 429,
      body: { detail: 'Request was throttled. Expected available in 45 seconds.' },
      headers: { 'Retry-After': '45' },
    })
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    const notice = await noticeTitled(SIGN_IN_TEXT.resetFailedTitle)
    expect(notice.getAttribute('role')).toBe('alert')
    expect(notice.textContent).toContain(SIGN_IN_TEXT.tooManyAttempts('in 45 seconds'))
    expect(document.body.textContent).not.toContain('Request was throttled')
    expect(screen.getByLabelText('New password').value).toBe(NEW_PASSWORD)
    await waitFor(() => expect(resetButton().disabled).toBe(false))
    expect(screen.queryByText(SIGN_IN_TEXT.resetLinkDeadTitle)).toBeNull()
  })

  it('in flight: Reset password disables and shows the loading state, and a second click sends nothing', async () => {
    const reply = heldResponse()
    const answered = serveReset(reply.route)
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    const busy = await screen.findByRole('button', { name: 'Resetting…' })
    expect(busy.disabled).toBe(true)
    expect(busy.getAttribute('aria-busy')).toBe('true')
    expect(busy.querySelector('.btn__spinner')).not.toBeNull()
    fireEvent.click(busy)
    expect(confirms(answered)).toHaveLength(1)

    reply.release({ body: COMPLETE })

    await noticeTitled(SIGN_IN_TEXT.resetDoneTitle)
    expect(confirms(answered)).toHaveLength(1)
  })

  it("a failure the contract does not name: the API client's fixed text, never the server's, and the form kept", async () => {
    serveReset({ status: 500, body: { detail: 'Traceback (most recent call last): IntegrityError' } })
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    const notice = await noticeTitled(SIGN_IN_TEXT.resetFailedTitle)
    expect(notice.textContent).toContain('Something went wrong. Please try again.')
    expect(document.body.textContent).not.toContain('Traceback')
    expect(screen.getByLabelText('New password')).toBeTruthy()
  })
})

describe('D-137: the page around the form', () => {
  it('names the tab "Reset password"', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    await waitFor(() => expect(document.title).toBe(`Reset password - ${APP_TITLE}`))
  })

  it('takes the keyboard through both fields and their toggles, the button, then the way back to sign in', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderAt(`/reset-password${LINK_QUERY}`)

    await screen.findByLabelText('New password')
    // Reset password is disabled, and so not a stop, until both fields pass.
    typeNewPassword(NEW_PASSWORD)

    const main = screen.getByRole('main')
    const inMain = tabThrough().filter((stop) => main.contains(stop)).map(stopName)
    expect(inMain).toEqual([
      'New password',
      'Show new password',
      'Confirm new password',
      'Show confirmed password',
      'Reset password',
      'Sign in',
    ])
  })
})

describe('RST-UI-3: a reset of the account signed in here ends its session here too, without saying it expired', () => {
  /**
   * `user` is signed in here. Once the confirm has answered 200, the session check
   * answers 401 if the reset was of that account, which ends every one of its sessions,
   * and goes on answering with the user if it was another account's.
   */
  function serveSignedInReset(user, { ownAccount = true } = {}) {
    let reset = false
    return serveApi({
      'GET /api/auth/me': () => (reset && ownAccount ? NOT_SIGNED_IN : { body: user }),
      'POST /api/auth/password-reset/confirm': () => {
        reset = true
        return { body: COMPLETE }
      },
    })
  }

  function sessionChecks(answered) {
    return answered.filter((request) => request.method === 'GET' && request.path === '/api/auth/me')
  }

  async function resetWhileSignedIn(user) {
    renderAt(`/reset-password${LINK_QUERY}`)
    await primaryNavigationFor(user)
    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())
    return noticeTitled(SIGN_IN_TEXT.resetDoneTitle)
  }

  it.each(BOTH_ROLES)(
    'as an $role resetting their own account: the header stops naming them, the page keeps its outcome, and nothing says the session expired',
    async (user) => {
      const answered = serveSignedInReset(user)
      const notice = await resetWhileSignedIn(user)

      const nav = screen.getByRole('navigation', { name: 'Primary' })
      await waitFor(() => expect(within(nav).queryByText(`Signed in as ${user.name}`)).toBeNull())
      expect(within(nav).queryByRole('button', { name: 'Log out' })).toBeNull()
      expect(within(nav).getByRole('link', { name: 'Sign in' })).toBeTruthy()
      // Still the reset page and its outcome: no move to sign-in, and no expiry notice.
      expect(probe.location.pathname).toBe('/reset-password')
      expect(notice.isConnected).toBe(true)
      expect(within(screen.getByRole('main')).getByRole('link', { name: 'Sign in' }).getAttribute('href')).toBe('/login')
      expect(screen.queryByText('Session expired')).toBeNull()
      expect(document.body.textContent).not.toContain(TEXT.sessionExpired)
      // The session check on arrival, and the one read after the reset.
      expect(sessionChecks(answered)).toHaveLength(2)
      expect(confirms(answered)).toEqual([{ uid: LINK.uid, token: LINK.token, new_password: NEW_PASSWORD }])
    },
  )

  it('an Administrator who resets another account stays signed in here', async () => {
    const answered = serveSignedInReset(ADMINISTRATOR, { ownAccount: false })
    await resetWhileSignedIn(ADMINISTRATOR)

    await waitFor(() => expect(sessionChecks(answered)).toHaveLength(2))
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByText(`Signed in as ${ADMINISTRATOR.name}`)).toBeTruthy()
    expect(within(nav).getByRole('button', { name: 'Log out' })).toBeTruthy()
    expect(probe.location.pathname).toBe('/reset-password')
  })

  it('reads the session no more when nobody is signed in here', async () => {
    const answered = serveReset({ body: COMPLETE })
    renderAt(`/reset-password${LINK_QUERY}`)
    await screen.findByLabelText('New password')
    typeNewPassword(NEW_PASSWORD)
    fireEvent.click(resetButton())

    await noticeTitled(SIGN_IN_TEXT.resetDoneTitle)
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(sessionChecks(answered)).toHaveLength(1)
  })
})
