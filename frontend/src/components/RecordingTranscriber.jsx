import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ApiError, NETWORK_ERROR_STATUS } from '../api/client.js'
import {
  getTranscriptionStatus,
  SEGMENT_STATUS,
  TRANSCRIPTION_BUSY_CODE,
  TRANSCRIPTION_DISABLED_CODE,
  TRANSCRIPTION_IN_FLIGHT_CODE,
  transcribeSegment,
} from '../api/transcriptions.js'
import { decodeRecording } from '../audio/decodeRecording.js'
import { RECORDING_ACCEPT, TEXT } from '../constants.js'
import { encodeWav, planSegments } from '../utils/audio.js'
import { screenRecording } from '../utils/uploads.js'
import Button from './Button.jsx'
import FileDropZone from './FileDropZone.jsx'
import Notice from './Notice.jsx'
import useApiResource from '../hooks/useApiResource.js'
import ProgressBar from './ProgressBar.jsx'

/** Whether a transcribed recording can be had here, from GET /api/transcriptions/status. */
const AVAILABILITY = {
  checking: 'checking',
  disabled: 'disabled',
  unavailable: 'unavailable',
  failed: 'failed',
  ready: 'ready',
}

/** Where a run is. `paused` is a run a failure stopped; `stopped` is one the person stopped. */
const PHASE = {
  idle: 'idle',
  reading: 'reading',
  transcribing: 'transcribing',
  stopped: 'stopped',
  paused: 'paused',
  done: 'done',
}

/** A wait that a Stop ends early, rejecting as an aborted request does. */
function pause(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, milliseconds)
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        reject(new DOMException('The operation was aborted.', 'AbortError'))
      },
      { once: true },
    )
  })
}

/** What a failed segment is reported as. The draft and the recording are kept in every case. */
function problemFor(error, done, total) {
  if (error instanceof ApiError) {
    if (error.status === 503 && error.code === TRANSCRIPTION_DISABLED_CODE) return TEXT.transcribeDisabledNow
    if (error.status === 503 || error.status === NETWORK_ERROR_STATUS) return TEXT.transcribeUnavailable(done, total)
    if (error.status === 429 && error.code === TRANSCRIPTION_IN_FLIGHT_CODE) return TEXT.transcribeInFlight
    if (error.status === 401 || error.status === 403) return error.message
  }
  return TEXT.transcribeRefused(done, total)
}

/**
 * D-123: a meeting recording turned into draft text, a segment at a time.
 *
 * **What it does.** It asks the server whether transcription is available, takes a
 * recording from the picker or a drop, decodes it in the browser, cuts it into WAV
 * segments (src/utils/audio.js) and sends them to `POST /api/transcriptions` one at
 * a time. Each transcribed segment's text is handed to `onText`, which is how the
 * form's draft grows; a silent segment is counted and adds nothing. Nothing here
 * adds a transcript: the form does that, once a person has reviewed the draft,
 * through FR-09's own route.
 *
 * **Invariant 8: a failure discards nothing.** A segment the server could not
 * transcribe pauses the run with the recording still decoded in this component
 * and the draft still in the form, and Resume sends that segment again. Stop does
 * the same at the person's request. A 429 from the transcription rate is waited
 * out and the run carries on by itself, since nothing was wrong with the segment.
 *
 * **What it says** at each point is in one live line beside a progress bar, so a
 * long run is visibly moving and a screen reader hears where it is.
 *
 * @param {object} props
 * @param {boolean} [props.active] The recording option is the one chosen. While it is not, the
 *   form keeps this component mounted and hidden, and its drop zone takes no page-wide drop.
 * @param {boolean} [props.disabled] The form is busy adding the transcript.
 * @param {(text: string) => void} props.onText Called with each transcribed segment's text, in order.
 * @param {(busy: boolean) => void} [props.onBusyChange] Told when a run starts and ends.
 */
export default function RecordingTranscriber({ active = true, disabled = false, onText, onBusyChange }) {
  // Asked once, when the option is chosen; Check again asks again.
  const status = useApiResource(getTranscriptionStatus)
  // Set when a segment is answered "not enabled": the server was switched off mid-run.
  const [switchedOff, setSwitchedOff] = useState(false)
  const [file, setFile] = useState(null)
  const [fileError, setFileError] = useState(null)
  const [phase, setPhase] = useState(PHASE.idle)
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [silentCount, setSilentCount] = useState(0)
  const [heardSpeech, setHeardSpeech] = useState(false)
  const [problem, setProblem] = useState(null)
  const [waitingSeconds, setWaitingSeconds] = useState(null)
  const [waitingBusy, setWaitingBusy] = useState(false)
  // Whether the chosen recording has been decoded, so Resume has something to resume.
  const [decoded, setDecoded] = useState(false)

  // The decoded recording and its cut points: kept out of state, since nothing
  // renders them and a long recording is many megabytes.
  const recordingRef = useRef(null)
  const nextSegmentRef = useRef(0)
  const controllerRef = useRef(null)
  const mountedRef = useRef(false)
  // The latest onText, for a run that started several renders ago.
  const onTextRef = useRef(onText)
  useEffect(() => {
    onTextRef.current = onText
  }, [onText])

  const busy = phase === PHASE.reading || phase === PHASE.transcribing

  // A layout effect, so the form learns a run has started or ended in the same
  // commit that shows it, before anything is painted: the draft box's read-only
  // state and the held source never lag the line that says where the run is.
  useLayoutEffect(() => {
    onBusyChange?.(busy)
  }, [busy, onBusyChange])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      controllerRef.current?.abort()
    }
  }, [])

  let availability = AVAILABILITY.ready
  if (status.loading) availability = AVAILABILITY.checking
  else if (status.error) availability = AVAILABILITY.failed
  else if (!status.data?.enabled || switchedOff) availability = AVAILABILITY.disabled
  else if (!status.data.available) availability = AVAILABILITY.unavailable
  const segmentSeconds = status.data?.segment_seconds

  function chooseFile(files) {
    const chosen = files[0]
    if (!chosen) return
    const rejection = screenRecording(chosen)
    setFile(rejection ? null : chosen)
    setFileError(rejection)
    recordingRef.current = null
    nextSegmentRef.current = 0
    setDecoded(false)
    setPhase(PHASE.idle)
    setProgress({ done: 0, total: 0 })
    setSilentCount(0)
    setHeardSpeech(false)
    setProblem(null)
  }

  async function run(controller) {
    const { samples, sampleRate, segments } = recordingRef.current
    setPhase(PHASE.transcribing)
    while (nextSegmentRef.current < segments.length) {
      const index = nextSegmentRef.current
      const { start, end } = segments[index]
      let reply
      try {
        reply = await transcribeSegment(encodeWav(samples.subarray(start, end), sampleRate), {
          signal: controller.signal,
        })
      } catch (error) {
        if (!mountedRef.current) return
        if (error?.name === 'AbortError') {
          setPhase(PHASE.stopped)
          return
        }
        const rateLimited =
          error instanceof ApiError &&
          error.status === 429 &&
          error.code !== TRANSCRIPTION_IN_FLIGHT_CODE &&
          typeof error.retryAfter === 'number'
        if (rateLimited) {
          // The rate limit's 429 and the busy server's both carry Retry-After; only the words differ.
          setWaitingBusy(error.code === TRANSCRIPTION_BUSY_CODE)
          setWaitingSeconds(error.retryAfter)
          try {
            await pause(error.retryAfter * 1000, controller.signal)
          } catch {
            if (!mountedRef.current) return
            setWaitingSeconds(null)
            setPhase(PHASE.stopped)
            return
          }
          if (!mountedRef.current) return
          setWaitingSeconds(null)
          continue // the same segment again: nothing was wrong with it
        }
        if (error instanceof ApiError && error.code === TRANSCRIPTION_DISABLED_CODE) setSwitchedOff(true)
        setProblem(problemFor(error, index, segments.length))
        setPhase(PHASE.paused)
        return
      }
      if (!mountedRef.current) return
      if (reply?.status === SEGMENT_STATUS.silent) {
        setSilentCount((count) => count + 1)
      } else if (reply?.text) {
        setHeardSpeech(true)
        onTextRef.current(reply.text)
      }
      nextSegmentRef.current = index + 1
      setProgress({ done: index + 1, total: segments.length })
    }
    setPhase(PHASE.done)
  }

  async function start() {
    if (!file || busy) return
    const controller = new AbortController()
    controllerRef.current = controller
    setProblem(null)
    if (!recordingRef.current) {
      setPhase(PHASE.reading)
      let recording
      try {
        recording = await decodeRecording(file)
      } catch {
        if (!mountedRef.current) return
        setPhase(PHASE.idle)
        setProblem(TEXT.transcribeUnreadable)
        return
      }
      if (!mountedRef.current) return
      const segments = planSegments(recording.samples, recording.sampleRate, segmentSeconds)
      recordingRef.current = { ...recording, segments }
      nextSegmentRef.current = 0
      setDecoded(true)
      setProgress({ done: 0, total: segments.length })
      if (controller.signal.aborted) {
        setPhase(PHASE.stopped)
        return
      }
    }
    await run(controller)
  }

  function resume() {
    if (!recordingRef.current || busy) return
    const controller = new AbortController()
    controllerRef.current = controller
    setProblem(null)
    run(controller)
  }

  function stop() {
    controllerRef.current?.abort()
  }

  if (availability === AVAILABILITY.checking) {
    return (
      <p className="meeting-form__note" role="status">
        {TEXT.recordingChecking}
      </p>
    )
  }
  if (availability === AVAILABILITY.disabled && phase === PHASE.idle) {
    return (
      <Notice variant="info" title={TEXT.recordingDisabledTitle}>
        {TEXT.recordingDisabled}
      </Notice>
    )
  }
  if (availability === AVAILABILITY.unavailable || availability === AVAILABILITY.failed) {
    return (
      <div className="recording-transcriber">
        <Notice
          variant="error"
          title={availability === AVAILABILITY.failed ? TEXT.recordingStatusFailed : TEXT.recordingUnavailableTitle}
        >
          {TEXT.recordingUnavailable}
        </Notice>
        <div className="recording-transcriber__actions">
          <Button variant="secondary" onClick={status.reload}>
            {TEXT.recordingCheckAgain}
          </Button>
        </div>
      </div>
    )
  }

  const { done, total } = progress
  const resumable =
    (phase === PHASE.stopped || phase === PHASE.paused) && decoded && availability === AVAILABILITY.ready
  let statusLine = ''
  if (phase === PHASE.reading) statusLine = TEXT.transcribeReading
  else if (phase === PHASE.transcribing) {
    if (waitingSeconds === null) statusLine = TEXT.transcribeProgress(done, total)
    else statusLine = waitingBusy ? TEXT.transcribeBusy(waitingSeconds) : TEXT.transcribeWaiting(waitingSeconds)
  } else if (phase === PHASE.stopped) statusLine = TEXT.transcribeStopped(done, total)
  else if (phase === PHASE.done) statusLine = heardSpeech ? TEXT.transcribeDone : TEXT.transcribeNothingHeard
  if (silentCount > 0 && phase !== PHASE.reading) statusLine = `${statusLine} ${TEXT.transcribeSilent(silentCount)}`.trim()

  return (
    <div className="recording-transcriber">
      <FileDropZone
        label={TEXT.recordingLabel}
        hint={TEXT.recordingHint}
        accept={RECORDING_ACCEPT}
        disabled={disabled || busy}
        disabledReason={TEXT.recordingBusy}
        error={fileError}
        status={file ? TEXT.recordingChosen(file.name) : TEXT.recordingNone}
        pageDrop={active}
        onFiles={chooseFile}
      />
      <div className="recording-transcriber__actions">
        {phase === PHASE.idle ? (
          <Button onClick={start} disabled={!file || disabled}>
            {TEXT.transcribeStart}
          </Button>
        ) : null}
        {busy ? (
          <Button variant="secondary" onClick={stop}>
            {TEXT.transcribeStop}
          </Button>
        ) : null}
        {resumable ? (
          <Button onClick={resume} disabled={disabled}>
            {TEXT.transcribeResume}
          </Button>
        ) : null}
      </div>
      {total > 0 ? (
        <ProgressBar
          label={TEXT.transcribeProgressLabel}
          value={(done / total) * 100}
          valueText={TEXT.transcribeProgress(done, total)}
        />
      ) : null}
      <p className="recording-transcriber__status" role="status" aria-live="polite">
        {statusLine}
      </p>
      {problem ? (
        <Notice variant="error" title={TEXT.transcribeFailedTitle}>
          {problem}
        </Notice>
      ) : null}
    </div>
  )
}
