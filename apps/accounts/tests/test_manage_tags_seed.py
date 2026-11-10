"""Accounts migration 0008: ``manage_tags``, held by Administrator only (D-105's dated note of 10
November 2026, night; D-119 finding 5).

FR-10's taxonomy clause, "Tags are deactivated rather than deleted where content still references
them", and its CRUD line, Tags "Delete", are performed by ``GET /api/tags`` and
``DELETE /api/tags/{id}``, and both check this code before anything else
(``apps/api/tests/test_fr10_tag_administration.py`` tests both from both roles). Seeded the way 0007
seeds ``review_knowledge_gaps`` (D-99's pattern).

The reversal is tested two ways, as 0007's is: through the migration's own functions, and through
the migration executor, migrating ``accounts`` back to 0007 and forward again.
"""

import importlib

import pytest
from django.apps import apps as registry
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.accounts.models import Permission, Role, RolePermission
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    CONTRIBUTE_CONTENT_PERMISSION,
    EFFECTIVE_ROLES,
    EMPLOYEE_ROLE_NAME,
    MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION,
    MANAGE_ROLES_PERMISSION,
    MANAGE_TAGS_PERMISSION,
    REVIEW_KNOWLEDGE_GAPS_PERMISSION,
)

pytestmark = pytest.mark.django_db

seed = importlib.import_module("apps.accounts.migrations.0008_seed_manage_tags")

THIS_MIGRATION = ("accounts", "0008_seed_manage_tags")
PREVIOUS_MIGRATION = ("accounts", "0007_seed_review_knowledge_gaps")
EARLIER_ADMINISTRATOR_CODES = {
    MANAGE_ROLES_PERMISSION, CONTRIBUTE_CONTENT_PERMISSION, MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION, REVIEW_KNOWLEDGE_GAPS_PERMISSION,
}


def permission_names(role):
    return set(role.permissions.values_list("permission_name", flat=True))


def test_the_migration_uses_the_permission_constant():
    """The constant and the frozen migration name must agree, or both tag routes would check a code
    nothing holds and refuse the Administrator too."""
    assert seed.MANAGE_TAGS == MANAGE_TAGS_PERMISSION
    assert seed.ROLE_PERMISSIONS == {
        ADMINISTRATOR_ROLE_NAME: (MANAGE_TAGS_PERMISSION,),
        EMPLOYEE_ROLE_NAME: (),
    }


def test_manage_tags_is_held_by_administrator_only(employee_role, administrator_role):
    assert Permission.objects.filter(permission_name=MANAGE_TAGS_PERMISSION).exists()
    assert MANAGE_TAGS_PERMISSION in permission_names(administrator_role)
    assert MANAGE_TAGS_PERMISSION not in permission_names(employee_role)
    holders = set(
        Role.objects.filter(permissions__permission_name=MANAGE_TAGS_PERMISSION)
        .values_list("role_name", flat=True)
    )
    assert holders == {ADMINISTRATOR_ROLE_NAME}


def test_administrator_still_generalises_employee(employee_role, administrator_role):
    assert permission_names(administrator_role) >= permission_names(employee_role)


def test_seed_is_idempotent():
    before = (Permission.objects.count(), RolePermission.objects.count())
    seed.seed_permissions(registry, None)
    assert (Permission.objects.count(), RolePermission.objects.count()) == before


def test_seed_is_reversible(employee_role, administrator_role):
    seed.unseed_permissions(registry, None)
    assert not Permission.objects.filter(permission_name=MANAGE_TAGS_PERMISSION).exists()
    # The rows cascade with the permission (D-12).
    assert not RolePermission.objects.filter(permission__permission_name=MANAGE_TAGS_PERMISSION).exists()
    # 0003's to 0007's seeds are untouched: unseeding one migration must not undo another.
    assert permission_names(administrator_role) == EARLIER_ADMINISTRATOR_CODES
    assert permission_names(employee_role) == {CONTRIBUTE_CONTENT_PERMISSION}
    assert Role.objects.count() == 2  # the roles themselves are 0002's

    seed.seed_permissions(registry, None)
    assert MANAGE_TAGS_PERMISSION in permission_names(administrator_role)
    assert MANAGE_TAGS_PERMISSION not in permission_names(employee_role)


def migrate_accounts_to(node):
    """Move accounts to ``node`` and leave every other app at its leaf (as 0007's test does)."""
    executor = MigrationExecutor(connection)
    targets = [leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "accounts"] + [node]
    executor.migrate(targets)


def test_the_migration_reverses_through_the_executor(employee_role, administrator_role):
    """Migrating ``accounts`` back to 0007 runs ``unseed_permissions`` as Django would, and forward
    again restores the seed. This also proves 0008 is the leaf of ``accounts``."""
    leaves = [
        key for key in MigrationExecutor(connection).loader.graph.leaf_nodes() if key[0] == "accounts"
    ]
    assert leaves == [THIS_MIGRATION]

    migrate_accounts_to(PREVIOUS_MIGRATION)
    assert not Permission.objects.filter(permission_name=MANAGE_TAGS_PERMISSION).exists()
    assert permission_names(administrator_role) == EARLIER_ADMINISTRATOR_CODES

    migrate_accounts_to(THIS_MIGRATION)
    assert MANAGE_TAGS_PERMISSION in permission_names(administrator_role)
    assert MANAGE_TAGS_PERMISSION not in permission_names(employee_role)


def test_every_role_holding_the_code_has_the_administrators_scope():
    """The inventory lists every tag and counts every source without a scope, and the argument that
    this discloses nothing is that its reader already reads every source (D-66), as the security
    review's L3 argued for FR-19's log. A role given ``manage_tags`` with a narrower scope would
    read tag names carried only by material it may not see, and counts of that material. So every
    role holding the code must have the Administrator's effective roles."""
    holders = set(
        RolePermission.objects.filter(permission__permission_name=MANAGE_TAGS_PERMISSION)
        .values_list("role__role_name", flat=True)
    )
    assert holders, "the code must be held by some role, or the inventory has no reader"
    full_scope = set(EFFECTIVE_ROLES[ADMINISTRATOR_ROLE_NAME])
    for role_name in holders:
        assert full_scope <= set(EFFECTIVE_ROLES.get(role_name, ())), role_name
