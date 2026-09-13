import { ApiError } from '../api/client.js'

/**
 * Pull field-level messages out of a failed request so a form can place them
 * under the field they concern.
 *
 * FR-01 Front-End: "On failure, (e.g., email already registered), an inline
 * error message appears under the relevant field." Two shapes carry a field
 * failure:
 *
 * - `400 {"field": ["message", ...]}`, DRF's validation shape. Only the fields
 *   the form knows about are read, and only when the value is a list of
 *   strings, so nothing unexpected from the server reaches the screen. DRF
 *   validation messages (for example the password rules) are written for end
 *   users and are the only backend text a form shows.
 * - `409` on registration, whose body is a `detail` rather than a field map.
 *   The client knows what that 409 means — the contract has exactly one, the
 *   duplicate address — so `conflictField` names the field it belongs under and
 *   the fixed `ApiError.message` is placed there instead of in a form-level
 *   banner.
 *
 * Every other failure uses the fixed `ApiError.message` as a form-level error.
 * A raw backend error string or stack trace is never surfaced.
 *
 * @param {unknown} error The caught error.
 * @param {string[]} fields Field names the form can display.
 * @param {object} [options]
 * @param {string} [options.conflictField] Field a 409 belongs under.
 * @returns {{ fieldErrors: Record<string, string>, formError: string | null }}
 */
export function extractFieldErrors(error, fields, { conflictField } = {}) {
  const fieldErrors = {}
  if (!(error instanceof ApiError)) return { fieldErrors, formError: null }

  if (error.status === 409 && conflictField) {
    // Inline under the field, and no banner as well: one message, one place.
    fieldErrors[conflictField] = error.message
    return { fieldErrors, formError: null }
  }

  if (error.status !== 400) return { fieldErrors, formError: error.message }

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
