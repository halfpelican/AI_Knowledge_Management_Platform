/**
 * FR-03's sign-in screen: the clauses only the interface can satisfy (D-130).
 *
 * - "After each failed login, a subtle warning appears once 2+ attempts remain: '2
 *   attempts remaining before temporary lockout'." Benjamin's decision 2: after the
 *   third and the fourth consecutive failure for an address, and never before.
 * - "Once locked, the login button is disabled with a countdown timer shown."
 * - "The lockout message states that an administrator can unlock the account, so a
 *   locked-out user has a route forward."
 * - The server's 403 counts down from its `retry_after`, or from the full fifteen
 *   minutes where that is absent or not a number, so Sign in never comes back before
 *   the lock could have ended (the build spec, D-130).
 *
 * The count is the page's own, one per address as typed and normalised, in memory only
 * (decision 1). The server's 401 is the same for every address, so nothing here depends
 * on whether an address has an account, and the page's own lock is worded to be true of
 * any address (the security review, finding C). The server's lock, the 403
 * `account_locked` with `retry_after` that only the right password receives, is decided
 * and tested in pytest. None of this screen is security: the server enforces the lock
 * whatever the page shows (CLAUDE.md §6, invariant 4).
 *
 * The clock is faked, `Date` and the interval the countdown is redrawn by, and nothing
 * else, so replies and renders run as ever and the countdown reads exactly what the
 * moved clock says. jsdom applies no stylesheet, so "subtle" is asserted as what it is
 * in the DOM, plain text in a polite live region beside the banner and not a second
 * alert. How it looks is not tested here.
 *
 * The whole application is rendered at /login with the real auth provider, mocked at
 * `fetch` through tests/fakeApi.js.
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App.jsx'
import { TEXT } from '../src/constants.js'
import { serveApi } from './fakeApi.js'

const JANE = 'jane@example.com'
const SAM = 'sam@example.com'
const WRONG_PASSWORD = 'Wrong-Horse-1'
const RIGHT_PASSWORD = 'Correct-Horse-1'

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

/** FR-02's banner text, written out so a change to it fails here. */
const INVALID_CREDENTIALS = 'Invalid email or password.'

/** Login's 401, the same for an unknown address and a wrong password (D-02). */
const INVALID = { status: 401, body: { detail: INVALID_CREDENTIALS } }

/** FR-03's warning, in the proposal's words (decision 2 adds the singular). */
const TWO_REMAINING = '2 attempts remaining before temporary lockout'
const ONE_REMAINING = '1 attempt remaining before temporary lockout'

/** Login's 403 for a locked account given the right password (docs/api-contract.md, D-130). */
function serverLock(retryAfter) {
  return {
    status: 403,
    body: {
      detail:
        'This account is temporarily locked after repeated failed sign-ins. Try again later, or ask an administrator to unlock it.',
      code: 'account_locked',
      retry_after: retryAfter,
    },
  }
}

beforeEach(() => {
  // Not setTimeout: the Testing Library's own waiting runs on it.
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
})

afterEach(() => {
  vi.useRealTimers()
})

/**
 * Signed out, with the login route answering each attempt with whatever `replies.next`
 * holds when the attempt arrives: a reply, or a function returning one.
 */
function serveSignIn() {
  const replies = { next: INVALID }
  const answered = serveApi({
    'GET /api/auth/me': NOT_SIGNED_IN,
    'POST /api/auth/login': () => (typeof replies.next === 'function' ? replies.next() : replies.next),
  })
  render(
    <MemoryRouter initialEntries={['/login']}>
      <App />
    </MemoryRouter>,
  )
  return { answered, replies }
}

/** Every login attempt the screen actually sent, in order. */
function logins(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/auth/login')
}

function signInButton() {
  return screen.getByRole('button', { name: 'Sign in' })
}

function typeAddress(email) {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
}

/** One sign-in attempt for `email`, waited for until its answer is drawn. */
async function attempt(email, password = WRONG_PASSWORD) {
  fireEvent.change(await screen.findByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
  fireEvent.click(signInButton())
  // In flight the button reads "Signing in…"; it reads "Sign in" again once the answer is drawn.
  await screen.findByRole('button', { name: 'Sign in' })
}

/** The sign-in banner, FR-02's alert, which carries the lock's message as well. */
function banner() {
  return screen.getByText('Could not sign in').closest('[role="alert"]')
}

/** The form's one polite live region, where the warning is written. */
function politeRegion() {
  const form = screen.getByLabelText('Email').closest('form')
  const regions = within(form).getAllByRole('status')
  expect(regions).toHaveLength(1)
  return regions[0]
}

/** The warning is shown, as `text`, beside the banner and not as a second alert. */
function expectWarning(text) {
  const region = politeRegion()
  expect(region.textContent).toBe(text)
  expect(region.previousElementSibling).toBe(banner())
  expect(banner().textContent).toContain(INVALID_CREDENTIALS)
  const alerts = within(region.closest('form')).getAllByRole('alert')
  expect(alerts).toHaveLength(1)
  expect(alerts[0]).toBe(banner())
}

function expectNoWarning() {
  expect(politeRegion().textContent).toBe('')
  expect(screen.queryByText(/remaining before temporary lockout/)).toBeNull()
}

/** Sign in is disabled, the countdown reads `countdown`, and the banner carries a lock's message. */
function expectLocked(countdown) {
  expect(signInButton().disabled).toBe(true)
  expect(screen.getByRole('timer').textContent).toBe(countdown)
}

function expectNotLocked() {
  expect(signInButton().disabled).toBe(false)
  expect(screen.queryByRole('timer')).toBeNull()
  expect(document.body.textContent).not.toContain(TEXT.accountMayBeLocked)
  expect(document.body.textContent).not.toContain(TEXT.accountLocked)
}

/**
 * Lets React run the effect that starts the countdown. React runs it a task after the
 * locked state is drawn, so a `findBy…` that has just seen the state may not have seen
 * the interval, and a clock moved before it exists moves past nothing.
 */
async function letTheCountdownStart() {
  await act(async () => {})
  expect(vi.getTimerCount(), 'the countdown is running').toBe(1)
}

/** Moves the faked clock on by `seconds`, and draws what that changed. */
async function wait(seconds) {
  await act(async () => {
    vi.advanceTimersByTime(seconds * 1000)
  })
}

describe('FR-03: the remaining-attempts warning, after the third and fourth failures only', () => {
  it('shows no warning after the first or second 401, then "2 attempts remaining…" and "1 attempt remaining…" in a polite status beside the banner', async () => {
    const { answered } = serveSignIn()

    await attempt(JANE)
    expect(banner().textContent).toContain(INVALID_CREDENTIALS)
    expectNoWarning()

    await attempt(JANE)
    expectNoWarning()

    await attempt(JANE)
    expectWarning(TWO_REMAINING)

    await attempt(JANE)
    expectWarning(ONE_REMAINING)
    expect(screen.queryByText(TWO_REMAINING)).toBeNull()

    // A warning, not a lock: Sign in is still offered.
    expectNotLocked()
    expect(logins(answered)).toHaveLength(4)
  })
})

describe('FR-03: at the fifth failure, Sign in is disabled with a countdown', () => {
  it('disables Sign in, shows "Try again in 15:00" as a timer, and says the address may be locked and an administrator can unlock it', async () => {
    serveSignIn()

    for (let failure = 1; failure <= 5; failure += 1) await attempt(JANE)

    expectLocked('Try again in 15:00')
    // True of any address: the page does not know whether it has an account, nor whether
    // the server locked it (the security review, finding C).
    const message = banner().textContent
    expect(message).toMatch(/If this address has an account/)
    expect(message).toMatch(/administrator/i)
    expect(message).toContain('15 minutes')
    expect(message).not.toContain(TEXT.accountLocked)
    // No "0 attempts remaining": the warning gives way to the lock.
    expectNoWarning()
  })

  it('enables Sign in at zero, removes the timer and the message, and counts the next failures from the start', async () => {
    serveSignIn()
    for (let failure = 1; failure <= 5; failure += 1) await attempt(JANE)
    await letTheCountdownStart()

    await wait(899)
    expectLocked('Try again in 0:01')

    await wait(1)
    expectNotLocked()
    expect(banner().textContent).not.toMatch(/If this address has an account/)

    // The count went with the lock: one failure locks nothing and warns of nothing, and
    // the warning comes back only at the third.
    await attempt(JANE)
    expectNotLocked()
    expectNoWarning()
    await attempt(JANE)
    expectNoWarning()
    await attempt(JANE)
    expectWarning(TWO_REMAINING)
  })

  it('sends nothing for a submission while locked, whether from the disabled button or from Enter in the password field', async () => {
    const { answered } = serveSignIn()
    for (let failure = 1; failure <= 5; failure += 1) await attempt(JANE)
    expect(logins(answered)).toHaveLength(5)

    const password = screen.getByLabelText('Password')
    fireEvent.change(password, { target: { value: RIGHT_PASSWORD } })
    fireEvent.click(signInButton())
    // jsdom has no implicit submission, so Enter in the password field is dispatched as
    // the submit event it causes. A browser does nothing for Enter while the default
    // button is disabled; this is the guard for any submission that does not come
    // through the button.
    fireEvent.submit(password.closest('form'))

    expect(screen.queryByRole('button', { name: 'Signing in…' })).toBeNull()
    expect(logins(answered)).toHaveLength(5)
    expectLocked('Try again in 15:00')
  })
})

describe('FR-03: the count is kept per address, as typed and normalised', () => {
  it("counts each address on its own, and an address typed again shows its own warning", async () => {
    serveSignIn()

    for (let failure = 1; failure <= 3; failure += 1) await attempt(JANE)
    expectWarning(TWO_REMAINING)

    // Another address has no count of its own yet, and Jane's failures are not its.
    typeAddress(SAM)
    expectNoWarning()
    await attempt(SAM)
    expectNoWarning()
    await attempt(SAM)
    expectNoWarning()

    // Jane's three, as they were, and Sam's two are not among them.
    typeAddress(JANE)
    expectWarning(TWO_REMAINING)
    await attempt(JANE)
    expectWarning(ONE_REMAINING)
    expectNotLocked()

    typeAddress(SAM)
    expectNoWarning()
    await attempt(SAM)
    expectWarning(TWO_REMAINING)
  })

  it("restores a locked address's lock when it is typed again, and does not lock another address", async () => {
    serveSignIn()
    for (let failure = 1; failure <= 5; failure += 1) await attempt(JANE)
    expectLocked('Try again in 15:00')

    typeAddress(SAM)
    expectNotLocked()
    expectNoWarning()

    typeAddress(JANE)
    expectLocked('Try again in 15:00')
    expect(banner().textContent).toMatch(/If this address has an account/)
  })

  it('counts "Jane@Example.com " and "jane@example.com" as one address', async () => {
    const { answered } = serveSignIn()

    await attempt('Jane@Example.com ')
    await attempt('Jane@Example.com ')
    expectNoWarning()

    await attempt('jane@example.com')
    expectWarning(TWO_REMAINING)

    // Typed the first way again, the same count.
    typeAddress('JANE@EXAMPLE.COM')
    expectWarning(TWO_REMAINING)
    expect(logins(answered).map((request) => request.body.email)).toEqual([
      'Jane@Example.com',
      'Jane@Example.com',
      'jane@example.com',
    ])
  })
})

describe('FR-03: only a 401 counts', () => {
  it('does not count a 400, a 429 or a network failure', async () => {
    const { answered, replies } = serveSignIn()

    await attempt(JANE)
    await attempt(JANE)
    expectNoWarning()

    replies.next = { status: 400, body: { email: ['Enter a valid email address.'] } }
    await attempt(JANE)
    expectNoWarning()

    replies.next = { status: 429, body: { detail: 'Request was throttled.' }, headers: { 'Retry-After': '30' } }
    await attempt(JANE)
    expect(banner().textContent).toContain('Too many attempts. Please wait a minute and try again.')
    expectNoWarning()

    replies.next = () => Promise.reject(new TypeError('Failed to fetch'))
    await attempt(JANE)
    expect(banner().textContent).toContain('Could not reach the server.')
    expectNoWarning()

    // The third 401 is the third failure counted.
    replies.next = INVALID
    await attempt(JANE)
    expectWarning(TWO_REMAINING)
    expect(logins(answered)).toHaveLength(6)
  })
})

describe("FR-03: the server's lock, a 403 account_locked with retry_after", () => {
  it('disables Sign in with "Try again in 2:00" for retry_after 120 and the message naming an administrator, sends nothing while locked, and enables it at zero', async () => {
    const { answered, replies } = serveSignIn()
    replies.next = serverLock(120)

    await attempt(JANE, RIGHT_PASSWORD)

    expectLocked('Try again in 2:00')
    const message = banner().textContent
    expect(message).toContain(TEXT.accountLocked)
    expect(message).toMatch(/administrator/i)
    // The server's, not the page's own: it is told only to the right password.
    expect(message).not.toMatch(/If this address has an account/)
    expect(message).not.toContain(INVALID_CREDENTIALS)

    fireEvent.change(screen.getByLabelText('Password'), { target: { value: RIGHT_PASSWORD } })
    fireEvent.submit(screen.getByLabelText('Password').closest('form'))
    expect(logins(answered)).toHaveLength(1)

    await letTheCountdownStart()
    await wait(119)
    expectLocked('Try again in 0:01')
    await wait(1)
    expectNotLocked()
    expect(screen.queryByText('Could not sign in')).toBeNull()
  })

  it('counts down the full 15:00 when the 403 carries no retry_after', async () => {
    const { replies } = serveSignIn()
    replies.next = serverLock(undefined)

    await attempt(JANE, RIGHT_PASSWORD)

    // Never sooner than the lock could end: no lock outlasts LOCKOUT_DURATION.
    expectLocked('Try again in 15:00')
    expect(banner().textContent).toContain(TEXT.accountLocked)
  })

  it('counts down the full 15:00 when the 403 carries a retry_after that is not a number of seconds', async () => {
    const { replies } = serveSignIn()
    replies.next = serverLock('soon')

    await attempt(JANE, RIGHT_PASSWORD)

    expectLocked('Try again in 15:00')
    expect(banner().textContent).toContain(TEXT.accountLocked)
  })

  it('does not lock for a 403 without the code', async () => {
    const { replies } = serveSignIn()
    replies.next = { status: 403, body: { detail: 'You do not have permission to perform this action.' } }

    await attempt(JANE, RIGHT_PASSWORD)

    expect(banner().textContent).toContain('You do not have permission to do that.')
    expect(banner().textContent).not.toContain(TEXT.accountLocked)
    expectNotLocked()
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe("FR-03: a lock released while the page is open", () => {
  it("says to reload once an administrator has unlocked the account, with the page's own lock and with the server's, and not before", async () => {
    const { replies } = serveSignIn()

    // Not locked: an ordinary failure says nothing about unlocking.
    await attempt(JANE)
    expect(banner().textContent).not.toContain(TEXT.lockedReloadHint)

    // The page's own lock, at the fifth failure: a release reaches the server, not this page.
    for (let failure = 2; failure <= 5; failure += 1) await attempt(JANE)
    expectLocked('Try again in 15:00')
    expect(banner().textContent).toContain(TEXT.accountMayBeLocked)
    expect(banner().textContent).toContain(TEXT.lockedReloadHint)

    // The server's lock, on another address given the right password.
    replies.next = serverLock(300)
    await attempt(SAM, RIGHT_PASSWORD)
    expectLocked('Try again in 5:00')
    expect(banner().textContent).toContain(TEXT.accountLocked)
    expect(banner().textContent).toContain(TEXT.lockedReloadHint)
  })
})
