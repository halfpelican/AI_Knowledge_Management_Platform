"""Accounts migration 0007: ``review_knowledge_gaps``, held by Administrator only (D-107).

FR-19's list is "visible to Administrators", and D-107 makes that a permission code seeded the
way 0006 seeds ``manage_meetings`` (D-99's pattern). Every knowledge-gap route checks it, and the
dashboard's ``knowledge_gaps`` panel is present only for a role that holds it
(``apps/api/tests/test_knowledge_gaps.py`` tests both from both roles).

The reversal is tested two ways, as 0006's is: through the migration's own functions, and through
the migration executor, migrating ``accounts`` back to 0006 and forward again.
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
    REVIEW_KNOWLEDGE_GAPS_PERMISSION,
)

pytestmark = pytest.mark.django_db

seed = importlib.import_module("apps.accounts.migrations.0007_seed_review_knowledge_gaps")

THIS_MIGRATION = ("accounts", "0007_seed_review_knowledge_gaps")
PREVIOUS_MIGRATION = ("accounts", "0006_seed_manage_meetings")
EARLIER_ADMINISTRATOR_CODES = {
    MANAGE_ROLES_PERMISSION, CONTRIBUTE_CONTENT_PERMISSION, MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION,
}


def permission_names(role):
    return set(role.permissions.values_list("permission_name", flat=True))


def test_the_migration_uses_the_permission_constant():
    """The constant and the frozen migration name must agree, or every knowledge-gap route would
    check a code nothing holds and refuse the Administrator too."""
    assert seed.REVIEW_KNOWLEDGE_GAPS == REVIEW_KNOWLEDGE_GAPS_PERMISSION
    assert seed.ROLE_PERMISSIONS == {
        ADMINISTRATOR_ROLE_NAME: (REVIEW_KNOWLEDGE_GAPS_PERMISSION,),
        EMPLOYEE_ROLE_NAME: (),
    }


def test_review_knowledge_gaps_is_held_by_administrator_only(employee_role, administrator_role):
    assert Permission.objects.filter(permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION).exists()
    assert REVIEW_KNOWLEDGE_GAPS_PERMISSION in permission_names(administrator_role)
    assert REVIEW_KNOWLEDGE_GAPS_PERMISSION not in permission_names(employee_role)
    holders = set(
        Role.objects.filter(permissions__permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION)
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
    assert not Permission.objects.filter(permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION).exists()
    # The rows cascade with the permission (D-12).
    assert not RolePermission.objects.filter(
        permission__permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION
    ).exists()
    # 0003's to 0006's seeds are untouched: unseeding one migration must not undo another.
    assert permission_names(administrator_role) == EARLIER_ADMINISTRATOR_CODES
    assert permission_names(employee_role) == {CONTRIBUTE_CONTENT_PERMISSION}
    assert Role.objects.count() == 2  # the roles themselves are 0002's

    seed.seed_permissions(registry, None)
    assert REVIEW_KNOWLEDGE_GAPS_PERMISSION in permission_names(administrator_role)
    assert REVIEW_KNOWLEDGE_GAPS_PERMISSION not in permission_names(employee_role)


def migrate_accounts_to(node):
    """Move accounts to ``node`` and leave every other app at its leaf (as 0006's test does)."""
    executor = MigrationExecutor(connection)
    targets = [leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "accounts"] + [node]
    executor.migrate(targets)


def test_the_migration_reverses_through_the_executor(employee_role, administrator_role):
    """Migrating ``accounts`` back to 0006 runs ``unseed_permissions`` as Django would, and
    forward again restores the seed. This also proves 0007 is the leaf of ``accounts``."""
    leaves = [
        key for key in MigrationExecutor(connection).loader.graph.leaf_nodes() if key[0] == "accounts"
    ]
    assert leaves == [THIS_MIGRATION]

    migrate_accounts_to(PREVIOUS_MIGRATION)
    assert not Permission.objects.filter(permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION).exists()
    assert permission_names(administrator_role) == EARLIER_ADMINISTRATOR_CODES

    migrate_accounts_to(THIS_MIGRATION)
    assert REVIEW_KNOWLEDGE_GAPS_PERMISSION in permission_names(administrator_role)
    assert REVIEW_KNOWLEDGE_GAPS_PERMISSION not in permission_names(employee_role)


def test_every_role_holding_the_code_has_the_administrators_scope():
    """The security review of 10 November 2026, L3. D-108's argument that the gap log discloses
    nothing rests on its readers already reading every chunk (D-66). A role given
    review_knowledge_gaps with a narrower scope would read other users' verbatim questions about
    content it may not see, and could use its own zero-result searches as an oracle over
    restricted text. So every role holding the code must have the Administrator's effective
    roles."""
    from apps.accounts.models import RolePermission
    from apps.core.constants import (
        ADMINISTRATOR_ROLE_NAME,
        EFFECTIVE_ROLES,
        REVIEW_KNOWLEDGE_GAPS_PERMISSION,
    )

    holders = set(
        RolePermission.objects.filter(
            permission__permission_name=REVIEW_KNOWLEDGE_GAPS_PERMISSION
        ).values_list("role__role_name", flat=True)
    )
    assert holders, "the code must be held by some role, or the log has no readers"
    full_scope = set(EFFECTIVE_ROLES[ADMINISTRATOR_ROLE_NAME])
    for role_name in holders:
        assert full_scope <= set(EFFECTIVE_ROLES.get(role_name, ())), role_name
