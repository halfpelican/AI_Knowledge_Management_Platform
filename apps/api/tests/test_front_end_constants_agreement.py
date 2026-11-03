"""The client's copies of server constants in ``frontend/src/constants.js`` must equal
``apps/core/constants.py`` (D-61's gap 13; item 10's finding S4).

``CLAUDE.md`` section 5 puts the tuned constants in ``apps/core/constants.py`` "and nowhere
else", and the front end restates some of them anyway, for a reason each copy's comment
gives: the upload screen refuses a format or a size before a byte is sent (FR-08), the
search field refuses a term under two characters client-side as FR-12 asks, and the question
field keeps Ask disabled until the question is within its bounds. Each is a convenience; the
server decides regardless (invariant 4).

**A drifted copy fails quietly, and in the user's face.** A client minimum above the
server's refuses a search the server would run; a client ceiling below the server's refuses
a file the server would take; a format list that gained an entry sends a file the server will
always answer 415. Nothing in either suite would notice: the front-end suite cannot import
Python, and its fixtures are written against the client's own values.

This test is the tie, built as ``test_in_flight_codes_agreement.py`` and
``apps/accounts/tests/test_password_policy_agreement.py`` are. It reads ``constants.js`` as
text and runs no JavaScript, so it passes on a machine with nothing but Python.

**What it holds**, enumerated from ``constants.js`` on 2 November 2026, every export that
copies a value of ``apps/core/constants.py``:

- ``SEARCH_MINIMUM_LENGTH``, ``QUESTION_MINIMUM_LENGTH``, ``QUESTION_MAXIMUM_LENGTH`` and
  ``MAX_UPLOAD_BYTES``: each equal to its server constant.
- ``MAX_UPLOAD_LABEL``: the ceiling in whole megabytes, as the server's value states it.
- ``ACCEPTED_EXTENSIONS`` and ``ACCEPTED_FORMATS_LABEL``: D-15's four, no more, no fewer.
- ``DOCUMENT_STATUS``, ``ROLES`` and ``SOURCE_TYPE``: the server's whole vocabulary, each
  value once. Equality and not inclusion, for ``DOCUMENT_STATUS`` especially: D-51 is the
  record of a status the server added and the client did not list, which the screens then
  displayed while applying the wrong rule to it.

**What it does not hold.** ``TEXT.noAnswerFallback`` and ``TEXT.provenanceRemovedFallback``
are held by the front-end suite, which reads ``apps/core/constants.py`` itself
(``frontend/tests/fakeApi.js``). Two copied texts live in ``constants.js`` whose server
originals are not in ``apps/core/constants.py``: ``TEXT.dashboardRangeInverted`` (the server's
is ``apps/api/serializers.py`` ``DATE_RANGE_REVERSED_MESSAGE``) and the four formats inside
``VALIDATION.fileTypeUnsupported`` (``apps/api/views.py`` ``UNSUPPORTED_FORMAT_MESSAGE``).
Neither is tied here. Nor is the literal "50 MB" in ``apps/api/views.py``
``FILE_TOO_LARGE_MESSAGE``, which is the server restating its own constant and an open item
of its own.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from django.conf import settings

from apps.core import constants

CLIENT_CONSTANTS = Path(settings.BASE_DIR) / "frontend" / "src" / "constants.js"

# The upload ceiling is stated in binary megabytes on both sides: 50 * 1024 * 1024.
MEGABYTE = 1024 * 1024

# (the client's export, the server constant it copies)
BOUNDS = [
    ("SEARCH_MINIMUM_LENGTH", "MINIMUM_SEARCH_LENGTH"),
    ("QUESTION_MINIMUM_LENGTH", "MINIMUM_QUESTION_LENGTH"),
    ("QUESTION_MAXIMUM_LENGTH", "MAXIMUM_QUESTION_LENGTH"),
    ("MAX_UPLOAD_BYTES", "MAX_UPLOAD_BYTES"),
]

VOCABULARIES = [
    ("DOCUMENT_STATUS", "DOCUMENT_STATUS_VALUES"),
    ("ROLES", "ROLE_NAMES"),
    ("SOURCE_TYPE", "SOURCE_TYPES"),
]

# `key: 'value',` inside an exported object, a single-quoted string on one line.
OBJECT_ENTRY = re.compile(r"^\s+([A-Za-z_][A-Za-z0-9_]*): ('(?:[^'\\]|\\.)*'),?\s*$")
# What else may sit inside such an object without being an entry.
OBJECT_FILLER = re.compile(r"^\s*(//.*)?$")


@pytest.fixture(scope="module")
def client_source() -> str:
    if not CLIENT_CONSTANTS.exists():
        pytest.fail(
            f"{CLIENT_CONSTANTS} is missing. The screens read their copies of the server's "
            "constants from it; if it moved, point this test at the new file rather than "
            "deleting it."
        )
    return CLIENT_CONSTANTS.read_text(encoding="utf-8")


def _exported(source: str, name: str) -> str:
    """The right-hand side of `export const <name> = ...`, as written on its line."""
    match = re.search(rf"^export const {re.escape(name)} = (.+)$", source, re.MULTILINE)
    assert match, f"{name} is not exported from constants.js; did it move or get renamed?"
    return match.group(1).strip()


def _javascript_string(literal: str) -> str:
    """A single-quoted JS string literal, decoded. JS and Python agree on the escapes such a
    literal can hold, so Python's own parser reads it safely."""
    assert re.fullmatch(r"'(?:[^'\\]|\\.)*'", literal), f"not a single-quoted string: {literal}"
    return ast.literal_eval(literal)


def _javascript_integer(expression: str) -> int:
    """An integer written as digits, or as a product of digits (`50 * 1024 * 1024`). Nothing
    else is evaluated."""
    assert re.fullmatch(r"\d+(\s*\*\s*\d+)*", expression), f"not an integer or a product of them: {expression}"
    product = 1
    for factor in expression.split("*"):
        product *= int(factor)
    return product


def _exported_object(source: str, name: str) -> dict[str, str]:
    """`export const <name> = { key: 'value', ... }`, each entry on its own line. A line in the
    object that is neither an entry nor a comment fails here rather than being skipped, so an
    entry written some other way cannot drop out of the comparison unseen."""
    match = re.search(rf"^export const {re.escape(name)} = \{{\n(.*?)^\}}", source, re.MULTILINE | re.DOTALL)
    assert match, f"{name} is not exported from constants.js as an object; did it move or get renamed?"
    entries: dict[str, str] = {}
    for line in match.group(1).splitlines():
        entry = OBJECT_ENTRY.match(line)
        if entry:
            entries[entry.group(1)] = _javascript_string(entry.group(2))
            continue
        assert OBJECT_FILLER.match(line), f"{name} holds a line this test cannot read: {line.strip()!r}"
    return entries


@pytest.mark.parametrize(("client_name", "server_name"), BOUNDS, ids=[client for client, _ in BOUNDS])
def test_the_clients_copy_of_each_bound_equals_the_server_constant(client_source, client_name, server_name):
    client = _javascript_integer(_exported(client_source, client_name))
    server = getattr(constants, server_name)
    assert client == server, (
        f"constants.js has {client_name} = {client}, and apps/core/constants.py has "
        f"{server_name} = {server}. The screen would refuse, or allow, what the server does not."
    )


def test_the_clients_upload_ceiling_label_states_the_servers_ceiling(client_source):
    assert constants.MAX_UPLOAD_BYTES % MEGABYTE == 0, "the server's ceiling is no longer a whole number of MB"
    label = _javascript_string(_exported(client_source, "MAX_UPLOAD_LABEL"))
    assert label == f"{constants.MAX_UPLOAD_BYTES // MEGABYTE} MB", (
        f"constants.js tells the user the ceiling is {label!r}; the server's is "
        f"{constants.MAX_UPLOAD_BYTES} bytes."
    )


def test_the_clients_accepted_extensions_are_the_servers_four(client_source):
    literal = _exported(client_source, "ACCEPTED_EXTENSIONS")
    assert re.fullmatch(r"\[\s*'[^']*'(\s*,\s*'[^']*')*\s*,?\s*\]", literal), f"not a list of strings: {literal}"
    client = ast.literal_eval(literal)
    assert len(client) == len(set(client)), f"ACCEPTED_EXTENSIONS lists an extension twice: {client}"
    assert set(client) == set(constants.ACCEPTED_EXTENSIONS), (
        f"constants.js accepts {sorted(client)} before upload; the server's are "
        f"{sorted(constants.ACCEPTED_EXTENSIONS)} (D-15)."
    )


def test_the_clients_accepted_formats_label_names_the_servers_four(client_source):
    label = _javascript_string(_exported(client_source, "ACCEPTED_FORMATS_LABEL"))
    named = [part.strip() for part in label.split(",")]
    assert all(part and part == part.upper() for part in named), f"not a list of upper-case formats: {label!r}"
    assert len(named) == len(set(named)), f"ACCEPTED_FORMATS_LABEL names a format twice: {label!r}"
    assert {part.lower() for part in named} == set(constants.ACCEPTED_FORMATS), (
        f"The refusal message names {label!r}; the server accepts {sorted(constants.ACCEPTED_FORMATS)} (D-15)."
    )


@pytest.mark.parametrize(("client_name", "server_name"), VOCABULARIES, ids=[client for client, _ in VOCABULARIES])
def test_the_clients_copy_of_each_vocabulary_lists_every_server_value_once(client_source, client_name, server_name):
    client = list(_exported_object(client_source, client_name).values())
    server = getattr(constants, server_name)
    # Not vacuous: the object was read and holds at least as many entries as the server has.
    assert len(client) >= len(server), f"{client_name} was read as {client}"
    assert len(client) == len(set(client)), f"{client_name} lists a value twice: {client}"
    assert set(client) == set(server), (
        f"constants.js {client_name} holds {sorted(client)}; apps/core/constants.py "
        f"{server_name} is {sorted(server)}. A value the client does not list is displayed "
        "with no rule of its own (D-51)."
    )
