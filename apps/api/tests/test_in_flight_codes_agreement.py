"""The client's copies of the in-flight codes must equal the server's (D-79, D-85).

``POST /api/ask`` can answer two kinds of 429, and so can the three ingestion routes: the
rate limit's, which carries no ``code`` and a ``Retry-After``, and the in-flight refusal's,
which carries ``ASK_IN_FLIGHT_CODE`` or ``INGESTION_IN_FLIGHT_CODE`` and no ``Retry-After``.
The client tells them apart by ``code`` alone and never parses ``detail``
(docs/api-contract.md). Each screen compares the reply's ``code`` with a copy of the server's
value, ``ASK_IN_FLIGHT_CODE`` in ``frontend/src/api/ask.js`` and ``INGESTION_IN_FLIGHT_CODE``
in ``frontend/src/api/ingestion.js``.

**A drifted copy fails quietly.** The in-flight 429 is then read as the rate limit's, and the
screen tells the user a limit was reached when it was not. The front-end suite cannot see the
server: its fixtures spell the code as the contract does, so they catch a client copy that
drifts from the contract and miss a server value that does. This test ties the copies to the
values the views send, as ``apps/accounts/tests/test_password_policy_agreement.py`` ties the
password policy. It reads each ``export const`` line as text and runs no JavaScript, so it
passes on a machine with nothing but Python.

Beyond the two the client branches on today, every ``*_CODE`` the client exports must name a
constant of ``apps/api/views.py`` with the same value, so a third copy is held to the same rule
from the day it is added.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from django.conf import settings

from apps.api import views

FRONTEND_SOURCE = Path(settings.BASE_DIR) / "frontend" / "src"

# The client's copies the screens branch on, and the file each one is exported from.
CLIENT_COPIES = [
    ("ASK_IN_FLIGHT_CODE", FRONTEND_SOURCE / "api" / "ask.js"),
    ("INGESTION_IN_FLIGHT_CODE", FRONTEND_SOURCE / "api" / "ingestion.js"),
    # D-123: the recording screen tells the in-flight 429 from the rate's, and the
    # disabled 503 from the unavailable one, by these.
    ("TRANSCRIPTION_IN_FLIGHT_CODE", FRONTEND_SOURCE / "api" / "transcriptions.js"),
    ("TRANSCRIPTION_DISABLED_CODE", FRONTEND_SOURCE / "api" / "transcriptions.js"),
    ("TRANSCRIPTION_UNAVAILABLE_CODE", FRONTEND_SOURCE / "api" / "transcriptions.js"),
]

# `export const NAME_CODE = '...'`, a single-quoted string on one line, as both files write it.
EXPORTED_CODE = re.compile(r"^export const ([A-Z][A-Z0-9_]*_CODE) = ('(?:[^'\\]|\\.)*')\s*$", re.MULTILINE)


def _exported_codes(path: Path) -> dict[str, str]:
    """Every `*_CODE` string constant `path` exports, decoded. JS and Python agree on the
    escapes a single-quoted literal can hold, so Python's parser reads it safely."""
    source = path.read_text(encoding="utf-8")
    return {name: ast.literal_eval(literal) for name, literal in EXPORTED_CODE.findall(source)}


@pytest.mark.parametrize(("name", "path"), CLIENT_COPIES, ids=[name for name, _ in CLIENT_COPIES])
def test_the_clients_copy_of_each_in_flight_code_equals_the_one_the_server_sends(name, path):
    if not path.exists():
        pytest.fail(
            f"{path} is missing. The screens read {name} from it; if it moved, point this "
            "test at the new file rather than deleting it."
        )
    client = _exported_codes(path)
    assert name in client, f"{name} is not exported from {path.name}; did it move or get renamed?"
    server = getattr(views, name, None)
    assert isinstance(server, str), f"apps/api/views.py no longer defines {name} as a string"
    assert client[name] == server, (
        f"{path.name} has {name} = {client[name]!r}, and the server sends {server!r}. The screen "
        "would read that 429 as the rate limit's."
    )


def test_every_code_the_client_exports_is_a_server_constant_with_the_same_value():
    exported = {}
    for path in sorted(FRONTEND_SOURCE.rglob("*.js")) + sorted(FRONTEND_SOURCE.rglob("*.jsx")):
        for name, value in _exported_codes(path).items():
            exported[name] = (value, path.relative_to(FRONTEND_SOURCE).as_posix())

    # Not vacuous: the sweep finds the two copies the screens branch on.
    assert {name for name, _ in CLIENT_COPIES} <= exported.keys()

    for name, (value, where) in exported.items():
        server = getattr(views, name, None)
        assert server == value, f"frontend/src/{where} exports {name} = {value!r}; apps/api/views.py has {server!r}"
