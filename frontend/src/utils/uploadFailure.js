import { ApiError, NETWORK_ERROR_STATUS, messageForStatus } from '../api/client.js'
import { TEXT, VALIDATION } from '../constants.js'
import { canReprocess, statusMessageFor } from './documentStatus.js'
import { extractFieldErrors } from './fieldErrors.js'

/**
 * What a failed upload shows against its own row, and whether that row is offered
 * FR-08's retry.
 *
 * **Why this is a module and not a function inside Upload.jsx, where it used to
 * live.** It is pure — an `ApiError` in, a row fragment out, no React and no fetch
 * — and this layer has no test runner (D-25), which is exactly how D-51's retry
 * affordance came to ship offered for a status no retry can change. Out here it can
 * be exercised from Node against real `ApiError` instances. `src/utils/turns.js`
 * left `Ask.jsx` for the same reason at Stage 4 item 1c.
 *
 * Every code FR-08 enumerates gets the message for that case, against that file,
 * rather than a page-level banner: in a queue of five files a banner cannot say
 * which one it means.
 *
 * The 409 does not use `error.message`: the client's generic 409 text is FR-01's
 * duplicate email address, while FR-08's 409 is a document whose *content* has been
 * uploaded before, compared by hash and not by filename.
 *
 * @param {unknown} error the rejection from `uploadDocument` or `reprocessDocument`
 * @returns {{message: string|null, retryable?: boolean, document?: object,
 *   titleError?: string|null}}
 */
export function failureFor(error) {
  if (!(error instanceof ApiError)) {
    return { message: messageForStatus(NETWORK_ERROR_STATUS), retryable: true }
  }
  switch (error.status) {
    case 422: {
      // The body still carries `doc_id` and `status`, so the row can name the
      // document that was stored but could not be indexed (the file is kept —
      // NFR-20, a failed AI step never discards the source). The status also
      // selects the wording: only an "Indexing failed" is a failure that trying
      // again can recover, so the others say what would actually change the
      // outcome instead of inviting a retry that cannot work (D-32).
      //
      // And for one status it selects whether there is an action at all: a
      // document refused for being over the chunk cap would fail at the identical
      // point on every press, so the queue withholds the button exactly as the
      // repository list does (D-51). A 422 whose body carried no status at all
      // still offers it, for `canReprocess`'s own reason — an unknown outcome is
      // the user's to ask about, not ours to decide silently.
      const status = error.details?.status
      return {
        message: statusMessageFor(status),
        retryable: status ? canReprocess(status) : true,
        document: error.details,
      }
    }
    case 415:
      // The signature disagreed with the extension. The same message the
      // client-side check uses, because it is the same refusal on better evidence.
      return { message: VALIDATION.fileTypeUnsupported }
    case 413:
      return { message: VALIDATION.fileTooLarge }
    case 409:
      return { message: TEXT.uploadDuplicate }
    case 403:
      // The role lacks `contribute_content`. The form never offers a scope
      // excluding the uploader's own role, so D-29's 403 is not reachable here.
      return { message: TEXT.uploadNotPermitted }
    case 400: {
      const { fieldErrors } = extractFieldErrors(error, ['title', 'file', 'visible_to_roles'])
      return {
        message: fieldErrors.file ?? fieldErrors.visible_to_roles ?? TEXT.uploadRejected,
        titleError: fieldErrors.title ?? null,
      }
    }
    default:
      return { message: error.message, retryable: error.status === NETWORK_ERROR_STATUS }
  }
}
