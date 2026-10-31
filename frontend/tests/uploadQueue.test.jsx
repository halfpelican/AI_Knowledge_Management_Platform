/**
 * FR-08's upload queue: what a row offers while the queue runs, and after its retry.
 *
 * The queue sends the rows as they were when Upload was pressed, one at a time
 * (src/pages/Upload.jsx). So a row still waiting to be sent is held until the queue
 * finishes: an edit to its title would not reach the request, and a removal would
 * not stop it. A removed file that uploads anyway is stored and indexed, and an
 * Employee cannot delete it afterwards, because deletion is Administrator-only
 * (D-73). These were found while item 6 built D-85's screens, and fixed before the
 * measured run.
 *
 * The queue sends through `XMLHttpRequest` (src/api/client.js `upload()`), which
 * tests/fakeApi.js answers from the same table as `fetch`.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthContext } from '../src/auth/context.js'
import { DOCUMENT_STATUS, ROLES, TEXT } from '../src/constants.js'
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

/** The document object a 201 or a 422 carries. */
function storedDocument(docId, title, status) {
  return {
    doc_id: docId,
    title,
    file_type: 'pdf',
    status,
    uploaded_at: '2026-10-28T10:00:00+11:00',
    department: '',
    visible_to_roles: [ROLES.employee, ROLES.administrator],
    file_size_bytes: 16,
    uploaded_by: EMPLOYEE.email,
  }
}

/** DRF's rate 429, with the `Retry-After` the screen reads. */
function throttled(seconds) {
  return {
    status: 429,
    body: { detail: `Request was throttled. Expected available in ${seconds} seconds.` },
    headers: { 'Retry-After': String(seconds) },
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

function titleOf(name) {
  return within(row(name)).getByLabelText(`Title for ${name}`)
}

function removeOf(name) {
  return within(row(name)).getByRole('button', { name: `${TEXT.uploadRemove} ${name}` })
}

function uploads(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/documents')
}

describe('FR-08: a queued file while the queue runs', () => {
  it("holds a queued file's title and Remove until the queue finishes, then an edit and a removal both take effect", async () => {
    // a.pdf is held on the server. b.pdf then meets the rate limit, so the queue
    // stops with b.pdf and c.pdf still queued, and the test can act on both.
    const first = heldResponse()
    let sent = 0
    const answered = serveApi({
      'POST /api/documents': () => {
        sent += 1
        if (sent === 1) return first.route()
        if (sent === 2) return throttled(60)
        return { status: 201, body: storedDocument(`doc-${sent}`, `stored ${sent}`, DOCUMENT_STATUS.indexed) }
      },
    })
    renderUpload()

    // macro.exe is refused client-side and never queued.
    choose([pdf('a.pdf'), pdf('b.pdf'), pdf('c.pdf'), new File(['MZ'], 'macro.exe')])
    fireEvent.click(screen.getByRole('button', { name: 'Upload 3 files' }))
    await waitFor(() => expect(uploads(answered)).toHaveLength(1))

    // While a.pdf is with the server, the files still to be sent are held.
    for (const name of ['b.pdf', 'c.pdf']) {
      await waitFor(() => expect(titleOf(name).disabled).toBe(true))
      expect(removeOf(name).disabled).toBe(true)
    }
    // A row the queue never held keeps its action.
    expect(removeOf('macro.exe').disabled).toBe(false)

    first.release({ status: 201, body: storedDocument('doc-1', 'a', DOCUMENT_STATUS.indexed) })
    await waitFor(() => expect(row('c.pdf').textContent).toContain(TEXT.uploadLimitReached('in 1 minute')))

    // The queue has finished, so the two still queued are given back their actions.
    for (const name of ['b.pdf', 'c.pdf']) {
      await waitFor(() => expect(titleOf(name).disabled).toBe(false))
      expect(removeOf(name).disabled).toBe(false)
    }

    // An edit and a removal made now are what the next Upload sends.
    fireEvent.change(titleOf('b.pdf'), { target: { value: 'Supplier contract' } })
    fireEvent.click(removeOf('c.pdf'))
    expect(screen.queryByText('c.pdf', { selector: '.upload-row__name' })).toBeNull()
    const again = screen.getByRole('button', { name: 'Upload 1 file' })
    await waitFor(() => expect(again.disabled).toBe(false))
    fireEvent.click(again)
    await waitFor(() => expect(chip('b.pdf').textContent).toBe(DOCUMENT_STATUS.indexed))

    // b.pdf went once under its old title, which met the limit, and once under the
    // new one. c.pdf was never sent.
    expect(uploads(answered).map((request) => request.body.get('title'))).toEqual(['a', 'b', 'Supplier contract'])
  })
})

describe("FR-08: a row's retry after it succeeds", () => {
  it('withdraws Try again once the retry has indexed the document, as an upload that succeeds first time offers none', async () => {
    const answered = serveApi({
      'POST /api/documents': {
        status: 422,
        body: storedDocument('doc-9', 'scan', DOCUMENT_STATUS.indexingFailed),
      },
      'POST /api/documents/doc-9/reprocess': {
        status: 201,
        body: storedDocument('doc-9', 'scan', DOCUMENT_STATUS.indexed),
      },
    })
    renderUpload()

    choose([pdf('scan.pdf')])
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))
    const retry = await within(row('scan.pdf')).findByRole('button', { name: TEXT.uploadRetry })
    await waitFor(() => expect(retry.disabled).toBe(false))
    fireEvent.click(retry)

    await waitFor(() => expect(chip('scan.pdf').textContent).toBe(DOCUMENT_STATUS.indexed))
    expect(row('scan.pdf').textContent).toContain(TEXT.uploadIndexed)
    expect(within(row('scan.pdf')).queryByRole('button', { name: TEXT.uploadRetry })).toBeNull()
    expect(
      answered.filter((request) => request.path === '/api/documents/doc-9/reprocess'),
    ).toHaveLength(1)
  })
})
