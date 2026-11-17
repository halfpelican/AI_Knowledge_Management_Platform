/**
 * The shared button's boundary belongs to components/Button.css alone (NFR-14's
 * style guide; NFR-16, WCAG 2.1 SC 1.4.11).
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
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../src/App.jsx'
import { ROLES, TEXT } from '../src/constants.js'
import { serveApi } from './fakeApi.js'
import { colourTokensIn, contrast, rulesMatching, tokenColour } from './stylesheets.js'

const BUTTON_SHEET = 'components/Button.css'
const BORDER = /^border(-(top|right|bottom|left))?(-(color|style|width))?$/
const BOUNDARY_MINIMUM = 3 // SC 1.4.11

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

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

describe('SC 1.4.11: every secondary button keeps Button.css’s 3:1 border, whatever else styles .btn', () => {
  it('lets no stylesheet but Button.css touch a secondary button’s border on the repository screen', async () => {
    serveApi({
      'GET /api/auth/me': { body: EMPLOYEE },
      'GET /api/documents/browse': {
        body: {
          filters: { q: null, status: null, department: null, project: null, process: null, topic: null, sort: '-uploaded_at' },
          facets: { department: [], project: [], process: [], topic: [] },
          documents: [FAILED],
        },
      },
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
