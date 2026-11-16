"""D-137: profile pictures, re-encoded by Pillow and seen by every signed-in user.

Benjamin's decision of 16 November 2026: every signed-in user sees every profile picture, wherever
users are listed; PNG, JPEG or WebP up to 5 MB, re-encoded as a PNG of at most 512 x 512; no GIF,
no SVG. The routes:

- ``POST /api/users/me/picture``, multipart ``picture``: set one's own. 200, the user object.
- ``DELETE /api/users/me/picture``: remove one's own, idempotently. 200, the user object.
- ``GET /api/users/{id}/picture``: anyone's, to any signed-in session, as PNG bytes.

What these tests hold the build to:

- **Both roles** upload, replace, delete and view their own picture, and view another user's.
- **The format is read from the content.** PNG, JPEG and WebP are accepted; GIF, SVG, BMP, text and
  an empty file are a 415 whatever they are called, and a corrupt or truncated picture is the same
  415 with the same body. Nothing is stored for any refusal.
- **Size.** A body declaring more than 5 MB plus the 64 KiB allowance is a 413 read from its
  ``Content-Length`` alone: a counting body shows no byte of it was read. A file over 5 MB inside a
  body under that is a 413 once parsed. A small file whose header declares more than 25,000,000
  pixels is a 413 without a pixel decoded: a spy on Pillow's ``load`` shows it never ran.
- **Only pixels are kept.** A JPEG carrying EXIF (GPS, camera, orientation), an ICC profile and a
  comment, and a PNG carrying text, ICC, a transparency key and a private chunk, each come back as a
  PNG with no chunk but IHDR, IDAT and IEND, at most 512 x 512, turned upright.
- **Files.** The old file is deleted after the commit, on replace and on delete, never before; a
  file the storage cannot delete does not fail the request; a failed save deletes the new file.
- **The one 404.** An unknown id, a user with no picture and a stored file gone from disk are the
  same 404 with the same body. Anonymous is 401.
- **Where ``picture`` appears:** the user object (``/auth/me``, login, register, ``GET /api/users``),
  directory entries, and a meeting detail's ``attendee_people``, which matches ``attendees`` and
  costs no query per attendee.

The throttle's 429, on POST only, is in ``apps/api/tests/test_throttles.py`` with every other rate.
Every protected route here is sent requests from an Employee and an Administrator session
(CLAUDE.md section 8 item 2).
"""

import calendar
import io
import re
import struct
import uuid
import zlib
from datetime import date, datetime
from datetime import timezone as dt_timezone
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from PIL import Image, ImageCms, ImageFile, PngImagePlugin
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts import pictures
from apps.api.views import (
    NO_PICTURE_SUBMITTED_MESSAGE,
    PICTURE_TOO_LARGE_MESSAGE,
    PICTURE_TOO_MANY_PIXELS_MESSAGE,
    UNSUPPORTED_PICTURE_MESSAGE,
    USER_NOT_FOUND_MESSAGE,
)
from apps.core.constants import (
    MAX_PICTURE_BYTES,
    PICTURE_MAX_DIMENSION,
    PICTURE_UPLOAD_ALLOWANCE_BYTES,
    ROLE_NAMES,
)
from apps.meetings.models import Meeting, MeetingAttendee
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

OWN_PICTURE_URL = "/api/users/me/picture"
ME_URL = "/api/auth/me"
USER_OBJECT_KEYS = {"id", "name", "email", "role", "created_at", "picture"}
STORED_NAME = re.compile(r"^profile-pictures/[0-9a-f]{32}\.png$")
# The only chunks the stored PNG may carry: no text, no ICC, no EXIF, no transparency key.
BARE_PNG_CHUNKS = {"IHDR", "IDAT", "IEND"}
NEVER_CACHE_DIRECTIVES = {"max-age=0", "no-cache", "no-store", "must-revalidate", "private"}


# --- Building pictures --------------------------------------------------------------------------


def encoded(image, image_format, **options) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, **options)
    return buffer.getvalue()


def a_photo(size=(64, 48), colour=(200, 30, 30)):
    return Image.new("RGB", size, colour)


def a_detailed_photo(size=(96, 96)):
    """Noise, so a truncated copy has a header and only half its data."""
    return Image.effect_noise(size, 64).convert("RGB")


def png_declaring(width, height, idat=None) -> bytes:
    """A PNG signature and an IHDR declaring ``width`` x ``height``, a scrap of IDAT and an IEND:
    under 100 bytes that a decoder would have to inflate into ``width * height`` pixels."""

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = zlib.compress(b"\0" * 64) if idat is None else idat
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", data) + chunk(b"IEND", b"")


def png_of_exactly(total_bytes) -> bytes:
    """A small valid PNG padded to exactly ``total_bytes`` with a private ancillary chunk."""
    base = encoded(a_photo((16, 16)), "PNG")
    padding = total_bytes - len(base) - 12
    assert padding >= 0
    payload = b"\0" * padding
    chunk = (struct.pack(">I", padding) + b"prVt" + payload
             + struct.pack(">I", zlib.crc32(b"prVt" + payload) & 0xFFFFFFFF))
    ihdr_end = 8 + 25  # signature, then IHDR's 4 + 4 + 13 + 4
    padded = base[:ihdr_end] + chunk + base[ihdr_end:]
    assert len(padded) == total_bytes
    return padded


def png_chunk_types(data: bytes) -> list[str]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    position, kinds = 8, []
    while position < len(data):
        (length,) = struct.unpack(">I", data[position:position + 4])
        kinds.append(data[position + 4:position + 8].decode("ascii"))
        position += 12 + length
    return kinds


def srgb_profile() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


# --- Sending them -------------------------------------------------------------------------------


def upload(client, data, name="me.png", content_type="image/png"):
    picture = SimpleUploadedFile(name, data, content_type=content_type)
    return client.post(OWN_PICTURE_URL, {"picture": picture}, format="multipart")


def logged_in(user):
    client = APIClient()
    client.force_login(user)
    return client


def the_other(session_client, employee, administrator):
    return administrator if session_client.user.pk == employee.pk else employee


def microseconds(instant) -> int:
    """Whole microseconds since the epoch, worked out here independently of the code under test."""
    return calendar.timegm(instant.utctimetuple()) * 1_000_000 + instant.microsecond


def expected_picture_url(user) -> str:
    user.refresh_from_db()
    return f"/api/users/{user.pk}/picture?v={microseconds(user.picture_updated_at)}"


def stored_files(media_root) -> list[str]:
    folder = media_root / "profile-pictures"
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


def stored_png(media_root, user) -> bytes:
    user.refresh_from_db()
    return (media_root / user.picture.name).read_bytes()


def assert_nothing_stored(user, media_root):
    user.refresh_from_db()
    assert not user.picture
    assert user.picture_updated_at is None
    assert stored_files(media_root) == []


# --- Both roles: upload, view, replace, delete --------------------------------------------------


def test_each_role_uploads_a_picture_and_gets_its_user_object(session_client, media_root):
    client, user = session_client.client, session_client.user

    response = upload(client, encoded(a_photo(), "PNG"))

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == USER_OBJECT_KEYS
    assert body["id"] == str(user.pk)
    assert body["picture"] == expected_picture_url(user)
    assert STORED_NAME.match(user.picture.name)
    assert (media_root / user.picture.name).is_file()
    assert body == client.get(ME_URL).json()


def test_each_role_views_their_own_picture_as_the_stored_png(session_client, media_root):
    client, user = session_client.client, session_client.user
    upload(client, encoded(a_photo(), "JPEG"), name="holiday.jpg", content_type="image/jpeg")

    response = client.get(f"/api/users/{user.pk}/picture")

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response.content == stored_png(media_root, user)
    assert Image.open(io.BytesIO(response.content)).format == "PNG"


def test_each_role_views_another_users_picture(session_client, employee, administrator, media_root):
    other = the_other(session_client, employee, administrator)
    assert upload(logged_in(other), encoded(a_photo(colour=(10, 200, 10)), "PNG")).status_code == 200

    response = session_client.client.get(f"/api/users/{other.pk}/picture")

    assert response.status_code == 200
    assert response.content == stored_png(media_root, other)


def test_each_role_replaces_their_picture_and_the_old_file_goes_after_the_commit(
    session_client, media_root, django_capture_on_commit_callbacks
):
    client, user = session_client.client, session_client.user
    with django_capture_on_commit_callbacks() as first_callbacks:
        assert upload(client, encoded(a_photo(colour=(255, 0, 0)), "PNG")).status_code == 200
    assert first_callbacks == []  # nothing was replaced
    user.refresh_from_db()
    old_name = user.picture.name

    with django_capture_on_commit_callbacks() as callbacks:
        response = upload(client, encoded(a_photo(colour=(0, 0, 255)), "PNG"))

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.picture.name != old_name
    assert response.json()["picture"] == expected_picture_url(user)
    # Before the commit both files exist, so a rollback would leave the row's file in place.
    assert stored_files(media_root) == sorted([old_name.split("/")[1], user.picture.name.split("/")[1]])
    assert len(callbacks) == 1
    callbacks[0]()  # the commit
    assert stored_files(media_root) == [user.picture.name.split("/")[1]]
    served = client.get(f"/api/users/{user.pk}/picture")
    assert Image.open(io.BytesIO(served.content)).convert("RGB").getpixel((0, 0)) == (0, 0, 255)


def test_each_role_deletes_their_picture_and_the_file_goes_after_the_commit(
    session_client, media_root, django_capture_on_commit_callbacks
):
    client, user = session_client.client, session_client.user
    upload(client, encoded(a_photo(), "PNG"))
    user.refresh_from_db()
    name = user.picture.name

    with django_capture_on_commit_callbacks() as callbacks:
        response = client.delete(OWN_PICTURE_URL)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == USER_OBJECT_KEYS
    assert body["picture"] is None
    user.refresh_from_db()
    assert not user.picture and user.picture_updated_at is None
    assert (media_root / name).is_file()  # not before the commit
    assert len(callbacks) == 1
    callbacks[0]()
    assert not (media_root / name).exists()
    assert client.get(f"/api/users/{user.pk}/picture").status_code == 404


def test_deleting_with_no_picture_is_the_same_200_and_deletes_nothing(
    session_client, django_capture_on_commit_callbacks
):
    client = session_client.client
    with django_capture_on_commit_callbacks() as callbacks:
        first = client.delete(OWN_PICTURE_URL)
        second = client.delete(OWN_PICTURE_URL)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["picture"] is None
    assert callbacks == []


def test_a_replaced_picture_has_a_new_address(session_client, monkeypatch):
    """``v`` is ``picture_updated_at`` in whole microseconds. The two instants are set here, because
    Windows' clock ticks every 15.6 ms and two uploads in one test could share a tick."""
    instants = iter([
        datetime(2026, 11, 16, 10, 0, 0, 123456, tzinfo=dt_timezone.utc),
        datetime(2026, 11, 16, 10, 0, 1, 654321, tzinfo=dt_timezone.utc),
    ])
    monkeypatch.setattr(pictures, "timezone", SimpleNamespace(now=lambda: next(instants)))
    client, user = session_client.client, session_client.user

    first = upload(client, encoded(a_photo(), "PNG")).json()["picture"]
    second = upload(client, encoded(a_photo(colour=(1, 2, 3)), "PNG")).json()["picture"]

    assert first == f"/api/users/{user.pk}/picture?v=1794823200123456"
    assert second == f"/api/users/{user.pk}/picture?v=1794823201654321"


def test_the_upload_locks_only_the_users_row_for_no_key_update(session_client):
    """Two uploads for one account take turns on the row, so neither leaves a file no row names.
    Read from the SQL, as the deletion tests read theirs."""
    with CaptureQueriesContext(connection) as queries:
        assert upload(session_client.client, encoded(a_photo(), "PNG")).status_code == 200

    locks = [query["sql"] for query in queries.captured_queries if " FOR " in query["sql"]]
    assert len(locks) == 1, locks
    assert locks[0].endswith('FOR NO KEY UPDATE OF "users"'), locks[0]


# --- The format comes from the content ----------------------------------------------------------


@pytest.mark.parametrize(
    "image_format, name, content_type, options",
    [
        ("PNG", "me.png", "image/png", {}),
        ("JPEG", "me.jpg", "image/jpeg", {"quality": 90}),
        ("WEBP", "me.webp", "image/webp", {"lossless": True}),
    ],
    ids=["png", "jpeg", "webp"],
)
def test_png_jpeg_and_webp_are_accepted_and_stored_as_png(
    session_client, media_root, image_format, name, content_type, options
):
    data = encoded(a_photo((80, 60)), image_format, **options)

    response = upload(session_client.client, data, name=name, content_type=content_type)

    assert response.status_code == 200, response.content
    stored = Image.open(io.BytesIO(stored_png(media_root, session_client.user)))
    assert (stored.format, stored.size, stored.mode) == ("PNG", (80, 60), "RGB")


def test_a_picture_is_read_by_its_content_whatever_it_is_called(session_client, media_root):
    """A JPEG called ``me.gif`` and declared ``text/plain`` is a JPEG."""
    data = encoded(a_photo(), "JPEG")

    response = upload(session_client.client, data, name="me.gif", content_type="text/plain")

    assert response.status_code == 200
    assert Image.open(io.BytesIO(stored_png(media_root, session_client.user))).format == "PNG"


SVG = (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
       b'<script>alert(1)</script><rect width="10" height="10"/></svg>')


def refused_uploads():
    gif = encoded(Image.new("RGB", (8, 8), "red"), "GIF")
    bmp = encoded(Image.new("RGB", (8, 8), "red"), "BMP")
    return {
        "GIF": (gif, "me.gif", "image/gif"),
        "GIF renamed .png": (gif, "me.png", "image/png"),
        "SVG": (SVG, "me.svg", "image/svg+xml"),
        "SVG renamed .png": (SVG, "me.png", "image/png"),
        "text renamed .png": (b"This is not a picture.\n" * 20, "me.png", "image/png"),
        "BMP, which Pillow reads, renamed .png": (bmp, "me.png", "image/png"),
        "an empty file": (b"", "me.png", "image/png"),
    }


@pytest.mark.parametrize("case", list(refused_uploads()))
def test_anything_but_png_jpeg_or_webp_is_415_and_nothing_is_stored(session_client, media_root, case):
    data, name, content_type = refused_uploads()[case]

    response = upload(session_client.client, data, name=name, content_type=content_type)

    assert response.status_code == 415, response.content
    assert response.json() == {"detail": UNSUPPORTED_PICTURE_MESSAGE}
    assert_nothing_stored(session_client.user, media_root)


def damaged_uploads():
    png = encoded(a_detailed_photo(), "PNG")
    jpeg = encoded(a_detailed_photo(), "JPEG", quality=95)
    webp = encoded(a_detailed_photo(), "WEBP", quality=90)
    return {
        "a truncated PNG": png[: len(png) // 2],
        "a truncated JPEG": jpeg[: len(jpeg) // 2],
        "a truncated WebP": webp[: len(webp) // 2],
        "a PNG whose data is not a zlib stream": png_declaring(16, 16, idat=b"not a zlib stream"),
    }


@pytest.mark.parametrize("case", list(damaged_uploads()))
def test_a_corrupt_or_truncated_picture_is_the_same_415(session_client, media_root, case):
    response = upload(session_client.client, damaged_uploads()[case])

    assert response.status_code == 415, response.content
    assert response.json() == {"detail": UNSUPPORTED_PICTURE_MESSAGE}
    assert_nothing_stored(session_client.user, media_root)


def test_no_picture_part_is_a_400(session_client, media_root):
    client = session_client.client

    missing = client.post(OWN_PICTURE_URL, {}, format="multipart")
    not_a_file = client.post(OWN_PICTURE_URL, {"picture": "a string, not a file"}, format="multipart")

    for response in (missing, not_a_file):
        assert response.status_code == 400
        assert response.json() == {"picture": [NO_PICTURE_SUBMITTED_MESSAGE]}
    assert_nothing_stored(session_client.user, media_root)


# --- Size: bytes, then pixels -------------------------------------------------------------------

BOUNDARY = "picture-bound-test"
MULTIPART = f"multipart/form-data; boundary={BOUNDARY}"
DECLARED_CEILING = MAX_PICTURE_BYTES + PICTURE_UPLOAD_ALLOWANCE_BYTES


class CountingBody:
    """A request body of ``length`` bytes that counts what is read from it, as
    test_request_body_bound.py's does: ``prefix``, NULs made only as they are read, ``suffix``."""

    def __init__(self, length, prefix=b"", suffix=b""):
        assert length >= len(prefix) + len(suffix)
        self.length, self.prefix, self.suffix = length, prefix, suffix
        self.bytes_read = 0

    def _bytes(self, start, end):
        filler_end = self.length - len(self.suffix)
        chunk = self.prefix[start:end]
        if end > len(self.prefix) and start < filler_end:
            chunk += b"\0" * (min(end, filler_end) - max(start, len(self.prefix)))
        if end > filler_end:
            chunk += self.suffix[max(start, filler_end) - filler_end:end - filler_end]
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


def a_picture_body(length):
    """A well-formed multipart body of ``length`` bytes: one file part, ``picture``, of NULs."""
    prefix = (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="picture"; filename="me.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode()
    return CountingBody(length, prefix=prefix, suffix=f"\r\n--{BOUNDARY}--\r\n".encode())


def browser_session(user):
    """CSRF enforced, signed in, holding the csrftoken cookie /api/auth/me sets, as the SPA is."""
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.get(ME_URL).status_code == 200
    return client, {"HTTP_X_CSRFTOKEN": client.cookies[settings.CSRF_COOKIE_NAME].value}


def send(client, body, headers):
    return client.generic(
        "POST", OWN_PICTURE_URL, content_type=MULTIPART, CONTENT_LENGTH=str(body.length),
        **headers, **{"wsgi.input": body},
    )


def test_a_body_declaring_over_the_ceiling_is_413_unread(session_client, media_root):
    client, csrf = browser_session(session_client.user)
    body = a_picture_body(DECLARED_CEILING + 1)

    response = send(client, body, csrf)

    assert body.bytes_read == 0
    assert response.status_code == 413, response.content
    assert response.json() == {"detail": PICTURE_TOO_LARGE_MESSAGE}
    assert_nothing_stored(session_client.user, media_root)


def test_a_body_declaring_the_ceiling_is_read_and_its_oversized_file_is_413(session_client, media_root):
    """The control for the test above, and the second check: the declared ceiling admits the body,
    which is read, and the file inside it, over 5 MB, is refused once parsed."""
    client, csrf = browser_session(session_client.user)
    body = a_picture_body(DECLARED_CEILING)

    response = send(client, body, csrf)

    assert body.bytes_read == DECLARED_CEILING
    assert response.status_code == 413, response.content
    assert response.json() == {"detail": PICTURE_TOO_LARGE_MESSAGE}
    assert_nothing_stored(session_client.user, media_root)


def test_a_picture_of_exactly_5_mb_is_accepted_and_one_byte_more_is_413(session_client, media_root):
    client = session_client.client

    assert upload(client, png_of_exactly(MAX_PICTURE_BYTES)).status_code == 200
    response = upload(client, png_of_exactly(MAX_PICTURE_BYTES + 1))

    assert response.status_code == 413
    assert response.json() == {"detail": PICTURE_TOO_LARGE_MESSAGE}


def test_an_anonymous_upload_is_401_unread():
    client = APIClient(enforce_csrf_checks=True)
    body = a_picture_body(DECLARED_CEILING + 1)

    response = send(client, body, {})

    assert body.bytes_read == 0
    assert response.status_code == 401


def test_an_upload_without_the_csrf_header_is_403_unread(session_client, media_root):
    client, _ = browser_session(session_client.user)
    body = a_picture_body(4096)

    response = send(client, body, {})

    assert body.bytes_read == 0
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]
    assert_nothing_stored(session_client.user, media_root)


def test_a_delete_without_the_csrf_header_is_403_and_keeps_the_picture(session_client):
    upload(session_client.client, encoded(a_photo(), "PNG"))
    client, _ = browser_session(session_client.user)

    response = client.delete(OWN_PICTURE_URL)

    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]
    session_client.user.refresh_from_db()
    assert session_client.user.picture


def test_the_throttle_refuses_before_the_body_is_read(session_client, monkeypatch):
    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES", {**ScopedRateThrottle.THROTTLE_RATES, "picture": "1/hour"}
    )
    client, csrf = browser_session(session_client.user)
    assert send(client, a_picture_body(4096), csrf).status_code == 415  # NULs: read, refused, counted
    body = a_picture_body(DECLARED_CEILING + 1)

    response = send(client, body, csrf)

    assert body.bytes_read == 0
    assert response.status_code == 429


@pytest.fixture
def decoded(monkeypatch):
    """Every image Pillow decodes, by its size: a spy on ``ImageFile.load``."""
    seen = []
    real_load = ImageFile.ImageFile.load

    def spy(self):
        seen.append(self.size)
        return real_load(self)

    monkeypatch.setattr(ImageFile.ImageFile, "load", spy)
    return seen


@pytest.mark.parametrize(
    "width, height",
    [(6000, 5000), (20000, 20000)],
    ids=["30 Mpx: over the cap, under Pillow's warning", "400 Mpx: over Pillow's own error"],
)
def test_a_small_file_declaring_too_many_pixels_is_413_undecoded(
    session_client, media_root, decoded, width, height
):
    data = png_declaring(width, height)
    assert len(data) < 100

    response = upload(session_client.client, data)

    assert response.status_code == 413, response.content
    assert response.json() == {"detail": PICTURE_TOO_MANY_PIXELS_MESSAGE}
    assert decoded == []
    assert_nothing_stored(session_client.user, media_root)


def test_a_picture_in_pillows_warning_band_is_refused_by_the_cap(session_client, decoded):
    """100 Mpx: Pillow only warns between its 89,478,485 and twice that, and the cap refuses."""
    with pytest.warns(Image.DecompressionBombWarning):
        response = upload(session_client.client, png_declaring(10000, 10000))

    assert response.status_code == 413
    assert response.json() == {"detail": PICTURE_TOO_MANY_PIXELS_MESSAGE}
    assert decoded == []


def test_the_pixel_cap_admits_exactly_its_count(session_client, monkeypatch, decoded):
    """The comparison, with the cap lowered so a picture at it is small: 12 x 10 is at a cap of 120.
    Also the control for the spy above: the picture admitted is decoded, and the spy sees it."""
    monkeypatch.setattr(pictures, "MAX_PICTURE_PIXELS", 120)
    client = session_client.client

    assert upload(client, encoded(a_photo((12, 10)), "PNG")).status_code == 200
    assert set(decoded) == {(12, 10)}  # load() may be entered more than once for one image
    assert upload(client, encoded(a_photo((13, 10)), "PNG")).status_code == 413
    assert set(decoded) == {(12, 10)}


# --- Nothing but the pixels ---------------------------------------------------------------------


def test_a_jpeg_carrying_gps_comes_back_as_a_bare_upright_png(session_client, media_root):
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: turn 90 degrees clockwise to show it upright
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x8825] = {1: "S", 2: (37.0, 48.0, 49.0), 3: "E", 4: (144.0, 57.0, 47.0)}  # GPS
    photo = encoded(
        a_photo((1200, 800)), "JPEG", exif=exif.tobytes(), icc_profile=srgb_profile(),
        comment=b"Taken at 12 Example Street", quality=90,
    )
    assert Image.open(io.BytesIO(photo)).getexif().get_ifd(0x8825)  # the source does carry GPS

    assert upload(session_client.client, photo, name="IMG_0001.jpg").status_code == 200

    stored_bytes = stored_png(media_root, session_client.user)
    assert set(png_chunk_types(stored_bytes)) <= BARE_PNG_CHUNKS
    for secret in (b"PhoneMaker", b"Example Street", b"Exif"):
        assert secret not in stored_bytes
    stored = Image.open(io.BytesIO(stored_bytes))
    assert stored.format == "PNG"
    assert not stored.getexif()
    assert not stored.text
    assert "icc_profile" not in stored.info and "exif" not in stored.info
    # Upright, so portrait, and fitted to 512: 800 x 1200 becomes 341 x 512.
    assert stored.size == (341, PICTURE_MAX_DIMENSION)


def test_a_png_carrying_text_icc_a_transparency_key_and_a_private_chunk_keeps_only_pixels(
    session_client, media_root
):
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "Taken at 12 Example Street")
    info.add_itxt("Author", "Erin Employee")
    info.add(b"prVt", b"a private secret")
    source = Image.new("RGB", (40, 30), (1, 2, 3))
    source.putpixel((0, 0), (250, 250, 250))
    data = encoded(source, "PNG", pnginfo=info, icc_profile=srgb_profile(), transparency=(1, 2, 3))

    assert upload(session_client.client, data).status_code == 200

    stored_bytes = stored_png(media_root, session_client.user)
    assert set(png_chunk_types(stored_bytes)) <= BARE_PNG_CHUNKS
    for secret in (b"Example Street", b"Erin Employee", b"private secret"):
        assert secret not in stored_bytes
    stored = Image.open(io.BytesIO(stored_bytes))
    # The key became an alpha band: the key colour is transparent and the rest is not.
    assert stored.mode == "RGBA"
    assert stored.getpixel((1, 1)) == (1, 2, 3, 0)
    assert stored.getpixel((0, 0)) == (250, 250, 250, 255)


def test_alpha_is_kept_and_an_opaque_picture_is_rgb(session_client, media_root):
    client, user = session_client.client, session_client.user
    translucent = Image.new("RGBA", (20, 20), (0, 128, 255, 77))

    upload(client, encoded(translucent, "WEBP", lossless=True), name="me.webp")
    with_alpha = Image.open(io.BytesIO(stored_png(media_root, user)))
    upload(client, encoded(a_photo((20, 20)), "JPEG"), name="me.jpg")
    opaque = Image.open(io.BytesIO(stored_png(media_root, user)))

    assert (with_alpha.mode, with_alpha.getpixel((5, 5))) == ("RGBA", (0, 128, 255, 77))
    assert opaque.mode == "RGB"


def test_an_animated_webp_is_stored_as_its_first_frame(session_client, media_root):
    frames = [Image.new("RGB", (16, 16), colour) for colour in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    animated = encoded(frames[0], "WEBP", save_all=True, append_images=frames[1:], lossless=True)
    assert Image.open(io.BytesIO(animated)).n_frames == 3

    assert upload(session_client.client, animated, name="me.webp").status_code == 200

    stored_bytes = stored_png(media_root, session_client.user)
    assert set(png_chunk_types(stored_bytes)) <= BARE_PNG_CHUNKS  # no APNG frames
    stored = Image.open(io.BytesIO(stored_bytes))
    assert getattr(stored, "n_frames", 1) == 1
    assert stored.getpixel((8, 8)) == (255, 0, 0)


@pytest.mark.parametrize(
    "size, stored_size",
    [((2000, 1000), (512, 256)), ((300, 2400), (64, 512)), ((100, 50), (100, 50))],
    ids=["wide, scaled down", "tall, scaled down", "small, never enlarged"],
)
def test_a_picture_is_fitted_to_512_keeping_its_shape(session_client, media_root, size, stored_size):
    assert upload(session_client.client, encoded(a_photo(size), "PNG")).status_code == 200

    assert Image.open(io.BytesIO(stored_png(media_root, session_client.user))).size == stored_size


# --- The stored file, when things go wrong ------------------------------------------------------


def test_a_file_the_storage_cannot_delete_does_not_fail_the_request(
    session_client, monkeypatch, django_capture_on_commit_callbacks
):
    client = session_client.client
    upload(client, encoded(a_photo(), "PNG"))

    def refuse(self, name):
        raise PermissionError(f"{name} is held open by another process")

    monkeypatch.setattr(FileSystemStorage, "delete", refuse)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = upload(client, encoded(a_photo(colour=(9, 9, 9)), "PNG"))

    assert response.status_code == 200
    assert len(callbacks) == 1


def test_a_failed_save_deletes_the_new_file_and_keeps_the_old(session_client, media_root, monkeypatch):
    client, user = session_client.client, session_client.user
    upload(client, encoded(a_photo(), "PNG"))
    user.refresh_from_db()
    old_name = user.picture.name

    def fail(name):
        raise RuntimeError("the transaction failed after the new file was written")

    monkeypatch.setattr(pictures, "_delete_after_commit", fail)
    with pytest.raises(RuntimeError):
        upload(client, encoded(a_photo(colour=(9, 9, 9)), "PNG"))

    user.refresh_from_db()
    assert user.picture.name == old_name
    assert stored_files(media_root) == [old_name.split("/")[1]]


# --- GET: one 404, anonymous 401, the headers ---------------------------------------------------


def test_an_unknown_id_and_a_user_with_no_picture_are_the_same_404(session_client, employee, administrator):
    client = session_client.client
    other = the_other(session_client, employee, administrator)

    unknown = client.get(f"/api/users/{uuid.uuid4()}/picture")
    without = client.get(f"/api/users/{other.pk}/picture")

    assert unknown.status_code == without.status_code == 404
    assert unknown.content == without.content
    assert unknown.json() == {"detail": USER_NOT_FOUND_MESSAGE}


def test_a_picture_gone_from_disk_is_the_same_404_and_is_logged(session_client, media_root, error_log_file):
    client, user = session_client.client, session_client.user
    upload(client, encoded(a_photo(), "PNG"))
    user.refresh_from_db()
    (media_root / user.picture.name).unlink()

    response = client.get(f"/api/users/{user.pk}/picture")

    assert response.status_code == 404
    assert response.content == client.get(f"/api/users/{uuid.uuid4()}/picture").content
    assert str(user.pk) in error_log_file.read_text(encoding="utf-8")


def test_anonymous_is_refused_on_every_picture_route(api_client, employee, media_root):
    assert upload(logged_in(employee), encoded(a_photo(), "PNG")).status_code == 200

    assert api_client.get(f"/api/users/{employee.pk}/picture").status_code == 401
    assert upload(api_client, encoded(a_photo(), "PNG")).status_code == 401
    assert api_client.delete(OWN_PICTURE_URL).status_code == 401
    employee.refresh_from_db()
    assert employee.picture


def test_the_picture_is_png_bytes_with_its_own_headers(session_client, settings):
    """``nosniff`` with SecurityMiddleware's own turned off, so the view's header is the one seen."""
    settings.SECURE_CONTENT_TYPE_NOSNIFF = False
    client = logged_in(session_client.user)
    upload(client, encoded(a_photo(), "PNG"))

    response = client.get(f"/api/users/{session_client.user.pk}/picture")

    assert response.status_code == 200
    assert not response.streaming  # bytes, not a FileResponse holding the file open
    assert response["Content-Type"] == "image/png"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Disposition"] == 'inline; filename="picture.png"'
    directives = {directive.strip() for directive in response["Cache-Control"].split(",")}
    assert directives == NEVER_CACHE_DIRECTIVES
    assert "Expires" in response


def test_a_client_asking_for_image_png_gets_it_not_a_406(session_client):
    upload(session_client.client, encoded(a_photo(), "PNG"))

    response = session_client.client.get(
        f"/api/users/{session_client.user.pk}/picture", HTTP_ACCEPT="image/png"
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"


def test_nothing_serves_the_stored_picture_from_the_media_folder(session_client, api_client, media_root):
    upload(session_client.client, encoded(a_photo(), "PNG"))
    stored_bytes = stored_png(media_root, session_client.user)

    for client in (api_client, session_client.client):
        response = client.get(f"/media/{session_client.user.picture.name}")
        assert response.status_code == 404
        assert response.content != stored_bytes
        assert response.json() == {"detail": "Not found."}


# --- Where picture appears ----------------------------------------------------------------------


def test_the_user_object_carries_the_picture_wherever_it_is_returned(
    session_client, employee, administrator, administrator_client
):
    client, user = session_client.client, session_client.user
    assert client.get(ME_URL).json()["picture"] is None

    upload(client, encoded(a_photo(), "PNG"))
    url = expected_picture_url(user)

    assert client.get(ME_URL).json()["picture"] == url
    signed_in = APIClient().post(
        "/api/auth/login", {"email": user.email, "password": PASSWORD}, format="json"
    )
    assert signed_in.status_code == 200 and signed_in.json()["picture"] == url
    listed = {row["id"]: row for row in administrator_client.get("/api/users").json()}
    assert listed[str(user.pk)]["picture"] == url
    other = the_other(session_client, employee, administrator)
    assert listed[str(other.pk)]["picture"] is None


def test_directory_entries_carry_the_picture(session_client, employee, administrator):
    other = the_other(session_client, employee, administrator)
    upload(logged_in(other), encoded(a_photo(), "PNG"))

    rows = {row["id"]: row for row in session_client.client.get("/api/users/directory").json()}

    assert rows[str(other.pk)]["picture"] == expected_picture_url(other)
    assert rows[str(session_client.user.pk)]["picture"] is None
    assert all(set(row) == {"id", "name", "email", "picture"} for row in rows.values())


def test_a_registration_returns_no_picture(api_client):
    response = api_client.post(
        "/api/auth/register",
        {"name": "Nadia Newcomer", "email": "nadia@example.com", "password": PASSWORD},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["picture"] is None


# --- A meeting detail's attendee_people ---------------------------------------------------------


def a_meeting(attendees, title="Board sync"):
    meeting = Meeting.objects.create(
        title=title, meeting_date=date(2026, 11, 2), transcript_text="Speaker A: the budget.",
        visible_to_roles=list(ROLE_NAMES),
    )
    for person in attendees:
        MeetingAttendee.objects.create(meeting=meeting, user=person)
    return meeting


def test_attendee_people_match_attendees_and_show_a_picture_once_uploaded(
    session_client, employee, administrator
):
    client, user = session_client.client, session_client.user
    zed = User.objects.create_user("zed@example.com", PASSWORD, name="Zed Zimmer")
    meeting = a_meeting([zed, employee, administrator])

    before = client.get(f"/api/meetings/{meeting.id}").json()
    upload(client, encoded(a_photo(), "PNG"))
    after = client.get(f"/api/meetings/{meeting.id}").json()

    assert before["attendees"] == after["attendees"]
    assert len(before["attendees"]) == 3
    for body in (before, after):
        assert [person["email"] for person in body["attendee_people"]] == body["attendees"]
        by_email = {person.email: person for person in (zed, employee, administrator)}
        assert [person["name"] for person in body["attendee_people"]] == [
            by_email[email].name for email in body["attendees"]
        ]
        assert all(set(person) == {"email", "name", "picture"} for person in body["attendee_people"])
    assert all(person["picture"] is None for person in before["attendee_people"])
    pictures_after = {person["email"]: person["picture"] for person in after["attendee_people"]}
    assert pictures_after == {
        zed.email: None,
        user.email: expected_picture_url(user),
        the_other(session_client, employee, administrator).email: None,
    }


def test_attendee_people_cost_no_query_per_attendee(session_client, employee, administrator):
    client = session_client.client
    others = [User.objects.create_user(f"guest{n}@example.com", PASSWORD, name=f"Guest {n}") for n in range(4)]
    for person in (employee, *others[:2]):
        upload(logged_in(person), encoded(a_photo(), "PNG"))
    small = a_meeting([employee], title="Small")
    large = a_meeting([employee, administrator, *others], title="Large")
    client.get(f"/api/meetings/{small.id}")  # warm the session

    with CaptureQueriesContext(connection) as small_queries:
        small_body = client.get(f"/api/meetings/{small.id}").json()
    with CaptureQueriesContext(connection) as large_queries:
        large_body = client.get(f"/api/meetings/{large.id}").json()

    assert len(small_body["attendee_people"]) == 1 and len(large_body["attendee_people"]) == 6
    assert len(large_queries) == len(small_queries)


def test_the_meeting_list_carries_no_attendee_people(session_client, employee):
    a_meeting([employee])

    rows = session_client.client.get("/api/meetings").json()

    assert rows and all("attendee_people" not in row for row in rows)
