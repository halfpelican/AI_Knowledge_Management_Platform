"""A proposal a person rejects stays rejected: ``reject_proposed_tag`` and ``apply_classification`` rule
4b (the requirements audit of D-128, finding A5; the lead's decision of 13 November 2026).

The audit found that a rejection dropped the proposal and recorded nothing, so a later run created and
linked the value at or above the threshold, or proposed it again below it. FR-10's correction clause:
"any value a user edits are retained and is not overwritten by later reprocessing", with "the machine
assignment ... retained alongside it" (UC-09 A3). Now:

- the rejection is recorded in ``DocumentAnalysis.rejected_tags`` with the machine's confidence from
  the proposal, one entry per dimension and value;
- every later run skips that value on that document, in every dimension, at any confidence, and
  before the in-scheme match, so it is not linked even once it is a Tag in the scheme;
- a run never replaces the record.

Driven with classifications and schemes made by hand, as test_classification_apply.py is. The routes,
from both roles, are apps/api/tests/test_fr10_rejected_proposals.py.
"""

import pytest

from apps.core.constants import PROCESS_DIMENSION, PROJECT_DIMENSION, REPOSITORY_TAG_DIMENSIONS, SOURCE_TYPES
from apps.documents.classification import NotOnThisDocument, apply_classification, reject_proposed_tag
from apps.documents.models import ContentTag, DocumentAnalysis, Tag

from .classification_builders import AT_THRESHOLD, BELOW_THRESHOLD, classification, scheme

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
VALUE = "harbour upgrade"
LOWER = round(BELOW_THRESHOLD - 0.1, 3)


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def analysis_of(document):
    return DocumentAnalysis.objects.get(document=document)


def propose(document, dimension, confidence=BELOW_THRESHOLD):
    """A run against a scheme without the value, below the threshold: the value is held."""
    analysis = apply_classification(
        document, classification(tags=[(dimension, "Harbour  Upgrade", confidence)]), scheme=scheme()
    )
    assert analysis.proposed_tags == [{"dimension": dimension, "value": VALUE, "confidence": confidence}]


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_rejection_is_recorded_with_the_machines_confidence_and_creates_nothing(document, dimension):
    propose(document, dimension)

    reject_proposed_tag(document, dimension, " Harbour UPGRADE ")  # matched after normalisation

    analysis = analysis_of(document)
    assert analysis.rejected_tags == [{"dimension": dimension, "value": VALUE, "confidence": BELOW_THRESHOLD}]
    assert analysis.proposed_tags == []
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


def test_rejecting_the_same_value_twice_keeps_one_entry_with_the_latest_confidence(document):
    """A run never proposes a rejected value again (rule 4b), so the second proposal is written by
    hand, as a row from before the fix could hold one. One entry is kept, with the later proposal's
    confidence: the machine's assignment at the time of the later decision."""
    propose(document, PROJECT_DIMENSION)
    reject_proposed_tag(document, PROJECT_DIMENSION, VALUE)
    analysis = analysis_of(document)
    analysis.proposed_tags = [{"dimension": PROJECT_DIMENSION, "value": VALUE, "confidence": LOWER}]
    analysis.save(update_fields=["proposed_tags"])

    reject_proposed_tag(document, PROJECT_DIMENSION, VALUE)

    assert analysis_of(document).rejected_tags == [
        {"dimension": PROJECT_DIMENSION, "value": VALUE, "confidence": LOWER}
    ]


def test_a_value_not_proposed_under_that_dimension_is_not_on_this_document_and_records_nothing(document):
    propose(document, PROJECT_DIMENSION)

    with pytest.raises(NotOnThisDocument):
        reject_proposed_tag(document, PROCESS_DIMENSION, VALUE)
    with pytest.raises(NotOnThisDocument):
        reject_proposed_tag(document, PROJECT_DIMENSION, "risk appetite")

    analysis = analysis_of(document)
    assert analysis.rejected_tags == []
    assert analysis.proposed_tags == [{"dimension": PROJECT_DIMENSION, "value": VALUE, "confidence": BELOW_THRESHOLD}]


@pytest.mark.parametrize("confidence", [BELOW_THRESHOLD, AT_THRESHOLD], ids=["below", "at"])
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_rejected_value_is_skipped_even_once_it_is_a_tag_in_the_scheme(document, dimension, confidence):
    """Rule 4b comes before the in-scheme match: the value has since become an active vocabulary Tag,
    listed in the scheme the run is given, and it is still neither linked, proposed nor discarded.
    The run leaves the record as it was."""
    propose(document, dimension)
    reject_proposed_tag(document, dimension, VALUE)
    tag = Tag.objects.create(tag_name=VALUE, dimension=dimension)  # vocabulary, added since

    analysis = apply_classification(
        document, classification(tags=[(dimension, VALUE, confidence)]),
        scheme=scheme(**{dimension.lower(): [VALUE]}),
    )

    analysis.refresh_from_db()
    assert not links_of(document).exists()
    assert (analysis.proposed_tags, analysis.discarded_suggestions) == ([], [])
    assert analysis.rejected_tags == [{"dimension": dimension, "value": VALUE, "confidence": BELOW_THRESHOLD}]
    tag.refresh_from_db()
    assert (tag.active, tag.grown) == (True, False)  # untouched: vocabulary it was, and stays
