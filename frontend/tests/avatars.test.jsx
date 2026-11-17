/**
 * D-137: "Every signed-in user" sees profile pictures, "wherever users are listed:
 * role management, attendees, the header". The server puts `picture` on every user
 * object, on every directory entry, and on each of a meeting's `attendee_people`
 * (docs/api-contract.md, "Profile pictures"); these tests defend the screens that
 * list people showing it.
 *
 * - **The Avatar** shows the picture, and the person's initials where there is none
 *   or where its address is not the contract's own, `/api/users/<id>/picture` (AVA-1),
 *   or where it fails to load. Beside a name it is decoration: `alt=""`, and the
 *   initials `aria-hidden`, painted by the stylesheet so the text of what holds them
 *   stays the name (SC 1.1.1: decoration is hidden, and the name is the text).
 * - **The header**: the signed-in user's picture, in the link to their Profile page
 *   beside "Signed in as …", after every page and Administrator link.
 * - **Role management** (FR-05), **the attendee picker** (FR-09) and **a meeting's
 *   attendees** (FR-09's stored transcript, viewable in full).
 *
 * What is not: that the browser fetches the picture with the session cookie, which
 * jsdom does not do, and the server's scoping of `GET /api/users/{id}/picture`,
 * which is pytest's.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'
import Avatar from '../src/components/Avatar.jsx'
import { PROFILE_TEXT, ROLES, TEXT } from '../src/constants.js'
import { summaryRoute, summaryState } from './fakeApi.js'
import { ADMINISTRATOR, BOTH_ROLES, EMPLOYEE, primaryNavigationFor, renderApp, serveSignedIn } from './routeWalk.jsx'
import { hidingCauses, styleRules } from './stylesheets.js'

const picture = (id, version = '1794823200123456') => `/api/users/${id}/picture?v=${version}`

/** The picture an element holds: its image's address, or `initials:XY` where it shows initials. */
function shown(container) {
  const image = container.querySelector('img')
  if (image) return image.getAttribute('src')
  const initials = container.querySelector('.avatar--initials')
  return initials ? `initials:${initials.getAttribute('data-initials')}` : null
}

describe('the Avatar (D-137)', () => {
  it('shows the picture as decoration, initials where there is none, initials again if it fails to load, and a new address once replaced', () => {
    const { container, rerender } = render(<Avatar name="Erin Employee" picture={picture('user-erin')} />)
    const image = container.querySelector('img')
    expect(image.getAttribute('src')).toBe(picture('user-erin'))
    expect(image.getAttribute('alt')).toBe('')

    fireEvent.error(image)
    expect(container.querySelector('img')).toBeNull()
    const initials = container.querySelector('.avatar--initials')
    expect(initials.getAttribute('data-initials')).toBe('EE')
    expect(initials.getAttribute('aria-hidden')).toBe('true')
    // Painted by the stylesheet, so no text is added to what holds it.
    expect(initials.textContent).toBe('')

    // A replaced picture has a new address, and it is tried.
    rerender(<Avatar name="Erin Employee" picture={picture('user-erin', '1794823299000001')} />)
    expect(shown(container)).toBe(picture('user-erin', '1794823299000001'))
    // None at all: the initials.
    rerender(<Avatar name="Erin Employee" picture={null} />)
    expect(shown(container)).toBe('initials:EE')
  })

  it.each([
    ['Ada', 'A'],
    ['Mary Ann Smith', 'MS'],
    ['  jane   doe  ', 'JD'],
    ['Élodie Ünal', 'ÉÜ'],
    ['', ''],
  ])('initials for "%s" are "%s"', (name, initials) => {
    const { container } = render(<Avatar name={name} picture={null} />)
    expect(container.querySelector('.avatar--initials').getAttribute('data-initials')).toBe(initials)
  })

  it('is named by its label, and not hidden, only where it is given one', () => {
    const { container, rerender } = render(<Avatar name="Ada Admin" picture={picture('user-ada')} label="Ada Admin" />)
    expect(container.querySelector('img').getAttribute('alt')).toBe('Ada Admin')
    rerender(<Avatar name="Ada Admin" picture={null} label="Ada Admin" />)
    const initials = screen.getByRole('img', { name: 'Ada Admin' })
    expect(initials.getAttribute('aria-hidden')).toBeNull()
  })

  it('paints the initials from data-initials in Avatar.css, and no rule hides an avatar', () => {
    const painting = styleRules().filter((rule) => rule.selectors.includes('.avatar--initials::before'))
    expect(painting.flatMap((rule) => rule.declarations)).toContainEqual({
      property: 'content',
      value: 'attr(data-initials)',
      important: false,
    })
    const { container } = render(
      <p>
        <Avatar name="Erin Employee" picture={null} className="avatar--inline" />
        <Avatar name="Erin Employee" picture={picture('user-erin')} className="avatar--inline" />
      </p>,
    )
    const [initials, image] = container.querySelectorAll('.avatar')
    // aria-hidden is the decoration's, for assistive technology; nothing hides either from the eye.
    expect(hidingCauses(initials).filter((cause) => !cause.endsWith('is aria-hidden'))).toEqual([])
    expect(hidingCauses(image)).toEqual([])
  })
})

describe('AVA-1: the Avatar uses only the contract’s own picture address', () => {
  // Each is something the server never sends, and each shows the initials: the browser
  // fetches nothing, and no other site learns who is looking at the page.
  it.each([
    ['a javascript: address', 'javascript:alert(1)'],
    ['a protocol-relative address elsewhere', '//evil.example/api/users/user-erin/picture?v=1'],
    ['an absolute https: address', 'https://evil.example/api/users/user-erin/picture?v=1'],
    ['an absolute address on this origin', 'http://localhost/api/users/user-erin/picture?v=1'],
    ['a data: address', 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"/>'],
    ['another path on this origin', '/api/documents/doc-1/download'],
    ['a path that climbs out with ..', '/api/users/../documents/doc-1/download'],
    ['an id that hides a slash', '/api/users/a%2F..%2Fb/picture'],
    ['the route with more after it', '/api/users/user-erin/picture/../../x'],
    ['the route with a fragment', '/api/users/user-erin/picture#x'],
    ['the route after a space', ' /api/users/user-erin/picture'],
  ])('shows the initials, never the image, for %s', (_, address) => {
    const { container } = render(<Avatar name="Erin Employee" picture={address} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('.avatar--initials').getAttribute('data-initials')).toBe('EE')
  })

  it.each([
    ['with its version', '/api/users/user-erin/picture?v=1794823200123456'],
    ['without a query', '/api/users/user-erin/picture'],
    ['with an id that is a UUID', '/api/users/0b7c2a54-0000-4000-8000-000000000001/picture?v=1'],
  ])('shows the picture from the contract’s address %s', (_, address) => {
    const { container } = render(<Avatar name="Erin Employee" picture={address} />)
    expect(container.querySelector('img').getAttribute('src')).toBe(address)
  })

  it('lets no module but the component sheet draw a picture without the check', () => {
    // AvatarPicture draws an image from any address its caller gives it. Only the
    // component sheet may, for its sample: a user's picture goes through Avatar.
    const SRC = join(import.meta.dirname, '..', 'src')
    const modules = (dir) =>
      readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
        entry.isDirectory() ? modules(join(dir, entry.name)) : /\.jsx?$/.test(entry.name) ? [join(dir, entry.name)] : [],
      )
    const users = modules(SRC)
      .filter((file) => /\bAvatarPicture\b/.test(readFileSync(file, 'utf8')))
      .map((file) => relative(SRC, file).split('\\').join('/'))
      .sort()
    expect(users).toEqual(['components/Avatar.jsx', 'components/ComponentSheet.jsx'])
  })
})

describe('D-137: the header shows the signed-in user’s picture', () => {
  it.each(BOTH_ROLES)('in the link to the Profile page, beside "Signed in as …" and after every other link, as an $role', async (user) => {
    serveSignedIn({ ...user, picture: picture(user.id) }, {})
    renderApp('/upload')
    const navigation = await primaryNavigationFor(user)

    const link = within(navigation).getByRole('link', { name: PROFILE_TEXT.navLabel })
    expect(link.getAttribute('href')).toBe('/profile')
    expect(link.textContent).toBe(PROFILE_TEXT.navLabel)
    expect(shown(link)).toBe(picture(user.id))
    expect(link.querySelector('img').getAttribute('alt')).toBe('')
    // In the signed-in user's corner: after "Signed in as …", before Log out.
    const signedIn = within(navigation).getByText(`Signed in as ${user.name}`)
    expect(signedIn.nextElementSibling).toBe(link)
    expect(link.nextElementSibling).toBe(within(navigation).getByRole('button', { name: 'Log out' }))
    // Not among the pages, nor between the knowledge map and the Administrator's links.
    const names = within(navigation)
      .getAllByRole('link')
      .map((each) => each.textContent)
    expect(names.at(-1)).toBe(PROFILE_TEXT.navLabel)
    expect(names.filter((name) => name === PROFILE_TEXT.navLabel)).toHaveLength(1)
  })

  it('shows initials there for a user with no picture', async () => {
    serveSignedIn({ ...EMPLOYEE, picture: null }, {})
    renderApp('/upload')
    const navigation = await primaryNavigationFor(EMPLOYEE)
    expect(shown(within(navigation).getByRole('link', { name: PROFILE_TEXT.navLabel }))).toBe('initials:EE')
  })
})

describe('D-137 and FR-05: role management shows each user’s picture', () => {
  const JANE = {
    id: 'user-jane',
    name: 'Jane Doe',
    email: 'jane.doe@company.com',
    role: ROLES.employee,
    created_at: '2026-09-20T10:00:00+10:00',
    picture: picture('user-jane'),
  }

  it('beside each name, in the row header, which still reads as the name alone', async () => {
    const administrator = { ...ADMINISTRATOR, picture: picture(ADMINISTRATOR.id) }
    const erin = { ...EMPLOYEE, picture: null }
    serveSignedIn(administrator, {
      'GET /api/users': { body: [administrator, JANE, erin] },
      'GET /api/roles': {
        body: [
          { role_id: 'role-employee', name: ROLES.employee, description: 'Default role', permissions: [] },
          { role_id: 'role-administrator', name: ROLES.administrator, description: 'Full management', permissions: [] },
        ],
      },
    })
    renderApp('/admin/roles')
    await screen.findByLabelText(`Role for ${JANE.name}`)

    const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    const headers = rows.map((row) => within(row).getByRole('rowheader'))
    expect(headers.map((header) => header.textContent)).toEqual([administrator.name, JANE.name, erin.name])
    expect(headers.map((header) => shown(header))).toEqual([picture(ADMINISTRATOR.id), picture('user-jane'), 'initials:EE'])
    for (const header of headers) {
      const image = header.querySelector('img')
      if (image) expect(image.getAttribute('alt')).toBe('')
    }
    expect(screen.getByRole('rowheader', { name: JANE.name })).toBe(headers[1])
  })
})

describe('D-137 and FR-09: the attendee lists show each person’s picture', () => {
  const DIRECTORY = [
    { id: 'user-ada', name: 'Ada Admin', email: 'ada@example.com', picture: picture('user-ada') },
    { id: 'user-erin', name: 'Erin Employee', email: 'erin@example.com', picture: null },
    { id: 'user-sam', name: 'Sam Scheduler', email: 'sam@example.com', picture: null },
  ]

  it('the attendee picker shows each chosen person with their picture beside their name', async () => {
    serveSignedIn(EMPLOYEE, { 'GET /api/meetings': { body: [] }, 'GET /api/users/directory': { body: DIRECTORY } })
    renderApp('/meetings')
    for (const id of ['user-ada', 'user-sam']) {
      fireEvent.change(await screen.findByLabelText(TEXT.attendeeAddLabel), { target: { value: id } })
      fireEvent.click(screen.getByRole('button', { name: TEXT.attendeeAddButton }))
    }

    const list = screen.getByRole('list', { name: TEXT.attendeeListLabel })
    const entries = within(list).getAllByRole('listitem')
    expect(entries.map((entry) => within(entry).getByText(/\(.+@example\.com\)$/).textContent)).toEqual([
      'Ada Admin (ada@example.com)',
      'Sam Scheduler (sam@example.com)',
    ])
    expect(entries.map((entry) => shown(entry))).toEqual([picture('user-ada'), 'initials:SS'])
    expect(entries[0].querySelector('img').getAttribute('alt')).toBe('')
  })

  const MEETING = {
    meeting_id: 'meeting-1',
    title: 'Supplier sync',
    meeting_date: '2026-01-15',
    status: 'Indexed',
    created_at: '2026-11-02T10:00:00+11:00',
    visible_to_roles: [ROLES.employee, ROLES.administrator],
    attendees: ['sam@example.com', 'ada@example.com'],
    transcript_text: 'Ada: the supplier review is due on Friday.',
    can_delete: false,
  }

  async function openMeeting(meeting) {
    serveSignedIn(EMPLOYEE, {
      [`GET /api/meetings/${meeting.meeting_id}`]: { body: meeting },
      [`GET /api/meetings/${meeting.meeting_id}/summary`]: summaryRoute(summaryState()),
    })
    renderApp(`/meetings/${meeting.meeting_id}`)
    await screen.findByRole('heading', { level: 1, name: meeting.title })
    await screen.findByText(TEXT.summaryNone)
    const term = screen.getByText('Attendees', { selector: 'dt' })
    return term.nextElementSibling
  }

  it('a meeting’s attendees, from attendee_people in the order of attendees, each with their picture beside their name', async () => {
    const attendees = await openMeeting({
      ...MEETING,
      attendee_people: [
        { email: 'sam@example.com', name: 'Sam Scheduler', picture: null },
        { email: 'ada@example.com', name: 'Ada Admin', picture: picture('user-ada') },
      ],
    })

    const entries = within(attendees).getAllByRole('listitem')
    expect(entries.map((entry) => entry.textContent)).toEqual(['Sam Scheduler (sam@example.com)', 'Ada Admin (ada@example.com)'])
    expect(entries.map((entry) => shown(entry))).toEqual(['initials:SS', picture('user-ada')])
    expect(entries[1].querySelector('img').getAttribute('alt')).toBe('')
  })

  it('lists the addresses, as before, from a reply without attendee_people', async () => {
    const attendees = await openMeeting(MEETING)
    expect(attendees.textContent).toBe('sam@example.com, ada@example.com')
    expect(attendees.querySelector('.avatar')).toBeNull()
  })

  it('says none were recorded when attendee_people is empty', async () => {
    const attendees = await openMeeting({ ...MEETING, attendees: [], attendee_people: [] })
    expect(attendees.textContent).toBe('None recorded')
  })
})
