/**
 * D-79's ingestion limit on the three screens that can meet it: FR-08's upload
 * queue and its retry, FR-09's transcript form, and FR-15's repository retry.
 *
 * One per-user budget covers `POST /api/documents`, `POST /api/meetings` and
 * `POST /api/documents/{id}/reprocess`, and past it each answers DRF's 429 with a
 * `Retry-After` in seconds, checked before the body is validated (docs/api-contract.md,
 * "Stage 5 item 5"). The rate and the sharing are pytest's. What these defend is
 * what only a screen can get right: that a 429 is not shown as the material being
 * wrong or as stored, that it says when uploading can resume, and that what the
 * user entered or queued is kept.
 *
 * The upload queue sends through `XMLHttpRequest` (src/api/client.js `upload()`),
 * which tests/fakeApi.js answers from the same table as `fetch`.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthContext } from '../src/auth/context.js'
import { DOCUMENT_STATUS, ROLES, TEXT, VALIDATION } from '../src/constants.js'
import DocumentRepository from '../src/pages/DocumentRepository.jsx'
import Meetings from '../src/pages/Meetings.jsx'
import Upload from '../src/pages/Upload.jsx'
import { serveApi } from './fakeApi.js'

const EMPLOYEE = {
  id: 'user-employee',
  name: 'Erin Employee',
  email: 'erin@example.com',
  role: ROLES.employee,
  created_at: '2026-09-12T10:00:00+10:00',
}

/** The signed-in session the screens read their role from. */
const AUTH = {
  user: EMPLOYEE,
  loading: false,
  login: async () => EMPLOYEE,
  register: async () => null,
  logout: async () => {},
  refresh: async () => EMPLOYEE,
}

/** DRF's rate 429, with the `Retry-After` the screens read. */
function throttled(seconds) {
  return {
    status: 429,
    body: { detail: `Request was throttled. Expected available in ${seconds} seconds.` },
    headers: { 'Retry-After': String(seconds) },
  }
}

/** The document object a 201 or a 422 carries. */
function storedDocument(docId, title, status) {
  return {
    doc_id: docId,
    title,
    file_type: 'pdf',
    status,
    uploaded_at: '2026-10-21T10:00:00+10:00',
    department: '',
    visible_to_roles: [ROLES.employee, ROLES.administrator],
    file_size_bytes: 16,
    uploaded_by: EMPLOYEE.email,
  }
}

function pdf(name) {
  return new File(['%PDF-1.4 sample'], name, { type: 'application/pdf' })
}

function renderAt(path, routes) {
  render(
    <AuthContext.Provider value={AUTH}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>{routes}</Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

function requests(answered, method, path) {
  return answered.filter((request) => request.method === method && request.path === path)
}

/* ---- FR-08 upload queue -------------------------------------------------- */

/** One queued file's row, found by its name. */
function row(name) {
  return screen.getByText(name, { selector: '.upload-row__name' }).closest('li')
}

function chip(name) {
  return row(name).querySelector('.upload-status')
}

/** Everything a row could say if the file were refused, invalid or failed. */
const REFUSALS = [
  VALIDATION.fileTypeUnsupported,
  VALIDATION.fileTooLarge,
  TEXT.uploadRejected,
  TEXT.uploadDuplicate,
  TEXT.processingFailed,
]

describe('D-79 on FR-08: a 429 in a multi-file upload', () => {
  it('stops the queue, and shows the 429\'d file and the file behind it as not stored and not invalid, saying when uploading can resume', async () => {
    // The first upload is stored; the second meets the limit; once the test lifts
    // the limit, every upload is stored.
    let sent = 0
    let lifted = false
    const answered = serveApi({
      'POST /api/documents': () => {
        sent += 1
        if (sent === 1 || lifted) {
          return { status: 201, body: storedDocument(`doc-${sent}`, `stored ${sent}`, DOCUMENT_STATUS.indexed) }
        }
        return throttled(720)
      },
    })
    renderAt('/upload', <Route path="/upload" element={<Upload />} />)

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('a.pdf'), pdf('b.pdf'), pdf('c.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 3 files' }))

    // c.pdf is the last row the queue updates, after the 429 on b.pdf.
    const limit = TEXT.uploadLimitReached('in 12 minutes')
    await waitFor(() => expect(row('c.pdf').textContent).toContain(limit))

    // The queue stopped at the 429: c.pdf was never sent.
    expect(requests(answered, 'POST', '/api/documents')).toHaveLength(2)
    expect(chip('a.pdf').textContent).toBe(DOCUMENT_STATUS.indexed)

    for (const name of ['b.pdf', 'c.pdf']) {
      expect(row(name).textContent).toContain(limit)
      expect(chip(name).textContent).toBe(TEXT.uploadLimitedStatus)
      // Not stored, so not shown with a stored status, and not failed or invalid.
      expect(chip(name).textContent).not.toBe(DOCUMENT_STATUS.indexed)
      expect(chip(name).textContent).not.toBe('Failed')
      expect(chip(name).classList.contains('upload-status--rejected')).toBe(false)
      expect(chip(name).classList.contains('upload-status--failed')).toBe(false)
      for (const refusal of REFUSALS) expect(row(name).textContent).not.toContain(refusal)
      // Still queued: its title can be edited, and nothing offers a reprocess.
      expect(within(row(name)).getByLabelText(`Title for ${name}`)).toBeTruthy()
      expect(within(row(name)).queryByRole('button', { name: TEXT.uploadRetry })).toBeNull()
    }
    expect(document.body.textContent).not.toContain('Request was throttled')
    expect(document.body.textContent).not.toContain('Please wait a minute')

    // Nothing was stored, so Upload sends both files again as uploads.
    const again = screen.getByRole('button', { name: 'Upload 2 files' })
    await waitFor(() => expect(again.disabled).toBe(false))
    lifted = true
    fireEvent.click(again)
    await waitFor(() => expect(chip('c.pdf').textContent).toBe(DOCUMENT_STATUS.indexed))
    expect(chip('b.pdf').textContent).toBe(DOCUMENT_STATUS.indexed)
    expect(requests(answered, 'POST', '/api/documents')).toHaveLength(4)
    expect(requests(answered, 'POST', '/api/documents').map((request) => request.body.get('title'))).toEqual([
      'a',
      'b',
      'b',
      'c',
    ])
  })
})

describe('D-79 on FR-08: a 429 on the queue\'s retry', () => {
  it('keeps the stored document at its status with the retry offered, and says when it can be tried again', async () => {
    const answered = serveApi({
      'POST /api/documents': {
        status: 422,
        body: storedDocument('doc-9', 'scan', DOCUMENT_STATUS.indexingFailed),
      },
      'POST /api/documents/doc-9/reprocess': throttled(30),
    })
    renderAt('/upload', <Route path="/upload" element={<Upload />} />)

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('scan.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))
    const retry = await within(row('scan.pdf')).findByRole('button', { name: TEXT.uploadRetry })
    await waitFor(() => expect(retry.disabled).toBe(false))
    fireEvent.click(retry)

    const limit = TEXT.reprocessLimitReached('in 30 seconds')
    await waitFor(() => expect(row('scan.pdf').textContent).toContain(limit))
    expect(chip('scan.pdf').textContent).toBe(DOCUMENT_STATUS.indexingFailed)
    expect(within(row('scan.pdf')).getByRole('button', { name: TEXT.uploadRetry })).toBeTruthy()
    expect(row('scan.pdf').textContent).not.toContain(TEXT.uploadIndexed)
    // A retry of a stored document re-runs it; the file is not sent again.
    expect(requests(answered, 'POST', '/api/documents')).toHaveLength(1)
    expect(requests(answered, 'POST', '/api/documents/doc-9/reprocess')).toHaveLength(1)
  })
})

/* ---- FR-09 transcript form ----------------------------------------------- */

describe('D-79 on FR-09: a 429 on meeting ingestion', () => {
  it('says the transcript was not stored and when it can be added, and keeps what was entered', async () => {
    const answered = serveApi({
      'GET /api/meetings': { body: [] },
      'GET /api/users/directory': { body: [] },
      'POST /api/meetings': throttled(3600),
    })
    renderAt('/meetings', <Route path="/meetings" element={<Meetings />} />)
    await screen.findByText(TEXT.noMeetings)

    const transcript = 'Alex: the supplier review is due on Friday.'
    fireEvent.change(screen.getByLabelText('Meeting title'), { target: { value: 'Supplier sync' } })
    fireEvent.change(screen.getByLabelText('Meeting date'), { target: { value: '2020-01-15' } })
    fireEvent.change(screen.getByLabelText('Transcript'), { target: { value: transcript } })
    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))

    const alert = (await screen.findByText('Could not add the transcript')).closest('[role="alert"]')
    expect(alert.textContent).toContain(TEXT.meetingLimitReached('in 60 minutes'))
    expect(document.body.textContent).not.toContain('Request was throttled')
    expect(document.body.textContent).not.toContain('Transcript stored')
    expect(document.body.textContent).not.toContain('Stored, but not indexed')
    expect(document.body.textContent).not.toContain(TEXT.meetingRejected)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Add transcript' }).disabled).toBe(false))
    expect(screen.getByLabelText('Meeting title').value).toBe('Supplier sync')
    expect(screen.getByLabelText('Meeting date').value).toBe('2020-01-15')
    expect(screen.getByLabelText('Transcript').value).toBe(transcript)
    expect(screen.getByLabelText('Transcript').getAttribute('aria-invalid')).not.toBe('true')
    // Nothing changed on the server, so the list is not re-read.
    expect(requests(answered, 'GET', '/api/meetings')).toHaveLength(1)
  })
})

/* ---- FR-15 repository retry ---------------------------------------------- */

describe('D-79 on FR-15: a 429 on the repository\'s retry', () => {
  it('leaves the row at its status with its retry, and says when it can be tried again', async () => {
    const FAILED = storedDocument('doc-7', 'Quarterly figures', DOCUMENT_STATUS.indexingFailed)
    const answered = serveApi({
      'GET /api/documents/browse': {
        body: {
          filters: { q: null, status: null, department: null, project: null, process: null, topic: null, sort: '-uploaded_at' },
          facets: { department: [], project: [], process: [], topic: [] },
          documents: [FAILED],
        },
      },
      'POST /api/documents/doc-7/reprocess': throttled(45),
    })
    renderAt('/documents', <Route path="/documents" element={<DocumentRepository />} />)

    const retry = await screen.findByRole('button', { name: TEXT.documentRetryLabel(FAILED.title) })
    fireEvent.click(retry)

    const alert = (await screen.findByText(TEXT.documentReprocessFailed)).closest('[role="alert"]')
    expect(alert.textContent).toContain(TEXT.reprocessLimitReached('in 45 seconds'))
    expect(document.body.textContent).not.toContain('Request was throttled')
    const tableRow = screen.getByRole('link', { name: FAILED.title }).closest('tr')
    expect(tableRow.textContent).toContain(DOCUMENT_STATUS.indexingFailed)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: TEXT.documentRetryLabel(FAILED.title) }).disabled).toBe(false),
    )
    // Nothing changed on the server, so the list is not re-read.
    expect(requests(answered, 'GET', '/api/documents/browse')).toHaveLength(1)
  })
})
