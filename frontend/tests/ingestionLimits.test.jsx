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
 * D-85 adds a second 429 on the same three routes: `{"detail": "...", "code":
 * "ingestion_in_flight"}` with no `Retry-After`, while another upload, transcript or
 * reprocess of the user's is still being processed (docs/api-contract.md, "One
 * ingestion in flight per user"). What only a screen can get right: that it gets its
 * own sentence and not the limit's, that the sentence names no time, that the two
 * are told apart by `code` alone, and that the upload screen never sends a second
 * ingestion of its own while one is still going.
 *
 * The upload queue sends through `XMLHttpRequest` (src/api/client.js `upload()`),
 * which tests/fakeApi.js answers from the same table as `fetch`.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthContext } from '../src/auth/context.js'
import { DOCUMENT_STATUS, ROLES, TEXT, VALIDATION } from '../src/constants.js'
import DocumentRepository from '../src/pages/DocumentRepository.jsx'
import Meetings from '../src/pages/Meetings.jsx'
import Upload from '../src/pages/Upload.jsx'
import { heldResponse, serveApi } from './fakeApi.js'

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

/** D-85's in-flight body, word for word from the contract. */
const IN_FLIGHT = { detail: 'Your previous upload is still being processed.', code: 'ingestion_in_flight' }

/** D-85's in-flight 429 as the server sends it: that body, and no `Retry-After`. */
function inFlight() {
  return { status: 429, body: IN_FLIGHT }
}

/**
 * The opening words of every limit sentence, which the in-flight 429 must never be
 * shown with. Checked against the sentences themselves, so it cannot quietly stop
 * matching if they are reworded.
 */
const LIMIT_WORDS = 'The upload limit has been reached'
for (const sentence of [TEXT.uploadLimitReached, TEXT.reprocessLimitReached, TEXT.meetingLimitReached]) {
  if (!sentence(TEXT.retryLater).startsWith(LIMIT_WORDS)) {
    throw new Error(`A limit sentence no longer opens with "${LIMIT_WORDS}"; update LIMIT_WORDS`)
  }
}

/** A time a sentence could promise: "in 30 seconds", "in 1 minute", "later", "now". */
function namesATime(text) {
  return /\d+ (second|minute)|\blater\b|\bnow\b/.test(text)
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

/* ---- D-85: the in-flight 429 on each screen ------------------------------ */

/** The repository's one browse reply, holding these documents. */
function browseOf(documents) {
  return {
    body: {
      filters: { q: null, status: null, department: null, project: null, process: null, topic: null, sort: '-uploaded_at' },
      facets: { department: [], project: [], process: [], topic: [] },
      documents,
    },
  }
}

/** A failed row's retry on the upload screen. */
function retryOn(name) {
  return within(row(name)).getByRole('button', { name: TEXT.uploadRetry })
}

/** The upload queue's one action, whichever label it is carrying. */
function uploadButton() {
  return screen.getByRole('button', { name: /^(Upload \d+ files?|Uploading…)$/ })
}

/** The transcript form's refusal, or "" while there is none. */
function meetingAlertText() {
  return screen.queryByText('Could not add the transcript')?.closest('[role="alert"]')?.textContent ?? ''
}

/** The repository's notice for a retry that did not run, or "" while there is none. */
function repositoryAlertText() {
  return screen.queryByText(TEXT.documentReprocessFailed)?.closest('[role="alert"]')?.textContent ?? ''
}

async function fillMeetingForm(transcript) {
  await screen.findByText(TEXT.noMeetings)
  fireEvent.change(screen.getByLabelText('Meeting title'), { target: { value: 'Supplier sync' } })
  fireEvent.change(screen.getByLabelText('Meeting date'), { target: { value: '2020-01-15' } })
  fireEvent.change(screen.getByLabelText('Transcript'), { target: { value: transcript } })
}

/** Lets a run's last updates land before looking at what it left behind. */
async function letLateWorkLand() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50))
  })
}

describe('D-85 on FR-08: the in-flight 429 in a multi-file upload', () => {
  it("stops the queue, and shows the 429'd file and the file behind it as not stored, in the in-flight sentence and not the limit's, naming no time", async () => {
    // The first upload meets another of this user's still being processed; once the
    // test lets that one finish, every upload is stored.
    let earlierFinished = false
    let sent = 0
    const answered = serveApi({
      'POST /api/documents': () => {
        sent += 1
        if (!earlierFinished) return inFlight()
        return { status: 201, body: storedDocument(`doc-${sent}`, `stored ${sent}`, DOCUMENT_STATUS.indexed) }
      },
    })
    renderAt('/upload', <Route path="/upload" element={<Upload />} />)

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('a.pdf'), pdf('b.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 2 files' }))

    // b.pdf is the last row the queue updates, after the 429 on a.pdf.
    await waitFor(() => expect(row('b.pdf').textContent).toContain(TEXT.uploadInFlight))

    // The queue stopped at the 429: b.pdf was never sent.
    expect(requests(answered, 'POST', '/api/documents')).toHaveLength(1)

    for (const name of ['a.pdf', 'b.pdf']) {
      const text = row(name).textContent
      expect(text).toContain(TEXT.uploadInFlight)
      expect(text).not.toContain(LIMIT_WORDS)
      expect(namesATime(text)).toBe(false)
      // Not stored, and nothing wrong with the file: queued, not failed or invalid.
      expect(chip(name).textContent).toBe(TEXT.uploadLimitedStatus)
      expect(chip(name).classList.contains('upload-status--rejected')).toBe(false)
      expect(chip(name).classList.contains('upload-status--failed')).toBe(false)
      for (const refusal of REFUSALS) expect(text).not.toContain(refusal)
      expect(within(row(name)).getByLabelText(`Title for ${name}`)).toBeTruthy()
      expect(within(row(name)).queryByRole('button', { name: TEXT.uploadRetry })).toBeNull()
    }
    // The client's own sentence, never the reply's `detail`.
    expect(document.body.textContent).not.toContain(IN_FLIGHT.detail)

    // Nothing was stored, so once the earlier upload has finished, Upload sends both
    // files again as uploads.
    earlierFinished = true
    const again = screen.getByRole('button', { name: 'Upload 2 files' })
    await waitFor(() => expect(again.disabled).toBe(false))
    fireEvent.click(again)
    await waitFor(() => expect(chip('b.pdf').textContent).toBe(DOCUMENT_STATUS.indexed))
    expect(chip('a.pdf').textContent).toBe(DOCUMENT_STATUS.indexed)
    expect(requests(answered, 'POST', '/api/documents').map((request) => request.body.get('title'))).toEqual([
      'a',
      'a',
      'b',
    ])
  })
})

describe("D-85 on FR-08: the in-flight 429 on the queue's retry", () => {
  it('keeps the stored document at its status with the retry offered, in the in-flight sentence, naming no time', async () => {
    const answered = serveApi({
      'POST /api/documents': {
        status: 422,
        body: storedDocument('doc-9', 'scan', DOCUMENT_STATUS.indexingFailed),
      },
      'POST /api/documents/doc-9/reprocess': inFlight(),
    })
    renderAt('/upload', <Route path="/upload" element={<Upload />} />)

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('scan.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))
    await waitFor(() => expect(retryOn('scan.pdf').disabled).toBe(false))
    fireEvent.click(retryOn('scan.pdf'))

    await waitFor(() => expect(row('scan.pdf').textContent).toContain(TEXT.reprocessInFlight))
    const text = row('scan.pdf').textContent
    expect(text).not.toContain(LIMIT_WORDS)
    expect(namesATime(text)).toBe(false)
    expect(text).not.toContain(TEXT.uploadIndexed)
    expect(document.body.textContent).not.toContain(IN_FLIGHT.detail)
    // Not processed again: still at the status it had, with the retry still offered.
    expect(chip('scan.pdf').textContent).toBe(DOCUMENT_STATUS.indexingFailed)
    await waitFor(() => expect(retryOn('scan.pdf').disabled).toBe(false))
    // A retry of a stored document re-runs it; the file is not sent again.
    expect(requests(answered, 'POST', '/api/documents')).toHaveLength(1)
    expect(requests(answered, 'POST', '/api/documents/doc-9/reprocess')).toHaveLength(1)
  })
})

describe('D-85 on FR-09: the in-flight 429 on meeting ingestion', () => {
  it("says the transcript was not stored, in the in-flight sentence and not the limit's, naming no time, and keeps what was entered", async () => {
    const answered = serveApi({
      'GET /api/meetings': { body: [] },
      'GET /api/users/directory': { body: [] },
      'POST /api/meetings': inFlight(),
    })
    renderAt('/meetings', <Route path="/meetings" element={<Meetings />} />)

    const transcript = 'Alex: the supplier review is due on Friday.'
    await fillMeetingForm(transcript)
    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))

    await waitFor(() => expect(meetingAlertText()).toContain(TEXT.meetingInFlight))
    expect(meetingAlertText()).not.toContain(LIMIT_WORDS)
    expect(namesATime(meetingAlertText())).toBe(false)
    expect(document.body.textContent).not.toContain(IN_FLIGHT.detail)
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

describe("D-85 on FR-15: the in-flight 429 on the repository's retry", () => {
  it("leaves the row at its status with its retry, in the in-flight sentence and not the limit's, naming no time", async () => {
    const FAILED = storedDocument('doc-7', 'Quarterly figures', DOCUMENT_STATUS.indexingFailed)
    const answered = serveApi({
      'GET /api/documents/browse': browseOf([FAILED]),
      'POST /api/documents/doc-7/reprocess': inFlight(),
    })
    renderAt('/documents', <Route path="/documents" element={<DocumentRepository />} />)

    fireEvent.click(await screen.findByRole('button', { name: TEXT.documentRetryLabel(FAILED.title) }))

    await waitFor(() => expect(repositoryAlertText()).toContain(TEXT.reprocessInFlight))
    expect(repositoryAlertText()).not.toContain(LIMIT_WORDS)
    expect(namesATime(repositoryAlertText())).toBe(false)
    expect(document.body.textContent).not.toContain(IN_FLIGHT.detail)
    const tableRow = screen.getByRole('link', { name: FAILED.title }).closest('tr')
    expect(tableRow.textContent).toContain(DOCUMENT_STATUS.indexingFailed)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: TEXT.documentRetryLabel(FAILED.title) }).disabled).toBe(false),
    )
    // Nothing changed on the server, so the list is not re-read.
    expect(requests(answered, 'GET', '/api/documents/browse')).toHaveLength(1)
  })
})

describe('D-85: the in-flight 429 is told apart from the limit by `code` alone', () => {
  // Both replies carry the in-flight `detail` word for word, so a screen reading
  // `detail` would say the same thing twice. And here the in-flight reply carries a
  // `Retry-After` while the limit's carries none, the reverse of what the server
  // sends, so a screen keying on the header would give each the other's sentence.
  // Only `code` tells them apart the right way round. The in-flight sentence still
  // names no time with a `Retry-After` beside it.
  function oneThenTheOther() {
    let sent = 0
    return () => {
      sent += 1
      return sent === 1
        ? { status: 429, body: IN_FLIGHT, headers: { 'Retry-After': '30' } }
        : { status: 429, body: { detail: IN_FLIGHT.detail } }
    }
  }

  it('on the upload queue', async () => {
    serveApi({ 'POST /api/documents': oneThenTheOther() })
    renderAt('/upload', <Route path="/upload" element={<Upload />} />)

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('a.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))
    await waitFor(() => expect(row('a.pdf').textContent).toContain(TEXT.uploadInFlight))
    expect(row('a.pdf').textContent).not.toContain(LIMIT_WORDS)
    expect(namesATime(row('a.pdf').textContent)).toBe(false)

    const again = screen.getByRole('button', { name: 'Upload 1 file' })
    await waitFor(() => expect(again.disabled).toBe(false))
    fireEvent.click(again)
    await waitFor(() => expect(row('a.pdf').textContent).toContain(TEXT.uploadLimitReached(TEXT.retryLater)))
    expect(row('a.pdf').textContent).not.toContain(TEXT.uploadInFlight)
  })

  it('on the transcript form', async () => {
    serveApi({
      'GET /api/meetings': { body: [] },
      'GET /api/users/directory': { body: [] },
      'POST /api/meetings': oneThenTheOther(),
    })
    renderAt('/meetings', <Route path="/meetings" element={<Meetings />} />)

    await fillMeetingForm('Alex: the supplier review is due on Friday.')
    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))
    await waitFor(() => expect(meetingAlertText()).toContain(TEXT.meetingInFlight))
    expect(meetingAlertText()).not.toContain(LIMIT_WORDS)
    expect(namesATime(meetingAlertText())).toBe(false)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Add transcript' }).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))
    await waitFor(() => expect(meetingAlertText()).toContain(TEXT.meetingLimitReached(TEXT.retryLater)))
    expect(meetingAlertText()).not.toContain(TEXT.meetingInFlight)
  })

  it("on the repository's retry", async () => {
    const FAILED = storedDocument('doc-7', 'Quarterly figures', DOCUMENT_STATUS.indexingFailed)
    serveApi({
      'GET /api/documents/browse': browseOf([FAILED]),
      'POST /api/documents/doc-7/reprocess': oneThenTheOther(),
    })
    renderAt('/documents', <Route path="/documents" element={<DocumentRepository />} />)

    const retry = () => screen.getByRole('button', { name: TEXT.documentRetryLabel(FAILED.title) })
    await screen.findByRole('button', { name: TEXT.documentRetryLabel(FAILED.title) })
    fireEvent.click(retry())
    await waitFor(() => expect(repositoryAlertText()).toContain(TEXT.reprocessInFlight))
    expect(repositoryAlertText()).not.toContain(LIMIT_WORDS)
    expect(namesATime(repositoryAlertText())).toBe(false)

    await waitFor(() => expect(retry().disabled).toBe(false))
    fireEvent.click(retry())
    await waitFor(() => expect(repositoryAlertText()).toContain(TEXT.reprocessLimitReached(TEXT.retryLater)))
    expect(repositoryAlertText()).not.toContain(TEXT.reprocessInFlight)
  })
})

/* ---- D-85: one send at a time from the upload screen ---------------------- */

describe('D-85 on FR-08: the upload screen sends one ingestion at a time', () => {
  it("disables a failed row's retry while the queue is uploading another file, and enables it once the queue has finished", async () => {
    // scan.pdf is stored but not indexed; b.pdf's upload is then held on the server.
    const upload = heldResponse()
    let sent = 0
    const answered = serveApi({
      'POST /api/documents': () => {
        sent += 1
        if (sent === 1) return { status: 422, body: storedDocument('doc-9', 'scan', DOCUMENT_STATUS.indexingFailed) }
        return upload.route()
      },
      'POST /api/documents/doc-9/reprocess': {
        status: 201,
        body: storedDocument('doc-9', 'scan', DOCUMENT_STATUS.indexed),
      },
    })
    renderAt('/upload', <Route path="/upload" element={<Upload />} />)

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('scan.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))
    await waitFor(() => expect(retryOn('scan.pdf').disabled).toBe(false))

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('b.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))

    // b.pdf is with the server and the queue is waiting on it.
    await waitFor(() => expect(requests(answered, 'POST', '/api/documents')).toHaveLength(2))
    await waitFor(() => expect(retryOn('scan.pdf').disabled).toBe(true))
    await letLateWorkLand()
    expect(retryOn('scan.pdf').disabled).toBe(true)
    expect(requests(answered, 'POST', '/api/documents/doc-9/reprocess')).toHaveLength(0)

    upload.release({ status: 201, body: storedDocument('doc-10', 'b', DOCUMENT_STATUS.indexed) })
    await waitFor(() => expect(chip('b.pdf').textContent).toBe(DOCUMENT_STATUS.indexed))
    await waitFor(() => expect(retryOn('scan.pdf').disabled).toBe(false))

    fireEvent.click(retryOn('scan.pdf'))
    await waitFor(() => expect(chip('scan.pdf').textContent).toBe(DOCUMENT_STATUS.indexed))
    expect(requests(answered, 'POST', '/api/documents/doc-9/reprocess')).toHaveLength(1)
  })

  it('keeps Upload disabled through a retry that ends while the queue is still sending, until the queue has finished', async () => {
    // With the retry disabled while the queue runs, the one way left to start a retry
    // beside the queue is two presses landing before the screen re-renders. Both are
    // pressed inside one act() to make that happen. The server is processing b.pdf,
    // so it answers the retry at once with the in-flight 429: the retry ends while
    // b.pdf is still being processed and c.pdf is still to go.
    const upload = heldResponse()
    let sent = 0
    const answered = serveApi({
      'POST /api/documents': () => {
        sent += 1
        if (sent === 1) return { status: 422, body: storedDocument('doc-9', 'scan', DOCUMENT_STATUS.indexingFailed) }
        if (sent === 2) return upload.route()
        return { status: 201, body: storedDocument(`doc-${sent}`, `stored ${sent}`, DOCUMENT_STATUS.indexed) }
      },
      'POST /api/documents/doc-9/reprocess': inFlight(),
    })
    renderAt('/upload', <Route path="/upload" element={<Upload />} />)

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('scan.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload 1 file' }))
    await waitFor(() => expect(retryOn('scan.pdf').disabled).toBe(false))

    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('b.pdf'), pdf('c.pdf')] } })
    const start = screen.getByRole('button', { name: 'Upload 2 files' })
    await waitFor(() => expect(start.disabled).toBe(false))
    const retry = retryOn('scan.pdf')
    act(() => {
      start.click()
      retry.click()
    })

    // The retry has ended: the in-flight 429 is on its row.
    await waitFor(() => expect(row('scan.pdf').textContent).toContain(TEXT.reprocessInFlight))
    await letLateWorkLand()
    // The queue has sent b.pdf and not yet c.pdf, so it is still sending, and the
    // page says so: Upload is not offered for c.pdf, and no file can be added.
    expect(requests(answered, 'POST', '/api/documents')).toHaveLength(2)
    expect(uploadButton().textContent).toBe('Uploading…')
    expect(uploadButton().disabled).toBe(true)
    expect(screen.getByLabelText('Choose files').disabled).toBe(true)

    upload.release({ status: 201, body: storedDocument('doc-2', 'b', DOCUMENT_STATUS.indexed) })
    await waitFor(() => expect(chip('c.pdf').textContent).toBe(DOCUMENT_STATUS.indexed))
    expect(chip('b.pdf').textContent).toBe(DOCUMENT_STATUS.indexed)
    // Every file was sent once, and the retry once.
    expect(requests(answered, 'POST', '/api/documents').map((request) => request.body.get('title'))).toEqual([
      'scan',
      'b',
      'c',
    ])
    expect(requests(answered, 'POST', '/api/documents/doc-9/reprocess')).toHaveLength(1)

    // Once the queue has finished the page is no longer busy: the retry is back, and
    // Upload takes a new file.
    await waitFor(() => expect(retryOn('scan.pdf').disabled).toBe(false))
    fireEvent.change(screen.getByLabelText('Choose files'), { target: { files: [pdf('d.pdf')] } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Upload 1 file' }).disabled).toBe(false))
  })
})
