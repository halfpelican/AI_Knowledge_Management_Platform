/**
 * A decoded meeting recording cut into the WAV segments the server transcribes
 * (D-123).
 *
 * The page decodes the recording in the browser (src/audio/decodeRecording.js),
 * then these pure functions mix it to mono, choose where to cut it and encode each
 * piece as a 16-bit PCM WAV, which is all `POST /api/transcriptions` accepts. Pure,
 * with no browser API and no React, so each is exercised on its own with numbers.
 *
 * **Why the browser cuts it.** At FLM's measured 0.24–0.31x real time an hour's
 * recording is a quarter of an hour of transcription; in one request that would
 * hold a server thread throughout and lose everything to a failure near the end.
 * Nothing in the server's stack decodes MP4, M4A or MP3, and the browser decodes
 * them all.
 *
 * **Where it cuts.** At most `segmentSeconds` per segment, and within that, at the
 * quietest tenth of a second in the segment's last third, so a cut rarely falls
 * inside a word: Whisper hears each segment on its own, and a word split in two is
 * a word misheard twice. A recording is cut only while more than a segment and
 * MINIMUM_TAIL_SECONDS remain, so the last segment may run up to that much over
 * the length rather than leave a sliver to be sent alone; the server's longer
 * ceiling (`maximum_segment_seconds`, 60) admits it.
 */

/** Where in a segment the search for a quiet cut begins, as a fraction of its length. */
export const CUT_SEARCH_FROM = 2 / 3
/** The length of the quiet stretch a cut is placed in, in seconds. */
export const CUT_WINDOW_SECONDS = 0.1
/** How far, in seconds, the last segment may run over the length rather than leave a sliver. */
export const MINIMUM_TAIL_SECONDS = 1

/**
 * One channel from several, by averaging them sample by sample.
 *
 * @param {Float32Array[]} channels Equal-length channels, as `AudioBuffer.getChannelData` gives them.
 * @returns {Float32Array}
 */
export function mixToMono(channels) {
  if (channels.length === 0) return new Float32Array(0)
  if (channels.length === 1) return channels[0]
  const length = channels[0].length
  const mono = new Float32Array(length)
  for (const channel of channels) {
    for (let i = 0; i < length; i += 1) mono[i] += channel[i]
  }
  for (let i = 0; i < length; i += 1) mono[i] /= channels.length
  return mono
}

/** The mean of the squares of `samples[start..end)`: loudness, without the square root. */
function meanSquare(samples, start, end) {
  let sum = 0
  for (let i = start; i < end; i += 1) sum += samples[i] * samples[i]
  return end > start ? sum / (end - start) : 0
}

/**
 * Where to cut a recording: consecutive `{start, end}` sample ranges covering all
 * of it, none longer than `segmentSeconds` except the last, which may run up to
 * MINIMUM_TAIL_SECONDS over it, and none shorter than MINIMUM_TAIL_SECONDS unless
 * the whole recording is.
 *
 * @param {Float32Array} samples The mono samples, to find the quiet places in.
 * @param {number} sampleRate In hertz.
 * @param {number} segmentSeconds The most a segment holds, from the server's status.
 * @returns {{start: number, end: number}[]}
 */
export function planSegments(samples, sampleRate, segmentSeconds) {
  const total = samples.length
  const target = Math.max(1, Math.round(segmentSeconds * sampleRate))
  const window = Math.max(1, Math.round(CUT_WINDOW_SECONDS * sampleRate))
  const tail = Math.round(MINIMUM_TAIL_SECONDS * sampleRate)
  const segments = []
  let start = 0
  // A cut falls at most `target` in, so while more than target + tail remain, what
  // is left after it is always longer than the tail.
  while (total - start > target + tail) {
    const searchFrom = start + Math.floor(target * CUT_SEARCH_FROM)
    const searchTo = start + target
    let cut = searchTo
    let quietest = Infinity
    for (let windowStart = searchFrom; windowStart + window <= searchTo; windowStart += window) {
      const level = meanSquare(samples, windowStart, windowStart + window)
      if (level < quietest) {
        quietest = level
        cut = windowStart + Math.floor(window / 2)
      }
    }
    segments.push({ start, end: cut })
    start = cut
  }
  if (total > start) segments.push({ start, end: total })
  return segments
}

function writeAscii(view, offset, text) {
  for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i))
}

/**
 * A mono 16-bit PCM WAV of `samples`, each clamped to [-1, 1]: the canonical
 * 44-byte header (one `fmt ` chunk, one `data` chunk) and nothing else.
 *
 * @param {Float32Array} samples
 * @param {number} sampleRate In hertz.
 * @returns {ArrayBuffer}
 */
export function encodeWav(samples, sampleRate) {
  const dataBytes = samples.length * 2
  const buffer = new ArrayBuffer(44 + dataBytes)
  const view = new DataView(buffer)
  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataBytes, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true) // the fmt chunk's size
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // bytes per second
  view.setUint16(32, 2, true) // bytes per frame
  view.setUint16(34, 16, true) // bits per sample
  writeAscii(view, 36, 'data')
  view.setUint32(40, dataBytes, true)
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(44 + i * 2, sample < 0 ? Math.round(sample * 0x8000) : Math.round(sample * 0x7fff), true)
  }
  return buffer
}

/**
 * The draft with one more segment's text on the end, a blank line between them.
 * An empty text adds nothing, so a segment Whisper heard nothing in leaves no gap.
 *
 * @param {string} draft
 * @param {string} text
 * @returns {string}
 */
export function appendToDraft(draft, text) {
  const addition = (text ?? '').trim()
  if (!addition) return draft
  return draft.trim() ? `${draft.replace(/\s+$/, '')}\n\n${addition}` : addition
}

/**
 * A filename for the draft saved as text: the meeting title made safe for a
 * filename, or "meeting" when there is none.
 *
 * @param {string} title
 * @returns {string}
 */
export function draftFilename(title) {
  const stem = (title ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${stem || 'meeting'}-transcript.txt`
}
