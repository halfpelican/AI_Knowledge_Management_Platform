"""Accounts migration 0012: ``users.picture`` and ``users.picture_updated_at`` (D-137).

CLAUDE.md section 7: migrations are additive and reversible. Tested through the migration executor,
as 0010's and 0008's are: back to 0011, which drops exactly the two columns and keeps every row,
then forward to the leaf, which adds them back, an existing row getting an empty ``picture`` and a
null ``picture_updated_at``.

0012 depends on 0011, FR-20's seed (D-132). It was written against 0010 while 0011 was on a branch
of its own, and was re-pointed to 0011 in the merge of ``main`` on 17 November 2026, before it had
been pushed, so ``accounts`` has one leaf and no merge migration. This test still asks only that
0012 is on the path to the leaf of ``accounts``, never that it is the leaf, so a later migration
does not break it.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db

THIS_MIGRATION = ("accounts", "0012_user_picture")
PREVIOUS_MIGRATION = ("accounts", "0011_seed_view_knowledge_map")
PICTURE_COLUMNS = {"picture", "picture_updated_at"}


def columns_of(table):
    with connection.cursor() as cursor:
        return {column.name for column in connection.introspection.get_table_description(cursor, table)}


def migrate_accounts_to(node):
    """Move accounts to ``node`` and leave every other app at its leaf (as 0010's test does)."""
    executor = MigrationExecutor(connection)
    targets = [leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "accounts"] + [node]
    executor.migrate(targets)


def picture_columns_of(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT picture, picture_updated_at FROM users WHERE user_id = %s", [user_id])
        return cursor.fetchone()


def test_0012_depends_on_0011_and_is_on_the_path_to_the_leaf():
    graph = MigrationExecutor(connection).loader.graph
    [leaf] = [key for key in graph.leaf_nodes() if key[0] == "accounts"]
    plan = graph.forwards_plan(leaf)
    assert plan.index(PREVIOUS_MIGRATION) < plan.index(THIS_MIGRATION)
    assert graph.nodes[THIS_MIGRATION].dependencies == [PREVIOUS_MIGRATION]


def test_0012_adds_and_drops_exactly_the_two_columns_and_keeps_every_row(employee, administrator):
    graph = MigrationExecutor(connection).loader.graph
    [leaf] = [key for key in graph.leaf_nodes() if key[0] == "accounts"]
    users_columns = columns_of("users")
    assert PICTURE_COLUMNS <= users_columns
    # The two users rows were inserted in this test's transaction, and their foreign keys are
    # checked at commit (Django's constraints are DEFERRABLE INITIALLY DEFERRED). Postgres refuses
    # to ALTER a table with checks still pending, so they are run now.
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    migrate_accounts_to(PREVIOUS_MIGRATION)
    assert columns_of("users") == users_columns - PICTURE_COLUMNS
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM users")
        assert cursor.fetchone() == (2,)

    migrate_accounts_to(leaf)
    assert columns_of("users") == users_columns
    assert picture_columns_of(employee.pk) == ("", None)
    assert picture_columns_of(administrator.pk) == ("", None)
