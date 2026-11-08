/**
 * Usability finding 5 (docs/usability-findings.md): the attendee control was a
 * native multi-select listbox, so a second person needed Ctrl+click, nothing
 * said so, and the natural gesture silently undid the first choice — a meeting
 * was ingested with zero attendees before anyone noticed.
 *
 * The replacement adds one person at a time with plain presses: a single
 * select, an Add button, and a visible list with a Remove per person
 * (src/components/AttendeePicker.jsx). These tests defend the gesture the
 * finding is about: two people chosen the natural way are both recorded and
 * both sent, and no multi-select listbox remains to bring the failure back.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthContext } from '../src/auth/context.js'
import { ROLES, TEXT } from '../src/constants.js'
import Meetings from '../src/pages/Meetings.jsx'
import { serveApi } from './fakeApi.js'

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

const AUTH = {
  user: EMPLOYEE,
  loading: false,
  login: async () => EMPLOYEE,
  register: async () => null,
  logout: async () => {},
  refresh: async () => EMPLOYEE,
}

/** The directory as D-34 serves it: name and address, no role. */
const DIRECTORY = [
  { id: 'user-ada', name: 'Ada Admin', email: 'ada@example.com' },
  { id: 'user-erin', name: 'Erin Employee', email: 'erin@example.com' },
  { id: 'user-sam', name: 'Sam Scheduler', email: 'sam@example.com' },
]

const STORED = {
  meeting_id: 'meeting-1',
  title: 'Supplier sync',
  meeting_date: '2026-01-15',
  status: 'Indexed',
  created_at: '2026-11-02T10:00:00+11:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: ['ada@example.com', 'sam@example.com'],
}

function renderMeetings(routes = {}) {
  const answered = serveApi({
    'GET /api/meetings': { body: [] },
    'GET /api/users/directory': { body: DIRECTORY },
    ...routes,
  })
  render(
    <AuthContext.Provider value={AUTH}>
      <MemoryRouter initialEntries={['/meetings']}>
        <Routes>
          <Route path="/meetings" element={<Meetings />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
  return answered
}

/** Chooses a person in the single select and presses Add — no modifier keys anywhere. */
async function addPerson(id) {
  fireEvent.change(await screen.findByLabelText(TEXT.attendeeAddLabel), { target: { value: id } })
  fireEvent.click(screen.getByRole('button', { name: TEXT.attendeeAddButton }))
}

function recordedList() {
  return screen.getByRole('list', { name: TEXT.attendeeListLabel })
}

describe('usability finding 5: attendees are added with plain presses, not Ctrl+click', () => {
  it('records two people chosen one after the other, shows both, and sends both', async () => {
    const answered = renderMeetings({
      'POST /api/meetings': { status: 201, body: STORED },
    })

    await addPerson('user-ada')
    await addPerson('user-sam')

    // Both on the screen at once: the second choice did not undo the first.
    const list = recordedList()
    expect(within(list).getByText('Ada Admin (ada@example.com)')).toBeTruthy()
    expect(within(list).getByText('Sam Scheduler (sam@example.com)')).toBeTruthy()
    // Someone already added is not offered again.
    const select = screen.getByLabelText(TEXT.attendeeAddLabel)
    expect(within(select).queryByRole('option', { name: 'Ada Admin (ada@example.com)' })).toBeNull()
    expect(within(select).getByRole('option', { name: 'Erin Employee (erin@example.com)' })).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Meeting title'), { target: { value: 'Supplier sync' } })
    fireEvent.change(screen.getByLabelText('Meeting date'), { target: { value: '2026-01-15' } })
    fireEvent.change(screen.getByLabelText('Transcript'), {
      target: { value: 'Ada: the supplier review is due on Friday. Sam: noted, I will draft it.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))

    await waitFor(() => {
      const ingest = answered.find((request) => request.method === 'POST' && request.path === '/api/meetings')
      expect(ingest?.body.attendees).toEqual(['user-ada', 'user-sam'])
    })
  })

  it('gives each recorded person their own Remove, named for them, and announces the change', async () => {
    renderMeetings()

    await addPerson('user-ada')
    await addPerson('user-sam')
    fireEvent.click(
      screen.getByRole('button', { name: TEXT.attendeeRemoveLabel('Ada Admin (ada@example.com)') }),
    )

    expect(within(recordedList()).queryByText('Ada Admin (ada@example.com)')).toBeNull()
    expect(within(recordedList()).getByText('Sam Scheduler (sam@example.com)')).toBeTruthy()
    // The removal is announced in the words the list change showed, and the
    // removed person is offered again.
    expect(screen.getByText(TEXT.attendeeRemoved('Ada Admin (ada@example.com)')).getAttribute('role')).toBe('status')
    const select = screen.getByLabelText(TEXT.attendeeAddLabel)
    expect(within(select).getByRole('option', { name: 'Ada Admin (ada@example.com)' })).toBeTruthy()
  })

  it('offers no multiple-selection listbox anywhere on the form', async () => {
    renderMeetings()
    await screen.findByLabelText(TEXT.attendeeAddLabel)
    expect(document.querySelector('select[multiple]')).toBeNull()
  })
})
