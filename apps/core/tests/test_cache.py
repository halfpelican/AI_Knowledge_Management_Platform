"""The default cache (the review of 17 November 2026, COR-2): what it holds, and what it drops first.

The cache holds every throttle count (D-26, D-79), the in-flight slots (D-79, D-85, D-123) and the
password reset's cooldown (D-137). Each bounds something only while its entry is there, and Django's
LocMemCache, with no ``CACHES`` set, held 300 entries and then dropped the least recently used third
of them, live or expired. A slot or a cooldown is written once and never read, so it was among the
first to go, and a throttle count could be pushed out by any 300 newer entries. The review showed
both from one client address: about fifty self-registered accounts were enough.

So ``CACHES`` names ``apps.core.cache.ExpiredFirstLocMemCache`` with ``CACHE_MAX_ENTRIES`` places.
What these tests hold it to:

- **The default cache is that class, with that many places,** and ``CACHE_MAX_ENTRIES`` is the
  value the build set (``apps/core/tests/test_constants.py`` pins it).
- **A full cache drops its expired entries first.** A live entry outlives every expired one, however
  long ago it was written or read.
- **A cull still frees a third,** as Django's does, when too few entries have expired, so a cache
  kept nearly full of live entries is not scanned again at the next insert. The entries dropped
  then are the least recently used, as Django drops them.

The route-level consequences are tested where the routes are: the cooldown in
``apps/api/tests/test_fr02_password_reset.py`` and the password change's count in
``apps/api/tests/test_throttles.py``.
"""

import time

import pytest
from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends import locmem

from apps.core import constants
from apps.core.cache import ExpiredFirstLocMemCache

_real_time = time.time


class LaterTime:
    """``time`` as LocMemCache reads it to decide whether an entry has expired, ``seconds`` ahead.
    Only that reading moves: the expiry was stamped from the real clock."""

    def __init__(self, seconds):
        self.seconds = seconds

    def time(self):
        return _real_time() + self.seconds


@pytest.fixture
def small_cache():
    """A cache of this class with nine places, empty before and after the test. Its entries live in
    LocMemCache's module-level store under its own name, so they outlive the instance."""
    built = []

    def build(name, max_entries=9):
        cache = ExpiredFirstLocMemCache(name, {"OPTIONS": {"MAX_ENTRIES": max_entries}})
        cache.clear()
        built.append(cache)
        return cache

    yield build
    for cache in built:
        cache.clear()


def keys_held(cache):
    """The keys in the cache, most recently used first, read without touching any of them."""
    return [key.split(":", 2)[2] for key in cache._cache]


def test_the_default_cache_drops_expired_entries_first_and_has_its_places():
    default = caches["default"]

    assert type(default) is ExpiredFirstLocMemCache
    assert default._max_entries == constants.CACHE_MAX_ENTRIES
    assert settings.CACHES["default"]["BACKEND"] == "apps.core.cache.ExpiredFirstLocMemCache"
    assert settings.CACHES["default"]["OPTIONS"]["MAX_ENTRIES"] == constants.CACHE_MAX_ENTRIES


def test_a_full_cache_drops_its_expired_entries_before_a_live_one(small_cache, monkeypatch):
    """The slot is written first and never read, so it is the least recently used entry, which is
    the first Django's own cull drops."""
    cache = small_cache("expired-first")
    assert cache.add("slot", "held", timeout=None)
    for index in range(8):
        cache.set(f"count-{index}", [index], timeout=60)
    monkeypatch.setattr(locmem, "time", LaterTime(61))

    cache.set("new", "added", timeout=60)  # the tenth entry, into nine places

    assert keys_held(cache) == ["new", "slot"]
    assert cache.get("slot") == "held"


def test_a_cull_that_finds_too_few_expired_entries_still_frees_a_third(small_cache, monkeypatch):
    """One expired entry of nine frees one place. The cull then drops the least recently used third
    of the rest, as Django's own does, so the next insert does not scan the cache again."""
    cache = small_cache("a-third")
    cache.set("stale", 0, timeout=60)
    for index in range(8):
        cache.set(f"live-{index}", index, timeout=3600)
    monkeypatch.setattr(locmem, "time", LaterTime(61))

    cache.set("new", "added", timeout=3600)

    # live-0 and live-1, the least recently used two of the eight left, went with the expired one.
    assert keys_held(cache) == ["new", *(f"live-{index}" for index in range(7, 1, -1))]


def test_a_cache_full_of_live_entries_culls_as_djangos_does(small_cache):
    cache = small_cache("all-live")
    for index in range(9):
        cache.set(f"live-{index}", index, timeout=3600)
    assert cache.get("live-0") == 0  # read, so now the most recently used

    cache.set("new", "added", timeout=3600)

    # The least recently used third, three of nine, went: live-1, live-2 and live-3.
    assert keys_held(cache) == ["new", "live-0", *(f"live-{index}" for index in range(8, 3, -1))]
