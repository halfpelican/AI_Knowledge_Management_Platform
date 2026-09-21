import { TRANSCRIPT_SOURCE, VALIDATION } from '../constants.js'
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
