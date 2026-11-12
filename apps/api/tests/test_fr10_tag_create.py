"""``POST /api/tags``: an Administrator adds a value to the scheme (D-128, 12 November 2026; FR-10's
CRUD line gives Tags "Create", and its Responses name "409 Conflict on a duplicate tag name within a
dimension").

The route is behind ``manage_tags``, which accounts 0008 gives the Administrator alone, checked as a
permission class, so the order is: 401 without a session; 403 for the Employee, before the body is
read and before the throttle counts the request; then, for the Administrator, the "tagging" throttle
(the POST only), the body's 400 keyed on the field, the 409 and the 201.

- ``dimension`` is Project, Process or Topic. Anything else, Department included, is 400 keyed on
  ``dimension``. ``tag_name`` is trimmed and normalised, and a blank or over-long one is 400 keyed on
  ``tag_name``.
- A name already a Tag in the dimension after normalisation, active or retired, is 409
  ``{"detail", "tag_id"}`` and changes nothing. A retired tag is not reactivated, and ``grown`` is
  not touched. A concurrent create of the same name is the same 409. The same name in another
  dimension is not a conflict.
- The 201 is the inventory's entry, ``{tag_id, dimension, tag_name, active: true, item_count: 0}``.
  The value is created **not grown**: vocabulary, offered in the ``tag_options`` of every document and
  listed in every classification prompt, whatever the document's audience.

The routes run from both roles wherever the answer depends on the role, so the dual-role matrix
credits ``POST /api/tags`` to each of them (CLAUDE.md section 8 item 2).
"""

from types import SimpleNamespace

import pytest
from rest_framework.throttling import ScopedRateThrottle

from apps.api.views import TAG_ALREADY_EXISTS_MESSAGE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DEPARTMENT_DIMENSION,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    MANAGE_TAGS_PERMISSION,
    PROJECT_DIMENSION,
    REPOSITORY_TAG_DIMENSIONS,
    TAGGING_THROTTLE_RATE,
    TOPIC_DIMENSION,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents import taxonomy
from apps.documents.classification import tag_scheme
from apps.documents.models import Document, ExtractedContent, Tag

pytestmark = pytest.mark.django_db

TAGS_URL = "/api/tags"
DOCUMENTS_URL = "/api/documents"
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
FORBIDDEN_BODY = {"detail": f"Your role does not hold the '{MANAGE_TAGS_PERMISSION}' permission."}
ENTRY_KEYS = {"tag_id", "dimension", "tag_name", "active", "item_count"}
TAGGING_LIMIT = ScopedRateThrottle().parse_rate(TAGGING_THROTTLE_RATE)[0]


def add(client, dimension, tag_name):
    return client.post(TAGS_URL, {"dimension": dimension, "tag_name": tag_name}, format="json")


def make_document(user, *, title="Harbour works plan", roles=None):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )
    ExtractedContent.objects.create(document=document, extracted_text="Berths, cranes and a timetable.")
    return document


def options(client, document):
    response = client.get(f"{DOCUMENTS_URL}/{document.id}")
    assert response.status_code == 200, response.content
    return response.json()["tag_options"]


def type_topic(client, document):
    """A person types a Topic on a document: the other route that spends the "tagging" budget."""
    return client.post(
        f"{DOCUMENTS_URL}/{document.id}/tags",
        {"dimension": TOPIC_DIMENSION, "tag_name": "night shifts"}, format="json",
    )


def rows():
    return sorted(Tag.objects.values_list("dimension", "tag_name", "active", "grown"))


# --- Who may add a value ---------------------------------------------------------------------------


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_an_administrator_adds_a_value_as_vocabulary_and_an_employee_is_refused(session_client, dimension):
    response = add(session_client.client, dimension, "  Harbour   UPGRADE ")

    if session_client.role_name == ADMINISTRATOR_ROLE_NAME:
        assert response.status_code == 201, response.content
        tag = Tag.objects.get(tag_name="harbour upgrade")
        body = response.json()
        assert set(body) == ENTRY_KEYS
        assert body == {
            "tag_id": str(tag.pk), "dimension": dimension, "tag_name": "harbour upgrade",
            "active": True, "item_count": 0,
        }
        # Vocabulary: active and not grown, as a seeded value is.
        assert rows() == [(dimension, "harbour upgrade", True, False)]
    else:
        assert response.status_code == 403, response.content
        assert response.json() == FORBIDDEN_BODY
        assert rows() == []


EMPLOYEE_BODIES = {
    "a valid body": {"dimension": PROJECT_DIMENSION, "tag_name": "harbour upgrade"},
    "no body": {},
    "a department": {"dimension": DEPARTMENT_DIMENSION, "tag_name": "harbour upgrade"},
    "a blank name": {"dimension": PROJECT_DIMENSION, "tag_name": "   "},
    "an over-long name": {"dimension": PROJECT_DIMENSION, "tag_name": "x" * (NAME_MAX_LENGTH + 1)},
    "a retired tag's name": {"dimension": PROJECT_DIMENSION, "tag_name": "Bridge  Maintenance"},
}


@pytest.mark.parametrize("body", sorted(EMPLOYEE_BODIES))
def test_an_employee_is_refused_before_the_body_is_read(employee_client, body):
    """``manage_tags`` is a permission class, so the Employee's 403 comes before the 400 a body would
    earn and before the 409 a name would: the same 403, whatever was sent, and nothing changes."""
    Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION, active=False)

    response = employee_client.post(TAGS_URL, EMPLOYEE_BODIES[body], format="json")

    assert response.status_code == 403, response.content
    assert response.json() == FORBIDDEN_BODY
    assert rows() == [(PROJECT_DIMENSION, "bridge maintenance", False, False)]


def test_adding_a_value_needs_a_session(api_client):
    response = add(api_client, PROJECT_DIMENSION, "harbour upgrade")

    assert response.status_code == 401, response.content
    assert rows() == []


# --- The body: 400 keyed on the field ----------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"tag_name": "harbour upgrade"},
        {"dimension": DEPARTMENT_DIMENSION, "tag_name": "harbour upgrade"},
        {"dimension": "Colour", "tag_name": "harbour upgrade"},
        {"dimension": PROJECT_DIMENSION.lower(), "tag_name": "harbour upgrade"},
    ],
    ids=["missing", "department", "unknown", "lower-case"],
)
def test_a_dimension_other_than_project_process_or_topic_is_400_keyed_on_dimension(
    administrator_client, body
):
    response = administrator_client.post(TAGS_URL, body, format="json")

    assert response.status_code == 400, response.content
    assert set(response.json()) == {"dimension"}
    assert rows() == []


@pytest.mark.parametrize(
    "body",
    [
        {"dimension": PROJECT_DIMENSION},
        {"dimension": PROJECT_DIMENSION, "tag_name": None},
        {"dimension": PROJECT_DIMENSION, "tag_name": ""},
        {"dimension": PROJECT_DIMENSION, "tag_name": "   "},
        {"dimension": PROJECT_DIMENSION, "tag_name": "x" * (NAME_MAX_LENGTH + 1)},
    ],
    ids=["missing", "null", "empty", "blank", "over-long"],
)
def test_a_missing_blank_or_over_long_name_is_400_keyed_on_tag_name(administrator_client, body):
    response = administrator_client.post(TAGS_URL, body, format="json")

    assert response.status_code == 400, response.content
    assert set(response.json()) == {"tag_name"}
    assert rows() == []


def test_a_name_exactly_as_long_as_the_column_is_added(administrator_client):
    name = "x" * NAME_MAX_LENGTH

    response = add(administrator_client, TOPIC_DIMENSION, f"  {name.upper()}  ")

    assert response.status_code == 201, response.content
    assert response.json()["tag_name"] == name
    assert rows() == [(TOPIC_DIMENSION, name, True, False)]


# --- 409: the name is already a Tag in the dimension ---------------------------------------------------


@pytest.mark.parametrize(
    ("active", "grown"),
    [(True, False), (True, True), (False, False), (False, True)],
    ids=["active-vocabulary", "active-grown", "retired-vocabulary", "retired-grown"],
)
def test_a_name_already_in_the_dimension_is_409_with_its_id_and_nothing_changes(
    administrator_client, active, grown
):
    """Active or retired, after normalisation. A retired tag is not reactivated (D-105's note:
    "Declined: a route that only reactivates"), and ``grown`` is neither set nor unset."""
    existing = Tag.objects.create(
        tag_name="harbour upgrade", dimension=PROJECT_DIMENSION, active=active, grown=grown
    )

    response = add(administrator_client, PROJECT_DIMENSION, "  Harbour   UPGRADE ")

    assert response.status_code == 409, response.content
    assert response.json() == {"detail": TAG_ALREADY_EXISTS_MESSAGE, "tag_id": str(existing.pk)}
    assert list(Tag.objects.values_list("pk", "active", "grown")) == [(existing.pk, active, grown)]


@pytest.mark.parametrize(
    ("held_in", "added_to"),
    [(held, added) for held in REPOSITORY_TAG_DIMENSIONS for added in REPOSITORY_TAG_DIMENSIONS
     if held != added],
)
def test_the_same_name_in_another_dimension_is_not_a_conflict(administrator_client, held_in, added_to):
    other = Tag.objects.create(tag_name="harbour upgrade", dimension=held_in, active=False)

    response = add(administrator_client, added_to, "Harbour Upgrade")

    assert response.status_code == 201, response.content
    added = Tag.objects.get(dimension=added_to, tag_name="harbour upgrade")
    assert response.json()["tag_id"] == str(added.pk) != str(other.pk)
    assert rows() == sorted([(held_in, "harbour upgrade", False, False),
                             (added_to, "harbour upgrade", True, False)])


def test_a_concurrent_create_of_the_same_name_is_the_same_409(administrator_client, monkeypatch):
    """The race ``create_tag`` handles: its check runs before another request commits the same name,
    so the check finds nothing, the insert then loses on ``tags_unique_name_per_dimension``, and the
    row read back afterwards is the other request's. Simulated by committing the other request's row
    first and letting ``create_tag``'s first lookup, its check, find nothing."""
    winner = Tag.objects.create(tag_name="harbour upgrade", dimension=PROJECT_DIMENSION)
    lookups = []

    class CheckBeforeTheOtherCommit:
        def filter(self, *args, **kwargs):
            lookups.append(kwargs)
            if len(lookups) == 1:
                return Tag.objects.none()
            return Tag.objects.filter(*args, **kwargs)

        def create(self, **kwargs):
            return Tag.objects.create(**kwargs)

    monkeypatch.setattr(taxonomy, "Tag", SimpleNamespace(objects=CheckBeforeTheOtherCommit()))

    response = add(administrator_client, PROJECT_DIMENSION, "Harbour Upgrade")

    assert response.status_code == 409, response.content
    assert response.json() == {"detail": TAG_ALREADY_EXISTS_MESSAGE, "tag_id": str(winner.pk)}
    # The check, then, after the insert lost, the read-back: the race path ran.
    assert lookups == [{"dimension": PROJECT_DIMENSION, "tag_name": "harbour upgrade"}] * 2
    assert list(Tag.objects.values_list("pk", flat=True)) == [winner.pk]


# --- The throttle: the "tagging" scope, the POST only ----------------------------------------------------


def test_adding_values_is_throttled_in_the_tagging_scope_and_writes_nothing_past_it(
    administrator, administrator_client
):
    for number in range(1, TAGGING_LIMIT + 1):
        assert add(administrator_client, TOPIC_DIMENSION, f"topic {number}").status_code == 201, number

    past = add(administrator_client, TOPIC_DIMENSION, "one too many")

    assert past.status_code == 429, past.content
    assert set(past.json()) == {"detail"}
    assert past.json()["detail"].startswith("Request was throttled.")
    assert Tag.objects.count() == TAGGING_LIMIT
    assert not Tag.objects.filter(tag_name="one too many").exists()
    # The budget is the one a person typing a tag on a document spends (D-79's note on tagging),
    # not a second budget at the same rate.
    assert type_topic(administrator_client, make_document(administrator)).status_code == 429


def test_the_inventory_is_never_throttled(administrator_client):
    for number in range(TAGGING_LIMIT):
        assert add(administrator_client, TOPIC_DIMENSION, f"topic {number}").status_code == 201, number
    assert add(administrator_client, TOPIC_DIMENSION, "one too many").status_code == 429

    for number in range(TAGGING_LIMIT + 1):
        response = administrator_client.get(TAGS_URL)
        assert response.status_code == 200, (number, response.content)
    assert len(response.json()) == TAGGING_LIMIT


def test_an_employees_refusals_come_before_the_throttle_and_spend_none_of_it(employee, employee_client):
    """DRF checks the permission classes before the throttles, so past the rate the Employee is still
    answered 403, and the requests refused spend none of the Employee's "tagging" budget."""
    for number in range(TAGGING_LIMIT + 1):
        response = add(employee_client, TOPIC_DIMENSION, f"topic {number}")
        assert response.status_code == 403, (number, response.content)
        assert response.json() == FORBIDDEN_BODY

    typed = type_topic(employee_client, make_document(employee, roles=[EMPLOYEE_ROLE_NAME]))

    assert typed.status_code == 201, typed.content


# --- What the value is: vocabulary, for every audience ---------------------------------------------------


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_an_added_value_is_offered_and_listed_for_every_audience(
    employee, administrator, employee_client, administrator_client, stub_ai_service, dimension
):
    """Not grown, so in every document's scheme (``tag_scheme``), offered in its ``tag_options`` and
    listed in its classification prompt: an Employee-visible document and an Administrator-only one
    alike, although no source carries the value."""
    staff = make_document(employee, title="Staff handbook", roles=[EMPLOYEE_ROLE_NAME])
    board = make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])

    response = add(administrator_client, dimension, "Harbour Upgrade")

    assert response.status_code == 201, response.content
    offered = {"tag_id": response.json()["tag_id"], "tag_name": "harbour upgrade"}
    for document in (staff, board):
        assert "harbour upgrade" in tag_scheme(document).tags[dimension], document.title
    assert offered in options(employee_client, staff)[dimension]
    assert offered in options(administrator_client, staff)[dimension]
    assert offered in options(administrator_client, board)[dimension]
    # An Employee may apply it, by id, to a document they read.
    applied = employee_client.post(
        f"{DOCUMENTS_URL}/{staff.id}/tags", {"tag_id": offered["tag_id"]}, format="json"
    )
    assert applied.status_code == 201, applied.content
    # And the prompt lists it for both audiences.
    for client, document in ((employee_client, staff), (administrator_client, board)):
        classified = client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")
        assert classified.status_code == 200, classified.content
        title, _, shown = stub_ai_service.classify_calls[-1]
        assert title == document.title
        assert "harbour upgrade" in shown.tags[dimension], document.title
