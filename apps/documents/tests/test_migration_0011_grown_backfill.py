"""documents 0011: every tag today's scheme withholds from some audience is marked grown (D-105's dated
note of 10 November 2026, night: the security review of ``84b5771``).

The backfill marks exactly the tags that have links and no link on a source every role reads, every
link counting (held and removed ones included), documents and meetings both. It leaves unlinked tags
and tags with a readable link as they are, and an already grown tag grown. Its reverse does nothing.

Built as the 0008 to 0010 tests are: the executor itself is driven, for ``documents`` only, from 0010
to 0011 and back, in the ordinary per-test transaction, and the test ends at the leaf. 0011 changes no
schema, so the rows are written through the current models while ``documents`` stands at 0010. Since
0012 (FR-16's ``ContentChunks.ai_generated``, D-125) the current models hold one column 0010 and 0011
do not; the rows this test writes there are tags, links, documents and meetings, never a chunk.
"""

import datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    EMPLOYEE_ROLE_NAME,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    USER_APPLIED,
)
from apps.documents.models import ContentTag, Document, Tag
from apps.meetings.models import Meeting

pytestmark = pytest.mark.django_db

BEFORE = ("documents", "0010_tag_grown")
AFTER = ("documents", "0011_grown_marks_withheld_tags")
DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]


def migrate_documents_to(node):
    """Move ``documents`` to ``node`` and leave every other app at its leaf. A fresh executor each
    time, because one that has migrated keeps a stale view of what is applied."""
    executor = MigrationExecutor(connection)
    targets = [
        leaf for leaf in executor.loader.graph.leaf_nodes() if leaf[0] != "documents"
    ] + [node]
    executor.migrate(targets)


def grown_by_id(ids):
    return dict(Tag.objects.filter(pk__in=ids).values_list("pk", "grown"))


@pytest.fixture
def sources(employee, administrator):
    def document(title, roles, user):
        return Document.objects.create(
            title=title, file_type="txt", uploaded_by=user, visible_to_roles=roles
        )

    def meeting(title, roles):
        return Meeting.objects.create(
            title=title, meeting_date=datetime.date(2026, 11, 2), transcript_text="Minutes.",
            visible_to_roles=roles,
        )

    return {
        "employee": document("Staff handbook", [EMPLOYEE_ROLE_NAME], employee),
        "both": document("Site notice", BOTH_ROLES, employee),
        "administrator": document("Board pack", [ADMINISTRATOR_ROLE_NAME], administrator),
        "nobody": document("Orphaned", [], employee),
        "board meeting": meeting("Board meeting", [ADMINISTRATOR_ROLE_NAME]),
        "staff meeting": meeting("Staff meeting", BOTH_ROLES),
    }


def link(tag, source, **fields):
    fields.setdefault("applied_by", USER_APPLIED)
    fields.setdefault("confirmed", True)
    source_type = MEETING_SOURCE_TYPE if isinstance(source, Meeting) else DOCUMENT_SOURCE_TYPE
    return ContentTag.objects.create(tag=tag, source_type=source_type, source_id=source.pk, **fields)


def documents_leaf():
    [leaf] = [
        key for key in MigrationExecutor(connection).loader.graph.leaf_nodes()
        if key[0] == "documents"
    ]
    return leaf


def test_0011_is_on_the_path_to_the_leaf_of_documents():
    """0011 was the leaf of ``documents`` until two migrations numbered 0012 followed it: FR-16's
    ``ContentChunks.ai_generated`` (D-125) and ``proposed_tags`` (D-128), joined by 0014's merge. So
    the test checks that 0011 is on the leaf's path, and the test below ends at the leaf, as the
    0009 and 0010 tests do."""
    graph = MigrationExecutor(connection).loader.graph
    assert AFTER in graph.forwards_plan(documents_leaf())


def test_0011_marks_exactly_the_tags_no_source_every_role_reads_carries_and_its_reverse_does_nothing(
    sources,
):
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # as the 0008 to 0010 tests do
    migrate_documents_to(BEFORE)
    held = {"applied_by": AI_APPLIED, "confirmed": False, "provisional": True}
    removed = {"applied_by": AI_APPLIED, "confirmed": False, "removed": True}
    expected = {}

    def tag(name, *carriers, grown=False, mark):
        row = Tag.objects.create(tag_name=name, dimension=PROJECT_DIMENSION, grown=grown)
        for source, fields in carriers:
            link(row, source, **fields)
        expected[row.pk] = mark
        return row

    # Linked, and no link on a source every role reads: marked.
    tag("restricted person link", (sources["administrator"], {}), mark=True)
    tag("restricted held link", (sources["administrator"], held), mark=True)
    tag("restricted removed link", (sources["administrator"], removed), mark=True)
    tag("restricted meeting", (sources["board meeting"], {}), mark=True)
    tag("on a document nobody reads", (sources["nobody"], {}), mark=True)
    # Unlinked, or with a link every role reads (an Administrator reads Employee material, D-66).
    tag("unlinked", mark=False)
    tag("on an employee document", (sources["employee"], {}), mark=False)
    tag("on both sides", (sources["administrator"], {}), (sources["both"], {}), mark=False)
    tag("on a staff meeting", (sources["staff meeting"], {}), mark=False)
    tag("readable through a removed link", (sources["both"], removed), mark=False)
    # Already grown, and readable: stays grown.
    already = tag("already grown", (sources["both"], {}), grown=True, mark=True)
    # The premise: before the migration, only that one is grown.
    assert [pk for pk, grown in grown_by_id(expected).items() if grown] == [already.pk]

    migrate_documents_to(AFTER)
    assert grown_by_id(expected) == expected

    # The reverse does nothing: every mark stays.
    migrate_documents_to(BEFORE)
    assert grown_by_id(expected) == expected

    migrate_documents_to(documents_leaf())  # the leaf, as the rest of the suite expects
