"""Logging configuration builders used by config/settings.py.

Kept out of the settings module so a test can build the same configuration for a
temporary path and prove the audit file, the error file and Waitress's file are written.
"""

# The root handler's name in the configuration below. conftest.py reads it to tell this
# handler from the ones pytest attaches to the root logger.
ERROR_FILE_HANDLER = "error_file"

# Waitress 3.0.2 logs through two loggers, both made in ``waitress/utilities.py``:
# ``waitress`` ("Serving on http://host:port", channel and server messages, and an exception
# that escapes the app) and its child ``waitress.queue`` ("Task queue depth is N", a WARNING
# logged when a request arrives and no thread is idle to take it). Configuring the parent
# covers both: the child has no handler of its own and propagates to it.
WAITRESS_LOGGER = "waitress"
WAITRESS_FILE_HANDLER = "waitress_file"

# apps/ai/attempt_log.py's logger, spelled out rather than imported so this module, which
# config/settings.py imports, stays free of apps/ imports. A test holds the two equal.
PROVIDER_ATTEMPTS_LOGGER = "apps.ai.attempts"
PROVIDER_ATTEMPTS_FILE_HANDLER = "provider_attempts_file"
# Every attempt, parsed or failed, at INFO, in a file of its own (step 7 phase 2a).
ATTEMPTS_FILE_HANDLER = "attempts_file"


def audit_logging(path) -> dict:
    """LOGGING for the ``audit`` logger (FR-05): one line per record, appended to
    ``path``, and still propagated so test capture and any root handler see it."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"audit": {"format": "%(message)s"}},
        "handlers": {
            "audit_file": {
                "class": "logging.FileHandler",
                "filename": str(path),
                "formatter": "audit",
                "encoding": "utf-8",
                "delay": True,
            }
        },
        "loggers": {"audit": {"handlers": ["audit_file"], "level": "INFO", "propagate": True}},
    }


def platform_logging(*, audit_path, error_path, waitress_path, attempts_path) -> dict:
    """LOGGING for the platform: the audit logger exactly as ``audit_logging`` builds it, an
    ERROR-level handler on the ROOT logger appending to ``error_path`` (D-75), and the
    ``waitress`` logger at INFO appending to ``waitress_path`` (D-87 section 3).

    **Why the root handler exists.** Until D-75, LOGGING configured only the audit logger, so
    with ``DEBUG=False`` an error had nowhere to go: Django's console handler requires
    ``DEBUG``, ``mail_admins`` has no ``ADMINS`` to send to, and an application logger reached
    stderr only through Python's last-resort handler, with no time and no level. On the root
    logger, this handler receives every propagating record at ERROR or above: Django's own
    (``django.request`` for a 500, ``django.db.backends.base`` for an ``on_commit(robust=True)``
    callback that raised, which is how D-73's file removal fails) and the application's (the
    download's missing file, D-75).

    **What it does not change.** The root logger's own level is left alone, so a WARNING still
    reaches pytest's capture and any other handler; this handler alone filters at ERROR. The
    audit logger's INFO records still propagate to the root and are not written here, because
    they are below the handler's level.

    **Why Waitress has its own file (D-87 section 3).** Until it existed, none of Waitress's own
    lines reached anything, not even "Serving on", and so not the "Task queue depth" warning
    either, which is the one that shows every thread busy. The reason: ``waitress-serve``
    imports the app first. Importing ``config.wsgi`` runs ``django.setup()``, which applies this
    LOGGING and gives the root logger the ERROR handler above. Only after that does
    ``waitress.serve()`` call ``logging.basicConfig()``, which does nothing once the root
    logger has a handler. The runner does set the ``waitress`` logger to INFO, so the records
    are made, but the only handler they reach is the root's, which drops everything below
    ERROR. Python's last-resort stderr handler isn't used while any handler exists, so the
    console stayed blank too.

    **What the Waitress file does.** The ``waitress`` logger writes INFO and above to
    ``waitress_path``, timestamped in the error file's format, for example
    ``2026-10-28 15:04:05,123 WARNING waitress.queue Task queue depth is 3``. The measured
    run's wrapper parses those lines, so a test pins the format.
    - **It keeps propagating,** so a Waitress ERROR reaches the error file as well. Its INFO and
      WARNING records reach the root too, where the error handler drops them.
    - **The file is opened on its first record.** Under ``waitress-serve`` that is
      "Serving on", so a ``manage.py`` command or a test that never runs Waitress creates no
      empty file.
    """
    config = audit_logging(audit_path)
    config["formatters"]["errors"] = {
        # A traceback, when the record carries one, is appended by the formatter itself.
        "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
    }
    config["handlers"][ERROR_FILE_HANDLER] = {
        "class": "logging.FileHandler",
        "level": "ERROR",
        "filename": str(error_path),
        "formatter": "errors",
        "encoding": "utf-8",
        "delay": True,
    }
    config["root"] = {"handlers": [ERROR_FILE_HANDLER]}
    config["handlers"][WAITRESS_FILE_HANDLER] = {
        # No level on the handler: the logger's INFO is the filter.
        "class": "logging.FileHandler",
        "filename": str(waitress_path),
        "formatter": "errors",
        "encoding": "utf-8",
        "delay": True,
    }
    config["loggers"][WAITRESS_LOGGER] = {
        "handlers": [WAITRESS_FILE_HANDLER],
        "level": "INFO",
        "propagate": True,
    }
    # Failed provider attempts and the 503 they end in (apps/ai/attempt_log.py, 1 November
    # 2026): WARNINGs, written to the error file by a handler of their own, because the
    # root's handler there drops everything below ERROR. It keeps propagating, as Waitress's
    # does, so pytest's capture still sees it; the root's handler drops the WARNING, so each
    # line is written once.
    config["handlers"][PROVIDER_ATTEMPTS_FILE_HANDLER] = {
        "class": "logging.FileHandler",
        "level": "WARNING",
        "filename": str(error_path),
        "formatter": "errors",
        "encoding": "utf-8",
        "delay": True,
    }
    # Every provider attempt, parsed or failed, at INFO, in ``attempts_path`` (step 7 phase 2a,
    # the user's decision of 7 November 2026). A parsed attempt is an INFO line
    # (apps/ai/attempt_log.py), and it belongs in neither the error file nor nowhere: until this
    # handler, the logger sat at WARNING and a running server dropped it. The logger is now at
    # INFO; the error file's handler above stays at WARNING, so a success never lands there, and
    # the root's handler drops the INFO it propagates. The file is opened on its first record.
    config["handlers"][ATTEMPTS_FILE_HANDLER] = {
        "class": "logging.FileHandler",
        "level": "INFO",
        "filename": str(attempts_path),
        "formatter": "errors",
        "encoding": "utf-8",
        "delay": True,
    }
    config["loggers"][PROVIDER_ATTEMPTS_LOGGER] = {
        "handlers": [PROVIDER_ATTEMPTS_FILE_HANDLER, ATTEMPTS_FILE_HANDLER],
        "level": "INFO",
        "propagate": True,
    }
    return config
