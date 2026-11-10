"""Accounts migration 0006: ``manage_meetings``, held by Administrator only (D-99).

Meeting deletion is not in the proposal; the lead asked for it on 7 November 2026 and chose a
permission of its own rather than ``manage_documents``. This is the seed
``DELETE /api/meetings/{id}`` reads, after resolving the meeting through the caller's scope
(``apps/api/tests/test_meeting_delete.py`` tests that route from both roles).

The reversal is tested two ways: through the migration's own functions, as 0003 to 0005's tests
do, and through the migration executor, migrating ``accounts`` back to 0005 and forward again.
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
    REVIEW_KNOWLEDGE_GAPS_PERMISSION,
)

pytestmark = pytest.mark.django_db

seed = importlib.import_module("apps.accounts.migrations.0006_seed_manage_meetings")

THIS_MIGRATION = ("accounts", "0006_seed_manage_meetings")
PREVIOUS_MIGRATION = ("accounts", "0005_seed_manage_documents")


def permission_names(role):
    return set(role.permissions.values_list("permission_name", flat=True))


def test_the_migration_uses_the_permission_constant():
    """The constant and the frozen migration name must agree, or the view would check a code
    nothing holds and refuse every meeting delete, the Administrator's included."""
    assert seed.MANAGE_MEETINGS == MANAGE_MEETINGS_PERMISSION
    assert seed.ROLE_PERMISSIONS == {
        ADMINISTRATOR_ROLE_NAME: (MANAGE_MEETINGS_PERMISSION,),
        EMPLOYEE_ROLE_NAME: (),
    }


def test_it_is_a_new_code_and_not_manage_documents():
    """D-99: not a reuse of D-73's permission, so granting one never grants the other."""
    assert MANAGE_MEETINGS_PERMISSION != MANAGE_DOCUMENTS_PERMISSION
    assert Permission.objects.filter(
        permission_name__in=[MANAGE_MEETINGS_PERMISSION, MANAGE_DOCUMENTS_PERMISSION]
    ).count() == 2


def test_manage_meetings_is_held_by_administrator_only(employee_role, administrator_role):
    assert Permission.objects.filter(permission_name=MANAGE_MEETINGS_PERMISSION).exists()
    assert MANAGE_MEETINGS_PERMISSION in permission_names(administrator_role)
    assert MANAGE_MEETINGS_PERMISSION not in permission_names(employee_role)
    holders = set(
        Role.objects.filter(permissions__permission_name=MANAGE_MEETINGS_PERMISSION)
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
    assert not Permission.objects.filter(permission_name=MANAGE_MEETINGS_PERMISSION).exists()
    # The rows cascade with the permission (D-12).
    assert not RolePermission.objects.filter(
        permission__permission_name=MANAGE_MEETINGS_PERMISSION
    ).exists()
    # 0003's, 0004's, 0005's, 0007's and 0008's seeds are untouched: unseeding one migration must
    # not undo another.
    assert permission_names(administrator_role) == {
        MANAGE_ROLES_PERMISSION, CONTRIBUTE_CONTENT_PERMISSION, MANAGE_DOCUMENTS_PERMISSION,
        REVIEW_KNOWLEDGE_GAPS_PERMISSION, MANAGE_TAGS_PERMISSION,
    }
    assert permission_names(employee_role) == {CONTRIBUTE_CONTENT_PERMISSION}
    assert Role.objects.count() == 2  # the roles themselves are 0002's

    seed.seed_permissions(registry, None)
    assert MANAGE_MEETINGS_PERMISSION in permission_names(administrator_role)
    assert MANAGE_MEETINGS_PERMISSION not in permission_names(employee_role)


def migrate_accounts_to(node):
    """Move accounts to ``node`` and leave every other app at its leaf.

    A fresh executor each time, because one that has migrated keeps a stale view of what is
    applied. This runs in the ordinary per-test transaction, as
    ``apps/retrieval/tests/test_migration_0003_citation_set_null.py`` does and for its reason: the
    ``django_migrations`` rows and the data roll back when the test ends, and the seeded roles a
    transactional test's flush would wipe are never touched.
    """
    executor = MigrationExecutor(connection)
    targets = [leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "accounts"] + [node]
    executor.migrate(targets)


def test_the_migration_reverses_through_the_executor(employee_role, administrator_role):
    """Migrating ``accounts`` back to 0005 runs ``unseed_permissions`` as Django would, and
    forward again restores the seed. The executor plans the real graph.

    0006 was the leaf of ``accounts`` until 0007 (D-107) followed it, so the test now checks
    that 0006 is on the leaf's path and migrates forward to the leaf, which reapplies 0007 and,
    since D-119 finding 5, 0008 too.
    """
    graph = MigrationExecutor(connection).loader.graph
    [leaf] = [key for key in graph.leaf_nodes() if key[0] == "accounts"]
    assert THIS_MIGRATION in graph.forwards_plan(leaf)

    migrate_accounts_to(PREVIOUS_MIGRATION)
    assert not Permission.objects.filter(permission_name=MANAGE_MEETINGS_PERMISSION).exists()
    assert permission_names(administrator_role) == {
        MANAGE_ROLES_PERMISSION, CONTRIBUTE_CONTENT_PERMISSION, MANAGE_DOCUMENTS_PERMISSION,
    }

    migrate_accounts_to(leaf)
    assert MANAGE_MEETINGS_PERMISSION in permission_names(administrator_role)
    assert MANAGE_MEETINGS_PERMISSION not in permission_names(employee_role)
