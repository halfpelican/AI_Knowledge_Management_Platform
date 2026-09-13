"""The client's copy of the password policy must equal the server's (FR-01).

FR-01 states the complexity rule twice, once per side: the server enforces it and
the registration form shows the same rules as the user types, keeping submit
disabled until they all pass. Two statements of one rule can drift, and one already
did — the client first counted any non-alphanumeric character as special, including
a space, so a password ending in a space passed the form and was refused by the
server.

Nothing else ties the two together: there is no build step, no generated file and no
front-end test runner. This test is that tie. It reads the client module as text and
compares the two values it declares against the constants the validator uses, so an
edit to either side fails here rather than at a demonstration.

It deliberately does not run JavaScript. Parsing two `export const` lines needs no
toolchain, and the suite must keep passing on a machine with nothing but Python.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from django.conf import settings

from apps.core.constants import PASSWORD_MINIMUM_LENGTH, PASSWORD_SPECIAL_CHARACTERS

CLIENT_POLICY = Path(settings.BASE_DIR) / "frontend" / "src" / "utils" / "password.js"


def _exported(name: str) -> str:
    """The right-hand side of `export const <name> = ...`, as written."""
    source = CLIENT_POLICY.read_text(encoding="utf-8")
    match = re.search(rf"^export const {re.escape(name)} = (.+)$", source, re.MULTILINE)
    assert match, f"{name} is not exported from {CLIENT_POLICY.name}; did it move or get renamed?"
    return match.group(1).strip()


def _javascript_string(literal: str) -> str:
    """Decode a single-quoted JS string literal. JS and Python agree on the escapes
    this file uses (\\' and \\\\), so Python's own parser is the safe reader."""
    return ast.literal_eval(literal)


@pytest.fixture(scope="module")
def client_policy_exists():
    if not CLIENT_POLICY.exists():
        pytest.fail(
            f"{CLIENT_POLICY} is missing. The registration form's password rules come "
            "from it; if the front end moved, point this test at the new location "
            "rather than deleting it."
        )


@pytest.mark.usefixtures("client_policy_exists")
def test_the_client_minimum_length_equals_the_server_constant():
    assert int(_exported("PASSWORD_MIN_LENGTH")) == PASSWORD_MINIMUM_LENGTH


@pytest.mark.usefixtures("client_policy_exists")
def test_the_client_special_characters_equal_the_server_set():
    client = _javascript_string(_exported("PASSWORD_SPECIAL_CHARACTERS"))

    # As a set, because the client stores a string and the server a frozenset.
    assert set(client) == set(PASSWORD_SPECIAL_CHARACTERS)
    # And no duplicates on the client, which a set comparison alone would hide.
    assert len(client) == len(set(client)) == len(PASSWORD_SPECIAL_CHARACTERS)


@pytest.mark.usefixtures("client_policy_exists")
def test_neither_side_counts_whitespace_as_a_special_character():
    """The regression the drift produced: a trailing space satisfied the client's
    rule and not the server's."""
    client = _javascript_string(_exported("PASSWORD_SPECIAL_CHARACTERS"))

    for character in " \t\n":
        assert character not in client
        assert character not in PASSWORD_SPECIAL_CHARACTERS
