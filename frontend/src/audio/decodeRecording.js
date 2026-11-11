/**
 * A meeting recording decoded in the browser, as mono samples at Whisper's rate
 * (D-123).
 *
 * The browser's own decoder reads every common audio and video format (M4A, MP3,
 * WAV, OGG, FLAC, and the audio track of an MP4 or WebM), which nothing in the
 * server's stack does. `decodeAudioData` resamples to the rate of the context it
 * is called on, so an `OfflineAudioContext` at TRANSCRIPTION_SAMPLE_RATE yields
 * 16 kHz samples directly; the channels are then averaged to one.
 *
 * The only module that touches the Web Audio API, so a test replaces it whole
 * (jsdom has none) and the pure cutting and encoding in src/utils/audio.js is
 * tested on its own.
 */
import { TRANSCRIPTION_SAMPLE_RATE } from '../constants.js'
import { mixToMono } from '../utils/audio.js'

/** The browser could not decode the recording, or has no decoder at all. */
export class RecordingUnreadable extends Error {
  constructor(message = 'The recording could not be decoded.') {
    super(message)
    this.name = 'RecordingUnreadable'
  }
}

/**
 * @param {File} file The recording.
 * @returns {Promise<{samples: Float32Array, sampleRate: number}>}
 * @throws {RecordingUnreadable}
 */
export async function decodeRecording(file) {
  const Context = globalThis.OfflineAudioContext ?? globalThis.webkitOfflineAudioContext
  if (!Context) throw new RecordingUnreadable('This browser cannot decode audio.')
  const data = await file.arrayBuffer()
  // One frame long: the context is used only for its decoder and its rate.
  const context = new Context(1, 1, TRANSCRIPTION_SAMPLE_RATE)
  let decoded
  try {
    decoded = await context.decodeAudioData(data)
  } catch {
    throw new RecordingUnreadable()
  }
  const channels = Array.from({ length: decoded.numberOfChannels }, (_, index) => decoded.getChannelData(index))
  return { samples: mixToMono(channels), sampleRate: decoded.sampleRate }
}
