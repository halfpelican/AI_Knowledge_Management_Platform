/**
 * Which thread the next question belongs to, and what becomes of a thread nobody
 * has asked anything in.
 *
 * **Why this is a module and not four expressions inside Ask.jsx.** The defect
 * these rules exist to fix was found by reading rather than by running anything,
 * when this layer had no test runner (D-25; it has had one since D-62). Nothing here
 * imports React, holds state or fetches, so the rules can be exercised on their
 * own — the same reason `src/utils/turns.js` is a module.
 *
 * **The constraint every rule below follows from.** `POST /api/conversations` has
 * no inverse: FR-13's CRUD line is `Conversations (Create, Read, Update)`, there is
 * no delete route, and inventing one would be inventing a requirement (D-80 keeps
 * it that way). A thread that is created and never asked in is therefore a
 * permanent row. Since D-80 the list leaves it out, so it no longer sits at the top
 * of FR-13's list as "New conversation"; it is still reachable by its address
 * (D-77), and each one still spends the per-user create budget (D-79). So the lever
 * this layer has is unchanged: create fewer of them, and go back into the one it
 * already made.
 *
 * **And the thread cannot simply be created later.** `POST /api/ask` attaches a
 * turn to a thread that already exists; it creates none, and a question sent with
 * no `conversation_id` is a one-off whose `QueryLog.conversation` stays NULL (D-12,
 * D-43). Creating the thread after a successful reply would leave that first
 * question outside it forever: the thread would reopen without it, and the prior
 * questions FR-13 resolves a follow-up against are read from the thread's own
 * `QueryLog` rows (D-42). The order create-then-ask is forced. What is fixed here
 * is the abandonment, not the order.
 *
 * A thread id is an opaque string here. Nothing in this module parses one, and
 * "unused" means only "this screen created it and has had no reply back for it" —
 * never anything read off the thread's title, which is a display string that a
 * whitespace-only question can leave standing (D-43).
 */

/**
 * The thread the next question should be a turn of, or null meaning one has to be
 * created first.
 *
 * The active thread if there is one. Otherwise a thread created earlier for a
 * question that never landed: it has no turns, so a new question in it is still a
 * new topic, and it is a row that already exists rather than a second one.
 */
export function threadForNextQuestion(activeThreadId, unusedThreadId) {
  return activeThreadId ?? unusedThreadId ?? null
}

/**
 * The unused thread after a reply comes back for `askedThreadId`.
 *
 * A reply means a `QueryLog` row was written and the thread was named from the
 * question (D-43), whether or not the question could be answered — a no-answer
 * turn is a turn. So the thread is no longer empty and no longer somewhere to
 * return to. Any other thread's reply leaves the empty one where it was.
 */
export function unusedThreadAfterTurn(unusedThreadId, askedThreadId) {
  return unusedThreadId === askedThreadId ? null : unusedThreadId
}

/**
 * The unused thread after an ask fails with `status` (null for a failure that
 * carried none, such as a dropped connection).
 *
 * Kept for every failure but one, because no turn was written: a 503 writes no
 * `QueryLog` row (NFR-19), and neither does a 400 or either of D-79's 429s — the
 * rate limit's, or the one that says this user's previous question is still being
 * answered. So the thread is still empty and still the right place for the next
 * attempt, which is the same question, since it stays in the field.
 *
 * A 429 on the create that precedes a first question (D-80's create throttle)
 * comes here too, and created nothing. Nothing was recorded for it, so what is kept
 * is what there was before the create was sent, which is null: the screen only
 * creates when there is no unused thread to go back into
 * (`threadForNextQuestion`). The next attempt creates again, and never names a
 * thread that does not exist.
 *
 * A 404 is the exception. It is the answer both for a thread that does not exist
 * and for one that is not this caller's, and this screen may not tell those apart
 * (CLAUDE.md §6, invariant 1); either way the id cannot be asked in again, so it is
 * dropped rather than carried into the next question.
 */
export function unusedThreadAfterFailure(unusedThreadId, status) {
  return status === 404 ? null : unusedThreadId
}

/**
 * The active thread after FR-13's "the active thread can be cleared to begin a new
 * topic".
 *
 * A thread with turns is dropped, which is what clearing means. A thread with none
 * is kept, because there is nothing in it to clear — it already is a new topic, and
 * letting go of it would leave it behind empty and create a second one on the next
 * question. Pressing the control repeatedly therefore costs nothing.
 */
export function threadAfterNewTopic(unusedThreadId) {
  return unusedThreadId ?? null
}
