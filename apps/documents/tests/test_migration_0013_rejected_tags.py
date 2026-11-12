"""documents 0013: ``DocumentAnalysis.rejected_tags`` (13 November 2026; the requirements audit of D-128,
finding A5).

- **Forward** adds the column. A row that existed before reads ``[]``, and no database default stays
  behind: the field's ``default=list`` fills the existing rows while the column is added, as 0009's
  added fields did (no ``db_default``).
- **Backwards** removes exactly the column, and the rows keep everything else.

Built as the 0010 to 0012 tests are: the executor itself is driven, for ``documents`` only, from 0012
to 0013 and back, in the ordinary per-test transaction, and each test ends at the leaf. Rows are
written and read through the historical models of the state the database is at.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.constants import EMPLOYEE_ROLE_NAME, PROJECT_DIMENSION, TOPIC_DIMENSION
from apps.documents.models import Document, DocumentAnalysis

pytestmark = pytest.mark.django_db

BEFORE = ("documents", "0012_proposed_tags")
AFTER = ("documents", "0013_rejected_tags")
TABLE = "document_analysis"
COLUMN = "rejected_tags"


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


def documents_leaf():
    [leaf] = [
        key for key in MigrationExecutor(connection).loader.graph.leaf_nodes()
        if key[0] == "documents"
    ]
    return leaf


def column_defaults(table):
    """``{column name: its database default, or None}`` for ``table``."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, column_default FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        return dict(cursor.fetchall())


def make_document(user, title):
    """Through the current model: 0013 changes only ``document_analysis``."""
    return Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, visible_to_roles=[EMPLOYEE_ROLE_NAME]
    )


@pytest.fixture(autouse=True)
def immediate_constraints():
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # as the 0008 to 0012 tests do


def test_0013_is_on_the_path_to_the_leaf_of_documents():
    graph = MigrationExecutor(connection).loader.graph
    assert AFTER in graph.forwards_plan(documents_leaf())


def test_0013_forward_adds_the_column_with_existing_rows_empty_and_no_database_default(employee):
    old_apps = migrate_documents_to(BEFORE)
    assert COLUMN not in column_defaults(TABLE)
    document = make_document(employee, "Harbour works plan")
    proposed = [{"dimension": TOPIC_DIMENSION, "value": "budget planning", "confidence": 0.8}]
    old_apps.get_model("documents", "DocumentAnalysis").objects.create(
        document_id=document.pk, classified_at=timezone.now(), proposed_tags=proposed,
    )

    new_apps = migrate_documents_to(AFTER)

    defaults = column_defaults(TABLE)
    assert COLUMN in defaults
    assert defaults[COLUMN] is None  # the fill's default was dropped again
    row = new_apps.get_model("documents", "DocumentAnalysis").objects.get(document_id=document.pk)
    assert row.rejected_tags == []
    assert row.proposed_tags == proposed

    migrate_documents_to(documents_leaf())  # the leaf, as the rest of the suite expects


def test_0013_backwards_removes_the_column_and_keeps_the_rest_of_the_row(employee):
    new_apps = migrate_documents_to(AFTER)
    document = make_document(employee, "Harbour works plan")
    proposed = [{"dimension": TOPIC_DIMENSION, "value": "budget planning", "confidence": 0.8}]
    new_apps.get_model("documents", "DocumentAnalysis").objects.create(
        document_id=document.pk, classified_at=timezone.now(), proposed_tags=proposed,
        rejected_tags=[{"dimension": PROJECT_DIMENSION, "value": "harbour upgrade", "confidence": 0.6}],
    )

    old_apps = migrate_documents_to(BEFORE)

    assert COLUMN not in column_defaults(TABLE)
    row = old_apps.get_model("documents", "DocumentAnalysis").objects.get(document_id=document.pk)
    assert row.proposed_tags == proposed

    migrate_documents_to(documents_leaf())
    assert DocumentAnalysis.objects.get(document=document).rejected_tags == []  # forward again: empty
