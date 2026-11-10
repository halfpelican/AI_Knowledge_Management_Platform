"""apps/ingestion/audio.py: a recording segment read, bounded, measured and rebuilt (D-123).

The route's own behaviour is apps/api/tests/test_transcriptions.py. These are the reader's rules,
one at a time, against WAVs built in memory (audio_builders.py).
"""

import io
import math
import wave

import pytest

from apps.ai.testing import STUB_ASR_MODEL, stub_transcript_text
from apps.core.constants import (
    MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS,
    TRANSCRIPTION_SAMPLE_RATE,
    TRANSCRIPTION_SILENCE_DBFS,
)
from apps.ingestion import audio
from apps.ingestion.tests import audio_builders as build


def frames_of(wav: bytes) -> bytes:
    with wave.open(io.BytesIO(wav), "rb") as reader:
        return reader.readframes(reader.getnframes())


# --- What is read ---------------------------------------------------------------------------------


def test_a_mono_16_khz_segment_is_read_with_its_shape_and_level():
    segment = audio.read_segment(build.tone(2.0, rms_dbfs=-20.0))

    assert (segment.sample_rate, segment.channels, segment.frame_count) == (16_000, 1, 32_000)
    assert segment.duration_seconds == 2.0
    assert segment.loudest_window_dbfs == pytest.approx(-20.0, abs=0.1)
    assert not segment.silent


def test_a_stereo_segment_is_unsupported():
    """Only what the page sends is accepted: 16 kHz mono (the security review of 11 November)."""
    with pytest.raises(audio.UnsupportedAudio, match="only mono"):
        audio.read_segment(build.tone(1.0, channels=2))


@pytest.mark.parametrize("rate", [8_000, 22_050, 44_100, 48_000])
def test_any_rate_but_the_pages_is_unsupported(rate):
    assert rate != TRANSCRIPTION_SAMPLE_RATE
    with pytest.raises(audio.UnsupportedAudio, match="Hz"):
        audio.read_segment(build.tone(0.5, rate=rate))


# --- What is refused ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb" * 64, id="an MP3"),
        pytest.param(b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 64, id="an M4A"),
        pytest.param(b"Speaker 1: good morning, everyone.\n" * 4, id="text"),
        pytest.param(b"RIFF\x24\x00\x00\x00AVI LIST" + b"\x00" * 32, id="a RIFF that is not WAVE"),
        pytest.param(b"RIFF", id="four bytes"),
        pytest.param(b"", id="nothing"),
    ],
)
def test_anything_but_a_wav_is_unsupported(data):
    with pytest.raises(audio.UnsupportedAudio):
        audio.read_segment(data)


def test_a_wav_cut_off_inside_its_header_is_unsupported():
    with pytest.raises(audio.UnsupportedAudio):
        audio.read_segment(build.tone(1.0)[:30])


def test_an_8_bit_wav_is_unsupported():
    with pytest.raises(audio.UnsupportedAudio, match="8-bit"):
        audio.read_segment(build.wav_from_samples(build.tone_samples(0.5), width=1))


def test_a_float_wav_is_unsupported():
    with pytest.raises(audio.UnsupportedAudio):
        audio.read_segment(build.float_wav(0.5))


def test_three_channels_are_unsupported():
    samples = build.tone_samples(0.5) * 3
    with pytest.raises(audio.UnsupportedAudio, match="3 channels; only mono"):
        audio.read_segment(build.wav_from_samples(samples, channels=3))


def test_a_wav_with_no_frames_is_empty():
    with pytest.raises(audio.EmptyAudio):
        audio.read_segment(build.wav_from_samples([]))


def test_the_longest_segment_is_accepted_and_one_frame_more_is_too_long():
    frames = MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS * TRANSCRIPTION_SAMPLE_RATE
    assert audio.read_segment(build.steady_wav(frames)).duration_seconds == (
        MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS
    )
    with pytest.raises(audio.SegmentTooLong) as refused:
        audio.read_segment(build.steady_wav(frames + 1))
    assert refused.value.seconds > MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS


def test_a_long_upload_is_refused_having_read_one_frame_past_the_limit():
    """However much audio follows, the reader stops one frame past the longest segment, so a
    50 MB WAV costs no more memory or time than a 60 s one before it is refused."""
    frames = MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS * TRANSCRIPTION_SAMPLE_RATE
    with pytest.raises(audio.SegmentTooLong) as refused:
        audio.read_segment(build.steady_wav(frames * 5))
    assert refused.value.seconds == (frames + 1) / TRANSCRIPTION_SAMPLE_RATE


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(
            build.with_chunk_before_data(build.tone(0.5), b"LIST", 2**31, b"INFO"),
            id="a LIST chunk declaring 2 GB before the data",
        ),
        pytest.param(build.with_chunk_before_fmt(build.tone(0.5), b"JUNK", 2**32 - 1), id="JUNK before fmt"),
        pytest.param(build.with_fmt_size(build.tone(0.5), 2**32 - 1), id="a fmt chunk declaring 4 GB"),
    ],
)
def test_a_header_whose_chunk_runs_past_the_file_is_unsupported_not_a_crash(data):
    """Python 3.12's wave raises a bare RuntimeError for these, which reached the user as a 500
    and wrote a traceback per request until the security review of 11 November. Fuzzing 20,020
    corrupted headers that day raised nothing else that escaped."""
    with pytest.raises(audio.UnsupportedAudio):
        audio.read_segment(data)


# --- Silence --------------------------------------------------------------------------------------


def test_digital_silence_is_silent_at_minus_infinity():
    segment = audio.read_segment(build.silence(3.0))

    assert segment.loudest_window_dbfs == -math.inf
    assert segment.silent


def test_quiet_noise_below_the_threshold_is_silent():
    segment = audio.read_segment(build.noise(3.0, rms_dbfs=TRANSCRIPTION_SILENCE_DBFS - 15))

    assert segment.loudest_window_dbfs < TRANSCRIPTION_SILENCE_DBFS
    assert segment.silent


def test_noise_above_the_threshold_is_not_silent():
    segment = audio.read_segment(build.noise(3.0, rms_dbfs=TRANSCRIPTION_SILENCE_DBFS + 10))

    assert not segment.silent


def test_one_spoken_half_second_in_a_long_pause_is_enough_to_send_it():
    """The loudest window decides, not the average: a 30 s segment that is a pause with a short
    answer in it averages far below the threshold, and must still be transcribed."""
    segment = audio.read_segment(
        build.quiet_with_a_burst(30.0, burst_seconds=0.5, burst_rms_dbfs=-25.0)
    )

    assert not segment.silent


# --- What is sent ---------------------------------------------------------------------------------


def test_the_rebuilt_wav_carries_exactly_the_frames_that_were_measured():
    original = build.tone(1.5, rms_dbfs=-18.0)
    segment = audio.read_segment(original)

    assert frames_of(segment.wav) == frames_of(original)
    with wave.open(io.BytesIO(segment.wav), "rb") as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (1, 2, 16_000)


def test_a_chunk_after_the_data_is_not_carried_through():
    original = build.tone(1.0)
    segment = audio.read_segment(build.with_trailing_chunk(original))

    assert segment.wav == audio.read_segment(original).wav
    assert b"LIST" not in segment.wav


def test_a_header_that_overstates_its_frames_is_read_for_the_frames_present():
    original = build.tone(1.0)
    segment = audio.read_segment(build.with_declared_frames(original, 16_000 * 50))

    assert segment.frame_count == 16_000
    assert frames_of(segment.wav) == frames_of(original)


def test_a_header_that_understates_its_frames_is_read_and_sent_for_the_frames_it_declares():
    """The audio past the declared size is neither measured nor sent: what Whisper hears is
    exactly what the duration bound and the silence check saw."""
    original = build.tone(2.0)
    segment = audio.read_segment(build.with_declared_frames(original, 8_000))

    assert segment.frame_count == 8_000
    assert len(frames_of(segment.wav)) == 8_000 * 2


def test_transcribe_sends_the_rebuilt_wav_through_the_ai_service(stub_ai_service):
    segment = audio.read_segment(build.with_trailing_chunk(build.tone(1.0)))

    result = audio.transcribe(segment)

    assert result.text == stub_transcript_text(1)
    assert result.model == STUB_ASR_MODEL
    assert stub_ai_service.transcribe_calls == [(segment.wav, audio.SEGMENT_FILENAME)]


def test_transcribe_refuses_a_silent_segment_without_calling_the_service(stub_ai_service):
    segment = audio.read_segment(build.silence(1.0))

    with pytest.raises(ValueError):
        audio.transcribe(segment)
    assert stub_ai_service.transcribe_calls == []
