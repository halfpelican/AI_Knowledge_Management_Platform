"""FR-20's knowledge map: ``GET /api/knowledge-map`` (docs/decisions.md D-132).

The contract is docs/api-contract.md, FR-20. The route returns the documents, meetings, tags and
contributors the caller's role may see, the relationships between them, and whether the view was
cut short by one of two caps. What this file defends, in the order the tests come:

1. **Invariants 1 and 3.** A source outside the caller's scope is absent, and so is everything
   known only through it: a tag only it carries, a person who only uploaded or attended it, its
   edges, and its share of a shared tag's or person's connection count. The caps come after the
   scope, so restricted rows move neither which nodes are returned nor ``truncated``. Attendance
   is a participation record and admits no meeting.
2. **The clauses.** The response's shape, the two caps and the reason reported for each, the
   orders, de-duplication, the empty map, and the 401, 403 and 400.

**Both roles.** Every test runs from an Employee and an Administrator session: through
``session_client``, where the row the caller may not read is stamped by
``apps/retrieval/tests/scopes.py`` (an Administrator reads everything but ``[]`` since D-66), or
as an Employee's absence beside the Administrator's presence, so a map returning nothing to
anybody cannot pass.

**Leakage is asserted against ``response.content``,** the raw bytes: a key nobody anticipated is
where a restricted title would turn up. Every body read through ``graph`` is also held to the
rules that must be true of any view (``assert_well_formed``): each edge joins two returned nodes
and each count is the number of returned edges touching its node.

**Timestamps are set, never left to the clock.** ``auto_now_add`` ignores a value passed to
``create()``, so ``uploaded_at`` and ``created_at`` are written with a queryset ``.update()``. On
this Windows machine rows made in one test can share a clock tick, so no order here relies on
creation order.

**The caps are patched where the module reads them** (``apps.api.knowledge_map``), so a cap test
builds six rows and not fifty. The tests that need the real values say so.
"""

import ast
import inspect
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import RolePermission
from apps.api import knowledge_map
from apps.api.knowledge_map import Edge, contributor_node, source_node, tag_node, walk
from apps.api.serializers import FOCUS_INCOMPLETE_MESSAGE
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    DOCUMENT_EXTRACTION_FAILED,
    DOCUMENT_INDEXED,
    EMPLOYEE_ROLE_NAME,
    KNOWLEDGE_MAP_NODE_TYPES,
    KNOWLEDGE_MAP_RELATIONSHIPS,
    KNOWLEDGE_MAP_TRUNCATION_REASONS,
    MAXIMUM_NODE_COUNT,
    MAXIMUM_TRAVERSAL_DEPTH,
    MEETING_INDEXED,
    MEETING_PROCESSING_FAILED,
    SOURCE_TYPES,
    VIEW_KNOWLEDGE_MAP_PERMISSION,
)
from apps.documents.models import ContentTag, Document, Tag
from apps.meetings.models import Meeting, MeetingAttendee
from apps.retrieval.tests.scopes import unreadable_scope

pytestmark = pytest.mark.django_db

User = get_user_model()

MAP_URL = "/api/knowledge-map"
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]
DOCUMENT, MEETING, TAG, CONTRIBUTOR = KNOWLEDGE_MAP_NODE_TYPES
TAGGED, UPLOADED, ATTENDED = KNOWLEDGE_MAP_RELATIONSHIPS
NODE_COUNT, DEPTH = KNOWLEDGE_MAP_TRUNCATION_REASONS
DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES

BODY_KEYS = {
    "focus", "nodes", "edges", "truncated", "truncated_by", "maximum_node_count",
    "maximum_traversal_depth",
}
NODE_KEYS = {"id", "type", "item_id", "label", "dimension", "connection_count"}
EDGE_KEYS = {"source", "target", "relationship"}

# The one body every "nothing to show" case gets: an empty database, a role with nothing in
# scope, and a focus that is not in the caller's graph for any reason (UC-11 E1). Written out, not
# derived from a response, so that all of those are compared with one literal.
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


def at(minutes):
    """A moment ``minutes`` after the earliest row: a higher number is a newer source."""
    return EARLIEST + timedelta(minutes=minutes)


# --- Row builders ----------------------------------------------------------------------------


def person(name, *, role=None):
    """A registered user with no usable password: a contributor, never a session."""
    address = f"{name.lower().replace(' ', '.')}@people.example"
    return User.objects.create_user(address, None, name=name, role=role)


def add_document(title, *, uploader, roles=None, added=None, status=DOCUMENT_INDEXED):
    document = Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=uploader,
        status=status,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )
    if added is not None:
        # auto_now_add ignores a value given to create(); update() writes it.
        Document.objects.filter(pk=document.pk).update(uploaded_at=added)
    return document


def add_meeting(title, *, roles=None, added=None, status=MEETING_INDEXED):
    meeting = Meeting.objects.create(
        title=title,
        meeting_date=EARLIEST.date(),
        # A phrase no test's title or name contains, so the bytes can be searched for it.
        transcript_text=f"TRANSCRIPT-BODY of {title}.",
        status=status,
        visible_to_roles=BOTH_ROLES if roles is None else roles,
    )
    if added is not None:
        Meeting.objects.filter(pk=meeting.pk).update(created_at=added)
    return meeting


def link(tag_row, source_type, source_id, **flags):
    flags.setdefault("applied_by", "user")
    flags.setdefault("confirmed", True)
    return ContentTag.objects.create(
        tag=tag_row, source_type=source_type, source_id=source_id, **flags
    )


def tag(source, dimension, name, **flags):
    """Link ``source``, a document or a meeting, to the tag ``name`` in ``dimension``."""
    tag_row, _ = Tag.objects.get_or_create(tag_name=name, dimension=dimension)
    source_type = MEETING_SOURCE_TYPE if isinstance(source, Meeting) else DOCUMENT_SOURCE_TYPE
    link(tag_row, source_type, source.id, **flags)
    return tag_row


def attend(meeting, *users):
    for user in users:
        MeetingAttendee.objects.create(meeting=meeting, user=user)


# --- Reading the route -------------------------------------------------------------------------


def key(row):
    """The node identifier the response gives ``row``."""
    node_type = {Document: DOCUMENT, Meeting: MEETING, Tag: TAG}.get(type(row), CONTRIBUTOR)
    return f"{node_type}:{row.id}"


def focus_on(row):
    node_type, item_id = key(row).split(":")
    return {"focus_type": node_type, "focus_id": item_id}


def the_map(client, focus=None):
    """The response to the overview, or to a selection of ``focus`` (a row, or a params dict)."""
    params = {} if focus is None else focus if isinstance(focus, dict) else focus_on(focus)
    response = client.get(MAP_URL, params)
    assert response.status_code == 200, response.content
    return response


def assert_well_formed(body):
    """What must be true of every view, whatever it holds."""
    assert set(body) == BODY_KEYS
    identifiers = [node["id"] for node in body["nodes"]]
    assert len(identifiers) == len(set(identifiers))
    assert len(identifiers) <= body["maximum_node_count"]
    for node in body["nodes"]:
        assert set(node) == NODE_KEYS
        assert node["type"] in KNOWLEDGE_MAP_NODE_TYPES
        assert node["id"] == f"{node['type']}:{node['item_id']}"
        assert (node["dimension"] is not None) == (node["type"] == TAG)
    touching = Counter()
    seen = set()
    for edge in body["edges"]:
        assert set(edge) == EDGE_KEYS
        assert edge["relationship"] in KNOWLEDGE_MAP_RELATIONSHIPS
        # Both ends are returned nodes: no edge points at something the view does not hold.
        assert edge["source"] in identifiers and edge["target"] in identifiers
        triple = (edge["source"], edge["target"], edge["relationship"])
        assert triple not in seen
        seen.add(triple)
        touching[edge["source"]] += 1
        touching[edge["target"]] += 1
    # Counts are taken last, over the edges this view returns.
    for node in body["nodes"]:
        assert node["connection_count"] == touching[node["id"]]
    assert (body["truncated_by"] is None) == (body["truncated"] is False)
    assert body["truncated_by"] in (None, *KNOWLEDGE_MAP_TRUNCATION_REASONS)
    if body["focus"] is not None:
        first = body["nodes"][0]
        assert body["focus"] == {"type": first["type"], "id": first["item_id"]}


def graph(client, focus=None):
    body = the_map(client, focus).json()
    assert_well_formed(body)
    return body


def node_ids(body):
    return [node["id"] for node in body["nodes"]]


def counts(body):
    return {node["id"]: node["connection_count"] for node in body["nodes"]}


def edges(body):
    return [(edge["source"], edge["target"], edge["relationship"]) for edge in body["edges"]]


def cap_nodes_at(monkeypatch, count):
    """Patch the node cap where the module reads it, as the route does on every request."""
    monkeypatch.setattr(knowledge_map, "MAXIMUM_NODE_COUNT", count)


def logged_in(user):
    client = APIClient()
    client.force_login(user)
    return client


# --- A two-level corpus ------------------------------------------------------------------------
#
# The restricted half carries one of everything that could leak: a source of each type, a tag
# only it carries, a person who only uploaded it and one who only attended it, AND a tag and a
# person it shares with the readable half, whose counts would each rise by exactly its share.

VISIBLE_DOCUMENT = "Leave policy 2026"
VISIBLE_MEETING = "Quarterly planning sync"
RESTRICTED_DOCUMENT = "Board remuneration review"
SECOND_RESTRICTED_DOCUMENT = "Chair succession shortlist"
RESTRICTED_MEETING = "Board in-camera session"
SHARED_TOPIC = "people matters"
VISIBLE_PROJECT = "atlas"
SEALED_TOPIC = "executive pay"
SEALED_PROCESS = "director appointments"
SHARED_PERSON = "Una Uploader"
RESTRICTED_UPLOADER = "Rex Sealed"
RESTRICTED_ATTENDEE = "Ravi Closed"


@dataclass
class Visible:
    person: object
    document: Document
    meeting: Meeting
    topic: Tag
    project: Tag

    @property
    def node_ids(self):
        return {key(row) for row in (self.person, self.document, self.meeting, self.topic, self.project)}

    @property
    def edges(self):
        return {
            (key(self.person), key(self.document), UPLOADED),
            (key(self.person), key(self.meeting), ATTENDED),
            (key(self.document), key(self.topic), TAGGED),
            (key(self.document), key(self.project), TAGGED),
            (key(self.meeting), key(self.topic), TAGGED),
            (key(self.meeting), key(self.project), TAGGED),
        }


@dataclass
class Restricted:
    document: Document
    second_document: Document
    meeting: Meeting
    topic: Tag
    process: Tag
    uploader: object
    attendee: object

    @property
    def traces(self):
        """Everything an out-of-scope reader's bytes must not carry: titles, names, identifiers."""
        rows = (self.document, self.second_document, self.meeting, self.topic, self.process,
                self.uploader, self.attendee)
        return (
            RESTRICTED_DOCUMENT, SECOND_RESTRICTED_DOCUMENT, RESTRICTED_MEETING, SEALED_TOPIC,
            SEALED_PROCESS, RESTRICTED_UPLOADER, RESTRICTED_ATTENDEE,
            *(str(row.id) for row in rows),
        )


def build_visible():
    """The readable half. Every node is within two hops of every other, so a selection of any of
    them returns the whole half and nothing is past the depth cap."""
    shared = person(SHARED_PERSON)
    document = add_document(VISIBLE_DOCUMENT, uploader=shared, added=at(10))
    meeting = add_meeting(VISIBLE_MEETING, added=at(20))
    attend(meeting, shared)
    topic = tag(document, "Topic", SHARED_TOPIC)
    tag(meeting, "Topic", SHARED_TOPIC)
    project = tag(document, "Project", VISIBLE_PROJECT)
    tag(meeting, "Project", VISIBLE_PROJECT)
    return Visible(person=shared, document=document, meeting=meeting, topic=topic, project=project)


def add_restricted(visible, scope):
    """The restricted half, every row NEWER than the readable ones, so a leak would lead a list."""
    uploader = person(RESTRICTED_UPLOADER)
    attendee = person(RESTRICTED_ATTENDEE)
    document = add_document(RESTRICTED_DOCUMENT, uploader=visible.person, roles=scope, added=at(30))
    second = add_document(SECOND_RESTRICTED_DOCUMENT, uploader=uploader, roles=scope, added=at(40))
    meeting = add_meeting(RESTRICTED_MEETING, roles=scope, added=at(50))
    attend(meeting, visible.person, attendee)
    tag(document, "Topic", SHARED_TOPIC)
    topic = tag(document, "Topic", SEALED_TOPIC)
    process = tag(meeting, "Process", SEALED_PROCESS)
    return Restricted(document=document, second_document=second, meeting=meeting, topic=topic,
                      process=process, uploader=uploader, attendee=attendee)


def selections(visible):
    """The overview and one selection of each node type in the readable half."""
    return [None, visible.document, visible.meeting, visible.topic, visible.project, visible.person]


# --- 1 to 4. A restricted source, and everything known only through it, is absent --------------


def test_a_restricted_source_and_what_only_it_carries_are_absent(session_client):
    """Items 1 to 3, from both roles. The restricted half is stamped with a scope this role may not
    read. Its titles, its own tags and people and every identifier are nowhere in the bytes, its
    edges are gone, and the shared tag and the shared person count only the readable half."""
    visible = build_visible()
    restricted = add_restricted(visible, unreadable_scope(session_client.role_name))

    for selection in selections(visible):
        response = the_map(session_client.client, selection)
        raw = response.content.decode()
        for trace in restricted.traces:
            assert trace not in raw, (selection, trace)
        body = response.json()
        assert_well_formed(body)
        # The presence beside the absence, so an empty map cannot pass: the whole readable half.
        assert set(node_ids(body)) == visible.node_ids
        assert set(edges(body)) == visible.edges
        # The shared tag is on two readable sources and one restricted; the shared person
        # uploaded or attended two readable sources and two restricted. Each counts two.
        assert counts(body)[key(visible.topic)] == 2
        assert counts(body)[key(visible.person)] == 2
        assert body["truncated"] is False


def test_the_administrator_is_shown_what_the_employee_is_not(employee_client, administrator_client):
    """The mirror of the test above. The same rows, stamped for the Administrator alone: absent
    from the Employee's bytes, and all of them in the Administrator's, where the shared tag's and
    the shared person's counts rise by exactly the restricted half's share."""
    visible = build_visible()
    restricted = add_restricted(visible, ADMINISTRATOR_ONLY)

    employee_raw = the_map(employee_client).content.decode()
    for trace in restricted.traces:
        assert trace not in employee_raw, trace
    employee_body = graph(employee_client)
    assert counts(employee_body)[key(visible.topic)] == 2
    assert counts(employee_body)[key(visible.person)] == 2

    administrator_raw = the_map(administrator_client).content.decode()
    for trace in restricted.traces:
        assert trace in administrator_raw, trace
    administrator_body = graph(administrator_client)
    assert counts(administrator_body)[key(visible.topic)] == 3  # + the restricted document
    assert counts(administrator_body)[key(visible.person)] == 4  # + one upload, one attendance
    assert set(edges(administrator_body)) == visible.edges | {
        (key(visible.person), key(restricted.document), UPLOADED),
        (key(restricted.uploader), key(restricted.second_document), UPLOADED),
        (key(visible.person), key(restricted.meeting), ATTENDED),
        (key(restricted.attendee), key(restricted.meeting), ATTENDED),
        (key(restricted.document), key(visible.topic), TAGGED),
        (key(restricted.document), key(restricted.topic), TAGGED),
        (key(restricted.meeting), key(restricted.process), TAGGED),
    }


@pytest.mark.parametrize("selected", ["overview", "document", "meeting", "topic", "person"])
def test_an_employees_bytes_are_identical_with_and_without_restricted_rows(
    employee_client, administrator_client, selected
):
    """Item 4: invariant 1 as one assertion. Nothing in the Employee's bytes moves when restricted
    rows arrive, for the overview and for a selection of each kind; the Administrator's do move."""
    visible = build_visible()
    selection = None if selected == "overview" else getattr(visible, selected)

    employee_before = the_map(employee_client, selection).content
    administrator_before = the_map(administrator_client, selection).content
    assert VISIBLE_DOCUMENT.encode() in employee_before  # not an empty map either side

    add_restricted(visible, ADMINISTRATOR_ONLY)

    assert the_map(employee_client, selection).content == employee_before
    assert the_map(administrator_client, selection).content != administrator_before


# --- 5 and 6. The node cap comes after the scope: the overview ---------------------------------


def test_an_overview_over_the_cap_is_not_moved_by_restricted_rows_of_any_age(
    employee_client, administrator_client, monkeypatch
):
    """Item 5. The readable sources alone are over the cap. Restricted sources are then added
    NEWER than every readable one, between them and older, sharing their tags and their uploader.
    A cap or a limit applied before the scope would let the newer ones take places; the
    Employee's bytes do not change."""
    cap_nodes_at(monkeypatch, 6)
    una = person("Una Uploader")
    first = add_document("Readable one", uploader=una, added=at(40))
    second = add_document("Readable two", uploader=una, added=at(30))
    third = add_document("Readable three", uploader=una, added=at(20))
    fourth = add_document("Readable four", uploader=una, added=at(10))
    one = tag(first, "Topic", "t-one")
    two = tag(second, "Topic", "t-two")
    tag(third, "Topic", "t-three")
    tag(fourth, "Topic", "t-one")

    employee_before = the_map(employee_client).content
    administrator_before = the_map(administrator_client).content
    body = graph(employee_client)
    # The premise: the cap binds on readable rows alone. The third does not fit (it would make
    # seven) and is skipped; the fourth, older and smaller, still does.
    assert node_ids(body) == [key(first), key(one), key(una), key(second), key(two), key(fourth)]
    assert (body["truncated"], body["truncated_by"]) == (True, NODE_COUNT)

    newer = add_document("Sealed newer", uploader=una, roles=ADMINISTRATOR_ONLY, added=at(50))
    between = add_document("Sealed between", uploader=una, roles=ADMINISTRATOR_ONLY, added=at(25))
    older = add_document("Sealed older", uploader=una, roles=ADMINISTRATOR_ONLY, added=at(5))
    tag(newer, "Topic", "t-one")
    tag(newer, "Topic", "t-three")
    tag(between, "Topic", "t-two")
    tag(older, "Topic", "t-three")

    assert the_map(employee_client).content == employee_before
    # The mirror: the same rows do change what the Administrator, whom they admit, is shown.
    administrator_after = the_map(administrator_client)
    assert administrator_after.content != administrator_before
    assert key(newer) in node_ids(administrator_after.json())


def test_an_overview_exactly_at_the_cap_is_not_truncated_by_restricted_rows(
    employee_client, administrator_client, monkeypatch
):
    """Item 6. The readable map is exactly the cap, so ``truncated`` is false. A restricted source
    then makes the Administrator's map one too many, and the Employee's flag does not move."""
    cap_nodes_at(monkeypatch, 6)
    una = person("Una Uploader")
    first = add_document("Readable one", uploader=una, added=at(30))
    second = add_document("Readable two", uploader=una, added=at(20))
    add_document("Readable three", uploader=una, added=at(10))
    tag(first, "Topic", "t-one")
    tag(second, "Topic", "t-two")

    for client in (employee_client, administrator_client):
        body = graph(client)
        assert len(body["nodes"]) == 6  # the premise: exactly at the cap
        assert (body["truncated"], body["truncated_by"]) == (False, None)
    employee_before = the_map(employee_client).content

    sealed = add_document("Sealed newest", uploader=una, roles=ADMINISTRATOR_ONLY, added=at(40))
    tag(sealed, "Topic", "t-one")

    assert the_map(employee_client).content == employee_before
    assert graph(employee_client)["truncated"] is False
    administrator_body = graph(administrator_client)
    assert (administrator_body["truncated"], administrator_body["truncated_by"]) == (True, NODE_COUNT)


# --- 7 to 9. The caps come after the scope: a selection ----------------------------------------


def test_a_selections_depth_flag_is_not_raised_by_restricted_material(
    employee_client, administrator_client
):
    """Item 7, with the real caps. A readable document shares its tag and its uploader with an
    Administrator-only document that carries a second tag, three hops away. For the Employee
    nothing lies beyond the second hop, so the view is complete; a flag read from an unscoped
    count of links would say otherwise. For the Administrator the document is returned and its
    second tag is past the depth cap."""
    una = person("Una Uploader")
    readable = add_document("Readable one", uploader=una, added=at(10))
    shared = tag(readable, "Topic", "t-one")
    before = the_map(employee_client, readable).content

    sealed = add_document("Sealed one", uploader=una, roles=ADMINISTRATOR_ONLY, added=at(20))
    tag(sealed, "Topic", "t-one")
    beyond = tag(sealed, "Topic", "t-two")

    assert the_map(employee_client, readable).content == before
    employee_body = graph(employee_client, readable)
    assert node_ids(employee_body) == [key(readable), key(shared), key(una)]
    assert (employee_body["truncated"], employee_body["truncated_by"]) == (False, None)

    administrator_body = graph(administrator_client, readable)
    assert node_ids(administrator_body) == [key(readable), key(shared), key(una), key(sealed)]
    assert key(beyond) not in node_ids(administrator_body)
    assert (administrator_body["truncated"], administrator_body["truncated_by"]) == (True, DEPTH)


def test_a_selection_exactly_at_the_cap_is_not_truncated_by_restricted_rows(
    employee_client, administrator_client, monkeypatch
):
    """Item 8. A tag's readable walk is exactly the cap with nothing beyond it. Restricted
    documents carrying the tag are added: the Employee's body does not change and is not
    truncated, and the Administrator's ring is cut at the cap."""
    cap_nodes_at(monkeypatch, 4)
    una = person("Una Uploader")
    newer = add_document("Readable newer", uploader=una, added=at(20))
    older = add_document("Readable older", uploader=una, added=at(10))
    shared = tag(newer, "Topic", "t-one")
    tag(older, "Topic", "t-one")

    before = the_map(employee_client, shared).content
    body = graph(employee_client, shared)
    assert node_ids(body) == [key(shared), key(newer), key(older), key(una)]  # exactly the cap
    assert (body["truncated"], body["truncated_by"]) == (False, None)

    sealed = [
        add_document(f"Sealed {n}", uploader=una, roles=ADMINISTRATOR_ONLY, added=at(30 + n))
        for n in range(2)
    ]
    for document in sealed:
        tag(document, "Topic", "t-one")

    assert the_map(employee_client, shared).content == before
    administrator_body = graph(administrator_client, shared)
    assert node_ids(administrator_body) == [key(shared), key(sealed[1]), key(sealed[0]), key(newer)]
    assert (administrator_body["truncated"], administrator_body["truncated_by"]) == (True, NODE_COUNT)


# --- 5 to 8 again, with each role as the one denied ---------------------------------------------
#
# The four tests above deny the Employee and mirror on the Administrator. The requirements audit
# of 15 November 2026 (finding A7) asked for the Administrator as the denied role at a cap that
# binds too. These run as each role, with the added rows stamped for no role that viewer's scope
# reaches, so there is no mirror to assert: the viewer's own bytes must not change.


def test_an_overview_over_the_cap_is_not_moved_by_rows_the_viewer_cannot_read(
    session_client, monkeypatch
):
    """Item 5, as each role: the cap binds on readable rows alone, and unreadable sources newer
    than, between and older than them, sharing their tags and their uploader, change nothing."""
    cap_nodes_at(monkeypatch, 6)
    hidden = unreadable_scope(session_client.role_name)
    una = person("Una Uploader")
    first = add_document("Readable one", uploader=una, added=at(40))
    second = add_document("Readable two", uploader=una, added=at(30))
    third = add_document("Readable three", uploader=una, added=at(20))
    fourth = add_document("Readable four", uploader=una, added=at(10))
    one = tag(first, "Topic", "t-one")
    two = tag(second, "Topic", "t-two")
    tag(third, "Topic", "t-three")
    tag(fourth, "Topic", "t-one")

    before = the_map(session_client.client).content
    body = graph(session_client.client)
    assert node_ids(body) == [key(first), key(one), key(una), key(second), key(two), key(fourth)]
    assert (body["truncated"], body["truncated_by"]) == (True, NODE_COUNT)

    newer = add_document("Sealed newer", uploader=una, roles=hidden, added=at(50))
    between = add_document("Sealed between", uploader=una, roles=hidden, added=at(25))
    older = add_document("Sealed older", uploader=una, roles=hidden, added=at(5))
    tag(newer, "Topic", "t-one")
    tag(newer, "Topic", "t-three")
    tag(between, "Topic", "t-two")
    tag(older, "Topic", "t-three")

    assert the_map(session_client.client).content == before


def test_an_overview_exactly_at_the_cap_is_not_truncated_by_rows_the_viewer_cannot_read(
    session_client, monkeypatch
):
    """Item 6, as each role: the readable map is exactly the cap, and a newer unreadable source
    sharing a tag and the uploader does not raise the flag."""
    cap_nodes_at(monkeypatch, 6)
    hidden = unreadable_scope(session_client.role_name)
    una = person("Una Uploader")
    first = add_document("Readable one", uploader=una, added=at(30))
    second = add_document("Readable two", uploader=una, added=at(20))
    add_document("Readable three", uploader=una, added=at(10))
    tag(first, "Topic", "t-one")
    tag(second, "Topic", "t-two")

    body = graph(session_client.client)
    assert len(body["nodes"]) == 6  # the premise: exactly at the cap
    assert (body["truncated"], body["truncated_by"]) == (False, None)
    before = the_map(session_client.client).content

    sealed = add_document("Sealed newest", uploader=una, roles=hidden, added=at(40))
    tag(sealed, "Topic", "t-one")

    assert the_map(session_client.client).content == before
    assert graph(session_client.client)["truncated"] is False


def test_a_selections_depth_flag_is_not_raised_by_material_the_viewer_cannot_read(session_client):
    """Item 7, as each role, with the real caps: an unreadable document shares the readable one's
    tag and uploader and carries a second tag three hops away. Nothing the viewer may read lies
    beyond the second hop, so the view is complete."""
    hidden = unreadable_scope(session_client.role_name)
    una = person("Una Uploader")
    readable = add_document("Readable one", uploader=una, added=at(10))
    shared = tag(readable, "Topic", "t-one")
    before = the_map(session_client.client, readable).content

    sealed = add_document("Sealed one", uploader=una, roles=hidden, added=at(20))
    tag(sealed, "Topic", "t-one")
    tag(sealed, "Topic", "t-two")

    assert the_map(session_client.client, readable).content == before
    body = graph(session_client.client, readable)
    assert node_ids(body) == [key(readable), key(shared), key(una)]
    assert (body["truncated"], body["truncated_by"]) == (False, None)


def test_a_selection_exactly_at_the_cap_is_not_truncated_by_rows_the_viewer_cannot_read(
    session_client, monkeypatch
):
    """Item 8, as each role: a tag's readable walk is exactly the cap with nothing beyond it, and
    newer unreadable documents carrying the tag neither take a place nor raise the flag."""
    cap_nodes_at(monkeypatch, 4)
    hidden = unreadable_scope(session_client.role_name)
    una = person("Una Uploader")
    newer = add_document("Readable newer", uploader=una, added=at(20))
    older = add_document("Readable older", uploader=una, added=at(10))
    shared = tag(newer, "Topic", "t-one")
    tag(older, "Topic", "t-one")

    before = the_map(session_client.client, shared).content
    body = graph(session_client.client, shared)
    assert node_ids(body) == [key(shared), key(newer), key(older), key(una)]  # exactly the cap
    assert (body["truncated"], body["truncated_by"]) == (False, None)

    for n in range(2):
        sealed = add_document(f"Sealed {n}", uploader=una, roles=hidden, added=at(30 + n))
        tag(sealed, "Topic", "t-one")

    assert the_map(session_client.client, shared).content == before


def test_the_walk_does_not_pass_through_a_restricted_node(session_client):
    """Item 9, from both roles. A shared tag is not a way to a restricted document's other tags
    or to its uploader, and a shared person is not a way to a restricted meeting's other
    attendees: the second hop starts only from nodes that were returned."""
    hidden = unreadable_scope(session_client.role_name)
    una = person("Una Uploader")
    other = person("Olga Other")
    readable = add_document("Readable one", uploader=una, added=at(10))
    shared = tag(readable, "Topic", "t-one")
    sealed = add_document("Sealed one", uploader=other, roles=hidden, added=at(20))
    tag(sealed, "Topic", "t-one")
    far_tag = tag(sealed, "Project", "sealed project")
    sealed_meeting = add_meeting("Sealed meeting", roles=hidden, added=at(30))
    attend(sealed_meeting, una, other)

    for selection in (shared, una, readable):
        response = the_map(session_client.client, selection)
        raw = response.content.decode()
        for trace in ("Sealed one", "Sealed meeting", "sealed project", "Olga Other",
                      str(sealed.id), str(sealed_meeting.id), str(far_tag.id), str(other.id)):
            assert trace not in raw, (selection, trace)
        body = response.json()
        assert_well_formed(body)
        assert set(node_ids(body)) == {key(readable), key(shared), key(una)}
        assert body["truncated"] is False


def test_the_administrator_walks_through_the_same_nodes_an_employee_cannot(
    employee_client, administrator_client
):
    """The mirror of the test above: stamped for the Administrator, the same document is walked
    through, and its other tag and its uploader are reached from the shared tag."""
    una = person("Una Uploader")
    other = person("Olga Other")
    readable = add_document("Readable one", uploader=una, added=at(10))
    shared = tag(readable, "Topic", "t-one")
    sealed = add_document("Sealed one", uploader=other, roles=ADMINISTRATOR_ONLY, added=at(20))
    tag(sealed, "Topic", "t-one")
    far_tag = tag(sealed, "Project", "sealed project")

    assert set(node_ids(graph(employee_client, shared))) == {key(shared), key(readable), key(una)}
    assert node_ids(graph(administrator_client, shared)) == [
        key(shared), key(sealed), key(readable), key(far_tag), key(other), key(una),
    ]


# --- 10. A focus that is not in the caller's graph: one answer, at one cost ---------------------


@dataclass
class Probes:
    visible: Visible
    restricted: Restricted
    by_cause: dict


def build_probes(scope):
    """The readable half, the restricted half, and one focus for each reason a focus can be
    absent from the caller's graph."""
    visible = build_visible()
    restricted = add_restricted(visible, scope)
    vocabulary = Tag.objects.create(tag_name="unused vocabulary", dimension="Topic")
    retired = Tag.objects.create(tag_name="retired elsewhere", dimension="Process", active=False)
    link(retired, DOCUMENT_SOURCE_TYPE, restricted.document.id)
    by_cause = {
        "an unknown id": {"focus_type": DOCUMENT, "focus_id": str(uuid.uuid4())},
        "a restricted source": focus_on(restricted.document),
        "a restricted-only tag": focus_on(restricted.topic),
        "a vocabulary tag with no link": focus_on(vocabulary),
        "a retired tag with no in-scope link": focus_on(retired),
        "a person with only restricted contributions": focus_on(restricted.uploader),
        # A readable meeting's identifier, sent as a document's: the type and the id do not match.
        "a type that does not match its id": {
            "focus_type": DOCUMENT, "focus_id": str(visible.meeting.id),
        },
    }
    return Probes(visible=visible, restricted=restricted, by_cause=by_cause)


def statements_of(client, params):
    with CaptureQueriesContext(connection) as captured:
        response = client.get(MAP_URL, params)
    return response, [query["sql"] for query in captured.captured_queries]


def is_the_sessions(statement):
    """Whether a statement belongs to the session row and not to the route.

    FR-04's sliding expiry saves the session on every request, with a new expiry each time, so
    its statements differ between two identical requests. Inside a test's transaction that save
    is wrapped in a savepoint whose name is numbered, which differs too.
    """
    return "django_session" in statement or "SAVEPOINT" in statement


def test_every_absent_focus_gets_the_literal_empty_body_from_identical_statements(session_client):
    """Item 10, from both roles. Unknown, restricted, known only through restricted material,
    never linked, or mismatched: each gets the body an empty map gets, which holds nothing the
    caller sent. The statements each request runs are the same list, because the focus is looked
    up in the assembled graph and is no statement's parameter; a lookup keyed on it would cost
    more for a tag restricted material carries than for an identifier that names nothing."""
    probes = build_probes(unreadable_scope(session_client.role_name))
    client = session_client.client
    # Not an empty map for this caller: a selection of a readable node returns it.
    assert node_ids(graph(client, probes.visible.document))[0] == key(probes.visible.document)

    statements = {}
    for cause, params in probes.by_cause.items():
        response, sql = statements_of(client, params)
        assert response.status_code == 200, cause
        assert response.json() == EMPTY_BODY, cause
        assert response.content == the_map(client, probes.by_cause["an unknown id"]).content, cause
        # The session's statements are counted and the route's own are compared as text.
        statements[cause] = (
            [text for text in sql if not is_the_sessions(text)],
            sum(is_the_sessions(text) for text in sql),
        )
        requested = uuid.UUID(params["focus_id"])
        for text in sql:
            if not is_the_sessions(text):
                assert str(requested) not in text and requested.hex not in text, (cause, text)

    reference = statements["an unknown id"]
    assert reference[0], "the route ran no statement of its own, so the comparison proves nothing"
    for cause, captured in statements.items():
        assert captured == reference, cause


def test_the_same_focuses_are_answered_for_the_administrator_they_admit(
    employee_client, administrator_client
):
    """The mirror of the test above, so that an empty answer for everybody cannot pass: stamped
    for the Administrator, the restricted source, its tag and its uploader are each returned to
    the Administrator as the focus, and are the empty body for the Employee."""
    probes = build_probes(ADMINISTRATOR_ONLY)
    for row in (probes.restricted.document, probes.restricted.topic, probes.restricted.uploader):
        assert the_map(employee_client, row).json() == EMPTY_BODY
        body = graph(administrator_client, row)
        assert node_ids(body)[0] == key(row)
        assert body["focus"] == {"type": key(row).split(":")[0], "id": str(row.id)}
    # A tag nothing links to, and an identifier that names nothing, are nobody's node.
    for cause in ("an unknown id", "a vocabulary tag with no link", "a type that does not match its id"):
        assert the_map(administrator_client, probes.by_cause[cause]).json() == EMPTY_BODY


# --- 11. Attendance is a participation record, never access (invariant 3) -----------------------


def test_the_viewers_own_attendance_of_a_restricted_meeting_admits_nothing(session_client):
    """Item 11, from both roles. The viewer is recorded as an attendee of a meeting their role
    may not read. The meeting is not in their map, and their own node counts only the document
    they uploaded."""
    viewer = session_client.user
    document = add_document("Readable one", uploader=viewer, added=at(10))
    sealed = add_meeting("Sealed meeting", roles=unreadable_scope(session_client.role_name), added=at(20))
    colleague = person("Cora Colleague")
    attend(sealed, viewer, colleague)
    tag(sealed, "Topic", "sealed topic")

    for selection in (None, viewer, document):
        response = the_map(session_client.client, selection)
        raw = response.content.decode()
        for trace in ("Sealed meeting", str(sealed.id), "Cora Colleague", str(colleague.id),
                      "sealed topic", ATTENDED):
            assert trace not in raw, (selection, trace)
        body = response.json()
        assert_well_formed(body)
        assert set(node_ids(body)) == {key(document), key(viewer)}
        assert counts(body)[key(viewer)] == 1
    assert the_map(session_client.client, sealed).json() == EMPTY_BODY


def test_an_employees_attendance_shows_only_to_a_role_that_reads_the_meeting(
    employee, employee_client, administrator_client
):
    """The mirror: the Administrator, whom the meeting admits, sees the Employee's attendance of
    it, and the Employee does not."""
    document = add_document("Readable one", uploader=employee, added=at(10))
    sealed = add_meeting("Sealed meeting", roles=ADMINISTRATOR_ONLY, added=at(20))
    attend(sealed, employee)

    assert counts(graph(employee_client))[key(employee)] == 1
    administrator_body = graph(administrator_client)
    assert (key(employee), key(sealed), ATTENDED) in edges(administrator_body)
    assert counts(administrator_body)[key(employee)] == 2
    assert key(document) in node_ids(administrator_body)


# --- 12. Nothing is kept between requests, and the role is read on each -------------------------


@pytest.mark.parametrize("selected", ["overview", "topic", "person"])
def test_one_process_serves_each_role_its_own_map_and_a_demotion_takes_effect_at_once(
    employee_client, administrator_client, administrator, employee_role, selected
):
    """Item 12. The Administrator asks first, then the Employee, in this one process: a graph
    kept from the first request would be served to the second. Then the Administrator is made an
    Employee, and the same session's next response is the Employee's, byte for byte."""
    visible = build_visible()
    restricted = add_restricted(visible, ADMINISTRATOR_ONLY)
    selection = None if selected == "overview" else getattr(visible, selected)

    administrator_first = the_map(administrator_client, selection).content.decode()
    assert RESTRICTED_DOCUMENT in administrator_first  # the Administrator's map was built
    employee_response = the_map(employee_client, selection)
    for trace in restricted.traces:
        assert trace not in employee_response.content.decode(), trace

    administrator.role = employee_role
    administrator.save(update_fields=["role"])

    # Same session cookie, no re-login: the scope is re-read from the users table per request.
    assert the_map(administrator_client, selection).content == employee_response.content


# --- 13 and 14. Which links are edges -----------------------------------------------------------


def test_a_tag_whose_only_readable_link_is_removed_or_provisional_is_not_a_node(
    employee_client, administrator_client
):
    """Item 13. Each tag is live on an Administrator-only document, and on the readable document
    only as a link a person removed, or as a suggestion still held. Neither is a tag of the
    readable document (FR-15's rule), so for the Employee neither is a node, by name or by id.
    The Administrator sees each through the restricted document alone."""
    una = person("Una Uploader")
    readable = add_document("Readable one", uploader=una, added=at(10))
    live = tag(readable, "Topic", "live topic")
    sealed = add_document("Sealed one", uploader=una, roles=ADMINISTRATOR_ONLY, added=at(20))
    removed = tag(sealed, "Topic", "removed here")
    held = tag(sealed, "Project", "held here")
    link(removed, DOCUMENT_SOURCE_TYPE, readable.id, removed=True)
    link(held, DOCUMENT_SOURCE_TYPE, readable.id, applied_by="ai", confirmed=False,
         provisional=True, confidence="0.400")

    for selection in (None, readable, removed, held):
        raw = the_map(employee_client, selection).content.decode()
        for trace in ("removed here", "held here", str(removed.id), str(held.id)):
            assert trace not in raw, (selection, trace)
    employee_body = graph(employee_client)
    assert set(node_ids(employee_body)) == {key(readable), key(live), key(una)}

    administrator_body = graph(administrator_client)
    assert {key(removed), key(held)} <= set(node_ids(administrator_body))
    # One edge each, to the restricted document: the readable document's links draw nothing.
    assert counts(administrator_body)[key(removed)] == 1
    assert counts(administrator_body)[key(held)] == 1
    assert (key(readable), key(removed), TAGGED) not in edges(administrator_body)
    assert (key(readable), key(held), TAGGED) not in edges(administrator_body)


def test_a_link_is_matched_on_its_source_type_and_identifier_together(session_client):
    """Item 14, from both roles. ``source_id`` is a bare UUID (D-07), so a meeting link can carry
    a readable document's identifier and a document link a readable meeting's: neither draws an
    edge. A meeting link is honoured through a meeting in scope and through no other. A
    Department-dimension link is neither a node nor an edge: Department is a column (D-72)."""
    hidden = unreadable_scope(session_client.role_name)
    una = person("Una Uploader")
    document = add_document("Readable one", uploader=una, added=at(10))
    meeting = add_meeting("Readable meeting", added=at(20))
    sealed_meeting = add_meeting("Sealed meeting", roles=hidden, added=at(30))

    crossed = Tag.objects.create(tag_name="crossed to a document", dimension="Topic")
    link(crossed, MEETING_SOURCE_TYPE, document.id)
    crossed_back = Tag.objects.create(tag_name="crossed to a meeting", dimension="Topic")
    link(crossed_back, DOCUMENT_SOURCE_TYPE, meeting.id)
    on_meeting = tag(meeting, "Topic", "meeting topic")
    on_sealed = tag(sealed_meeting, "Topic", "sealed meeting topic")
    department = tag(document, "Department", "finance department")

    response = the_map(session_client.client)
    raw = response.content.decode()
    for trace in ("crossed to a document", "crossed to a meeting", "sealed meeting topic",
                  "finance department", str(crossed.id), str(crossed_back.id), str(on_sealed.id),
                  str(department.id)):
        assert trace not in raw, trace
    body = response.json()
    assert_well_formed(body)
    assert edges(body) == [
        (key(meeting), key(on_meeting), TAGGED),
        (key(una), key(document), UPLOADED),
    ]
    for absent in (crossed, crossed_back, on_sealed, department):
        assert the_map(session_client.client, absent).json() == EMPTY_BODY


# --- 15 and 16. What a node carries, and what the module may read -------------------------------


def test_a_contributor_is_a_name_and_an_identifier_and_nothing_else(
    session_client, administrator_role
):
    """Item 15, from both roles: the user's choice "Contributor nodes" (D-132). A contributor's
    email and role are nowhere in the bytes, for an uploader who is an Administrator and an
    attendee who is an Employee. A transcript is not there either."""
    uploader = person("Una Uploader", role=administrator_role)
    attendee = person("Otto Attendee")
    document = add_document("Readable one", uploader=uploader, added=at(10))
    meeting = add_meeting("Readable meeting", added=at(20))
    attend(meeting, attendee)

    for selection in (None, uploader, attendee, document, meeting):
        response = the_map(session_client.client, selection)
        raw = response.content.decode()
        for trace in (uploader.email, attendee.email, "@", EMPLOYEE_ROLE_NAME,
                      ADMINISTRATOR_ROLE_NAME, "TRANSCRIPT-BODY", session_client.user.email):
            assert trace not in raw, (selection, trace)
    by_id = {node["id"]: node for node in graph(session_client.client)["nodes"]}
    assert by_id[key(uploader)] == {
        "id": key(uploader), "type": CONTRIBUTOR, "item_id": str(uploader.id),
        "label": "Una Uploader", "dimension": None, "connection_count": 1,
    }
    assert by_id[key(attendee)]["label"] == "Otto Attendee"


def _code_of(function_or_module):
    """The syntax tree of a module or function with its docstrings removed, so that prose naming
    what the code must not do is not mistaken for the code doing it."""
    tree = ast.parse(inspect.getsource(function_or_module))
    for holder in ast.walk(tree):
        if isinstance(holder, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(holder):
            holder.body = holder.body[1:]
    return tree


def _identifiers(tree):
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    return names, attributes, imported, strings


MANAGER_ATTRIBUTES = {"objects", "_default_manager", "_base_manager"}
# The reverse relations from a user or a tag to its sources: each reaches every source the
# person or tag is linked to, with the caller's scope nowhere in the path.
REVERSE_RELATIONS = {"uploaded_documents", "meeting_attendances", "content_tags"}


def test_the_module_reads_no_tag_table_no_user_table_and_no_reverse_relation():
    """Item 16. The D-53 scan covers the Document, Meeting and ContentChunk managers only, so this
    holds the module to the rest: the one manager it reads is ``MeetingAttendee``'s, narrowed to
    scoped meetings, and tag links come through ``repository.live_tag_links``. A focus label
    fetched with ``Tag.objects.filter(pk=...)`` or a user's ``uploaded_documents`` would pass that
    scan and fail here."""
    tree = _code_of(knowledge_map)
    names, attributes, imported, strings = _identifiers(tree)

    managers_read = {
        node.value.id for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in MANAGER_ATTRIBUTES
        and isinstance(node.value, ast.Name)
    }
    assert managers_read == {"MeetingAttendee"}
    assert attributes & MANAGER_ATTRIBUTES == {"objects"}  # and that one read is the only one

    forbidden_names = {"Tag", "ContentTag", "User", "get_user_model", "settings", "Document",
                       "Meeting", "ContentChunk"}
    assert (names | imported) & forbidden_names == set()
    assert {"scoped_documents", "scoped_meetings", "live_tag_links"} <= imported

    assert attributes & REVERSE_RELATIONS == set()
    for text in strings:
        assert set(text.split("__")) & REVERSE_RELATIONS == set(), text
    # Never selected: a transcript, extracted text, a file, an email or a role.
    selected = {part for text in strings for part in text.split("__")}
    assert selected & {"transcript_text", "extracted_text", "file_path", "email", "role",
                       "role_name", "active", "grown", "applied_by", "confidence",
                       "confirmed"} == set()


def test_the_assembly_takes_no_focus_and_the_walk_touches_no_database(django_assert_num_queries):
    """The two-part structure, held: ``assemble`` is given the role and nothing else, so no
    statement can take the focus as a parameter, and ``walk`` and its helpers name nothing that
    reads the database and run no statement."""
    assert list(inspect.signature(knowledge_map.assemble).parameters) == ["role_name"]

    database_names = {"MeetingAttendee", "scoped_documents", "scoped_meetings", "live_tag_links",
                      "assemble"}
    queryset_methods = {"objects", "filter", "values_list", "values", "distinct", "exclude"}
    for function in (knowledge_map.walk, knowledge_map._overview, knowledge_map._rings,
                     knowledge_map._body):
        names, attributes, _, _ = _identifiers(_code_of(function))
        assert names & database_names == set(), function.__name__
        assert attributes & queryset_methods == set(), function.__name__

    document = source_node(DOCUMENT, uuid.uuid4(), "A", at(10))
    topic = tag_node(uuid.uuid4(), "t", "Topic")
    who = contributor_node(uuid.uuid4(), "Una")
    joins = [Edge(document.id, topic.id, TAGGED), Edge(who.id, document.id, UPLOADED)]
    with django_assert_num_queries(0):
        overview = walk([document, topic, who], joins, None, maximum_node_count=50,
                        maximum_traversal_depth=2)
        absent = walk([document, topic, who], joins, f"{MEETING}:{document.item_id}",
                      maximum_node_count=50, maximum_traversal_depth=2)
    assert node_ids(overview) == [document.id, topic.id, who.id]
    assert absent == EMPTY_BODY


# --- 17. The response contract ------------------------------------------------------------------


def test_the_body_has_exactly_the_contracts_keys_and_the_two_maximums(session_client):
    """Item 17, from both roles: seven keys, six on every node, three on every edge, and the two
    maximums equal to the constants, so the page needs no literal 50 or 2."""
    visible = build_visible()

    body = the_map(session_client.client).json()

    assert set(body) == BODY_KEYS
    assert all(set(node) == NODE_KEYS for node in body["nodes"])
    assert all(set(edge) == EDGE_KEYS for edge in body["edges"])
    assert body["maximum_node_count"] == MAXIMUM_NODE_COUNT == 50
    assert body["maximum_traversal_depth"] == MAXIMUM_TRAVERSAL_DEPTH == 2
    assert body["focus"] is None
    by_id = {node["id"]: node for node in body["nodes"]}
    assert by_id[key(visible.document)] == {
        "id": f"document:{visible.document.id}", "type": "document",
        "item_id": str(visible.document.id), "label": VISIBLE_DOCUMENT, "dimension": None,
        "connection_count": 3,
    }
    assert by_id[key(visible.meeting)]["label"] == VISIBLE_MEETING
    assert by_id[key(visible.topic)] == {
        "id": f"tag:{visible.topic.id}", "type": "tag", "item_id": str(visible.topic.id),
        "label": SHARED_TOPIC, "dimension": "Topic", "connection_count": 2,
    }
    assert {edge["relationship"] for edge in body["edges"]} == {"tagged", "uploaded", "attended"}


def test_the_focus_is_the_returned_node_in_its_canonical_form(session_client):
    """Item 17. ``focus`` is null for the overview and for a focus that is not returned. For one
    that is, it is the node's own type and identifier, however the caller spelt the identifier."""
    visible = build_visible()
    client = session_client.client
    canonical = {"type": DOCUMENT, "id": str(visible.document.id)}

    spellings = [
        str(visible.document.id),
        str(visible.document.id).upper(),
        visible.document.id.hex,
        "{%s}" % visible.document.id,
    ]
    bodies = [
        graph(client, {"focus_type": DOCUMENT, "focus_id": spelling}) for spelling in spellings
    ]
    for body in bodies:
        assert body["focus"] == canonical
        assert body["nodes"][0]["id"] == key(visible.document)
        assert body == bodies[0]

    assert graph(client)["focus"] is None
    absent = the_map(client, {"focus_type": DOCUMENT, "focus_id": str(uuid.uuid4())}).json()
    assert absent["focus"] is None


def test_the_same_request_gives_the_same_bytes(session_client):
    """Item 17: nodes come in walk order and edges in the order of their ends, so two requests
    for one view are byte for byte the same."""
    visible = build_visible()
    for selection in selections(visible):
        first = the_map(session_client.client, selection).content
        assert the_map(session_client.client, selection).content == first


# --- 18. The node cap on the overview -----------------------------------------------------------


def test_the_overview_returns_at_most_the_real_node_cap(session_client):
    """Item 18, with the real cap. Thirty documents, each with a tag of its own and one shared
    uploader, are sixty-one nodes. The newest twenty-four fit (forty-nine nodes); the next would
    make fifty-one, so it and the rest are left out and the view says the count is why."""
    una = person("Una Uploader")
    documents = [add_document(f"Paper {n:02d}", uploader=una, added=at(n)) for n in range(30)]
    for n, document in enumerate(documents):
        tag(document, "Topic", f"topic {n:02d}")

    body = graph(session_client.client)

    assert len(body["nodes"]) == 49 <= MAXIMUM_NODE_COUNT
    returned = [node["label"] for node in body["nodes"] if node["type"] == DOCUMENT]
    assert returned == [f"Paper {n:02d}" for n in range(29, 5, -1)]  # newest first
    assert (body["truncated"], body["truncated_by"]) == (True, NODE_COUNT)


def _heavily_tagged(title, uploader, added, tags=60):
    """A document with ``tags`` Topic tags: with itself and its uploader, more than the cap."""
    document = add_document(title, uploader=uploader, added=added)
    rows = Tag.objects.bulk_create(
        [Tag(tag_name=f"heavy topic {n:02d}", dimension="Topic") for n in range(tags)]
    )
    ContentTag.objects.bulk_create([
        ContentTag(tag=row, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.id,
                   applied_by="user", confirmed=True)
        for row in rows
    ])
    return document, rows


def test_a_source_that_does_not_fit_is_skipped_and_older_smaller_ones_still_appear(session_client):
    """Item 18, with the real cap: the design review's F4. A document with sixty tags is newer
    than three small ones. It can never fit, so it is skipped, and the walk carries on: the three
    older documents are in the overview, which says it is cut by the count."""
    una = person("Una Uploader")
    heavy, heavy_tags = _heavily_tagged("Heavily tagged", una, at(40))
    small = [add_document(f"Small {n}", uploader=una, added=at(10 + n)) for n in range(3)]
    small_tags = [tag(document, "Topic", f"small topic {n}") for n, document in enumerate(small)]

    body = graph(session_client.client)

    assert node_ids(body) == [
        key(small[2]), key(small_tags[2]), key(una),
        key(small[1]), key(small_tags[1]),
        key(small[0]), key(small_tags[0]),
    ]
    assert key(heavy) not in node_ids(body)
    assert (body["truncated"], body["truncated_by"]) == (True, NODE_COUNT)
    # It is reached by selecting one of its connections, cut at the cap in its turn.
    selected = graph(session_client.client, heavy_tags[0])
    assert node_ids(selected)[:2] == [key(heavy_tags[0]), key(heavy)]


def test_when_no_source_fits_the_newest_is_returned_with_as_many_neighbours_as_fit(session_client):
    """Item 18's corner, with the real cap. The only source has sixty tags and an uploader. An
    empty map would say there is nothing to see, so it is returned with forty-nine neighbours,
    tags before contributors, and the count is the reason."""
    una = person("Una Uploader")
    heavy, heavy_tags = _heavily_tagged("Heavily tagged", una, at(40))

    body = graph(session_client.client)

    assert len(body["nodes"]) == MAXIMUM_NODE_COUNT
    assert node_ids(body) == [key(heavy), *(key(row) for row in heavy_tags[:49])]
    assert key(una) not in node_ids(body)
    assert counts(body)[key(heavy)] == 49
    assert (body["truncated"], body["truncated_by"]) == (True, NODE_COUNT)


# --- 19 and 20. The caps on a selection ----------------------------------------------------------


def test_a_ring_is_cut_at_the_node_cap_and_the_count_is_the_reason(session_client, monkeypatch):
    """Item 19. A tag on three documents, with the cap at three: the tag and the two newest
    documents are returned, the oldest is left out by the count, and the tag counts the two
    connections shown."""
    cap_nodes_at(monkeypatch, 3)
    una = person("Una Uploader")
    documents = [add_document(f"Paper {n}", uploader=una, added=at(10 * n)) for n in range(3)]
    shared = None
    for document in documents:
        shared = tag(document, "Topic", "t-one")

    body = graph(session_client.client, shared)

    assert node_ids(body) == [key(shared), key(documents[2]), key(documents[1])]
    assert counts(body)[key(shared)] == 2
    assert (body["truncated"], body["truncated_by"], body["maximum_node_count"]) == (True, NODE_COUNT, 3)


def test_a_first_ring_that_fills_the_cap_leaves_the_second_out_by_count(session_client, monkeypatch):
    """Item 19. The first ring ends exactly at the cap and a second ring exists, within the depth
    cap: its nodes were left out because the count was reached, so the reason is the count."""
    cap_nodes_at(monkeypatch, 3)
    una = person("Una Uploader")
    documents = [add_document(f"Paper {n}", uploader=una, added=at(10 * n)) for n in range(2)]
    shared = None
    for document in documents:
        shared = tag(document, "Topic", "t-one")

    body = graph(session_client.client, shared)

    assert node_ids(body) == [key(shared), key(documents[1]), key(documents[0])]
    assert key(una) not in node_ids(body)
    assert (body["truncated"], body["truncated_by"]) == (True, NODE_COUNT)


def test_a_walk_that_ends_at_exactly_the_cap_with_more_beyond_reports_depth(
    session_client, monkeypatch
):
    """Item 19. The second ring ends at exactly the cap and nothing within two hops was refused,
    while a last-ring document carries a tag three hops out. No node was left out for want of
    room, so the reason is the depth, not the count."""
    cap_nodes_at(monkeypatch, 4)
    una = person("Una Uploader")
    first = add_document("Paper one", uploader=una, added=at(20))
    second = add_document("Paper two", uploader=una, added=at(10))
    shared = tag(first, "Topic", "t-one")
    tag(second, "Topic", "t-one")
    beyond = tag(second, "Topic", "t-two")

    body = graph(session_client.client, first)

    assert node_ids(body) == [key(first), key(shared), key(una), key(second)]
    assert len(body["nodes"]) == body["maximum_node_count"] == 4
    assert key(beyond) not in node_ids(body)
    assert (body["truncated"], body["truncated_by"]) == (True, DEPTH)


def test_a_node_three_hops_from_the_selection_is_absent_and_depth_is_the_reason(session_client):
    """Item 20, with the real caps. Document, tag, document, tag: the second tag is three hops
    from the first document and is not returned. From the shared tag it is two hops and is."""
    first = add_document("Paper one", uploader=session_client.user, added=at(20))
    second = add_document("Paper two", uploader=session_client.user, added=at(10))
    shared = tag(first, "Topic", "t-one")
    tag(second, "Topic", "t-one")
    far = tag(second, "Topic", "t-two")
    client = session_client.client

    body = graph(client, first)
    assert key(far) not in node_ids(body)
    assert key(second) in node_ids(body)
    assert (body["truncated"], body["truncated_by"]) == (True, DEPTH)
    assert body["maximum_traversal_depth"] == 2

    from_the_tag = graph(client, shared)
    assert key(far) in node_ids(from_the_tag)
    assert (from_the_tag["truncated"], from_the_tag["truncated_by"]) == (False, None)


def test_the_depth_cap_is_read_where_the_module_reads_it(session_client, monkeypatch):
    """The depth the walk takes is the constant, not a literal two: at one hop the neighbours'
    neighbours are left out, and the body reports the depth it used."""
    monkeypatch.setattr(knowledge_map, "MAXIMUM_TRAVERSAL_DEPTH", 1)
    first = add_document("Paper one", uploader=session_client.user, added=at(20))
    second = add_document("Paper two", uploader=session_client.user, added=at(10))
    shared = tag(first, "Topic", "t-one")
    tag(second, "Topic", "t-one")

    body = graph(session_client.client, first)

    assert node_ids(body) == [key(first), key(shared), key(session_client.user)]
    assert (body["truncated"], body["truncated_by"], body["maximum_traversal_depth"]) == (True, DEPTH, 1)


# --- 21. The orders -----------------------------------------------------------------------------


@dataclass
class Ordered:
    adam: object
    bea: object
    meeting: Meeting
    middle: Document
    ties: list
    oldest: Document
    alpha: Tag
    beta: Tag
    mid: Tag
    zeta: Tag


def build_ordered():
    """Rows whose stable orders differ from their creation order and from a naive sort.

    "adam Lower" sorts before "Bea Upper" only without regard to case. Process "mid" and Project
    "zeta" sort before Topic "alpha" only because the dimension comes first. The two tied
    documents share one timestamp, so the identifier decides. Everything is created oldest last.
    """
    bea = person("Bea Upper")
    adam = person("adam Lower")
    oldest = add_document("Oldest paper", uploader=adam, added=at(10))
    ties = sorted(
        (add_document(f"Tied paper {n}", uploader=adam, added=at(20)) for n in range(2)),
        key=lambda document: str(document.id),
    )
    middle = add_document("Middle paper", uploader=bea, added=at(30))
    meeting = add_meeting("Newest meeting", added=at(40))
    attend(meeting, bea, adam)
    zeta = tag(middle, "Project", "zeta")
    alpha = tag(middle, "Topic", "alpha")
    mid = tag(middle, "Process", "mid")
    tag(meeting, "Topic", "alpha")
    beta = tag(oldest, "Topic", "beta")
    return Ordered(adam=adam, bea=bea, meeting=meeting, middle=middle, ties=ties, oldest=oldest,
                   alpha=alpha, beta=beta, mid=mid, zeta=zeta)


def test_the_overview_is_in_walk_order_and_its_edges_in_the_order_of_their_ends(session_client):
    """Item 21. Sources newest first, documents and meetings as one list, the identifier breaking
    a tie; each source followed by its not-yet-included tags (dimension, then name) and then its
    contributors (name, without regard to case). Edges by their source's place, then their
    target's."""
    rows = build_ordered()

    body = graph(session_client.client)

    assert node_ids(body) == [
        key(rows.meeting), key(rows.alpha), key(rows.adam), key(rows.bea),
        key(rows.middle), key(rows.mid), key(rows.zeta),
        key(rows.ties[0]), key(rows.ties[1]),
        key(rows.oldest), key(rows.beta),
    ]
    assert edges(body) == [
        (key(rows.meeting), key(rows.alpha), TAGGED),
        (key(rows.adam), key(rows.meeting), ATTENDED),
        (key(rows.adam), key(rows.ties[0]), UPLOADED),
        (key(rows.adam), key(rows.ties[1]), UPLOADED),
        (key(rows.adam), key(rows.oldest), UPLOADED),
        (key(rows.bea), key(rows.meeting), ATTENDED),
        (key(rows.bea), key(rows.middle), UPLOADED),
        (key(rows.middle), key(rows.alpha), TAGGED),
        (key(rows.middle), key(rows.mid), TAGGED),
        (key(rows.middle), key(rows.zeta), TAGGED),
        (key(rows.oldest), key(rows.beta), TAGGED),
    ]
    assert body["truncated"] is False


def test_each_ring_of_a_selection_is_ordered_as_a_whole(session_client):
    """Item 21. A ring is one list: sources, then tags, then contributors, each in its stable
    order. It is not grouped by the node of the ring before that reached it."""
    rows = build_ordered()
    client = session_client.client

    from_adam = graph(client, rows.adam)
    assert node_ids(from_adam) == [
        key(rows.adam),
        # Ring 1, all sources: newest first, the tie by identifier.
        key(rows.meeting), key(rows.ties[0]), key(rows.ties[1]), key(rows.oldest),
        # Ring 2 as a whole: both tags, then the person. Grouped by parent, the meeting's person
        # would come before the oldest paper's tag.
        key(rows.alpha), key(rows.beta), key(rows.bea),
    ]
    # The middle paper is three hops from adam, through the tag or through Bea.
    assert (from_adam["truncated"], from_adam["truncated_by"]) == (True, DEPTH)

    from_alpha = graph(client, rows.alpha)
    assert node_ids(from_alpha) == [
        key(rows.alpha),
        key(rows.meeting), key(rows.middle),
        key(rows.mid), key(rows.zeta), key(rows.adam), key(rows.bea),
    ]


# --- 22 and 23. Edges, nodes and counts ---------------------------------------------------------


def test_duplicate_link_rows_are_one_edge(session_client):
    """Item 22. Neither link table is unique on its pair: a document linked twice to one tag, and
    a person recorded twice on one meeting, are one edge each and count once."""
    una = person("Una Uploader")
    document = add_document("Paper one", uploader=una, added=at(10))
    twice = tag(document, "Topic", "t-one")
    link(twice, DOCUMENT_SOURCE_TYPE, document.id, applied_by="ai", confirmed=False)
    # A live link beside a removed one to the same tag is still an edge.
    link(twice, DOCUMENT_SOURCE_TYPE, document.id, removed=True)
    meeting = add_meeting("Meeting one", added=at(20))
    attend(meeting, una, una)

    body = graph(session_client.client)

    assert sorted(edges(body)) == sorted([
        (key(document), key(twice), TAGGED),
        (key(una), key(document), UPLOADED),
        (key(una), key(meeting), ATTENDED),
    ])
    assert counts(body) == {key(document): 2, key(twice): 1, key(una): 2, key(meeting): 1}


def test_a_retired_tag_two_dimensions_of_one_name_and_a_failed_source_are_nodes(session_client):
    """Item 22. ``Tag.active`` is not consulted, as FR-15 does not consult it: a retired tag
    still linked is a node. A name is unique only within a dimension, so one name in two
    dimensions is two nodes. Sources in every status are nodes, as the lists show them."""
    una = person("Una Uploader")
    failed = add_document("Unreadable scan", uploader=una, added=at(10),
                          status=DOCUMENT_EXTRACTION_FAILED)
    failed_meeting = add_meeting("Broken transcript", added=at(20), status=MEETING_PROCESSING_FAILED)
    retired = tag(failed, "Topic", "retired but linked")
    Tag.objects.filter(pk=retired.pk).update(active=False, grown=True)
    as_topic = tag(failed, "Topic", "finance")
    as_process = tag(failed, "Process", "finance")

    body = graph(session_client.client)

    by_id = {node["id"]: node for node in body["nodes"]}
    assert {key(failed), key(failed_meeting), key(retired)} <= set(by_id)
    assert by_id[key(as_topic)]["label"] == by_id[key(as_process)]["label"] == "finance"
    assert (by_id[key(as_topic)]["dimension"], by_id[key(as_process)]["dimension"]) == ("Topic", "Process")
    assert as_topic.id != as_process.id
    # Nothing about a tag's state, or a link's provenance, is in the payload.
    raw = the_map(session_client.client).content.decode()
    for trace in ("active", "grown", "applied_by", "confirmed", "confidence", "status",
                  DOCUMENT_EXTRACTION_FAILED):
        assert trace not in raw, trace


def test_an_isolated_meeting_is_a_node_with_no_connections(session_client):
    """Item 23. A meeting with no tag and no attendee has no edge, and is still returned, in the
    overview and as a selection, with a count of zero."""
    meeting = add_meeting("Unconnected meeting", added=at(10))

    body = graph(session_client.client)
    assert node_ids(body) == [key(meeting)]
    assert body["edges"] == []
    assert counts(body) == {key(meeting): 0}
    assert body["truncated"] is False

    selected = graph(session_client.client, meeting)
    assert node_ids(selected) == [key(meeting)]
    assert selected["focus"] == {"type": MEETING, "id": str(meeting.id)}
    assert selected["truncated"] is False


def test_a_count_is_of_the_edges_shown_on_a_truncated_view(session_client, monkeypatch):
    """Item 23. A node's count is the number of returned edges touching it, so the same tag
    counts three in a complete view and two in one the cap cut: never a total."""
    una = person("Una Uploader")
    documents = [add_document(f"Paper {n}", uploader=una, added=at(10 * n)) for n in range(3)]
    shared = None
    for document in documents:
        shared = tag(document, "Topic", "t-one")
    client = session_client.client

    complete = graph(client, shared)
    assert complete["truncated"] is False
    assert counts(complete)[key(shared)] == 3

    cap_nodes_at(monkeypatch, 3)
    cut = graph(client, shared)
    assert cut["truncated"] is True
    assert counts(cut)[key(shared)] == 2
    assert len(cut["edges"]) == 2
    # No total, "N of M" or omitted-node count is returned: the body holds nothing that says three.
    assert set(cut) == BODY_KEYS


# --- 24. UC-11 E1: an empty map, never an error -------------------------------------------------


def test_nothing_in_scope_is_the_same_bytes_as_an_empty_database(session_client):
    """Item 24, from both roles. "The system presents an empty map or table rather than an error,
    so that neither reveals the existence of content the Employee cannot see": a role with
    nothing in scope gets a 200 with the literal empty body, byte for byte what an empty database
    gets, although material it may not read exists and the viewer is recorded on it."""
    client = session_client.client
    on_an_empty_database = the_map(client)
    assert on_an_empty_database.json() == EMPTY_BODY

    hidden = unreadable_scope(session_client.role_name)
    document = add_document("Sealed one", uploader=session_client.user, roles=hidden, added=at(10))
    meeting = add_meeting("Sealed meeting", roles=hidden, added=at(20))
    attend(meeting, session_client.user)
    tag(document, "Topic", "sealed topic")
    tag(meeting, "Topic", "sealed topic")

    assert the_map(client).content == on_an_empty_database.content
    assert the_map(client, session_client.user).content == on_an_empty_database.content


# --- 25. 401, 403 and 400 -----------------------------------------------------------------------


def test_an_anonymous_request_is_401(api_client):
    build_visible()
    for params in ({}, {"focus_type": "bogus"}):
        response = api_client.get(MAP_URL, params)
        assert response.status_code == 401
        assert VISIBLE_DOCUMENT.encode() not in response.content


def test_a_role_without_view_knowledge_map_is_forbidden(session_client, employee, administrator):
    """Item 25, from both roles. Both seeded roles hold the code, so the only way to show the
    gate is enforced is to take it away (D-30's precedent). The 403 names the code, carries no
    node, and comes before the query is read; the role that still holds the code is still
    served."""
    visible = build_visible()
    assert the_map(session_client.client).status_code == 200
    RolePermission.objects.filter(
        role=session_client.user.role, permission__permission_name=VIEW_KNOWLEDGE_MAP_PERMISSION
    ).delete()

    for params in ({}, focus_on(visible.document), {"focus_type": "bogus"}):
        response = session_client.client.get(MAP_URL, params)
        assert response.status_code == 403
        assert response.json() == {
            "detail": "Your role does not hold the 'view_knowledge_map' permission."
        }
        assert VISIBLE_DOCUMENT.encode() not in response.content

    # Held against the role, not the user (D-14): the other role is untouched.
    other = administrator if session_client.role_name == EMPLOYEE_ROLE_NAME else employee
    assert the_map(logged_in(other)).status_code == 200


@pytest.mark.parametrize(
    "params, field",
    [
        ({"focus_type": "department", "focus_id": "0b7c1a52-7d0e-4c55-9a51-2f6d0e1f3a44"}, "focus_type"),
        ({"focus_type": "Document", "focus_id": "0b7c1a52-7d0e-4c55-9a51-2f6d0e1f3a44"}, "focus_type"),
        ({"focus_type": "document", "focus_id": "not-a-uuid"}, "focus_id"),
        ({"focus_type": "document", "focus_id": "12"}, "focus_id"),
        ({"focus_type": "document"}, "focus_id"),
        ({"focus_id": "0b7c1a52-7d0e-4c55-9a51-2f6d0e1f3a44"}, "focus_type"),
        ({"focus_type": "document", "focus_id": ""}, "focus_id"),
        ({"focus_type": "document\x00", "focus_id": "0b7c1a52-7d0e-4c55-9a51-2f6d0e1f3a44"}, "focus_type"),
        ({"focus_type": "document", "focus_id": "0b7c1a52-7d0e-4c55-9a51-2f6d0e1f3a44\x00"}, "focus_id"),
        ({"focus_type": "tag", "focus_id": "\x00"}, "focus_id"),
    ],
    ids=["type-outside-the-vocabulary", "type-in-the-wrong-case", "id-not-a-uuid", "id-a-number",
         "type-without-id", "id-without-type", "type-with-an-empty-id", "nul-in-type", "nul-in-id",
         "id-only-a-nul"],
)
def test_a_malformed_query_is_400_keyed_on_its_parameter(session_client, params, field):
    """Item 25, from both roles: the three shapes, and a NUL byte, which is neither a valid
    choice nor a valid UUID and so never reaches an ORM lookup (D-65)."""
    build_visible()

    response = session_client.client.get(MAP_URL, params)

    assert response.status_code == 400
    assert response["Content-Type"] == "application/json"
    assert set(response.json()) == {field}
    # A 400 carries no map.
    assert VISIBLE_DOCUMENT.encode() not in response.content


def test_one_parameter_without_the_other_names_the_rule_under_the_missing_one(session_client):
    client = session_client.client
    assert client.get(MAP_URL, {"focus_type": "tag"}).json() == {"focus_id": [FOCUS_INCOMPLETE_MESSAGE]}
    assert client.get(MAP_URL, {"focus_id": str(uuid.uuid4())}).json() == {
        "focus_type": [FOCUS_INCOMPLETE_MESSAGE]
    }


def test_two_empty_parameters_are_the_overview(session_client):
    """An empty value is the same as an absent one, as on the dashboard and browse."""
    build_visible()
    client = session_client.client
    assert client.get(MAP_URL, {"focus_type": "", "focus_id": ""}).content == the_map(client).content


# --- 26. Read only, and a fixed number of statements -------------------------------------------

WRITES = ("INSERT", "UPDATE", "DELETE")
TABLES_READ = ('"documents"', '"meetings"', '"content_tags"', '"tags"', '"users"',
               '"meeting_attendees"')


def _populate(first, last, uploader, attendee):
    for n in range(first, last):
        document = add_document(f"Paper {n:02d}", uploader=uploader, added=at(2 * n))
        tag(document, "Topic", f"topic {n % 7}")
        meeting = add_meeting(f"Meeting {n:02d}", added=at(2 * n + 1))
        tag(meeting, "Process", f"process {n % 5}")
        attend(meeting, attendee)


@pytest.mark.parametrize("selected", ["overview", "selection"])
def test_the_route_writes_nothing_and_its_statements_do_not_grow_with_the_corpus(
    session_client, selected
):
    """Item 26, from both roles. The route's own code runs SELECT statements only; the one write
    is the session row, saved on every request by FR-04's sliding expiry. The number of
    statements is the same for three sources of each type as for thirty: there is no query per
    source, so an Employee asking in a loop costs a handful of statements each time."""
    una = person("Una Uploader")
    otto = person("Otto Attendee")
    _populate(0, 3, una, otto)
    params = {} if selected == "overview" else focus_on(una)
    client = session_client.client
    the_map(client, params)  # the first request of a session, set aside

    response, few = statements_of(client, params)
    assert response.status_code == 200 and response.json()["nodes"]
    for statement in few:
        if statement.lstrip().upper().startswith(WRITES):
            assert "django_session" in statement, statement
    joined = "\n".join(few)
    for table in TABLES_READ:
        assert table in joined, table  # the premise: the tables the contract names were read

    _populate(3, 30, una, otto)

    response, many = statements_of(client, params)
    assert len(response.json()["nodes"]) > 20
    assert len(many) == len(few)
    for statement in many:
        if statement.lstrip().upper().startswith(WRITES):
            assert "django_session" in statement, statement


# --- The walk on plain values: the corners a database test reaches slowly -----------------------


def _plain_graph():
    """Two sources, three tags and two people, as plain nodes and edges."""
    newer = source_node(MEETING, uuid.UUID(int=2), "Newer", at(20))
    older = source_node(DOCUMENT, uuid.UUID(int=1), "Older", at(10))
    alpha = tag_node(uuid.UUID(int=11), "alpha", "Topic")
    beta = tag_node(uuid.UUID(int=12), "beta", "Topic")
    gamma = tag_node(uuid.UUID(int=13), "gamma", "Process")
    ann = contributor_node(uuid.UUID(int=21), "Ann")
    bob = contributor_node(uuid.UUID(int=22), "bob")
    joins = [
        Edge(newer.id, alpha.id, TAGGED), Edge(newer.id, beta.id, TAGGED),
        Edge(bob.id, newer.id, ATTENDED), Edge(ann.id, newer.id, ATTENDED),
        Edge(older.id, gamma.id, TAGGED), Edge(ann.id, older.id, UPLOADED),
    ]
    return [older, gamma, bob, beta, newer, ann, alpha], joins


def test_the_walk_skips_what_does_not_fit_and_takes_tags_before_people_in_the_corner():
    """The overview's rule on plain values, at three caps. At seven everything fits. At four the
    newer source (five nodes with its neighbours) is skipped and the older one (three) is taken.
    At two no source fits, so the newest comes with one neighbour, a tag before any person."""
    nodes, joins = _plain_graph()
    newer, older = f"{MEETING}:{uuid.UUID(int=2)}", f"{DOCUMENT}:{uuid.UUID(int=1)}"
    alpha, beta, gamma = (f"{TAG}:{uuid.UUID(int=n)}" for n in (11, 12, 13))
    ann, bob = (f"{CONTRIBUTOR}:{uuid.UUID(int=n)}" for n in (21, 22))

    def overview(cap):
        body = walk(nodes, joins, None, maximum_node_count=cap, maximum_traversal_depth=2)
        assert_well_formed(body)
        return body

    whole = overview(7)
    assert node_ids(whole) == [newer, alpha, beta, ann, bob, older, gamma]
    assert (whole["truncated"], whole["truncated_by"]) == (False, None)

    skipped = overview(4)
    assert node_ids(skipped) == [older, gamma, ann]
    assert (skipped["truncated"], skipped["truncated_by"]) == (True, NODE_COUNT)

    corner = overview(2)
    assert node_ids(corner) == [newer, alpha]
    assert (corner["truncated"], corner["truncated_by"]) == (True, NODE_COUNT)


def test_the_walk_ignores_an_edge_whose_end_is_not_a_node():
    """Returned edges are those with both ends returned. An edge naming a node the graph does not
    hold is never returned and is never a way to anything."""
    nodes, joins = _plain_graph()
    stray = Edge(f"{DOCUMENT}:{uuid.UUID(int=1)}", f"{TAG}:{uuid.UUID(int=99)}", TAGGED)

    with_stray = walk(nodes, [*joins, stray], None, maximum_node_count=50, maximum_traversal_depth=2)
    without = walk(nodes, joins, None, maximum_node_count=50, maximum_traversal_depth=2)

    assert_well_formed(with_stray)
    assert with_stray == without
