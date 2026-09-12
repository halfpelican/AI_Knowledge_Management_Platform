"""Logging configuration builders used by config/settings.py.

Kept out of the settings module so a test can build the same configuration for a
temporary path and prove the audit file is written.
"""


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
