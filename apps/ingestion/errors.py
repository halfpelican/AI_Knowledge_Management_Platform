"""Exceptions raised by the ingestion pipeline (FR-08, FR-09).

One base class so a caller may catch everything ingestion raises in a single
``except`` and answer the FR-08 status code, and three specific classes because the
three failures mean different things to the operator:

- ``UnsupportedFormatError`` — the pipeline was asked for a format it has no parser
  for. That is a configuration defect (a format reached ACCEPTED_FORMATS without a
  parser, D-15), not a bad upload.
- ``ExtractionError`` — the file really is of its declared format and the parser
  could not read it. That is a bad upload: the document is marked
  "Extraction failed" (constants.DOCUMENT_EXTRACTION_FAILED) and the original is
  still kept (CLAUDE.md invariant 8).
- ``OversizedArchiveContentError`` — a DOCX or XLSX whose own table of contents
  declares more decompressed content than the detector will let a parser inflate.
  Raised during detection, before any parser runs, and answered with a size
  rejection rather than a format one (Stage 4 item 12b).

Both carry a message only. No vendor exception type escapes ingestion, so nothing
downstream has to import pypdf, python-docx or openpyxl to handle a failure.
"""


class IngestionError(Exception):
    """Base class for every failure raised inside apps.ingestion."""


class UnsupportedFormatError(IngestionError):
    """A format with no parser in this stack was routed for extraction."""


class ExtractionError(IngestionError):
    """A parser failed on a file of its own declared format."""


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
