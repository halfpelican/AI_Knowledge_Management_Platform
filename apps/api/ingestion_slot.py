"""One ingestion in flight per user (docs/decisions.md D-85, extending D-79's in-flight ask).

``POST /api/documents``, ``POST /api/meetings`` and ``POST /api/documents/{id}/reprocess`` each
extract, chunk and embed synchronously, holding a Waitress thread until the last chunk is
stored. D-79 rate-limits them, which bounds how many a user sends in an hour but not how many
run at once: one user firing uploads concurrently could hold every thread (D-85, "What this
decision does not cover"). This slot bounds that to one thread per user, shared by the three
routes, as the ``ingestion`` throttle scope is.

**The mechanism is the ask slot's** (``apps/api/ask_slot.py``): ``cache.add`` on the default
cache, which is atomic because no ``CACHES`` is set and Waitress runs one process (D-64), a fresh
token per take, and a release that deletes the key only if the token still matches. The key is
distinct from the ask slot's, so a user may have one ask and one ingestion in flight at once.
What ``ask_slot.py`` says of a multi-process server and of restarts is true here too.

**It has no timeout**, unlike the ask slot, because no timeout would be honest here.

- The ask slot's timeout is generation's worst case plus the question's embedding. The same
  derivation for an ingestion is MAXIMUM_CHUNKS_PER_SOURCE chunks, each embedded at its worst:
  1,000 x 3 x (5 + 600) s, about three weeks. That would be no timeout in all but name.
- Release is in ``finally``, and the cache is this process's memory. The slot can outlive its
  ingestion only if the process dies, and that empties the cache as well.
- A timeout could therefore only ever free the slot while its ingestion is still running, which
  is to say while it still holds the thread the slot exists to count.

A multi-process server with a shared cache would need one, because a process that died there
would leave its slots behind. That is the change D-79 already says such a server needs.

The token check stays all the same: it costs nothing, and it keeps ``cache.clear()`` (the test
suite's, or anyone's) from letting one ingestion's release free another's slot.
"""

import uuid

from django.core.cache import cache

# No expiry: Django's cache reads a timeout of None as "never".
INGESTION_SLOT_TIMEOUT_SECONDS = None


def ingestion_slot_key(user) -> str:
    """The cache key of this user's slot. Distinct from the ask slot's and from DRF's
    ``throttle_<scope>_<ident>``."""
    return f"ingestion_in_flight_{user.pk}"


def take_ingestion_slot(user) -> str | None:
    """Take this user's slot and return its token, or None if an ingestion of theirs holds it."""
    token = uuid.uuid4().hex
    if cache.add(ingestion_slot_key(user), token, timeout=INGESTION_SLOT_TIMEOUT_SECONDS):
        return token
    return None


def release_ingestion_slot(user, token: str) -> None:
    """Free this user's slot, but only if it is still the one ``token`` took."""
    key = ingestion_slot_key(user)
    if cache.get(key) == token:
        cache.delete(key)
