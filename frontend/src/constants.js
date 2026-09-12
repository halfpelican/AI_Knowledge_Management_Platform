export const APP_TITLE = 'Organisational Knowledge Platform'

/** Role names as the API returns them (FR-05). */
export const ROLES = {
  employee: 'Employee',
  administrator: 'Administrator',
}

/** Mirrors the server's password validators (docs/api-contract.md, registration). */
export const PASSWORD_MIN_LENGTH = 8

/** Client-side validation text. Fixed here so every form says the same thing. */
export const VALIDATION = {
  nameRequired: 'Enter your name.',
  emailRequired: 'Enter your email address.',
  emailInvalid: 'Enter a valid email address.',
  passwordRequired: 'Enter a password.',
  passwordTooShort: `Use at least ${PASSWORD_MIN_LENGTH} characters.`,
}

/** Fixed, user-facing text for the auth and role screens. */
export const TEXT = {
  sessionExpired: 'Your session has expired. Please sign in again.',
  signedOut: 'You have signed out.',
  registered: 'Your account has been created. Sign in to continue.',
  notPermittedTitle: 'Not permitted',
  notPermitted: 'You do not have permission to view this page.',
  checkingSession: 'Checking your session…',
  loadingUsers: 'Loading users…',
  noUsers: 'There are no users to show.',
  roleSaved: (name, role) => `${name}'s role is now ${role}.`,
}
