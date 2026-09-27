"""FR-12's traceability clause holds at write time and not after a reprocess or a re-index.

    The question, the retrieved chunk identifiers, the answer and its verified citations
    are logged, so that any answer can later be traced to the material that produced it.

**That clause is satisfied when the row is written and falsified by two ordinary
operations afterwards.** ``AnswerCitation.chunk`` is ``on_delete=CASCADE``, and both
``reprocess_document`` (FR-08's "Please try again", reachable at
``POST /api/documents/{id}/reprocess`` and gated on ``contribute_content``, which D-30 gives
BOTH roles) and ``manage.py reindex`` delete a source's chunks and write new ones with fresh
UUIDs. Every ``AnswerCitation`` row citing the old chunks is deleted with them. The
``QueryLog`` row survives, still saying ``answered = True``, still carrying its
``answer_text`` and still carrying ``retrieved_chunk_ids`` — which now name no row in
``content_chunks`` at all. The answer can no longer be traced to the material that produced
it, and nothing in the record says so.

**D-12 settled the cascade, and it settled it about a different case.** Its reasoning is
FR-15's permissioned document deletion: "with the chunk gone the citation has nothing to
cite", and a citation row must not block deleting a document. That is true where the
material is genuinely gone. **Neither path here deletes material.** A reprocess re-extracts
and re-chunks the same stored original; a re-index re-embeds the same
``ExtractedContent.extracted_text``. The passage the answer was drawn from still exists,
word for word — it simply has a new identifier, and the citation that pointed at the old one
was destroyed rather than moved. CLAUDE.md section 4 mandates a full re-index on any provider
or embedding-model change, so this is the documented happy path and not an edge case.

**NO SCHEMA CHANGE IS BEING MADE BEFORE M6, and none is proposed here.** This file asserts
what the system actually does, so that it is asserted rather than assumed. The model-level
test ``apps/retrieval/tests/test_models.py::test_citation_cascades_when_its_chunk_is_deleted``
has asserted the same cascade since Stage 1 **as desirable behaviour** — which is precisely
why nobody connected it to FR-12's traceability clause. These tests are written at the FR
level, through the API, so the finding is recorded where the requirement lives. They are
modelled on ``apps/core/tests/test_visibility_cascade.py::
test_bulk_create_upsert_is_a_known_hole_and_does_not_cascade``: a test whose name says the
behaviour is known, asserting the current behaviour deliberately, so that a later fix fails
here and that failure is the notification.

**These assertions are about the DESTRUCTION OF THE ROWS and not about how a thread
renders.** The rendering is separated in Stage 4 item 1c — a turn whose citation rows are
gone stops claiming the question could not be answered — and this file must keep passing
across that change, so nothing here reads a serialized turn.

**What this file does not cover.**

- **FR-15's document deletion**, where the material really is gone and D-12's reasoning
  applies unchanged. That path is Stage 5 and is not the finding.
- **A meeting.** ``reindex`` rebuilds meeting chunks the same way and the cascade is the same
  column, so the same loss follows; only the document paths are exercised here.
- **An ``Indexed`` document reached through the reprocess route.** The view answers 409 for
  that status, so the reachable route to the endpoint is a document that did not fully index
  — "Partially indexed" below. ``manage.py reindex`` has no such guard and reaches an
  ``Indexed`` document, which is the second test.
- **Whether anything should be done about it.** Not a decision this file makes.
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
    assert AnswerCitation.objects.filter(query=turn).count() == 1
    # The traceability record as written: every identifier it names exists.
    assert turn.retrieved_chunk_ids
    assert ContentChunk.objects.filter(id__in=turn.retrieved_chunk_ids).count() == len(
        turn.retrieved_chunk_ids
    )
    return doc_id, turn


def assert_the_record_survives_without_its_citations(turn, *, doc_id, chunk_ids_before):
    """The finding, asserted as the behaviour it currently is.

    Four properties, and the pairing is the point: the citations are gone, the log row is
    not, the log row still says it was answered, and the identifiers it kept name nothing.
    The material itself is still here under new identifiers, which is what separates this
    from FR-15's deletion and from D-12's reasoning.
    """
    assert AnswerCitation.objects.filter(query=turn).count() == 0

    surviving = QueryLog.objects.get(pk=turn.pk)
    assert surviving.answered is True  # still claims an answer
    assert surviving.answer_text == turn.answer_text  # still carries the prose
    assert surviving.retrieved_chunk_ids == turn.retrieved_chunk_ids  # unchanged, and dangling

    # "so that any answer can later be traced to the material that produced it": it cannot.
    assert ContentChunk.objects.filter(id__in=surviving.retrieved_chunk_ids).count() == 0

    # And the material was never deleted. New rows, new identifiers, same passages.
    chunk_ids_after = chunk_ids_for(doc_id)
    assert chunk_ids_after
    assert chunk_ids_after.isdisjoint(chunk_ids_before)
    assert Document.objects.filter(pk=doc_id).exists()


def test_a_reprocess_destroys_the_citations_of_every_answer_drawn_from_the_document(
    session_client, monkeypatch
):
    """``POST /api/documents/{id}/reprocess``, from an Employee session and an Administrator
    session — D-30 gives ``contribute_content`` to both roles, so either can reach it.

    The sequence is one a user performs on purpose: a document did not fully index, somebody
    asked a question it answered, and somebody then pressed FR-08's "Please try again". The
    retry succeeds, which is D-32's real recovery case, and it takes the provenance of the
    earlier answer with it.
    """
    client = session_client.client
    doc_id, turn = upload_and_ask(client, monkeypatch, fail_a_chunk=True)
    chunk_ids_before = chunk_ids_for(doc_id)

    # The provider has recovered, so this reprocess indexes every chunk.
    install(monkeypatch, OneVectorService())
    reprocessed = client.post(f"{DOCUMENTS_URL}/{doc_id}/reprocess", {}, format="json")

    assert reprocessed.status_code == 201
    assert reprocessed.data["status"] == DOCUMENT_INDEXED
    assert_the_record_survives_without_its_citations(
        turn, doc_id=doc_id, chunk_ids_before=chunk_ids_before
    )


def test_a_re_index_destroys_them_too_and_it_is_the_documented_happy_path(
    employee_client, monkeypatch
):
    """``manage.py reindex`` — CLAUDE.md section 4: switching provider or embedding model is
    a full re-index event, and this command is how that switch is a supported operation.

    So the loss is not reached only by a retry on a document that failed. An entirely healthy
    ``Indexed`` document, re-indexed exactly as the documentation instructs, loses the
    provenance of every answer ever drawn from it. The reprocess route refuses an ``Indexed``
    document; this one does not, which is why both are asserted.
    """
    doc_id, turn = upload_and_ask(employee_client, monkeypatch, fail_a_chunk=False)
    chunk_ids_before = chunk_ids_for(doc_id)

    call_command("reindex")

    assert Document.objects.get(pk=doc_id).status == DOCUMENT_INDEXED
    assert_the_record_survives_without_its_citations(
        turn, doc_id=doc_id, chunk_ids_before=chunk_ids_before
    )
