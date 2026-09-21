/**
 * Role management endpoints (FR-05), per docs/api-contract.md.
 * Thin wrappers over the one API client; no fetch here.
 */
import { get, patch } from './client.js'

/** Any signed-in user. 200 [{role_id, name, description, permissions}]. */
export function listRoles(options = {}) {
  return get('/roles', options)
}

/** Administrator only. 200 [user object] ordered by created_at; 403 for an Employee. */
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
