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
import { EVIDENCE_MAP_NODE_TYPE, KNOWLEDGE_MAP_NODE_TYPE } from '../src/constants.js'
import { colourTokensIn, contrast, resolve, styleRules, tokenColour } from './stylesheets.js'

const TEXT_MINIMUM = 4.5 // SC 1.4.3, normal text
const BOUNDARY_MINIMUM = 3 // SC 1.4.11, UI component boundaries and states

/** The opaque surfaces content sits on. --color-overlay is handled on its own. */
const SURFACES = [
  '--color-surface',
  '--color-surface-alt',
  '--color-danger-surface',
  '--color-success-surface',
  '--color-warning-surface',
  // PR #119's surfaces: the page behind its home screen and sign-in card, its
  // repository's info notice, and its status badges' two fills. Listed here so
  // body and muted text are held to 4.5:1 on each, as on the five above.
  '--color-background',
  '--color-info-surface',
  '--color-status-indexed-surface',
  '--color-status-not-indexed-surface',
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
  // PR #119's screens. Headings on the home page and the document table's
  // titles; links on the sign-in card and, on hover, in the dashboard's panels;
  // the repository's info and error notices; the status badge for "Indexed" and
  // the one for every other status (FR-15); and the home illustration's one line
  // of text that sits on a fill of its own, the left chat bubble.
  { fg: '--color-heading', on: ['--color-background', '--color-surface'] },
  { fg: '--color-link', on: ['--color-background', '--color-surface'] },
  { fg: '--color-primary-hover', on: ['--color-info-surface'] },
  { fg: '--color-danger-text', on: ['--color-danger-surface'] },
  { fg: '--color-status-indexed', on: ['--color-status-indexed-surface'] },
  { fg: '--color-status-not-indexed', on: ['--color-status-not-indexed-surface'] },
  { fg: '--color-illustration-bubble-text', on: ['--color-text-muted'] },
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
  // FR-20's knowledge map (D-132), which sits on the surface. Its document,
  // meeting and tag shapes are filled with --color-primary, --color-success and
  // --color-warning, and its lines are --color-border-strong, all paired above.
  // These two are the rest: the contributor's fill, and the selected node's
  // outline and lines. The map's second view (D-138) adds no pair: its claim is
  // filled with --color-text and its passage with --color-primary.
  { fg: '--color-text-muted', on: ['--color-surface'] },
  { fg: '--color-text', on: ['--color-surface'] },
  // PR #119's screens: the home screen's outline button on the page, and its
  // illustration, the device on the page and the figure on the device. The
  // accent is the token behind one of the shapes under the illustration.
  { fg: '--color-border-strong', on: ['--color-background'] },
  { fg: '--color-illustration-device', on: ['--color-background'] },
  { fg: '--color-illustration-figure', on: ['--color-illustration-device'] },
  { fg: '--color-accent', on: ['--color-background'] },
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

describe('FR-20: "node type distinguished by colour and shape", the colour half (D-132)', () => {
  /** The one colour token a class's rules give `property`, or every token found when it is not one. */
  function tokensFor(selector, property) {
    return styleRules()
      .filter((rule) => rule.selectors.includes(selector))
      .flatMap((rule) => rule.declarations)
      .filter((declaration) => declaration.property === property)
      .flatMap((declaration) => colourTokensIn(declaration.value))
  }

  /** Whether the boundary table above holds `token` against the surface the map sits on. */
  function pairedOnSurface(token) {
    return BOUNDARY_PAIRS.some((pair) => pair.fg === token && pair.on.includes('--color-surface'))
  }

  const types = Object.values(KNOWLEDGE_MAP_NODE_TYPE)

  it('gives each of the four node classes one fill token, four different ones, each a tested 3:1 pair on the surface', () => {
    const fills = types.map((type) => tokensFor(`.knowledge-map__glyph--${type}`, 'fill'))
    for (const [index, tokens] of fills.entries()) {
      expect(tokens, `.knowledge-map__glyph--${types[index]} declares one fill token`).toHaveLength(1)
      expect(pairedOnSurface(tokens[0]), `${tokens[0]} is in BOUNDARY_PAIRS on --color-surface`).toBe(true)
    }
    // Four types, four colours: two classes sharing a fill would leave the shape
    // as the only difference between them.
    expect(new Set(fills.map((tokens) => tokens[0])).size).toBe(types.length)
    // And the values behind the tokens differ too, not only their names.
    expect(new Set(fills.map((tokens) => JSON.stringify(tokenColour(tokens[0])))).size).toBe(types.length)
  })

  it('draws the lines in a tested 3:1 colour, never the decorative border, and the selected node’s in another', () => {
    const line = tokensFor('.knowledge-map__line', 'stroke')
    const selected = tokensFor('.knowledge-map__line--selected', 'stroke')
    expect(line).toHaveLength(1)
    expect(selected).toHaveLength(1)
    // A line is needed to read the diagram (SC 1.4.11), so the 1.47:1 separator
    // colour, which the sweep below exempts, is not allowed here.
    expect(line[0]).not.toBe('--color-border')
    expect(pairedOnSurface(line[0])).toBe(true)
    expect(pairedOnSurface(selected[0])).toBe(true)
    expect(selected[0]).not.toBe(line[0])
  })

  // The map's second view, claims and passages (D-138), sits on the same surface.
  it('the second view (D-138): gives the claim and the passage one fill token each, two different ones, each a tested 3:1 pair on the surface', () => {
    const evidenceTypes = Object.values(EVIDENCE_MAP_NODE_TYPE)
    expect(evidenceTypes).toHaveLength(2)
    const fills = evidenceTypes.map((type) => tokensFor(`.knowledge-map__glyph--${type}`, 'fill'))
    for (const [index, tokens] of fills.entries()) {
      expect(tokens, `.knowledge-map__glyph--${evidenceTypes[index]} declares one fill token`).toHaveLength(1)
      expect(pairedOnSurface(tokens[0]), `${tokens[0]} is in BOUNDARY_PAIRS on --color-surface`).toBe(true)
    }
    // Two types, two colours, by name and by value.
    expect(fills[0][0]).not.toBe(fills[1][0])
    expect(JSON.stringify(tokenColour(fills[0][0]))).not.toBe(JSON.stringify(tokenColour(fills[1][0])))
  })

  it('the second view (D-138): a line’s three weights are three widths, each greater than the last, and no colour of their own', () => {
    const declarationsFor = (selector) =>
      styleRules()
        .filter((rule) => rule.selectors.includes(selector))
        .flatMap((rule) => rule.declarations)
    const widths = ['light', 'medium', 'heavy'].map((weight) => {
      const declarations = declarationsFor(`.knowledge-map__line--${weight}`)
      // The width and nothing else: a weight never changes the line's tested colour.
      expect(declarations.map((declaration) => declaration.property)).toEqual(['stroke-width'])
      return parseFloat(resolve(declarations[0].value))
    })
    expect(widths[0]).toBeGreaterThan(0)
    expect(widths[1]).toBeGreaterThan(widths[0])
    expect(widths[2]).toBeGreaterThan(widths[1])
  })
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

/** Selectors whose rules may use --color-border on a border: separators and panels, not controls.
    The last entry is FR-20's node and its reference in a table or the panel, with their
    modifiers, and not the classes that merely begin the same way (`__node-text`, `__nodes`).
    `.profile-picture__label` is PR #119's profile picture chooser, a label drawn as a button. */
const CONTROL_SELECTOR = /^(button|input|select|textarea|a\b|\.btn|\.facet|\.citation(?!-)|\.ask-threads__item|\.password-toggle|\.sort-header__button|\.skip-link|\.profile-picture__label|\.knowledge-map__(node|ref)(?![a-z_]|-[a-z]))/

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
