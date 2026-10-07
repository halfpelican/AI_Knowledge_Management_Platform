/**
 * The one API client module.
 *
 * This is the only place in the frontend that calls `fetch` or constructs an
 * `XMLHttpRequest`. Components and hooks import the endpoint helpers
 * (src/api/auth.js, src/api/users.js, src/api/documents.js, src/api/meetings.js)
 * or `get`, `post`, `patch`, `del`, `request` and `upload` from here; they never talk to
 * the network themselves.
 *
 * Authentication is Django's session cookie (D-21). The cookie is HttpOnly, so
 * this module never sees, stores or forwards a credential: every request is
 * sent with `credentials: "same-origin"` and the browser attaches the cookie.
 * Unsafe methods carry the CSRF token read from the `csrftoken` cookie, which
 * the login and current-user responses set.
 *
 * Every failure is normalised into an `ApiError` carrying the HTTP status and a
 * fixed, user-facing `message`. The raw backend error string is never used as
 * the message and stack traces are never surfaced (NFR-14 usability, security
 * review finding). Screens may render `error.message` as-is. The parsed body is
 * kept on `error.details` so a form can place a 400's field validation messages
 * next to the fields (see src/utils/fieldErrors.js).
 */

import { VALIDATION } from '../constants.js'

/* Same-origin path: the Vite dev server proxies it to Django and the alpha
   deployment serves the built front end from the API's origin (D-21). */
const DEFAULT_BASE_URL = '/api'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, '')

/** Status 0 marks a request that never reached the server. */
export const NETWORK_ERROR_STATUS = 0

const CSRF_COOKIE_NAME = 'csrftoken'
const CSRF_HEADER_NAME = 'X-CSRFToken'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

const MESSAGES = {
  network: 'Could not reach the server. Check your connection and try again.',
  400: 'Some of the information provided is not valid. Please check it and try again.',
  401: 'Your session has expired. Please sign in again.',
  403: 'You do not have permission to do that.',
  404: 'The requested item could not be found.',
  // The only 409 in the contract is FR-01's duplicate address, which the
  // registration form places under the email field (src/utils/fieldErrors.js).
  409: VALIDATION.emailTaken,
  // Registration and login are rate limited per client address (D-26); reachable
  // in a demonstration, since the lockout scenario alone needs several attempts.
  429: 'Too many attempts. Please wait a minute and try again.',
  503: 'The AI service is currently unavailable. Please try again shortly.',
  default: 'Something went wrong. Please try again.',
}

/** The contract's fixed login failure text (same for unknown email and wrong password). */
export const LOGIN_FAILED_MESSAGE = 'Invalid email or password.'

export class ApiError extends Error {
  /**
   * @param {number} status HTTP status, or NETWORK_ERROR_STATUS when no response arrived.
   * @param {string} message Fixed, safe, user-facing text.
   * @param {unknown} [details] Parsed response body, if any. Kept for form-level
   *   handling (for example field validation); never rendered verbatim.
   */
  constructor(status, message, details = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

export function messageForStatus(status) {
  if (status === NETWORK_ERROR_STATUS) return MESSAGES.network
  return MESSAGES[status] ?? MESSAGES.default
}

/* ---- Session expiry notification ---------------------------------------- */

const unauthorizedListeners = new Set()

/**
 * Subscribe to 401 responses. The auth provider uses this to notice that the
 * session has expired mid-use (FR-04, 60-minute inactivity expiry) and to send
 * the user back to the login screen. Returns an unsubscribe function.
 *
 * @param {(path: string) => void} listener
 */
export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

function notifyUnauthorized(path) {
  for (const listener of unauthorizedListeners) listener(path)
}

/* ---- Helpers ------------------------------------------------------------ */

export function readCookie(name) {
  if (typeof document === 'undefined' || !document.cookie) return null
  const prefix = `${name}=`
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) return decodeURIComponent(trimmed.slice(prefix.length))
  }
  return null
}

/** Parsed JSON, or null for an empty or non-JSON body. */
function parseJson(text) {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    // Non-JSON body (for example an HTML error page from a proxy): nothing usable.
    return null
  }
}

async function parseBody(response) {
  if (response.status === 204) return null
  return parseJson(await response.text())
}

/** The rejection an aborted request produces, matching what fetch throws. */
function abortError() {
  if (typeof DOMException === 'function') {
    return new DOMException('The operation was aborted.', 'AbortError')
  }
  const error = new Error('The operation was aborted.')
  error.name = 'AbortError'
  return error
}

/* ---- Request ------------------------------------------------------------ */

/**
 * Perform a JSON request against the API.
 *
 * @param {string} path Path relative to the API base, for example `/auth/login`.
 * @param {object} [options]
 * @param {string} [options.method] HTTP method, default GET.
 * @param {unknown} [options.body] Serialised as JSON when provided.
 * @param {AbortSignal} [options.signal] Abort signal; an aborted request rejects with the
 *   browser's AbortError, not an ApiError, so callers can ignore their own cancellations.
 * @returns {Promise<unknown>} Parsed JSON body, or null for an empty response.
 * @throws {ApiError} For any non-2xx response or network failure.
 */
export async function request(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const upperMethod = method.toUpperCase()
  if (!SAFE_METHODS.has(upperMethod)) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME)
    if (csrfToken) headers[CSRF_HEADER_NAME] = csrfToken
  }

  const url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`

  let response
  try {
    response = await fetch(url, {
      method: upperMethod,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
      signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new ApiError(NETWORK_ERROR_STATUS, MESSAGES.network)
  }

  const data = await parseBody(response)

  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized(path)
    throw new ApiError(response.status, messageForStatus(response.status), data)
  }

  return data
}

export function get(path, options = {}) {
  return request(path, { ...options, method: 'GET' })
}

export function post(path, body, options = {}) {
  return request(path, { ...options, method: 'POST', body })
}

export function patch(path, body, options = {}) {
  return request(path, { ...options, method: 'PATCH', body })
}

/**
 * DELETE. Named `del` because `delete` is a reserved word. It sends no body, and
 * a 204 resolves to null, as every empty response does.
 */
export function del(path, options = {}) {
  return request(path, { ...options, method: 'DELETE' })
}

/* ---- Upload ------------------------------------------------------------- */

/**
 * Send a `FormData` body and report how much of it has been transferred.
 *
 * This is the one thing `request()` above cannot do: `fetch` exposes no upload
 * progress, and FR-08's front end requires that "each file shows a progress
 * indicator and an individual progress bar during upload", so the transfer has
 * to be observed. `XMLHttpRequest` is the only browser API that reports it, and
 * it lives here, beside `request()`, rather than in a component — the rule is
 * one API client module, not one transport (CLAUDE.md, src/api/client.js
 * header).
 *
 * Every guarantee `request()` makes is kept:
 *
 * - Cookies. `withCredentials` is left false, which for XHR means exactly what
 *   `credentials: "same-origin"` means for fetch: the session cookie is sent to
 *   our own origin and to nobody else.
 * - CSRF. POST is unsafe, so the `csrftoken` cookie travels in `X-CSRFToken`
 *   (D-21). The browser holds a session by the time anything is uploaded, so
 *   DRF's session authenticator enforces the check.
 * - `Content-Type` is deliberately NOT set: the browser writes
 *   `multipart/form-data` with the boundary it generated, and setting it by hand
 *   omits the boundary and produces an unparseable body.
 * - Failures become an `ApiError` with a fixed, safe message and the parsed body
 *   on `details`. FR-08's 422 carries `doc_id` and `status`, which is how a row
 *   can name the document it failed on; a raw backend string is never rendered.
 * - A 401 notifies the session-expiry listener, as every other call does.
 *
 * @param {string} path Path relative to the API base, for example `/documents`.
 * @param {FormData} formData The multipart body.
 * @param {object} [options]
 * @param {string} [options.method] HTTP method, default POST.
 * @param {(percent: number) => void} [options.onProgress] Called with 0–100 as
 *   the body is transferred, and once with 100 when the last byte has gone. The
 *   server is still working at that point — ingestion is synchronous — so a
 *   caller showing a bar should switch to an indeterminate "processing" state
 *   there rather than call the upload finished.
 * @param {AbortSignal} [options.signal] Aborts the transfer; rejects with
 *   AbortError, not an ApiError, as `request()` does.
 * @returns {Promise<unknown>} Parsed JSON body of a 2xx response.
 * @throws {ApiError} For any non-2xx response or network failure.
 */
export function upload(path, formData, { method = 'POST', onProgress, signal } = {}) {
  const url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
  const upperMethod = method.toUpperCase()

  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError())
      return
    }

    const xhr = new XMLHttpRequest()
    xhr.open(upperMethod, url, true)
    xhr.setRequestHeader('Accept', 'application/json')
    if (!SAFE_METHODS.has(upperMethod)) {
      const csrfToken = readCookie(CSRF_COOKIE_NAME)
      if (csrfToken) xhr.setRequestHeader(CSRF_HEADER_NAME, csrfToken)
    }

    function detach() {
      signal?.removeEventListener('abort', handleAbortSignal)
    }

    function handleAbortSignal() {
      xhr.abort()
    }

    if (onProgress) {
      xhr.upload.addEventListener('progress', (event) => {
        // Not computable while the browser is still measuring the body; the bar
        // stays at its last value rather than jumping about.
        if (event.lengthComputable && event.total > 0) {
          onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
        }
      })
      // The last byte has left. Reported explicitly so the caller can move to
      // "processing" even where no progress event reached 100.
      xhr.upload.addEventListener('load', () => onProgress(100))
    }

    xhr.addEventListener('load', () => {
      detach()
      const data = parseJson(xhr.responseText)
      const ok = xhr.status >= 200 && xhr.status < 300
      if (ok) {
        resolve(data)
        return
      }
      if (xhr.status === 401) notifyUnauthorized(path)
      reject(new ApiError(xhr.status, messageForStatus(xhr.status), data))
    })

    xhr.addEventListener('error', () => {
      detach()
      reject(new ApiError(NETWORK_ERROR_STATUS, MESSAGES.network))
    })

    xhr.addEventListener('timeout', () => {
      detach()
      reject(new ApiError(NETWORK_ERROR_STATUS, MESSAGES.network))
    })

    xhr.addEventListener('abort', () => {
      detach()
      reject(abortError())
    })

    signal?.addEventListener('abort', handleAbortSignal)
    xhr.send(formData)
  })
}
