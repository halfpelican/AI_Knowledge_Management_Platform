export const APP_TITLE = 'Organisational Knowledge Platform'

/** Role names as the API returns them (FR-05). */
export const ROLES = {
  employee: 'Employee',
  administrator: 'Administrator',
}

/**
 * FR-02: "On success, user is redirected to a role-specific dashboard (e.g.,
 * Administrator -> Admin Console; Employee -> Knowledge Dashboard)."
 *
 * The dashboards themselves are FR-14 and arrive in Stage 5. These routes exist
 * now so the redirect is genuinely role-specific today; Stage 5 replaces what they
 * render, not where they live. See docs/decisions.md D-25.
 */
export const DASHBOARD_PATHS = {
  [ROLES.administrator]: '/admin',
  [ROLES.employee]: '/dashboard',
}

/** Where a signed-in user belongs. Falls back to the shared placeholder. */
export function dashboardPathForRole(role) {
  return DASHBOARD_PATHS[role] ?? '/'
}

/**
 * Client-side validation text. Fixed here so every form says the same thing.
 * The password rules themselves live in src/utils/password.js, which is the
 * single copy of the policy the server also enforces (FR-01).
 */
export const VALIDATION = {
  nameRequired: 'Enter your name.',
  emailRequired: 'Enter your email address.',
  emailInvalid: 'Enter a valid email address.',
  emailTaken: 'That email address is already registered.',
  passwordRequired: 'Enter a password.',
  passwordRequirements: 'Your password does not meet all of the requirements listed below.',
  confirmPasswordRequired: 'Re-enter your password.',
  passwordMismatch: 'The two passwords do not match.',
}

/** Fixed, user-facing text for the auth and role screens. */
export const TEXT = {
  sessionExpired: 'Your session has expired. Please sign in again.',
  // FR-04 wording: "a brief confirmation 'You've been logged out'".
  loggedOut: 'You’ve been logged out.',
  registered: 'Your account has been created. Sign in to continue.',
  // FR-02: "Where the account is locked and the submitted password was correct,
  // a distinct message is shown." Distinct from the 401 text, and it names no
  // account detail, so it discloses nothing a 401 does not.
  accountLocked:
    'This account is temporarily locked after too many failed sign-in attempts. ' +
    'Please try again later.',
  // FR-06: the "403 - Access Denied" page a guarded route redirects to. It never
  // describes what the requested screen would have contained.
  accessDeniedTitle: '403 – Access Denied',
  accessDenied: 'You do not have permission to view this page.',
  notPermittedTitle: 'Not permitted',
  notPermitted: 'You do not have permission to view this page.',
  checkingSession: 'Checking your session…',
  loadingUsers: 'Loading users…',
  noUsers: 'There are no users to show.',
  roleSaved: (name, role) => `${name}'s role is now ${role}.`,
  // FR-05 confirmation dialogue, worded as the FR's own example
  // ("Change Jane Doe's role to Admin?").
  roleChangeConfirm: (name, role) => `Change ${name}'s role to ${role}?`,
  roleChangeStale: 'That user or role no longer exists. The list has been reloaded.',
  // FR-05: "a user cannot remove their own administrator role, preventing
  // accidental lockout of the last administrator."
  roleChangeSelfDemotion:
    'You cannot remove your own Administrator role. Ask another Administrator to change it for you.',
}
