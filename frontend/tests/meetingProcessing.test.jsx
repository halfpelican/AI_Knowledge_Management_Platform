/**
 * FR-09's transcript form: "A processing indicator is shown while ingestion runs."
 *
 * Ingestion is synchronous (FR-08's chunking and embedding run inside the request), so
 * the wait is the request, and the indicator is what tells the user the form has not
 * frozen. Both ways FR-09 offers to supply a transcript are exercised: pasted text,
 * which goes through `fetch`, and a file, which goes through `XMLHttpRequest`
 * (src/api/meetings.js). tests/fakeApi.js answers both from one table, and
 * `heldResponse` keeps the request open long enough to look at the screen.
 *
 * The 400s, the future-date refusal and the transcript surviving a failed index
 * (NFR-20) are the server's and pytest's. jsdom applies no stylesheet, so "shown"
 * here means in the document and not inside anything hidden by markup
 * (`hidden`, `.visually-hidden`); a CSS rule that hid the line would not be seen.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthContext } from '../src/auth/context.js'
import { ROLES, TEXT } from '../src/constants.js'
import Meetings from '../src/pages/Meetings.jsx'
import { heldResponse, serveApi } from './fakeApi.js'

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

/** The signed-in session the screen reads its role from. */
const AUTH = {
  user: EMPLOYEE,
  loading: false,
  login: async () => EMPLOYEE,
  register: async () => null,
  logout: async () => {},
  refresh: async () => EMPLOYEE,
}

const TRANSCRIPT = 'Alex: the supplier review is due on Friday. Sam: I will circulate the draft on Wednesday.'

const STORED = {
  meeting_id: 'meeting-9',
  title: 'Supplier sync',
  meeting_date: '2020-01-15',
  status: 'Indexed',
  created_at: '2026-11-02T10:00:00+11:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: [],
}

function renderMeetings() {
  render(
    <AuthContext.Provider value={AUTH}>
      <MemoryRouter initialEntries={['/meetings']}>
        <Routes>
          <Route path="/meetings" element={<Meetings />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

/** True where nothing on the path from the node to the root hides it by markup. */
function isOnScreen(node) {
  for (let current = node; current; current = current.parentElement) {
    if (current.hidden || current.classList?.contains('visually-hidden')) return false
  }
  return true
}

/** The form's live line, which carries the indicator's words while it runs. */
function progressLine() {
  const form = screen.getByRole('button', { name: /Add transcript|Processing…/ }).closest('form')
  return within(form)
    .getAllByRole('status')
    .find((node) => node.classList.contains('meeting-form__progress'))
}

async function fillForm(source) {
  await screen.findByText(TEXT.noMeetings)
  fireEvent.change(screen.getByLabelText('Meeting title'), { target: { value: STORED.title } })
  fireEvent.change(screen.getByLabelText('Meeting date'), { target: { value: STORED.meeting_date } })
  if (source === 'text') {
    fireEvent.change(screen.getByLabelText('Transcript'), { target: { value: TRANSCRIPT } })
  } else {
    fireEvent.click(screen.getByLabelText(TEXT.meetingSourceFile))
    fireEvent.change(screen.getByLabelText('Transcript file'), {
      target: { files: [new File([TRANSCRIPT], 'supplier-sync.txt', { type: 'text/plain' })] },
    })
  }
}

function ingestions(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/meetings')
}

describe('FR-09: a processing indicator while ingestion runs', () => {
  it.each(['text', 'file'])(
    'shows it while a %s transcript is ingested, holds the form, and withdraws it when the server answers',
    async (source) => {
      const ingestion = heldResponse()
      let stored = false
      const answered = serveApi({
        'GET /api/meetings': () => ({ body: stored ? [STORED] : [] }),
        'GET /api/users/directory': { body: [] },
        'POST /api/meetings': ingestion.route,
      })
      renderMeetings()
      await fillForm(source)
      expect(progressLine().textContent).toBe('')

      fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))

      // While the request is out: the indicator's words in the live line, on screen;
      // the button busy and disabled, so it cannot be sent twice; the form held.
      await waitFor(() => expect(progressLine().textContent).toBe(TEXT.meetingProcessing))
      expect(TEXT.meetingProcessing).toMatch(/processing/i)
      expect(isOnScreen(progressLine())).toBe(true)
      const busy = screen.getByRole('button', { name: 'Processing…' })
      expect(busy.disabled).toBe(true)
      expect(busy.getAttribute('aria-busy')).toBe('true')
      expect(screen.getByLabelText('Meeting title').disabled).toBe(true)
      expect(screen.getByLabelText('Meeting date').disabled).toBe(true)
      expect(screen.queryByText('Transcript stored')).toBeNull()
      expect(ingestions(answered)).toHaveLength(1)

      stored = true
      ingestion.release({ status: 201, body: STORED })

      const notice = (await screen.findByText('Transcript stored')).closest('[role="status"]')
      expect(notice.textContent).toContain(TEXT.meetingIndexed(STORED.title))
      expect(within(notice).getByRole('link', { name: 'View the transcript' }).getAttribute('href')).toBe(
        `/meetings/${STORED.meeting_id}`,
      )
      expect(progressLine().textContent).toBe('')
      expect(screen.getByRole('button', { name: 'Add transcript' }).disabled).toBe(false)
      expect(screen.queryByRole('button', { name: 'Processing…' })).toBeNull()
      expect(ingestions(answered)).toHaveLength(1)
    },
  )

  it('withdraws it when the transcript is stored but cannot be indexed, and says so', async () => {
    const ingestion = heldResponse()
    serveApi({
      'GET /api/meetings': { body: [] },
      'GET /api/users/directory': { body: [] },
      'POST /api/meetings': ingestion.route,
    })
    renderMeetings()
    await fillForm('text')

    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))
    await waitFor(() => expect(progressLine().textContent).toBe(TEXT.meetingProcessing))

    ingestion.release({ status: 422, body: { ...STORED, status: 'Processing failed' } })

    const notice = (await screen.findByText('Stored, but not indexed')).closest('[role="alert"]')
    expect(notice.textContent).toContain(TEXT.meetingStoredNotIndexed)
    expect(progressLine().textContent).toBe('')
    expect(screen.getByRole('button', { name: 'Add transcript' }).disabled).toBe(false)
    expect(screen.queryByText('Transcript stored')).toBeNull()
  })
})
