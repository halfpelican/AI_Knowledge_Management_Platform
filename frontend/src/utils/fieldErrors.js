import { ApiError } from '../api/client.js'

/**
 * Pull field-level validation messages out of a 400 response.
 *
 * The contract's validation shape is DRF's: `{"field": ["message", ...]}`.
 * Only the fields the form knows about are read, and only when the value is a
 * list of strings, so nothing unexpected from the server reaches the screen.
 * DRF validation messages (for example the password rules) are written for end
 * users and are the only backend text a form shows; every other failure uses
 * the fixed `ApiError.message`.
 *
 * @param {unknown} error The caught error.
 * @param {string[]} fields Field names the form can display.
 * @returns {{ fieldErrors: Record<string, string>, formError: string | null }}
 */
export function extractFieldErrors(error, fields) {
  const fieldErrors = {}
  if (!(error instanceof ApiError) || error.status !== 400) {
    return { fieldErrors, formError: error instanceof ApiError ? error.message : null }
  }

  const details = error.details
  if (details && typeof details === 'object' && !Array.isArray(details)) {
    for (const field of fields) {
      const value = details[field]
      if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'string') {
        fieldErrors[field] = value[0]
      }
    }
  }

  // Nothing landed on a field: fall back to the fixed 400 message.
  const formError = Object.keys(fieldErrors).length === 0 ? error.message : null
  return { fieldErrors, formError }
}
