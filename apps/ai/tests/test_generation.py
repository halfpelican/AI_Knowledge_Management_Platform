"""NFR-19 fault injection: the generation attempt loop (apps/ai/generation.py).

**This file is the only evidence the retry policy works.** docs/flm-baseline.md says so
explicitly under "Conformance was measured on the happy path": every one of the 50
baseline questions conformed on its FIRST attempt, so the live run never once executed a
retry, a second attempt or the 503 path. Those branches have never been exercised against
a real model and, on the evidence, may never be. What is asserted here is all anyone knows
about them.

The policy under test (CLAUDE.md section 5, D-19, invariant 10):

- MAXIMUM_GENERATION_ATTEMPTS is a TOTAL — 1 initial call + 2 retries — so the provider is
  called exactly three times before ProviderUnavailable. Not two, not four. The count is
  asserted as an equality, which is the assertion that keeps someone from "helpfully"
  correcting the constant to 2.
- A reply that does not conform is a failed attempt, not a partial answer.
- A reply that conforms on a later attempt is returned, and no further calls are made.
- Since D-118, a 429 is a failed attempt like an outage and is retried to the limit. Any
  other 4xx is ProviderRefused and ends the loop after one call. Each is logged, a 429 as
  a WARNING and the rest as ERRORs.

Exercised through FLMService against the openai SDK's MockTransport, in-process, so the
transport failures are real SDK exceptions rather than stand-ins. Nothing here reaches a
network.
"""

import json
import logging

import httpx2
import openai
import pytest
from django.test import override_settings

from apps.ai import attempt_log
from apps.ai.base import Passage, ProviderRefused, ProviderUnavailable
from apps.ai.flm import FLMService
from apps.ai.generation import GENERATION_MAX_TOKENS, GENERATION_TIMEOUT_SECONDS
from apps.ai.prompting import SYSTEM_PROMPT
from apps.core.constants import MAXIMUM_GENERATION_ATTEMPTS

BASE_URL = "http://flm.test/v1"
CHAT_MODEL = "gemma3:4b"
CHUNK_ID = "3f2a91c7-5e48-4d0b-9a16-7c8e2b4f6a03"
PASSAGES = [Passage(chunk_id=CHUNK_ID, text="Twenty days of annual leave per year.")]
QUESTION = "How much annual leave do I get?"

CONFORMING = json.dumps({"statements": [{"text": "Twenty days.", "chunk_id": CHUNK_ID}]})


@pytest.fixture(autouse=True)
def flm_settings():
    with override_settings(FLM_BASE_URL=BASE_URL, FLM_API_KEY="flm", FLM_CHAT_MODEL=CHAT_MODEL):
        yield


def chat_response(content: str):
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": CHAT_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        },
    )


def make_service(handler):
    client = openai.OpenAI(
        base_url=BASE_URL,
        api_key="flm",
        max_retries=0,  # the retry policy is the application's, not the SDK's
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return FLMService(client=client)


def scripted(*replies):
    """A handler answering with each reply in turn, recording every request."""
    seen = []

    def handler(request):
        seen.append(request)
        reply = replies[min(len(seen) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx2.Response):
            return reply
        return chat_response(reply)

    handler.seen = seen
    return handler


# --- The happy path, and the prompt that went with it ----------------------------------


def test_one_conforming_reply_is_returned_after_exactly_one_call():
    handler = scripted(CONFORMING)

    result = make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert [statement.text for statement in result.statements] == ["Twenty days."]
    assert [statement.chunk_id for statement in result.statements] == [CHUNK_ID]
    assert len(handler.seen) == 1
    assert str(handler.seen[0].url) == f"{BASE_URL}/chat/completions"


def test_the_request_carries_the_passages_the_prompt_and_the_measured_parameters():
    """The wire request, asserted once: this is what the baseline measured.

    temperature 0.0 so the same passages give the same reply run to run; max_tokens and
    the timeout at the values docs/flm-baseline.md was recorded at.
    """
    handler = scripted(CONFORMING)

    make_service(handler).generate_statements(QUESTION, PASSAGES)

    sent = json.loads(handler.seen[0].content)
    assert sent["model"] == CHAT_MODEL
    assert sent["temperature"] == 0.0
    assert sent["max_tokens"] == GENERATION_MAX_TOKENS == 800
    assert sent["stream"] is False
    assert [message["role"] for message in sent["messages"]] == ["system", "user"]
    assert sent["messages"][0]["content"] == SYSTEM_PROMPT
    # The passages and their identifiers are in the prompt; nothing else is.
    assert f"[chunk_id: {CHUNK_ID}]" in sent["messages"][1]["content"]
    assert PASSAGES[0].text in sent["messages"][1]["content"]
    assert QUESTION in sent["messages"][1]["content"]
    assert GENERATION_TIMEOUT_SECONDS == 300


def test_an_empty_statement_list_is_returned_and_not_retried():
    """The model saying "these passages do not answer it" is an answer to that question.

    Retrying here would spend three NPU calls collecting the same correct reply and would
    end in a 503, hiding the signal no-answer path B exists to expose (invariant 7).
    """
    handler = scripted('{"statements": []}')

    result = make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert result.statements == []
    assert len(handler.seen) == 1


def test_generation_refuses_an_empty_passage_list_without_calling_the_provider():
    """Failure path: no grounding material must never reach the model.

    FR-12's no-answer path A returns before generation, so the pipeline cannot produce
    this; a caller that does has a bug, and spending an NPU call on a prompt with no
    passages could only invite invention.
    """

    def handler(request):
        raise AssertionError("no request expected when there are no passages")

    with pytest.raises(ValueError, match="at least one passage"):
        make_service(handler).generate_statements(QUESTION, [])


# --- Retry: the malformed reply ---------------------------------------------------------


def test_a_malformed_reply_twice_then_a_valid_one_returns_the_valid_one():
    """Two failed attempts and a third that conforms: three calls, and an answer."""
    handler = scripted("Sure! Here you go: I cannot produce JSON.", "{not json", CONFORMING)

    result = make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert [statement.text for statement in result.statements] == ["Twenty days."]
    assert len(handler.seen) == MAXIMUM_GENERATION_ATTEMPTS == 3


def test_a_reply_that_conforms_on_the_second_attempt_stops_there():
    """No further calls once a reply conforms: the loop returns, it does not finish."""
    handler = scripted("prose, no object", CONFORMING, CONFORMING)

    make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert len(handler.seen) == 2


def test_three_malformed_replies_raise_provider_unavailable_after_exactly_three_calls():
    """THE NFR-19 assertion: exactly MAXIMUM_GENERATION_ATTEMPTS calls, then 503.

    An equality, not a ceiling. The proposal words the policy as "2 retries" and the
    constant as a total of 3; if someone reconciles the two by setting the constant to 2,
    this fails. The 503 the view returns is downstream of this exception.
    """
    handler = scripted("no json here", "still none", "nope")

    with pytest.raises(ProviderUnavailable) as excinfo:
        make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert len(handler.seen) == MAXIMUM_GENERATION_ATTEMPTS == 3
    assert "STATEMENT_LIST_SCHEMA" in str(excinfo.value)
    assert BASE_URL in str(excinfo.value)  # which provider could not answer


def test_a_reply_that_is_the_wrong_shape_is_a_failed_attempt_not_a_partial_answer():
    """Invariant 10: valid JSON of the wrong shape is no response at all.

    The reply below is JSON, is parseable, and even contains a plausible sentence and a
    real identifier. It is still discarded whole, because a statement list this code had
    to guess the shape of is a statement list nothing can verify.
    """
    nearly = json.dumps({"answer": "Twenty days.", "source": CHUNK_ID})
    handler = scripted(nearly, nearly, nearly)

    with pytest.raises(ProviderUnavailable):
        make_service(handler).generate_statements(QUESTION, PASSAGES)
    assert len(handler.seen) == 3


def test_an_empty_choices_list_is_a_failed_attempt():
    """No reply at all, which FLM can answer with; treated as the non-response it is."""
    empty = httpx2.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": CHAT_MODEL,
            "choices": [],
        },
    )
    handler = scripted(empty, empty, CONFORMING)

    result = make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert result.statements != []
    assert len(handler.seen) == 3


# --- Retry: the transport failure -------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        httpx2.ConnectError("connection refused"),
        httpx2.ReadTimeout("timed out"),
    ],
    ids=["connection-refused", "timeout"],
)
def test_a_transport_failure_is_a_failed_attempt_and_is_retried(failure):
    handler = scripted(failure, failure, CONFORMING)

    result = make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert result.statements != []
    assert len(handler.seen) == 3


def test_a_server_error_is_a_failed_attempt_and_is_retried():
    error = httpx2.Response(503, json={"error": {"message": "model loading"}})
    handler = scripted(error, error, CONFORMING)

    result = make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert result.statements != []
    assert len(handler.seen) == 3


def test_three_transport_failures_raise_provider_unavailable_naming_the_last_one():
    handler = scripted(*[httpx2.ConnectError("connection refused")] * 3)

    with pytest.raises(ProviderUnavailable) as excinfo:
        make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert len(handler.seen) == 3
    assert "unreachable" in str(excinfo.value)


def test_a_mixture_of_failure_kinds_still_stops_at_three_attempts():
    """A timeout, a malformed reply and a 5xx are three failed attempts between them.

    The budget is attempts, not attempts-of-each-kind: nothing resets the counter.
    """
    handler = scripted(
        httpx2.ReadTimeout("timed out"),
        "prose",
        httpx2.Response(500, json={"error": "boom"}),
    )

    with pytest.raises(ProviderUnavailable):
        make_service(handler).generate_statements(QUESTION, PASSAGES)
    assert len(handler.seen) == 3


# --- A 4xx ends in the 503: a 429 is retried, any other 4xx is refused (D-118) ----------


def test_a_refused_request_ends_the_loop_at_once_with_its_cause_logged(caplog):
    """D-118: a 4xx other than a rate limit is ProviderRefused.

    A mistyped FLM_CHAT_MODEL would be refused the same way three times, so the loop stops
    after one call. The view's 503 still catches it as the ProviderUnavailable it is, and
    the cause is one ERROR line naming the status. Until 10 November 2026 a 4xx surfaced as
    the SDK's own exception, which reached the user as a 500 on the anthropic provider,
    where rate limits and an exhausted credit are routine.
    """
    handler = scripted(httpx2.Response(404, json={"error": {"message": "unknown model"}}))

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with pytest.raises(ProviderRefused, match="HTTP 404"):
            make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert len(handler.seen) == 1
    refusals = [r for r in caplog.records if "refused the request" in r.getMessage()]
    assert [r.levelno for r in refusals] == [logging.ERROR]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_no_refusal_is_retried(status):
    handler = scripted(httpx2.Response(status, json={"error": {"message": "nope"}}))

    with pytest.raises(ProviderRefused):
        make_service(handler).generate_statements(QUESTION, PASSAGES)
    assert len(handler.seen) == 1


def test_a_rate_limit_is_retried_to_the_attempt_limit():
    """A 429 is a failed attempt like an outage: three calls, then ProviderUnavailable,
    and not ProviderRefused, because a rate limit passes."""
    handler = scripted(httpx2.Response(429, json={"error": {"message": "rate limited"}}))

    with pytest.raises(ProviderUnavailable) as excinfo:
        make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert not isinstance(excinfo.value, ProviderRefused)
    assert len(handler.seen) == MAXIMUM_GENERATION_ATTEMPTS == 3


def test_a_rate_limit_is_a_warning_and_a_later_conforming_reply_is_returned(caplog):
    """A 429 passes, so it is a WARNING rather than an ERROR, and the next attempt's
    conforming reply is the answer."""
    handler = scripted(httpx2.Response(429, json={"error": {"message": "rate limited"}}), CONFORMING)

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        result = make_service(handler).generate_statements(QUESTION, PASSAGES)

    assert result.statements != []
    assert len(handler.seen) == 2
    (refusal,) = [r for r in caplog.records if "refused the request" in r.getMessage()]
    assert refusal.levelno == logging.WARNING


# --- The diagnostic hook the harness measures with ---------------------------------------


def test_every_attempt_is_reported_to_on_attempt_in_order():
    """scripts/citation_harness.py reads these to compute the conformance rate.

    Per RESPONSE, as docs/flm-baseline.md reports it, with the first-attempt rate
    separately — which the harness can only do if it sees each attempt. The hook is
    diagnostic: nothing in apps/ branches on it.
    """
    handler = scripted(httpx2.ConnectError("refused"), "prose only", CONFORMING)
    recorded = []

    make_service(handler).generate_statements(QUESTION, PASSAGES, on_attempt=recorded.append)

    assert [attempt.number for attempt in recorded] == [1, 2, 3]
    assert [attempt.outcome for attempt in recorded] == [
        "call-failed",
        "schema-violation",
        "parsed",
    ]
    assert recorded[0].raw is None  # the call itself failed, so there was no reply
    assert recorded[1].raw == "prose only"  # the raw reply is kept for the record
    assert recorded[2].statements == 1
    assert all(attempt.seconds >= 0 for attempt in recorded)


def test_the_hook_is_optional_and_nothing_in_the_pipeline_passes_it():
    """Called with two arguments, as docs/ai-provider.md section 1 documents the contract."""
    handler = scripted(CONFORMING)
    result = make_service(handler).generate_statements(QUESTION, PASSAGES)
    assert result.statements != []


def test_the_attempts_reported_before_a_503_are_all_three():
    handler = scripted("prose", "prose", "prose")
    recorded = []

    with pytest.raises(ProviderUnavailable):
        make_service(handler).generate_statements(QUESTION, PASSAGES, on_attempt=recorded.append)

    assert [attempt.outcome for attempt in recorded] == ["schema-violation"] * 3
    assert len(recorded) == MAXIMUM_GENERATION_ATTEMPTS


# --- The observer cannot change what it observes ----------------------------------------


def exploding_observer(calls):
    """A callback that records that it was called and then raises, every time."""

    def observe(attempt):
        calls.append(attempt.number)
        raise RuntimeError("the measuring instrument is broken")

    return observe


def test_a_callback_that_raises_does_not_disturb_the_success_path():
    """A broken observer leaves the answer exactly as it would have been.

    The callback is a measuring instrument. If a fault in it could change the reply, every
    number the harness reports would be a number about a run the harness itself altered.
    """
    handler = scripted(CONFORMING)
    observed = []

    result = make_service(handler).generate_statements(
        QUESTION, PASSAGES, on_attempt=exploding_observer(observed)
    )

    assert [statement.text for statement in result.statements] == ["Twenty days."]
    assert [statement.chunk_id for statement in result.statements] == [CHUNK_ID]
    assert observed == [1]  # it was called, it raised, and nothing came of it
    assert len(handler.seen) == 1


def test_a_callback_that_raises_does_not_move_the_attempt_count():
    """THE assertion: exactly MAXIMUM_GENERATION_ATTEMPTS provider calls, then the 503.

    This is the number NFR-19's fault injection is about, and it is the one an observer
    must not be able to move. A callback raising on attempt 2 must not end the loop early,
    must not make the sequence two attempts long, and must not replace ProviderUnavailable
    with an exception raised from the instrument — which would reach the view as a 500
    about a broken harness rather than a 503 about a provider that could not answer.
    """
    handler = scripted("prose", "prose", "prose")
    observed = []

    with pytest.raises(ProviderUnavailable) as excinfo:
        make_service(handler).generate_statements(
            QUESTION, PASSAGES, on_attempt=exploding_observer(observed)
        )

    assert len(handler.seen) == MAXIMUM_GENERATION_ATTEMPTS == 3
    assert observed == [1, 2, 3]  # every attempt was still observed, and each one raised
    assert "STATEMENT_LIST_SCHEMA" in str(excinfo.value)
    assert not isinstance(excinfo.value, RuntimeError)


def test_a_callback_that_raises_on_one_attempt_only_still_leaves_three():
    """The mid-sequence case stated separately, since it is the one that could truncate."""
    handler = scripted("prose", "prose", "prose")
    observed = []

    def observe(attempt):
        observed.append(attempt.number)
        if attempt.number == 2:
            raise RuntimeError("broken on the second attempt only")

    with pytest.raises(ProviderUnavailable):
        make_service(handler).generate_statements(QUESTION, PASSAGES, on_attempt=observe)

    assert len(handler.seen) == 3
    assert observed == [1, 2, 3]


def test_a_callback_that_raises_does_not_prevent_a_later_attempt_from_succeeding():
    handler = scripted("prose", CONFORMING)
    observed = []

    result = make_service(handler).generate_statements(
        QUESTION, PASSAGES, on_attempt=exploding_observer(observed)
    )

    assert result.statements != []
    assert observed == [1, 2]
    assert len(handler.seen) == 2


def test_the_callbacks_return_value_is_ignored():
    """An observer cannot answer the question by returning something either."""
    handler = scripted(CONFORMING)

    result = make_service(handler).generate_statements(
        QUESTION, PASSAGES, on_attempt=lambda attempt: "a statement list, allegedly"
    )

    assert [statement.text for statement in result.statements] == ["Twenty days."]
