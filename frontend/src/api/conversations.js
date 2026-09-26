/**
 * FR-13 conversations, per docs/api-contract.md "FR-13 — conversations". Thin
 * wrappers over the one API client.
 *
 * Create, Read and Update — and Update is the server's own: the pipeline touches
 * `last_updated_at` on every turn and replaces the placeholder title with the
 * first question (D-43). **There is no rename route and no delete route**, so
 * there is no helper for either here and no control for either in the
 * interface. Clearing the active thread is `createConversation()`, not a
 * deletion: the old thread's `QueryLog` rows are FR-19 evidence that outlives
 * the reader's interest in them (D-12).
 */
import { get, post } from './client.js'

/**
 * `GET /api/conversations` — the caller's own threads, newest activity first.
 * Each is `{conversation_id, title, last_updated_at}`; never a user id, because
 * every thread a caller can reach is theirs.
 *
 * 200 with a possibly empty array; 401.
 */
export function listConversations(options = {}) {
  return get('/conversations', options)
}

/**
 * `POST /api/conversations` — 201 with the new thread.
 *
 * `title` is optional (D-43). The assistant never asks the user to name a topic
 * before typing, so it sends none: the thread is created as "New conversation"
 * and the first turn through `POST /api/ask` replaces that with the question
 * itself. 400 only for a title over 255 characters, which this screen cannot
 * send because it sends no title at all.
 */
export function createConversation({ title } = {}, options = {}) {
  const body = {}
  if (title) body.title = title
  return post('/conversations', body, options)
}

/**
 * `GET /api/conversations/{id}` — one thread **with** its `turns`, so a reopened
 * conversation renders from the server rather than from whatever the browser
 * still holds.
 *
 * Each turn is `{question, answered, asked_at, message, statements}`. A turn
 * carries no `sources` and no passage text: nothing stores the passages that were
 * supplied to a past turn in a form any reply exposes, so a reopened thread shows
 * each statement and its citation number and cannot expand one. It carries no
 * `no_answer_reason` and no `rejected_count` either — a thread read is a second
 * route past them and is closed for the same reason (invariant 1).
 *
 * 200; 401; 404 both for an id that names nothing and for another user's thread,
 * which is what stops a caller enumerating threads one request at a time.
 */
export function fetchConversation(conversationId, options = {}) {
  return get(`/conversations/${encodeURIComponent(conversationId)}`, options)
}
