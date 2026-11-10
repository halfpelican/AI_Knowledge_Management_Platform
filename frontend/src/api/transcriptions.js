/**
 * Recording transcription's two routes (D-123; docs/api-contract.md,
 * "Recording transcription"). Thin wrappers over the one API client; no fetch and
 * no XMLHttpRequest here.
 *
 * Neither stores anything. The page assembles the replies into a draft, a person
 * reviews it, and only then does `ingestMeeting` (src/api/meetings.js) add it,
 * through FR-09's own route.
 */
import { get, upload } from './client.js'

/** The 503 for a server with transcription off: paste or upload the transcript instead. */
export const TRANSCRIPTION_DISABLED_CODE = 'transcription_disabled'
/** NFR-19's 503 after the provider's attempts: nothing was stored, so the segment can be sent again. */
export const TRANSCRIPTION_UNAVAILABLE_CODE = 'transcription_unavailable'
/** The 429 while another segment of this user's is still being transcribed. */
export const TRANSCRIPTION_IN_FLIGHT_CODE = 'transcription_in_flight'

/** The two values of a transcribed segment's `status`. */
export const SEGMENT_STATUS = {
  transcribed: 'transcribed',
  silent: 'silent',
}

/**
 * `GET /api/transcriptions/status`, session plus `contribute_content`: 200
 * `{enabled, available, segment_seconds, maximum_segment_seconds}`. `available`
 * means FLM answered, not that its speech model is loaded.
 */
export function getTranscriptionStatus(options = {}) {
  return get('/transcriptions/status', options)
}

/**
 * `POST /api/transcriptions`: one 16-bit PCM WAV segment in, its text out, as
 * `{status, text, model, duration_seconds, loudest_dbfs}`; the last is the level
 * the server's silence rule compared, for checking the threshold, and the screen
 * does not show it. 200 for a transcribed segment and for
 * a silent one, which is never sent to Whisper; 400 no audio, an empty segment or
 * one too long; 413 over 50 MB; 415 not a 16-bit PCM WAV; 429 past the rate, with
 * `Retry-After`, or with `code` `transcription_in_flight`; 503 with `code`
 * `transcription_disabled` or `transcription_unavailable`.
 *
 * Sent through `upload()` because the body is multipart. The server checks the
 * permission on every call whatever the screen showed (CLAUDE.md §6, invariant 4).
 *
 * @param {ArrayBuffer} wav
 * @param {{signal?: AbortSignal}} [options]
 */
export function transcribeSegment(wav, options = {}) {
  const body = new FormData()
  body.append('audio', new Blob([wav], { type: 'audio/wav' }), 'segment.wav')
  return upload('/transcriptions', body, options)
}
