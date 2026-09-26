"""ingest_and_index_document() (proposal section 7.8, FR-08).

The pipeline at its own level: the statuses section 7.8 assigns, the
insufficient-content guard, and the NFR-21 transaction. The same journey through the
HTTP endpoint is apps/api/tests/, which is the coordinator's.

Every test uses the media_root fixture, so uploads are written into the test's own
temporary directory and "the stored file was removed" means something.
"""

import pytest

from apps.ai.prefixes import document_text
from apps.core.constants import (
    DOCUMENT_INDEXED,
    DOCUMENT_INDEXING_FAILED,
    DOCUMENT_INSUFFICIENT_CONTENT,
    DOCUMENT_PARTIALLY_INDEXED,
    DOCUMENT_STATUS_VALUES,
    DOCUMENT_TOO_LARGE_TO_INDEX,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_CHUNKS_PER_SOURCE,
    MAXIMUM_EMBED_ATTEMPTS,
    MINIMUM_CONTENT_LENGTH,
)
from apps.documents.models import ContentChunk, Document, ExtractedContent
from apps.ingestion.chunking import length_in_tokens, split_into_overlapping_chunks
from apps.ingestion.documents import TOO_MANY_CHUNKS_MESSAGE, ingest_and_index_document
from apps.ingestion.embedding import DOCUMENT_SOURCE_TYPE
from apps.ingestion.signatures import compute_content_hash
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install
from apps.ingestion.tests.builders import upload, words

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("media_root")]

# Comfortably above MINIMUM_CONTENT_LENGTH and below CHUNK_SIZE: one chunk.
ONE_CHUNK_TEXT = words(120)
# Two chunks, and the second is the only one ending in "w500", which is how a test
# fails exactly one chunk of a document (the "Partially indexed" case).
TWO_CHUNK_TEXT = words(501)
SECOND_CHUNK_MARKER = "w500"
DOCUMENT_TITLE = "Leave Policy 2026"


def sent(text):
    """What the provider receives for a chunk of this document: the document task
    prefix wraps it when the configured embedding model takes prefixes
    (apps/ai/prefixes.py). The stored chunk_text is asserted separately, and
    verbatim, in apps/ingestion/tests/test_embedding.py."""
    return document_text(DOCUMENT_TITLE, text)


def ingest(text=ONE_CHUNK_TEXT, *, user, roles=None, name="policy.txt"):
    """ingest_and_index_document() for a TXT upload of ``text``."""
    file = upload(text.encode("utf-8"), name)
    return ingest_and_index_document(
        uploaded_file=file,
        file_format="txt",
        content_hash=compute_content_hash(file),
        title=DOCUMENT_TITLE,
        department="People",
        visible_to_roles=roles if roles is not None else [EMPLOYEE_ROLE_NAME],
        uploaded_by=user,
    )


def fail_second_chunk_only(text):
    return text.rstrip().endswith(SECOND_CHUNK_MARKER)


# --- The happy path: indexed ---------------------------------------------------------


def test_a_document_is_extracted_chunked_embedded_and_indexed(employee, stub_ai_service):
    outcome = ingest(user=employee)

    assert outcome.http_status == 201
    assert outcome.document.status == DOCUMENT_INDEXED
    assert ExtractedContent.objects.get(document=outcome.document).extracted_text == ONE_CHUNK_TEXT
    chunks = ContentChunk.objects.filter(source_id=outcome.document.id)
    assert chunks.count() == 1
    assert stub_ai_service.embed_calls == [[sent(ONE_CHUNK_TEXT)]]


def test_chunks_are_keyed_to_the_document_and_carry_its_visibility(employee):
    """D-17: stamped at ingestion from the owning Document, so FR-11 can filter
    before ranking without a join."""
    outcome = ingest(TWO_CHUNK_TEXT, user=employee, roles=[EMPLOYEE_ROLE_NAME])

    chunks = ContentChunk.objects.filter(source_id=outcome.document.id).order_by("chunk_index")
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert {chunk.source_type for chunk in chunks} == {DOCUMENT_SOURCE_TYPE}
    assert all(chunk.visible_to_roles == [EMPLOYEE_ROLE_NAME] for chunk in chunks)
    # The stored chunk text is what the chunker produced, verbatim (D-31).
    assert [chunk.chunk_text for chunk in chunks] == [
        chunk.text for chunk in split_into_overlapping_chunks(TWO_CHUNK_TEXT)
    ]


# --- Partially indexed and indexing failed (section 7.8 lines 89-96, D-28) --------------


def test_some_chunks_failing_is_partially_indexed_and_still_a_201(employee, monkeypatch):
    install(
        monkeypatch,
        ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS, should_fail=fail_second_chunk_only),
    )

    outcome = ingest(TWO_CHUNK_TEXT, user=employee)

    assert outcome.http_status == 201
    assert outcome.document.status == DOCUMENT_PARTIALLY_INDEXED
    # The record is committed with the status that names the outcome; it is not a
    # half-written row, which is the distinction D-28 draws.
    assert Document.objects.get(pk=outcome.document.pk).status == DOCUMENT_PARTIALLY_INDEXED
    assert ContentChunk.objects.filter(source_id=outcome.document.id).count() == 1
    assert ExtractedContent.objects.filter(document=outcome.document).exists()


def test_every_chunk_failing_is_indexing_failed_and_a_422(employee, monkeypatch):
    install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))

    outcome = ingest(TWO_CHUNK_TEXT, user=employee)

    assert outcome.http_status == 422
    assert outcome.detail
    assert Document.objects.get(pk=outcome.document.pk).status == DOCUMENT_INDEXING_FAILED
    # And NOT the value Stage 4 item 12b added: "Indexing failed" is the ATTEMPTED outcome,
    # and this document was attempted — three embed calls per chunk, all of them refused.
    assert outcome.document.status != DOCUMENT_TOO_LARGE_TO_INDEX
    assert not ContentChunk.objects.filter(source_id=outcome.document.id).exists()
    # CLAUDE.md invariant 8 and NFR-20: a failed AI step never discards the source.
    # The original and its text both survive the failure.
    assert ExtractedContent.objects.filter(document=outcome.document).exists()
    assert outcome.document.file_path.storage.exists(outcome.document.file_path.name)


def test_a_transient_failure_costs_nothing_when_a_retry_succeeds(employee, monkeypatch):
    service = install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS - 1))

    outcome = ingest(user=employee)

    assert outcome.document.status == DOCUMENT_INDEXED
    assert service.attempts_for(sent(ONE_CHUNK_TEXT)) == MAXIMUM_EMBED_ATTEMPTS == 3


# --- Insufficient content (section 7.8 lines 46-53, D-31) ---------------------------------


def test_text_below_the_minimum_is_marked_and_never_embedded(employee, stub_ai_service):
    """FR-08: content below the threshold is marked "insufficient content" and is
    not submitted for embedding. A fragment embeds into an unreliable vector that
    would match unpredictably against every later query."""
    short_text = words(MINIMUM_CONTENT_LENGTH - 1)
    assert length_in_tokens(short_text) < MINIMUM_CONTENT_LENGTH

    outcome = ingest(short_text, user=employee)

    assert outcome.http_status == 422
    assert outcome.detail
    assert Document.objects.get(pk=outcome.document.pk).status == DOCUMENT_INSUFFICIENT_CONTENT
    # "Not submitted for embedding" is the clause, so no call was made at all.
    assert stub_ai_service.embed_calls == []
    assert not ContentChunk.objects.filter(source_id=outcome.document.id).exists()


def test_insufficient_content_writes_no_extracted_content_row(employee):
    """Section 7.8 returns at line 53, before CREATE ExtractedContent at line 58.
    Deliberate, and asserted here so it cannot be "tidied up" later: the file itself
    is kept and stays downloadable, and re-parsing it would produce the same text."""
    outcome = ingest(words(MINIMUM_CONTENT_LENGTH - 1), user=employee)

    assert not ExtractedContent.objects.filter(document=outcome.document).exists()
    assert outcome.document.file_path.storage.exists(outcome.document.file_path.name)


def test_text_exactly_at_the_minimum_is_indexed(employee):
    # The boundary is "below the minimum", so the minimum itself passes.
    at_the_line = words(MINIMUM_CONTENT_LENGTH)
    assert length_in_tokens(at_the_line) == MINIMUM_CONTENT_LENGTH

    outcome = ingest(at_the_line, user=employee)

    assert outcome.document.status == DOCUMENT_INDEXED


# --- NFR-21: ingestion is atomic ------------------------------------------------------------


def test_an_unexpected_failure_mid_ingestion_leaves_nothing_behind(
    employee, monkeypatch, media_root
):
    """CLAUDE.md invariant 9. The failure is raised from inside the embed call, so
    it happens on the real path with the document row, its text and its first chunk
    already written inside the transaction.

    RuntimeError rather than ProviderUnavailable on purpose: an outage is an outcome
    the pipeline decides about and commits a status for, while an unexpected
    exception is a defect and must leave no trace."""
    install(
        monkeypatch,
        ScriptedEmbedService(
            failures=1,
            should_fail=fail_second_chunk_only,
            error=RuntimeError("the provider client crashed"),
        ),
    )

    with pytest.raises(RuntimeError):
        ingest(TWO_CHUNK_TEXT, user=employee)

    assert not Document.objects.exists()
    assert not ExtractedContent.objects.exists()
    assert not ContentChunk.objects.exists()
    # A filesystem does not roll back with the database, so the stored original has
    # to be removed explicitly or it is an orphan nothing references.
    assert [path for path in media_root.rglob("*") if path.is_file()] == []


# --- MAXIMUM_CHUNKS_PER_SOURCE (Stage 4 item 12a) ---------------------------------------
#
# WHY THE CEILING EXISTS. Every chunk is a separate, sequential NPU embed call inside one
# ``transaction.atomic()`` block in one synchronous request. Measured: 2.4 MB of text yields
# 1,111 chunks, so a 50 MB TXT at MAX_UPLOAD_BYTES extrapolates to ~23,300 embed calls in one
# request — which Objective 02's "20 documents and a 20-page file in under 60 seconds" does
# not survive. ``apps/ingestion/tests/test_chunking.py`` checks the VALUE against those two
# figures; what is tested here is the BEHAVIOUR at the ceiling.
#
# The cap is patched down to a value the tests can reach in a second. A test that ingested
# 1,000 real chunks would take minutes and would assert nothing the patched version does not,
# and the arithmetic test above is what ties the shipped number to the measurements.


@pytest.fixture
def low_chunk_ceiling(monkeypatch):
    """MAXIMUM_CHUNKS_PER_SOURCE lowered to 1, where the guard reads it.

    Patched on ``apps.ingestion.documents`` rather than on ``apps.core.constants``, because
    the module imports the name at import time and that is the binding the guard resolves.
    """
    import apps.ingestion.documents as documents_module

    monkeypatch.setattr(documents_module, "MAXIMUM_CHUNKS_PER_SOURCE", 1)
    return 1


def test_a_document_over_the_chunk_ceiling_is_stored_and_not_indexed(
    employee, stub_ai_service, low_chunk_ceiling
):
    """422, the original kept, and NOT ONE EMBED CALL MADE.

    The last of those is the whole purpose of the guard: it is decided on the predicted chunk
    count, before the first call to the provider, so an oversized document costs extraction
    and chunking arithmetic and no NPU time at all. A guard that fired after the embedding
    loop would be a comment rather than a protection.

    Invariant 8 is the other half: a failed AI step never discards the source, and refusing
    to start one is no different — the file stays stored and downloadable, and the row carries
    a status saying why it is not searchable.
    """
    outcome = ingest(TWO_CHUNK_TEXT, user=employee)  # two chunks against a ceiling of one

    assert outcome.http_status == 422
    assert outcome.detail == TOO_MANY_CHUNKS_MESSAGE
    # Stage 4 item 12b: its own status, because nothing was attempted. Item 12a asserted
    # DOCUMENT_INDEXING_FAILED here, which claimed an attempt that the line below proves
    # was never made.
    assert outcome.document.status == DOCUMENT_TOO_LARGE_TO_INDEX
    assert stub_ai_service.embed_calls == []
    assert not ContentChunk.objects.filter(source_id=outcome.document.id).exists()
    # No 50 MB text column for a document nothing will index from: the same order the
    # insufficient-content branch uses.
    assert not ExtractedContent.objects.filter(document=outcome.document).exists()
    # The original is kept.
    assert outcome.document.file_path.storage.exists(outcome.document.file_path.name)
    # And the duplicate slot is released, as on every other 422, so the same file can be
    # uploaded again once it has been split up (D-32).
    assert outcome.document.content_hash is None


def test_a_document_at_the_chunk_ceiling_is_indexed_normally(
    employee, stub_ai_service, monkeypatch
):
    """The bound is inclusive: a document of exactly MAXIMUM_CHUNKS_PER_SOURCE chunks indexes.

    Asserted because the guard is a ``>`` and an off-by-one there would refuse a document the
    constant says is acceptable — the expensive direction to be wrong in, since the user's
    only remedy is to split the file.
    """
    import apps.ingestion.documents as documents_module

    monkeypatch.setattr(documents_module, "MAXIMUM_CHUNKS_PER_SOURCE", 2)

    outcome = ingest(TWO_CHUNK_TEXT, user=employee)

    assert outcome.http_status == 201
    assert outcome.document.status == DOCUMENT_INDEXED
    assert ContentChunk.objects.filter(source_id=outcome.document.id).count() == 2
    assert len(stub_ai_service.embed_calls) == 2


def test_the_ceiling_does_not_affect_an_ordinary_document(employee, stub_ai_service):
    """With the SHIPPED constant, the corpus this platform indexes is untouched.

    No patching here: a one-chunk document and a two-chunk document both index under
    MAXIMUM_CHUNKS_PER_SOURCE as it ships, which is the assertion that the ceiling is a
    protection against a pathological file rather than a limit users will meet.
    """
    assert MAXIMUM_CHUNKS_PER_SOURCE >= 1000  # the shipped value, not a patched one

    outcome = ingest(TWO_CHUNK_TEXT, user=employee)

    assert outcome.http_status == 201
    assert outcome.document.status == DOCUMENT_INDEXED


# --- The seventh status is distinct IN MEANING (Stage 4 item 12b) ------------------------
#
# Item 12a recorded an over-cap document as "Indexing failed", which in this vocabulary
# means "attempted, and every chunk failed to embed". Nothing was attempted. The overload
# was user-visible rather than untidy: FR-08's interface offers "Processing failed. Please
# try again" on that status, and a reprocess of an over-cap document fails identically every
# time — D-32 re-runs extraction and chunking in full on the stored original before failing
# at the same point. D-32's other retry cases MAY succeed; this one cannot.
#
# The two halves below are one test on purpose. Each status asserted alone would still pass
# if a later refactor collapsed them back into one value, and the pairing is the only thing
# that cannot.


def test_the_two_terminal_not_indexed_statuses_do_not_mean_the_same_thing(
    employee, stub_ai_service, monkeypatch
):
    """Refused before attempting, against attempted and failed, in one test.

    ``stub_ai_service.embed_calls`` is the evidence for the distinction rather than a detail
    of it: empty for the first document, three calls per chunk for the second. That is what
    "attempted" means here, and it is the difference the two status values carry.
    """
    import apps.ingestion.documents as documents_module

    # (a) Over MAXIMUM_CHUNKS_PER_SOURCE: refused before the first embed call.
    monkeypatch.setattr(documents_module, "MAXIMUM_CHUNKS_PER_SOURCE", 1)
    refused = ingest(TWO_CHUNK_TEXT, user=employee, name="too-big.txt")

    assert refused.document.status == DOCUMENT_TOO_LARGE_TO_INDEX
    assert refused.document.status != DOCUMENT_INDEXING_FAILED
    assert stub_ai_service.embed_calls == []  # never attempted

    # (b) Under the ceiling, and every chunk really did fail to embed.
    monkeypatch.setattr(documents_module, "MAXIMUM_CHUNKS_PER_SOURCE", MAXIMUM_CHUNKS_PER_SOURCE)
    failing = install(monkeypatch, ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS))
    attempted = ingest(ONE_CHUNK_TEXT, user=employee, name="unlucky.txt")

    assert attempted.document.status == DOCUMENT_INDEXING_FAILED
    assert attempted.document.status != DOCUMENT_TOO_LARGE_TO_INDEX
    assert failing.attempts_for(sent(ONE_CHUNK_TEXT)) == MAXIMUM_EMBED_ATTEMPTS  # attempted

    # Both are 422 and both keep the original (invariant 8). The STATUS is what tells them
    # apart, and after item 12b it does.
    assert refused.http_status == attempted.http_status == 422
    assert DOCUMENT_TOO_LARGE_TO_INDEX in DOCUMENT_STATUS_VALUES
    assert DOCUMENT_TOO_LARGE_TO_INDEX != DOCUMENT_INDEXING_FAILED
    # Named for what happened, with no claim that anything was tried: not a variant of
    # "failed", which is the word this value exists to stop being used loosely.
    assert "failed" not in DOCUMENT_TOO_LARGE_TO_INDEX.lower()
