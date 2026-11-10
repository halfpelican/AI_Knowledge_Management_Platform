/**
 * The application's stylesheets, read from disk, for the checks jsdom cannot make.
 *
 * jsdom applies no stylesheet: Vite's CSS imports are empty modules under Vitest,
 * so a rendered screen carries its classes and none of their rules. Stage 5 item 7
 * names the consequence: a rule that hid the Ask screen's acknowledgement line
 * would pass every rendering test. This module reads every `.css` file under
 * `src/` and gives the tests three things to check against:
 *
 * - the rules, as selector and declarations, with any `@media` condition kept;
 * - the design tokens from `src/styles/tokens.css`, with `var()` resolved, and
 *   WCAG 2.1 contrast arithmetic over them;
 * - which rules match a rendered element, through jsdom's own selector matching,
 *   and whether any of them hides it.
 *
 * The parser is deliberately small and strict. It handles what the stylesheets
 * use — rules, `@media` and `@keyframes` — and throws on any other at-rule, so a
 * stylesheet it cannot read fails the suite rather than being skipped. That every
 * rule was read is asserted by `stylesheets.test.js`, which counts the opening
 * braces in each file against what was parsed.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = join(import.meta.dirname, '..', 'src')

/** Every `.css` file under `src/`, as paths relative to `src/` with forward slashes. */
export function stylesheetFiles(dir = SRC) {
  const found = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) found.push(...stylesheetFiles(path))
    else if (entry.name.endsWith('.css')) found.push(relative(SRC, path).replaceAll('\\', '/'))
  }
  return found.sort()
}

/** The text of one stylesheet, by its path relative to `src/`. */
export function readStylesheet(file) {
  return readFileSync(join(SRC, file), 'utf8')
}

/** Comments replaced by spaces of the same length, so offsets and line numbers hold. */
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '))
}

/** Splits on `separator` where it is outside parentheses, brackets and quotes. */
export function splitTopLevel(text, separator) {
  const parts = []
  let depth = 0
  let quote = null
  let start = 0
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    if (quote) {
      if (ch === quote && text[i - 1] !== '\\') quote = null
    } else if (ch === '"' || ch === "'") quote = ch
    else if (ch === '(' || ch === '[') depth += 1
    else if (ch === ')' || ch === ']') depth -= 1
    else if (ch === separator && depth === 0) {
      parts.push(text.slice(start, i))
      start = i + 1
    }
  }
  parts.push(text.slice(start))
  return parts.map((part) => part.trim()).filter(Boolean)
}

/** The index of the brace that closes the one at `open`. */
function matchingBrace(text, open) {
  let depth = 0
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1
    else if (text[i] === '}') {
      depth -= 1
      if (depth === 0) return i
    }
  }
  throw new Error(`Unbalanced brace at offset ${open}`)
}

function parseDeclarations(body) {
  return splitTopLevel(body, ';').map((raw) => {
    const colon = raw.indexOf(':')
    if (colon < 0) throw new Error(`Not a declaration: "${raw}"`)
    let value = raw.slice(colon + 1).trim()
    const important = /!important$/i.test(value)
    if (important) value = value.replace(/\s*!important$/i, '')
    return { property: raw.slice(0, colon).trim().toLowerCase(), value, important }
  })
}

function lineOf(text, offset) {
  return text.slice(0, offset).split('\n').length
}

/**
 * One stylesheet as a flat list of rules. A rule inside `@media` carries the
 * condition; a keyframe step carries the animation's name and is never matched
 * against an element.
 *
 * @returns {{file: string, line: number, selectors: string[], declarations: {property: string, value: string, important: boolean}[], media: string|null, keyframes: string|null}[]}
 */
export function parseStylesheet(text, file = '(inline)') {
  const source = stripComments(text)
  const rules = []

  function parseBlock(start, end, media, keyframes) {
    let i = start
    while (i < end) {
      const open = source.indexOf('{', i)
      if (open < 0 || open >= end) {
        if (source.slice(i, end).trim()) throw new Error(`${file}: text outside any rule near line ${lineOf(source, i)}`)
        return
      }
      const prelude = source.slice(i, open).trim()
      const close = matchingBrace(source, open)
      if (prelude.startsWith('@media')) {
        parseBlock(open + 1, close, prelude.slice('@media'.length).trim(), null)
      } else if (prelude.startsWith('@keyframes')) {
        parseBlock(open + 1, close, media, prelude.slice('@keyframes'.length).trim())
      } else if (prelude.startsWith('@')) {
        throw new Error(`${file}: at-rule this reader does not understand, line ${lineOf(source, i)}: ${prelude}`)
      } else {
        rules.push({
          file,
          line: lineOf(source, open),
          selectors: splitTopLevel(prelude, ','),
          declarations: parseDeclarations(source.slice(open + 1, close)),
          media,
          keyframes,
        })
      }
      i = close + 1
    }
  }

  parseBlock(0, source.length, null, null)
  return rules
}

let cachedRules = null

/** Every rule in every stylesheet under `src/`, in file order. */
export function allRules() {
  if (!cachedRules) cachedRules = stylesheetFiles().flatMap((file) => parseStylesheet(readStylesheet(file), file))
  return cachedRules
}

/** Rules that can apply to an element: not keyframe steps. */
export function styleRules() {
  return allRules().filter((rule) => rule.keyframes === null)
}

/* ---- Tokens ------------------------------------------------------------- */

let cachedTokens = null

/** Every custom property `:root` declares in tokens.css, unresolved. */
export function tokens() {
  if (!cachedTokens) {
    const root = parseStylesheet(readStylesheet('styles/tokens.css'), 'styles/tokens.css').filter((rule) =>
      rule.selectors.includes(':root'),
    )
    cachedTokens = Object.fromEntries(
      root.flatMap((rule) => rule.declarations).filter((d) => d.property.startsWith('--')).map((d) => [d.property, d.value]),
    )
  }
  return cachedTokens
}

/** A value with every `var()` replaced by the token's own value, recursively. */
export function resolve(value, depth = 0) {
  if (depth > 10) throw new Error(`var() nested too deeply in "${value}"`)
  const replaced = value.replace(/var\(\s*(--[\w-]+)\s*(?:,([^)]*))?\)/g, (whole, name, fallback) => {
    const found = tokens()[name] ?? fallback?.trim()
    if (found === undefined) throw new Error(`Undefined token ${name}`)
    return found
  })
  return replaced === value ? value : resolve(replaced, depth + 1)
}

/** The colour tokens a value names, directly or through another token such as `--focus-ring`. */
export function colourTokensIn(value, depth = 0) {
  const names = new Set()
  for (const [, name] of value.matchAll(/var\(\s*(--[\w-]+)/g)) {
    if (name.startsWith('--color-')) names.add(name)
    else if (tokens()[name] !== undefined && depth < 10) for (const inner of colourTokensIn(tokens()[name], depth + 1)) names.add(inner)
  }
  return [...names]
}

/* ---- Colour and contrast ------------------------------------------------ */

/** `#rgb`, `#rrggbb`, `rgb(r g b / a%)` or `rgb(r, g, b)` as {r, g, b, a}, or null. */
export function parseColour(value) {
  const text = value.trim().toLowerCase()
  const hex = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/)
  if (hex) {
    const full = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join('') : hex[1]
    const [r, g, b] = full.match(/../g).map((pair) => parseInt(pair, 16))
    return { r, g, b, a: 1 }
  }
  const rgb = text.match(/^rgba?\(([^)]+)\)$/)
  if (rgb) {
    const [channels, alphaPart] = rgb[1].split('/').map((part) => part.trim())
    const values = channels.split(/[\s,]+/).filter(Boolean)
    const alphaText = alphaPart ?? values[3]
    const [r, g, b] = values.slice(0, 3).map(Number)
    let a = 1
    if (alphaText !== undefined) a = alphaText.endsWith('%') ? parseFloat(alphaText) / 100 : parseFloat(alphaText)
    return { r, g, b, a }
  }
  return null
}

/** A translucent colour laid over an opaque one, as the browser composites it. */
export function composite(top, bottom) {
  const mix = (t, b) => Math.round(t * top.a + b * (1 - top.a))
  return { r: mix(top.r, bottom.r), g: mix(top.g, bottom.g), b: mix(top.b, bottom.b), a: 1 }
}

function luminance({ r, g, b }) {
  const channel = (c) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

/** WCAG 2.1 contrast ratio between two opaque colours. */
export function contrast(first, second) {
  const [hi, lo] = [luminance(first), luminance(second)].sort((a, b) => b - a)
  return (hi + 0.05) / (lo + 0.05)
}

/** A colour token's value, parsed, with a translucent one composited over `over` (a token name). */
export function tokenColour(name, over) {
  const colour = parseColour(resolve(`var(${name})`))
  if (!colour) throw new Error(`${name} is not a colour: ${resolve(`var(${name})`)}`)
  if (colour.a === 1) return colour
  if (!over) throw new Error(`${name} is translucent; say what it is laid over`)
  return composite(colour, tokenColour(over))
}

/* ---- Rules against a rendered element ------------------------------------ */

/** Whether `selector` matches `element` in its current state, through jsdom's matcher. */
export function selectorMatches(element, selector) {
  try {
    return element.matches(selector)
  } catch {
    return false
  }
}

/** Every rule with a selector matching `element` now, with the selector that matched. */
export function rulesMatching(element) {
  const matched = []
  for (const rule of styleRules()) {
    const selector = rule.selectors.find((candidate) => selectorMatches(element, candidate))
    if (selector) matched.push({ ...rule, selector })
  }
  return matched
}

const ZERO = /^-?0(\.0+)?(px|rem|em|%)?$/
const ONE_PIXEL_OR_LESS = /^(0(\.\d+)?|1)(px)?$/
const FAR_OFF = /^-\d{3,}(\.\d+)?(px|rem|em)$/

/**
 * Why a declaration hides what it applies to, or null. Conservative: any of these
 * on the element or an ancestor takes it off the screen, whatever else applies.
 * A rule that hides and another that restores would both match and the hiding one
 * would still be reported, which is the intended direction to be wrong in.
 */
export function hidingReason({ property, value }) {
  const v = resolve(value).trim().toLowerCase()
  switch (property) {
    case 'display':
      return v === 'none' ? 'display: none' : null
    case 'visibility':
      return v === 'hidden' || v === 'collapse' ? `visibility: ${v}` : null
    case 'opacity':
      return ZERO.test(v) ? 'opacity: 0' : null
    case 'content-visibility':
      return v === 'hidden' ? 'content-visibility: hidden' : null
    case 'clip':
      return v.startsWith('rect(') ? `clip: ${v}` : null
    case 'clip-path':
      return /^inset\((50|100)%\)$/.test(v) || /^circle\(0/.test(v) ? `clip-path: ${v}` : null
    case 'width':
    case 'height':
    case 'max-width':
    case 'max-height':
      return ONE_PIXEL_OR_LESS.test(v) || ZERO.test(v) ? `${property}: ${v}` : null
    case 'font-size':
      return ZERO.test(v) ? 'font-size: 0' : null
    case 'color':
      return v === 'transparent' ? 'color: transparent' : null
    case 'text-indent':
    case 'left':
    case 'top':
    case 'right':
    case 'margin-left':
    case 'margin-top':
      return FAR_OFF.test(v) ? `${property}: ${v}` : null
    case 'transform':
      return /scale\(0(\.0+)?\)/.test(v) ? `transform: ${v}` : null
    default:
      return null
  }
}

/**
 * What takes `element` off the screen: a `hidden` or `aria-hidden` ancestor, or
 * a matching rule on it or any ancestor that hides. An empty list means nothing
 * in the markup or the stylesheets hides it.
 *
 * @returns {string[]} one line per cause, naming the element and the rule.
 */
export function hidingCauses(element) {
  const causes = []
  for (let node = element; node && node.nodeType === 1; node = node.parentElement) {
    const name = describe(node)
    if (node.hidden) causes.push(`${name} has the hidden attribute`)
    if (node.getAttribute('aria-hidden') === 'true') causes.push(`${name} is aria-hidden`)
    if (node.getAttribute('inert') !== null) causes.push(`${name} is inert`)
    if (node.style?.display === 'none') causes.push(`${name} has an inline display: none`)
    for (const rule of rulesMatching(node)) {
      for (const declaration of rule.declarations) {
        const reason = hidingReason(declaration)
        if (reason) causes.push(`${name} matches ${rule.selector} (${rule.file}:${rule.line}): ${reason}`)
      }
    }
  }
  return causes
}

/** A short name for an element in a failure message. */
export function describe(element) {
  const id = element.id ? `#${element.id}` : ''
  const classes = element.classList?.length ? `.${[...element.classList].join('.')}` : ''
  return `<${element.tagName.toLowerCase()}${id}${classes}>`
}
