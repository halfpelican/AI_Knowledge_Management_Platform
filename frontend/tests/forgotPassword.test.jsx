/**
 * D-137's forgotten-password request, PR #119's page wired to POST
 * /api/auth/password-reset: the clauses only the interface can satisfy.
 *
 * - **One message for every address (D-25).** The page sends the address and shows the
 *   server's 200 sentence as it was sent, and nothing else about the address, so it
 *   never says whether an account uses it. What the server answers is pytest's
 *   (apps/api/tests/test_fr02_password_reset.py): the same status and body for every
 *   well-formed address.
 * - **No simulated success.** Nothing says a link is on its way until a 200 has
 *   arrived. #119's page set its "Check your email" state without sending anything.
 * - **The refusals.** An empty address is refused before anything is sent; the 400's
 *   field error goes under the field, as on FR-01's page; the 429 says when to try
 *   again; any other failure shows the API client's fixed text, never the server's.
 * - **FR-02's loading pattern**, focus once the form gives way to the message, the
 *   tab's title, and the way here from the sign-in page.
 *
 * The whole application is rendered with the real auth provider, mocked at `fetch`
 * through tests/fakeApi.js.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { APP_TITLE, SIGN_IN_TEXT, VALIDATION } from '../src/constants.js'
import { heldResponse, serveApi } from './fakeApi.js'
import { stopName, tabThrough } from './keyboard.js'

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

/** The contract's one 200 (docs/api-contract.md, "Resetting a forgotten password"), written out. */
const REQUESTED = {
  detail:
    'If an account uses this address, an email with a link to reset its password is on its way. ' +
    'The link works once, within 60 minutes.',
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

function renderApp(path = '/forgot-password') {
  probe.location = null
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  )
}

/** Signed out, with the reset route answering as `reply` says. */
function serveForgot(reply) {
  return serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN, 'POST /api/auth/password-reset': reply })
}

async function requestLink(address) {
  fireEvent.change(await screen.findByLabelText('Email address'), { target: { value: address } })
  fireEvent.click(screen.getByRole('button', { name: 'Send reset instructions' }))
}

/** Every reset request the page sent, in order. */
function resetRequests(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/auth/password-reset')
}

/** The message rendered under a field, found through the field's own aria-describedby. */
function messageUnder(label) {
  const input = screen.getByLabelText(label)
  const ids = (input.getAttribute('aria-describedby') ?? '').split(' ').filter((id) => id.endsWith('-error'))
  return ids.map((id) => document.getElementById(id)?.textContent ?? '').join('')
}

/** The "Check your email" notice, once it is on screen. */
async function sentNotice() {
  return (await screen.findByText('Check your email')).closest('[role="status"]')
}

describe('D-137 and D-25: the request, and the one message for every address', () => {
  it.each([
    { who: 'an address an account uses', typed: '  jane@example.com ', sent: 'jane@example.com' },
    { who: 'an address no account uses', typed: 'nobody@example.com', sent: 'nobody@example.com' },
  ])('sends $who, trimmed, and shows the server\'s 200 sentence as sent, naming nothing of the address', async ({ typed, sent }) => {
    const answered = serveForgot({ body: REQUESTED })
    renderApp()

    await requestLink(typed)

    const notice = await sentNotice()
    // The address arrives trimmed. A `type="email"` field strips the spaces from its own
    // value, in jsdom as in a browser, so this holds the result, not the page's `.trim()`.
    // Exactly the server's sentence under the title: no copy of it, no echo of the address.
    expect(notice.querySelector('.notice__body').textContent).toBe(REQUESTED.detail)
    expect(document.body.textContent).not.toContain(sent)
    expect(resetRequests(answered).map((request) => request.body)).toEqual([{ email: sent }])
    // The form has given way to the message; the way back to sign in is kept.
    expect(screen.queryByRole('button', { name: 'Send reset instructions' })).toBeNull()
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'Sign in' }).getAttribute('href')).toBe('/login')
  })

  it('shows a different sentence from the server as it was sent, so the page restates nothing the server decides', async () => {
    const changed = { detail: 'If an account uses this address, a reset link is on its way. It works once, within 30 minutes.' }
    serveForgot({ body: changed })
    renderApp()

    await requestLink('jane@example.com')

    expect((await sentNotice()).querySelector('.notice__body').textContent).toBe(changed.detail)
    expect(document.body.textContent).not.toContain('60 minutes')
  })

  it('falls back to its own sentence, naming no number, for a 200 that carried no text', async () => {
    serveForgot({ body: null })
    renderApp()

    await requestLink('jane@example.com')

    expect((await sentNotice()).querySelector('.notice__body').textContent).toBe(SIGN_IN_TEXT.resetRequestedFallback)
    expect(SIGN_IN_TEXT.resetRequestedFallback).not.toMatch(/\d/)
  })
})

describe('D-137: no success before the server has answered', () => {
  it('disables the button and shows the loading state in flight, says nothing of a link, and sends no second request on a second click', async () => {
    const reply = heldResponse()
    const answered = serveForgot(reply.route)
    renderApp()

    await requestLink('jane@example.com')

    const busy = await screen.findByRole('button', { name: 'Sending…' })
    expect(busy.disabled).toBe(true)
    expect(busy.getAttribute('aria-busy')).toBe('true')
    expect(busy.querySelector('.btn__spinner')).not.toBeNull()
    expect(screen.queryByText('Check your email')).toBeNull()
    fireEvent.click(busy)
    expect(resetRequests(answered)).toHaveLength(1)

    reply.release({ body: REQUESTED })

    await sentNotice()
    expect(resetRequests(answered)).toHaveLength(1)
  })

  it('refuses an empty address under the field, sending nothing', async () => {
    // Nothing answers the reset route: a request would fail the test (tests/setup.js).
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderApp()

    await requestLink('   ')

    await waitFor(() => expect(messageUnder('Email address')).toContain(VALIDATION.emailRequired))
    expect(screen.getByLabelText('Email address').getAttribute('aria-invalid')).toBe('true')
    expect(screen.queryByText('Check your email')).toBeNull()
  })
})

describe('D-137: the refusals', () => {
  it("puts the 400's field error under the field, with no success and the address kept", async () => {
    const answered = serveForgot({ status: 400, body: { email: ['Enter a valid email address.'] } })
    renderApp()

    await requestLink('jane@example')

    await waitFor(() => expect(messageUnder('Email address')).toContain('Enter a valid email address.'))
    expect(screen.getByLabelText('Email address').value).toBe('jane@example')
    expect(screen.queryByText('Check your email')).toBeNull()
    expect(screen.queryByText('Could not send reset instructions')).toBeNull()
    expect(resetRequests(answered)).toHaveLength(1)
  })

  it("says when to try again after the 429, from its Retry-After, never in the server's words, keeping the address", async () => {
    serveForgot({
      status: 429,
      body: { detail: 'Request was throttled. Expected available in 30 seconds.' },
      headers: { 'Retry-After': '30' },
    })
    renderApp()

    await requestLink('jane@example.com')

    const alert = (await screen.findByText('Could not send reset instructions')).closest('[role="alert"]')
    expect(alert.textContent).toContain(SIGN_IN_TEXT.tooManyAttempts('in 30 seconds'))
    expect(document.body.textContent).not.toContain('Request was throttled')
    expect(screen.getByLabelText('Email address').value).toBe('jane@example.com')
    expect(screen.queryByText('Check your email')).toBeNull()
    expect(screen.getByRole('button', { name: 'Send reset instructions' }).disabled).toBe(false)
  })

  it("shows the API client's fixed text for a failure the contract does not name, never the server's", async () => {
    serveForgot({ status: 500, body: { detail: 'Traceback (most recent call last): smtplib.SMTPException' } })
    renderApp()

    await requestLink('jane@example.com')

    const alert = (await screen.findByText('Could not send reset instructions')).closest('[role="alert"]')
    expect(alert.textContent).toContain('Something went wrong. Please try again.')
    expect(document.body.textContent).not.toContain('Traceback')
    expect(screen.queryByText('Check your email')).toBeNull()
  })
})

describe('D-137: the page around the form', () => {
  it('moves focus to the heading once the form gives way to the message', async () => {
    serveForgot({ body: REQUESTED })
    renderApp()

    await requestLink('jane@example.com')
    await sentNotice()

    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: 'Forgot password' })))
  })

  it('names the tab, and is reached from the sign-in page\'s "Forgot password?" link', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderApp('/login')

    fireEvent.click(await screen.findByRole('link', { name: 'Forgot password?' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Forgot password' })).toBeTruthy()
    await waitFor(() => expect(probe.location.pathname).toBe('/forgot-password'))
    await waitFor(() => expect(document.title).toBe(`Forgot password - ${APP_TITLE}`))
  })

  it('takes the keyboard through the address, the button and the way back to sign in, in that order', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderApp()
    await screen.findByLabelText('Email address')

    const stops = tabThrough()
    const main = screen.getByRole('main')
    const inMain = stops.filter((stop) => main.contains(stop)).map(stopName)
    expect(inMain).toEqual(['Email address', 'Send reset instructions', 'Sign in'])
  })
})
