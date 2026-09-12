/**
 * Role management endpoints (FR-05), per docs/api-contract.md.
 * Thin wrappers over the one API client; no fetch here.
 */
import { get, patch } from './client.js'

/** Any signed-in user. 200 [{name, description, permissions}]. */
export function listRoles(options = {}) {
  return get('/roles', options)
}

/** Administrator only. 200 [user object] ordered by created_at; 403 for an Employee. */
export function listUsers(options = {}) {
  return get('/users', options)
}

/** Administrator only. 200 updated user object; 400 unknown role; 403; 404 unknown user. */
export function updateUserRole(userId, role) {
  return patch(`/users/${encodeURIComponent(userId)}/role`, { role })
}
