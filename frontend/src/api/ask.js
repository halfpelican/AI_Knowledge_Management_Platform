/**
 * FR-12's answer path, which is also FR-13's conversational turn — one endpoint
 * serves both, per docs/api-contract.md "FR-12 — the answer path, which is also
 * FR-13's turn". A thin wrapper over the one API client.
 */
import { post } from './client.js'

/**
 * The `code` D-79's in-flight 429 carries, `{"detail": "...", "code":
 * "ask_in_flight"}`, which is how a screen tells it from the rate limit's 429 on
 * the same route. `detail` is never parsed (docs/api-contract.md, "Stage 5 item 5").
 */
export const ASK_IN_FLIGHT_CODE = 'ask_in_flight'

/**
 * `POST /api/ask` — a question, optionally as a turn of a thread.
 *
 * The reply has **the same key set on every exit**, so the interface branches on
 * `answered` rather than on two response shapes:
 *
 * - `answered: true` — `statements` (each `{position, text, chunk_id}`),
 *   `sources` (each `{source_type, source_id, title, date, passages: [{chunk_id,
 *   text}]}`), `result_count`, `message: null`, `conversation`.
 * - `answered: false` — the fixed `message`, `result_count` 0, both lists empty.
 *   The two no-answer paths are byte-identical and the interface must not try to
 *   tell them apart (CLAUDE.md §6, invariants 6 and 7).
 *
 * There is no field for a rejected statement, none for `no_answer_reason` and
 * none for `rejected_count`: they are record-only, so no screen can display
 * one.
 *
 * Failures: 400 `{"question": [...]}` for a missing question or one outside
 * `MINIMUM_QUESTION_LENGTH`–`MAXIMUM_QUESTION_LENGTH`; 400
 * `{"conversation_id": [...]}` for an id that is not a UUID; 401; 404 for a
 * well-formed id that is not this caller's — never 403, which would confirm the
 * thread exists (invariant 1); 503 when the AI service could not be reached
 * after `MAXIMUM_GENERATION_ATTEMPTS`. A 503 writes no `QueryLog` row, so the
 * question can safely be asked again (NFR-19).
 *
 * Two 429s since D-79, neither of which writes a `QueryLog` row: past the per-user
 * ask rate, DRF's body with a `Retry-After` in seconds (`error.retryAfter`); and
 * while this user's previous question is still being answered, `code`
 * `ask_in_flight` (`error.code`, ASK_IN_FLIGHT_CODE above) and no `Retry-After`.
 * The in-flight check runs after validation and the conversation check, so a 400
 * or a 404 is returned first.
 *
 * The question is sent exactly as typed, because that is what `QueryLog.question`
 * stores and what the length rule is applied to.
 *
 * @param {object} body
 * @param {string} body.question
 * @param {string} [body.conversationId] Omitted sends no field at all, which is
 *   a one-off question whose `QueryLog.conversation` stays NULL (D-12).
 * @param {object} [options]
 * @param {AbortSignal} [options.signal]
 */
export function askQuestion({ question, conversationId }, options = {}) {
  const body = { question }
  if (conversationId) body.conversation_id = conversationId
  return post('/ask', body, options)
}
