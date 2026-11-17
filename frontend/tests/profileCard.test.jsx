/**
 * The card at the top of #119's Profile page: the signed-in user's picture or
 * initials, name, address, role badge and "Member since".
 *
 * - **The role badge in #119's colours (FEA-7).** Sagarika's badge was an inline
 *   style: the Administrator's #166534 on #dcfce7, the Employee's #1e40af on #dbeafe.
 *   D-137's wiring moved it to Profile.css on the tokens that existed then, which
 *   changed both. Each is back, from tokens, and each pair is held to 4.5:1 here and
 *   in tests/contrast.test.js.
 *
 * jsdom applies no stylesheet, so the colours are read from the rules
 * tests/stylesheets.js finds matching the rendered badge.
 */
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PROFILE_TEXT, ROLES } from '../src/constants.js'
import { BOTH_ROLES, primaryNavigationFor, renderApp, serveSignedIn } from './routeWalk.jsx'
import { colourTokensIn, contrast, hidingCauses, rulesMatching, tokenColour } from './stylesheets.js'

const TEXT_MINIMUM = 4.5 // SC 1.4.3

/** A parsed colour as #rrggbb. */
function hex({ r, g, b }) {
  return `#${[r, g, b].map((channel) => channel.toString(16).padStart(2, '0')).join('')}`
}

async function openProfile(user) {
  serveSignedIn(user, {})
  renderApp('/profile')
  await screen.findByRole('heading', { level: 1, name: PROFILE_TEXT.heading })
  await primaryNavigationFor(user)
}

/** The badge on the card. */
function badge() {
  return document.querySelector('.profile-card .profile-role')
}

/**
 * The one colour token the rules matching `element` give `property`. Exactly one rule
 * may set it, so which one the browser uses never depends on order.
 */
function colourFor(element, property) {
  const setting = rulesMatching(element).flatMap((rule) =>
    rule.declarations.filter((declaration) => declaration.property === property).map((declaration) => ({ rule, declaration })),
  )
  expect(
    setting.map(({ rule }) => `${rule.file}:${rule.line} ${rule.selector}`),
    `one rule sets the badge's ${property}`,
  ).toHaveLength(1)
  const tokens = colourTokensIn(setting[0].declaration.value)
  expect(tokens, `the badge's ${property} is one colour token`).toHaveLength(1)
  return { token: tokens[0], colour: tokenColour(tokens[0]) }
}

describe('FEA-7: the role badge in #119’s colours, from tokens', () => {
  const HERS = {
    [ROLES.administrator]: { text: '#166534', fill: '#dcfce7' },
    [ROLES.employee]: { text: '#1e40af', fill: '#dbeafe' },
  }

  it.each(BOTH_ROLES)('as an $role, says the role in #119’s colours for it, 4.5:1 or better, and nothing hides it', async (user) => {
    await openProfile(user)
    const shown = badge()
    expect(shown.textContent).toBe(user.role)

    const text = colourFor(shown, 'color')
    const fill = colourFor(shown, 'background-color')
    expect(hex(text.colour), 'the text colour #119 gave this role').toBe(HERS[user.role].text)
    expect(hex(fill.colour), 'the fill #119 gave this role').toBe(HERS[user.role].fill)
    expect(contrast(text.colour, fill.colour)).toBeGreaterThanOrEqual(TEXT_MINIMUM)
    // #119's borders were a shade darker than each fill and have no token: each is
    // drawn in its own fill, so the badge keeps its size and shows no other colour.
    expect(colourFor(shown, 'border-color').token).toBe(fill.token)
    expect(hidingCauses(shown)).toEqual([])
  })
})
