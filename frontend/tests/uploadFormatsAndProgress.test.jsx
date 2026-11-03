/**
 * FR-08's upload area: two clauses only the interface can satisfy.
 *
 * - "Unsupported formats are rejected immediately client-side with a message (E.g.,
 *   File type not supported. Accepted formats: PDF, DOCX, XLSX)." The formats are the
 *   four D-15 settles, not the six FR-08's upload area names; DOC and XLS are refused.
 * - "Each file shows a progress indicator and an individual progress bar during
 *   upload."
 *
 * The client's format check is a convenience and not a control. The server decides on
 * the file's signature (pytest's), and a file the client let through on its name is
 * shown the server's refusal against its own row, which the third test asserts.
 * That the client's list equals the server's is
 * apps/api/tests/test_front_end_constants_agreement.py.
 *
 * The queue sends through `XMLHttpRequest` (src/api/client.js `upload()`), which
 * tests/fakeApi.js answers from the same table as `fetch`. That fake reports a whole
 * body sent at once, so the progress test also keeps each request the screen makes,
 * to report part of a body as a browser would.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../src/auth/context.js'
import { DOCUMENT_STATUS, ROLES } from '../src/constants.js'
import Upload from '../src/pages/Upload.jsx'
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

/** FR-08's message with D-15's four formats, written out so a change to it fails here. */
const UNSUPPORTED = 'File type not supported. Accepted formats: PDF, DOCX, XLSX, TXT.'

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

function pdf(name) {
  return new File(['%PDF-1.4 sample'], name, { type: 'application/pdf' })
}

function renderUpload() {
  render(
    <AuthContext.Provider value={AUTH}>
      <MemoryRouter initialEntries={['/upload']}>
        <Routes>
          <Route path="/upload" element={<Upload />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

function choose(files) {
  fireEvent.change(screen.getByLabelText('Choose files'), { target: { files } })
}

/** One queued file's row, found by its name. */
function row(name) {
  return screen.getByText(name, { selector: '.upload-row__name' }).closest('li')
}

function chip(name) {
  return row(name).querySelector('.upload-status')
}

/**
 * Every `XMLHttpRequest` the screen constructs from here on, in order. A subclass of
 * the one tests/fakeApi.js installed, so each request is still answered or refused
 * from the same table; this only keeps a handle on it.
 */
function keepUploadRequests() {
  const made = []
  const Served = globalThis.XMLHttpRequest
  vi.stubGlobal(
    'XMLHttpRequest',
    class extends Served {
      constructor() {
        super()
        made.push(this)
      }
    },
  )
  return made
}

describe('FR-08: an unsupported format is refused before anything is sent', () => {
  it('refuses a file whose extension is not one of the four the moment it is chosen or dropped, naming the four, and queues the four it accepts', async () => {
    // Nothing answers the upload route, so a refused file that was sent fails the test.
    const answered = serveApi({})
    renderUpload()

    const input = screen.getByLabelText('Choose files')
    expect(input.getAttribute('accept')).toBe('.pdf,.docx,.xlsx,.txt')

    choose([
      pdf('policy.pdf'),
      new File(['PK'], 'contract.docx'),
      new File(['PK'], 'budget.xlsx'),
      new File(['minutes'], 'notes.txt'),
      new File(['\xD0\xCF'], 'legacy.doc'),
      new File(['\xD0\xCF'], 'legacy.xls'),
      new File(['MZ'], 'macro.exe'),
      new File(['plain'], 'README'),
    ])

    // Refused at once, before Upload is pressed: the reason against the file, and no
    // title to fill in for a file that will not be sent.
    for (const name of ['legacy.doc', 'legacy.xls', 'macro.exe', 'README']) {
      expect(chip(name).textContent).toBe('Not uploaded')
      expect(row(name).querySelector('.upload-row__message').textContent).toBe(UNSUPPORTED)
      expect(within(row(name)).queryByLabelText(`Title for ${name}`)).toBeNull()
    }
    for (const name of ['policy.pdf', 'contract.docx', 'budget.xlsx', 'notes.txt']) {
      expect(chip(name).textContent).toBe('Ready to upload')
      expect(row(name).textContent).not.toContain(UNSUPPORTED)
      expect(within(row(name)).getByLabelText(`Title for ${name}`)).toBeTruthy()
    }
    expect(screen.getByRole('button', { name: 'Upload 4 files' })).toBeTruthy()

    // A dropped file never meets the picker's `accept`, so the screen's own check is
    // the only one it gets.
    const dropZone = input.closest('.dropzone')
    fireEvent.drop(dropZone, { dataTransfer: { files: [new File(['MZ'], 'setup.exe'), pdf('handbook.pdf')] } })
    expect(chip('setup.exe').textContent).toBe('Not uploaded')
    expect(row('setup.exe').textContent).toContain(UNSUPPORTED)
    expect(chip('handbook.pdf').textContent).toBe('Ready to upload')
    expect(screen.getByRole('button', { name: 'Upload 5 files' })).toBeTruthy()

    expect(answered).toEqual([])
  })

  it("sends a file the client accepts on its name, and shows the server's signature refusal against its row", async () => {
    // A PE executable renamed .pdf: the extension is a claim, the signature the evidence.
    const answered = serveApi({ 'POST /api/documents': { status: 415, body: { detail: UNSUPPORTED } } })
    renderUpload()

    choose([new File(['MZ\x90\x00'], 'disguised.pdf'), new File(['MZ'], 'plain.exe')])
    expect(chip('disguised.pdf').textContent).toBe('Ready to upload')
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))

    await waitFor(() => expect(chip('disguised.pdf').textContent).toBe('Failed'))
    expect(row('disguised.pdf').querySelector('.upload-row__message').textContent).toBe(UNSUPPORTED)
    // The format will not change on a second press, so none is offered.
    expect(within(row('disguised.pdf')).queryByRole('button', { name: 'Try again' })).toBeNull()
    // Only the file the client let through was sent.
    expect(answered.map((request) => request.body.get('file').name)).toEqual(['disguised.pdf'])
  })
})

describe('FR-08: each file its own progress bar', () => {
  it('gives the file being sent its own bar while its bytes go, then a processing indicator until the server answers, and none once it has', async () => {
    const first = heldResponse()
    const second = heldResponse()
    let sent = 0
    const answered = serveApi({
      'POST /api/documents': () => {
        sent += 1
        return sent === 1 ? first.route() : second.route()
      },
    })
    const requests = keepUploadRequests()
    renderUpload()

    choose([pdf('a.pdf'), pdf('b.pdf')])
    expect(screen.queryAllByRole('progressbar')).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Upload 2 files' }))

    // a.pdf's transfer has begun and nothing has been reported yet: a determinate bar
    // at 0%, named for its file. b.pdf waits its turn and has none.
    const transfer = within(row('a.pdf')).getByRole('progressbar', { name: 'Upload progress for a.pdf' })
    expect(transfer.getAttribute('aria-valuenow')).toBe('0')
    expect(chip('a.pdf').textContent).toBe('Uploading')
    expect(within(row('b.pdf')).queryByRole('progressbar')).toBeNull()

    // The browser reports three tenths of the body sent.
    act(() => requests[0].upload.emit('progress', { lengthComputable: true, loaded: 3, total: 10 }))
    expect(transfer.getAttribute('aria-valuenow')).toBe('30')
    expect(row('a.pdf').textContent).toContain('30%')

    // The last byte has gone and the server is extracting, chunking and embedding:
    // the bar has no value to report, and says what is happening instead.
    const processing = await within(row('a.pdf')).findByRole('progressbar', { name: 'Processing a.pdf' })
    expect(processing.getAttribute('aria-valuenow')).toBeNull()
    expect(processing.getAttribute('aria-valuetext')).toBe('Processing…')
    expect(chip('a.pdf').textContent).toBe('Processing…')
    expect(within(row('b.pdf')).queryByRole('progressbar')).toBeNull()

    first.release({ status: 201, body: storedDocument('doc-a', 'a') })

    // a.pdf is indexed and its bar is gone; b.pdf now has a bar of its own.
    await within(row('b.pdf')).findByRole('progressbar', { name: 'Processing b.pdf' })
    expect(chip('a.pdf').textContent).toBe(DOCUMENT_STATUS.indexed)
    expect(within(row('a.pdf')).queryByRole('progressbar')).toBeNull()
    expect(screen.getAllByRole('progressbar')).toHaveLength(1)

    // A refusal after the transfer withdraws the bar too, and says why against the file.
    second.release({ status: 413, body: { detail: 'File exceeds the maximum permitted size of 50 MB.' } })
    await waitFor(() => expect(chip('b.pdf').textContent).toBe('Failed'))
    expect(row('b.pdf').querySelector('.upload-row__message').textContent).toBe(
      'File is larger than 50 MB. Choose a smaller file.',
    )
    expect(screen.queryAllByRole('progressbar')).toHaveLength(0)
    expect(requests).toHaveLength(2)
    expect(answered).toHaveLength(2)
  })
})
