"""The default cache: Django's per-process LocMemCache, dropping expired entries before live ones.

The cache holds every throttle count (D-26, D-79), the in-flight slots (D-79, D-85, D-123) and
D-137's password reset cooldown. Each bounds something only while its entry is there. Django's
LocMemCache, when an insert finds it full, drops the least recently used third of its entries,
whether they have expired or not, and it removes an expired entry only when that entry is read
again. So it fills with expired entries, and then a cull takes live ones with them. A slot or a
cooldown is written once and never read, which makes it among the first to go. The review of 17
November 2026 (COR-2) showed both from one client address: about fifty self-registered accounts gave
a session left open ten more guesses at the password within the hour, and let an account be sent a
reset email inside its cooldown.

Two things change, and nothing else does:

- **``CACHE_MAX_ENTRIES`` places** (config/settings.py ``CACHES``), not Django's 300.
- **A full cache drops its expired entries first** (``ExpiredFirstLocMemCache._cull``). If that frees
  less than the third Django's own cull frees, Django's cull runs as well, dropping the least
  recently used third of what is left, so a cache kept nearly full of live entries is not scanned
  again at the next insert. A live entry is dropped only once more than two thirds of the places
  hold live entries.

Everything else is LocMemCache's: one store per process, which a restart empties; its lock around
every operation, which is what makes ``add`` atomic for the slots and the cooldown (Waitress runs one
process, D-64); and when an entry counts as expired, read from the same clock its ``get`` reads.
"""

from django.core.cache.backends.locmem import LocMemCache


class ExpiredFirstLocMemCache(LocMemCache):
    """LocMemCache whose cull drops every expired entry before it drops a live one."""

    def _cull(self):
        # Called by _set, holding self._lock, when an insert finds MAX_ENTRIES entries.
        for key in [key for key in self._cache if self._has_expired(key)]:
            self._delete(key)
        if self._cull_frequency == 0:
            super()._cull()  # CULL_FREQUENCY 0 is Django's "empty the cache"
        elif len(self._cache) > self._max_entries - self._max_entries // self._cull_frequency:
            super()._cull()  # too little had expired: the least recently used third goes too
