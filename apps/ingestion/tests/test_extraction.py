"""extract_plain_text() (proposal section 7.4, FR-08).

Each format is round-tripped through the library that will parse it in production,
so a change of parser version that loses text fails here rather than at a demo. No
database: extraction touches none.
"""

import pytest

from apps.core.constants import ACCEPTED_FORMATS
from apps.ingestion.errors import ExtractionError, IngestionError, UnsupportedFormatError
from apps.ingestion.extraction import _PARSERS, extract_plain_text
from apps.ingestion.tests.builders import docx_bytes, pdf_bytes, upload, xlsx_bytes, zip_bytes


# --- The happy path, one format at a time -------------------------------------------


def test_pdf_text_is_extracted():
    text = extract_plain_text(upload(pdf_bytes("Leave requests need approval")), "pdf")
    assert "Leave requests need approval" in text


def test_docx_paragraph_text_is_extracted():
    content = docx_bytes(paragraphs=["Approval limits policy", "Reviewed annually."])
    text = extract_plain_text(upload(content), "docx")
    assert "Approval limits policy" in text
    assert "Reviewed annually." in text


def test_docx_table_text_is_extracted():
    """A policy's approval limits are usually in a table, and FR-12 is asked about
    exactly those numbers. Dropping tables would lose them silently."""
    content = docx_bytes(
        paragraphs=["Approval limits policy"],
        table_rows=[("Role", "Limit"), ("Manager", "5000"), ("Director", "50000")],
    )
    text = extract_plain_text(upload(content), "docx")
    assert "Manager | 5000" in text
    assert "Director | 50000" in text


def test_xlsx_rows_and_sheet_names_are_extracted():
    content = xlsx_bytes(
        {
            "Limits": [("Role", "Limit"), ("Manager", 5000)],
            "Notes": [("Reviewed annually",)],
        }
    )
    text = extract_plain_text(upload(content), "xlsx")
    assert "Limits" in text and "Notes" in text
    assert "Role | Limit" in text
    assert "Manager | 5000" in text


def test_xlsx_yields_cached_values_not_formula_source():
    # data_only=True. "=SUM(B1:B2)" answers no question a user can ask, and a cell
    # openpyxl has no cached value for is skipped rather than emitted as its source.
    content = xlsx_bytes({"Limits": [("Manager", 5000), ("Total", "=SUM(B1:B1)")]})
    text = extract_plain_text(upload(content), "xlsx")
    assert "=SUM" not in text
    assert "Total" in text


def test_txt_is_read_directly():
    text = extract_plain_text(upload("Minutes of the meeting".encode("utf-8")), "txt")
    assert text == "Minutes of the meeting"


def test_txt_byte_order_mark_is_stripped():
    # Notepad writes a BOM by default on this project's development platform; left
    # in, it becomes the first character of the first chunk.
    text = extract_plain_text(upload("﻿Leave policy".encode("utf-8")), "txt")
    assert text == "Leave policy"


def test_txt_that_is_not_valid_utf8_is_decoded_with_replacement():
    # Reachable only when a caller declares "txt" for bytes the signature check never
    # saw. No encoding is guessed: a wrong guess is silent corruption, U+FFFD is not.
    text = extract_plain_text(upload(b"Caf\xe9 policy"), "txt")
    assert "policy" in text
    assert "�" in text


# --- Normalisation ---------------------------------------------------------------------


def test_normalisation_trims_lines_and_collapses_blank_runs():
    # Five blank lines become two; trailing spaces and tabs go; the ends are
    # stripped, which takes the first line's indentation with them. A single blank
    # line survives, because that separation is real structure a reader uses.
    content = b"  Leave policy   \n\n\n\n\n\nApproval limits\t\n\nEnd\n\n\n"
    text = extract_plain_text(upload(content), "txt")
    assert text == "Leave policy\n\n\nApproval limits\n\nEnd"


def test_extraction_returns_empty_string_never_none():
    # A scanned, image-only PDF is a valid file with no text. "" is the honest
    # answer; the insufficient-content rule decides what to do about it.
    assert extract_plain_text(upload(b"   \n\n  "), "txt") == ""


# --- Failure paths -----------------------------------------------------------------------


def test_a_format_with_no_parser_raises_unsupported_format():
    """Section 7.4 keeps this branch deliberately.

    It is unreachable while validation runs first, but a fifth format added to
    ACCEPTED_FORMATS without a parser must fail loudly here rather than silently
    produce "" that is then stored and indexed as an empty document.
    """
    with pytest.raises(UnsupportedFormatError):
        extract_plain_text(upload(b"\xd0\xcf\x11\xe0legacy binary"), "doc")


def test_every_accepted_format_has_a_parser():
    # The condition that keeps the branch above unreachable in this build (D-15).
    assert set(_PARSERS) == set(ACCEPTED_FORMATS)


@pytest.mark.parametrize(
    "content,file_format",
    [
        pytest.param(pdf_bytes("Leave policy")[:120], "pdf", id="truncated-pdf"),
        pytest.param(b"%PDF-1.4\nnot actually a document", "pdf", id="pdf-without-objects"),
        pytest.param(zip_bytes({"hello.txt": b"not office"}), "docx", id="zip-that-is-not-docx"),
        pytest.param(docx_bytes(paragraphs=["x"])[:200], "docx", id="truncated-docx"),
        pytest.param(zip_bytes({"hello.txt": b"not office"}), "xlsx", id="zip-that-is-not-xlsx"),
    ],
)
def test_a_corrupt_file_of_its_declared_format_raises_extraction_error(content, file_format):
    # No vendor exception escapes: pypdf's PdfReadError, python-docx's
    # PackageNotFoundError and the KeyError both leak on a bad archive all arrive as
    # one type the caller can answer "Extraction failed" to.
    with pytest.raises(ExtractionError):
        extract_plain_text(upload(content), file_format)


def test_extraction_failures_share_one_base_class():
    # So a view may catch everything ingestion raises in a single except.
    assert issubclass(ExtractionError, IngestionError)
    assert issubclass(UnsupportedFormatError, IngestionError)


# --- The position contract ---------------------------------------------------------------


@pytest.mark.parametrize(
    "content,file_format",
    [
        pytest.param(pdf_bytes("Leave policy"), "pdf", id="pdf"),
        pytest.param(docx_bytes(paragraphs=["Approval limits"]), "docx", id="docx"),
        pytest.param(xlsx_bytes({"Limits": [("Role", "Limit")]}), "xlsx", id="xlsx"),
        pytest.param(b"Minutes of the meeting", "txt", id="txt"),
    ],
)
def test_extraction_leaves_the_position_at_zero(content, file_format):
    # The same handle is used to store the original after extraction (D-05).
    file = upload(content)
    extract_plain_text(file, file_format)
    assert file.tell() == 0


def test_extraction_leaves_the_position_at_zero_after_a_failure():
    file = upload(pdf_bytes("Leave policy")[:120])
    with pytest.raises(ExtractionError):
        extract_plain_text(file, "pdf")
    assert file.tell() == 0
