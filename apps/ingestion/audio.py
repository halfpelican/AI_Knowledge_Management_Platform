"""One recording segment: read, measured and, unless it is silent, transcribed (D-123).

The page decodes a meeting recording in the browser and posts it here one WAV segment at a time
(POST /api/transcriptions). This module is everything that happens to a segment between the
route's checks and its reply:

- **Read.** Only what the page sends is accepted: a 16-bit PCM mono WAV at
  TRANSCRIPTION_SAMPLE_RATE (16 kHz), which Python's ``wave`` reads. Nothing else is needed, and
  every other rate or channel count only makes a segment dearer to measure: the security review
  of 11 November measured a 60 s, 48 kHz stereo segment at about thirteen times the CPU of the
  page's own. The format is decided by the bytes, as FR-08 decides a document's, never by a
  filename or a declared type. A header ``wave`` cannot follow is refused as unsupported, whatever
  ``wave`` raised for it.
- **Bounded.** A segment longer than MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS is refused before its
  loudness is measured, so one request stays short, and no more than one frame past that limit is
  ever read from it. One with no frames at all is refused as empty.
- **Measured.** The loudest TRANSCRIPTION_SILENCE_WINDOW_SECONDS of the segment, in dBFS. Below
  TRANSCRIPTION_SILENCE_DBFS the segment is silent and goes no further: Whisper invents text from
  silence, as a silent track showed on 6 November ("E ai E ai...").
- **Rebuilt.** What is sent to the provider is a WAV rebuilt from exactly the frames that were
  measured, not the bytes that arrived. A header that understates its data, or extra chunks
  after it, cannot carry more audio past the duration bound or the silence check than they saw.
- **Transcribed** through ``apps.ai.get_ai_service().transcribe()`` (CLAUDE.md section 4), by
  ``transcribe``, which the route calls only for a segment that is not silent and only while it
  holds the user's transcription slot. The provider's own failures, ProviderUnavailable and its
  subclasses, propagate to the route.

**Nothing is stored.** No meeting, no chunk, no file and no row: the page holds the recording and
the draft, and a person submits the confirmed draft through FR-09's POST /api/meetings, the one
path into the index. So a failed transcription cannot discard anything here (invariant 8).
"""

import array
import io
import math
import sys
import wave
from dataclasses import dataclass

import apps.ai
from apps.ai.base import Transcription
from apps.core.constants import (
    MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS,
    TRANSCRIPTION_SAMPLE_RATE,
    TRANSCRIPTION_SILENCE_DBFS,
    TRANSCRIPTION_SILENCE_WINDOW_SECONDS,
)

# A WAV file is a RIFF container whose form type is WAVE: bytes 0-3 and 8-11.
RIFF_SIGNATURE = b"RIFF"
WAVE_FORM_TYPE = b"WAVE"
SAMPLE_WIDTH_BYTES = 2  # 16-bit PCM, the only width accepted
CHANNELS = 1  # mono, the only channel count accepted
# A 16-bit sample's full scale, for dBFS: 0 dBFS is a square wave at the largest magnitude.
FULL_SCALE = 32768.0
# The loudness of a segment with no signal at all: every sample zero.
DIGITAL_SILENCE_DBFS = float("-inf")
# What the rebuilt segment is called when it is sent.
SEGMENT_FILENAME = "segment.wav"


class UnsupportedAudio(ValueError):
    """Not a 16-bit PCM mono WAV at TRANSCRIPTION_SAMPLE_RATE, or not a WAV ``wave`` can read."""


class EmptyAudio(ValueError):
    """A WAV holding no audio frames."""


class SegmentTooLong(ValueError):
    """More audio than MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS. ``seconds`` is how much was read, which
    stops one frame past the limit: a lower bound on the segment's length, not its length."""

    def __init__(self, seconds: float):
        super().__init__(f"{seconds:.1f} s of audio, above {MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS} s")
        self.seconds = seconds


@dataclass(frozen=True)
class AudioSegment:
    """A segment as read: its shape, its loudest window, and the WAV rebuilt from its frames."""

    sample_rate: int
    channels: int
    frame_count: int
    loudest_window_dbfs: float
    wav: bytes

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate

    @property
    def silent(self) -> bool:
        return self.loudest_window_dbfs < TRANSCRIPTION_SILENCE_DBFS


def read_segment(data: bytes) -> AudioSegment:
    """Read, bound, measure and rebuild one segment. Raises UnsupportedAudio, EmptyAudio or
    SegmentTooLong."""
    if len(data) < 12 or data[:4] != RIFF_SIGNATURE or data[8:12] != WAVE_FORM_TYPE:
        raise UnsupportedAudio("not a WAV file")
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            rate = reader.getframerate()
            if width != SAMPLE_WIDTH_BYTES:
                raise UnsupportedAudio(f"{width * 8}-bit samples; only 16-bit PCM is accepted")
            if channels != CHANNELS:
                raise UnsupportedAudio(f"{channels} channels; only mono is accepted")
            if rate != TRANSCRIPTION_SAMPLE_RATE:
                raise UnsupportedAudio(f"{rate} Hz; only {TRANSCRIPTION_SAMPLE_RATE} Hz is accepted")
            # At most one frame past the longest segment is read, whatever the header declares
            # and however much data follows it, so a long upload costs no more memory or time
            # than the longest segment before it is refused.
            longest = MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS * rate
            raw = reader.readframes(longest + 1)
    except (wave.Error, EOFError, RuntimeError) as exc:
        # wave.Error covers a WAV whose encoding is not PCM, a missing fmt or data chunk and a
        # malformed chunk; EOFError a file cut off inside its header. RuntimeError is what
        # Python 3.12's wave raises, bare, when a chunk before the data declares a size past the
        # end of the file (its _Chunk.seek), which a truncated recording's LIST chunk can do: a
        # 500 until the security review of 11 November found it. 20,020 corrupted headers fuzzed
        # that day raised nothing else; apps/ingestion/tests/test_audio.py keeps the cases.
        raise UnsupportedAudio(f"not a readable PCM WAV ({exc!r})") from exc

    # The frames actually present, which a header can overstate; a trailing partial frame is
    # dropped.
    frame_bytes = SAMPLE_WIDTH_BYTES * channels
    frame_count = len(raw) // frame_bytes
    if frame_count == 0:
        raise EmptyAudio("the segment holds no audio")
    if frame_count > longest:
        raise SegmentTooLong(frame_count / rate)

    raw = raw[: frame_count * frame_bytes]
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder == "big":
        samples.byteswap()  # WAV is little-endian
    window = max(1, round(rate * TRANSCRIPTION_SILENCE_WINDOW_SECONDS)) * channels
    return AudioSegment(
        sample_rate=rate,
        channels=channels,
        frame_count=frame_count,
        loudest_window_dbfs=loudest_window_dbfs(samples, window),
        wav=_rebuild(raw, rate, channels),
    )


def loudest_window_dbfs(samples: array.array, window: int) -> float:
    """The RMS level of the loudest run of ``window`` samples, in dBFS; -inf if all are zero.

    Consecutive, non-overlapping runs; the last may be shorter. Stereo samples are interleaved, so
    a run of ``window`` samples spans both channels, which is what loudness for this purpose
    wants: a segment is silent only if neither channel carries anything.
    """
    loudest = 0.0
    for start in range(0, len(samples), window):
        run = samples[start : start + window]
        loudest = max(loudest, math.sumprod(run, run) / len(run))
    if loudest == 0:
        return DIGITAL_SILENCE_DBFS
    return 10 * math.log10(loudest / (FULL_SCALE * FULL_SCALE))


def _rebuild(raw: bytes, rate: int, channels: int) -> bytes:
    """A canonical WAV of exactly ``raw``: one fmt chunk and one data chunk, nothing else."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(SAMPLE_WIDTH_BYTES)
        writer.setframerate(rate)
        writer.writeframes(raw)
    return buffer.getvalue()


def transcribe(segment: AudioSegment) -> Transcription:
    """The text of a segment ``read_segment`` admitted, through the AI service. Stores nothing.

    Refuses a silent segment with ValueError rather than sending it: the caller answers a silent
    segment itself, and a silent one reaching here is a caller's bug that would otherwise spend
    NPU time inviting invention. The provider's ProviderUnavailable (TranscriptionDisabled and
    ProviderRefused included) propagates.
    """
    if segment.silent:
        raise ValueError("a silent segment is never sent for transcription")
    return apps.ai.get_ai_service().transcribe(segment.wav, filename=SEGMENT_FILENAME)
