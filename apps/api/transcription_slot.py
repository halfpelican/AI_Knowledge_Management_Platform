"""One recording segment in transcription per user (docs/decisions.md D-123).

``POST /api/transcriptions`` holds a Waitress thread while FLM transcribes a segment: seconds
normally, and up to MAXIMUM_TRANSCRIBE_ATTEMPTS times TRANSCRIPTION_TIMEOUT_SECONDS if FLM hangs.
The page sends one segment at a time, so a person transcribing never meets this. It bounds a
client that sends several at once: without it, one user could hold every thread, and FLM's one
NPU would queue them anyway. The ``transcription`` throttle scope bounds how many a user sends;
this bounds how many run at once, as D-85's ingestion slot does for ingestion.

**The mechanism is the ingestion slot's** (``apps/api/ingestion_slot.py``): ``cache.add`` on the
default cache, atomic because no ``CACHES`` is set and Waitress runs one process (D-64); a fresh
token per take; a release in ``finally`` that deletes the key only while the token still
matches. The key is its own, so a user may have one ask, one ingestion and one transcription in
flight at once: the person submitting a confirmed draft while another segment is out is not
refused for it. What ``ask_slot.py`` says of a multi-process server and of restarts is true here.

**No timeout**, for the ingestion slot's reason: the release is in ``finally`` and the cache is
this process's memory, so the slot can outlive its request only if the process dies, which
empties the cache too.
"""

import uuid

from django.core.cache import cache

# No expiry: Django's cache reads a timeout of None as "never".
TRANSCRIPTION_SLOT_TIMEOUT_SECONDS = None


def transcription_slot_key(user) -> str:
    """The cache key of this user's slot. Distinct from the ask's, the ingestion's and DRF's
    ``throttle_<scope>_<ident>``."""
    return f"transcription_in_flight_{user.pk}"


def take_transcription_slot(user) -> str | None:
    """Take this user's slot and return its token, or None if a segment of theirs holds it."""
    token = uuid.uuid4().hex
    if cache.add(transcription_slot_key(user), token, timeout=TRANSCRIPTION_SLOT_TIMEOUT_SECONDS):
        return token
    return None


def release_transcription_slot(user, token: str) -> None:
    """Free this user's slot, but only if it is still the one ``token`` took."""
    key = transcription_slot_key(user)
    if cache.get(key) == token:
        cache.delete(key)
