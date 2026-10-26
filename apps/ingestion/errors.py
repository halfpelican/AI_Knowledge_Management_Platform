"""Exceptions raised by the ingestion pipeline (FR-08, FR-09).

One base class so a caller may catch everything ingestion raises in a single
``except`` and answer the FR-08 status code, and four specific classes because the
four failures mean different things to the operator:

- ``UnsupportedFormatError`` — the pipeline was asked for a format it has no parser
  for. That is a configuration defect (a format reached ACCEPTED_FORMATS without a
  parser, D-15), not a bad upload.
- ``ExtractionError`` — the file really is of its declared format and the parser
  could not read it. That is a bad upload: the document is marked
  "Extraction failed" (constants.DOCUMENT_EXTRACTION_FAILED) and the original is
  still kept (CLAUDE.md invariant 8).
- ``TooLargeToExtractError`` — a subclass of ExtractionError: a readable PDF refused by
  one of D-81's extraction bounds. Marked "Too large to index", not "Extraction failed",
  because a retry fails at the same bound every time (D-51).
- ``OversizedArchiveContentError`` — a DOCX or XLSX whose own table of contents
  declares more decompressed content than the detector will let a parser inflate.
  Raised during detection, before any parser runs, and answered with a size
  rejection rather than a format one (Stage 4 item 12b).

Each carries a message; ``TooLargeToExtractError`` also carries a ``limit_message`` safe to
show the uploader. No vendor exception type escapes ingestion, so nothing
downstream has to import pypdf, python-docx or openpyxl to handle a failure.
"""


class IngestionError(Exception):
    """Base class for every failure raised inside apps.ingestion."""


class UnsupportedFormatError(IngestionError):
    """A format with no parser in this stack was routed for extraction."""


class ExtractionError(IngestionError):
    """A parser failed on a file of its own declared format."""


class TooLargeToExtractError(ExtractionError):
    """A PDF crossed one of D-81's extraction bounds, so its text was not read.

    Raised by ``extraction._extract_pdf`` for the per-stream caps on decoded and stored
    size (pypdf's ``LimitReachedError``), the page cap and the operator budget. The text
    ceiling does NOT raise this: it returns the text read so far and leaves the refusal to
    the MAXIMUM_CHUNKS_PER_SOURCE check in ``documents.py``, so that bound has one refusal
    path (D-81 item 4).

    ``limit_message`` is the bound's LIMIT SENTENCE alone: fixed text, one per bound, saying
    what the file met and whether splitting it would help, and saying nothing about what
    happened to the file, because that differs by route. ``documents.py`` stores the
    document and answers "Too large to index" rather than "Extraction failed" (D-81 item 5:
    the file is a readable PDF, and a retry fails at the same bound every time, D-51's
    argument), prefixing the sentence with the fact that the document was stored. The
    meetings view (``MeetingsView._transcript_from``) has stored nothing, so it answers
    FR-09's 400 with the sentence as it is. ``str(exception)`` is the diagnostic and stays
    on the server.

    **A subclass of ExtractionError on purpose.** A caller that catches ExtractionError and
    does not know this class still handles it, rather than letting it escape as a 500.
    """

    def __init__(self, limit_message: str, diagnostic: str = ""):
        super().__init__(diagnostic or limit_message)
        self.limit_message = limit_message


class OversizedArchiveContentError(IngestionError):
    """An OOXML package declares more decompressed content than may be inflated.

    Raised by ``signatures._ooxml_format`` (Stage 4 item 12b) for an archive that is
    recognisably a DOCX or an XLSX and whose central directory declares either one member
    over ``MEMBER_MAXIMUM_BYTES`` or a total over ``ARCHIVE_MAXIMUM_DECLARED_BYTES``.

    **A DISTINCT class, and NOT the None that means "unrecognised format"**, for the same
    reason ``SearchQueryContainsNullCharacter`` is not ``SearchQueryTooShort``
    (apps/retrieval/search.py): the two would map to different status codes anyway, and
    refusing a file that really is a DOCX with "the format is not one of the four accepted
    ones" states something false about the request. An error message that misstates the
    reason is worse than an extra exception class — here it would tell the uploader to
    convert a file whose format was never the problem.

    The message carries the offending member and the two numbers, for whoever diagnoses it
    later. The VIEW answers with its own fixed text: ``str(exception)`` names an internal
    part of the archive, which is no more use to an uploader than a path under MEDIA_ROOT.
    """
