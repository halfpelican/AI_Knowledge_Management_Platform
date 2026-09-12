/**
 * WCAG 2.1 contrast arithmetic, used by the component sheet to verify the
 * token palette from its live values rather than from hand-copied numbers.
 */

/** Parses `#rgb` or `#rrggbb` into [r, g, b] on 0-255, or null when not a hex colour. */
export function parseHex(value) {
  const hex = String(value ?? '').trim().replace(/^#/, '')
  if (!/^([0-9a-f]{3}|[0-9a-f]{6})$/i.test(hex)) return null
  const full = hex.length === 3 ? hex.split('').map((c) => c + c).join('') : hex
  return full.match(/.{2}/g).map((pair) => parseInt(pair, 16))
}

/** Relative luminance per WCAG 2.1, from an [r, g, b] triple on 0-255. */
export function relativeLuminance([r, g, b]) {
  const channel = (c) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

/** Contrast ratio (1 to 21) between two hex colours, or null when either cannot be parsed. */
export function contrastRatio(foreground, background) {
  const fg = parseHex(foreground)
  const bg = parseHex(background)
  if (!fg || !bg) return null
  const [hi, lo] = [relativeLuminance(fg), relativeLuminance(bg)].sort((a, b) => b - a)
  return (hi + 0.05) / (lo + 0.05)
}
