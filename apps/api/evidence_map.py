"""The knowledge map's second view: claims and the passages they cite (docs/decisions.md D-138).

After the proposal's Evidence mock-up (Figure 8.7, "Claims to passages ... selected claim at the
right"). A **claim** is a verified statement of an answered question, an ``AnswerCitations`` row's
``statement_text``; the same statement admitted in several answers is one claim. A **passage** is
the chunk a statement cites. Nothing is stored here and nothing is cached between requests, for
the reasons ``apps/api/knowledge_map.py`` gives.

**Two parts, as the first view has, and only the first touches the database.** ``assemble`` reads
the rows the role may see and returns plain nodes and edges, with what the screen shows beside
each. ``knowledge_map.walk`` then caps them: the same pure function, the same two caps and the
same truncation rule as the first view, so nothing the caller cannot read is left for a cap, a
count or a flag to turn on (invariant 1).

**Which rows a role sees.** A citation row is read only when all three hold:

1. **Its cited chunk is one of the passages its answer was generated from.**
   ``QueryLog.retrieved_chunk_ids`` holds the identifiers supplied to the model
   (``apps/retrieval/query_log.py``), and every row the answer path writes cites one of them. A
   row whose list is empty or does not hold its own citation was written by something else, and
   rule 2 could say nothing about it, so it is not read: this fails closed (the security review
   of the built code, S5). A row whose chunk was deleted cites nothing and is left out with it
   (``AnswerCitation``'s own rule, D-67).
2. **Every one of those passages is a chunk in the role's scope** (``scoped_chunks``), and so the
   cited one is. A statement cites one passage, but the model wrote it with every supplied
   passage in front of it, and citation verification checks the identifier and never the content
   (invariant 5). So a statement from an Administrator's answer can carry what an
   Administrator-only passage said while citing a passage every role reads. A supplied chunk
   that no longer exists is not in scope, so the row is left out: this fails closed too.
3. **The cited chunk's own source is in scope** (``scoped_documents`` or ``scoped_meetings``),
   which is where the passage's title is read from. A chunk and a source that disagree show
   nothing.

**Two more conditions, each on a row no answer path writes.** The row's question must be
recorded as answered: a citation is written only for an answer that was returned. And the
statement must hold something besides whitespace: a claim with no text would be a node with
no name. Each has a test of its own.

**What is never selected:** the question, who asked it, the answer's whole text, a query's
identifier, and any passage text. A claim is the statement's text and what is counted from the
rows above; a passage is its source's title and its place in the source.

**When an answer was given is returned as a calendar day and no finer** (the security review,
S2). Every statement of one answer shares its moment, so the moment would let a reader put
another person's answer back together and guess who was asking. The day is the project's own
(``TIME_ZONE``). Claims are ordered by day, newest first, and within a day by identifier, so the
order does not give the moment back.

**A claim's identifier is a keyed hash of its text** (the security review, S4): HMAC-SHA-256 under
the server's ``SECRET_KEY``. It sits in addresses, and an unkeyed hash would let anyone who came
by one confirm a guessed statement offline.

**Counts are of the role's own rows.** How often a claim was admitted, how many passages support
it and the days it was first and last admitted are computed from the rows above and nothing
else, so a claim also admitted in answers the role may not see counts only the ones it may.
"""

import hashlib
import hmac
from datetime import date

from django.conf import settings
from django.contrib.postgres.expressions import ArraySubquery
from django.db.models import F, Func, IntegerField
from django.utils import timezone

from apps.core.constants import (
    EVIDENCE_MAP_CITES,
    EVIDENCE_MAP_CLAIM,
    EVIDENCE_MAP_PASSAGE,
    MAXIMUM_NODE_COUNT,
    MAXIMUM_TRAVERSAL_DEPTH,
    SOURCE_TYPES,
)
from apps.retrieval.models import AnswerCitation
from apps.retrieval.scoping import scoped_chunks, scoped_documents, scoped_meetings

from .knowledge_map import Edge, Node, node_id, walk

_DOCUMENT_SOURCE, _MEETING_SOURCE = SOURCE_TYPES


def claim_text(statement_text: str) -> str:
    """A statement as a claim shows it: runs of whitespace are one space, and the ends are bare.

    Two rows are the same claim when this is the same for both, character for character. Nothing
    cleverer is attempted: a reworded statement is another claim.
    """
    return " ".join(statement_text.split())


def claim_id(text: str) -> str:
    """A claim's identifier: the HMAC-SHA-256 of its text under ``SECRET_KEY``, in hexadecimal.

    A claim has no row of its own, so this is what a selection names. A selection that names a
    claim outside the caller's rows is not in the assembled graph, and gets the one empty answer
    every absent focus gets. Keyed, so that an identifier seen in an address confirms nothing to
    somebody guessing at the statement behind it. A changed key changes every identifier, and an
    address saved before the change then selects nothing.
    """
    key = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()


def claim_node(text: str, last_admitted_on: date) -> Node:
    """A claim node. Claims are ordered by the day each was last admitted, newest first, and
    within a day by identifier."""
    identifier = claim_id(text)
    newest_first = -last_admitted_on.toordinal()
    return Node(EVIDENCE_MAP_CLAIM, identifier, text, None, (newest_first, identifier))


def passage_label(source_title: str, position: int) -> str:
    return f"{source_title} · passage {position}"


def passage_node(chunk_id, source_title: str, position: int) -> Node:
    """A passage node, ordered by its source's title and then its place in the source."""
    order = (source_title.casefold(), position, str(chunk_id))
    return Node(EVIDENCE_MAP_PASSAGE, str(chunk_id), passage_label(source_title, position), None, order)


def evidence_map(*, role_name: str, focus: tuple | None) -> dict:
    """The body of ``GET /api/knowledge-map/evidence`` for ``role_name``: assemble, then walk.

    ``focus`` is ``None`` for the overview, or the validated ``(focus_type, focus_id)`` pair. The
    walk's body is the first view's seven keys. Each node then gains ``detail`` and each edge
    ``weight``, both computed in ``assemble`` from the rows the role may see.
    """
    nodes, edges, detail, weight = assemble(role_name=role_name)
    body = walk(
        nodes,
        edges,
        None if focus is None else node_id(*focus),
        maximum_node_count=MAXIMUM_NODE_COUNT,
        maximum_traversal_depth=MAXIMUM_TRAVERSAL_DEPTH,
    )
    for node in body["nodes"]:
        node["detail"] = detail[node["id"]]
    for edge in body["edges"]:
        edge["weight"] = weight[edge["source"], edge["target"]]
    return body


def assemble(*, role_name: str) -> tuple[list[Node], list[Edge], dict, dict]:
    """Every claim and passage ``role_name`` may see, the edges between them, and what the
    screen shows beside each (FR-11, invariant 1). The module docstring gives the three rules.

    Three statements, whatever the log and the corpus hold: the citation rows, the scoped
    documents' titles and the scoped meetings' titles. None takes the focus as a parameter.
    """
    chunks = scoped_chunks(role_name=role_name)
    rows = AnswerCitation.objects.annotate(
        # Where the cited chunk sits among the passages supplied to the model: NULL when it is
        # not one of them, and when the chunk is gone.
        supplied_place=Func(
            F("query__retrieved_chunk_ids"), F("chunk_id"),
            function="array_position", output_field=IntegerField(),
        ),
    ).filter(
        supplied_place__isnull=False,  # rule 1
        query__answered=True,
        # Rule 2: every identifier supplied to the model names a chunk in scope.
        query__retrieved_chunk_ids__contained_by=ArraySubquery(chunks.values("id")),
    ).values_list(
        "statement_text", "chunk_id", "chunk__source_type", "chunk__source_id",
        "chunk__chunk_index", "chunk__ai_generated", "query_id", "query__answered_at",
    )
    titles = {
        _DOCUMENT_SOURCE: dict(scoped_documents(role_name=role_name).values_list("id", "title")),
        _MEETING_SOURCE: dict(scoped_meetings(role_name=role_name).values_list("id", "title")),
    }

    passages: dict[str, Node] = {}
    detail: dict[str, dict] = {}
    weight: dict[tuple[str, str], int] = {}
    claims: dict[str, dict] = {}  # by claim text
    for (statement_text, chunk_id, source_type, source_id, chunk_index, ai_generated, query_id,
         answered_at) in rows:
        source_title = titles.get(source_type, {}).get(source_id)
        text = claim_text(statement_text)
        if source_title is None or not text:
            # Rule 3: the chunk's source is not one the role reads. Or the statement is blank.
            continue
        passage = passage_node(chunk_id, source_title, chunk_index + 1)
        if passage.id not in passages:
            passages[passage.id] = passage
            detail[passage.id] = {
                "source_type": source_type,
                "source_id": str(source_id),
                "source_title": source_title,
                "position": chunk_index + 1,
                # NFR-15: a passage of a meeting's AI-written summary says that it is one.
                "ai_generated": ai_generated,
            }
        claim = claims.setdefault(text, {"queries": set(), "passages": set(), "days": []})
        claim["queries"].add(query_id)
        claim["passages"].add(passage.id)
        # The day and no finer: the moment would tie an answer's statements back together.
        claim["days"].append(timezone.localtime(answered_at).date())
        pair = (node_id(EVIDENCE_MAP_CLAIM, claim_id(text)), passage.id)
        weight[pair] = weight.get(pair, 0) + 1

    nodes: list[Node] = []
    for text, claim in claims.items():
        node = claim_node(text, max(claim["days"]))
        nodes.append(node)
        detail[node.id] = {
            "answer_count": len(claim["queries"]),
            "passage_count": len(claim["passages"]),
            "first_admitted_at": min(claim["days"]),
            "last_admitted_at": max(claim["days"]),
        }
    nodes.extend(passages.values())
    edges = [Edge(source, target, EVIDENCE_MAP_CITES) for source, target in weight]
    return nodes, edges, detail, weight
