"""A run discards a Topic longer than a tag name instead of proposing it (D-134, 15 November 2026).

From D-129 until D-134 a run proposed a Topic outside the scheme whatever its length. One longer
than the Tags column's 255 characters could never be confirmed, because confirming creates a Tag,
and until D-133 it could not be rejected either. Since D-133 the reject route reads a value up to
MAXIMUM_PROPOSED_TAG_LENGTH, so a person could only reject it, and the security review of D-133
left two notes on that:
- **L1:** each rejection is kept in ``rejected_tags``, which nothing prunes, as long as the proposal,
  so steered runs could grow one row by a reply's worth each;
- **I1:** a proposal past MAXIMUM_PROPOSED_TAG_LENGTH could be produced on purpose, and would be
  stuck.

Since D-134 rule 4d of ``apply_classification`` discards such a Topic into
``discarded_suggestions``, which is not exposed and which each run replaces. Here, through the
routes:

- **A classify suggesting a 359-character Topic,** the re-audit's probe length, beside a short one:
  the short one is proposed and the long one is not. The reply does not carry the discard. The record
  holds it with its confidence, and no Tag or link is made. The reject route, which reads a value
  that long, does not find it: the document's own 404 body, with nothing recorded, so no rejection
  that long can be kept.
- **A Topic exactly as long as a tag name** is proposed, and the confirm route makes the Tag. So
  every proposal a run makes can be confirmed.

The apply layer's own tests, every confidence and both models' thresholds, are in
apps/documents/tests/test_classification_d128.py. A proposal stored before D-134 is still rejected
through the route: apps/api/tests/test_fr10_reject_long_proposal.py.

Every test runs from an Employee and an Administrator session through ``session_client``. The stub
answers classification below the classifying model's own threshold, and no provider is reached.
"""

import pytest

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.classification import confidence_threshold
from apps.documents.models import (
    ContentTag,
    Document,
    DocumentAnalysis,
    ExtractedContent,
    Tag,
    normalise_tag_name,
)
from apps.documents.tests.classification_builders import EPSILON, STUB_CHAT_MODEL, classification

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
NOT_FOUND_BODY = {"detail": "No Document matches the given query."}
# The classification builders' model, which the stub's replies here carry: its own threshold.
BELOW = round(confidence_threshold(STUB_CHAT_MODEL) - EPSILON, 3)

# The re-audit's probe length (finding C15), normalised as a proposal or a discard holds it.
PROBE_LENGTH = 359
LONG_TOPIC = ("berth renewal and crane replacement " * 10)[:PROBE_LENGTH]
assert len(LONG_TOPIC) == PROBE_LENGTH > NAME_MAX_LENGTH
assert normalise_tag_name(LONG_TOPIC) == LONG_TOPIC
# Exactly as long as a tag name, normalised.
AT_THE_COLUMN = ("crane safety audit " * 14)[:NAME_MAX_LENGTH]
assert len(AT_THE_COLUMN) == NAME_MAX_LENGTH
assert normalise_tag_name(AT_THE_COLUMN) == AT_THE_COLUMN
SHORT_TOPIC = "berth renewal"


def make_document(user):
    document = Document.objects.create(
        title="Harbour works plan", file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=BOTH_ROLES,
    )
    ExtractedContent.objects.create(document=document, extracted_text="Berths, cranes and a timetable.")
    return document


def classify(client, stub, document, *written):
    """A classify through the route, the stub suggesting each Topic as written, below the
    threshold."""
    stub.classification = classification(tags=[(TOPIC_DIMENSION, value, BELOW) for value in written])
    response = client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")
    stub.classification = None
    assert response.status_code == 200, response.content
    return response.json()


def act(client, action, document, value):
    return client.post(
        f"{DOCUMENTS_URL}/{document.id}/proposed-tags/{action}",
        {"dimension": TOPIC_DIMENSION, "value": value}, format="json",
    )


def entry(value):
    return {"dimension": TOPIC_DIMENSION, "value": value, "confidence": BELOW}


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def test_a_classify_discards_a_topic_longer_than_a_tag_name_and_proposes_the_short_one_beside_it(
    session_client, stub_ai_service
):
    client = session_client.client
    document = make_document(session_client.user)

    body = classify(client, stub_ai_service, document, LONG_TOPIC.upper(), SHORT_TOPIC)

    assert body["classification"]["proposed_tags"] == [entry(SHORT_TOPIC)]
    assert "discarded_suggestions" not in body["classification"]  # recorded, and not exposed
    assert body["tag_details"] == []
    analysis = DocumentAnalysis.objects.get(document=document)
    assert analysis.discarded_suggestions == [entry(LONG_TOPIC)]
    assert not Tag.objects.exists()
    assert not links_of(document).exists()

    # Not proposed, so the reject route, which reads a value this long (D-133), finds nothing: the
    # document's own 404 body, and no rejection that long is kept. (Confirm refuses the value itself,
    # 400, as past its own bound: test_fr10_reject_long_proposal.py.)
    response = act(client, "reject", document, LONG_TOPIC)
    assert response.status_code == 404, response.content
    assert response.json() == NOT_FOUND_BODY
    analysis.refresh_from_db()
    assert (analysis.proposed_tags, analysis.rejected_tags) == ([entry(SHORT_TOPIC)], [])
    assert analysis.discarded_suggestions == [entry(LONG_TOPIC)]
    assert not Tag.objects.exists()


def test_a_topic_exactly_as_long_as_a_tag_name_is_proposed_and_the_confirm_route_makes_the_tag(
    session_client, stub_ai_service
):
    client = session_client.client
    document = make_document(session_client.user)

    body = classify(client, stub_ai_service, document, AT_THE_COLUMN.upper())

    assert body["classification"]["proposed_tags"] == [entry(AT_THE_COLUMN)]
    assert DocumentAnalysis.objects.get(document=document).discarded_suggestions == []

    response = act(client, "confirm", document, AT_THE_COLUMN)

    assert response.status_code == 200, response.content
    confirmed = response.json()
    assert confirmed["classification"]["proposed_tags"] == []
    assert [(tag["dimension"], tag["name"], tag["confirmed"]) for tag in confirmed["tag_details"]] == [
        (TOPIC_DIMENSION, AT_THE_COLUMN, True)
    ]
    assert Tag.objects.get().tag_name == AT_THE_COLUMN
