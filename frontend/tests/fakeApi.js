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
 * handling (the 503 message, the ApiError, the JSON parsing, a 429's
 * `Retry-After`) is exercised as shipped rather than replaced.
 *
 * `XMLHttpRequest` is answered from the same table, because src/api/client.js's
 * `upload()` uses it: FR-08's per-file progress needs it, since `fetch` reports
 * none, and FR-09's transcript file goes through the same helper. It is the same
 * rule: a route the table names is answered, and any other is refused and recorded
 * exactly as tests/setup.js's own stand-in records it, so the test fails.
 */
import { vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { refuseFetch, refusedCalls } from './setup.js'

/**
 * Routes are matched on method and path; the query string is not part of the key,
 * and is recorded on each answered request as `search` (`""` when there is none),
 * so a test can assert what a screen asked for as well as where.
 *
 * A route given as a function is called with the request's `URL` and may return a
 * promise, which is how a test answers from the query string or holds a response
 * back to observe a loading state.
 *
 * A route may give `headers`, such as D-79's `Retry-After`, which are sent beside
 * `Content-Type` on whichever transport asked.
 *
 * A request's `body` is recorded as the screen sent it: parsed JSON from `fetch`,
 * and the `FormData` itself from `XMLHttpRequest`, so a test reads a field with
 * `.get()`.
 *
 * @param {Record<string, {status?: number, body?: unknown, headers?: Record<string, string>} | ((url: URL) => {status?: number, body?: unknown, headers?: Record<string, string>} | Promise<{status?: number, body?: unknown, headers?: Record<string, string>}>)>} routes
 * @returns {{method: string, path: string, search: string, body: unknown}[]} every request answered, in order, from both transports
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
      const { status = 200, body = null, headers = {} } = typeof route === 'function' ? await route(url) : route
      // No body is a null body, not an empty string: the Fetch spec refuses any
      // body at all on a 204, so `new Response('', {status: 204})` throws, and the
      // client would have reported FR-15's 204 as an unreachable server. Read as
      // text, a null body is "" exactly as the empty string was.
      return new Response(body === null ? null : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json', ...headers },
      })
    }),
  )
  vi.stubGlobal('XMLHttpRequest', servedXMLHttpRequest(routes, answered))
  return answered
}

/**
 * The part of `EventTarget` the client uses on an `XMLHttpRequest` and on its
 * `upload`: listeners added and removed by type, and events fired at them.
 */
class Listeners {
  constructor() {
    this.byType = new Map()
  }

  addEventListener(type, listener) {
    if (!this.byType.has(type)) this.byType.set(type, new Set())
    this.byType.get(type).add(listener)
  }

  removeEventListener(type, listener) {
    this.byType.get(type)?.delete(listener)
  }

  emit(type, event = {}) {
    for (const listener of [...(this.byType.get(type) ?? [])]) listener({ type, ...event })
  }
}

/**
 * An `XMLHttpRequest` class answering from `routes`, with what src/api/client.js's
 * `upload()` reads: `open`, `setRequestHeader`, `send`, `abort`, the `load`,
 * `error`, `timeout` and `abort` events, `upload`'s `progress` and `load`, then
 * `status`, `responseText` and `getResponseHeader`.
 *
 * Once sent, the whole body is reported transferred at once (one `progress` at
 * 100%, then `upload`'s `load`), and the reply follows when the route answers, a
 * task later at the earliest, so a screen's "uploading" and "processing" states
 * both happen. A route that holds its answer (`heldResponse`) holds the reply.
 */
function servedXMLHttpRequest(routes, answered) {
  return class ServedXMLHttpRequest extends Listeners {
    constructor() {
      super()
      this.upload = new Listeners()
      this.status = 0
      this.responseText = ''
      this.responseHeaders = new Map()
      this.settled = false
    }

    open(method, url) {
      this.method = method.toUpperCase()
      this.url = new URL(url, 'http://localhost')
      this.route = routes[`${this.method} ${this.url.pathname}`]
      if (!this.route) {
        // Refused as tests/setup.js's stand-in refuses: recorded, so the test fails
        // in afterEach whatever it asserted, and thrown, as that one throws.
        refusedCalls.push(`XMLHttpRequest ${method} ${url}`)
        throw new TypeError(`The front-end suite has no network: XMLHttpRequest ${method} ${url}`)
      }
    }

    setRequestHeader() {}

    getResponseHeader(name) {
      return this.responseHeaders.get(name.toLowerCase()) ?? null
    }

    abort() {
      if (this.settled) return
      this.settled = true
      this.emit('abort')
    }

    send(body) {
      answered.push({ method: this.method, path: this.url.pathname, search: this.url.search, body })
      const { route, url } = this
      setTimeout(async () => {
        if (this.settled) return
        this.upload.emit('progress', { lengthComputable: true, loaded: 1, total: 1 })
        this.upload.emit('load')
        const { status = 200, body: replyBody = null, headers = {} } =
          typeof route === 'function' ? await route(url) : route
        if (this.settled) return
        this.settled = true
        this.status = status
        this.responseText = replyBody === null ? '' : JSON.stringify(replyBody)
        for (const [name, value] of Object.entries({ 'Content-Type': 'application/json', ...headers })) {
          this.responseHeaders.set(name.toLowerCase(), String(value))
        }
        this.emit('load')
      }, 0)
    }
  }
}

/**
 * A route that answers only when the test says so, for what a screen does while a
 * request is in flight and what it does with a reply that lands late.
 *
 * `route` goes in the `serveApi` table. Every request it receives waits on one
 * promise, which `release` resolves with `{status, body}` as a plain route would
 * give, and each waiting request is then answered with a response of its own.
 *
 * @returns {{route: () => Promise<{status?: number, body?: unknown}>, release: (response: {status?: number, body?: unknown}) => void}}
 */
export function heldResponse() {
  let release
  const answer = new Promise((resolve) => {
    release = resolve
  })
  return { route: () => answer, release: (response) => release(response) }
}

/**
 * A fixed text of the server's, read from the one place it is defined
 * (apps/core/constants.py, D-27) rather than copied into the test, so the test
 * cannot agree with a front-end copy that has drifted from the server's.
 *
 * Written on one line, or as adjacent literals in parentheses, which Python joins.
 * Neither form uses an escape in that file, and anything else fails loudly here.
 */
function serverText(name) {
  const source = readFileSync(join(import.meta.dirname, '..', '..', 'apps', 'core', 'constants.py'), 'utf8')
  const match = source.match(new RegExp(`^${name} = (?:"(.+)"|\\(((?:\\s*"[^"\\r\\n]*")+)\\s*\\))\\s*$`, 'm'))
  if (!match) throw new Error(`${name} not found in apps/core/constants.py`)
  if (match[1] !== undefined) return match[1]
  return [...match[2].matchAll(/"([^"\r\n]*)"/g)].map((literal) => literal[1]).join('')
}

/** What a reply and a stored turn say when nothing could be answered. */
export const NO_ANSWER_MESSAGE = serverText('NO_ANSWER_MESSAGE')

/** What a stored turn says when none of its citations still points at a chunk. */
export const PROVENANCE_REMOVED_MESSAGE = serverText('PROVENANCE_REMOVED_MESSAGE')

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

/** When every stored turn in these fixtures was asked. */
const ASKED_AT = '2026-10-01T09:00:00Z'

/**
 * A stored turn that renders as answered, as `GET /api/conversations/{id}` returns
 * it: its statements, each with its `chunk_id`, and since D-78 the `sources` it
 * consulted, in the live reply's shape. No `partial_matches`, which no turn carries.
 *
 * @param {{question: string, statements: object[], sources: object[]}} turn
 */
export function storedAnsweredTurn({ question, statements, sources }) {
  return { question, answered: true, asked_at: ASKED_AT, message: null, statements, sources }
}

/**
 * A stored turn none of whose citations still points at a chunk (D-67): its own
 * message, no statements, `sources: []`, and the one key present only on this state.
 *
 * @param {{question: string}} turn
 */
export function storedProvenanceRemovedTurn({ question }) {
  return {
    question,
    answered: false,
    asked_at: ASKED_AT,
    message: PROVENANCE_REMOVED_MESSAGE,
    statements: [],
    sources: [],
    provenance_removed: true,
  }
}
