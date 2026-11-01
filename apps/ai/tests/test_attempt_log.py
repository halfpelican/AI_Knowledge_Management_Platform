"""Failed provider attempts are logged with their cause, their time and the account (1 November 2026).

NFR-08's first run on 1 November 2026 had two 503s that could be bounded but not explained:
nothing recorded a generation or embedding attempt. ``apps/ai/attempt_log.py`` logs each
failed attempt; these tests pin what a line says, that a success logs nothing, and that
logging changes no attempt count. The view's 503 line is tested from both roles in
``apps/api/tests/test_ask.py``, and the file it lands in in
``apps/core/tests/test_logging_config.py``.
"""

from __future__ import annotations

import logging

import httpx2  # the openai SDK's HTTP layer, as apps/ai/tests/test_flm.py imports it
import openai
import pytest
from django.conf import settings

import apps.ai
from apps.ai import attempt_log
from apps.ai.base import EmbeddingResult, ProviderUnavailable
from apps.ai.generation import run_generation_attempts
from apps.core.constants import MAXIMUM_EMBED_ATTEMPTS, MAXIMUM_GENERATION_ATTEMPTS
from apps.retrieval.query_embedding import embed_question

FLM_URL = "http://127.0.0.1:8625/v1/chat/completions"
VALID_REPLY = '{"statements": []}'


def _unavailable(cause: Exception) -> ProviderUnavailable:
    """What flm.py raises: ProviderUnavailable from the OpenAI client's exception."""
    try:
        raise ProviderUnavailable(f"http://127.0.0.1:8625/v1 unreachable: {cause}") from cause
    except ProviderUnavailable as exc:
        return exc


def _timeout() -> ProviderUnavailable:
    return _unavailable(openai.APITimeoutError(request=httpx2.Request("POST", FLM_URL)))


def _scripted(*steps):
    """A call_once that raises or returns each step in turn, and counts its calls."""
    remaining = list(steps)
    calls = []

    def call_once():
        calls.append(1)
        step = remaining.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    return call_once, calls


def _attempt_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]


def test_each_failed_generation_attempt_is_logged_with_its_cause_time_and_account(caplog):
    call_once, calls = _scripted(_timeout(), "this is not JSON", VALID_REPLY)

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with attempt_log.account("account-7"):
            result = run_generation_attempts(call_once=call_once, label="FLM")

    assert result.statements == []
    assert len(calls) == 3
    first, second = _attempt_lines(caplog)
    assert first.startswith(f"generation attempt 1 of {MAXIMUM_GENERATION_ATTEMPTS} failed after ")
    assert "(account account-7): APITimeoutError: " in first
    assert "timed out" in first
    assert second.startswith(f"generation attempt 2 of {MAXIMUM_GENERATION_ATTEMPTS} failed after ")
    assert "(account account-7): SchemaViolation: " in second


def test_a_first_attempt_that_parses_logs_nothing(caplog):
    call_once, _ = _scripted(VALID_REPLY)

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        run_generation_attempts(call_once=call_once, label="FLM")

    assert _attempt_lines(caplog) == []


@pytest.mark.parametrize(
    ("cause", "name"),
    [
        (openai.APIConnectionError(request=httpx2.Request("POST", FLM_URL)), "APIConnectionError"),
        (ValueError("NPU fault"), "ValueError"),
    ],
)
def test_logging_changes_no_attempt_count_and_the_last_failure_still_raises(caplog, cause, name):
    """NFR-19's count holds: three calls, then ProviderUnavailable, whatever is logged."""
    call_once, calls = _scripted(*[_unavailable(cause) for _ in range(MAXIMUM_GENERATION_ATTEMPTS)])

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with pytest.raises(ProviderUnavailable):
            run_generation_attempts(call_once=call_once, label="FLM")

    assert len(calls) == MAXIMUM_GENERATION_ATTEMPTS
    lines = _attempt_lines(caplog)
    assert len(lines) == MAXIMUM_GENERATION_ATTEMPTS
    assert all(f": {name}: " in line for line in lines)
    # Outside the view's block, the line says so rather than naming a stale account.
    assert all("(account not set)" in line for line in lines)


def test_the_account_is_not_carried_past_its_block(caplog):
    with attempt_log.account("account-1"):
        pass
    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        attempt_log.failed_attempt("generation", 1, 3, 0.5, "APITimeoutError", "Request timed out.")

    assert "(account not set)" in _attempt_lines(caplog)[0]


def test_a_long_detail_is_cut_and_kept_on_one_line(caplog):
    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        attempt_log.failed_attempt("generation", 1, 3, 1.0, "SchemaViolation", "x\ny " * 500)

    (line,) = _attempt_lines(caplog)
    assert "\n" not in line
    assert line.endswith("...")
    assert len(line.split(": SchemaViolation: ", 1)[1]) == attempt_log.DETAIL_LIMIT


class _FlakyEmbedder:
    """Fails the first ``failures`` embeds, then answers with a usable vector."""

    def __init__(self, failures, *, unusable=False):
        self.failures = failures
        self.unusable = unusable
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        if self.calls <= self.failures:
            raise _unavailable(openai.APIConnectionError(request=httpx2.Request("POST", FLM_URL)))
        dimension = settings.EMBEDDING_DIMENSION + (1 if self.unusable else 0)
        return EmbeddingResult(vectors=[[0.1] * dimension], model="embed-gemma", dimension=dimension)


def test_each_failed_question_embedding_attempt_is_logged(caplog, monkeypatch):
    embedder = _FlakyEmbedder(failures=2)
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: embedder)

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with attempt_log.account("account-3"):
            embed_question("How much annual leave do I earn?")

    assert embedder.calls == 3
    lines = _attempt_lines(caplog)
    assert [line.split(" failed after ")[0] for line in lines] == [
        f"question embedding attempt 1 of {MAXIMUM_EMBED_ATTEMPTS}",
        f"question embedding attempt 2 of {MAXIMUM_EMBED_ATTEMPTS}",
    ]
    assert all("(account account-3): APIConnectionError: " in line for line in lines)
    assert all("annual leave" not in line for line in lines)


def test_an_unusable_embedding_reply_is_logged_before_its_503(caplog, monkeypatch):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: _FlakyEmbedder(failures=0, unusable=True))

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with pytest.raises(ProviderUnavailable):
            embed_question("How much annual leave do I earn?")

    (line,) = _attempt_lines(caplog)
    assert line.startswith(f"question embedding attempt 1 of {MAXIMUM_EMBED_ATTEMPTS} failed after ")
    assert ": unusable reply: " in line
