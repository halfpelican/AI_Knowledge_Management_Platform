/**
 * The one API client module.
 *
 * This is the only place in the frontend that calls `fetch`. Components and
 * hooks import `get`, `post` or `request` from here; they never fetch directly.
 *
 * Every failure is normalised into an `ApiError` carrying the HTTP status and a
 * fixed, user-facing `message`. The raw backend error string is never used as
 * the message and stack traces are never surfaced (NFR-14 usability, security
 * review finding). Screens may render `error.message` as-is.
 */

const DEFAULT_BASE_URL = 'http://127.0.0.1:8000/api'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, '')

/** Status 0 marks a request that never reached the server. */
export const NETWORK_ERROR_STATUS = 0

const MESSAGES = {
  network: 'Could not reach the server. Check your connection and try again.',
  400: 'Some of the information provided is not valid. Please check it and try again.',
  401: 'Your session has expired. Please sign in again.',
  403: 'You do not have permission to do that.',
  404: 'The requested item could not be found.',
  503: 'The AI service is currently unavailable. Please try again shortly.',
  default: 'Something went wrong. Please try again.',
}

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

async function parseBody(response) {
  if (response.status === 204) return null
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    // Non-JSON body (for example an HTML error page from a proxy): nothing usable.
    return null
  }
}

/**
 * Perform a JSON request against the API.
 *
 * @param {string} path Path relative to the API base, for example `/documents/`.
 * @param {object} [options]
 * @param {string} [options.method] HTTP method, default GET.
 * @param {unknown} [options.body] Serialised as JSON when provided.
 * @param {string} [options.token] Bearer token; the Authorization header is sent only when given.
 * @param {AbortSignal} [options.signal] Abort signal; an aborted request rejects with the
 *   browser's AbortError, not an ApiError, so callers can ignore their own cancellations.
 * @returns {Promise<unknown>} Parsed JSON body, or null for an empty response.
 * @throws {ApiError} For any non-2xx response or network failure.
 */
export async function request(path, { method = 'GET', body, token, signal } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  const url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`

  let response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new ApiError(NETWORK_ERROR_STATUS, MESSAGES.network)
  }

  const data = await parseBody(response)

  if (!response.ok) {
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
