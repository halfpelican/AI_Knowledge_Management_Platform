import { Link } from 'react-router-dom'
import { TEXT } from '../constants.js'
import './DashboardPanel.css'

/**
 * One FR-14 dashboard panel: a labelled region whose heading is the link into
 * the module that owns it — FR-14's "each panel links through to its full view",
 * and the proposal's "each panel is a route into the module that owns it".
 *
 * It has four states, and the order is the order they are checked in:
 *
 * - **loading** — FR-14's "panels display a loading state while data is
 *   retrieved". Words in a `role="status"` region, not a spinner alone, so the
 *   state has a text equivalent a screen reader reaches (WCAG 2.1 SC 1.1.1).
 * - **failed** — the dashboard's one request failed. Plain text, because the
 *   failure is announced once above the panels and four alerts saying the same
 *   thing would be noise.
 * - **empty** — an ordinary state, never styled as an error. It says nothing
 *   about what exists outside the caller's scope, because the screen is not told
 *   (CLAUDE.md §6, invariant 1).
 * - otherwise the panel's content.
 *
 * A panel with no single full view — the indexed totals, whose two figures link
 * to two modules — passes no `to`, and its heading is plain text.
 *
 * @param {object} props
 * @param {string} props.headingId Labels the region; unique on the page.
 * @param {string} props.heading
 * @param {string} [props.to] The full view the heading links to.
 * @param {boolean} [props.loading]
 * @param {string} props.loadingText
 * @param {boolean} [props.failed]
 * @param {boolean} [props.empty]
 * @param {string} [props.emptyText]
 * @param {import('react').ReactNode} [props.children]
 */
export default function DashboardPanel({
  headingId,
  heading,
  to,
  loading = false,
  loadingText,
  failed = false,
  empty = false,
  emptyText,
  children,
}) {
  let body
  if (loading) {
    body = (
      <p role="status" className="dashboard-panel__state">
        {loadingText}
      </p>
    )
  } else if (failed) {
    body = <p className="dashboard-panel__state">{TEXT.dashboardPanelUnavailable}</p>
  } else if (empty) {
    body = <p className="dashboard-panel__state">{emptyText}</p>
  } else {
    body = children
  }

  return (
    <section className="dashboard-panel" aria-labelledby={headingId}>
      <h2 id={headingId} className="dashboard-panel__heading">
        {to ? <Link to={to}>{heading}</Link> : heading}
      </h2>
      {body}
    </section>
  )
}
