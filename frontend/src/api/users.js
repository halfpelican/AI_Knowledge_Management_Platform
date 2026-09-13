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
