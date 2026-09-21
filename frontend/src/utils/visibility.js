import { ROLES, TEXT } from '../constants.js'

/**
 * The visibility choice offered when content is contributed (FR-08, FR-09).
 *
 * Two values, not a list of role names, because only two scopes can be asked for
 * without the server refusing the request (D-29):
 *
 * - `everyone` sends no `visible_to_roles` field at all. Omitted means both
 *   roles — "a document nobody thought about is visible to everybody", so an
 *   omitted field can never accidentally hide content.
 * - `administrators` sends `["Administrator"]`, and is offered only to an
 *   Administrator. A list excluding the contributor's own role is answered 403,
 *   because uploading into a scope you cannot read is how content is lost, so an
 *   Employee is never shown a choice the server would refuse.
 *
 * Narrowing the options by role is usability. The server decides: it re-checks
 * the submitted list against the requesting user's own role on every request
 * (CLAUDE.md §6, invariant 4).
 */
export const VISIBILITY_EVERYONE = 'everyone'
export const VISIBILITY_ADMINISTRATORS = 'administrators'

/** Options for a SelectInput, given the signed-in user's role name. */
export function visibilityOptionsFor(role) {
  const options = [{ value: VISIBILITY_EVERYONE, label: TEXT.visibilityEveryone }]
  if (role === ROLES.administrator) {
    options.push({ value: VISIBILITY_ADMINISTRATORS, label: TEXT.visibilityAdministrators })
  }
  return options
}

/**
 * The `visible_to_roles` value for a choice, or null to omit the field.
 *
 * @param {string} choice One of the two constants above.
 * @returns {string[] | null} Role names to send, or null for "send nothing".
 */
export function rolesForVisibility(choice) {
  return choice === VISIBILITY_ADMINISTRATORS ? [ROLES.administrator] : null
}
