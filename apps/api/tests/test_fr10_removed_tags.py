"""FR-10's removal through the routes, and FR-15's reads after it (D-119 findings 3 and 10).

``DELETE /api/documents/{id}/tags/{content_tag_id}`` keeps its URL and its 204, and since D-105's
dated note of 10 November 2026 (night) an AI link it removes is kept, marked removed, beside the
machine's confidence. Since the requirements re-audit of ``5377e3a`` a person's link is kept the same
way: deleted, it was linked again as the machine's by the next classify or reprocess that suggested
it. A removed link is in no read: not the detail's ``tags`` or ``tag_details``, not the classify
reply's ``tag_details``, not a browse facet value and not a filter hit. A later classify or reprocess
neither links the tag again nor alters it, nor proposes it again, in any dimension (until D-128 a
removed Topic alone was skipped). A removed link is the same 404 as an
unknown one when it is confirmed or removed again.

The classification object's ``department_applied_by`` (finding 10) is read here through the classify,
confirm and detail replies.

Every test runs from an Employee and an Administrator session through ``session_client``; the stub
answers ``classify_document`` (apps/ai/testing.py), and no provider is reached.
"""

from decimal import Decimal

import pytest

from apps.ai.testing import STUB_CONFIDENCE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    ASSIGNMENT_APPLIED,
    ASSIGNMENT_CONFIRMED,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_EMBED_ATTEMPTS,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.documents.models import ContentTag, Document, DocumentAnalysis, ExtractedContent, Tag
from apps.documents.tests.classification_builders import ABOVE_THRESHOLD, BELOW_THRESHOLD, classification
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
NOT_FOUND_BODY = {"detail": "No Document matches the given query."}
TEXT = "Bridge inspections are scheduled twice a year. Repairs follow the inspection report."
BRIDGE = "bridge maintenance"


def make_document(user, *, title="Bridge works", department="", text=TEXT):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        department=department, visible_to_roles=BOTH_ROLES,
    )
    if text is not None:
        ExtractedContent.objects.create(document=document, extracted_text=text)
    return document


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def classify(client, doc_id):
    return client.post(f"{DOCUMENTS_URL}/{doc_id}/classify", {}, format="json")


def remove(client, doc_id, link_id):
    return client.delete(f"{DOCUMENTS_URL}/{doc_id}/tags/{link_id}")


def detail(client, doc_id):
    response = client.get(f"{DOCUMENTS_URL}/{doc_id}")
    assert response.status_code == 200, response.content
    return response.json()


def browse(client, **filters):
    return client.get(f"{DOCUMENTS_URL}/browse", filters)


@pytest.fixture
def removed_link(session_client):
    """A document whose AI link in Project was APPLIED (at STUB_CONFIDENCE, above the threshold),
    seen in every read, then removed through the route."""
    client = session_client.client
    document = make_document(session_client.user)
    Tag.objects.create(tag_name=BRIDGE, dimension=PROJECT_DIMENSION)  # unlinked: in every scheme
    assert classify(client, document.id).status_code == 200
    link = links_of(document).get()
    assert (link.applied_by, link.provisional) == (AI_APPLIED, False)
    # The premise: before the removal, every read shows the tag.
    before = detail(client, document.id)
    assert before["tags"]["project"] == [BRIDGE]
    assert [entry["content_tag_id"] for entry in before["tag_details"]] == [str(link.id)]
    assert browse(client).json()["facets"]["project"] == [{"value": BRIDGE, "count": 1}]
    assert browse(client, project=BRIDGE).status_code == 200

    response = remove(client, document.id, link.id)
    assert response.status_code == 204, response.content
    assert not response.content
    return document, link


# --- The removal itself -------------------------------------------------------------------------


def test_removing_an_ai_tag_keeps_it_removed_beside_the_machines_assignment(session_client, removed_link):
    document, link = removed_link
    kept = links_of(document).get()
    assert kept.pk == link.pk
    assert (kept.removed, kept.applied_by, kept.provisional) == (True, AI_APPLIED, False)
    assert kept.confidence == Decimal(str(STUB_CONFIDENCE))
    assert Tag.objects.filter(tag_name=BRIDGE).exists()


def test_removing_a_persons_tag_keeps_it_marked_removed(session_client):
    """As an AI link is kept, since the requirements re-audit of ``5377e3a``: FR-10's correction
    clause, "not overwritten by later reprocessing" (D-105's dated note)."""
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="harbour upgrade", dimension=PROJECT_DIMENSION)
    link = ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=USER_APPLIED, confirmed=True,
    )

    response = remove(session_client.client, document.id, link.id)

    assert response.status_code == 204
    kept = links_of(document).get()
    assert (kept.pk, kept.removed, kept.applied_by, kept.confirmed, kept.confidence) == (
        link.pk, True, USER_APPLIED, True, None,
    )
    assert detail(session_client.client, document.id)["tag_details"] == []
    assert Tag.objects.filter(pk=tag.pk).exists()


def test_a_removed_link_is_the_same_404_when_confirmed_or_removed_again(session_client, removed_link):
    document, link = removed_link
    client = session_client.client
    for response in (
        client.post(f"{DOCUMENTS_URL}/{document.id}/tags/{link.id}/confirm", {}, format="json"),
        remove(client, document.id, link.id),
    ):
        assert response.status_code == 404, response.content
        assert response.json() == NOT_FOUND_BODY
    kept = links_of(document).get()
    assert (kept.removed, kept.confirmed) == (True, False)


def test_a_persons_removed_link_is_the_same_404_when_confirmed_or_removed_again(session_client):
    """The person's-link twin of the test above (the focused re-audit of ``88a488d``): a person's
    removal is kept since the requirements re-audit of ``5377e3a``, and its id is "not here" too."""
    client = session_client.client
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="harbour upgrade", dimension=PROJECT_DIMENSION)
    link = ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk,
        applied_by=USER_APPLIED, confirmed=True,
    )
    assert remove(client, document.id, link.id).status_code == 204

    for response in (
        client.post(f"{DOCUMENTS_URL}/{document.id}/tags/{link.id}/confirm", {}, format="json"),
        remove(client, document.id, link.id),
    ):
        assert response.status_code == 404, response.content
        assert response.json() == NOT_FOUND_BODY
    kept = links_of(document).get()
    assert (kept.pk, kept.removed, kept.applied_by, kept.confirmed) == (link.pk, True, USER_APPLIED, True)


# --- FR-15's reads, one read per test -----------------------------------------------------------


def test_a_removed_link_is_not_in_the_details_tags(session_client, removed_link):
    document, _ = removed_link
    assert detail(session_client.client, document.id)["tags"]["project"] == []


def test_a_removed_link_is_not_in_the_details_tag_details(session_client, removed_link):
    document, _ = removed_link
    assert detail(session_client.client, document.id)["tag_details"] == []


def test_a_removed_link_is_not_a_facet_value(session_client, removed_link):
    assert browse(session_client.client).json()["facets"]["project"] == []


def test_a_removed_link_is_not_a_filter_hit(session_client, removed_link):
    response = browse(session_client.client, project=BRIDGE)
    assert response.status_code == 204  # a filter set and nothing in scope matches (D-72)
    assert not response.content


# --- Reprocessing respects the removal ----------------------------------------------------------


def test_a_reclassify_leaves_a_removed_tag_removed_and_its_reply_omits_it(
    session_client, removed_link, stub_ai_service
):
    document, link = removed_link
    # The same tag suggested again, at a confidence that would make a live AI link provisional.
    stub_ai_service.classification = classification(
        tags=[(PROJECT_DIMENSION, BRIDGE, BELOW_THRESHOLD)]
    )

    response = classify(session_client.client, document.id)

    assert response.status_code == 200, response.content
    assert len(stub_ai_service.classify_calls) == 2  # the fixture's run and this one
    assert response.json()["tag_details"] == []
    kept = links_of(document).get()
    assert (kept.pk, kept.removed, kept.provisional) == (link.pk, True, False)
    assert kept.confidence == Decimal(str(STUB_CONFIDENCE))


def test_a_reprocess_leaves_a_removed_tag_removed(session_client, upload, monkeypatch):
    """The reprocess route reruns ingestion, and with it classification (D-32, D-105)."""
    client = session_client.client
    Tag.objects.create(tag_name=BRIDGE, dimension=PROJECT_DIMENSION)
    # The first attempt classifies (the hook runs before embedding), then fails to index. The
    # scripted service is the suite's stub underneath, so its classification is the stub's
    # default: the scheme's one Project tag, at STUB_CONFIDENCE, applied.
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
    failed = client.post(DOCUMENTS_URL, {"file": upload("sample.txt"), "title": "Sample"},
                         format="multipart")
    assert failed.status_code == 422, failed.content
    document = Document.objects.get(pk=failed.json()["doc_id"])
    link = links_of(document).get()
    assert (link.applied_by, link.provisional) == (AI_APPLIED, False)
    assert remove(client, document.id, link.id).status_code == 204

    healthy = ScriptedEmbedService()
    # The same tag suggested again, at a confidence that would make a live AI link provisional.
    healthy.classification = classification(tags=[(PROJECT_DIMENSION, BRIDGE, BELOW_THRESHOLD)])
    install(monkeypatch, healthy)
    reprocessed = client.post(f"{DOCUMENTS_URL}/{document.id}/reprocess", {}, format="json")

    assert reprocessed.status_code == 201, reprocessed.content
    assert len(healthy.classify_calls) == 1  # the reprocess did classify again
    kept = links_of(document).get()
    assert (kept.pk, kept.removed, kept.provisional) == (link.pk, True, False)
    assert kept.confidence == Decimal(str(STUB_CONFIDENCE))
    assert detail(client, document.id)["tag_details"] == []


PERSON_VALUES = ["a seeded Process value", "a Topic a person typed"]


def apply_then_remove(client, document, kind):
    """A person applies a tag through the route, then removes it through the route; its Tag."""
    if kind == "a seeded Process value":
        seeded = Tag.objects.create(tag_name="purchasing", dimension=PROCESS_DIMENSION)  # vocabulary
        body = {"tag_id": str(seeded.pk)}
    else:
        body = {"dimension": TOPIC_DIMENSION, "tag_name": "Night shifts"}
    applied = client.post(f"{DOCUMENTS_URL}/{document.id}/tags", body, format="json")
    assert applied.status_code == 201, applied.content
    [entry] = applied.json()["tag_details"]
    assert entry["applied_by"] == USER_APPLIED
    assert remove(client, document.id, entry["content_tag_id"]).status_code == 204
    return ContentTag.objects.get(pk=entry["content_tag_id"]).tag


@pytest.mark.parametrize("kind", PERSON_VALUES)
@pytest.mark.parametrize("run", ["classify", "reprocess"])
def test_a_persons_removed_tag_is_neither_linked_nor_proposed_again(
    session_client, upload, monkeypatch, stub_ai_service, run, kind
):
    """The requirements re-audit of ``5377e3a`` (its finding 3): a person's link was deleted on
    removal, so the next run that suggested the value linked it again, ``applied_by="ai"``, through
    ``_link_tag``'s create branch, and a Topic the person had typed was proposed again. FR-10's
    correction clause: "not overwritten by later reprocessing" (UC-09 A3 step 3)."""
    client = session_client.client
    if run == "classify":
        document = make_document(session_client.user)
    else:
        # The first attempt fails to index, so the document can be reprocessed (D-32). Nothing is
        # in the scheme yet, so its classification suggests no tag.
        install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
        failed = client.post(DOCUMENTS_URL, {"file": upload("sample.txt"), "title": "Sample"},
                             format="multipart")
        assert failed.status_code == 422, failed.content
        document = Document.objects.get(pk=failed.json()["doc_id"])
    tag = apply_then_remove(client, document, kind)
    suggestion = classification(tags=[(tag.dimension, tag.tag_name, ABOVE_THRESHOLD)])

    if run == "classify":
        stub_ai_service.classification = suggestion
        response = classify(client, document.id)
        assert response.status_code == 200, response.content
    else:
        healthy = ScriptedEmbedService()
        healthy.classification = suggestion
        install(monkeypatch, healthy)
        response = client.post(f"{DOCUMENTS_URL}/{document.id}/reprocess", {}, format="json")
        assert response.status_code == 201, response.content
        assert len(healthy.classify_calls) == 1  # the reprocess did classify again

    kept = list(links_of(document).filter(tag=tag))
    assert [(link.removed, link.applied_by) for link in kept] == [(True, USER_APPLIED)]
    assert detail(client, document.id)["tag_details"] == []
    proposals = DocumentAnalysis.objects.get(document=document).proposed_tags
    assert tag.tag_name not in [proposal["value"] for proposal in proposals]


# --- department_applied_by in the three replies (finding 10) -------------------------------------


def test_a_typed_department_the_machine_matched_reads_as_the_persons_in_every_reply(session_client):
    """The stub suggests the scheme's first department, and this document's own department is the
    only one in its scheme, so the suggestion equals what the uploader typed."""
    client = session_client.client
    document = make_document(session_client.user, department="People")

    classified = classify(client, document.id).json()["classification"]
    assert (classified["department_outcome"], classified["department_applied_by"]) == (
        ASSIGNMENT_APPLIED, USER_APPLIED,
    )
    assert detail(client, document.id)["classification"]["department_applied_by"] == USER_APPLIED

    confirmed = client.post(f"{DOCUMENTS_URL}/{document.id}/classification", {}, format="json")
    assert confirmed.status_code == 200, confirmed.content
    assert (confirmed.json()["classification"]["department_outcome"],
            confirmed.json()["classification"]["department_applied_by"]) == (
        ASSIGNMENT_CONFIRMED, USER_APPLIED,
    )


def test_a_department_the_machine_filled_reads_as_the_machines_until_a_person_edits_it(session_client):
    client = session_client.client
    make_document(session_client.user, title="Budget memo", department="Finance")  # puts it in the scheme
    document = make_document(session_client.user, department="")

    classified = classify(client, document.id).json()
    assert classified["department"] == "Finance"
    assert classified["classification"]["department_applied_by"] == AI_APPLIED
    assert detail(client, document.id)["classification"]["department_applied_by"] == AI_APPLIED

    edited = client.post(f"{DOCUMENTS_URL}/{document.id}/classification",
                         {"department": "Operations"}, format="json")
    assert edited.status_code == 200, edited.content
    assert edited.json()["department"] == "Operations"
    assert edited.json()["classification"]["department_applied_by"] == USER_APPLIED
    assert detail(client, document.id)["classification"]["department_applied_by"] == USER_APPLIED
