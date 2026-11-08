/**
 * Usability findings 1 to 4 (docs/usability-findings.md), all on FR-08's drop
 * zone and the FR-09 form that shares it. Each was found by hand at Stage 3 and
 * passed every test then; each test below names the finding it closes.
 *
 * jsdom applies no stylesheet, so where a finding is about what is on the screen
 * the test reads the rule from src/ (tests/stylesheets.js) rather than trusting a
 * class name.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthContext } from '../src/auth/context.js'
import { DOCUMENT_STATUS, ROLES, TEXT } from '../src/constants.js'
import Meetings from '../src/pages/Meetings.jsx'
import Upload from '../src/pages/Upload.jsx'
import { heldResponse, serveApi } from './fakeApi.js'
import { tabTo } from './keyboard.js'
import { hidingCauses, resolve, rulesMatching, styleRules } from './stylesheets.js'

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

function pdf(name) {
  return new File(['%PDF-1.4 sample'], name, { type: 'application/pdf' })
}

function storedDocument(docId, title) {
  return {
    doc_id: docId,
    title,
    file_type: 'pdf',
    status: DOCUMENT_STATUS.indexed,
    uploaded_at: '2026-11-02T10:00:00+11:00',
    department: '',
    visible_to_roles: [ROLES.employee, ROLES.administrator],
    file_size_bytes: 16,
    uploaded_by: EMPLOYEE.email,
  }
}

function renderAt(path, element) {
  render(
    <AuthContext.Provider value={AUTH}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={path} element={element} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

/** The drop zone around the file input with this label. */
function zone(label = 'Choose files') {
  return screen.getByLabelText(label).closest('.dropzone')
}

/** The zone's own status line. */
function zoneStatus(label = 'Choose files') {
  return within(zone(label)).getByRole('status')
}

function queued(name) {
  return screen.queryByText(name, { selector: '.upload-row__name' })
}

/** A drag carrying files, as a browser reports one. */
function fileDrag(files) {
  return { dataTransfer: { files, types: ['Files'] } }
}

describe('usability finding 1: a drop is confirmed where it happened', () => {
  it('says in the zone, on the screen and in a live region, what a drop added, and keeps the page live region', async () => {
    serveApi({})
    renderAt('/upload', <Upload />)

    fireEvent.drop(zone(), fileDrag([pdf('policy.pdf'), new File(['MZ'], 'setup.exe')]))

    const status = zoneStatus()
    expect(status.textContent).toBe(TEXT.dropZoneAdded(['policy.pdf', 'setup.exe'], 1))
    expect(status.getAttribute('aria-live')).toBe('polite')
    // On the screen: nothing in the markup or the stylesheets hides it.
    expect(hidingCauses(status)).toEqual([])
    // Inside the zone, not further up the page where the queue is.
    expect(zone().contains(status)).toBe(true)

    // The page's own live region is kept as it was: hidden, polite, and announcing
    // the refused file in the words its row shows.
    const pageRegion = document.querySelector('.upload-page > p[role="status"]')
    expect(pageRegion.classList.contains('visually-hidden')).toBe(true)
    expect(pageRegion.getAttribute('aria-live')).toBe('polite')
    expect(pageRegion.textContent).toContain('setup.exe')
  })
})

describe('usability finding 2: the browser’s "No file chosen" no longer contradicts a choice', () => {
  it('hides the native input, shows its label as the control, and states the chosen file itself', async () => {
    serveApi({ 'GET /api/meetings': { body: [] }, 'GET /api/users/directory': { body: [] } })
    renderAt('/meetings', <Meetings />)
    fireEvent.click(await screen.findByLabelText(TEXT.meetingSourceFile))

    const input = screen.getByLabelText('Transcript file')
    const label = document.querySelector(`label[for="${input.id}"]`)
    // The native control, with its own label text, is off the screen; the label
    // standing in for it is on it.
    expect(hidingCauses(input).length).toBeGreaterThan(0)
    expect(hidingCauses(label)).toEqual([])
    expect(zoneStatus('Transcript file').textContent).toBe(TEXT.meetingFileNone)

    fireEvent.change(input, { target: { files: [new File(['minutes'], 'minutes.txt')] } })

    // The input's value is cleared so the same file can be chosen again, and the
    // zone still says which file is chosen.
    expect(input.value).toBe('')
    expect(zoneStatus('Transcript file').textContent).toBe(TEXT.meetingFileChosen('minutes.txt'))
  })

  it('draws the focus ring on the label while the hidden input has the keyboard focus', () => {
    serveApi({})
    renderAt('/upload', <Upload />)
    const input = screen.getByLabelText('Choose files')
    const label = document.querySelector(`label[for="${input.id}"]`)
    const ringRules = () =>
      rulesMatching(label).filter((rule) =>
        rule.declarations.some((d) => d.property === 'outline' && resolve(d.value).includes(resolve('var(--color-focus)'))),
      )

    expect(ringRules()).toEqual([])
    // Reached by Tab, as a keyboard user reaches it: jsdom decides :focus-visible
    // from the key events, as a browser does.
    tabTo(input)
    expect(ringRules().map((rule) => rule.selector)).toEqual(['.dropzone__input:focus-visible + .dropzone__choose'])
  })
})

describe('usability finding 3: the drop target is not a thin strip', () => {
  it('is given real height by its stylesheet', () => {
    const rule = styleRules().find((candidate) => candidate.selectors.includes('.dropzone'))
    const minHeight = rule.declarations.find((d) => d.property === 'min-height')
    // rem, at the browser's default 16px.
    const pixels = parseFloat(resolve(minHeight.value)) * 16
    expect(resolve(minHeight.value)).toMatch(/rem$/)
    expect(pixels).toBeGreaterThanOrEqual(128)
  })

  it('takes a file dropped anywhere on the page, lights up while one is dragged over it, and leaves other drags alone', () => {
    serveApi({})
    renderAt('/upload', <Upload />)
    const heading = screen.getByRole('heading', { level: 1 })

    // Dragging a file over the page, outside the zone, lights the zone up, and the
    // drag is claimed so the browser will not navigate to the file.
    expect(fireEvent.dragOver(heading, fileDrag([]))).toBe(false)
    expect(zone().classList.contains('dropzone--active')).toBe(true)

    // A near miss is the zone's drop, not the browser's navigation.
    expect(fireEvent.drop(heading, fileDrag([pdf('near-miss.pdf')]))).toBe(false)
    expect(queued('near-miss.pdf')).toBeTruthy()
    expect(zone().classList.contains('dropzone--active')).toBe(false)
    expect(zoneStatus().textContent).toBe(TEXT.dropZoneAdded(['near-miss.pdf'], 0))

    // A drag carrying text is not taken.
    expect(fireEvent.dragOver(heading, { dataTransfer: { files: [], types: ['text/plain'] } })).toBe(true)
  })
})

describe('usability finding 4: a drop while an upload is in flight is answered', () => {
  it('says why nothing can be added while the queue sends, answers a drop with a refusal, and recovers afterwards', async () => {
    const held = heldResponse()
    serveApi({ 'POST /api/documents': () => held.route() })
    renderAt('/upload', <Upload />)

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('first.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))

    await waitFor(() => expect(zoneStatus().textContent).toBe(TEXT.dropZoneBusy))
    expect(hidingCauses(zoneStatus())).toEqual([])

    // On the zone, and on the page outside it: refused out loud, and nothing added.
    fireEvent.drop(zone(), fileDrag([pdf('late.pdf')]))
    expect(zoneStatus().textContent).toBe(TEXT.dropZoneRefused)
    fireEvent.drop(screen.getByRole('heading', { level: 1 }), fileDrag([pdf('later.pdf')]))
    expect(zoneStatus().textContent).toBe(TEXT.dropZoneRefused)
    expect(queued('late.pdf')).toBeNull()
    expect(queued('later.pdf')).toBeNull()

    held.release({ status: 201, body: storedDocument('doc-1', 'first') })
    await waitFor(() => expect(screen.getByLabelText('Choose files').disabled).toBe(false))
    // The refusal was about the upload that has finished, so it goes.
    expect(zoneStatus().textContent).toBe('')
    fireEvent.drop(zone(), fileDrag([pdf('late.pdf')]))
    expect(queued('late.pdf')).toBeTruthy()
  })
})
