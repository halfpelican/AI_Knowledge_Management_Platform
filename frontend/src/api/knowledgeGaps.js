/**
 * FR-19 knowledge-gap log, per docs/api-contract.md "NIT3004 — FR-19, Objective
 * 06". Thin wrappers over the one API client; no fetch and no XMLHttpRequest here.
 *
 * Every route needs a session **and** the `review_knowledge_gaps` permission,
 * which accounts migration 0007 gives the Administrator alone (D-107): 401
 * without a session, 403 for a role that lacks the code. The screen that calls
 * these is offered to an Administrator only, and that is usability: the server
 * checks the code on every request whatever the interface showed (CLAUDE.md §6,
 * invariant 4).
 *
 * No payload names who asked, their role, or why a question was left out of the
 * log, and none counts the rows left out (D-107, D-108). Nothing here reads one,
 * and nothing on the screen suggests one exists.
 */
import { get, patch, post } from './client.js'

/**
 * An entry's two statuses, the fixed vocabulary of apps/core/constants.py
 * `KNOWLEDGE_GAP_STATUS_VALUES`. The screen offers "Mark addressed" on an Open
 * entry and "Reopen" on an Addressed one, and no action on any other value, so a
 * value added later is shown without being guessed at.
 * tests/knowledgeGaps.test.jsx fails when this and the server's copy drift.
 */
export const KNOWLEDGE_GAP_STATUS = {
  open: 'Open',
  addressed: 'Addressed',
}

/**
 * `GET /api/knowledge-gaps` — FR-19's list.
 *
 * 200 with every entry, each `{gap_id, subject, occurrence_count, status,
 * first_seen_at, last_seen_at}`: Open entries first, by `occurrence_count`
 * descending then `last_seen_at` descending, then Addressed entries in the same
 * order. `[]` before any cycle. No pagination. The order is the server's, and the
 * screen keeps it rather than sorting again. 401; 403.
 *
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function listKnowledgeGaps(options = {}) {
  return get('/knowledge-gaps', options)
}

/**
 * `POST /api/knowledge-gaps/cycles` — run one aggregation cycle now. It runs
 * synchronously, in one transaction, and is the same cycle the scheduled trigger
 * (`manage.py aggregate_knowledge_gaps`) runs.
 *
 * 201 with `{cycle_id, started_at, finished_at, queries_considered,
 * searches_considered, entries_created, entries_updated}`. The two `_considered`
 * counts are the questions and searches the cycle **added to the log**, so a row
 * left out on permission grounds is in no count (D-108); `entries_created` is the
 * entries it started and `entries_updated` the existing entries that gained a
 * member. 503 when embedding failed after `MAXIMUM_EMBED_ATTEMPTS` (NFR-19): the
 * cycle rolled back and nothing was changed. 401; 403.
 *
 * The body is `{}`, as FR-08's reprocess sends: the route reads none.
 *
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function runKnowledgeGapCycle(options = {}) {
  return post('/knowledge-gaps/cycles', {}, options)
}

/**
 * `PATCH /api/knowledge-gaps/{id}` with `{"status": "Addressed"}` or
 * `{"status": "Open"}` — FR-19's "the ability to mark an entry as addressed", and
 * back. Only the status changes.
 *
 * 200 with the updated entry; 400 `{"status": ["..."]}` for any other value, or
 * none; 404 no entry with that id, checked before the body. 401; 403.
 *
 * @param {string} gapId The entry's `gap_id`.
 * @param {string} status One of `KNOWLEDGE_GAP_STATUS`.
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function updateKnowledgeGapStatus(gapId, status, options = {}) {
  return patch(`/knowledge-gaps/${encodeURIComponent(gapId)}`, { status }, options)
}
