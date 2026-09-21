"""read_file_signature() and compute_content_hash() (proposal section 7.3, FR-08).

FR-08 requires the format to be confirmed "by inspecting the file signature rather
than the extension alone, preventing a disguised file from being accepted", so the
uploads here are named to lie wherever the name would be tempting to trust.

No database: these functions touch none, so no test in this module takes the db
fixture.
"""

import hashlib

import pytest

from apps.core.constants import ACCEPTED_FORMATS
from apps.ingestion.signatures import TEXT_SAMPLE_BYTES, compute_content_hash, read_file_signature
from apps.ingestion.tests.builders import docx_bytes, pdf_bytes, upload, xlsx_bytes, zip_bytes

# The first bytes of a real Windows PE executable: the MZ magic, then the DOS
# header. A renamed .exe is the disguised file FR-08 names.
PE_HEADER = (
    b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    + b"\xb8\x00\x00\x00" * 8
    + b"\x0e\x1f\xba\x0e\x00\xb4\x09\xcd\x21\xb8\x01\x4c\xcd\x21"
    + b"This program cannot be run in DOS mode.\r\r\n$"
)

# The same shape of file, but padded with NUL rather than with bytes that happen to
# be invalid UTF-8. Section 7.3's literal rule ("decodes cleanly as UTF-8") admits
# this one; test_nul_padded_executable_would_pass_a_naive_utf8_check proves it.
NUL_PADDED_EXECUTABLE = (
    b"MZ" + b"\x00" * 64 + b"This program cannot be run in DOS mode.\r\n" + b"\x00" * 64
)


# --- The four accepted formats, identified from content (D-15) -----------------------


def test_pdf_is_identified_from_its_signature():
    assert read_file_signature(upload(pdf_bytes("Leave policy"), "policy.txt")) == "pdf"


def test_docx_is_identified_from_the_archive_content_type():
    # DOCX and XLSX share the ZIP signature, so only the manifest separates them.
    content = docx_bytes(paragraphs=["Approval limits"])
    assert read_file_signature(upload(content, "limits.xlsx")) == "docx"


def test_xlsx_is_identified_from_the_archive_content_type():
    content = xlsx_bytes({"Limits": [("Role", "Limit")]})
    assert read_file_signature(upload(content, "limits.docx")) == "xlsx"


def test_plain_text_is_identified_when_nothing_else_matches():
    content = "Minutes\tof the meeting\r\nSecond line\n\nThird\n".encode("utf-8")
    assert read_file_signature(upload(content, "minutes.pdf")) == "txt"


def test_every_accepted_format_can_be_returned_by_the_detector():
    # Guards the pairing the pipeline relies on: the detector's vocabulary is
    # ACCEPTED_FORMATS, so no upload can be admitted under a name the router in
    # extraction.py has never heard of.
    detected = {
        read_file_signature(upload(pdf_bytes("x"))),
        read_file_signature(upload(docx_bytes(paragraphs=["x"]))),
        read_file_signature(upload(xlsx_bytes({"S": [("x",)]}))),
        read_file_signature(upload(b"plain text, nothing more")),
    }
    assert detected == set(ACCEPTED_FORMATS)


def test_a_utf8_file_longer_than_the_sample_is_still_text():
    # The sample cuts the content mid-character on purpose: "é" is two bytes and its
    # lead byte lands on the last byte read. A non-incremental decode would call
    # that invalid and reject a perfectly ordinary text file.
    content = ("a" * (TEXT_SAMPLE_BYTES - 1) + "é" * 100).encode("utf-8")
    assert content[TEXT_SAMPLE_BYTES - 1] == 0xC3  # the cut really is mid-character
    assert read_file_signature(upload(content, "notes.txt")) == "txt"


def test_an_empty_file_is_text():
    # Not a rejection: an empty upload is answered by the insufficient-content rule
    # (MINIMUM_CONTENT_LENGTH), which is the accurate reason, rather than by a claim
    # that the format was unrecognised.
    assert read_file_signature(upload(b"", "empty.txt")) == "txt"


# --- Disguised and unrecognised files ------------------------------------------------


def test_an_executable_renamed_as_a_pdf_is_rejected():
    assert read_file_signature(upload(PE_HEADER, "invoice.pdf")) is None


def test_nul_padded_executable_would_pass_a_naive_utf8_check():
    """The reason section 7.3's literal rule is strengthened in _text_format().

    NUL is valid UTF-8, so a NUL-padded binary decodes without error. On the literal
    rule this file is TXT: it would be stored, chunked, embedded and indexed.
    """
    NUL_PADDED_EXECUTABLE.decode("utf-8")  # no exception: the naive check passes

    assert read_file_signature(upload(NUL_PADDED_EXECUTABLE, "handbook.txt")) is None


def test_control_character_padding_without_nul_is_rejected():
    # A binary that avoids NUL but is still not text. Every byte below 0x80 decodes,
    # so only the control-character share catches this one.
    content = b"MZ" + bytes(range(1, 32)) * 20 + b"payload"
    assert b"\x00" not in content
    content.decode("utf-8")  # decodes cleanly, and is still not a document

    assert read_file_signature(upload(content, "report.txt")) is None


def test_an_occasional_control_character_does_not_reject_a_text_file():
    # A form feed from a page-break-aware export is not grounds to refuse an upload.
    content = ("Leave policy\f" + "Every employee accrues leave monthly. " * 20).encode("utf-8")
    assert read_file_signature(upload(content, "policy.txt")) == "txt"


def test_a_zip_that_is_neither_docx_nor_xlsx_is_unrecognised():
    content = zip_bytes({"holiday.jpg": b"\xff\xd8\xff\xe0not really"})
    assert read_file_signature(upload(content, "photos.docx")) is None


def test_a_zip_with_no_manifest_entry_is_unrecognised():
    content = zip_bytes({"word/document.xml": b"<w:document/>"})
    assert read_file_signature(upload(content, "report.docx")) is None


def test_a_corrupt_archive_is_unrecognised_and_does_not_raise():
    # zipfile.BadZipFile is a None, never an exception out of the detector.
    truncated = docx_bytes(paragraphs=["Approval limits"])[:200]
    assert read_file_signature(upload(truncated, "limits.docx")) is None


def test_invalid_utf8_that_is_no_other_format_is_unrecognised():
    assert read_file_signature(upload(b"\xff\xfe\x00\x01\x02\x80\x81rubbish", "x.txt")) is None


# --- The position contract -------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(pdf_bytes("Leave policy"), id="pdf"),
        pytest.param(docx_bytes(paragraphs=["Approval limits"]), id="docx"),
        pytest.param(xlsx_bytes({"Limits": [("Role", "Limit")]}), id="xlsx"),
        pytest.param(b"plain text", id="txt"),
        pytest.param(PE_HEADER, id="executable"),
        pytest.param(docx_bytes(paragraphs=["x"])[:200], id="corrupt-archive"),
    ],
)
def test_detection_leaves_the_position_at_zero(content):
    # The caller stores the original bytes and then extracts text from the same
    # handle, so a detector that consumed the file would silently store an empty one.
    file = upload(content)
    read_file_signature(file)
    assert file.tell() == 0
    assert file.read() == content


def test_detection_leaves_the_position_at_zero_for_a_file_on_disk(tmp_path):
    # UploadedFile is BytesIO-backed in memory but a file over 2.5 MB is spooled to
    # disk by Django, so the contract is asserted against a real file handle too.
    path = tmp_path / "policy.pdf"
    path.write_bytes(pdf_bytes("Leave policy"))
    with path.open("rb") as file:
        assert read_file_signature(file) == "pdf"
        assert file.tell() == 0


# --- Content hashing (FR-08's 409, section 7.2) ----------------------------------------


def test_content_hash_is_the_sha256_of_the_whole_file():
    content = pdf_bytes("Leave policy") + b"\n% padding " * 10000  # larger than one read block
    assert compute_content_hash(upload(content)) == hashlib.sha256(content).hexdigest()


def test_content_hash_ignores_the_filename():
    # Section 7.2 compares by content "so that the same document uploaded under two
    # different names is still caught".
    content = docx_bytes(paragraphs=["Approval limits"])
    assert compute_content_hash(upload(content, "limits.docx")) == compute_content_hash(
        upload(content, "limits-final-v2.docx")
    )


def test_content_hash_differs_for_different_content():
    assert compute_content_hash(upload(b"one")) != compute_content_hash(upload(b"two"))


def test_content_hash_leaves_the_position_at_zero():
    file = upload(b"Leave requests need a manager's approval.")
    compute_content_hash(file)
    assert file.tell() == 0
    assert file.read() == b"Leave requests need a manager's approval."
