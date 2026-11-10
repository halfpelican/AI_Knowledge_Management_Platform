"""FR-05 role management: GET /api/roles, GET /api/users, PATCH /api/users/{id}/role
(docs/api-contract.md, Stage 2), with the audit entry every role change writes.

Every protected route is exercised anonymously (401), from an Employee session and
from an Administrator session (CLAUDE.md section 8 item 2).

FR-05 Server-End: the body is the role's id, not its name ("Receives { user_id,
new_role_id }"), an id naming no row is 404 ("404 Not Found if user/role doesn't
exist"), and "a user cannot remove their own administrator role". All three were
the other way before the proposal arrived; see D-25.
"""

import json
import logging
import uuid

from datetime import timedelta

import pytest
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.api.views import LAST_ADMINISTRATOR_MESSAGE, SELF_DEMOTION_MESSAGE
from apps.accounts.models import Permission, Role, RolePermission
from apps.accounts.audit import AUDIT_LOGGER_NAME, ROLE_CHANGED
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    CONTRIBUTE_CONTENT_PERMISSION,
    MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION,
    MANAGE_ROLES_PERMISSION,
    MANAGE_TAGS_PERMISSION,
    REVIEW_KNOWLEDGE_GAPS_PERMISSION,
    ROLE_NAMES,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

ROLES = reverse("role-list")
USERS = reverse("user-list")
USER_OBJECT_KEYS = {"id", "name", "email", "role", "created_at"}
SECRET_COLUMNS = {"password", "password_hash", "failed_attempts", "locked_until", "last_login"}


def role_url(user_or_id):
    pk = getattr(user_or_id, "pk", user_or_id)
    return reverse("user-role", kwargs={"pk": pk})


def role_id_for(role_name):
    from apps.accounts.models import Role

    return str(Role.objects.get(role_name=role_name).pk)


def change_role(client, target, role_name):
    """FR-05's body: the role's id, which the client reads from GET /api/roles."""
    return client.patch(role_url(target), {"role_id": role_id_for(role_name)}, format="json")


# --- GET /api/roles ---------------------------------------------------------------------


def test_roles_is_401_anonymously(api_client):
    assert api_client.get(ROLES).status_code == 401


def test_roles_lists_both_roles_with_their_permissions(session_client):
    response = session_client.client.get(ROLES)
    assert response.status_code == 200
    body = response.json()
    assert [role["name"] for role in body] == list(ROLE_NAMES)
    assert all(set(role) == {"role_id", "name", "description", "permissions"} for role in body)
    assert all(role["description"] for role in body)
    by_name = {role["name"]: role for role in body}
    # Both roles contribute content (D-30); manage_roles, manage_documents (accounts 0005,
    # D-73), manage_meetings (accounts 0006, D-99), review_knowledge_gaps (accounts 0007,
    # D-107) and manage_tags (accounts 0008, D-119 finding 5) are Administrator's alone. Listed by
    # name.
    assert by_name[EMPLOYEE_ROLE_NAME]["permissions"] == [CONTRIBUTE_CONTENT_PERMISSION]
    assert by_name[ADMINISTRATOR_ROLE_NAME]["permissions"] == [
        CONTRIBUTE_CONTENT_PERMISSION,
        MANAGE_DOCUMENTS_PERMISSION,
        MANAGE_MEETINGS_PERMISSION,
        MANAGE_ROLES_PERMISSION,
        MANAGE_TAGS_PERMISSION,
        REVIEW_KNOWLEDGE_GAPS_PERMISSION,
    ]


def test_roles_carries_the_role_id_the_role_change_needs(session_client):
    """FR-05's body is { new_role_id }, so the client has to be able to learn the
    id; GET /api/roles is where it reads it. Each id is the row's own primary key."""
    from apps.accounts.models import Role

    body = session_client.client.get(ROLES).json()
    ids = {role["name"]: role["role_id"] for role in body}
    assert ids == {role.role_name: str(role.pk) for role in Role.objects.all()}
    assert all(uuid.UUID(value) for value in ids.values())


def test_the_role_id_from_the_listing_drives_the_role_change(administrator_client, employee):
    """The client's whole round trip: read the roles, take the id, send it."""
    listing = administrator_client.get(ROLES).json()
    administrator_role_id = next(
        role["role_id"] for role in listing if role["name"] == ADMINISTRATOR_ROLE_NAME
    )

    response = administrator_client.patch(
        role_url(employee), {"role_id": administrator_role_id}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["role"] == ADMINISTRATOR_ROLE_NAME


# --- GET /api/users -----------------------------------------------------------------------


def test_users_is_401_anonymously(api_client):
    assert api_client.get(USERS).status_code == 401


def test_users_is_403_for_an_employee(employee_client):
    response = employee_client.get(USERS)
    assert response.status_code == 403
    assert list(response.json()) == ["detail"]


def test_users_lists_every_user_for_an_administrator(administrator_client, employee, administrator):
    response = administrator_client.get(USERS)
    assert response.status_code == 200
    body = response.json()
    assert {user["id"] for user in body} == {str(employee.id), str(administrator.id)}
    assert all(set(user) == USER_OBJECT_KEYS for user in body)
    assert all(SECRET_COLUMNS.isdisjoint(user) for user in body)


def test_users_are_ordered_by_created_at(administrator_client, employee):
    later = User.objects.create_user("zed@example.com", PASSWORD, name="Zed")
    # The view orders by (created_at, pk), and the pk is a random UUID, so two users
    # sharing a created_at come back in an arbitrary order. Three users registered
    # inside one test can share one: the ordering this test is about is the
    # timestamp, not the resolution of the system clock or the tiebreak behind it.
    # Backdating the others makes `later` unambiguously last.
    User.objects.exclude(pk=later.pk).update(created_at=timezone.now() - timedelta(minutes=1))

    body = administrator_client.get(USERS).json()

    created = [user["created_at"] for user in body]
    assert created == sorted(created)
    assert body[-1]["id"] == str(later.id)


# --- PATCH /api/users/{id}/role ---------------------------------------------------------------


def test_role_change_is_401_anonymously(api_client, employee):
    assert change_role(api_client, employee, ADMINISTRATOR_ROLE_NAME).status_code == 401


def test_role_change_is_403_for_an_employee(employee_client, employee, administrator):
    response = change_role(employee_client, employee, ADMINISTRATOR_ROLE_NAME)
    assert response.status_code == 403
    employee.refresh_from_db()
    assert employee.role.role_name == EMPLOYEE_ROLE_NAME
    # Nor can an Employee demote an Administrator.
    assert change_role(employee_client, administrator, EMPLOYEE_ROLE_NAME).status_code == 403
    administrator.refresh_from_db()
    assert administrator.role.role_name == ADMINISTRATOR_ROLE_NAME


def test_administrator_promotes_an_employee(administrator_client, employee):
    response = change_role(administrator_client, employee, ADMINISTRATOR_ROLE_NAME)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == USER_OBJECT_KEYS
    assert body["id"] == str(employee.id)
    assert body["role"] == ADMINISTRATOR_ROLE_NAME
    employee.refresh_from_db()
    assert employee.role.role_name == ADMINISTRATOR_ROLE_NAME


def test_administrator_demotes_an_administrator(administrator_client, administrator_role):
    other = User.objects.create_user("other@example.com", PASSWORD, name="Other", role=administrator_role)
    response = change_role(administrator_client, other, EMPLOYEE_ROLE_NAME)
    assert response.status_code == 200
    assert response.json()["role"] == EMPLOYEE_ROLE_NAME


# --- FR-05: "a user cannot remove their own administrator role" (D-25) --------------


def test_an_administrator_cannot_demote_themselves(administrator_client, administrator):
    """FR-05 Validation: "a user cannot remove their own administrator role,
    preventing accidental lockout of the last administrator." 403 is a convention:
    FR-05 enumerates only 200, 403 and 404, and this is an authorised requester
    being refused an action. This was permitted before the proposal arrived."""
    response = change_role(administrator_client, administrator, EMPLOYEE_ROLE_NAME)

    assert response.status_code == 403
    assert response.json() == {"detail": "You cannot remove your own Administrator role."}
    administrator.refresh_from_db()
    assert administrator.role.role_name == ADMINISTRATOR_ROLE_NAME


def test_the_refusal_leaves_the_administrator_able_to_manage_roles(administrator_client, administrator):
    # The point of the clause: the system is never left with no way back in.
    change_role(administrator_client, administrator, EMPLOYEE_ROLE_NAME)
    assert administrator_client.get(USERS).status_code == 200


def test_a_refused_self_demotion_writes_no_audit_entry(administrator_client, administrator, caplog):
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
    change_role(administrator_client, administrator, EMPLOYEE_ROLE_NAME)
    assert not [record for record in caplog.records if record.name == AUDIT_LOGGER_NAME]


def test_an_administrator_may_set_their_own_role_to_administrator(administrator_client, administrator):
    # A no-op is not a demotion; only removing the role is refused.
    response = change_role(administrator_client, administrator, ADMINISTRATOR_ROLE_NAME)
    assert response.status_code == 200
    assert response.json()["role"] == ADMINISTRATOR_ROLE_NAME


def test_the_refusal_does_not_stop_an_administrator_demoting_someone_else(
    administrator_client, administrator, administrator_role
):
    other = User.objects.create_user(
        "other.admin@example.com", PASSWORD, name="Other", role=administrator_role
    )
    assert change_role(administrator_client, other, EMPLOYEE_ROLE_NAME).status_code == 200
    # And the refusal is about the requester, not about the Administrator role as
    # such: the same administrator still cannot demote themselves.
    assert change_role(administrator_client, administrator, EMPLOYEE_ROLE_NAME).status_code == 403


def test_a_second_administrator_may_demote_the_first(administrator, administrator_role):
    """The clause protects against demoting *yourself*, not against the role being
    removed at all, so two administrators can still each be demoted by the other."""
    second = User.objects.create_user(
        "second.admin@example.com", PASSWORD, name="Second", role=administrator_role
    )
    client = APIClient()
    client.force_login(second)

    assert change_role(client, administrator, EMPLOYEE_ROLE_NAME).status_code == 200
    administrator.refresh_from_db()
    assert administrator.role.role_name == EMPLOYEE_ROLE_NAME


def test_setting_the_same_role_is_200(administrator_client, employee):
    response = change_role(administrator_client, employee, EMPLOYEE_ROLE_NAME)
    assert response.status_code == 200
    assert response.json()["role"] == EMPLOYEE_ROLE_NAME


def test_an_unknown_role_id_is_404(administrator_client, employee):
    """FR-05 Responses: "404 Not Found if user/role doesn't exist". A well-formed id
    that names no row is a missing role, not a malformed body; this was 400 before
    the proposal arrived (D-25)."""
    response = administrator_client.patch(
        role_url(employee), {"role_id": str(uuid.uuid4())}, format="json"
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "No role with that role_id exists."}
    employee.refresh_from_db()
    assert employee.role.role_name == EMPLOYEE_ROLE_NAME


@pytest.mark.parametrize(
    "body",
    [
        {},  # missing
        {"role_id": "Administrator"},  # the role's name, which is no longer the key
        {"role_id": "not-a-uuid"},
        {"role_id": ""},
        {"role_id": None},
        {"role": "Administrator"},  # the old body shape
    ],
)
def test_a_malformed_body_is_400(administrator_client, employee, body):
    # A missing or non-UUID role_id is a malformed body, which stays 400.
    response = administrator_client.patch(role_url(employee), body, format="json")
    assert response.status_code == 400
    assert list(response.json()) == ["role_id"]
    employee.refresh_from_db()
    assert employee.role.role_name == EMPLOYEE_ROLE_NAME


def test_unknown_user_is_404(administrator_client):
    response = change_role(administrator_client, uuid.uuid4(), ADMINISTRATOR_ROLE_NAME)
    assert response.status_code == 404
    assert list(response.json()) == ["detail"]


def test_a_malformed_body_is_400_before_the_user_is_looked_up(administrator_client):
    # Both halves are wrong; the body is answered first, as DRF validates it first.
    response = administrator_client.patch(role_url(uuid.uuid4()), {}, format="json")
    assert response.status_code == 400


def test_a_path_that_is_not_a_uuid_is_a_json_404(administrator_client):
    response = administrator_client.patch(
        "/api/users/not-a-uuid/role", {"role_id": role_id_for(EMPLOYEE_ROLE_NAME)}, format="json"
    )
    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == {"detail": "Not found."}


def test_role_change_only_accepts_patch(administrator_client, employee):
    assert administrator_client.get(role_url(employee)).status_code == 405
    assert administrator_client.post(
        role_url(employee), {"role_id": role_id_for(EMPLOYEE_ROLE_NAME)}, format="json"
    ).status_code == 405


# --- Audit entry (FR-05) ------------------------------------------------------------------------


def test_role_change_writes_an_audit_entry(administrator_client, administrator, employee, caplog):
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)

    change_role(administrator_client, employee, ADMINISTRATOR_ROLE_NAME)

    records = [record for record in caplog.records if record.name == AUDIT_LOGGER_NAME]
    assert len(records) == 1
    entry = json.loads(records[0].getMessage())
    assert entry["event"] == ROLE_CHANGED
    assert entry["actor_id"] == str(administrator.id)
    assert entry["actor_email"] == administrator.email
    assert entry["target_id"] == str(employee.id)
    assert entry["target_email"] == employee.email
    assert entry["old_role"] == EMPLOYEE_ROLE_NAME
    assert entry["new_role"] == ADMINISTRATOR_ROLE_NAME
    assert entry["timestamp"]


def test_a_refused_role_change_writes_no_audit_entry(employee_client, employee, caplog):
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
    change_role(employee_client, employee, ADMINISTRATOR_ROLE_NAME)
    assert not [record for record in caplog.records if record.name == AUDIT_LOGGER_NAME]


def test_audit_entries_are_json_lines_in_the_audit_file(audit_file, administrator_client, employee):
    # audit_file (conftest.py) is AUDIT_LOG_PATH overridden to a temporary path.
    change_role(administrator_client, employee, ADMINISTRATOR_ROLE_NAME)
    change_role(administrator_client, employee, EMPLOYEE_ROLE_NAME)

    lines = audit_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert (first["old_role"], first["new_role"]) == (EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME)
    assert (second["old_role"], second["new_role"]) == (ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME)


def test_audit_log_path_is_configured_from_settings():
    handler = django_settings.LOGGING["handlers"]["audit_file"]
    assert handler["filename"] == str(django_settings.AUDIT_LOG_PATH)
    assert django_settings.LOGGING["loggers"][AUDIT_LOGGER_NAME]["handlers"] == ["audit_file"]


def test_a_role_change_without_the_csrf_header_is_refused(employee, administrator):
    """The contract requires X-CSRFToken on every unsafe method. Logout has covered
    this since FR-04; the role change is the other unsafe route and carries the
    privilege, so it is worth its own test rather than an argument from symmetry."""
    client = APIClient(enforce_csrf_checks=True)
    assert client.post(
        reverse("auth-login"), {"email": administrator.email, "password": PASSWORD}, format="json"
    ).status_code == 200
    url = role_url(employee)

    body = {"role_id": role_id_for(ADMINISTRATOR_ROLE_NAME)}

    refused = client.patch(url, body, format="json")

    assert refused.status_code == 403
    employee.refresh_from_db()
    assert employee.role.role_name == EMPLOYEE_ROLE_NAME

    header = {"HTTP_X_CSRFTOKEN": client.cookies[django_settings.CSRF_COOKIE_NAME].value}
    accepted = client.patch(url, body, format="json", **header)
    assert accepted.status_code == 200


# --- The administrator set can never be emptied (FR-05, D-26) ---------------------------------


def test_the_last_administrator_cannot_be_demoted_by_anyone(administrator_client, administrator):
    """FR-05's clause is worded as a self-demotion rule, but its stated purpose is
    "preventing accidental lockout of the last administrator". A sole administrator
    is the last one whoever asks, so the refusal is about the set, not the requester."""
    second = User.objects.create_user(
        "second-admin@example.com", PASSWORD, name="Second Admin", role=Role.objects.get(
            role_name=ADMINISTRATOR_ROLE_NAME
        )
    )
    employee_role = Role.objects.get(role_name=EMPLOYEE_ROLE_NAME)

    # Two administrators exist, so demoting one is allowed.
    assert change_role(administrator_client, second, EMPLOYEE_ROLE_NAME).status_code == 200

    # The requester is now the only administrator left; it may not be emptied.
    second.refresh_from_db()
    assert second.role == employee_role
    refused = change_role(administrator_client, administrator, EMPLOYEE_ROLE_NAME)
    assert refused.status_code == 403
    # The self-demotion guard is checked first, so this is the branch that answers.
    # The set-level branch is reached by the test below, where requester != target.
    assert refused.json() == {"detail": SELF_DEMOTION_MESSAGE}
    administrator.refresh_from_db()
    assert administrator.role.role_name == ADMINISTRATOR_ROLE_NAME


def test_two_administrators_cannot_race_each_other_to_zero(administrator):
    """Reproduces the concurrency hole the security review found: A demotes B while
    B demotes A. Neither is a self-demotion and the two lock different target rows,
    so a self-only guard let both commit and left no administrator at all, with
    manage_roles held by that role alone and no way back through the product.

    Serialised rather than threaded, so what this asserts is the outcome, not the
    locking: once A has demoted B, B can no longer act at all. Under true concurrency
    both requests pass the permission check while both are still administrators and
    the second blocks on the row lock over the administrator set, then re-reads and
    is refused by the set-level branch — which the test below reaches directly.
    """
    administrator_role = Role.objects.get(role_name=ADMINISTRATOR_ROLE_NAME)
    other = User.objects.create_user(
        "other-admin@example.com", PASSWORD, name="Other Admin", role=administrator_role
    )
    a_client, b_client = APIClient(), APIClient()
    a_client.force_login(administrator)
    b_client.force_login(other)

    first = change_role(a_client, other, EMPLOYEE_ROLE_NAME)
    second = change_role(b_client, administrator, EMPLOYEE_ROLE_NAME)

    assert first.status_code == 200
    assert second.status_code == 403  # would have been 200, leaving zero administrators
    assert User.objects.filter(role__role_name=ADMINISTRATOR_ROLE_NAME).count() == 1


def test_a_permitted_non_administrator_cannot_empty_the_administrator_set(
    administrator, employee, employee_client
):
    """The branch the self-demotion guard cannot reach.

    Its condition is requester != target, so the requester must hold manage_roles
    without being an Administrator. Permissions are held against roles (D-14), which
    makes that reachable by granting the permission to Employee. Without the
    set-level check this request would leave the organisation with no administrator
    and no way to appoint one, because manage_roles is normally held by that role
    alone.
    """
    RolePermission.objects.create(
        role=Role.objects.get(role_name=EMPLOYEE_ROLE_NAME),
        permission=Permission.objects.get(permission_name=MANAGE_ROLES_PERMISSION),
    )

    response = change_role(employee_client, administrator, EMPLOYEE_ROLE_NAME)

    assert response.status_code == 403
    assert response.json() == {"detail": LAST_ADMINISTRATOR_MESSAGE}
    administrator.refresh_from_db()
    assert administrator.role.role_name == ADMINISTRATOR_ROLE_NAME
    assert User.objects.filter(role__role_name=ADMINISTRATOR_ROLE_NAME).count() == 1
