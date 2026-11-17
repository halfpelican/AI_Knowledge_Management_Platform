/**
 * #119's profile picture, wired to D-137's `POST` and `DELETE /api/users/me/picture`
 * (docs/api-contract.md, "FR-04 — account self-service", "Profile pictures").
 *
 * What is defended here, each a clause only the page can satisfy:
 *
 * - **The upload is the contract's**: one multipart part, `picture`. After it, and
 *   after a removal, the session's user is read again, so the header shows what the
 *   server now holds (D-137: pictures wherever users are listed, the header included).
 * - **Remove** is `DELETE /api/users/me/picture` for a saved picture. For a chosen
 *   picture not yet sent, it takes the choice away and sends nothing, as #119's did.
 * - **The client-side check** refuses a file over 5 MB, or one that is not a PNG, JPEG
 *   or WebP, before a byte is sent, naming what would do.
 * - **The server's refusals** are told in the contract's words for the 400, the 413
 *   and the 415, and in the page's for the rate's 429, never by the reply's `detail`.
 * - **`picture_busy`**: the server is busy, and Upload waits out its Retry-After before
 *   the same picture can be sent again.
 * - **The keyboard reaches the picker.** #119's file inputs were hidden by the
 *   stylesheet inside labels, so no key reached them. Two buttons open the one input,
 *   which is never a stop itself.
 * - **The copies** of the server's limits and texts this page holds are the server's
 *   and the contract's, read from apps/core/constants.py and docs/api-contract.md.
 *
 * What is not: whether the picker's buttons can be seen while focused, which needs
 * the stylesheets, and is tests/tabOrder.test.jsx's "profile" case; and the server's
 * decisions, which are pytest's.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import {
  MAX_PICTURE_BYTES,
  MAX_PICTURE_LABEL,
  MAX_PICTURE_PIXELS,
  PICTURE_FORMATS_LABEL,
  PICTURE_TYPES,
  PROFILE_TEXT,
} from '../src/constants.js'
import { PICTURE_BUSY_CODE } from '../src/api/profile.js'
import { serveApi } from './fakeApi.js'
import { tabThrough } from './keyboard.js'
import { EMPLOYEE, primaryNavigationFor, renderApp, requested, serveSignedIn } from './routeWalk.jsx'

const SAVED = '/api/users/user-employee/picture?v=1794823200123456'
const REPLACED = '/api/users/user-employee/picture?v=1794823299000001'

const REPOSITORY = join(import.meta.dirname, '..', '..')

/** A picture file of `type`, eight bytes long unless `size` says otherwise. */
function pictureFile(name = 'me.png', type = 'image/png', size = null) {
  const file = new File([new Uint8Array(8)], name, { type })
  if (size !== null) Object.defineProperty(file, 'size', { value: size })
  return file
}

function fileInput() {
  return document.querySelector('input[type="file"]')
}

function choose(file) {
  fireEvent.change(fileInput(), { target: { files: [file] } })
}

function uploadButton() {
  return screen.getByRole('button', { name: PROFILE_TEXT.uploadPicture })
}

/** The Profile link in the navigation, where the header shows the user's picture. */
function profileLink() {
  return within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: PROFILE_TEXT.navLabel })
}

function headerPicture() {
  return profileLink().querySelector('img')?.getAttribute('src') ?? null
}

function pictureRequests(answered) {
  return answered.filter((request) => request.path === '/api/users/me/picture')
}

function sessionReads(answered) {
  return answered.filter((request) => request.method === 'GET' && request.path === '/api/auth/me').length
}

async function openProfile(user) {
  renderApp('/profile')
  await screen.findByRole('heading', { level: 1, name: PROFILE_TEXT.heading })
  await primaryNavigationFor(user)
}

/** A server whose session check answers with whoever the picture routes last made the user. */
function serveChangingUser(start, routes) {
  const state = { user: start }
  const answered = serveApi({
    'GET /api/auth/me': () => ({ body: state.user }),
    ...Object.fromEntries(Object.entries(routes).map(([key, route]) => [key, () => route(state)])),
  })
  return answered
}

describe('D-137: the picture goes to the server, and the header shows what it now holds', () => {
  it('sends the chosen picture as the one multipart part "picture", then reads the session again, so the header shows it', async () => {
    const answered = serveChangingUser(
      { ...EMPLOYEE, picture: null },
      {
        'POST /api/users/me/picture': (state) => {
          state.user = { ...EMPLOYEE, picture: REPLACED }
          return { body: state.user }
        },
      },
    )
    await openProfile(EMPLOYEE)
    expect(headerPicture()).toBeNull()
    expect(uploadButton().disabled).toBe(true)

    const file = pictureFile('me.png')
    choose(file)
    // The form's button names the file, as #119's label did.
    expect(screen.getByRole('button', { name: PROFILE_TEXT.choosePictureChosen('me.png') }).textContent).toBe('me.png')
    expect(uploadButton().disabled).toBe(false)
    fireEvent.click(uploadButton())

    await waitFor(() => expect(headerPicture()).toBe(REPLACED))
    const sent = pictureRequests(answered)
    expect(sent.map((request) => request.method)).toEqual(['POST'])
    expect([...sent[0].body.keys()]).toEqual(['picture'])
    const part = sent[0].body.get('picture')
    expect([part.name, part.type, part.size]).toEqual(['me.png', 'image/png', 8])
    // The session check on arrival, and the read after the upload.
    expect(sessionReads(answered)).toBe(2)
    expect(await screen.findByText(PROFILE_TEXT.pictureUpdated)).toBeTruthy()
    // The page's own picture is the saved one now, and nothing is left chosen.
    expect(document.querySelector('.profile-avatar img').getAttribute('src')).toBe(REPLACED)
    expect(uploadButton().disabled).toBe(true)
  })

  it('removes a saved picture with DELETE /api/users/me/picture, then reads the session again, so the header shows initials', async () => {
    const answered = serveChangingUser(
      { ...EMPLOYEE, picture: SAVED },
      {
        'DELETE /api/users/me/picture': (state) => {
          state.user = { ...EMPLOYEE, picture: null }
          return { body: state.user }
        },
      },
    )
    await openProfile(EMPLOYEE)
    expect(headerPicture()).toBe(SAVED)

    fireEvent.click(screen.getByRole('button', { name: PROFILE_TEXT.removeSavedLabel }))

    await waitFor(() => expect(headerPicture()).toBeNull())
    expect(profileLink().querySelector('.avatar--initials').getAttribute('data-initials')).toBe('EE')
    expect(pictureRequests(answered).map((request) => [request.method, request.body])).toEqual([['DELETE', undefined]])
    expect(sessionReads(answered)).toBe(2)
    expect(await screen.findByText(PROFILE_TEXT.pictureRemoved)).toBeTruthy()
    // Nothing is left to remove.
    expect(screen.getByRole('button', { name: PROFILE_TEXT.removeSavedLabel }).disabled).toBe(true)
  })

  it('takes a chosen picture away with Remove, as #119’s did, and sends nothing', async () => {
    const answered = serveSignedIn({ ...EMPLOYEE, picture: SAVED }, {})
    await openProfile(EMPLOYEE)
    choose(pictureFile('me.png'))
    const remove = screen.getByRole('button', { name: PROFILE_TEXT.removeChosenLabel })
    expect(remove.textContent).toBe(PROFILE_TEXT.removePicture)

    fireEvent.click(remove)

    expect(screen.getByRole('button', { name: PROFILE_TEXT.choosePicture })).toBeTruthy()
    expect(uploadButton().disabled).toBe(true)
    // The saved picture is still offered for removal, and it is still the header's.
    expect(screen.getByRole('button', { name: PROFILE_TEXT.removeSavedLabel }).disabled).toBe(false)
    expect(headerPicture()).toBe(SAVED)
    expect(requested(answered)).toEqual(['GET /api/auth/me'])
  })
})

describe('D-137: a file the page will not send', () => {
  it.each([
    ['a GIF', pictureFile('cat.gif', 'image/gif'), PROFILE_TEXT.pictureTypeUnsupported],
    ['an SVG', pictureFile('logo.svg', 'image/svg+xml'), PROFILE_TEXT.pictureTypeUnsupported],
    ['a .gif with no type', pictureFile('cat.gif', ''), PROFILE_TEXT.pictureTypeUnsupported],
    ['a PNG one byte over 5 MB', pictureFile('big.png', 'image/png', MAX_PICTURE_BYTES + 1), PROFILE_TEXT.pictureTooLarge],
  ])('refuses %s before sending anything, and says what would do', async (_, file, message) => {
    const answered = serveSignedIn(EMPLOYEE, {})
    await openProfile(EMPLOYEE)

    choose(file)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe(`${PROFILE_TEXT.pictureUploadFailed}${message}`)
    expect(uploadButton().disabled).toBe(true)
    expect(screen.getByRole('button', { name: PROFILE_TEXT.choosePicture })).toBeTruthy()
    expect(requested(answered)).toEqual(['GET /api/auth/me'])
  })

  it('names the accepted formats and the ceiling in its refusals', () => {
    expect(PROFILE_TEXT.pictureTypeUnsupported).toBe('File type not supported. Accepted formats: PNG, JPEG, WebP.')
    expect(PROFILE_TEXT.pictureTooLarge).toBe('Picture exceeds the maximum permitted size of 5 MB.')
    expect(PICTURE_FORMATS_LABEL).toBe('PNG, JPEG, WebP')
  })

  it.each([
    ['a PNG of exactly 5 MB', pictureFile('edge.png', 'image/png', MAX_PICTURE_BYTES)],
    ['a JPEG', pictureFile('me.jpg', 'image/jpeg')],
    ['a WebP', pictureFile('me.webp', 'image/webp')],
    ['a .webp with no type', pictureFile('me.webp', '')],
  ])('accepts %s and offers to upload it', async (_, file) => {
    serveSignedIn(EMPLOYEE, {})
    await openProfile(EMPLOYEE)
    expect(fileInput().getAttribute('accept')).toBe('image/png,image/jpeg,image/webp')

    choose(file)

    expect(screen.queryByRole('alert')).toBeNull()
    expect(uploadButton().disabled).toBe(false)
  })
})

describe('D-137: what the server refuses, in the contract’s words, never its own', () => {
  it.each([
    { status: 400, body: { picture: ['SERVER: No picture.'] }, headers: {}, message: PROFILE_TEXT.pictureNotSubmitted },
    { status: 413, body: { detail: 'SERVER: too many pixels' }, headers: {}, message: PROFILE_TEXT.pictureTooManyPixels },
    { status: 415, body: { detail: 'SERVER: not a picture' }, headers: {}, message: PROFILE_TEXT.pictureUnsupported },
    {
      status: 429,
      body: { detail: 'SERVER: Request was throttled. Expected available in 1800 seconds.' },
      headers: { 'Retry-After': '1800' },
      message: PROFILE_TEXT.pictureRateLimited('in 30 minutes'),
    },
  ])('a $status shows its own message, and keeps the picture chosen to send again', async ({ status, body, headers, message }) => {
    const answered = serveSignedIn(EMPLOYEE, { 'POST /api/users/me/picture': { status, body, headers } })
    await openProfile(EMPLOYEE)
    choose(pictureFile('me.png'))
    fireEvent.click(uploadButton())

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe(`${PROFILE_TEXT.pictureUploadFailed}${message}`)
    expect(alert.textContent).not.toContain('SERVER')
    // Nothing was stored, so the session is not read again and the picture waits.
    await waitFor(() => expect(uploadButton().disabled).toBe(false))
    expect(screen.getByRole('button', { name: PROFILE_TEXT.choosePictureChosen('me.png') })).toBeTruthy()
    expect(sessionReads(answered)).toBe(1)
    expect(headerPicture()).toBeNull()
  })

  it('a picture_busy 429 says the server is busy, holds Upload back for its Retry-After, then the same picture can be sent', async () => {
    const answered = serveChangingUser(
      { ...EMPLOYEE, picture: null },
      {
        'POST /api/users/me/picture': (state) => {
          if (pictureRequests(answered).length === 1) {
            return {
              status: 429,
              body: { detail: 'SERVER: busy', code: PICTURE_BUSY_CODE },
              headers: { 'Retry-After': '1' },
            }
          }
          state.user = { ...EMPLOYEE, picture: REPLACED }
          return { body: state.user }
        },
      },
    )
    await openProfile(EMPLOYEE)
    choose(pictureFile('me.png'))
    fireEvent.click(uploadButton())

    const sentence = await screen.findByText(PROFILE_TEXT.pictureBusy('in 1 second'))
    const notice = sentence.closest('[role="status"]')
    expect(notice, 'information, not an alert: nothing the user did').toBeTruthy()
    expect(notice.textContent).toContain(PROFILE_TEXT.pictureBusyTitle)
    expect(notice.textContent).not.toContain('SERVER')
    // Held back until the Retry-After has passed: pressed, it sends nothing.
    await waitFor(() => expect(uploadButton().textContent).toBe(PROFILE_TEXT.uploadPicture))
    expect(uploadButton().disabled).toBe(true)
    fireEvent.submit(uploadButton().closest('form'))
    expect(pictureRequests(answered)).toHaveLength(1)

    await waitFor(() => expect(uploadButton().disabled).toBe(false), { timeout: 3000 })
    fireEvent.click(uploadButton())
    await waitFor(() => expect(headerPicture()).toBe(REPLACED))
    expect(pictureRequests(answered).map((request) => request.body.get('picture').name)).toEqual(['me.png', 'me.png'])
  })
})

describe('D-137 and #119: the keyboard reaches the picture picker', () => {
  it('opens the one file input from two buttons Tab reaches, "Change picture" and "Choose a picture", and the input is never a stop', async () => {
    serveSignedIn(EMPLOYEE, {})
    await openProfile(EMPLOYEE)
    const input = fileInput()
    expect(document.querySelectorAll('input[type="file"]')).toHaveLength(1)
    const opened = vi.spyOn(input, 'click').mockImplementation(() => {})

    const stops = tabThrough()
    expect(stops).not.toContain(input)
    const change = screen.getByRole('button', { name: PROFILE_TEXT.changePicture })
    const chooser = screen.getByRole('button', { name: PROFILE_TEXT.choosePicture })
    expect(stops).toContain(change)
    expect(stops).toContain(chooser)
    expect(stops.indexOf(change)).toBeLessThan(stops.indexOf(chooser))

    // A key press on a focused button is its click.
    fireEvent.click(change)
    expect(opened).toHaveBeenCalledTimes(1)
    fireEvent.click(chooser)
    expect(opened).toHaveBeenCalledTimes(2)
    opened.mockRestore()
  })
})

describe('the page’s copies of the server’s limits and of the contract’s texts', () => {
  const constants = readFileSync(join(REPOSITORY, 'apps', 'core', 'constants.py'), 'utf8')

  /** A Python constant written as whole numbers multiplied, `5 * 1024 * 1024`, or `25_000_000`. */
  function pythonNumber(name) {
    const match = constants.match(new RegExp(`^${name} = ([\\d_ *]+?)\\s*(?:#.*)?$`, 'm'))
    if (!match) throw new Error(`${name} not found in apps/core/constants.py`)
    return match[1].split('*').reduce((product, factor) => product * Number(factor.trim().replaceAll('_', '')), 1)
  }

  it('holds the size, the pixel ceiling and the formats to apps/core/constants.py', () => {
    const bytes = pythonNumber('MAX_PICTURE_BYTES')
    expect(MAX_PICTURE_BYTES).toBe(bytes)
    expect(MAX_PICTURE_LABEL).toBe(`${bytes / (1024 * 1024)} MB`)
    expect(MAX_PICTURE_PIXELS).toBe(pythonNumber('MAX_PICTURE_PIXELS'))
    const formats = constants.match(/^PICTURE_FORMATS = \(([^)]*)\)/m)
    expect(formats, 'PICTURE_FORMATS in apps/core/constants.py').not.toBeNull()
    const named = [...formats[1].matchAll(/"([A-Z]+)"/g)].map((match) => match[1])
    expect(named.length).toBeGreaterThan(0)
    expect(PICTURE_TYPES).toEqual(named.map((format) => `image/${format.toLowerCase()}`))
  })

  it('shows the contract’s own text for the picture’s refusals, for picture_busy and for the change’s 200', () => {
    const contract = readFileSync(join(REPOSITORY, 'docs', 'api-contract.md'), 'utf8')
    for (const text of [
      PROFILE_TEXT.pictureNotSubmitted,
      PROFILE_TEXT.pictureTooLarge,
      PROFILE_TEXT.pictureTooManyPixels,
      PROFILE_TEXT.pictureUnsupported,
      // Its Retry-After is put where the contract says "in a few seconds".
      PROFILE_TEXT.pictureBusy('in a few seconds'),
      PROFILE_TEXT.passwordChanged,
    ]) {
      expect(contract, text).toContain(`"${text}"`)
    }
  })
})
