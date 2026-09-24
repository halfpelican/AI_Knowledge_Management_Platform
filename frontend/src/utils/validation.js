import {
  QUESTION_MAXIMUM_LENGTH,
  QUESTION_MINIMUM_LENGTH,
  SEARCH_MINIMUM_LENGTH,
  TRANSCRIPT_SOURCE,
  VALIDATION,
} from '../constants.js'
import { todayIsoDate } from './dates.js'
import { passwordMeetsPolicy } from './password.js'
import { screenFile } from './uploads.js'

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

/**
 * FR-09's client-side checks. Keys are the API's own field names, so a 400 can
 * overwrite them from `details` without a second naming scheme
 * (src/utils/fieldErrors.js).
 *
 * `source` is "text" or "file": exactly one carries the transcript, because
 * supplying both is a 400 and neither is a 400 as well. The minimum transcript
 * length is not checked here — it is counted in tokens by the same definition
 * the chunker uses (D-31), which is not something the browser can reproduce, so
 * the server owns it and answers 400.
 */
export function validateMeetingIngestion({ title, meetingDate, transcriptText, source, file }) {
  const errors = {}
  if (!title.trim()) errors.title = VALIDATION.meetingTitleRequired
  if (!meetingDate) errors.meeting_date = VALIDATION.meetingDateRequired
  else if (meetingDate > todayIsoDate()) errors.meeting_date = VALIDATION.meetingDateFuture
  if (source === TRANSCRIPT_SOURCE.file) {
    if (!file) errors.file = VALIDATION.transcriptFileRequired
    else {
      // The same pre-transfer screening the document upload does: FR-09's file
      // goes through FR-08's signature check and parsers on the server.
      const rejection = screenFile(file)
      if (rejection) errors.file = rejection
    }
  } else if (!transcriptText.trim()) {
    errors.transcript_text = VALIDATION.transcriptRequired
  }
  return errors
}

/**
 * FR-12's client-side search check: "queries shorter than two characters are
 * rejected client-side".
 *
 * The length is measured on the term **as typed**, with no trimming, because that
 * is what the server measures: it stores and matches the term character for
 * character, and a two-character query of whitespace is long enough and matches
 * whatever the caller may already list. Trimming here would refuse a query the
 * server accepts, and would mean the screen and the `SearchLog` row disagreed
 * about what was searched for.
 *
 * @param {string} term
 * @returns {string | null} The message to show, or null when the term is askable.
 */
export function searchTermError(term) {
  const value = term ?? ''
  if (value.length === 0) return VALIDATION.searchTermRequired
  if (value.length < SEARCH_MINIMUM_LENGTH) return VALIDATION.searchTermTooShort
  return null
}

/**
 * FR-12's question bounds, mirrored from the server so the submit button can stay
 * disabled until the question is askable — the same arrangement FR-01's password
 * rules use.
 *
 * Measured as typed for the same reason as above: the pipeline applies the bounds
 * to the question character for character and `QueryLog.question` stores it as
 * asked. Both bounds are inclusive. The server answers 400 either way
 * (CLAUDE.md §6, invariant 4); this only decides what the screen says first.
 *
 * @param {string} question
 * @returns {string | null}
 */
export function questionError(question) {
  const value = question ?? ''
  if (value.length === 0) return VALIDATION.questionRequired
  if (value.length < QUESTION_MINIMUM_LENGTH) return VALIDATION.questionTooShort
  if (value.length > QUESTION_MAXIMUM_LENGTH) return VALIDATION.questionTooLong
  return null
}
