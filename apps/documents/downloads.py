"""The name a stored original downloads under (FR-15's download, docs/decisions.md D-75).

Kept a pure function, apart from the view, so every case of D-75's naming rule is tested
directly rather than only through a request.
"""

import posixpath


def download_filename(stored_name: str, file_format: str) -> str:
    """The stored original's own name, with its last extension corrected to ``file_format``.

    ``stored_name`` is ``Document.file_path.name`` (``documents/<id>/<name>``); only its last
    component is used. Storage names always use ``/``, Windows included, so the POSIX form is
    used whatever the server's platform. ``file_format`` is ``Document.file_type``, which
    ``read_file_signature`` proved from the bytes at upload.

    **Why the name is corrected at all (D-75).** The server never reads an upload's extension:
    ``ACCEPTED_EXTENSIONS`` gates only the upload control in the browser. So UTF-8 text sent
    through the API as ``Q3_budget.vbs`` or ``invoice.html`` is accepted as txt and stored under
    that name, and served under it unchanged it would download as something a colleague's
    machine runs or renders. Corrected, it downloads as ``Q3_budget.txt`` and ``invoice.txt``.

    - The comparison ignores case, so ``Report.PDF`` proven to be a pdf keeps its name.
    - Only the last extension is replaced: ``report.pdf.exe`` proven to be txt is
      ``report.pdf.txt``.
    - A name with no extension gains one: ``minutes`` proven to be docx is ``minutes.docx``.

    What counts as an extension is ``os.path.splitext``'s rule, so a leading dot is not one:
    ``.profile`` as txt is ``.profile.txt``, and a trailing dot is an empty one: ``notes.`` as
    txt is ``notes.txt``.
    """
    basename = posixpath.basename(stored_name)
    root, extension = posixpath.splitext(basename)
    if extension[1:].lower() == file_format:
        return basename
    return f"{root}.{file_format}"
