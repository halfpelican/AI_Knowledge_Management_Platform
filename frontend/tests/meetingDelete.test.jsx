/**
 * The meeting delete (D-99), rendered against a faked `GET /api/meetings`,
 * `GET /api/meetings/{id}` and `DELETE /api/meetings/{id}` (docs/api-contract.md,
 * "Meeting deletion"). It is not in the proposal; it mirrors FR-15's document
 * delete, whose tests are in tests/documentRepository.test.jsx, and these follow
 * them.
 *
 * Each test defends one clause only the interface can satisfy — whether the screen
 * offers the control, asks before it sends anything, sends the one request, lands
 * on the list with a confirmation, and reports a refusal in words. The scoped-first
 * 404, the 403 and what the delete removes are the server's and are tested in
 * pytest (apps/api/tests/test_meeting_delete.py); nothing here stands in for them.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { NETWORK_ERROR_STATUS, messageForStatus } from '../src/api/client.js'
import { AuthContext } from '../src/auth/context.js'
import { ROLES, TEXT } from '../src/constants.js'
import MeetingDetail from '../src/pages/MeetingDetail.jsx'
import Meetings from '../src/pages/Meetings.jsx'
import { serveApi } from './fakeApi.js'

/* ---- Fixtures, in the contract's shapes ---------------------------------- */

const ADMINISTRATOR = {
  id: 'user-administrator',
  name: 'Ada Administrator',
  email: 'ada@example.com',
  role: ROLES.administrator,
  created_at: '2026-09-12T10:00:00+10:00',
}

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

/** The signed-in session the meetings list reads its role from. */
function sessionOf(user) {
  return {
    user,
    loading: false,
    login: async () => user,
    register: async () => null,
    logout: async () => {},
    refresh: async () => user,
  }
}

/** The meeting object as the list returns it: no transcript, no `can_delete`. */
const PLANNING = {
  meeting_id: 'meeting-1',
  title: 'Q3 planning sync',
  meeting_date: '2026-07-28',
  status: 'Indexed',
  created_at: '2026-09-21T10:00:00+10:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: ['erin@example.com'],
}

const SUPPLIERS = {
  meeting_id: 'meeting-2',
  title: 'Supplier review',
  meeting_date: '2026-07-14',
  status: 'Indexed',
  created_at: '2026-09-20T10:00:00+10:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: [],
}

/** The detail object: the meeting object with `transcript_text`, and `can_delete` (D-99). */
function detailOf(meeting, overrides = {}) {
  return {
    ...meeting,
    transcript_text: 'Alex: the supplier review is due on Friday.\nSam: I will circulate the draft.',
    can_delete: false,
    ...overrides,
  }
}

/** What DRF sends with each refusal. The screen must never show it. */
const SERVER_403 = { detail: 'You do not have permission to perform this action.' }
const SERVER_404 = { detail: 'No Meeting matches the given query.' }

/* ---- Rendering ----------------------------------------------------------- */

/** The router's current location and its Back, as the probe below last saw them. */
const probe = { location: null, back: null }

/** Exposes the router's location and Back to the test, from inside the router. */
function HistoryProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  // A layout effect, not a passive one: it runs inside the commit that rendered this
  // location, before a `findBy…` waiting on that commit can resolve.
  useLayoutEffect(() => {
    probe.location = location
    probe.back = () => navigate(-1)
  })
  return null
}

/** The meetings list and the detail view at their real paths, with a history to go Back through. */
function renderMeetings(path, user = ADMINISTRATOR) {
  probe.location = null
  probe.back = null
  render(
    <AuthContext.Provider value={sessionOf(user)}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/meetings" element={<Meetings />} />
          <Route path="/meetings/:meetingId" element={<MeetingDetail />} />
        </Routes>
        <HistoryProbe />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
  return probe
}

/** The detail view at its path, for a meeting the fake API describes. */
async function renderDetail(detail, extraRoutes = {}, user = ADMINISTRATOR) {
  const answered = serveApi({ [`GET /api/meetings/${detail.meeting_id}`]: { body: detail }, ...extraRoutes })
  const probe = renderMeetings(`/meetings/${detail.meeting_id}`, user)
  await screen.findByRole('heading', { level: 1, name: detail.title })
  return { answered, probe }
}

/** Every DELETE the screen sent. */
function deletes(answered) {
  return answered.filter((request) => request.method === 'DELETE')
}

/** Every read of the meetings list. */
function listReads(answered) {
  return answered.filter((request) => request.method === 'GET' && request.path === '/api/meetings')
}

/** Any control on the screen whose words mention deleting. */
function deleteButtons() {
  return screen.queryAllByRole('button').filter((button) => /delete/i.test(button.textContent))
}

/**
 * A click as a browser makes one: the button takes focus, then is clicked.
 * `fireEvent.click` alone moves no focus, which leaves `document.activeElement`
 * on the body and makes every assertion about where focus goes meaningless.
 */
function press(element) {
  element.focus()
  fireEvent.click(element)
}

/** Opens the dialogue from the detail's control and confirms it. */
function confirmDeletion() {
  fireEvent.click(screen.getByRole('button', { name: TEXT.meetingDelete }))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: TEXT.meetingDelete }))
}

/**
 * The detail is still on screen, as a record and not as something deleted: its
 * heading and transcript are there, the address is still its own, and no
 * "was deleted" confirmation is anywhere.
 */
function expectStillOnRecord(meeting, probe) {
  expect(screen.getByRole('heading', { level: 1, name: meeting.title })).toBeTruthy()
  expect(screen.getByRole('region', { name: TEXT.transcriptHeading })).toBeTruthy()
  expect(probe.location.pathname).toBe(`/meetings/${meeting.meeting_id}`)
  expect(screen.queryByText(TEXT.meetingsDeleted(meeting.title))).toBeNull()
  expect(screen.queryByRole('dialog')).toBeNull()
}

/* ---- The control --------------------------------------------------------- */

describe('D-99 meeting deletion: offered only with manage_meetings, and only after confirmation', () => {
  it('offers the delete control to an Administrator, whose detail says can_delete, and the keyboard reaches it', async () => {
    await renderDetail(detailOf(PLANNING, { can_delete: true }))

    const control = screen.getByRole('button', { name: TEXT.meetingDelete })
    control.focus()
    expect(document.activeElement).toBe(control)
    // Offering it opens nothing and sends nothing.
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  // False is what an Employee's detail says. Absent is the list's meeting object,
  // which carries no `can_delete`, and the control fails closed on it.
  it.each([
    ['false', false],
    ['absent', undefined],
  ])('offers no delete control to an Employee, whose detail says can_delete is %s', async (_, canDelete) => {
    await renderDetail(detailOf(PLANNING, { can_delete: canDelete }), {}, EMPLOYEE)

    expect(screen.queryByRole('button', { name: TEXT.meetingDelete })).toBeNull()
    expect(deleteButtons()).toEqual([])
    expect(screen.queryByRole('dialog')).toBeNull()
    // The rest of the record is there: only the control is withheld.
    expect(screen.getByRole('region', { name: TEXT.transcriptHeading }).textContent).toContain('supplier review')
  })

  it('asks for confirmation, saying what goes, before sending anything, and Cancel sends no DELETE', async () => {
    const { answered } = await renderDetail(detailOf(PLANNING, { can_delete: true }), {
      [`DELETE /api/meetings/${PLANNING.meeting_id}`]: { status: 204 },
    })

    const control = screen.getByRole('button', { name: TEXT.meetingDelete })
    press(control)

    const dialog = screen.getByRole('dialog', { name: TEXT.meetingDeleteConfirm(PLANNING.title) })
    // The meeting's own words, not the document's: the meeting, its transcript and
    // its passages go, and it will not be found or answered from again.
    expect(dialog.textContent).toContain(TEXT.meetingDeleteBody)
    expect(TEXT.meetingDeleteBody).toMatch(/meeting, its transcript and its indexed passages/)
    // Opening the dialogue sends nothing.
    expect(deletes(answered)).toEqual([])

    fireEvent.click(within(dialog).getByRole('button', { name: TEXT.meetingDeleteCancel }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(deletes(answered)).toEqual([])
    // The record is still on screen, and focus is back on the control that opened it.
    expect(screen.getByRole('heading', { level: 1, name: PLANNING.title })).toBeTruthy()
    expect(document.activeElement).toBe(control)
  })

  it('sends exactly one DELETE on confirm, then returns to the meetings list with a confirmation', async () => {
    let deleted = false
    const answered = serveApi({
      'GET /api/meetings': () => ({ body: deleted ? [SUPPLIERS] : [PLANNING, SUPPLIERS] }),
      'GET /api/users/directory': { body: [] },
      [`GET /api/meetings/${PLANNING.meeting_id}`]: { body: detailOf(PLANNING, { can_delete: true }) },
      [`DELETE /api/meetings/${PLANNING.meeting_id}`]: () => {
        deleted = true
        return { status: 204 }
      },
    })
    const probe = renderMeetings('/meetings')
    fireEvent.click(await screen.findByRole('link', { name: PLANNING.title }))
    await screen.findByRole('heading', { level: 1, name: PLANNING.title })

    fireEvent.click(screen.getByRole('button', { name: TEXT.meetingDelete }))
    const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: TEXT.meetingDelete })
    // Pressed twice, as an impatient user does, and both presses inside one act, so
    // the second lands before the busy state has rendered. That is the case the
    // screen's own in-flight guard is for; once busy has rendered, the dialogue
    // ignores a press itself. Still one request.
    act(() => {
      confirm.click()
      confirm.click()
    })

    expect(await screen.findByText(TEXT.meetingsDeleted(PLANNING.title))).toBeTruthy()
    expect(deletes(answered)).toEqual([
      { method: 'DELETE', path: `/api/meetings/${PLANNING.meeting_id}`, search: '', body: undefined },
    ])
    expect(probe.location.pathname).toBe('/meetings')
    expect(screen.queryByRole('dialog')).toBeNull()

    // The list is read again and no longer names the meeting. Its request is sent by
    // an effect after the first commit, so it is waited for rather than read at once.
    await waitFor(() => expect(listReads(answered)).toHaveLength(2))
    expect(await screen.findByRole('link', { name: SUPPLIERS.title })).toBeTruthy()
    expect(screen.queryByRole('link', { name: PLANNING.title })).toBeNull()
    // Focus starts at the top of the list, under which the confirmation sits.
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: 'Meeting transcripts' })),
    )

    // Back does not return to the record that is gone: the delete replaced it in the
    // history, so the entry behind the list is the list the user started from.
    const keyBefore = probe.location.key
    act(() => probe.back())
    await waitFor(() => expect(probe.location.key).not.toBe(keyBefore))
    expect(probe.location.pathname).toBe('/meetings')
    // The detail's one read and the one DELETE, and no second read of a record that is gone.
    expect(answered.filter((request) => request.path === `/api/meetings/${PLANNING.meeting_id}`)).toHaveLength(2)
  })
})

/* ---- Failures ------------------------------------------------------------ */

describe('D-99 meeting deletion: a refusal is reported in words, and the meeting is not shown as deleted', () => {
  it('says so when the server refuses the delete with a 403, and withdraws the control', async () => {
    const { answered, probe } = await renderDetail(detailOf(PLANNING, { can_delete: true }), {
      [`DELETE /api/meetings/${PLANNING.meeting_id}`]: { status: 403, body: SERVER_403 },
    })

    confirmDeletion()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.meetingDeleteFailed)
    expect(alert.textContent).toContain(TEXT.meetingDeleteNotPermitted)
    expect(document.body.textContent).not.toContain(SERVER_403.detail)
    // The role does not hold the permission, whatever the detail said: the control goes.
    expect(screen.queryByRole('button', { name: TEXT.meetingDelete })).toBeNull()
    expectStillOnRecord(PLANNING, probe)
    expect(deletes(answered)).toHaveLength(1)
  })

  it('says it could not be found on a 404, in the words a 404 on opening it uses, and nothing more', async () => {
    // Already deleted, or narrowed out of the caller's scope since the detail loaded.
    // The server answers both alike, and so does the screen (CLAUDE.md §6, invariant 1).
    const { answered, probe } = await renderDetail(detailOf(PLANNING, { can_delete: true }), {
      [`DELETE /api/meetings/${PLANNING.meeting_id}`]: { status: 404, body: SERVER_404 },
    })

    confirmDeletion()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe(`${TEXT.meetingDeleteFailed}${TEXT.meetingNotFound}`)
    expect(document.body.textContent).not.toContain(SERVER_404.detail)
    expectStillOnRecord(PLANNING, probe)
    expect(deletes(answered)).toHaveLength(1)
  })

  it('says the server could not be reached when the request never arrives', async () => {
    const { answered, probe } = await renderDetail(detailOf(PLANNING, { can_delete: true }), {
      // Answered by rejecting, as `fetch` does when the network is down.
      [`DELETE /api/meetings/${PLANNING.meeting_id}`]: () => Promise.reject(new TypeError('Failed to fetch')),
    })

    confirmDeletion()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(TEXT.meetingDeleteFailed)
    expect(alert.textContent).toContain(messageForStatus(NETWORK_ERROR_STATUS))
    expect(document.body.textContent).not.toContain('Failed to fetch')
    expectStillOnRecord(PLANNING, probe)
    // Nothing said the role lacks the permission, so the control is still offered.
    expect(screen.getByRole('button', { name: TEXT.meetingDelete })).toBeTruthy()
    expect(deletes(answered)).toHaveLength(1)
  })
})
