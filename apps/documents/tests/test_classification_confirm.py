"""A person's decisions over a classification: ``confirm_classification``, ``confirm_tag``,
``reject_tag``, ``confirm_proposed_tag`` and ``reject_proposed_tag`` (FR-10, D-105, D-128).

FR-10: assignments below the threshold are "presented for confirmation rather than applied
silently"; AI tags and a person's "may be accepted or removed in a single action"; "any value a
user edits [is] retained and is not overwritten by later reprocessing". Since D-128 a value outside
the scheme below the threshold, in Project, Process or Topic, is held as a proposal and its Tag is
created, or brought back, only when a person confirms it (FR-10 said this of a new Topic alone).
Each function answers ``NotOnThisDocument`` for an id or value that is not this document's, which
the route turns into the same 404 as a document outside the caller's scope (D-46).
"""

import uuid
from decimal import Decimal

import pytest

from apps.core.constants import (
    AI_APPLIED,
    ASSIGNMENT_APPLIED,
    ASSIGNMENT_CONFIRMED,
    ASSIGNMENT_DISCARDED,
    ASSIGNMENT_PROVISIONAL,
    EMPLOYEE_ROLE_NAME,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.documents.classification import (
    InvalidClassification,
    NotOnThisDocument,
    apply_classification,
    confirm_classification,
    confirm_proposed_tag,
    confirm_tag,
    reject_proposed_tag,
    reject_tag,
)
from apps.documents.models import ContentTag, Document, DocumentAnalysis, Tag

from .classification_builders import (
    ABOVE_THRESHOLD,
    BELOW_THRESHOLD,
    POLICY,
    REPORT,
    classification,
    scheme,
)

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
DEPARTMENTS = ("Finance", "Legal")


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


@pytest.fixture
def other_document(employee):
    return Document.objects.create(
        title="Another document", file_type="txt", uploaded_by=employee,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )


def classified(document, *, type_confidence=ABOVE_THRESHOLD, department="Finance",
               department_confidence=ABOVE_THRESHOLD, tags=()):
    return apply_classification(
        document,
        classification(
            doc_type=POLICY, type_confidence=type_confidence,
            department=department, department_confidence=department_confidence, tags=tags,
        ),
        scheme=scheme(departments=DEPARTMENTS, project=["bridge maintenance"]),
    )


# --- confirm_classification ----------------------------------------------------------------------


def test_confirming_as_it_stands_applies_a_provisional_type_and_marks_both_confirmed(document):
    classified(document, type_confidence=BELOW_THRESHOLD)
    analysis = confirm_classification(document)
    document.refresh_from_db()
    assert (analysis.doc_type, analysis.doc_type_outcome) == (POLICY, ASSIGNMENT_CONFIRMED)
    assert (document.department, analysis.department_outcome) == ("Finance", ASSIGNMENT_CONFIRMED)
    assert analysis.user_edited is True
    assert analysis.machine_doc_type == POLICY  # retained alongside


def test_an_edited_type_is_written_and_the_machine_type_is_kept(document):
    classified(document)
    analysis = confirm_classification(document, doc_type=REPORT)
    assert (analysis.doc_type, analysis.doc_type_outcome) == (REPORT, ASSIGNMENT_CONFIRMED)
    assert analysis.machine_doc_type == POLICY
    assert analysis.user_edited is True


def test_a_type_outside_the_fixed_list_is_refused_and_nothing_changes(document):
    classified(document)
    with pytest.raises(InvalidClassification):
        confirm_classification(document, doc_type="Memo")
    analysis = DocumentAnalysis.objects.get(document=document)
    assert (analysis.doc_type, analysis.doc_type_outcome) == (POLICY, ASSIGNMENT_APPLIED)
    assert analysis.user_edited is False


def test_confirming_a_provisional_department_writes_it_to_the_document(document):
    classified(document, department_confidence=BELOW_THRESHOLD)
    document.refresh_from_db()
    assert document.department == ""
    analysis = confirm_classification(document)
    document.refresh_from_db()
    assert document.department == "Finance"
    assert analysis.department_outcome == ASSIGNMENT_CONFIRMED


def test_confirming_a_discarded_department_leaves_things_as_they_are(document):
    classified(document, department="Marketing")  # not in the scheme
    analysis = confirm_classification(document)
    document.refresh_from_db()
    assert document.department == ""
    assert analysis.department_outcome == ASSIGNMENT_DISCARDED
    assert analysis.user_edited is True


@pytest.mark.parametrize("edited", ["Operations", "  Operations  ", ""], ids=["value", "padded", "blank"])
def test_an_edited_department_is_written_as_given_after_stripping(document, edited):
    classified(document)
    analysis = confirm_classification(document, department=edited)
    document.refresh_from_db()
    assert document.department == edited.strip()
    assert analysis.department_outcome == ASSIGNMENT_CONFIRMED
    assert analysis.machine_department == "Finance"


def test_a_document_without_a_classification_cannot_be_confirmed(document):
    with pytest.raises(NotOnThisDocument):
        confirm_classification(document)
    with pytest.raises(NotOnThisDocument):
        confirm_classification(document, doc_type=POLICY)


def test_after_a_confirmation_a_rerun_changes_nothing_a_person_decided(document):
    classified(document)
    confirm_classification(document, doc_type=REPORT, department="Operations")
    analysis = classified(document, type_confidence=ABOVE_THRESHOLD, department="Legal")
    document.refresh_from_db()
    assert (analysis.doc_type, analysis.doc_type_outcome) == (REPORT, ASSIGNMENT_CONFIRMED)
    assert (document.department, analysis.department_outcome) == ("Operations", ASSIGNMENT_CONFIRMED)
    assert (analysis.machine_doc_type, analysis.machine_department) == (POLICY, "Legal")


# --- confirm_tag and reject_tag ------------------------------------------------------------------


@pytest.fixture
def held_link(document):
    Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    classified(document, tags=[(PROJECT_DIMENSION, "bridge maintenance", BELOW_THRESHOLD)])
    link = links_of(document).get()
    assert (link.provisional, link.confirmed) == (True, False)
    return link


def test_confirming_a_held_tag_applies_it_and_keeps_its_provenance(document, held_link):
    link = confirm_tag(document, held_link.pk)
    link.refresh_from_db()
    assert (link.confirmed, link.provisional, link.applied_by) == (True, False, AI_APPLIED)
    assert link.confidence == Decimal(str(BELOW_THRESHOLD))


def test_rejecting_an_ai_tag_keeps_the_link_removed_and_keeps_the_vocabulary(document, held_link):
    """Until D-105's dated note of 10 November 2026 (night) this deleted the link. An AI link is now
    kept, marked removed, with the machine's assignment (test_classification_removal.py)."""
    reject_tag(document, held_link.pk)
    kept = links_of(document).get()
    assert (kept.pk, kept.removed, kept.provisional) == (held_link.pk, True, True)
    assert Tag.objects.filter(tag_name="bridge maintenance").exists()


def test_a_tag_on_another_document_is_not_on_this_one(document, other_document, held_link):
    with pytest.raises(NotOnThisDocument):
        confirm_tag(other_document, held_link.pk)
    with pytest.raises(NotOnThisDocument):
        reject_tag(other_document, held_link.pk)
    held_link.refresh_from_db()
    assert (held_link.confirmed, held_link.provisional) == (False, True)


@pytest.mark.parametrize("bad_id", [uuid.uuid4(), "not-a-uuid", ""], ids=["unknown", "malformed", "empty"])
def test_an_id_that_is_not_a_link_is_not_on_this_document(document, held_link, bad_id):
    with pytest.raises(NotOnThisDocument):
        confirm_tag(document, bad_id)
    with pytest.raises(NotOnThisDocument):
        reject_tag(document, bad_id)
    assert links_of(document).count() == 1


def test_a_persons_own_tag_is_removed_in_the_same_action_and_kept_marked_removed(document):
    """Kept, as an AI link is, since the requirements re-audit of ``5377e3a``: FR-10's correction
    clause, "not overwritten by later reprocessing" (D-105's dated note)."""
    tag = Tag.objects.create(tag_name="leave", dimension=TOPIC_DIMENSION)
    link = ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=USER_APPLIED, confirmed=True,
    )
    reject_tag(document, link.pk)
    kept = links_of(document).get()
    assert (kept.pk, kept.removed, kept.applied_by, kept.confirmed) == (link.pk, True, USER_APPLIED, True)


# --- Proposed tags (D-128; proposed topics until then) -------------------------------------------

PROPOSAL = {"dimension": TOPIC_DIMENSION, "value": "budget planning", "confidence": BELOW_THRESHOLD}


@pytest.fixture
def proposed(document):
    """Below the threshold, so held (D-128: at or above it the value would be created and applied)."""
    analysis = classified(document, tags=[(TOPIC_DIMENSION, "Budget  Planning", BELOW_THRESHOLD)])
    assert analysis.proposed_tags == [PROPOSAL]
    return analysis


def test_confirming_a_proposed_topic_is_when_the_tag_is_created(document, proposed):
    assert not Tag.objects.filter(tag_name="budget planning").exists()
    # The un-normalised form works.
    link = confirm_proposed_tag(document, TOPIC_DIMENSION, "Budget Planning")
    tag = Tag.objects.get(tag_name="budget planning", dimension=TOPIC_DIMENSION)
    assert tag.active is True
    assert link.tag == tag
    assert (link.applied_by, link.confirmed, link.provisional) == (AI_APPLIED, True, False)
    assert link.confidence == Decimal(str(BELOW_THRESHOLD))
    proposed.refresh_from_db()
    assert proposed.proposed_tags == []


def test_confirming_a_proposed_topic_reuses_and_reactivates_an_existing_tag(document, proposed):
    retired = Tag.objects.create(tag_name="budget planning", dimension=TOPIC_DIMENSION, active=False)
    link = confirm_proposed_tag(document, TOPIC_DIMENSION, "budget planning")
    assert link.tag == retired
    retired.refresh_from_db()
    assert retired.active is True
    assert Tag.objects.filter(tag_name="budget planning").count() == 1


def test_rejecting_a_proposed_topic_creates_nothing(document, proposed):
    reject_proposed_tag(document, TOPIC_DIMENSION, "budget planning")
    proposed.refresh_from_db()
    assert proposed.proposed_tags == []
    assert not Tag.objects.filter(tag_name="budget planning").exists()
    assert not links_of(document).exists()


def test_a_value_that_was_not_proposed_is_not_on_this_document(document, other_document, proposed):
    with pytest.raises(NotOnThisDocument):
        confirm_proposed_tag(document, TOPIC_DIMENSION, "risk appetite")
    with pytest.raises(NotOnThisDocument):
        reject_proposed_tag(document, TOPIC_DIMENSION, "risk appetite")
    # D-128: the proposal is matched by dimension and value, so the same value under another
    # dimension is not proposed.
    with pytest.raises(NotOnThisDocument):
        confirm_proposed_tag(document, PROJECT_DIMENSION, "budget planning")
    with pytest.raises(NotOnThisDocument):
        reject_proposed_tag(document, PROJECT_DIMENSION, "budget planning")
    # The proposal belongs to ``document``; the other document has no classification at all.
    with pytest.raises(NotOnThisDocument):
        confirm_proposed_tag(other_document, TOPIC_DIMENSION, "budget planning")
    with pytest.raises(NotOnThisDocument):
        reject_proposed_tag(other_document, TOPIC_DIMENSION, "budget planning")
    assert not Tag.objects.filter(tag_name__in=["risk appetite", "budget planning"]).exists()
    proposed.refresh_from_db()
    assert proposed.proposed_tags == [PROPOSAL]


def test_a_confirmed_topic_survives_a_rerun_as_a_confirmed_link(document, proposed):
    confirm_proposed_tag(document, TOPIC_DIMENSION, "budget planning")
    # The next run sees the value in the scheme and the link already confirmed, and suggests it at
    # a confidence that would change an unconfirmed link's.
    apply_classification(
        document,
        classification(tags=[(TOPIC_DIMENSION, "budget planning", round(BELOW_THRESHOLD - 0.1, 3))]),
        scheme=scheme(departments=DEPARTMENTS, topic=["budget planning"]),
    )
    link = links_of(document).get()
    assert (link.confirmed, link.provisional) == (True, False)
    assert link.confidence == Decimal(str(BELOW_THRESHOLD))
