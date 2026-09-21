/** Date formatting shared by the screens that list records. */

const dateFormat = new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium' })

/**
 * An ISO date or timestamp from the API, in the reader's locale format. An
 * unparseable value renders as an empty cell rather than "Invalid Date".
 */
export function formatDate(iso) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : dateFormat.format(date)
}

/**
 * Today as `YYYY-MM-DD` in the browser's own timezone, for a date input's `max`.
 *
 * The server compares against the project's timezone (TIME_ZONE) rather than
 * UTC, so a browser set to a different zone can be a day out at the boundary.
 * That is why this is only the control's ceiling: FR-09's "the date may not be
 * in the future" is enforced by the server, which answers 400 for one
 * (CLAUDE.md §6, invariant 4).
 */
export function todayIsoDate() {
  const now = new Date()
  const month = `${now.getMonth() + 1}`.padStart(2, '0')
  const day = `${now.getDate()}`.padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}
