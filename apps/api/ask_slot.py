"""One ask in flight per user (docs/decisions.md D-79).

``POST /api/ask`` holds a Waitress thread for as long as the answer takes, which can be many
minutes. The rate throttle bounds how many asks a user sends; this slot bounds what one user's
asks can hold at once: one thread.

**How it is held.** A key per user in Django's default cache, written with ``cache.add``, which
writes only when the key is absent, and carrying a fresh token. ``add`` is atomic here because
no ``CACHES`` is set, so the default cache is the per-process ``LocMemCache``, which takes a lock
around it, and Waitress runs one process (D-64). It is the same cache the throttle counters
live in. **A multi-process server would need a shared cache** (Redis or memcached, where ``add``
is atomic across processes): with ``LocMemCache`` each process would hold its own slot, and a
user could have one ask in flight per process. A restart empties it, as it empties the counters.

**Its timeout** is generation's worst case, ``GENERATION_TIMEOUT_SECONDS`` times
``MAXIMUM_GENERATION_ATTEMPTS``, plus ``ASK_IN_FLIGHT_MARGIN_SECONDS``, which covers the
question's embedding (the constant says how). The timeout matters only if ``release_ask_slot`` is
never reached, so it is sized to outlast the longest ask rather than to free the slot early.

**Release** compares the token first, so an ask whose slot expired and was taken by the same
user's next ask cannot release the next one's. Django's cache has no compare-and-delete, so the
read and the delete are two steps: if the slot expired and was re-taken between them, the newer
slot would be released. With a timeout of three quarters of an hour that window is not
defended.
"""

import uuid

from django.core.cache import cache

from apps.ai.generation import GENERATION_TIMEOUT_SECONDS
from apps.core.constants import ASK_IN_FLIGHT_MARGIN_SECONDS, MAXIMUM_GENERATION_ATTEMPTS

ASK_SLOT_TIMEOUT_SECONDS = (
    GENERATION_TIMEOUT_SECONDS * MAXIMUM_GENERATION_ATTEMPTS + ASK_IN_FLIGHT_MARGIN_SECONDS
)


def ask_slot_key(user) -> str:
    """The cache key of this user's slot. Distinct from DRF's ``throttle_<scope>_<ident>``."""
    return f"ask_in_flight_{user.pk}"


def take_ask_slot(user) -> str | None:
    """Take this user's slot and return its token, or None if an ask of theirs holds it."""
    token = uuid.uuid4().hex
    if cache.add(ask_slot_key(user), token, timeout=ASK_SLOT_TIMEOUT_SECONDS):
        return token
    return None


def release_ask_slot(user, token: str) -> None:
    """Free this user's slot, but only if it is still the one ``token`` took."""
    key = ask_slot_key(user)
    if cache.get(key) == token:
        cache.delete(key)
