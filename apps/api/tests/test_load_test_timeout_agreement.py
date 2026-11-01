"""k6's ask timeout must outlast the server's in-flight slot (D-79, D-82's note of 1 November 2026).

NFR-08's first run on 1 November 2026 was INVALID for this: k6 gave up on asks at 300 s
while the server was still answering them, so each account's slot was still held, and the
account's next asks were ``ask_in_flight`` 429s until the server finished, 67 of them. Since
then ``tests/load/common.js`` keeps ``ASK_SLOT_TIMEOUT_S``, a copy of the server's
``ASK_SLOT_TIMEOUT_SECONDS``, and ``ASK_TIMEOUT_S`` is that copy plus a margin.

**A drifted copy fails quietly.** If generation's timeout, its attempts or the embedding margin
grow, the slot outlasts k6 again, and the next load run is INVALID on 429s, found only after it
has run. This test reads the two ``export const`` lines as text and runs no JavaScript, as
``test_in_flight_codes_agreement.py`` does for the in-flight codes.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

from apps.api.ask_slot import ASK_SLOT_TIMEOUT_SECONDS

COMMON_JS = Path(settings.BASE_DIR) / "tests" / "load" / "common.js"

SLOT_COPY = re.compile(r"^export const ASK_SLOT_TIMEOUT_S = (\d+);\s*$", re.MULTILINE)
ASK_TIMEOUT = re.compile(r"^export const ASK_TIMEOUT_S = ASK_SLOT_TIMEOUT_S \+ (\d+);\s*$", re.MULTILINE)


def _source() -> str:
    return COMMON_JS.read_text(encoding="utf-8")


def test_the_k6_copy_of_the_slot_timeout_equals_the_servers():
    found = SLOT_COPY.findall(_source())
    assert len(found) == 1, (
        f"{COMMON_JS} must export ASK_SLOT_TIMEOUT_S once, as a whole number of seconds; "
        f"found {found}"
    )
    assert int(found[0]) == ASK_SLOT_TIMEOUT_SECONDS, (
        f"common.js copies the slot timeout as {found[0]} s but apps/api/ask_slot.py's is "
        f"{ASK_SLOT_TIMEOUT_SECONDS} s. Change the copy, or k6 can abandon an ask whose slot is "
        "still held and the run goes INVALID on ask_in_flight 429s."
    )


def test_the_k6_ask_timeout_is_the_slot_timeout_plus_a_margin():
    found = ASK_TIMEOUT.findall(_source())
    assert len(found) == 1, (
        f"{COMMON_JS} must define ASK_TIMEOUT_S as ASK_SLOT_TIMEOUT_S plus a margin in seconds, "
        f"so it can never fall below the slot's timeout; found {found}"
    )
    assert int(found[0]) > 0
