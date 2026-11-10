"""Which Topics are grown: ``Tag.grown`` (D-105's dated note of 10 November 2026, night, the lead's
revision).

Only a Topic that came into use through a name is grown, and so out of every scheme once nothing
links it: the Topic a person's ``apply_tag`` name form links, created or fetched (one carried only by
restricted material, or a retired one), and the Topic ``confirm_proposed_topic`` links, created or
fetched. The ``tag_id`` form marks nothing, since an offered tag is already readable or vocabulary,
and neither does the machine's own linking of a seeded Topic.
"""

import pytest

from apps.core.constants import ADMINISTRATOR_ROLE_NAME, SOURCE_TYPES, TOPIC_DIMENSION, USER_APPLIED
from apps.documents.classification import apply_classification, apply_tag, confirm_proposed_topic
from apps.documents.models import ContentTag, Document, Tag

from .classification_builders import ABOVE_THRESHOLD, classification, scheme

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
NAME = "merger talks"
KINDS = ["created", "restricted", "inactive"]


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
        topic = Tag.objects.create(tag_name=NAME, dimension=TOPIC_DIMENSION)
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


def test_apply_tags_tag_id_form_marks_nothing(document):
    seeded = Tag.objects.create(tag_name="safety", dimension=TOPIC_DIMENSION)  # vocabulary: offered

    apply_tag(document, tag_id=seeded.pk)

    seeded.refresh_from_db()
    assert seeded.grown is False
    assert ContentTag.objects.filter(tag=seeded, source_id=document.pk).exists()


@pytest.mark.parametrize("kind", KINDS)
def test_confirm_proposed_topic_marks_the_topic_it_links_grown(document, restricted, kind):
    existing = existing_topic(kind, restricted)
    # A hand-written scheme with no Topics, so the suggestion is proposed whatever exists.
    apply_classification(
        document, classification(tags=[(TOPIC_DIMENSION, NAME, ABOVE_THRESHOLD)]), scheme=scheme()
    )

    confirm_proposed_topic(document, NAME)

    topic = Tag.objects.get(tag_name=NAME, dimension=TOPIC_DIMENSION)
    assert (topic.grown, topic.active) == (True, True)
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
