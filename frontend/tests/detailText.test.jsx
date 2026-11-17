/**
 * The two blocks of stored text the detail screens show in full: FR-15's
 * extracted content on a document's page and FR-09's transcript on a meeting's.
 *
 * Both are untrusted text rendered as a text child (D-63), so their line breaks
 * are kept by CSS alone, and both can be long, so each scrolls inside its own
 * labelled, focusable region instead of stretching the page or, with one long
 * line, widening it (SC 1.4.10). PR #119 rewrote pages/Repository.css, which
 * these screens share, and the rules that did this went with the rewrite: the
 * extracted text ran its lines together. jsdom applies no stylesheet, so the
 * rules are read from disk (tests/stylesheets.js) and matched against the
 * rendered region.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthContext } from '../src/auth/context.js'
import { ROLES, TEXT } from '../src/constants.js'
import DocumentDetail from '../src/pages/DocumentDetail.jsx'
import MeetingDetail from '../src/pages/MeetingDetail.jsx'
import { serveApi, summaryRoute, summaryState } from './fakeApi.js'
import { hidingCauses, resolve, rulesMatching } from './stylesheets.js'

/** A line longer than any screen is wide, with no space to break at. */
const UNBROKEN = 'x'.repeat(400)

const DOCUMENT = {
  doc_id: 'doc-1',
  title: 'Leave policy 2026',
  file_type: 'pdf',
  status: 'Indexed',
  uploaded_at: '2026-09-21T10:00:00+10:00',
  department: 'Human Resources',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  file_size_bytes: 14203,
  uploaded_by: 'erin@example.com',
  extracted_text: `Employees may request annual leave.\nRequests go to the line manager.\n${UNBROKEN}`,
  tags: { project: [], process: [], topic: [] },
  can_delete: false,
}

const MEETING = {
  meeting_id: 'meeting-1',
  title: 'Q3 planning sync',
  meeting_date: '2026-07-28',
  status: 'Indexed',
  created_at: '2026-09-21T10:00:00+10:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: [],
  transcript_text: `Alex: the supplier review is due on Friday.\nSam: I will circulate the draft.\n${UNBROKEN}`,
  can_delete: false,
}

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

const SESSION = {
  user: EMPLOYEE,
  loading: false,
  login: async () => EMPLOYEE,
  register: async () => null,
  logout: async () => {},
  refresh: async () => EMPLOYEE,
}

function renderAt(path, element, routePath) {
  render(
    <AuthContext.Provider value={SESSION}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={element} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

/** What the rules matching `element` declare, later rules over earlier, `var()` resolved. */
function declaredOn(element) {
  return Object.fromEntries(
    rulesMatching(element)
      .flatMap((rule) => rule.declarations)
      .map((declaration) => [declaration.property, resolve(declaration.value).trim()]),
  )
}

/** The checks both blocks share: lines kept, long lines wrapped, scrolled in place. */
function expectKeptAndContained(region, text) {
  // The text is one text child, line breaks and all: nothing turned them into markup.
  expect(region.textContent).toBe(text)
  expect(region.children).toHaveLength(0)

  const declared = declaredOn(region)
  // The line breaks are kept and a long line wraps, which only pre-wrap does both of.
  expect(declared['white-space'], 'white-space').toBe('pre-wrap')
  // A run with nowhere to break still breaks, rather than widening the page.
  expect(declared['word-break'] ?? declared['overflow-wrap'], 'word-break or overflow-wrap').toMatch(/break-word|anywhere/)
  // It scrolls in its own region, at a height of its own, rather than stretching the page.
  expect(declared.overflow ?? declared['overflow-y'], 'overflow').toMatch(/^(auto|scroll)$/)
  expect(parseFloat(declared['max-height']), 'max-height').toBeGreaterThan(0)

  // A region a keyboard can reach and scroll, and nothing hides it.
  expect(region.tabIndex).toBe(0)
  expect(hidingCauses(region)).toEqual([])
}

describe('FR-15 / D-63: a document’s extracted text keeps its line breaks and scrolls in its own region', () => {
  it('keeps each line, wraps the long one, and scrolls inside the labelled region', async () => {
    serveApi({ [`GET /api/documents/${DOCUMENT.doc_id}`]: { body: DOCUMENT } })
    renderAt(`/documents/${DOCUMENT.doc_id}`, <DocumentDetail />, '/documents/:docId')
    await screen.findByRole('heading', { level: 1, name: DOCUMENT.title })

    expectKeptAndContained(screen.getByRole('region', { name: TEXT.documentExtractedHeading }), DOCUMENT.extracted_text)
  })
})

describe('FR-09: the stored transcript, viewable in full, keeps its lines and scrolls in its own region', () => {
  it('keeps each line, wraps the long one, and scrolls inside the labelled region', async () => {
    serveApi({
      [`GET /api/meetings/${MEETING.meeting_id}`]: { body: MEETING },
      [`GET /api/meetings/${MEETING.meeting_id}/summary`]: summaryRoute(summaryState()),
    })
    renderAt(`/meetings/${MEETING.meeting_id}`, <MeetingDetail />, '/meetings/:meetingId')
    await screen.findByRole('heading', { level: 1, name: MEETING.title })

    expectKeptAndContained(screen.getByRole('region', { name: TEXT.transcriptHeading }), MEETING.transcript_text)
  })
})
