/**
 * The API a test is allowed to talk to, and nothing else.
 *
 * `serveApi` stubs `fetch` with a table of routes keyed `"METHOD /api/path"`.
 * A request for a route the table does not name is handed to tests/setup.js's
 * refusal, which records it and fails the test — so a screen that starts making
 * a request nobody expected is caught, rather than answered with whatever a
 * permissive fake would have made up.
 *
 * Mocked at `fetch`, beneath src/api/client.js, so the client's own status
 * handling (the 503 message, the ApiError, the JSON parsing) is exercised as
 * shipped rather than replaced.
 */
import { vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { refuseFetch } from './setup.js'

/**
 * Routes are matched on method and path; the query string is not part of the key,
 * and is recorded on each answered request as `search` (`""` when there is none),
 * so a test can assert what a screen asked for as well as where.
 *
 * A route given as a function is called with the request's `URL` and may return a
 * promise, which is how a test answers from the query string or holds a response
 * back to observe a loading state.
 *
 * @param {Record<string, {status?: number, body?: unknown} | ((url: URL) => {status?: number, body?: unknown} | Promise<{status?: number, body?: unknown}>)>} routes
 * @returns {{method: string, path: string, search: string, body: unknown}[]} every request answered, in order
 */
export function serveApi(routes) {
  const answered = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input, init = {}) => {
      const url = new URL(typeof input === 'string' ? input : input.url, 'http://localhost')
      const method = (init.method ?? 'GET').toUpperCase()
      const route = routes[`${method} ${url.pathname}`]
      if (!route) return refuseFetch(input)
      answered.push({
        method,
        path: url.pathname,
        search: url.search,
        body: init.body ? JSON.parse(init.body) : undefined,
      })
      const { status = 200, body = null } = typeof route === 'function' ? await route(url) : route
      // No body is a null body, not an empty string: the Fetch spec refuses any
      // body at all on a 204, so `new Response('', {status: 204})` throws, and the
      // client would have reported FR-15's 204 as an unreachable server. Read as
      // text, a null body is "" exactly as the empty string was.
      return new Response(body === null ? null : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
  return answered
}

/**
 * The server's fixed no-answer text, read from the one place it is defined
 * (apps/core/constants.py, D-27) rather than copied into the test, so the test
 * cannot agree with a front-end copy that has drifted from the server's.
 */
export const NO_ANSWER_MESSAGE = (() => {
  const source = readFileSync(join(import.meta.dirname, '..', '..', 'apps', 'core', 'constants.py'), 'utf8')
  const match = source.match(/^NO_ANSWER_MESSAGE = "(.+)"$/m)
  if (!match) throw new Error('NO_ANSWER_MESSAGE not found in apps/core/constants.py')
  return match[1]
})()

export const CONVERSATION = {
  conversation_id: '6f1c2a54-0000-4000-8000-000000000001',
  title: 'New conversation',
  last_updated_at: '2026-09-28T09:00:00Z',
}

/**
 * The reply `POST /api/ask` sends on both no-answer paths: the same key set as an
 * answer, both lists empty, and the fixed message (docs/api-contract.md).
 */
export function noAnswerReply() {
  return {
    answered: false,
    message: NO_ANSWER_MESSAGE,
    statements: [],
    sources: [],
    result_count: 0,
    partial_matches: [],
    conversation: CONVERSATION,
  }
}

/** An answered reply: one verified statement, cited to one passage of one source. */
export function answeredReply() {
  return {
    answered: true,
    message: null,
    statements: [{ position: 1, text: 'Annual leave accrues at four weeks a year.', chunk_id: 'chunk-a' }],
    sources: [
      {
        source_type: 'document',
        source_id: 'doc-1',
        title: 'Leave policy',
        date: '2026-08-01',
        passages: [{ chunk_id: 'chunk-a', text: 'Full-time staff accrue four weeks of annual leave per year.' }],
      },
    ],
    result_count: 1,
    partial_matches: [],
    conversation: CONVERSATION,
  }
}
