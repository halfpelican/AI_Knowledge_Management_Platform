/**
 * Where FR-13's active thread is written down: the address (D-77).
 *
 * `/ask?c=<id>` names the active thread, and `/ask` with no `c` means there is
 * none. The address is the only source of truth for it, so a citation followed in
 * the same tab and then Back returns to the conversation that was left (D-61's gap
 * 3). These are the two directions of that mapping and nothing else. Nothing here
 * imports React or fetches, for the reason `src/utils/threads.js` gives, and which
 * thread the next question belongs to stays there.
 *
 * A thread id is an opaque string here, as it is in `threads.js`. Nothing checks
 * that it is a UUID: the server answers one 404 for an unknown id, another user's
 * thread and an id that is not a UUID (CLAUDE.md §6, invariant 1), and the Ask
 * screen treats all three alike.
 */

/** The route the Ask screen is mounted at (src/App.jsx). */
export const ASK_PATH = '/ask'

/**
 * The thread a query string names, or null for none. An empty `c` names none, so
 * `/ask?c=` is read as `/ask`.
 *
 * @param {string} search a location's `search`, with or without its leading `?`
 * @returns {string | null}
 */
export function threadInSearch(search) {
  const id = new URLSearchParams(search).get('c')
  return id ? id : null
}

/**
 * The question a query string carries, from the search screen's "Ask this as a
 * question" link (`/ask?q=…`), or the empty string.
 *
 * @param {string} search
 * @returns {string}
 */
export function questionInSearch(search) {
  return new URLSearchParams(search).get('q') ?? ''
}

/**
 * The query string that names `threadId` and nothing else: `?c=<id>`, or the empty
 * string for none. Any other parameter — Search's `q` in particular — is not carried
 * over, which is how writing a thread to the address drops it (D-77).
 *
 * @param {string | null} threadId
 * @returns {string}
 */
export function searchForThread(threadId) {
  return threadId ? `?${new URLSearchParams({ c: threadId })}` : ''
}

/**
 * The address that names `threadId`: `/ask?c=<id>`, or `/ask` for none.
 *
 * @param {string | null} threadId
 * @returns {string}
 */
export function addressForThread(threadId) {
  return `${ASK_PATH}${searchForThread(threadId)}`
}
