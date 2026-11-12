/**
 * FR-13's Front-End clause: "A conversational interface reachable from any page".
 *
 * It is built as the Ask link in the shell's primary navigation (src/App.jsx,
 * `PrimaryNav`), shown while a user is signed in. A requirements re-audit on
 * 11 November 2026 found that nothing under tests/ asserted the link, so the clause
 * had no front-end evidence (CLAUDE.md §8 condition 2). The sibling clause, FR-12's
 * "a search field available from every page", was graded partial for being tested
 * on two pages with no test walking the routes (docs/stage-5-front-end-clauses.md),
 * so this file walks them.
 *
 * The walk itself, meaning the cases, each page's replies and the rendering, is in
 * tests/routeWalk.jsx since 12 November 2026, when FR-12's clause was given the
 * same walk in tests/headerSearchField.test.jsx. The assertions here are FR-13's.
 *
 * What is defended here:
 *
 * - **The walk.** The whole application, with the real routes, guards and auth
 *   provider, is rendered at every path in src/App.jsx's route table, and at `/`,
 *   once as an Employee and once as an Administrator. On the page each ends on,
 *   the navigation landmark named "Primary" holds exactly one link whose accessible
 *   name is `TEXT.askNavLabel`, and its `href` is `/ask`. Where the application
 *   sends the user on, the case says where and asserts it: `/`, `/login` and
 *   `/register` send a signed-in user to their dashboard, and the three
 *   Administrator-only paths send an Employee to `/403`.
 * - **Following the link.** From four of those pages, two for each role, a click on
 *   the link shows the Ask screen at `/ask` in place of the page it was on.
 * - **The route table.** Every `path="…"` in src/App.jsx has a case in the walk as
 *   each role, so a route added there without one fails here. FR-12's file walks
 *   the same cases and relies on this test.
 *
 * What is not:
 *
 * - **Whether the link can be seen.** jsdom applies no stylesheet. These tests find
 *   the link in the accessibility tree; a CSS rule that hid it, or the navigation,
 *   would not fail them. tests/tabOrder.test.jsx would, on the screens it walks as
 *   an Employee: it reads the stylesheets and fails on any keyboard stop a rule
 *   hides (break V2 of 12 November, docs/decisions.md D-94's later note).
 * - **An anonymous visitor.** One is offered no Ask link, by design: RequireAuth
 *   would send them to `/login` (src/App.jsx). This file asserts that neither way.
 * - **An address no route matches.** It is not a page, and it is not walked.
 * - **Following the link from every page.** The link's presence and target are
 *   asserted on every page; the click is made from four.
 * - **Which roles a new route admits.** The route-table test cannot read a guard
 *   from the source, so it asks for a case as each role and the case says where
 *   that role lands.
 * - **The Ask screen itself**, which is tests/ask*.test.jsx's, and everything the
 *   server decides. The replies are the same for both roles: what a server would
 *   send each differently (scope, `can_delete`) plays no part in the navigation.
 *
 * Each case's table names the routes its page asks for and no others: a request
 * nothing answers fails the test (tests/setup.js), and so does a route the page
 * never asked for.
 *
 * The location is read by a probe in a layout effect and asserted in `waitFor`
 * (tests/dashboard.test.jsx says why).
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { matchPath } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import {
  ADMINISTRATOR,
  ASK,
  BOTH_ROLES,
  DASHBOARD,
  DOCUMENT,
  DOCUMENT_DETAIL,
  EMPLOYEE,
  TAGS,
  WALK,
  expectedRequests,
  pathnameOf,
  primaryNavigationFor,
  renderApp,
  requested,
  serveSignedIn,
  walkCase,
} from './routeWalk.jsx'

/** Where every link named `TEXT.askNavLabel` in the navigation goes. */
function askLinkTargets(navigation) {
  return within(navigation)
    .queryAllByRole('link', { name: TEXT.askNavLabel })
    .map((link) => link.getAttribute('href'))
}

/* ---- Tests --------------------------------------------------------------- */

describe('FR-13: the Ask link is in the primary navigation of every page, for each role', () => {
  it.each(WALK)('$path as $who', async ({ user, path, page, lands }) => {
    const answered = serveSignedIn(user, page.api)
    const probe = renderApp(path)

    await page.settled()
    await waitFor(() => expect(probe.location?.pathname).toBe(lands))
    const navigation = await primaryNavigationFor(user)

    // Exactly one, and it goes to the Ask screen.
    expect(askLinkTargets(navigation)).toEqual(['/ask'])
    // The page asked for what its table names: nothing more (tests/setup.js fails
    // the test on a request nothing answers) and nothing less.
    expect(requested(answered)).toEqual(expectedRequests(page))
  })
})

describe('FR-13: the Ask link opens the Ask screen', () => {
  it.each([
    walkCase(EMPLOYEE, '/dashboard', DASHBOARD),
    walkCase(EMPLOYEE, `/documents/${DOCUMENT.doc_id}`, DOCUMENT_DETAIL),
    walkCase(ADMINISTRATOR, '/admin', DASHBOARD),
    walkCase(ADMINISTRATOR, '/admin/tags', TAGS),
  ])('from $path as $who', async ({ user, path, page, lands }) => {
    const answered = serveSignedIn(user, { ...page.api, ...ASK.api })
    const probe = renderApp(path)
    await page.settled()
    await waitFor(() => expect(probe.location?.pathname).toBe(lands))
    const navigation = await primaryNavigationFor(user)

    fireEvent.click(within(navigation).getByRole('link', { name: TEXT.askNavLabel }))

    await waitFor(() => expect(probe.location?.pathname).toBe('/ask'))
    await ASK.settled()
    // The Ask screen with no thread named, in place of the page the link was on.
    expect(probe.location.search).toBe('')
    expect(screen.getAllByRole('heading', { level: 1 }).map((heading) => heading.textContent)).toEqual([TEXT.askHeading])
    expect(requested(answered)).toEqual(expectedRequests(page, ASK))
  })
})

describe('the walk is held to the route table', () => {
  it('has a case, as each role, for every path in the route table of src/App.jsx', () => {
    const source = readFileSync(join(import.meta.dirname, '..', 'src', 'App.jsx'), 'utf8')
    const declared = [...source.matchAll(/\bpath="([^"]+)"/g)].map((match) => match[1])
    // Every `path=` in the file was read. One written another way (`path={…}`)
    // fails here rather than being skipped. The index route has no path, and is
    // walked as `/`.
    expect(declared).toHaveLength(source.match(/\bpath=/g).length)

    for (const user of BOTH_ROLES) {
      const walked = WALK.filter((walk) => walk.user === user).map((walk) => pathnameOf(walk.path))
      const unwalked = declared.filter((pattern) => !walked.some((pathname) => matchPath(`/${pattern}`, pathname)))
      expect(unwalked, `paths in src/App.jsx with no case as an ${user.role}`).toEqual([])
    }
  })
})
