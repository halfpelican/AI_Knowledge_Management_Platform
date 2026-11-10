"""WAV segments built in memory for the recording-transcription tests (D-123).

Every level is stated as an RMS level in dBFS, the unit apps/ingestion/audio.py measures and
TRANSCRIPTION_SILENCE_DBFS is written in, so a test reads as "a tone at -20 dBFS" rather than as
an amplitude. A sine's RMS is its peak over the square root of two, which ``tone`` accounts for.
Built with the standard library alone, as the code under test is.
"""

import array
import io
import math
import random
import struct
import sys
import wave

from apps.core.constants import TRANSCRIPTION_SAMPLE_RATE

FULL_SCALE = 32768.0
LARGEST_SAMPLE = 32767


def wav_from_samples(samples, *, rate=TRANSCRIPTION_SAMPLE_RATE, channels=1, width=2) -> bytes:
    """A WAV of ``samples``, interleaved when ``channels`` is 2. 16-bit unless ``width`` says not."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        if width == 2:
            data = array.array("h", samples)
            if sys.byteorder == "big":
                data.byteswap()
            writer.writeframes(data.tobytes())
        else:
            # 8-bit WAV is unsigned: 128 is zero.
            writer.writeframes(bytes(128 + (sample >> 8) for sample in samples))
    return buffer.getvalue()


def _amplitude(rms_dbfs: float) -> float:
    return FULL_SCALE * (10 ** (rms_dbfs / 20))


def tone_samples(seconds, *, rms_dbfs=-20.0, frequency=440.0, rate=TRANSCRIPTION_SAMPLE_RATE):
    peak = min(LARGEST_SAMPLE, _amplitude(rms_dbfs) * math.sqrt(2))
    count = round(seconds * rate)
    return [round(peak * math.sin(2 * math.pi * frequency * n / rate)) for n in range(count)]


def tone(seconds, *, rms_dbfs=-20.0, rate=TRANSCRIPTION_SAMPLE_RATE, channels=1) -> bytes:
    """A sine at ``rms_dbfs``: loud enough to stand for speech at the default level."""
    mono = tone_samples(seconds, rms_dbfs=rms_dbfs, rate=rate)
    if channels == 1:
        return wav_from_samples(mono, rate=rate)
    return wav_from_samples([s for sample in mono for s in (sample, sample)], rate=rate, channels=2)


def silence(seconds, *, rate=TRANSCRIPTION_SAMPLE_RATE, channels=1) -> bytes:
    """Digital silence: every sample zero, as the silent Game Bar track of 6 November was in effect."""
    return wav_from_samples([0] * (round(seconds * rate) * channels), rate=rate, channels=channels)


def noise(seconds, *, rms_dbfs, rate=TRANSCRIPTION_SAMPLE_RATE, seed=8) -> bytes:
    """Uniform noise at ``rms_dbfs``, seeded so every run builds the same bytes."""
    rng = random.Random(seed)
    # A uniform distribution on [-a, a] has an RMS of a / sqrt(3).
    bound = min(LARGEST_SAMPLE, _amplitude(rms_dbfs) * math.sqrt(3))
    count = round(seconds * rate)
    return wav_from_samples([round(rng.uniform(-bound, bound)) for _ in range(count)], rate=rate)


def quiet_with_a_burst(seconds, *, burst_seconds, burst_rms_dbfs, rate=TRANSCRIPTION_SAMPLE_RATE) -> bytes:
    """Digital silence with one tone burst in the middle: a segment that is mostly a pause."""
    total = round(seconds * rate)
    burst = tone_samples(burst_seconds, rms_dbfs=burst_rms_dbfs, rate=rate)
    start = (total - len(burst)) // 2
    samples = [0] * total
    samples[start : start + len(burst)] = burst
    return wav_from_samples(samples, rate=rate)


def steady_wav(frames: int, *, value=1000, rate=TRANSCRIPTION_SAMPLE_RATE) -> bytes:
    """``frames`` mono frames all at ``value``, built from repeated bytes so a long one is quick."""
    return wav_bytes_from_pcm(struct.pack("<h", value) * frames, rate=rate)


def wav_bytes_from_pcm(pcm: bytes, *, rate=TRANSCRIPTION_SAMPLE_RATE, channels=1) -> bytes:
    """A 16-bit WAV around little-endian ``pcm`` as given."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm)
    return buffer.getvalue()


def with_chunk_before_data(wav: bytes, chunk_id: bytes, declared_size: int, payload: bytes = b"") -> bytes:
    """``wav`` with a chunk between its fmt and data chunks declaring ``declared_size`` bytes,
    whatever it holds. A size past the end of the file is what makes Python 3.12's wave raise a
    bare RuntimeError (the security review of 11 November, finding 3)."""
    assert wav[36:40] == b"data", "expected the canonical 44-byte header"
    return wav[:36] + chunk_id + struct.pack("<I", declared_size) + payload + wav[36:]


def with_chunk_before_fmt(wav: bytes, chunk_id: bytes, declared_size: int) -> bytes:
    """``wav`` with a chunk straight after the WAVE form type, before fmt."""
    return wav[:12] + chunk_id + struct.pack("<I", declared_size) + wav[12:]


def with_fmt_size(wav: bytes, declared_size: int) -> bytes:
    """``wav`` with its fmt chunk declaring ``declared_size`` bytes."""
    assert wav[12:16] == b"fmt "
    return wav[:16] + struct.pack("<I", declared_size) + wav[20:]


def with_declared_frames(wav: bytes, frames: int) -> bytes:
    """``wav`` with its data chunk's declared size rewritten to ``frames`` mono 16-bit frames.

    For a header that overstates or understates its data. Assumes the canonical 44-byte header
    ``wave`` writes, whose data chunk size sits at bytes 40-43.
    """
    assert wav[36:40] == b"data", "expected the canonical 44-byte header"
    return wav[:40] + struct.pack("<I", frames * 2) + wav[44:]


def with_trailing_chunk(wav: bytes, chunk_id: bytes = b"LIST", payload: bytes = b"INFOjunk") -> bytes:
    """``wav`` with another chunk after its data, and the RIFF size grown to cover it."""
    chunk = chunk_id + struct.pack("<I", len(payload)) + payload
    riff_size = struct.unpack("<I", wav[4:8])[0] + len(chunk)
    return wav[:4] + struct.pack("<I", riff_size) + wav[8:] + chunk


def float_wav(seconds, *, rate=TRANSCRIPTION_SAMPLE_RATE) -> bytes:
    """A 32-bit IEEE float WAV (format tag 3), which ``wave`` does not read and the route refuses."""
    count = round(seconds * rate)
    data = struct.pack(f"<{count}f", *([0.1] * count))
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body
