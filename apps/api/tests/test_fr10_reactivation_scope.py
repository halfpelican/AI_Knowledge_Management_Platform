"""A retired tag comes back only through a document every role reads (D-128's security review,
finding 1).

The review's two-world probe, inverted. A document both roles read carries a value, in Project,
Process or Topic, from before an Administrator retired it (``DELETE /api/tags/{id}``, 200). Retired,
the value is offered nowhere, though the readable document still shows it (D-72). Then one of three
things brings the value in on an Administrator-only document:

- a classification that suggests it at or above the threshold (``apply_classification`` rule 4d);
- an Administrator confirming a proposal of it, held below the threshold (``confirm_proposed_tag``);
- for a Topic, an Administrator typing its name (``apply_tag``'s name form, D-105's own path).

Until the fix each one reactivated the tag, grown. The readable carrier then put it back in the
options of every document an Employee reads: an Employee saw it reappear while nothing they could
read had changed, which told them that the restricted material carries it (CLAUDE.md invariant 1).
Now the tag stays retired and the Administrator-only document holds the link. Everything an
Employee reads is identical before and after: each readable document's ``tag_options``, ``tags`` and
``tag_details``, and the browse facets.

The positive case is the same three things on a document every role reads. They do reactivate the
tag, grown, and an Employee is offered it again. There the change is that document's own link,
which every role can see, exactly as for a value created there.

Routes only. The stub answers classification, and no provider is reached.
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
VALUE = "atlas"

CLASSIFIED = "classified at the threshold"
CONFIRMED = "a held proposal confirmed"
NAMED = "a Topic named"
CASES = [
    (dimension, action)
    for dimension in REPOSITORY_TAG_DIMENSIONS
    for action in (CLASSIFIED, CONFIRMED, NAMED)
    if action != NAMED or dimension == TOPIC_DIMENSION  # the name form is Topic-only
]
# The link each action leaves on the document: (applied_by, confirmed, provisional, removed).
LINK_LEFT = {
    CLASSIFIED: (AI_APPLIED, False, False, False),
    CONFIRMED: (AI_APPLIED, True, False, False),
    NAMED: (USER_APPLIED, True, False, False),
}


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


def bring_in(client, stub, document, dimension, action):
    """``action`` on ``document`` through the routes, as ``client``'s role."""
    if action == NAMED:
        response = client.post(
            f"{DOCUMENTS_URL}/{document.id}/tags",
            {"dimension": TOPIC_DIMENSION, "tag_name": "Atlas"}, format="json",
        )
        assert response.status_code == 201, response.content
        return
    stub.classification = classification(
        tags=[(dimension, "Atlas", THRESHOLD if action == CLASSIFIED else BELOW)]
    )
    response = client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")
    assert response.status_code == 200, response.content
    stub.classification = None
    if action == CONFIRMED:
        assert response.json()["classification"]["proposed_tags"] == [
            {"dimension": dimension, "value": VALUE, "confidence": BELOW}
        ]
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


@pytest.mark.parametrize("dimension, action", CASES)
def test_a_retired_value_brought_in_on_administrator_only_material_stays_retired_and_an_employee_sees_nothing_move(
    employee, administrator, employee_client, administrator_client, stub_ai_service, dimension, action
):
    readable, value, watched = retired_value(dimension, employee, administrator_client)
    restricted = make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])
    before = seen_by_the_employee(employee_client, readable, watched)
    # The premise: retired, the value is offered nowhere, though the readable document shows it.
    assert VALUE not in offered(employee_client, watched, dimension)
    assert VALUE not in offered(employee_client, readable, dimension)
    assert VALUE in before[readable.title]["tags"][dimension.lower()]

    bring_in(administrator_client, stub_ai_service, restricted, dimension, action)

    # What the invariant is about first: nothing an Employee reads has moved.
    assert seen_by_the_employee(employee_client, readable, watched) == before
    # And why: the tag stayed retired, its grown unchanged, while the link was made all the same.
    value.refresh_from_db()
    assert (value.active, value.grown) == (False, False)
    assert link_on(restricted, value) == LINK_LEFT[action]


@pytest.mark.parametrize("dimension, action", CASES)
def test_a_retired_value_brought_in_on_a_document_every_role_reads_is_reactivated_grown(
    session_client, employee, employee_client, administrator_client, stub_ai_service, dimension, action
):
    """The positive case, from both roles: on a document every role reads, the same three things
    reactivate the value, grown, and an Employee is offered it again everywhere a carrier they read
    makes it eligible, the document acted on included."""
    readable, value, watched = retired_value(dimension, employee, administrator_client)
    shared = make_document(session_client.user, title="Atlas plan", roles=BOTH_ROLES)

    bring_in(session_client.client, stub_ai_service, shared, dimension, action)

    value.refresh_from_db()
    assert (value.active, value.grown) == (True, True)
    assert link_on(shared, value) == LINK_LEFT[action]
    for document in (shared, watched, readable):
        assert VALUE in offered(employee_client, document, dimension), document.title
