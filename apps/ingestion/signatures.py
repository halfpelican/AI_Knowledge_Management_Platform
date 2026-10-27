"""File-signature detection and content hashing for uploads (proposal section 7.3).

FR-08 requires the format to be "confirmed by inspecting the file signature rather
than the extension alone, preventing a disguised file from being accepted", so this
module answers from the bytes only. The filename never reaches it: the extension is
a claim, the signature is evidence (ACCEPTED_EXTENSIONS gates the upload control,
ACCEPTED_FORMATS gates the server, and only this module maps one file to the other).

Both public functions leave the file's position at 0 on every path, including on an
exception, because the caller stores the original bytes and then extracts text from
the same handle.
"""

import hashlib
import zipfile
from codecs import getincrementaldecoder

from apps.core.constants import (
    EXCEL_CONTENT_TYPE,
    MAX_UPLOAD_BYTES,
    PDF_SIGNATURE,
    SIGNATURE_LENGTH,
    WORD_CONTENT_TYPE,
    ZIP_SIGNATURE,
)
from apps.ingestion.errors import OversizedArchiveContentError

# The OOXML manifest every DOCX and XLSX carries at the root of its ZIP container.
# It names the package's own content type, which is how two formats that share the
# ZIP signature are told apart (proposal section 7.3).
CONTENT_TYPES_ENTRY = "[Content_Types].xml"

# How much of the file the TXT test reads. Enough to catch binary padding well past
# a header, small enough that a 50 MB upload is not pulled into memory to be
# classified. Kept here rather than in apps/core/constants.py: these two numbers are
# implementation detail of one detector, not a tuned platform constant from
# CLAUDE.md section 5, and nothing else in the system may read them.
TEXT_SAMPLE_BYTES = 8192

# Share of decoded characters that may be C0 control codes other than tab, newline
# and carriage return before the sample is judged binary. Non-zero because a stray
# form feed or bell in a legitimate export should not cost a user their upload; small
# because real prose has none at all.
MAXIMUM_CONTROL_CHARACTER_SHARE = 0.01

# Control characters that are ordinary in plain text and are not counted against it.
TEXT_CONTROL_CHARACTERS = frozenset("\t\n\r")

# Bytes read per iteration when hashing. 64 KB keeps a 50 MB upload off the heap.
HASH_BLOCK_BYTES = 64 * 1024

# Most of the OOXML manifest this detector will decompress (Stage 4 item 12a).
#
# **The finding.** ``_ooxml_format`` read the manifest with ``archive.read(...)``, which
# decompresses the whole member however large it turns out to be. A 199 KB upload whose
# ``[Content_Types].xml`` expands to 200 MB was decompressed entirely into memory in
# 0.41 s, and BOTH size checks in the view passed, because the checks are on the UPLOAD
# and the upload really is 199 KB. Deflate's ceiling is about 1032:1, so a 50 MB upload
# at MAX_UPLOAD_BYTES can ask for roughly 51 GB — from a request that is inside every
# documented limit. It is not a parser bug: no parser has run yet, and nothing has been
# validated beyond four leading bytes.
#
# **Why 64 KB.** Measured on this repository's own fixture corpus, a real manifest is
# 975 bytes (sample.xlsx) and 1,738 bytes (sample.docx); the function does not parse it
# and only scans it for two ASCII markers. 64 KB is roughly 37 times the larger of those
# and holds a package with some hundreds of ``Override`` entries — far past anything this
# platform will index — while capping what one upload can make the server allocate here
# at 64 KB rather than at whatever the archive declares. Too tight would refuse a
# legitimate file with a 415, which is the expensive direction to be wrong in, so the
# bound is generous rather than minimal: it exists to make the number FINITE, and
# 64 KB and 200 MB are the same answer to a user and a different answer to the server.
#
# Local to this module, like TEXT_SAMPLE_BYTES above and for the same reason: it is
# implementation detail of one detector rather than a tuned platform constant from
# CLAUDE.md section 5, and nothing else in the system may read it.
MANIFEST_MAXIMUM_BYTES = 64 * 1024

# Most one member of an accepted OOXML package may DECLARE, decompressed (Stage 4 item 12b).
#
# **What item 12a did not close.** Item 12a bounded the manifest read, and the bomb class
# survived one member further on: the parsers in apps/ingestion/extraction.py run after the
# format is accepted and are unbounded, so a 199 KB DOCX whose ``word/document.xml`` declares
# 200 MB was still inflated whole — inside the NFR-21 ingestion transaction, holding a worker
# and a database transaction while it allocated. Same class, one member along, and the checks
# in the view still pass because they are checks on the UPLOAD, which really is 199 KB.
#
# **The measurement.** A minimal real DOCX — one paragraph, written by python-docx — is a
# 36 KB archive declaring 827 KB across 17 members, the largest of them
# ``word/stylesWithEffects.xml`` at 438 KB. A real XLSX of two cells is 4.8 KB declaring
# 16.5 KB. So a legitimate document is itself a 22:1 expansion before anybody attacks
# anything, and a bound set from "a page of text cannot need much" would refuse every DOCX
# this stack can write.
#
# **Why 64 MB, and why the generous direction.** It is LARGER than MAX_UPLOAD_BYTES itself
# (50 MB), so no archive that fits the upload ceiling can be refused for a member it stores
# without compressing — the DOCX carrying one big JPEG is the case to protect, since already
# compressed media deflates at about 1:1 and python-docx reads every part of the package.
# Against the other end of the pipeline it is ~30 times the ~2.2 MB of extracted text that
# MAXIMUM_CHUNKS_PER_SOURCE will index at all, so nothing this platform could index reaches
# it. A false rejection of a real document is the expensive direction — the uploader's only
# remedy is to split a file that was never the problem — so the bound exists to make the
# number FINITE, not to make it small: 64 MB and 51 GB are the same answer to a user and a
# very different answer to the server.
MEMBER_MAXIMUM_BYTES = 64 * 1024 * 1024

# Most ALL the members together may declare, decompressed. Not in the brief for item 12b, and
# added because the per-member bound alone does not close the class it claims to: deflate's
# ceiling is about 1032:1, so a 50 MB upload at MAX_UPLOAD_BYTES can honestly declare ~51 GB
# spread over 800 members of 63 MB each, every one of them inside MEMBER_MAXIMUM_BYTES. Two
# bounds, one loop, one rejection path.
#
# Four times MAX_UPLOAD_BYTES. XML deflates at roughly 10:1, so a 50 MB spreadsheet of pure
# XML can honestly exceed this — and such a file is refused by MAXIMUM_CHUNKS_PER_SOURCE
# minutes later anyway, so the choice is only about WHICH refusal it gets and how much work
# it costs first. 200 MB is past every real document in this corpus by two orders of
# magnitude.
ARCHIVE_MAXIMUM_DECLARED_BYTES = 4 * MAX_UPLOAD_BYTES


def read_file_signature(file) -> str | None:
    """Identify an uploaded file's true format from its leading bytes.

    ``file`` is a Django ``UploadedFile`` or any seekable binary file object.
    Returns "pdf", "docx", "xlsx", "txt", or None when the content matches none of
    the four accepted formats (D-15). None means "unrecognised format", which the
    caller answers 415, and a corrupt ZIP is unrecognised rather than an error
    (proposal section 7.3).

    Raises ``OversizedArchiveContentError`` — the ONE exception from this module, added by
    Stage 4 item 12b — for a recognisable DOCX or XLSX that declares more decompressed
    content than ``_ooxml_format`` will let a parser inflate. It is deliberately not folded
    into the None: that file's format is not the problem and saying so would be untrue, and
    the caller answers it with a size rejection (413) rather than a format one. Nothing else
    here raises; every other rejection is still None.

    The position is restored to 0 before returning, on every path, including that one.
    """
    try:
        file.seek(0)
        header = file.read(SIGNATURE_LENGTH)

        # 1. PDF is decisive on its own.
        if header.startswith(PDF_SIGNATURE):
            return "pdf"

        # 2. DOCX and XLSX share the ZIP container signature; the archive's own
        #    manifest separates them.
        if header.startswith(ZIP_SIGNATURE):
            return _ooxml_format(file)

        # 3/4. TXT has no signature, so it is the last resort rather than the
        #      default, and it is decided on the content's shape.
        return _text_format(file, header)
    finally:
        file.seek(0)


def compute_content_hash(file) -> str:
    """SHA-256 hex digest of the whole file.

    FR-08 answers 409 for a duplicate upload and section 7.2 compares "by content
    hash rather than by filename, so that the same document uploaded under two
    different names is still caught"; this produces the value stored in
    Documents.content_hash.

    Read in blocks: an upload may be MAX_UPLOAD_BYTES (50 MB) and a digest never
    needs the whole file resident. The position is restored to 0.
    """
    digest = hashlib.sha256()
    try:
        file.seek(0)
        for block in iter(lambda: file.read(HASH_BLOCK_BYTES), b""):
            digest.update(block)
    finally:
        file.seek(0)
    return digest.hexdigest()


def _ooxml_format(file) -> str | None:
    """"docx", "xlsx" or None for a file whose first bytes are a ZIP signature.

    Every failure is None except one, the oversized-content rejection four paragraphs
    below, which is an exception because it is not a statement about the format. A
    truncated archive, an archive with no manifest, a plain
    ZIP of holiday photos and an OOXML format that is not one of the two accepted
    ones are all simply "not an accepted format", and telling them apart would give
    an uploader more detail about what the server tried than it needs. **A manifest over
    MANIFEST_MAXIMUM_BYTES joins that list** — an archive whose own table of contents is
    tens of thousands of times the size of a real one is not a document, and an uploader
    learning only "unrecognised format" is the correct amount of detail.

    **The read is BOUNDED, and both checks below matter for different reasons**
    (Stage 4 item 12a; see MANIFEST_MAXIMUM_BYTES for the measurement):

    - the DECLARED size (``ZipInfo.file_size``) is rejected first. It costs nothing, it
      comes from the archive's own central directory, and it stops the common case before a
      single byte is decompressed.
    - the declared size is ATTACKER-SUPPLIED, so it is not the defence. ``archive.open``
      streams the member and one bounded read takes at most MANIFEST_MAXIMUM_BYTES + 1
      bytes, so an archive that lies about its manifest's size — declaring 2 KB and
      expanding to 200 MB — is stopped by the read rather than by the claim. The extra
      byte is what tells "exactly at the bound" from "over it" without a second read.

    Nothing about the payload is decompressed on either path: the rejection happens while
    reading the table of contents, so the remaining members are never touched.

    **EVERY MEMBER IS BOUNDED TOO, and that is a different rejection** (Stage 4 item 12b;
    see MEMBER_MAXIMUM_BYTES). Once the manifest has identified the package as a DOCX or an
    XLSX, ``_oversized_declaration`` walks the central directory and
    ``OversizedArchiveContentError`` is raised for a member over MEMBER_MAXIMUM_BYTES or a
    total over ARCHIVE_MAXIMUM_DECLARED_BYTES. Four things about that check:

    - it is DECLARED size only, from the central directory the ZipFile constructor has
      already read. No member is decompressed by it.
    - **ASSUMED, NOT PROVEN HERE, and the assumption has a dependency.** A declared size is
      attacker-supplied, so the objection is that a member could lie. It cannot usefully
      lie: Python's ``zipfile`` caps a member's decompressed output at ``zinfo.file_size``
      and raises ``BadZipFile: Bad CRC-32`` when the real data runs past it — measured on
      this interpreter, where an archive declaring 1,024 bytes over 20 MB of payload raises
      on ``ZipFile.open(...).read()``, on ``ZipFile.read(...)`` and on a bounded read, and
      where patching the CRC to match the truncated prefix returns exactly the declared
      1,024 bytes. So the CAP is the guarantee and the CRC error is how it usually surfaces:
      an honest bomb declares its size and this check refuses it, a lying one cannot expand
      past its lie. **The assumption is that the parsers read through ``zipfile``** —
      ``python-docx`` (``docx.opc.phys_pkg``) and ``openpyxl`` (``openpyxl.reader.excel``)
      both do. A future parser that brought its own inflate would void this paragraph, and
      the bound would then be advice rather than a limit.
    - it runs only AFTER the manifest has named one of the two accepted content types, so a
      plain ZIP of holiday photos with a 200 MB member is still an unrecognised format (415)
      rather than a size rejection. The oversized-content answer is reserved for a file this
      platform would otherwise have parsed.
    - it does not touch PDF, and it does not need to. ``pypdf`` inflates object streams with
      no ZIP involved, so this ZIP-level scan never saw a PDF; D-50 recorded the PDF bomb
      class as still OPEN here. **It is now closed too, elsewhere** — bounded at the point
      pypdf inflates, in ``apps/ingestion/extraction.py`` (per-stream cap, page cap, operator
      budget and a text ceiling, D-81), not by this detector. The two defences stay separate
      because the two attacks are: an OOXML bomb is caught before any parser runs, by a
      declared size this ``zipfile``-backed stack cannot exceed; a PDF bomb is caught while
      pypdf parses, because there is no equivalent cheap declaration to trust.

    **The residue.** This is validation doing extraction's job: the bound belongs, in
    principle, to the code that inflates. It is here because one check with the archive
    handle already open beats three guards spread across three libraries, two of which do
    their reading before this module's caller gets a chance to wrap them.
    """
    try:
        file.seek(0)
        with zipfile.ZipFile(file) as archive:
            if archive.getinfo(CONTENT_TYPES_ENTRY).file_size > MANIFEST_MAXIMUM_BYTES:
                # The archive says so itself. Cheap, and true of an honest bomb.
                return None
            with archive.open(CONTENT_TYPES_ENTRY) as member:
                manifest = member.read(MANIFEST_MAXIMUM_BYTES + 1)
            if len(manifest) > MANIFEST_MAXIMUM_BYTES:
                # A declared size that was a lie. This is the check that holds.
                return None

            # errors="replace" because the manifest is only searched for two ASCII
            # markers; a mangled byte elsewhere in it must not raise out of a detector.
            declared = manifest.decode("utf-8", errors="replace")
            if WORD_CONTENT_TYPE in declared:
                file_format = "docx"
            elif EXCEL_CONTENT_TYPE in declared:
                file_format = "xlsx"
            else:
                return None

            # Inside the ``with``: the archive handle is open and its central directory is
            # already parsed, so this costs a walk over a list and no I/O at all.
            oversized = _oversized_declaration(archive)
    except (zipfile.BadZipFile, KeyError, OSError, EOFError, ValueError):
        # KeyError: no [Content_Types].xml entry, so not an OOXML package at all.
        return None

    if oversized is not None:
        # Raised outside the ``except`` above deliberately: OversizedArchiveContentError is
        # an IngestionError and none of those types, so it could not be swallowed there
        # either, but raising here makes that independent of the tuple's contents.
        raise OversizedArchiveContentError(oversized)
    return file_format


def _oversized_declaration(archive: zipfile.ZipFile) -> str | None:
    """A diagnostic message for an over-declared archive, or None when it is within bounds.

    Two bounds in one walk (Stage 4 item 12b): MEMBER_MAXIMUM_BYTES on the largest single
    member, and ARCHIVE_MAXIMUM_DECLARED_BYTES on the sum. The second exists because the
    first does not close the class on its own — 800 members of 63 MB each are all inside
    the per-member bound and total ~51 GB, which is what a 50 MB upload can honestly declare
    at deflate's ~1032:1 ceiling.

    Returns a message rather than raising, so the caller raises outside the ``except`` block
    that turns every archive fault into "unrecognised format".
    """
    total = 0
    for member in archive.infolist():
        if member.file_size > MEMBER_MAXIMUM_BYTES:
            return (
                f"Archive member {member.filename!r} declares {member.file_size} bytes "
                f"decompressed, over the {MEMBER_MAXIMUM_BYTES}-byte limit for one member."
            )
        total += member.file_size
        if total > ARCHIVE_MAXIMUM_DECLARED_BYTES:
            # Checked inside the loop, so a directory of a million entries stops being
            # counted at the point the answer is already decided.
            return (
                f"The archive's members declare over {ARCHIVE_MAXIMUM_DECLARED_BYTES} bytes "
                f"decompressed in total."
            )
    return None


def _text_format(file, header: bytes) -> str | None:
    """"txt" when the leading content is plain text, otherwise None.

    Section 7.3 says only "decodes cleanly as UTF-8", which is not sufficient on its
    own and would defeat the disguised-file rule FR-08 states explicitly. A Windows
    PE executable begins "MZ" and is padded with NUL bytes, and U+0000 is perfectly
    valid UTF-8, so a renamed .exe decodes without error and would be admitted as
    TXT, chunked, embedded and indexed. Two extra conditions close that:

    - any NUL byte means binary. No text document contains one.
    - more than MAXIMUM_CONTROL_CHARACTER_SHARE of the sample being C0 control
      characters other than tab, newline or carriage return means binary. This
      catches padded binaries that happen to avoid NUL.

    Only the first TEXT_SAMPLE_BYTES are examined, so a 50 MB file is classified
    without being read into memory. The sample may cut a multi-byte character in
    half, which is why an incremental decoder is used with final=False: a truncated
    trailing sequence is held rather than reported as invalid.
    """
    sample = header + file.read(max(TEXT_SAMPLE_BYTES - len(header), 0))
    if not sample:
        # An empty file decodes to nothing and is text by default. It is rejected
        # later by MINIMUM_CONTENT_LENGTH as "Insufficient content", which is the
        # accurate reason; claiming the format was unrecognised would not be.
        return "txt"

    decoder = getincrementaldecoder("utf-8")()
    try:
        text = decoder.decode(sample, False)
    except UnicodeDecodeError:
        return None

    if "\x00" in text:
        return None

    controls = sum(
        1 for character in text if character < " " and character not in TEXT_CONTROL_CHARACTERS
    )
    if text and controls / len(text) > MAXIMUM_CONTROL_CHARACTER_SHARE:
        return None

    return "txt"
