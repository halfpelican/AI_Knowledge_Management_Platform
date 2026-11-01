/**
 * The API client talks to its own origin, with nothing in between (Stage 5 item 9,
 * D-21, D-64).
 *
 * In development the Vite proxy forwards `/api` to Django; the alpha's production
 * build has no proxy, and Django serves the SPA and `/api` from one origin. What
 * that depends on is the request the client makes: a root-relative address, the
 * session cookie sent on it, and on an unsafe method the CSRF token copied from the
 * `csrftoken` cookie into `X-CSRFToken`, because no proxy will add it.
 *
 * tests/fakeApi.js matches a route by its path alone, so the other suites would
 * pass against `http://127.0.0.1:8000/api/...` as readily as against `/api/...`.
 * The address the client passes to `fetch` is read here directly.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { API_BASE_URL, apiUrl, get, post } from '../src/api/client.js'
import { documentDownloadUrl } from '../src/api/documents.js'
import { serveApi } from './fakeApi.js'

const CSRF_TOKEN = 'token-from-the-csrftoken-cookie'

/** The address and options of every request the client handed to `fetch`. */
function fetchCalls() {
  return globalThis.fetch.mock.calls.map(([input, init = {}]) => ({ input, init }))
}

describe('the API client on the alpha’s single origin', () => {
  beforeEach(() => {
    document.cookie = `csrftoken=${CSRF_TOKEN}; path=/`
  })

  afterEach(() => {
    document.cookie = 'csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  })

  it('builds every API address as a path from the site root, with no scheme or host', () => {
    expect(API_BASE_URL).toBe('/api')
    expect(apiUrl('/documents')).toBe('/api/documents')
    expect(apiUrl('documents')).toBe('/api/documents')
    // The one API address the browser follows itself, as a plain link (FR-15, D-75).
    expect(documentDownloadUrl('doc-1')).toBe('/api/documents/doc-1/download')
  })

  it('sends an unsafe request to its own origin with the session cookie and the CSRF token', async () => {
    serveApi({ 'POST /api/auth/logout': { status: 200 } })

    await post('/auth/logout')

    const [{ input, init }] = fetchCalls()
    expect(input).toBe('/api/auth/logout')
    expect(init.credentials).toBe('same-origin')
    expect(init.headers['X-CSRFToken']).toBe(CSRF_TOKEN)
  })

  it('sends a safe request to its own origin with the session cookie and no CSRF token', async () => {
    serveApi({ 'GET /api/auth/me': { body: { id: 1 } } })

    await get('/auth/me')

    const [{ input, init }] = fetchCalls()
    expect(input).toBe('/api/auth/me')
    expect(init.credentials).toBe('same-origin')
    expect(init.headers).not.toHaveProperty('X-CSRFToken')
  })
})
