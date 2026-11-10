"""documents 0010 applies and reverses: ``Tags.grown`` (D-105's dated note of 10 November 2026, night,
the lead's revision).

Built as the 0008 and 0009 tests are: the executor itself is driven, for ``documents`` only, from 0009
to 0010 and back, in the ordinary per-test transaction, and the test ends at the leaf. A Tag written
under 0009 survives both directions and reads ``grown = false`` after the forward; the reverse drops
exactly the column.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.core.constants import TOPIC_DIMENSION
from apps.documents.models import Tag

pytestmark = pytest.mark.django_db

BEFORE = ("documents", "0009_fr10_tag_corrections")
AFTER = ("documents", "0010_tag_grown")


def migrate_documents_to(node):
    """Move ``documents`` to ``node`` and leave every other app at its leaf; returns the historical
    app registry at that state. A fresh executor each time, because one that has migrated keeps a
    stale view of what is applied."""
    executor = MigrationExecutor(connection)
    targets = [
        leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "documents"
    ] + [node]
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


def columns_of(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def test_0010_is_the_leaf_of_documents():
    leaves = [
        key for key in MigrationExecutor(connection).loader.graph.leaf_nodes()
        if key[0] == "documents"
    ]
    assert leaves == [AFTER]


def test_0010_applies_and_reverses_keeping_the_tags_either_way():
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # as the 0008 and 0009 tests do

    # --- At 0009: no column; a Topic written under that schema -----------------------------------
    old_apps = migrate_documents_to(BEFORE)
    assert "grown" not in columns_of("tags")
    topic = old_apps.get_model("documents", "Tag").objects.create(
        tag_name="night shifts", dimension=TOPIC_DIMENSION
    )

    # --- Forward: the column exists, and the existing row reads false ------------------------------
    new_apps = migrate_documents_to(AFTER)
    assert "grown" in columns_of("tags")
    assert new_apps.get_model("documents", "Tag").objects.get(pk=topic.pk).grown is False

    # --- Reverse: the column goes, the row stays ---------------------------------------------------
    old_apps = migrate_documents_to(BEFORE)
    assert "grown" not in columns_of("tags")
    assert old_apps.get_model("documents", "Tag").objects.filter(pk=topic.pk).exists()

    # --- Forward again, through the current models -------------------------------------------------
    migrate_documents_to(AFTER)
    assert Tag.objects.get(pk=topic.pk).grown is False
