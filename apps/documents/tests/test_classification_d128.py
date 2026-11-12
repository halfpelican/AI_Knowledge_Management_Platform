"""``apply_classification`` under D-128 (12 November 2026): what becomes of a suggestion outside the
scheme, read through each classifying model's own threshold.

D-128 departs from FR-10's controlled taxonomy growth clause for tags. A value outside the scheme in
Project, Process or Topic is created and applied when its confidence is at or above the threshold:
an active, grown Tag, and an AI link, unconfirmed, not provisional, carrying the confidence. Below
the threshold it is held in ``proposed_tags``. A name longer than a tag name can be goes to
``discarded_suggestions`` whatever its confidence, and creates nothing. A department outside the
scheme is still discarded, as before D-128.

Every threshold is read through ``confidence_threshold(model)``, never written as a number, for two
models whose thresholds differ: the stub's, which gets CLASSIFICATION_CONFIDENCE_THRESHOLD, and
claude-haiku-5-5, which CLASSIFICATION_CONFIDENCE_THRESHOLD_BY_MODEL lists (D-122; its value since
D-128's prompt). The schemes are written by hand, as in test_classification_apply.py, which already
holds the Project and Process cases for the stub's model.
"""

from decimal import Decimal

import pytest

from apps.core.constants import (
    AI_APPLIED,
    ASSIGNMENT_DISCARDED,
    DEPARTMENT_DIMENSION,
    MAXIMUM_CREATED_TAG_WORDS,
    PROJECT_DIMENSION,
    REPOSITORY_TAG_DIMENSIONS,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.classification import apply_classification, apply_tag, confidence_threshold
from apps.documents.models import ContentTag, Tag

from .classification_builders import EPSILON, STUB_CHAT_MODEL, classification, scheme

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
HAIKU = "claude-haiku-5-5"
MODELS = (STUB_CHAT_MODEL, HAIKU)
SIDES = ("below", "at", "above")
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


def test_the_two_models_have_different_thresholds():
    """The premise of the parametrisation below: each model is judged by its own value."""
    assert confidence_threshold(HAIKU) != confidence_threshold(STUB_CHAT_MODEL)
    assert confidence(HAIKU, "above") < confidence(STUB_CHAT_MODEL, "below")


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_value_outside_the_scheme_is_held_below_the_models_threshold_and_created_at_it(
    document, dimension, side, model
):
    value = confidence(model, side)

    analysis = apply_classification(
        document, classification(tags=[(dimension, "  Harbour   Upgrade ", value)], model=model),
        scheme=scheme(),
    )

    analysis.refresh_from_db()
    assert analysis.discarded_suggestions == []
    if side == "below":
        assert analysis.proposed_tags == [
            {"dimension": dimension, "value": "harbour upgrade", "confidence": value}
        ]
        assert not Tag.objects.exists()
        assert not links_of(document).exists()
    else:
        assert analysis.proposed_tags == []
        tag = Tag.objects.get()
        assert (tag.dimension, tag.tag_name, tag.active, tag.grown) == (
            dimension, "harbour upgrade", True, True,
        )
        link = links_of(document).get()
        assert (link.tag_id, link.applied_by, link.confirmed, link.provisional, link.removed) == (
            tag.pk, AI_APPLIED, False, False, False,
        )
        assert link.confidence == Decimal(str(value))


@pytest.mark.parametrize("side", ("below", "at"))
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_name_longer_than_a_tag_name_is_discarded_whatever_its_confidence(document, dimension, side):
    value = confidence(STUB_CHAT_MODEL, side)

    analysis = apply_classification(
        document, classification(tags=[(dimension, f" {TOO_LONG.upper()} ", value)]), scheme=scheme()
    )

    analysis.refresh_from_db()
    assert analysis.discarded_suggestions == [
        {"dimension": dimension, "value": TOO_LONG, "confidence": value}
    ]
    assert analysis.proposed_tags == []
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


def test_the_length_is_the_normalised_names_so_one_as_long_as_a_tag_name_is_created(document):
    """Longer than a tag name as the model wrote it, exactly as long once normalised: created."""
    name = "a" * 100 + " " + "b" * (NAME_MAX_LENGTH - 101)
    written = "  " + "A" * 100 + "     " + "B" * (NAME_MAX_LENGTH - 101) + "  "
    assert len(name) == NAME_MAX_LENGTH < len(written)

    analysis = apply_classification(
        document,
        classification(tags=[(PROJECT_DIMENSION, written, confidence(STUB_CHAT_MODEL, "at"))]),
        scheme=scheme(),
    )

    assert analysis.discarded_suggestions == []
    assert analysis.proposed_tags == []
    assert list(Tag.objects.values_list("dimension", "tag_name", "grown")) == [
        (PROJECT_DIMENSION, name, True)
    ]
    assert links_of(document).get().tag.tag_name == name


@pytest.mark.parametrize("side", SIDES)
def test_a_department_outside_the_scheme_is_still_discarded_while_a_tag_outside_it_is_not(document, side):
    """D-128 left the department alone: outside the scheme it is discarded at any confidence, the
    document's department is not written, and a department named as a tag is ignored rather than
    created, proposed or discarded. In the same run a Project value outside the scheme is D-128's to
    hold or create."""
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
    assert not Tag.objects.filter(dimension=DEPARTMENT_DIMENSION).exists()
    assert not Tag.objects.filter(tag_name="marketing").exists()
    assert analysis.discarded_suggestions == []
    if side == "below":
        assert analysis.proposed_tags == [
            {"dimension": PROJECT_DIMENSION, "value": "harbour upgrade", "confidence": value}
        ]
        assert not Tag.objects.exists()
    else:
        assert analysis.proposed_tags == []
        assert list(Tag.objects.values_list("dimension", "tag_name", "grown")) == [
            (PROJECT_DIMENSION, "harbour upgrade", True)
        ]


# --- What may become a tag (D-128's security review, finding 2) ---------------------------------------
#
# Rule 4d discards, whatever its confidence, a value outside the scheme that:
#   - has more than MAXIMUM_CREATED_TAG_WORDS words;
#   - holds ";", the prompt's list separator;
#   - holds a control (Cc) or format (Cf) character;
#   - or, beyond the review's letter, holds a lone surrogate (Cs), which can no more be written than
#     a NUL.
# Otherwise uploaded text could plant itself in other documents' prompts once created. The record
# replaces each such character with U+FFFD, so the jsonb column always accepts it. The characters
# are built with chr(), so this file holds none of them.

NUL = chr(0x0000)
RIGHT_TO_LEFT_OVERRIDE = chr(0x202E)
ZERO_WIDTH_SPACE = chr(0x200B)
LONE_SURROGATE = chr(0xD800)
REPLACEMENT_CHARACTER = chr(0xFFFD)
FOUR_WORDS = "port of melbourne expansion"
THREE_WORDS = "port of melbourne"


@pytest.mark.parametrize("side", ("below", "at"))
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_value_of_more_than_three_words_is_discarded_whatever_its_confidence(document, dimension, side):
    assert len(FOUR_WORDS.split()) == MAXIMUM_CREATED_TAG_WORDS + 1 == 4  # the premise
    value = confidence(STUB_CHAT_MODEL, side)

    analysis = apply_classification(
        document, classification(tags=[(dimension, "  Port of   Melbourne EXPANSION ", value)]),
        scheme=scheme(),
    )

    analysis.refresh_from_db()
    assert analysis.discarded_suggestions == [
        {"dimension": dimension, "value": FOUR_WORDS, "confidence": value}
    ]
    assert analysis.proposed_tags == []
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_value_of_three_words_is_created_at_the_threshold_and_held_below_it(document, dimension, side):
    assert len(THREE_WORDS.split()) == MAXIMUM_CREATED_TAG_WORDS  # the premise
    value = confidence(STUB_CHAT_MODEL, side)

    analysis = apply_classification(
        document, classification(tags=[(dimension, "Port of Melbourne", value)]), scheme=scheme()
    )

    analysis.refresh_from_db()
    assert analysis.discarded_suggestions == []
    if side == "below":
        assert analysis.proposed_tags == [
            {"dimension": dimension, "value": THREE_WORDS, "confidence": value}
        ]
        assert not Tag.objects.exists()
    else:
        assert analysis.proposed_tags == []
        assert list(Tag.objects.values_list("dimension", "tag_name", "active", "grown")) == [
            (dimension, THREE_WORDS, True, True)
        ]
        assert links_of(document).get().tag.tag_name == THREE_WORDS


# (as the model wrote it, as the discard records it)
CHARACTER_CASES = {
    "the list separator": ("Payroll; Finance", "payroll; finance"),
    "a right-to-left override": (f"Pay{RIGHT_TO_LEFT_OVERRIDE}roll", f"pay{REPLACEMENT_CHARACTER}roll"),
    "a zero-width space": (f"Pay{ZERO_WIDTH_SPACE}roll", f"pay{REPLACEMENT_CHARACTER}roll"),
    "a NUL": (f"Pay{NUL}roll", f"pay{REPLACEMENT_CHARACTER}roll"),
    "a lone surrogate": (f"Pay{LONE_SURROGATE}roll", f"pay{REPLACEMENT_CHARACTER}roll"),
}


@pytest.mark.parametrize("side", ("below", "at"))
@pytest.mark.parametrize("case", sorted(CHARACTER_CASES))
def test_a_value_holding_the_separator_or_a_control_format_or_surrogate_character_is_discarded(
    document, case, side
):
    """Discarded at either confidence, nothing created, proposed or linked. The record is read back
    from the database, so it was written: each such character as U+FFFD, the rest as written."""
    written, recorded = CHARACTER_CASES[case]
    value = confidence(STUB_CHAT_MODEL, side)

    analysis = apply_classification(
        document, classification(tags=[(TOPIC_DIMENSION, written, value)]), scheme=scheme()
    )

    analysis.refresh_from_db()
    assert analysis.discarded_suggestions == [
        {"dimension": TOPIC_DIMENSION, "value": recorded, "confidence": value}
    ]
    assert analysis.proposed_tags == []
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


def test_a_value_already_a_tag_in_the_scheme_is_matched_whatever_its_words(document):
    """The limits are rule 4d's alone. A Tag already in the scheme, here a four-word vocabulary
    value an Administrator added, is linked as it stands (rule 4c)."""
    tag = Tag.objects.create(tag_name=FOUR_WORDS, dimension=PROJECT_DIMENSION)

    analysis = apply_classification(
        document,
        classification(tags=[(PROJECT_DIMENSION, FOUR_WORDS, confidence(STUB_CHAT_MODEL, "at"))]),
        scheme=scheme(project=[FOUR_WORDS]),
    )

    assert analysis.discarded_suggestions == []
    assert links_of(document).get().tag == tag


def test_a_persons_name_form_is_not_held_to_the_classifiers_limits(document):
    """``apply_tag``'s name form keeps its own checks: a four-word Topic a person types is created."""
    applied = apply_tag(document, tag_name=FOUR_WORDS)

    assert applied.created is True
    assert (applied.link.tag.dimension, applied.link.tag.tag_name, applied.link.applied_by) == (
        TOPIC_DIMENSION, FOUR_WORDS, USER_APPLIED,
    )
