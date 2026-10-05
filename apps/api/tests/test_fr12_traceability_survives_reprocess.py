"""FR-12's traceability clause holds after a reprocess and after a re-index (D-67).

    The question, the retrieved chunk identifiers, the answer and its verified citations
    are logged, so that any answer can later be traced to the material that produced it.

**What this file used to pin, recorded rather than quietly replaced.** Until Stage 5 item 1a
this was ``test_fr12_traceability_lost_on_reprocess.py``, and it asserted the LOSS:
``AnswerCitation.chunk`` was ``on_delete=CASCADE`` (D-12), and both ``reprocess_document``
(FR-08's "Please try again", reachable at ``POST /api/documents/{id}/reprocess`` and gated on
``contribute_content``, which D-30 gives BOTH roles) and ``manage.py reindex`` delete a
source's chunks and write new ones with fresh UUIDs. Every ``AnswerCitation`` row citing the
old chunks was deleted with them, while the ``QueryLog`` row survived still saying
``answered = True``, still carrying its ``answer_text``, and still carrying
``retrieved_chunk_ids`` that named no row at all. It asserted a citation count of 0 on
purpose, modelled on ``apps/core/tests/test_visibility_cascade.py::
test_bulk_create_upsert_is_a_known_hole_and_does_not_cascade``, so that a fix would fail it and
the failure would be the notification. D-48's 27 September qualification and D-61's gap 5
are the records of that finding.

**The fix, and the notification it produced.** Retrieval migration 0003 makes the foreign key
``on_delete=SET_NULL`` and adds ``chunk_uuid``, which ``record_query`` writes with the same
UUID as ``chunk_id`` (D-67). Before this file was rewritten, its old text was run against the
changed code, and every one of its tests failed at the citation count, ``assert 1 == 0``: the
row it expected to be gone was still there. The tests below assert what now happens instead.
The citation rows survive with ``chunk`` NULL and ``chunk_uuid`` equal to the identifier they
cited. The ``QueryLog`` row is untouched, column for column. So an answer can still be traced
to the identifiers of the material that produced it after that material's chunks are gone.

**D-12's reasoning about FR-15 still stands for the material, and it no longer reaches the
record.** "With the chunk gone the citation has nothing to cite" is true of what a reader may
be shown, and the reopened-turn serializer reads a NULL-chunk row as if it had been deleted
(``apps/api/tests/test_null_chunk_citations_on_a_reopened_turn.py``). It is not true of the
audit trail, which is what FR-12's traceability clause is about.

**These assertions are about the ROWS and not about how a thread renders.** Rendering is
asserted in ``test_provenance_removed_turn.py`` and
``test_null_chunk_citations_on_a_reopened_turn.py``, so nothing here reads a serialized turn.

**What this file does not cover.**

- **FR-15's document deletion.** It is not built (Stage 5 item 2). It deletes chunks through
  the same foreign key, so the same SET_NULL applies; item 2 tests its own path.
- **A meeting.** ``reindex`` rebuilds meeting chunks the same way, through the same foreign
  key, so the same survival follows; only the document paths are exercised here.
- **An ``Indexed`` document reached through the reprocess route.** The view answers 409 for
  that status, so the reachable route to the endpoint is a document that did not fully index
  — "Partially indexed" below. ``manage.py reindex`` has no such guard and reaches an
  ``Indexed`` document, which is the second test.
- **Resolving ``chunk_uuid`` to the new chunk.** Nothing does, and nothing should: a re-index
  is not guaranteed to reproduce the same chunk boundaries, so "the chunk that replaced it"
  is not a fact the record holds. The identifier traces the answer to what it cited, at the
  time it cited it.
"""

from collections import Counter

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

import apps.ai
from apps.ai.base import (
    EmbeddingResult,
    ProviderUnavailable,
    Statement,
    StatementList,
)
from apps.ai.prefixes import document_text
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    DOCUMENT_INDEXED,
    DOCUMENT_PARTIALLY_INDEXED,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.retrieval.models import AnswerCitation, QueryLog

pytestmark = pytest.mark.django_db

DOCUMENTS_URL = "/api/documents"
ASK_URL = "/api/ask"
DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]

DOCUMENT_TITLE = "Leave Policy 2026"
QUESTION = "How much annual leave do I accrue each year?"
ANSWER_STATEMENT = "Staff accrue twenty days of annual leave a year."

# The chunk scripted to fail. A document must reach "Partially indexed" for the reprocess
# route to accept it at all, and one failing chunk of several is the only way there
# (apps/ingestion/documents.py, section 7.8 lines 89-96).
FAILING_CHUNK_FIRST_WORD = "clause450"


def long_text_file():
    """~1200 words, which is about three chunks at CHUNK_SIZE 500 with CHUNK_OVERLAP 50.

    Several chunks are needed so that one of them can fail while another succeeds. The same
    construction ``test_document_indexing.py`` uses for the partially-indexed case.
    """
    words = " ".join(f"clause{n}" for n in range(1200))
    return SimpleUploadedFile("long.txt", words.encode("utf-8"), content_type="text/plain")


class OneVectorService:
    """One fixed vector for every text, and one statement citing the best-ranked passage.

    Every chunk therefore scores 1.0 against the question, so the corpus is answerable
    without a test having to predict a similarity score, and ``embedding_model`` matches
    between the chunks and the query because both come from here (risk R10's predicate in
    ``candidate_chunks``).

    ``fail_for`` selects chunks whose embedding never succeeds, which is how the upload
    lands on "Partially indexed"; the reprocess below installs one with no failures, which
    is D-32's real recovery case — the provider was down and is now back.
    """

    def __init__(self, *, fail_for=None):
        self.fail_for = fail_for if fail_for is not None else (lambda text: False)
        self.embed_calls = []
        self.attempts = Counter()

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        self.attempts[texts[0]] += 1
        if any(self.fail_for(text) for text in texts):
            raise ProviderUnavailable("scripted outage for one chunk")
        vector = [1.0] + [0.0] * (settings.EMBEDDING_DIMENSION - 1)
        return EmbeddingResult(
            vectors=[list(vector) for _ in texts],
            model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        return StatementList(
            statements=[Statement(text=ANSWER_STATEMENT, chunk_id=passages[0].chunk_id)]
        )

    def health(self):  # pragma: no cover - the answer path does not check provider health
        raise AssertionError("the answer path does not check provider health")


def install(monkeypatch, service):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
    return service


def fails_the_scripted_chunk(text):
    """Matches the prefixed string the provider is handed, not the stored chunk text."""
    return text.startswith(document_text(DOCUMENT_TITLE, f"{FAILING_CHUNK_FIRST_WORD} "))


def chunk_ids_for(doc_id):
    return set(
        ContentChunk.objects.filter(
            source_type=DOCUMENT_SOURCE_TYPE, source_id=doc_id
        ).values_list("id", flat=True)
    )


def columns_of(row):
    """Every column of a row, by attribute name, so "untouched" means every one of them."""
    return {field.attname: getattr(row, field.attname) for field in type(row)._meta.fields}


def upload_and_ask(client, monkeypatch, *, fail_a_chunk):
    """An answered turn, cited, over a document uploaded through the API.

    Both halves go through HTTP: FR-08's upload writes the chunks and FR-12's answer path
    writes the ``QueryLog`` row and its ``AnswerCitation`` rows. Nothing is constructed in
    the database directly, because the finding is about two shipped routes meeting.
    """
    install(monkeypatch, OneVectorService(fail_for=fails_the_scripted_chunk if fail_a_chunk else None))
    uploaded = client.post(
        DOCUMENTS_URL, {"file": long_text_file(), "title": DOCUMENT_TITLE}, format="multipart"
    )
    assert uploaded.status_code == 201
    expected_status = DOCUMENT_PARTIALLY_INDEXED if fail_a_chunk else DOCUMENT_INDEXED
    assert uploaded.data["status"] == expected_status
    doc_id = uploaded.data["doc_id"]

    answer = client.post(ASK_URL, {"question": QUESTION}, format="json")
    assert answer.status_code == 200
    body = answer.json()
    assert body["answered"] is True
    [statement] = body["statements"]
    assert statement["text"] == ANSWER_STATEMENT

    turn = QueryLog.objects.get()
    assert turn.answered is True
    [citation] = AnswerCitation.objects.filter(query=turn)
    # The traceability record as written: every identifier it names exists, and the
    # citation names its chunk in both columns, with one value (record_query, D-67).
    assert turn.retrieved_chunk_ids
    assert ContentChunk.objects.filter(id__in=turn.retrieved_chunk_ids).count() == len(
        turn.retrieved_chunk_ids
    )
    assert citation.chunk_id is not None
    assert citation.chunk_uuid == citation.chunk_id
    assert str(citation.chunk_id) == statement["chunk_id"]
    return doc_id, turn, citation


def assert_the_citations_survive_their_chunks(turn, citation, *, doc_id, chunk_ids_before):
    """What D-67 changes, asserted on the rows.

    The citation row is the same row: same primary key, same statement, same position. Its
    ``chunk_id`` is NULL because the chunk is gone, and its ``chunk_uuid`` is still the
    identifier it cited, which is also one of the identifiers on the ``QueryLog`` row. The
    ``QueryLog`` row is identical in every column. The material itself is still in the
    corpus under new identifiers, which is what separates a reprocess or a re-index from
    FR-15's deletion.
    """
    [after] = AnswerCitation.objects.filter(query=turn)
    assert after.pk == citation.pk
    assert after.chunk_id is None  # the chunk was deleted, and the foreign key says so
    assert after.chunk_uuid == citation.chunk_id  # the identifier it cited is kept
    assert after.statement_text == citation.statement_text
    assert after.position == citation.position

    # The QueryLog row is untouched, every column of it.
    assert columns_of(QueryLog.objects.get(pk=turn.pk)) == columns_of(turn)

    # "so that any answer can later be traced to the material that produced it": the
    # citation and the log row still agree about which identifier that was, and the
    # identifier is one the source carried before the operation.
    assert after.chunk_uuid in turn.retrieved_chunk_ids
    assert after.chunk_uuid in chunk_ids_before
    # It names a chunk that no longer exists, which is why chunk_id is NULL: the record
    # traces to an identifier, and the identifier resolves to nothing.
    assert not ContentChunk.objects.filter(id=after.chunk_uuid).exists()

    # And the material was never deleted. New rows, new identifiers, same passages.
    chunk_ids_after = chunk_ids_for(doc_id)
    assert chunk_ids_after
    assert chunk_ids_after.isdisjoint(chunk_ids_before)
    assert Document.objects.filter(pk=doc_id).exists()


def test_a_reprocess_keeps_the_citations_of_every_answer_drawn_from_the_document(
    session_client, monkeypatch
):
    """``POST /api/documents/{id}/reprocess``, from an Employee session and an Administrator
    session — D-30 gives ``contribute_content`` to both roles, so either can reach it.

    The sequence is one a user performs on purpose: a document did not fully index, somebody
    asked a question it answered, and somebody then pressed FR-08's "Please try again". The
    retry succeeds, which is D-32's real recovery case. Before D-67 it took the provenance of
    the earlier answer with it; now the provenance stays.
    """
    client = session_client.client
    doc_id, turn, citation = upload_and_ask(client, monkeypatch, fail_a_chunk=True)
    chunk_ids_before = chunk_ids_for(doc_id)

    # The provider has recovered, so this reprocess indexes every chunk.
    install(monkeypatch, OneVectorService())
    reprocessed = client.post(f"{DOCUMENTS_URL}/{doc_id}/reprocess", {}, format="json")

    assert reprocessed.status_code == 201
    assert reprocessed.data["status"] == DOCUMENT_INDEXED
    assert_the_citations_survive_their_chunks(
        turn, citation, doc_id=doc_id, chunk_ids_before=chunk_ids_before
    )


def test_a_re_index_keeps_them_too_and_it_is_the_documented_happy_path(
    employee_client, monkeypatch
):
    """``manage.py reindex`` — CLAUDE.md section 4: switching provider or embedding model is
    a full re-index event, and this command is how that switch is a supported operation.

    An entirely healthy ``Indexed`` document, re-indexed exactly as the documentation
    instructs, used to lose the provenance of every answer ever drawn from it. The reprocess
    route refuses an ``Indexed`` document; this one does not, which is why both are asserted.
    """
    doc_id, turn, citation = upload_and_ask(employee_client, monkeypatch, fail_a_chunk=False)
    chunk_ids_before = chunk_ids_for(doc_id)

    call_command("reindex")

    assert Document.objects.get(pk=doc_id).status == DOCUMENT_INDEXED
    assert_the_citations_survive_their_chunks(
        turn, citation, doc_id=doc_id, chunk_ids_before=chunk_ids_before
    )
