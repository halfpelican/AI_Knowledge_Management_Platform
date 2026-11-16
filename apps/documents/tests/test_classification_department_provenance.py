"""Whose department it is: ``DocumentAnalysis.department_applied_by`` (FR-10, D-119 finding 10).

FR-10's provenance clause tells what the machine applied from what a person did. The department
outcome cannot: since D-105's note of 10 November the machine fills only a blank department, and
"applied" is recorded both when a run wrote its suggestion into a blank department and when the
suggestion merely equalled the department the uploader typed. The interface labelled both
"Suggested by AI", although in the second case a person supplied the value. ``department_applied_by``
says whose value the department is, in the tags' provenance vocabulary: "user", "ai", or null for
none.
"""

import pytest

from apps.core.constants import (
    AI_APPLIED,
    ASSIGNMENT_APPLIED,
    ASSIGNMENT_CONFIRMED,
    ASSIGNMENT_DISCARDED,
    ASSIGNMENT_PROVISIONAL,
    USER_APPLIED,
)
from apps.documents.classification import apply_classification, confirm_classification

from .classification_builders import ABOVE_THRESHOLD, BELOW_THRESHOLD, classification, scheme

pytestmark = pytest.mark.django_db

DEPARTMENTS = ("Finance", "Legal")


def run(document, department, confidence=ABOVE_THRESHOLD):
    return apply_classification(
        document,
        classification(department=department, department_confidence=confidence),
        scheme=scheme(departments=DEPARTMENTS),
    )


def typed(document, value):
    """The department as the uploader typed it at upload, before any classification."""
    document.department = value
    document.save(update_fields=["department"])
    return document


def test_a_typed_department_the_machine_matched_is_the_persons(document):
    """Finding 10's case: the outcome is "applied", and the value is still the uploader's."""
    typed(document, "Finance")
    analysis = run(document, "Finance")
    assert analysis.department_outcome == ASSIGNMENT_APPLIED
    assert analysis.department_applied_by == USER_APPLIED


def test_a_department_the_machine_wrote_into_a_blank_is_the_machines(document):
    analysis = run(document, "Finance")
    document.refresh_from_db()
    assert document.department == "Finance"
    assert (analysis.department_outcome, analysis.department_applied_by) == (
        ASSIGNMENT_APPLIED, AI_APPLIED,
    )


def test_a_rerun_matching_the_machines_own_earlier_value_keeps_it_the_machines(document):
    """The second run finds the department equal to its suggestion, exactly as in finding 10's
    case, and the record of the first run is what tells the two apart."""
    run(document, "Finance")
    analysis = run(document, "Finance")
    assert (analysis.department_outcome, analysis.department_applied_by) == (
        ASSIGNMENT_APPLIED, AI_APPLIED,
    )


def test_a_typed_department_held_against_a_different_suggestion_stays_the_persons(document):
    typed(document, "Legal")
    analysis = run(document, "Finance")
    assert (analysis.department_outcome, analysis.department_applied_by) == (
        ASSIGNMENT_PROVISIONAL, USER_APPLIED,
    )


def test_a_typed_department_beside_a_discarded_suggestion_stays_the_persons(document):
    typed(document, "Legal")
    analysis = run(document, "Marketing")  # not in the scheme
    assert (analysis.department_outcome, analysis.department_applied_by) == (
        ASSIGNMENT_DISCARDED, USER_APPLIED,
    )


def test_a_blank_department_is_nobodys(document):
    analysis = run(document, "Finance", BELOW_THRESHOLD)  # held, so nothing is written
    document.refresh_from_db()
    assert document.department == ""
    assert (analysis.department_outcome, analysis.department_applied_by) == (
        ASSIGNMENT_PROVISIONAL, None,
    )


@pytest.mark.parametrize(("edited", "expected"), [("Operations", USER_APPLIED), ("", None)],
                         ids=["value", "blank"])
def test_a_department_a_person_edits_is_the_persons_and_a_blank_one_nobodys(document, edited, expected):
    run(document, "Finance")  # the machine's value first, so the edit has something to replace
    analysis = confirm_classification(document, department=edited)
    assert analysis.department_outcome == ASSIGNMENT_CONFIRMED
    assert analysis.department_applied_by == expected


def test_confirming_a_held_suggestion_keeps_it_the_machines(document):
    """A person accepting the machine's held value writes it and confirms it; its provenance stays
    the machine's, as a confirmed AI tag keeps ``applied_by="ai"``."""
    run(document, "Finance", BELOW_THRESHOLD)
    analysis = confirm_classification(document)
    document.refresh_from_db()
    assert document.department == "Finance"
    assert (analysis.department_outcome, analysis.department_applied_by) == (
        ASSIGNMENT_CONFIRMED, AI_APPLIED,
    )


def test_after_a_person_edits_a_rerun_leaves_the_provenance_alone(document):
    run(document, "Finance")
    confirm_classification(document, department="Legal")
    analysis = run(document, "Legal")
    assert analysis.department_applied_by == USER_APPLIED
