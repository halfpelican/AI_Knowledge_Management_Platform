"""The proposed-tags routes in every dimension (D-128, 12 November 2026):
``POST /api/documents/{id}/proposed-tags/confirm`` and ``/reject``, body ``{"dimension", "value"}``.

Since D-129 (13 November 2026) a classification proposes a Topic outside the scheme, at any
confidence, and discards a Project or Process value. A Project or Process proposal is one a run made
while D-128 was in force, when such a value was held below the threshold, and the routes still act on
it. Confirming a proposal is when its Tag is created (or brought back), grown, and linked
``applied_by="ai"``, confirmed, not provisional, with the proposal's confidence; rejecting it creates
nothing. A proposal is matched by its dimension AND its normalised value, so acting on one dimension
leaves the same value proposed in another.

The order on both routes is the session, then the scoped 404 (D-46), then ``contribute_content``'s
403, then the body: 400 keyed on ``dimension`` for a missing one or any other (Department included),
and 400 keyed on ``value`` for a missing, blank or over-long one. Both roles hold
``contribute_content`` (accounts 0004), so the 403 is shown by taking it from the caller's role, as
apps/api/tests/test_document_classification.py does.

apps/api/tests/test_document_classification.py already holds the Topic path (confirm, reject, a value
not proposed, a value proposed under another dimension, a blank or over-long Topic value, and the
403 with a valid Topic body). This file holds what D-128 added: every dimension. Every test runs from
both roles through ``session_client``. A Topic is proposed by the classify route, the stub answering
below the classifying model's own threshold (``confidence_threshold``). A Project or Process
proposal is written onto the analysis row, as a run left one while D-128 was in force.
"""

from decimal import Decimal

import pytest

from apps.accounts.models import RolePermission
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    CONTRIBUTE_CONTENT_PERMISSION,
    DEPARTMENT_DIMENSION,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    PROJECT_DIMENSION,
    REPOSITORY_TAG_DIMENSIONS,
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
FORBIDDEN_BODY = {"detail": f"Your role does not hold the '{CONTRIBUTE_CONTENT_PERMISSION}' permission."}
# The classification builders' model, which the stub's replies here carry: its own threshold.
BELOW = round(confidence_threshold(STUB_CHAT_MODEL) - EPSILON, 3)
VALUE = "harbour upgrade"
ACTIONS = ("confirm", "reject")


def make_document(user):
    document = Document.objects.create(
        title="Harbour works plan", file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=BOTH_ROLES,
    )
    ExtractedContent.objects.create(document=document, extracted_text="Berths, cranes and a timetable.")
    return document


def propose(client, stub, document, *suggestions):
    """Hold each ``(dimension, value)`` as a proposal on ``document``, below the threshold, and
    return ``proposed_tags`` as they then stand.

    A Topic goes through the classify route, the stub suggesting it, since a classification proposes
    a Topic outside the scheme (D-129). A classification discards a Project or Process value outside
    the scheme, so such a proposal is written onto the analysis row after the run, as a run left one
    while D-128 was in force."""
    topics = [(dimension, value) for dimension, value in suggestions if dimension == TOPIC_DIMENSION]
    others = [(dimension, value) for dimension, value in suggestions if dimension != TOPIC_DIMENSION]
    stub.classification = classification(tags=[(dimension, value, BELOW) for dimension, value in topics])
    response = client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")
    assert response.status_code == 200, response.content
    stub.classification = None
    analysis = DocumentAnalysis.objects.get(document=document)
    if others:
        analysis.proposed_tags = analysis.proposed_tags + [
            {"dimension": dimension, "value": normalise_tag_name(value), "confidence": BELOW}
            for dimension, value in others
        ]
        analysis.save(update_fields=["proposed_tags"])
    return analysis.proposed_tags


def act(client, action, document, body):
    return client.post(f"{DOCUMENTS_URL}/{document.id}/proposed-tags/{action}", body, format="json")


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def held(document):
    return DocumentAnalysis.objects.get(document=document).proposed_tags


def revoke_contribute(user):
    RolePermission.objects.filter(
        role=user.role, permission__permission_name=CONTRIBUTE_CONTENT_PERMISSION
    ).delete()


# --- Confirm and reject, in every dimension ----------------------------------------------------------


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_confirming_a_proposal_creates_its_tag_grown_and_links_it_confirmed(
    session_client, stub_ai_service, dimension
):
    client = session_client.client
    document = make_document(session_client.user)
    assert propose(client, stub_ai_service, document, (dimension, "Harbour  Upgrade")) == [
        {"dimension": dimension, "value": VALUE, "confidence": BELOW}
    ]
    assert not Tag.objects.filter(tag_name=VALUE).exists()  # held, so not yet created

    response = act(client, "confirm", document, {"dimension": dimension, "value": " Harbour UPGRADE "})

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"classification", "tag_details"}
    assert body["classification"]["proposed_tags"] == []
    [entry] = body["tag_details"]
    assert {key: entry[key] for key in entry if key != "content_tag_id"} == {
        "dimension": dimension, "name": VALUE, "applied_by": AI_APPLIED, "confirmed": True,
        "provisional": False, "confidence": BELOW,
    }
    tag = Tag.objects.get(tag_name=VALUE)
    assert (tag.dimension, tag.active, tag.grown) == (dimension, True, True)
    link = links_of(document).get()
    assert str(link.pk) == entry["content_tag_id"]
    assert (link.tag_id, link.applied_by, link.confirmed, link.provisional, link.removed) == (
        tag.pk, AI_APPLIED, True, False, False,
    )
    assert link.confidence == Decimal(str(BELOW))
    assert held(document) == []


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_rejecting_a_proposal_drops_it_and_creates_nothing(session_client, stub_ai_service, dimension):
    client = session_client.client
    document = make_document(session_client.user)
    propose(client, stub_ai_service, document, (dimension, VALUE))

    response = act(client, "reject", document, {"dimension": dimension, "value": "Harbour Upgrade"})

    assert response.status_code == 200, response.content
    assert response.json()["classification"]["proposed_tags"] == []
    assert response.json()["tag_details"] == []
    assert held(document) == []
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


@pytest.mark.parametrize("action", ACTIONS)
def test_acting_on_a_proposal_in_one_dimension_leaves_the_same_value_proposed_in_another(
    session_client, stub_ai_service, action
):
    client = session_client.client
    document = make_document(session_client.user)
    propose(client, stub_ai_service, document, (PROJECT_DIMENSION, VALUE), (TOPIC_DIMENSION, VALUE))
    assert sorted(entry["dimension"] for entry in held(document)) == [PROJECT_DIMENSION, TOPIC_DIMENSION]

    response = act(client, action, document, {"dimension": PROJECT_DIMENSION, "value": VALUE})

    assert response.status_code == 200, response.content
    still_held = [{"dimension": TOPIC_DIMENSION, "value": VALUE, "confidence": BELOW}]
    assert response.json()["classification"]["proposed_tags"] == still_held
    assert held(document) == still_held
    created = {(PROJECT_DIMENSION, VALUE)} if action == "confirm" else set()
    assert set(Tag.objects.values_list("dimension", "tag_name")) == created


# --- The body: 400 keyed on the field ----------------------------------------------------------------

DIMENSION_BODIES = {
    "missing": {"value": VALUE},
    "department": {"dimension": DEPARTMENT_DIMENSION, "value": VALUE},
    "unknown": {"dimension": "Colour", "value": VALUE},
    "lower-case": {"dimension": PROJECT_DIMENSION.lower(), "value": VALUE},
}


@pytest.mark.parametrize("body", sorted(DIMENSION_BODIES))
@pytest.mark.parametrize("action", ACTIONS)
def test_a_missing_or_other_dimension_is_400_keyed_on_dimension(session_client, stub_ai_service, action, body):
    """The value is proposed in all three dimensions, so a dimension read as any of them would be
    acted on rather than refused."""
    client = session_client.client
    document = make_document(session_client.user)
    propose(client, stub_ai_service, document, *[(dimension, VALUE) for dimension in REPOSITORY_TAG_DIMENSIONS])
    before = held(document)

    response = act(client, action, document, DIMENSION_BODIES[body])

    assert response.status_code == 400, response.content
    assert set(response.json()) == {"dimension"}
    assert held(document) == before
    assert not Tag.objects.exists()


VALUE_BODIES = {
    "missing": None,
    "empty": "",
    "blank": "   ",
    "over-long": "x" * (NAME_MAX_LENGTH + 1),
}


@pytest.mark.parametrize("value", sorted(VALUE_BODIES))
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_missing_blank_or_over_long_value_is_400_keyed_on_value(
    session_client, stub_ai_service, dimension, action, value
):
    client = session_client.client
    document = make_document(session_client.user)
    propose(client, stub_ai_service, document, (dimension, VALUE))
    body = {"dimension": dimension}
    if VALUE_BODIES[value] is not None:
        body["value"] = VALUE_BODIES[value]

    response = act(client, action, document, body)

    assert response.status_code == 400, response.content
    assert set(response.json()) == {"value"}
    assert held(document) == [{"dimension": dimension, "value": VALUE, "confidence": BELOW}]
    assert not Tag.objects.exists()


# --- 403: contribute_content, after the scoped lookup and before the body -------------------------------


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_role_without_contribute_content_is_refused_before_the_body_is_read(
    session_client, stub_ai_service, dimension, action
):
    """The proposal is made while the role still holds the permission. Without it, the answer is the
    same 403 whatever the body: one the route would act on, and ones it would refuse 400."""
    client = session_client.client
    document = make_document(session_client.user)
    propose(client, stub_ai_service, document, (dimension, VALUE))
    revoke_contribute(session_client.user)

    for body in (
        {"dimension": dimension, "value": VALUE},
        {"dimension": DEPARTMENT_DIMENSION, "value": VALUE},
        {"dimension": dimension, "value": "   "},
        {},
    ):
        response = act(client, action, document, body)
        assert response.status_code == 403, (body, response.content)
        assert response.json() == FORBIDDEN_BODY

    assert held(document) == [{"dimension": dimension, "value": VALUE, "confidence": BELOW}]
    assert not Tag.objects.exists()
    assert not links_of(document).exists()
