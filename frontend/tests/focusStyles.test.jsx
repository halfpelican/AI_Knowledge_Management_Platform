/**
 * Focus visibility and the stylesheet-level hiding checks (Stage 5 item 7;
 * NFR-16's SC 2.4.7 visible focus, and the M6 brief's warning that jsdom
 * applies no stylesheet, "the acknowledgement line is the known case").
 *
 * jsdom cannot show a focus ring or hide an element by CSS, so these tests
 * read the stylesheets from disk (tests/stylesheets.js) and check the rules
 * themselves, alongside the rendered markup where a state (focused, filled)
 * decides which rules match.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import App from '../src/App.jsx'
import Ask from '../src/pages/Ask.jsx'
import { answeredReply, CONVERSATION, serveApi } from './fakeApi.js'
import { pressTab } from './keyboard.js'
import { hidingCauses, resolve, styleRules } from './stylesheets.js'

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

describe('SC 2.4.7: one visible focus ring, from the stylesheet every element shares', () => {
  it('declares :focus-visible globally with a solid outline of at least 2px, offset off the element, in the focus colour', () => {
    const rule = styleRules().find(
      (candidate) => candidate.file === 'styles/base.css' && candidate.selectors.includes(':focus-visible'),
    )
    expect(rule, 'base.css no longer has the global :focus-visible rule').toBeTruthy()

    const declared = Object.fromEntries(rule.declarations.map((d) => [d.property, resolve(d.value)]))
    const outline = declared.outline ?? ''
    const width = parseFloat(outline)
    expect(outline).toContain('solid')
    expect(width).toBeGreaterThanOrEqual(2)
    // The ring is drawn in the focus token's colour; contrast.test.js holds that
    // colour to 3:1 against both surfaces (SC 1.4.11).
    expect(outline.toLowerCase()).toContain(resolve('var(--color-focus)').toLowerCase())
    expect(parseFloat(declared['outline-offset'] ?? '0')).toBeGreaterThanOrEqual(1)
  })

  it('never removes an outline without drawing a replacement in the same rule', () => {
    const offenders = []
    for (const rule of styleRules()) {
      for (const declaration of rule.declarations) {
        const value = resolve(declaration.value).trim().toLowerCase()
        const removesRing =
          (declaration.property === 'outline' && (value === 'none' || value === '0' || parseFloat(value) === 0)) ||
          (declaration.property === 'outline-width' && parseFloat(value) === 0) ||
          (declaration.property === 'outline-style' && value === 'none')
        if (!removesRing) continue
        const replacement = rule.declarations.some(
          (other) =>
            other !== declaration &&
            ((other.property === 'outline' && parseFloat(resolve(other.value)) > 0) ||
              other.property === 'box-shadow' ||
              (other.property === 'border' && parseFloat(resolve(other.value)) > 0)),
        )
        if (!replacement) offenders.push(`${rule.file}:${rule.line} ${rule.selectors.join(', ')}`)
      }
    }
    expect(offenders).toEqual([])
  })
})

describe('the skip link: hidden until focused, then shown in place', () => {
  it('is clipped while unfocused, and nothing hides it the moment keyboard focus reaches it', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    render(
      <MemoryRouter initialEntries={['/login']}>
        <App />
      </MemoryRouter>,
    )
    const skipLink = await screen.findByRole('link', { name: 'Skip to content' })

    // Unfocused: the .skip-link:not(:focus) rule collapses it.
    expect(hidingCauses(skipLink).join('\n')).toContain('.skip-link:not(:focus)')

    // The first press of Tab reaches it, and no rule hides a focused skip link.
    expect(pressTab()).toBe(skipLink)
    expect(hidingCauses(skipLink)).toEqual([])
  })

  it('moves focus to the main landmark when followed, so tabbing continues from the content', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    render(
      <MemoryRouter initialEntries={['/login']}>
        <App />
      </MemoryRouter>,
    )
    const skipLink = await screen.findByRole('link', { name: 'Skip to content' })
    const main = document.getElementById('main')
    expect(skipLink.getAttribute('href')).toBe('#main')
    // The main landmark can take focus programmatically without joining the tab order.
    expect(main.tabIndex).toBe(-1)
    main.focus()
    expect(document.activeElement).toBe(main)
  })
})

describe("the acknowledgement line: the brief's known case for a CSS rule jsdom cannot see", () => {
  it('is hidden by nothing in the markup or the stylesheets once an answer has arrived', async () => {
    serveApi({
      'GET /api/conversations': { body: [] },
      'POST /api/conversations': { status: 201, body: CONVERSATION },
      'POST /api/ask': { body: answeredReply() },
    })
    render(
      <MemoryRouter initialEntries={['/ask']}>
        <Ask />
      </MemoryRouter>,
    )
    await screen.findByText(TEXT.noConversations)
    fireEvent.change(screen.getByLabelText(TEXT.askFieldLabel), {
      target: { value: 'How much annual leave do I get?' },
    })
    fireEvent.click(screen.getByRole('button', { name: TEXT.askSubmit }))

    const acknowledgement = await screen.findByText(TEXT.answerReady(1, 1))
    expect(acknowledgement.getAttribute('role')).toBe('status')
    // The existing markup-level test (ask.test.jsx) checks classes and hidden
    // attributes; this one also reads every stylesheet rule matching the line
    // and its ancestors, so a hiding rule — display: none, zero size, clip,
    // transparent text — fails here instead of shipping.
    expect(hidingCauses(acknowledgement)).toEqual([])
    // It reserves its line, so an arriving answer does not shift the layout.
    const own = styleRules().find((rule) => rule.selectors.includes('.ask-form__status'))
    expect(own.declarations.some((d) => d.property === 'min-height' && parseFloat(resolve(d.value)) > 0)).toBe(true)
  })
})

describe('the reflow guards (SC 1.4.10, usability finding 6)', () => {
  it('anchors .table-scroll so absolutely positioned hidden text cannot escape the clip and widen the page', () => {
    // Measured on /documents at 320 CSS px before the fix: the sort heading's
    // visually-hidden ", sorted descending" span escaped the scroller — its
    // containing block was the page — and the whole page scrolled sideways by
    // 70px under content that painted nothing. position: relative makes the
    // scroller the containing block, so the span is clipped with its table.
    const scroller = styleRules().find((rule) => rule.selectors.includes('.table-scroll'))
    const declared = Object.fromEntries(scroller.declarations.map((d) => [d.property, resolve(d.value)]))
    expect(declared.position).toBe('relative')
    expect(declared['overflow-x']).toBe('auto')

    const hidden = styleRules().find((rule) => rule.selectors.includes('.visually-hidden'))
    expect(hidden.declarations.find((d) => d.property === 'position')?.value).toBe('absolute')
  })
})
