import { VALIDATION } from '../constants.js'
import { passwordMeetsPolicy } from './password.js'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/**
 * FR-01's client-side checks, in full.
 *
 * The FR keeps the submit button disabled "until all client-side checks pass",
 * so this function decides both what to show under a field and whether the
 * button is enabled: an empty object means every check passed. The server
 * validates authoritatively regardless (CLAUDE.md §6, invariant 4); the password
 * rules here are the same rules it enforces, read from one module
 * (src/utils/password.js) so the two cannot drift.
 */
export function validateRegistration(values) {
  const errors = {}
  if (!values.name.trim()) errors.name = VALIDATION.nameRequired
  if (!values.email.trim()) errors.email = VALIDATION.emailRequired
  else if (!EMAIL_PATTERN.test(values.email.trim())) errors.email = VALIDATION.emailInvalid
  if (!values.password) errors.password = VALIDATION.passwordRequired
  else if (!passwordMeetsPolicy(values.password)) errors.password = VALIDATION.passwordRequirements
  // FR-01 Front-End: the form collects "full name, email, password, confirm
  // password", so a mismatch is a client-side failure with its own message.
  if (!values.confirmPassword) errors.confirmPassword = VALIDATION.confirmPasswordRequired
  else if (values.confirmPassword !== values.password) {
    errors.confirmPassword = VALIDATION.passwordMismatch
  }
  return errors
}

export function validateLogin(values) {
  const errors = {}
  if (!values.email.trim()) errors.email = VALIDATION.emailRequired
  else if (!EMAIL_PATTERN.test(values.email.trim())) errors.email = VALIDATION.emailInvalid
  if (!values.password) errors.password = VALIDATION.passwordRequired
  return errors
}
