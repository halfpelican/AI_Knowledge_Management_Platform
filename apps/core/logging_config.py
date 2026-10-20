"""Logging configuration builders used by config/settings.py.

Kept out of the settings module so a test can build the same configuration for a
temporary path and prove the audit file and the error file are written.
"""

# The root handler's name in the configuration below. conftest.py reads it to tell this
# handler from the ones pytest attaches to the root logger.
ERROR_FILE_HANDLER = "error_file"


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


def platform_logging(*, audit_path, error_path) -> dict:
    """LOGGING for the platform: the audit logger exactly as ``audit_logging`` builds it, and
    an ERROR-level handler on the ROOT logger appending to ``error_path`` (D-75).

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
    return config
