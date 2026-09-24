import { SEARCH_MINIMUM_LENGTH } from '../constants.js'

/**
 * The term to search for when offering FR-12's partial matches beside a
 * no-answer.
 *
 * **Why the question cannot be sent as it stands.** `GET /api/search` matches the
 * term as **one substring**, case-insensitively, against a title or a passage
 * (`apps/retrieval/search.py`: `Q(title__icontains=query_text)` and
 * `chunk_text__icontains=query_text`). A whole question is therefore matched as a
 * whole phrase, which no document contains. Measured against the live corpus on
 * 25 September 2026: `q=What is the migration schedule for the Antarctic
 * satellite ground station?` returned `total_count` 0, and `q=migration` returned
 * the meeting that discusses one. Sending the question verbatim would satisfy
 * FR-12's partial-matches clause with a list that is empty by construction.
 *
 * **So one word is chosen from it.** The longest word that is not a question word
 * and is long enough to search — the longest word being the crudest available
 * proxy for the most specific one, with no index, no stemming and no term
 * weighting available in the browser. One word means one request and one
 * `SearchLog` row per no-answer, and that row records a plausible search term
 * rather than a sentence, which is the more useful FR-19 evidence of what people
 * are looking for and not finding.
 *
 * **What this is not.** It is not relevance ranking and it is not a second
 * retrieval path: what comes back is whatever the keyword search finds for one
 * word, offered as links and clearly labelled as partial matches. The screen names
 * the word it searched for, so nobody has to guess why an item is in the list.
 *
 * The better fix is server-side — either the ask reply carrying its own partial
 * matches, or the search endpoint accepting several terms — and it needs a
 * contract change. This is the front-end approximation until then; see the Stage 4
 * report.
 *
 * @param {string} question
 * @returns {string | null} The word to search for, or null when the question has
 *   no word worth searching, in which case nothing extra is shown.
 */
const QUESTION_WORDS = new Set([
  'about',
  'after',
  'again',
  'also',
  'another',
  'anything',
  'because',
  'been',
  'before',
  'being',
  'between',
  'both',
  'could',
  'does',
  'doing',
  'during',
  'each',
  'from',
  'have',
  'having',
  'here',
  'how',
  'into',
  'just',
  'many',
  'much',
  'must',
  'need',
  'only',
  'other',
  'ours',
  'over',
  'please',
  'should',
  'some',
  'such',
  'tell',
  'than',
  'that',
  'their',
  'them',
  'then',
  'there',
  'these',
  'they',
  'this',
  'those',
  'told',
  'under',
  'very',
  'want',
  'what',
  'when',
  'where',
  'which',
  'while',
  'who',
  'whom',
  'whose',
  'will',
  'with',
  'would',
  'your',
  'yours',
])

/** Words shorter than this are too generic to be worth one whole search. */
const MINIMUM_KEYWORD_LENGTH = 4

export function partialMatchTerm(question) {
  const words = (question ?? '').toLowerCase().split(/[^\p{L}\p{N}]+/u)
  let best = null
  for (const word of words) {
    if (word.length < MINIMUM_KEYWORD_LENGTH) continue
    if (word.length < SEARCH_MINIMUM_LENGTH) continue
    if (QUESTION_WORDS.has(word)) continue
    // Strictly longer, so the first of two equally long words wins and the choice
    // is stable for a given question.
    if (best === null || word.length > best.length) best = word
  }
  return best
}
