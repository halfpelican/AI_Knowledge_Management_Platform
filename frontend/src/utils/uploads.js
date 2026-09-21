import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_BYTES, VALIDATION } from '../constants.js'

/**
 * The checks the upload control makes before a byte is transferred (FR-08).
 *
 * FR-08 Front-End: "Unsupported formats are rejected immediately client-side
 * with a message (E.g., File type not supported. Accepted formats: PDF, DOCX,
 * XLSX)", and the size ceiling is applied before the file is sent as well, so a
 * 50 MB transfer is not begun only to be refused.
 *
 * Both are conveniences and neither is a control. The extension is a claim the
 * filename makes; the evidence is the file signature, which only the server
 * reads (FR-08 Validation: "file type is confirmed by inspecting the file
 * signature rather than the extension alone, preventing a disguised file from
 * being accepted"). The server checks the size twice as well, against the
 * declared length and against the bytes it received. A file that passes
 * everything here can still come back 415 or 413, and the upload screen shows
 * that answer against the file's own row (CLAUDE.md §6, invariant 4).
 */

/** The `accept` attribute for a file input: a hint to the picker, not a check. */
export const FILE_INPUT_ACCEPT = ACCEPTED_EXTENSIONS.join(',')

/** The lower-cased extension of a filename, including the dot, or "". */
export function extensionOf(filename) {
  const dot = filename.lastIndexOf('.')
  return dot <= 0 ? '' : filename.slice(dot).toLowerCase()
}

/**
 * The default title for a file: its name without the extension, so the common
 * case is one click. FR-08 requires a title per file and it stays editable.
 */
export function titleFromFilename(filename) {
  const extension = extensionOf(filename)
  const stem = extension ? filename.slice(0, -extension.length) : filename
  return stem.trim() || filename
}

/**
 * Why this file cannot be sent, or null when it may be.
 *
 * @param {File} file
 * @returns {string | null} A fixed, user-facing message naming the accepted
 *   formats or the size ceiling.
 */
export function screenFile(file) {
  if (!ACCEPTED_EXTENSIONS.includes(extensionOf(file.name))) return VALIDATION.fileTypeUnsupported
  if (file.size > MAX_UPLOAD_BYTES) return VALIDATION.fileTooLarge
  return null
}
