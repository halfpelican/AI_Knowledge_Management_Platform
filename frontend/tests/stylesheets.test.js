/**
 * The checks that keep tests/stylesheets.js honest, and the two whole-sheet
 * rules every stylesheet must hold to (Stage 5 item 7).
 *
 * jsdom applies no stylesheet, so the accessibility tests read the CSS from
 * disk through tests/stylesheets.js. A reader that silently skipped a rule
 * would make every one of those tests pass vacuously; the first test here
 * counts the braces in each file against what was parsed, so an unreadable
 * rule fails the suite instead of disappearing.
 */
import { describe, expect, it } from 'vitest'
import {
  allRules,
  parseColour,
  parseStylesheet,
  readStylesheet,
  resolve,
  styleRules,
  stylesheetFiles,
  tokens,
} from './stylesheets.js'

/** Values that look like colours but defer to another declaration, and the keywords. */
const COLOUR_LITERAL = /#[0-9a-f]{3,8}\b|\brgba?\(|\bhsla?\(/i
const PROPERTIES_THAT_TAKE_COLOUR =
  /^(color|background|background-color|border|border-color|border-(top|right|bottom|left)(-color)?|outline|outline-color|box-shadow|caret-color|fill|stroke|text-decoration-color)$/

describe('the stylesheet reader reads everything', () => {
  it('parses every rule in every stylesheet: the brace count and the parsed count agree', () => {
    for (const file of stylesheetFiles()) {
      const text = readStylesheet(file).replace(/\/\*[\s\S]*?\*\//g, '')
      const braces = (text.match(/\{/g) ?? []).length
      const parsed = parseStylesheet(text, file)
      // Each rule consumes one brace; @media and @keyframes blocks consume one
      // more each for their own braces.
      const wrappers =
        (text.match(/@media[^{]*\{/g) ?? []).length + (text.match(/@keyframes[^{]*\{/g) ?? []).length
      expect(parsed.length + wrappers, `${file}: rules its reader did not account for`).toBe(braces)
      expect(parsed.length, `${file}: parsed no rules`).toBeGreaterThan(0)
    }
  })

  it('resolves every var() in every declaration to a defined token', () => {
    for (const rule of allRules()) {
      for (const declaration of rule.declarations) {
        // Throws on an undefined token, which is the assertion.
        expect(() => resolve(declaration.value)).not.toThrow()
      }
    }
  })

  it('parses the colour notations the tokens use', () => {
    expect(parseColour('#1d4ed8')).toEqual({ r: 29, g: 78, b: 216, a: 1 })
    expect(parseColour('#fff')).toEqual({ r: 255, g: 255, b: 255, a: 1 })
    expect(parseColour('rgb(31 41 51 / 60%)')).toEqual({ r: 31, g: 41, b: 51, a: 0.6 })
    expect(parseColour('var(--x)')).toBeNull()
  })
})

describe('design tokens, not scattered literals (CLAUDE.md, react-frontend standing rules)', () => {
  it('keeps every colour literal in tokens.css: component stylesheets only reference tokens', () => {
    const offenders = []
    for (const rule of allRules()) {
      if (rule.file === 'styles/tokens.css') continue
      for (const declaration of rule.declarations) {
        if (COLOUR_LITERAL.test(declaration.value)) {
          offenders.push(`${rule.file}:${rule.line} ${declaration.property}: ${declaration.value}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })

  it('names only defined colour tokens in colour-taking declarations', () => {
    const defined = new Set(Object.keys(tokens()))
    for (const rule of styleRules()) {
      for (const declaration of rule.declarations) {
        if (!PROPERTIES_THAT_TAKE_COLOUR.test(declaration.property)) continue
        for (const [, name] of declaration.value.matchAll(/var\(\s*(--[\w-]+)/g)) {
          expect(defined.has(name), `${rule.file}:${rule.line} references ${name}`).toBe(true)
        }
      }
    }
  })
})
