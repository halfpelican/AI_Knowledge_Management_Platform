"""The knowledge map's second view: ``GET /api/knowledge-map/evidence`` (D-138).

Claims joined to the passages they cite, after the proposal's Evidence mock-up (Figure 8.7).
The scoping rules are tested from both an Employee and an Administrator session (CLAUDE.md
section 8, item 2): the row a role may not read is stamped by ``unreadable_scope``, which for
an Administrator is a row stamped for nobody (D-66).

What the module docstring of ``apps/api/evidence_map.py`` calls its three rules:

1. a claim's cited chunk is one of the passages its answer was generated from;
2. every one of those passages is a chunk in the viewer's scope, and so the cited one is;
3. the cited chunk's own source is in the viewer's scope.
"""

import ast
import hashlib
import hmac
import inspect
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import RolePermission
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api import evidence_map
from apps.api.serializers import EVIDENCE_FOCUS_MALFORMED_MESSAGE, FOCUS_INCOMPLETE_MESSAGE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    EVIDENCE_MAP_NODE_TYPES,
    EVIDENCE_MAP_RELATIONSHIPS,
    KNOWLEDGE_MAP_THROTTLE_RATE,
    KNOWLEDGE_MAP_TRUNCATION_REASONS,
    MAXIMUM_NODE_COUNT,
    MAXIMUM_TRAVERSAL_DEPTH,
    MEETING_INDEXED,
    SOURCE_TYPES,
    VIEW_KNOWLEDGE_MAP_PERMISSION,
)
from apps.documents.models import ContentChunk, Document
from apps.meetings.models import Meeting
from apps.retrieval.models import AnswerCitation, QueryLog
from apps.retrieval.tests.scopes import unreadable_scope

pytestmark = pytest.mark.django_db

User = get_user_model()

EVIDENCE_URL = "/api/knowledge-map/evidence"
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
CLAIM, PASSAGE = EVIDENCE_MAP_NODE_TYPES
(CITES,) = EVIDENCE_MAP_RELATIONSHIPS
NODE_COUNT, DEPTH = KNOWLEDGE_MAP_TRUNCATION_REASONS
DOCUMENT_SOURCE, MEETING_SOURCE = SOURCE_TYPES

BODY_KEYS = {
    "focus", "nodes", "edges", "truncated", "truncated_by", "maximum_node_count",
    "maximum_traversal_depth",
}
NODE_KEYS = {"id", "type", "item_id", "label", "dimension", "connection_count", "detail"}
EDGE_KEYS = {"source", "target", "relationship", "weight"}
CLAIM_DETAIL_KEYS = {"answer_count", "passage_count", "first_admitted_at", "last_admitted_at"}
PASSAGE_DETAIL_KEYS = {"source_type", "source_id", "source_title", "position", "ai_generated"}

# The one body every "nothing to show" case gets, written out and not derived from a response.
EMPTY_BODY = {
    "focus": None,
    "nodes": [],
    "edges": [],
    "truncated": False,
    "truncated_by": None,
    "maximum_node_count": MAXIMUM_NODE_COUNT,
    "maximum_traversal_depth": MAXIMUM_TRAVERSAL_DEPTH,
}

EARLIEST = datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc)

# Text no claim, title or name in this file contains, so the bytes can be searched for each.
QUESTION_MARKER = "QUESTION-TEXT-NOBODY-ELSE-SEES"
ANSWER_MARKER = "WHOLE-ANSWER-TEXT"
PASSAGE_MARKER = "PASSAGE-BODY-TEXT"

LEAVE = "Annual leave is twenty days."
NOTICE = "Leave needs two weeks' notice."
PARKING = "Parking permits renew in July."
SECRET = "The restructure removes four roles."


def at(days):
    """A moment ``days`` days after the earliest row: 09:00 UTC, the same day in the project's zone."""
    return EARLIEST + timedelta(days=days)


# --- Row builders ----------------------------------------------------------------------------


def person(name):
    return User.objects.create_user(f"{name.lower().replace(' ', '.')}@people.example", None, name=name)


def add_document(title, *, uploader, roles=None):
    return Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=uploader,
        status=DOCUMENT_INDEXED,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )


def add_meeting(title, *, roles=None):
    return Meeting.objects.create(
        title=title,
        meeting_date=EARLIEST.date(),
        transcript_text=f"TRANSCRIPT-BODY of {title}.",
        status=MEETING_INDEXED,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )


def add_chunk(source, index=0, *, roles=None, ai_generated=False):
    """A chunk of ``source``, stamped as ingestion stamps it unless ``roles`` says otherwise."""
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[0] = 1.0
    return ContentChunk.objects.create(
        source_type=MEETING_SOURCE if isinstance(source, Meeting) else DOCUMENT_SOURCE,
        source_id=source.id,
        chunk_index=index,
        chunk_text=f"{PASSAGE_MARKER} {index} of {source.title}.",
        embedding=vector,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=source.visible_to_roles if roles is None else roles,
        ai_generated=ai_generated,
    )


def answer(asker, *statements, supplied=None, days=0, when=None):
    """One answered question: its log row and one citation row for each ``(text, chunk)``.

    ``supplied`` is every chunk, or chunk identifier, the model was given. It defaults to the
    chunks the statements cite. It was answered ``days`` days after the earliest row, or at
    the moment ``when``.
    """
    given = [chunk for _, chunk in statements] if supplied is None else supplied
    query = QueryLog.objects.create(
        user=asker,
        question=f"{QUESTION_MARKER} asked by {asker.name}",
        answer_text=ANSWER_MARKER,
        retrieved_chunk_ids=[getattr(item, "id", item) for item in given],
        answered=True,
    )
    QueryLog.objects.filter(pk=query.pk).update(answered_at=at(days) if when is None else when)
    for position, (text, chunk) in enumerate(statements):
        AnswerCitation.objects.create(
            query=query, chunk=chunk, chunk_uuid=chunk.id, statement_text=text, position=position
        )
    return query


# --- Reading the route -------------------------------------------------------------------------


def claim_key(text):
    key = settings.SECRET_KEY.encode("utf-8")
    return f"{CLAIM}:{hmac.new(key, text.encode('utf-8'), hashlib.sha256).hexdigest()}"


def passage_key(chunk):
    return f"{PASSAGE}:{chunk.id}"


def focus_on(key):
    node_type, item_id = key.split(":")
    return {"focus_type": node_type, "focus_id": item_id}


def the_map(client, focus=None):
    params = {} if focus is None else focus if isinstance(focus, dict) else focus_on(focus)
    response = client.get(EVIDENCE_URL, params)
    assert response.status_code == 200, response.content
    return response


def logged_in(user):
    client = APIClient()
    client.force_login(user)
    return client


def assert_well_formed(body):
    """What must be true of every view, whatever it holds."""
    assert set(body) == BODY_KEYS
    identifiers = [node["id"] for node in body["nodes"]]
    assert len(identifiers) == len(set(identifiers))
    assert len(identifiers) <= body["maximum_node_count"]
    for node in body["nodes"]:
        assert set(node) == NODE_KEYS
        assert node["type"] in EVIDENCE_MAP_NODE_TYPES
        assert node["id"] == f"{node['type']}:{node['item_id']}"
        assert node["dimension"] is None
        assert set(node["detail"]) == (CLAIM_DETAIL_KEYS if node["type"] == CLAIM else PASSAGE_DETAIL_KEYS)
    touching = dict.fromkeys(identifiers, 0)
    for edge in body["edges"]:
        assert set(edge) == EDGE_KEYS
        assert edge["relationship"] == CITES
        assert edge["source"].startswith(f"{CLAIM}:") and edge["target"].startswith(f"{PASSAGE}:")
        assert edge["source"] in identifiers and edge["target"] in identifiers
        assert edge["weight"] >= 1
        touching[edge["source"]] += 1
        touching[edge["target"]] += 1
    for node in body["nodes"]:
        assert node["connection_count"] == touching[node["id"]]
    assert (body["truncated_by"] is None) == (body["truncated"] is False)


def node_of(body, key):
    found = [node for node in body["nodes"] if node["id"] == key]
    assert len(found) == 1, (key, [node["id"] for node in body["nodes"]])
    return found[0]


def ids_of(body):
    return [node["id"] for node in body["nodes"]]


def edges_of(body):
    return {(edge["source"], edge["target"]): edge["weight"] for edge in body["edges"]}


def stamp(value):
    """The day of a moment as the response writes it: the project's own day, and no time."""
    return timezone.localtime(value).date().isoformat()


@pytest.fixture
def una():
    return person("Una Uploader")


@pytest.fixture
def handbook(una):
    """A document every role reads, with three passages."""
    document = add_document("Staff Handbook", uploader=una)
    return document, [add_chunk(document, index) for index in range(3)]


# --- Who may ask -------------------------------------------------------------------------------


def test_an_anonymous_request_is_401(api_client, handbook, employee):
    _, (first, *_rest) = handbook
    answer(employee, (LEAVE, first))
    for params in ({}, {"focus_type": "bogus"}):
        response = api_client.get(EVIDENCE_URL, params)
        assert response.status_code == 401
        assert LEAVE.encode() not in response.content


def test_a_role_without_view_knowledge_map_is_forbidden(session_client, handbook, employee, administrator):
    """From both roles. Both seeded roles hold the code, so the gate is shown by taking it away
    (D-30's precedent). The 403 carries no claim and comes before the query is read; the role
    that still holds the code is still served."""
    _, (first, *_rest) = handbook
    answer(employee, (LEAVE, first))
    assert LEAVE in the_map(session_client.client).content.decode()
    RolePermission.objects.filter(
        role=session_client.user.role, permission__permission_name=VIEW_KNOWLEDGE_MAP_PERMISSION
    ).delete()

    for params in ({}, focus_on(claim_key(LEAVE)), {"focus_type": "bogus"}):
        response = session_client.client.get(EVIDENCE_URL, params)
        assert response.status_code == 403
        assert response.json() == {
            "detail": "Your role does not hold the 'view_knowledge_map' permission."
        }
        assert LEAVE.encode() not in response.content

    other = administrator if session_client.role_name == EMPLOYEE_ROLE_NAME else employee
    assert LEAVE in the_map(logged_in(other)).content.decode()


# --- What a view holds -------------------------------------------------------------------------


def test_an_empty_log_is_the_empty_body(session_client, handbook):
    """Passages nobody has cited are not on this map: a passage is a node through a claim."""
    assert the_map(session_client.client).json() == EMPTY_BODY


def test_a_claim_is_joined_to_the_passage_it_cites(session_client, handbook, employee):
    document, (first, second, _third) = handbook
    answer(employee, (LEAVE, first), (NOTICE, second), days=5)

    body = the_map(session_client.client).json()

    assert_well_formed(body)
    assert body["focus"] is None and body["truncated"] is False
    # Each claim with its passage, in the order the answer gave them back: one moment, so the
    # identifier decides between the two claims.
    assert set(ids_of(body)) == {
        claim_key(LEAVE), passage_key(first), claim_key(NOTICE), passage_key(second)
    }
    claim = node_of(body, claim_key(LEAVE))
    assert claim["label"] == LEAVE
    assert claim["detail"] == {
        "answer_count": 1,
        "passage_count": 1,
        "first_admitted_at": stamp(at(5)),
        "last_admitted_at": stamp(at(5)),
    }
    passage = node_of(body, passage_key(first))
    assert passage["label"] == "Staff Handbook · passage 1"
    assert passage["detail"] == {
        "source_type": DOCUMENT_SOURCE,
        "source_id": str(document.id),
        "source_title": "Staff Handbook",
        "position": 1,
        "ai_generated": False,
    }
    assert node_of(body, passage_key(second))["detail"]["position"] == 2
    assert edges_of(body) == {
        (claim_key(LEAVE), passage_key(first)): 1,
        (claim_key(NOTICE), passage_key(second)): 1,
    }


def test_one_statement_in_several_answers_is_one_claim_and_its_line_carries_the_count(
    session_client, handbook, employee, administrator
):
    """The same statement admitted three times, once with other spacing, is one claim. The line's
    weight is how often the pairing was admitted, and the dates are the first and the last."""
    _, (first, second, _third) = handbook
    answer(employee, (LEAVE, first), days=10)
    answer(administrator, (f"  Annual leave   is twenty days.\n", first), days=30)
    answer(employee, (LEAVE, second), days=20)

    body = the_map(session_client.client).json()

    assert_well_formed(body)
    # The claim, then its passages in the order their source holds them.
    assert ids_of(body) == [claim_key(LEAVE), passage_key(first), passage_key(second)]
    assert node_of(body, claim_key(LEAVE))["detail"] == {
        "answer_count": 3,
        "passage_count": 2,
        "first_admitted_at": stamp(at(10)),
        "last_admitted_at": stamp(at(30)),
    }
    assert edges_of(body) == {
        (claim_key(LEAVE), passage_key(first)): 2,
        (claim_key(LEAVE), passage_key(second)): 1,
    }


def test_claims_come_newest_first_each_followed_by_its_passages(session_client, handbook, employee):
    _, (first, second, third) = handbook
    answer(employee, (PARKING, third), days=1)
    answer(employee, (LEAVE, second), days=9)
    answer(employee, (NOTICE, first), (NOTICE, second), days=5)

    body = the_map(session_client.client).json()

    assert ids_of(body) == [
        claim_key(LEAVE), passage_key(second),
        claim_key(NOTICE), passage_key(first),
        claim_key(PARKING), passage_key(third),
    ]


def test_a_meetings_passage_names_the_meeting_and_an_ai_written_one_says_so(session_client, employee):
    meeting = add_meeting("Quarterly Review")
    spoken = add_chunk(meeting, 4)
    summary = add_chunk(meeting, 0, ai_generated=True)
    answer(employee, (LEAVE, spoken), (NOTICE, summary))

    body = the_map(session_client.client).json()

    assert node_of(body, passage_key(spoken))["label"] == "Quarterly Review · passage 5"
    assert node_of(body, passage_key(spoken))["detail"] == {
        "source_type": MEETING_SOURCE,
        "source_id": str(meeting.id),
        "source_title": "Quarterly Review",
        "position": 5,
        "ai_generated": False,
    }
    assert node_of(body, passage_key(summary))["detail"]["ai_generated"] is True


def test_nothing_of_the_question_the_asker_or_the_passage_text_is_in_the_bytes(
    session_client, handbook, una
):
    """A claim is a statement and what is counted from its rows. The question, who asked it, the
    whole answer and the passage's text are never selected."""
    asker = person("Quentin Asker")
    _, (first, *_rest) = handbook
    query = answer(asker, (LEAVE, first))

    for focus in (None, claim_key(LEAVE), passage_key(first)):
        content = the_map(session_client.client, focus).content.decode()
        assert LEAVE in content
        for absent in (QUESTION_MARKER, ANSWER_MARKER, PASSAGE_MARKER, "Quentin", "quentin.asker",
                       str(query.id), str(asker.id), "Una", str(una.id)):
            assert absent not in content, absent


def test_an_answers_moment_is_returned_as_the_projects_own_day_and_no_finer(session_client, handbook, employee):
    """The security review's S2, from both roles. Every statement of one answer shares its
    moment, so the moment would tie another person's answer back together. 15:00 UTC on 1 October
    is 01:00 on 2 October in the project's time zone."""
    _, (first, *_rest) = handbook
    answer(employee, (LEAVE, first), when=EARLIEST + timedelta(hours=6))

    response = the_map(session_client.client)

    detail = node_of(response.json(), claim_key(LEAVE))["detail"]
    assert detail["first_admitted_at"] == detail["last_admitted_at"] == "2026-10-02"
    assert "T15:00" not in response.content.decode()


def test_claims_of_one_day_are_ordered_by_identifier_and_not_by_the_moment(session_client, handbook, employee):
    """The order does not give the moment back: six claims minutes apart on one day."""
    _, (first, *_rest) = handbook
    texts = [f"Claim of one day, number {n}." for n in range(6)]
    for n, text in enumerate(texts):
        answer(employee, (text, first), when=EARLIEST + timedelta(minutes=n))

    body = the_map(session_client.client).json()

    claims = [node["id"] for node in body["nodes"] if node["type"] == CLAIM]
    assert claims == sorted(claim_key(text) for text in texts)
    # The premise: that is not the order the moments would give, newest first or oldest.
    by_moment = [claim_key(text) for text in texts]
    assert claims not in (by_moment, by_moment[::-1])


def test_a_claims_identifier_is_keyed_with_the_servers_secret(session_client, handbook, employee, settings):
    """The security review's S4, from both roles. The identifier sits in addresses. Unkeyed, it
    would let anyone who came by one confirm a guessed statement offline."""
    _, (first, *_rest) = handbook
    answer(employee, (LEAVE, first))
    plain = hashlib.sha256(LEAVE.encode("utf-8")).hexdigest()
    client = session_client.client

    [claim] = [node for node in the_map(client).json()["nodes"] if node["type"] == CLAIM]

    assert claim["item_id"] == claim_key(LEAVE).split(":")[1]
    assert claim["item_id"] != plain
    # The unkeyed hash of the text selects nothing.
    assert the_map(client, {"focus_type": CLAIM, "focus_id": plain}).json() == EMPTY_BODY
    # Another key, another identifier, read from the function: a request under a changed key
    # would no longer hold its session.
    before = evidence_map.claim_id(LEAVE)
    settings.SECRET_KEY = "another-key-entirely"
    assert evidence_map.claim_id(LEAVE) != before


# --- Scope: the three rules, each from both roles -----------------------------------------------


def _baseline(client, *focuses):
    """The bytes of the overview and of each selection, before a row the viewer cannot read."""
    return [the_map(client).content, *[the_map(client, focus).content for focus in focuses]]


def test_a_claim_citing_a_passage_the_viewer_cannot_read_is_absent(session_client, handbook, employee, una):
    """Rule 1, from both roles. The bytes are what they were before the row existed: no node, no
    edge, no count and no flag turns on it."""
    _, (first, *_rest) = handbook
    answer(employee, (LEAVE, first))
    client = session_client.client
    before = _baseline(client, claim_key(LEAVE), passage_key(first))

    hidden_document = add_document("Restructure Plan", uploader=una,
                                   roles=unreadable_scope(session_client.role_name))
    hidden = add_chunk(hidden_document)
    # A claim of its own, and the visible claim admitted again from the hidden passage.
    answer(employee, (SECRET, hidden), (LEAVE, hidden), days=50)

    assert _baseline(client, claim_key(LEAVE), passage_key(first)) == before
    for focus in (claim_key(SECRET), passage_key(hidden)):
        assert the_map(client, focus).json() == EMPTY_BODY


def test_a_claim_whose_cited_passage_is_not_among_those_supplied_is_not_read(
    session_client, handbook, employee
):
    """Rule 1 on its own, from both roles. Every passage here is one the viewer reads. One row's
    list of supplied passages does not hold the passage it cites, and another's holds nothing:
    rows no answer path writes. Rule 2 has nothing to refuse in either, so only rule 1 keeps
    them out (the security review's S5)."""
    _, (first, second, third) = handbook
    answer(employee, (LEAVE, first))
    client = session_client.client
    before = _baseline(client, claim_key(LEAVE), passage_key(first))

    answer(employee, (NOTICE, second), supplied=[third], days=50)
    answer(employee, (PARKING, third), supplied=[], days=51)

    assert _baseline(client, claim_key(LEAVE), passage_key(first)) == before
    for focus in (claim_key(NOTICE), claim_key(PARKING), passage_key(second), passage_key(third)):
        assert the_map(client, focus).json() == EMPTY_BODY


def test_a_claim_citing_a_chunk_out_of_scope_is_absent_though_its_row_does_not_list_it(
    session_client, handbook, employee
):
    """Rule 1 again, from both roles, where it matters most. The cited chunk is stamped out of the
    viewer's scope, its source is not, and the row lists only a passage the viewer reads. Rules 2
    and 3 pass. The claim is kept out because its citation is not one of the supplied passages."""
    document, (first, *_rest) = handbook
    answer(employee, (LEAVE, first))
    client = session_client.client
    before = _baseline(client, claim_key(LEAVE), passage_key(first))

    narrowed = add_chunk(document, 7, roles=unreadable_scope(session_client.role_name))
    answer(employee, (SECRET, narrowed), supplied=[first], days=50)

    assert _baseline(client, claim_key(LEAVE), passage_key(first)) == before
    for focus in (claim_key(SECRET), passage_key(narrowed)):
        assert the_map(client, focus).json() == EMPTY_BODY


def test_a_claim_from_an_answer_generated_from_a_passage_the_viewer_cannot_read_is_absent(
    session_client, handbook, employee, una
):
    """Rule 2, from both roles. The statement cites a passage the viewer reads, but the model
    was also given one the viewer does not. What it wrote may carry that passage's content, so
    the claim is not shown, and nothing else moves."""
    _, (first, second, _third) = handbook
    answer(employee, (LEAVE, first))
    client = session_client.client
    before = _baseline(client, claim_key(LEAVE), passage_key(first))

    hidden_document = add_document("Restructure Plan", uploader=una,
                                   roles=unreadable_scope(session_client.role_name))
    hidden = add_chunk(hidden_document)
    # Cites readable passages only. Supplied: those and the hidden one.
    answer(employee, (SECRET, second), (LEAVE, first), supplied=[first, second, hidden], days=50)

    assert _baseline(client, claim_key(LEAVE), passage_key(first)) == before
    for focus in (claim_key(SECRET), passage_key(second)):
        assert the_map(client, focus).json() == EMPTY_BODY


def test_a_supplied_passage_that_no_longer_exists_removes_the_answers_claims(
    session_client, handbook, employee
):
    """Rule 2 fails closed, from both roles: an identifier that names no chunk is not in scope."""
    _, (first, second, _third) = handbook
    answer(employee, (LEAVE, first))
    client = session_client.client
    before = _baseline(client, claim_key(LEAVE))

    answer(employee, (NOTICE, second), supplied=[second, uuid.uuid4()], days=50)

    assert _baseline(client, claim_key(LEAVE)) == before
    assert the_map(client, claim_key(NOTICE)).json() == EMPTY_BODY


def test_a_claim_whose_cited_chunk_was_deleted_is_absent(session_client, handbook, employee):
    """Rule 1, from both roles: the row outlives its chunk (D-67) and is removed for every
    reader. The answer's other statement goes with it, because the deleted chunk was supplied."""
    _, (first, second, third) = handbook
    answer(employee, (LEAVE, first))
    answer(employee, (NOTICE, second), (PARKING, third), days=50)
    client = session_client.client
    assert claim_key(NOTICE) in ids_of(the_map(client).json())

    second.delete()

    body = the_map(client).json()
    assert ids_of(body) == [claim_key(LEAVE), passage_key(first)]
    assert the_map(client, claim_key(NOTICE)).json() == EMPTY_BODY


def test_a_passage_whose_source_the_viewer_cannot_read_shows_nothing(session_client, handbook, employee, una):
    """Rule 3, from both roles. The chunk is stamped for the viewer and its source is not: the
    two disagree, and the passage's title would come from the source. Nothing is shown."""
    _, (first, *_rest) = handbook
    answer(employee, (LEAVE, first))
    client = session_client.client
    before = _baseline(client, claim_key(LEAVE))

    hidden_document = add_document("Restructure Plan", uploader=una,
                                   roles=unreadable_scope(session_client.role_name))
    mismatched = add_chunk(hidden_document, roles=BOTH_ROLES)
    answer(employee, (SECRET, mismatched), days=50)

    assert _baseline(client, claim_key(LEAVE)) == before
    assert b"Restructure Plan" not in the_map(client).content
    for focus in (claim_key(SECRET), passage_key(mismatched)):
        assert the_map(client, focus).json() == EMPTY_BODY


def test_the_administrator_is_shown_the_claim_an_employee_is_not(handbook, employee, administrator, una):
    """The same rows, read by the role they admit: what the Employee half hides is there."""
    _, (first, *_rest) = handbook
    restricted = add_document("Restructure Plan", uploader=una, roles=[ADMINISTRATOR_ROLE_NAME])
    hidden = add_chunk(restricted)
    answer(administrator, (SECRET, hidden), (LEAVE, first))

    for_employee = the_map(logged_in(employee)).json()
    for_administrator = the_map(logged_in(administrator)).json()

    assert for_employee == EMPTY_BODY
    assert set(ids_of(for_administrator)) == {
        claim_key(SECRET), passage_key(hidden), claim_key(LEAVE), passage_key(first)
    }
    assert node_of(for_administrator, passage_key(hidden))["label"] == "Restructure Plan · passage 1"


def test_a_role_change_takes_effect_on_the_next_request(handbook, employee, administrator, employee_role, una):
    """One process serves each role its own view, and a demotion is read on the next request."""
    restricted = add_document("Restructure Plan", uploader=una, roles=[ADMINISTRATOR_ROLE_NAME])
    hidden = add_chunk(restricted)
    answer(administrator, (SECRET, hidden))
    client = logged_in(administrator)
    assert claim_key(SECRET) in ids_of(the_map(client).json())

    administrator.role = employee_role
    administrator.save(update_fields=["role"])

    assert the_map(client).json() == EMPTY_BODY
    assert the_map(client, claim_key(SECRET)).json() == EMPTY_BODY


# --- A selection --------------------------------------------------------------------------------


def test_selecting_a_claim_walks_to_its_passages_and_the_claims_that_share_them(
    session_client, handbook, employee
):
    """Two hops: the claim's passages, then every other claim resting on one of them. A third hop
    is not taken, and the reply says the view stops there."""
    _, (first, second, third) = handbook
    answer(employee, (LEAVE, first), days=1)
    answer(employee, (NOTICE, first), (NOTICE, second), days=2)
    answer(employee, (PARKING, second), (PARKING, third), days=3)

    body = the_map(session_client.client, claim_key(LEAVE)).json()

    assert_well_formed(body)
    assert body["focus"] == {"type": CLAIM, "id": claim_key(LEAVE).split(":")[1]}
    assert ids_of(body) == [claim_key(LEAVE), passage_key(first), claim_key(NOTICE)]
    assert edges_of(body) == {
        (claim_key(LEAVE), passage_key(first)): 1,
        (claim_key(NOTICE), passage_key(first)): 1,
    }
    # NOTICE also cites the second passage, which is three hops from the selection.
    assert (body["truncated"], body["truncated_by"]) == (True, DEPTH)
    # The claim's own figures are of all the viewer's rows, not of this view.
    assert node_of(body, claim_key(NOTICE))["detail"]["passage_count"] == 2
    # One answer cites it twice: it was admitted in one answer, not in two.
    assert node_of(body, claim_key(NOTICE))["detail"]["answer_count"] == 1
    assert node_of(body, claim_key(NOTICE))["connection_count"] == 1


def test_selecting_a_passage_walks_to_the_claims_that_cite_it(session_client, handbook, employee):
    _, (first, second, _third) = handbook
    answer(employee, (LEAVE, first), days=1)
    answer(employee, (NOTICE, first), (NOTICE, second), days=2)

    body = the_map(session_client.client, passage_key(first)).json()

    assert_well_formed(body)
    assert body["focus"] == {"type": PASSAGE, "id": str(first.id)}
    assert ids_of(body) == [passage_key(first), claim_key(NOTICE), claim_key(LEAVE), passage_key(second)]
    assert body["truncated"] is False


def test_every_absent_focus_gets_the_one_empty_body(session_client, handbook, employee, una):
    """A claim nobody made, a passage nobody cited, a chunk that does not exist, and a claim and
    a passage the viewer may not read: one answer, byte for byte, holding nothing that was sent."""
    _, (first, second, _third) = handbook
    answer(employee, (LEAVE, first))
    hidden_document = add_document("Restructure Plan", uploader=una,
                                   roles=unreadable_scope(session_client.role_name))
    hidden = add_chunk(hidden_document)
    answer(employee, (SECRET, hidden))
    client = session_client.client

    replies = [
        the_map(client, focus)
        for focus in (
            claim_key("Nobody ever said this."),
            claim_key(SECRET),
            passage_key(hidden),
            passage_key(second),
            {"focus_type": PASSAGE, "focus_id": str(uuid.uuid4())},
            # A claim's identifier offered as a passage's type cannot be: it is not a UUID, so
            # the nearest well-formed mismatch is a chunk's identifier that is no chunk.
            {"focus_type": PASSAGE, "focus_id": str(uuid.UUID(int=7))},
        )
    ]

    assert all(reply.json() == EMPTY_BODY for reply in replies)
    assert len({reply.content for reply in replies}) == 1


def test_the_focus_is_answered_in_one_spelling(session_client, handbook, employee):
    _, (first, *_rest) = handbook
    answer(employee, (LEAVE, first))
    claim = claim_key(LEAVE).split(":")[1]
    client = session_client.client

    shouted = the_map(client, {"focus_type": CLAIM, "focus_id": claim.upper()})
    unhyphenated = the_map(client, {"focus_type": PASSAGE, "focus_id": first.id.hex.upper()})

    assert shouted.json()["focus"] == {"type": CLAIM, "id": claim}
    assert shouted.content == the_map(client, claim_key(LEAVE)).content
    assert unhyphenated.json()["focus"] == {"type": PASSAGE, "id": str(first.id)}


MALFORMED = {
    "type-without-id": ({"focus_type": CLAIM}, "focus_id", FOCUS_INCOMPLETE_MESSAGE),
    "id-without-type": ({"focus_id": "a" * 64}, "focus_type", FOCUS_INCOMPLETE_MESSAGE),
    "type-with-an-empty-id": ({"focus_type": PASSAGE, "focus_id": ""}, "focus_id", FOCUS_INCOMPLETE_MESSAGE),
    "claim-id-too-short": ({"focus_type": CLAIM, "focus_id": "a" * 63}, "focus_id", EVIDENCE_FOCUS_MALFORMED_MESSAGE),
    "claim-id-not-hexadecimal": ({"focus_type": CLAIM, "focus_id": "g" * 64}, "focus_id", EVIDENCE_FOCUS_MALFORMED_MESSAGE),
    "passage-id-not-a-uuid": ({"focus_type": PASSAGE, "focus_id": "a" * 64}, "focus_id", EVIDENCE_FOCUS_MALFORMED_MESSAGE),
    "passage-id-a-word": ({"focus_type": PASSAGE, "focus_id": "first"}, "focus_id", EVIDENCE_FOCUS_MALFORMED_MESSAGE),
}


@pytest.mark.parametrize("case", MALFORMED, ids=list(MALFORMED))
def test_a_malformed_query_is_400_keyed_on_its_parameter(session_client, handbook, employee, case):
    """From both roles. Shape only: nothing about what exists decides a status code (D-65)."""
    _, (first, *_rest) = handbook
    answer(employee, (LEAVE, first))
    params, field, message = MALFORMED[case]

    response = session_client.client.get(EVIDENCE_URL, params)

    assert response.status_code == 400
    assert response.json() == {field: [message]}


@pytest.mark.parametrize("params", [
    {"focus_type": "document", "focus_id": str(uuid.UUID(int=1))},
    {"focus_type": "Passage", "focus_id": str(uuid.UUID(int=1))},
    {"focus_type": CLAIM, "focus_id": "a" * 65},
], ids=["type-of-the-first-view", "type-in-the-wrong-case", "id-too-long"])
def test_a_value_outside_the_vocabulary_or_the_length_is_400(session_client, params):
    response = session_client.client.get(EVIDENCE_URL, params)

    assert response.status_code == 400
    assert set(response.json()) <= {"focus_type", "focus_id"}


def test_two_empty_parameters_are_the_overview(session_client, handbook, employee):
    _, (first, *_rest) = handbook
    answer(employee, (LEAVE, first))
    client = session_client.client

    assert client.get(EVIDENCE_URL, {"focus_type": "", "focus_id": ""}).content == the_map(client).content


# --- The caps ----------------------------------------------------------------------------------


def test_the_overview_is_cut_at_the_node_cap_and_says_so(session_client, handbook, employee, monkeypatch):
    """The first view's cap and its reason, read where this module reads them."""
    _, (first, second, third) = handbook
    answer(employee, (LEAVE, first), days=3)
    answer(employee, (NOTICE, second), days=2)
    answer(employee, (PARKING, third), days=1)
    monkeypatch.setattr(evidence_map, "MAXIMUM_NODE_COUNT", 4)

    body = the_map(session_client.client).json()

    assert_well_formed(body)
    assert ids_of(body) == [claim_key(LEAVE), passage_key(first), claim_key(NOTICE), passage_key(second)]
    assert (body["truncated"], body["truncated_by"], body["maximum_node_count"]) == (True, NODE_COUNT, 4)


def test_a_view_exactly_at_the_cap_is_not_cut_by_rows_the_viewer_cannot_read(
    session_client, handbook, employee, una, monkeypatch
):
    """Scope before the cap, from both roles: a newer claim the viewer may not read takes no
    place under the cap and raises no flag. The newer claims cite passages the viewer reads and
    were generated from one the viewer does not, so rule 2 alone keeps them out."""
    _, (first, second, _third) = handbook
    answer(employee, (LEAVE, first), days=3)
    answer(employee, (NOTICE, second), days=2)
    monkeypatch.setattr(evidence_map, "MAXIMUM_NODE_COUNT", 4)
    client = session_client.client
    before = the_map(client).content
    assert the_map(client).json()["truncated"] is False

    hidden_document = add_document("Restructure Plan", uploader=una,
                                   roles=unreadable_scope(session_client.role_name))
    hidden = add_chunk(hidden_document)
    for minute, chunk in enumerate([first, second, first]):
        answer(employee, (f"{SECRET} {minute}", chunk), supplied=[chunk, hidden], days=60 + minute)

    assert the_map(client).content == before


def test_the_depth_cap_is_read_where_the_module_reads_it(session_client, handbook, employee, monkeypatch):
    _, (first, _second, _third) = handbook
    answer(employee, (LEAVE, first), days=1)
    answer(employee, (NOTICE, first), days=2)
    monkeypatch.setattr(evidence_map, "MAXIMUM_TRAVERSAL_DEPTH", 1)

    body = the_map(session_client.client, claim_key(LEAVE)).json()

    assert ids_of(body) == [claim_key(LEAVE), passage_key(first)]
    assert (body["truncated"], body["truncated_by"], body["maximum_traversal_depth"]) == (True, DEPTH, 1)


# --- The rate limit (D-138, the user's decision of 17 November 2026) ----------------------------

FIRST_VIEW_URL = "/api/knowledge-map"
MAP_LIMIT = int(KNOWLEDGE_MAP_THROTTLE_RATE.split("/")[0])


@pytest.mark.parametrize("url", [EVIDENCE_URL, FIRST_VIEW_URL], ids=["second-view", "first-view"])
def test_each_view_is_limited_for_each_user_in_one_budget_for_the_two(
    session_client, employee, administrator, url
):
    """From both roles, at the real rate. Past it the reply is DRF's 429 with ``Retry-After``. The
    two views share the budget, and it is each user's own."""
    client = session_client.client
    for _ in range(MAP_LIMIT):
        assert client.get(url).status_code == 200

    refused = client.get(url)

    assert refused.status_code == 429
    assert int(refused["Retry-After"]) > 0
    other_view = FIRST_VIEW_URL if url == EVIDENCE_URL else EVIDENCE_URL
    assert client.get(other_view).status_code == 429
    other = administrator if session_client.role_name == EMPLOYEE_ROLE_NAME else employee
    assert logged_in(other).get(url).status_code == 200


# --- Cost, writes, and what the module may read -------------------------------------------------

WRITES = ("INSERT", "UPDATE", "DELETE")
TABLES_READ = ('"answer_citations"', '"query_log"', '"content_chunks"', '"documents"', '"meetings"')


def statements_of(client, params):
    with CaptureQueriesContext(connection) as captured:
        response = client.get(EVIDENCE_URL, params)
    return response, [query["sql"] for query in captured.captured_queries]


@pytest.mark.parametrize("selected", ["overview", "selection"])
def test_the_route_writes_nothing_and_its_statements_do_not_grow_with_the_log(
    session_client, handbook, employee, selected
):
    """From both roles. The route's own code runs SELECT statements only; the one write is the
    session row (FR-04's sliding expiry). Three answers cost what thirty do."""
    _, chunks = handbook
    for n in range(3):
        answer(employee, (f"Claim number {n}.", chunks[n % 3]), days=n)
    params = {} if selected == "overview" else focus_on(claim_key("Claim number 0."))
    client = session_client.client
    the_map(client, params)  # the first request of a session, set aside

    response, few = statements_of(client, params)
    assert response.status_code == 200 and response.json()["nodes"]
    for statement in few:
        if statement.lstrip().upper().startswith(WRITES):
            assert "django_session" in statement, statement
    joined = "\n".join(few)
    for table in TABLES_READ:
        assert table in joined, table

    for n in range(3, 30):
        answer(employee, (f"Claim number {n}.", chunks[n % 3]), days=n)

    response, many = statements_of(client, params)
    assert len(response.json()["nodes"]) > 3
    assert len(many) == len(few)


def test_the_same_request_gives_the_same_bytes(session_client, handbook, employee):
    _, (first, second, _third) = handbook
    answer(employee, (LEAVE, first), (NOTICE, second))
    answer(employee, (PARKING, second), days=4)
    # Eight claims of one moment on one passage: an order that was not fixed would have to
    # fall the same way twice among them.
    answer(employee, *[(f"Claim of one moment, number {n}.", first) for n in range(8)], days=9)
    client = session_client.client

    for focus in (None, claim_key(LEAVE), passage_key(second)):
        assert the_map(client, focus).content == the_map(client, focus).content


def test_the_module_selects_eight_columns_and_reads_sources_through_the_scoped_helpers():
    """Read from the module's source. The citation rows are the one query written here, and it
    selects exactly these columns: no question, no asker, no answer text and no passage text.
    Chunks, documents and meetings are reached through the three scoped helpers and no manager."""
    source = inspect.getsource(evidence_map)
    tree = ast.parse(source)

    selected = [
        [argument.value for argument in call.args]
        for call in ast.walk(tree)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
        and call.func.attr == "values_list"
    ]
    assert [
        "statement_text", "chunk_id", "chunk__source_type", "chunk__source_id",
        "chunk__chunk_index", "chunk__ai_generated", "query_id", "query__answered_at",
    ] in selected
    assert sorted(selected, key=len)[:2] == [["id", "title"], ["id", "title"]] and len(selected) == 3

    managers = {
        node.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "objects" and isinstance(node.value, ast.Name)
    }
    assert managers == {"AnswerCitation"}
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"scoped_chunks", "scoped_documents", "scoped_meetings"} <= called
