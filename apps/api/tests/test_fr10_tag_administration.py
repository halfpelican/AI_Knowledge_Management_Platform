"""FR-10's taxonomy, administered: ``GET /api/tags`` and ``DELETE /api/tags/{id}`` (D-119 finding 5;
D-105's dated note of 10 November 2026, night).

FR-10: "Tags are deactivated rather than deleted where content still references them, preserving
historical classification"; its CRUD line gives Tags "Delete". Both routes need a session and
``manage_tags``, which accounts 0008 gives the Administrator alone, checked before anything else:
401 without a session, 403 for a role without the code, and only then the 404 for an unknown tag.

- The inventory lists every Tag in Project, Process and Topic, active or not, ordered by dimension
  then name, each with ``item_count``: the sources, documents and meetings, with a link to it that
  is neither provisional nor removed, each source counted once.
- A delete deactivates a tag that any link references, in any state, and answers 200 with the tag;
  it deletes a tag nothing references and answers 204. A retired tag leaves every document's
  options and stays on the documents that carry it.

Every route is exercised from both roles through ``session_client``.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    DEPARTMENT_DIMENSION,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    MANAGE_TAGS_PERMISSION,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.documents.models import ContentTag, Document, Tag
from apps.meetings.models import Meeting

pytestmark = pytest.mark.django_db

TAGS_URL = "/api/tags"
DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
FORBIDDEN_BODY = {"detail": f"Your role does not hold the '{MANAGE_TAGS_PERMISSION}' permission."}
TAG_NOT_FOUND_BODY = {"detail": "No Tag matches the given query."}
ENTRY_KEYS = {"tag_id", "dimension", "tag_name", "active", "item_count"}


def is_administrator(session_client) -> bool:
    return session_client.role_name == ADMINISTRATOR_ROLE_NAME


def make_document(user, *, title="Bridge works", roles=None):
    return Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )


def link(tag, source_id, *, source_type=DOCUMENT_SOURCE_TYPE, **fields):
    fields.setdefault("applied_by", USER_APPLIED)
    fields.setdefault("confirmed", True)
    return ContentTag.objects.create(tag=tag, source_type=source_type, source_id=source_id, **fields)


def entry(tag, item_count, *, active=None):
    return {
        "tag_id": str(tag.pk), "dimension": tag.dimension, "tag_name": tag.tag_name,
        "active": tag.active if active is None else active, "item_count": item_count,
    }


def delete(client, tag_id):
    return client.delete(f"{TAGS_URL}/{tag_id}")


# --- GET /api/tags ------------------------------------------------------------------------------


def test_the_inventory_is_the_administrators_alone(session_client):
    Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)

    response = session_client.client.get(TAGS_URL)

    if is_administrator(session_client):
        assert response.status_code == 200, response.content
        assert [item["tag_name"] for item in response.json()] == ["bridge maintenance"]
    else:
        assert response.status_code == 403
        assert response.json() == FORBIDDEN_BODY


def test_the_inventory_needs_a_session(api_client):
    assert api_client.get(TAGS_URL).status_code == 401


def test_the_inventory_lists_every_tag_with_the_sources_that_carry_it(administrator_client, employee, administrator):
    shared = make_document(employee, title="Staff handbook")
    other = make_document(employee, title="Site rules")
    restricted = make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])
    meeting = Meeting.objects.create(
        title="Works meeting", meeting_date=date(2026, 11, 2), transcript_text="Transcript.",
        visible_to_roles=BOTH_ROLES,
    )
    bridge = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    link(bridge, shared.pk)
    link(bridge, shared.pk)  # the same source twice: counted once
    link(bridge, restricted.pk)  # the Administrator reads every source (D-66), so it counts
    link(bridge, meeting.pk, source_type=MEETING_SOURCE_TYPE)  # a meeting is a source too
    harbour = Tag.objects.create(tag_name="harbour upgrade", dimension=PROJECT_DIMENSION)
    link(harbour, shared.pk, applied_by=AI_APPLIED, confirmed=False, provisional=True,
         confidence=Decimal("0.500"))  # held: not yet a tag of its source
    link(harbour, other.pk, applied_by=AI_APPLIED, confirmed=False, removed=True,
         confidence=Decimal("0.970"))  # removed: no longer one
    purchasing = Tag.objects.create(tag_name="purchasing", dimension=PROCESS_DIMENSION)
    link(purchasing, other.pk, applied_by=AI_APPLIED, confirmed=False, confidence=Decimal("0.980"))
    retired = Tag.objects.create(tag_name="retired topic", dimension=TOPIC_DIMENSION, active=False)
    Tag.objects.create(tag_name="people", dimension=DEPARTMENT_DIMENSION)  # not a repository dimension

    response = administrator_client.get(TAGS_URL)

    assert response.status_code == 200, response.content
    body = response.json()
    assert all(set(item) == ENTRY_KEYS for item in body)
    # Ordered by dimension, then name: Process, Project, Topic.
    assert body == [
        entry(purchasing, 1),
        entry(bridge, 3),
        entry(harbour, 0),
        entry(retired, 0),
    ]


# --- DELETE /api/tags/{id} ----------------------------------------------------------------------


def test_deleting_an_unused_tag_removes_it(session_client):
    unused = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)

    response = delete(session_client.client, unused.pk)

    if is_administrator(session_client):
        assert response.status_code == 204, response.content
        assert not response.content
        assert not Tag.objects.filter(pk=unused.pk).exists()
    else:
        assert response.status_code == 403
        assert response.json() == FORBIDDEN_BODY
        assert Tag.objects.filter(pk=unused.pk).exists()


@pytest.mark.parametrize("state", ["applied", "held", "removed", "on a meeting"])
def test_deleting_a_tag_any_link_references_deactivates_it_and_keeps_the_link(
    administrator_client, employee, state
):
    document = make_document(employee)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    if state == "applied":
        kept = link(tag, document.pk)
    elif state == "held":
        kept = link(tag, document.pk, applied_by=AI_APPLIED, confirmed=False, provisional=True,
                    confidence=Decimal("0.500"))
    elif state == "removed":
        kept = link(tag, document.pk, applied_by=AI_APPLIED, confirmed=False, removed=True,
                    confidence=Decimal("0.970"))
    else:
        meeting = Meeting.objects.create(
            title="Works meeting", meeting_date=date(2026, 11, 2), transcript_text="Transcript.",
            visible_to_roles=BOTH_ROLES,
        )
        kept = link(tag, meeting.pk, source_type=MEETING_SOURCE_TYPE)

    response = delete(administrator_client, tag.pk)

    assert response.status_code == 200, response.content
    expected_count = 1 if state in ("applied", "on a meeting") else 0
    assert response.json() == entry(tag, expected_count, active=False)
    tag.refresh_from_db()
    assert tag.active is False
    assert ContentTag.objects.filter(pk=kept.pk, tag=tag).exists()


def test_deleting_a_retired_tag_that_is_still_referenced_answers_200_again(administrator_client, employee):
    document = make_document(employee)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION, active=False)
    link(tag, document.pk)

    response = delete(administrator_client, tag.pk)

    assert response.status_code == 200, response.content
    assert response.json() == entry(tag, 1, active=False)
    assert Tag.objects.filter(pk=tag.pk, active=False).exists()


def test_a_tag_whose_only_link_a_person_removed_is_deactivated_not_deleted(
    session_client, administrator_client
):
    """Since the requirements re-audit of ``5377e3a`` a person's removed link is kept, so it still
    references its tag: retiring the tag deactivates it (200) rather than deleting it (204). The
    removal runs from both roles; only an Administrator retires (``manage_tags``)."""
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    kept = link(tag, document.pk)  # a person's
    removed = session_client.client.delete(f"/api/documents/{document.id}/tags/{kept.id}")
    assert removed.status_code == 204, removed.content

    response = delete(administrator_client, tag.pk)

    assert response.status_code == 200, response.content
    assert response.json() == entry(tag, 0, active=False)
    assert ContentTag.objects.filter(pk=kept.pk, removed=True).exists()


def test_an_unknown_tag_is_404_for_the_administrator_and_403_before_it_for_an_employee(session_client):
    response = delete(session_client.client, uuid.uuid4())

    if is_administrator(session_client):
        assert response.status_code == 404
        assert response.json() == TAG_NOT_FOUND_BODY
    else:
        assert response.status_code == 403
        assert response.json() == FORBIDDEN_BODY


def test_a_department_tag_is_not_one_this_route_acts_on(administrator_client):
    """The inventory lists Project, Process and Topic only, and so does the delete: a Department
    tag, which nothing reads (D-72), is an unknown id here."""
    department = Tag.objects.create(tag_name="people", dimension=DEPARTMENT_DIMENSION)

    response = delete(administrator_client, department.pk)

    assert response.status_code == 404
    assert response.json() == TAG_NOT_FOUND_BODY
    assert Tag.objects.filter(pk=department.pk).exists()


# --- What retiring a tag does to the rest of FR-10 and FR-15 ---------------------------------------


def test_a_retired_tag_leaves_the_options_and_stays_on_the_documents_that_carry_it(
    session_client, administrator_client
):
    """``Tag.active`` is not consulted by FR-15's reads (D-72's clarification of 7 October), which
    this change keeps: the retired tag still shows on its document, as a facet value and as a
    filter. It leaves ``tag_scheme``, so it is no longer offered and cannot be applied by id."""
    client = session_client.client
    document = make_document(session_client.user)
    other = make_document(session_client.user, title="Site rules")
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    link(tag, document.pk)
    assert delete(administrator_client, tag.pk).status_code == 200

    body = client.get(f"{DOCUMENTS_URL}/{document.id}").json()
    assert body["tags"]["project"] == ["bridge maintenance"]
    assert [item["name"] for item in body["tag_details"]] == ["bridge maintenance"]
    assert body["tag_options"][PROJECT_DIMENSION] == []
    browse = client.get(f"{DOCUMENTS_URL}/browse").json()
    assert browse["facets"]["project"] == [{"value": "bridge maintenance", "count": 1}]
    assert client.get(f"{DOCUMENTS_URL}/browse", {"project": "bridge maintenance"}).status_code == 200

    refused = client.post(f"{DOCUMENTS_URL}/{other.id}/tags", {"tag_id": str(tag.pk)}, format="json")
    assert refused.status_code == 400
    assert set(refused.json()) == {"tag_id"}


def test_typing_a_retired_topics_name_brings_it_back(session_client, administrator_client):
    """There is no reactivation route. A retired Topic comes back the way confirm_proposed_topic
    has always brought one back: a person names it, and it is linked and reactivated, answered as a
    new Topic would be, since a retired value is in no scheme."""
    document = make_document(session_client.user)
    other = make_document(session_client.user, title="Site rules")
    topic = Tag.objects.create(tag_name="night shifts", dimension=TOPIC_DIMENSION)
    link(topic, document.pk)
    assert delete(administrator_client, topic.pk).status_code == 200

    response = session_client.client.post(
        f"{DOCUMENTS_URL}/{other.id}/tags", {"dimension": TOPIC_DIMENSION, "tag_name": "Night Shifts"},
        format="json",
    )

    assert response.status_code == 201, response.content
    topic.refresh_from_db()
    assert topic.active is True
    assert Tag.objects.filter(tag_name="night shifts").count() == 1
