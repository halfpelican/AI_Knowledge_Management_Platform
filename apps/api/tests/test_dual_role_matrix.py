"""The dual-role coverage matrix itself (apps/api/tests/dual_role_matrix.py).

The matrix is the number reported at the gate (CLAUDE.md section 8 item 2), so its
three parts are tested rather than trusted: a viewset registered on a router is
enumerated without anyone listing it; the verdict names a missing role and fails
below 100%; and a request is credited to the role the server authenticated, not to
the fixture the test asked for.
"""

import pytest
from django.urls import reverse
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.api.tests.dual_role_matrix import (
    ANONYMOUS,
    PLUGIN_NAME,
    Endpoint,
    enumerate_endpoints,
    evaluate,
    exit_status_for,
    failure_lines,
    format_matrix,
    summary_line,
)
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, ROLE_NAMES

ROLES = tuple(ROLE_NAMES)


# --- Enumeration: a router's viewsets appear automatically -----------------------------------


class ThrowawayViewSet(viewsets.ViewSet):
    def list(self, request):  # pragma: no cover - never dispatched
        return Response([])

    def create(self, request):  # pragma: no cover
        return Response({})

    def retrieve(self, request, pk=None):  # pragma: no cover
        return Response({})


class OpenViewSet(ThrowawayViewSet):
    permission_classes = [AllowAny]


def test_a_viewset_registered_on_a_router_is_enumerated_per_method():
    router = DefaultRouter()
    router.register("things", ThrowawayViewSet, basename="thing")
    router.register("public", OpenViewSet, basename="public")

    endpoints = enumerate_endpoints(router.urls, prefix="api/")
    by_key = {(e.name, e.method): e for e in endpoints}

    assert {("thing-list", "GET"), ("thing-list", "POST"), ("thing-detail", "GET")} <= set(by_key)
    assert all(by_key[k].protected for k in by_key if k[0].startswith("thing-"))
    assert by_key[("thing-detail", "GET")].path.startswith("/api/things/")
    assert by_key[("thing-list", "GET")].path == "/api/things/"
    assert by_key[("thing-list", "GET")].permission_classes == (IsAuthenticated,)
    # The open viewset is enumerated too, classified from its own permission classes.
    assert not by_key[("public-list", "GET")].protected
    # Format-suffix variants (things.json) are not endpoints of their own.
    assert not [e for e in endpoints if "format" in e.route]


def test_enumeration_of_the_real_url_conf_covers_only_api():
    endpoints = enumerate_endpoints()
    assert endpoints
    assert all(e.route.startswith("api/") for e in endpoints)
    assert {e.method for e in endpoints} <= {"GET", "POST", "PATCH", "PUT", "DELETE"}


# --- Verdict: the failure mode --------------------------------------------------------------


def _endpoint(name, method="GET", protected=True):
    return Endpoint(f"api/{name}", name, method, protected, (IsAuthenticated,))


def _seen(*roles, status=200):
    return {role: {"statuses": {status}, "tests": {"t"}} for role in roles}


def test_a_protected_endpoint_reached_from_both_roles_is_covered():
    endpoints = [_endpoint("a"), _endpoint("open", protected=False)]
    verdict = evaluate(endpoints, {("api/a", "GET"): _seen(ANONYMOUS, *ROLES)}, ROLES)
    assert verdict.complete
    assert verdict.percentage == 100.0
    assert "1/1" in summary_line(verdict)
    assert [e.name for e in verdict.open_rows] == ["open"]


def test_a_missing_administrator_test_fails_the_verdict_and_is_named():
    endpoints = [_endpoint("a"), _endpoint("b", "PATCH")]
    records = {
        ("api/a", "GET"): _seen(*ROLES),
        ("api/b", "PATCH"): _seen(EMPLOYEE_ROLE_NAME, status=403),
    }
    verdict = evaluate(endpoints, records, ROLES)
    assert not verdict.complete
    assert verdict.percentage == 50.0
    [row] = verdict.incomplete
    assert row.endpoint.name == "b"
    assert row.missing(ROLES) == [ADMINISTRATOR_ROLE_NAME]
    text = "\n".join(failure_lines(verdict))
    assert "PATCH /api/b (b): no Administrator test" in text
    assert "1 of 2 protected endpoints" in text
    matrix = "\n".join(format_matrix(verdict))
    assert "MISSING" in matrix


def test_a_role_that_only_appears_on_a_failing_test_does_not_count():
    # evaluate() sees only committed records; the plugin commits after a passing
    # call phase, so a test that failed leaves nothing behind.
    verdict = evaluate([_endpoint("a")], {}, ROLES)
    assert not verdict.complete
    assert verdict.percentage == 0.0


def test_an_open_endpoint_is_never_counted():
    verdict = evaluate([_endpoint("open", protected=False)], {}, ROLES)
    assert verdict.complete
    assert verdict.percentage == 100.0
    assert verdict.protected == []


def test_a_view_that_is_not_drf_cannot_pass_as_covered():
    endpoint = Endpoint("api/raw", "raw", "?", True, (), {}, "function raw_view")
    verdict = evaluate([endpoint], {("api/raw", "GET"): _seen(*ROLES)}, ROLES)
    assert not verdict.complete
    assert "not a DRF view" in "\n".join(failure_lines(verdict))


# --- Enforcement: what the run's exit status becomes -------------------------------------------


@pytest.mark.parametrize(
    "exitstatus, enforced, complete, expected",
    [
        # The gate: a full run where every test passed but a role is missing fails.
        (pytest.ExitCode.OK, True, False, pytest.ExitCode.TESTS_FAILED),
        (pytest.ExitCode.OK, True, True, pytest.ExitCode.OK),
        # A partial run is silent: the missing roles are the tests not asked for.
        (pytest.ExitCode.OK, False, False, pytest.ExitCode.OK),
        # It never rescues or reclassifies a run that already failed.
        (pytest.ExitCode.TESTS_FAILED, True, True, pytest.ExitCode.TESTS_FAILED),
        (pytest.ExitCode.INTERRUPTED, True, False, pytest.ExitCode.INTERRUPTED),
    ],
)
def test_incomplete_coverage_fails_an_otherwise_green_full_run(exitstatus, enforced, complete, expected):
    assert exit_status_for(exitstatus, enforced=enforced, complete=complete) == expected


# --- Recording: the role is what the server resolved -------------------------------------------


@pytest.fixture
def plugin(request):
    return request.config.pluginmanager.get_plugin(PLUGIN_NAME)


def _pending(plugin, route, method):
    return [(role, status) for (r, m), role, status in plugin._pending if (r, m) == (route, method)]


@pytest.mark.django_db
def test_a_request_is_credited_to_the_role_the_server_authenticated(plugin, session_client):
    assert session_client.client.get(reverse("role-list")).status_code == 200
    assert _pending(plugin, "api/roles", "GET") == [(session_client.role_name, 200)]


@pytest.mark.django_db
def test_an_anonymous_request_is_credited_to_nobody(plugin, api_client):
    assert api_client.get(reverse("role-list")).status_code == 401
    assert _pending(plugin, "api/roles", "GET") == [(ANONYMOUS, 401)]


@pytest.mark.django_db
def test_the_role_recorded_is_the_current_one_not_the_fixture(plugin, employee_client, employee, administrator_role):
    # A test that promotes its user mid-way is credited to the promoted role, so a
    # fixture named employee_client cannot mislabel an Administrator's request.
    employee.role = administrator_role
    employee.save(update_fields=["role"])
    assert employee_client.get(reverse("user-list")).status_code == 200
    assert _pending(plugin, "api/users", "GET") == [(ADMINISTRATOR_ROLE_NAME, 200)]


@pytest.mark.django_db
def test_a_request_that_never_resolves_a_route_records_nothing(plugin, employee_client):
    assert employee_client.get("/api/no/such/route").status_code == 404
    assert not plugin._pending
