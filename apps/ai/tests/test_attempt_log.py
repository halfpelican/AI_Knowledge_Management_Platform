"""Failed provider attempts are logged with their cause, their time and the account (1 November 2026).

NFR-08's first run on 1 November 2026 had two 503s that could be bounded but not explained:
nothing recorded a generation or embedding attempt. ``apps/ai/attempt_log.py`` logs each
failed attempt; these tests pin what a line says, that a success logs no warning, and that
logging changes no attempt count. The view's 503 line is tested from both roles in
``apps/api/tests/test_ask.py``, and the file it lands in in
``apps/core/tests/test_logging_config.py``.

**7 November 2026, step 7 phase 1.** Every generation attempt now records what its reply
reported (``finish_reason``, completion and prompt tokens) and the ``max_tokens`` sent, and
a parsed attempt is an INFO line. The tests for that are at the end of this file; the
Anthropic provider's are in ``apps/ai/tests/test_anthropic.py``.
"""

from __future__ import annotations

import json
import logging
import re

import httpx2  # the openai SDK's HTTP layer, as apps/ai/tests/test_flm.py imports it
import openai
import pytest
from django.conf import settings

import apps.ai
from apps.ai import attempt_log
from apps.ai.base import EmbeddingResult, Passage, ProviderUnavailable
from apps.ai.flm import FLMService
from apps.ai.generation import GENERATION_MAX_TOKENS, fewer_statements, run_generation_attempts
from apps.core.constants import MAXIMUM_EMBED_ATTEMPTS, MAXIMUM_GENERATION_ATTEMPTS, MAXIMUM_STATEMENTS
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

    def call_once(max_statements):
        calls.append(max_statements)
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


def test_a_first_attempt_that_parses_logs_no_warning(caplog):
    """Its INFO line is tested at the end of this file; at WARNING there is nothing."""
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

    def embed(self, texts, *, input_type=None):
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


# --- What each generation attempt's reply reported (7 November 2026) ---------------------------
#
# Step 7 phase 1, at the user's order: "log each attempt's finish_reason and completion-token
# count". Exercised through FLMService over the SDK's MockTransport, so each value travels the
# real response parsing: FLM's JSON, the openai SDK's model, FLMService._chat_once, the loop and
# the log line.

FLM_BASE = "http://flm.test/v1"
CHUNK_ID = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
PASSAGES = [Passage(chunk_id=CHUNK_ID, text="Twenty days of annual leave per year.")]
QUESTION = "How much annual leave do I get?"
CONFORMING = json.dumps({"statements": [{"text": "Twenty days.", "chunk_id": CHUNK_ID}]})
# A reply that stops before its JSON closes, as every failed attempt in NFR-08's run 3 did.
TRUNCATED = '{"statements": [{"text": "Twenty days.", "chunk_id": "3f2a91c7-5e48'


@pytest.fixture
def flm_settings(settings):
    settings.FLM_BASE_URL = FLM_BASE
    settings.FLM_API_KEY = "flm"
    settings.FLM_CHAT_MODEL = "gemma3:4b"


def _chat(content, *, finish_reason="stop", usage=None):
    """One FLM chat completion. ``usage`` None leaves the usage block out entirely."""
    body = {
        "id": "fastflowlm-chat-completion",
        "object": "chat.completion",
        "created": 0,
        "model": "gemma3:4b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return httpx2.Response(200, json=body)


def _usage(prompt, completion):
    # total_tokens differs from both, so reading the wrong field cannot pass.
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


def _flm(*steps):
    """FLMService answering each request with the next step (a response, or an exception to
    raise), and the JSON body of every request it sent."""
    remaining = list(steps)
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        step = remaining.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    client = openai.OpenAI(
        base_url=FLM_BASE,
        api_key="flm",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return FLMService(client=client), sent


def _records(caplog):
    return [r for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]


def test_a_parsed_attempt_is_an_info_line_carrying_what_its_reply_reported(caplog, flm_settings):
    service, sent = _flm(_chat(CONFORMING, finish_reason="stop", usage=_usage(412, 37)))

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with attempt_log.account("account-5"):
            service.generate_statements(QUESTION, PASSAGES)

    (record,) = _records(caplog)
    assert record.levelno == logging.INFO
    match = re.fullmatch(
        rf"generation attempt 1 of {MAXIMUM_GENERATION_ATTEMPTS} parsed after \d+\.\d s "
        r"\[finish_reason=stop completion_tokens=37 prompt_tokens=412 max_tokens=(\d+) "
        r"max_statements=(\d+)\] \(account account-5\): 1 statement\(s\)",
        record.getMessage(),
    )
    assert match, record.getMessage()
    # The max_tokens logged is the max_tokens the request carried.
    assert int(match.group(1)) == sent[0]["max_tokens"] == GENERATION_MAX_TOKENS
    # And the cap logged is the one the first attempt's prompt stated.
    assert int(match.group(2)) == MAXIMUM_STATEMENTS
    assert f"Give at most {MAXIMUM_STATEMENTS} statement" in sent[0]["messages"][1]["content"]


def test_each_attempt_carries_its_own_reply_and_a_failed_call_reports_only_max_tokens(
    caplog, flm_settings
):
    """A timeout, then a reply cut off at max_tokens, then a conforming one: three lines, each
    with its own values, and the call that produced no reply reports nothing but what it sent."""
    service, sent = _flm(
        httpx2.ReadTimeout("timed out"),
        _chat(TRUNCATED, finish_reason="length", usage=_usage(1500, 800)),
        _chat(CONFORMING, finish_reason="stop", usage=_usage(1500, 41)),
    )

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        service.generate_statements(QUESTION, PASSAGES)

    records = _records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING, logging.WARNING, logging.INFO]
    assert len(sent) == MAXIMUM_GENERATION_ATTEMPTS
    first, second, third = (r.getMessage() for r in records)
    # The timeout keeps the cap; the ceiling hit halves it for attempt 3 (step 7 phase 2a).
    reduced = fewer_statements(MAXIMUM_STATEMENTS)
    assert re.fullmatch(
        r"generation attempt 1 of 3 failed after \d+\.\d s \[finish_reason=unreported "
        r"completion_tokens=unreported prompt_tokens=unreported "
        rf"max_tokens={sent[0]['max_tokens']} max_statements={MAXIMUM_STATEMENTS}\] "
        r"\(account not set\): APITimeoutError: .+",
        first,
    ), first
    assert re.fullmatch(
        r"generation attempt 2 of 3 failed after \d+\.\d s \[finish_reason=length "
        rf"completion_tokens=800 prompt_tokens=1500 max_tokens={sent[1]['max_tokens']} "
        rf"max_statements={MAXIMUM_STATEMENTS}\] "
        r"\(account not set\): SchemaViolation: unbalanced JSON object in the response",
        second,
    ), second
    assert re.fullmatch(
        r"generation attempt 3 of 3 parsed after \d+\.\d s \[finish_reason=stop "
        rf"completion_tokens=41 prompt_tokens=1500 max_tokens={sent[2]['max_tokens']} "
        rf"max_statements={reduced}\] "
        r"\(account not set\): 1 statement\(s\)",
        third,
    ), third


def test_a_reply_that_reports_no_usage_reads_unreported(caplog, flm_settings):
    """FLM leaving the usage block out is logged as such, not as zero and not as a crash."""
    service, _ = _flm(_chat(CONFORMING, finish_reason="stop", usage=None))

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        result = service.generate_statements(QUESTION, PASSAGES)

    assert [s.chunk_id for s in result.statements] == [CHUNK_ID]
    (line,) = [r.getMessage() for r in _records(caplog)]
    assert (
        "[finish_reason=stop completion_tokens=unreported prompt_tokens=unreported "
        f"max_tokens={GENERATION_MAX_TOKENS} max_statements={MAXIMUM_STATEMENTS}]"
    ) in line


def test_success_lines_go_to_the_attempts_file_and_never_to_the_error_file(
    error_log_file, attempts_log_file, flm_settings
):
    """The user's decision of 7 November 2026 (step 7 phase 2a), under the shipped LOGGING as
    conftest.py builds it, with nothing lowered by the test: the attempts file holds every
    attempt, the failed one and the parsed one; the error file holds the failure only."""
    service, _ = _flm(
        _chat(TRUNCATED, finish_reason="length", usage=_usage(1500, 800)),
        _chat(CONFORMING, finish_reason="stop", usage=_usage(1500, 41)),
    )

    with attempt_log.account("account-9"):
        service.generate_statements(QUESTION, PASSAGES)

    attempts = attempts_log_file.read_text(encoding="utf-8").splitlines()
    assert len(attempts) == 2
    assert " WARNING apps.ai.attempts generation attempt 1 of 3 failed after " in attempts[0]
    assert " INFO apps.ai.attempts generation attempt 2 of 3 parsed after " in attempts[1]
    assert "(account account-9): 1 statement(s)" in attempts[1]
    errors = error_log_file.read_text(encoding="utf-8").splitlines()
    assert len(errors) == 1
    assert " WARNING apps.ai.attempts generation attempt 1 of 3 failed after " in errors[0]
    assert "parsed" not in error_log_file.read_text(encoding="utf-8")
