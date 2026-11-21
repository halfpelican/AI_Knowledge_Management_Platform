"""documents 0016: FR-10's document summary on ``DocumentAnalysis`` (D-139, 21 November 2026).

- **Forward** adds the five columns. A row that existed before reads ``""``, ``[]``, false, ``""``
  and null, and no database default stays behind: each field's own default fills the existing rows
  while its column is added, as 0009's and 0013's added fields did (no ``db_default``).
- **Backwards** removes exactly the five columns, and the rows keep everything else.
- **Additive:** every operation is an ``AddField`` on ``documentanalysis``.

Built as the 0010 to 0015 tests are: the executor itself is driven, for ``documents`` only, from 0015
to 0016 and back, in the ordinary per-test transaction, and each test ends at the leaf. Rows are
written and read through the historical models of the state the database is at.
"""

import importlib
from datetime import datetime, timezone as datetime_timezone

import pytest
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.constants import EMPLOYEE_ROLE_NAME, TOPIC_DIMENSION
from apps.documents.models import Document, DocumentAnalysis

pytestmark = pytest.mark.django_db

BEFORE = ("documents", "0015_departments")
AFTER = ("documents", "0016_document_summary")
TABLE = "document_analysis"
COLUMNS = {"summary", "key_points", "summary_truncated", "summary_model", "summarised_at"}


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
    """Through the current model: 0016 changes only ``document_analysis``."""
    return Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, visible_to_roles=[EMPLOYEE_ROLE_NAME]
    )


@pytest.fixture(autouse=True)
def immediate_constraints():
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # as the 0008 to 0015 tests do


def test_0016_is_on_the_path_to_the_leaf_of_documents():
    graph = MigrationExecutor(connection).loader.graph
    assert AFTER in graph.forwards_plan(documents_leaf())


def test_0016_only_adds_fields_to_document_analysis():
    """Additive (CLAUDE.md section 7, Migrations): nothing is altered, renamed, removed or run."""
    migration = importlib.import_module("apps.documents.migrations.0016_document_summary").Migration

    assert migration.dependencies == [BEFORE]
    assert all(type(operation) is migrations.AddField for operation in migration.operations)
    assert {operation.model_name for operation in migration.operations} == {"documentanalysis"}
    assert {operation.name for operation in migration.operations} == COLUMNS


def test_0016_forward_adds_the_columns_with_existing_rows_empty_and_no_database_default(employee):
    old_apps = migrate_documents_to(BEFORE)
    assert not COLUMNS & set(column_defaults(TABLE))
    document = make_document(employee, "Harbour works plan")
    proposed = [{"dimension": TOPIC_DIMENSION, "value": "budget planning", "confidence": 0.8}]
    classified_at = datetime(2026, 11, 9, 10, 0, tzinfo=datetime_timezone.utc)
    old_apps.get_model("documents", "DocumentAnalysis").objects.create(
        document_id=document.pk, classified_at=classified_at, model="classifying-model",
        proposed_tags=proposed,
    )

    new_apps = migrate_documents_to(AFTER)

    defaults = column_defaults(TABLE)
    assert COLUMNS <= set(defaults)
    assert {defaults[column] for column in COLUMNS} == {None}  # each fill's default was dropped again
    row = new_apps.get_model("documents", "DocumentAnalysis").objects.get(document_id=document.pk)
    # A document classified before 0016: an analysis with no summary.
    assert (row.summary, row.key_points, row.summary_truncated) == ("", [], False)
    assert (row.summary_model, row.summarised_at) == ("", None)
    # And the classification it already had is untouched.
    assert (row.proposed_tags, row.model, row.classified_at) == (proposed, "classifying-model", classified_at)

    migrate_documents_to(documents_leaf())  # the leaf, as the rest of the suite expects


def test_0016_backwards_removes_the_columns_and_keeps_the_rest_of_the_row(employee):
    new_apps = migrate_documents_to(AFTER)
    document = make_document(employee, "Harbour works plan")
    proposed = [{"dimension": TOPIC_DIMENSION, "value": "budget planning", "confidence": 0.8}]
    new_apps.get_model("documents", "DocumentAnalysis").objects.create(
        document_id=document.pk, classified_at=timezone.now(), proposed_tags=proposed,
        summary="The plan for the harbour works.", key_points=["Dredging starts in March."],
        summary_truncated=True, summary_model="summarising-model", summarised_at=timezone.now(),
    )

    old_apps = migrate_documents_to(BEFORE)

    assert not COLUMNS & set(column_defaults(TABLE))
    row = old_apps.get_model("documents", "DocumentAnalysis").objects.get(document_id=document.pk)
    assert row.proposed_tags == proposed

    migrate_documents_to(documents_leaf())
    # Forward again: the columns are back and empty. The summary went with its columns.
    again = DocumentAnalysis.objects.get(document=document)
    assert (again.summary, again.key_points, again.summary_truncated) == ("", [], False)
    assert (again.summary_model, again.summarised_at) == ("", None)
