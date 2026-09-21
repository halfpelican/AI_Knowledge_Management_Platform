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
    PDF_SIGNATURE,
    SIGNATURE_LENGTH,
    WORD_CONTENT_TYPE,
    ZIP_SIGNATURE,
)

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


def read_file_signature(file) -> str | None:
    """Identify an uploaded file's true format from its leading bytes.

    ``file`` is a Django ``UploadedFile`` or any seekable binary file object.
    Returns "pdf", "docx", "xlsx", "txt", or None when the content matches none of
    the four accepted formats (D-15). None is the only rejection: an unrecognised
    upload is answered 415 by the caller, never by an exception from here, and a
    corrupt ZIP is unrecognised rather than an error (proposal section 7.3).

    The position is restored to 0 before returning, on every path.
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

    Every failure is None. A truncated archive, an archive with no manifest, a plain
    ZIP of holiday photos and an OOXML format that is not one of the two accepted
    ones are all simply "not an accepted format", and telling them apart would give
    an uploader more detail about what the server tried than it needs.
    """
    try:
        file.seek(0)
        with zipfile.ZipFile(file) as archive:
            manifest = archive.read(CONTENT_TYPES_ENTRY)
    except (zipfile.BadZipFile, KeyError, OSError, EOFError, ValueError):
        # KeyError: no [Content_Types].xml entry, so not an OOXML package at all.
        return None

    # errors="replace" because the manifest is only searched for two ASCII markers;
    # a mangled byte elsewhere in it must not raise out of a detector.
    declared = manifest.decode("utf-8", errors="replace")
    if WORD_CONTENT_TYPE in declared:
        return "docx"
    if EXCEL_CONTENT_TYPE in declared:
        return "xlsx"
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
