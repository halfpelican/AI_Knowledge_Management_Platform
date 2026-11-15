"""Accounts migration 0011: ``view_knowledge_map``, held by both roles (D-132).

FR-20's knowledge map, ``GET /api/knowledge-map``, checks this code before anything else on the
request. The proposal names no permission for FR-20; the lead decided on 14 November 2026 that
the route sits behind a code of its own, held by Employee and Administrator. Seeded the way 0004
seeds ``contribute_content`` (D-30): both roles hold it, so in the shipped seed it refuses nobody,
and the test that proves the gate works takes it away from a role and asserts the 403
(``apps/api/tests/test_knowledge_map.py``, from both roles).

The reversal is tested two ways, as 0006's to 0008's are: through the migration's own functions,
and through the migration executor, migrating ``accounts`` back to 0010 and forward again.

**The number and the dependency.** 0009 and 0010 are FR-03's (D-130). This migration was written
while they were on FR-03's branch, and depended on 0008 as 0009 did. FR-03 reached ``main`` first,
so the dependency was re-pointed to 0010 in the merge of 15 November 2026, before this migration
had been pushed or applied anywhere (D-132's dated note). ``accounts`` has one leaf, 0011, and the
executor test below says so.
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
    EMPLOYEE_ROLE_NAME,
    MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION,
    MANAGE_ROLES_PERMISSION,
    MANAGE_TAGS_PERMISSION,
    RELEASE_ACCOUNT_LOCKS_PERMISSION,
    REVIEW_KNOWLEDGE_GAPS_PERMISSION,
    VIEW_KNOWLEDGE_MAP_PERMISSION,
)

pytestmark = pytest.mark.django_db

seed = importlib.import_module("apps.accounts.migrations.0011_seed_view_knowledge_map")

THIS_MIGRATION = ("accounts", "0011_seed_view_knowledge_map")
PREVIOUS_MIGRATION = ("accounts", "0010_seed_release_account_locks")
EARLIER_ADMINISTRATOR_CODES = {
    MANAGE_ROLES_PERMISSION, CONTRIBUTE_CONTENT_PERMISSION, MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION, REVIEW_KNOWLEDGE_GAPS_PERMISSION, MANAGE_TAGS_PERMISSION,
    RELEASE_ACCOUNT_LOCKS_PERMISSION,
}
EARLIER_EMPLOYEE_CODES = {CONTRIBUTE_CONTENT_PERMISSION}


def permission_names(role):
    return set(role.permissions.values_list("permission_name", flat=True))


def test_the_migration_uses_the_permission_constant():
    """The constant and the frozen migration name must agree, or the route would check a code
    nothing holds and refuse everybody."""
    assert seed.VIEW_KNOWLEDGE_MAP == VIEW_KNOWLEDGE_MAP_PERMISSION
    assert seed.ROLE_PERMISSIONS == {
        ADMINISTRATOR_ROLE_NAME: (VIEW_KNOWLEDGE_MAP_PERMISSION,),
        EMPLOYEE_ROLE_NAME: (VIEW_KNOWLEDGE_MAP_PERMISSION,),
    }


def test_the_migration_depends_on_0010_and_nothing_else():
    """It builds on the last accounts migration ``main`` holds, FR-03's 0010 (D-130). A dependency
    on 0008, which it had before the merge of 15 November 2026, would give ``accounts`` two leaves."""
    assert seed.Migration.dependencies == [PREVIOUS_MIGRATION]


def test_it_is_a_new_code_and_not_one_already_seeded():
    """D-132: a code of its own, so that granting or revoking it changes nothing else."""
    assert VIEW_KNOWLEDGE_MAP_PERMISSION not in EARLIER_ADMINISTRATOR_CODES
    assert Permission.objects.filter(permission_name=VIEW_KNOWLEDGE_MAP_PERMISSION).count() == 1


def test_both_roles_may_view_the_knowledge_map(employee_role, administrator_role):
    assert Permission.objects.filter(permission_name=VIEW_KNOWLEDGE_MAP_PERMISSION).exists()
    assert VIEW_KNOWLEDGE_MAP_PERMISSION in permission_names(employee_role)
    assert VIEW_KNOWLEDGE_MAP_PERMISSION in permission_names(administrator_role)
    holders = set(
        Role.objects.filter(permissions__permission_name=VIEW_KNOWLEDGE_MAP_PERMISSION)
        .values_list("role_name", flat=True)
    )
    assert holders == {EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME}


def test_administrator_still_generalises_employee(employee_role, administrator_role):
    # FR-05's "Administrator generalises Employee": a code the Employee holds, the Administrator
    # holds too.
    assert permission_names(administrator_role) >= permission_names(employee_role)


def test_seed_is_idempotent():
    before = (Permission.objects.count(), RolePermission.objects.count())
    seed.seed_permissions(registry, None)
    assert (Permission.objects.count(), RolePermission.objects.count()) == before


def test_seed_is_reversible(employee_role, administrator_role):
    seed.unseed_permissions(registry, None)
    assert not Permission.objects.filter(permission_name=VIEW_KNOWLEDGE_MAP_PERMISSION).exists()
    # The rows cascade with the permission (D-12), for both roles.
    assert not RolePermission.objects.filter(
        permission__permission_name=VIEW_KNOWLEDGE_MAP_PERMISSION
    ).exists()
    # 0003's to 0010's seeds are untouched: unseeding one migration must not undo another.
    assert permission_names(administrator_role) == EARLIER_ADMINISTRATOR_CODES
    assert permission_names(employee_role) == EARLIER_EMPLOYEE_CODES
    assert Role.objects.count() == 2  # the roles themselves are 0002's

    seed.seed_permissions(registry, None)
    assert VIEW_KNOWLEDGE_MAP_PERMISSION in permission_names(administrator_role)
    assert VIEW_KNOWLEDGE_MAP_PERMISSION in permission_names(employee_role)


def migrate_accounts_to(node):
    """Move accounts to ``node`` and leave every other app at its leaf (as 0008's test does)."""
    executor = MigrationExecutor(connection)
    targets = [leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "accounts"] + [node]
    executor.migrate(targets)


def test_the_migration_reverses_through_the_executor(employee_role, administrator_role):
    """Migrating ``accounts`` back to 0010 runs ``unseed_permissions`` as Django would, and forward
    again restores the seed for both roles. This also proves ``accounts`` has one leaf and that
    0011 is it: a second leaf stops ``migrate`` and ``makemigrations --check``, which are CI's two
    steps before the suite."""
    leaves = [
        key for key in MigrationExecutor(connection).loader.graph.leaf_nodes() if key[0] == "accounts"
    ]
    assert leaves == [THIS_MIGRATION]

    migrate_accounts_to(PREVIOUS_MIGRATION)
    assert not Permission.objects.filter(permission_name=VIEW_KNOWLEDGE_MAP_PERMISSION).exists()
    assert permission_names(administrator_role) == EARLIER_ADMINISTRATOR_CODES
    assert permission_names(employee_role) == EARLIER_EMPLOYEE_CODES

    migrate_accounts_to(THIS_MIGRATION)
    assert VIEW_KNOWLEDGE_MAP_PERMISSION in permission_names(administrator_role)
    assert VIEW_KNOWLEDGE_MAP_PERMISSION in permission_names(employee_role)
