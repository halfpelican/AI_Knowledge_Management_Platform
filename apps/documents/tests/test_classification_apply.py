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
    CLASSIFICATION_CONFIDENCE_THRESHOLD,
    CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL,
    CLASSIFICATION_DEPARTMENT_CONFIDENCE_THRESHOLD_BY_MODEL,
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
    EPSILON,
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


# --- D-122: the threshold is the classifying model's own -----------------------------------------

HAIKU = "claude-haiku-5-5"
BETWEEN_THE_TWO_VALUES = 0.8  # at or above Haiku's 0.72, below CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_the_confidence_threshold_is_the_classifying_models_own():
    """D-122: a listed model gets its value; any other, gemma3:4b and the stub included, the default."""
    assert module.confidence_threshold(HAIKU) == CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL[HAIKU]
    assert module.confidence_threshold("gemma3:4b") == CLASSIFICATION_CONFIDENCE_THRESHOLD
    assert module.confidence_threshold("stub-chat") == CLASSIFICATION_CONFIDENCE_THRESHOLD


@pytest.mark.parametrize(
    ("model", "outcome", "effective", "provisional_tag"),
    [(HAIKU, ASSIGNMENT_APPLIED, POLICY, False), ("gemma3:4b", ASSIGNMENT_PROVISIONAL, None, True)],
    ids=["haiku", "unlisted"],
)
def test_assignments_between_the_two_values_follow_the_classifying_model(
    document, model, outcome, effective, provisional_tag
):
    """D-122: at 0.80 the type and a tag apply on Haiku's 0.72, and the department on Haiku's own 0.30
    (D-129), and all three are held on 0.95."""
    # The premise: 0.80 sits between the two values, so the model alone decides.
    assert (CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL[HAIKU] <= BETWEEN_THE_TWO_VALUES
            < CLASSIFICATION_CONFIDENCE_THRESHOLD)
    make_tag(PROJECT_DIMENSION, "bridge maintenance")
    analysis = apply_classification(
        document,
        classification(doc_type=POLICY, type_confidence=BETWEEN_THE_TWO_VALUES,
                       department="Finance", department_confidence=BETWEEN_THE_TWO_VALUES,
                       tags=[(PROJECT_DIMENSION, "bridge maintenance", BETWEEN_THE_TWO_VALUES)],
                       model=model),
        scheme=scheme(departments=["Finance"], project=["bridge maintenance"]),
    )
    analysis.refresh_from_db()
    document.refresh_from_db()
    assert analysis.model == model
    assert analysis.doc_type_outcome == outcome
    assert analysis.doc_type == effective
    assert analysis.department_outcome == outcome
    assert document.department == ("Finance" if effective else "")
    assert links_of(document).get().provisional is provisional_tag


# --- D-129: a department has a threshold of its own --------------------------------------------------

HAIKU_DEPARTMENT_THRESHOLD = CLASSIFICATION_DEPARTMENT_CONFIDENCE_THRESHOLD_BY_MODEL[HAIKU]  # 0.30
BETWEEN_THE_HAIKU_VALUES = 0.5  # at or above Haiku's department 0.30, below its shared 0.72


def test_the_department_threshold_is_its_own_on_haiku_and_the_shared_value_for_an_unlisted_model():
    """D-129: Haiku's department value from its own map; any other model's department falls back to
    that model's shared value, which the type and the tags keep."""
    assert module.department_threshold(HAIKU) == HAIKU_DEPARTMENT_THRESHOLD == 0.30
    assert module.confidence_threshold(HAIKU) == CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL[HAIKU] == 0.72
    for unlisted in ("gemma3:4b", "stub-chat"):
        assert module.department_threshold(unlisted) == module.confidence_threshold(unlisted)
        assert module.department_threshold(unlisted) == CLASSIFICATION_CONFIDENCE_THRESHOLD


@pytest.mark.parametrize(
    ("confidence", "outcome", "written"),
    [
        (HAIKU_DEPARTMENT_THRESHOLD, ASSIGNMENT_APPLIED, True),
        (round(HAIKU_DEPARTMENT_THRESHOLD - EPSILON, 3), ASSIGNMENT_PROVISIONAL, False),
        (round(HAIKU_DEPARTMENT_THRESHOLD - 0.01, 2), ASSIGNMENT_PROVISIONAL, False),
    ],
    ids=["at-0.30", "just-below", "0.29"],
)
def test_a_haiku_department_at_its_threshold_fills_a_blank_department_and_one_below_it_is_held(
    document, confidence, outcome, written
):
    """Rule 3 on Haiku (D-129): applied at 0.30, which fills the blank department, and held below it.
    Nothing else about rule 3 changes."""
    analysis = apply_classification(
        document,
        classification(department="Finance", department_confidence=confidence, model=HAIKU),
        scheme=scheme(departments=["Finance"]),
    )
    analysis.refresh_from_db()
    document.refresh_from_db()
    assert analysis.department_outcome == outcome
    assert document.department == ("Finance" if written else "")
    assert analysis.department_applied_by == ("ai" if written else None)


@pytest.mark.parametrize("model", ["stub-chat", "gemma3:4b"])
def test_an_unlisted_models_department_falls_back_to_its_shared_threshold(document, model):
    """Haiku's department 0.30 is Haiku's alone: on an unlisted model a department at 0.30 is held,
    one just below the shared value is held, and one at the shared value fills the blank department."""
    shared = CLASSIFICATION_CONFIDENCE_THRESHOLD
    for confidence, outcome in (
        (HAIKU_DEPARTMENT_THRESHOLD, ASSIGNMENT_PROVISIONAL),
        (round(shared - EPSILON, 3), ASSIGNMENT_PROVISIONAL),
    ):
        analysis = apply_classification(
            document,
            classification(department="Finance", department_confidence=confidence, model=model),
            scheme=scheme(departments=["Finance"]),
        )
        assert (confidence, analysis.department_outcome) == (confidence, outcome)
        document.refresh_from_db()
        assert document.department == ""

    analysis = apply_classification(
        document,
        classification(department="Finance", department_confidence=shared, model=model),
        scheme=scheme(departments=["Finance"]),
    )
    document.refresh_from_db()
    assert analysis.department_outcome == ASSIGNMENT_APPLIED
    assert document.department == "Finance"


def test_on_haiku_the_type_and_the_tags_keep_the_shared_threshold_while_the_department_uses_its_own(
    document,
):
    """At 0.50 on Haiku: the department applies (0.50 >= 0.30) and fills the blank department, while
    the type and a tag are held (0.50 < 0.72)."""
    assert HAIKU_DEPARTMENT_THRESHOLD <= BETWEEN_THE_HAIKU_VALUES < CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL[HAIKU]
    make_tag(PROJECT_DIMENSION, "bridge maintenance")
    analysis = apply_classification(
        document,
        classification(doc_type=POLICY, type_confidence=BETWEEN_THE_HAIKU_VALUES,
                       department="Finance", department_confidence=BETWEEN_THE_HAIKU_VALUES,
                       tags=[(PROJECT_DIMENSION, "bridge maintenance", BETWEEN_THE_HAIKU_VALUES)],
                       model=HAIKU),
        scheme=scheme(departments=["Finance"], project=["bridge maintenance"]),
    )
    analysis.refresh_from_db()
    document.refresh_from_db()
    assert (analysis.doc_type_outcome, analysis.doc_type) == (ASSIGNMENT_PROVISIONAL, None)
    assert links_of(document).get().provisional is True
    assert analysis.department_outcome == ASSIGNMENT_APPLIED
    assert document.department == "Finance"


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
    assert analysis.proposed_tags == [
        {"dimension": TOPIC_DIMENSION, "value": "budget planning", "confidence": ABOVE_THRESHOLD}
    ]
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
    assert analysis.proposed_tags == []
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
    assert analysis.proposed_tags == []
    assert analysis.discarded_suggestions == []
    assert not links_of(document).exists()
    assert Tag.objects.count() == 0


def test_proposed_tags_are_deduplicated_by_normalised_value_and_replaced_on_a_rerun(document):
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
    assert first.proposed_tags == [
        {"dimension": TOPIC_DIMENSION, "value": "budget planning", "confidence": ABOVE_THRESHOLD}
    ]
    second = apply_classification(
        document,
        classification(tags=[(TOPIC_DIMENSION, "Risk Appetite", ABOVE_THRESHOLD)]),
        scheme=scheme(),
    )
    assert second.proposed_tags == [
        {"dimension": TOPIC_DIMENSION, "value": "risk appetite", "confidence": ABOVE_THRESHOLD}
    ]
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
