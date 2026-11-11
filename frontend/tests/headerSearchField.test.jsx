/**
 * FR-12's Front-End clause: "A search field available from every page".
 *
 * It is built as `HeaderSearch` in the shell's header (src/App.jsx): one
 * `SearchField`, a `role="search"` landmark of its own, rendered while a user is
 * signed in. tests/search.test.jsx uses that field from the dashboard, and
 * docs/stage-5-front-end-clauses.md graded the clause partial because no test
 * walked the routes. This file walks them, with the walk FR-13's sibling clause
 * was given in tests/askNavLink.test.jsx (tests/routeWalk.jsx holds the cases).
 *
 * What is defended here:
 *
 * - **The walk.** The whole application, with the real routes, guards and auth
 *   provider, is rendered at every path in src/App.jsx's route table, and at `/`,
 *   once as an Employee and once as an Administrator. On the page each ends on,
 *   the banner landmark holds exactly one search landmark, and that holds exactly
 *   one input whose label is `TEXT.searchFieldLabel`, not disabled. It is
 *   looked for inside the banner because two pages have a search field of their
 *   own in the page (the search screen's, and the component sheet's sample), which
 *   must not stand in for the header's.
 * - **Using the field as an Administrator.** From an Administrator-only page, a
 *   term submitted in the header field shows the Search screen at `/search` for
 *   that term, in place of the page it was on. The same as an Employee, from the
 *   dashboard, is tests/search.test.jsx :: refuses one character from the header
 *   field with a message naming the minimum, sends nothing, and searches at two,
 *   and is not repeated here.
 *
 * What is not:
 *
 * - **Whether the field can be seen.** jsdom applies no stylesheet. These tests
 *   find the field in the accessibility tree; a CSS rule that hid it, or the
 *   header, would not fail them.
 * - **An anonymous visitor.** One has no search field, by design: RequireAuth
 *   would send them to `/login` before any results could render (src/App.jsx).
 *   tests/logout.test.jsx asserts there is no search landmark once signed out;
 *   this file asserts nothing about a visitor who never signed in.
 * - **An address no route matches.** It is not a page, and it is not walked.
 * - **Using the field from every page.** Its presence is asserted on every page;
 *   a term is submitted from one page here and one in tests/search.test.jsx. The
 *   test that submits one does not notice a disabled field, because `fireEvent`
 *   sets its value all the same; the walk does.
 * - **That the walk is every page.** tests/askNavLink.test.jsx :: has a case, as
 *   each role, for every path in the route table of src/App.jsx holds the cases
 *   to the route table, and they are the same cases here. That each page asks the
 *   API for what its case names is asserted there too, once.
 * - **The search screen itself**, which is tests/search.test.jsx's, the two-character
 *   minimum, and everything the server decides.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TEXT } from '../src/constants.js'
import {
  ADMINISTRATOR,
  SEARCH,
  SEARCH_TERM,
  TAGS,
  WALK,
  expectedRequests,
  primaryNavigationFor,
  renderApp,
  requested,
  serveSignedIn,
  walkCase,
} from './routeWalk.jsx'

/** For each search landmark in the page's banner, the inputs in it labelled `TEXT.searchFieldLabel`. */
function headerSearchFields() {
  return within(screen.getByRole('banner'))
    .queryAllByRole('search')
    .map((landmark) => within(landmark).queryAllByLabelText(TEXT.searchFieldLabel, { selector: 'input' }))
}

describe('FR-12: the search field is in the header of every page, for each role', () => {
  it.each(WALK)('$path as $who', async ({ user, path, page, lands }) => {
    serveSignedIn(user, page.api)
    const probe = renderApp(path)

    await page.settled()
    await waitFor(() => expect(probe.location?.pathname).toBe(lands))
    // The header shows the field only once the session check has answered, which
    // is after the heading on a page outside RequireAuth.
    await primaryNavigationFor(user)

    const landmarks = headerSearchFields()
    // Exactly one search landmark in the header, with exactly one labelled field.
    expect(landmarks.map((fields) => fields.length)).toEqual([1])
    // And the field can be typed in.
    expect(landmarks[0][0].disabled).toBe(false)
  })
})

describe('FR-12: the header search field searches, for an Administrator as for an Employee', () => {
  it('shows the Search screen at /search for a term an Administrator submits from /admin/tags', async () => {
    const { user, path, page, lands } = walkCase(ADMINISTRATOR, '/admin/tags', TAGS)
    const answered = serveSignedIn(user, { ...page.api, ...SEARCH.api })
    const probe = renderApp(path)
    await page.settled()
    await waitFor(() => expect(probe.location?.pathname).toBe(lands))
    await primaryNavigationFor(user)

    const header = within(screen.getByRole('banner')).getByRole('search')
    fireEvent.change(within(header).getByLabelText(TEXT.searchFieldLabel), { target: { value: SEARCH_TERM } })
    fireEvent.click(within(header).getByRole('button', { name: TEXT.searchSubmit }))

    await waitFor(() => expect(probe.location?.pathname).toBe('/search'))
    await SEARCH.settled()
    // The Search screen for the term as typed, in place of the page the field was used on.
    expect(probe.location.search).toBe(`?q=${SEARCH_TERM}`)
    expect(screen.getAllByRole('heading', { level: 1 }).map((heading) => heading.textContent)).toEqual([TEXT.searchHeading])
    expect(screen.getByRole('heading', { level: 2, name: TEXT.searchResultsFor(SEARCH_TERM) })).toBeTruthy()
    // One search, for that term, beside what the two pages ask for on their own.
    expect(answered.filter((request) => request.path === '/api/search').map((request) => request.search)).toEqual([
      `?q=${SEARCH_TERM}`,
    ])
    expect(requested(answered)).toEqual(expectedRequests(page, SEARCH))
  })
})
