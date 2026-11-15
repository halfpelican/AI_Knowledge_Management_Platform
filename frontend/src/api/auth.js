/**
 * Authentication endpoints (FR-01, FR-02, FR-04), per docs/api-contract.md.
 * Thin wrappers over the one API client; no fetch here.
 */
import { get, post } from './client.js'

/**
 * The `code` on login's 403 for a locked account, `{"detail": "...", "code":
 * "account_locked", "retry_after": N}`, which is how the sign-in page tells it from
 * any other 403. `detail` is never parsed (docs/api-contract.md). The sweep in
 * apps/api/tests/test_in_flight_codes_agreement.py holds this copy to
 * apps/api/views.py ACCOUNT_LOCKED_CODE.
 */
export const ACCOUNT_LOCKED_CODE = 'account_locked'

/** FR-01. 201 user object; 400 field validation; 409 email already registered. */
export function register({ name, email, password }) {
  return post('/auth/register', { name, email, password })
}

/**
 * FR-02. 200 user object and sets the session cookie; 400 a missing field or a
 * malformed address; 401 an unknown address or a wrong password, one message for
 * both; 403 the account is locked (docs/api-contract.md, D-25).
 *
 * FR-03 (D-130): the 403 carries `code` ACCOUNT_LOCKED_CODE and `retry_after`, the
 * whole seconds until the lock ends, and only a request whose password matched gets
 * it. The 401 never carries either, so it is the same for every address.
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

/**
 * FR-03's running lockout policy (D-130 decision 7): 200
 * `{"lockout_threshold": 5, "lockout_duration_seconds": 900}`, anonymous, the same for
 * every caller. The sign-in page asks after its first failed attempt, so a policy set
 * in the server's .env reaches the page without a rebuild.
 */
export function getLockoutPolicy() {
  return get('/auth/lockout-policy')
}

/** The signed-in user, or 401. Also refreshes the csrftoken cookie. */
export function fetchCurrentUser(options = {}) {
  return get('/auth/me', options)
}
