/**
 * D-26's throttle on registration and login keeps the text it has always had, now
 * that D-79's per-user limits have texts of their own (src/api/client.js).
 *
 * The whole application is rendered at each route, with the real auth provider,
 * so the 429 travels the path a user's does: the screen, the endpoint helper and
 * the one API client. A `Retry-After` is sent, as DRF sends one on these routes too,
 * to show the auth text does not borrow D-79's wording from it.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { TEXT } from '../src/constants.js'
import { serveApi } from './fakeApi.js'

/** The text D-26's throttle has shown since Stage 2. Written out, so a change to it fails here. */
const AUTH_THROTTLED = 'Too many attempts. Please wait a minute and try again.'

const THROTTLED = {
  status: 429,
  body: { detail: 'Request was throttled. Expected available in 30 seconds.' },
  headers: { 'Retry-After': '30' },
}

/** No session: `GET /api/auth/me` answers 401, as for any visitor. */
const SIGNED_OUT = { 'GET /api/auth/me': { status: 401, body: { detail: 'Authentication credentials were not provided.' } } }

function renderApp(path) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe("D-26: the auth throttle's 429 keeps its text", () => {
  it('shows login\'s fixed text for a 429 on sign-in, not a D-79 sentence and not the backend\'s', async () => {
    serveApi({ ...SIGNED_OUT, 'POST /api/auth/login': THROTTLED })
    renderApp('/login')

    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'erin@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Correct-Horse-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    const alert = (await screen.findByText('Could not sign in')).closest('[role="alert"]')
    expect(alert.textContent).toContain(AUTH_THROTTLED)
    expect(alert.textContent).not.toContain('30 seconds')
    expect(document.body.textContent).not.toContain('Request was throttled')
    expect(document.body.textContent).not.toContain(TEXT.askRateLimitedTitle)
  })

  it('shows the same text for a 429 on registration', async () => {
    serveApi({ ...SIGNED_OUT, 'POST /api/auth/register': THROTTLED })
    renderApp('/register')

    fireEvent.change(await screen.findByLabelText('Full name'), { target: { value: 'Erin Employee' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'erin@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Correct-Horse-1' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'Correct-Horse-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText(AUTH_THROTTLED)).toBeTruthy()
    expect(document.body.textContent).not.toContain('Request was throttled')
  })
})
