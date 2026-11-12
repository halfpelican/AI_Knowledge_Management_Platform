"""The summary attempt loop (apps/ai/summarisation.py): run_summary_attempts (FR-16, D-125).

FR-16 Server-End states two different allowances, and the loop has to honour both at once:

    The response is schema-validated before storage, and a malformed response triggers one retry.
    Failures are retried twice before the summary is marked unavailable.

So, with ``MAXIMUM_SUMMARY_ATTEMPTS`` a TOTAL of 3 (1 initial call + 2 retries) and
``MAXIMUM_MALFORMED_SUMMARY_REPLIES`` 2 (1 malformed reply + 1 retry):

- a failed call (ProviderUnavailable from ``call_once``: unreachable, a 5xx, a 429) is retried
  until three calls have been made, then ProviderUnavailable;
- a refused call (ProviderRefused: any other 4xx, D-118) is re-raised after ONE call;
- the first malformed reply is retried; the SECOND raises MalformedSummary at once, even with an
  attempt left;
- the two counts share one budget of three calls, so a mixture never makes a fourth;
- anything else ``call_once`` raises propagates after one call and consumes no retry.

Exercised directly, with a scripted ``call_once``, so each count is the loop's own; the two
providers are exercised through their fakes in test_summarisation_providers.py. Every attempt is
recorded through apps/ai/attempt_log.py under the step "summarisation", and no line quotes the reply.
"""

from __future__ import annotations

import inspect
import json
import logging
import re

import pytest

from apps.ai import attempt_log
from apps.ai.base import (
    ExtractedActionItem,
    MalformedSummary,
    MeetingSummaryDraft,
    ProviderRefused,
    ProviderUnavailable,
    SummaryElement,
)
from apps.ai.generation import ChatReply
from apps.ai.summarisation import SUMMARY_MAX_TOKENS, run_summary_attempts
from apps.core.constants import MAXIMUM_MALFORMED_SUMMARY_REPLIES, MAXIMUM_SUMMARY_ATTEMPTS

# Distinctive words, so a log line that quoted the reply would be caught by name.
CONFORMING = json.dumps(
    {
        "summary": [{"text": "The Wombat programme was paused.", "passages": ["P1"]}],
        "decisions": [{"text": "Wombat is paused until Easter.", "passages": ["P2"]}],
        "highlights": [],
        "action_items": [
            {"description": "Tell the Wombat suppliers", "owner": "Quentin", "due": "next Friday",
             "passages": ["P2"]},
        ],
    }
)
REPLY_WORDS = ("Wombat", "Easter", "Quentin", "suppliers", "next Friday")
# Three ways of breaking SUMMARY_SCHEMA: prose, JSON of the wrong shape, and a sentence citing nothing.
PROSE = "The Wombat programme was paused until Easter; Quentin will tell the suppliers."
WRONG_SHAPE = json.dumps({"summary": "The Wombat programme was paused."})
CITES_NOTHING = CONFORMING.replace('["P1"]', "[]")
LABEL = "FLM at http://flm.test/v1"
MODEL = "gemma3:4b"


def unavailable(cause: Exception | None = None) -> ProviderUnavailable:
    """What a provider's one-call function raises for a failed call, with its cause."""
    try:
        raise ProviderUnavailable("http://flm.test/v1 unreachable: refused") from cause
    except ProviderUnavailable as exc:
        return exc


def refused() -> ProviderRefused:
    return ProviderRefused("http://flm.test/v1 refused the request with HTTP 401: invalid api key")


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
    arguments = dict(label=LABEL, model=MODEL, max_tokens=SUMMARY_MAX_TOKENS)
    arguments.update(overrides)
    return run_summary_attempts(call_once, **arguments)


def attempt_records(caplog):
    return [r for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]


def attempt_lines(caplog):
    return [r.getMessage() for r in attempt_records(caplog)]


# --- The two constants -------------------------------------------------------------------------


def test_the_attempt_constants_are_totals_as_fr16_words_them():
    """"Failures are retried twice": three calls. "A malformed response triggers one retry": two
    malformed replies. If someone reconciles either wording by subtracting one, this fails."""
    assert MAXIMUM_SUMMARY_ATTEMPTS == 3  # 1 initial call + 2 retries
    assert MAXIMUM_MALFORMED_SUMMARY_REPLIES == 2  # 1 malformed reply + 1 retry
    assert MAXIMUM_MALFORMED_SUMMARY_REPLIES < MAXIMUM_SUMMARY_ATTEMPTS


# --- The happy path -------------------------------------------------------------------------------


def test_a_conforming_reply_is_returned_after_exactly_one_call():
    call_once, calls = scripted(CONFORMING)

    result = run(call_once)

    assert isinstance(result, MeetingSummaryDraft)
    assert result.narrative == (SummaryElement(text="The Wombat programme was paused.", passages=(1,)),)
    assert result.decisions == (SummaryElement(text="Wombat is paused until Easter.", passages=(2,)),)
    assert result.highlights == ()
    assert result.action_items == (
        ExtractedActionItem(
            description="Tell the Wombat suppliers", owner="Quentin", due="next Friday", passages=(2,)
        ),
    )
    assert calls == [1]


def test_the_draft_carries_the_model_it_was_given_and_never_parses_one():
    """UC-04: the summary carries "a record of the model that produced it". The name is the
    provider's, written on; a reply cannot name its own model."""
    call_once, _ = scripted(CONFORMING)
    assert run(call_once, model="claude-haiku-5-5").model == "claude-haiku-5-5"

    call_once, _ = scripted(CONFORMING)
    assert run(call_once, model="gemma3:4b").model == "gemma3:4b"


def test_a_chat_reply_object_and_bare_text_are_both_accepted():
    call_once, _ = scripted(ChatReply(text=CONFORMING, finish_reason="stop", completion_tokens=140, prompt_tokens=2100))
    from_reply = run(call_once)
    call_once, _ = scripted(CONFORMING)
    from_text = run(call_once)

    assert from_reply == from_text
    assert from_text.narrative[0].text == "The Wombat programme was paused."


def test_an_empty_action_item_section_is_returned_and_not_retried():
    """UC-04 A1: a meeting that raised no action items is a result. A loop that retried it would
    spend its attempts on a correct reply and then mark the summary unavailable."""
    call_once, calls = scripted(json.dumps(
        {"summary": [{"text": "The team met.", "passages": ["P1"]}], "decisions": [], "highlights": [],
         "action_items": []}
    ))

    result = run(call_once)

    assert result.action_items == ()
    assert calls == [1]


# --- Failed calls: retried twice, three calls in all -------------------------------------------------


def test_three_failed_calls_raise_provider_unavailable_after_exactly_three_calls():
    """THE assertion for "Failures are retried twice": exactly MAXIMUM_SUMMARY_ATTEMPTS calls, an
    equality, then ProviderUnavailable and not one of its two subclasses."""
    call_once, calls = scripted(*[unavailable() for _ in range(5)])

    with pytest.raises(ProviderUnavailable) as excinfo:
        run(call_once)

    assert len(calls) == MAXIMUM_SUMMARY_ATTEMPTS == 3
    assert type(excinfo.value) is ProviderUnavailable
    assert "SUMMARY_SCHEMA" in str(excinfo.value)
    assert LABEL in str(excinfo.value)  # which provider could not answer
    assert "call failed" in str(excinfo.value)  # and the last failure
    assert "unreachable" in str(excinfo.value)


def test_a_failed_call_is_retried_and_the_third_call_can_succeed():
    call_once, calls = scripted(unavailable(), unavailable(), CONFORMING)

    result = run(call_once)

    assert result.narrative[0].text == "The Wombat programme was paused."
    assert calls == [1, 2, 3]


# --- A refusal: one call, never retried (D-118) -------------------------------------------------------


def test_a_refused_call_is_re_raised_after_exactly_one_call():
    """A bad key or an exhausted credit would be refused the same way three times. The exception
    is the provider's own, re-raised as itself, so the caller records "provider_refused"."""
    error = refused()
    call_once, calls = scripted(error, CONFORMING, CONFORMING)

    with pytest.raises(ProviderRefused) as excinfo:
        run(call_once)

    assert excinfo.value is error
    assert calls == [1]


def test_a_refusal_after_a_failed_call_still_ends_the_loop_at_once():
    error = refused()
    call_once, calls = scripted(unavailable(), error, CONFORMING)

    with pytest.raises(ProviderRefused) as excinfo:
        run(call_once)

    assert excinfo.value is error
    assert calls == [1, 2]


# --- Malformed replies: exactly one retry ---------------------------------------------------------------


@pytest.mark.parametrize("malformed", [PROSE, WRONG_SHAPE, CITES_NOTHING, ""],
                         ids=["prose", "wrong shape", "cites nothing", "empty"])
def test_a_malformed_reply_then_a_conforming_one_succeeds_on_the_second_call(malformed):
    call_once, calls = scripted(malformed, CONFORMING)

    result = run(call_once)

    assert result.narrative[0].text == "The Wombat programme was paused."
    assert calls == [1, 2]


def test_two_malformed_replies_raise_malformed_summary_after_exactly_two_calls():
    """THE assertion for "a malformed response triggers one retry": TWO calls, though a third
    attempt remains. A loop that treated a malformed reply like any failed attempt would make
    three; the third reply is scripted as conforming, so that loop would return a summary here."""
    call_once, calls = scripted(PROSE, WRONG_SHAPE, CONFORMING)

    with pytest.raises(MalformedSummary) as excinfo:
        run(call_once)

    assert len(calls) == MAXIMUM_MALFORMED_SUMMARY_REPLIES == 2
    assert len(calls) < MAXIMUM_SUMMARY_ATTEMPTS  # an attempt was left, and was not spent
    assert "SUMMARY_SCHEMA" in str(excinfo.value)
    assert LABEL in str(excinfo.value)
    assert "schema violation" in str(excinfo.value)


def test_malformed_summary_is_a_provider_unavailable_so_a_caller_of_outages_still_fails_the_run():
    call_once, _ = scripted(PROSE, PROSE)

    with pytest.raises(ProviderUnavailable) as excinfo:
        run(call_once)

    assert isinstance(excinfo.value, MalformedSummary)
    assert not isinstance(excinfo.value, ProviderRefused)


# --- Mixtures: one budget of three calls, two allowances inside it ----------------------------------------


def test_a_failed_call_then_two_malformed_replies_is_malformed_summary_at_the_third_call():
    call_once, calls = scripted(unavailable(), PROSE, WRONG_SHAPE, CONFORMING)

    with pytest.raises(MalformedSummary):
        run(call_once)

    assert calls == [1, 2, 3]


def test_a_malformed_reply_then_two_failed_calls_is_provider_unavailable_after_three_calls():
    """One malformed reply is inside its allowance, so the run ended on the outage: the reason the
    caller records is "provider_unavailable", not "malformed"."""
    call_once, calls = scripted(PROSE, unavailable(), unavailable(), CONFORMING)

    with pytest.raises(ProviderUnavailable) as excinfo:
        run(call_once)

    assert calls == [1, 2, 3]
    assert type(excinfo.value) is ProviderUnavailable
    assert not isinstance(excinfo.value, MalformedSummary)
    assert "call failed" in str(excinfo.value)


def test_a_malformed_reply_a_failed_call_and_a_malformed_reply_is_malformed_summary():
    """The malformed count is not reset by the failed call between them."""
    call_once, calls = scripted(PROSE, unavailable(), WRONG_SHAPE, CONFORMING)

    with pytest.raises(MalformedSummary):
        run(call_once)

    assert calls == [1, 2, 3]


@pytest.mark.parametrize(
    "steps",
    [
        (unavailable(), PROSE, CONFORMING),
        (PROSE, unavailable(), CONFORMING),
        (unavailable(), unavailable(), CONFORMING),
    ],
    ids=["outage, malformed", "malformed, outage", "outage, outage"],
)
def test_one_failure_of_each_kind_leaves_the_third_call_to_succeed(steps):
    call_once, calls = scripted(*steps)

    result = run(call_once)

    assert result.narrative[0].text == "The Wombat programme was paused."
    assert calls == [1, 2, 3]


@pytest.mark.parametrize(
    "steps",
    [
        (unavailable(), unavailable(), unavailable()),
        (PROSE, WRONG_SHAPE),
        (unavailable(), PROSE, PROSE),
        (PROSE, unavailable(), unavailable()),
        (unavailable(), unavailable(), PROSE),
        (PROSE, unavailable(), PROSE),
    ],
)
def test_no_mixture_ever_makes_a_fourth_call(steps):
    """Each script would succeed on one call more than the policy allows."""
    call_once, calls = scripted(*steps, CONFORMING, CONFORMING)

    with pytest.raises(ProviderUnavailable):
        run(call_once)

    assert len(calls) == len(steps) <= MAXIMUM_SUMMARY_ATTEMPTS


# --- Anything else propagates after one call ---------------------------------------------------------------


class UndecidedError(Exception):
    """Stands in for an exception the provider did not decide, which is a bug, not an outage."""


@pytest.mark.parametrize("error", [UndecidedError("unexpected"), ValueError("bad request"), KeyError("choices")],
                         ids=["undecided", "ValueError", "KeyError"])
def test_any_other_exception_propagates_as_itself_after_one_call(error):
    call_once, calls = scripted(error, CONFORMING, CONFORMING)

    with pytest.raises(type(error)) as excinfo:
        run(call_once)

    assert excinfo.value is error
    assert not isinstance(excinfo.value, ProviderUnavailable)
    assert calls == [1]  # no retries


# --- The attempt log ------------------------------------------------------------------------------------------


def test_each_attempt_is_logged_under_the_summarisation_step(caplog):
    """A failed call, a schema violation and a parsed reply: three lines, in order, with the step,
    the number of the total, the cause and the reply facts; the parsed line at INFO with its counts."""
    call_once, _ = scripted(
        unavailable(ConnectionError("refused")),
        ChatReply(text=PROSE, finish_reason="stop", completion_tokens=22, prompt_tokens=2100),
        ChatReply(text=CONFORMING, finish_reason="stop", completion_tokens=140, prompt_tokens=2100),
    )

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with attempt_log.account("account-4"):
            run(call_once)

    records = attempt_records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING, logging.WARNING, logging.INFO]
    first, second, third = (r.getMessage() for r in records)
    assert re.fullmatch(
        rf"summarisation attempt 1 of {MAXIMUM_SUMMARY_ATTEMPTS} failed after \d+\.\d s "
        rf"\[finish_reason=unreported completion_tokens=unreported prompt_tokens=unreported "
        rf"max_tokens={SUMMARY_MAX_TOKENS} max_statements=unreported\] "
        r"\(account account-4\): ConnectionError: .+unreachable.+",
        first,
    ), first
    assert re.fullmatch(
        rf"summarisation attempt 2 of {MAXIMUM_SUMMARY_ATTEMPTS} failed after \d+\.\d s "
        rf"\[finish_reason=stop completion_tokens=22 prompt_tokens=2100 "
        rf"max_tokens={SUMMARY_MAX_TOKENS} max_statements=unreported\] "
        r"\(account account-4\): SchemaViolation: no JSON object in the response",
        second,
    ), second
    assert re.fullmatch(
        rf"summarisation attempt 3 of {MAXIMUM_SUMMARY_ATTEMPTS} parsed after \d+\.\d s "
        rf"\[finish_reason=stop completion_tokens=140 prompt_tokens=2100 "
        rf"max_tokens={SUMMARY_MAX_TOKENS} max_statements=unreported\] "
        r"\(account account-4\): 1 sentence\(s\), 1 decision\(s\), 0 highlight\(s\), 1 action item\(s\)",
        third,
    ), third


def test_a_first_attempt_that_parses_logs_one_info_line_and_no_warning(caplog):
    call_once, _ = scripted(CONFORMING)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        run(call_once)

    (record,) = attempt_records(caplog)
    assert record.levelno == logging.INFO
    assert record.getMessage().startswith(f"summarisation attempt 1 of {MAXIMUM_SUMMARY_ATTEMPTS} parsed after ")


@pytest.mark.parametrize(
    "steps,warnings,infos",
    [
        ((unavailable(), unavailable(), unavailable()), 3, 0),
        ((PROSE, WRONG_SHAPE), 2, 0),
        ((unavailable(), PROSE, CITES_NOTHING), 3, 0),
        ((PROSE, CONFORMING), 1, 1),
        ((unavailable(), unavailable(), CONFORMING), 2, 1),
        ((refused(),), 1, 0),
    ],
    ids=["three outages", "two malformed", "outage then two malformed", "malformed then parsed",
         "two outages then parsed", "refused"],
)
def test_there_is_one_warning_per_failure_and_one_info_for_the_parsed_attempt(caplog, steps, warnings, infos):
    call_once, calls = scripted(*steps)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        try:
            run(call_once)
        except ProviderUnavailable:
            pass

    records = attempt_records(caplog)
    assert [r.levelno for r in records].count(logging.WARNING) == warnings
    assert [r.levelno for r in records].count(logging.INFO) == infos
    assert len(records) == len(calls) == len(steps)  # one line per call, and logging changed no count
    for number, record in enumerate(records, start=1):
        assert record.getMessage().startswith(f"summarisation attempt {number} of {MAXIMUM_SUMMARY_ATTEMPTS} ")


def test_no_line_quotes_the_reply(caplog):
    """A summary is the meeting's content, and the log quotes no reply: not a sentence, a decision,
    an owner or a deadline, from a malformed reply or from a parsed one."""
    call_once, _ = scripted(PROSE, CONFORMING)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        run(call_once)

    lines = attempt_lines(caplog)
    assert len(lines) == 2
    for line in lines:
        for word in REPLY_WORDS:
            assert word not in line, line


@pytest.mark.parametrize("malformed", [WRONG_SHAPE, CITES_NOTHING, CONFORMING.replace('"P2"', '"Wombat-2"')],
                         ids=["wrong shape", "cites nothing", "bad label"])
def test_no_line_quotes_a_reply_that_broke_the_schema_twice(caplog, malformed):
    call_once, _ = scripted(malformed, malformed)

    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        with pytest.raises(MalformedSummary) as excinfo:
            run(call_once)

    for text in (*attempt_lines(caplog), str(excinfo.value)):
        for word in REPLY_WORDS:
            assert word not in text, text


def test_the_attempts_file_holds_every_attempt_and_the_error_file_only_the_failures(
    error_log_file, attempts_log_file
):
    """Under the shipped LOGGING as conftest.py builds it, with nothing lowered by the test: the
    attempts file holds the failed attempt and the parsed one; the error file holds the failure
    only; and neither holds a word of the reply."""
    call_once, _ = scripted(
        ChatReply(text=PROSE, finish_reason="stop", completion_tokens=22, prompt_tokens=2100),
        ChatReply(text=CONFORMING, finish_reason="stop", completion_tokens=140, prompt_tokens=2100),
    )

    with attempt_log.account("account-9"):
        run(call_once)

    attempts = attempts_log_file.read_text(encoding="utf-8").splitlines()
    assert len(attempts) == 2
    assert f" WARNING apps.ai.attempts summarisation attempt 1 of {MAXIMUM_SUMMARY_ATTEMPTS} failed after " in attempts[0]
    assert f" INFO apps.ai.attempts summarisation attempt 2 of {MAXIMUM_SUMMARY_ATTEMPTS} parsed after " in attempts[1]
    assert "(account account-9): 1 sentence(s), 1 decision(s), 0 highlight(s), 1 action item(s)" in attempts[1]
    errors = error_log_file.read_text(encoding="utf-8").splitlines()
    assert len(errors) == 1
    assert f" WARNING apps.ai.attempts summarisation attempt 1 of {MAXIMUM_SUMMARY_ATTEMPTS} failed after " in errors[0]
    for text in (*attempts, *errors):
        for word in REPLY_WORDS:
            assert word not in text, text


# --- No observer ---------------------------------------------------------------------------------------------------


def test_the_loop_has_no_on_attempt_observer():
    """``on_attempt`` is generation's hook for the citation harness; nothing measures a summary per
    attempt, and a second route from a raw reply into apps/ is not opened here."""
    parameters = inspect.signature(run_summary_attempts).parameters
    assert "on_attempt" not in parameters
    assert [name for name, p in parameters.items() if p.kind is p.POSITIONAL_OR_KEYWORD] == ["call_once"]
    assert set(parameters) == {"call_once", "label", "model", "max_tokens"}
