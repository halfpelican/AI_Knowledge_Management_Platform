"""Failed provider attempts and the 503 they end in, logged as WARNINGs to the error file.

Added on 1 November 2026, at the user's instruction, after NFR-08's first run. That run's
two 503s could be bounded but not explained: nothing recorded a generation or embedding
attempt, and the ask view discarded the exception whose message names the cause. So a
measurement could not say whether attempts had timed out and been retried, which is the
question the user asked of it (corpus/objective-02/runs/2026-11-01/nfr08-runs.md).

**What is logged**, on the ``apps.ai.attempts`` logger, which ``platform_logging`` gives
its own WARNING handler on the error file (the root's handler there drops everything
below ERROR, and lowering it would let in every 4xx WARNING from ``django.request``):

- each failed generation attempt: its number, how long it took, and its cause, which is
  the class of the exception underneath (``APITimeoutError`` is a timeout,
  ``APIConnectionError`` a refused connection, ``InternalServerError`` a 5xx,
  ``ValueError`` FLM's 200 carrying an error body) or ``SchemaViolation``;
- each failed attempt to embed the question, the same way, and an embedding reply that
  cannot be used as a query vector;
- the 503 ``POST /api/ask`` answers, with the message of the exception that caused it;
- **each request a provider refuses with a 4xx (D-118, 10 November 2026),** with the
  status and the provider's message. A 429 is a WARNING, because a rate limit is expected
  under load and passes. Any other 4xx is an ERROR: a bad key, an unknown model, a
  malformed request or an exhausted credit, none of which a retry fixes.
  - **What the provider raises** (apps/ai/_status.py): a 429 as ProviderUnavailable, which
    callers retry, and any other 4xx as ProviderRefused, which they do not.
  - **What the user sees:** NFR-19's 503 either way.
  - **Where the cause shows:** this line, the ingestion path included, which logs no
    attempts of its own.

Each line names the account, by primary key, when the view has set it with ``account``.
Nothing logged here quotes the question, a passage or the model's reply: the details are
the exception messages, which describe the failure (``not valid JSON: ...``, ``Request
timed out.``), and they are cut at ``DETAIL_LIMIT`` characters.

**What each generation attempt's reply reported (7 November 2026),** at the user's order
for step 7: "log each attempt's finish_reason and completion-token count". D-82's notes of
1 November could only call a reply cut off at ``GENERATION_MAX_TOKENS`` "the likely
reading, not observed", because nothing recorded how a reply ended.

- **Every generation attempt's line carries a bracket,** ``[finish_reason=stop
  completion_tokens=800 prompt_tokens=1520 max_tokens=800]``: the reason the provider gave
  for ending the reply, verbatim; the completion and prompt token counts it reported; and
  the ``max_tokens`` the request sent. A value the provider did not report, or a call that
  produced no reply, reads ``unreported``. The bracket sits between the time and the
  account, so the detail stays at the end of the line. Question-embedding lines have no
  bracket and are unchanged.
- **A failed attempt is a WARNING, as before. A parsed attempt is an INFO,**
  ``generation attempt 2 of 3 parsed after 58.1 s [...] (account ...): 3 statement(s)``.
  It is not a warning, so it does not belong in the error file, and the error file's
  handler for this logger is at WARNING.
- **Every attempt goes to the attempts file (step 7 phase 2a, the user's decision of
  7 November 2026).** ``platform_logging`` gives this logger a second handler, at INFO,
  writing ``ATTEMPTS_LOG_PATH`` (default ``logs/attempts.log``), and sets the logger to INFO.
  So the attempts file holds every generation attempt, parsed or failed, and the 503 lines;
  the error file still holds the WARNINGs only. Until this, the INFO line was dropped at the
  logger on a running server.
- **The bracket also carries ``max_statements``,** the statement cap the attempt's prompt
  asked for (apps/ai/generation.py), so a reader sees when a retry asked for fewer.
- **FLM's ``finish_reason`` is recorded, not trusted.** On 7 November 2026 FLM v0.9.39
  answered ``finish_reason: "stop"`` to a request whose reply stopped at exactly
  ``max_tokens`` (20 of 20, mid-list). So the completion-token count against
  ``max_tokens`` is logged beside it, and a reader compares the two.

**Classification attempts (9 November 2026, FR-10, D-104).** The loop in
``apps/ai/classification.py`` records each attempt the same way, under the step
``classification``: a failed attempt is a WARNING and a parsed attempt an INFO line ending
``: 2 tag(s)``. The bracket's ``max_statements`` reads ``unreported`` on those lines, because a
classification request carries no statement cap. As everywhere in this file, nothing of the
reply is quoted: not the type, the department or a tag.

**It observes; it does not decide.** No attempt count, timeout or reply changes because
of it. A logging call does not raise into its caller: a handler that fails reports through
``logging``'s own ``handleError``.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from dataclasses import dataclass

ATTEMPT_LOGGER_NAME = "apps.ai.attempts"
DETAIL_LIMIT = 300
# A provider's finish_reason is a short word ("stop", "length", "end_turn"). Anything
# longer is cut, so a misbehaving server cannot write an arbitrary string into the line.
FACT_LIMIT = 40
UNREPORTED = "unreported"

logger = logging.getLogger(ATTEMPT_LOGGER_NAME)

# Per thread under Waitress, and reset when the view's block ends, so a thread reused for
# the next request never carries the previous account.
_account: contextvars.ContextVar[str | None] = contextvars.ContextVar("kmp_attempt_account", default=None)


@contextmanager
def account(user_pk):
    """Name the account on every line logged inside this block."""
    token = _account.set(str(user_pk))
    try:
        yield
    finally:
        _account.reset(token)


def cause_of(exc: BaseException) -> str:
    """The class of the exception underneath ``exc``, or of ``exc`` itself if there is none."""
    underneath = exc.__cause__ if exc.__cause__ is not None else exc
    return type(underneath).__name__


def _detail(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= DETAIL_LIMIT else text[: DETAIL_LIMIT - 3] + "..."


@dataclass(frozen=True)
class ReplyFacts:
    """What one generation attempt sent, and what the provider reported about its reply.

    ``max_tokens`` is the value the request carried. The other three are the provider's own
    report, and None where it reported nothing or there was no reply: ``finish_reason``
    verbatim (FLM's ``choices[0].finish_reason``; Anthropic's ``stop_reason``), and the
    completion and prompt token counts from its usage block.
    """

    max_tokens: int | None = None
    finish_reason: str | None = None
    completion_tokens: int | None = None
    prompt_tokens: int | None = None
    # The statement cap the attempt's prompt asked for (step 7 phase 2a): what the request
    # sent, like max_tokens, not something the provider reports.
    max_statements: int | None = None


def _fact(value) -> str:
    if value is None:
        return UNREPORTED
    return "_".join(str(value).split())[:FACT_LIMIT]


def _bracket(reply: ReplyFacts | None) -> str:
    """`` [finish_reason=... completion_tokens=... prompt_tokens=... max_tokens=...
    max_statements=...]``, or nothing for a step that has no reply to describe."""
    if reply is None:
        return ""
    return (
        f" [finish_reason={_fact(reply.finish_reason)}"
        f" completion_tokens={_fact(reply.completion_tokens)}"
        f" prompt_tokens={_fact(reply.prompt_tokens)}"
        f" max_tokens={_fact(reply.max_tokens)}"
        f" max_statements={_fact(reply.max_statements)}]"
    )


def failed_attempt(
    step: str,
    number: int,
    of: int,
    seconds: float,
    cause: str,
    detail: str,
    *,
    reply: ReplyFacts | None = None,
) -> None:
    """One failed attempt of ``step``: "generation", "question embedding", "classification",
    "transcription" (one recording segment, D-123) or "summarisation" (one meeting, D-125).

    ``reply`` is passed for a generation or a classification attempt, and adds the bracket.
    """
    logger.warning(
        "%s attempt %d of %d failed after %.1f s%s (account %s): %s: %s",
        step,
        number,
        of,
        seconds,
        _bracket(reply),
        _account.get() or "not set",
        cause,
        _detail(detail),
    )


def parsed_attempt(number: int, of: int, seconds: float, statements: int, *, reply: ReplyFacts) -> None:
    """One generation attempt whose reply parsed into STATEMENT_LIST_SCHEMA, at INFO.

    Not a warning: nothing went wrong. It reaches the attempts file and not the error file;
    see the module docstring.
    """
    logger.info(
        "generation attempt %d of %d parsed after %.1f s%s (account %s): %d statement(s)",
        number,
        of,
        seconds,
        _bracket(reply),
        _account.get() or "not set",
        statements,
    )


def refused(source: str, status: int, detail: str) -> None:
    """A provider's 4xx refusal of one request (D-118).

    ``source`` names the provider or endpoint, ``status`` is the HTTP status, and
    ``detail`` is the SDK's message, which carries the provider's error body. It is cut at
    DETAIL_LIMIT, as every detail here is.
    """
    logger.log(
        logging.WARNING if status == 429 else logging.ERROR,
        "%s refused the request with HTTP %d (account %s): %s",
        source,
        status,
        _account.get() or "not set",
        _detail(detail),
    )


def parsed_classification(number: int, of: int, seconds: float, tags: int, *, reply: ReplyFacts) -> None:
    """One classification attempt whose reply parsed into CLASSIFICATION_SCHEMA, at INFO (FR-10).

    ``parsed_attempt``'s counterpart for ``classify_document`` (D-104). Like it, the line says how
    many items the reply held and nothing of what they were: a suggested type, department or
    tag is the model's reply, and this module quotes no reply.
    """
    logger.info(
        "classification attempt %d of %d parsed after %.1f s%s (account %s): %d tag(s)",
        number,
        of,
        seconds,
        _bracket(reply),
        _account.get() or "not set",
        tags,
    )


def parsed_summary(
    number: int,
    of: int,
    seconds: float,
    *,
    sentences: int,
    decisions: int,
    highlights: int,
    action_items: int,
    reply: ReplyFacts,
) -> None:
    """One summary attempt whose reply parsed into SUMMARY_SCHEMA, at INFO (FR-16, D-125).

    ``parsed_classification``'s counterpart for ``summarise_meeting``. The line says how many
    elements of each kind the reply held and nothing of what they said: this module quotes no
    reply, and a meeting's summary is the meeting's content.
    """
    logger.info(
        "summarisation attempt %d of %d parsed after %.1f s%s (account %s): %d sentence(s), "
        "%d decision(s), %d highlight(s), %d action item(s)",
        number,
        of,
        seconds,
        _bracket(reply),
        _account.get() or "not set",
        sentences,
        decisions,
        highlights,
        action_items,
    )


def unavailable(exc: BaseException) -> None:
    """The 503 an ask ended in, with its cause."""
    logger.warning(
        "POST /api/ask answered 503 (account %s): %s: %s",
        _account.get() or "not set",
        cause_of(exc),
        _detail(str(exc)),
    )
