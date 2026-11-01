"""D-75's error log, an ERROR-level root handler writing ``logs/errors.log`` beside ``audit.log``,
and D-87's Waitress log, the ``waitress`` logger at INFO writing ``logs/waitress.log`` beside both.

Tested the way the FR-05 audit file is (``apps/api/tests/test_roles.py``): conftest.py's
``log_files`` builds the platform's logging for temporary paths, exactly as config/settings.py
builds it for the real ones, and these tests prove what reaches each file.

D-73's 7 October clarification says a failed on-commit file removal is logged, and D-75's 13 October
clarification says that was untrue with ``DEBUG=False`` until this handler existed. Django logs that
failure through ``django.db.backends.base``, so one test sends a record through that exact logger
object and reads it back from the file.

D-87 section 3 says Waitress's own lines were dropped, "Serving on" included, and that the
measured run's wrapper copies the "Task queue depth" lines into its results. So the Waitress tests
make those records through Waitress's own code rather than a logger looked up by name: the
``log_info`` that ``print_listen`` calls, and a real ``ThreadedTaskDispatcher.add_task`` with no
idle thread. They also pin the exact line format the wrapper parses. One test pins the logger
names to the installed Waitress, so an upgrade that renames them fails here and not on the night of
a run.
"""

import logging
import os
import re
from pathlib import Path

import django.db.backends.base.base as database_backend_base
import pytest
from django.conf import settings as django_settings
from waitress import task as waitress_task
from waitress import utilities as waitress_utilities
from waitress import wasyncore

import config.settings as settings_module
from apps.ai import attempt_log
from apps.core.logging_config import (
    ERROR_FILE_HANDLER,
    PROVIDER_ATTEMPTS_FILE_HANDLER,
    PROVIDER_ATTEMPTS_LOGGER,
    WAITRESS_FILE_HANDLER,
    WAITRESS_LOGGER,
    audit_logging,
    platform_logging,
)

AUDIT_LOGGER_NAME = "audit"

# The error file's ``asctime``: ``2026-10-28 15:04:05,123``. Every Waitress line starts with it.
TIMESTAMP = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}"


def _paths(tmp_path):
    return {
        "audit_path": tmp_path / "audit.log",
        "error_path": tmp_path / "errors.log",
        "waitress_path": tmp_path / "waitress.log",
    }


def _lines(path):
    """The file's lines, or none if the file was never opened (every handler here is ``delay``)."""
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_the_audit_logger_is_configured_exactly_as_before(tmp_path):
    paths = _paths(tmp_path)
    alone = audit_logging(paths["audit_path"])
    platform = platform_logging(**paths)

    assert platform["loggers"]["audit"] == alone["loggers"]["audit"]
    assert platform["handlers"]["audit_file"] == alone["handlers"]["audit_file"]
    assert platform["formatters"]["audit"] == alone["formatters"]["audit"]
    assert platform["disable_existing_loggers"] is False
    # D-87 adds the Waitress logger, and D-82's note of 1 November 2026 the provider-attempts
    # logger, and nothing else.
    assert set(platform["loggers"]) == {"audit", WAITRESS_LOGGER, PROVIDER_ATTEMPTS_LOGGER}


def test_the_error_handler_is_on_the_root_logger_and_filters_at_error(tmp_path):
    paths = _paths(tmp_path)
    config = platform_logging(**paths)

    handler = config["handlers"][ERROR_FILE_HANDLER]
    assert handler["class"] == "logging.FileHandler"
    assert handler["level"] == "ERROR"
    assert handler["filename"] == str(paths["error_path"])
    assert handler["encoding"] == "utf-8"
    # No level on the root itself: the handler filters, so a WARNING still reaches every other
    # handler, pytest's capture included.
    assert config["root"] == {"handlers": [ERROR_FILE_HANDLER]}


def test_settings_build_logging_from_the_three_environment_driven_paths():
    """config/settings.py, as imported, before any test overrides it."""
    assert settings_module.LOGGING == platform_logging(
        audit_path=settings_module.AUDIT_LOG_PATH,
        error_path=settings_module.ERROR_LOG_PATH,
        waitress_path=settings_module.WAITRESS_LOG_PATH,
    )
    assert settings_module.ERROR_LOG_PATH.parent.is_dir()
    assert settings_module.WAITRESS_LOG_PATH.parent.is_dir()


def test_the_error_log_path_is_configured_from_settings():
    handler = django_settings.LOGGING["handlers"][ERROR_FILE_HANDLER]
    assert handler["filename"] == str(django_settings.ERROR_LOG_PATH)


@pytest.mark.parametrize("logger_name", ["apps.api.views", "django.request", "apps.ingestion.documents"])
def test_an_error_from_any_logger_is_written_to_the_error_file(error_log_file, logger_name):
    logging.getLogger(logger_name).error("Stored original missing for document %s.", "d-123")

    written = error_log_file.read_text(encoding="utf-8")
    assert "ERROR" in written
    assert logger_name in written
    assert "Stored original missing for document d-123." in written


def test_a_failed_on_commit_callback_logged_by_django_is_written_to_the_error_file(error_log_file):
    """``transaction.on_commit(..., robust=True)`` logs a callback that raised through this logger,
    which is how D-73's file removal reports a failure (on Windows, a download holding the file)."""
    logger = database_backend_base.logger
    assert logger.name == "django.db.backends.base"
    try:
        raise PermissionError("The process cannot access the file because it is being used.")
    except PermissionError as exc:
        # Django's own wording, from BaseDatabaseWrapper.on_commit.
        logger.error("Error calling %s in on_commit() (%s).", "<lambda>", exc, exc_info=True)

    written = error_log_file.read_text(encoding="utf-8")
    assert "ERROR django.db.backends.base Error calling <lambda> in on_commit()" in written
    # The traceback is written with it.
    assert "Traceback (most recent call last)" in written
    assert "PermissionError: The process cannot access the file" in written


def test_a_warning_and_an_audit_entry_are_not_written_to_the_error_file(error_log_file, audit_file):
    logging.getLogger("django.request").warning("Not Found: /api/documents/x")
    logging.getLogger(AUDIT_LOGGER_NAME).info('{"event": "role_changed"}')

    assert not error_log_file.exists() or error_log_file.read_text(encoding="utf-8") == ""
    # The audit entry still goes where it always went.
    assert audit_file.read_text(encoding="utf-8").strip() == '{"event": "role_changed"}'


def test_a_warning_still_reaches_pytests_capture(caplog):
    """The root logger's level is untouched, so the error handler does not narrow what anything
    else sees."""
    logging.getLogger("apps.api.views").warning("still captured")
    assert [record.getMessage() for record in caplog.records] == ["still captured"]


# --- Failed provider attempts (apps/ai/attempt_log.py, 1 November 2026) ------------------------


def test_the_provider_attempts_logger_is_the_one_attempt_log_writes_through():
    assert attempt_log.ATTEMPT_LOGGER_NAME == PROVIDER_ATTEMPTS_LOGGER


def test_a_provider_attempt_warning_is_written_to_the_error_file_once_with_a_timestamp(
    error_log_file, caplog
):
    """Its own handler takes the WARNING the root's ERROR handler drops. It still propagates, so
    pytest sees it too, and the root's handler does not write it a second time."""
    attempt_log.failed_attempt("generation", 1, 3, 300.0, "APITimeoutError", "Request timed out.")

    lines = error_log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert re.match(
        rf"^{TIMESTAMP} WARNING {PROVIDER_ATTEMPTS_LOGGER} generation attempt 1 of 3 failed after "
        r"300\.0 s \(account not set\): APITimeoutError: Request timed out\.$",
        lines[0],
    )
    assert [r.name for r in caplog.records] == [PROVIDER_ATTEMPTS_LOGGER]


def test_the_provider_attempts_handler_writes_the_error_file_at_warning(tmp_path):
    paths = _paths(tmp_path)
    config = platform_logging(**paths)

    assert config["loggers"][PROVIDER_ATTEMPTS_LOGGER] == {
        "handlers": [PROVIDER_ATTEMPTS_FILE_HANDLER],
        "level": "WARNING",
        "propagate": True,
    }
    handler = config["handlers"][PROVIDER_ATTEMPTS_FILE_HANDLER]
    assert handler["filename"] == str(paths["error_path"])
    assert handler["level"] == "WARNING"
    # The root's handler stays at ERROR, so a django.request 4xx WARNING stays out.
    assert config["handlers"][ERROR_FILE_HANDLER]["level"] == "ERROR"


# --- Waitress's file (D-87 section 3) ----------------------------------------------------------


def test_the_waitress_logger_writes_its_own_file_at_info_and_keeps_propagating(tmp_path):
    paths = _paths(tmp_path)
    config = platform_logging(**paths)

    assert config["loggers"][WAITRESS_LOGGER] == {
        "handlers": [WAITRESS_FILE_HANDLER],
        "level": "INFO",
        "propagate": True,
    }
    handler = config["handlers"][WAITRESS_FILE_HANDLER]
    assert handler["class"] == "logging.FileHandler"
    assert handler["filename"] == str(paths["waitress_path"])
    assert handler["encoding"] == "utf-8"
    # The logger's INFO is the only filter.
    assert "level" not in handler
    assert "%(asctime)s" in config["formatters"][handler["formatter"]]["format"]


def test_the_waitress_log_path_is_configured_from_settings():
    handler = django_settings.LOGGING["handlers"][WAITRESS_FILE_HANDLER]
    assert handler["filename"] == str(django_settings.WAITRESS_LOG_PATH)


def test_the_waitress_log_path_is_read_from_the_environment_and_defaults_beside_the_error_file():
    """``WAITRESS_LOG_PATH``, or ``logs/waitress.log`` when it is unset, as ``ERROR_LOG_PATH``
    defaults to ``logs/errors.log``."""
    default = settings_module.BASE_DIR / "logs" / "waitress.log"
    assert settings_module.WAITRESS_LOG_PATH == Path(os.environ.get("WAITRESS_LOG_PATH", str(default)))
    assert default.parent == (settings_module.BASE_DIR / "logs" / "errors.log").parent


def test_the_loggers_configured_are_the_ones_the_installed_waitress_logs_through():
    assert waitress_utilities.logger.name == WAITRESS_LOGGER
    assert waitress_utilities.queue_logger.name == f"{WAITRESS_LOGGER}.queue"
    # The "Serving on" line: BaseWSGIServer.print_listen -> wasyncore.dispatcher.log_info.
    assert wasyncore.dispatcher.logger is waitress_utilities.logger
    # "Task queue depth is N": ThreadedTaskDispatcher.add_task.
    assert waitress_task.ThreadedTaskDispatcher.queue_logger is waitress_utilities.queue_logger


def test_waitresss_serving_on_line_is_written_to_its_file_with_a_timestamp(waitress_log_file, error_log_file):
    # What BaseWSGIServer.print_listen does with "Serving on http://{}:{}" once it has the address.
    wasyncore.dispatcher(map={}).log_info("Serving on http://127.0.0.1:8001")

    lines = _lines(waitress_log_file)
    assert len(lines) == 1, lines
    assert re.fullmatch(rf"{TIMESTAMP} INFO waitress Serving on http://127\.0\.0\.1:8001", lines[0]), lines[0]
    # INFO is below the error file's level.
    assert _lines(error_log_file) == []


def test_waitresss_task_queue_depth_warning_is_written_to_its_file_with_a_timestamp(waitress_log_file):
    """A dispatcher whose threads were never started has none idle, so every task it is given
    queues, and Waitress warns with the depth each time, as it does when all 24 threads are busy."""
    dispatcher = waitress_task.ThreadedTaskDispatcher()
    dispatcher.add_task(object())
    dispatcher.add_task(object())

    lines = _lines(waitress_log_file)
    assert len(lines) == 2, lines
    assert re.fullmatch(rf"{TIMESTAMP} WARNING waitress\.queue Task queue depth is 1", lines[0]), lines[0]
    assert re.fullmatch(rf"{TIMESTAMP} WARNING waitress\.queue Task queue depth is 2", lines[1]), lines[1]


def test_a_waitress_error_is_written_to_its_file_and_also_reaches_the_error_file(
    waitress_log_file, error_log_file
):
    try:
        raise RuntimeError("the app raised past Django")
    except RuntimeError:
        # HTTPChannel.service's wording when an exception escapes the application.
        waitress_utilities.logger.exception("Exception while serving /api/ask")

    waitress_written = waitress_log_file.read_text(encoding="utf-8") if waitress_log_file.exists() else ""
    assert re.match(rf"{TIMESTAMP} ERROR waitress Exception while serving /api/ask\n", waitress_written)
    # Propagation: the root's error handler writes it too, traceback included.
    error_written = error_log_file.read_text(encoding="utf-8") if error_log_file.exists() else ""
    assert "ERROR waitress Exception while serving /api/ask" in error_written
    assert "RuntimeError: the app raised past Django" in error_written


def test_the_waitress_file_holds_only_waitresss_records_and_is_not_created_without_one(waitress_log_file):
    logging.getLogger("django.request").warning("Not Found: /api/documents/x")
    logging.getLogger("apps.api.views").error("Stored original missing for document d-123.")
    logging.getLogger(AUDIT_LOGGER_NAME).info('{"event": "role_changed"}')

    assert not waitress_log_file.exists()
