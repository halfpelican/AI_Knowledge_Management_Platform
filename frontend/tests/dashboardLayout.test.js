/**
 * PR #119's FR-14 dashboard stylesheet (pages/Dashboard.css) at every width.
 *
 * jsdom applies no stylesheet and evaluates no media query, so these read the
 * rules from disk (tests/stylesheets.js) with the condition each sits under.
 * Two things went wrong in #119's version and were seen in a browser at 320 CSS
 * px: the "Signed in as" line's rules sat inside the 640px block, so a wider
 * screen showed the line unstyled; and where the filters stack into a column,
 * the flex basis each field had for the row became its height, leaving a date
 * field 12rem tall and the department field 20rem.
 */
import { describe, expect, it } from 'vitest'
import { resolve, styleRules } from './stylesheets.js'

const DASHBOARD = 'pages/Dashboard.css'

/** The condition the filters stack under, as the reader records an @media prelude. */
const STACKED = '(max-width: 640px)'

/** The last value Dashboard.css gives `property` for exactly `selector` under `media` (null: no condition). */
function declared(selector, media, property) {
  return styleRules()
    .filter((rule) => rule.file === DASHBOARD && rule.media === media && rule.selectors.includes(selector))
    .flatMap((rule) => rule.declarations)
    .filter((declaration) => declaration.property === property)
    .map((declaration) => resolve(declaration.value).trim())
    .at(-1)
}

/** A flex shorthand or basis that sets a length, which in a column is a height. */
const LENGTH_BASIS = /(^|\s)-?\d*\.?\d+(px|rem|em|vh|vw|%)$/

describe('FR-14: the dashboard’s own rules hold at every width', () => {
  it('styles the "Signed in as" line at every width, not only under 640px', () => {
    const rules = styleRules().filter(
      (rule) => rule.file === DASHBOARD && rule.selectors.some((selector) => selector.startsWith('.dashboard__user')),
    )
    expect(rules.length).toBeGreaterThan(0)
    for (const rule of rules) {
      expect(rule.media, `${rule.file}:${rule.line} ${rule.selectors.join(', ')}`).toBeNull()
    }
  })

  it.each([
    ['.dashboard-filters', '.dashboard-filters__department'],
    ['.dashboard-filters__dates', '.dashboard-filters__dates > .field'],
  ])('where %s stacks into a column, %s gives up the basis it has for the row', (container, item) => {
    // The container does stack there.
    expect(declared(container, STACKED, 'flex-direction')).toBe('column')
    // The item has a length basis for the row, so the stacked block has to undo
    // it: in a column that length is the item's height.
    expect(declared(item, null, 'flex')).toMatch(LENGTH_BASIS)
    const stacked = declared(item, STACKED, 'flex-basis') ?? declared(item, STACKED, 'flex')
    expect(stacked, `${item} under ${STACKED}`).toBeDefined()
    expect(stacked).not.toMatch(LENGTH_BASIS)
  })
})
