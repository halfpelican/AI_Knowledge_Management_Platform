/**
 * NFR-14's style guide, the component sheet at /components, shows every design
 * token with its live value, and its contrast table computes each pair from
 * those values (components/ComponentSheet.jsx).
 *
 * The sheet reads a token's value only if one of its token lists names it. PR
 * #119's redesign added fifteen contrast pairs over thirteen new colours, and the
 * lists named none of them, so in a browser those fifteen rows read "n/a" and
 * "Fail". componentSheet.test.jsx still passed, because it recomputes each pair
 * from tokens.css on disk rather than reading the rendered table.
 *
 * jsdom applies no stylesheet, so each test here first gives the document the
 * values a browser computes for tokens.css's custom properties: each token's own
 * value with any var() in it replaced, which is a custom property's computed
 * value (CSS Custom Properties, section 2) and a substitution jsdom does not make.
 * The sheet then reads them through getComputedStyle, as it does in a browser.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import ComponentSheet from '../src/components/ComponentSheet.jsx'
import { CONTRAST_PAIRS } from '../src/components/contrastPairs.js'
import { stopName, tabbable } from './keyboard.js'
import { contrast, resolve, tokenColour, tokens } from './stylesheets.js'

/** A token's value as a browser's getComputedStyle reports it: var() substituted. */
function computedValue(name) {
  return resolve(`var(${name})`).trim()
}

/** Two values compared as the browser and jsdom may space them differently. */
function unspaced(value) {
  return value.replace(/\s+/g, '')
}

let computedTokens = null

beforeEach(() => {
  computedTokens = document.createElement('style')
  const declarations = Object.keys(tokens()).map((name) => `${name}: ${computedValue(name)};`)
  computedTokens.textContent = `:root { ${declarations.join(' ')} }`
  document.head.appendChild(computedTokens)
})

afterEach(() => {
  computedTokens.remove()
})

function renderSheet() {
  render(
    <MemoryRouter initialEntries={['/components']}>
      <ComponentSheet />
    </MemoryRouter>,
  )
}

/** Each token the sheet lists, with the value it shows beside it. */
function shownTokens() {
  const shown = new Map()
  for (const item of document.querySelectorAll('.swatches > li, .token-list > li')) {
    const name = item.querySelector('code')?.textContent ?? ''
    if (!name.startsWith('--')) continue
    shown.set(name, item.querySelector('.swatch__value, .token-row__value')?.textContent ?? '')
  }
  return shown
}

describe('NFR-14: the component sheet shows every design token, and computes each contrast pair from them', () => {
  it('has a colour swatch for every token a contrast pair names, so the table reads each one’s value', () => {
    renderSheet()
    const swatches = new Set([...document.querySelectorAll('.swatch__name')].map((name) => name.textContent))
    const named = [...new Set(CONTRAST_PAIRS.flatMap((pair) => [pair.fg, pair.bg]))]
    expect(named.length).toBeGreaterThan(0)
    expect(named.filter((name) => !swatches.has(name))).toEqual([])
  })

  it('shows every custom property tokens.css declares, each with the value a browser computes for it', () => {
    renderSheet()
    const shown = shownTokens()
    const declared = Object.keys(tokens())
    expect(declared.length).toBeGreaterThan(0)
    // A token the sheet does not list is a token the style guide does not document.
    expect(declared.filter((name) => !shown.has(name))).toEqual([])
    // A listed token whose value is blank is one the sheet lists but never reads.
    const wrong = declared
      .filter((name) => shown.has(name) && unspaced(shown.get(name)) !== unspaced(computedValue(name)))
      .map((name) => `${name} shows "${shown.get(name)}", not "${computedValue(name)}"`)
    expect(wrong).toEqual([])
  })

  it('shows each contrast pair’s ratio as tokens.css gives it, and Pass: never "n/a" or "Fail"', () => {
    renderSheet()
    const table = screen.getByRole('table', { name: 'Contrast ratio of each text and background pair' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(CONTRAST_PAIRS.length)
    const shown = rows.map((row) => [...row.cells].map((cell) => cell.textContent))
    const expected = CONTRAST_PAIRS.map((pair) => [
      pair.label,
      pair.fg,
      pair.bg,
      `${contrast(tokenColour(pair.fg), tokenColour(pair.bg)).toFixed(2)}:1`,
      `${pair.minimum}:1`,
      'Pass',
    ])
    expect(shown).toEqual(expected)
  })
})

describe('D-137: the sheet shows the Avatar, with a picture and with initials', () => {
  it('shows each beside the name it decorates, as decoration a screen reader skips and the keyboard never stops at', () => {
    renderSheet()
    const section = screen.getByRole('region', { name: 'Avatar (D-137)' })
    const people = [...section.querySelectorAll('.avatar-list__person')]
    expect(people).toHaveLength(2)

    // With a picture: the image itself, its alt empty because the name is beside it.
    const [withPicture, withInitials] = people
    const picture = withPicture.querySelector('img.avatar')
    expect(picture, 'the first person has a picture').not.toBeNull()
    expect(picture.classList.contains('avatar--image')).toBe(true)
    expect(picture.getAttribute('src')).toBeTruthy()
    expect(picture.getAttribute('alt')).toBe('')
    expect(withPicture.textContent).toContain('Jane Doe')

    // With none: the initials, painted by Avatar.css from data-initials and hidden
    // from assistive technology, so the line reads as the name alone.
    expect(withInitials.querySelector('img')).toBeNull()
    const initials = withInitials.querySelector('.avatar--initials')
    expect(initials, 'the second person has initials').not.toBeNull()
    expect(initials.getAttribute('data-initials')).toBe('EE')
    expect(initials.getAttribute('aria-hidden')).toBe('true')
    expect(initials.textContent).toBe('')
    expect(withInitials.textContent).toContain('Erin Employee')

    // Decoration is never a stop.
    expect(tabbable(section).map(stopName)).toEqual([])
  })
})
