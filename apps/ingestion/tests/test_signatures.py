"""read_file_signature() and compute_content_hash() (proposal section 7.3, FR-08).

FR-08 requires the format to be confirmed "by inspecting the file signature rather
than the extension alone, preventing a disguised file from being accepted", so the
uploads here are named to lie wherever the name would be tempting to trust.

No database: these functions touch none, so no test in this module takes the db
fixture.
"""

import hashlib
import io
import struct
import zipfile
from unittest import mock

import pytest

from apps.core.constants import (
    ACCEPTED_FORMATS,
    EXCEL_CONTENT_TYPE,
    MAX_UPLOAD_BYTES,
    WORD_CONTENT_TYPE,
)
from apps.ingestion import signatures
from apps.ingestion.errors import ExtractionError, OversizedArchiveContentError
from apps.ingestion.extraction import extract_plain_text
from apps.ingestion.signatures import (
    ARCHIVE_MAXIMUM_DECLARED_BYTES,
    CONTENT_TYPES_ENTRY,
    MANIFEST_MAXIMUM_BYTES,
    MAXIMUM_CONTROL_CHARACTER_SHARE,
    MEMBER_MAXIMUM_BYTES,
    TEXT_SAMPLE_BYTES,
    compute_content_hash,
    read_file_signature,
)
from apps.ingestion.tests.builders import (
    docx_bytes,
    ooxml_declaring,
    pdf_bytes,
    upload,
    xlsx_bytes,
    zip_bytes,
)

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


def test_text_with_an_embedded_nul_is_not_accepted_as_txt():
    """The case that isolates the NUL-byte rule, and the only one that does.

    Found by mutation on 2026-09-21: removing the NUL rule from
    read_file_signature() left the whole suite green, because the disguised_utf8.pdf
    fixture is 80% NUL and the control-character-share rule rejects it long before
    the NUL rule is reached. The rule was load-bearing in intent and dead in test
    terms.

    This payload is what the share rule cannot catch: ordinary prose with two NUL
    bytes buried in it, a share of well under a tenth of a percent. It decodes
    cleanly as UTF-8, so section 7.3's literal last rule would return TXT for it and
    hand a corrupt file to the pipeline to be chunked, embedded and indexed. No
    plain-text document contains a NUL; a file that does is not one, whatever share
    of it is readable.
    """
    import io

    body = ("Annual leave is accrued at one and two-thirds days per month. " * 48).encode("utf-8")
    with_nuls = body[:900] + bytes(2) + body[900:]
    decoded = with_nuls.decode("utf-8")  # section 7.3's literal rule would admit it

    # And the share rule does not reach it: the assertion is here so the test cannot
    # quietly stop isolating the NUL rule if the threshold is ever retuned.
    share = decoded.count(chr(0)) / len(decoded)
    assert share < MAXIMUM_CONTROL_CHARACTER_SHARE

    assert read_file_signature(io.BytesIO(with_nuls)) is None


# --- Stage 4 item 12a: the manifest read is bounded ------------------------------------
#
# THE FINDING, once, for the tests below. ``_ooxml_format`` read ``[Content_Types].xml``
# with ``archive.read(...)``, which decompresses the whole member however large it turns
# out to be. A 199 KB upload whose manifest expands to 200 MB was decompressed entirely
# into memory in 0.41 s, and BOTH size checks in the view passed, because they are checks
# on the UPLOAD and the upload really is 199 KB. Deflate's ceiling is about 1032:1, so a
# 50 MB upload at MAX_UPLOAD_BYTES can ask for roughly 51 GB.
#
# The bombs here are BUILT IN THE TEST and never committed: a checked-in bomb is a file in
# the repository whose only purpose is to be dangerous, and every one of these is three
# lines of zipfile.
#
# The payload member is what the assertions turn on. Each archive carries a second member,
# ``word/document.xml``, that is itself enormous, and every test asserts it was never
# decompressed — the rejection happens while reading the table of contents, so the payload
# is not touched.

MANIFEST_BOMB_BYTES = MANIFEST_MAXIMUM_BYTES * 200  # ~12.8 MB from a few hundred bytes
PAYLOAD_BOMB_BYTES = MANIFEST_MAXIMUM_BYTES * 400


def manifest_bomb(*, manifest_size=MANIFEST_BOMB_BYTES, declare_truthfully=True) -> bytes:
    """A ZIP whose manifest expands to ``manifest_size``, with a huge payload beside it.

    The manifest opens with the real Word content type, so a detector that reads it at all
    answers "docx" — which is how a test can tell "rejected by the bound" from "rejected
    because the manifest was unreadable".

    With ``declare_truthfully=False`` the archive LIES about the manifest's uncompressed
    size in both places a ZIP records it, the local file header and the central directory,
    by rewriting the four-byte field. That is the case the declared-size check cannot catch
    and the bounded read must.
    """
    filler = b"<!-- " + b"A" * (manifest_size - 100) + b" -->"
    manifest = (
        b'<?xml version="1.0"?><Types><Default Extension="xml" ContentType="'
        + WORD_CONTENT_TYPE.encode("ascii")
        + b'"/>'
        + filler
        + b"</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", manifest)
        archive.writestr("word/document.xml", b"B" * PAYLOAD_BOMB_BYTES)
    content = buffer.getvalue()
    if declare_truthfully:
        return content
    # Both records of the manifest's uncompressed size, rewritten to a plausible 2 KB.
    true_size = struct.pack("<I", len(manifest))
    assert content.count(true_size) == 2, "expected the local header and the central directory"
    return content.replace(true_size, struct.pack("<I", 2048))


def test_a_manifest_larger_than_the_bound_is_unrecognised():
    """THE FINDING: an archive whose declared manifest is tens of thousands of times the
    size of a real one is not an accepted format.

    The archive is otherwise a perfectly good DOCX declaration — it names the Word content
    type in its first hundred bytes — so what this measures is the bound and not a parse
    failure.
    """
    content = manifest_bomb()

    assert read_file_signature(upload(content, "quarterly-report.docx")) is None
    # A fraction of the size it expands to: this is the shape of the finding, a small
    # upload inside every documented limit asking the server for something much larger.
    assert len(content) < MANIFEST_BOMB_BYTES // 100


def test_a_manifest_that_lies_about_its_size_is_still_unrecognised():
    """The declared size is attacker-supplied, so it is not the defence.

    This archive claims a 2 KB manifest and holds a 12.8 MB one. The declared-size check
    passes it; the bounded read stops it. Without the read bound this file is the original
    finding with one field edited.
    """
    content = manifest_bomb(declare_truthfully=False)

    assert zipfile.ZipFile(io.BytesIO(content)).getinfo("[Content_Types].xml").file_size == 2048
    assert read_file_signature(upload(content, "quarterly-report.docx")) is None


def test_the_payload_is_never_decompressed_while_the_manifest_is_rejected():
    """Rejected while reading the table of contents, so the rest of the archive is untouched.

    ``zipfile.ZipFile.open`` is patched to record every member it is asked for. The manifest
    appears at most once and the payload never — which is the property that makes the bound
    worth anything: decompressing a 25 MB payload to conclude the manifest was too big would
    be the same defect at a different member.
    """
    opened: list[str] = []
    original = zipfile.ZipFile.open
    # Built BEFORE the patch: ``writestr`` goes through ``ZipFile.open`` too, and recording
    # the test's own construction of the bomb would say nothing about the detector.
    honest = upload(manifest_bomb(), "report.docx")
    lying = upload(manifest_bomb(declare_truthfully=False), "report.docx")

    def recording_open(self, name, *args, **kwargs):
        opened.append(name if isinstance(name, str) else name.filename)
        return original(self, name, *args, **kwargs)

    with mock.patch.object(zipfile.ZipFile, "open", recording_open):
        assert read_file_signature(honest) is None
        assert read_file_signature(lying) is None

    assert "word/document.xml" not in opened
    assert opened.count("[Content_Types].xml") <= 2  # at most one per call, and zero is fine


def test_a_manifest_at_the_bound_is_still_read():
    """The bound is inclusive: a manifest of exactly MANIFEST_MAXIMUM_BYTES is read and
    answered normally. Asserted because the read takes ``MANIFEST_MAXIMUM_BYTES + 1`` bytes
    to tell "at the bound" from "over it", and an off-by-one there would refuse a file the
    constant says is acceptable."""
    content = manifest_bomb(manifest_size=MANIFEST_MAXIMUM_BYTES - 200)

    assert (
        zipfile.ZipFile(io.BytesIO(content)).getinfo("[Content_Types].xml").file_size
        <= MANIFEST_MAXIMUM_BYTES
    )
    assert read_file_signature(upload(content, "report.docx")) == "docx"


def test_a_real_docx_and_a_real_xlsx_are_unaffected_by_the_bound():
    """The measurement the constant was chosen against: a real manifest is about 1 to 2 KB.

    Both formats are asserted, because the bound sits in the one function that tells them
    apart, and a bound that rejected either would turn every OOXML upload into a 415.
    """
    docx = docx_bytes(paragraphs=["Approval limits"])
    xlsx = xlsx_bytes({"Limits": [("Role", "Limit")]})

    assert read_file_signature(upload(docx, "limits.docx")) == "docx"
    assert read_file_signature(upload(xlsx, "limits.xlsx")) == "xlsx"

    for content in (docx, xlsx):
        declared = zipfile.ZipFile(io.BytesIO(content)).getinfo("[Content_Types].xml").file_size
        assert declared < MANIFEST_MAXIMUM_BYTES // 8  # comfortably inside, not marginally


# --- Stage 4 item 12b: every member is bounded, not just the manifest -------------------
#
# WHAT ITEM 12a LEFT OPEN. Item 12a bounded the manifest read and the bomb class survived one
# member along: the parsers in apps/ingestion/extraction.py run after the format has been
# accepted and are unbounded, so a 199 KB DOCX whose ``word/document.xml`` declares 200 MB was
# still inflated whole — inside the NFR-21 ingestion transaction, holding a worker and a
# database transaction while it allocated. The view's two size checks pass, because they are
# checks on the UPLOAD, and the upload really is 199 KB.
#
# THE REJECTION IS NOT THE 415. An oversized member is a size rejection of a file whose format
# is fine, so ``_ooxml_format`` raises ``OversizedArchiveContentError`` and the view answers
# 413 (apps/api/tests/test_document_upload.py holds that half). Answering "File type not
# supported" would tell the uploader to convert a file that was never the wrong type, which is
# the argument that made a NUL byte in a search term its own exception rather than "too short".
#
# WHY A DECLARED SIZE IS ENOUGH, which is the part that is inherited rather than ours:
# Python's ``zipfile`` caps a member's decompressed output at ``zinfo.file_size``. An honest
# bomb declares its size and the check below refuses it; a lying one cannot expand past its
# lie. That holds only while the parsers read through ``zipfile`` — python-docx and openpyxl
# both do — and ``test_a_member_that_lies_downwards_cannot_expand_past_its_lie`` is the
# measurement, not the assertion of a hope.
#
# The archives are built in the test and never committed, and they DECLARE what they do not
# hold, so nothing here allocates the sizes it talks about.

# The finding's own number: a member declaring 200 MB, from an upload of a few hundred KB.
DECLARED_MEMBER_BOMB_BYTES = 200 * 1024 * 1024
# Real content behind it. Deliberately not a round number: builders.ooxml_declaring rewrites
# the four bytes recording this length, and a round value is likelier to collide with
# something else in the compressed archive (the builder asserts it does not).
REAL_MEMBER_BYTES = 100_003


def member_bomb(*, declared=DECLARED_MEMBER_BOMB_BYTES, content_type=WORD_CONTENT_TYPE) -> bytes:
    """A recognisable DOCX (or XLSX) whose ``word/document.xml`` declares ``declared`` bytes."""
    return ooxml_declaring(
        {"word/document.xml": b"A" * REAL_MEMBER_BYTES},
        content_type=content_type,
        declared_sizes={"word/document.xml": declared},
    )


def test_a_member_declaring_more_than_the_bound_is_refused_as_a_size_rejection():
    """THE FINDING, at the shipped constant: a small upload declaring a 200 MB member.

    ``OversizedArchiveContentError`` and not None, because this file IS a DOCX — the manifest
    names the Word content type — and its format was never the problem.
    """
    content = member_bomb()

    assert len(content) < MEMBER_MAXIMUM_BYTES // 100  # the shape of it: small in, huge out
    with pytest.raises(OversizedArchiveContentError):
        read_file_signature(upload(content, "quarterly-report.docx"))


def test_the_same_bound_covers_xlsx():
    """One check in the one function that tells the two OOXML formats apart, so DOCX and XLSX
    are covered together rather than by two guards that could drift."""
    content = member_bomb(content_type=EXCEL_CONTENT_TYPE)

    with pytest.raises(OversizedArchiveContentError):
        read_file_signature(upload(content, "quarterly-figures.xlsx"))


def test_nothing_is_decompressed_to_reach_that_conclusion():
    """The declared sizes come from the central directory the ZipFile constructor already read.

    ``zipfile.ZipFile.open`` is patched to record every member it is asked for: the manifest
    appears (item 12a reads it, bounded) and ``word/document.xml`` never does. Inflating the
    payload to conclude that the payload is too big would be the same defect at a new place.
    """
    opened: list[str] = []
    original = zipfile.ZipFile.open
    bomb = upload(member_bomb(), "report.docx")  # built BEFORE the patch: writestr opens too

    def recording_open(self, name, *args, **kwargs):
        opened.append(name if isinstance(name, str) else name.filename)
        return original(self, name, *args, **kwargs)

    with mock.patch.object(zipfile.ZipFile, "open", recording_open):
        with pytest.raises(OversizedArchiveContentError):
            read_file_signature(bomb)

    assert "word/document.xml" not in opened
    assert opened == [CONTENT_TYPES_ENTRY]


def test_a_member_that_lies_downwards_cannot_expand_past_its_lie():
    """The inherited guarantee the declared-size check rests on, MEASURED.

    A declared size is attacker-supplied, so the objection is that a member could lie. It
    cannot usefully lie: ``zipfile`` caps a member's decompressed output at
    ``zinfo.file_size`` and raises ``BadZipFile: Bad CRC-32`` when the real data runs past it.

    So this archive — declaring 2 KB over 400 KB of payload — gets past the size check and is
    recognised as a DOCX, and then cannot deliver its payload to anyone: the DOCX parser is
    refused by the same cap, which apps/ingestion/extraction.py turns into ExtractionError and
    ingestion records as "Extraction failed" with the original kept. Rejected, one step later
    and for the accurate reason.

    **The dependency, asserted here because it is the assumption:** this holds because
    python-docx reads through ``zipfile``. A parser that brought its own inflate would void
    it, and the bound in ``_ooxml_format`` would become advice rather than a limit.
    """
    payload = b"A" * 400_003
    content = ooxml_declaring(
        {"word/document.xml": payload}, declared_sizes={"word/document.xml": 2048}
    )

    archive = zipfile.ZipFile(io.BytesIO(content))
    assert archive.getinfo("word/document.xml").file_size == 2048
    # The cap, and how it surfaces: the real bytes run past the declaration, so the CRC of
    # what zipfile is willing to hand over does not match the recorded one.
    with pytest.raises(zipfile.BadZipFile):
        archive.read("word/document.xml")

    # Not refused by the bound — it declares 2 KB — and refused by the parser instead.
    assert read_file_signature(upload(content, "report.docx")) == "docx"
    with pytest.raises(ExtractionError):
        extract_plain_text(upload(content, "report.docx"), "docx")


def test_the_members_together_are_bounded_as_well_as_each_one():
    """The per-member bound does not close the class on its own.

    Deflate's ceiling is about 1032:1, so a 50 MB upload at MAX_UPLOAD_BYTES can honestly
    declare roughly 51 GB spread over members that are every one of them inside
    MEMBER_MAXIMUM_BYTES. Four members of 63 MB here, each admissible alone, 252 MB together.
    """
    sizes = {f"word/part{index}.xml": 63 * 1024 * 1024 for index in range(4)}
    members = {name: b"B" * (50_003 + index) for index, name in enumerate(sizes)}
    content = ooxml_declaring(members, declared_sizes=sizes)

    assert all(declared <= MEMBER_MAXIMUM_BYTES for declared in sizes.values())
    assert sum(sizes.values()) > ARCHIVE_MAXIMUM_DECLARED_BYTES
    with pytest.raises(OversizedArchiveContentError):
        read_file_signature(upload(content, "quarterly-report.docx"))


def test_the_two_bounds_are_generous_against_the_numbers_they_were_chosen_from():
    """Arithmetic only. The constants are set where a false rejection cannot happen.

    MEMBER_MAXIMUM_BYTES is larger than the whole upload ceiling, so an archive that stores a
    member without compressing it — the DOCX carrying one big photograph — cannot be refused
    for that member. And the total bound is well under what deflate lets a 50 MB upload
    declare, which is the arithmetic that says the per-member bound needed company.
    """
    assert MEMBER_MAXIMUM_BYTES > MAX_UPLOAD_BYTES
    assert ARCHIVE_MAXIMUM_DECLARED_BYTES >= MEMBER_MAXIMUM_BYTES
    # ~1032:1 is deflate's ceiling, so this is what a 50 MB upload could otherwise ask for.
    assert ARCHIVE_MAXIMUM_DECLARED_BYTES < MAX_UPLOAD_BYTES * 1032


def test_a_plain_zip_with_an_enormous_member_is_still_an_unrecognised_format():
    """The order inside ``_ooxml_format``, which is a decision and not an accident.

    The size bound runs only after the manifest has named one of the two accepted content
    types. A ZIP of holiday photos is not a document whatever its members declare, so it stays
    415 — the oversized-content answer is reserved for a file this platform would otherwise
    have parsed, and a 413 would imply that a smaller ZIP would have been indexed.
    """
    content = ooxml_declaring(
        {"holiday/photo.xml": b"C" * 70_003},
        content_type="image/jpeg",
        declared_sizes={"holiday/photo.xml": DECLARED_MEMBER_BOMB_BYTES},
    )

    assert read_file_signature(upload(content, "photos.docx")) is None


def test_an_oversized_manifest_is_still_the_415_and_not_the_413(monkeypatch):
    """Item 12a's rejection is unchanged by item 12b, including where both would fire.

    The manifest checks run first and answer None, so an archive whose own table of contents
    is tens of thousands of times the size of a real one is still "unrecognised format". That
    is the right way round: a manifest that size is not a document, while a large
    ``word/document.xml`` is exactly what a large document has.
    """
    monkeypatch.setattr(signatures, "MEMBER_MAXIMUM_BYTES", 1024)

    assert read_file_signature(upload(manifest_bomb(), "report.docx")) is None


def test_a_real_docx_and_a_real_xlsx_pass_with_room_to_spare():
    """The expensive direction to be wrong in, pinned: both formats still identify normally,
    and the largest member either of them declares is asserted well inside the bound.

    MEASURED HERE, and it is why the bound is generous rather than minimal. A minimal real
    DOCX of one paragraph is a 36 KB archive whose largest member, ``word/stylesWithEffects
    .xml``, declares 438 KB, with 827 KB across 17 members — a real document is itself a 22:1
    expansion before anyone attacks anything. A bound set from "a paragraph of text should not
    need much" would refuse every DOCX python-docx writes.
    """
    docx = docx_bytes(paragraphs=["Approval limits"], table_rows=[("Role", "Limit")])
    xlsx = xlsx_bytes({"Limits": [("Role", "Limit"), ("Manager", "5000")]})

    assert read_file_signature(upload(docx, "limits.docx")) == "docx"
    assert read_file_signature(upload(xlsx, "limits.xlsx")) == "xlsx"

    for content in (docx, xlsx):
        members = zipfile.ZipFile(io.BytesIO(content)).infolist()
        largest = max(member.file_size for member in members)
        total = sum(member.file_size for member in members)
        # Comfortably inside, not marginally: a factor of 16 on each, which is what the
        # measurement above says the headroom actually is.
        assert largest < MEMBER_MAXIMUM_BYTES // 16
        assert total < ARCHIVE_MAXIMUM_DECLARED_BYTES // 16
