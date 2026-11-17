/**
 * The shared button's look belongs to components/Button.css alone, everywhere but the
 * home page's two calls to action (NFR-14's style guide; NFR-16, WCAG 2.1 SC 1.4.11).
 *
 * A secondary button is the surface colour on the surface: its border is the
 * only thing that shows it is a control, and Button.css draws it in
 * --color-border-strong, 3:1 or better on both surfaces. PR #119's home screen
 * stylesheet restated the bare `.btn` rule with `border: ... transparent`, and
 * because pages/Home.css comes after Button.css in the bundle, that shorthand
 * reset the secondary border on every screen: in a browser the header's Search,
 * Log out and the repository's Filter showed as bare words. jsdom applies no
 * stylesheet and the bundle's order is not visible here, so the test asks the
 * stronger thing that makes the order irrelevant: of every rule that reaches a
 * secondary button on a real screen, only Button.css's touch its border.
 *
 * **The rest of #119's button look stays on the home page (Benjamin, 18 November
 * 2026).** Home.css's other `.btn` rules gave every button on every screen #119's
 * padding, weight and transition, and every primary button its hover lift and
 * shadow, disabled ones included (FEA-8). They are now scoped to the home page's
 * calls to action. Three tests hold that:
 *
 * - no stylesheet but Button.css styles a button's own classes on a screen other than
 *   the home page, and every other stylesheet that names one does so under a
 *   context of its own;
 * - a disabled primary button neither lifts nor darkens on hover, and an enabled one
 *   gets Button.css's hover alone;
 * - on the home page, #119's look reaches both calls to action, and it outranks every
 *   other rule there by specificity, so it no longer depends on the bundle's order.
 *
 * jsdom matches no `:hover`. A hover rule is read here as the rule it would be with
 * `:hover` taken out of its selector: what reaches the element once the pointer is on
 * it.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { PROFILE_TEXT, ROLES, TEXT } from '../src/constants.js'
import { heldResponse, serveApi } from './fakeApi.js'
import { BOTH_ROLES, renderApp, serveSignedIn } from './routeWalk.jsx'
import {
  colourTokensIn,
  compareSpecificity,
  contrast,
  rulesMatching,
  selectorMatches,
  specificity,
  splitTopLevel,
  styleRules,
  tokenColour,
} from './stylesheets.js'

const BUTTON_SHEET = 'components/Button.css'
const HOME_SHEET = 'pages/Home.css'
const BORDER = /^border(-(top|right|bottom|left))?(-(color|style|width))?$/
const BOUNDARY_MINIMUM = 3 // SC 1.4.11

/** A selector that names one of the shared button's own classes: `.btn` or a `.btn--variant`, not `.btn__spinner`. */
const BUTTON_CLASS = /\.btn(?:--[\w-]+)?(?![\w-])/

/** What a hover does to a button: lift it, shadow it, or change its colours. */
const HOVER_EFFECT = /^(transform|translate|scale|box-shadow|background|background-color|border|border-color|color|filter)$/

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

const NOT_SIGNED_IN = { status: 401, body: { detail: 'Authentication credentials were not provided.' } }

/** A document that failed to index, so its row offers FR-08's retry as a secondary button. */
const FAILED = {
  doc_id: 'doc-1',
  title: 'Leave policy 2026',
  file_type: 'pdf',
  status: 'Indexing failed',
  uploaded_at: '2026-09-21T10:00:00+10:00',
  department: 'Human Resources',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  file_size_bytes: 14203,
  uploaded_by: 'erin@example.com',
}

const BROWSE = {
  filters: { q: null, status: null, department: null, project: null, process: null, topic: null, sort: '-uploaded_at' },
  facets: { department: [], project: [], process: [], topic: [] },
  documents: [FAILED],
}

/** A user's saved picture, so the Profile page's Remove is offered too. */
const pictureOf = (user) => `/api/users/${user.id}/picture?v=1794823200123456`

/** Every rule whose selector, with `:hover` taken out, reaches `element`: what applies once it is hovered. */
function hoverRulesFor(element) {
  const found = []
  for (const rule of styleRules()) {
    const selector = rule.selectors.find(
      (candidate) => candidate.includes(':hover') && selectorMatches(element, candidate.replaceAll(':hover', '')),
    )
    if (selector) found.push({ ...rule, selector })
  }
  return found
}

/** A rule as a failure message names it. */
function named(rule) {
  return `${rule.file}:${rule.line} ${rule.selector}`
}

/**
 * The compound selector that names a button class, and how many compounds come before
 * it: zero for a bare `.btn--primary:hover`, one for `.home-actions .btn`.
 */
function compoundsBeforeButtonClass(selector) {
  const compounds = splitTopLevel(selector.replace(/\s*([>+~])\s*/g, ' '), ' ')
  return compounds.findIndex((compound) => BUTTON_CLASS.test(compound))
}

describe('SC 1.4.11: every secondary button keeps Button.css’s 3:1 border, whatever else styles .btn', () => {
  it('lets no stylesheet but Button.css touch a secondary button’s border on the repository screen', async () => {
    serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/documents/browse': { body: BROWSE },
    })
    render(
      <MemoryRouter initialEntries={['/documents']}>
        <App />
      </MemoryRouter>,
    )
    await screen.findByRole('link', { name: FAILED.title })

    // The header's search and log out, the title filter, and the row's retry.
    const buttons = [
      screen.getByRole('button', { name: TEXT.searchSubmit }),
      screen.getByRole('button', { name: 'Log out' }),
      screen.getByRole('button', { name: TEXT.repositoryFilterSubmit }),
      screen.getByRole('button', { name: TEXT.documentRetryLabel(FAILED.title) }),
    ]
    for (const button of buttons) {
      expect(button.classList.contains('btn--secondary'), `${button.textContent} is a secondary button`).toBe(true)

      const touching = rulesMatching(button).filter((rule) =>
        rule.declarations.some((declaration) => BORDER.test(declaration.property)),
      )
      const elsewhere = touching.filter((rule) => rule.file !== BUTTON_SHEET)
      expect(
        elsewhere.map((rule) => `${rule.file}:${rule.line} ${rule.selector}`),
        `rules outside ${BUTTON_SHEET} that set "${button.textContent}"'s border`,
      ).toEqual([])

      // And Button.css's own border for it is a boundary colour: 3:1 on both surfaces.
      const colours = touching
        .flatMap((rule) => rule.declarations)
        .filter((declaration) => BORDER.test(declaration.property))
        .flatMap((declaration) => colourTokensIn(declaration.value))
      const border = colours.at(-1)
      expect(border, `"${button.textContent}" has a border colour`).toBeDefined()
      for (const surface of ['--color-surface', '--color-surface-alt']) {
        expect(contrast(tokenColour(border), tokenColour(surface))).toBeGreaterThanOrEqual(BOUNDARY_MINIMUM)
      }
    }
  })
})

/* ---- #119's button look, on the home page alone (Benjamin, 18 November 2026) ---- */

/**
 * Screens other than the home page, as each role where signed in. Between them they
 * hold both variants, enabled and disabled, and links and a label with the button's look.
 */
const SCREENS = [
  {
    what: 'sign-in, to a visitor not signed in',
    path: '/login',
    serve: () => serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN }),
    settled: () => screen.findByRole('heading', { level: 1, name: 'Sign in' }),
  },
  ...BOTH_ROLES.flatMap((user) => [
    {
      what: `the repository, as an ${user.role}`,
      path: '/documents',
      serve: () => serveSignedIn(user, { 'GET /api/documents/browse': { body: BROWSE } }),
      settled: () => screen.findByRole('link', { name: FAILED.title }),
    },
    {
      what: `the Profile page, as an ${user.role}`,
      path: '/profile',
      serve: () => serveSignedIn({ ...user, picture: pictureOf(user) }, {}),
      settled: () => screen.findByRole('heading', { level: 1, name: PROFILE_TEXT.heading }),
    },
    {
      what: `upload, as an ${user.role}`,
      path: '/upload',
      serve: () => serveSignedIn(user, {}),
      settled: () => screen.findByRole('heading', { level: 1, name: 'Upload documents' }),
    },
  ]),
]

describe('NFR-14: #119’s button look is the home page’s alone; every other screen’s buttons are Button.css’s', () => {
  it.each(SCREENS)('lets no stylesheet but Button.css style a button’s own classes on $what', async ({ path, serve, settled }) => {
    serve()
    renderApp(path)
    await settled()

    // Buttons, and links and labels given the button's look. Never an empty walk.
    const buttons = [...document.querySelectorAll('.btn')]
    expect(buttons.length).toBeGreaterThan(0)
    for (const button of buttons) {
      const elsewhere = rulesMatching(button).filter((rule) => rule.file !== BUTTON_SHEET && BUTTON_CLASS.test(rule.selector))
      expect(elsewhere.map(named), `rules outside ${BUTTON_SHEET} that style "${button.textContent}"`).toEqual([])
    }
  })

  it('names a button class outside Button.css only under a context of its own, never bare', () => {
    const bare = []
    for (const rule of styleRules()) {
      if (rule.file === BUTTON_SHEET) continue
      for (const selector of rule.selectors) {
        if (BUTTON_CLASS.test(selector) && compoundsBeforeButtonClass(selector) === 0) bare.push(`${rule.file}:${rule.line} ${selector}`)
      }
    }
    expect(bare).toEqual([])
  })
})

describe('FEA-8: a disabled primary button neither lifts nor darkens on hover, on any screen', () => {
  /** Each screen's disabled primary buttons, in the state that disables them. */
  const DISABLED = [
    {
      // Sign in, while a sign-in is in flight.
      what: 'sign-in, while signing in',
      async open() {
        serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN, 'POST /api/auth/login': heldResponse().route })
        renderApp('/login')
        fireEvent.change(await screen.findByLabelText('Email'), { target: { value: EMPLOYEE.email } })
        fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Correct-Horse-1' } })
        fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
        return [await screen.findByRole('button', { name: 'Signing in…' })]
      },
    },
    ...BOTH_ROLES.flatMap((user) => [
      {
        // Change password and Upload picture, with nothing to send.
        what: `the Profile page, as an ${user.role}`,
        async open() {
          serveSignedIn(user, {})
          renderApp('/profile')
          await screen.findByRole('heading', { level: 1, name: PROFILE_TEXT.heading })
          return [
            screen.getByRole('button', { name: PROFILE_TEXT.changePassword }),
            screen.getByRole('button', { name: PROFILE_TEXT.uploadPicture }),
          ]
        },
      },
      {
        // Upload, with nothing queued.
        what: `upload, as an ${user.role}`,
        async open() {
          serveSignedIn(user, {})
          renderApp('/upload')
          return [await screen.findByRole('button', { name: 'Upload 0 files' })]
        },
      },
    ]),
  ]

  it.each(DISABLED)('no hover rule lifts or recolours a disabled primary button on $what', async ({ open }) => {
    const buttons = await open()
    expect(buttons.length).toBeGreaterThan(0)
    for (const button of buttons) {
      expect(button.disabled, `"${button.textContent}" is disabled`).toBe(true)
      expect(button.classList.contains('btn--primary'), `"${button.textContent}" is a primary button`).toBe(true)
      const effects = hoverRulesFor(button).filter((rule) =>
        rule.declarations.some((declaration) => HOVER_EFFECT.test(declaration.property)),
      )
      expect(effects.map(named), `hover rules that reach the disabled "${button.textContent}"`).toEqual([])
    }
  })

  it.each(BOTH_ROLES)('an enabled primary button gets Button.css’s hover and no lift, as an $role', async (user) => {
    serveSignedIn({ ...user, picture: pictureOf(user) }, {})
    renderApp('/profile')
    await screen.findByRole('heading', { level: 1, name: PROFILE_TEXT.heading })
    const remove = screen.getByRole('button', { name: PROFILE_TEXT.removeSavedLabel })
    expect(remove.disabled).toBe(false)
    expect(remove.classList.contains('btn--primary')).toBe(true)

    // The matcher sees a hover where there is one: Button.css darkens the fill.
    const hovers = hoverRulesFor(remove).filter((rule) =>
      rule.declarations.some((declaration) => HOVER_EFFECT.test(declaration.property)),
    )
    expect(hovers.length).toBeGreaterThan(0)
    expect(hovers.filter((rule) => rule.file !== BUTTON_SHEET).map(named)).toEqual([])
    const lifts = hovers.flatMap((rule) => rule.declarations).filter((declaration) => /^(transform|translate|box-shadow)$/.test(declaration.property))
    expect(lifts).toEqual([])
  })
})

describe('#119’s look stays on the home page’s two calls to action, and wins there whatever the bundle’s order', () => {
  /** Every declaration of every rule reaching `element`, with its rule's file and specificity, for a property. */
  function declarationsFor(rules, property) {
    return rules.flatMap((rule) =>
      rule.declarations
        .filter((declaration) => declaration.property === property)
        .map((declaration) => ({ ...declaration, rule, specificity: specificity(rule.selector) })),
    )
  }

  /**
   * For each property a Home.css rule sets on `element`, that rule outranks every other
   * stylesheet's rule setting the same property by specificity alone. In the browser
   * the bundle's order breaks a tie, and nothing here can see that order.
   */
  function expectHomeOutranks(rules) {
    const fromHome = rules.filter((rule) => rule.file === HOME_SHEET)
    const losing = []
    for (const property of new Set(fromHome.flatMap((rule) => rule.declarations.map((declaration) => declaration.property)))) {
      const all = declarationsFor(rules, property)
      const home = all.filter((declaration) => declaration.rule.file === HOME_SHEET)
      const strongest = home.reduce((best, declaration) =>
        compareSpecificity(declaration.specificity, best.specificity) > 0 ? declaration : best,
      )
      for (const other of all.filter((declaration) => declaration.rule.file !== HOME_SHEET)) {
        if (compareSpecificity(strongest.specificity, other.specificity) <= 0) {
          losing.push(`${property}: ${named(strongest.rule)} [${strongest.specificity}] does not outrank ${named(other.rule)} [${other.specificity}]`)
        }
      }
    }
    expect(losing).toEqual([])
  }

  /** The value a Home.css rule reaching the element gives `property`, or undefined. */
  function homeValue(rules, property) {
    return declarationsFor(rules.filter((rule) => rule.file === HOME_SHEET), property).at(-1)?.value
  }

  it('gives "Sign in" #119’s large primary look and its lift on hover, and "Create an account" its outline look, to a visitor not signed in', async () => {
    serveApi({ 'GET /api/auth/me': NOT_SIGNED_IN })
    renderApp('/')
    await screen.findByRole('heading', { level: 1, name: TEXT.homeHeading })
    const actions = within(screen.getByRole('main'))
    const signIn = actions.getByRole('link', { name: TEXT.homeSignIn })
    const register = actions.getByRole('link', { name: TEXT.homeRegister })

    for (const link of [signIn, register]) {
      const rules = rulesMatching(link)
      // #119's padding, weight and size, and its large call to action's width.
      expect(homeValue(rules, 'padding'), `${link.textContent}: #119's large padding`).toBe('var(--space-4) var(--space-6)')
      expect(homeValue(rules, 'font-weight')).toBe('var(--weight-semibold)')
      expect(homeValue(rules, 'min-width')).toBe('160px')
      expectHomeOutranks(rules)
      expectHomeOutranks(hoverRulesFor(link))
    }

    const signInRules = rulesMatching(signIn)
    expect(homeValue(signInRules, 'background-color')).toBe('var(--color-primary)')
    const signInHover = hoverRulesFor(signIn)
    expect(homeValue(signInHover, 'transform')).toBe('translateY(-1px)')
    expect(homeValue(signInHover, 'box-shadow')).toBe('var(--shadow-md)')

    const registerRules = rulesMatching(register)
    expect(homeValue(registerRules, 'background-color')).toBe('transparent')
    expect(homeValue(registerRules, 'border-color')).toBe('var(--color-border-strong)')
    expect(homeValue(hoverRulesFor(register), 'border-color')).toBe('var(--color-primary)')
  })
})
