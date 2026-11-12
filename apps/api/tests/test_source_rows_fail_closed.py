"""D-53: one predicate for source rows, and it fails closed.

D-53 found two modules resolving Document and Meeting rows for chunks that scoping had
already admitted, and disagreeing: ``apps/retrieval/search.py`` applied the source's own
``visible_to_roles`` and so failed **closed**, while ``apps/api/answers.py`` applied nothing and
failed **open**. The predicate itself was written by hand at eight sites. D-53 decided that
failing closed is authoritative and that the mechanism is one helper —
``scoped_documents()`` and ``scoped_meetings()`` beside ``scoped_chunks()`` — and said what was
owed before FR-15 wrote a ninth copy, including "one test enumerating the routes that return
source rows, asserting each carries the predicate". This is that test, in three parts.

1. **The predicate is spelled in one module.** A scan of every production module: a
   ``visible_to_roles__<lookup>`` appears only in ``apps/retrieval/scoping.py``, and the
   request-serving packages (``apps/api``, ``apps/retrieval``) read ``Document``, ``Meeting``
   and ``ContentChunk`` rows only through it, with named exceptions carrying their reasons.
   This is what stops a tenth copy being written beside the helpers.

2. **Every route is classified.** Each (route, method) in the URL conf is either in
   ``ROUTES_RETURNING_SOURCE_ROWS`` with a probe, or in ``ROUTES_RETURNING_NO_SOURCE_ROWS`` with
   the reason it returns none. A route that is in neither fails the suite, so FR-14's
   aggregation and FR-15's browse, detail, download and delete routes cannot land unclassified.
   The dual-role matrix would credit a route that returned everything, as long as both roles
   got a 200 from it; this does not.

3. **Every source-returning route fails closed on a disagreement.** The fixture builds the
   state D-53 is about: a source whose own row says Administrator-only while its chunks are
   stamped for both roles. That state is unreachable through any shipped write path while
   D-47's cascade holds; ``bulk_create(update_conflicts=True)`` and raw SQL reach it, and here a
   plain ``ContentChunk`` UPDATE does, because that model carries no cascade. From an Employee
   session each route must not disclose the source: absent from a list, 404 on a detail. Each
   absence has its mirror — the Administrator, whom the source admits, is shown it — so a
   route returning nothing to anybody cannot pass.

**What this does not test:** the statements of a live answer. The chunk stamp admitted the
passage, so the model was sent it and its statement survives verification; failing closed on
the source drops the item from ``sources`` and ``partial_matches`` and nothing more. D-53's
implementation note records why that boundary is where it is.
"""

import ast
import uuid
from dataclasses import dataclass
from datetime import date
from math import sqrt
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

import apps.ai
from apps.ai.base import EmbeddingResult, Statement, StatementList
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api.tests.dual_role_matrix import enumerate_endpoints
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, ContentTag, Document, DocumentAnalysis, Tag
from apps.meetings.models import Meeting
from apps.retrieval.scoping import scoped_chunks, scoped_documents, scoped_meetings

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APPS_DIRECTORY = REPOSITORY_ROOT / "apps"


# --- 1. The predicate is spelled in one module -------------------------------------------

SCOPING_MODULE = "apps/retrieval/scoping.py"

# The packages that serve requests. Ingestion is excluded: it writes the stamp and reads
# sources by the primary key of a row a scoped view already resolved, and ``manage.py
# reindex`` is an operator's command, not a route.
REQUEST_SERVING_PACKAGES = ("apps/api", "apps/retrieval")

# The models whose rows are the material, or the source of it.
SOURCE_MODELS = frozenset({"Document", "Meeting", "ContentChunk"})

# Reads of those models' managers permitted outside the scoping module, each keyed by
# (module, enclosing function) with its reason. An entry that matches no read fails below.
UNSCOPED_READS = {
    ("apps/api/views.py", "DocumentsView.post"): (
        "FR-08's 409 duplicate check compares content hashes across every scope. That is "
        "the existence oracle D-33 records and accepts, and a scoped check would let a "
        "duplicate of a restricted document be uploaded."
    ),
}


def production_modules():
    for path in sorted(APPS_DIRECTORY.rglob("*.py")):
        parts = path.relative_to(REPOSITORY_ROOT).parts
        if "tests" in parts or "migrations" in parts:
            continue
        yield path


class _Scoped(ast.NodeVisitor):
    """Walk a module, recording each node with the dotted class/function name enclosing it."""

    def __init__(self):
        self.scope: list[str] = []
        self.keywords: list[tuple[str, ast.keyword]] = []
        self.constants: list[tuple[str, ast.Constant]] = []
        self.managers: list[tuple[str, ast.Attribute]] = []

    def _enter(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_ClassDef = _enter
    visit_FunctionDef = _enter
    visit_AsyncFunctionDef = _enter

    @property
    def here(self) -> str:
        return ".".join(self.scope) or "<module>"

    def visit_keyword(self, node):
        self.keywords.append((self.here, node))
        self.generic_visit(node)

    def visit_Constant(self, node):
        self.constants.append((self.here, node))

    def visit_Attribute(self, node):
        if (
            node.attr in {"objects", "_default_manager", "_base_manager"}
            and isinstance(node.value, ast.Name)
            and node.value.id in SOURCE_MODELS
        ):
            self.managers.append((self.here, node))
        self.generic_visit(node)


def scan(path: Path) -> _Scoped:
    visitor = _Scoped()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return visitor


def role_predicates(visitor: _Scoped) -> list[tuple[str, int]]:
    """Every ``visible_to_roles__<lookup>``, as a keyword or as a string key for ``**{...}``.

    The bare column name is not a predicate: ingestion passes ``visible_to_roles=...`` to
    stamp a row, and the cascade compares the whole array. A lookup suffix is what makes it a
    read-side test of membership.
    """
    found = [
        (where, node.value.lineno)
        for where, node in visitor.keywords
        if node.arg and node.arg.startswith("visible_to_roles__")
    ]
    found += [
        (where, node.lineno)
        for where, node in visitor.constants
        if isinstance(node.value, str) and node.value.startswith("visible_to_roles__")
    ]
    return found


def test_the_role_predicate_on_a_source_or_a_chunk_is_spelled_only_in_the_scoping_module():
    elsewhere = {}
    for path in production_modules():
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        if relative == SCOPING_MODULE:
            continue
        found = role_predicates(scan(path))
        if found:
            elsewhere[relative] = found
    assert elsewhere == {}, (
        "The FR-11 predicate is written outside apps/retrieval/scoping.py. Use "
        f"scoped_chunks(), scoped_documents() or scoped_meetings() instead (D-53): {elsewhere}"
    )


def test_the_scoping_module_does_spell_it_so_the_scan_can_see_one():
    """The negative control for the test above: the scan finds the predicate where it is."""
    assert role_predicates(scan(REPOSITORY_ROOT / SCOPING_MODULE)) != []


def unscoped_source_reads() -> dict[tuple[str, str], list[int]]:
    reads: dict[tuple[str, str], list[int]] = {}
    for path in production_modules():
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        if relative == SCOPING_MODULE or not relative.startswith(REQUEST_SERVING_PACKAGES):
            continue
        for where, node in scan(path).managers:
            reads.setdefault((relative, where), []).append(node.lineno)
    return reads


def test_request_serving_code_reads_source_rows_only_through_the_scoped_helpers():
    unexpected = {key: lines for key, lines in unscoped_source_reads().items() if key not in UNSCOPED_READS}
    assert unexpected == {}, (
        "A Document, Meeting or ContentChunk manager is read outside apps/retrieval/scoping.py "
        f"in a request-serving package. Start from the scoped helper (D-53): {unexpected}"
    )


def test_every_named_unscoped_read_is_still_a_real_read():
    reads = unscoped_source_reads()
    assert [key for key in UNSCOPED_READS if key not in reads] == []


# --- 3's fixture: a source its own chunks disagree with ----------------------------------

DOCUMENT_TITLE = "Directors' succession register"
DOCUMENT_TEXT = "The succession register names two candidates for the chair."
DOCUMENT_DEPARTMENT = "Board office"
MEETING_TITLE = "Nominations committee"
MEETING_TEXT = "The committee shortlisted succession candidates for the chair."
# In both chunks' text and in neither title, so the keyword search finds the items through
# the chunk branch — the branch whose stamp is the one that disagrees.
SEARCH_TERM = "succession"
QUESTION = "Who are the succession candidates for the chair?"

NEAREST = 0.95
assert RELEVANCE_THRESHOLD < NEAREST - 0.05


def _wide(*components) -> list[float]:
    return list(components) + [0.0] * (settings.EMBEDDING_DIMENSION - len(components))


QUERY = _wide(1.0)


def _at_cosine(value: float) -> list[float]:
    return _wide(value, sqrt(1.0 - value * value))


def _chunk(*, source_type, source_id, text, cosine):
    return ContentChunk.objects.create(
        source_type=source_type,
        source_id=source_id,
        chunk_index=0,
        chunk_text=text,
        embedding=_at_cosine(cosine),
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )


@dataclass
class Disagreement:
    document: Document
    meeting: Meeting

    @property
    def traces(self) -> tuple[str, ...]:
        """What an Employee's bytes must never carry: each source's title and identifier.

        Not the chunk identifiers and not the passage text: the chunk stamp admits those to
        the Employee, so the answer path legitimately sends them (see the module docstring).
        """
        return (
            DOCUMENT_TITLE,
            DOCUMENT_DEPARTMENT,
            str(self.document.id),
            MEETING_TITLE,
            str(self.meeting.id),
        )

    def disclosed_in(self, response) -> bool:
        raw = response.content.decode()
        return any(trace in raw for trace in self.traces)


@pytest.fixture
def disagreement(administrator):
    document = Document.objects.create(
        title=DOCUMENT_TITLE,
        file_type="pdf",
        uploaded_by=administrator,
        department=DOCUMENT_DEPARTMENT,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )
    meeting = Meeting.objects.create(
        title=MEETING_TITLE,
        meeting_date=date(2026, 9, 1),
        transcript_text=MEETING_TEXT,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )
    chunks = [
        _chunk(source_type=DOCUMENT_SOURCE_TYPE, source_id=document.id, text=DOCUMENT_TEXT, cosine=NEAREST),
        _chunk(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id, text=MEETING_TEXT, cosine=NEAREST - 0.05),
    ]
    # The disagreement. ``ContentChunk`` has a plain manager, so this widens the chunks and
    # cascades nowhere: the sources still say Administrator-only.
    ContentChunk.objects.filter(id__in=[chunk.id for chunk in chunks]).update(visible_to_roles=BOTH_ROLES)

    # The premise, asserted rather than assumed: the chunk predicate admits the Employee and
    # the source predicate does not. Without both halves the tests below test nothing.
    assert {chunk.id for chunk in chunks} <= set(
        scoped_chunks(role_name=EMPLOYEE_ROLE_NAME).values_list("id", flat=True)
    )
    assert not scoped_documents(role_name=EMPLOYEE_ROLE_NAME).filter(id=document.id).exists()
    assert not scoped_meetings(role_name=EMPLOYEE_ROLE_NAME).filter(id=meeting.id).exists()
    return Disagreement(document=document, meeting=meeting)


class _CitingService:
    """A double: the query vector is QUERY, and the reply cites the first passage supplied."""

    def embed(self, texts, *, input_type=None):
        return EmbeddingResult(
            vectors=[list(QUERY)], model=STUB_EMBEDDING_MODEL, dimension=settings.EMBEDDING_DIMENSION
        )

    def generate_statements(self, question, passages):
        return StatementList(
            statements=[Statement(text="A grounded statement.", chunk_id=passages[0].chunk_id)]
        )

    def health(self):  # pragma: no cover - the answer path does not check provider health
        raise AssertionError("not called")


# --- 2 and 3. Every route classified, and each source-returning route probed --------------
#
# A probe returns True when the response discloses the disagreeing source to the caller.


def _lists(url):
    def probe(client, case, monkeypatch):
        return case.disclosed_in(client.get(url))

    return probe


def _is_found(url_of, method="get"):
    def probe(client, case, monkeypatch):
        response = getattr(client, method)(url_of(case))
        # 404 is the only answer that says nothing: any other status confirms the id is real.
        return response.status_code != 404

    return probe


def _store_an_original(document):
    """Give the fixture's document a stored original, which it is created without.

    Without one, the download's Administrator mirror would be the missing-file 404 and the
    download probe would prove nothing. ``update_fields`` names only ``file_path``, so the save
    re-stamps no chunk (D-47) and the disagreement stands; the probe asserts that it does.
    """
    if not document.file_path:
        document.file_path.save("register.txt", ContentFile(DOCUMENT_TEXT.encode()), save=False)
        document.save(update_fields=["file_path"])


def _downloads(client, case, monkeypatch):
    """FR-15's download (D-75) returns the original's bytes and can consult only the document's
    own stamp, because the original is one file: exactly the case this fixture builds."""
    _store_an_original(case.document)
    # The premise, still: the Employee's chunk predicate admits this document's chunk.
    assert scoped_chunks(role_name=EMPLOYEE_ROLE_NAME).filter(source_id=case.document.id).exists()
    response = client.get(f"/api/documents/{case.document.id}/download")
    if response.streaming:
        # Read to the end, which closes the response and the stored file it holds open.
        assert b"".join(response.streaming_content) == DOCUMENT_TEXT.encode()
    # 404 is the only answer that says nothing; any other status confirms the id is real.
    return response.status_code != 404


def _searches(client, case, monkeypatch):
    return case.disclosed_in(client.get("/api/search", {"q": SEARCH_TERM}))


def _asks(client, case, monkeypatch):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: _CitingService())
    response = client.post("/api/ask", {"question": QUESTION}, format="json")
    assert response.status_code == 200
    return case.disclosed_in(response)


def _reopens(client, case, monkeypatch):
    """FR-13's reopened thread carries each answered turn's Sources panel since D-78, built by
    the live reply's ``resolve_sources`` and so failing closed in the same place. The turn is
    asked through the real route and then read back; only the read is probed."""
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: _CitingService())
    created = client.post("/api/conversations", {}, format="json")
    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]
    asked = client.post(
        "/api/ask", {"question": QUESTION, "conversation_id": conversation_id}, format="json"
    )
    assert asked.status_code == 200
    response = client.get(f"/api/conversations/{conversation_id}")
    assert response.status_code == 200
    # The premise: the chunk stamp admits this caller, so the turn renders as answered and its
    # panel is built, rather than skipped as a re-scoped turn's would be.
    [turn] = response.json()["turns"]
    assert turn["answered"] is True
    return case.disclosed_in(response)


# A Project tag carried only by the disagreeing document. FR-15's facets would offer it if they
# were read from the Tags table or from tag links not narrowed to the scoped documents (D-72).
DOCUMENT_TAG = "succession register review"


def _browses(client, case, monkeypatch):
    tag, _ = Tag.objects.get_or_create(tag_name=DOCUMENT_TAG, dimension="Project")
    ContentTag.objects.get_or_create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=case.document.id,
        defaults={"applied_by": "user", "confirmed": True},
    )
    response = client.get("/api/documents/browse")
    assert response.status_code == 200  # no filter set, so never the 204
    return case.disclosed_in(response) or DOCUMENT_TAG in response.content.decode()


# FR-10's routes (D-105) act on a document by id, so each is a status-code probe like the delete:
# 404 says nothing, anything else confirms the id is real. Each probe first gives the disagreeing
# document what its route acts on (an analysis, a proposal, a tag link), so that the
# Administrator's mirror reaches the work and answers non-404, and the Employee's 404 can only be
# the scope's. contribute_content is held by both roles, so the Employee's 404 is not a 403 hidden
# behind one: it is resolved before the permission (D-73's order).
PROPOSED_TOPIC = "succession planning"
# The proposed-tags routes' body (D-128): the proposal's dimension and value.
PROPOSAL_BODY = {"dimension": "Topic", "value": PROPOSED_TOPIC}


def _classified(document) -> DocumentAnalysis:
    analysis, _ = DocumentAnalysis.objects.get_or_create(
        document=document,
        defaults={
            "classified_at": timezone.now(),
            "proposed_tags": [{"dimension": "Topic", "value": PROPOSED_TOPIC, "confidence": 0.8}],
        },
    )
    return analysis


def _linked(document) -> ContentTag:
    tag, _ = Tag.objects.get_or_create(tag_name=DOCUMENT_TAG, dimension="Project")
    link, _ = ContentTag.objects.get_or_create(
        tag=tag, source_type=DOCUMENT_SOURCE_TYPE, source_id=document.id,
        defaults={"applied_by": "ai", "confirmed": False, "provisional": True},
    )
    return link


def _acts_on(method, path, body=None, prepare=None):
    def probe(client, case, monkeypatch):
        if prepare is not None:
            prepare(case.document)
        url = f"/api/documents/{case.document.id}/{path(case)}"
        response = getattr(client, method)(url, body or {}, format="json")
        return response.status_code != 404

    return probe


ROUTES_RETURNING_SOURCE_ROWS = {
    ("api/documents", "GET"): _lists("/api/documents"),
    ("api/documents/<uuid:pk>", "GET"): _is_found(lambda case: f"/api/documents/{case.document.id}"),
    ("api/documents/<uuid:pk>/reprocess", "POST"): _is_found(
        lambda case: f"/api/documents/{case.document.id}/reprocess", method="post"
    ),
    ("api/meetings", "GET"): _lists("/api/meetings"),
    ("api/meetings/<uuid:pk>", "GET"): _is_found(lambda case: f"/api/meetings/{case.meeting.id}"),
    ("api/search", "GET"): _searches,
    # The Sources panel and the partial matches: the route D-53 found failing open.
    ("api/ask", "POST"): _asks,
    # FR-13's reopened thread: the same Sources panel, rebuilt on every read (D-78).
    ("api/conversations/<uuid:pk>", "GET"): _reopens,
    # FR-14: recent documents and meetings, and the offered departments, which would carry the
    # disagreeing document's "Board office" if they were read from anything but the scoped rows.
    ("api/dashboard", "GET"): _lists("/api/dashboard"),
    # FR-15: the documents, the department facet ("Board office") and a tag facet (D-72).
    ("api/documents/browse", "GET"): _browses,
    # FR-15's delete returns no row, but its status code is one: 404 says nothing, while 403 or
    # 204 confirms the id is real. Scope is resolved before the permission (D-73), so the
    # Employee, who also lacks manage_documents, must get 404; the Administrator's mirror is the
    # 204, and the document is then deleted.
    ("api/documents/<uuid:pk>", "DELETE"): _is_found(
        lambda case: f"/api/documents/{case.document.id}", method="delete"
    ),
    # FR-15's download (D-75): the stored original, scoped by the document's own stamp alone.
    ("api/documents/<uuid:pk>/download", "GET"): _downloads,
    # Meeting deletion (D-99), the same as the document delete's: scope before manage_meetings,
    # so the Employee gets 404 and the Administrator's mirror is the 204.
    ("api/meetings/<uuid:pk>", "DELETE"): _is_found(
        lambda case: f"/api/meetings/{case.meeting.id}", method="delete"
    ),
    # FR-10 (D-105). Classify: the document has no extracted text, so the Administrator's mirror is
    # the 422, which no provider call precedes; the Employee's answer is the scope's 404.
    ("api/documents/<uuid:pk>/classify", "POST"): _acts_on("post", lambda case: "classify"),
    ("api/documents/<uuid:pk>/classification", "POST"): _acts_on(
        "post", lambda case: "classification", prepare=_classified
    ),
    ("api/documents/<uuid:pk>/tags/<uuid:content_tag_id>/confirm", "POST"): _acts_on(
        "post", lambda case: f"tags/{_linked(case.document).id}/confirm"
    ),
    ("api/documents/<uuid:pk>/tags/<uuid:content_tag_id>", "DELETE"): _acts_on(
        "delete", lambda case: f"tags/{_linked(case.document).id}"
    ),
    ("api/documents/<uuid:pk>/proposed-tags/confirm", "POST"): _acts_on(
        "post", lambda case: "proposed-tags/confirm", body=PROPOSAL_BODY, prepare=_classified,
    ),
    ("api/documents/<uuid:pk>/proposed-tags/reject", "POST"): _acts_on(
        "post", lambda case: "proposed-tags/reject", body=PROPOSAL_BODY, prepare=_classified,
    ),
    # A person applies a tag (D-105's dated note of 10 November 2026, night): a new Topic, so the
    # Administrator's mirror is the 201 and the Employee's answer is the scope's 404.
    ("api/documents/<uuid:pk>/tags", "POST"): _acts_on(
        "post", lambda case: "tags", body={"dimension": "Topic", "tag_name": "board succession"}
    ),
}

ROUTES_RETURNING_NO_SOURCE_ROWS = {
    ("api/", "GET"): "DRF's API root: a map of router routes, of which there are none.",
    ("api/auth/register", "POST"): "Users only.",
    ("api/auth/login", "POST"): "Users only.",
    ("api/auth/logout", "POST"): "A confirmation message.",
    ("api/auth/me", "GET"): "The caller's own user row.",
    ("api/roles", "GET"): "Roles and their permission codes.",
    ("api/users", "GET"): "Users and roles (FR-05).",
    ("api/users/directory", "GET"): "Names and addresses (D-34).",
    ("api/users/<uuid:pk>/role", "PATCH"): "The updated user.",
    ("api/documents", "POST"): (
        "Returns the document the caller has just uploaded, which D-29 places inside the "
        "caller's own scope. Its 409 duplicate check is the cross-scope existence oracle D-33 "
        "records and accepts, named in UNSCOPED_READS above."
    ),
    ("api/meetings", "POST"): (
        "Returns the meeting the caller has just ingested, which D-29 places inside the "
        "caller's own scope."
    ),
    ("api/conversations", "GET"): "The caller's own threads: titles they wrote or asked.",
    ("api/conversations", "POST"): "The new thread.",
    # FR-19 (D-107). An entry's subject is a question someone typed, not a source row, and no
    # route here reads Document or Meeting rows; the cycle reads chunks only through
    # candidate_chunks and search_total, which are the scoped helpers.
    ("api/knowledge-gaps", "GET"): "Gap entries: a subject, a count, a status and two dates.",
    ("api/knowledge-gaps/cycles", "POST"): "The cycle row: its times and four counts.",
    ("api/knowledge-gaps/<uuid:pk>", "PATCH"): "The updated gap entry.",
    # FR-10's tag administration (D-119 finding 5), Administrator-only through manage_tags. Tag rows
    # and counts of the sources carrying them, read by a role that reads every source (D-66); no
    # Document or Meeting row is read or returned.
    ("api/tags", "GET"): "Tags and their counts of sources, for the Administrator alone.",
    # D-128: an Administrator adds a value; the 201 is the new tag's entry, and the 409 names the
    # existing tag's id, which the inventory above already lists to the same reader.
    ("api/tags", "POST"): "The new tag's entry, or the id of the tag already holding the name.",
    ("api/tags/<uuid:pk>", "DELETE"): "The retired tag's entry, or nothing.",
    # Recording transcription (D-123). No transcription route reads a Document, a Meeting or a
    # chunk, or stores anything: a transcript enters the knowledge base only through
    # POST /api/meetings, classified above.
    ("api/transcriptions/status", "GET"): "Two flags and the two segment lengths.",
    ("api/transcriptions", "POST"): (
        "The text of the audio segment the caller has just sent, and that segment's length and level."
    ),
}


def test_every_route_is_classified_by_whether_it_returns_source_rows():
    routes = {endpoint.key for endpoint in enumerate_endpoints()}
    returning = set(ROUTES_RETURNING_SOURCE_ROWS)
    not_returning = set(ROUTES_RETURNING_NO_SOURCE_ROWS)
    assert returning & not_returning == set()
    assert routes - returning - not_returning == set(), (
        "A route is in neither table. Decide whether it returns Document or Meeting rows; if "
        "it does, give it a probe here."
    )
    assert (returning | not_returning) - routes == set(), "A classified route no longer exists."


@pytest.mark.django_db
@pytest.mark.parametrize("route", sorted(ROUTES_RETURNING_SOURCE_ROWS), ids=" ".join)
def test_a_source_its_chunks_disagree_with_is_withheld_from_an_employee(
    employee_client, disagreement, monkeypatch, route
):
    assert ROUTES_RETURNING_SOURCE_ROWS[route](employee_client, disagreement, monkeypatch) is False


@pytest.mark.django_db
@pytest.mark.parametrize("route", sorted(ROUTES_RETURNING_SOURCE_ROWS), ids=" ".join)
def test_the_same_source_is_returned_to_the_administrator_it_admits(
    administrator_client, disagreement, monkeypatch, route
):
    """The mirror of the test above, so a route that discloses nothing to anybody fails."""
    assert ROUTES_RETURNING_SOURCE_ROWS[route](administrator_client, disagreement, monkeypatch) is True


@pytest.mark.django_db
def test_an_unknown_identifier_is_answered_exactly_as_the_withheld_one_is(employee_client, disagreement):
    """404 for the withheld source and for an identifier that names nothing: one answer."""
    for template in ("/api/documents/{}", "/api/meetings/{}"):
        unknown = employee_client.get(template.format(uuid.uuid4()))
        assert unknown.status_code == 404
    assert employee_client.get(f"/api/documents/{disagreement.document.id}").content == (
        employee_client.get(f"/api/documents/{uuid.uuid4()}").content
    )
    # FR-15's delete, the same: one 404 body, and the withheld document is still there.
    withheld = employee_client.delete(f"/api/documents/{disagreement.document.id}")
    assert withheld.status_code == 404
    assert withheld.content == employee_client.delete(f"/api/documents/{uuid.uuid4()}").content
    assert Document.objects.filter(pk=disagreement.document.id).exists()
    # FR-15's download (D-75), the same, with the withheld document's original really stored, so
    # the 404 is the scope's and not the missing file's.
    _store_an_original(disagreement.document)
    withheld = employee_client.get(f"/api/documents/{disagreement.document.id}/download")
    unknown = employee_client.get(f"/api/documents/{uuid.uuid4()}/download")
    assert withheld.status_code == unknown.status_code == 404
    assert withheld.content == unknown.content
    # Meeting deletion (D-99), the same: one 404 body, and the withheld meeting is still there.
    withheld = employee_client.delete(f"/api/meetings/{disagreement.meeting.id}")
    unknown = employee_client.delete(f"/api/meetings/{uuid.uuid4()}")
    assert withheld.status_code == unknown.status_code == 404
    assert withheld.content == unknown.content
    assert Meeting.objects.filter(pk=disagreement.meeting.id).exists()
