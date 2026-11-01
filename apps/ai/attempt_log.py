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
- the 503 ``POST /api/ask`` answers, with the message of the exception that caused it.

Each line names the account, by primary key, when the view has set it with ``account``.
Nothing logged here quotes the question, a passage or the model's reply: the details are
the exception messages, which describe the failure (``not valid JSON: ...``, ``Request
timed out.``), and they are cut at ``DETAIL_LIMIT`` characters.

**It observes; it does not decide.** No attempt count, timeout or reply changes because
of it. A logging call does not raise into its caller: a handler that fails reports through
``logging``'s own ``handleError``.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager

ATTEMPT_LOGGER_NAME = "apps.ai.attempts"
DETAIL_LIMIT = 300

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


def failed_attempt(step: str, number: int, of: int, seconds: float, cause: str, detail: str) -> None:
    """One failed attempt of ``step``, "generation" or "question embedding"."""
    logger.warning(
        "%s attempt %d of %d failed after %.1f s (account %s): %s: %s",
        step,
        number,
        of,
        seconds,
        _account.get() or "not set",
        cause,
        _detail(detail),
    )


def unavailable(exc: BaseException) -> None:
    """The 503 an ask ended in, with its cause."""
    logger.warning(
        "POST /api/ask answered 503 (account %s): %s: %s",
        _account.get() or "not set",
        cause_of(exc),
        _detail(str(exc)),
    )
