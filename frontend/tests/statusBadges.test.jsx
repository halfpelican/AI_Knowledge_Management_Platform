/**
 * PR #119's status badges on FR-15's document table, for every status the server
 * sends (apps/core/constants.py DOCUMENT_STATUS_VALUES, mirrored in
 * src/constants.js DOCUMENT_STATUS).
 *
 * DocumentRepository.jsx builds each badge's class from the status the server
 * recorded, and pages/Repository.css colours it. jsdom applies no stylesheet,
 * so the rules are read from disk (tests/stylesheets.js) and matched against the
 * rendered badge: each status must reach a rule that gives the badge its own
 * text colour and fill, and that pair must meet NFR-16's 4.5:1 (SC 1.4.3). A
 * status whose class no rule names would fall back to whatever the row has, and
 * a new status added to the vocabulary without a rule fails here by name.
 *
 * The badge is never the only carrier of the status: it shows the status in the
 * server's own words (SC 1.4.1), and nothing in the markup or the stylesheets
 * hides it. tokens.css has one theme, so there is one set of values to check.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { DOCUMENT_STATUS } from '../src/constants.js'
import DocumentRepository from '../src/pages/DocumentRepository.jsx'
import { serveApi } from './fakeApi.js'
import { colourTokensIn, contrast, hidingCauses, rulesMatching, tokenColour } from './stylesheets.js'

const TEXT_MINIMUM = 4.5 // SC 1.4.3, normal text

const STATUSES = Object.values(DOCUMENT_STATUS)

/** One document per status, in the contract's shape, each titled by its status. */
const DOCUMENTS = STATUSES.map((status, index) => ({
  doc_id: `doc-${index + 1}`,
  title: `Document whose status is ${status}`,
  file_type: 'pdf',
  status,
  uploaded_at: '2026-11-03T10:00:00+11:00',
  department: 'Finance',
  visible_to_roles: ['Employee', 'Administrator'],
  file_size_bytes: 14203,
  uploaded_by: 'erin@example.com',
}))

const BROWSE = {
  filters: { q: null, status: null, department: null, project: null, process: null, topic: null, sort: '-uploaded_at' },
  facets: { department: [{ value: 'Finance', count: DOCUMENTS.length }], project: [], process: [], topic: [] },
  documents: DOCUMENTS,
}

function renderRepository() {
  serveApi({ 'GET /api/documents/browse': { body: BROWSE } })
  render(
    <MemoryRouter initialEntries={['/documents']}>
      <Routes>
        <Route path="/documents" element={<DocumentRepository />} />
      </Routes>
    </MemoryRouter>,
  )
}

/** The colour tokens the rules matching `element` itself give `properties`. */
function tokensOn(element, properties) {
  return rulesMatching(element)
    .flatMap((rule) => rule.declarations)
    .filter((declaration) => properties.includes(declaration.property))
    .flatMap((declaration) => colourTokensIn(declaration.value))
}

describe('FR-15 / NFR-16: the status badge, for every status the server sends', () => {
  it('walks the seven statuses the server records, so the walk below is never empty or short', () => {
    // A value added to the vocabulary joins the walk below; one dropped from the
    // client's copy would leave its badge unchecked, so the count is held here.
    expect(STATUSES).toHaveLength(7)
  })

  it.each(STATUSES)('"%s": the status in words, on a fill of its own, its text 4.5:1 on that fill, hidden by nothing', async (status) => {
    renderRepository()
    const link = await screen.findByRole('link', { name: `Document whose status is ${status}` })
    const row = link.closest('tr')

    // In words: the badge holds the status exactly as the server sent it.
    const badge = within(row).getByText(status, { exact: true, selector: '.status-badge' })
    expect(badge.textContent).toBe(status)

    // Its own pair: one fill and one text colour, from rules that match the badge
    // itself, so neither is left to the row behind it.
    const fills = tokensOn(badge, ['background-color', 'background'])
    const inks = tokensOn(badge, ['color'])
    expect(fills, `no rule gives the "${status}" badge a fill`).toHaveLength(1)
    expect(inks, `no rule gives the "${status}" badge a text colour`).toHaveLength(1)

    const ratio = contrast(tokenColour(inks[0]), tokenColour(fills[0]))
    expect(ratio, `${inks[0]} on ${fills[0]} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(TEXT_MINIMUM)

    expect(hidingCauses(badge)).toEqual([])
  })
})
