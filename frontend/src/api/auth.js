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
 *
 * D-137's "Remember me": `remember: true` gives the session REMEMBERED_SESSION_DAYS
 * without use instead of 60 minutes. The contract makes the field optional and `false`
 * when absent, and calls an unticked sign-in "a sign-in without `remember`", so an
 * unticked box sends the body as it always was, `{email, password}`; the server then
 * gives FR-04's 60 minutes, and ends a remembered session this browser already holds.
 */
export function login({ email, password, remember = false }) {
  return post('/auth/login', remember === true ? { email, password, remember: true } : { email, password })
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

/**
 * D-137's self-service reset, step one, anonymous. 200 `{"detail": "If an account uses
 * this address, ..."}`, the same status and body for every well-formed address, whether
 * or not an account uses it (D-25), and only an account is emailed a link; 400
 * `{"email": [...]}` for an address missing, blank or not a valid format, decided from
 * the text alone; 429 past the `auth` rate, with `Retry-After` (docs/api-contract.md,
 * "Resetting a forgotten password").
 */
export function requestPasswordReset({ email }) {
  return post('/auth/password-reset', { email })
}

/**
 * D-137's self-service reset, step two, anonymous: the emailed link's `uid` and `token`
 * with the new password. 200 `{"detail": "Your password has been reset. ..."}`: every
 * session of the account ends, and nobody is signed in. 400 `{"detail": ...}`, one body
 * for every link that does not work; 400 `{"new_password": [...]}` for a password
 * registration would refuse, which leaves the link working; 400 with DRF's messages for
 * a field missing, blank or null; 429 past the `auth` rate (docs/api-contract.md,
 * "Resetting a forgotten password").
 */
export function confirmPasswordReset({ uid, token, newPassword }) {
  return post('/auth/password-reset/confirm', { uid, token, new_password: newPassword })
}

/**
 * The `detail` of a 200 from one of D-137's two reset routes, where it is text, else
 * null. Each route answers success with one fixed sentence written for the person, and
 * the page shows it as sent, so what it says (the link's life, for one) is the server's
 * own. Only a success's `detail` is read here: a refusal's is never shown (src/api/client.js).
 */
export function replyDetail(reply) {
  const detail = reply && typeof reply === 'object' ? reply.detail : undefined
  return typeof detail === 'string' && detail.trim() !== '' ? detail : null
}
