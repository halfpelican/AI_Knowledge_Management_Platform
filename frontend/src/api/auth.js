/**
 * Authentication endpoints (FR-01, FR-02, FR-04), per docs/api-contract.md.
 * Thin wrappers over the one API client; no fetch here.
 */
import { get, post } from './client.js'

/** FR-01. 201 user object; 400 field validation; 409 email already registered. */
export function register({ name, email, password }) {
  return post('/auth/register', { name, email, password })
}

/**
 * FR-02. 200 user object and sets the session cookie; 400 a missing field or a
 * malformed address; 401 an unknown address or a wrong password, one message for
 * both; 403 the account is locked (docs/api-contract.md, D-25).
 */
export function login({ email, password }) {
  return post('/auth/login', { email, password })
}

/**
 * FR-04. 200 and the session is destroyed server-side; 401 when there was no
 * session. The FR's Responses clause is "200 OK on success" (D-25); the client
 * ignores the body either way, so a 204 from an older build is handled too.
 */
export function logout() {
  return post('/auth/logout')
}

/** The signed-in user, or 401. Also refreshes the csrftoken cookie. */
export function fetchCurrentUser(options = {}) {
  return get('/auth/me', options)
}
