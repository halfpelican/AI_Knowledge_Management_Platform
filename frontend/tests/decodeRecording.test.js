/**
 * src/audio/decodeRecording.js, the one module that touches the Web Audio API
 * (D-123). jsdom has no OfflineAudioContext, so each test supplies one that
 * records how it was built and answers decodeAudioData as the test says. What is
 * held: the context is built at Whisper's rate, so the decoder resamples to it;
 * the channels are averaged to one; a decode the browser refuses, or a browser
 * with no decoder at all, is RecordingUnreadable. The screen that uses it is
 * tests/recordingTranscription.test.jsx, which replaces this module whole.
 */
import { describe, expect, it, vi } from 'vitest'
import { decodeRecording, RecordingUnreadable } from '../src/audio/decodeRecording.js'
import { TRANSCRIPTION_SAMPLE_RATE } from '../src/constants.js'

function recording() {
  return new File([new Uint8Array(32)], 'meeting.m4a', { type: 'audio/mp4' })
}

/** An OfflineAudioContext whose decodeAudioData answers with `decode`, recording its construction. */
function fakeContext(decode) {
  const built = []
  class FakeOfflineAudioContext {
    constructor(channels, length, sampleRate) {
      built.push({ channels, length, sampleRate })
    }

    decodeAudioData(data) {
      return decode(data)
    }
  }
  return { FakeOfflineAudioContext, built }
}

describe('decodeRecording', () => {
  it('decodes at Whisper’s rate and averages the channels to one', async () => {
    const left = Float32Array.from([1, 0.5, 0])
    const right = Float32Array.from([0, 0.5, 1])
    const { FakeOfflineAudioContext, built } = fakeContext(async (data) => {
      expect(data).toBeInstanceOf(ArrayBuffer)
      return { numberOfChannels: 2, sampleRate: TRANSCRIPTION_SAMPLE_RATE, getChannelData: (i) => [left, right][i] }
    })
    vi.stubGlobal('OfflineAudioContext', FakeOfflineAudioContext)

    const { samples, sampleRate } = await decodeRecording(recording())

    expect(built).toEqual([{ channels: 1, length: 1, sampleRate: TRANSCRIPTION_SAMPLE_RATE }])
    expect(TRANSCRIPTION_SAMPLE_RATE).toBe(16000)
    expect(sampleRate).toBe(TRANSCRIPTION_SAMPLE_RATE)
    expect(Array.from(samples)).toEqual([0.5, 0.5, 0.5])
  })

  it('is RecordingUnreadable when the browser cannot decode the file', async () => {
    const { FakeOfflineAudioContext } = fakeContext(async () => {
      throw new DOMException('Unable to decode audio data', 'EncodingError')
    })
    vi.stubGlobal('OfflineAudioContext', FakeOfflineAudioContext)

    await expect(decodeRecording(recording())).rejects.toBeInstanceOf(RecordingUnreadable)
  })

  it('is RecordingUnreadable in a browser with no decoder at all', async () => {
    vi.stubGlobal('OfflineAudioContext', undefined)
    vi.stubGlobal('webkitOfflineAudioContext', undefined)

    await expect(decodeRecording(recording())).rejects.toBeInstanceOf(RecordingUnreadable)
  })
})
