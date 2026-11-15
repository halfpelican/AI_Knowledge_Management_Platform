"""``apply_classification`` rule 4d since D-129 (13 November 2026), read through each classifying
model's own threshold.

D-129 reverses D-128's creation of values. FR-10's controlled taxonomy growth clause and Objective
05's clause 3 hold as written: "suggested values falling outside the established scheme must be
discarded in the Department, Project and Process dimensions while being proposed for confirmation in
the Topic dimension only". So, at any confidence:

- a Topic value outside the scheme is proposed, and no Tag is created;
- a Project or Process value outside the scheme is discarded, and no Tag is created;
- a value that cannot be stored, holding a NUL or a lone surrogate, is discarded whatever its
  dimension, recorded with U+FFFD. That is the 500 fix of D-128's security review, kept.
- Nothing else is refused: a Topic of many words, holding ";", a control or format character, or
  longer than the column, is proposed, as before D-128. A person who confirms one longer than the
  column is refused.
- A department outside the scheme is discarded.

Every threshold is read through ``confidence_threshold(model)``, never written as a number, for two
models whose thresholds differ: the stub's, which gets CLASSIFICATION_CONFIDENCE_THRESHOLD, and
claude-haiku-5-5, which CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL lists (D-122). The schemes are
written by hand, as in test_classification_apply.py. The characters are built with chr(), so this
file holds none of them.
"""

import pytest

from apps.core.constants import (
    ASSIGNMENT_DISCARDED,
    DEPARTMENT_DIMENSION,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    REPOSITORY_TAG_DIMENSIONS,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.classification import (
    InvalidClassification,
    apply_classification,
    apply_tag,
    confidence_threshold,
    confirm_proposed_tag,
)
from apps.documents.models import ContentTag, Tag

from .classification_builders import EPSILON, STUB_CHAT_MODEL, classification, scheme

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
HAIKU = "claude-haiku-5-5"
MODELS = (STUB_CHAT_MODEL, HAIKU)
SIDES = ("below", "at", "above")
NUL = chr(0x0000)
LONE_SURROGATE = chr(0xD800)
RIGHT_TO_LEFT_OVERRIDE = chr(0x202E)
START_OF_HEADING = chr(0x0001)  # a control character other than NUL, which jsonb accepts
REPLACEMENT_CHARACTER = chr(0xFFFD)
TOO_LONG = "x" * (NAME_MAX_LENGTH + 1)


def confidence(model, side):
    """A confidence just below, at, or just above ``model``'s own threshold, at the resolution the
    decimal(4,3) columns record."""
    threshold = confidence_threshold(model)
    return {
        "below": round(threshold - EPSILON, 3),
        "at": threshold,
        "above": round(min(1.0, threshold + EPSILON), 3),
    }[side]


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def run(document, dimension, written, value, model=STUB_CHAT_MODEL):
    analysis = apply_classification(
        document, classification(tags=[(dimension, written, value)], model=model), scheme=scheme()
    )
    analysis.refresh_from_db()  # read back: the record was written
    return analysis


def test_the_two_models_have_different_thresholds():
    """The premise of the parametrisation below: each model is judged by its own value."""
    assert confidence_threshold(HAIKU) != confidence_threshold(STUB_CHAT_MODEL)
    assert confidence(HAIKU, "above") < confidence(STUB_CHAT_MODEL, "below")


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("side", SIDES)
def test_a_topic_outside_the_scheme_is_proposed_at_any_confidence_and_no_tag_is_created(
    document, side, model
):
    value = confidence(model, side)

    analysis = run(document, TOPIC_DIMENSION, "  Harbour   Upgrade ", value, model=model)

    assert analysis.proposed_tags == [
        {"dimension": TOPIC_DIMENSION, "value": "harbour upgrade", "confidence": value}
    ]
    assert analysis.discarded_suggestions == []
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("dimension", [PROJECT_DIMENSION, PROCESS_DIMENSION])
def test_a_project_or_process_outside_the_scheme_is_discarded_at_any_confidence_and_no_tag_is_created(
    document, dimension, side, model
):
    value = confidence(model, side)

    analysis = run(document, dimension, "  Harbour   Upgrade ", value, model=model)

    assert analysis.discarded_suggestions == [
        {"dimension": dimension, "value": "harbour upgrade", "confidence": value}
    ]
    assert analysis.proposed_tags == []
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


@pytest.mark.parametrize("higher_first", [True, False], ids=["higher first", "higher last"])
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_value_suggested_twice_is_recorded_once_at_its_higher_confidence(
    document, dimension, higher_first
):
    """One value outside the scheme suggested twice, in either order, is one entry at the higher
    confidence: proposed for a Topic, discarded for a Project or Process. test_classification_apply.py
    puts the lower first only, which a run keeping the last suggestion would also pass."""
    lower = confidence(STUB_CHAT_MODEL, "below")
    higher = confidence(STUB_CHAT_MODEL, "above")
    written = [(dimension, "Harbour Upgrade", higher), (dimension, " harbour   upgrade ", lower)]
    if not higher_first:
        written.reverse()

    analysis = apply_classification(
        document, classification(tags=written, model=STUB_CHAT_MODEL), scheme=scheme()
    )
    analysis.refresh_from_db()

    entry = [{"dimension": dimension, "value": "harbour upgrade", "confidence": higher}]
    if dimension == TOPIC_DIMENSION:
        assert (analysis.proposed_tags, analysis.discarded_suggestions) == (entry, [])
    else:
        assert (analysis.proposed_tags, analysis.discarded_suggestions) == ([], entry)
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


# (as the model wrote it, as the proposal holds it)
PROPOSED_AS_WRITTEN = {
    "four words": ("Port of  Melbourne Expansion", "port of melbourne expansion"),
    "the list separator": ("Payroll; Finance", "payroll; finance"),
    "a format character": (f"Pay{RIGHT_TO_LEFT_OVERRIDE}roll", f"pay{RIGHT_TO_LEFT_OVERRIDE}roll"),
    "a control character other than NUL": (f"Pay{START_OF_HEADING}roll", f"pay{START_OF_HEADING}roll"),
    "longer than the column": (TOO_LONG.upper(), TOO_LONG),
}


@pytest.mark.parametrize("side", ("below", "above"))
@pytest.mark.parametrize("case", sorted(PROPOSED_AS_WRITTEN))
def test_a_topic_that_d128_refused_is_proposed_again(document, case, side):
    """D-128's security review refused these as names a prompt could not list safely; that rule
    went with D-128's creation. Each is proposed, as before D-128, for a person to judge."""
    written, held = PROPOSED_AS_WRITTEN[case]
    value = confidence(STUB_CHAT_MODEL, side)

    analysis = run(document, TOPIC_DIMENSION, written, value)

    assert analysis.proposed_tags == [{"dimension": TOPIC_DIMENSION, "value": held, "confidence": value}]
    assert analysis.discarded_suggestions == []
    assert not Tag.objects.exists()


@pytest.mark.parametrize("side", ("below", "above"))
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
@pytest.mark.parametrize("character", ["a NUL", "a lone surrogate"])
def test_a_value_that_cannot_be_stored_is_discarded_with_the_replacement_character(
    document, character, dimension, side
):
    """Neither a text column nor jsonb holds a NUL, and neither can encode a lone surrogate, so the
    value is discarded in every dimension, recorded with U+FFFD. Read back from the database, so the
    record was written."""
    special = NUL if character == "a NUL" else LONE_SURROGATE
    value = confidence(STUB_CHAT_MODEL, side)

    analysis = run(document, dimension, f"Pay{special}roll", value)

    assert analysis.discarded_suggestions == [
        {"dimension": dimension, "value": f"pay{REPLACEMENT_CHARACTER}roll", "confidence": value}
    ]
    assert analysis.proposed_tags == []
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


def test_a_topic_longer_than_the_column_is_proposed_and_confirming_it_is_refused(document):
    """Proposed whatever its length, as before D-128. A person who confirms it gets
    ``InvalidClassification``, the route's 400, and no Tag is made."""
    run(document, TOPIC_DIMENSION, TOO_LONG, confidence(STUB_CHAT_MODEL, "below"))

    with pytest.raises(InvalidClassification):
        confirm_proposed_tag(document, TOPIC_DIMENSION, TOO_LONG)

    assert not Tag.objects.exists()
    assert not links_of(document).exists()


@pytest.mark.parametrize("side", SIDES)
def test_a_department_outside_the_scheme_is_discarded_and_one_named_as_a_tag_is_ignored(document, side):
    """D-128 left the department alone and D-129 leaves it so: outside the scheme it is discarded
    at any confidence, the document's department is not written, and a department named as a tag
    is ignored rather than proposed or discarded. In the same run a Project value outside the
    scheme is discarded."""
    value = confidence(STUB_CHAT_MODEL, side)

    analysis = apply_classification(
        document,
        classification(
            department="Marketing", department_confidence=value,
            tags=[(DEPARTMENT_DIMENSION, "Marketing", value), (PROJECT_DIMENSION, "harbour upgrade", value)],
        ),
        scheme=scheme(departments=["Finance"]),
    )

    analysis.refresh_from_db()
    document.refresh_from_db()
    assert (analysis.machine_department, analysis.department_outcome) == ("Marketing", ASSIGNMENT_DISCARDED)
    assert document.department == ""
    assert not Tag.objects.exists()
    assert analysis.proposed_tags == []
    assert analysis.discarded_suggestions == [
        {"dimension": PROJECT_DIMENSION, "value": "harbour upgrade", "confidence": value}
    ]


def test_a_value_already_a_tag_in_the_scheme_is_matched_whatever_its_words(document):
    """Rule 4c: a Tag in the scheme, here a four-word vocabulary value an Administrator added, is
    linked as it stands."""
    tag = Tag.objects.create(tag_name="port of melbourne expansion", dimension=PROJECT_DIMENSION)

    analysis = apply_classification(
        document,
        classification(tags=[(PROJECT_DIMENSION, "port of melbourne expansion", confidence(STUB_CHAT_MODEL, "at"))]),
        scheme=scheme(project=["port of melbourne expansion"]),
    )

    assert analysis.discarded_suggestions == []
    assert links_of(document).get().tag == tag


def test_a_persons_name_form_creates_a_topic_of_many_words(document):
    """``apply_tag``'s name form keeps its own checks: a four-word Topic a person types is created."""
    applied = apply_tag(document, tag_name="port of melbourne expansion")

    assert applied.created is True
    assert (applied.link.tag.dimension, applied.link.tag.tag_name, applied.link.applied_by) == (
        TOPIC_DIMENSION, "port of melbourne expansion", USER_APPLIED,
    )
