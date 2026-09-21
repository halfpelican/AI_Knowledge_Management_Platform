"""Regenerate the committed ingestion fixture corpus.

    .venv/Scripts/python.exe apps/ingestion/tests/fixtures/build_fixtures.py

The files this writes are committed, because a test that builds a PDF with the same
library the parser uses proves less than one that reads a file on disk: it cannot
catch a change in how the library *writes*, only a round trip through its own
assumptions. They are deliberately small — a few kilobytes each — and hold the same
recognisable policy text so one assertion serves every format.

Two files cover the FR-08 disguised-file case: "file type is confirmed by inspecting
the file signature rather than the extension alone, preventing a disguised file from
being accepted". Both are minimal Windows PE executables carrying a ``.pdf``
extension. Neither is a working program and neither executes anything; each is a few
hundred bytes shaped like one, which is all a signature check looks at. They are two
files because they fail the check for two different reasons, and only one of those
reasons is the interesting one:

- ``disguised.pdf`` is a realistic PE: a full DOS header with the ``0xFF`` and
  ``0xB8`` bytes a real one carries. It is not a PDF, not a ZIP, and does not decode
  as UTF-8, so even the literal pseudocode of section 7.3 rejects it.
- ``disguised_utf8.pdf`` is the case that pseudocode would **admit**. It is an
  ``MZ`` header padded with NUL bytes and ASCII only — no high bytes at all — so it
  decodes as valid UTF-8 and section 7.3's last rule would return TXT for it. It is
  rejected only by the added NUL-byte rule in ``read_file_signature``, which is why
  that rule exists. A test asserts the file really does decode cleanly, so the test
  cannot quietly stop testing anything if the payload is ever edited.

NUL padding below is written as ``bytes(n)``, never as an escape in a string
literal: an escape has to survive every tool that ever edits this file, and one that
does not turns the source into something Python refuses to parse.
"""

import pathlib

import openpyxl
from docx import Document as DocxDocument

HERE = pathlib.Path(__file__).resolve().parent

# ~130 words, comfortably above MINIMUM_CONTENT_LENGTH (50 tokens, D-31), so the
# same corpus serves the end-to-end indexing tests and not only the parser tests.
POLICY_PARAGRAPHS = [
    "Annual leave is accrued at the rate of one and two-thirds days for each "
    "completed month of service. Employees may carry a maximum of ten days of "
    "accrued leave across a financial year, and any balance above that ceiling is "
    "paid out in the first pay cycle of the new year.",
    "Requests for annual leave must be submitted at least fourteen days before the "
    "intended start date. A manager may approve a shorter notice period where "
    "operational requirements allow. Leave taken without an approved request is "
    "recorded as unpaid absence.",
    "Purchase orders above ten thousand dollars require two approvals, one of which "
    "must be from a delegate of the finance team. Orders below that threshold "
    "require a single approval from the requesting employee's direct manager.",
]

# The sentence every format-round-trip assertion looks for. Present in all four.
MARKER_SENTENCE = "Purchase orders above ten thousand dollars require two approvals"


def build_txt() -> None:
    (HERE / "sample.txt").write_text("\n\n".join(POLICY_PARAGRAPHS) + "\n", encoding="utf-8")


def build_pdf() -> None:
    """Write a minimal one-page PDF by hand, with no PDF library involved.

    Deliberately not built with ``pypdf``, which is the library that will parse it:
    a fixture written and read by the same code proves only that the code agrees
    with itself. This is a plain PDF 1.4 file — catalog, page tree, one page, one
    Helvetica text object — so the test exercises pypdf against a file it did not
    produce. pypdf has no text-drawing API in any case.
    """
    lines = []
    for paragraph in POLICY_PARAGRAPHS:
        lines.extend(_wrap(paragraph, 80))
        lines.append("")

    def escape(text):
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    drawn = "\n".join(f"({escape(line)}) Tj T*" for line in lines)
    stream = f"BT\n/F1 11 Tf\n40 800 Td\n14 TL\n{drawn}\nET".encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)

    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    (HERE / "sample.pdf").write_bytes(bytes(out))


def build_docx() -> None:
    document = DocxDocument()
    document.add_heading("Leave and Delegation Policy", level=1)
    for paragraph in POLICY_PARAGRAPHS[:2]:
        document.add_paragraph(paragraph)
    # The third paragraph goes in a TABLE on purpose. A policy's approval limits are
    # very often in a table, and a DOCX parser that reads paragraphs only drops
    # exactly the content FR-12 is asked about most. A test asserts it survives.
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Threshold"
    table.cell(0, 1).text = "Approvals required"
    table.cell(1, 0).text = "Ten thousand dollars"
    table.cell(1, 1).text = POLICY_PARAGRAPHS[2]
    document.save(HERE / "sample.docx")


def build_xlsx() -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Delegations"
    sheet.append(["Clause", "Text"])
    for index, paragraph in enumerate(POLICY_PARAGRAPHS, start=1):
        sheet.append([f"{index}", paragraph])
    workbook.save(HERE / "sample.xlsx")


def build_no_text_pdf() -> None:
    """A valid PDF with a blank page and no text layer.

    The scanned-document case: the file is a perfectly good PDF, the parser reads it
    without error, and there is simply no text in it. Section 7.8 lines 41-44 answer
    422 and mark the record "Extraction failed" while keeping the original, which is
    a different outcome from a corrupt file even though FR-08 gives them one code.
    """
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << >> >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    (HERE / "no_text.pdf").write_bytes(bytes(out))


def build_corrupt_docx() -> None:
    """A ZIP that declares itself a DOCX and then is not one.

    ``[Content_Types].xml`` names the Word content type, so ``read_file_signature``
    correctly identifies it as DOCX and the upload is accepted; ``word/document.xml``
    is then not valid document XML, so python-docx raises and the extractor turns
    that into ExtractionError. This is the path that proves a vendor exception is
    caught rather than escaping as a 500.
    """
    import zipfile

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" ContentType="'
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        '.main+xml"/></Types>'
    )
    with zipfile.ZipFile(HERE / "corrupt.docx", "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", "this is not document xml at all")


def build_disguised_pdf() -> None:
    """A minimal, realistic PE executable named .pdf — see the module docstring."""
    dos_header = bytearray(b"MZ")
    dos_header += bytes([0x90, 0x00, 0x03, 0x00, 0x00, 0x00, 0x04, 0x00])
    dos_header += bytes([0x00, 0x00, 0xFF, 0xFF, 0x00, 0x00, 0xB8, 0x00])
    dos_header += bytes(16)
    dos_header += bytes(32)
    dos_header += (0x80).to_bytes(4, "little")  # e_lfanew: offset of the PE header
    stub = bytearray(bytes([0x0E, 0x1F, 0xBA, 0x0E, 0x00, 0xB4, 0x09, 0xCD, 0x21]))
    stub += b"This program cannot be run in DOS mode.\r\r\n$"
    stub += bytes(0x80 - len(dos_header) - len(stub))
    pe_header = b"PE" + bytes(2) + bytes([0x4C, 0x01]) + bytes(122)
    (HERE / "disguised.pdf").write_bytes(bytes(dos_header + stub) + pe_header)


def build_disguised_utf8_pdf() -> None:
    """A PE header that decodes cleanly as UTF-8 — see the module docstring.

    ASCII and NUL bytes only. NUL is valid UTF-8, so section 7.3's "decodes cleanly
    as UTF-8 -> TXT" rule would admit this file and hand an executable to the TXT
    reader. The NUL-byte rule in read_file_signature is what stops it.
    """
    header = bytearray(b"MZ")
    header += bytes(62)
    header += b"This program cannot be run in DOS mode.\r\n$"
    header += bytes(64)
    header += b"PE" + bytes(2) + bytes(60)
    (HERE / "disguised_utf8.pdf").write_bytes(bytes(header))


def _wrap(text: str, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


if __name__ == "__main__":
    build_txt()
    build_pdf()
    build_docx()
    build_xlsx()
    build_no_text_pdf()
    build_corrupt_docx()
    build_disguised_pdf()
    build_disguised_utf8_pdf()
    for path in sorted(HERE.glob("*")):
        if path.suffix in {".pdf", ".docx", ".xlsx", ".txt"}:
            print(f"{path.name:>22}  {path.stat().st_size:>7,} bytes")
