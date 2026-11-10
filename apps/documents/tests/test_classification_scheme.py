"""``tag_scheme``: the scheme a document is classified against is the vocabulary its own audience
may read (D-105, CLAUDE.md invariant 1).

The rule under test, from the function's docstring: a value is in the scheme only if EVERY role
in ``document.visible_to_roles`` can read at least one source carrying it; a value with no links
is vocabulary only and is always in; readability comes from ``scoped_documents`` and
``scoped_meetings`` and from nothing written here.

The fixtures build the smallest corpus that tells the cases apart: an Employee-visible document
and an Administrator-only one, a Project linked only to the restricted document, a Process both
carry, a Topic nothing carries, a Topic held provisionally on the restricted document, and a
department each.
"""

import datetime
import sys

import pytest

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    DEPARTMENT_DIMENSION,
    DOCUMENT_TYPES,
    EMPLOYEE_ROLE_NAME,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    REPOSITORY_TAG_DIMENSIONS,
    ROLE_NAMES,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.documents import classification as module
from apps.documents.classification import tag_scheme
from apps.documents.models import ContentTag, Document, Tag
from apps.meetings.models import Meeting

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES

RESTRICTED_PROJECT = "restricted project"
SHARED_PROCESS = "shared process"
UNLINKED_TOPIC = "unlinked topic"
HELD_TOPIC = "held topic"
RETIRED_PROJECT = "retired project"
BOARD_TOPIC = "board topic"


def make_document(user, title, roles, department=""):
    return Document.objects.create(
        title=title, file_type="pdf", uploaded_by=user, department=department,
        visible_to_roles=roles,
    )


def link(tag, source_type, source_id, **fields):
    fields.setdefault("applied_by", USER_APPLIED)
    fields.setdefault("confirmed", True)
    return ContentTag.objects.create(tag=tag, source_type=source_type, source_id=source_id, **fields)


@pytest.fixture
def employee_document(employee):
    return make_document(employee, "Staff handbook", [EMPLOYEE_ROLE_NAME], "People")


@pytest.fixture
def administrator_document(administrator):
    return make_document(administrator, "Board pack", [ADMINISTRATOR_ROLE_NAME], "Legal")


@pytest.fixture
def corpus(employee_document, administrator_document):
    restricted = Tag.objects.create(tag_name=RESTRICTED_PROJECT, dimension=PROJECT_DIMENSION)
    link(restricted, DOCUMENT_SOURCE_TYPE, administrator_document.pk)
    shared = Tag.objects.create(tag_name=SHARED_PROCESS, dimension=PROCESS_DIMENSION)
    link(shared, DOCUMENT_SOURCE_TYPE, administrator_document.pk)
    link(shared, DOCUMENT_SOURCE_TYPE, employee_document.pk)
    Tag.objects.create(tag_name=UNLINKED_TOPIC, dimension=TOPIC_DIMENSION)
    held = Tag.objects.create(tag_name=HELD_TOPIC, dimension=TOPIC_DIMENSION)
    link(held, DOCUMENT_SOURCE_TYPE, administrator_document.pk,
         applied_by=AI_APPLIED, confirmed=False, provisional=True)
    Tag.objects.create(tag_name=RETIRED_PROJECT, dimension=PROJECT_DIMENSION, active=False)
    # A Department-dimension tag exists in the vocabulary and is never part of the scheme (D-72).
    Tag.objects.create(tag_name="people", dimension=DEPARTMENT_DIMENSION)


# --- The audience rule, per dimension -------------------------------------------------------------


def test_a_tag_linked_only_to_an_administrator_only_document_is_withheld_from_an_employee_visible_one(
    corpus, employee_document, administrator_document
):
    assert RESTRICTED_PROJECT not in tag_scheme(employee_document).tags[PROJECT_DIMENSION]
    assert RESTRICTED_PROJECT in tag_scheme(administrator_document).tags[PROJECT_DIMENSION]


def test_an_unlinked_seeded_tag_is_vocabulary_only_and_in_both_schemes(
    corpus, employee_document, administrator_document
):
    """The corpus fixture's Topic that nothing carries was made as a seed makes it, so it is not
    grown: vocabulary, in both schemes. 11a610f inverted this, keeping every unlinked Topic out, and
    was narrowed the same night (D-105's dated note of 10 November 2026, night)."""
    assert UNLINKED_TOPIC in tag_scheme(employee_document).tags[TOPIC_DIMENSION]
    assert UNLINKED_TOPIC in tag_scheme(administrator_document).tags[TOPIC_DIMENSION]


def test_a_tag_both_audiences_can_read_a_source_of_is_in_both_schemes(
    corpus, employee_document, administrator_document
):
    assert SHARED_PROCESS in tag_scheme(employee_document).tags[PROCESS_DIMENSION]
    assert SHARED_PROCESS in tag_scheme(administrator_document).tags[PROCESS_DIMENSION]


def test_a_held_provisional_link_on_a_restricted_document_still_counts_as_a_link(
    corpus, employee_document, administrator_document
):
    assert HELD_TOPIC not in tag_scheme(employee_document).tags[TOPIC_DIMENSION]
    assert HELD_TOPIC in tag_scheme(administrator_document).tags[TOPIC_DIMENSION]


def test_an_inactive_tag_is_in_neither_scheme(corpus, employee_document, administrator_document):
    assert RETIRED_PROJECT not in tag_scheme(employee_document).tags[PROJECT_DIMENSION]
    assert RETIRED_PROJECT not in tag_scheme(administrator_document).tags[PROJECT_DIMENSION]


def test_a_department_carried_only_by_administrator_only_documents_is_withheld_likewise(
    corpus, employee_document, administrator_document
):
    assert tag_scheme(employee_document).departments == ("People",)
    # D-66: an Administrator reads Employee-visible documents too, so both departments.
    assert tag_scheme(administrator_document).departments == ("Legal", "People")


def test_a_document_visible_to_both_roles_gets_the_intersection(corpus, employee):
    both = make_document(employee, "Site notice", list(ROLE_NAMES), "People")
    the_scheme = tag_scheme(both)
    assert RESTRICTED_PROJECT not in the_scheme.tags[PROJECT_DIMENSION]
    assert HELD_TOPIC not in the_scheme.tags[TOPIC_DIMENSION]
    assert SHARED_PROCESS in the_scheme.tags[PROCESS_DIMENSION]
    assert the_scheme.departments == ("People",)


def test_a_tag_linked_only_to_a_restricted_meeting_is_withheld_the_table_admits_both_source_types(
    corpus, employee_document, administrator_document
):
    meeting = Meeting.objects.create(
        title="Board meeting", meeting_date=datetime.date(2026, 11, 2),
        transcript_text="Minutes.", visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )
    board = Tag.objects.create(tag_name=BOARD_TOPIC, dimension=TOPIC_DIMENSION)
    link(board, MEETING_SOURCE_TYPE, meeting.pk)
    assert BOARD_TOPIC not in tag_scheme(employee_document).tags[TOPIC_DIMENSION]
    assert BOARD_TOPIC in tag_scheme(administrator_document).tags[TOPIC_DIMENSION]

    # Widen the meeting and the Employee-visible document's scheme gains the value.
    Meeting.objects.filter(pk=meeting.pk).update(visible_to_roles=list(ROLE_NAMES))
    assert BOARD_TOPIC in tag_scheme(employee_document).tags[TOPIC_DIMENSION]


# --- A grown Topic must be on a source the audience reads (D-105's dated note of 10 November 2026,
#     night, the lead's review and revision)
#
# An unlinked Topic admitted as vocabulary, beside a Topic linked only on restricted material and
# withheld, let apply, remove and apply again tell an Employee whether a restricted Topic name
# exists. 11a610f kept every unlinked Topic out; that changed the scheme Objective 05 was measured
# with, six seeded, unlinked Topics, so it was narrowed: only a Topic that came into use through a
# name (Tag.grown) is out once nothing links it. Seeded Topics, and Project and Process tags, are
# vocabulary while unlinked.

TOPIC_LINK_STATES = {"removed": {"removed": True}, "held": {"provisional": True}}


def test_an_unlinked_seeded_topic_is_in_every_scheme(employee, employee_document, administrator_document):
    Tag.objects.create(tag_name="night shifts", dimension=TOPIC_DIMENSION)  # as a seed makes it
    both = make_document(employee, "Site notice", list(ROLE_NAMES))
    nobody = make_document(employee, "Orphaned", [])
    for document in (employee_document, administrator_document, both, nobody):
        assert "night shifts" in tag_scheme(document).tags[TOPIC_DIMENSION]


def test_an_unlinked_grown_topic_is_in_no_scheme_but_an_empty_audiences(
    employee, employee_document, administrator_document
):
    """Renamed from 11a610f's test_an_unlinked_topic_is_in_no_scheme, whose Topic is now grown: the
    one kind of unlinked Topic that stays out."""
    Tag.objects.create(tag_name="night shifts", dimension=TOPIC_DIMENSION, grown=True)
    both = make_document(employee, "Site notice", list(ROLE_NAMES))
    for document in (employee_document, administrator_document, both):
        assert "night shifts" not in tag_scheme(document).tags[TOPIC_DIMENSION]
    # The empty-audience branch is unchanged: nobody reads that document, so nobody is protected.
    nobody = make_document(employee, "Orphaned", [])
    assert "night shifts" in tag_scheme(nobody).tags[TOPIC_DIMENSION]


def test_the_objective_05_scheme_only_seed_puts_all_its_topics_in_the_scheme(
    employee_document, administrator_document, monkeypatch
):
    """Objective 05 was measured on a database seeded by ``seed_objective02_tags.py --scheme-only``:
    the manifest's fourteen values as Tags rows and no links (D-106; the run record's "before the
    run"). The seed is run here as it ran there, and every value, its six Topics included, is in
    the scheme of a document of either audience, as it was when the runs began."""
    import django

    from scripts import seed_objective02_tags as seed

    monkeypatch.setattr(sys, "argv", ["seed_objective02_tags.py", "--scheme-only"])
    monkeypatch.setattr(sys, "path", list(sys.path))  # the script inserts the repository root
    monkeypatch.setattr(django, "setup", lambda: None)  # pytest has set Django up already

    assert seed.main() == 0

    assert not ContentTag.objects.exists()
    assert not Tag.objects.filter(grown=True).exists()
    seeded = set(Tag.objects.values_list("dimension", "tag_name"))
    topics = {name for dimension, name in seeded if dimension == TOPIC_DIMENSION}
    assert len(topics) == 6  # compliance, finance, people, safety, technology, workplace
    for document in (employee_document, administrator_document):
        the_scheme = tag_scheme(document)
        assert set(the_scheme.tags[TOPIC_DIMENSION]) == topics
        assert {(dimension, name) for dimension, names in the_scheme.tags.items() for name in names} == seeded


def test_unlinked_project_and_process_tags_are_still_vocabulary(employee_document, administrator_document):
    Tag.objects.create(tag_name="harbour upgrade", dimension=PROJECT_DIMENSION)
    Tag.objects.create(tag_name="purchasing", dimension=PROCESS_DIMENSION)
    for document in (employee_document, administrator_document):
        the_scheme = tag_scheme(document)
        assert "harbour upgrade" in the_scheme.tags[PROJECT_DIMENSION]
        assert "purchasing" in the_scheme.tags[PROCESS_DIMENSION]


@pytest.mark.parametrize("state", sorted(TOPIC_LINK_STATES))
def test_a_topic_whose_only_link_is_removed_or_held_on_a_readable_source_is_in(
    employee_document, administrator_document, state
):
    topic = Tag.objects.create(tag_name="night shifts", dimension=TOPIC_DIMENSION)
    link(topic, DOCUMENT_SOURCE_TYPE, employee_document.pk, applied_by=AI_APPLIED, confirmed=False,
         **TOPIC_LINK_STATES[state])
    # Both audiences read the Employee-visible document, an Administrator through D-66.
    for document in (employee_document, administrator_document):
        assert "night shifts" in tag_scheme(document).tags[TOPIC_DIMENSION]


@pytest.mark.parametrize("state", sorted(TOPIC_LINK_STATES))
def test_the_same_topic_on_a_restricted_source_is_out(employee_document, administrator_document, state):
    topic = Tag.objects.create(tag_name="night shifts", dimension=TOPIC_DIMENSION)
    link(topic, DOCUMENT_SOURCE_TYPE, administrator_document.pk, applied_by=AI_APPLIED,
         confirmed=False, **TOPIC_LINK_STATES[state])
    assert "night shifts" not in tag_scheme(employee_document).tags[TOPIC_DIMENSION]
    assert "night shifts" in tag_scheme(administrator_document).tags[TOPIC_DIMENSION]


# --- The edges of the audience -----------------------------------------------------------------


def test_an_empty_audience_gets_the_full_scheme(corpus, employee):
    nobody = make_document(employee, "Orphaned", [])
    the_scheme = tag_scheme(nobody)
    assert RESTRICTED_PROJECT in the_scheme.tags[PROJECT_DIMENSION]
    assert HELD_TOPIC in the_scheme.tags[TOPIC_DIMENSION]
    assert the_scheme.departments == ("Legal", "People")
    assert RETIRED_PROJECT not in the_scheme.tags[PROJECT_DIMENSION]


def test_a_role_scoping_does_not_know_fails_closed(corpus, employee):
    unknown = make_document(employee, "Audit file", ["Auditor"], "Audit")
    the_scheme = tag_scheme(unknown)
    assert the_scheme.departments == ()
    assert the_scheme.tags[PROJECT_DIMENSION] == ()
    assert the_scheme.tags[PROCESS_DIMENSION] == ()
    assert the_scheme.tags[TOPIC_DIMENSION] == (UNLINKED_TOPIC,)


def test_readability_is_decided_by_the_scoping_helpers_and_not_here(
    corpus, administrator_document, monkeypatch
):
    """With the helpers answering nothing, every linked value and every department is withheld:
    the function has no predicate of its own on ``visible_to_roles``."""
    monkeypatch.setattr(module, "scoped_documents", lambda *, role_name: Document.objects.none())
    monkeypatch.setattr(module, "scoped_meetings", lambda *, role_name: Meeting.objects.none())
    the_scheme = tag_scheme(administrator_document)
    assert the_scheme.departments == ()
    assert the_scheme.tags[PROJECT_DIMENSION] == ()
    assert the_scheme.tags[PROCESS_DIMENSION] == ()
    assert the_scheme.tags[TOPIC_DIMENSION] == (UNLINKED_TOPIC,)


# --- Shape -----------------------------------------------------------------------------------


def test_the_scheme_has_the_fixed_types_the_three_tag_dimensions_and_sorted_tuples(
    corpus, administrator_document
):
    the_scheme = tag_scheme(administrator_document)
    assert the_scheme.doc_types == DOCUMENT_TYPES
    assert set(the_scheme.tags) == set(REPOSITORY_TAG_DIMENSIONS)
    assert DEPARTMENT_DIMENSION not in the_scheme.tags
    assert "people" not in the_scheme.tags.get(DEPARTMENT_DIMENSION, ())
    for values in the_scheme.tags.values():
        assert isinstance(values, tuple)
        assert list(values) == sorted(values)
    assert isinstance(the_scheme.departments, tuple)
    assert list(the_scheme.departments) == sorted(the_scheme.departments)


def test_blank_departments_are_never_offered(corpus, employee, employee_document):
    make_document(employee, "Undepartmented", [EMPLOYEE_ROLE_NAME], "")
    assert "" not in tag_scheme(employee_document).departments
