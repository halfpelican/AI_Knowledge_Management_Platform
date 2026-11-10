"""The classification attempt loop (apps/ai/classification.py): run_classification_attempts (FR-10).

The policy under test is run_generation_attempts' (D-19, invariant 10), with
MAXIMUM_CLASSIFY_ATTEMPTS as the TOTAL — 1 initial call + 2 retries:

- a transport failure (ProviderUnavailable from ``call_once``) is a failed attempt;
- a reply that does not conform to CLASSIFICATION_SCHEMA is a failed attempt, not a partial
  classification;
- anything else ``call_once`` raises propagates after ONE call and consumes no retry;
- after the last attempt, ProviderUnavailable naming the label and the last failure.

Exercised directly, with a scripted ``call_once``, so the count is the loop's own; the two
providers are exercised through their fakes in test_classification_providers.py. Every attempt is
recorded through apps/ai/attempt_log.py under the step "classification", and no line quotes the
reply.
"""

from __future__ import annotations

import inspect
import json
import logging
import re

import pytest

from apps.ai import attempt_log
from apps.ai.base import Assignment, DocumentClassification, ProviderUnavailable, TagScheme, TagSuggestion
from apps.ai.classification import CLASSIFICATION_MAX_TOKENS, run_classification_attempts
from apps.ai.generation import ChatReply
from apps.core.constants import DOCUMENT_TYPES, MAXIMUM_CLASSIFY_ATTEMPTS

SCHEME = TagScheme(
    doc_types=DOCUMENT_TYPES,
    departments=("Finance",),
    tags={"Project": (), "Process": ("onboarding",), "Topic": ("safety",)},
)
CONFORMING = json.dumps(
    {
        "doc_type": {"value": "Procedure", "confidence": 0.9},
        "department": {"value": "Finance", "confidence": 0.6},
        "tags": [{"dimension": "Process", "value": "onboarding", "confidence": 0.8}],
    }
)
OUT_OF_SCHEME_TYPE = CONFORMING.replace("Procedure", "Memo")
LABEL = "FLM at http://flm.test/v1"


def unavailable(cause: Exception | None = None) -> ProviderUnavailable:
    """What a provider's one-call function raises for a transport failure, with its cause."""
    try:
        raise ProviderUnavailable("http://flm.test/v1 unreachable: refused") from cause
    except ProviderUnavailable as exc:
        return exc


def scripted(*steps):
    """A ``call_once`` that raises or returns each step in turn, counting its calls."""
    remaining = list(steps)
    calls = []

    def call_once():
        calls.append(len(calls) + 1)
        step = remaining.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    return call_once, calls


def run(call_once, **overrides):
    arguments = dict(scheme=SCHEME, label=LABEL, model="gemma3:4b", input_truncated=False,
                     max_tokens=CLASSIFICATION_MAX_TOKENS)
    arguments.update(overrides)
    return run_classification_attempts(call_once, **arguments)


def attempt_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]


# --- The happy path -------------------------------------------------------------------------


def test_a_conforming_reply_is_returned_after_exactly_one_call():
    call_once, calls = scripted(CONFORMING)

    result = run(call_once, model="gemma3:4b", input_truncated=True)

    assert isinstance(result, DocumentClassification)
    assert result.doc_type == Assignment(value="Procedure", confidence=0.9)
    assert result.department == Assignment(value="Finance", confidence=0.6)
    assert result.tags == (TagSuggestion(dimension="Process", value="onboarding", confidence=0.8),)
    assert result.model == "gemma3:4b"  # the provider's, written on, never parsed
    assert result.input_truncated is True  # the caller's flag, written on, never parsed
    assert calls == [1]


def test_a_chat_reply_object_and_bare_text_are_both_accepted():
    call_once, _ = scripted(ChatReply(text=CONFORMING, finish_reason="stop", completion_tokens=40, prompt_tokens=900))
    assert run(call_once).doc_type.value == "Procedure"
    call_once, _ = scripted(CONFORMING)
    assert run(call_once).doc_type.value == "Procedure"


# --- Retry: the malformed reply ---------------------------------------------------------------


def test_a_reply_that_conforms_on_the_second_attempt_returns_and_the_count_is_two():
    call_once, calls = scripted("Sure! Here is the classification in prose.", CONFORMING)

    result = run(call_once)

    assert result.doc_type.value == "Procedure"
    assert calls == [1, 2]


def test_three_malformed_replies_raise_provider_unavailable_after_exactly_three_calls():
    """THE assertion: exactly MAXIMUM_CLASSIFY_ATTEMPTS calls, an equality, then ProviderUnavailable.

    The constant is a total of 3 (1 initial call + 2 retries, D-19); if someone reconciles the
    proposal's "2 retries" wording by setting it to 2, this fails."""
    call_once, calls = scripted("no json", "{not json", '{"answer": "Policy"}')

    with pytest.raises(ProviderUnavailable) as excinfo:
        run(call_once)

    assert len(calls) == MAXIMUM_CLASSIFY_ATTEMPTS == 3
    assert "CLASSIFICATION_SCHEMA" in str(excinfo.value)
    assert LABEL in str(excinfo.value)  # which provider could not answer
    assert "schema violation" in str(excinfo.value)  # and the last failure


def test_a_type_outside_the_fixed_list_is_a_failed_attempt_and_is_retried():
    """Invariant 10 applied to FR-10's fixed list: valid JSON, right shape, wrong type — no reply."""
    call_once, calls = scripted(OUT_OF_SCHEME_TYPE, CONFORMING)

    result = run(call_once)

    assert result.doc_type.value == "Procedure"
    assert calls == [1, 2]


def test_three_replies_with_a_type_outside_the_list_are_an_outage_not_a_corrected_type():
    call_once, calls = scripted(*[OUT_OF_SCHEME_TYPE] * MAXIMUM_CLASSIFY_ATTEMPTS)

    with pytest.raises(ProviderUnavailable, match="document types"):
        run(call_once)
    assert len(calls) == MAXIMUM_CLASSIFY_ATTEMPTS


# --- Retry: the transport failure -------------------------------------------------------------


def test_a_transport_failure_is_a_failed_attempt_and_is_retried():
    call_once, calls = scripted(unavailable(), unavailable(), CONFORMING)

    result = run(call_once)

    assert result.doc_type.value == "Procedure"
    assert calls == [1, 2, 3]


def test_three_transport_failures_raise_provider_unavailable_naming_the_last_one():
    call_once, calls = scripted(*[unavailable() for _ in range(MAXIMUM_CLASSIFY_ATTEMPTS)])

    with pytest.raises(ProviderUnavailable) as excinfo:
        run(call_once)

    assert len(calls) == MAXIMUM_CLASSIFY_ATTEMPTS
    assert "call failed" in str(excinfo.value)
    assert "unreachable" in str(excinfo.value)


def test_a_mixture_of_failure_kinds_still_stops_at_three_attempts():
    """The budget is attempts, not attempts of each kind: nothing resets the counter."""
    call_once, calls = scripted(unavailable(), "prose", OUT_OF_SCHEME_TYPE)

    with pytest.raises(ProviderUnavailable):
        run(call_once)
    assert len(calls) == MAXIMUM_CLASSIFY_ATTEMPTS


# --- Anything else propagates after one call --------------------------------------------------


class UndecidedError(Exception):
    """Stands in for an exception the provider did not decide, which is a bug, not an outage.

    Since D-118 a 4xx is not one of these: the providers raise it as ProviderUnavailable,
    and test_classification_providers.py asserts that it is retried as a failed attempt.
    """


@pytest.mark.parametrize("error", [UndecidedError("unexpected"), ValueError("bad request")], ids=["undecided", "ValueError"])
def test_any_other_exception_propagates_as_itself_after_one_call(error):
    call_once, calls = scripted(error, CONFORMING, CONFORMING)

    with pytest.raises(type(error)) as excinfo:
        run(call_once)

    assert excinfo.value is error
    assert not isinstance(excinfo.value, ProviderUnavailable)
    assert calls == [1]  # no retries


# --- The attempt log -----------------------------------------------------------------------------


def test_each_attempt_is_logged_under_the_classification_step(caplog):
    """A failed call, a schema violation and a parsed reply: three lines, in order, with the step,
    the number of the total, the cause and the reply facts; the parsed line at INFO."""
    call_once, _ = scripted(
        unavailable(ConnectionError("refused")),
        ChatReply(text="prose", finish_reason="stop", completion_tokens=12, prompt_tokens=800),
        ChatReply(text=CONFORMING, finish_reason="stop", completion_tokens=61, prompt_tokens=800),
    )

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with attempt_log.account("account-4"):
            run(call_once)

    records = [r for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]
    assert [r.levelno for r in records] == [logging.WARNING, logging.WARNING, logging.INFO]
    first, second, third = (r.getMessage() for r in records)
    assert re.fullmatch(
        rf"classification attempt 1 of {MAXIMUM_CLASSIFY_ATTEMPTS} failed after \d+\.\d s "
        rf"\[finish_reason=unreported completion_tokens=unreported prompt_tokens=unreported "
        rf"max_tokens={CLASSIFICATION_MAX_TOKENS} max_statements=unreported\] "
        r"\(account account-4\): ConnectionError: .+unreachable.+",
        first,
    ), first
    assert re.fullmatch(
        rf"classification attempt 2 of {MAXIMUM_CLASSIFY_ATTEMPTS} failed after \d+\.\d s "
        rf"\[finish_reason=stop completion_tokens=12 prompt_tokens=800 "
        rf"max_tokens={CLASSIFICATION_MAX_TOKENS} max_statements=unreported\] "
        r"\(account account-4\): SchemaViolation: no JSON object in the response",
        second,
    ), second
    assert re.fullmatch(
        rf"classification attempt 3 of {MAXIMUM_CLASSIFY_ATTEMPTS} parsed after \d+\.\d s "
        rf"\[finish_reason=stop completion_tokens=61 prompt_tokens=800 "
        rf"max_tokens={CLASSIFICATION_MAX_TOKENS} max_statements=unreported\] "
        r"\(account account-4\): 1 tag\(s\)",
        third,
    ), third


def test_no_line_quotes_the_reply(caplog):
    """A suggested type, department or tag is the model's reply, and the log quotes no reply."""
    call_once, _ = scripted(OUT_OF_SCHEME_TYPE, CONFORMING)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        run(call_once)

    for line in attempt_lines(caplog):
        for value in ("Memo", "Procedure", "Finance", "onboarding"):
            assert value not in line, line


def test_logging_changes_no_attempt_count(caplog):
    call_once, calls = scripted(*[unavailable() for _ in range(MAXIMUM_CLASSIFY_ATTEMPTS)])

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with pytest.raises(ProviderUnavailable):
            run(call_once)

    assert len(calls) == MAXIMUM_CLASSIFY_ATTEMPTS
    lines = attempt_lines(caplog)
    assert len(lines) == MAXIMUM_CLASSIFY_ATTEMPTS
    assert all(line.startswith("classification attempt ") for line in lines)
    assert all("(account not set)" in line for line in lines)


def test_a_first_attempt_that_parses_logs_no_warning(caplog):
    call_once, _ = scripted(CONFORMING)

    with caplog.at_level(logging.WARNING, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        run(call_once)

    assert attempt_lines(caplog) == []


# --- No observer -------------------------------------------------------------------------------


def test_the_loop_has_no_on_attempt_observer():
    """``on_attempt`` is generation's hook for the citation harness; nothing measures classification
    per attempt, and a second route from a raw reply into apps/ is not opened here."""
    parameters = inspect.signature(run_classification_attempts).parameters
    assert "on_attempt" not in parameters
    assert [name for name, p in parameters.items() if p.kind is p.POSITIONAL_OR_KEYWORD] == ["call_once"]
    assert set(parameters) == {"call_once", "scheme", "label", "model", "input_truncated", "max_tokens"}
