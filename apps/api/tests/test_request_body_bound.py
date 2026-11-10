"""D-124: no request body is read before it is refused, and the CSRF check still refuses.

**The defect.** Django's CSRF check reads ``request.POST``, looking for a form-field token, before
it falls back to the ``X-CSRFToken`` header. That read parses the body, on two paths:

- **DRF's session authentication runs the check** on every request from a signed-in session.
  There ``POST`` runs the view's parser:
  - a multipart upload was parsed whole, its files spooled to temporary files;
  - a JSON body was read and parsed when within Django's ``DATA_UPLOAD_MAX_MEMORY_SIZE``
    (2.5 MiB). DRF parses JSON from ``request.body``, which refuses a larger declared length
    unread, with a 400.
- **Django ran the check itself** on three routes, before DRF, signed in or not:
  - ``ensure_csrf_cookie`` on login and ``/api/auth/me``;
  - ``CsrfViewMiddleware`` on the SPA's catch-all, which was not exempt.

  A made-up ``csrftoken`` cookie was enough, and a multipart body was parsed whole.

So a body was parsed before the 401, the 403, the 429 and the upload routes' declared-length 413.
A multipart one was bounded only by Waitress's default of 1 GB. The suite never saw it: the test
client enforces CSRF only when asked, and with CSRF off Django's check returns before it reads
anything.

**How these tests see a read.** A request here is sent as the SPA sends it:

- from a session holding the ``csrftoken`` cookie that ``GET /api/auth/me`` sets;
- with the token in ``X-CSRFToken``;
- with CSRF enforced.

Its body is a ``CountingBody``, put in place as ``wsgi.input``. That is the stream every reader of
a body reads from: DRF's parsers, Django's ``request.body`` and ``request.POST``, and anything else.
Bytes read are asserted before status, because they are the property under test. A multipart
body here is a well-formed upload of one file, as an attack would send. Its bytes are made on
demand, so a body over the 50 MB ceiling costs nothing to send.

**The declared length is the real length** here: a ``CountingBody`` holds exactly the number of
bytes it declares. Under Waitress the two cannot differ either. It reads exactly the declared
number, and it reassembles a chunked body and declares its length before Django sees it. The
Waitress tests at the end cover the other half of D-124: Waitress refuses a body at
``MAX_REQUEST_BODY_BYTES`` before reading it, and every documented serve command sets that value.

Every protected route here is sent requests from an Employee and an Administrator session
(CLAUDE.md section 8 item 2).
"""

import importlib
import re
import socket
import sys
import threading
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.middleware.csrf import REASON_CSRF_TOKEN_MISSING, REASON_NO_CSRF_COOKIE
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import RolePermission
from apps.api.views import (
    FILE_TOO_LARGE_MESSAGE,
    TRANSCRIPT_TOO_LARGE_MESSAGE,
    declares_a_body_over_the_upload_ceiling,
)
from apps.core.constants import (
    CONTRIBUTE_CONTENT_PERMISSION,
    MAX_REQUEST_BODY_BYTES,
    MAX_UPLOAD_BYTES,
)
from apps.documents.models import Document
from apps.meetings.models import Meeting
from config.errors import BAD_REQUEST_MESSAGE
from conftest import PASSWORD

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

ME_URL = "/api/auth/me"
LOGIN_URL = "/api/auth/login"
ASK_URL = "/api/ask"
DOCUMENTS_URL = "/api/documents"
MEETINGS_URL = "/api/meetings"

BOUNDARY = "body-bound-test"
MULTIPART = f"multipart/form-data; boundary={BOUNDARY}"
JSON = "application/json"

# One byte over the upload ceiling, and well under Waitress's, so the body reaches the view.
OVERSIZED = MAX_UPLOAD_BYTES + 1
# Under every ceiling, Django's 2.5 MiB for JSON included: a body the routes may read.
SMALL = 2048
# A token the client made up. It is well formed, 64 letters and digits, so Django's check takes it
# as a cookie and goes on to look for the token, which is where it read the body.
MADE_UP_TOKEN = "a1" * 32

# Over MINIMUM_CONTENT_LENGTH (50 tokens), so the transcript is long enough to index.
TRANSCRIPT = "Speaker A: " + " ".join(f"word{number}" for number in range(80))


class CountingBody:
    """A request body that counts the bytes read from it.

    It holds ``length`` bytes: ``prefix``, then NULs, then ``suffix``. The NULs are made only as
    they are read. ``readline`` stops after a newline, as a file's does.
    """

    def __init__(self, length=None, prefix=b"", suffix=b""):
        self.length = len(prefix) + len(suffix) if length is None else length
        assert self.length >= len(prefix) + len(suffix)
        self.prefix = prefix
        self.suffix = suffix
        self.bytes_read = 0

    def _bytes(self, start, end):
        filler_end = self.length - len(self.suffix)
        chunk = self.prefix[start:end]
        if end > len(self.prefix) and start < filler_end:
            chunk += b"\0" * (min(end, filler_end) - max(start, len(self.prefix)))
        if end > filler_end:
            chunk += self.suffix[max(start, filler_end) - filler_end : end - filler_end]
        return chunk

    def read(self, size=-1):
        remaining = self.length - self.bytes_read
        if size is None or size < 0 or size > remaining:
            size = remaining
        start = self.bytes_read
        self.bytes_read += size
        return self._bytes(start, start + size)

    def readline(self, size=-1):
        remaining = self.length - self.bytes_read
        limit = remaining if size is None or size < 0 else min(size, remaining)
        window = self._bytes(self.bytes_read, self.bytes_read + limit)
        newline = window.find(b"\n")
        return self.read(newline + 1 if newline >= 0 else limit)


def an_upload(length):
    """A well-formed multipart body of ``length`` bytes: one file, its contents NULs."""
    prefix = (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="board-pack.txt"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode()
    return CountingBody(length, prefix=prefix, suffix=f"\r\n--{BOUNDARY}--\r\n".encode())


def a_json_body(length):
    """``length`` NULs declared as JSON. A parser that reads them refuses them."""
    return CountingBody(length)


def browser_session(user):
    """A client that enforces CSRF, signed in as ``user``, and the header the SPA sends (D-21).

    ``GET /api/auth/me`` sets the ``csrftoken`` cookie, as it does for the SPA when it starts.
    """
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.get(ME_URL).status_code == 200
    return client, {"HTTP_X_CSRFTOKEN": client.cookies[settings.CSRF_COOKIE_NAME].value}


def anonymous_with_a_made_up_cookie():
    client = APIClient(enforce_csrf_checks=True)
    client.cookies[settings.CSRF_COOKIE_NAME] = MADE_UP_TOKEN
    return client


def send(client, url, body, content_type, headers):
    """POST ``body`` to ``url``, declaring its real length."""
    return client.generic(
        "POST",
        url,
        content_type=content_type,
        CONTENT_LENGTH=str(body.length),
        **headers,
        **{"wsgi.input": body},
    )


def withdraw_contribute_content(user):
    RolePermission.objects.filter(
        role=user.role, permission__permission_name=CONTRIBUTE_CONTENT_PERMISSION
    ).delete()


# The upload routes D-124 bounds, and the forms each accepts.
UPLOADS = {
    "documents, multipart": (DOCUMENTS_URL, an_upload, MULTIPART, FILE_TOO_LARGE_MESSAGE, Document),
    "meetings, multipart": (MEETINGS_URL, an_upload, MULTIPART, TRANSCRIPT_TOO_LARGE_MESSAGE, Meeting),
    "meetings, JSON": (MEETINGS_URL, a_json_body, JSON, TRANSCRIPT_TOO_LARGE_MESSAGE, Meeting),
}
UPLOAD_ROUTES = {"documents": DOCUMENTS_URL, "meetings": MEETINGS_URL}


# --- The declared length -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "meta, over",
    [
        ({}, False),
        ({"CONTENT_LENGTH": ""}, False),
        ({"CONTENT_LENGTH": "not a number"}, False),
        ({"CONTENT_LENGTH": str(MAX_UPLOAD_BYTES)}, False),
        ({"CONTENT_LENGTH": str(MAX_UPLOAD_BYTES + 1)}, True),
    ],
    ids=["absent", "blank", "malformed", "at the ceiling", "one byte over"],
)
def test_the_declared_length_is_over_only_past_the_ceiling(meta, over):
    """A missing or malformed length counts as no body, which is what Django reads: none."""
    assert declares_a_body_over_the_upload_ceiling(SimpleNamespace(META=meta)) is over


# --- Refused unread: the upload routes ---------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("route", list(UPLOADS))
def test_an_oversized_upload_is_refused_unread(session_client, route):
    """The 413 is answered from the declared length alone.

    It comes before the signature's 415, as it has since Stage 3, because the signature cannot be
    read without reading the body. Before D-124 the 413 was answered too, but only after the CSRF
    check had parsed the whole upload. A JSON body over 2.5 MiB was refused unread even then, by
    Django, with a 400.
    """
    url, build, content_type, message, model = UPLOADS[route]
    client, csrf = browser_session(session_client.user)
    body = build(OVERSIZED)

    response = send(client, url, body, content_type, csrf)

    assert body.bytes_read == 0
    assert response.status_code == 413, response.content
    assert response.json() == {"detail": message}
    assert not model.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("route", list(UPLOADS))
def test_a_body_under_the_ceiling_is_read(session_client, route):
    """The control: a counted body the route does read shows it, so a 0 above means unread."""
    url, build, content_type, _, model = UPLOADS[route]
    client, csrf = browser_session(session_client.user)
    body = build(SMALL)

    response = send(client, url, body, content_type, csrf)

    assert body.bytes_read == SMALL
    assert response.status_code in (400, 415), response.content  # NULs are no valid upload
    assert not model.objects.exists()


@pytest.mark.django_db
def test_a_json_body_over_djangos_ceiling_is_400_unread(session_client):
    """A pasted transcript between 2.5 MiB and the 50 MB ceiling. DRF parses JSON from
    ``request.body``, and Django refuses a declared length over ``DATA_UPLOAD_MAX_MEMORY_SIZE``
    without reading it. That was so before D-124 too. The contract lists it since D-124."""
    client, csrf = browser_session(session_client.user)
    body = a_json_body(settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1)

    response = send(client, MEETINGS_URL, body, JSON, csrf)

    assert body.bytes_read == 0
    assert response.status_code == 400
    assert response.json() == {"detail": BAD_REQUEST_MESSAGE}
    assert not Meeting.objects.exists()


# --- Refused unread: every refusal before the view -----------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("route", list(UPLOAD_ROUTES))
def test_an_anonymous_upload_is_refused_unread(route):
    body = an_upload(OVERSIZED)

    response = send(anonymous_with_a_made_up_cookie(), UPLOAD_ROUTES[route], body, MULTIPART, {})

    assert body.bytes_read == 0
    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("route", list(UPLOAD_ROUTES))
def test_the_403_comes_before_the_413_and_reads_nothing(session_client, route):
    """FR-08's section 7.2 puts the permission first as "the cheapest rejection", and D-124 keeps
    that order. Now the rejection is cheap in fact: before D-124 the body was parsed first."""
    withdraw_contribute_content(session_client.user)
    client, csrf = browser_session(session_client.user)
    body = an_upload(OVERSIZED)

    response = send(client, UPLOAD_ROUTES[route], body, MULTIPART, csrf)

    assert body.bytes_read == 0
    assert response.status_code == 403
    assert "CSRF" not in response.json()["detail"]  # the permission's 403, not CSRF's


@pytest.mark.django_db
@pytest.mark.parametrize("route", list(UPLOAD_ROUTES))
def test_the_429_comes_before_the_413_and_reads_nothing(session_client, route, monkeypatch):
    """Past the ingestion rate (D-79) an oversized body is refused by the throttle, unread."""
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "ingestion": "1/hour"},
    )
    client, csrf = browser_session(session_client.user)
    spent = send(client, UPLOAD_ROUTES[route], an_upload(SMALL), MULTIPART, csrf)
    assert spent.status_code in (400, 415)  # the one request the rate allows
    body = an_upload(OVERSIZED)

    response = send(client, UPLOAD_ROUTES[route], body, MULTIPART, csrf)

    assert body.bytes_read == 0
    assert response.status_code == 429


@pytest.mark.django_db
def test_reprocess_reads_no_body(session_client):
    """``POST /api/documents/{id}/reprocess`` takes no body. Before D-124 the CSRF check read and
    parsed a JSON one of up to 2.5 MiB. Now none is read, so the route needs no ceiling of its own:
    it answers as it would without one."""
    client, csrf = browser_session(session_client.user)
    body = a_json_body(SMALL)

    response = send(client, f"{DOCUMENTS_URL}/{uuid.uuid4()}/reprocess", body, JSON, csrf)

    assert body.bytes_read == 0
    assert response.status_code == 404


@pytest.mark.django_db
def test_a_json_route_reads_nothing_before_its_429(session_client, monkeypatch):
    """The fix is in authentication, so it is not the upload routes' alone. Before D-124 a JSON
    body under Django's 2.5 MiB was read and parsed before the throttle could refuse it."""
    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES", {**ScopedRateThrottle.THROTTLE_RATES, "ask": "1/min"}
    )
    client, csrf = browser_session(session_client.user)
    spent = send(client, ASK_URL, a_json_body(SMALL), JSON, csrf)
    assert spent.status_code == 400  # NULs are no JSON: read, refused, and counted
    body = a_json_body(SMALL)

    response = send(client, ASK_URL, body, JSON, csrf)

    assert body.bytes_read == 0
    assert response.status_code == 429


# --- Refused unread: the routes where Django ran the check itself ------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url, answered",
    [(LOGIN_URL, 415), (ME_URL, 401), ("/", 405), ("/documents", 405)],
    ids=["login", "me", "the SPA's root", "a client route"],
)
def test_no_route_reads_a_body_for_a_made_up_cookie(url, answered):
    """Signed out, holding only a ``csrftoken`` cookie the client made up.

    Before D-124 Django's own CSRF check ran on these routes before anything else could refuse
    the request. ``ensure_csrf_cookie`` ran it on login and ``/api/auth/me``, and
    ``CsrfViewMiddleware`` ran it on the SPA's catch-all. Each read and parsed the whole upload.
    Now:

    - login answers 415, because it parses JSON only;
    - ``/api/auth/me`` answers 401;
    - the catch-all answers ``require_safe``'s 405.
    """
    body = an_upload(OVERSIZED)

    response = send(anonymous_with_a_made_up_cookie(), url, body, MULTIPART, {})

    assert body.bytes_read == 0
    assert response.status_code == answered


@pytest.mark.django_db
@pytest.mark.parametrize("url, answered", [(LOGIN_URL, 415), (ME_URL, 405)], ids=["login", "me"])
def test_a_session_reads_no_body_on_login_or_me(session_client, url, answered):
    client, csrf = browser_session(session_client.user)
    body = an_upload(OVERSIZED)

    response = send(client, url, body, MULTIPART, csrf)

    assert body.bytes_read == 0
    assert response.status_code == answered


@pytest.mark.django_db
def test_me_still_sends_the_csrf_cookie_when_signed_out(api_client):
    """What ``ensure_csrf_cookie`` did for these two views, ``SendsCsrfCookieMixin`` still does,
    on every response, a 401 included."""
    response = api_client.get(ME_URL)

    assert response.status_code == 401
    assert response.cookies[settings.CSRF_COOKIE_NAME].value


@pytest.mark.django_db
def test_a_failed_login_still_sends_the_csrf_cookie(api_client, employee):
    response = api_client.post(
        LOGIN_URL, {"email": employee.email, "password": PASSWORD + "-wrong"}, format="json"
    )

    assert response.status_code == 401
    assert response.cookies[settings.CSRF_COOKIE_NAME].value


# --- The CSRF check still refuses, still without reading --------------------------------------


@pytest.mark.django_db
def test_a_missing_csrf_header_is_403_and_reads_nothing(session_client):
    """Before D-124 the body was parsed first, looking for a form-field token, and then refused."""
    client, _ = browser_session(session_client.user)
    body = an_upload(OVERSIZED)

    response = send(client, DOCUMENTS_URL, body, MULTIPART, {})

    assert body.bytes_read == 0
    assert response.status_code == 403
    assert response.json() == {"detail": f"CSRF Failed: {REASON_CSRF_TOKEN_MISSING}"}


@pytest.mark.django_db
def test_a_wrong_csrf_token_is_403(session_client):
    client, _ = browser_session(session_client.user)
    body = an_upload(SMALL)

    # Well formed (64 letters and digits), so it is compared rather than rejected for its shape.
    response = send(client, DOCUMENTS_URL, body, MULTIPART, {"HTTP_X_CSRFTOKEN": MADE_UP_TOKEN})

    assert body.bytes_read == 0
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail.startswith("CSRF Failed: ") and "incorrect" in detail


@pytest.mark.django_db
def test_a_token_in_a_form_field_is_not_accepted(session_client):
    """The one thing D-124 gives up: the ``csrfmiddlewaretoken`` form field as a second place for
    the token. Nothing sends it there. The SPA, the measurement scripts and the load test all use
    the header. The body carries the right token, and it is never looked at."""
    client, csrf = browser_session(session_client.user)
    token = csrf["HTTP_X_CSRFTOKEN"]
    content = (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="csrfmiddlewaretoken"\r\n\r\n'
        f"{token}\r\n--{BOUNDARY}--\r\n"
    ).encode()
    body = CountingBody(prefix=content)

    response = send(client, DOCUMENTS_URL, body, MULTIPART, {})

    assert body.bytes_read == 0
    assert response.status_code == 403
    assert response.json() == {"detail": f"CSRF Failed: {REASON_CSRF_TOKEN_MISSING}"}


@pytest.mark.django_db
def test_a_foreign_origin_is_403(session_client):
    client, csrf = browser_session(session_client.user)
    body = an_upload(SMALL)

    response = send(
        client, DOCUMENTS_URL, body, MULTIPART, {**csrf, "HTTP_ORIGIN": "https://elsewhere.example"}
    )

    assert body.bytes_read == 0
    assert response.status_code == 403
    assert response.json()["detail"].startswith("CSRF Failed: Origin checking failed")


@pytest.mark.django_db
def test_a_missing_csrf_cookie_is_403(session_client):
    client, csrf = browser_session(session_client.user)
    del client.cookies[settings.CSRF_COOKIE_NAME]
    body = an_upload(SMALL)

    response = send(client, DOCUMENTS_URL, body, MULTIPART, csrf)

    assert body.bytes_read == 0
    assert response.status_code == 403
    assert response.json() == {"detail": f"CSRF Failed: {REASON_NO_CSRF_COOKIE}"}


# --- The SPA's own requests still pass --------------------------------------------------------


@pytest.mark.django_db
def test_an_upload_with_the_csrf_header_is_stored(session_client, upload):
    client, csrf = browser_session(session_client.user)

    response = client.post(
        DOCUMENTS_URL,
        {"file": upload("sample.txt"), "title": "Leave Policy 2026"},
        format="multipart",
        **csrf,
    )

    assert response.status_code == 201, response.content
    assert Document.objects.filter(pk=response.json()["doc_id"]).exists()


@pytest.mark.django_db
def test_a_transcript_with_the_csrf_header_is_stored(session_client):
    client, csrf = browser_session(session_client.user)

    response = client.post(
        MEETINGS_URL,
        {"title": "Q3 Planning Sync", "meeting_date": date.today().isoformat(),
         "transcript_text": TRANSCRIPT},
        format="json",
        **csrf,
    )

    assert response.status_code == 201, response.content
    assert Meeting.objects.filter(pk=response.json()["meeting_id"]).exists()


# --- Waitress: what bounds the receiving (D-124) --------------------------------------------


def test_waitress_ceiling_sits_just_above_the_upload_ceiling_and_far_below_its_default():
    from waitress.adjustments import Adjustments

    assert MAX_REQUEST_BODY_BYTES == MAX_UPLOAD_BYTES + 2 * 1024 * 1024
    assert MAX_REQUEST_BODY_BYTES < Adjustments.max_request_body_size  # 1 GB unless told otherwise


def scripts_module(monkeypatch, name):
    """A module from scripts/, imported afresh, as the measurement-script tests import them."""
    monkeypatch.syspath_prepend(str(REPOSITORY_ROOT / "scripts"))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_objective_02s_oversized_item_still_reaches_the_view(monkeypatch):
    """The ingestion generates I02 ``OVERSIZE_EXTRA_BYTES`` past the upload ceiling, after a
    one-line PDF header, and sends it with a title and the visibility fields. Its body must stay
    under Waitress's ceiling, so that it is still refused by the view's JSON 413 as in every
    recorded run. Over it, Waitress would refuse it at the headers while the script was still
    sending, and on Windows the reset can arrive before the 413 does. 64 KiB is far more than the
    header and the multipart framing take."""
    ingestion = scripts_module(monkeypatch, "ingest_objective02")

    assert MAX_UPLOAD_BYTES + ingestion.OVERSIZE_EXTRA_BYTES + 64 * 1024 < MAX_REQUEST_BODY_BYTES


def exchange(port, request):
    """Send raw bytes to a local server and read until it closes the connection."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as connection:
        connection.sendall(request)
        reply = b""
        while True:
            try:
                data = connection.recv(65536)
            except ConnectionError:
                break
            if not data:
                break
            reply += data
        return reply


def test_waitress_refuses_a_body_at_the_ceiling_before_reading_it():
    """The behaviour D-124 relies on, from the installed Waitress. A declared length at
    ``max_request_body_size`` is refused at the headers (Waitress compares ``>=``), with Waitress's
    own 413, before the body is sent and without calling the application."""
    from waitress.server import create_server

    calls = []

    def application(environ, start_response):
        calls.append(environ.get("CONTENT_LENGTH"))
        received = environ["wsgi.input"].read()
        start_response("200 OK", [("Content-Length", str(len(received)))])
        return [received]

    server = create_server(
        application, host="127.0.0.1", port=0, threads=1,
        max_request_body_size=MAX_REQUEST_BODY_BYTES,
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        at_the_ceiling = exchange(
            server.effective_port,
            f"POST /api/documents HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n"
            f"Content-Length: {MAX_REQUEST_BODY_BYTES}\r\n\r\n".encode(),
        )
        assert at_the_ceiling.startswith(b"HTTP/1.1 413 ")
        assert calls == []

        small = exchange(
            server.effective_port,
            b"POST /api/documents HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n"
            b"Content-Length: 5\r\n\r\nhello",
        )
        assert small.startswith(b"HTTP/1.1 200 ")
        assert calls == ["5"]
    finally:
        server.close()
        thread.join(timeout=10)


FLAG = f"--max-request-body-size={MAX_REQUEST_BODY_BYTES}"
# Where a serve command is written for someone to run. decisions.md is not read: its entries
# record what was decided when, and D-85's dated note points to D-124. Neither is corpus/: its
# records say how each past run was served.
SERVE_COMMAND_DOCUMENTS = ("docs/alpha-deployment.md", "docs/measurement-runbook.md",
                           "tests/load/README.md")
# Waitress, by name or by the runbook's $waitress variable, then its --listen= option: a command,
# not prose that mentions the option.
SERVE_COMMAND = re.compile(r"waitress\S*\s+--listen=", re.IGNORECASE)


def documented_serve_commands():
    """Every line under docs/, tests/load/ and in README.md that starts Waitress."""
    paths = [REPOSITORY_ROOT / "README.md"]
    paths += sorted((REPOSITORY_ROOT / "docs").rglob("*.md"))
    paths += sorted((REPOSITORY_ROOT / "tests" / "load").rglob("*.md"))
    found = []
    for path in paths:
        if path.name == "decisions.md":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if SERVE_COMMAND.search(line):
                found.append((path.relative_to(REPOSITORY_ROOT).as_posix(), number, line))
    return found


def test_every_documented_serve_command_sets_waitress_ceiling():
    commands = documented_serve_commands()

    assert {path for path, _, _ in commands} >= set(SERVE_COMMAND_DOCUMENTS)
    missing = [f"{path}:{number}" for path, number, line in commands if FLAG not in line]
    assert not missing, f"serve commands without {FLAG}: {missing}"


def test_the_measurement_scripts_tell_the_server_to_start_with_the_ceiling(monkeypatch):
    """``server_record.D85_COMMAND`` is the command the scripts print when they refuse a server.
    It is standard library only, so it holds its own copy of the value, tied here."""
    server_record = scripts_module(monkeypatch, "server_record")

    assert server_record.D85_MAX_REQUEST_BODY_BYTES == MAX_REQUEST_BODY_BYTES
    assert FLAG in server_record.D85_COMMAND
    assert FLAG in server_record.__doc__
