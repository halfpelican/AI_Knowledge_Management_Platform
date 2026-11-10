"""documents 0009 applies and reverses: ``ContentTags.removed`` and
``DocumentAnalysis.department_applied_by`` (D-105's dated note of 10 November 2026, night; D-119
findings 3 and 10).

Built as ``test_migration_0008_document_analysis.py`` is: the executor itself is driven, for
``documents`` only, from 0008 to 0009 and back, in the ordinary per-test transaction, so the ALTERs,
the ``django_migrations`` rows and the data roll back when the test ends. ``SET CONSTRAINTS ALL
IMMEDIATE`` first, for the reason that file gives: a ``content_tags`` row inserted in this
transaction leaves a pending deferred foreign-key check, and PostgreSQL refuses ``ALTER TABLE``
while one is pending.

What it shows: rows written under 0008 survive both directions, a link reads ``removed = false``
and an analysis ``department_applied_by = null`` after the forward, and the reverse drops exactly
the two columns. Since the security review's finding 5, the reverse also deletes a link marked
removed, which the code before 0009 would show as a live tag, and keeps every live one.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.constants import AI_APPLIED, PROJECT_DIMENSION, SOURCE_TYPES
from apps.documents.models import ContentTag, DocumentAnalysis

pytestmark = pytest.mark.django_db

BEFORE = ("documents", "0008_fr10_document_analysis")
AFTER = ("documents", "0009_fr10_tag_corrections")
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]


def migrate_documents_to(node):
    """Move ``documents`` to ``node`` and leave every other app at its leaf; returns the
    historical app registry at that state. A fresh executor each time, because one that has
    migrated keeps a stale view of what is applied."""
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


def documents_leaf():
    [leaf] = [
        key for key in MigrationExecutor(connection).loader.graph.leaf_nodes()
        if key[0] == "documents"
    ]
    return leaf


def test_0009_is_on_the_path_to_the_leaf_of_documents():
    """0009 was the leaf of ``documents`` until 0010 (``Tags.grown``, the lead's revision of the same
    night) followed it, so the test checks that 0009 is on the leaf's path, and the test below ends
    at the leaf."""
    graph = MigrationExecutor(connection).loader.graph
    assert AFTER in graph.forwards_plan(documents_leaf())


def test_0009_applies_and_reverses_keeping_live_rows_and_deleting_removed_links(document):
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # see the module docstring

    # --- At 0008: neither column; a link and an analysis written under that schema ---------------
    old_apps = migrate_documents_to(BEFORE)
    assert "removed" not in columns_of("content_tags")
    assert "department_applied_by" not in columns_of("document_analysis")
    OldTag = old_apps.get_model("documents", "Tag")
    OldContentTag = old_apps.get_model("documents", "ContentTag")
    OldAnalysis = old_apps.get_model("documents", "DocumentAnalysis")
    tag = OldTag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    link = OldContentTag.objects.create(
        tag_id=tag.pk, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=AI_APPLIED, confirmed=False, provisional=True,
    )
    analysis = OldAnalysis.objects.create(document_id=document.pk, classified_at=timezone.now())

    # --- Forward: both columns exist, and the old rows read with the defaults ---------------------
    new_apps = migrate_documents_to(AFTER)
    assert "removed" in columns_of("content_tags")
    assert "department_applied_by" in columns_of("document_analysis")
    kept_link = new_apps.get_model("documents", "ContentTag").objects.get(pk=link.pk)
    assert (kept_link.removed, kept_link.provisional) == (False, True)
    kept_analysis = new_apps.get_model("documents", "DocumentAnalysis").objects.get(pk=analysis.pk)
    assert kept_analysis.department_applied_by is None
    # A link a person removed, written under 0009.
    removed_link = new_apps.get_model("documents", "ContentTag").objects.create(
        tag_id=tag.pk, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=AI_APPLIED, confirmed=False, removed=True,
    )

    # --- Reverse: the two columns go, the live rows stay, the removed link goes ---------------------
    old_apps = migrate_documents_to(BEFORE)
    assert "removed" not in columns_of("content_tags")
    assert "department_applied_by" not in columns_of("document_analysis")
    remaining = list(old_apps.get_model("documents", "ContentTag").objects.values_list("pk", flat=True))
    assert removed_link.pk not in remaining  # the 0008 code would have shown it as a live tag
    assert remaining == [link.pk]
    assert old_apps.get_model("documents", "DocumentAnalysis").objects.filter(pk=analysis.pk).exists()

    # --- Forward again, to the leaf, through the current models ----------------------------------
    migrate_documents_to(documents_leaf())
    assert ContentTag.objects.get(pk=link.pk).removed is False
    assert DocumentAnalysis.objects.get(pk=analysis.pk).department_applied_by is None
