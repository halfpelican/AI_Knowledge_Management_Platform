"""FR-20's knowledge map: the scoped graph of documents, meetings, tags and contributors, and
the capped view of it one request returns (docs/decisions.md D-132).

FR-20's Server-End clause: "Assembles nodes and edges from existing tables (ContentTags for
classification links, Documents.uploaded_by for authorship, MeetingAttendees for participation)
rather than maintaining a separate relationship store." Nothing is stored here and nothing is
cached between requests: a graph kept for one role would be served to the next, and would outlive
a change of role.

**Two parts, and only the first touches the database.**

1. ``assemble`` runs a fixed set of statements for the role the view resolved on this request,
   and returns plain nodes and edges. Every statement starts from, or is constrained by,
   ``scoped_documents`` or ``scoped_meetings`` (D-53). Both roles go through the same code:
   there is no Administrator shortcut, so a source stamped for nobody is in nobody's map. The
   number of statements does not grow with the corpus, and none takes the focus as a parameter.
2. ``walk`` is a pure function over those nodes and edges, the focus and the two caps. It
   receives no queryset, no user and no identifier to look up. It decides which nodes and edges
   are returned, both truncation fields and every connection count. The focus is found by
   membership in the assembled graph, so a focus the caller may not see and one that does not
   exist are the same absence, at the same cost.

**Why the caps come after the scope, never before** (invariant 1). The proposal's UC-11 scopes at
assembly (step 03), caps (04), then removes inaccessible nodes again (05). A cap applied to a set
that still held anything the caller cannot read would let that material decide which nodes
survive and whether ``truncated`` is true, and both are things the caller sees. So every removal
happens in ``assemble``, including the two kinds step 03 cannot filter because they carry no
visibility column: a tag or a person is a node only when a link reaches it from a source in
scope. ``walk`` is then handed nothing it would have to remove, and step 05 has nothing left to
do. Connection counts are still taken last, over the edges that are returned.

**Which links are read.**

- Tag links through ``repository.live_tag_links``, FR-15's rule: not provisional, not removed,
  a dimension in ``REPOSITORY_TAG_DIMENSIONS``, matched on the source type and identifier
  together. ``Tag.active`` and ``Tag.grown`` are not consulted, as FR-15 does not consult them.
- Authorship from each scoped document's own ``uploaded_by``.
- Participation from ``MeetingAttendee`` rows whose meeting is a scoped meeting. Attendance is
  read for a meeting already in scope and never admits one (invariant 3, D-16).

**What is never read:** the ``Tag`` table on its own, the user table on its own, and any reverse
relation from a user or a tag to its sources. Each of those reaches material by a path the scope
is not a condition on. The D-53 scan covers only the ``Document``, ``Meeting`` and
``ContentChunk`` managers, so ``apps/api/tests/test_knowledge_map.py`` holds this module to the
rest by reading its source.

**What is never selected:** a transcript, extracted text or a file field. A source is its
identifier, its title and when it was added; a person is an identifier and a name, never an email
or a role (D-132, the lead's decision 4).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from apps.core.constants import (
    KNOWLEDGE_MAP_ATTENDED,
    KNOWLEDGE_MAP_CONTRIBUTOR,
    KNOWLEDGE_MAP_DOCUMENT,
    KNOWLEDGE_MAP_MEETING,
    KNOWLEDGE_MAP_TAG,
    KNOWLEDGE_MAP_TAGGED,
    KNOWLEDGE_MAP_TRUNCATED_BY_DEPTH,
    KNOWLEDGE_MAP_TRUNCATED_BY_NODE_COUNT,
    KNOWLEDGE_MAP_UPLOADED,
    MAXIMUM_NODE_COUNT,
    MAXIMUM_TRAVERSAL_DEPTH,
)
from apps.meetings.models import MeetingAttendee
from apps.retrieval.scoping import scoped_documents, scoped_meetings

from .repository import live_tag_links

# Where each kind sits when a ring, or a source's neighbours, are put in order: documents and
# meetings are one list, then tags, then contributors (D-132).
_SOURCES, _TAGS, _CONTRIBUTORS = range(3)
_KIND = {
    KNOWLEDGE_MAP_DOCUMENT: _SOURCES,
    KNOWLEDGE_MAP_MEETING: _SOURCES,
    KNOWLEDGE_MAP_TAG: _TAGS,
    KNOWLEDGE_MAP_CONTRIBUTOR: _CONTRIBUTORS,
}

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND = timedelta(microseconds=1)


@dataclass(frozen=True)
class Node:
    """One node of the scoped graph, as plain values.

    ``order`` is the node's place among nodes of its own kind, and reads only the node's own
    columns, so nothing outside the caller's scope can move it:

    - a document or a meeting: newest first by when it was added, then by identifier;
    - a tag: dimension, name, identifier;
    - a contributor: name without regard to case, then identifier.
    """

    type: str
    item_id: str
    label: str
    dimension: str | None
    order: tuple

    @property
    def id(self) -> str:
        return node_id(self.type, self.item_id)


@dataclass(frozen=True)
class Edge:
    """One relationship, read "source, relationship, target". Both ends are node identifiers."""

    source: str
    target: str
    relationship: str


def node_id(node_type: str, item_id) -> str:
    """A node's identifier in the response: its type and its row's own identifier.

    The type is part of the key because a document and a meeting, or a tag and a person, are
    different tables and nothing stops two rows sharing a UUID. So a focus whose type and
    identifier do not match names no node.
    """
    return f"{node_type}:{item_id}"


def source_node(node_type: str, item_id, title: str, added_at: datetime) -> Node:
    """A document or meeting node. ``added_at`` is ``uploaded_at`` or ``created_at``."""
    # Whole microseconds, negated, so that ascending order is newest first and two rows a
    # microsecond apart are never tied by a float's rounding.
    newest_first = -((added_at - _EPOCH) // _MICROSECOND)
    return Node(node_type, str(item_id), title, None, (newest_first, str(item_id)))


def tag_node(tag_id, name: str, dimension: str) -> Node:
    return Node(KNOWLEDGE_MAP_TAG, str(tag_id), name, dimension, (dimension, name, str(tag_id)))


def contributor_node(user_id, name: str) -> Node:
    order = (name.casefold(), str(user_id))
    return Node(KNOWLEDGE_MAP_CONTRIBUTOR, str(user_id), name, None, order)


def knowledge_map(*, role_name: str, focus: tuple | None) -> dict:
    """The body of ``GET /api/knowledge-map`` for ``role_name``: assemble, then walk.

    ``focus`` is ``None`` for the overview, or the validated ``(focus_type, focus_id)`` pair. It
    is turned into a node identifier here and goes nowhere near ``assemble``. The two caps are
    read from this module at call time, which is where a test patches them.
    """
    nodes, edges = assemble(role_name=role_name)
    return walk(
        nodes,
        edges,
        None if focus is None else node_id(*focus),
        maximum_node_count=MAXIMUM_NODE_COUNT,
        maximum_traversal_depth=MAXIMUM_TRAVERSAL_DEPTH,
    )


# --- Assembly: the only part that touches the database -----------------------------------------


def assemble(*, role_name: str) -> tuple[list[Node], list[Edge]]:
    """Every node and edge ``role_name`` may see, and nothing else (FR-11, invariant 1).

    Five statements, whatever the corpus holds: the scoped documents with their uploaders, the
    scoped meetings, the live tag links of each, and the attendees of the scoped meetings.
    Sources in every status are read, as the repository and the meetings list show them.

    Edges are de-duplicated: neither ``ContentTags`` nor ``MeetingAttendees`` is unique on its
    pair, so a source linked twice to one tag, or a person recorded twice on one meeting, is one
    edge. A link is kept only when its source is among the sources read above, so an edge can
    never point at a node this graph does not hold.
    """
    documents = scoped_documents(role_name=role_name)
    meetings = scoped_meetings(role_name=role_name)

    nodes: dict[str, Node] = {}
    edges: dict[Edge, None] = {}  # insertion-ordered, and a repeated edge is one key

    document_rows = documents.values_list(
        "id", "title", "uploaded_at", "uploaded_by_id", "uploaded_by__name"
    )
    for document_id, title, uploaded_at, uploader_id, uploader_name in document_rows:
        document = source_node(KNOWLEDGE_MAP_DOCUMENT, document_id, title, uploaded_at)
        nodes[document.id] = document
        # The uploader is a node because this document, which the caller reads, names them.
        uploader = contributor_node(uploader_id, uploader_name)
        nodes.setdefault(uploader.id, uploader)
        edges[Edge(uploader.id, document.id, KNOWLEDGE_MAP_UPLOADED)] = None

    for meeting_id, title, created_at in meetings.values_list("id", "title", "created_at"):
        meeting = source_node(KNOWLEDGE_MAP_MEETING, meeting_id, title, created_at)
        nodes[meeting.id] = meeting

    for source_type, sources in (
        (KNOWLEDGE_MAP_DOCUMENT, documents),
        (KNOWLEDGE_MAP_MEETING, meetings),
    ):
        # A document link is honoured only through a scoped document and a meeting link only
        # through a scoped meeting: type and identifier together (D-07).
        link_rows = (
            live_tag_links(source_type=source_type, source_ids=sources.values("id"))
            .values_list("source_id", "tag_id", "tag__tag_name", "tag__dimension")
            .distinct()
        )
        for source_id, tag_id, name, dimension in link_rows:
            source = node_id(source_type, source_id)
            if source not in nodes:
                continue
            tag = tag_node(tag_id, name, dimension)
            nodes.setdefault(tag.id, tag)
            edges[Edge(source, tag.id, KNOWLEDGE_MAP_TAGGED)] = None

    # Participation, for meetings already in scope. Attendance never admits a meeting
    # (invariant 3): the condition is the scoped meetings, and the attendee is what is read.
    attendee_rows = (
        MeetingAttendee.objects.filter(meeting_id__in=meetings.values("id"))
        .values_list("meeting_id", "user_id", "user__name")
        .distinct()
    )
    for meeting_id, user_id, name in attendee_rows:
        meeting = node_id(KNOWLEDGE_MAP_MEETING, meeting_id)
        if meeting not in nodes:
            continue
        attendee = contributor_node(user_id, name)
        nodes.setdefault(attendee.id, attendee)
        edges[Edge(attendee.id, meeting, KNOWLEDGE_MAP_ATTENDED)] = None

    return list(nodes.values()), list(edges)


# --- The walk: a pure function over plain values ------------------------------------------------


def walk(nodes, edges, focus: str | None, *, maximum_node_count: int,
         maximum_traversal_depth: int) -> dict:
    """The response body for one view of the graph ``nodes`` and ``edges`` describe.

    ``focus`` is a node identifier or ``None``. Everything here is computed from the arguments
    alone, which the caller has already scoped.

    **Without a focus, the overview.** Each source in turn, newest first, with one hop: the
    source, then its tags, then its contributors, those not yet included. A source is included
    only when it and all of those fit under ``maximum_node_count``; one that does not fit is
    skipped and the walk carries on, so one heavily connected source cannot hide everything
    older. If no source at all fits, the newest is returned with as many of its neighbours as fit.

    **With a focus.** From that node, up to ``maximum_traversal_depth`` hops, ring by ring. Each
    ring is the not-yet-included neighbours of the ring before it, ordered as a whole: sources,
    then tags, then contributors. Nodes are added in that order until the count is reached.

    **A focus that is not a node of this graph** gets the empty body, whatever the reason: the
    body an empty overview gets, holding nothing the caller sent (UC-11 E1).

    **Truncation.** ``truncated`` is true when a returned node has a neighbour that was not
    returned, or, in the overview, when a source was not returned. ``truncated_by`` is
    ``"node_count"`` if and only if a node within reach was left out because the count was
    reached, and ``"depth"`` otherwise; when both apply it is ``"node_count"``. In the overview
    every node is one hop from a source, so every node is within reach and the depth cap is
    never what limits it.

    **Counts last.** A node's ``connection_count`` is the number of returned edges touching it:
    the connections shown in this view, never a total.
    """
    by_id = {node.id: node for node in nodes}
    neighbours: dict[str, set[str]] = {key: set() for key in by_id}
    joined = [edge for edge in edges if edge.source in by_id and edge.target in by_id]
    for edge in joined:
        neighbours[edge.source].add(edge.target)
        neighbours[edge.target].add(edge.source)

    def in_order(keys) -> list[str]:
        return sorted(keys, key=lambda key: (_KIND[by_id[key].type], by_id[key].order))

    if focus is None:
        returned = _overview(by_id, neighbours, in_order, maximum_node_count)
        # Every node is one hop from a source, so any node left out was left out by the count.
        left_out_by_count = len(returned) < len(by_id)
    elif focus not in by_id:
        return _body(None, [], [], False, None, maximum_node_count, maximum_traversal_depth)
    else:
        returned, left_out_by_count = _rings(
            focus, neighbours, in_order, maximum_node_count, maximum_traversal_depth
        )

    kept = set(returned)
    truncated = any(neighbour not in kept for key in returned for neighbour in neighbours[key])
    if focus is None:
        truncated = truncated or any(
            _KIND[node.type] == _SOURCES and key not in kept for key, node in by_id.items()
        )
    truncated_by = None
    if truncated:
        truncated_by = (
            KNOWLEDGE_MAP_TRUNCATED_BY_NODE_COUNT
            if left_out_by_count
            else KNOWLEDGE_MAP_TRUNCATED_BY_DEPTH
        )

    place = {key: index for index, key in enumerate(returned)}
    shown = sorted(
        (edge for edge in joined if edge.source in kept and edge.target in kept),
        key=lambda edge: (place[edge.source], place[edge.target]),
    )
    # Taken last, over the edges this view returns (FR-20: "connection counts are recomputed
    # after filtering").
    counts = dict.fromkeys(returned, 0)
    for edge in shown:
        counts[edge.source] += 1
        counts[edge.target] += 1

    return _body(
        None if focus is None else by_id[focus],
        [(by_id[key], counts[key]) for key in returned],
        shown,
        truncated,
        truncated_by,
        maximum_node_count,
        maximum_traversal_depth,
    )


def _overview(by_id, neighbours, in_order, maximum_node_count: int) -> list[str]:
    sources = in_order(key for key, node in by_id.items() if _KIND[node.type] == _SOURCES)
    returned: list[str] = []
    kept: set[str] = set()
    for source in sources:
        group = [source, *in_order(neighbours[source] - kept)]
        if len(returned) + len(group) <= maximum_node_count:
            returned.extend(group)
            kept.update(group)
    if not returned and sources:
        # No source fits with all of its neighbours: the newest, with as many as fit, tags
        # before contributors. An empty map would say there is nothing to see.
        newest = sources[0]
        returned = [newest, *in_order(neighbours[newest])][: max(maximum_node_count, 0)]
    return returned


def _rings(focus: str, neighbours, in_order, maximum_node_count: int,
           maximum_traversal_depth: int) -> tuple[list[str], bool]:
    """The nodes within ``maximum_traversal_depth`` hops of ``focus``, in walk order, cut at
    ``maximum_node_count``, and whether the count is what left a node within reach out."""
    returned = [focus]
    kept = {focus}
    ring = [focus]
    for _ in range(maximum_traversal_depth):
        reached = set().union(*(neighbours[key] for key in ring)) - kept
        if not reached:
            break
        ring = in_order(reached)[: max(maximum_node_count - len(returned), 0)]
        returned.extend(ring)
        kept.update(ring)
        if len(ring) < len(reached):
            # The count was reached inside a ring: a node within reach was left out by it.
            return returned, True
    return returned, False


def _body(focus: Node | None, nodes, edges, truncated: bool, truncated_by: str | None,
          maximum_node_count: int, maximum_traversal_depth: int) -> dict:
    """The seven keys of the response, in the contract's order (docs/api-contract.md, FR-20)."""
    return {
        # Null unless the focus is one of the returned nodes, and then the node's own type and
        # canonical identifier, never the caller's spelling of them.
        "focus": None if focus is None else {"type": focus.type, "id": focus.item_id},
        "nodes": [
            {
                "id": node.id,
                "type": node.type,
                "item_id": node.item_id,
                "label": node.label,
                "dimension": node.dimension,
                "connection_count": connection_count,
            }
            for node, connection_count in nodes
        ],
        "edges": [
            {"source": edge.source, "target": edge.target, "relationship": edge.relationship}
            for edge in edges
        ],
        "truncated": truncated,
        "truncated_by": truncated_by,
        "maximum_node_count": maximum_node_count,
        "maximum_traversal_depth": maximum_traversal_depth,
    }
