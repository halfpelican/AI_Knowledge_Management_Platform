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
"""

import re

import docx
import openpyxl
import pypdf

from apps.ingestion.errors import ExtractionError, UnsupportedFormatError

# Row and table cells are joined with this rather than a tab so the text reads as a
# sentence to a human and to the model: FR-12 shows a retrieved passage verbatim.
CELL_SEPARATOR = " | "

# Blank lines between two PDF pages, DOCX blocks or XLSX sheets.
BLOCK_SEPARATOR = "\n\n"

# Four or more consecutive newlines are three or more blank lines; they collapse to
# two blank lines. Run-on blank space is an artefact of the source layout and wastes
# the chunk budget, but some vertical separation is real structure worth keeping.
_EXCESS_BLANK_LINES = re.compile(r"\n{4,}")


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
    """Page text, in page order, one blank line between pages.

    A PDF with no text layer (a scan) yields "" rather than an error: the file is
    valid, it simply has no text, and "Insufficient content" is the accurate status
    for it.
    """
    reader = pypdf.PdfReader(file)
    return BLOCK_SEPARATOR.join(page.extract_text() or "" for page in reader.pages)


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
