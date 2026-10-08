"""Accounts migration 0005: ``manage_documents``, held by Administrator only (D-73).

FR-15's Server-End validation: "the requesting user must hold manage_documents to delete". This
is the seed ``DELETE /api/documents/{id}`` reads, after resolving the document through the
caller's scope (``apps/api/tests/test_document_delete.py`` tests that route from both roles).
"""

import importlib

import pytest
from django.apps import apps as registry

from apps.accounts.models import Permission, Role, RolePermission
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    CONTRIBUTE_CONTENT_PERMISSION,
    EMPLOYEE_ROLE_NAME,
    MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_ROLES_PERMISSION,
)

pytestmark = pytest.mark.django_db

seed = importlib.import_module("apps.accounts.migrations.0005_seed_manage_documents")


def permission_names(role):
    return set(role.permissions.values_list("permission_name", flat=True))


def test_the_migration_uses_the_permission_constant():
    """The constant and the frozen migration name must agree, or the view would check a code
    nothing holds and refuse every delete, the Administrator's included."""
    assert seed.MANAGE_DOCUMENTS == MANAGE_DOCUMENTS_PERMISSION
    assert seed.ROLE_PERMISSIONS == {
        ADMINISTRATOR_ROLE_NAME: (MANAGE_DOCUMENTS_PERMISSION,),
        EMPLOYEE_ROLE_NAME: (),
    }


def test_manage_documents_is_held_by_administrator_only(employee_role, administrator_role):
    assert Permission.objects.filter(permission_name=MANAGE_DOCUMENTS_PERMISSION).exists()
    assert MANAGE_DOCUMENTS_PERMISSION in permission_names(administrator_role)
    assert MANAGE_DOCUMENTS_PERMISSION not in permission_names(employee_role)


def test_the_seeded_permissions_are_exactly_the_three_codes(employee_role, administrator_role):
    """Every seed so far, together: what each role holds after 0003, 0004 and 0005."""
    assert permission_names(administrator_role) == {
        MANAGE_ROLES_PERMISSION, CONTRIBUTE_CONTENT_PERMISSION, MANAGE_DOCUMENTS_PERMISSION,
    }
    assert permission_names(employee_role) == {CONTRIBUTE_CONTENT_PERMISSION}


def test_administrator_still_generalises_employee(employee_role, administrator_role):
    assert permission_names(administrator_role) >= permission_names(employee_role)


def test_seed_is_idempotent():
    before = (Permission.objects.count(), RolePermission.objects.count())
    seed.seed_permissions(registry, None)
    assert (Permission.objects.count(), RolePermission.objects.count()) == before


def test_seed_is_reversible(employee_role, administrator_role):
    seed.unseed_permissions(registry, None)
    assert not Permission.objects.filter(permission_name=MANAGE_DOCUMENTS_PERMISSION).exists()
    # The rows cascade with the permission (D-12).
    assert not RolePermission.objects.filter(
        permission__permission_name=MANAGE_DOCUMENTS_PERMISSION
    ).exists()
    # 0003's and 0004's seeds are untouched: unseeding one migration must not undo another.
    assert permission_names(administrator_role) == {MANAGE_ROLES_PERMISSION, CONTRIBUTE_CONTENT_PERMISSION}
    assert permission_names(employee_role) == {CONTRIBUTE_CONTENT_PERMISSION}
    assert Role.objects.count() == 2  # the roles themselves are 0002's

    seed.seed_permissions(registry, None)
    assert MANAGE_DOCUMENTS_PERMISSION in permission_names(administrator_role)
    assert MANAGE_DOCUMENTS_PERMISSION not in permission_names(employee_role)
