"""D-75's error log: an ERROR-level root handler writing ``logs/errors.log`` beside ``audit.log``.

Tested the way the FR-05 audit file is (``apps/api/tests/test_roles.py``): conftest.py's
``log_files`` builds the platform's logging for temporary paths, exactly as config/settings.py
builds it for the real ones, and these tests prove what reaches the error file.

D-73's 7 October clarification says a failed on-commit file removal is logged, and D-75's 13 October
clarification says that was untrue with ``DEBUG=False`` until this handler existed. Django logs that
failure through ``django.db.backends.base``, so one test sends a record through that exact logger
object and reads it back from the file.
"""

import logging

import django.db.backends.base.base as database_backend_base
import pytest
from django.conf import settings as django_settings

import config.settings as settings_module
from apps.core.logging_config import ERROR_FILE_HANDLER, audit_logging, platform_logging

AUDIT_LOGGER_NAME = "audit"


def test_the_audit_logger_is_configured_exactly_as_before(tmp_path):
    audit_path = tmp_path / "audit.log"
    alone = audit_logging(audit_path)
    platform = platform_logging(audit_path=audit_path, error_path=tmp_path / "errors.log")

    assert platform["loggers"] == alone["loggers"]
    assert platform["handlers"]["audit_file"] == alone["handlers"]["audit_file"]
    assert platform["formatters"]["audit"] == alone["formatters"]["audit"]
    assert platform["disable_existing_loggers"] is False


def test_the_error_handler_is_on_the_root_logger_and_filters_at_error(tmp_path):
    error_path = tmp_path / "errors.log"
    config = platform_logging(audit_path=tmp_path / "audit.log", error_path=error_path)

    handler = config["handlers"][ERROR_FILE_HANDLER]
    assert handler["class"] == "logging.FileHandler"
    assert handler["level"] == "ERROR"
    assert handler["filename"] == str(error_path)
    assert handler["encoding"] == "utf-8"
    # No level on the root itself: the handler filters, so a WARNING still reaches every other
    # handler, pytest's capture included.
    assert config["root"] == {"handlers": [ERROR_FILE_HANDLER]}


def test_settings_build_logging_from_the_two_environment_driven_paths():
    """config/settings.py, as imported, before any test overrides it."""
    assert settings_module.LOGGING == platform_logging(
        audit_path=settings_module.AUDIT_LOG_PATH, error_path=settings_module.ERROR_LOG_PATH
    )
    assert settings_module.ERROR_LOG_PATH.parent.is_dir()


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
