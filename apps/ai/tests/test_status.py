"""D-118: what a provider raises for an HTTP error status (apps/ai/_status.py).

The user's rule of 10 November 2026: retry a 429, and answer the rest with the 503. So a
rate limit is a plain ProviderUnavailable, which the retry loops retry. Any other 4xx is
ProviderRefused, which they do not, and which is still a ProviderUnavailable, so the ask
view's 503 catches it. A 5xx stays what it always was, an outage, retried under D-19.
"""

import logging

import pytest

from apps.ai import attempt_log
from apps.ai._status import error_for_status
from apps.ai.base import ProviderRefused, ProviderUnavailable

SOURCE = "Example API"


def refusals(caplog):
    return [r for r in caplog.records if r.name == attempt_log.ATTEMPT_LOGGER_NAME]


@pytest.mark.parametrize("status", [500, 502, 503, 529])
def test_a_server_error_is_an_outage_and_is_not_logged_here(status, caplog):
    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        error = error_for_status(SOURCE, status, "boom")

    assert type(error) is ProviderUnavailable
    assert str(error) == f"{SOURCE} returned HTTP {status}: boom"
    assert refusals(caplog) == []


def test_a_rate_limit_is_retryable_and_logged_as_a_warning(caplog):
    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        error = error_for_status(SOURCE, 429, "slow down")

    assert type(error) is ProviderUnavailable  # not ProviderRefused: a rate limit passes
    (record,) = refusals(caplog)
    assert record.levelno == logging.WARNING
    assert f"{SOURCE} refused the request with HTTP 429" in record.getMessage()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_any_other_client_error_is_a_refusal_and_logged_as_an_error(status, caplog):
    with caplog.at_level(logging.INFO, logger=attempt_log.ATTEMPT_LOGGER_NAME):
        error = error_for_status(SOURCE, status, "no")

    assert isinstance(error, ProviderRefused)
    assert isinstance(error, ProviderUnavailable)  # so the ask view's 503 still catches it
    (record,) = refusals(caplog)
    assert record.levelno == logging.ERROR
    assert f"{SOURCE} refused the request with HTTP {status}" in record.getMessage()
