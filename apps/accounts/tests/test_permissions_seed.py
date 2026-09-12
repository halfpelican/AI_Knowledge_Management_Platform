"""Accounts migration 0003: the seeded permissions and which role holds them.

FR-05 ("Administrator generalises Employee"), FR-06 and docs/decisions.md D-14.
"""

import importlib

import pytest
from django.apps import apps as registry

from apps.accounts.models import Permission, Role, RolePermission
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, MANAGE_ROLES_PERMISSION

pytestmark = pytest.mark.django_db

seed = importlib.import_module("apps.accounts.migrations.0003_seed_permissions")


def permission_names(role):
    return set(role.permissions.values_list("permission_name", flat=True))


def test_manage_roles_is_seeded_and_held_by_administrator_only(employee_role, administrator_role):
    assert Permission.objects.filter(permission_name=MANAGE_ROLES_PERMISSION).exists()
    assert permission_names(administrator_role) == {MANAGE_ROLES_PERMISSION}
    assert permission_names(employee_role) == set()


def test_administrator_generalises_employee(employee_role, administrator_role):
    # Whatever later seeds add, Administrator must never hold less than Employee.
    assert permission_names(administrator_role) >= permission_names(employee_role)


def test_seed_migration_uses_the_permission_constant():
    assert seed.MANAGE_ROLES == MANAGE_ROLES_PERMISSION
    assert set(seed.ROLE_PERMISSIONS) == {EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME}
    assert seed.ROLE_PERMISSIONS[ADMINISTRATOR_ROLE_NAME] == (MANAGE_ROLES_PERMISSION,)


def test_seed_is_idempotent():
    before = (Permission.objects.count(), RolePermission.objects.count())
    seed.seed_permissions(registry, None)
    assert (Permission.objects.count(), RolePermission.objects.count()) == before


def test_seed_is_reversible(administrator_role):
    seed.unseed_permissions(registry, None)
    assert not Permission.objects.filter(permission_name=MANAGE_ROLES_PERMISSION).exists()
    assert not RolePermission.objects.filter(role=administrator_role).exists()
    assert Role.objects.count() == 2  # the roles themselves are 0002's

    seed.seed_permissions(registry, None)
    assert permission_names(administrator_role) == {MANAGE_ROLES_PERMISSION}


def test_permissions_are_never_held_by_a_user():
    # D-14: no per-user permission column or table exists.
    user_model = registry.get_model("accounts", "User")
    field_names = {field.name for field in user_model._meta.get_fields()}
    assert "permissions" not in field_names
    assert "user_permissions" not in field_names
    assert "groups" not in field_names
