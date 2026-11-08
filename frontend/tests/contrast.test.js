/**
 * WCAG 2.1 AA contrast over the shipped palette (NFR-16: "a minimum 4.5:1
 * contrast ratio for normal text (SC 1.4.3)"; SC 1.4.11 asks 3:1 of user
 * interface component boundaries).
 *
 * Two layers, so a later colour change cannot silently fail AA:
 *
 * 1. **Every pair the interface uses is asserted against its bar**, computed
 *    from the live values in src/styles/tokens.css. Changing a token's value
 *    recomputes every ratio it takes part in; the table in
 *    docs/accessibility.md is this list, prose-formatted.
 * 2. **Every colour-taking declaration in every stylesheet must be accounted
 *    for** — as a foreground in the pair table, as one of the known surfaces,
 *    or in the named decorative exceptions. A new colour usage fails here until
 *    it is paired, so the table cannot rot while the stylesheets move on.
 */
import { describe, expect, it } from 'vitest'
import { colourTokensIn, contrast, styleRules, tokenColour } from './stylesheets.js'

const TEXT_MINIMUM = 4.5 // SC 1.4.3, normal text
const BOUNDARY_MINIMUM = 3 // SC 1.4.11, UI component boundaries and states

/** The opaque surfaces content sits on. --color-overlay is handled on its own. */
const SURFACES = [
  '--color-surface',
  '--color-surface-alt',
  '--color-danger-surface',
  '--color-success-surface',
  '--color-warning-surface',
]

/**
 * Text foregrounds, each with every background the stylesheets put it on.
 *
 * `--color-text` and `--color-text-muted` are listed against all five surfaces
 * because a Notice takes arbitrary children, so body and muted text can sit on
 * any of them. The others are listed where a rule actually puts them.
 */
const TEXT_PAIRS = [
  { fg: '--color-text', on: SURFACES },
  { fg: '--color-text-muted', on: SURFACES },
  // Links and link-styled controls: page, panels, and the in-page 403's link on
  // the error notice (components/NotPermitted.jsx).
  { fg: '--color-primary', on: ['--color-surface', '--color-surface-alt', '--color-danger-surface'] },
  { fg: '--color-primary-hover', on: ['--color-surface', '--color-surface-alt', '--color-danger-surface'] },
  // Button and skip-link text on the primary fills.
  { fg: '--color-primary-text', on: ['--color-primary', '--color-primary-hover'] },
  // Field errors (forms sit on the page and inside the dashboard's filter
  // panel), failed upload chips, and the error notice's title.
  { fg: '--color-danger', on: ['--color-surface', '--color-surface-alt', '--color-danger-surface'] },
  // Indexed upload chips and the component sheet's pass column.
  { fg: '--color-success', on: ['--color-surface', '--color-surface-alt', '--color-success-surface'] },
  // The AI-unavailable notice's title (NFR-19).
  { fg: '--color-warning', on: ['--color-surface', '--color-warning-surface'] },
]

/**
 * Non-text boundaries and state fills, each with the surfaces adjacent to it.
 *
 * `--color-border` is deliberately absent: it is a decorative separator, 1.47:1
 * on the surface, and the sweep below holds it to that role by failing any rule
 * that makes it the boundary of a control (see BOUNDARY_SELECTOR_EXCEPTIONS).
 */
const BOUNDARY_PAIRS = [
  // Inputs, secondary buttons, chips, drop zone, scroll-region boundaries.
  { fg: '--color-border-strong', on: ['--color-surface', '--color-surface-alt'] },
  // The focus ring, drawn with an offset so it sits on the page or a panel.
  { fg: '--color-focus', on: ['--color-surface', '--color-surface-alt'] },
  // Primary buttons, the pressed facet's fill, the progress bar's fill, the
  // active drop zone's border, the info notice's leading edge.
  { fg: '--color-primary', on: ['--color-surface', '--color-surface-alt'] },
  { fg: '--color-primary-hover', on: ['--color-surface', '--color-surface-alt'] },
  // The invalid input's border and the failed chip's border; the error notice's
  // leading edge against its own surface.
  { fg: '--color-danger', on: ['--color-surface', '--color-surface-alt', '--color-danger-surface'] },
  // The indexed chip's border, and the success surface should a notice use it.
  { fg: '--color-success', on: ['--color-surface', '--color-success-surface'] },
  // The unavailable notice's leading edge (NFR-19).
  { fg: '--color-warning', on: ['--color-surface', '--color-warning-surface'] },
]

describe('SC 1.4.3: text pairs meet 4.5:1, computed from the live token values', () => {
  for (const pair of TEXT_PAIRS) {
    for (const background of pair.on) {
      it(`${pair.fg} on ${background}`, () => {
        const ratio = contrast(tokenColour(pair.fg), tokenColour(background))
        expect(ratio, `${pair.fg} on ${background} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(TEXT_MINIMUM)
      })
    }
  }
})

describe('SC 1.4.11: component boundaries and fills meet 3:1 against what they sit on', () => {
  for (const pair of BOUNDARY_PAIRS) {
    for (const background of pair.on) {
      it(`${pair.fg} against ${background}`, () => {
        const ratio = contrast(tokenColour(pair.fg), tokenColour(background))
        expect(ratio, `${pair.fg} against ${background} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
          BOUNDARY_MINIMUM,
        )
      })
    }
  }
})

describe('the modal scrim backs no text', () => {
  it('gives the dialogue its own opaque surface and text colour, so nothing is read on the composite', () => {
    // tokens.css: "Nothing is read through it; it is decorative and
    // aria-hidden." That stays true only while the dialogue restates both its
    // background and its colour — on the scrim composite alone, white text
    // measures about 4.05:1, under the 4.5:1 bar.
    const dialog = styleRules().find((rule) => rule.selectors.includes('.dialog'))
    const declared = Object.fromEntries(dialog.declarations.map((d) => [d.property, d.value]))
    expect(colourTokensIn(declared['background-color'])).toEqual(['--color-surface'])
    expect(colourTokensIn(declared.color)).toEqual(['--color-text'])
  })
})

/* ---- Exhaustiveness: no colour usage outside this file's tables ----------- */

/** Foreground tokens the pair tables above account for. */
const PAIRED = new Set([...TEXT_PAIRS, ...BOUNDARY_PAIRS].map((pair) => pair.fg))

/**
 * Colour tokens that may appear without a pair, each with the reason it is
 * exempt from a contrast requirement.
 */
const EXEMPT = new Set([
  // Decorative separators between rows and sections; never the sole boundary of
  // a control (tokens.css). The selector check below enforces the "never".
  '--color-border',
  // The surfaces themselves, as backgrounds.
  ...SURFACES,
  '--color-primary',
  '--color-primary-hover',
  // The scrim: decorative, aria-hidden, asserted separately above.
  '--color-overlay',
])

/** Selectors whose rules may use --color-border on a border: separators and panels, not controls. */
const CONTROL_SELECTOR = /^(button|input|select|textarea|a\b|\.btn|\.facet|\.citation(?!-)|\.ask-threads__item|\.password-toggle|\.sort-header__button|\.skip-link)/

const PROPERTIES_THAT_TAKE_COLOUR =
  /^(color|background|background-color|border|border-color|border-(top|right|bottom|left)(-color)?|outline|outline-color|box-shadow|caret-color|fill|stroke|text-decoration-color)$/

describe('every colour usage is accounted for', () => {
  it('pairs or exempts every colour token every stylesheet uses', () => {
    const unaccounted = []
    for (const rule of styleRules()) {
      for (const declaration of rule.declarations) {
        if (!PROPERTIES_THAT_TAKE_COLOUR.test(declaration.property)) continue
        for (const token of colourTokensIn(declaration.value)) {
          if (!PAIRED.has(token) && !EXEMPT.has(token)) {
            unaccounted.push(`${rule.file}:${rule.line} ${declaration.property} uses ${token}`)
          }
        }
      }
    }
    expect(unaccounted).toEqual([])
  })

  it('never makes the decorative border the boundary of a control', () => {
    const offenders = []
    for (const rule of styleRules()) {
      if (rule.file === 'styles/tokens.css') continue
      const bordersWithWeakToken = rule.declarations.filter(
        (declaration) =>
          /^border/.test(declaration.property) && colourTokensIn(declaration.value).includes('--color-border'),
      )
      if (bordersWithWeakToken.length === 0) continue
      for (const selector of rule.selectors) {
        if (CONTROL_SELECTOR.test(selector.trim())) {
          offenders.push(`${rule.file}:${rule.line} ${selector}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})
