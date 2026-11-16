"""A person applies a tag: ``POST /api/documents/{id}/tags``, and the detail's ``tag_options``
(FR-10, D-119 finding 4; D-105's dated note of 10 November 2026, night).

FR-10's provenance clause: tags "applied automatically are visually distinguished from those
applied by a person and either may be accepted or removed in a single action"; UC-09 A3: a person
"adds one it did not"; Responses: "409 Conflict on a duplicate tag name within a dimension". The
body is exactly one of ``{"tag_id"}``, an existing tag offered for this document, or
``{"dimension": "Topic", "tag_name"}``, a new Topic. This name form is Topic-only, as FR-10's
controlled taxonomy growth has it: an Administrator adds a value in any of the three dimensions
(``POST /api/tags``, D-128), and the classifier creates none (D-129).

**Nothing in an answer may tell "does not exist" from "you may not see it"** (invariant 1):

- a ``tag_id`` that is unknown, inactive or outside the document's scheme gets one 400 and one body;
- a Topic name already in the document's scheme is the 409, because the caller is already offered
  it; a Topic of that name that exists but is NOT in the scheme (carried only by material some
  audience role cannot read, or inactive) is linked as it stands and answered byte for byte as a
  brand-new Topic would be, so a 409 never names a restricted value.

The guards (401, the scoped 404 first, then ``contribute_content``'s 403) are tested with the other
FR-10 routes in ``test_document_classification.py``'s ``ROUTES``, and the 401 by ``test_rbac.py``'s
walk. Every test here runs from both roles through ``session_client`` unless it names one.
"""

import uuid
from decimal import Decimal

import pytest
from django.db import transaction

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    DEPARTMENT_DIMENSION,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.documents.classification import InvalidClassification, apply_tag, tag_scheme
from apps.documents.models import ContentTag, Document, ExtractedContent, Tag

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
TAG_DETAIL_KEYS = {
    "content_tag_id", "dimension", "name", "applied_by", "confirmed", "provisional", "confidence",
}
OPTION_DIMENSIONS = {PROJECT_DIMENSION, PROCESS_DIMENSION, TOPIC_DIMENSION}


def make_document(user, *, title="Bridge works", roles=None):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )
    ExtractedContent.objects.create(document=document, extracted_text="Bridge inspections twice a year.")
    return document


def apply(client, doc_id, **body):
    return client.post(f"{DOCUMENTS_URL}/{doc_id}/tags", body, format="json")


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def link(tag, document, **fields):
    fields.setdefault("applied_by", USER_APPLIED)
    fields.setdefault("confirmed", True)
    return ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk, **fields
    )


def detail(client, doc_id):
    response = client.get(f"{DOCUMENTS_URL}/{doc_id}")
    assert response.status_code == 200, response.content
    return response.json()


def fields_of(row):
    row.refresh_from_db()
    return (row.applied_by, row.confirmed, row.provisional, row.removed, row.confidence)


class _RolledBack(Exception):
    pass


def answered_then_undone(send):
    """``send()``'s response, with everything it wrote rolled back, so one test can compare the
    reply to a brand-new Topic with the reply to an existing one of the same name."""
    response = None
    try:
        with transaction.atomic():
            response = send()
            raise _RolledBack
    except _RolledBack:
        return response


def without_link_id(response) -> bytes:
    """The reply's bytes with its one random identifier, the new link's, replaced."""
    [entry] = response.json()["tag_details"]
    return response.content.replace(entry["content_tag_id"].encode(), b"<content_tag_id>")


@pytest.fixture
def restricted(administrator):
    """An Administrator-only document: what it carries is withheld from a document both roles
    can read, because the Employee in that audience cannot read it (tag_scheme, D-105)."""
    return make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])


# --- An existing tag, by id ---------------------------------------------------------------------


def test_applying_an_offered_tag_links_it_as_the_persons(session_client):
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)

    response = apply(session_client.client, document.id, tag_id=str(tag.pk))

    assert response.status_code == 201, response.content
    body = response.json()
    assert set(body) == {"tag_details"}
    [entry] = body["tag_details"]
    assert set(entry) == TAG_DETAIL_KEYS
    assert (entry["dimension"], entry["name"]) == (PROJECT_DIMENSION, "bridge maintenance")
    assert (entry["applied_by"], entry["confirmed"], entry["provisional"], entry["confidence"]) == (
        USER_APPLIED, True, False, None,
    )
    created = links_of(document).get()
    assert entry["content_tag_id"] == str(created.pk)
    assert fields_of(created) == (USER_APPLIED, True, False, False, None)
    # A person's tag is a tag of the document in every read.
    assert detail(session_client.client, document.id)["tags"]["project"] == ["bridge maintenance"]


def test_a_tag_that_cannot_be_offered_gets_one_400_whatever_the_reason(session_client, restricted):
    document = make_document(session_client.user)
    inactive = Tag.objects.create(tag_name="retired project", dimension=PROJECT_DIMENSION, active=False)
    withheld = Tag.objects.create(tag_name="succession planning", dimension=PROJECT_DIMENSION, grown=True)
    link(withheld, restricted)  # carried only by material the Employee in the audience cannot read
    department = Tag.objects.create(tag_name="people", dimension=DEPARTMENT_DIMENSION)
    cases = {
        "unknown": uuid.uuid4(), "inactive": inactive.pk, "outside the scheme": withheld.pk,
        "a Department tag": department.pk,
    }

    responses = {name: apply(session_client.client, document.id, tag_id=str(tag_id))
                 for name, tag_id in cases.items()}

    first = responses["unknown"]
    assert first.status_code == 400, first.content
    assert set(first.json()) == {"tag_id"}
    for name, response in responses.items():
        assert (response.status_code, response.content) == (400, first.content), name
    assert not links_of(document).exists()
    assert links_of(restricted).count() == 1


def test_applying_a_held_ai_tag_confirms_it(session_client):
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    held = link(tag, document, applied_by=AI_APPLIED, confirmed=False, provisional=True,
                confidence=Decimal("0.610"))

    response = apply(session_client.client, document.id, tag_id=str(tag.pk))

    assert response.status_code == 200, response.content
    assert fields_of(held) == (AI_APPLIED, True, False, False, Decimal("0.610"))
    [entry] = response.json()["tag_details"]
    assert (entry["content_tag_id"], entry["confirmed"], entry["provisional"]) == (str(held.pk), True, False)


def test_applying_a_removed_ai_tag_restores_it(session_client):
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    removed = link(tag, document, applied_by=AI_APPLIED, confirmed=False, provisional=True,
                   removed=True, confidence=Decimal("0.610"))
    assert detail(session_client.client, document.id)["tag_details"] == []

    response = apply(session_client.client, document.id, tag_id=str(tag.pk))

    assert response.status_code == 200, response.content
    # Restored and confirmed; its provenance and the machine's confidence are kept.
    assert fields_of(removed) == (AI_APPLIED, True, False, False, Decimal("0.610"))
    assert [entry["content_tag_id"] for entry in response.json()["tag_details"]] == [str(removed.pk)]
    assert links_of(document).count() == 1


@pytest.mark.parametrize("state", ["ai applied", "a person's"])
def test_applying_a_tag_already_applied_changes_nothing(session_client, state):
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    if state == "ai applied":
        existing = link(tag, document, applied_by=AI_APPLIED, confirmed=False, provisional=False,
                        confidence=Decimal("0.990"))
    else:
        existing = link(tag, document)
    before = fields_of(existing)

    response = apply(session_client.client, document.id, tag_id=str(tag.pk))

    assert response.status_code == 200, response.content
    assert fields_of(existing) == before
    assert links_of(document).count() == 1


# --- A new Topic, by name -----------------------------------------------------------------------


def test_a_new_topic_is_created_and_linked_as_the_persons(session_client):
    document = make_document(session_client.user)

    response = apply(session_client.client, document.id, dimension=TOPIC_DIMENSION,
                     tag_name="  Night   Shifts ")

    assert response.status_code == 201, response.content
    tag = Tag.objects.get(dimension=TOPIC_DIMENSION, tag_name="night shifts")
    assert tag.active is True
    created = links_of(document).get()
    assert created.tag == tag
    assert fields_of(created) == (USER_APPLIED, True, False, False, None)
    [entry] = response.json()["tag_details"]
    assert (entry["dimension"], entry["name"], entry["applied_by"]) == (
        TOPIC_DIMENSION, "night shifts", USER_APPLIED,
    )
    # It joins the document's own options, which its audience can now read it on.
    options = detail(session_client.client, document.id)["tag_options"][TOPIC_DIMENSION]
    assert {"tag_id": str(tag.pk), "tag_name": "night shifts"} in options


def test_a_topic_name_already_offered_is_409(session_client):
    document = make_document(session_client.user)
    offered = Tag.objects.create(tag_name="safety", dimension=TOPIC_DIMENSION)  # seeded, unlinked: offered

    response = apply(session_client.client, document.id, dimension=TOPIC_DIMENSION, tag_name=" SAFETY ")

    assert response.status_code == 409, response.content
    body = response.json()
    assert set(body) == {"detail", "tag_id"}
    assert body["tag_id"] == str(offered.pk)
    assert not links_of(document).exists()
    assert Tag.objects.filter(tag_name="safety").count() == 1


@pytest.mark.parametrize("existing", ["restricted", "inactive"])
def test_an_existing_topic_outside_the_scheme_answers_exactly_as_a_new_one(
    session_client, restricted, existing
):
    """The rule that keeps the 409 from disclosing anything: a Topic not in this document's scheme
    is linked and answered as if it were new, byte for byte apart from the new link's id."""
    client = session_client.client
    document = make_document(session_client.user)
    name = "merger talks"
    assert not Tag.objects.filter(tag_name=name).exists()
    as_new = answered_then_undone(
        lambda: apply(client, document.id, dimension=TOPIC_DIMENSION, tag_name="Merger Talks")
    )
    assert as_new.status_code == 201, as_new.content
    assert not Tag.objects.filter(tag_name=name).exists()  # the first answer left nothing behind

    if existing == "restricted":
        # Grown, as documents 0011 marks a value only restricted material carries.
        topic = Tag.objects.create(tag_name=name, dimension=TOPIC_DIMENSION, grown=True)
        restricted_link = link(topic, restricted)
    else:
        topic = Tag.objects.create(tag_name=name, dimension=TOPIC_DIMENSION, active=False)
    assert name not in tag_scheme(document).tags[TOPIC_DIMENSION]

    response = apply(client, document.id, dimension=TOPIC_DIMENSION, tag_name="Merger Talks")

    assert response.status_code == as_new.status_code == 201, response.content
    assert without_link_id(response) == without_link_id(as_new)
    # The existing Tag is reused, never duplicated, and reactivated if it had been retired.
    assert Tag.objects.filter(tag_name=name, dimension=TOPIC_DIMENSION).count() == 1
    topic.refresh_from_db()
    assert topic.active is True
    assert links_of(document).get().tag == topic
    if existing == "restricted":
        assert fields_of(restricted_link) == (USER_APPLIED, True, False, False, None)


def test_a_new_name_in_another_dimension_is_400(session_client):
    document = make_document(session_client.user)

    response = apply(session_client.client, document.id, dimension=PROJECT_DIMENSION,
                     tag_name="harbour upgrade")

    assert response.status_code == 400, response.content
    assert set(response.json()) == {"dimension"}
    assert not Tag.objects.filter(tag_name="harbour upgrade").exists()
    assert not links_of(document).exists()


@pytest.mark.parametrize(
    "body, field",
    [
        ({}, "non_field_errors"),
        ({"tag_id": "<tag>", "dimension": TOPIC_DIMENSION, "tag_name": "night shifts"}, "non_field_errors"),
        ({"tag_name": "night shifts"}, "dimension"),
        ({"dimension": TOPIC_DIMENSION}, "tag_name"),
        ({"dimension": TOPIC_DIMENSION, "tag_name": "   "}, "tag_name"),
        ({"tag_id": "not-a-uuid"}, "tag_id"),
    ],
    ids=["neither form", "both forms", "no dimension", "no name", "a blank name", "a malformed id"],
)
def test_a_body_that_is_not_exactly_one_form_is_400(session_client, body, field):
    """Each 400 names the field the contract's 400 list gives it (the focused re-audit of ``88a488d``
    asked that the missing dimension's be checked as ``dimension``, not by its status alone)."""
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    body = {key: str(tag.pk) if value == "<tag>" else value for key, value in body.items()}

    response = apply(session_client.client, document.id, **body)

    assert response.status_code == 400, response.content
    assert set(response.json()) == {field}
    assert not links_of(document).exists()
    assert not Tag.objects.filter(tag_name="night shifts").exists()


# --- tag_options on the detail --------------------------------------------------------------------


def test_the_detail_offers_the_documents_scheme_with_ids(session_client, restricted):
    document = make_document(session_client.user)
    bridge = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    harbour = Tag.objects.create(tag_name="harbour upgrade", dimension=PROJECT_DIMENSION)
    purchasing = Tag.objects.create(tag_name="purchasing", dimension=PROCESS_DIMENSION)
    link(purchasing, document)
    withheld = Tag.objects.create(tag_name="succession planning", dimension=TOPIC_DIMENSION, grown=True)
    link(withheld, restricted)
    Tag.objects.create(tag_name="retired topic", dimension=TOPIC_DIMENSION, active=False)
    Tag.objects.create(tag_name="people", dimension=DEPARTMENT_DIMENSION)

    options = detail(session_client.client, document.id)["tag_options"]

    assert options == {
        PROJECT_DIMENSION: [
            {"tag_id": str(bridge.pk), "tag_name": "bridge maintenance"},
            {"tag_id": str(harbour.pk), "tag_name": "harbour upgrade"},
        ],
        PROCESS_DIMENSION: [{"tag_id": str(purchasing.pk), "tag_name": "purchasing"}],
        TOPIC_DIMENSION: [],
    }
    # Exactly tag_scheme's values: the options are the scheme the classifier is shown, no more.
    scheme = tag_scheme(document)
    assert {dimension: [entry["tag_name"] for entry in entries] for dimension, entries in options.items()} == {
        dimension: list(scheme.tags[dimension]) for dimension in OPTION_DIMENSIONS
    }


def test_the_administrator_is_offered_a_restricted_value_on_the_restricted_document(
    administrator_client, restricted
):
    """The mirror of the test above: the value withheld from a document both roles read is offered
    on the document only the Administrator reads, so the options are not simply empty."""
    withheld = Tag.objects.create(tag_name="succession planning", dimension=TOPIC_DIMENSION, grown=True)
    link(withheld, restricted)

    options = detail(administrator_client, restricted.id)["tag_options"]

    assert options[TOPIC_DIMENSION] == [{"tag_id": str(withheld.pk), "tag_name": "succession planning"}]


def test_apply_tag_refuses_a_name_that_normalises_to_nothing(document):
    """The function's own guard, beneath the route's serializer, which refuses a blank name first."""
    with pytest.raises(InvalidClassification):
        apply_tag(document, tag_name="   ")
    assert not Tag.objects.exists()
    assert not links_of(document).exists()


# --- Apply, remove, apply again: the same answers either way (D-105's dated note, the lead's review)


def three_steps(client, doc_id, name):
    """Apply a new Topic name, remove the link that made, read the options, apply the name again.
    Returns the three status codes and the document's ``tag_options`` after the removal."""
    first = apply(client, doc_id, dimension=TOPIC_DIMENSION, tag_name=name)
    entry = next(item for item in first.json()["tag_details"] if item["name"] == name)
    removed = client.delete(f"{DOCUMENTS_URL}/{doc_id}/tags/{entry['content_tag_id']}")
    options = detail(client, doc_id)["tag_options"]
    second = apply(client, doc_id, dimension=TOPIC_DIMENSION, tag_name=name)
    return (first.status_code, removed.status_code, second.status_code), options


def option_names(options):
    """``tag_options`` by name. Each variant's Topic is its own row, with its own random id (uuid4),
    which says nothing about whether the row existed before."""
    return {dimension: [entry["tag_name"] for entry in entries] for dimension, entries in options.items()}


def test_apply_remove_apply_answers_alike_whether_or_not_a_restricted_topic_exists(
    employee, employee_client, restricted
):
    """The oracle the lead's review found in the 409 rule as first built. An Employee applies a
    Topic name to a document both roles read, removes it and applies it again. While an unlinked
    Topic was vocabulary, the second apply was a 409 for a name nothing else carried and a 201 for
    one carried only by Administrator-only material, and the options in between differed the same
    way. Since the requirements re-audit of ``5377e3a`` the removed link is kept and still counts,
    so the document itself carries the name: both runs answer 201, 204, 409 and list the name after
    the removal. The answers are the same either way, so the oracle stays closed."""
    document = make_document(employee)
    name = "merger talks"
    as_new = answered_then_undone(lambda: three_steps(employee_client, document.id, name))
    assert not Tag.objects.filter(tag_name=name).exists()

    topic = Tag.objects.create(tag_name=name, dimension=TOPIC_DIMENSION, grown=True)
    link(topic, restricted)  # the restricted Topic: on the Administrator-only document alone, grown
    as_restricted = three_steps(employee_client, document.id, name)

    assert as_new[0] == as_restricted[0] == (201, 204, 409)
    assert option_names(as_new[1]) == option_names(as_restricted[1])
    assert name in option_names(as_new[1])[TOPIC_DIMENSION]


def test_applying_removing_and_applying_a_new_topic_again_is_201_204_409_and_its_id_restores_it(
    session_client,
):
    """The mirror from both roles, each on a document of their own role: the Employee on an
    Employee-only document, the Administrator on an Administrator-only one. Since the requirements
    re-audit of ``5377e3a`` a person's removed link is kept and counts, so the name is still offered
    after the removal, applying it again by name is the 409 that names it, and applying its id
    restores the same link: 200 (``_apply_link``)."""
    document = make_document(session_client.user, roles=[session_client.role_name])

    codes, options = three_steps(session_client.client, document.id, "night shifts")

    assert codes == (201, 204, 409)
    topic = Tag.objects.get(tag_name="night shifts", dimension=TOPIC_DIMENSION)  # one row, not two
    assert options[TOPIC_DIMENSION] == [{"tag_id": str(topic.pk), "tag_name": "night shifts"}]
    [kept] = links_of(document).filter(tag=topic)
    assert (kept.removed, kept.applied_by) == (True, USER_APPLIED)

    restored = apply(session_client.client, document.id, tag_id=str(topic.pk))

    assert restored.status_code == 200, restored.content
    [after] = links_of(document).filter(tag=topic)
    assert (after.pk, after.removed, after.confirmed, after.applied_by) == (
        kept.pk, False, True, USER_APPLIED,
    )


def test_apply_remove_apply_answers_alike_for_a_new_a_restricted_and_a_retired_seeded_topic(
    employee, employee_client, restricted
):
    """Three runs of the Employee's sequence, each undone before the next: a name nothing has, a
    Topic carried only by Administrator-only material, and a retired, seeded, unlinked Topic. Since
    the requirements re-audit of ``5377e3a`` a person's removed link is kept and counts, so each run
    answers 201, 204, 409 and lists the name after the removal: the same answers in every variant,
    so the oracle stays closed. The options are compared by name, each variant's Topic having its
    own random id. Whether the retired Topic is grown as it comes back no longer shows here, since
    the document carries the name either way; ``test_fr10_tag_vocabulary.py`` holds it at the
    route."""
    document = make_document(employee)
    name = "merger talks"

    def run_with(setup):
        def send():
            setup()
            return three_steps(employee_client, document.id, name)
        return answered_then_undone(send)

    def restricted_topic():
        link(Tag.objects.create(tag_name=name, dimension=TOPIC_DIMENSION, grown=True), restricted)

    def retired_seeded_topic():
        Tag.objects.create(tag_name=name, dimension=TOPIC_DIMENSION, active=False)

    results = {
        "new": run_with(lambda: None),
        "restricted": run_with(restricted_topic),
        "retired, seeded, unlinked": run_with(retired_seeded_topic),
    }

    assert not Tag.objects.filter(tag_name=name).exists()  # every run was undone
    for label, (codes, options) in results.items():
        assert codes == (201, 204, 409), label
        assert option_names(options) == option_names(results["new"][1]), label
        assert name in option_names(options)[TOPIC_DIMENSION], label
