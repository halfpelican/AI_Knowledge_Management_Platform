"""A person's removal of an AI tag is kept, and reprocessing respects it (FR-10, D-119 finding 3).

FR-10's correction clause: "any value a user edits are retained and is not overwritten by later
reprocessing, and the machine assignment is retained alongside it so that classification accuracy
can be measured over time rather than being overwritten and lost". Until D-105's dated note of 10
November 2026 (night), ``reject_tag`` deleted the link, so the machine's assignment was lost and the
next classify or reprocess linked the tag again. Now:

- an AI link that is removed stays, marked ``removed``, with the confidence and provisional flag the
  machine gave it, whether it was held, applied or confirmed;
- a later run neither links it again nor alters it, and a removed Topic is not proposed again;
- a removed link is no longer found by id, so it cannot be confirmed or removed a second time;
- ``tag_scheme`` still counts it as a link, so the tag stays in its own document's scheme: offered
  there to be applied again, and shown to the classifier, which leaves the removed link alone.

A person's own link is kept the same way since the requirements re-audit of ``5377e3a`` (D-105's
dated note): ``test_classification_confirm.py`` holds that case
(``test_a_persons_own_tag_is_removed_in_the_same_action_and_kept_marked_removed``), and
``apps/api/tests/test_fr10_removed_tags.py`` the later classify and reprocess.
"""

from decimal import Decimal

import pytest

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    EMPLOYEE_ROLE_NAME,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
)
from apps.documents.classification import (
    NotOnThisDocument,
    apply_classification,
    confirm_proposed_topic,
    confirm_tag,
    reject_tag,
    tag_scheme,
)
from apps.documents.models import ContentTag, Document, DocumentAnalysis, Tag

from .classification_builders import ABOVE_THRESHOLD, BELOW_THRESHOLD, classification, scheme

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BRIDGE = "bridge maintenance"
BUDGET = "budget planning"


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def run(document, *tags, project=(BRIDGE,), topic=()):
    """One classification run with these tag suggestions, against a hand-written scheme."""
    return apply_classification(
        document, classification(tags=tags), scheme=scheme(project=project, topic=topic)
    )


@pytest.fixture
def bridge(db):
    return Tag.objects.create(tag_name=BRIDGE, dimension=PROJECT_DIMENSION)


@pytest.mark.parametrize("state", ["held", "applied", "confirmed"])
def test_removing_an_ai_tag_keeps_the_row_with_the_machines_assignment(document, bridge, state):
    confidence = BELOW_THRESHOLD if state == "held" else ABOVE_THRESHOLD
    run(document, (PROJECT_DIMENSION, BRIDGE, confidence))
    link = links_of(document).get()
    if state == "confirmed":
        confirm_tag(document, link.pk)
    link.refresh_from_db()
    before = (link.applied_by, link.confirmed, link.provisional, link.confidence)

    reject_tag(document, link.pk)

    kept = links_of(document).get()  # still there: one row, the same one
    assert kept.pk == link.pk
    assert kept.removed is True
    # The machine's assignment as it stood, kept beside the person's decision.
    assert (kept.applied_by, kept.confirmed, kept.provisional, kept.confidence) == before
    assert kept.confidence == Decimal(str(confidence))
    assert Tag.objects.filter(pk=bridge.pk).exists()


def test_a_reclassify_neither_relinks_nor_alters_a_removed_tag(document, bridge):
    run(document, (PROJECT_DIMENSION, BRIDGE, ABOVE_THRESHOLD))
    link = links_of(document).get()
    reject_tag(document, link.pk)

    # The next run suggests the same tag again, at a confidence that would make a live AI link
    # provisional and change its confidence.
    run(document, (PROJECT_DIMENSION, BRIDGE, BELOW_THRESHOLD))

    kept = links_of(document).get()
    assert kept.pk == link.pk
    assert (kept.removed, kept.provisional) == (True, False)
    assert kept.confidence == Decimal(str(ABOVE_THRESHOLD))


def test_a_removed_link_is_no_longer_found_to_confirm_or_remove(document, bridge):
    run(document, (PROJECT_DIMENSION, BRIDGE, BELOW_THRESHOLD))
    link = links_of(document).get()
    reject_tag(document, link.pk)

    with pytest.raises(NotOnThisDocument):
        confirm_tag(document, link.pk)
    with pytest.raises(NotOnThisDocument):
        reject_tag(document, link.pk)

    kept = links_of(document).get()
    assert (kept.removed, kept.confirmed, kept.provisional) == (True, False, True)


def test_a_removed_topic_is_not_proposed_again_once_its_tag_is_retired(document):
    topic = Tag.objects.create(tag_name=BUDGET, dimension=TOPIC_DIMENSION)
    run(document, (TOPIC_DIMENSION, BUDGET, ABOVE_THRESHOLD), topic=(BUDGET,))
    link = links_of(document).get()
    reject_tag(document, link.pk)
    # Retired since: no longer in any scheme, so without the removal the suggestion would be
    # proposed as a new Topic and a person asked again about a value they took off this document.
    topic.active = False
    topic.save(update_fields=["active"])

    analysis = run(document, (TOPIC_DIMENSION, BUDGET, ABOVE_THRESHOLD), topic=())

    assert analysis.proposed_topics == []
    kept = links_of(document).get()
    assert (kept.pk, kept.removed) == (link.pk, True)


def test_confirming_a_proposed_topic_puts_a_removed_link_back(document):
    """A proposal recorded before its Topic was removed and retired: a person confirming it wants
    the Topic on the document, so the one link is restored rather than left removed."""
    analysis = run(document, (TOPIC_DIMENSION, BUDGET, ABOVE_THRESHOLD), topic=())
    assert [proposal["value"] for proposal in analysis.proposed_topics] == [BUDGET]
    retired = Tag.objects.create(tag_name=BUDGET, dimension=TOPIC_DIMENSION, active=False)
    removed = ContentTag.objects.create(
        tag=retired, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=AI_APPLIED, confirmed=False, provisional=False, removed=True,
        confidence=Decimal("0.500"),
    )

    link = confirm_proposed_topic(document, BUDGET)

    assert link.pk == removed.pk
    link.refresh_from_db()
    assert (link.removed, link.confirmed, link.provisional) == (False, True, False)
    assert link.confidence == Decimal("0.500")  # the machine's earlier assignment, kept
    retired.refresh_from_db()
    assert retired.active is True
    assert links_of(document).count() == 1
    assert DocumentAnalysis.objects.get(document=document).proposed_topics == []


def test_tag_scheme_counts_a_removed_link_on_a_restricted_document(employee, administrator):
    """A Topic whose only link is a removed suggestion on an Administrator-only document is still
    withheld from an Employee-visible document's scheme: the removal is a fact about the
    restricted document, not a reason to offer its value to everybody (invariant 1)."""
    staff = Document.objects.create(
        title="Staff handbook", file_type="pdf", uploaded_by=employee,
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
    )
    board = Document.objects.create(
        title="Board pack", file_type="pdf", uploaded_by=administrator,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )
    # Grown, as documents 0011 marks a value only restricted material carries; a value that is not
    # grown is vocabulary and in every scheme whatever its links (the security review's rule).
    topic = Tag.objects.create(tag_name="succession planning", dimension=TOPIC_DIMENSION, grown=True)
    ContentTag.objects.create(
        tag=topic, source_type=DOCUMENT_SOURCE_TYPE, source_id=board.pk,
        applied_by=AI_APPLIED, confirmed=False, provisional=False, removed=True,
        confidence=Decimal("0.970"),
    )

    assert "succession planning" not in tag_scheme(staff).tags[TOPIC_DIMENSION]
    assert "succession planning" in tag_scheme(board).tags[TOPIC_DIMENSION]
