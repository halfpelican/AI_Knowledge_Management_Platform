"""Accounts migration 0004: ``contribute_content``, held by both roles (D-30).

FR-08's section 7.2 ``validateUpload()`` opens with a contribute-permission check
returning 403, before the signature, size and title checks. This is the seed that
gives that check something to read.

That both roles hold it is the point worth being plain about: in the shipped seed the
permission refuses nobody. It is the enforcement point the clause requires, not a
restriction that does anything, and the test that proves the gate works is in
``apps/api/tests/test_document_upload.py``, which takes the permission away from a
role and asserts the 403.
"""

import importlib

import pytest
from django.apps import apps as registry

from apps.accounts.models import Permission, RolePermission
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    CONTRIBUTE_CONTENT_PERMISSION,
    EMPLOYEE_ROLE_NAME,
)

pytestmark = pytest.mark.django_db

seed = importlib.import_module("apps.accounts.migrations.0004_seed_contribute_content")


def permission_names(role):
    return set(role.permissions.values_list("permission_name", flat=True))


def test_the_migration_uses_the_permission_constant():
    """The constant and the frozen migration name must agree, or the view would
    check a code nothing holds and refuse every upload."""
    assert seed.CONTRIBUTE_CONTENT == CONTRIBUTE_CONTENT_PERMISSION
    assert set(seed.ROLE_PERMISSIONS) == {EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME}


def test_both_roles_may_contribute_content(employee_role, administrator_role):
    assert Permission.objects.filter(permission_name=CONTRIBUTE_CONTENT_PERMISSION).exists()
    assert CONTRIBUTE_CONTENT_PERMISSION in permission_names(employee_role)
    assert CONTRIBUTE_CONTENT_PERMISSION in permission_names(administrator_role)


def test_administrator_still_generalises_employee(employee_role, administrator_role):
    # FR-05's "Administrator generalises Employee": whatever a seed adds,
    # Administrator must never hold less than Employee.
    assert permission_names(administrator_role) >= permission_names(employee_role)


def test_seed_is_idempotent():
    before = (Permission.objects.count(), RolePermission.objects.count())
    seed.seed_permissions(registry, None)
    assert (Permission.objects.count(), RolePermission.objects.count()) == before


def test_seed_is_reversible(employee_role, administrator_role):
    seed.unseed_permissions(registry, None)
    assert not Permission.objects.filter(permission_name=CONTRIBUTE_CONTENT_PERMISSION).exists()
    # The rows cascade with the permission (D-12), for both roles.
    assert not RolePermission.objects.filter(
        permission__permission_name=CONTRIBUTE_CONTENT_PERMISSION
    ).exists()
    # 0003's seed is untouched: unseeding one migration must not undo another.
    assert permission_names(administrator_role)

    seed.seed_permissions(registry, None)
    assert CONTRIBUTE_CONTENT_PERMISSION in permission_names(employee_role)
