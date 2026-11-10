"""documents 0008 applies and reverses: DocumentAnalysis, and ContentTags' two FR-10 columns (D-105).

Follows ``apps/retrieval/tests/test_migration_0003_citation_set_null.py``: the executor itself is
driven, for ``documents`` only, from 0007 to 0008 and back, in the ordinary per-test transaction.
PostgreSQL's DDL is transactional, so the CREATE, the ALTERs, the ``django_migrations`` rows and
the data all roll back when the test ends, and the test ends at 0008 anyway so that the schema the
rest of the suite expects is the one it leaves.

``SET CONSTRAINTS ALL IMMEDIATE`` first, for the reason that file gives: a ``content_tags`` row
inserted in this transaction leaves a pending deferred foreign-key check on the table, and
PostgreSQL refuses ``ALTER TABLE`` while one is pending. In a real ``migrate`` the rows were
committed long before.

What this file does not cover: migrating any app but ``documents``, and a ``content_tags`` table
large enough for the two ``ADD COLUMN``s to matter.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.constants import DOCUMENT_TYPES, PROJECT_DIMENSION, SOURCE_TYPES, USER_APPLIED
from apps.documents.models import ContentTag, Tag

pytestmark = pytest.mark.django_db

BEFORE = ("documents", "0007_document_status_too_large_to_index")
AFTER = ("documents", "0008_fr10_document_analysis")
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


def test_0008_is_the_leaf_of_documents():
    leaves = [
        key for key in MigrationExecutor(connection).loader.graph.leaf_nodes()
        if key[0] == "documents"
    ]
    assert leaves == [AFTER]


def test_0008_applies_and_reverses_keeping_the_tag_links_either_way(document):
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # see the module docstring

    # --- At 0007: no analysis table, no FR-10 columns; a link written under that schema -------
    old_apps = migrate_documents_to(BEFORE)
    assert columns_of("document_analysis") == set()
    assert columns_of("content_tags").isdisjoint({"confidence", "provisional"})
    OldTag = old_apps.get_model("documents", "Tag")
    OldContentTag = old_apps.get_model("documents", "ContentTag")
    tag = OldTag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    link = OldContentTag.objects.create(
        tag_id=tag.pk, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=USER_APPLIED, confirmed=True,
    )

    # --- Forward: the table and the columns exist; the old link reads with the defaults -------
    new_apps = migrate_documents_to(AFTER)
    assert columns_of("document_analysis") == {
        "analysis_id", "doc_id", "machine_doc_type", "machine_doc_type_confidence",
        "machine_department", "machine_department_confidence", "doc_type", "doc_type_outcome",
        "department_outcome", "user_edited", "proposed_topics", "discarded_suggestions",
        "model", "input_truncated", "classified_at",
    }
    assert {"confidence", "provisional"} <= columns_of("content_tags")
    NewContentTag = new_apps.get_model("documents", "ContentTag")
    kept = NewContentTag.objects.get(pk=link.pk)
    assert (kept.confidence, kept.provisional, kept.confirmed) == (None, False, True)
    Analysis = new_apps.get_model("documents", "DocumentAnalysis")
    analysis = Analysis.objects.create(
        document_id=document.pk, doc_type=DOCUMENT_TYPES[0], classified_at=timezone.now()
    )
    assert Analysis.objects.filter(pk=analysis.pk).exists()

    # --- Reverse: the table goes, the columns go, the link stays --------------------------------
    old_apps = migrate_documents_to(BEFORE)
    assert columns_of("document_analysis") == set()
    assert columns_of("content_tags").isdisjoint({"confidence", "provisional"})
    OldContentTag = old_apps.get_model("documents", "ContentTag")
    assert list(OldContentTag.objects.values_list("pk", "source_id", "confirmed")) == [
        (link.pk, document.pk, True)
    ]

    # --- Forward again, through the current models ----------------------------------------------
    migrate_documents_to(AFTER)
    assert ContentTag.objects.get(pk=link.pk).provisional is False
    assert Tag.objects.filter(pk=tag.pk).exists()
