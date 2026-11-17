"""Profile pictures (D-137): an upload read by Pillow and re-encoded, and the stored file replaced.

D-137, Benjamin's decision of 16 November 2026: a picture is seen by every signed-in user, wherever
users are listed, so what is stored has to be safe to show to anybody. Three things make it so.

- **The format comes from the content.** Pillow is told to try PICTURE_FORMATS (PNG, JPEG, WebP)
  and nothing else. The upload's name and declared type are never read. A GIF, an SVG or text,
  under any name, is unidentified and refused, and no other format's parser runs at all.
- **The pixel count is checked before a pixel is decoded.** For a PNG or a JPEG, ``Image.open``
  reads the header only, so a small file declaring enormous dimensions is refused at
  MAX_PICTURE_PIXELS without being decompressed. **A WebP is different:** Pillow opens one by
  creating libwebp's decoder, which allocates the canvas twice over, so a WebP's canvas is read
  from its first bytes here, as libwebp reads it (``webp_canvas_size``), and refused before Pillow
  opens it. Until the review of 17 November 2026 (PIC-1) it was not, and a 140-byte WebP declaring
  13,300 x 13,300 pixels made libwebp commit about 1.4 GB of memory before the cap refused it.
  Pillow raises its own ``DecompressionBombError`` while reading a header that declares more than
  twice its MAX_IMAGE_PIXELS, and that is the same refusal.
- **Nothing but the pixels is kept.** The first frame is decoded, turned upright by its EXIF
  orientation, converted to RGB, or RGBA when it has transparency, and scaled down to fit
  PICTURE_MAX_DIMENSION. Then a fresh image is built from those pixels alone, with
  ``Image.frombytes``, and saved as a PNG. Pillow's PNG save copies an ICC profile, a transparency
  key and EXIF from the image's ``info``, and a fresh image has none, so a photo's location, its
  camera and its colour profile are not stored.

**What a decode may cost** (PIC-1). A picture at the cap is up to 100 MB decoded, and decoding one
touched about 400 to 500 MB, with its copies. The review measured ten decodes at once taking a
process's peak working set from 53 MB to 4,191 MB, and the `picture` throttle let ten through at
once. So:

- **At most MAXIMUM_PICTURE_DECODES_IN_FLIGHT pictures are decoded at once** in this process,
  across every user. An upload that finds every place taken raises ``PicturesBusy``, which the route
  answers at once with its 429, before anything of the picture is read. A place is a count in this
  process's memory, not a cache entry: the memory it protects is this process's own, and no cache
  can drop it.
- **A JPEG is decoded at a reduced scale.** libjpeg can divide each side by 2, 4 or 8 as it decodes,
  and the largest of those that still leaves twice the stored size on each side is used, as Pillow's
  ``thumbnail`` asks for when the picture is not decoded yet. PNG and WebP have no such scale.
- **The decoded picture is the one full-size image** of a picture already RGB or RGBA: it is turned
  upright in place and converted only if its mode must change. (Pillow's own scaling premultiplies
  an alpha band at full size, which this does not avoid.)

**One refusal for anything Pillow cannot read.** Pillow's decoders raise many kinds of error on a
damaged file: ``OSError`` for a truncated or broken stream, ``SyntaxError``, ``ValueError``,
``struct.error`` and others for a malformed header or EXIF block. Each means the same thing here,
that the upload is not a picture this server can read, so every one is ``UnreadablePicture``, which
the route answers with its one 415. The broad catch wraps only the Pillow calls on the upload.

**The stored file is replaced in one transaction, and the old one deleted after it commits.** See
``replace_picture``. A filesystem is not transactional, so the order is what keeps a row and its
file agreeing: the new file exists before the row names it, and the old one outlives the row that
named it until that row's change has committed.
"""

import io
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps

from apps.accounts.models import User
from apps.core.constants import (
    MAX_PICTURE_PIXELS,
    MAXIMUM_PICTURE_DECODES_IN_FLIGHT,
    PICTURE_FORMATS,
    PICTURE_MAX_DIMENSION,
)

# What FieldFile.save() is handed as the upload's name. picture_upload_path ignores it and makes
# a random one, so nothing the client sent names a file.
STORED_NAME = "picture.png"

_EPOCH = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
_ONE_MICROSECOND = timedelta(microseconds=1)

# How much of a WebP holds its canvas's size: "RIFF", the file's length, "WEBP", then the first
# chunk's name and length and the first ten bytes of its payload (``webp_canvas_size``).
WEBP_HEADER_BYTES = 30
# A JPEG is decoded at the most reduced of libjpeg's scales that still leaves at least this much on
# each side: twice the stored size, as Pillow's thumbnail asks for with its default reducing_gap of 2.
_JPEG_DRAFT_SIZE = (2 * PICTURE_MAX_DIMENSION, 2 * PICTURE_MAX_DIMENSION)

# How many pictures this process is decoding now. Read and changed only under its lock.
_decodes_in_flight = 0
_decodes_lock = threading.Lock()


class PictureTooLarge(Exception):
    """The picture's header declares more than MAX_PICTURE_PIXELS pixels: the route's 413."""


class UnreadablePicture(Exception):
    """Not a PNG, JPEG or WebP, or one that is corrupt or truncated: the route's one 415."""


class PicturesBusy(Exception):
    """MAXIMUM_PICTURE_DECODES_IN_FLIGHT pictures are being decoded already: the route's 429."""


@contextmanager
def _decode_place():
    """Hold one of this process's MAXIMUM_PICTURE_DECODES_IN_FLIGHT places while a picture is read.

    Raises ``PicturesBusy`` at once when every place is held, rather than waiting, so a refused
    upload holds no thread (PIC-1). The place is given back however the block ends.
    """
    global _decodes_in_flight
    with _decodes_lock:
        if _decodes_in_flight >= MAXIMUM_PICTURE_DECODES_IN_FLIGHT:
            raise PicturesBusy
        _decodes_in_flight += 1
    try:
        yield
    finally:
        with _decodes_lock:
            _decodes_in_flight -= 1


def webp_canvas_size(header: bytes) -> tuple[int, int] | None:
    """The canvas a WebP's first WEBP_HEADER_BYTES declare, or None when it is not a WebP whose size
    they give.

    Read as libwebp reads it when Pillow opens the file, which is when it allocates the canvas, and
    as Pillow 13 reads it for its own check, from the first chunk, the one Pillow requires a WebP to
    begin with:

    - ``VP8X``, the extended format (animation, alpha, metadata): the canvas, 24 bits for each side,
      less one.
    - ``VP8 ``, a lossy picture: its key frame's 14-bit width and height, after the start code.
    - ``VP8L``, a lossless picture: 14 bits for each side, less one, after the signature byte.

    None for anything else, which then reaches Pillow as before: a WebP with no such header has no
    canvas for libwebp to allocate, and fails to open.
    """
    if len(header) < WEBP_HEADER_BYTES or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return None
    chunk = header[12:16]
    if chunk == b"VP8X":
        return int.from_bytes(header[24:27], "little") + 1, int.from_bytes(header[27:30], "little") + 1
    if chunk == b"VP8 " and header[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(header[26:28], "little") & 0x3FFF
        return width, int.from_bytes(header[28:30], "little") & 0x3FFF
    if chunk == b"VP8L" and header[20] == 0x2F:
        bits = int.from_bytes(header[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def reencode_picture(upload) -> bytes:
    """The upload's first frame as a PNG of at most PICTURE_MAX_DIMENSION a side, and nothing else.

    Raises ``PicturesBusy`` before reading anything when MAXIMUM_PICTURE_DECODES_IN_FLIGHT pictures
    are being decoded already, ``PictureTooLarge`` before decoding anything when the header declares
    more than MAX_PICTURE_PIXELS, and ``UnreadablePicture`` for anything Pillow cannot open or decode
    as a PNG, JPEG or WebP. ``upload`` is any binary file object; it is read from the start.
    """
    with _decode_place():
        upload.seek(0)
        canvas = webp_canvas_size(upload.read(WEBP_HEADER_BYTES))
        upload.seek(0)
        if canvas is not None and canvas[0] * canvas[1] > MAX_PICTURE_PIXELS:
            # Before Image.open, which for a WebP allocates the canvas twice over (PIC-1).
            raise PictureTooLarge
        try:
            source = Image.open(upload, formats=PICTURE_FORMATS)
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            # The error, above twice Pillow's MAX_IMAGE_PIXELS. The warning is caught too, for a
            # process that turns warnings into errors; otherwise Pillow only warns and the cap
            # below refuses.
            raise PictureTooLarge from error
        except Exception as error:  # noqa: BLE001 - see the module docstring: one 415 for all
            raise UnreadablePicture from error
        with source:
            # Read from the header: nothing has been decoded yet.
            width, height = source.size
            if width * height > MAX_PICTURE_PIXELS:
                raise PictureTooLarge
            try:
                return _pixels_as_png(source)
            except Exception as error:  # noqa: BLE001 - see the module docstring: one 415 for all
                raise UnreadablePicture from error


def _pixels_as_png(source) -> bytes:
    """Decode ``source``'s first frame and keep only its pixels, as a PNG (the module docstring)."""
    source.seek(0)  # the first frame of an animated WebP or a multi-picture JPEG
    source.draft(None, _JPEG_DRAFT_SIZE)  # a JPEG's reduced scale; nothing for PNG or WebP
    source.load()  # decodes it: a corrupt or truncated file fails here
    image = source
    ImageOps.exif_transpose(image, in_place=True)  # turned as its EXIF says, without a copy
    mode = "RGBA" if image.has_transparency_data else "RGB"
    # Converted only if its mode must change: a transparency key or a palette's alpha becomes an
    # alpha band. Converting to the mode it has would copy it at full size.
    pixels = image if image.mode == mode else image.convert(mode)
    pixels.thumbnail((PICTURE_MAX_DIMENSION, PICTURE_MAX_DIMENSION))  # keeps its shape; never enlarges
    # A new image from the raw pixels, with an empty info: no ICC profile, transparency key, EXIF or
    # text for the PNG encoder to copy.
    fresh = Image.frombytes(mode, pixels.size, pixels.tobytes())
    buffer = io.BytesIO()
    fresh.save(buffer, format="PNG")
    return buffer.getvalue()


def picture_version(updated_at) -> int:
    """``updated_at`` in whole microseconds since the Unix epoch: the user object's ``?v=``.

    Exact integer arithmetic on the datetime, never a float timestamp, which can lose the last
    microsecond. A replaced picture has a later ``picture_updated_at``, so a new address.
    """
    return (updated_at - _EPOCH) // _ONE_MICROSECOND


def _picture_storage():
    return User._meta.get_field("picture").storage


def _locked_account(user):
    """The user's row, read afresh and locked until the transaction ends, with its role.

    FOR NO KEY UPDATE, and of the users row alone (``of=("self",)``), as FR-03's release locks its
    target. It conflicts with login's FOR UPDATE and with another picture change on the same row, so
    those take turns, but not with the key-share locks that inserts referencing the user take. It is
    the only row this transaction locks, so it cannot join a lock cycle with the role change or the
    release, which lock several users rows in primary-key order (D-130).
    """
    return (
        User.objects.select_for_update(no_key=True, of=("self",))
        .select_related("role")
        .get(pk=user.pk)
    )


def _delete_after_commit(name: str) -> None:
    """Delete the stored file ``name`` once the transaction commits, as FR-15's deletion removes a
    document's original (apps/documents/deletion.py).

    ``robust=True``: once the row has committed the change is made, and a file the storage could
    not delete, held open by another process for example, is logged by Django rather than turned
    into an error for a request that has already succeeded. Nothing serves MEDIA_ROOT, so a file
    left behind is unreachable.

    **A named function, never ``functools.partial``.** Django 5.2 logs a robust callback's failure
    with ``func.__qualname__``, which a partial does not have, so a partial that raised would raise
    ``AttributeError`` from the commit hook instead, and ``robust`` would protect nothing.
    """
    storage = _picture_storage()

    def delete_replaced_picture():
        storage.delete(name)

    transaction.on_commit(delete_replaced_picture, robust=True)


def replace_picture(user, png: bytes):
    """Store ``png`` as ``user``'s picture, and return the row as it now stands, with its role.

    In one transaction:

    1. **The user's row is locked and read afresh** (``_locked_account``). Two uploads for one account
       then take turns, and each replaces what the other committed. Without the lock both would read
       the same old name, and the file of whichever committed first would be named by no row and
       never deleted.
    2. **The PNG is written under a new random name** (``picture_upload_path``).
    3. **``picture`` and ``picture_updated_at`` are saved, and no other column,** so a role change or
       an FR-02 lock committed while the request ran is kept.
    4. **The old file, if there was one, is deleted after the commit** (``_delete_after_commit``). A
       transaction that rolls back leaves the row naming the old file, which is still there.

    If anything in the transaction fails, the row is rolled back and the new file is deleted, as
    ingestion deletes a stored original whose transaction failed (apps/ingestion/documents.py).
    """
    stored_name = None
    try:
        with transaction.atomic():
            account = _locked_account(user)
            previous_name = account.picture.name
            account.picture.save(STORED_NAME, ContentFile(png), save=False)
            stored_name = account.picture.name
            account.picture_updated_at = timezone.now()
            account.save(update_fields=["picture", "picture_updated_at"])
            if previous_name:
                _delete_after_commit(previous_name)
    except Exception:
        if stored_name:
            _picture_storage().delete(stored_name)
        raise
    return account


def remove_picture(user):
    """Clear ``user``'s picture, and return the row as it now stands, with its role.

    Idempotent: a user with no picture is saved with none, and nothing is deleted. The row is locked
    as ``replace_picture`` locks it, so a removal and an upload take turns, and the file the row
    named is deleted after the commit, in the same way.
    """
    with transaction.atomic():
        account = _locked_account(user)
        previous_name = account.picture.name
        account.picture = ""
        account.picture_updated_at = None
        account.save(update_fields=["picture", "picture_updated_at"])
        if previous_name:
            _delete_after_commit(previous_name)
    return account
