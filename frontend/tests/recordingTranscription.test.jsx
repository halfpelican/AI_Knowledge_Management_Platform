/**
 * D-123 on the meetings screen: a recording becomes a draft a person must
 * review before it is added through FR-09.
 *
 * The browser's decoder is replaced (jsdom has no Web Audio API), so each test
 * says what the recording decodes to; everything after it runs as shipped: the
 * cutting and encoding (src/utils/audio.js), the client's upload and its error
 * handling, and the screen. tests/fakeApi.js answers the routes, and refuses any
 * the test did not name.
 *
 * What these hold, enumerated, the clauses only the interface can satisfy
 * (CLAUDE.md §8 item 2):
 *
 * - the status: not enabled here; not answering, with Check again;
 * - the happy path: each segment sent as a WAV, in order, the draft growing, and
 *   the run's progress said in words;
 * - the review: no draft added until a person ticks that they reviewed it, then
 *   added through `POST /api/meetings` as pasted text, exactly as edited;
 * - silence: counted, adding nothing;
 * - invariant 8: a failed segment (503, a refused connection) pauses the run with
 *   the draft kept, and Resume sends that segment again;
 * - a 429 from the rate waited out, the run carrying on by itself; the in-flight
 *   429 and the disabled 503 pausing with their own words;
 * - Stop, keeping the draft, then Resume;
 * - a recording the browser cannot read, one too large, one that is not audio;
 * - the draft kept across a change of source, read-only while segments arrive;
 * - the draft saved as a text file, and the browser asking before a tab with an
 *   unadded draft is closed.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { decodeRecording } from '../src/audio/decodeRecording.js'
import { AuthContext } from '../src/auth/context.js'
import { MAXIMUM_RECORDING_BYTES, ROLES, TEXT, VALIDATION } from '../src/constants.js'
import Meetings from '../src/pages/Meetings.jsx'
import { planSegments } from '../src/utils/audio.js'
import { heldResponse, serveApi } from './fakeApi.js'

vi.mock('../src/audio/decodeRecording.js', () => ({
  decodeRecording: vi.fn(),
  RecordingUnreadable: class RecordingUnreadable extends Error {},
}))

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

const RATE = 16000
// One-second segments keep the decoded recordings small: 3.5 s is three segments.
const SEGMENT_SECONDS = 1
const RECORDING_SECONDS = 3.5
const READY = { enabled: true, available: true, segment_seconds: SEGMENT_SECONDS, maximum_segment_seconds: 60 }
const STORED = {
  meeting_id: 'meeting-7',
  title: 'Budget review',
  meeting_date: '2020-01-15',
  status: 'Indexed',
  created_at: '2026-11-10T10:00:00+11:00',
  visible_to_roles: [ROLES.employee, ROLES.administrator],
  attendees: [],
}

function decoded(seconds = RECORDING_SECONDS) {
  return { samples: new Float32Array(Math.round(seconds * RATE)).fill(0.2), sampleRate: RATE }
}

const SEGMENT_COUNT = planSegments(decoded().samples, RATE, SEGMENT_SECONDS).length

function said(number) {
  return `Segment ${number} was said.`
}

/** A reply per segment, in order: transcribed with its own text unless a test says otherwise. */
function transcribedReply(number) {
  return { body: { status: 'transcribed', text: said(number), model: 'whisper-v3:turbo', duration_seconds: 1 } }
}

function recordingFile(name = 'budget-review.m4a', type = 'audio/mp4') {
  return new File([new Uint8Array(64)], name, { type })
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

/**
 * The API for one test. `segments` answers each POST /api/transcriptions in turn,
 * as a list of replies or a function of the request's number; `status` is the
 * status route's body.
 */
function serve({ status = READY, segments = transcribedReply, meetings = {} } = {}) {
  let segmentNumber = 0
  let stored = false
  return serveApi({
    'GET /api/meetings': () => ({ body: stored ? [STORED] : [] }),
    'GET /api/users/directory': { body: [] },
    'GET /api/transcriptions/status': typeof status === 'function' ? status : { body: status },
    'POST /api/transcriptions': () => {
      segmentNumber += 1
      return Array.isArray(segments) ? segments[segmentNumber - 1] : segments(segmentNumber)
    },
    'POST /api/meetings': () => {
      stored = true
      return { status: 201, body: STORED, ...meetings }
    },
  })
}

function segmentRequests(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/transcriptions')
}

function meetingRequests(answered) {
  return answered.filter((request) => request.method === 'POST' && request.path === '/api/meetings')
}

async function chooseRecordingOption() {
  await screen.findByText(TEXT.noMeetings)
  fireEvent.click(screen.getByLabelText(TEXT.meetingSourceRecording))
}

async function transcribe(file = recordingFile()) {
  await chooseRecordingOption()
  fireEvent.change(await screen.findByLabelText(TEXT.recordingLabel), { target: { files: [file] } })
  fireEvent.click(screen.getByRole('button', { name: TEXT.transcribeStart }))
}

function draftBox() {
  return screen.getByLabelText(TEXT.draftLabel)
}

function fillMeetingDetails() {
  fireEvent.change(screen.getByLabelText('Meeting title'), { target: { value: STORED.title } })
  fireEvent.change(screen.getByLabelText('Meeting date'), { target: { value: STORED.meeting_date } })
}

function expectedDraft(numbers) {
  return numbers.map(said).join('\n\n')
}

beforeEach(() => {
  decodeRecording.mockReset()
  decodeRecording.mockResolvedValue(decoded())
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('D-123: whether a recording can be transcribed here', () => {
  it('says transcription is not enabled on this server, and offers no picker', async () => {
    serve({ status: { ...READY, enabled: false, available: false } })
    renderMeetings()
    await chooseRecordingOption()

    expect(await screen.findByText(TEXT.recordingDisabled)).toBeTruthy()
    expect(screen.queryByLabelText(TEXT.recordingLabel)).toBeNull()
  })

  it('says the service is not answering, and checks again on request', async () => {
    let up = false
    serve({ status: () => ({ body: { ...READY, available: up } }) })
    renderMeetings()
    await chooseRecordingOption()

    expect(await screen.findByText(TEXT.recordingUnavailable)).toBeTruthy()
    up = true
    fireEvent.click(screen.getByRole('button', { name: TEXT.recordingCheckAgain }))

    expect(await screen.findByLabelText(TEXT.recordingLabel)).toBeTruthy()
  })
})

describe('D-123: a recording becomes a draft, a segment at a time', () => {
  it('sends each segment as a WAV in order, grows the draft, and says where it is', async () => {
    const answered = serve()
    renderMeetings()
    await transcribe()

    await screen.findByText(TEXT.transcribeDone)
    const numbers = Array.from({ length: SEGMENT_COUNT }, (_, i) => i + 1)
    expect(draftBox().value).toBe(expectedDraft(numbers))
    expect(screen.getByText(TEXT.transcribeProgress(SEGMENT_COUNT, SEGMENT_COUNT))).toBeTruthy()

    const sent = segmentRequests(answered)
    expect(sent).toHaveLength(SEGMENT_COUNT)
    for (const request of sent) {
      const part = request.body.get('audio')
      expect(part.type).toBe('audio/wav')
      expect(part.name).toBe('segment.wav')
      const header = new Uint8Array(await part.arrayBuffer()).slice(0, 12)
      expect(String.fromCharCode(...header.slice(0, 4), ...header.slice(8, 12))).toBe('RIFFWAVE')
    }
    expect(meetingRequests(answered)).toHaveLength(0) // nothing is added by transcribing
    expect(decodeRecording).toHaveBeenCalledTimes(1)
  })

  it('counts a silent segment and adds nothing for it', async () => {
    serve({
      segments: (n) =>
        n === 2 ? { body: { status: 'silent', text: '', model: null, duration_seconds: 1 } } : transcribedReply(n),
    })
    renderMeetings()
    await transcribe()

    // The finished line carries the count after it.
    await screen.findByText(`${TEXT.transcribeDone} ${TEXT.transcribeSilent(1)}`)
    const heard = Array.from({ length: SEGMENT_COUNT }, (_, i) => i + 1).filter((n) => n !== 2)
    expect(draftBox().value).toBe(expectedDraft(heard))
  })

  it('says when nothing at all was heard', async () => {
    serve({ segments: () => ({ body: { status: 'silent', text: '', model: null, duration_seconds: 1 } }) })
    renderMeetings()
    await transcribe()

    expect(
      await screen.findByText(`${TEXT.transcribeNothingHeard} ${TEXT.transcribeSilent(SEGMENT_COUNT)}`),
    ).toBeTruthy()
    // No draft, so no box to review and nothing to tick.
    await waitFor(() => expect(screen.queryByLabelText(TEXT.draftLabel)).toBeNull())
    expect(screen.queryByLabelText(TEXT.draftReviewed)).toBeNull()
  })
})

describe('D-123: nothing is added until a person has reviewed the draft', () => {
  it('refuses to add an unreviewed draft, then adds the reviewed, edited text as pasted text', async () => {
    const answered = serve()
    renderMeetings()
    await transcribe()
    await screen.findByText(TEXT.transcribeDone)
    fillMeetingDetails()

    // The notice names what Whisper gets wrong.
    expect(screen.getByText(TEXT.draftReviewNotice)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))
    expect(await screen.findByText(VALIDATION.transcriptReviewRequired)).toBeTruthy()
    expect(meetingRequests(answered)).toHaveLength(0)

    const corrected = `${draftBox().value}\n\nCorrected: the budget starts on 1 March 2027.`
    fireEvent.change(draftBox(), { target: { value: corrected } })
    fireEvent.click(screen.getByLabelText(TEXT.draftReviewed))
    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))

    await screen.findByText(TEXT.meetingIndexed(STORED.title))
    const [added] = meetingRequests(answered)
    expect(added.body).toEqual({ title: STORED.title, meeting_date: STORED.meeting_date, transcript_text: corrected })
    // Added, so it is no longer a draft: the box is gone and the run starts afresh.
    await waitFor(() => expect(screen.queryByLabelText(TEXT.draftLabel)).toBeNull())
    expect(await screen.findByText(TEXT.recordingNone)).toBeTruthy()
  })

  it('keeps the draft and the tick when the add itself is refused', async () => {
    const answered = serve({
      meetings: { status: 429, body: { detail: 'Request was throttled.' }, headers: { 'Retry-After': '30' } },
    })
    renderMeetings()
    await transcribe()
    await screen.findByText(TEXT.transcribeDone)
    fillMeetingDetails()
    const draft = draftBox().value
    fireEvent.click(screen.getByLabelText(TEXT.draftReviewed))

    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))

    expect(await screen.findByText(new RegExp(TEXT.meetingLimitReached('').split('.')[0]))).toBeTruthy()
    expect(meetingRequests(answered)).toHaveLength(1)
    expect(draftBox().value).toBe(draft)
    expect(screen.getByLabelText(TEXT.draftReviewed).checked).toBe(true)
  })

  it('has nothing to add before a recording is transcribed', async () => {
    const answered = serve()
    renderMeetings()
    await chooseRecordingOption()
    await screen.findByLabelText(TEXT.recordingLabel)
    fillMeetingDetails()

    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))

    expect(await screen.findByText(VALIDATION.transcriptDraftRequired)).toBeTruthy()
    expect(meetingRequests(answered)).toHaveLength(0)
  })
})

describe('D-123: a failed segment discards nothing (invariant 8)', () => {
  it.each([
    [
      'the service is unavailable',
      { status: 503, body: { detail: 'down', code: 'transcription_unavailable' } },
      TEXT.transcribeUnavailable(1, SEGMENT_COUNT),
    ],
    [
      'the segment is refused',
      { status: 415, body: { detail: 'Audio must be a 16-bit PCM mono WAV segment at 16 kHz.' } },
      TEXT.transcribeRefused(1, SEGMENT_COUNT),
    ],
  ])('pauses when %s, keeps the draft, and resumes from the failed segment', async (_, failure, words) => {
    let failed = false
    const answered = serve({
      segments: (n) => {
        if (n === 2 && !failed) {
          failed = true
          return failure
        }
        return transcribedReply(failed ? n - 1 : n)
      },
    })
    renderMeetings()
    await transcribe()

    expect(await screen.findByText(words)).toBeTruthy()
    expect(draftBox().value).toBe(expectedDraft([1]))

    fireEvent.click(screen.getByRole('button', { name: TEXT.transcribeResume }))

    await screen.findByText(TEXT.transcribeDone)
    expect(draftBox().value).toBe(expectedDraft(Array.from({ length: SEGMENT_COUNT }, (_, i) => i + 1)))
    // The failed segment was sent twice, the rest once; the recording was decoded once.
    expect(segmentRequests(answered)).toHaveLength(SEGMENT_COUNT + 1)
    expect(decodeRecording).toHaveBeenCalledTimes(1)
  })

  it('waits out the transcription rate and carries on by itself', async () => {
    let limited = false
    serve({
      segments: (n) => {
        if (n === 2 && !limited) {
          limited = true
          return { status: 429, body: { detail: 'Request was throttled.' }, headers: { 'Retry-After': '1' } }
        }
        return transcribedReply(limited ? n - 1 : n)
      },
    })
    renderMeetings()
    await transcribe()

    expect(await screen.findByText(TEXT.transcribeWaiting(1))).toBeTruthy()
    await screen.findByText(TEXT.transcribeDone, {}, { timeout: 4000 })
    expect(draftBox().value).toBe(expectedDraft(Array.from({ length: SEGMENT_COUNT }, (_, i) => i + 1)))
  })

  it('waits out a busy server with its own words and carries on by itself', async () => {
    let busy = false
    serve({
      segments: (n) => {
        if (n === 2 && !busy) {
          busy = true
          return { status: 429, body: { detail: 'busy', code: 'transcription_busy' }, headers: { 'Retry-After': '1' } }
        }
        return transcribedReply(busy ? n - 1 : n)
      },
    })
    renderMeetings()
    await transcribe()

    expect(await screen.findByText(TEXT.transcribeBusy(1))).toBeTruthy()
    await screen.findByText(TEXT.transcribeDone, {}, { timeout: 4000 })
    expect(draftBox().value).toBe(expectedDraft(Array.from({ length: SEGMENT_COUNT }, (_, i) => i + 1)))
  })

  it('pauses with its own words while another transcription of the user is in flight', async () => {
    serve({
      segments: (n) =>
        n === 1 ? { status: 429, body: { detail: 'busy', code: 'transcription_in_flight' } } : transcribedReply(n),
    })
    renderMeetings()
    await transcribe()

    expect(await screen.findByText(TEXT.transcribeInFlight)).toBeTruthy()
    expect(screen.getByRole('button', { name: TEXT.transcribeResume })).toBeTruthy()
  })

  it('stops for good, keeping the draft, when the server has switched transcription off', async () => {
    serve({
      segments: (n) =>
        n === 2 ? { status: 503, body: { detail: 'off', code: 'transcription_disabled' } } : transcribedReply(n),
    })
    renderMeetings()
    await transcribe()

    expect(await screen.findByText(TEXT.transcribeDisabledNow)).toBeTruthy()
    expect(draftBox().value).toBe(expectedDraft([1]))
    expect(screen.queryByRole('button', { name: TEXT.transcribeResume })).toBeNull()
  })

  it('takes back a tick given before more of the recording was transcribed', async () => {
    let failed = false
    const answered = serve({
      segments: (n) => {
        if (n === 2 && !failed) {
          failed = true
          return { status: 503, body: { detail: 'down', code: 'transcription_unavailable' } }
        }
        return transcribedReply(failed ? n - 1 : n)
      },
    })
    renderMeetings()
    await transcribe()
    await screen.findByText(TEXT.transcribeUnavailable(1, SEGMENT_COUNT))
    fireEvent.click(screen.getByLabelText(TEXT.draftReviewed))
    expect(screen.getByLabelText(TEXT.draftReviewed).checked).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: TEXT.transcribeResume }))
    await screen.findByText(TEXT.transcribeDone)

    // The later segments have not been read, so the tick is gone and must be given again.
    expect(screen.getByLabelText(TEXT.draftReviewed).checked).toBe(false)
    fillMeetingDetails()
    fireEvent.click(screen.getByRole('button', { name: 'Add transcript' }))
    expect(await screen.findByText(VALIDATION.transcriptReviewRequired)).toBeTruthy()
    expect(meetingRequests(answered)).toHaveLength(0)
  })

  it('keeps its place through a look at another source, and resumes without repeating a segment', async () => {
    let failed = false
    const answered = serve({
      segments: (n) => {
        if (n === 2 && !failed) {
          failed = true
          return { status: 503, body: { detail: 'down', code: 'transcription_unavailable' } }
        }
        return transcribedReply(failed ? n - 1 : n)
      },
    })
    renderMeetings()
    await transcribe()
    await screen.findByText(TEXT.transcribeUnavailable(1, SEGMENT_COUNT))

    fireEvent.click(screen.getByLabelText(TEXT.meetingSourceText))
    fireEvent.click(screen.getByLabelText(TEXT.meetingSourceRecording))
    fireEvent.click(screen.getByRole('button', { name: TEXT.transcribeResume }))

    await screen.findByText(TEXT.transcribeDone)
    expect(draftBox().value).toBe(expectedDraft(Array.from({ length: SEGMENT_COUNT }, (_, i) => i + 1)))
    expect(segmentRequests(answered)).toHaveLength(SEGMENT_COUNT + 1)
    expect(decodeRecording).toHaveBeenCalledTimes(1)
  })

  it('stops at the person’s request, keeping the draft, and resumes', async () => {
    const first = heldResponse()
    let number = 0
    const answered = serve({
      segments: () => {
        number += 1
        return number === 1 ? first.route() : transcribedReply(number - 1)
      },
    })
    renderMeetings()
    await transcribe()

    // While a segment is out: the draft is read-only, the source and the submit are held.
    const stop = await screen.findByRole('button', { name: TEXT.transcribeStop })
    await waitFor(() => expect(draftBox().readOnly).toBe(true))
    expect(screen.getByLabelText(TEXT.meetingSourceText).disabled).toBe(true)
    expect(screen.getByRole('button', { name: 'Add transcript' }).disabled).toBe(true)

    fireEvent.click(stop)
    expect(await screen.findByText(TEXT.transcribeStopped(0, SEGMENT_COUNT))).toBeTruthy()
    // Nothing was heard before the stop, so there is no draft box until there is a draft.
    await waitFor(() => expect(screen.queryByLabelText(TEXT.draftLabel)).toBeNull())
    expect(screen.getByLabelText(TEXT.meetingSourceText).disabled).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: TEXT.transcribeResume }))
    await screen.findByText(TEXT.transcribeDone)
    expect(draftBox().value).toBe(expectedDraft(Array.from({ length: SEGMENT_COUNT }, (_, i) => i + 1)))
    expect(segmentRequests(answered)).toHaveLength(SEGMENT_COUNT + 1)
  })
})

describe('D-123: the recording itself', () => {
  it('says so when the browser cannot read it', async () => {
    decodeRecording.mockRejectedValue(new Error('cannot decode'))
    const answered = serve()
    renderMeetings()
    await transcribe()

    expect(await screen.findByText(TEXT.transcribeUnreadable)).toBeTruthy()
    expect(segmentRequests(answered)).toHaveLength(0)
  })

  it('refuses one too large to decode in the page, before reading it', async () => {
    serve()
    renderMeetings()
    await chooseRecordingOption()
    const large = recordingFile('all-day.mp4', 'video/mp4')
    Object.defineProperty(large, 'size', { value: MAXIMUM_RECORDING_BYTES + 1 })

    fireEvent.change(await screen.findByLabelText(TEXT.recordingLabel), { target: { files: [large] } })

    expect(await screen.findByText(VALIDATION.recordingTooLarge)).toBeTruthy()
    expect(screen.getByRole('button', { name: TEXT.transcribeStart }).disabled).toBe(true)
    expect(decodeRecording).not.toHaveBeenCalled()
  })

  it('refuses a file that is neither audio nor video', async () => {
    serve()
    renderMeetings()
    await chooseRecordingOption()

    fireEvent.change(await screen.findByLabelText(TEXT.recordingLabel), {
      target: { files: [new File(['Speaker 1: hello'], 'notes.txt', { type: 'text/plain' })] },
    })

    expect(await screen.findByText(VALIDATION.recordingTypeUnsupported)).toBeTruthy()
  })

  it('takes a video recording, as a screen recorder writes one', async () => {
    serve()
    renderMeetings()
    await transcribe(recordingFile('game-bar.mp4', 'video/mp4'))

    expect(await screen.findByText(TEXT.transcribeDone)).toBeTruthy()
  })
})

describe('D-123: the draft is the person’s work', () => {
  it('is kept when the source is changed and changed back', async () => {
    serve()
    renderMeetings()
    await transcribe()
    await screen.findByText(TEXT.transcribeDone)
    const draft = draftBox().value

    fireEvent.click(screen.getByLabelText(TEXT.meetingSourceText))
    expect(screen.getByLabelText('Transcript').value).toBe('') // the paste box is its own
    fireEvent.click(screen.getByLabelText(TEXT.meetingSourceRecording))

    expect((await screen.findByLabelText(TEXT.draftLabel)).value).toBe(draft)
  })

  it('can be saved as a text file named after the meeting', async () => {
    serve()
    renderMeetings()
    await transcribe()
    await screen.findByText(TEXT.transcribeDone)
    fillMeetingDetails()
    const saved = []
    // jsdom has neither, so they are put on URL for this test and taken off after.
    URL.createObjectURL = vi.fn((blob) => {
      saved.push(blob)
      return 'blob:draft'
    })
    URL.revokeObjectURL = vi.fn()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function record() {
      saved.push(this.download)
    })

    try {
      fireEvent.click(screen.getByRole('button', { name: TEXT.draftSave }))

      expect(click).toHaveBeenCalledTimes(1)
      const [blob, filename] = saved
      expect(filename).toBe('budget-review-transcript.txt')
      expect(await blob.text()).toBe(draftBox().value)
      // Revoked a moment after the click, not at once, so the download is not cancelled.
      expect(URL.revokeObjectURL).not.toHaveBeenCalled()
      await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:draft'), { timeout: 2000 })
    } finally {
      delete URL.createObjectURL
      delete URL.revokeObjectURL
    }
  })

  it('makes the browser ask before a tab with a draft not yet added is closed', async () => {
    serve()
    renderMeetings()
    await chooseRecordingOption()
    await screen.findByLabelText(TEXT.recordingLabel)

    const before = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(before)
    expect(before.defaultPrevented).toBe(false)

    fireEvent.click(screen.getByLabelText(TEXT.meetingSourceRecording))
    fireEvent.change(screen.getByLabelText(TEXT.recordingLabel), { target: { files: [recordingFile()] } })
    fireEvent.click(screen.getByRole('button', { name: TEXT.transcribeStart }))
    await screen.findByText(TEXT.transcribeDone)

    const during = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(during)
    expect(during.defaultPrevented).toBe(true)
  })

  it('names the progress in a live region a screen reader hears', async () => {
    serve()
    renderMeetings()
    await transcribe()
    await screen.findByText(TEXT.transcribeDone)

    const live = screen.getByText(TEXT.transcribeDone).closest('[role="status"]')
    expect(live).not.toBeNull()
    expect(within(live).getByText(TEXT.transcribeDone)).toBeTruthy()
    expect(screen.getByRole('progressbar', { name: TEXT.transcribeProgressLabel })).toBeTruthy()
  })
})
