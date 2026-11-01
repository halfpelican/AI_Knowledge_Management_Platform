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
- A 4xx is NOT a failed attempt. It is a configuration or request error, it will fail
  identically three times, and it surfaces unchanged so it is read as the bug it is
  rather than as an outage. It therefore consumes no retries, which mirrors
  ``_openai_compat.embed``.
- After the last attempt, ProviderUnavailable, which the view turns into the NFR-19 503.
- An EMPTY statement list that parses is a successful attempt and is returned as-is. It
  is the model correctly reporting that the passages do not answer the question, and
  FR-12's second no-answer path depends on receiving it rather than retrying it.

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

import time
from dataclasses import dataclass
from typing import Callable

from apps.ai import attempt_log
from apps.ai.base import ProviderUnavailable, StatementList
from apps.ai.schema import SchemaViolation, parse_statement_list
from apps.core.constants import MAXIMUM_GENERATION_ATTEMPTS

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


def run_generation_attempts(
    *,
    call_once: Callable[[], str],
    label: str,
    on_attempt: Callable[[GenerationAttempt], None] | None = None,
) -> StatementList:
    """Call ``call_once`` until it returns a conforming reply, or give up loudly.

    ``call_once`` returns the model's raw reply text and raises ProviderUnavailable for a
    retryable transport failure; anything else it raises propagates untouched.
    ``label`` names the provider and endpoint in the final message, so a 503 says which
    provider could not answer.
    """
    last_detail = "no attempt was made"
    for number in range(1, MAXIMUM_GENERATION_ATTEMPTS + 1):  # 1 initial call + 2 retries
        started = time.perf_counter()
        try:
            raw = call_once()
        except ProviderUnavailable as exc:
            last_detail = f"call failed: {exc}"
            _record(on_attempt, number, "call-failed", started, detail=str(exc))
            attempt_log.failed_attempt(
                "generation", number, MAXIMUM_GENERATION_ATTEMPTS, time.perf_counter() - started,
                attempt_log.cause_of(exc), str(exc),
            )
            continue
        try:
            parsed = parse_statement_list(raw)
        except SchemaViolation as exc:
            # Invariant 10: a reply that does not conform is no reply at all.
            last_detail = f"schema violation: {exc}"
            _record(on_attempt, number, "schema-violation", started, raw=raw, detail=str(exc))
            attempt_log.failed_attempt(
                "generation", number, MAXIMUM_GENERATION_ATTEMPTS, time.perf_counter() - started,
                "SchemaViolation", str(exc),
            )
            continue
        _record(
            on_attempt,
            number,
            "parsed",
            started,
            raw=raw,
            statements=len(parsed.statements),
        )
        return parsed
    raise ProviderUnavailable(
        f"{label} returned no response conforming to STATEMENT_LIST_SCHEMA in "
        f"{MAXIMUM_GENERATION_ATTEMPTS} attempts; last failure: {last_detail}"
    )


def _record(on_attempt, number, outcome, started, *, raw=None, detail=None, statements=None):
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
            )
        )
    except Exception:  # noqa: BLE001 - deliberately every exception; see the module docstring
        # Swallowed, and not logged. The attempt loop continues exactly as it would have
        # with no callback: the same number of provider calls, the same return value, and
        # the same ProviderUnavailable at the end. A measuring instrument may not move the
        # number it is measuring.
        pass
