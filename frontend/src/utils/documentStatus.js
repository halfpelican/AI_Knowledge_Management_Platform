import { DOCUMENT_STATUS, TEXT } from '../constants.js'

/**
 * What the screens that show a document's ingestion status may say about it.
 *
 * Shared by the upload queue (FR-08) and the repository list (FR-08, and the
 * list FR-15 builds on). The wording is load-bearing — D-32 turns on saying
 * what a second attempt can actually change — so the rule lives in one place
 * rather than once per screen, where the two copies would drift apart.
 */

/**
 * Whether FR-08's "Processing failed. Please try again" action is offered for a
 * document in this status.
 *
 * Every status except "Indexed": the three a 422 records, and "Partially
 * indexed", where the document is searchable but some of its passages are not.
 * A status this build does not know about is offered the action too, because
 * the safe direction for an unrecognised value is to let the user ask rather
 * than to decide silently that nothing can be done.
 *
 * It is a display rule and not a control. The server decides: it answers 409
 * for a document that is already indexed (CLAUDE.md §6, invariant 4).
 */
export function canReprocess(status) {
  return Boolean(status) && status !== DOCUMENT_STATUS.indexed
}

/**
 * What a document in this status shows beside the retry action.
 *
 * FR-08 ties the action to extraction failing, but a file with no text layer
 * parses identically however many times the same bytes are read. Only an
 * "Indexing failed" — a provider outage — is a failure a retry genuinely
 * recovers, so that case gets FR-08's own words and the others say what would
 * actually change the outcome instead of inviting an attempt that cannot work
 * (D-32). The action is still offered in every case the clause names.
 */
export function retryMessageFor(status) {
  if (status === DOCUMENT_STATUS.extractionFailed) return TEXT.processingFailedExtraction
  if (status === DOCUMENT_STATUS.insufficientContent) return TEXT.processingFailedInsufficient
  // Not a failure: the document is in the index, but not all of it is.
  if (status === DOCUMENT_STATUS.partiallyIndexed) return TEXT.reprocessPartiallyIndexed
  // "Indexing failed", and anything a later status vocabulary adds: FR-08's own
  // wording, which is true for a transient failure.
  return TEXT.processingFailed
}
