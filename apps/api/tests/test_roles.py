"""FR-05 role management: GET /api/roles, GET /api/users, PATCH /api/users/{id}/role
(docs/api-contract.md, Stage 2), with the audit entry every role change writes.

Every protected route is exercised anonymously (401), from an Employee session and
from an Administrator session (CLAUDE.md section 8 item 2).
"""

import json
import logging
import uuid

import pytest
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.audit import AUDIT_LOGGER_NAME, ROLE_CHANGED
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MANAGE_ROLES_PERMISSION,
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


def change_role(client, target, role_name):
    return client.patch(role_url(target), {"role": role_name}, format="json")


# --- GET /api/roles ---------------------------------------------------------------------


def test_roles_is_401_anonymously(api_client):
    assert api_client.get(ROLES).status_code == 401


def test_roles_lists_both_roles_with_their_permissions(session_client):
    response = session_client.client.get(ROLES)
    assert response.status_code == 200
    body = response.json()
    assert [role["name"] for role in body] == list(ROLE_NAMES)
    assert all(set(role) == {"name", "description", "permissions"} for role in body)
    assert all(role["description"] for role in body)
    by_name = {role["name"]: role for role in body}
    assert by_name[EMPLOYEE_ROLE_NAME]["permissions"] == []
    assert by_name[ADMINISTRATOR_ROLE_NAME]["permissions"] == [MANAGE_ROLES_PERMISSION]


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


def test_administrator_may_change_their_own_role(administrator_client, administrator):
    # Nothing in the proposal or the contract forbids it; recorded in the report.
    response = change_role(administrator_client, administrator, EMPLOYEE_ROLE_NAME)
    assert response.status_code == 200
    administrator.refresh_from_db()
    assert administrator.role.role_name == EMPLOYEE_ROLE_NAME


def test_setting_the_same_role_is_200(administrator_client, employee):
    response = change_role(administrator_client, employee, EMPLOYEE_ROLE_NAME)
    assert response.status_code == 200
    assert response.json()["role"] == EMPLOYEE_ROLE_NAME


def test_unknown_role_name_is_400(administrator_client, employee):
    response = change_role(administrator_client, employee, "Contractor")
    assert response.status_code == 400
    assert list(response.json()) == ["role"]
    employee.refresh_from_db()
    assert employee.role.role_name == EMPLOYEE_ROLE_NAME


def test_missing_role_is_400(administrator_client, employee):
    response = administrator_client.patch(role_url(employee), {}, format="json")
    assert response.status_code == 400
    assert list(response.json()) == ["role"]


def test_unknown_user_is_404(administrator_client):
    response = change_role(administrator_client, uuid.uuid4(), ADMINISTRATOR_ROLE_NAME)
    assert response.status_code == 404
    assert list(response.json()) == ["detail"]


def test_a_path_that_is_not_a_uuid_is_a_json_404(administrator_client):
    response = administrator_client.patch("/api/users/not-a-uuid/role", {"role": "Employee"}, format="json")
    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == {"detail": "Not found."}


def test_role_change_only_accepts_patch(administrator_client, employee):
    assert administrator_client.get(role_url(employee)).status_code == 405
    assert administrator_client.post(role_url(employee), {"role": "Employee"}, format="json").status_code == 405


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

    refused = client.patch(url, {"role": ADMINISTRATOR_ROLE_NAME}, format="json")

    assert refused.status_code == 403
    employee.refresh_from_db()
    assert employee.role.role_name == EMPLOYEE_ROLE_NAME

    header = {"HTTP_X_CSRFTOKEN": client.cookies[django_settings.CSRF_COOKIE_NAME].value}
    accepted = client.patch(url, {"role": ADMINISTRATOR_ROLE_NAME}, format="json", **header)
    assert accepted.status_code == 200
