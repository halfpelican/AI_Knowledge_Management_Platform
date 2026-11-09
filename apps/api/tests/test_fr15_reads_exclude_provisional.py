"""FR-15's reads stop at a provisional link (D-105).

FR-10: an assignment below the threshold is "marked provisional and presented for confirmation
rather than applied silently". A provisional AI tag is therefore not a tag of the document: it is
not in the detail's ``tags``, not a browse facet value and not a filter hit. It is visible in
``tag_details``, where it waits. Once confirmed it is all three. Both roles, through
``session_client``.
"""

from decimal import Decimal

import pytest

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
)
from apps.documents.models import ContentTag, Document, Tag

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
NAME = "harbour upgrade"


@pytest.fixture
def held(session_client):
    """A document with one provisional AI link in Project."""
    document = Document.objects.create(
        title="Harbour works", file_type="pdf", uploaded_by=session_client.user,
        status=DOCUMENT_INDEXED, visible_to_roles=BOTH_ROLES,
    )
    tag = Tag.objects.create(tag_name=NAME, dimension=PROJECT_DIMENSION)
    link = ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=AI_APPLIED, confirmed=False, provisional=True, confidence=Decimal("0.500"),
    )
    return document, link


def facet_values(body, name):
    return [entry["value"] for entry in body["facets"][name]]


def test_a_provisional_link_is_not_a_tag_a_facet_or_a_filter_hit_and_a_confirmed_one_is_all_three(
    session_client, held
):
    client = session_client.client
    document, link = held

    detail = client.get(f"{DOCUMENTS_URL}/{document.id}").json()
    assert detail["tags"]["project"] == []
    [entry] = detail["tag_details"]
    assert (entry["name"], entry["provisional"], entry["confirmed"]) == (NAME, True, False)
    browse = client.get(f"{DOCUMENTS_URL}/browse").json()
    assert facet_values(browse, "project") == []
    assert client.get(f"{DOCUMENTS_URL}/browse", {"project": NAME}).status_code == 204

    confirmed = client.post(f"{DOCUMENTS_URL}/{document.id}/tags/{link.id}/confirm", {}, format="json")
    assert confirmed.status_code == 200, confirmed.content

    detail = client.get(f"{DOCUMENTS_URL}/{document.id}").json()
    assert detail["tags"]["project"] == [NAME]
    [entry] = detail["tag_details"]
    assert (entry["provisional"], entry["confirmed"], entry["applied_by"]) == (False, True, AI_APPLIED)
    browse = client.get(f"{DOCUMENTS_URL}/browse").json()
    assert browse["facets"]["project"] == [{"value": NAME, "count": 1}]
    filtered = client.get(f"{DOCUMENTS_URL}/browse", {"project": NAME})
    assert filtered.status_code == 200
    assert [entry["doc_id"] for entry in filtered.json()["documents"]] == [str(document.id)]


def test_a_rejected_provisional_link_is_gone_from_every_read(session_client, held):
    client = session_client.client
    document, link = held

    removed = client.delete(f"{DOCUMENTS_URL}/{document.id}/tags/{link.id}")
    assert removed.status_code == 204

    detail = client.get(f"{DOCUMENTS_URL}/{document.id}").json()
    assert detail["tags"]["project"] == [] and detail["tag_details"] == []
    assert facet_values(client.get(f"{DOCUMENTS_URL}/browse").json(), "project") == []
    assert Tag.objects.filter(tag_name=NAME).exists()  # the vocabulary stays
