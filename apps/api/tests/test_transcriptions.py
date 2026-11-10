"""Recording transcription's routes, the status and the segment (D-123; docs/api-contract.md,
"Recording transcription").

``GET /api/transcriptions/status`` and ``POST /api/transcriptions``: a session and
``contribute_content`` on both (FR-06), every test that can run from both roles runs from both
(``session_client``; CLAUDE.md section 8, Objective 01). The stub stands in for FLM (conftest.py),
and transcription is off unless a test turns it on with the ``transcription_on`` fixture, because
conftest.py pins ``TRANSCRIPTION_PROVIDER`` to ``none`` whatever a developer's .env says.

What they hold, enumerated:

- the happy path: a segment's text and the model, from the stub, sent the rebuilt WAV;
- nothing is stored: no meeting, no chunk, by any outcome;
- silence: answered ``silent`` with no provider call, for digital silence and for quiet noise;
- the refusals: 401, 403, 503 ``transcription_disabled``, 413 on the declared length, 400 with no
  ``audio``, 415 for anything but a 16-bit PCM mono WAV at 16 kHz, 400 for an empty or over-long
  segment, and the parser's 415 for JSON; and the 403 and 413 again from a session that sends its
  CSRF token, as the page does, which has its body parsed during authentication;
- the provider failing: NFR-19's 503 ``transcription_unavailable`` for an outage and for a
  refusal, nothing stored, the user's slot released;
- one segment in flight per user: 429 ``transcription_in_flight`` while it is held, and a silent
  or refused segment answered without it; and MAXIMUM_TRANSCRIPTIONS_IN_FLIGHT across the server:
  429 ``transcription_busy`` with Retry-After while every server slot is held;
- CSRF on a session that does not send the token;
- the status route's two flags and its segment lengths.

The throttle is apps/api/tests/test_throttles.py's, with the other scopes.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import RolePermission
from apps.ai.base import ProviderRefused, ProviderUnavailable, TranscriptionDisabled
from apps.ai.testing import STUB_ASR_MODEL, stub_transcript_text
from apps.api.transcription_slot import (
    server_slot_key,
    take_server_slot,
    take_transcription_slot,
    transcription_slot_key,
)
from apps.api.views import (
    EMPTY_AUDIO_MESSAGE,
    FILE_TOO_LARGE_MESSAGE,
    NO_AUDIO_SUBMITTED_MESSAGE,
    SEGMENT_TOO_LONG_MESSAGE,
    TRANSCRIPTION_DISABLED_CODE,
    TRANSCRIPTION_BUSY_CODE,
    TRANSCRIPTION_BUSY_MESSAGE,
    TRANSCRIPTION_DISABLED_MESSAGE,
    TRANSCRIPTION_IN_FLIGHT_CODE,
    TRANSCRIPTION_UNAVAILABLE_CODE,
    TRANSCRIPTION_UNAVAILABLE_MESSAGE,
    UNSUPPORTED_AUDIO_MESSAGE,
)
from apps.core.constants import (
    CONTRIBUTE_CONTENT_PERMISSION,
    MAX_UPLOAD_BYTES,
    MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS,
    MAXIMUM_TRANSCRIPTIONS_IN_FLIGHT,
    TRANSCRIPTION_BUSY_RETRY_SECONDS,
    TRANSCRIPTION_SAMPLE_RATE,
    TRANSCRIPTION_SEGMENT_SECONDS,
    TRANSCRIPTION_SILENCE_DBFS,
)
from apps.documents.models import ContentChunk
from apps.ingestion import audio
from apps.ingestion.tests import audio_builders as build
from apps.meetings.models import Meeting

pytestmark = pytest.mark.django_db

TRANSCRIPTIONS_URL = "/api/transcriptions"
STATUS_URL = "/api/transcriptions/status"


@pytest.fixture
def transcription_on():
    with override_settings(TRANSCRIPTION_PROVIDER="flm"):
        yield


def segment_file(data: bytes, name="segment.wav", content_type="audio/wav"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def post_segment(client, data=None, **extra):
    body = {} if data is None else {"audio": segment_file(data)}
    return client.post(TRANSCRIPTIONS_URL, body, format="multipart", **extra)


def revoke_contribute_content(user):
    RolePermission.objects.filter(
        role=user.role, permission__permission_name=CONTRIBUTE_CONTENT_PERMISSION
    ).delete()


def raising(exc):
    """A stub transcription override that raises ``exc``, as a failing provider does."""

    def fail(audio_bytes, filename):
        raise exc

    return fail


def assert_nothing_stored(chunks_before=0):
    assert not Meeting.objects.exists()
    assert ContentChunk.objects.count() == chunks_before


# --- The happy path -------------------------------------------------------------------------------


def test_a_segment_is_transcribed(session_client, transcription_on, stub_ai_service):
    original = build.tone(2.0)

    response = post_segment(session_client.client, original)

    assert response.status_code == 200, response.content
    body = response.json()
    assert body == {
        "status": "transcribed",
        "text": stub_transcript_text(1),
        "model": STUB_ASR_MODEL,
        "duration_seconds": 2.0,
        "loudest_dbfs": body["loudest_dbfs"],
    }
    # The level the silence rule compared: the tone was built at -20 dBFS.
    assert body["loudest_dbfs"] == pytest.approx(-20.0, abs=0.2)
    # The provider was sent the WAV rebuilt from the frames that were measured.
    assert stub_ai_service.transcribe_calls == [
        (audio.read_segment(original).wav, audio.SEGMENT_FILENAME)
    ]


def test_successive_segments_come_back_in_the_order_sent(employee_client, transcription_on):
    texts = [post_segment(employee_client, build.tone(1.0)).json()["text"] for _ in range(3)]

    assert texts == [stub_transcript_text(n) for n in (1, 2, 3)]


def test_a_transcribed_segment_stores_nothing(employee_client, transcription_on, content_chunk):
    chunks_before = ContentChunk.objects.count()

    assert post_segment(employee_client, build.tone(1.0)).status_code == 200

    assert not Meeting.objects.exists()
    assert ContentChunk.objects.count() == chunks_before


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(build.tone(1.0, channels=2), id="stereo"),
        pytest.param(build.tone(1.0, rate=44_100), id="44.1 kHz"),
    ],
)
def test_anything_but_what_the_page_sends_is_415(employee_client, transcription_on, stub_ai_service, data):
    """16 kHz mono only: the page sends nothing else, and a wider range only made a segment
    dearer to measure (the security review of 11 November)."""
    response = post_segment(employee_client, data)

    assert response.status_code == 415
    assert stub_ai_service.transcribe_calls == []


# --- Silence never reaches the provider -----------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(build.silence(5.0), id="digital silence"),
        pytest.param(build.noise(5.0, rms_dbfs=TRANSCRIPTION_SILENCE_DBFS - 15), id="quiet noise"),
    ],
)
def test_a_silent_segment_is_answered_without_a_provider_call(
    session_client, transcription_on, stub_ai_service, data
):
    response = post_segment(session_client.client, data)

    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in ("status", "text", "model", "duration_seconds")} == {
        "status": "silent", "text": "", "model": None, "duration_seconds": 5.0,
    }
    # Null for digital silence, which JSON cannot write as minus infinity; a level below the
    # threshold otherwise.
    assert body["loudest_dbfs"] is None or body["loudest_dbfs"] < TRANSCRIPTION_SILENCE_DBFS
    assert stub_ai_service.transcribe_calls == []
    assert_nothing_stored()


# --- Refused before the provider ------------------------------------------------------------------


def test_an_anonymous_caller_is_unauthorised(api_client, transcription_on):
    assert post_segment(api_client, build.tone(1.0)).status_code == 401
    assert api_client.get(STATUS_URL).status_code == 401


def test_a_role_without_contribute_content_is_forbidden(session_client, transcription_on, stub_ai_service):
    revoke_contribute_content(session_client.user)

    assert post_segment(session_client.client, build.tone(1.0)).status_code == 403
    assert session_client.client.get(STATUS_URL).status_code == 403
    assert stub_ai_service.transcribe_calls == []


def test_with_transcription_off_a_segment_is_503_and_reaches_no_provider(session_client, stub_ai_service):
    # No audio at all: the refusal does not need any.
    response = post_segment(session_client.client)

    assert response.status_code == 503
    assert response.json() == {
        "detail": TRANSCRIPTION_DISABLED_MESSAGE,
        "code": TRANSCRIPTION_DISABLED_CODE,
    }
    assert stub_ai_service.transcribe_calls == []


def test_a_declared_length_over_the_ceiling_is_413(session_client, transcription_on):
    response = post_segment(
        session_client.client, build.tone(1.0), CONTENT_LENGTH=str(MAX_UPLOAD_BYTES + 1)
    )

    assert response.status_code == 413
    assert response.json() == {"detail": FILE_TOO_LARGE_MESSAGE}


def test_a_segment_over_the_ceiling_is_413(employee_client, transcription_on, stub_ai_service, monkeypatch):
    """The ceiling is lowered rather than 50 MB sent. The second check, against the bytes that
    arrived, is the document upload's own defence for a client that understates its length; the
    test client always declares the true length, so it cannot reach that line, and neither does
    the upload's own suite."""
    small_ceiling = 1000
    monkeypatch.setattr("apps.api.views.MAX_UPLOAD_BYTES", small_ceiling)
    data = build.tone(1.0)
    assert len(data) > small_ceiling

    response = post_segment(employee_client, data)

    assert response.status_code == 413
    assert stub_ai_service.transcribe_calls == []


def test_no_audio_part_is_400(session_client, transcription_on):
    response = post_segment(session_client.client)

    assert response.status_code == 400
    assert response.json() == {"audio": [NO_AUDIO_SUBMITTED_MESSAGE]}


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb" * 64, id="an MP3"),
        pytest.param(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64, id="an MP4"),
        pytest.param(b"Speaker 1: good morning.\n", id="a transcript"),
        pytest.param(build.wav_from_samples(build.tone_samples(0.5), width=1), id="an 8-bit WAV"),
        pytest.param(build.float_wav(0.5), id="a float WAV"),
    ],
)
def test_anything_but_a_16_bit_pcm_wav_is_415(session_client, transcription_on, stub_ai_service, data):
    response = post_segment(session_client.client, data)

    assert response.status_code == 415
    assert response.json() == {"detail": UNSUPPORTED_AUDIO_MESSAGE}
    assert stub_ai_service.transcribe_calls == []


def test_a_segment_disguised_by_its_name_is_still_judged_by_its_bytes(employee_client, transcription_on):
    response = employee_client.post(
        TRANSCRIPTIONS_URL,
        {"audio": segment_file(b"Speaker 1: hello.\n" * 8, name="meeting.wav", content_type="audio/wav")},
        format="multipart",
    )

    assert response.status_code == 415


def test_an_empty_segment_is_400(session_client, transcription_on):
    response = post_segment(session_client.client, build.wav_from_samples([]))

    assert response.status_code == 400
    assert response.json() == {"audio": [EMPTY_AUDIO_MESSAGE]}


def test_a_segment_over_the_longest_is_400(session_client, transcription_on, stub_ai_service):
    data = build.steady_wav(MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS * TRANSCRIPTION_SAMPLE_RATE + 1)

    response = post_segment(session_client.client, data)

    assert response.status_code == 400
    assert response.json() == {"audio": [SEGMENT_TOO_LONG_MESSAGE]}
    assert stub_ai_service.transcribe_calls == []


def test_a_json_body_is_415(employee_client, transcription_on):
    response = employee_client.post(TRANSCRIPTIONS_URL, {"audio": "UklGRg=="}, format="json")

    assert response.status_code == 415


def test_a_session_without_the_csrf_token_is_refused(employee, transcription_on):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(employee)

    response = post_segment(client, build.tone(1.0))

    assert response.status_code == 403


def csrf_session(user):
    """A session that sends its CSRF token, as the page does: the cookie from GET /api/auth/me, and
    the token in X-CSRFToken on every POST. DRF parses such a request's body while it checks the
    token, before the permission and the size checks (the security review of 11 November)."""
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.get("/api/auth/me").status_code == 200
    return client, {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


def test_a_session_sending_its_token_is_answered_as_any_other(session_client, transcription_on, stub_ai_service):
    client, token = csrf_session(session_client.user)

    response = post_segment(client, build.tone(1.0), **token)

    assert response.status_code == 200
    assert response.json()["status"] == "transcribed"


def test_a_session_sending_its_token_still_gets_the_403_and_the_413(
    session_client, transcription_on, stub_ai_service, monkeypatch
):
    """The answers keep their order with CSRF enforced; what the order does not do is spare the
    parse (D-123, "What it does not cover"). That shows here too: a declared length larger than the
    bytes sent, which the plain client's 413 test uses, cannot be sent with the token, because DRF
    reads the whole declared body while checking it. So the ceiling is lowered and a real body sent
    over it."""
    client, token = csrf_session(session_client.user)
    monkeypatch.setattr("apps.api.views.MAX_UPLOAD_BYTES", 1000)
    oversized = post_segment(client, build.tone(1.0), **token)
    monkeypatch.undo()
    revoke_contribute_content(session_client.user)
    forbidden = post_segment(client, build.tone(1.0), **token)

    assert oversized.status_code == 413
    assert forbidden.status_code == 403
    assert stub_ai_service.transcribe_calls == []


# --- The provider failing (NFR-19, D-118, invariant 8) --------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(ProviderUnavailable("FLM unreachable"), id="an outage"),
        pytest.param(ProviderRefused("FLM returned HTTP 400"), id="a refusal"),
    ],
)
def test_a_provider_failure_is_503_and_stores_nothing(
    session_client, transcription_on, stub_ai_service, failure
):
    def fail(audio_bytes, filename):
        raise failure

    stub_ai_service.transcription = fail

    response = post_segment(session_client.client, build.tone(1.0))

    assert response.status_code == 503
    assert response.json() == {
        "detail": TRANSCRIPTION_UNAVAILABLE_MESSAGE,
        "code": TRANSCRIPTION_UNAVAILABLE_CODE,
    }
    assert len(stub_ai_service.transcribe_calls) == 1
    assert_nothing_stored()


def test_a_failed_segment_can_be_sent_again_once_the_provider_is_back(
    employee_client, transcription_on, stub_ai_service
):
    """The page resumes by sending the same segment again: the failure left no slot held and
    nothing that a second attempt could collide with."""
    stub_ai_service.transcription = raising(ProviderUnavailable("down"))
    data = build.tone(1.0)
    assert post_segment(employee_client, data).status_code == 503

    stub_ai_service.transcription = None
    response = post_segment(employee_client, data)

    assert response.status_code == 200
    assert response.json()["text"] == stub_transcript_text(2)


def test_a_disabled_provider_mid_request_is_answered_as_disabled(
    employee_client, transcription_on, stub_ai_service
):
    stub_ai_service.transcription = raising(TranscriptionDisabled("off"))

    response = post_segment(employee_client, build.tone(1.0))

    assert response.status_code == 503
    assert response.json()["code"] == TRANSCRIPTION_DISABLED_CODE


def test_the_503_is_logged_naming_the_account(employee, employee_client, transcription_on, stub_ai_service, caplog):
    stub_ai_service.transcription = raising(ProviderUnavailable("FLM unreachable"))

    with caplog.at_level("WARNING", logger="apps.ai.attempts"):
        post_segment(employee_client, build.tone(1.0))

    assert any(
        record.getMessage().startswith(f"POST /api/transcriptions answered 503 (account {employee.pk})")
        for record in caplog.records
    )


# --- One segment in flight per user ---------------------------------------------------------------


def test_a_second_segment_while_one_is_in_flight_is_429(session_client, transcription_on, stub_ai_service):
    take_transcription_slot(session_client.user)

    response = post_segment(session_client.client, build.tone(1.0))

    assert response.status_code == 429
    assert response.json()["code"] == TRANSCRIPTION_IN_FLIGHT_CODE
    assert stub_ai_service.transcribe_calls == []


def test_a_silent_or_refused_segment_needs_no_slot(employee, employee_client, transcription_on):
    take_transcription_slot(employee)

    assert post_segment(employee_client, build.silence(1.0)).json()["status"] == "silent"
    assert post_segment(employee_client, b"not audio").status_code == 415


def test_one_users_slot_is_not_anothers(employee, administrator_client, transcription_on):
    take_transcription_slot(employee)

    assert post_segment(administrator_client, build.tone(1.0)).status_code == 200


def test_every_server_slot_held_is_429_busy_with_retry_after(
    employee, administrator, employee_client, transcription_on, stub_ai_service
):
    """MAXIMUM_TRANSCRIPTIONS_IN_FLIGHT across every user: other people's segments are with FLM, so
    this one is refused at once, with its own words and a time to try again, and costs nothing."""
    from django.core.cache import cache

    held = [take_server_slot() for _ in range(MAXIMUM_TRANSCRIPTIONS_IN_FLIGHT)]
    assert all(held) and take_server_slot() is None

    response = post_segment(employee_client, build.tone(1.0))

    assert response.status_code == 429
    assert response.json() == {"detail": TRANSCRIPTION_BUSY_MESSAGE, "code": TRANSCRIPTION_BUSY_CODE}
    assert response["Retry-After"] == str(TRANSCRIPTION_BUSY_RETRY_SECONDS)
    assert stub_ai_service.transcribe_calls == []
    # The user's own slot was given back, so the segment goes as soon as a server slot is free.
    assert cache.get(transcription_slot_key(employee)) is None
    cache.delete(server_slot_key(0))
    assert post_segment(employee_client, build.tone(1.0)).status_code == 200


def test_a_silent_segment_needs_no_server_slot(employee_client, transcription_on):
    for _ in range(MAXIMUM_TRANSCRIPTIONS_IN_FLIGHT):
        take_server_slot()

    assert post_segment(employee_client, build.silence(1.0)).json()["status"] == "silent"


def test_the_slot_is_released_after_a_success_and_after_a_failure(
    employee, employee_client, transcription_on, stub_ai_service
):
    from django.core.cache import cache

    def all_free():
        return cache.get(transcription_slot_key(employee)) is None and all(
            cache.get(server_slot_key(index)) is None for index in range(MAXIMUM_TRANSCRIPTIONS_IN_FLIGHT)
        )

    assert post_segment(employee_client, build.tone(1.0)).status_code == 200
    assert all_free()

    stub_ai_service.transcription = raising(ProviderUnavailable("down"))
    assert post_segment(employee_client, build.tone(1.0)).status_code == 503
    assert all_free()


# --- The status route -----------------------------------------------------------------------------


def test_the_status_says_transcription_is_off_by_default(session_client, stub_ai_service):
    response = session_client.client.get(STATUS_URL)

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "available": False,
        "segment_seconds": TRANSCRIPTION_SEGMENT_SECONDS,
        "maximum_segment_seconds": MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS,
    }


def test_the_status_says_available_when_the_provider_answers(session_client, transcription_on):
    body = session_client.client.get(STATUS_URL).json()

    assert (body["enabled"], body["available"]) == (True, True)


def test_the_status_says_unavailable_when_the_provider_does_not_answer(
    session_client, transcription_on, stub_ai_service
):
    stub_ai_service.transcription_available = False

    body = session_client.client.get(STATUS_URL).json()

    assert (body["enabled"], body["available"]) == (True, False)


def test_the_status_discloses_no_provider_detail(employee_client, transcription_on, stub_ai_service):
    stub_ai_service.transcription_available = False

    body = employee_client.get(STATUS_URL).json()

    assert set(body) == {"enabled", "available", "segment_seconds", "maximum_segment_seconds"}


def test_the_page_segment_length_is_within_what_the_server_accepts():
    assert TRANSCRIPTION_SEGMENT_SECONDS < MAXIMUM_TRANSCRIPTION_SEGMENT_SECONDS
