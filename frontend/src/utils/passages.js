/**
 * FR-16's passage references, read off a summary as `GET /api/meetings/{id}/summary`
 * sends it (docs/api-contract.md, D-125). Pure, with no React, so it can be
 * exercised on its own, as src/utils/turns.js is.
 *
 * A summary's `narrative`, `decisions` and `highlights` are lists of
 * `{text, passages}`, and an action item carries `passages` too. The numbers are
 * keys of the summary's `passages` object, which holds the text of every
 * transcript passage one of its own elements names (UC-04: "Every element of the
 * summary carries a reference to the passage of the transcript it was drawn
 * from"). The server checked each number against the passages it sent to the model
 * (CLAUDE.md §6, invariant 5); nothing here checks it again or could.
 */

/**
 * The passage numbers an element names: positive whole numbers, each once, in the
 * order given. Anything else in the list is left out rather than shown as a
 * reference to nothing.
 *
 * @param {{passages?: unknown}} element a narrative sentence, decision, highlight or action item
 * @returns {number[]}
 */
export function passageNumbers(element) {
  const listed = Array.isArray(element?.passages) ? element.passages : []
  const numbers = []
  for (const value of listed) {
    if (Number.isInteger(value) && value > 0 && !numbers.includes(value)) numbers.push(value)
  }
  return numbers
}

/**
 * The text of transcript passage `number`, or null where the summary does not
 * carry it. That happens for an action item kept through a Regenerate: its numbers
 * still name the transcript's passages, and the current summary's `passages` holds
 * only the ones it cites itself, so the page shows the number alone.
 *
 * @param {Record<string, unknown>|null|undefined} passages the summary's `passages`
 * @param {number} number
 * @returns {string|null}
 */
export function passageText(passages, number) {
  const text = passages && typeof passages === 'object' ? passages[String(number)] : undefined
  return typeof text === 'string' && text.length > 0 ? text : null
}

/**
 * The elements of one part of a summary that can be shown: each with its text and
 * at least one passage reference.
 *
 * The server sends no element without a reference ("an element that named none is
 * not here"), so this drops nothing from a real reply. It is here so that the
 * panel cannot show a sentence with no reference whatever it is handed: UC-04's
 * rule is held by the screen as well as by the server, as the answer view holds
 * invariant 6.
 *
 * @param {unknown} elements `summary.narrative`, `.decisions` or `.highlights`
 * @returns {{text: string, passages: number[]}[]}
 */
export function referencedElements(elements) {
  const shown = []
  for (const element of Array.isArray(elements) ? elements : []) {
    const text = typeof element?.text === 'string' ? element.text.trim() : ''
    const passages = passageNumbers(element)
    if (text && passages.length > 0) shown.push({ text, passages })
  }
  return shown
}
