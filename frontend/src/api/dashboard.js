/**
 * FR-14 dashboard, per docs/api-contract.md "Stage 5 — FR-14, FR-15 / FR-14 —
 * dashboard". A thin wrapper over the one API client; no fetch and no
 * XMLHttpRequest here.
 */
import { get } from './client.js'

/** The three query parameters, in the contract's own names and order. */
export const DASHBOARD_FILTER_KEYS = ['date_from', 'date_to', 'department']

/**
 * `GET /api/dashboard?date_from=&date_to=&department=` — every panel in one
 * request, which is FR-14's Server-End clause: "a single endpoint aggregates
 * counts and recent items … in one request rather than issuing separate calls
 * per panel". The screen makes this call and no other.
 *
 * 200 with `{filters, departments, indexed_totals, recent_documents,
 * recent_meetings, recent_questions}`, including when every list is empty and
 * every count is 0. Every number and list is computed over the caller's scope
 * before anything is counted (CLAUDE.md §6, invariant 1), so the screen renders
 * what arrives and filters nothing itself. 400 `{"<parameter>": ["..."]}` for a
 * date that is not `YYYY-MM-DD`, `date_from` later than `date_to`, or a
 * department over 255 characters; 401 for no session.
 *
 * An empty value is the same as an absent one (the contract), so only the
 * parameters that carry a value are sent and the query string stays the one the
 * screen's own URL shows.
 *
 * @param {{date_from?: string, date_to?: string, department?: string}} filters
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function fetchDashboard(filters = {}, options = {}) {
  const params = new URLSearchParams()
  for (const key of DASHBOARD_FILTER_KEYS) {
    if (filters[key]) params.set(key, filters[key])
  }
  const query = params.toString()
  return get(query ? `/dashboard?${query}` : '/dashboard', options)
}
