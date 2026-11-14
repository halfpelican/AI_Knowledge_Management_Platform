"""A retired tag comes back only through a person, on a document every role reads (D-128's security
review, finding 1; D-129).

The set-up is the review's. A document both roles read carries a value, in Project, Process or
Topic, from before an Administrator retired it (``DELETE /api/tags/{id}``, 200). Retired, the value is
offered nowhere, though the readable document still shows it (D-72).

- **The classifier never brings it back** (D-129, which reverses D-128's creation and reactivation).
  A classification that suggests the retired value at or above the threshold proposes it (a Topic)
  or discards it (a Project or Process), on a document every role reads and on an Administrator-only
  one alike. The tag stays retired and no link is made. Until D-129 the classifier reactivated it,
  and until the security review's fix it did so even from Administrator-only material, which the
  readable carrier then showed to every Employee.
- **A person brings it back only on a document every role reads.** That happens when an
  Administrator confirms a proposal of the value (``confirm_proposed_tag``) or, for a Topic, types
  its name (``apply_tag``'s name form, D-105's own path).
  - On an Administrator-only document the tag stays retired, its ``grown`` unchanged, and the link
    is made. Everything an Employee reads is identical before and after: each readable document's
    ``tag_options``, ``tags`` and ``tag_details``, and the browse facets.
  - On a document every role reads the tag is reactivated, grown, and an Employee is offered it
    again. The change there is that document's own link, which every role can see.

A Project or Process proposal is written onto the analysis row, as a run left one while D-128 was in
force, since a classification discards such a value since D-129. Routes only. The stub answers
classification, and no provider is reached.
"""

import pytest
from django.utils import timezone

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
from apps.documents.models import ContentTag, Document, DocumentAnalysis, ExtractedContent, Tag
from apps.documents.tests.classification_builders import EPSILON, STUB_CHAT_MODEL, classification

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
TAGS_URL = "/api/tags"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
# The classification builders' model, which every scripted reply here carries: its own threshold.
THRESHOLD = confidence_threshold(STUB_CHAT_MODEL)
ABOVE = round(min(1.0, THRESHOLD + EPSILON), 3)
BELOW = round(THRESHOLD - EPSILON, 3)
VALUE = "atlas"
AUDIENCES = {"every role": BOTH_ROLES, "administrator only": [ADMINISTRATOR_ROLE_NAME]}

CONFIRMED = "a proposal confirmed"
NAMED = "a Topic named"
PERSON_CASES = [
    (dimension, action)
    for dimension in REPOSITORY_TAG_DIMENSIONS
    for action in (CONFIRMED, NAMED)
    if action != NAMED or dimension == TOPIC_DIMENSION  # the name form is Topic-only
]
# The link each person's action leaves on the document: (applied_by, confirmed, provisional, removed).
LINK_LEFT = {CONFIRMED: (AI_APPLIED, True, False, False), NAMED: (USER_APPLIED, True, False, False)}


def make_document(user, *, title, roles):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=roles,
    )
    ExtractedContent.objects.create(document=document, extracted_text="Quarterly figures and plans.")
    return document


def retired_value(dimension, employee, administrator_client):
    """The review's setup: a document both roles read carries the value, which an Administrator
    then retires through the route. Returns that document, the Tag, and a second document an
    Employee reads, which carries nothing."""
    readable = make_document(employee, title="Atlas kickoff notes", roles=BOTH_ROLES)
    value = Tag.objects.create(tag_name=VALUE, dimension=dimension)  # vocabulary, as seeded
    ContentTag.objects.create(
        tag=value, source_type=DOCUMENT_SOURCE_TYPE, source_id=readable.pk,
        applied_by=USER_APPLIED, confirmed=True,
    )
    retired = administrator_client.delete(f"{TAGS_URL}/{value.pk}")
    assert retired.status_code == 200, retired.content
    assert retired.json()["active"] is False
    watched = make_document(employee, title="Staff handbook", roles=[EMPLOYEE_ROLE_NAME])
    return readable, value, watched


def classify(client, stub, document, *tags):
    stub.classification = classification(tags=list(tags))
    response = client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")
    assert response.status_code == 200, response.content
    stub.classification = None
    return response.json()


def by_a_person(client, stub, document, dimension, action):
    """``action`` on ``document`` through the routes, as ``client``'s role."""
    if action == NAMED:
        response = client.post(
            f"{DOCUMENTS_URL}/{document.id}/tags",
            {"dimension": TOPIC_DIMENSION, "tag_name": "Atlas"}, format="json",
        )
        assert response.status_code == 201, response.content
        return
    if dimension == TOPIC_DIMENSION:
        body = classify(client, stub, document, (dimension, "Atlas", BELOW))
        assert body["classification"]["proposed_tags"] == [
            {"dimension": dimension, "value": VALUE, "confidence": BELOW}
        ]
    else:  # discarded by a classification since D-129: the proposal as D-128 left one
        DocumentAnalysis.objects.update_or_create(
            document=document,
            defaults={"classified_at": timezone.now(),
                      "proposed_tags": [{"dimension": dimension, "value": VALUE, "confidence": BELOW}]},
        )
    response = client.post(
        f"{DOCUMENTS_URL}/{document.id}/proposed-tags/confirm",
        {"dimension": dimension, "value": VALUE}, format="json",
    )
    assert response.status_code == 200, response.content


def seen_by_the_employee(employee_client, *documents):
    """Everything an Employee reads in which the value could appear: each document's
    ``tag_options``, ``tags`` and ``tag_details``, and the repository's browse facets."""
    seen = {}
    for document in documents:
        response = employee_client.get(f"{DOCUMENTS_URL}/{document.id}")
        assert response.status_code == 200, response.content
        body = response.json()
        seen[document.title] = {key: body[key] for key in ("tag_options", "tags", "tag_details")}
    browse = employee_client.get(f"{DOCUMENTS_URL}/browse")
    assert browse.status_code == 200, browse.content
    seen["facets"] = browse.json()["facets"]
    return seen


def offered(client, document, dimension):
    response = client.get(f"{DOCUMENTS_URL}/{document.id}")
    assert response.status_code == 200, response.content
    return [entry["tag_name"] for entry in response.json()["tag_options"][dimension]]


def link_on(document, value):
    [link] = ContentTag.objects.filter(
        tag=value, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk
    )
    return (link.applied_by, link.confirmed, link.provisional, link.removed)


@pytest.mark.parametrize("audience", sorted(AUDIENCES))
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_the_classifier_never_brings_a_retired_value_back(
    employee, administrator, employee_client, administrator_client, stub_ai_service, dimension, audience
):
    """At and above the threshold: a Topic is proposed and a Project or Process value is discarded,
    and the tag stays retired with no link made, whoever can read the document (D-129)."""
    readable, value, watched = retired_value(dimension, employee, administrator_client)
    document = make_document(administrator, title="Atlas plan", roles=AUDIENCES[audience])
    before = seen_by_the_employee(employee_client, readable, watched)

    for confidence in (THRESHOLD, ABOVE):
        body = classify(administrator_client, stub_ai_service, document, (dimension, "Atlas", confidence))

        entry = {"dimension": dimension, "value": VALUE, "confidence": confidence}
        record = DocumentAnalysis.objects.get(document=document)
        if dimension == TOPIC_DIMENSION:
            assert body["classification"]["proposed_tags"] == [entry], confidence
            assert record.discarded_suggestions == [], confidence
        else:
            assert body["classification"]["proposed_tags"] == [], confidence
            assert record.discarded_suggestions == [entry], confidence
        assert body["tag_details"] == [], confidence
        value.refresh_from_db()
        assert (value.active, value.grown) == (False, False), confidence
        assert not ContentTag.objects.filter(tag=value, source_id=document.pk).exists(), confidence

    assert seen_by_the_employee(employee_client, readable, watched) == before


@pytest.mark.parametrize("dimension, action", PERSON_CASES)
def test_a_person_bringing_a_retired_value_in_on_administrator_only_material_leaves_it_retired(
    employee, administrator, employee_client, administrator_client, stub_ai_service, dimension, action
):
    readable, value, watched = retired_value(dimension, employee, administrator_client)
    restricted = make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])
    before = seen_by_the_employee(employee_client, readable, watched)
    # The premise: retired, the value is offered nowhere, though the readable document shows it.
    assert VALUE not in offered(employee_client, watched, dimension)
    assert VALUE not in offered(employee_client, readable, dimension)
    assert VALUE in before[readable.title]["tags"][dimension.lower()]

    by_a_person(administrator_client, stub_ai_service, restricted, dimension, action)

    # What the invariant is about first: nothing an Employee reads has moved.
    assert seen_by_the_employee(employee_client, readable, watched) == before
    # And why: the tag stayed retired, its grown unchanged, while the link was made all the same.
    value.refresh_from_db()
    assert (value.active, value.grown) == (False, False)
    assert link_on(restricted, value) == LINK_LEFT[action]


@pytest.mark.parametrize("dimension, action", PERSON_CASES)
def test_a_person_bringing_a_retired_value_in_on_a_document_every_role_reads_reactivates_it(
    session_client, employee, employee_client, administrator_client, stub_ai_service, dimension, action
):
    """From both roles: on a document every role reads, the person's action reactivates the value,
    grown, and an Employee is offered it again wherever a carrier they read makes it eligible."""
    readable, value, watched = retired_value(dimension, employee, administrator_client)
    shared = make_document(session_client.user, title="Atlas plan", roles=BOTH_ROLES)

    by_a_person(session_client.client, stub_ai_service, shared, dimension, action)

    value.refresh_from_db()
    assert (value.active, value.grown) == (True, True)
    assert link_on(shared, value) == LINK_LEFT[action]
    for document in (shared, watched, readable):
        assert VALUE in offered(employee_client, document, dimension), document.title
