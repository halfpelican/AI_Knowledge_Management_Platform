"""Exceptions raised by the ingestion pipeline (FR-08, FR-09).

One base class so a caller may catch everything ingestion raises in a single
``except`` and answer the FR-08 status code, and two specific classes because the
two failures mean different things to the operator:

- ``UnsupportedFormatError`` — the pipeline was asked for a format it has no parser
  for. That is a configuration defect (a format reached ACCEPTED_FORMATS without a
  parser, D-15), not a bad upload.
- ``ExtractionError`` — the file really is of its declared format and the parser
  could not read it. That is a bad upload: the document is marked
  "Extraction failed" (constants.DOCUMENT_EXTRACTION_FAILED) and the original is
  still kept (CLAUDE.md invariant 8).

Both carry a message only. No vendor exception type escapes ingestion, so nothing
downstream has to import pypdf, python-docx or openpyxl to handle a failure.
"""


class IngestionError(Exception):
    """Base class for every failure raised inside apps.ingestion."""


class UnsupportedFormatError(IngestionError):
    """A format with no parser in this stack was routed for extraction."""


class ExtractionError(IngestionError):
    """A parser failed on a file of its own declared format."""
