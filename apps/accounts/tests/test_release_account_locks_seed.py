"""Accounts migrations 0009 and 0010: the ``login_attempts`` table, and ``release_account_locks``
held by Administrator only (FR-03, D-130).

FR-03: "Only a user holding the Administrator role may release a lock." ``POST
/api/users/{id}/unlock`` checks this code before anything else, and ``GET /api/users`` shows each
live lock only to a holder of it (``apps/api/tests/test_fr03_unlock.py`` and
``test_fr03_user_list_lock.py`` test both from both roles). Seeded the way 0008 seeds
``manage_tags`` (D-99's pattern). The release's lock order also rests on it: ``UserUnlockView``
locks the Administrators' rows before the target, which keeps the requester's own row out of a
lock cycle only while every holder is an Administrator (see the comment in
``UserUnlockView.post``).

The reversal is tested two ways, as 0008's is: through the seed's own functions, and through the
migration executor, migrating ``accounts`` back to 0008 and forward again one migration at a time,
which also proves 0009 creates and drops exactly the one table.
"""

import importlib

import pytest
from django.apps import apps as registry
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.accounts.models import LoginAttempt, Permission, Role, RolePermission
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
)

pytestmark = pytest.mark.django_db

seed = importlib.import_module("apps.accounts.migrations.0010_seed_release_account_locks")

THIS_MIGRATION = ("accounts", "0010_seed_release_account_locks")
TABLE_MIGRATION = ("accounts", "0009_login_attempts")
PREVIOUS_MIGRATION = ("accounts", "0008_seed_manage_tags")
EARLIER_ADMINISTRATOR_CODES = {
    MANAGE_ROLES_PERMISSION, CONTRIBUTE_CONTENT_PERMISSION, MANAGE_DOCUMENTS_PERMISSION,
    MANAGE_MEETINGS_PERMISSION, REVIEW_KNOWLEDGE_GAPS_PERMISSION, MANAGE_TAGS_PERMISSION,
}
# docs/schema-v1.md section 1, LoginAttempts: the proposal's five columns, then FR-03's four.
LOGIN_ATTEMPT_COLUMNS = {
    "attempt_id", "attempted_email", "source_ip", "success", "attempted_at",
    "event", "user_id", "released_by", "locked_until",
}


def permission_names(role):
    return set(role.permissions.values_list("permission_name", flat=True))


def holders_of(code):
    return set(Role.objects.filter(permissions__permission_name=code).values_list("role_name", flat=True))


def test_the_migration_uses_the_permission_constant():
    """The constant and the frozen migration name must agree, or the release would check a code
    nothing holds and refuse the Administrator too, and the list would never show a lock."""
    assert seed.RELEASE_ACCOUNT_LOCKS == RELEASE_ACCOUNT_LOCKS_PERMISSION
    assert seed.ROLE_PERMISSIONS == {
        ADMINISTRATOR_ROLE_NAME: (RELEASE_ACCOUNT_LOCKS_PERMISSION,),
        EMPLOYEE_ROLE_NAME: (),
    }


def test_release_account_locks_is_held_by_administrator_only(employee_role, administrator_role):
    assert Permission.objects.filter(permission_name=RELEASE_ACCOUNT_LOCKS_PERMISSION).exists()
    assert RELEASE_ACCOUNT_LOCKS_PERMISSION in permission_names(administrator_role)
    assert RELEASE_ACCOUNT_LOCKS_PERMISSION not in permission_names(employee_role)
    assert holders_of(RELEASE_ACCOUNT_LOCKS_PERMISSION) == {ADMINISTRATOR_ROLE_NAME}


def test_administrator_still_generalises_employee(employee_role, administrator_role):
    assert permission_names(administrator_role) >= permission_names(employee_role)


def test_seed_is_idempotent():
    before = (Permission.objects.count(), RolePermission.objects.count())
    seed.seed_permissions(registry, None)
    seed.seed_permissions(registry, None)
    assert (Permission.objects.count(), RolePermission.objects.count()) == before
    assert holders_of(RELEASE_ACCOUNT_LOCKS_PERMISSION) == {ADMINISTRATOR_ROLE_NAME}


def test_seed_is_reversible(employee_role, administrator_role):
    seed.unseed_permissions(registry, None)
    assert not Permission.objects.filter(permission_name=RELEASE_ACCOUNT_LOCKS_PERMISSION).exists()
    # The rows cascade with the permission (D-12).
    assert not RolePermission.objects.filter(
        permission__permission_name=RELEASE_ACCOUNT_LOCKS_PERMISSION
    ).exists()
    # 0003's to 0008's seeds are untouched: unseeding one migration must not undo another.
    assert permission_names(administrator_role) == EARLIER_ADMINISTRATOR_CODES
    assert permission_names(employee_role) == {CONTRIBUTE_CONTENT_PERMISSION}
    assert Role.objects.count() == 2  # the roles themselves are 0002's

    seed.seed_permissions(registry, None)
    assert holders_of(RELEASE_ACCOUNT_LOCKS_PERMISSION) == {ADMINISTRATOR_ROLE_NAME}


def table_names():
    return set(connection.introspection.table_names())


def columns_of(table):
    with connection.cursor() as cursor:
        return {column.name for column in connection.introspection.get_table_description(cursor, table)}


def migrate_accounts_to(node):
    """Move accounts to ``node`` and leave every other app at its leaf (as 0008's test does)."""
    executor = MigrationExecutor(connection)
    targets = [leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "accounts"] + [node]
    executor.migrate(targets)


def test_the_migrations_apply_and_reverse_through_the_executor(employee_role, administrator_role):
    """Back to 0008: 0010's seed is undone and 0009's table is dropped, and ``users`` is left as it
    was. Forward to 0009: the table returns with its nine columns and no seed. Forward to the leaf:
    the seed returns, Administrator only.

    Both are checked to be on the path to the leaf of ``accounts`` rather than to be the leaf, so
    a later migration does not break this test, as 0009 broke 0008's."""
    graph = MigrationExecutor(connection).loader.graph
    [leaf] = [key for key in graph.leaf_nodes() if key[0] == "accounts"]
    plan = graph.forwards_plan(leaf)
    assert plan.index(PREVIOUS_MIGRATION) < plan.index(TABLE_MIGRATION) < plan.index(THIS_MIGRATION)
    users_columns = columns_of("users")
    assert LoginAttempt._meta.db_table in table_names()

    migrate_accounts_to(PREVIOUS_MIGRATION)
    assert "login_attempts" not in table_names()
    assert columns_of("users") == users_columns
    assert not Permission.objects.filter(permission_name=RELEASE_ACCOUNT_LOCKS_PERMISSION).exists()
    assert permission_names(administrator_role) == EARLIER_ADMINISTRATOR_CODES

    migrate_accounts_to(TABLE_MIGRATION)
    assert columns_of("login_attempts") == LOGIN_ATTEMPT_COLUMNS
    assert not Permission.objects.filter(permission_name=RELEASE_ACCOUNT_LOCKS_PERMISSION).exists()

    migrate_accounts_to(leaf)
    assert columns_of("login_attempts") == LOGIN_ATTEMPT_COLUMNS
    assert holders_of(RELEASE_ACCOUNT_LOCKS_PERMISSION) == {ADMINISTRATOR_ROLE_NAME}
    assert columns_of("users") == users_columns
