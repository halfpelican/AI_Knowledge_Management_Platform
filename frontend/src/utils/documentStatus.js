import { DOCUMENT_STATUS, TEXT } from '../constants.js'

/**
 * What the screens that show a document's ingestion status may say about it, and
 * which of them may offer FR-08's retry.
 *
 * Shared by the upload queue (FR-08) and the repository list (FR-08, and the
 * list FR-15 builds on). The wording is load-bearing — D-32 turns on saying
 * what a second attempt can actually change — so the rule lives in one place
 * rather than once per screen, where the two copies would drift apart.
 *
 * **The two questions are separate, and were not before.** "What does this row
 * say" and "is the action offered" were one question while every status except
 * "Indexed" was retryable. D-51's seventh status is the first that must be
 * explained on screen *and* refused the action, so a caller asks for the message
 * and for the affordance independently. A row that said nothing would be the
 * opposite defect: a status a person cannot act on and is told nothing about.
 *
 * Neither function is a control. The server decides (CLAUDE.md §6, invariant 4).
 */

/**
 * Whether FR-08's "Processing failed. Please try again" action is offered for a
 * document in this status.
 *
 * Two statuses are refused it, for different reasons:
 *
 * - **"Indexed"** — there is nothing to redo, and the server agrees: a reprocess
 *   of an indexed document is `409` (D-32).
 * - **"Too large to index"** — the document was refused *before* extraction was
 *   attempted, on a property of the content itself (D-51). D-32's retry re-runs
 *   ingestion against the stored original, so the file is byte-for-byte the one
 *   that was refused: every press would redo extraction and chunking in full and
 *   stop at the identical point. **And the server is not a backstop here** — it
 *   accepts the reprocess and fails it again, so unlike the 409 above this is the
 *   only place the affordance can be withheld. D-51 records the suppression as
 *   required follow-up; until it landed, the row stated the truth and the button
 *   lied.
 *
 * Every other status is offered the action: the statuses a 422 records,
 * "Partially indexed" where the document is searchable but some of its passages
 * are not, and a status this build does not know about — the safe direction for an
 * **unrecognised** value is to let the user ask rather than to decide silently
 * that nothing can be done. That argument is about a value whose outcome this
 * build cannot know. It does not extend to a recognised value whose outcome is
 * known in advance, which is what "Too large to index" now is.
 */
export function canReprocess(status) {
  // Nothing has failed yet, so there is nothing to retry. Unreachable in practice, and listed
  // so it cannot fall through to the retry wording and tell the user that a document still
  // being processed had failed.
  if (status === DOCUMENT_STATUS.processing) return false
  if (!status) return false
  if (status === DOCUMENT_STATUS.indexed) return false
  if (status === DOCUMENT_STATUS.tooLargeToIndex) return false
  return true
}

/**
 * What a document in this status shows beside its status, or null where there is
 * nothing to add.
 *
 * FR-08 ties its action to extraction failing, but a file with no text layer
 * parses identically however many times the same bytes are read. Only an
 * "Indexing failed" — a provider outage — is a failure a retry genuinely
 * recovers, so that case gets FR-08's own words and the others say what would
 * actually change the outcome instead of inviting an attempt that cannot work
 * (D-32).
 *
 * "Too large to index" is the one status whose sentence stands without an action
 * beside it, so it has to say why there is nothing to press as well as what would
 * help (D-51). An unrecognised status still gets FR-08's own wording, which is
 * true for a transient failure and matches the action `canReprocess` still
 * offers it.
 */
export function statusMessageFor(status) {
  if (status === DOCUMENT_STATUS.processing) return TEXT.documentProcessing
  if (status === DOCUMENT_STATUS.indexed) return null
  if (status === DOCUMENT_STATUS.extractionFailed) return TEXT.processingFailedExtraction
  if (status === DOCUMENT_STATUS.insufficientContent) return TEXT.processingFailedInsufficient
  // Refused before anything was attempted, and no retry is offered beside it.
  if (status === DOCUMENT_STATUS.tooLargeToIndex) return TEXT.documentTooLargeToIndex
  // Not a failure: the document is in the index, but not all of it is.
  if (status === DOCUMENT_STATUS.partiallyIndexed) return TEXT.reprocessPartiallyIndexed
  // "Indexing failed", and anything a later status vocabulary adds: FR-08's own
  // wording, which is true for a transient failure.
  return TEXT.processingFailed
}
