"""CLAUDE.md invariant 1 since D-129 (13 November 2026): what the classifier does with a value outside
the scheme, and what a person's confirmation then makes of it, discloses nothing about material a
reader cannot see.

D-129 reverses D-128's creation of values. A classification proposes a Topic outside the scheme at
any confidence, and discards a Project or Process value outside it. A person confirming a proposal
is when a Tag is created, linked or brought back (``confirm_proposed_tag``). Seen from a reader of
the document being classified, a value outside that document's scheme is one of these, and the
reader must not be able to tell which:

(a) no Tag has it;
(b) an active, grown Tag that only material the reader cannot see carries, or that nothing carries
    any longer;
(c) a retired Tag, carried only by such material or by nothing.

So what the reader can observe must be identical in every case, apart from the ids of the rows:
- the classify reply;
- the document's detail: its ``tag_details``, ``classification.proposed_tags`` and ``tag_options``;
- the repository's browse;
- the scheme the classification prompt was built from;
- and, for a Topic, the confirmation's reply and everything after it.

Each case is set up and observed inside a savepoint that is then rolled back, so the cases share one
document and one value and differ only in what existed beforehand. The file was written for D-128,
when the classifier itself created such a value at or above the threshold.

``grown`` is what keeps a Topic a person brings in on an Administrator-only document away from every
document an Employee reads (``tag_scheme``). A Topic confirmed on an Employee-visible document is
offered to Employee-visible documents. Both are shown through the routes, from both roles, with the
stub recording the scheme each prompt was built from. No provider is reached.
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
    TOPIC_DIMENSION,
    USER_APPLIED,
)
from apps.documents.classification import confidence_threshold, tag_scheme
from apps.documents.models import ContentTag, Document, DocumentAnalysis, ExtractedContent, Tag
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


def confirm(client, document, dimension, value):
    response = client.post(
        f"{DOCUMENTS_URL}/{document.id}/proposed-tags/confirm",
        {"dimension": dimension, "value": value}, format="json",
    )
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
    """The document is the Employee's to read. It is classified by the session's role, and observed by
    the Employee: the classify reply, the detail, the browse, and the scheme shown to the model. A
    Topic is held at either confidence, and the session's role then confirms it, which is when its
    Tag is created, linked or brought back (``confirm_proposed_tag``). That reply, and the Employee's
    detail and browse after it, are observed as well. A Project or Process value is discarded and
    never shown (D-129)."""
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
            if dimension == TOPIC_DIMENSION:
                confirmed = confirm(session_client.client, staff, dimension, VALUE)
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
    # Not vacuously equal: what each case shows.
    classified, detail = first["classify"][1], first["detail"][1]
    assert first["detail"][0] == first["browse"][0] == 200
    assert VALUE not in first["scheme shown to the model"].tags[dimension]
    assert classified["tag_details"] == detail["tag_details"] == []
    assert detail["tag_options"][dimension] == []
    assert first["browse"][1]["facets"][dimension.lower()] == []
    if dimension == TOPIC_DIMENSION:
        held = [{"dimension": dimension, "value": VALUE, "confidence": confidence}]
        assert classified["classification"]["proposed_tags"] == held
        assert detail["classification"]["proposed_tags"] == held
        status, confirmed = first["confirm"]
        assert status == 200
        assert confirmed["classification"]["proposed_tags"] == []
        assert confirmed["tag_details"] == [{
            "dimension": dimension, "name": VALUE, "applied_by": AI_APPLIED, "provisional": False,
            "confirmed": True, "confidence": confidence,
        }]
        after = first["detail after the confirmation"][1]
        assert after["tag_options"][dimension] == [{"tag_name": VALUE}]
        assert first["browse after the confirmation"][1]["facets"][dimension.lower()] == [
            {"value": VALUE, "count": 1}
        ]
    else:
        assert classified["classification"]["proposed_tags"] == []
        assert detail["classification"]["proposed_tags"] == []


# --- grown: where a Topic a person confirms is offered ---------------------------------------------------


def proposed_and_confirmed(client, stub, document, name):
    """The classifier proposes the Topic ``name`` on ``document``, and ``client``'s role confirms it."""
    stub.classification = classification(tags=[(TOPIC_DIMENSION, name, THRESHOLD)])
    held = classify(client, document).json()["classification"]["proposed_tags"]
    assert [(entry["dimension"], entry["value"]) for entry in held] == [(TOPIC_DIMENSION, name.lower())]
    stub.classification = None  # from here the stub answers from the scheme it is shown
    [entry] = confirm(client, document, TOPIC_DIMENSION, name).json()["tag_details"]
    assert (entry["dimension"], entry["name"], entry["confirmed"]) == (TOPIC_DIMENSION, name.lower(), True)
    return Tag.objects.get(tag_name=name.lower(), dimension=TOPIC_DIMENSION)


def test_a_topic_confirmed_on_administrator_only_material_is_offered_only_to_administrator_only_material(
    employee, administrator, employee_client, administrator_client, stub_ai_service
):
    board = make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])
    other_board = make_document(administrator, title="Remuneration review", roles=[ADMINISTRATOR_ROLE_NAME])
    staff = make_document(employee, title="Staff handbook", roles=[EMPLOYEE_ROLE_NAME])
    shared = make_document(employee, title="Site notice", roles=BOTH_ROLES)

    created = proposed_and_confirmed(administrator_client, stub_ai_service, board, "Merger Talks")

    assert (created.active, created.grown) == (True, True)
    # Withheld from every document an Employee reads: its scheme, its options as either role reads
    # them, and the scheme its classification prompt is built from.
    for document in (staff, shared):
        assert "merger talks" not in tag_scheme(document).tags[TOPIC_DIMENSION], document.title
        for client in (employee_client, administrator_client):
            assert "merger talks" not in names(options(client, document)[TOPIC_DIMENSION]), document.title
        classify(employee_client, document)
        assert "merger talks" not in shown_to_the_model(stub_ai_service).tags[TOPIC_DIMENSION], document.title
    # Offered to another Administrator-only document.
    assert "merger talks" in tag_scheme(other_board).tags[TOPIC_DIMENSION]
    assert {"tag_id": str(created.pk), "tag_name": "merger talks"} in options(administrator_client, other_board)[TOPIC_DIMENSION]
    classify(administrator_client, other_board)
    assert "merger talks" in shown_to_the_model(stub_ai_service).tags[TOPIC_DIMENSION]


def test_a_topic_confirmed_on_an_employee_visible_document_is_offered_to_employee_visible_documents(
    employee, administrator, employee_client, administrator_client, stub_ai_service
):
    """An Administrator reads all an Employee reads (D-66), so a value an Employee-visible document
    carries is readable by every role: offered to every audience, Administrator-only included."""
    staff = make_document(employee, title="Staff handbook", roles=[EMPLOYEE_ROLE_NAME])
    other_staff = make_document(employee, title="Rostering guide", roles=[EMPLOYEE_ROLE_NAME])
    shared = make_document(employee, title="Site notice", roles=BOTH_ROLES)
    board = make_document(administrator, title="Board pack", roles=[ADMINISTRATOR_ROLE_NAME])

    created = proposed_and_confirmed(employee_client, stub_ai_service, staff, "Night Shifts")

    assert (created.active, created.grown) == (True, True)
    offered = {"tag_id": str(created.pk), "tag_name": "night shifts"}
    for document in (other_staff, shared, board):
        assert "night shifts" in tag_scheme(document).tags[TOPIC_DIMENSION], document.title
    assert offered in options(employee_client, other_staff)[TOPIC_DIMENSION]
    assert offered in options(employee_client, shared)[TOPIC_DIMENSION]
    assert offered in options(administrator_client, shared)[TOPIC_DIMENSION]
    assert offered in options(administrator_client, board)[TOPIC_DIMENSION]
    classify(employee_client, other_staff)
    assert "night shifts" in shown_to_the_model(stub_ai_service).tags[TOPIC_DIMENSION]
    applied = employee_client.post(f"{DOCUMENTS_URL}/{shared.id}/tags", {"tag_id": offered["tag_id"]}, format="json")
    assert applied.status_code == 201, applied.content


def test_a_project_or_process_value_outside_the_scheme_is_never_created_from_any_document(
    administrator, administrator_client, stub_ai_service
):
    """The other side of D-129: whatever the document's audience, a classification discards a Project
    or Process value outside the scheme and creates no Tag, so there is nothing to offer anywhere."""
    for roles in (BOTH_ROLES, [ADMINISTRATOR_ROLE_NAME]):
        document = make_document(administrator, title=f"Plan for {'-'.join(roles)}", roles=roles)
        stub_ai_service.classification = classification(
            tags=[(dimension, "Merger Talks", THRESHOLD) for dimension in REPOSITORY_TAG_DIMENSIONS
                  if dimension != TOPIC_DIMENSION]
        )
        classify(administrator_client, document)
        analysis = DocumentAnalysis.objects.get(document=document)
        assert sorted(entry["dimension"] for entry in analysis.discarded_suggestions) == sorted(
            dimension for dimension in REPOSITORY_TAG_DIMENSIONS if dimension != TOPIC_DIMENSION
        )
        assert analysis.proposed_tags == []
    assert not Tag.objects.exists()
