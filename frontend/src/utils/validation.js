import { PASSWORD_MIN_LENGTH, VALIDATION } from '../constants.js'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/**
 * Minimal client-side checks so an obviously incomplete form does not need a
 * round trip. The server validates authoritatively; these only mirror the
 * contract's stated rules (docs/api-contract.md, registration).
 */
export function validateRegistration(values) {
  const errors = {}
  if (!values.name.trim()) errors.name = VALIDATION.nameRequired
  if (!values.email.trim()) errors.email = VALIDATION.emailRequired
  else if (!EMAIL_PATTERN.test(values.email.trim())) errors.email = VALIDATION.emailInvalid
  if (!values.password) errors.password = VALIDATION.passwordRequired
  else if (values.password.length < PASSWORD_MIN_LENGTH) errors.password = VALIDATION.passwordTooShort
  return errors
}

export function validateLogin(values) {
  const errors = {}
  if (!values.email.trim()) errors.email = VALIDATION.emailRequired
  if (!values.password) errors.password = VALIDATION.passwordRequired
  return errors
}
