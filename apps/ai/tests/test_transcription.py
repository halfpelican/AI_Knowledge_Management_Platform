"""AIService.transcribe and transcription_health, on both providers and the stub (D-123).

Both providers send a segment to FLM's ``/v1/audio/transcriptions``, because only FLM has
speech-to-text; apps/ai/transcription.py holds the call and its attempt policy once. These tests
drive it against an in-process mock of the OpenAI wire format, as test_flm.py does: no live server.

What they hold:

- the request: one multipart POST to ``/audio/transcriptions`` with FLM_ASR_MODEL, English, JSON
  and the segment as a WAV part, carrying TRANSCRIPTION_TIMEOUT_SECONDS;
- the attempt policy: MAXIMUM_TRANSCRIBE_ATTEMPTS calls (1 initial call + 2 retries) for a 5xx, a
  429, a refused connection or a 200 with no text, then ProviderUnavailable; one call for any
  other 4xx, then ProviderRefused (D-118);
- the setting: with TRANSCRIPTION_PROVIDER ``none``, TranscriptionDisabled and no call at all,
  from either provider, and an unknown value is ImproperlyConfigured;
- the Anthropic provider sends to FLM, not to Claude or Voyage;
- health is a report that never raises.
"""

import json

import httpx2
import openai
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.ai.anthropic import AnthropicService
from apps.ai.base import (
    ProviderRefused,
    ProviderUnavailable,
    Transcription,
    TranscriptionDisabled,
)
from apps.ai.flm import FLMService
from apps.ai.testing import STUB_ASR_MODEL, StubAIService, stub_transcript_text
from apps.ai.transcription import TRANSCRIPTION_TIMEOUT_SECONDS
from apps.core.constants import MAXIMUM_TRANSCRIBE_ATTEMPTS

BASE_URL = "http://flm.test/v1"
ASR_MODEL = "whisper-v3:turbo"
SEGMENT = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 64  # bytes; the provider does not parse it


@pytest.fixture
def transcription_on():
    with override_settings(
        FLM_BASE_URL=BASE_URL, FLM_API_KEY="flm", FLM_ASR_MODEL=ASR_MODEL, TRANSCRIPTION_PROVIDER="flm"
    ):
        yield


def scripted(handler) -> openai.OpenAI:
    return openai.OpenAI(
        base_url=BASE_URL,
        api_key="flm",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


class Script:
    """Answers each request with the next of ``replies`` and records it. A reply is a status
    code, a (status, body) pair, or an exception to raise as the transport would."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        status, body = reply if isinstance(reply, tuple) else (reply, {"error": {"message": "x"}})
        return httpx2.Response(status, json=body, request=request)


def transcribed(text="  We agreed the budget on the first of March.  "):
    return (200, {"text": text})


def connect_error():
    return httpx2.ConnectError("connection refused")


# --- The request and a good reply -----------------------------------------------------------------


def test_flm_sends_one_multipart_request_and_returns_the_stripped_text(transcription_on):
    script = Script(transcribed())

    result = FLMService(client=scripted(script)).transcribe(SEGMENT, filename="segment.wav")

    assert result == Transcription(text="We agreed the budget on the first of March.", model=ASR_MODEL)
    assert len(script.requests) == 1
    request = script.requests[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/audio/transcriptions"
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.read()
    for field, value in (("model", ASR_MODEL), ("language", "en"), ("response_format", "json")):
        assert f'name="{field}"\r\n\r\n{value}\r\n'.encode() in body, field
    assert b'filename="segment.wav"' in body
    assert b"Content-Type: audio/wav" in body
    assert SEGMENT in body


def test_every_call_carries_the_transcription_timeout(transcription_on):
    script = Script(transcribed())

    FLMService(client=scripted(script)).transcribe(SEGMENT)

    timeout = script.requests[0].extensions["timeout"]
    assert timeout["read"] == TRANSCRIPTION_TIMEOUT_SECONDS


def test_an_empty_transcription_is_a_reply_not_a_failure(transcription_on):
    script = Script(transcribed("   "))

    result = FLMService(client=scripted(script)).transcribe(SEGMENT)

    assert result.text == ""
    assert len(script.requests) == 1


# --- The attempt policy (D-19, D-118) -------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(500, id="a 5xx"),
        pytest.param(503, id="FLM's own 503"),
        pytest.param(429, id="a rate limit"),
        pytest.param(connect_error(), id="a refused connection"),
        pytest.param((200, {"error": {"message": "NPU fault"}}), id="a 200 with no text"),
    ],
)
def test_a_failed_call_is_retried_to_the_attempt_total_then_unavailable(transcription_on, failure):
    script = Script(failure)

    with pytest.raises(ProviderUnavailable) as raised:
        FLMService(client=scripted(script)).transcribe(SEGMENT)

    assert not isinstance(raised.value, (ProviderRefused, TranscriptionDisabled))
    assert len(script.requests) == MAXIMUM_TRANSCRIBE_ATTEMPTS  # 1 initial call + 2 retries
    assert MAXIMUM_TRANSCRIBE_ATTEMPTS == 3


def test_a_success_on_the_last_attempt_is_returned(transcription_on):
    script = Script(500, 500, transcribed("Third time."))

    result = FLMService(client=scripted(script)).transcribe(SEGMENT)

    assert result.text == "Third time."
    assert len(script.requests) == MAXIMUM_TRANSCRIBE_ATTEMPTS


@pytest.mark.parametrize("status", [400, 401, 404, 422])
def test_a_refusal_is_not_retried(transcription_on, status):
    script = Script(status)

    with pytest.raises(ProviderRefused):
        FLMService(client=scripted(script)).transcribe(SEGMENT)

    assert len(script.requests) == 1


def test_each_failed_attempt_is_logged_under_transcription(transcription_on, caplog):
    script = Script(500)

    with caplog.at_level("WARNING", logger="apps.ai.attempts"):
        with pytest.raises(ProviderUnavailable):
            FLMService(client=scripted(script)).transcribe(SEGMENT)

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("transcription attempt")]
    assert len(lines) == MAXIMUM_TRANSCRIBE_ATTEMPTS
    assert lines[0].startswith(f"transcription attempt 1 of {MAXIMUM_TRANSCRIBE_ATTEMPTS} failed")


# --- The setting ----------------------------------------------------------------------------------


def test_with_transcription_off_flm_refuses_before_any_call():
    script = Script(transcribed())

    with override_settings(TRANSCRIPTION_PROVIDER="none"):
        with pytest.raises(TranscriptionDisabled):
            FLMService(client=scripted(script)).transcribe(SEGMENT)

    assert script.requests == []


def test_with_transcription_off_the_anthropic_provider_builds_no_flm_client():
    service = AnthropicService()

    with override_settings(TRANSCRIPTION_PROVIDER="none"):
        with pytest.raises(TranscriptionDisabled):
            service.transcribe(SEGMENT)

    assert service._transcription_client is None


def test_an_unknown_setting_is_improperly_configured():
    with override_settings(TRANSCRIPTION_PROVIDER="whisper-cpu"):
        with pytest.raises(ImproperlyConfigured, match="TRANSCRIPTION_PROVIDER"):
            FLMService(client=scripted(Script(transcribed()))).transcribe(SEGMENT)


def test_transcription_disabled_is_a_provider_unavailable():
    """So a caller that knows only outages still answers 503 for it."""
    assert issubclass(TranscriptionDisabled, ProviderUnavailable)
    assert not issubclass(TranscriptionDisabled, ProviderRefused)


# --- The Anthropic provider sends to FLM ----------------------------------------------------------


def test_the_anthropic_provider_transcribes_through_flm(transcription_on):
    script = Script(transcribed("Through FLM."))

    with override_settings(AI_PROVIDER="anthropic"):
        result = AnthropicService(transcription_client=scripted(script)).transcribe(SEGMENT)

    assert result == Transcription(text="Through FLM.", model=ASR_MODEL)
    assert [str(r.url) for r in script.requests] == [f"{BASE_URL}/audio/transcriptions"]


def test_the_anthropic_provider_builds_its_flm_client_from_the_flm_settings(transcription_on):
    service = AnthropicService()

    client = service._flm_for_transcription()

    assert str(client.base_url).rstrip("/") == BASE_URL
    assert client.max_retries == 0  # the attempt policy is the application's (D-19)


def test_the_anthropic_provider_retries_and_refuses_as_flm_does(transcription_on):
    unavailable, refused = Script(503), Script(400)

    with pytest.raises(ProviderUnavailable):
        AnthropicService(transcription_client=scripted(unavailable)).transcribe(SEGMENT)
    with pytest.raises(ProviderRefused):
        AnthropicService(transcription_client=scripted(refused)).transcribe(SEGMENT)

    assert len(unavailable.requests) == MAXIMUM_TRANSCRIBE_ATTEMPTS
    assert len(refused.requests) == 1


# --- Health: a report that never raises -----------------------------------------------------------


def models(request):
    return httpx2.Response(200, json={"object": "list", "data": []}, request=request)


@pytest.mark.parametrize("make", [lambda c: FLMService(client=c), lambda c: AnthropicService(transcription_client=c)])
def test_health_is_available_when_flm_answers(transcription_on, make):
    seen = []

    def handler(request):
        seen.append(request)
        return models(request)

    health = make(scripted(handler)).transcription_health()

    assert health.available
    assert ASR_MODEL in health.detail
    assert [str(r.url) for r in seen] == [f"{BASE_URL}/models"]


@pytest.mark.parametrize("failure", [connect_error(), 500])
def test_health_is_unavailable_and_does_not_raise_when_flm_does_not_answer(transcription_on, failure):
    health = FLMService(client=scripted(Script(failure))).transcription_health()

    assert not health.available


def test_health_reports_transcription_off_without_a_call():
    script = Script(transcribed())

    with override_settings(TRANSCRIPTION_PROVIDER="none"):
        health = FLMService(client=scripted(script)).transcription_health()
        anthropic_health = AnthropicService().transcription_health()

    assert not health.available and not anthropic_health.available
    assert "not enabled" in health.detail
    assert script.requests == []


def test_health_reports_an_unknown_setting_without_raising():
    with override_settings(TRANSCRIPTION_PROVIDER="whisper-cpu"):
        health = FLMService(client=scripted(Script(transcribed()))).transcription_health()

    assert not health.available
    assert "TRANSCRIPTION_PROVIDER" in health.detail


# --- The stub -------------------------------------------------------------------------------------


def test_the_stub_numbers_its_transcripts_and_records_each_call():
    stub = StubAIService()

    first = stub.transcribe(b"one")
    second = stub.transcribe(b"two", filename="other.wav")

    assert first == Transcription(text=stub_transcript_text(1), model=STUB_ASR_MODEL)
    assert second.text == stub_transcript_text(2)
    assert stub.transcribe_calls == [(b"one", "segment.wav"), (b"two", "other.wav")]


def test_the_stub_can_be_told_what_to_return_or_raise():
    fixed = Transcription(text="Fixed.", model="m")
    assert StubAIService(transcription=fixed).transcribe(b"x") is fixed

    def outage(audio, filename):
        raise ProviderUnavailable("down")

    stub = StubAIService(transcription=outage)
    with pytest.raises(ProviderUnavailable):
        stub.transcribe(b"x")
    assert stub.transcribe_calls == [(b"x", "segment.wav")]


def test_the_stubs_health_follows_its_flag():
    assert StubAIService().transcription_health().available
    assert not StubAIService(transcription_available=False).transcription_health().available


def test_both_providers_and_the_stub_declare_the_two_operations():
    """The contract and its implementations differing by a method is the defect base.py warns of."""
    for implementation in (FLMService, AnthropicService, StubAIService):
        assert callable(getattr(implementation, "transcribe", None)), implementation
        assert callable(getattr(implementation, "transcription_health", None)), implementation


def test_the_request_body_names_the_segment_part_audio_free_of_json(transcription_on):
    """FLM's endpoint is multipart, like OpenAI's: nothing is sent as JSON."""
    script = Script(transcribed())

    FLMService(client=scripted(script)).transcribe(SEGMENT)

    with pytest.raises(json.JSONDecodeError):
        json.loads(script.requests[0].read())
