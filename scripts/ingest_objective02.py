"""Objective 02: ingest the verification corpus through the real API, and record what happened.

Objective 02 (proposal section 2, due 2 October): "every valid item must reach indexed status
and return its own content when searched for a phrase known to be in it; every invalid item
must be refused with its documented error rather than partly ingested; a document of twenty
pages or fewer must finish processing within sixty seconds."

Everything goes through the HTTP API a browser uses, against a running server:

- documents through FR-08's upload, ``POST /api/documents`` (multipart);
- transcripts through FR-09's paste path, ``POST /api/meetings`` (JSON ``transcript_text``);
- each valid item's phrase through FR-12's keyword search, ``GET /api/search?q=``, from an
  Administrator session and from an Employee session. An Administrator-only item must be
  found by the Administrator and must leave no trace — title or identifier — in the
  Employee's reply (FR-11).

The order is the manifest's: every valid item first, so D03 is indexed before B01, its
byte-identical copy, is sent and refused 409. The oversized item I02 is not committed: a
file over MAX_UPLOAD_BYTES that starts with a PDF signature is written to a temporary
directory at run time, so that it is refused for its size (413) and not its format.

**The one check that is not through the API.** "Rather than partly ingested" is a claim about
chunk rows, and no route returns chunks. After the run the script reads the ContentChunk count
for each document the API created, through the Django ORM, read-only. It is labelled as such in
the results.

Usage, with the server and FLM running (``waitress-serve`` as D-85 starts it, and ``flm serve``)::

    $env:KMP_CORPUS_ADMIN_EMAIL = "..."      # an Administrator account
    $env:KMP_CORPUS_ADMIN_PASSWORD = "..."
    $env:KMP_CORPUS_EMPLOYEE_EMAIL = "..."   # an Employee account
    $env:KMP_CORPUS_EMPLOYEE_PASSWORD = "..."
    .venv/Scripts/python.exe scripts/ingest_objective02.py [--base-url http://127.0.0.1:8000] \
        [--output-dir corpus/objective-02/runs/<date>]

docs/measurement-runbook.md gives the commands for the item 6 run, with its own database.

It refuses to run if any manifest title is already in the repository or the meetings list, so
a second run cannot mix duplicates and 409s into the evidence. ``manifest.json`` is the only
manifest this script reads; a spreadsheet beside it is not consulted.

**Where the results go.** ``results.json`` and ``results.md`` are written to ``--output-dir``,
which defaults to this folder, beside the manifest. A full run refuses to start if that folder
already holds a ``results.json``, so the 6 October evidence beside the manifest is never
overwritten (D-84 decision 1): a new run writes to a dated folder of its own, for example
``--output-dir corpus/objective-02/runs/2026-10-27``.

**What a full run records, and what it checks first (D-83, D-84, D-85).** Before signing in, it
runs scripts/check_flm.py's checks and refuses unless they pass and FLM is v0.9.39, because an
ingestion on a noisy FLM stores noise as the index. It refuses if the database its own process
reads is ``kmp``. It observes the server at ``--base-url`` (scripts/server_record.py: the
listening process's command line and the reply's Server header) and refuses one that is
positively not D-85's Waitress at 24 threads, unless ``--any-server`` is passed. The results
carry the commit SHA, whether tracked files had uncommitted changes, the FLM version, the
database NAME (never its URL), and the server, its version and its thread count.

**The chunk count reads the database this process sees, which must be the server's.** The
measurement server has its own ``DATABASE_URL`` (D-84), and a value set in the shell wins over
``.env``, so set the same one in this shell. If a document the server created is not in this
process's database, its chunk count is not read, and the item is marked as missed rather than
passing with a count of nothing.

``--search-only`` re-runs the phrase searches of an earlier run, without uploading anything:
re-uploading would only be refused 409 for every document. It reads the identifiers the earlier
run recorded in ``results.json`` in ``--output-dir``, searches each valid item's CURRENT manifest
phrase from both sessions, re-judges every item, and rewrites the results there. Every ingestion
outcome (status, time, pages, chunks) is kept from the earlier run, and the results say which run
each column comes from.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlencode, urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import check_flm  # noqa: E402  scripts/check_flm.py, the D-83 gate
import measurement_record  # noqa: E402  scripts/measurement_record.py
import server_record  # noqa: E402  scripts/server_record.py, D-85's server record

CORPUS = REPOSITORY_ROOT / "corpus" / "objective-02"
MANIFEST = CORPUS / "manifest.json"
REFUSED = 2  # exit code: refused before anything was uploaded

# Objective 02's bound, and the page count it applies to.
PROCESSING_BOUND_SECONDS = 60
PAGE_BOUND = 20
# A generous client timeout: one synchronous upload embeds every chunk on the NPU, and the
# server's own worst case is far longer than the bound being measured.
REQUEST_TIMEOUT_SECONDS = 900
OVERSIZE_EXTRA_BYTES = 1024 * 1024  # how far past MAX_UPLOAD_BYTES the generated file goes

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
}


# --- A minimal session-cookie HTTP client (standard library only) ------------------------


class ApiSession:
    """One signed-in browser, as far as the server can tell: session and CSRF cookies,
    and the CSRF header on unsafe requests (D-21)."""

    def __init__(self, base_url: str):
        parts = urlsplit(base_url)
        self.base_url = base_url.rstrip("/")
        self.host = parts.hostname
        self.port = parts.port or (443 if parts.scheme == "https" else 80)
        self.https = parts.scheme == "https"
        self.cookies: dict[str, str] = {}
        # The last reply's headers, names lower-cased: the Server header names the server
        # a run went through (D-85).
        self.last_headers: dict[str, str] = {}

    def _connection(self):
        cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=REQUEST_TIMEOUT_SECONDS)

    def request(self, method, path, *, json_body=None, body=None, content_type=None, query=None):
        """Returns (status, parsed JSON or text or None, seconds, transport_note)."""
        url = path + ("?" + urlencode(query) if query else "")
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            content_type = "application/json"
        headers = {"Accept": "application/json", "Host": f"{self.host}:{self.port}"}
        if body is not None:
            headers["Content-Type"] = content_type
            headers["Content-Length"] = str(len(body))
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if method not in ("GET", "HEAD") and "csrftoken" in self.cookies:
            headers["X-CSRFToken"] = self.cookies["csrftoken"]
            headers["Referer"] = self.base_url + "/"

        connection = self._connection()
        note = None
        started = time.perf_counter()
        connection.putrequest(method, url, skip_host=True, skip_accept_encoding=True)
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.endheaders()
        if body is not None:
            # Sent in pieces, so a server that answers before reading the whole body (the
            # 413 on a declared Content-Length) is still heard: the send is abandoned and the
            # response it already wrote is read.
            view = memoryview(body)
            try:
                for offset in range(0, len(body), 1024 * 1024):
                    connection.send(view[offset : offset + 1024 * 1024])
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as exc:
                note = f"server closed the connection while the body was being sent ({type(exc).__name__})"
        try:
            response = connection.getresponse()
            raw = response.read()
            status = response.status
            self.last_headers = {header.lower(): value for header, value in response.getheaders()}
            for header, value in response.getheaders():
                if header.lower() == "set-cookie":
                    cookie = SimpleCookie()
                    cookie.load(value)
                    for key, morsel in cookie.items():
                        self.cookies[key] = morsel.value
        except (ConnectionResetError, ConnectionAbortedError, http.client.RemoteDisconnected) as exc:
            status, raw = None, b""
            note = (note + "; " if note else "") + f"no response read ({type(exc).__name__})"
        finally:
            connection.close()
        seconds = time.perf_counter() - started
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = raw[:500].decode("utf-8", "replace")
        return status, parsed, seconds, note


def multipart(fields: list[tuple[str, str]], file_field: str, filename: str, data: bytes, content_type: str):
    boundary = f"----kmp-objective02-{uuid.uuid4().hex}"
    parts = []
    for name, value in fields:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
            f"filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n"
        ).encode()
    )
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def sign_in(base_url: str, email: str, password: str, expected_role: str) -> ApiSession:
    session = ApiSession(base_url)
    status, body, _, note = session.request(
        "POST", "/api/auth/login", json_body={"email": email, "password": password}
    )
    if status != 200:
        sys.exit(f"Could not sign in as {email}: HTTP {status} {body} {note or ''}")
    if body.get("role") != expected_role:
        sys.exit(f"{email} signed in with role {body.get('role')!r}, expected {expected_role!r}")
    return session


# --- The run ---------------------------------------------------------------------------


def page_count(path: Path) -> int | None:
    """Pages for a PDF; None for formats with no page in the file (DOCX, XLSX, TXT)."""
    if path.suffix.lower() != ".pdf":
        return None
    try:
        from pypdf import PdfReader

        return len(PdfReader(path).pages)
    except Exception:  # noqa: BLE001 - a corrupt PDF has no countable pages; that is a result
        return None


def oversized_file(directory: Path, max_upload_bytes: int) -> Path:
    path = directory / "I02_oversized_board_pack.pdf"
    with path.open("wb") as handle:
        handle.write(b"%PDF-1.7\n% Objective 02 oversized item, generated at run time\n")
        remaining = max_upload_bytes + OVERSIZE_EXTRA_BYTES
        block = b"0" * (1024 * 1024)
        while remaining > 0:
            handle.write(block[: min(len(block), remaining)])
            remaining -= len(block)
    return path


def ingest(item, sessions, temp_dir, max_upload_bytes):
    uploader = sessions[item["uploader"]]
    if item["kind"] == "transcript":
        text = (CORPUS / item["file"]).read_text(encoding="utf-8")
        payload = {
            "title": item["title"],
            "meeting_date": item["meeting_date"],
            "transcript_text": text,
            "visible_to_roles": item["visible_to_roles"],
        }
        status, body, seconds, note = uploader.request("POST", "/api/meetings", json_body=payload)
        return status, body, seconds, note, None

    path = oversized_file(temp_dir, max_upload_bytes) if item.get("generated_at_run_time") else CORPUS / item["file"]
    fields = [("title", item["title"])]
    if item["department"]:
        fields.append(("department", item["department"]))
    fields += [("visible_to_roles", role) for role in item["visible_to_roles"]]
    data = path.read_bytes()
    body, content_type = multipart(
        fields, "file", path.name, data, CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    )
    status, response, seconds, note = uploader.request(
        "POST", "/api/documents", body=body, content_type=content_type
    )
    return status, response, seconds, note, path


def search_finds(session, phrase, source_id, title):
    """(found, other_results, trace_in_bytes) for one search from one session."""
    status, body, _, note = session.request("GET", "/api/search", query={"q": phrase})
    if status != 200 or not isinstance(body, dict):
        return {"status": status, "error": body, "note": note}
    results = body["documents"]["results"] + body["meetings"]["results"]
    found = any(result["source_id"] == source_id for result in results)
    raw = json.dumps(body)
    return {
        "status": status,
        "found": found,
        "total_count": body["total_count"],
        "other_results": [r["title"] for r in results if r["source_id"] != source_id],
        "trace_in_bytes": bool(source_id and source_id in raw) or bool(title and title in raw),
    }


def orm_database_name() -> str:
    """The NAME of the database this process's ORM reads. Never the URL or a credential."""
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings

    return str(settings.DATABASES["default"].get("NAME", ""))


def chunk_counts(document_ids):
    """Read-only, through the ORM: how many chunks each created document has.

    None for a document whose row is not in this process's database: the script is then
    reading a different database from the server's, and a count of 0 would read as "nothing
    was partly ingested" when nothing was looked at.
    """
    orm_database_name()  # sets Django up
    from apps.documents.models import ContentChunk, Document

    present = {str(pk) for pk in Document.objects.filter(id__in=document_ids).values_list("id", flat=True)}
    return {
        doc_id: (ContentChunk.objects.filter(source_id=doc_id).count() if str(doc_id) in present else None)
        for doc_id in document_ids
    }


def judge(item, outcome):
    """Compare one item's outcome with what the manifest expects. Returns a list of misses."""
    expected = item["expected"]
    misses = []
    if outcome["http_status"] != expected["http_status"]:
        misses.append(f"HTTP {outcome['http_status']}, expected {expected['http_status']}")
    if item["kind"] == "document" and outcome.get("document_status") != expected["document_status"]:
        misses.append(f"status {outcome.get('document_status')!r}, expected {expected['document_status']!r}")
    if item["kind"] == "transcript" and outcome.get("meeting_status") != expected["meeting_status"]:
        misses.append(f"status {outcome.get('meeting_status')!r}, expected {expected['meeting_status']!r}")
    if item["kind"] == "invalid" and expected["document_status"] is not None:
        if outcome.get("document_status") != expected["document_status"]:
            misses.append(f"status {outcome.get('document_status')!r}, expected {expected['document_status']!r}")
    if item["kind"] == "invalid" and expected["document_status"] is None and outcome.get("source_id"):
        misses.append("a record was created for an item that should have been refused outright")
    if item["kind"] == "invalid" and outcome.get("chunks"):
        misses.append(f"{outcome['chunks']} chunk(s) written for an invalid item: partly ingested")
    if outcome.get("chunk_count_unread"):
        misses.append(
            "its record is not in the database this script reads, so its chunks were not counted: "
            "set this shell's DATABASE_URL to the server's"
        )
    for role in expected.get("found_by", []):
        search = outcome["search"].get(role, {})
        if not search.get("found"):
            misses.append(f"{role} search for its phrase did not find it")
        if search.get("other_results"):
            misses.append(f"{role} search for its phrase also found {search['other_results']}")
    for role in expected.get("hidden_from", []):
        search = outcome["search"].get(role, {})
        if search.get("found") or search.get("trace_in_bytes"):
            misses.append(f"{role} search reached an item outside its scope")
    pages = outcome.get("pages")
    if (
        item["kind"] != "invalid"
        and (pages is None or pages <= PAGE_BOUND)
        and outcome["seconds"] > PROCESSING_BOUND_SECONDS
    ):
        misses.append(f"took {outcome['seconds']:.1f}s, over the {PROCESSING_BOUND_SECONDS}s bound")
    return misses


def write_results(manifest, outcomes, started_at, base_url, searches_rerun=None, *,
                  output_dir=CORPUS, record=None):
    results = {
        "run_started": started_at,
        "searches_rerun": searches_rerun,
        "base_url": base_url,
        "record": record,
        "manifest": "corpus/objective-02/manifest.json — the only manifest the script reads",
        "criteria": manifest["criteria"],
        "items": outcomes,
        "missed": [o["id"] for o in outcomes if o["misses"]],
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        "# Objective 02 — ingestion results",
        "",
        f"Run started {started_at} against `{base_url}`, by `scripts/ingest_objective02.py`, from",
        "`corpus/objective-02/manifest.json`. Times are the wall-clock time of the synchronous upload",
        "or paste request, which includes extraction, chunking and embedding on the NPU. The chunk",
        "count is the one check made outside the API: a read-only ORM count after the run.",
        "",
        "`corpus/objective-02/manifest.json` is the only manifest the script reads. The team's",
        "`Objective02_Manifest.xlsx` was the source it was transcribed from, and is not read.",
        "",
    ]
    if record:
        flm = record.get("flm_version") or {}
        changes = " Tracked files had UNCOMMITTED changes." if record.get("uncommitted_tracked_changes") else ""
        lines += [
            f"Commit `{record.get('commit_sha')}`.{changes} FLM `{flm.get('cli')}` by `flm version`,",
            f"`{flm.get('server')}` by the server. Database `{record.get('database')}`.",
        ]
        if record.get("server"):
            # D-85 decision 4: the server, its version and the thread count, beside the result.
            lines.append(f"Server: {server_record.summary(record['server'])}.")
            if record.get("server_gate_waived"):
                lines.append("**This server is not D-85's**, and the run was made with `--any-server`.")
        lines.append("")
    if searches_rerun:
        lines += [
            f"**The search columns were re-run on {searches_rerun}** with `--search-only`, against the",
            "manifest's current phrases, after D-71 made keyword search collapse whitespace. Every",
            "other column is from the ingestion run above. Nothing was uploaded a second time.",
            "",
        ]
    lines += [
        "| ID | Kind | Scope | HTTP | Status | Seconds | Pages | Chunks | Admin finds | Employee finds | Result |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for o in outcomes:
        def found(role):
            search = o["search"].get(role)
            if not search:
                return "—"
            return "yes" if search.get("found") else ("no (trace in bytes)" if search.get("trace_in_bytes") else "no")

        lines.append(
            "| {id} | {kind} | {scope} | {http} | {status} | {seconds:.1f} | {pages} | {chunks} | {admin} | {employee} | {result} |".format(
                id=o["id"],
                kind=o["kind"],
                scope=", ".join(o["visible_to_roles"]),
                http=o["http_status"],
                status=o.get("document_status") or o.get("meeting_status") or "—",
                seconds=o["seconds"],
                pages=o["pages"] if o["pages"] is not None else "—",
                chunks=o["chunks"] if o["chunks"] is not None else "—",
                admin=found("Administrator"),
                employee=found("Employee"),
                result="PASS" if not o["misses"] else "MISS: " + "; ".join(o["misses"]),
            )
        )
    missed = [o for o in outcomes if o["misses"]]
    lines += ["", f"Items that missed their expected result: {', '.join(o['id'] for o in missed) or 'none'}."]
    slow = [
        o["id"]
        for o in outcomes
        if o["kind"] != "invalid" and (o["pages"] is None or o["pages"] <= PAGE_BOUND)
        and o["seconds"] > PROCESSING_BOUND_SECONDS
    ]
    lines.append(
        f"Documents of {PAGE_BOUND} pages or fewer over {PROCESSING_BOUND_SECONDS}s: {', '.join(slow) or 'none'}."
    )
    (output_dir / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return missed, slow


def output_dir_problem(output_dir: Path) -> str | None:
    """Why a full run may not write to ``output_dir``, or None. Never overwrites evidence."""
    existing = Path(output_dir) / "results.json"
    if existing.exists():
        return (
            f"{existing} already exists, and a run never overwrites earlier evidence (D-84). "
            "Pass --output-dir with a new folder, e.g. corpus/objective-02/runs/<date>."
        )
    return None


def gate_problems() -> tuple[list[str], dict]:
    """check_flm.py's checks and the pinned version, before anything is uploaded (D-83).

    Returns (reasons to refuse, the FLM version record). Reads FLM_BASE_URL from this
    process's environment, as check_flm.py does, so set the server's value in this shell.
    """
    base_url, _ = check_flm.read_env("FLM_BASE_URL", check_flm.DEFAULT_BASE_URL)
    api_key, _ = check_flm.read_env("FLM_API_KEY", check_flm.DEFAULT_API_KEY)
    chat_model, _ = check_flm.read_env("FLM_CHAT_MODEL", check_flm.DEFAULT_CHAT_MODEL)
    embed_model, _ = check_flm.read_env("FLM_EMBED_MODEL", check_flm.DEFAULT_EMBED_MODEL)
    print(f"FLM gate: scripts/check_flm.py's checks against {base_url} (D-83)")
    checks = check_flm.run_checks(base_url, api_key, chat_model, embed_model)
    version = check_flm.flm_version(base_url, api_key)
    problems = []
    if not check_flm.checks_passed(checks):
        failed = "; ".join(f"{name}: {status}" for name, status, _ in checks if status != "PASS")
        problems.append(f"scripts/check_flm.py's checks did not pass ({failed})")
    problems += version.problems()
    print(f"\nFLM version: {version.summary()}")
    return problems, version.as_record()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=os.environ.get("KMP_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--max-upload-bytes", type=int, default=50 * 1024 * 1024,
                        help="MAX_UPLOAD_BYTES (apps/core/constants.py); the generated I02 exceeds it")
    parser.add_argument("--search-only", action="store_true",
                        help="re-run the phrase searches of the run in results.json; upload nothing")
    parser.add_argument("--output-dir", type=Path, default=CORPUS,
                        help="where results.json and results.md go (default: beside the manifest); "
                             "a full run refuses a folder that already holds results.json")
    parser.add_argument("--any-server", action="store_true",
                        help="run against a server that is not D-85's Waitress at 24 threads; "
                             "the results say so")
    args = parser.parse_args()

    # Cheap refusals first, before any credential is read or any request is sent.
    if not args.search_only:
        problem = output_dir_problem(args.output_dir)
        if problem:
            print(f"REFUSED: {problem}\nNothing was uploaded.")
            return REFUSED

    credentials = {
        "Administrator": ("KMP_CORPUS_ADMIN_EMAIL", "KMP_CORPUS_ADMIN_PASSWORD"),
        "Employee": ("KMP_CORPUS_EMPLOYEE_EMAIL", "KMP_CORPUS_EMPLOYEE_PASSWORD"),
    }
    missing = [name for pair in credentials.values() for name in pair if not os.environ.get(name)]
    if missing:
        sys.exit(f"Set {', '.join(missing)} (see the module docstring).")

    record = None
    if not args.search_only:
        # The database this process reads, by NAME. Never kmp for a run of this script
        # (D-84 decision 1), and named in the results so a reader can see which it was.
        database = orm_database_name()
        print(f"This process reads the database {database!r}; the server must write to the same one.")
        try:
            measurement_record.refuse_protected_database(database)
        except measurement_record.RecordError as exc:
            print(f"REFUSED: {exc}\nNothing was uploaded.")
            return REFUSED
        problems, flm = gate_problems()
        try:
            record = measurement_record.run_record(dump_sha256=None, database=database, flm=flm)
        except measurement_record.RecordError as exc:
            problems.append(f"the run cannot be recorded: {exc}")
        # D-85: the server this run goes through, observed, before anything is sent to it
        # but one unauthenticated GET. Refused only on evidence of another server; a lookup
        # that failed is recorded and warned about instead.
        server = server_record.observe(
            args.base_url, server_record.fetch_server_header(args.base_url.rstrip("/") + "/api/")
        )
        print(f"Server: {server_record.summary(server)}")
        contradictions = server_record.contradicts_d85(server)
        if contradictions and not args.any_server:
            problems += [f"{c}; start it as `{server_record.D85_COMMAND}`, or pass --any-server"
                         for c in contradictions]
        for warning in server_record.problems(server):
            print(f"WARNING: {warning}")
        if record is not None:
            record["server"] = server
            record["server_gate_waived"] = bool(contradictions and args.any_server)
        if problems:
            print("\n" + "\n".join(f"REFUSED: {p}" for p in problems) + "\nNothing was uploaded.")
            return REFUSED

    sessions = {
        role: sign_in(args.base_url, os.environ[email], os.environ[password], role)
        for role, (email, password) in credentials.items()
    }

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = manifest["items"]

    if args.search_only:
        return search_only(manifest, items, sessions, args.base_url, args.output_dir)

    # Refuse to mix a second run into the evidence.
    admin = sessions["Administrator"]
    _, documents, _, _ = admin.request("GET", "/api/documents")
    _, meetings, _, _ = admin.request("GET", "/api/meetings")
    existing = {d["title"] for d in documents} | {m["title"] for m in meetings}
    clash = sorted(item["title"] for item in items if item["title"] in existing)
    if clash:
        sys.exit(f"Already present, so this is not a clean run: {clash}")

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="kmp-objective02-") as temp:
        for item in items:
            status, body, seconds, note, path = ingest(item, sessions, Path(temp), args.max_upload_bytes)
            body = body if isinstance(body, dict) else {"raw": body}
            source_id = body.get("doc_id") or body.get("meeting_id")
            outcome = {
                "id": item["id"],
                "kind": item["kind"],
                "title": item["title"],
                "visible_to_roles": item["visible_to_roles"],
                "uploader": item["uploader"],
                "http_status": status,
                "seconds": round(seconds, 2),
                "transport_note": note,
                "source_id": source_id,
                "document_status": body.get("status") if item["kind"] != "transcript" else None,
                "meeting_status": body.get("status") if item["kind"] == "transcript" else None,
                "detail": body.get("detail"),
                "pages": page_count(path) if path is not None else None,
                "chunks": None,
                "search": {},
            }
            if item.get("phrase") and source_id:
                for role, session in sessions.items():
                    outcome["search"][role] = search_finds(session, item["phrase"], source_id, item["title"])
            outcomes.append(outcome)
            print(f"{item['id']}: HTTP {status} {outcome['document_status'] or outcome['meeting_status'] or ''} "
                  f"{seconds:.1f}s {note or ''}", flush=True)

    counts = chunk_counts([o["source_id"] for o in outcomes if o["source_id"] and o["kind"] != "transcript"])
    for outcome in outcomes:
        if outcome["source_id"] in counts:
            outcome["chunks"] = counts[outcome["source_id"]]
            outcome["chunk_count_unread"] = counts[outcome["source_id"]] is None
    for item, outcome in zip(items, outcomes):
        outcome["misses"] = judge(item, outcome)
    if any(o.get("chunk_count_unread") for o in outcomes):
        print("\nWARNING: documents the server created are not in this process's database. "
              "Set DATABASE_URL in this shell to the server's.")

    missed, slow = write_results(manifest, outcomes, started_at, args.base_url,
                                 output_dir=args.output_dir, record=record)
    print(f"\nMissed: {[o['id'] for o in missed] or 'none'}; over the bound: {slow or 'none'}")
    print(f"Wrote {args.output_dir / 'results.json'} and {args.output_dir / 'results.md'}")
    return 1 if missed or slow else 0


def search_only(manifest, items, sessions, base_url, output_dir=CORPUS):
    output_dir = Path(output_dir)
    previous = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    by_id = {outcome["id"]: outcome for outcome in previous["items"]}
    missing = [item["id"] for item in items if item["id"] not in by_id]
    if missing:
        sys.exit(f"results.json has no outcome for {missing}; run the full ingestion first.")
    rerun_at = datetime.now().astimezone().isoformat(timespec="seconds")
    outcomes = []
    for item in items:
        outcome = dict(by_id[item["id"]])
        outcome["search"] = {}
        if item.get("phrase") and outcome.get("source_id"):
            for role, session in sessions.items():
                outcome["search"][role] = search_finds(
                    session, item["phrase"], outcome["source_id"], item["title"]
                )
        outcome["misses"] = judge(item, outcome)
        outcomes.append(outcome)
        print(f"{item['id']}: {item.get('phrase')!r} -> "
              f"{ {role: s.get('found') for role, s in outcome['search'].items()} }", flush=True)
    missed, slow = write_results(manifest, outcomes, previous["run_started"], base_url, rerun_at,
                                 output_dir=output_dir, record=previous.get("record"))
    print(f"\nMissed: {[o['id'] for o in missed] or 'none'}; over the bound: {slow or 'none'}")
    return 1 if missed or slow else 0


if __name__ == "__main__":
    sys.exit(main())
