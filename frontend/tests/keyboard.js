/**
 * Tab and Shift+Tab, as a browser moves focus, for the tab-order tests.
 *
 * `@testing-library/user-event` is not installed, and Stage 5 item 7 adds no
 * package, so this is the part of its `tab()` the tests need, written out. A
 * press fires `keydown` on the focused element first, so a handler that takes the
 * key — the confirmation dialogue's focus trap — can claim it with
 * `preventDefault`. Only an unclaimed press moves focus, to the next element in
 * the sequential focus order HTML defines:
 *
 * - elements with a positive `tabindex` first, in ascending order, then the rest
 *   in document order (no screen here uses a positive one, and
 *   `tabOrder.test.jsx` asserts that);
 * - not disabled, not inside a disabled fieldset, not `tabindex="-1"`, not
 *   inside a `hidden`, `inert` or `display: none` subtree, and not inside a
 *   closed `<details>` other than its summary;
 * - one stop per radio group: the checked radio, or the first when none is.
 *
 * Firing the key events matters beyond the trap: jsdom's selector engine decides
 * `:focus-visible` from them, as a browser does, so a stylesheet rule written for
 * keyboard focus matches after `pressTab()` and not after a bare `focus()`.
 */
import { fireEvent } from '@testing-library/react'

const CANDIDATES = [
  'a[href]',
  'area[href]',
  'button',
  'input',
  'select',
  'textarea',
  'iframe',
  'summary',
  '[tabindex]',
  '[contenteditable=""]',
  '[contenteditable="true"]',
].join(',')

function isDisabled(element) {
  if ('disabled' in element && element.disabled && /^(BUTTON|INPUT|SELECT|TEXTAREA)$/.test(element.tagName)) return true
  // A control inside a disabled fieldset is disabled, unless it is in that
  // fieldset's first legend.
  const fieldset = element.closest('fieldset[disabled]')
  if (fieldset && /^(BUTTON|INPUT|SELECT|TEXTAREA)$/.test(element.tagName)) {
    const legend = fieldset.querySelector(':scope > legend')
    if (!legend || !legend.contains(element)) return true
  }
  return false
}

/* jsdom applies no stylesheet, so an inline style is the only `display: none` it
   can hold; what the stylesheets hide is tests/stylesheets.js's to find. */
function isRendered(element) {
  for (let node = element; node && node.nodeType === 1; node = node.parentElement) {
    if (node.hidden || node.hasAttribute('inert')) return false
    if (node.style?.display === 'none') return false
    const details = node.parentElement?.closest('details')
    if (details && !details.open) {
      const summary = details.querySelector(':scope > summary')
      if (!summary || !summary.contains(node)) return false
    }
  }
  return true
}

function tabIndexOf(element) {
  const attribute = element.getAttribute('tabindex')
  if (attribute === null) return 0
  const value = Number.parseInt(attribute, 10)
  return Number.isNaN(value) ? 0 : value
}

/** Every element Tab can stop at under `root`, in the order Tab visits them. */
export function tabbable(root = document.body) {
  const all = Array.from(root.querySelectorAll(CANDIDATES)).filter((element) => {
    if (element.tagName === 'INPUT' && element.type === 'hidden') return false
    if (tabIndexOf(element) < 0) return false
    return !isDisabled(element) && isRendered(element)
  })

  // One stop per radio group, named within its form (or the document).
  const seenGroups = new Map()
  const stops = all.filter((element) => {
    if (element.tagName !== 'INPUT' || element.type !== 'radio' || !element.name) return true
    const key = `${element.form ? 'form' : 'doc'}:${element.name}`
    const group = all.filter(
      (other) => other.tagName === 'INPUT' && other.type === 'radio' && other.name === element.name && other.form === element.form,
    )
    const chosen = group.find((radio) => radio.checked) ?? group[0]
    if (seenGroups.has(key)) return false
    if (element !== chosen) return false
    seenGroups.set(key, element)
    return true
  })

  const positive = stops.filter((element) => tabIndexOf(element) > 0).sort((a, b) => tabIndexOf(a) - tabIndexOf(b))
  return [...positive, ...stops.filter((element) => tabIndexOf(element) === 0)]
}

/** The stop after (or before) `from`, by document position where `from` is not a stop itself. */
function nextStop(stops, from, backwards) {
  const index = stops.indexOf(from)
  if (index >= 0) return stops[index + (backwards ? -1 : 1)] ?? null
  if (!from || from === document.body) return backwards ? (stops.at(-1) ?? null) : (stops[0] ?? null)
  // Focus is on something Tab does not stop at (a heading moved to, say): carry on
  // from where it sits in the document, as a browser does.
  const following = (stop) => Boolean(from.compareDocumentPosition(stop) & Node.DOCUMENT_POSITION_FOLLOWING)
  if (backwards) return [...stops].reverse().find((stop) => !following(stop) && stop !== from) ?? null
  return stops.find(following) ?? null
}

/**
 * One press of Tab (or Shift+Tab). Returns the element that has focus afterwards,
 * which is `document.body` when focus has left the last stop for the browser's
 * own controls.
 */
export function pressTab({ shift = false } = {}) {
  const from = document.activeElement ?? document.body
  const unclaimed = fireEvent.keyDown(from, { key: 'Tab', code: 'Tab', shiftKey: shift })
  if (unclaimed) {
    const to = nextStop(tabbable(), from, shift)
    if (to) to.focus()
    else from.blur?.()
  }
  fireEvent.keyUp(document.activeElement ?? document.body, { key: 'Tab', code: 'Tab', shiftKey: shift })
  return document.activeElement
}

/**
 * Tabs from the top of the page until focus leaves the last stop, and returns
 * every element it stopped at, in order. Fails if focus comes back to a stop it
 * has already visited before leaving, which is a keyboard trap (WCAG 2.1 SC
 * 2.1.2), or if it takes more than `limit` presses.
 */
export function tabThrough({ shift = false, limit = 300 } = {}) {
  document.activeElement?.blur?.()
  const visited = []
  for (let press = 0; press < limit; press += 1) {
    const now = pressTab({ shift })
    if (now === document.body || now === null) return visited
    if (visited.includes(now)) {
      throw new Error(`Focus returned to a stop already visited without leaving the page: a trap at stop ${visited.length}`)
    }
    visited.push(now)
  }
  throw new Error(`Still tabbing after ${limit} presses`)
}

/** Presses Tab until `element` has focus, the way a keyboard user reaches it. */
export function tabTo(element, limit = 300) {
  document.activeElement?.blur?.()
  for (let press = 0; press < limit; press += 1) {
    if (pressTab() === element) return element
  }
  throw new Error('Tab never reached the element')
}

/** What a stop is called, for a failure message or an expected order. */
export function stopName(element) {
  const label =
    element.getAttribute('aria-label') ??
    (element.labels?.[0]?.textContent ||
      (element.getAttribute('aria-labelledby')
        ? element
            .getAttribute('aria-labelledby')
            .split(/\s+/)
            .map((id) => document.getElementById(id)?.textContent ?? '')
            .join(' ')
        : element.textContent))
  return label.replace(/\s+/g, ' ').trim()
}
