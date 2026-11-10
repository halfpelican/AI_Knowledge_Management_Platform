"""The generation attempt loop, shared by both providers (NFR-19, D-19).

One definition of "structured output or nothing" (CLAUDE.md invariant 10) and one
definition of the retry policy, used by FLMService and AnthropicService alike. Written
once rather than twice because the two copies would be identical on the day they were
written and the NFR-19 fault-injection test only ever exercises one of them.

The policy, exactly:

- MAXIMUM_GENERATION_ATTEMPTS is a TOTAL of 1 initial call + 2 retries (D-19).
- A reply that does not parse into STATEMENT_LIST_SCHEMA is a failed attempt, not a
  partial answer.
- A transport failure — the provider unreachable, timed out, or answering 5xx — is also
  a failed attempt. The provider's ``call_once`` signals it by raising
  ProviderUnavailable.
- A 4xx is a failed attempt too, since D-118 (10 November 2026). The provider logs its
  status and body (apps/ai/attempt_log.py: a 429 as a WARNING, anything else as an
  ERROR) and raises ProviderUnavailable, as ``_openai_compat.embed`` does. Until then a 4xx
  surfaced as itself, on the reasoning that a misconfiguration is not an outage. On FLM
  that never arose. On the ``anthropic`` provider a rate limit and an exhausted credit
  are routine 4xx, and surfacing them reached the user as a 500, not NFR-19's 503. A
  mistyped model name now costs two wasted retries and a 503, with its cause in the log.
- After the last attempt, ProviderUnavailable, which the view turns into the NFR-19 503.
- An EMPTY statement list that parses is a successful attempt and is returned as-is. It
  is the model correctly reporting that the passages do not answer the question, and
  FR-12's second no-answer path depends on receiving it rather than retrying it.
- **The statement cap (step 7 phase 2a, 7 November 2026).** Each attempt asks for at most
  a number of statements, passed to ``call_once`` and held against the reply by the
  parser. The first attempt asks for MAXIMUM_STATEMENTS. After a reply that hit the token
  ceiling (``completion_tokens`` at or above the ``max_tokens`` sent) or held more
  statements than asked for, the next attempt asks for ``fewer_statements`` of the last
  number. Phase 1 showed that repeating the identical request never recovered a reply cut
  off at the ceiling (D-82's note of 7 November 2026). After any other failure the number
  stays. The attempt COUNT is unchanged: three in total, whatever each one asks for, and a
  reply over its cap is rejected whole, never trimmed (invariant 10).

``on_attempt`` is an observer on this loop, declared in the contract in
docs/ai-provider.md section 1 and in ``AIService`` itself. It is keyword-only, optional,
passed by nothing under ``apps/`` and used only by scripts/citation_harness.py, which
needs per-attempt records to compute the schema conformance rate the way
docs/flm-baseline.md reports it: per response, with the first-attempt rate separately.
Without it the harness would have to keep its own retry loop, and a second retry loop is
precisely the duplication item 5 exists to end. It exists to measure, not to branch on.

**An observer cannot be allowed to change what it observes**, so an exception raised
inside the callback is caught and discarded by ``_record`` below, and the loop proceeds
exactly as if no callback had been passed. The number that matters is the attempt count:
NFR-19's fault injection asserts the provider was called exactly three times before the
503, and a callback that raised on attempt 2 must not be able to make that two, or to
replace the 503 with an exception of some other type raised from a measuring instrument.
Nothing is logged when it happens — a misbehaving observer is a bug in the harness, which
is run interactively by the person who would read the traceback anyway, and a log line
here would write once per attempt into a real run's output for a fault that cannot affect
the answer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from apps.ai import attempt_log
from apps.ai.base import ProviderUnavailable, StatementList
from apps.ai.schema import SchemaViolation, StatementCapExceeded, parse_statement_list
from apps.core.constants import MAXIMUM_GENERATION_ATTEMPTS, MAXIMUM_STATEMENTS

# A single chat call's ceiling and timeout. Generous: a long passage set can justify
# several statements, and a truncated reply would be scored as a schema failure that the
# prompt did not cause. These two numbers came across from the harness with the prompt
# and the parser, because the baseline was measured at these values; they live here
# rather than in apps/core/constants.py because they are parameters of a provider call,
# not tuned retrieval constants from CLAUDE.md section 5.
GENERATION_MAX_TOKENS = 800
GENERATION_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class GenerationAttempt:
    """One attempt's record, for measurement only.

    ``outcome`` is one of "parsed", "schema-violation" or "call-failed". The strings are
    the ones scripts/citation_harness.py's report already groups by; they are a
    diagnostic vocabulary, not one of the fixed vocabularies in docs/schema-v1.md, and
    nothing in apps/ branches on them.
    """

    number: int  # 1-based, so the last is MAXIMUM_GENERATION_ATTEMPTS
    outcome: str
    seconds: float
    raw: str | None = None  # the reply text, or None where the call itself failed
    detail: str | None = None  # the violation message or the failure description
    statements: int | None = None
    max_statements: int | None = None  # the statement cap this attempt asked for


def fewer_statements(max_statements: int) -> int:
    """What the next attempt asks for after a ceiling hit or a cap violation: half, at least 1.

    With MAXIMUM_STATEMENTS at 6, the three attempts can ask for 6, 3 and 1. Once at 1 the
    number stays at 1: an answer of one cited statement is still an answer.
    """
    return max(1, max_statements // 2)


def _hit_ceiling(reply: ChatReply, max_tokens: int | None) -> bool:
    """The reply used every token it was allowed: ``completion_tokens`` >= ``max_tokens``.

    Read from the reported count, because FLM v0.9.39 answers ``finish_reason`` "stop" for a
    reply cut off at the ceiling (D-82's note of 7 November 2026). Unreported counts are
    never a ceiling hit.
    """
    return (
        reply.completion_tokens is not None
        and max_tokens is not None
        and reply.completion_tokens >= max_tokens
    )


@dataclass(frozen=True)
class ChatReply:
    """One provider call's reply text, and what the provider reported about it.

    Returned by each provider's ``call_once`` (7 November 2026), so the attempt log can
    record how every reply ended (apps/ai/attempt_log.py). Only ``text`` is parsed; the
    other three are logged and nothing branches on them. None means the provider did not
    report the value.
    """

    text: str
    finish_reason: str | None = None  # verbatim: FLM's finish_reason, Anthropic's stop_reason
    completion_tokens: int | None = None
    prompt_tokens: int | None = None


def run_generation_attempts(
    *,
    call_once: Callable[[int], str | ChatReply],
    label: str,
    on_attempt: Callable[[GenerationAttempt], None] | None = None,
    max_tokens: int | None = None,
) -> StatementList:
    """Call ``call_once`` until it returns a conforming reply, or give up loudly.

    ``call_once(max_statements)`` makes one provider call whose prompt asks for at most
    ``max_statements`` statements. It returns the model's reply, as a ChatReply or as bare
    text, and raises ProviderUnavailable for a failed call (a transport failure, or any
    status error since D-118); anything else it raises propagates untouched. Bare text is a reply the provider reported nothing about:
    both providers return a ChatReply, and the suite's scripted fakes return text.
    ``label`` names the provider and endpoint in the final message, so a 503 says which
    provider could not answer. ``max_tokens`` is the value the provider's request carries:
    each attempt's line records it, and a reply that reaches it makes the next attempt ask
    for fewer statements.
    """
    last_detail = "no attempt was made"
    # Read here, at call time, rather than bound as a default: the one name the first
    # attempt's cap comes from.
    max_statements = MAXIMUM_STATEMENTS
    for number in range(1, MAXIMUM_GENERATION_ATTEMPTS + 1):  # 1 initial call + 2 retries
        started = time.perf_counter()
        try:
            reply = call_once(max_statements)
        except ProviderUnavailable as exc:
            # A transport failure says nothing about the reply's length: the number stays.
            last_detail = f"call failed: {exc}"
            _record(on_attempt, number, "call-failed", started, detail=str(exc),
                    max_statements=max_statements)
            attempt_log.failed_attempt(
                "generation", number, MAXIMUM_GENERATION_ATTEMPTS, time.perf_counter() - started,
                attempt_log.cause_of(exc), str(exc),
                reply=attempt_log.ReplyFacts(max_tokens=max_tokens, max_statements=max_statements),
            )
            continue
        if not isinstance(reply, ChatReply):
            reply = ChatReply(text=reply)
        raw = reply.text
        facts = attempt_log.ReplyFacts(
            max_tokens=max_tokens,
            finish_reason=reply.finish_reason,
            completion_tokens=reply.completion_tokens,
            prompt_tokens=reply.prompt_tokens,
            max_statements=max_statements,
        )
        try:
            parsed = parse_statement_list(raw, max_statements=max_statements)
        except SchemaViolation as exc:
            # Invariant 10: a reply that does not conform is no reply at all. One that broke
            # the cap is rejected whole too, never trimmed to fit.
            last_detail = f"schema violation: {exc}"
            _record(on_attempt, number, "schema-violation", started, raw=raw, detail=str(exc),
                    max_statements=max_statements)
            attempt_log.failed_attempt(
                "generation", number, MAXIMUM_GENERATION_ATTEMPTS, time.perf_counter() - started,
                "SchemaViolation", str(exc),
                reply=facts,
            )
            if isinstance(exc, StatementCapExceeded) or _hit_ceiling(reply, max_tokens):
                # Too long, by count or by tokens: the next attempt asks for fewer, instead
                # of repeating a request phase 1 saw never recover.
                max_statements = fewer_statements(max_statements)
            continue
        _record(
            on_attempt,
            number,
            "parsed",
            started,
            raw=raw,
            statements=len(parsed.statements),
            max_statements=max_statements,
        )
        attempt_log.parsed_attempt(
            number, MAXIMUM_GENERATION_ATTEMPTS, time.perf_counter() - started,
            len(parsed.statements), reply=facts,
        )
        return parsed
    raise ProviderUnavailable(
        f"{label} returned no response conforming to STATEMENT_LIST_SCHEMA in "
        f"{MAXIMUM_GENERATION_ATTEMPTS} attempts; last failure: {last_detail}"
    )


def _record(on_attempt, number, outcome, started, *, raw=None, detail=None, statements=None,
            max_statements=None):
    """Hand one attempt to the observer, and let nothing it does reach the caller."""
    if on_attempt is None:
        return
    try:
        on_attempt(
            GenerationAttempt(
                number=number,
                outcome=outcome,
                seconds=round(time.perf_counter() - started, 1),
                raw=raw,
                detail=detail,
                statements=statements,
                max_statements=max_statements,
            )
        )
    except Exception:  # noqa: BLE001 - deliberately every exception; see the module docstring
        # Swallowed, and not logged. The attempt loop continues exactly as it would have
        # with no callback: the same number of provider calls, the same return value, and
        # the same ProviderUnavailable at the end. A measuring instrument may not move the
        # number it is measuring.
        pass
