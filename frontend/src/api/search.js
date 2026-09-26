/**
 * FR-12 keyword search, per docs/api-contract.md "FR-12 — keyword search".
 * A thin wrapper over the one API client; no fetch and no XMLHttpRequest here.
 */
import { get } from './client.js'

/**
 * `GET /api/search?q=<term>` — results grouped by type, scoped to the caller's
 * role.
 *
 * 200 with `{query, documents: {count, results}, meetings: {count, results},
 * total_count}`, including when nothing matched; 400 `{"q": [...]}` when `q` is
 * absent or shorter than the minimum term length; 401 for no session.
 *
 * Each result carries `source_type`, `source_id`, `title`, `snippet`,
 * `department` and `date` — the four things FR-12's Front-End clause says a
 * result shows, plus the type and identifier the interface links with. Both
 * counts are computed after permission filtering, so the screen may render them
 * as they arrive: no total in this reply describes anything the caller may not
 * see (CLAUDE.md §6, invariant 1).
 *
 * **The term is sent exactly as typed.** The server stores and matches it
 * character for character with no trimming and no sanitiser, so this function
 * does not trim either — a client that trimmed would search for something other
 * than what the `SearchLog` row records.
 *
 * @param {string} term
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function searchKnowledge(term, options = {}) {
  return get(`/search?q=${encodeURIComponent(term)}`, options)
}
