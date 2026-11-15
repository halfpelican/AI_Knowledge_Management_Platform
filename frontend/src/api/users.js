/**
 * Role management endpoints (FR-05), and FR-03's release of a lock, per
 * docs/api-contract.md. Thin wrappers over the one API client; no fetch here.
 */
import { get, patch, post } from './client.js'

/** Any signed-in user. 200 [{role_id, name, description, permissions}]. */
export function listRoles(options = {}) {
  return get('/roles', options)
}

/**
 * Administrator only. 200 [user object] ordered by created_at; 403 for an Employee.
 *
 * FR-03 (D-130): for a holder of `release_account_locks` each user also carries
 * `lock`, either null or `{locked_until, locked_at, source_ip}`; `locked_at` and
 * `source_ip` are null for a lock older than the LoginAttempts table. A requester
 * without the permission gets the plain user object, with no `lock` key at all.
 */
export function listUsers(options = {}) {
  return get('/users', options)
}

/**
 * Any signed-in user. 200 [{id, name, email}] ordered by name; 401 without a
 * session. Populates FR-09's attendee picker.
 *
 * **This is not `listUsers` with fewer callers, and merging the two would be a
 * regression (D-34).** `GET /api/users` is Administrator-only because it carries
 * the role each person holds and drives FR-05 role management; the directory
 * carries a name and an address and nothing else. FR-09 gives attendee
 * association to *any* user, and naming an attendee needs a person, not their
 * standing in the organisation. Pointing this at `/users` to save a function
 * would hand every Employee the role of every colleague to satisfy a clause that
 * needs only their name — the server refuses that anyway, with the 403 a test
 * pins in place.
 */
export function listUserDirectory(options = {}) {
  return get('/users/directory', options)
}

/**
 * Administrator only. FR-05's Server-End clause receives `{ user_id, new_role_id }`:
 * the user id travels in the path and the role id in the body (D-25).
 *
 * 200 updated user object; 400 a missing or malformed `role_id`; 401; 403 for an
 * Employee, or for an Administrator demoting themselves; 404 the user or the role
 * does not exist.
 *
 * @param {string} userId UUID of the user whose role is changing.
 * @param {string} roleId UUID of the new role, from GET /api/roles.
 */
export function updateUserRole(userId, roleId) {
  return patch(`/users/${encodeURIComponent(userId)}/role`, { role_id: roleId })
}

/**
 * FR-03 (D-130). Releases a lock: clears `locked_until` and resets the failed
 * attempts, the state natural expiry reaches. The password, the role and any session
 * are never touched. No body is sent.
 *
 * - 200 the user as `listUsers` lists it, now with `lock: null`;
 * - 401 no session;
 * - 403 a role without `release_account_locks`, before any lookup, or the target is
 *   the requester, locked or not;
 * - 404 no such user;
 * - 409 the account is not locked: `locked_until` is empty or already past.
 *
 * @param {string} userId UUID of the user whose lock is released.
 */
export function unlockUser(userId) {
  return post(`/users/${encodeURIComponent(userId)}/unlock`)
}
