"""``download_filename``: the name FR-15's download serves a stored original under (D-75).

The rule, from D-75: the stored original's name with its LAST extension corrected to the format
the signature proved, compared case-insensitively, and one added when there is none. The route's
own tests (``apps/api/tests/test_document_download.py``) send the security cases through a real
upload and a real download; this file holds the rule itself, case by case.
"""

import pytest

from apps.core.constants import ACCEPTED_FORMATS
from apps.documents.downloads import download_filename


@pytest.mark.parametrize(
    ("stored_name", "file_format", "expected"),
    [
        # D-75's two named security cases: text that would run or render under its own name.
        ("Q3_budget.vbs", "txt", "Q3_budget.txt"),
        ("invoice.html", "txt", "invoice.txt"),
        # Only the last extension is replaced.
        ("report.pdf.exe", "txt", "report.pdf.txt"),
        # No extension: one is added.
        ("minutes", "docx", "minutes.docx"),
        # The extension already agrees with the bytes: the name is served as stored, and the
        # comparison ignores case.
        ("Report.PDF", "pdf", "Report.PDF"),
        ("notes.TXT", "txt", "notes.TXT"),
        ("budget.xlsx", "xlsx", "budget.xlsx"),
        ("Policy.Docx", "docx", "Policy.Docx"),
        # A genuine PDF uploaded as notes.txt is accepted as pdf (FR-08), and downloads as one.
        ("notes.txt", "pdf", "notes.pdf"),
        # A DOCX and an XLSX share the ZIP signature; the manifest decides, and so the name.
        ("figures.docx", "xlsx", "figures.xlsx"),
        # os.path.splitext's rule: a leading dot is not an extension, a trailing one is empty.
        (".profile", "txt", ".profile.txt"),
        ("notes.", "txt", "notes.txt"),
    ],
)
def test_the_last_extension_is_corrected_to_the_proven_format(stored_name, file_format, expected):
    assert download_filename(stored_name, file_format) == expected


@pytest.mark.parametrize(
    ("stored_name", "expected"),
    [
        ("documents/0b5c1c9e-6a43-4a83-9a0e-6d3f1b2b9b0d/Q3_budget.vbs", "Q3_budget.txt"),
        ("documents/0b5c1c9e-6a43-4a83-9a0e-6d3f1b2b9b0d/Report.PDF", "Report.txt"),
    ],
)
def test_only_the_stored_names_last_component_is_used(stored_name, expected):
    """``Document.file_path.name`` is ``documents/<id>/<name>``: the directory is never part of
    the name a download is offered under."""
    assert download_filename(stored_name, "txt") == expected


@pytest.mark.parametrize("file_format", sorted(ACCEPTED_FORMATS))
def test_every_accepted_format_corrects_a_misleading_name(file_format):
    assert download_filename("payload.exe", file_format) == f"payload.{file_format}"
    assert download_filename(f"kept.{file_format.upper()}", file_format) == f"kept.{file_format.upper()}"
