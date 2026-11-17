/**
 * PR #119's landing page never scrolls sideways (NFR-16; WCAG 2.1 SC 1.4.10,
 * reflow at 320 CSS px).
 *
 * The illustration on `/` sits on three blurred shapes, absolutely positioned
 * and placed partly outside it. Measured in headless Edge, unclipped, the third
 * shape made the page 360px wide in a 320px viewport, and at 1180px the second
 * made it 1194. A positioned box widens the page unless an ancestor clips it, so
 * the test asks that each shape has one. jsdom lays nothing out, so the rules
 * are read from disk (tests/stylesheets.js) and matched against the rendered
 * shapes and their ancestors.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { serveApi } from './fakeApi.js'
import { describe as name, resolve, rulesMatching } from './stylesheets.js'

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

/** What the rules matching `element` declare, later rules over earlier, `var()` resolved. */
function declaredOn(element) {
  return Object.fromEntries(
    rulesMatching(element)
      .flatMap((rule) => rule.declarations)
      .map((declaration) => [declaration.property, resolve(declaration.value).trim()]),
  )
}

/** Whether a declaration set clips sideways overflow. */
function clipsSideways(declared) {
  const value = declared['overflow-x'] ?? declared.overflow?.split(/\s+/)[0]
  return value === 'clip' || value === 'hidden'
}

describe('SC 1.4.10: the landing page’s decorative shapes never widen the page', () => {
  it('positions each shape absolutely inside an ancestor that clips sideways overflow', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )
    await screen.findByRole('link', { name: 'Create an account' })

    const shapes = [...document.querySelectorAll('.home-visual__shape')]
    expect(shapes.length).toBeGreaterThan(0)
    for (const shape of shapes) {
      // The kind of box that escapes its parent and widens the page.
      expect(declaredOn(shape).position, name(shape)).toBe('absolute')

      let clipper = null
      for (let node = shape.parentElement; node && !clipper; node = node.parentElement) {
        if (clipsSideways(declaredOn(node))) clipper = node
      }
      expect(clipper, `nothing clips ${name(shape)} sideways`).not.toBeNull()
    }
  })
})
