"""CLAUDE.md invariant 1 under D-128 (12 November 2026): a value the classifier creates or holds
discloses nothing about material a reader cannot see.

D-128 lets the classifier create and apply a value outside the scheme at or above the threshold, in
Project, Process or Topic, and hold one below it. Seen from a reader of the document being
classified, a value outside that document's scheme is one of these, and the reader must not be able
to tell which:

(a) no Tag has it;
(b) an active, grown Tag that only material the reader cannot see carries, or that nothing carries
    any longer;
(c) a retired Tag, carried only by such material or by nothing.

So what the reader can observe must be identical in every case, apart from the ids of the rows:
the classify reply, the document's detail (its ``tag_details``, ``classification.proposed_tags``
and ``tag_options``), the repository's browse, and the scheme the classification prompt was built
from. Each case is set up and observed inside a savepoint that is then rolled back, so the cases
share one document and one value and differ only in what existed beforehand.

``grown`` is what keeps a value the classifier creates from an Administrator-only document away
from every document an Employee reads (``tag_scheme``), and a value created from an Employee-visible
document is offered to Employee-visible documents. Both are shown through the routes, from both
roles, with the stub recording the scheme each prompt was built from. No provider is reached.
"""

import copy

import pytest
from django.db import transaction

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    AI_APPLIED,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    REPOSITORY_TAG_DIMENSIONS,
    SOURCE_TYPES,
    USER_APPLIED,
)
from apps.documents.classification import confidence_threshold, tag_scheme
from apps.documents.models import ContentTag, Document, ExtractedContent, Tag
from apps.documents.tests.classification_builders import EPSILON, STUB_CHAT_MODEL, classification

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
# The classification builders' model, which every scripted reply here carries: its own threshold.
THRESHOLD = confidence_threshold(STUB_CHAT_MODEL)
CONFIDENCES = {"at-threshold": THRESHOLD, "below-threshold": round(THRESHOLD - EPSILON, 3)}
VALUE = "harbour upgrade"

# What existed before the classification, as an Employee reading the document cannot tell apart.
STATES = (
    "no tag has it",
    "an active grown tag only administrator-only material carries",
    "an active grown tag nothing carries any longer",
    "a retired tag only administrator-only material carries",
    "a retired tag nothing carries",
)


def make_document(user, *, title, roles, department=""):
    document = Document.objects.create(
        title=title, file_type="txt", uploaded_by=user, status=DOCUMENT_INDEXED,
        visible_to_roles=roles, department=department,
    )
    ExtractedContent.objects.create(document=document, extracted_text="Berths, cranes and a timetable.")
    return document


def prepare(state, dimension, administrator):
    """Make ``state`` true of ``VALUE`` in ``dimension``. The retired tags are vocabulary that was
    retired (not grown), as a seeded value an Administrator retired would be."""
    if state == "no tag has it":
        return
    tag = Tag.objects.create(
        tag_name=VALUE, dimension=dimension, active="retired" not in state, grown="grown" in state
    )
    if "administrator-only material" in state:
        board = make_document(
            administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME], department="Executive"
        )
        ContentTag.objects.create(
            tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=board.pk,
            applied_by=USER_APPLIED, confirmed=True,
        )


def without_ids(body):
    """``body`` without what names a row or a moment: each link's id, each offered tag's id, and
    when the classification ran. Everything else is compared."""
    body = copy.deepcopy(body)
    if body.get("classification"):
        body["classification"].pop("classified_at")
    for entry in body.get("tag_details", []):
        entry.pop("content_tag_id")
    for entries in (body.get("tag_options") or {}).values():
        for entry in entries:
            entry.pop("tag_id")
    return body


class _RolledBack(Exception):
    pass


def undone(send):
    """``send()``'s result, with everything it wrote rolled back."""
    result = None
    try:
        with transaction.atomic():
            result = send()
            raise _RolledBack
    except _RolledBack:
        return result


def classify(client, document):
    response = client.post(f"{DOCUMENTS_URL}/{document.id}/classify", {}, format="json")
    assert response.status_code == 200, response.content
    return response


def options(client, document):
    response = client.get(f"{DOCUMENTS_URL}/{document.id}")
    assert response.status_code == 200, response.content
    return response.json()["tag_options"]


def names(entries):
    return [entry["tag_name"] for entry in entries]


def shown_to_the_model(stub):
    """The scheme the last classification prompt was built from, as the stub received it."""
    _, _, scheme = stub.classify_calls[-1]
    return scheme


# --- The equivalence ---------------------------------------------------------------------------------


@pytest.mark.parametrize("side", sorted(CONFIDENCES))
@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_an_employee_observes_the_same_whatever_a_value_outside_the_scheme_is(
    session_client, employee_client, administrator, stub_ai_service, dimension, side
):
    """The document is the Employee's to read. It is classified by the session's role, and observed
    by the Employee: the classify reply, the detail, the browse, and the scheme shown to the model.
    Below the threshold the value is held, and the session's role then confirms the proposal, which
    is when its Tag is created, linked or brought back (``confirm_proposed_tag``): that reply, and
    the Employee's detail and browse after it, are observed as well."""
    confidence = CONFIDENCES[side]
    staff = make_document(session_client.user, title="Harbour works plan", roles=[EMPLOYEE_ROLE_NAME])
    stub_ai_service.classification = classification(tags=[(dimension, "Harbour  Upgrade", confidence)])

    def seen_by_the_employee():
        detail = employee_client.get(f"{DOCUMENTS_URL}/{staff.id}")
        browse = employee_client.get(f"{DOCUMENTS_URL}/browse")
        return (detail.status_code, without_ids(detail.json())), (browse.status_code, browse.json())

    def observed(state):
        def send():
            prepare(state, dimension, administrator)
            classified = classify(session_client.client, staff)
            detail, browse = seen_by_the_employee()
            seen = {
                "classify": (classified.status_code, without_ids(classified.json())),
                "detail": detail,
                "browse": browse,
                "scheme shown to the model": shown_to_the_model(stub_ai_service),
            }
            if side == "below-threshold":
                confirmed = session_client.client.post(
                    f"{DOCUMENTS_URL}/{staff.id}/proposed-tags/confirm",
                    {"dimension": dimension, "value": VALUE}, format="json",
                )
                seen["confirm"] = (confirmed.status_code, without_ids(confirmed.json()))
                seen["detail after the confirmation"], seen["browse after the confirmation"] = (
                    seen_by_the_employee()
                )
            return seen
        return undone(send)

    observations = {state: observed(state) for state in STATES}

    first = observations[STATES[0]]
    for state in STATES[1:]:
        assert observations[state] == first, state
    # Not vacuously equal: what each case shows, at or above the threshold and below it.
    classified, detail = first["classify"][1], first["detail"][1]
    assert first["detail"][0] == first["browse"][0] == 200
    assert VALUE not in first["scheme shown to the model"].tags[dimension]
    linked = {"dimension": dimension, "name": VALUE, "applied_by": AI_APPLIED, "provisional": False}
    if side == "at-threshold":
        applied = [{**linked, "confirmed": False, "confidence": confidence}]
        assert classified["tag_details"] == detail["tag_details"] == applied
        assert classified["classification"]["proposed_tags"] == []
        assert detail["tag_options"][dimension] == [{"tag_name": VALUE}]
        assert first["browse"][1]["facets"][dimension.lower()] == [{"value": VALUE, "count": 1}]
    else:
        held = [{"dimension": dimension, "value": VALUE, "confidence": confidence}]
        assert classified["classification"]["proposed_tags"] == held
        assert detail["classification"]["proposed_tags"] == held
        assert classified["tag_details"] == detail["tag_details"] == []
        assert detail["tag_options"][dimension] == []
        assert first["browse"][1]["facets"][dimension.lower()] == []
        status, confirmed = first["confirm"]
        assert status == 200
        assert confirmed["classification"]["proposed_tags"] == []
        assert confirmed["tag_details"] == [{**linked, "confirmed": True, "confidence": confidence}]
        after = first["detail after the confirmation"][1]
        assert after["tag_options"][dimension] == [{"tag_name": VALUE}]
        assert first["browse after the confirmation"][1]["facets"][dimension.lower()] == [
            {"value": VALUE, "count": 1}
        ]


# --- grown: where a value the classifier creates is offered --------------------------------------------


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_value_created_from_administrator_only_material_is_offered_only_to_administrator_only_material(
    employee, administrator, employee_client, administrator_client, stub_ai_service, dimension
):
    board = make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])
    other_board = make_document(administrator, title="Remuneration review", roles=[ADMINISTRATOR_ROLE_NAME])
    staff = make_document(employee, title="Staff handbook", roles=[EMPLOYEE_ROLE_NAME])
    shared = make_document(employee, title="Site notice", roles=BOTH_ROLES)
    stub_ai_service.classification = classification(tags=[(dimension, "Merger Talks", THRESHOLD)])

    [entry] = classify(administrator_client, board).json()["tag_details"]

    assert (entry["dimension"], entry["name"], entry["provisional"]) == (dimension, "merger talks", False)
    created = Tag.objects.get(tag_name="merger talks")
    assert (created.dimension, created.active) == (dimension, True)
    stub_ai_service.classification = None  # from here the stub answers from the scheme it is shown
    # Withheld from every document an Employee reads: its scheme, its options as either role reads
    # them, and the scheme its classification prompt is built from.
    for document in (staff, shared):
        assert "merger talks" not in tag_scheme(document).tags[dimension], document.title
        for client in (employee_client, administrator_client):
            assert "merger talks" not in names(options(client, document)[dimension]), document.title
        classify(employee_client, document)
        assert "merger talks" not in shown_to_the_model(stub_ai_service).tags[dimension], document.title
    # Offered to another Administrator-only document.
    assert "merger talks" in tag_scheme(other_board).tags[dimension]
    assert {"tag_id": str(created.pk), "tag_name": "merger talks"} in options(administrator_client, other_board)[dimension]
    classify(administrator_client, other_board)
    assert "merger talks" in shown_to_the_model(stub_ai_service).tags[dimension]


@pytest.mark.parametrize("dimension", REPOSITORY_TAG_DIMENSIONS)
def test_a_value_created_from_an_employee_visible_document_is_offered_to_employee_visible_documents(
    employee, administrator, employee_client, administrator_client, stub_ai_service, dimension
):
    """An Administrator reads all an Employee reads (D-66), so a value an Employee-visible document
    carries is readable by every role: offered to every audience, Administrator-only included."""
    staff = make_document(employee, title="Staff handbook", roles=[EMPLOYEE_ROLE_NAME])
    other_staff = make_document(employee, title="Rostering guide", roles=[EMPLOYEE_ROLE_NAME])
    shared = make_document(employee, title="Site notice", roles=BOTH_ROLES)
    board = make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])
    stub_ai_service.classification = classification(tags=[(dimension, "Night Shifts", THRESHOLD)])

    classify(employee_client, staff)

    created = Tag.objects.get(tag_name="night shifts")
    assert created.dimension == dimension
    stub_ai_service.classification = None
    offered = {"tag_id": str(created.pk), "tag_name": "night shifts"}
    for document in (other_staff, shared, board):
        assert "night shifts" in tag_scheme(document).tags[dimension], document.title
    assert offered in options(employee_client, other_staff)[dimension]
    assert offered in options(employee_client, shared)[dimension]
    assert offered in options(administrator_client, shared)[dimension]
    assert offered in options(administrator_client, board)[dimension]
    classify(employee_client, other_staff)
    assert "night shifts" in shown_to_the_model(stub_ai_service).tags[dimension]
    applied = employee_client.post(f"{DOCUMENTS_URL}/{shared.id}/tags", {"tag_id": offered["tag_id"]}, format="json")
    assert applied.status_code == 201, applied.content
