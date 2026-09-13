"""Audit log entries (FR-05: "role changes write an audit-log entry").

Schema v1 defines no audit table, so nothing is written to the database. Each
entry is one JSON line on the ``audit`` logger, which config/settings.py sends
to AUDIT_LOG_PATH. The storage medium is a decision for docs/decisions.md.
"""

import json
import logging

from django.utils import timezone

AUDIT_LOGGER_NAME = "audit"
ROLE_CHANGED = "role_changed"

logger = logging.getLogger(AUDIT_LOGGER_NAME)


def log_role_change(*, actor, target, old_role: str, new_role: str) -> dict:
    entry = {
        "timestamp": timezone.now().isoformat(),
        "event": ROLE_CHANGED,
        "actor_id": str(actor.pk),
        "actor_email": actor.email,
        "target_id": str(target.pk),
        "target_email": target.email,
        "old_role": old_role,
        "new_role": new_role,
    }
    logger.info(json.dumps(entry))
    return entry
