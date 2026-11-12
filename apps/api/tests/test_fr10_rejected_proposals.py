"""A proposal a person rejects through ``POST /api/documents/{id}/proposed-tags/reject`` stays rejected
(the requirements audit of D-128, finding A5; the lead's decision of 13 November 2026).

The auditor executed the finding. A held value was rejected through the route, and the next classify
created and linked it as an AI tag at or above the threshold, or proposed it again below it. That
contradicts FR-10's correction clause ("any value a user edits are retained and is not overwritten
by later reprocessing") and UC-09 A3. Here:

- **The audit's own case,** in Project, Process and Topic: after the rejection, a classify at the
  threshold creates no Tag and no link, and one below it proposes nothing.
- **In the scheme:** an Administrator then adds the value as vocabulary (``POST /api/tags``), so the
  document's prompt lists it, and a classify still does not link it.
- **Scope:** the rejection is this document's. The same value on another document is created at the
  threshold and held below it, as for any value.
- **A person is never blocked:** a person can still apply the value by ``tag_id`` once it exists,
  and a Topic by its name.

Every route runs from an Employee and an Administrator session through ``session_client``. The stub
answers classification, and no provider is reached. The record itself, ``rejected_tags``, is not in
any reply; apps/documents/tests/test_classification_rejected.py reads it.
"""

import pytest

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    REPOSITORY_TAG_DIMENSIONS,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.documents.classification import confidence_threshold
from apps.documents.models import ContentTag, Document, ExtractedContent, Tag
from apps.documents.tests.classification_builders import EPSILON, STUB_CHAT_MODEL, classification

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
TAGS_URL = "/api/tags"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
# The classification builders' model, which every scripted reply here carries: its own threshold.
THRESHOLD = confidence_threshold(STUB_CHAT_MODEL)
BELOW = round(THRESHOLD - EPSILON, 3)
SIDES = {"at-threshold": THRESHOLD, "below-threshold": BELOW}
VALUE = "harbour upgrade"


def make_document(user, title="Harbour works plan"):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=BOTH_ROLES,
    )
    ExtractedContent.objects.create(document=document, extracted_text="Berths, cranes and a timetable.")
    return document


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def classify(client, stub, document, dimension, confidence):
    """A classify through the route, the stub suggesting ``VALUE`` in ``dimension``."""
    stub.classification = classification(tags=[(dimension, "Harbour  Upgrade", confidence)])
    response = client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")
    assert response.status_code == 200, response.content
    stub.classification = None
    return response.json()


def rejected_on(client, stub, document, dimension):
    """The audit's set-up: the value is held below the threshold, then rejected through the route."""
    held = classify(client, stub, document, dimension, BELOW)
    assert held["classification"]["proposed_tags"] == [
        {"dimension": dimension, "value": VALUE, "confidence": BELOW}
    ]
    response = client.post(
        f"{DOCUMENTS_URL}/{document.id}/proposed-tags/reject",
        {"dimension": dimension, "value": VALUE}, format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["classification"]["proposed_tags"] == []
    assert "rejected_tags" not in body["classification"]  # recorded, and not exposed
    assert not Tag.objects.filter(tag_name=VALUE).exists()


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_rejected_proposal_is_neither_created_at_the_threshold_nor_proposed_again_below_it(
    session_client, stub_ai_service, dimension
):
    client = session_client.client
    document = make_document(session_client.user)
    rejected_on(client, stub_ai_service, document, dimension)

    at = classify(client, stub_ai_service, document, dimension, THRESHOLD)

    assert (at["tag_details"], at["classification"]["proposed_tags"]) == ([], [])
    assert not Tag.objects.filter(tag_name=VALUE).exists()
    assert not links_of(document).exists()

    below = classify(client, stub_ai_service, document, dimension, BELOW)

    assert (below["tag_details"], below["classification"]["proposed_tags"]) == ([], [])
    assert not Tag.objects.filter(tag_name=VALUE).exists()


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_rejected_value_is_not_linked_after_an_administrator_adds_it_to_the_scheme(
    session_client, administrator_client, stub_ai_service, dimension
):
    client = session_client.client
    document = make_document(session_client.user)
    rejected_on(client, stub_ai_service, document, dimension)
    added = administrator_client.post(
        TAGS_URL, {"dimension": dimension, "tag_name": "Harbour Upgrade"}, format="json"
    )
    assert added.status_code == 201, added.content

    body = classify(client, stub_ai_service, document, dimension, THRESHOLD)

    # The premise: vocabulary now, so in this document's scheme and listed to the model.
    _, _, shown = stub_ai_service.classify_calls[-1]
    assert VALUE in shown.tags[dimension]
    assert (body["tag_details"], body["classification"]["proposed_tags"]) == ([], [])
    assert not links_of(document).exists()


@pytest.mark.parametrize("side", sorted(SIDES))
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_rejection_on_one_document_does_not_block_the_value_on_another(
    session_client, stub_ai_service, dimension, side
):
    client = session_client.client
    rejecting = make_document(session_client.user, title="Harbour works plan")
    other = make_document(session_client.user, title="Port budget")
    rejected_on(client, stub_ai_service, rejecting, dimension)

    body = classify(client, stub_ai_service, other, dimension, SIDES[side])

    if side == "at-threshold":
        [entry] = body["tag_details"]
        assert (entry["dimension"], entry["name"], entry["applied_by"], entry["provisional"]) == (
            dimension, VALUE, AI_APPLIED, False,
        )
        assert links_of(other).get().tag == Tag.objects.get(tag_name=VALUE, dimension=dimension)
    else:
        assert body["classification"]["proposed_tags"] == [
            {"dimension": dimension, "value": VALUE, "confidence": BELOW}
        ]
    assert not links_of(rejecting).exists()


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_person_can_still_apply_a_rejected_value_by_its_id_once_it_exists(
    session_client, administrator_client, stub_ai_service, dimension
):
    client = session_client.client
    document = make_document(session_client.user)
    rejected_on(client, stub_ai_service, document, dimension)
    added = administrator_client.post(
        TAGS_URL, {"dimension": dimension, "tag_name": "Harbour Upgrade"}, format="json"
    )
    assert added.status_code == 201, added.content

    applied = client.post(
        f"{DOCUMENTS_URL}/{document.id}/tags", {"tag_id": added.json()["tag_id"]}, format="json"
    )

    assert applied.status_code == 201, applied.content
    [entry] = applied.json()["tag_details"]
    assert (entry["dimension"], entry["name"], entry["applied_by"], entry["confirmed"]) == (
        dimension, VALUE, USER_APPLIED, True,
    )


def test_a_person_can_still_name_a_rejected_topic(session_client, stub_ai_service):
    client = session_client.client
    document = make_document(session_client.user)
    rejected_on(client, stub_ai_service, document, TOPIC_DIMENSION)

    applied = client.post(
        f"{DOCUMENTS_URL}/{document.id}/tags",
        {"dimension": TOPIC_DIMENSION, "tag_name": "Harbour Upgrade"}, format="json",
    )

    assert applied.status_code == 201, applied.content
    [entry] = applied.json()["tag_details"]
    assert (entry["dimension"], entry["name"], entry["applied_by"], entry["confirmed"]) == (
        TOPIC_DIMENSION, VALUE, USER_APPLIED, True,
    )
    # A later run leaves the person's link alone, and still does not take the value up itself.
    after = classify(client, stub_ai_service, document, TOPIC_DIMENSION, THRESHOLD)
    assert [(item["name"], item["applied_by"]) for item in after["tag_details"]] == [(VALUE, USER_APPLIED)]
