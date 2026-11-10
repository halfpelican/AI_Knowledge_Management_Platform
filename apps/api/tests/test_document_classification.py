"""FR-10's routes (D-104, D-105): classify now, confirm or edit the classification, accept or remove a
tag, confirm or reject a proposed topic; the detail's ``classification`` and ``tag_details``; and
the ``classification`` the upload's and the reprocess's 201 bodies carry.

Each route: a session; the document resolved through the caller's scope FIRST, so an unknown id and
one outside the scope are the same 404 with the same body (D-46); then ``contribute_content``, held
by both roles (D-105), so the 403 is proven by taking it away, as test_document_upload.py does;
never a body that says more than the 404 would. Every route is exercised from both roles through
``session_client``.

No live provider: the stub's ``classify_document`` answers from the scheme (apps/ai/testing.py),
and a test that needs a particular reply sets the stub's ``classification``.
"""

import uuid

import pytest

from apps.accounts.models import RolePermission
from apps.ai.base import ProviderUnavailable
from apps.ai.testing import STUB_CHAT_MODEL, STUB_CONFIDENCE
from apps.api.views import CLASSIFICATION_UNAVAILABLE_MESSAGE, INSUFFICIENT_TEXT_MESSAGE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    ASSIGNMENT_APPLIED,
    ASSIGNMENT_CONFIRMED,
    ASSIGNMENT_DISCARDED,
    ASSIGNMENT_PROVISIONAL,
    CONTRIBUTE_CONTENT_PERMISSION,
    DOCUMENT_INDEXED,
    DOCUMENT_TYPES,
    EMPLOYEE_ROLE_NAME,
    INGESTION_THROTTLE_RATE,
    MAXIMUM_EMBED_ATTEMPTS,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
)
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import ContentTag, Document, DocumentAnalysis, ExtractedContent, Tag
from apps.documents.tests.classification_builders import (
    ABOVE_THRESHOLD,
    BELOW_THRESHOLD,
    POLICY,
    REPORT,
    classification,
)
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
NOT_FOUND_BODY = {"detail": "No Document matches the given query."}
FORBIDDEN_BODY = {
    "detail": f"Your role does not hold the '{CONTRIBUTE_CONTENT_PERMISSION}' permission."
}
TEXT = "Employees may request annual leave in writing. Approval rests with the manager."
CLASSIFICATION_KEYS = {
    "doc_type", "doc_type_outcome", "department_outcome", "machine_doc_type",
    "machine_doc_type_confidence", "machine_department", "machine_department_confidence",
    "user_edited", "proposed_topics", "classified_at", "model", "input_truncated",
    # D-119 finding 10: whose department it is ("user", "ai" or null).
    "department_applied_by",
}
TAG_DETAIL_KEYS = {
    "content_tag_id", "dimension", "name", "applied_by", "confirmed", "provisional", "confidence",
}


# --- Helpers -----------------------------------------------------------------------------------


def make_document(user, *, title="Leave policy", roles=None, department="People", text=TEXT):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        department=department, visible_to_roles=BOTH_ROLES if roles is None else roles,
    )
    if text is not None:
        ExtractedContent.objects.create(document=document, extracted_text=text)
    return document


def classify(client, doc_id):
    return client.post(f"{DOCUMENTS_URL}/{doc_id}/classify", {}, format="json")


def confirm(client, doc_id, **body):
    return client.post(f"{DOCUMENTS_URL}/{doc_id}/classification", body, format="json")


def accept_tag(client, doc_id, link_id):
    return client.post(f"{DOCUMENTS_URL}/{doc_id}/tags/{link_id}/confirm", {}, format="json")


def remove_tag(client, doc_id, link_id):
    return client.delete(f"{DOCUMENTS_URL}/{doc_id}/tags/{link_id}")


def confirm_topic(client, doc_id, value="budget planning"):
    return client.post(f"{DOCUMENTS_URL}/{doc_id}/proposed-topics/confirm", {"value": value}, format="json")


def reject_topic(client, doc_id, value="budget planning"):
    return client.post(f"{DOCUMENTS_URL}/{doc_id}/proposed-topics/reject", {"value": value}, format="json")


def detail(client, doc_id):
    return client.get(f"{DOCUMENTS_URL}/{doc_id}")


def revoke_contribute(user):
    RolePermission.objects.filter(
        role=user.role, permission__permission_name=CONTRIBUTE_CONTENT_PERMISSION
    ).delete()


def links_of(document):
    return ContentTag.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk)


def outage(title, text, scheme):
    raise ProviderUnavailable("stub outage")


# Every route, sent the cheapest request it accepts, for the tests that only need to reach it.
ROUTES = {
    "POST classify": lambda client, doc_id, link_id: classify(client, doc_id),
    "POST classification": lambda client, doc_id, link_id: confirm(client, doc_id),
    "POST tag confirm": lambda client, doc_id, link_id: accept_tag(client, doc_id, link_id),
    "DELETE tag": lambda client, doc_id, link_id: remove_tag(client, doc_id, link_id),
    "POST proposed-topics/confirm": lambda client, doc_id, link_id: confirm_topic(client, doc_id),
    "POST proposed-topics/reject": lambda client, doc_id, link_id: reject_topic(client, doc_id),
}


# --- POST /api/documents/{id}/classify ---------------------------------------------------------


def test_classify_returns_the_classification_and_the_tag_details(session_client):
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)

    response = classify(session_client.client, document.id)

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"classification", "tag_details", "department"}
    # The suggestion equals the document's own department, so nothing was written and it stands.
    assert body["department"] == "People"
    result = body["classification"]
    assert set(result) == CLASSIFICATION_KEYS
    assert (result["doc_type"], result["doc_type_outcome"]) == (POLICY, ASSIGNMENT_APPLIED)
    assert result["machine_doc_type"] == POLICY
    assert result["machine_doc_type_confidence"] == STUB_CONFIDENCE
    assert isinstance(result["machine_doc_type_confidence"], float)  # a number, not a string
    # The document's own department is in its scheme, so the stub's suggestion of it is applied.
    assert (result["machine_department"], result["department_outcome"]) == ("People", ASSIGNMENT_APPLIED)
    assert result["machine_department_confidence"] == STUB_CONFIDENCE
    assert result["user_edited"] is False
    assert result["proposed_topics"] == []
    assert result["model"] == STUB_CHAT_MODEL
    assert result["input_truncated"] is False
    assert result["classified_at"]
    [entry] = body["tag_details"]
    assert set(entry) == TAG_DETAIL_KEYS
    assert (entry["dimension"], entry["name"]) == (PROJECT_DIMENSION, "bridge maintenance")
    assert (entry["applied_by"], entry["confirmed"], entry["provisional"]) == (AI_APPLIED, False, False)
    assert entry["confidence"] == STUB_CONFIDENCE
    assert uuid.UUID(entry["content_tag_id"]) == links_of(document).get().pk
    assert links_of(document).get().tag == tag


def test_classify_replies_with_the_department_the_machine_filled(session_client):
    """A blank department is filled by an applied in-scheme suggestion (D-105's note of 10
    November), and the reply carries it, re-read from the row, so the page need not reload."""
    # "Finance" is in the scheme because another document both roles can read carries it, and it
    # is the scheme's only department, so it is what the stub suggests, at STUB_CONFIDENCE.
    make_document(session_client.user, title="Budget memo", department="Finance")
    document = make_document(session_client.user, department="")

    response = classify(session_client.client, document.id)

    assert response.status_code == 200, response.content
    body = response.json()
    result = body["classification"]
    assert (result["machine_department"], result["department_outcome"]) == ("Finance", ASSIGNMENT_APPLIED)
    assert body["department"] == "Finance"
    document.refresh_from_db()
    assert document.department == "Finance"


def test_classify_keeps_a_different_department_and_replies_with_it(session_client):
    """A department already on the document is not the machine's to replace: the suggestion is
    held as provisional, and the reply's department is the one stored, not the suggestion."""
    # The scheme is ("Finance", "People"), sorted, so the stub suggests "Finance".
    make_document(session_client.user, title="Budget memo", department="Finance")
    document = make_document(session_client.user, department="People")

    response = classify(session_client.client, document.id)

    assert response.status_code == 200, response.content
    body = response.json()
    result = body["classification"]
    assert (result["machine_department"], result["department_outcome"]) == ("Finance", ASSIGNMENT_PROVISIONAL)
    assert body["department"] == "People"
    document.refresh_from_db()
    assert document.department == "People"


def test_classify_without_extracted_text_is_422(session_client, stub_ai_service):
    document = make_document(session_client.user, text=None)

    response = classify(session_client.client, document.id)

    assert response.status_code == 422
    assert response.json() == {"detail": INSUFFICIENT_TEXT_MESSAGE}
    assert stub_ai_service.classify_calls == []
    assert not DocumentAnalysis.objects.exists()


def test_classify_during_a_provider_outage_is_503_and_writes_nothing(session_client, stub_ai_service):
    document = make_document(session_client.user)
    stub_ai_service.classification = outage

    response = classify(session_client.client, document.id)

    assert response.status_code == 503
    assert response.json() == {"detail": CLASSIFICATION_UNAVAILABLE_MESSAGE}
    assert not DocumentAnalysis.objects.exists()


def test_classify_twice_updates_the_one_analysis(session_client):
    document = make_document(session_client.user)
    first = classify(session_client.client, document.id).json()["classification"]
    second = classify(session_client.client, document.id).json()["classification"]
    assert DocumentAnalysis.objects.filter(document=document).count() == 1
    assert second["classified_at"] >= first["classified_at"]


def test_classify_is_throttled_in_the_ingestion_scope(session_client):
    """D-79's one budget: a classify of nothing is a 404 that still spends it, and past the rate
    both classify and the upload answer 429."""
    client = session_client.client
    limit = int(INGESTION_THROTTLE_RATE.split("/")[0])
    for _ in range(limit):
        assert classify(client, uuid.uuid4()).status_code == 404
    assert classify(client, uuid.uuid4()).status_code == 429
    assert client.post(DOCUMENTS_URL, {"title": "No file"}, format="multipart").status_code == 429


# --- 404 before 403, on every route -----------------------------------------------------------


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_an_unknown_document_is_404_on_every_route(session_client, route):
    response = ROUTES[route](session_client.client, uuid.uuid4(), uuid.uuid4())
    assert response.status_code == 404, (route, response.content)
    assert response.json() == NOT_FOUND_BODY


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_an_employee_reaching_an_administrator_only_document_gets_the_same_404_with_or_without_the_permission(
    employee, employee_client, administrator, stub_ai_service, route
):
    restricted = make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])
    tag = Tag.objects.create(tag_name="succession planning", dimension=PROJECT_DIMENSION)
    link = ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=restricted.pk, applied_by=AI_APPLIED,
    )

    with_permission = ROUTES[route](employee_client, restricted.id, link.id)
    revoke_contribute(employee)
    without_permission = ROUTES[route](employee_client, restricted.id, link.id)

    for response in (with_permission, without_permission):
        assert response.status_code == 404, (route, response.content)
        assert response.json() == NOT_FOUND_BODY
        assert b"Board pack" not in response.content and b"succession" not in response.content
    assert stub_ai_service.classify_calls == []
    assert not DocumentAnalysis.objects.exists()
    assert links_of(restricted).count() == 1


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_a_role_without_contribute_content_is_403_on_a_document_it_can_see(
    session_client, stub_ai_service, route
):
    document = make_document(session_client.user)
    tag = Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    link = ContentTag.objects.create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.pk, applied_by=AI_APPLIED,
    )
    revoke_contribute(session_client.user)

    response = ROUTES[route](session_client.client, document.id, link.id)

    assert response.status_code == 403, (route, response.content)
    assert response.json() == FORBIDDEN_BODY
    assert stub_ai_service.classify_calls == []
    assert links_of(document).count() == 1


# --- POST /api/documents/{id}/classification ---------------------------------------------------


def test_confirming_as_it_stands_applies_a_provisional_type_and_marks_both_confirmed(
    session_client, stub_ai_service
):
    # "Finance" is in the scheme because another document both roles can read carries it; the
    # document being classified starts with no department, so writing it is visible.
    make_document(session_client.user, title="Budget memo", department="Finance")
    document = make_document(session_client.user, department="")
    stub_ai_service.classification = classification(
        doc_type=POLICY, type_confidence=BELOW_THRESHOLD,
        department="Finance", department_confidence=BELOW_THRESHOLD,
    )
    held = classify(session_client.client, document.id).json()["classification"]
    assert (held["doc_type"], held["doc_type_outcome"]) == (None, ASSIGNMENT_PROVISIONAL)
    assert held["department_outcome"] == ASSIGNMENT_PROVISIONAL
    document.refresh_from_db()
    assert document.department == ""  # held, not written

    response = confirm(session_client.client, document.id)

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"classification", "department"}
    # The effective department after the confirm, so the client need not infer it.
    assert body["department"] == "Finance"
    result = body["classification"]
    assert (result["doc_type"], result["doc_type_outcome"]) == (POLICY, ASSIGNMENT_CONFIRMED)
    assert result["department_outcome"] == ASSIGNMENT_CONFIRMED
    assert result["user_edited"] is True
    document.refresh_from_db()
    assert document.department == "Finance"


def test_an_edited_type_and_department_are_written_and_the_machine_values_kept(session_client):
    document = make_document(session_client.user)
    classify(session_client.client, document.id)

    response = confirm(session_client.client, document.id, doc_type=REPORT, department="Operations")

    assert response.status_code == 200, response.content
    assert response.json()["department"] == "Operations"  # the edited value, as now stored
    result = response.json()["classification"]
    assert (result["doc_type"], result["machine_doc_type"]) == (REPORT, POLICY)
    assert (result["doc_type_outcome"], result["department_outcome"]) == (ASSIGNMENT_CONFIRMED, ASSIGNMENT_CONFIRMED)
    assert result["machine_department"] == "People"
    assert detail(session_client.client, document.id).json()["department"] == "Operations"


def test_a_blank_department_is_written_blank(session_client):
    document = make_document(session_client.user)
    classify(session_client.client, document.id)
    response = confirm(session_client.client, document.id, department="")
    assert response.status_code == 200, response.content
    assert detail(session_client.client, document.id).json()["department"] == ""


def test_a_type_outside_the_fixed_list_is_400_keyed_on_doc_type(session_client):
    document = make_document(session_client.user)
    classify(session_client.client, document.id)

    response = confirm(session_client.client, document.id, doc_type="Memo")

    assert response.status_code == 400
    assert set(response.json()) == {"doc_type"}
    analysis = DocumentAnalysis.objects.get(document=document)
    assert (analysis.doc_type, analysis.user_edited) == (POLICY, False)


def test_an_over_long_department_is_400_keyed_on_department(session_client):
    document = make_document(session_client.user)
    classify(session_client.client, document.id)
    response = confirm(session_client.client, document.id, department="x" * (NAME_MAX_LENGTH + 1))
    assert response.status_code == 400
    assert set(response.json()) == {"department"}


def test_confirming_a_document_never_classified_is_the_same_404(session_client):
    document = make_document(session_client.user)
    response = confirm(session_client.client, document.id, doc_type=POLICY)
    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


# --- Tags: accept or remove in a single action -------------------------------------------------


@pytest.fixture
def held_link(session_client, stub_ai_service):
    """A document with one provisional AI link in Project, written by the classify route."""
    document = make_document(session_client.user)
    Tag.objects.create(tag_name="bridge maintenance", dimension=PROJECT_DIMENSION)
    stub_ai_service.classification = classification(
        department="People", tags=[(PROJECT_DIMENSION, "bridge maintenance", BELOW_THRESHOLD)]
    )
    body = classify(session_client.client, document.id).json()
    [entry] = body["tag_details"]
    assert entry["provisional"] is True
    stub_ai_service.classification = None
    return document, links_of(document).get()


def test_accepting_a_held_tag_returns_the_entry_confirmed_with_its_provenance(session_client, held_link):
    document, link = held_link

    response = accept_tag(session_client.client, document.id, link.id)

    assert response.status_code == 200, response.content
    entry = response.json()
    assert set(entry) == TAG_DETAIL_KEYS
    assert entry["content_tag_id"] == str(link.id)
    assert (entry["confirmed"], entry["provisional"], entry["applied_by"]) == (True, False, AI_APPLIED)
    assert entry["confidence"] == BELOW_THRESHOLD
    assert detail(session_client.client, document.id).json()["tags"]["project"] == ["bridge maintenance"]


def test_removing_a_tag_is_204_and_the_vocabulary_stays(session_client, held_link):
    """The held AI link is kept, marked removed, beside the machine's assignment, and is in no read
    (D-105's dated note of 10 November 2026, night; until then the row was deleted)."""
    document, link = held_link

    response = remove_tag(session_client.client, document.id, link.id)

    assert response.status_code == 204
    assert not response.content
    kept = links_of(document).get()
    assert (kept.pk, kept.removed, kept.provisional) == (link.pk, True, True)
    assert Tag.objects.filter(tag_name="bridge maintenance").exists()
    assert detail(session_client.client, document.id).json()["tag_details"] == []


def test_a_link_on_another_document_is_404_for_accept_and_remove(session_client, held_link):
    document, link = held_link
    other = make_document(session_client.user, title="Another document")

    for response in (accept_tag(session_client.client, other.id, link.id),
                     remove_tag(session_client.client, other.id, link.id)):
        assert response.status_code == 404
        assert response.json() == NOT_FOUND_BODY
    link.refresh_from_db()
    assert (link.confirmed, link.provisional) == (False, True)


def test_an_unknown_link_id_is_404_for_accept_and_remove(session_client, held_link):
    document, _ = held_link
    for response in (accept_tag(session_client.client, document.id, uuid.uuid4()),
                     remove_tag(session_client.client, document.id, uuid.uuid4())):
        assert response.status_code == 404
        assert response.json() == NOT_FOUND_BODY
    assert links_of(document).count() == 1


# --- Proposed topics ---------------------------------------------------------------------------


@pytest.fixture
def proposed(session_client, stub_ai_service):
    """A document whose classification proposed the out-of-scheme Topic "budget planning"."""
    document = make_document(session_client.user)
    stub_ai_service.classification = classification(
        department="People", tags=[(TOPIC_DIMENSION, "Budget  Planning", ABOVE_THRESHOLD)]
    )
    body = classify(session_client.client, document.id).json()
    assert body["classification"]["proposed_topics"] == [
        {"value": "budget planning", "confidence": ABOVE_THRESHOLD}
    ]
    assert body["tag_details"] == []
    stub_ai_service.classification = None
    return document


def test_confirming_a_proposed_topic_creates_the_tag_and_the_confirmed_link(session_client, proposed):
    response = confirm_topic(session_client.client, proposed.id, "Budget Planning")

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"classification", "tag_details"}
    assert body["classification"]["proposed_topics"] == []
    [entry] = body["tag_details"]
    assert (entry["dimension"], entry["name"]) == (TOPIC_DIMENSION, "budget planning")
    assert (entry["applied_by"], entry["confirmed"], entry["provisional"]) == (AI_APPLIED, True, False)
    assert entry["confidence"] == ABOVE_THRESHOLD
    assert Tag.objects.filter(tag_name="budget planning", dimension=TOPIC_DIMENSION, active=True).exists()
    assert detail(session_client.client, proposed.id).json()["tags"]["topic"] == ["budget planning"]


def test_rejecting_a_proposed_topic_drops_it_and_creates_nothing(session_client, proposed):
    response = reject_topic(session_client.client, proposed.id, "budget planning")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["classification"]["proposed_topics"] == []
    assert body["tag_details"] == []
    assert not Tag.objects.filter(tag_name="budget planning").exists()


def test_a_value_that_was_not_proposed_is_the_same_404(session_client, proposed):
    for response in (confirm_topic(session_client.client, proposed.id, "risk appetite"),
                     reject_topic(session_client.client, proposed.id, "risk appetite")):
        assert response.status_code == 404
        assert response.json() == NOT_FOUND_BODY
    assert not Tag.objects.filter(tag_name="risk appetite").exists()
    assert DocumentAnalysis.objects.get(document=proposed).proposed_topics == [
        {"value": "budget planning", "confidence": ABOVE_THRESHOLD}
    ]


@pytest.mark.parametrize("value", ["", "   ", "x" * (NAME_MAX_LENGTH + 1)], ids=["empty", "blank", "long"])
def test_a_blank_or_over_long_value_is_400_keyed_on_value(session_client, proposed, value):
    for response in (confirm_topic(session_client.client, proposed.id, value),
                     reject_topic(session_client.client, proposed.id, value)):
        assert response.status_code == 400, response.content
        assert set(response.json()) == {"value"}


# --- The detail's two new fields ---------------------------------------------------------------


def test_the_detail_carries_null_classification_and_empty_tag_details_before_any_classification(
    session_client,
):
    document = make_document(session_client.user)
    body = detail(session_client.client, document.id).json()
    assert body["classification"] is None
    assert body["tag_details"] == []


def test_the_detail_carries_the_classification_and_every_link_sorted_by_dimension_then_name(
    session_client, stub_ai_service
):
    document = make_document(session_client.user)
    for dimension, name in ((PROJECT_DIMENSION, "bridge maintenance"), (PROCESS_DIMENSION, "procurement"),
                            (TOPIC_DIMENSION, "safety"), (PROJECT_DIMENSION, "harbour upgrade")):
        Tag.objects.create(tag_name=name, dimension=dimension)
    stub_ai_service.classification = classification(
        department="People",
        tags=[
            (TOPIC_DIMENSION, "safety", BELOW_THRESHOLD),
            (PROJECT_DIMENSION, "harbour upgrade", ABOVE_THRESHOLD),
            (PROCESS_DIMENSION, "procurement", ABOVE_THRESHOLD),
            (PROJECT_DIMENSION, "bridge maintenance", ABOVE_THRESHOLD),
        ],
    )
    classify(session_client.client, document.id)

    body = detail(session_client.client, document.id).json()

    assert set(body["classification"]) == CLASSIFICATION_KEYS
    assert body["classification"]["doc_type"] == POLICY
    assert [(entry["dimension"], entry["name"], entry["provisional"]) for entry in body["tag_details"]] == [
        (PROCESS_DIMENSION, "procurement", False),
        (PROJECT_DIMENSION, "bridge maintenance", False),
        (PROJECT_DIMENSION, "harbour upgrade", False),
        (TOPIC_DIMENSION, "safety", True),
    ]
    # ``tags`` keeps its shape and lists the applied links only.
    assert body["tags"] == {"project": ["bridge maintenance", "harbour upgrade"],
                            "process": ["procurement"], "topic": []}


def test_a_discarded_department_is_reported_as_such(session_client, stub_ai_service):
    document = make_document(session_client.user)
    stub_ai_service.classification = classification(department="Marketing")
    result = classify(session_client.client, document.id).json()["classification"]
    assert (result["machine_department"], result["department_outcome"]) == ("Marketing", ASSIGNMENT_DISCARDED)
    assert detail(session_client.client, document.id).json()["department"] == "People"


# --- The 201 bodies of the upload and the reprocess ---------------------------------------------


def test_the_upload_201_carries_the_classification(session_client, upload):
    response = session_client.client.post(
        DOCUMENTS_URL, {"file": upload("sample.txt"), "title": "Sample"}, format="multipart"
    )
    assert response.status_code == 201, response.content
    result = response.json()["classification"]
    assert set(result) == CLASSIFICATION_KEYS
    assert result["machine_doc_type"] == DOCUMENT_TYPES[0]
    assert DocumentAnalysis.objects.filter(document_id=response.json()["doc_id"]).exists()


def test_the_upload_201_carries_null_when_the_classification_failed(session_client, upload, stub_ai_service):
    stub_ai_service.classification = outage
    response = session_client.client.post(
        DOCUMENTS_URL, {"file": upload("sample.txt"), "title": "Sample"}, format="multipart"
    )
    assert response.status_code == 201, response.content
    assert response.json()["classification"] is None
    assert response.json()["status"] == DOCUMENT_INDEXED


def test_a_422_upload_carries_no_classification_and_the_reprocess_201_does(
    session_client, upload, monkeypatch
):
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
    failed = session_client.client.post(
        DOCUMENTS_URL, {"file": upload("sample.txt"), "title": "Sample"}, format="multipart"
    )
    assert failed.status_code == 422, failed.content
    assert "classification" not in failed.json()

    install(monkeypatch, ScriptedEmbedService())
    reprocessed = session_client.client.post(
        f"{DOCUMENTS_URL}/{failed.json()['doc_id']}/reprocess", {}, format="json"
    )
    assert reprocessed.status_code == 201, reprocessed.content
    assert set(reprocessed.json()["classification"]) == CLASSIFICATION_KEYS
    assert reprocessed.json()["status"] == DOCUMENT_INDEXED
