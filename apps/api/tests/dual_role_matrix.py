"""The dual-role coverage matrix (CLAUDE.md section 8 item 2; Objective 01).

Objective 01 requires 100% of protected endpoints exercised from both an Employee
session and an Administrator session. This pytest plugin, registered from the
root conftest.py, turns that number into a generated fact rather than a hand-kept
list:

- Enumeration. Every URL pattern under /api/ is read from the root URL conf at the
  end of the session, one row per (route, HTTP method). A viewset registered on the
  DRF router appears automatically, because the router's patterns are part of the
  URL conf. A route is *open* only when every permission class on its view is
  AllowAny; everything else is *protected*. The classification comes from the view,
  never from a list kept here.

- Recording. Every request a test makes through the Django/DRF test client is
  observed after the response: the resolved route, the method, the status, and the
  role the server's own authenticator resolved for the session. The role is
  captured inside apps.api.authentication.SessionAuthentication.authenticate, so
  a row is credited to a role only when the server saw that role on the request;
  a test's name or fixture list is never consulted. Records are kept only from
  tests that passed.

- Verdict. In the terminal summary the matrix is printed (one row per endpoint:
  anonymous / Employee / Administrator, with the statuses seen) followed by the
  percentage of protected endpoints exercised from both roles. On a full run of the
  suite, anything under 100% makes the session exit non-zero, even when every test
  passed. On a partial run (a path, -k, -m, --lf, --deselect, -x) the matrix is
  printed but not enforced, so one file can still be run on its own.

Two helpers are importable by tests: enumerate_endpoints() (test_rbac.py walks it
anonymously and with a forged session) and evaluate() (pure, so the failure mode
is unit-tested rather than trusted).
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pytest

PLUGIN_NAME = "dual-role-matrix"

ANONYMOUS = "anonymous"
_ROLE_ATTRIBUTE = "_dual_role_matrix_user"
_MISSING = object()
_IGNORED_METHODS = frozenset({"options", "head", "trace"})


# --- Enumeration ---------------------------------------------------------------------------


@dataclass
class Endpoint:
    """One (route, method) pair from the URL conf."""

    route: str  # django.urls.ResolverMatch.route, e.g. "api/users/<uuid:pk>/role"
    name: str | None  # namespaced URL name, e.g. "user-role"
    method: str  # upper-case, e.g. "PATCH"
    protected: bool
    permission_classes: tuple = field(compare=False)
    reverse_kwargs: dict = field(default_factory=dict, compare=False)
    view: str = field(default="", compare=False)

    @property
    def key(self) -> tuple[str, str]:
        return (self.route, self.method)

    @property
    def path(self) -> str:
        # Display only: drop the regex anchors a re_path/router pattern carries.
        return "/" + re.sub(r"\$(?=/|$)", "", re.sub(r"(?:^|(?<=/))\^", "", self.route))


def _sample_kwargs(pattern) -> dict | None:
    """Placeholder kwargs so a pattern with parameters can be reversed; None for the
    format-suffix variant the router adds, which is not a route of its own."""
    from django.urls.converters import IntConverter, UUIDConverter
    from django.urls.resolvers import RegexPattern, RoutePattern

    if isinstance(pattern, RoutePattern):
        if "format" in pattern.converters:
            return None
        kwargs = {}
        for name, converter in pattern.converters.items():
            if isinstance(converter, UUIDConverter):
                kwargs[name] = uuid.uuid4()
            elif isinstance(converter, IntConverter):
                kwargs[name] = 1
            else:
                kwargs[name] = "x"
        return kwargs
    if isinstance(pattern, RegexPattern):
        groups = pattern.regex.groupindex
        if "format" in groups:
            return None
        return {name: "1" for name in groups}
    raise TypeError(pattern)  # pragma: no cover


def _permission_classes(callback, view_class) -> tuple:
    initkwargs = getattr(callback, "view_initkwargs", None) or getattr(callback, "initkwargs", None) or {}
    return tuple(initkwargs.get("permission_classes", getattr(view_class, "permission_classes", ())))


def _methods(callback, view_class) -> list[str]:
    actions = getattr(callback, "actions", None)  # a viewset bound by the router
    if actions:
        names = list(actions)
    else:
        names = [m for m in view_class.http_method_names if hasattr(view_class, m)]
    return [m.upper() for m in names if m not in _IGNORED_METHODS]


def _is_open(permission_classes: tuple) -> bool:
    from rest_framework.permissions import AllowAny

    return bool(permission_classes) and all(p is AllowAny for p in permission_classes)


def enumerate_endpoints(patterns=None, prefix: str = "", namespace: str | None = None) -> list[Endpoint]:
    """Every (route, method) reachable under ``prefix`` in ``patterns``; by default
    everything under /api/ in the root URL conf. Nested includes are walked."""
    from django.urls import get_resolver
    from django.urls.resolvers import URLResolver

    if patterns is None:
        return [e for e in enumerate_endpoints(get_resolver().url_patterns) if e.route.startswith("api/")]

    endpoints = []
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            inner = ":".join(filter(None, [namespace, entry.namespace]))
            endpoints.extend(enumerate_endpoints(entry.url_patterns, route, inner or None))
            continue
        kwargs = _sample_kwargs(entry.pattern)
        if kwargs is None:
            continue
        callback = entry.callback
        view_class = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
        name = ":".join(filter(None, [namespace, entry.name])) or None
        if view_class is None:
            # Not a DRF view: no permission classes to read, so it cannot be shown
            # protected. It is listed as protected with no method so the matrix
            # fails and names it.
            endpoints.append(Endpoint(route, name, "?", True, (), kwargs, repr(callback)))
            continue
        permissions = _permission_classes(callback, view_class)
        for method in _methods(callback, view_class):
            endpoints.append(
                Endpoint(route, name, method, not _is_open(permissions), permissions, kwargs, view_class.__name__)
            )
    return endpoints


# --- Verdict --------------------------------------------------------------------------------


@dataclass
class Row:
    endpoint: Endpoint
    seen: dict  # role label -> {"statuses": set[int], "tests": set[str]}

    def missing(self, roles) -> list[str]:
        return [role for role in roles if role not in self.seen]


@dataclass
class Verdict:
    rows: list[Row]
    roles: tuple[str, ...]
    open_rows: list[Endpoint]

    @property
    def protected(self) -> list[Row]:
        return [row for row in self.rows if row.endpoint.protected]

    @property
    def incomplete(self) -> list[Row]:
        return [row for row in self.protected if row.missing(self.roles)]

    @property
    def covered(self) -> int:
        return len(self.protected) - len(self.incomplete)

    @property
    def percentage(self) -> float:
        return 100.0 if not self.protected else 100.0 * self.covered / len(self.protected)

    @property
    def complete(self) -> bool:
        return not self.incomplete


def evaluate(endpoints: list[Endpoint], records: dict, roles: tuple[str, ...]) -> Verdict:
    """Pure: ``records`` maps (route, method) -> role label -> {"statuses", "tests"}."""
    rows = [Row(e, dict(records.get(e.key, {}))) for e in endpoints if e.protected]
    return Verdict(rows, roles, [e for e in endpoints if not e.protected])


def format_matrix(verdict: Verdict) -> list[str]:
    columns = (ANONYMOUS,) + verdict.roles
    header = ["METHOD", "PATH", "NAME", *(c.upper() for c in columns)]
    table = [header]
    for row in verdict.protected:
        cells = [row.endpoint.method, row.endpoint.path, row.endpoint.name or "-"]
        for column in columns:
            seen = row.seen.get(column)
            if seen is None:
                cells.append("MISSING" if column in verdict.roles else "-")
            else:
                statuses = ",".join(str(s) for s in sorted(seen["statuses"]))
                cells.append(f"{statuses} ({len(seen['tests'])} tests)")
        table.append(cells)
    widths = [max(len(r[i]) for r in table) for i in range(len(header))]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)).rstrip() for r in table]
    if verdict.open_rows:
        opened = ", ".join(f"{e.method} {e.path}" for e in verdict.open_rows)
        lines.append(f"open (AllowAny, not counted): {opened}")
    return lines


def summary_line(verdict: Verdict) -> str:
    total = len(verdict.protected)
    return (
        f"Dual-role coverage: {verdict.covered}/{total} protected endpoints exercised from both "
        f"{' and '.join(verdict.roles)} sessions ({verdict.percentage:.1f}%)"
    )


def exit_status_for(exitstatus, enforced: bool, complete: bool):
    """The run's exit status once the matrix has had its say.

    Incomplete coverage fails an otherwise green full run — that is the whole point
    of the gate. It never rescues a run that already failed, and it never speaks on
    a partial run, where the missing roles are simply the tests that were not asked
    for.
    """
    if enforced and not complete and exitstatus == pytest.ExitCode.OK:
        return pytest.ExitCode.TESTS_FAILED
    return exitstatus


def failure_lines(verdict: Verdict) -> list[str]:
    lines = [
        f"{len(verdict.incomplete)} of {len(verdict.protected)} protected endpoints lack a passing test "
        f"from both roles (CLAUDE.md section 8 item 2; Objective 01 requires 100%):"
    ]
    for row in verdict.incomplete:
        e = row.endpoint
        missing = ", ".join(f"no {role} test" for role in row.missing(verdict.roles))
        if e.method == "?":
            missing = f"not a DRF view ({e.view}); its permission classes cannot be read"
        lines.append(f"  {e.method} {e.path} ({e.name or e.view}): {missing}")
    lines.append(
        "A protected endpoint is credited to a role only when a passing test sent a request to it "
        "from a session the server authenticated as that role."
    )
    return lines


# --- The plugin -----------------------------------------------------------------------------


class DualRoleMatrixPlugin:
    def __init__(self):
        self.records = defaultdict(dict)  # (route, method) -> role -> {"statuses", "tests"}
        self._pending: list[tuple[tuple[str, str], str, int]] = []
        self._current_test: str | None = None
        self._deselected = 0
        self._unpatch = []

    # Recording ----------------------------------------------------------------------------

    def observe(self, response) -> None:
        from django.urls.exceptions import Resolver404

        request = getattr(response, "wsgi_request", None)
        if request is None:
            return
        try:
            match = getattr(response, "resolver_match", None)
            route = getattr(match, "route", None) if match is not None else None
        except Resolver404:
            # The test client sets response.resolver_match to a lazy resolve() of the
            # path, so touching it re-runs resolution and raises for a path that
            # matches no pattern. That is a 404 the suite is entitled to assert on:
            # record nothing, and never let this observer change a test's outcome.
            return
        if not route:
            return
        user = getattr(request, _ROLE_ATTRIBUTE, _MISSING)
        if user is _MISSING:
            return  # the server's authenticator never ran: a 404, or not a DRF view
        role = ANONYMOUS if user is None else getattr(getattr(user, "role", None), "role_name", "?")
        self._pending.append(((match.route, request.method.upper()), role, response.status_code))

    def _commit(self) -> None:
        for key, role, status in self._pending:
            seen = self.records[key].setdefault(role, {"statuses": set(), "tests": set()})
            seen["statuses"].add(status)
            seen["tests"].add(self._current_test)
        self._pending = []

    def _patch(self) -> None:
        from django.test.client import Client

        from apps.api.authentication import SessionAuthentication

        plugin = self
        original_request = Client.request
        original_authenticate = SessionAuthentication.authenticate

        def request(self, **kwargs):
            response = original_request(self, **kwargs)
            plugin.observe(response)
            return response

        def authenticate(self, request):
            result = original_authenticate(self, request)
            # None: no session, anonymous. Otherwise (user, None). The attribute goes
            # on the WSGIRequest the test client hands back as response.wsgi_request.
            setattr(request._request, _ROLE_ATTRIBUTE, None if result is None else result[0])
            return result

        Client.request = request
        SessionAuthentication.authenticate = authenticate
        self._unpatch = [
            lambda: setattr(Client, "request", original_request),
            lambda: setattr(SessionAuthentication, "authenticate", original_authenticate),
        ]

    # pytest hooks ---------------------------------------------------------------------------

    def pytest_sessionstart(self, session):
        if not session.config.getoption("collectonly"):
            self._patch()

    def pytest_deselected(self, items):
        self._deselected += len(items)

    def pytest_runtest_logstart(self, nodeid, location):
        self._current_test = nodeid
        self._pending = []

    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return
        if report.passed:
            self._commit()
        else:
            self._pending = []  # a failing test proves nothing about the route

    def _is_full_run(self, session) -> bool:
        config = session.config
        if config.getoption("collectonly"):
            return False
        if self._deselected or session.shouldstop or session.shouldfail:
            return False
        for option in ("keyword", "markexpr", "lf", "deselect"):
            if config.getoption(option, default=None):
                return False
        if config.args_source is not config.ArgsSource.ARGS:
            return True
        # Explicit paths: full only if they cover every configured testpath.
        testpaths = [config.rootpath / p for p in (config.getini("testpaths") or ["."])]
        given = [Path(arg.split("::", 1)[0]).resolve() for arg in config.args]
        return all(any(g == t or g in t.parents for g in given) for t in testpaths)

    def verdict(self) -> Verdict:
        from apps.core.constants import ROLE_NAMES

        return evaluate(enumerate_endpoints(), self.records, tuple(ROLE_NAMES))

    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        if config.getoption("collectonly"):
            return
        verdict = self.verdict()
        enforced = self._is_full_run(terminalreporter._session)
        terminalreporter.write_sep("-", "dual-role coverage matrix (protected endpoints under /api/)")
        for line in format_matrix(verdict):
            terminalreporter.write_line(line)
        colour = {"green": True} if verdict.complete else {"red": True, "bold": True}
        terminalreporter.write_line(summary_line(verdict), **colour)
        if verdict.complete:
            return
        if enforced:
            terminalreporter.write_sep("!", "dual-role coverage matrix incomplete: the run fails", red=True, bold=True)
        else:
            terminalreporter.write_line(
                "(partial run: the matrix is reported but not enforced; a full `pytest` run fails below 100%)",
                yellow=True,
            )
        for line in failure_lines(verdict):
            terminalreporter.write_line(line, red=enforced, yellow=not enforced)

    def pytest_sessionfinish(self, session, exitstatus):
        for undo in self._unpatch:
            undo()
        self._unpatch = []
        if session.config.getoption("collectonly"):
            return
        session.exitstatus = exit_status_for(
            exitstatus, enforced=self._is_full_run(session), complete=self.verdict().complete
        )


def pytest_configure(config):
    config.pluginmanager.register(DualRoleMatrixPlugin(), PLUGIN_NAME)
