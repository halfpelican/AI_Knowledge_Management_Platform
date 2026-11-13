"""Which Topics a person's name grows: ``Tag.grown`` (D-105's dated note of 10 November 2026, night:
the lead's revision, and the lead's decision after the security review of ``84b5771``).

A Topic a person's name brings into use is grown when the call creates it or reactivates it, the
``apply_tag`` name form's and ``confirm_proposed_tag``'s alike. An active Topic either one fetches
keeps its value (``_bring_into_use``). A grown one, such as one only restricted material carries
(``documents 0011`` marks those), stays grown. One that is not grown is vocabulary and stays so: the
name form never fetches one, since it is offered and answered 409, and confirming a proposal of its
name made before it was vocabulary links it and leaves it vocabulary. The ``tag_id`` form marks
nothing, since an offered tag is already readable or vocabulary, and neither does the machine's own
linking of a seeded Topic in the scheme. (From D-128 until D-129 the classifier also created or
reactivated a value outside the scheme at or above the threshold, through the same
``_bring_into_use``. Since D-129 it creates and reactivates nothing.)
"""

import pytest

from apps.core.constants import ADMINISTRATOR_ROLE_NAME, SOURCE_TYPES, TOPIC_DIMENSION, USER_APPLIED
from apps.documents.classification import (
    TopicAlreadyOffered,
    apply_classification,
    apply_tag,
    confirm_proposed_tag,
)
from apps.documents.models import ContentTag, Document, Tag

from .classification_builders import ABOVE_THRESHOLD, BELOW_THRESHOLD, classification, scheme

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
NAME = "merger talks"
KINDS = ["created", "restricted", "inactive"]
# Active and not grown: vocabulary, in every scheme. Only a proposal made before the Topic existed
# can name one to confirm_proposed_tag, and the name form answers 409 for one.
VOCABULARY_KINDS = ["vocabulary, unlinked", "vocabulary, on restricted material"]


@pytest.fixture
def restricted(administrator):
    return Document.objects.create(
        title="Board pack", file_type="pdf", uploaded_by=administrator,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )


def existing_topic(kind, restricted):
    """None for a name nothing has; otherwise the Topic of that name, as ``kind`` describes it."""
    if kind == "created":
        return None
    if kind == "restricted":
        # Grown, as documents 0011 marks a value only restricted material carries. One that is not
        # grown is vocabulary, in the scheme, so the name form would find it offered (409).
        topic = Tag.objects.create(tag_name=NAME, dimension=TOPIC_DIMENSION, grown=True)
        ContentTag.objects.create(
            tag=topic, source_type=DOCUMENT_SOURCE_TYPE, source_id=restricted.pk,
            applied_by=USER_APPLIED, confirmed=True,
        )
        return topic
    if kind in VOCABULARY_KINDS:
        topic = Tag.objects.create(tag_name=NAME, dimension=TOPIC_DIMENSION)  # as the seed creates it
        if kind == "vocabulary, on restricted material":
            ContentTag.objects.create(
                tag=topic, source_type=DOCUMENT_SOURCE_TYPE, source_id=restricted.pk,
                applied_by=USER_APPLIED, confirmed=True,
            )
        return topic
    return Tag.objects.create(tag_name=NAME, dimension=TOPIC_DIMENSION, active=False)  # retired, seeded


@pytest.mark.parametrize("kind", KINDS)
def test_apply_tags_name_form_marks_the_topic_it_links_grown(document, restricted, kind):
    existing = existing_topic(kind, restricted)

    applied = apply_tag(document, tag_name=NAME)

    topic = Tag.objects.get(tag_name=NAME, dimension=TOPIC_DIMENSION)
    assert applied.link.tag == topic
    assert (topic.grown, topic.active) == (True, True)
    if existing is not None:
        assert topic.pk == existing.pk  # fetched, never duplicated


@pytest.mark.parametrize("kind", VOCABULARY_KINDS)
def test_the_name_form_never_fetches_an_active_vocabulary_topic(document, restricted, kind):
    """The premise that leaves confirmation the only caller to fetch one: a vocabulary Topic is in
    every scheme, so the name form answers 409 (``TopicAlreadyOffered``) before it fetches."""
    topic = existing_topic(kind, restricted)

    with pytest.raises(TopicAlreadyOffered):
        apply_tag(document, tag_name=NAME)

    topic.refresh_from_db()
    assert (topic.grown, topic.active) == (False, True)
    assert not ContentTag.objects.filter(tag=topic, source_id=document.pk).exists()


def test_apply_tags_tag_id_form_marks_nothing(document):
    seeded = Tag.objects.create(tag_name="safety", dimension=TOPIC_DIMENSION)  # vocabulary: offered

    apply_tag(document, tag_id=seeded.pk)

    seeded.refresh_from_db()
    assert seeded.grown is False
    assert ContentTag.objects.filter(tag=seeded, source_id=document.pk).exists()


CONFIRM_CASES = [
    ("created", True),  # grown by the call
    ("restricted", True),  # grown already, as 0011 marks it; kept grown, not marked
    ("inactive", True),  # reactivated and grown by the call
    ("vocabulary, unlinked", False),  # a stale proposal: vocabulary it was, and stays
    ("vocabulary, on restricted material", False),
]


@pytest.mark.parametrize("kind, grown", CONFIRM_CASES)
def test_confirm_proposed_tag_grows_only_a_topic_it_creates_or_reactivates(
    document, restricted, kind, grown
):
    existing = existing_topic(kind, restricted)
    # A hand-written scheme with no Topics, so the suggestion is proposed whatever exists (D-129: a
    # Topic outside the scheme is proposed at any confidence; below it here). For the vocabulary
    # kinds that is a proposal made before the Topic existed, as when the seed script runs after a
    # document was classified.
    apply_classification(
        document, classification(tags=[(TOPIC_DIMENSION, NAME, BELOW_THRESHOLD)]), scheme=scheme()
    )

    confirm_proposed_tag(document, TOPIC_DIMENSION, NAME)

    topic = Tag.objects.get(tag_name=NAME, dimension=TOPIC_DIMENSION)
    assert (topic.grown, topic.active) == (grown, True)
    if existing is not None:
        assert topic.pk == existing.pk


def test_the_machine_linking_a_seeded_topic_marks_nothing(document):
    seeded = Tag.objects.create(tag_name="safety", dimension=TOPIC_DIMENSION)

    apply_classification(
        document, classification(tags=[(TOPIC_DIMENSION, "safety", ABOVE_THRESHOLD)]),
        scheme=scheme(topic=["safety"]),
    )

    seeded.refresh_from_db()
    assert seeded.grown is False
    assert ContentTag.objects.filter(tag=seeded, source_id=document.pk).exists()
