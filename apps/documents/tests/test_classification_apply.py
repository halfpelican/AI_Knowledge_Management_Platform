"""``apply_classification``: FR-10's business logic as application code over the model's
suggestions (D-105).

Driven with ``DocumentClassification`` objects built by hand and schemes written by hand, so
these tests isolate the rules from the provider and from ``tag_scheme`` (which
test_classification_scheme.py covers). Every confidence is derived from
CLASSIFICATION_CONFIDENCE_THRESHOLD in classification_builders.py, never written as a number.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.constants import (
    AI_APPLIED,
    ASSIGNMENT_APPLIED,
    ASSIGNMENT_CONFIRMED,
    ASSIGNMENT_DISCARDED,
    ASSIGNMENT_PROVISIONAL,
    DEPARTMENT_DIMENSION,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.documents import classification as module
from apps.documents.classification import (
    InvalidClassification,
    apply_classification,
    confirm_classification,
)
from apps.documents.models import ContentTag, DocumentAnalysis, Tag

from .classification_builders import (
    ABOVE_THRESHOLD,
    AT_THRESHOLD,
    BELOW_THRESHOLD,
    POLICY,
    REPORT,
    classification,
    scheme,
)

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def make_tag(dimension, name, active=True):
    return Tag.objects.create(tag_name=name, dimension=dimension, active=active)


# --- Rule 2: the type and the threshold ----------------------------------------------------------


@pytest.mark.parametrize(
    ("confidence", "outcome", "effective"),
    [
        (BELOW_THRESHOLD, ASSIGNMENT_PROVISIONAL, None),
        (AT_THRESHOLD, ASSIGNMENT_APPLIED, POLICY),
        (ABOVE_THRESHOLD, ASSIGNMENT_APPLIED, POLICY),
    ],
    ids=["below", "at", "above"],
)
def test_the_type_is_provisional_below_the_threshold_and_applied_at_it(
    document, confidence, outcome, effective
):
    analysis = apply_classification(
        document, classification(doc_type=POLICY, type_confidence=confidence), scheme=scheme()
    )
    analysis.refresh_from_db()
    assert analysis.machine_doc_type == POLICY
    assert analysis.machine_doc_type_confidence == Decimal(str(confidence))
    assert analysis.doc_type_outcome == outcome
    assert analysis.doc_type == effective
    assert analysis.user_edited is False


def test_a_type_outside_the_fixed_list_is_refused_and_nothing_is_written(document):
    with pytest.raises(InvalidClassification):
        apply_classification(document, classification(doc_type="Memo"), scheme=scheme())
    assert not DocumentAnalysis.objects.filter(document=document).exists()


# --- Rule 3: the department, the scheme and the threshold ----------------------------------------


@pytest.mark.parametrize(
    ("confidence", "outcome", "written"),
    [
        (BELOW_THRESHOLD, ASSIGNMENT_PROVISIONAL, False),
        (AT_THRESHOLD, ASSIGNMENT_APPLIED, True),
        (ABOVE_THRESHOLD, ASSIGNMENT_APPLIED, True),
    ],
    ids=["below", "at", "above"],
)
def test_a_department_in_the_scheme_is_provisional_below_the_threshold_and_written_at_it(
    document, confidence, outcome, written
):
    analysis = apply_classification(
        document,
        classification(department="Finance", department_confidence=confidence),
        scheme=scheme(departments=["Finance"]),
    )
    document.refresh_from_db()
    assert analysis.machine_department == "Finance"
    assert analysis.machine_department_confidence == Decimal(str(confidence))
    assert analysis.department_outcome == outcome
    assert document.department == ("Finance" if written else "")


@pytest.mark.parametrize(
    "suggested", ["Legal", "finance", "Fin ance", ""], ids=["unknown", "case", "spacing", "empty"]
)
def test_a_department_outside_the_scheme_is_discarded_and_nothing_is_written(document, suggested):
    analysis = apply_classification(
        document,
        classification(department=suggested, department_confidence=ABOVE_THRESHOLD),
        scheme=scheme(departments=["Finance"]),
    )
    document.refresh_from_db()
    assert analysis.department_outcome == ASSIGNMENT_DISCARDED
    assert analysis.machine_department == suggested.strip()
    assert document.department == ""


def test_the_department_is_compared_after_stripping(document):
    analysis = apply_classification(
        document, classification(department="  Finance "), scheme=scheme(departments=["Finance"])
    )
    document.refresh_from_db()
    assert analysis.department_outcome == ASSIGNMENT_APPLIED
    assert analysis.machine_department == "Finance"
    assert document.department == "Finance"


# --- Rule 3, continued: the machine fills only a blank department (D-105's note, 10 November) ------


def test_a_department_the_uploader_gave_is_kept_and_a_different_suggestion_is_held(document):
    document.department = "Operations"
    document.save(update_fields=["department"])
    analysis = apply_classification(
        document,
        classification(department="Finance", department_confidence=ABOVE_THRESHOLD),
        scheme=scheme(departments=["Finance", "Operations"]),
    )
    document.refresh_from_db()
    assert document.department == "Operations"
    assert analysis.machine_department == "Finance"
    assert analysis.department_outcome == ASSIGNMENT_PROVISIONAL


def test_a_suggestion_matching_the_department_already_there_is_applied_with_nothing_written(document):
    document.department = "Finance"
    document.save(update_fields=["department"])
    analysis = apply_classification(
        document,
        classification(department="Finance", department_confidence=AT_THRESHOLD),
        scheme=scheme(departments=["Finance"]),
    )
    document.refresh_from_db()
    assert document.department == "Finance"
    assert analysis.department_outcome == ASSIGNMENT_APPLIED


def test_a_department_an_earlier_run_wrote_is_not_replaced_by_a_later_run(document):
    departments = ["Finance", "Operations"]
    apply_classification(
        document,
        classification(department="Finance", department_confidence=ABOVE_THRESHOLD),
        scheme=scheme(departments=departments),
    )
    analysis = apply_classification(
        document,
        classification(department="Operations", department_confidence=ABOVE_THRESHOLD),
        scheme=scheme(departments=departments),
    )
    document.refresh_from_db()
    assert document.department == "Finance"
    assert analysis.machine_department == "Operations"
    assert analysis.department_outcome == ASSIGNMENT_PROVISIONAL


def test_confirming_a_suggestion_held_against_a_given_department_replaces_it(document):
    document.department = "Operations"
    document.save(update_fields=["department"])
    apply_classification(
        document,
        classification(department="Finance", department_confidence=ABOVE_THRESHOLD),
        scheme=scheme(departments=["Finance", "Operations"]),
    )
    analysis = confirm_classification(document)
    document.refresh_from_db()
    assert document.department == "Finance"
    assert analysis.department_outcome == ASSIGNMENT_CONFIRMED


# --- Rule 4: tags in the scheme ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("confidence", "provisional"),
    [(BELOW_THRESHOLD, True), (AT_THRESHOLD, False), (ABOVE_THRESHOLD, False)],
    ids=["below", "at", "above"],
)
def test_an_in_scheme_tag_is_linked_as_ai_applied_and_provisional_only_below_the_threshold(
    document, confidence, provisional
):
    tag = make_tag(PROJECT_DIMENSION, "bridge maintenance")
    apply_classification(
        document,
        classification(tags=[(PROJECT_DIMENSION, "Bridge  Maintenance", confidence)]),
        scheme=scheme(project=["bridge maintenance"]),
    )
    link = links_of(document).get()
    assert link.tag == tag
    assert link.applied_by == AI_APPLIED
    assert link.confirmed is False
    assert link.provisional is provisional
    assert link.confidence == Decimal(str(confidence))


def test_a_tag_a_person_applied_and_confirmed_is_not_altered_by_a_rerun(document):
    tag = make_tag(TOPIC_DIMENSION, "leave")
    link = ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=USER_APPLIED, confirmed=True,
    )
    apply_classification(
        document,
        classification(tags=[(TOPIC_DIMENSION, "Leave", BELOW_THRESHOLD)]),
        scheme=scheme(topic=["leave"]),
    )
    link.refresh_from_db()
    assert (link.applied_by, link.confirmed, link.provisional, link.confidence) == (
        USER_APPLIED, True, False, None,
    )
    assert links_of(document).count() == 1


def test_a_confirmed_ai_tag_is_not_altered_by_a_rerun_either(document):
    tag = make_tag(TOPIC_DIMENSION, "leave")
    link = ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=AI_APPLIED, confirmed=True, provisional=False,
        confidence=Decimal(str(ABOVE_THRESHOLD)),
    )
    apply_classification(
        document,
        classification(tags=[(TOPIC_DIMENSION, "leave", BELOW_THRESHOLD)]),
        scheme=scheme(topic=["leave"]),
    )
    link.refresh_from_db()
    assert (link.confirmed, link.provisional, link.confidence) == (
        True, False, Decimal(str(ABOVE_THRESHOLD)),
    )


def test_an_unconfirmed_ai_link_takes_the_new_confidence_and_provisional_flag(document):
    make_tag(PROJECT_DIMENSION, "bridge maintenance")
    the_scheme = scheme(project=["bridge maintenance"])
    apply_classification(
        document,
        classification(tags=[(PROJECT_DIMENSION, "bridge maintenance", ABOVE_THRESHOLD)]),
        scheme=the_scheme,
    )
    first = links_of(document).get()
    assert first.provisional is False
    apply_classification(
        document,
        classification(tags=[(PROJECT_DIMENSION, "bridge maintenance", BELOW_THRESHOLD)]),
        scheme=the_scheme,
    )
    second = links_of(document).get()
    assert second.pk == first.pk
    assert second.provisional is True
    assert second.confidence == Decimal(str(BELOW_THRESHOLD))


def test_links_the_new_run_does_not_mention_are_left_alone(document):
    make_tag(PROJECT_DIMENSION, "bridge maintenance")
    make_tag(PROCESS_DIMENSION, "procurement")
    the_scheme = scheme(project=["bridge maintenance"], process=["procurement"])
    apply_classification(
        document,
        classification(tags=[(PROJECT_DIMENSION, "bridge maintenance", ABOVE_THRESHOLD)]),
        scheme=the_scheme,
    )
    apply_classification(
        document,
        classification(tags=[(PROCESS_DIMENSION, "procurement", ABOVE_THRESHOLD)]),
        scheme=the_scheme,
    )
    assert set(links_of(document).values_list("tag__tag_name", flat=True)) == {
        "bridge maintenance", "procurement",
    }


def test_a_tag_deactivated_since_the_scheme_was_built_is_treated_as_outside_it(document):
    make_tag(PROJECT_DIMENSION, "old project", active=False)
    analysis = apply_classification(
        document,
        classification(tags=[(PROJECT_DIMENSION, "old project", ABOVE_THRESHOLD)]),
        scheme=scheme(project=["old project"]),
    )
    assert not links_of(document).exists()
    assert analysis.discarded_suggestions == [
        {"dimension": PROJECT_DIMENSION, "value": "old project", "confidence": ABOVE_THRESHOLD}
    ]


# --- Rule 4: the scheme clause, per dimension ---------------------------------------------------


def test_a_topic_outside_the_scheme_is_proposed_and_no_tag_row_exists_for_it(document):
    analysis = apply_classification(
        document,
        classification(tags=[(TOPIC_DIMENSION, "Budget  Planning", ABOVE_THRESHOLD)]),
        scheme=scheme(),
    )
    assert analysis.proposed_topics == [{"value": "budget planning", "confidence": ABOVE_THRESHOLD}]
    assert analysis.discarded_suggestions == []
    assert not Tag.objects.filter(tag_name="budget planning").exists()
    assert not links_of(document).exists()


@pytest.mark.parametrize("dimension", [PROJECT_DIMENSION, PROCESS_DIMENSION])
def test_a_project_or_process_outside_the_scheme_is_discarded_and_recorded(document, dimension):
    analysis = apply_classification(
        document,
        classification(tags=[(dimension, "Harbour  Upgrade", ABOVE_THRESHOLD)]),
        scheme=scheme(),
    )
    assert analysis.discarded_suggestions == [
        {"dimension": dimension, "value": "harbour upgrade", "confidence": ABOVE_THRESHOLD}
    ]
    assert analysis.proposed_topics == []
    assert not Tag.objects.filter(tag_name="harbour upgrade").exists()
    assert not links_of(document).exists()


def test_a_suggestion_in_a_dimension_outside_the_three_is_ignored(document):
    analysis = apply_classification(
        document,
        classification(
            tags=[
                (DEPARTMENT_DIMENSION, "Finance", ABOVE_THRESHOLD),
                ("Colour", "blue", ABOVE_THRESHOLD),
                (TOPIC_DIMENSION, "   ", ABOVE_THRESHOLD),
            ]
        ),
        scheme=scheme(departments=["Finance"]),
    )
    assert analysis.proposed_topics == []
    assert analysis.discarded_suggestions == []
    assert not links_of(document).exists()
    assert Tag.objects.count() == 0


def test_proposed_topics_are_deduplicated_by_normalised_value_and_replaced_on_a_rerun(document):
    first = apply_classification(
        document,
        classification(
            tags=[
                (TOPIC_DIMENSION, "Budget Planning", BELOW_THRESHOLD),
                (TOPIC_DIMENSION, " budget   planning ", ABOVE_THRESHOLD),
            ]
        ),
        scheme=scheme(),
    )
    assert first.proposed_topics == [{"value": "budget planning", "confidence": ABOVE_THRESHOLD}]
    second = apply_classification(
        document,
        classification(tags=[(TOPIC_DIMENSION, "Risk Appetite", ABOVE_THRESHOLD)]),
        scheme=scheme(),
    )
    assert second.proposed_topics == [{"value": "risk appetite", "confidence": ABOVE_THRESHOLD}]
    assert not Tag.objects.filter(dimension=TOPIC_DIMENSION).exists()


# --- Correction: user_edited, and one row per document -------------------------------------------


def test_user_edited_protects_the_effective_values_while_the_machine_values_still_update(document):
    the_scheme = scheme(departments=["Finance", "Legal"])
    apply_classification(
        document,
        classification(
            doc_type=POLICY, type_confidence=ABOVE_THRESHOLD,
            department="Finance", department_confidence=ABOVE_THRESHOLD,
        ),
        scheme=the_scheme,
    )
    confirm_classification(document)  # as it stands

    analysis = apply_classification(
        document,
        classification(
            doc_type=REPORT, type_confidence=BELOW_THRESHOLD,
            department="Legal", department_confidence=ABOVE_THRESHOLD,
            model="stub-chat-2", input_truncated=True,
        ),
        scheme=the_scheme,
    )
    document.refresh_from_db()
    assert analysis.user_edited is True
    # The person's decisions stand.
    assert (analysis.doc_type, analysis.doc_type_outcome) == (POLICY, ASSIGNMENT_CONFIRMED)
    assert (document.department, analysis.department_outcome) == ("Finance", ASSIGNMENT_CONFIRMED)
    # The machine's new assignment is still recorded alongside them.
    assert analysis.machine_doc_type == REPORT
    assert analysis.machine_doc_type_confidence == Decimal(str(BELOW_THRESHOLD))
    assert analysis.machine_department == "Legal"
    assert analysis.machine_department_confidence == Decimal(str(ABOVE_THRESHOLD))
    assert (analysis.model, analysis.input_truncated) == ("stub-chat-2", True)


def test_one_analysis_per_document_a_second_apply_updates_it(document):
    first = apply_classification(document, classification(doc_type=POLICY), scheme=scheme())
    second = apply_classification(document, classification(doc_type=REPORT), scheme=scheme())
    assert second.pk == first.pk
    assert DocumentAnalysis.objects.filter(document=document).count() == 1
    document.refresh_from_db()
    assert document.analysis.machine_doc_type == REPORT


def test_the_run_itself_is_recorded(document):
    before = timezone.now()
    analysis = apply_classification(
        document, classification(model="gemma3:4b", input_truncated=True), scheme=scheme()
    )
    assert (analysis.model, analysis.input_truncated) == ("gemma3:4b", True)
    assert before <= analysis.classified_at <= timezone.now()


class Boom(Exception):
    pass


def test_apply_is_one_transaction_a_failure_part_way_leaves_nothing(document, monkeypatch):
    """The department is written before the tags are linked; a failure linking them must take
    the department write and the analysis row back with it (CLAUDE.md invariant 9)."""
    make_tag(PROJECT_DIMENSION, "bridge maintenance")

    def boom(*args, **kwargs):
        raise Boom()

    monkeypatch.setattr(module, "_link_tag", boom)
    with pytest.raises(Boom):
        apply_classification(
            document,
            classification(
                department="Finance", department_confidence=ABOVE_THRESHOLD,
                tags=[(PROJECT_DIMENSION, "bridge maintenance", ABOVE_THRESHOLD)],
            ),
            scheme=scheme(departments=["Finance"], project=["bridge maintenance"]),
        )
    document.refresh_from_db()
    assert document.department == ""
    assert not DocumentAnalysis.objects.filter(document=document).exists()
    assert not links_of(document).exists()
