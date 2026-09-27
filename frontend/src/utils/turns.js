import { TEXT } from '../constants.js'

/**
 * The three states one turn of a thread can be in, and the mapping from a stored
 * turn as `GET /api/conversations/{id}` returns it to the object the Ask screen
 * renders.
 *
 * **Why this is a module and not four lines inside Ask.jsx.** This layer has no
 * test runner, and D-51's retry affordance shipped broken for exactly that
 * reason. A pure function with no React in it can be exercised from plain Node
 * against bodies captured from the Django suite, which is how the three states
 * below were hand-verified. Nothing here imports React, and nothing here
 * fetches.
 *
 * **The three states are not each other**, and the screen keeps them apart
 * because a user who confuses them retries the wrong thing — or worse, stops
 * asking a question the system can answer:
 *
 * - `answered` — statements, each with its citation number.
 * - `noAnswer` — the corpus had nothing to answer from. A designed outcome,
 *   stated plainly. **This is also what a re-scoped turn renders as, and it is
 *   deliberately indistinguishable from it**: a turn whose statements were drawn
 *   from material the reader's current role may no longer see says nothing at
 *   all, because a notice that something was removed is itself a disclosure that
 *   material exists which this role may not read (CLAUDE.md §6, invariant 1).
 *   The server does not tell this screen the difference and must not.
 * - `provenanceRemoved` — the turn WAS answered, and the record of what it was
 *   drawn from no longer exists. `AnswerCitation.chunk` is `on_delete=CASCADE`
 *   (D-12), and FR-08's reprocess action, `manage.py reindex` and FR-15's deletion each delete a
 *   source's chunks and write new ones with fresh identifiers, so the citations
 *   of the old ones go with them while the passage itself still exists. The
 *   server sends `provenance_removed: true` on that turn and nothing else, and
 *   this screen shows no statements — invariant 6 — but it does NOT say the
 *   question cannot be answered from the knowledge base, because that is untrue
 *   and a user would act on it.
 *
 * **The flag is present on a turn only when it is true**, which is the server's
 * guarantee that a re-scoped turn's body is byte-for-byte a never-answered one
 * (`ConversationTurnSerializer.to_representation`). An absent key and `false` are
 * the same test here, so nothing in this module depends on which it is.
 */
export const TURN_STATE = {
  answered: 'answered',
  noAnswer: 'no-answer',
  provenanceRemoved: 'provenance-removed',
}

/**
 * Which of the three states a screen turn is in.
 *
 * `answered` is checked first: a turn the server says is answered has statements
 * it may be shown with, and the server has already re-scoped them. The order
 * matters only defensively — the two flags cannot both be true, since the server
 * derives `answered` as "answered and something is still readable" and
 * `provenance_removed` as "answered and there are no citation rows at all".
 *
 * @param {{answered?: boolean, provenanceRemoved?: boolean}} turn
 * @returns {string} one of TURN_STATE
 */
export function turnStateOf(turn) {
  if (turn?.answered) return TURN_STATE.answered
  if (turn?.provenanceRemoved) return TURN_STATE.provenanceRemoved
  return TURN_STATE.noAnswer
}

/**
 * One turn of a reopened thread, as the screen holds it.
 *
 * `sources` is empty and `expandable` is false because nothing returns what a
 * past turn was built from: a stored turn keeps each statement and its citation
 * number, and a citation cannot expand to its passage. Said on the screen rather
 * than left as a control that does nothing.
 *
 * `partialMatches` is empty rather than absent, so the same branch renders a
 * stored turn and a live one. They were derived from the ranking of the turn that
 * was live and no route returns a past turn's candidates.
 *
 * @param {object} turn a turn object from `GET /api/conversations/{id}`
 * @param {{key: string}} options the React key the caller assigned
 */
export function savedTurnFrom(turn, { key }) {
  const provenanceRemoved = Boolean(turn?.provenance_removed)
  return {
    key,
    question: turn?.question,
    answered: Boolean(turn?.answered),
    provenanceRemoved,
    // The server sends the fixed text for both silent states and for this one. The
    // fallbacks exist only so a turn always says something plain, and they are
    // never used against a real reply — which is why the one chosen here still has
    // to match the state, or the fallback would reintroduce the false sentence.
    message: turn?.message ?? (provenanceRemoved ? TEXT.provenanceRemovedFallback : TEXT.noAnswerFallback),
    statements: turn?.statements ?? [],
    sources: [],
    partialMatches: [],
    expandable: false,
    askedAt: turn?.asked_at,
  }
}

/**
 * One turn just answered by `POST /api/ask`, as the screen holds it.
 *
 * **`provenanceRemoved` is always false on a live turn, and cannot be otherwise.**
 * The `QueryLog` row and its `AnswerCitation` rows are written in one transaction
 * (`apps/retrieval/query_log.py`), so there is no moment at which a live reply
 * could be rendered without the citations of the answer it is returning. The field
 * is set explicitly rather than left undefined so that both turn shapes carry the
 * same keys and `turnStateOf` has nothing to guess.
 *
 * @param {object} reply the body of `POST /api/ask`
 * @param {{question: string}} asked the question as the user sent it
 */
export function liveTurnFrom(reply, { question }) {
  return {
    question,
    answered: Boolean(reply?.answered),
    provenanceRemoved: false,
    message: reply?.message ?? TEXT.noAnswerFallback,
    statements: reply?.statements ?? [],
    sources: reply?.sources ?? [],
    partialMatches: reply?.partial_matches ?? [],
    expandable: true,
  }
}
