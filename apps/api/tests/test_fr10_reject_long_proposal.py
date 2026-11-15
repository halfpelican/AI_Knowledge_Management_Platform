"""A proposed Topic longer than the Tags column can be rejected (D-133, 15 November 2026).

The requirements re-audit of ``d909537`` (finding C15) proposed a 359-character Topic and found it
could be neither confirmed nor rejected. Both proposed-tags routes read ``ProposedTagSerializer``,
whose ``value`` was capped at the column's 255 characters, so both answered 400 keyed on ``value``:
the proposal stayed, nothing was recorded in ``rejected_tags``, and the next run could propose it
again. The cap came with #85's ``ProposedTopicSerializer`` and predates D-128 and D-129.

Since D-133 the reject route reads ``ProposedTagRejectSerializer``, whose ``value`` may be up to
MAXIMUM_PROPOSED_TAG_LENGTH characters: a rejection writes only JSON and matches by normalised
value, and a run proposes a Topic whatever its length (D-129). Confirm keeps the column's cap and
its 400, because confirming creates a Tag. Here:

- **The probe's case:** a 359-character Topic proposal is rejected, 200. It leaves
  ``proposed_tags``, joins ``rejected_tags`` with the machine's confidence, and nothing is created.
- **The rejection sticks:** a later classify suggesting the same Topic skips it (rule 4b).
- **Confirm is unchanged:** the same proposal confirmed is 400 keyed on ``value``, and stays.
- **The bound:** a value of exactly MAXIMUM_PROPOSED_TAG_LENGTH characters is read (not proposed
  here, so the document's 404), and one character more is 400 keyed on ``value``.

Every test runs from an Employee and an Administrator session through ``session_client``. The stub
answers classification below the classifying model's own threshold, and no provider is reached.
"""

import pytest

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_PROPOSED_TAG_LENGTH,
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

# The re-audit's probe length (finding C15): over the column, and normalised as a proposal holds it,
# lower case with single spaces, so the value the page sends back is the value held.
PROBE_LENGTH = 359
LONG_TOPIC = ("berth renewal and crane replacement " * 10)[:PROBE_LENGTH]
assert len(LONG_TOPIC) == PROBE_LENGTH > NAME_MAX_LENGTH
assert normalise_tag_name(LONG_TOPIC) == LONG_TOPIC
PROPOSAL = {"dimension": TOPIC_DIMENSION, "value": LONG_TOPIC, "confidence": BELOW}


def make_document(user):
    document = Document.objects.create(
        title="Harbour works plan", file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=BOTH_ROLES,
    )
    ExtractedContent.objects.create(document=document, extracted_text="Berths, cranes and a timetable.")
    return document


def classify(client, stub, document):
    """A classify through the route, the stub suggesting the long Topic in capitals, below the
    threshold: outside the scheme, so it is proposed (D-129), normalised."""
    stub.classification = classification(tags=[(TOPIC_DIMENSION, LONG_TOPIC.upper(), BELOW)])
    response = client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")
    assert response.status_code == 200, response.content
    stub.classification = None
    return response.json()


def act(client, action, document, value):
    return client.post(
        f"{DOCUMENTS_URL}/{document.id}/proposed-tags/{action}",
        {"dimension": TOPIC_DIMENSION, "value": value}, format="json",
    )


def analysis_of(document):
    return DocumentAnalysis.objects.get(document=document)


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


@pytest.fixture
def proposed(session_client, stub_ai_service):
    """A document whose classification proposed the 359-character Topic."""
    document = make_document(session_client.user)
    body = classify(session_client.client, stub_ai_service, document)
    assert body["classification"]["proposed_tags"] == [PROPOSAL]
    return document


def test_rejecting_a_topic_longer_than_the_column_drops_it_and_records_the_rejection(
    session_client, proposed
):
    response = act(session_client.client, "reject", proposed, LONG_TOPIC)

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"classification", "tag_details"}
    assert body["classification"]["proposed_tags"] == []
    assert "rejected_tags" not in body["classification"]  # recorded, and not exposed
    assert body["tag_details"] == []
    analysis = analysis_of(proposed)
    assert analysis.proposed_tags == []
    assert analysis.rejected_tags == [PROPOSAL]  # with the machine's confidence
    assert not Tag.objects.exists()
    assert not links_of(proposed).exists()


def test_a_rejected_long_topic_is_not_proposed_again(session_client, stub_ai_service, proposed):
    """Before D-133 nothing was recorded, so this run proposed it again."""
    client = session_client.client
    assert act(client, "reject", proposed, LONG_TOPIC).status_code == 200

    body = classify(client, stub_ai_service, proposed)

    assert (body["classification"]["proposed_tags"], body["tag_details"]) == ([], [])
    analysis = analysis_of(proposed)
    assert (analysis.proposed_tags, analysis.discarded_suggestions) == ([], [])
    assert analysis.rejected_tags == [PROPOSAL]
    assert not Tag.objects.exists()


def test_confirming_a_topic_longer_than_the_column_is_still_400(session_client, proposed):
    """Confirming creates a Tag, whose name the column limits, so confirm keeps its cap."""
    response = act(session_client.client, "confirm", proposed, LONG_TOPIC)

    assert response.status_code == 400, response.content
    assert set(response.json()) == {"value"}
    analysis = analysis_of(proposed)
    assert analysis.proposed_tags == [PROPOSAL]
    assert analysis.rejected_tags == []
    assert not Tag.objects.exists()
    assert not links_of(proposed).exists()


def test_the_reject_route_reads_a_value_up_to_its_bound_and_refuses_one_past_it(session_client, proposed):
    """At the bound the value passes validation, and is not proposed here: the document's own 404
    body. One character more is 400 keyed on ``value``. Neither changes anything."""
    client = session_client.client

    at_bound = act(client, "reject", proposed, "x" * MAXIMUM_PROPOSED_TAG_LENGTH)
    past_bound = act(client, "reject", proposed, "x" * (MAXIMUM_PROPOSED_TAG_LENGTH + 1))

    assert at_bound.status_code == 404, at_bound.content[:200]
    assert at_bound.json() == NOT_FOUND_BODY
    assert past_bound.status_code == 400, past_bound.content[:200]
    assert set(past_bound.json()) == {"value"}
    analysis = analysis_of(proposed)
    assert (analysis.proposed_tags, analysis.rejected_tags) == ([PROPOSAL], [])
