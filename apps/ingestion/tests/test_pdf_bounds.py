"""D-81's PDF extraction bounds: the per-stream cap, the page cap, the operator budget,
the text ceiling, and the applied configuration.

The bomb PDFs are built in code (``apps/ingestion/tests/builders.py``), never committed as
binaries (Stage 4 item 12a's rule). Each bomb fixture is first PROVEN to parse — pypdf
returns "" for a page with no /Resources font WITHOUT reading its content, so a fixture
without one would pass every bound by never being read — and only then run against the
bound. Every bound is kept reachable in a fast test by patching its constant DOWN on the
extraction module, the way ``test_documents.py`` patches MAXIMUM_CHUNKS_PER_SOURCE; the
shipped values are too large to reach in a second and are asserted by the constants tests.
"""

import io
import time

import pypdf
import pytest

import apps.ingestion.extraction as extraction
from apps.core.constants import (
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_PDF_PAGES,
    PDF_MAXIMUM_OPERATORS,
    PDF_MAXIMUM_STORED_STREAM_BYTES,
    PDF_MAXIMUM_STREAM_BYTES,
)
from apps.documents.models import ContentChunk, ExtractedContent
from apps.ingestion.chunking import chunk_count_for_tokens, length_in_tokens
from apps.ingestion.documents import ingest_and_index_document, pdf_bound_detail
from apps.ingestion.errors import ExtractionError, TooLargeToExtractError
from apps.ingestion.extraction import (
    PDF_STREAM_TOO_LARGE_MESSAGE,
    PDF_TOO_MANY_OPERATORS_MESSAGE,
    PDF_TOO_MANY_PAGES_MESSAGE,
    _PDF_STORED_STREAM_LIMIT_FIELD,
    _PDF_STREAM_LIMIT_FIELDS,
    extract_plain_text,
)
from apps.ingestion.signatures import compute_content_hash
from apps.ingestion.tests.builders import (
    pdf_form_repeated,
    pdf_pages,
    pdf_shared_stream,
    pdf_with_embedded_font,
    pdf_with_image,
    repeated_operators,
    text_content,
    upload,
    words,
)


def count_operators(data: bytes) -> int:
    """Operators pypdf parses from ``data`` with no budget: the proof a fixture is real.

    A positive count means the page (or its form) carried a /Resources font and pypdf
    actually read the content stream. Used only on small fixtures, so it is cheap."""
    count = 0

    def visitor(operator, operands, cm, tm):
        nonlocal count
        count += 1

    reader = pypdf.PdfReader(io.BytesIO(data))
    for page in reader.pages:
        page.extract_text(visitor_operand_before=visitor)
    return count


# --- The crafted fixtures really are parsed (D-81's precondition) -----------------------


def test_a_bomb_page_is_actually_parsed():
    """``q Q`` repeated, with the font pypdf needs to read a content stream at all. If this
    is 0, every bound test below is proving nothing — see the module docstring."""
    assert count_operators(pdf_pages([repeated_operators(50)])) == 100


def test_a_bomb_form_is_actually_parsed():
    """The form carries its OWN /Resources font, or pypdf would not descend into it. One
    page draws a 20-operator form 3 times: 3 page-level Do, plus the form parsed 3 times."""
    assert count_operators(pdf_form_repeated(repeated_operators(10), 3)) == 3 + 3 * 20


def test_a_shared_stream_is_parsed_once_per_page():
    """Five pages naming one 20-operator stream: pypdf re-parses it per page, which is the
    work the per-document operator budget exists to bound."""
    assert count_operators(pdf_shared_stream(5, repeated_operators(10))) == 5 * 20


# --- The per-stream cap (D-81 item 1) ---------------------------------------------------


@pytest.fixture
def low_stream_cap(monkeypatch):
    monkeypatch.setattr(extraction, "PDF_MAXIMUM_STREAM_BYTES", 4096)
    return 4096


def test_a_page_over_the_stream_cap_is_refused_fast(low_stream_cap):
    """A single stream that decompresses to ~4 MB, against a 4 KB cap. pypdf stops
    decompression AT the cap and raises its own LimitReachedError, so the refusal is near
    instant rather than after inflating the whole stream — the measured 10 MB page took
    ~15 s to parse in full (D-81). Caught before the broad except and turned into the
    per-stream message."""
    data = pdf_pages([repeated_operators(1_000_000)])  # ~4 MB decompressed, tiny compressed

    start = time.perf_counter()
    with pytest.raises(TooLargeToExtractError) as caught:
        extract_plain_text(upload(data, "bomb.pdf"), "pdf")
    elapsed = time.perf_counter() - start

    assert caught.value.limit_message == PDF_STREAM_TOO_LARGE_MESSAGE
    assert elapsed < 10  # generous; the point is it does not inflate ~4 MB first


def test_the_stream_cap_is_a_too_large_error_not_a_plain_extraction_failure(low_stream_cap):
    """LimitReachedError is pypdf's own class, not a PdfReadError, so it is caught before the
    broad except that would otherwise record a plain "Extraction failed" (D-81 item 5)."""
    data = pdf_pages([repeated_operators(100_000)])
    with pytest.raises(TooLargeToExtractError):
        extract_plain_text(upload(data, "bomb.pdf"), "pdf")


# --- The page cap (D-81 item 2) ---------------------------------------------------------


@pytest.fixture
def low_page_cap(monkeypatch):
    monkeypatch.setattr(extraction, "MAXIMUM_PDF_PAGES", 3)
    return 3


def test_a_pdf_over_the_page_cap_is_refused(low_page_cap):
    data = pdf_pages([text_content(f"page {n}") for n in range(5)])
    assert count_operators(data) > 0  # the pages are real and parseable

    with pytest.raises(TooLargeToExtractError) as caught:
        extract_plain_text(upload(data, "many-pages.pdf"), "pdf")
    assert caught.value.limit_message == PDF_TOO_MANY_PAGES_MESSAGE


def test_a_page_tree_that_under_declares_its_count_is_still_refused(low_page_cap):
    """The cap counts the real page tree, not the /Count a file declares (D-81 item 2). A
    tree holding 5 pages but declaring /Count 1 is refused, because len(reader.pages) walks
    the Kids rather than trusting the number."""
    data = pdf_pages([text_content(f"page {n}") for n in range(5)], declared_count=1)
    # pypdf reports the true tree size, not the declared 1 — the precondition for the cap.
    assert len(pypdf.PdfReader(io.BytesIO(data)).pages) == 5

    with pytest.raises(TooLargeToExtractError) as caught:
        extract_plain_text(upload(data, "liar.pdf"), "pdf")
    assert caught.value.limit_message == PDF_TOO_MANY_PAGES_MESSAGE


# --- The operator budget (D-81 item 3) --------------------------------------------------


@pytest.fixture
def low_operator_budget(monkeypatch):
    monkeypatch.setattr(extraction, "PDF_MAXIMUM_OPERATORS", 10)
    return 10


def test_a_form_repetition_bomb_is_stopped_by_the_operator_budget(
    low_operator_budget, monkeypatch, caplog
):
    """A form drawn many times, over a budget crossed INSIDE the form. pypdf swallows the
    raise there ("Impossible to decode XFormObject"); the counter stays over budget and the
    next page-level Do re-raises and propagates (D-81 item 3). Proven parseable first.

    **Stopped at the next page-level operator, not at the end of the page.** The after-page
    check in ``_extract_pdf`` would also refuse this document if the counter raised only
    once, but only after every remaining Do on the page had re-parsed the form, which is the
    work the budget exists to prevent. So the count at refusal is asserted: the raise inside
    the form at limit + 1, the next page-level Do at limit + 2. A counter that raised once
    would reach the end of the page first: 50 Do plus 50 parses of 20 operators."""
    invocations, form_operators = 50, 20
    data = pdf_form_repeated(repeated_operators(form_operators // 2), invocations)
    assert count_operators(data) == invocations + invocations * form_operators

    budgets = []

    class RecordingBudget(extraction._OperatorBudget):
        """The production counter, unchanged, with its instance kept for the assertion."""

        def __init__(self, limit):
            super().__init__(limit)
            budgets.append(self)

    monkeypatch.setattr(extraction, "_OperatorBudget", RecordingBudget)

    with pytest.raises(TooLargeToExtractError) as caught:
        extract_plain_text(upload(data, "form-bomb.pdf"), "pdf")

    assert caught.value.limit_message == PDF_TOO_MANY_OPERATORS_MESSAGE
    # The first raise happened inside the form and pypdf swallowed it, so this test is the
    # swallow-and-re-raise path and not a raise that merely happened at page level.
    assert any("Impossible to decode XFormObject" in record.getMessage() for record in caplog.records)
    assert budgets[0].count == low_operator_budget + 2


def test_a_shared_stream_bomb_is_stopped_by_the_same_budget(low_operator_budget):
    """One stream shared by five pages, each re-parsed. The budget is DOCUMENT-WIDE: no
    single page exceeds it — 4 operators a page against a budget of 10 — but the cumulative
    count does, on page 3. That proves the budget accumulates across pages rather than
    resetting per page, which is what a shared-stream bomb exploits."""
    data = pdf_shared_stream(5, repeated_operators(2))
    assert count_operators(data) == 5 * 4

    with pytest.raises(TooLargeToExtractError) as caught:
        extract_plain_text(upload(data, "shared-bomb.pdf"), "pdf")
    assert caught.value.limit_message == PDF_TOO_MANY_OPERATORS_MESSAGE


def test_an_ordinary_pdf_is_under_the_operator_budget():
    """With the SHIPPED budget, a normal page indexes: the budget is a bomb guard, not a
    limit a real document meets."""
    text = extract_plain_text(upload(pdf_pages([text_content("Leave requests need approval")]), "p.pdf"), "pdf")
    assert "Leave requests need approval" in text


# --- The applied configuration (D-81 item 1, and the upgrade tripwire) ------------------


def test_the_shipped_bounds_are_d_81s_values():
    """The values every test above patches down, asserted as shipped. The page cap sits above
    the ~820 pages of text the chunk ceiling allows, so it cannot refuse a document the
    ceiling would have indexed (D-81 item 2)."""
    assert MAXIMUM_PDF_PAGES == 2000
    assert PDF_MAXIMUM_STREAM_BYTES == 10_000_000
    assert PDF_MAXIMUM_STORED_STREAM_BYTES == 20_000_000
    assert PDF_MAXIMUM_OPERATORS == 1_300_000
    assert MAXIMUM_PDF_PAGES > 820
    # The stored-size limit stays well under the 50 MB upload ceiling, or it would bound
    # nothing an upload could hold (the user's reasoning, apps/core/constants.py).
    from apps.core.constants import MAX_UPLOAD_BYTES

    assert PDF_MAXIMUM_STORED_STREAM_BYTES < MAX_UPLOAD_BYTES


def test_the_stream_limit_fields_exist_on_pypdfs_configuration():
    """A rename in a pypdf upgrade fails here rather than silently leaving a stream at 75 MB.
    apply_configuration raises TypeError for an unknown field, so the names must all be real
    and must all be below pypdf's default."""
    default = pypdf.Configuration()
    for name in _PDF_STREAM_LIMIT_FIELDS:
        assert hasattr(default, name), name
        assert getattr(default, name) > PDF_MAXIMUM_STREAM_BYTES  # we really lower it
    assert hasattr(default, _PDF_STORED_STREAM_LIMIT_FIELD)
    assert getattr(default, _PDF_STORED_STREAM_LIMIT_FIELD) > PDF_MAXIMUM_STORED_STREAM_BYTES


def test_the_lowered_configuration_is_in_force_during_extraction(monkeypatch):
    """Read pypdf's configuration from inside the extraction, through the operator visitor
    the production code installs, and confirm every stream field is the lowered value — not
    pypdf's 75 MB. A spy standing in for the budget captures it on first call."""
    seen = {}

    class ConfigSpy:
        def __init__(self, limit):
            self.limit = limit
            self.count = 0

        @property
        def exceeded(self):
            return self.count > self.limit

        def __call__(self, operator, operands, cm, tm):
            if not seen:
                seen["configuration"] = pypdf.get_configuration()
            self.count += 1

    monkeypatch.setattr(extraction, "_OperatorBudget", ConfigSpy)

    extract_plain_text(upload(pdf_pages([repeated_operators(5)]), "p.pdf"), "pdf")

    configuration = seen["configuration"]
    for name in _PDF_STREAM_LIMIT_FIELDS:
        assert getattr(configuration, name) == PDF_MAXIMUM_STREAM_BYTES, name
    # The stored-size limit, set in the same apply_configuration call.
    assert (
        getattr(configuration, _PDF_STORED_STREAM_LIMIT_FIELD) == PDF_MAXIMUM_STORED_STREAM_BYTES
    )


def test_the_configuration_is_reset_after_extraction():
    """apply_configuration is ContextVar-scoped, so other Waitress threads keep pypdf's
    default. After an extraction returns, this thread's configuration is pypdf's again."""
    extract_plain_text(upload(pdf_pages([repeated_operators(5)]), "p.pdf"), "pdf")
    current, default = pypdf.get_configuration(), pypdf.Configuration()
    assert current.zlib_maximum_output_length == default.zlib_maximum_output_length
    assert getattr(current, _PDF_STORED_STREAM_LIMIT_FIELD) == getattr(
        default, _PDF_STORED_STREAM_LIMIT_FIELD
    )


# --- The text ceiling, through the whole pipeline (D-81 item 4) -------------------------
#
# The ceiling is MAXIMUM_CHUNKS_PER_SOURCE read during extraction: once the running token
# count would be refused, extraction returns the text so far and the ONE existing chunk-
# ceiling check in documents.py refuses it (D-81 item 4: one refusal path, no second raise).
# Both modules' copies of the constant are patched to the same small value, and a PDF is
# built just under and just over the resulting token line.


@pytest.fixture
def low_chunk_ceiling(monkeypatch):
    """MAXIMUM_CHUNKS_PER_SOURCE = 2 on both modules that read it.

    chunk_count_for_tokens(950) == 2 (indexed, == the ceiling) and
    chunk_count_for_tokens(951) == 3 (> the ceiling, refused)."""
    import apps.ingestion.documents as documents_module

    monkeypatch.setattr(extraction, "MAXIMUM_CHUNKS_PER_SOURCE", 2)
    monkeypatch.setattr(documents_module, "MAXIMUM_CHUNKS_PER_SOURCE", 2)
    assert chunk_count_for_tokens(950) == 2
    assert chunk_count_for_tokens(951) == 3
    return 2


def ingest_pdf(data, employee):
    file = upload(data, "doc.pdf")
    return ingest_and_index_document(
        uploaded_file=file,
        file_format="pdf",
        content_hash=compute_content_hash(file),
        title="A PDF",
        department="People",
        visible_to_roles=[EMPLOYEE_ROLE_NAME],
        uploaded_by=employee,
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("media_root")
def test_a_pdf_just_under_the_text_ceiling_indexes(employee, stub_ai_service, low_chunk_ceiling):
    data = pdf_pages([text_content(words(950))])
    # The fixture really carries 950 whitespace tokens, so the boundary is where it says.
    assert length_in_tokens(extract_plain_text(upload(data, "x.pdf"), "pdf")) == 950

    outcome = ingest_pdf(data, employee)

    assert outcome.http_status == 201
    assert outcome.document.status == "Indexed"
    assert ContentChunk.objects.filter(source_id=outcome.document.id).count() == 2


@pytest.mark.django_db
@pytest.mark.usefixtures("media_root")
def test_a_pdf_just_over_the_text_ceiling_is_too_large_to_index(
    employee, stub_ai_service, low_chunk_ceiling
):
    data = pdf_pages([text_content(words(951))])

    outcome = ingest_pdf(data, employee)

    assert outcome.http_status == 422
    assert outcome.document.status == "Too large to index"
    # Refused before any chunk or extracted-content row, the original kept — the chunk-
    # ceiling refusal's own shape (documents.py), reached via the text ceiling in extraction.
    assert not ContentChunk.objects.filter(source_id=outcome.document.id).exists()
    assert not ExtractedContent.objects.filter(document=outcome.document).exists()
    assert outcome.document.file_path.storage.exists(outcome.document.file_path.name)


def test_extraction_stops_reading_pages_once_the_text_ceiling_is_crossed(low_chunk_ceiling):
    """The ceiling is a bound on the WORK, not only on what is indexed: once the running
    token count would be refused, no further page is parsed. Without it, documents.py would
    still refuse the document, so the just-over test above cannot tell; this one can. The
    first page alone crosses the ceiling, and the second page's marker must not be read."""
    data = pdf_pages([text_content(words(951)), text_content("MARKER after the ceiling")])

    text = extract_plain_text(upload(data, "x.pdf"), "pdf")

    assert "w950" in text  # the crossing page is returned whole
    assert "MARKER" not in text


@pytest.mark.django_db
@pytest.mark.usefixtures("media_root")
def test_the_text_ceiling_is_one_refusal_path_not_a_raise(employee, low_chunk_ceiling):
    """Extraction itself does NOT raise for the text ceiling: it returns the text read so
    far (D-81 item 4). The refusal is documents.py's single chunk-ceiling check."""
    data = pdf_pages([text_content(words(951))])
    # No exception from extraction — a plain string comes back.
    text = extract_plain_text(upload(data, "x.pdf"), "pdf")
    assert isinstance(text, str)
    assert chunk_count_for_tokens(length_in_tokens(text)) > low_chunk_ceiling


# --- "Too large to index", not "Extraction failed", for a real PDF bound ----------------


@pytest.mark.django_db
@pytest.mark.usefixtures("media_root")
def test_a_stream_cap_bound_lands_on_too_large_to_index(employee, stub_ai_service, monkeypatch):
    """The whole pipeline: a per-stream-cap refusal is a decided "Too large to index", the
    original kept, no chunks, no extracted content — the same shape as the chunk ceiling,
    and distinct from "Extraction failed" (D-81 item 5, D-51)."""
    monkeypatch.setattr(extraction, "PDF_MAXIMUM_STREAM_BYTES", 4096)
    data = pdf_pages([repeated_operators(100_000)])

    outcome = ingest_pdf(data, employee)

    assert outcome.http_status == 422
    assert outcome.document.status == "Too large to index"
    assert outcome.detail == pdf_bound_detail(PDF_STREAM_TOO_LARGE_MESSAGE)
    assert not ContentChunk.objects.filter(source_id=outcome.document.id).exists()
    assert not ExtractedContent.objects.filter(document=outcome.document).exists()
    assert outcome.document.file_path.storage.exists(outcome.document.file_path.name)
    assert outcome.document.content_hash is None  # the duplicate slot is released, as on every 422


def test_too_large_is_an_extraction_error_subclass_so_no_bound_escapes_as_a_500():
    """A caller that only knows ExtractionError still handles every D-81 bound."""
    assert issubclass(TooLargeToExtractError, ExtractionError)


# --- The messages: a limit sentence, and the clause only the documents route adds ------


def test_no_limit_sentence_says_anything_was_stored():
    """FR-09's file path meets these bounds having stored nothing, and sends the sentence as
    it is, so no sentence may claim storage. The documents route adds that clause itself."""
    for sentence in (
        PDF_STREAM_TOO_LARGE_MESSAGE,
        PDF_TOO_MANY_PAGES_MESSAGE,
        PDF_TOO_MANY_OPERATORS_MESSAGE,
    ):
        assert "stored" not in sentence.lower(), sentence
        assert "split" in sentence.lower(), sentence  # D-81: whether splitting would help
        detail = pdf_bound_detail(sentence)
        assert detail.startswith("The document was stored but not indexed. ")
        assert detail.endswith(sentence)


# --- The stored-size limit (settled by the user, 26 October) ----------------------------
#
# A separate limit from the decoded-size cap: a stream stored without a filter is never
# decompressed, so only its stored length can bound it. pypdf reads a font program the
# page's text uses (and never decodes it), so a font over the limit refuses the document;
# pypdf swallows an over-limit image or form XObject, so those are skipped and the page's
# text is kept. apps/core/constants.py records the user's measurements.


@pytest.mark.django_db
@pytest.mark.usefixtures("media_root")
def test_a_12_mb_stored_font_program_still_indexes(employee, stub_ai_service):
    """The SHIPPED limits, unpatched: a 12 MB font program is over the 10 MB decoded-size cap
    and under the 20 MB stored-size limit. pypdf reads it and never decodes it, so only the
    stored size counts, and a document embedding a whole CJK font is not refused for it."""
    font_program = b"\x00" * 12_000_000
    assert PDF_MAXIMUM_STREAM_BYTES < len(font_program) < PDF_MAXIMUM_STORED_STREAM_BYTES

    outcome = ingest_pdf(pdf_with_embedded_font(words(60), font_program), employee)

    assert outcome.http_status == 201
    assert outcome.document.status == "Indexed"
    assert "w59" in ExtractedContent.objects.get(document=outcome.document).extracted_text


def test_a_font_program_over_the_stored_limit_is_refused(monkeypatch):
    """The other side of the test above, and the proof that the font program is reached at
    all: the same 12 MB font against the limit at 10 MB, the value the user measured with, is
    refused with the per-stream sentence."""
    monkeypatch.setattr(extraction, "PDF_MAXIMUM_STORED_STREAM_BYTES", 10_000_000)
    data = pdf_with_embedded_font(words(60), b"\x00" * 12_000_000)

    with pytest.raises(TooLargeToExtractError) as caught:
        extract_plain_text(upload(data, "font.pdf"), "pdf")
    assert caught.value.limit_message == PDF_STREAM_TOO_LARGE_MESSAGE


@pytest.mark.django_db
@pytest.mark.usefixtures("media_root")
def test_an_uncompressed_content_stream_over_the_stored_limit_is_too_large_to_index(
    employee, stub_ai_service, monkeypatch
):
    """The gap this limit closes: an uncompressed content stream is never decompressed, so
    the decoded-size cap never sees it. The stored-size limit is patched down to 4 KB for
    speed, and the stream is ~8 KB, far under the UNPATCHED 10 MB decoded-size cap, so only
    the stored-size limit can be what refuses it."""
    monkeypatch.setattr(extraction, "PDF_MAXIMUM_STORED_STREAM_BYTES", 4096)
    content = text_content(words(60)) + b"\n" + b" " * 8192
    assert 4096 < len(content) < PDF_MAXIMUM_STREAM_BYTES

    outcome = ingest_pdf(pdf_pages([content], compress=False), employee)

    assert outcome.http_status == 422
    assert outcome.document.status == "Too large to index"
    assert outcome.detail == pdf_bound_detail(PDF_STREAM_TOO_LARGE_MESSAGE)
    assert not ContentChunk.objects.filter(source_id=outcome.document.id).exists()
    assert outcome.document.file_path.storage.exists(outcome.document.file_path.name)


def test_an_uncompressed_content_stream_over_20_mb_is_refused_at_the_shipped_limit():
    """The SHIPPED value, unpatched: one uncompressed content stream just over 20 MB. pypdf
    checks the declared length before reading the stream, so this is fast."""
    content = text_content(words(60)) + b"\n" + b" " * PDF_MAXIMUM_STORED_STREAM_BYTES
    data = pdf_pages([content], compress=False)

    start = time.perf_counter()
    with pytest.raises(TooLargeToExtractError) as caught:
        extract_plain_text(upload(data, "plain.pdf"), "pdf")
    assert time.perf_counter() - start < 10  # generous; it refuses before reading 20 MB
    assert caught.value.limit_message == PDF_STREAM_TOO_LARGE_MESSAGE


def test_a_page_with_an_image_over_the_stored_limit_still_yields_its_text(monkeypatch, caplog):
    """pypdf swallows an over-limit image XObject and carries on, so the image is SKIPPED, not
    refused, and the page's text is kept. The limit is patched down to 4 KB for speed against
    an 8 KB image. The swallow warning proves the image really met the limit and was not
    simply read."""
    monkeypatch.setattr(extraction, "PDF_MAXIMUM_STORED_STREAM_BYTES", 4096)

    text = extract_plain_text(upload(pdf_with_image(words(60), 8192), "image.pdf"), "pdf")

    assert "w0" in text and "w59" in text
    assert any("Impossible to decode XFormObject" in record.getMessage() for record in caplog.records)
