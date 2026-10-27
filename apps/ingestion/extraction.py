"""Plain-text extraction from an uploaded file (proposal section 7.4, FR-08).

The extracted text is stored separately from the original (D-05) so it is reusable
without re-parsing, and it is the only thing chunking and embedding ever see. Three
rules shape this module:

- one router, one parser per format, and no fallthrough. A format with no parser
  raises UnsupportedFormatError rather than returning "".
- no vendor exception escapes. pypdf, python-docx and openpyxl raise their own
  types, and anything they raise on a file of its own declared format becomes
  ExtractionError, which the caller records as "Extraction failed" while keeping the
  stored original (CLAUDE.md invariant 8).
- the return value is always a string, normalised, never None. An empty string is a
  legitimate answer for a scanned image-only PDF; it is the insufficient-content
  check (MINIMUM_CONTENT_LENGTH) that decides what to do about it, not this module.

**PDF extraction is bounded (D-81), which corrects D-50's "PDF is open".** pypdf
inflates object streams with no ZIP involved, so none of signatures.py's OOXML bounds
touch it, and pypdf 6.19.0's own 75 MB per-stream cap does not bound one page: a 10 MB
stream of operators decodes in ~17 s and +671 MB, and pages or forms that re-parse one
stream multiply that. ``_extract_pdf`` lowers the per-stream caps, on decoded size and (since
26 October) on stored size, caps the page count and the whole-document operator count, and
stops reading text at the point the chunk ceiling would refuse it. The caps, the page count
and the budget raise ``TooLargeToExtractError``, which a document lands on "Too large to
index" (D-51); the ceiling returns the text read so far and leaves the single
MAXIMUM_CHUNKS_PER_SOURCE refusal in documents.py to do its job (D-81 items 4 and 5).
"""

import re

import docx
import openpyxl
import pypdf
from pypdf.errors import LimitReachedError

from apps.core.constants import (
    MAXIMUM_CHUNKS_PER_SOURCE,
    MAXIMUM_PDF_PAGES,
    PDF_MAXIMUM_OPERATORS,
    PDF_MAXIMUM_STORED_STREAM_BYTES,
    PDF_MAXIMUM_STREAM_BYTES,
)
from apps.ingestion.chunking import chunk_count_for_tokens, length_in_tokens
from apps.ingestion.errors import (
    ExtractionError,
    TooLargeToExtractError,
    UnsupportedFormatError,
)

# Row and table cells are joined with this rather than a tab so the text reads as a
# sentence to a human and to the model: FR-12 shows a retrieved passage verbatim.
CELL_SEPARATOR = " | "

# Blank lines between two PDF pages, DOCX blocks or XLSX sheets.
BLOCK_SEPARATOR = "\n\n"

# Four or more consecutive newlines are three or more blank lines; they collapse to
# two blank lines. Run-on blank space is an artefact of the source layout and wastes
# the chunk budget, but some vertical separation is real structure worth keeping.
_EXCESS_BLANK_LINES = re.compile(r"\n{4,}")

# --- D-81 PDF bounds ------------------------------------------------------------------
# The pypdf Configuration fields that cap one stream's decompressed output, every one of
# them lowered to PDF_MAXIMUM_STREAM_BYTES (D-81 item 1). pypdf 6.19.0 names exactly these
# five with the ``*_maximum_output_length`` suffix; its module-level constants in
# pypdf.filters are deprecated and are NOT what is set here. They are listed rather than
# discovered by suffix on purpose: pypdf.apply_configuration rejects an unknown field name
# with a TypeError, so a release that renames one fails loudly here and in the test that
# reads the applied configuration, instead of quietly leaving that stream at 75 MB.
_PDF_STREAM_LIMIT_FIELDS = (
    "array_based_stream_maximum_output_length",
    "jbig2_maximum_output_length",
    "lzw_maximum_output_length",
    "run_length_maximum_output_length",
    "zlib_maximum_output_length",
)

# The pypdf Configuration field that caps one stream's STORED length, its declared /Length
# in the file, lowered to PDF_MAXIMUM_STORED_STREAM_BYTES (settled by the user on
# 26 October; apps/core/constants.py has their reasoning). A separate limit from the five
# above, because a stream stored without a filter is never decompressed and so never meets
# them. Named for the same reason they are: a rename fails apply_configuration loudly.
_PDF_STORED_STREAM_LIMIT_FIELD = "maximum_declared_stream_length"


def _pdf_stream_limits() -> dict:
    """The per-stream caps to pass to ``apply_configuration``, built at call time.

    Both limits go in ONE call: the five decoded-size fields at PDF_MAXIMUM_STREAM_BYTES and
    the stored-size field at PDF_MAXIMUM_STORED_STREAM_BYTES. Built here rather than once at
    import so a test may lower either constant on this module and reach the guard, the way
    test_documents.py lowers MAXIMUM_CHUNKS_PER_SOURCE (the module-level names are looked up
    when this runs)."""
    limits = {name: PDF_MAXIMUM_STREAM_BYTES for name in _PDF_STREAM_LIMIT_FIELDS}
    limits[_PDF_STORED_STREAM_LIMIT_FIELD] = PDF_MAXIMUM_STORED_STREAM_BYTES
    return limits


# Each bound's own LIMIT SENTENCE (D-81 item 5: "Each limit has its own message, so the
# uploader knows whether splitting the file would help"). Each says only what the file met
# and whether splitting it would help. None says what happened to the file, because that
# depends on the route: FR-08 has stored the document by then, and documents.py prefixes
# that; FR-09's file path has stored nothing, and the meetings view sends the sentence as
# it is. They carry no pypdf internals; the diagnostic with the real numbers rides on the
# exception for the server log only.
#
# The per-stream sentence serves both caps, decoded size and stored size. It is true of
# either: one stream, a single element of the file, is over a limit, and splitting the file
# leaves that element whole in one of the parts.
PDF_STREAM_TOO_LARGE_MESSAGE = (
    "One part of this PDF is too large to process. Splitting the file into smaller files "
    "is unlikely to help, because that part is a single element inside it."
)
PDF_TOO_MANY_PAGES_MESSAGE = (
    "This PDF has too many pages to index in one request. Splitting it into smaller files "
    "would let each part be indexed."
)
PDF_TOO_MANY_OPERATORS_MESSAGE = (
    "This PDF holds too much drawing detail to index in one request. Splitting it into "
    "smaller files may help, unless a single page holds most of that detail."
)


class _OperatorBudgetExceeded(Exception):
    """Raised by the operator-counting visitor once the document is over budget.

    A private signal, not an IngestionError: it is caught inside ``_extract_pdf`` and turned
    into TooLargeToExtractError there. It must subclass nothing pypdf catches as "a damaged
    page" — but note pypdf DOES swallow any exception raised inside a form XObject (it logs
    "Impossible to decode XFormObject"), which is why the visitor keeps raising on every
    call rather than once: a raise inside a form is lost, and the next page-level operator
    re-raises and propagates (D-81 item 3)."""


class _OperatorBudget:
    """A visitor_operand_before callable that counts operators and stops over budget.

    pypdf calls it once per content-stream operator, including the operators inside form
    XObjects and before each ``Do`` (D-81 item 3), so one counter bounds the whole document
    including the repeated parsing a per-stream cap cannot see. It never resets: once over
    budget it raises on every subsequent call, so the first raise that is NOT inside a form
    propagates out of ``extract_text``."""

    def __init__(self, limit: int):
        self.limit = limit
        self.count = 0

    @property
    def exceeded(self) -> bool:
        return self.count > self.limit

    def __call__(self, operator, operands, cm_matrix, tm_matrix) -> None:
        self.count += 1
        if self.count > self.limit:
            raise _OperatorBudgetExceeded()


def extract_plain_text(file, file_format: str) -> str:
    """Extract plain text from ``file``, parsed as ``file_format``.

    ``file_format`` is the value read from the file's own signature
    (signatures.read_file_signature), never from its extension.

    Raises UnsupportedFormatError for any format with no parser here, including one
    that is in ACCEPTED_FORMATS. That branch is unreachable while validation runs
    first, and section 7.4 keeps it deliberately: a fifth format added to
    ACCEPTED_FORMATS without a parser must fail loudly at this point rather than
    silently produce an empty string that is then stored, chunked and indexed as an
    empty document nobody notices until a search fails to find it.

    Raises ExtractionError when the parser fails on a file genuinely of its own
    format (a truncated PDF, a corrupt OOXML package).
    """
    parser = _PARSERS.get(file_format)
    if parser is None:
        raise UnsupportedFormatError(f"No text parser is installed for format {file_format!r}.")

    try:
        file.seek(0)
        text = parser(file)
    except ExtractionError:
        raise
    except Exception as exception:  # noqa: BLE001 — see the module docstring
        # Deliberately broad. Each library raises its own hierarchy (PdfReadError,
        # PackageNotFoundError, InvalidFileException) and also leaks KeyError,
        # zipfile.BadZipFile and struct.error from its dependencies on a malformed
        # file. Listing them would let a new one through as a 500.
        raise ExtractionError(
            f"Could not extract text from the {file_format.upper()} file: {exception}"
        ) from exception
    finally:
        file.seek(0)

    return _normalise(text)


def _extract_pdf(file) -> str:
    """Page text, in page order, one blank line between pages, within D-81's bounds.

    A PDF with no text layer (a scan) yields "" rather than an error: the file is
    valid, it simply has no text, and "Insufficient content" is the accurate status
    for it.

    Four bounds, so a crafted PDF cannot exhaust memory or hold a worker (D-81):

    1. Every per-stream decompression cap is lowered to PDF_MAXIMUM_STREAM_BYTES, and the
       stored-length cap to PDF_MAXIMUM_STORED_STREAM_BYTES, in one
       ``pypdf.apply_configuration`` — a ContextVar overwrite, so only this thread's
       extraction is affected and other Waitress threads keep pypdf's default. It wraps
       both the reader construction and the page loop, because a stream is read and
       decompressed lazily when its page is read, not when the reader is built. pypdf
       raises its own ``LimitReachedError`` (not a PdfReadError) over either cap, caught
       below. pypdf swallows that error for an image or form XObject, which is skipped
       and the page's other text kept; it is a page content stream or a font program over
       a cap that refuses the document.
    2. The page count is checked with ``len(reader.pages)`` BEFORE any page is parsed.
       That walks the real page tree, so a tree that under-declares its /Count is still
       counted in full.
    3. A whole-document operator budget, counted by the visitor. It bounds the repeated
       parsing the per-stream cap cannot: shared streams and repeated forms.
    4. A text ceiling: once the running token count would be refused by
       MAXIMUM_CHUNKS_PER_SOURCE, stop and return the text read so far, so the one
       existing check in documents.py refuses it. No second refusal path, and no raise.

    The first three raise ``TooLargeToExtractError`` (-> "Too large to index"); the fourth
    does not (-> the chunk-ceiling refusal already in documents.py).
    """
    with pypdf.apply_configuration(**_pdf_stream_limits()):
        try:
            reader = pypdf.PdfReader(file)

            page_count = len(reader.pages)
            if page_count > MAXIMUM_PDF_PAGES:
                raise TooLargeToExtractError(
                    PDF_TOO_MANY_PAGES_MESSAGE,
                    f"PDF has {page_count} pages, over the {MAXIMUM_PDF_PAGES}-page limit.",
                )

            budget = _OperatorBudget(PDF_MAXIMUM_OPERATORS)
            pages: list[str] = []
            tokens = 0
            for page in reader.pages:
                try:
                    page_text = page.extract_text(visitor_operand_before=budget) or ""
                except _OperatorBudgetExceeded:
                    raise TooLargeToExtractError(
                        PDF_TOO_MANY_OPERATORS_MESSAGE,
                        f"PDF processed over {budget.limit} content-stream operators.",
                    )
                if budget.exceeded:
                    # The over-budget raise happened inside a form XObject, where pypdf
                    # swallows it, and this page had no page-level operator left to
                    # re-raise. Stop now rather than parse another page (D-81 item 3).
                    raise TooLargeToExtractError(
                        PDF_TOO_MANY_OPERATORS_MESSAGE,
                        f"PDF processed over {budget.limit} content-stream operators.",
                    )
                pages.append(page_text)
                tokens += length_in_tokens(page_text)
                if chunk_count_for_tokens(tokens) > MAXIMUM_CHUNKS_PER_SOURCE:
                    # The text ceiling (D-81 item 4). Return what has been read; the
                    # MAXIMUM_CHUNKS_PER_SOURCE check in documents.py is the one refusal.
                    break
            return BLOCK_SEPARATOR.join(pages)
        except LimitReachedError as exception:
            # pypdf's per-stream caps, decoded and stored, and its other internal limits.
            # Its own class, not a PdfReadError, so it is caught here BEFORE
            # extract_plain_text's broad except would turn it into a plain "Extraction
            # failed" (D-81 item 5).
            raise TooLargeToExtractError(
                PDF_STREAM_TOO_LARGE_MESSAGE, f"pypdf limit reached: {exception}"
            ) from exception


def _extract_docx(file) -> str:
    """Paragraph text and table cell text.

    Tables are included because a policy document's approval limits, retention
    periods and thresholds are usually in one, and dropping them silently loses
    exactly the content FR-12 is asked about most.

    Paragraphs are emitted first and tables after, rather than in document order:
    python-docx exposes the two as separate collections and interleaving them means
    walking the underlying XML body element. Order within the extracted text does
    not affect retrieval (chunks are embedded independently), so the boring version
    stands. A table nested inside another table's cell is not reached; cell.text does
    include the cell's own paragraphs.
    """
    document = docx.Document(file)
    blocks = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(CELL_SEPARATOR.join(cell for cell in cells if cell))
        blocks.append("\n".join(row for row in rows if row))
    return "\n".join(blocks)


def _extract_xlsx(file) -> str:
    """Sheet by sheet: the sheet name, then one line per row.

    read_only=True streams the rows instead of building the whole workbook in
    memory; data_only=True yields a formula's cached result rather than the formula
    source, since "=SUM(B2:B9)" answers no question a user can ask.
    """
    workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
    try:
        sheets = []
        for worksheet in workbook.worksheets:
            lines = [worksheet.title]
            for row in worksheet.iter_rows(values_only=True):
                values = [str(value).strip() for value in row if value is not None]
                line = CELL_SEPARATOR.join(value for value in values if value)
                if line:
                    lines.append(line)
            sheets.append("\n".join(lines))
        return BLOCK_SEPARATOR.join(sheets)
    finally:
        # read_only leaves the underlying archive open until it is closed.
        workbook.close()


def _extract_txt(file) -> str:
    """The file's bytes decoded as UTF-8.

    utf-8-sig strips a byte-order mark, which Notepad writes by default on the
    platform this project is developed on and which would otherwise survive into the
    first chunk.

    Fallback for content that is not valid UTF-8: decode again with errors="replace".
    Reachable only when a caller declares "txt" for bytes the signature check never
    saw, since that check admits TXT only when it decodes. No encoding is guessed:
    no charset detector is in the stack, and a wrong guess is silent corruption of
    every accented word, whereas U+FFFD is visible to whoever reads the passage.
    """
    data = file.read()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


# The router. Its keys are the values read_file_signature() can return, which is
# ACCEPTED_FORMATS (D-15); anything else is UnsupportedFormatError.
_PARSERS = {
    "pdf": _extract_pdf,
    "docx": _extract_docx,
    "xlsx": _extract_xlsx,
    "txt": _extract_txt,
}


def _normalise(text: str) -> str:
    """Tidy extracted text without altering its words.

    Trailing whitespace per line, runs of three or more blank lines and leading and
    trailing whitespace all come from the source's layout, not its content, and each
    costs tokens in a chunk and in the grounding context. Internal single blank lines
    and line breaks are kept: a chunk is shown to a reader (D-31), so its shape has
    to survive.
    """
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    return _EXCESS_BLANK_LINES.sub("\n\n\n", "\n".join(lines)).strip()
