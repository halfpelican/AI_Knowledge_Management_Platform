/**
 * Runs before every front-end test file.
 *
 * **No test reaches the network or a running backend.** This is the front-end
 * counterpart of conftest.py's `no_live_provider` fixture, which points every AI
 * provider at a closed port so that an accidental live call fails instead of
 * quietly succeeding against a running FLM server. Here the equivalent is
 * `fetch` and `XMLHttpRequest` — the only two transports src/api/client.js uses —
 * replaced before each test with stand-ins that refuse.
 *
 * **Refusing is not enough on its own, and the afterEach below is why.**
 * `request()` catches a transport failure and turns it into an ordinary
 * "Could not reach the server" ApiError, which a screen renders as a normal
 * failure state — so a blocked call would not fail the test, it would put the
 * screen in a state the test might not look at. Every refused call is therefore
 * recorded, and a test that made one fails in afterEach whatever it asserted.
 *
 * A test supplies the API it needs by stubbing `fetch` again inside the test,
 * answering named routes only. A call nothing answers for reaches the refusal.
 */
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, expect, vi } from 'vitest'

/** Every call that reached a refusing transport during the current test. */
export const refusedCalls = []

/** What the suite answers a request nothing was set up to answer. */
export function refuseFetch(input) {
  const url = typeof input === 'string' ? input : input?.url
  refusedCalls.push(`fetch ${url}`)
  return Promise.reject(new TypeError(`The front-end suite has no network: fetch ${url}`))
}

class RefusingXMLHttpRequest {
  open(method, url) {
    refusedCalls.push(`XMLHttpRequest ${method} ${url}`)
    throw new TypeError(`The front-end suite has no network: XMLHttpRequest ${method} ${url}`)
  }
}

beforeEach(() => {
  refusedCalls.length = 0
  vi.stubGlobal('fetch', vi.fn(refuseFetch))
  vi.stubGlobal('XMLHttpRequest', RefusingXMLHttpRequest)
})

afterEach(() => {
  // Testing Library registers this itself only when the runner exposes globals,
  // and this suite imports `describe`/`it` explicitly instead.
  cleanup()
  vi.unstubAllGlobals()
  expect(refusedCalls, 'a test reached for the network').toEqual([])
})

// jsdom does no layout, so it has no scrollIntoView. The Ask screen calls it on
// the turn it has just focused (usability finding 1); a no-op is the honest
// stand-in, because nothing here can observe scrolling anyway.
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {}
}
