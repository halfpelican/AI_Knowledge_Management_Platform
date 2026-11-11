/**
 * src/utils/audio.js: a decoded recording mixed, cut and encoded for
 * `POST /api/transcriptions` (D-123). Pure functions, so plain numbers in
 * and out; the screen that uses them is tests/recordingTranscription.test.jsx.
 */
import { describe, expect, it } from 'vitest'
import {
  appendToDraft,
  CUT_SEARCH_FROM,
  draftFilename,
  encodeWav,
  MINIMUM_TAIL_SECONDS,
  mixToMono,
  planSegments,
} from '../src/utils/audio.js'

const RATE = 16000

/** `seconds` of a constant level, so every stretch is as loud as every other. */
function steady(seconds, level = 0.2) {
  return new Float32Array(Math.round(seconds * RATE)).fill(level)
}

/** `samples` with `[from, to)` seconds silenced: a pause in the speech. */
function withPause(samples, from, to) {
  samples.fill(0, Math.round(from * RATE), Math.round(to * RATE))
  return samples
}

function ascii(view, offset, length) {
  return String.fromCharCode(...Array.from({ length }, (_, i) => view.getUint8(offset + i)))
}

describe('mixToMono', () => {
  it('averages the channels sample by sample', () => {
    const mono = mixToMono([Float32Array.from([1, 0.5, -1]), Float32Array.from([0, 0.5, 1])])
    expect(Array.from(mono)).toEqual([0.5, 0.5, 0])
  })

  it('returns a single channel as it is, and nothing for no channels', () => {
    const only = Float32Array.from([0.1, 0.2])
    expect(mixToMono([only])).toBe(only)
    expect(mixToMono([]).length).toBe(0)
  })
})

describe('planSegments', () => {
  it('leaves a recording shorter than one segment whole', () => {
    expect(planSegments(steady(12), RATE, 30)).toEqual([{ start: 0, end: 12 * RATE }])
  })

  it('covers the whole recording with contiguous segments, none over the length but a last that took a tail', () => {
    const samples = steady(95)
    const segments = planSegments(samples, RATE, 30)

    expect(segments[0].start).toBe(0)
    expect(segments.at(-1).end).toBe(samples.length)
    for (let i = 1; i < segments.length; i += 1) expect(segments[i].start).toBe(segments[i - 1].end)
    for (const { start, end } of segments.slice(0, -1)) expect(end - start).toBeLessThanOrEqual(30 * RATE)
    expect(segments.at(-1).end - segments.at(-1).start).toBeLessThanOrEqual((30 + MINIMUM_TAIL_SECONDS) * RATE)
  })

  it('cuts inside a pause in the last third rather than at the limit', () => {
    // Speech throughout, but a pause from 24.0 to 24.6 s: the cut goes there.
    const segments = planSegments(withPause(steady(50), 24.0, 24.6), RATE, 30)

    const cut = segments[0].end / RATE
    expect(cut).toBeGreaterThanOrEqual(24.0)
    expect(cut).toBeLessThanOrEqual(24.6)
  })

  it('cuts no earlier than the last third, even at a pause before it', () => {
    // A pause at 5 s is ignored: a cut there would make the first segment needlessly short.
    const segments = planSegments(withPause(steady(50), 5, 6), RATE, 30)

    expect(segments[0].end).toBeGreaterThanOrEqual(Math.floor(30 * RATE * CUT_SEARCH_FROM))
  })

  it('sends a recording a little over one segment whole rather than leave a sliver', () => {
    const segments = planSegments(steady(30.5), RATE, 30)

    expect(segments).toEqual([{ start: 0, end: 30.5 * RATE }])
  })

  it('never leaves a last segment shorter than the tail allowance', () => {
    for (const seconds of [31.2, 45, 60.9, 61.1, 90.4, 125]) {
      const segments = planSegments(steady(seconds), RATE, 30)
      const last = segments.at(-1)
      expect(last.end - last.start, `${seconds} s`).toBeGreaterThan(MINIMUM_TAIL_SECONDS * RATE)
    }
  })
})

describe('encodeWav', () => {
  it('writes the canonical 16-bit PCM mono header for the samples', () => {
    const view = new DataView(encodeWav(new Float32Array(10), RATE))

    expect(view.byteLength).toBe(44 + 20)
    expect(ascii(view, 0, 4)).toBe('RIFF')
    expect(view.getUint32(4, true)).toBe(36 + 20)
    expect(ascii(view, 8, 4)).toBe('WAVE')
    expect(ascii(view, 12, 4)).toBe('fmt ')
    expect(view.getUint32(16, true)).toBe(16)
    expect(view.getUint16(20, true)).toBe(1) // PCM
    expect(view.getUint16(22, true)).toBe(1) // mono
    expect(view.getUint32(24, true)).toBe(RATE)
    expect(view.getUint32(28, true)).toBe(RATE * 2)
    expect(view.getUint16(32, true)).toBe(2)
    expect(view.getUint16(34, true)).toBe(16)
    expect(ascii(view, 36, 4)).toBe('data')
    expect(view.getUint32(40, true)).toBe(20)
  })

  it('scales the samples to 16 bits and clamps anything past full scale', () => {
    const view = new DataView(encodeWav(Float32Array.from([0, 1, -1, 0.5, 2, -2]), RATE))
    const sample = (index) => view.getInt16(44 + index * 2, true)

    expect([sample(0), sample(1), sample(2), sample(3)]).toEqual([0, 32767, -32768, 16384])
    expect([sample(4), sample(5)]).toEqual([32767, -32768])
  })
})

describe('appendToDraft', () => {
  it('starts the draft with the first text, and puts a blank line before each after it', () => {
    expect(appendToDraft('', ' Good morning. ')).toBe('Good morning.')
    expect(appendToDraft('Good morning.', 'The budget is agreed.')).toBe('Good morning.\n\nThe budget is agreed.')
  })

  it('adds nothing for an empty text, so a quiet segment leaves no gap', () => {
    expect(appendToDraft('Good morning.', '   ')).toBe('Good morning.')
    expect(appendToDraft('Good morning.', '')).toBe('Good morning.')
  })
})

describe('draftFilename', () => {
  it('names the file after the meeting, safely', () => {
    expect(draftFilename('Q3 Planning: Budget & Risks')).toBe('q3-planning-budget-risks-transcript.txt')
    expect(draftFilename('  ')).toBe('meeting-transcript.txt')
  })
})
