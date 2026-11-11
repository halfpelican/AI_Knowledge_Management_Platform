"""FR-06 server-side RBAC on every protected route (CLAUDE.md section 6 invariant 4,
docs/decisions.md D-14 and D-21).

401 for no, forged or expired session; 403 for a valid session whose role lacks the
permission. The first tests walk every URL pattern under /api/ (enumerated by
apps/api/tests/dual_role_matrix.py, which also reports whether each protected
endpoint was reached from both roles) so a route added later without a permission
class fails here, not in the demonstration. The role is resolved from
role_permissions on every request, so a change takes effect on the user's next
request without re-login, in both directions.
"""

import datetime
import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import PermissionsMixin
from django.contrib.sessions.models import Session
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.models import Permission, Role, RolePermission
from apps.api.permissions import HasRolePermission
from apps.api.tests.dual_role_matrix import enumerate_endpoints
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    CONTRIBUTE_CONTENT_PERMISSION,
    EMPLOYEE_ROLE_NAME,
    MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION,
    MANAGE_ROLES_PERMISSION,
    MANAGE_TAGS_PERMISSION,
    REVIEW_KNOWLEDGE_GAPS_PERMISSION,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

# What docs/api-contract.md says: the two routes D-21 lets an anonymous client reach,
# and every protected URL name. The tests below check the URL conf's own permission
# classes against these names; the dual-role matrix (dual_role_matrix.py) then
# reports, per protected endpoint, whether a passing test reached it from each role.
OPEN_ROUTES = {"auth-register", "auth-login"}
PROTECTED_ROUTES = {"api-root", "auth-logout", "auth-me", "role-list", "user-list", "user-role",
                    "user-directory",  # FR-09 attendee selection (D-34)
                    "document-list", "document-reprocess",  # Stage 3: FR-08 (D-32)
                    "document-detail",  # Stage 4 item 10b: FR-12's citation link (D-46)
                    "meeting-list", "meeting-detail",  # Stage 3: FR-09; its DELETE is D-99's
                    "search",  # Stage 4: FR-12 keyword search (D-41)
                    "ask",  # Stage 4: FR-12's answer path, FR-13's turn
                    "conversation-list", "conversation-detail",  # Stage 4: FR-13
                    "dashboard",  # Stage 5 item 3: FR-14
                    "document-browse",  # Stage 5 item 2: FR-15 (D-72); its DELETE is document-detail's
                    "document-download",  # Stage 5 item 2a: FR-15's download link (D-75)
                    # NIT3004: FR-10's classification routes (D-104, D-105). contribute_content is
                    # checked inside each method, after the scoped lookup, as the deletes check
                    # theirs; apps/api/tests/test_document_classification.py proves the 404
                    # before the 403 on every one of them.
                    "document-classify", "document-classification", "document-tag-confirm",
                    "document-tag", "document-proposed-topic-confirm",
                    "document-proposed-topic-reject",
                    # A person applies a tag (D-105's dated note of 10 November 2026, night):
                    # contribute_content inside the method too, after the scoped lookup.
                    "document-tags",
                    # NIT3004: FR-19's knowledge-gap log, every route behind a permission (D-107)
                    "knowledge-gap-list", "knowledge-gap-cycles", "knowledge-gap-detail",
                    # NIT3004: FR-10's tag administration, both routes behind manage_tags (D-119
                    # finding 5; D-105's dated note of 10 November 2026, night)
                    "tag-list", "tag-detail",
                    # Recording transcription, both routes behind contribute_content
                    # (D-123)
                    "transcription-status", "transcription-list"}
# Routes that need more than a session, with the permission code they check.
# document-list is absent on purpose: its GET needs only a session, and the
# contribute permission its POST needs is returned by get_permissions() per method
# rather than declared on the class, so reading permission_classes cannot see it.
# apps/api/tests/test_document_upload.py proves that 403 directly.
# document-detail is absent for a stronger reason: its DELETE checks manage_documents
# INSIDE the method, after resolving the document through the caller's scope, because a
# permission class runs first and would answer 403 for a document the caller cannot see
# (D-73). apps/api/tests/test_document_delete.py proves the 403 and the 404 before it.
# meeting-detail is absent for the same reason: its DELETE checks manage_meetings inside the
# method, after the scoped lookup (D-99). apps/api/tests/test_meeting_delete.py proves both.
PERMISSIONED_ROUTES = {
    "user-list": MANAGE_ROLES_PERMISSION,
    "user-role": MANAGE_ROLES_PERMISSION,
    # D-32: reprocess declares contribute_content on the class. Listed on 9 November 2026, when
    # test_each_permissioned_route_checks_its_own_code began reading every route's classes and
    # found it absent from this table, though the route has checked the code since Stage 3.
    "document-reprocess": CONTRIBUTE_CONTENT_PERMISSION,
    # FR-19 (D-107): review_knowledge_gaps, a permission_classes entry on all three.
    "knowledge-gap-list": REVIEW_KNOWLEDGE_GAPS_PERMISSION,
    "knowledge-gap-cycles": REVIEW_KNOWLEDGE_GAPS_PERMISSION,
    "knowledge-gap-detail": REVIEW_KNOWLEDGE_GAPS_PERMISSION,
    # FR-10's tag administration (D-119 finding 5): manage_tags, a permission_classes entry on both.
    "tag-list": MANAGE_TAGS_PERMISSION,
    "tag-detail": MANAGE_TAGS_PERMISSION,
    # Recording transcription (D-123): contribute_content, a permission_classes entry on
    # both, so the 403 comes before the body is read. Nothing on either route is scoped.
    "transcription-status": CONTRIBUTE_CONTENT_PERMISSION,
    "transcription-list": CONTRIBUTE_CONTENT_PERMISSION,
}
# Codes checked inside a view rather than declared on it, so the seed test below covers them.
IN_VIEW_PERMISSION_CODES = {
    MANAGE_DOCUMENTS_PERMISSION,  # DocumentDetailView.delete (D-73)
    MANAGE_MEETINGS_PERMISSION,  # MeetingDetailView.delete (D-99)
    CONTRIBUTE_CONTENT_PERMISSION,  # FR-10's seven document routes (D-105 and its dated notes)
}

USERS = reverse("user-list")
ROLES = reverse("role-list")


def role_id_for(role_name):
    """FR-05's body carries the role's id, not its name (D-25)."""
    return str(Role.objects.get(role_name=role_name).pk)


# --- Enumerating the URL conf ---------------------------------------------------------------


def test_the_url_conf_is_exactly_the_contract():
    endpoints = enumerate_endpoints()
    assert {e.name for e in endpoints} == OPEN_ROUTES | PROTECTED_ROUTES
    assert set(PERMISSIONED_ROUTES) <= PROTECTED_ROUTES
    # Open and protected are read from each view's permission classes, so a route
    # that opts out of IsAuthenticated cannot pass as protected by being listed.
    assert {e.name for e in endpoints if not e.protected} == OPEN_ROUTES
    assert {e.name for e in endpoints if e.protected} == PROTECTED_ROUTES
    for endpoint in endpoints:
        if endpoint.name in OPEN_ROUTES:
            assert endpoint.permission_classes == (AllowAny,), endpoint
        else:
            assert endpoint.permission_classes[0] is IsAuthenticated, endpoint


def test_each_permissioned_route_checks_its_own_code():
    """The code each route's permission classes check is the one PERMISSIONED_ROUTES names, and
    every other protected route checks none, so a code cannot be dropped from or added to a route
    without this table changing with it."""
    for endpoint in enumerate_endpoints():
        codes = {
            permission.permission_name
            for permission in endpoint.permission_classes
            if isinstance(permission, type) and issubclass(permission, HasRolePermission)
        }
        expected = {PERMISSIONED_ROUTES[endpoint.name]} if endpoint.name in PERMISSIONED_ROUTES else set()
        assert codes == expected, endpoint


def test_every_endpoint_has_a_method_and_a_drf_view():
    for endpoint in enumerate_endpoints():
        assert endpoint.method != "?", f"{endpoint.path} is not a DRF view"


def _walk(client, expected_for):
    failures = []
    for endpoint in enumerate_endpoints():
        url = reverse(endpoint.name, kwargs=endpoint.reverse_kwargs)
        response = client.generic(endpoint.method, url, data="{}", content_type="application/json")
        expected = expected_for(endpoint.name)
        if response.status_code != expected:
            failures.append((endpoint.method, url, response.status_code, expected))
    assert not failures, failures


def test_every_route_but_the_two_opt_outs_is_401_anonymously(api_client):
    def expected(name):
        # The two opt-outs run their validation on the empty body: 400, not 401.
        return 400 if name in OPEN_ROUTES else 401

    _walk(api_client, expected)


def test_every_route_but_the_two_opt_outs_is_401_with_a_forged_session(api_client):
    api_client.cookies[settings.SESSION_COOKIE_NAME] = "forged-session-key"
    _walk(api_client, lambda name: 400 if name in OPEN_ROUTES else 401)


def test_every_protected_route_names_401_as_the_scheme(api_client):
    for endpoint in enumerate_endpoints():
        if not endpoint.protected:
            continue
        response = api_client.generic(endpoint.method, reverse(endpoint.name, kwargs=endpoint.reverse_kwargs))
        assert response["WWW-Authenticate"] == "Session", endpoint


# --- 401 versus 403 from both roles -----------------------------------------------------------


def test_expired_session_is_401_not_403_on_a_permissioned_route(session_client):
    # Expiry is checked before the role: an Administrator with a dead session is
    # anonymous, not "an Administrator who may proceed".
    client = session_client.client
    session_key = client.cookies[settings.SESSION_COOKIE_NAME].value
    Session.objects.filter(session_key=session_key).update(
        expire_date=timezone.now() - datetime.timedelta(seconds=1)
    )
    assert client.get(USERS).status_code == 401


def test_session_only_route_admits_both_roles(session_client):
    assert session_client.client.get(ROLES).status_code == 200


def test_permissioned_routes_are_403_for_an_employee_and_200_for_an_administrator(session_client, employee):
    expected = 200 if session_client.role_name == ADMINISTRATOR_ROLE_NAME else 403
    assert session_client.client.get(USERS).status_code == expected
    response = session_client.client.patch(
        reverse("user-role", kwargs={"pk": employee.pk}),
        {"role_id": role_id_for(EMPLOYEE_ROLE_NAME)},
        format="json",
    )
    assert response.status_code == expected


def test_403_names_the_missing_permission(employee_client):
    response = employee_client.get(USERS)
    assert response.status_code == 403
    assert response.json() == {
        "detail": f"Your role does not hold the '{MANAGE_ROLES_PERMISSION}' permission."
    }
    assert "WWW-Authenticate" not in response


def test_403_comes_before_404_so_nothing_is_disclosed(employee_client):
    response = employee_client.patch(
        reverse("user-role", kwargs={"pk": uuid.uuid4()}),
        {"role_id": role_id_for(EMPLOYEE_ROLE_NAME)},
        format="json",
    )
    assert response.status_code == 403


# --- A role change takes effect on the next request, without re-login ----------------------------


def login(user):
    client = APIClient()
    assert client.post(reverse("auth-login"), {"email": user.email, "password": PASSWORD}, format="json").status_code == 200
    return client


def test_promotion_takes_effect_on_the_next_request(employee, administrator_client):
    employee_session = login(employee)
    assert employee_session.get(USERS).status_code == 403

    response = administrator_client.patch(
        reverse("user-role", kwargs={"pk": employee.pk}),
        {"role_id": role_id_for(ADMINISTRATOR_ROLE_NAME)},
        format="json",
    )
    assert response.status_code == 200

    # Same cookie, no re-login.
    assert employee_session.get(USERS).status_code == 200
    assert employee_session.get(reverse("auth-me")).json()["role"] == ADMINISTRATOR_ROLE_NAME


def test_demotion_takes_effect_on_the_next_request(administrator, administrator_client, administrator_role):
    other = User.objects.create_user("second.admin@example.com", PASSWORD, name="Second", role=administrator_role)
    other_session = login(other)
    assert other_session.get(USERS).status_code == 200

    response = administrator_client.patch(
        reverse("user-role", kwargs={"pk": other.pk}),
        {"role_id": role_id_for(EMPLOYEE_ROLE_NAME)},
        format="json",
    )
    assert response.status_code == 200

    assert other_session.get(USERS).status_code == 403
    assert other_session.get(reverse("auth-me")).json()["role"] == EMPLOYEE_ROLE_NAME


def test_self_demotion_is_refused_so_the_administrator_keeps_their_access(administrator, administrator_client):
    """FR-05 forbids removing your own administrator role (D-25). This test used to
    pin the opposite: that the demotion succeeded and the administrator lost role
    management on the very next request, with no in-product way back, because
    permissions are held only against roles (D-14), there is no Django admin and
    manage_roles is the only permission."""
    response = administrator_client.patch(
        reverse("user-role", kwargs={"pk": administrator.pk}),
        {"role_id": role_id_for(EMPLOYEE_ROLE_NAME)},
        format="json",
    )
    assert response.status_code == 403
    assert administrator_client.get(USERS).status_code == 200


def test_the_session_stores_no_role_or_permission(session_client):
    session_key = session_client.client.cookies[settings.SESSION_COOKIE_NAME].value
    data = Session.objects.get(session_key=session_key).get_decoded()
    assert set(data) <= {"_auth_user_id", "_auth_user_backend", "_auth_user_hash"}


# --- Permissions are held against roles, never against users (D-14) ------------------------------


def test_revoking_the_permission_from_the_role_revokes_it_from_every_administrator(administrator_client, administrator_role):
    RolePermission.objects.filter(
        role=administrator_role, permission__permission_name=MANAGE_ROLES_PERMISSION
    ).delete()
    assert administrator_client.get(USERS).status_code == 403


def test_granting_the_permission_to_the_role_grants_it_to_every_employee(employee_client, employee_role):
    permission = Permission.objects.get(permission_name=MANAGE_ROLES_PERMISSION)
    RolePermission.objects.create(role=employee_role, permission=permission)
    assert employee_client.get(USERS).status_code == 200


def test_user_model_has_no_django_permission_machinery():
    assert PermissionsMixin not in User.__mro__
    assert not hasattr(User, "has_perm")
    assert not hasattr(User, "user_permissions")
    assert not hasattr(User, "groups")


# --- HasRolePermission itself -------------------------------------------------------------------


def _request_as(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


def test_for_code_builds_a_distinct_class_per_code():
    first = HasRolePermission.for_code("manage_roles")
    second = HasRolePermission.for_code("manage_documents")
    assert first is not second
    assert issubclass(first, HasRolePermission) and issubclass(second, HasRolePermission)
    assert first.permission_name == "manage_roles"
    assert second.permission_name == "manage_documents"
    assert "manage_documents" in second.message


def test_the_bare_class_refuses_to_guard_a_route(employee):
    with pytest.raises(ImproperlyConfigured):
        HasRolePermission().has_permission(_request_as(employee), view=None)


def test_permission_resolves_through_the_role(employee, administrator):
    check = HasRolePermission.for_code(MANAGE_ROLES_PERMISSION)()
    assert check.has_permission(_request_as(administrator), view=None) is True
    assert check.has_permission(_request_as(employee), view=None) is False


def test_an_unknown_code_is_held_by_nobody(employee, administrator):
    check = HasRolePermission.for_code("no_such_permission")()
    assert check.has_permission(_request_as(administrator), view=None) is False
    assert check.has_permission(_request_as(employee), view=None) is False


def test_an_anonymous_user_holds_nothing():
    from django.contrib.auth.models import AnonymousUser

    check = HasRolePermission.for_code(MANAGE_ROLES_PERMISSION)()
    assert check.has_permission(_request_as(AnonymousUser()), view=None) is False


def test_every_permission_code_in_use_is_seeded():
    # A route can only name a code that exists in the permissions table.
    seeded = set(Permission.objects.values_list("permission_name", flat=True))
    assert set(PERMISSIONED_ROUTES.values()) <= seeded
    assert IN_VIEW_PERMISSION_CODES <= seeded
    assert Role.objects.filter(role_name=ADMINISTRATOR_ROLE_NAME, permissions__permission_name=MANAGE_ROLES_PERMISSION).exists()
    assert Role.objects.filter(role_name=ADMINISTRATOR_ROLE_NAME, permissions__permission_name=MANAGE_DOCUMENTS_PERMISSION).exists()
    assert Role.objects.filter(role_name=ADMINISTRATOR_ROLE_NAME, permissions__permission_name=MANAGE_MEETINGS_PERMISSION).exists()
    assert Role.objects.filter(role_name=ADMINISTRATOR_ROLE_NAME, permissions__permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION).exists()
    assert not Role.objects.filter(role_name=EMPLOYEE_ROLE_NAME, permissions__permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION).exists()
    assert Role.objects.filter(role_name=ADMINISTRATOR_ROLE_NAME, permissions__permission_name=MANAGE_TAGS_PERMISSION).exists()
    assert not Role.objects.filter(role_name=EMPLOYEE_ROLE_NAME, permissions__permission_name=MANAGE_TAGS_PERMISSION).exists()
