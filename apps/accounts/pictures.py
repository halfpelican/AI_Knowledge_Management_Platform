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
  from its first bytes here, wherever Pillow reads one (``webp_canvas_size``), and refused before
  Pillow opens it. Until the review of 17 November 2026 (PIC-1) it was not, and a 140-byte WebP
  declaring 13,300 x 13,300 pixels made libwebp commit about 1.4 GB of memory before the cap refused
  it. The final review that day (PIC-1R) found the size still unread in a lossless WebP of 25 to 29
  bytes, which Pillow reads and libwebp opens: about 1.3 GB for one of 26 bytes. Pillow raises its
  own ``DecompressionBombError`` while reading a header that declares more than twice its
  MAX_IMAGE_PIXELS, and that is the same refusal.
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
- **A JPEG has at most MAX_PICTURE_JPEG_SCANS scans** (the final review of 17 November 2026, JPG-1).
  The reduced scale reduces only the output: libjpeg still decodes every scan, each a pass over
  every block of its component, however few bytes the scan takes. The review's 5 MB file repeated
  one 42-byte refinement scan to hold a decode place for about 47 minutes. So before Pillow opens a
  JPEG, ``jpeg_scan_bound`` counts its scans, and one with more than the cap is ``UnreadablePicture``.

  **The count is an upper bound, and what that costs.** It is the number of FF DA byte pairs in the
  whole file. Every scan begins with its SOS marker, FF DA, and no scan's entropy-coded data holds
  one, since an FF there is followed only by 00 or a restart marker. So the count is never short of
  the scans libjpeg decodes, however the file is malformed. But it counts FF DA wherever it falls,
  in metadata too: EXIF, an ICC profile, a comment, an embedded thumbnail (a small JPEG with scans of
  its own), or a second picture after the first one ends. So a JPEG whose other bytes hold more FF
  DA pairs than the cap leaves room for is refused with the same 415. By chance a pair is one in
  65,536, so it takes about 6.5 MB of random bytes to hold 100, more than MAX_PICTURE_BYTES allows.
  Walking the marker segments instead would leave metadata out, but it counts correctly only if it
  reads a malformed file exactly as libjpeg does: a walker that skipped bytes libjpeg reads as scans
  would count short, and the cap would hold nothing back.
- **The decoded picture is the one full-size image** of a picture already RGB or RGBA: it is turned
  upright in place and converted only if its mode must change. (Pillow's own scaling premultiplies
  an alpha band at full size, which this does not avoid.)

**A 16-bit greyscale PNG** (the review's COR-1) opens as mode I;16, and Pillow's conversion of that
to RGB clips every sample above 255 to white instead of scaling it. ``_eight_bit`` scales it first,
and turns its 16-bit transparency key into an alpha band, which Pillow matched by its low byte.

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
    MAX_PICTURE_JPEG_SCANS,
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

# How much of a WebP Pillow reads to find its canvas's size, and this too: "RIFF", the file's
# length, "WEBP", then the first chunk's name and length and the first ten bytes of its payload
# (``webp_canvas_size``).
WEBP_HEADER_BYTES = 30
# How much of that a lossless WebP needs: its VP8L chunk gives its size in the first five bytes of
# its payload, so Pillow reads the size of one of 25 bytes or more (PIC-1R).
WEBP_LOSSLESS_HEADER_BYTES = 25
# A JPEG begins with its SOI marker, and each of its scans with an SOS marker (``jpeg_scan_bound``).
JPEG_START = b"\xff\xd8"
JPEG_SCAN_MARKER = b"\xff\xda"
# A JPEG is decoded at the most reduced of libjpeg's scales that still leaves at least this much on
# each side: twice the stored size, as Pillow's thumbnail asks for with its default reducing_gap of 2.
_JPEG_DRAFT_SIZE = (2 * PICTURE_MAX_DIMENSION, 2 * PICTURE_MAX_DIMENSION)
# The modes Pillow opens a 16-bit greyscale picture in. Only I;16 comes from a PNG today; the rest
# are its byte orders, and I its 32-bit form, which converts the same way.
_SIXTEEN_BIT_GREY_MODES = ("I;16", "I;16B", "I;16L", "I;16N", "I")
# Each 16-bit sample in 8 bits, rounded: 65535 is 255 x 257, so v / 257 takes 0 to 0 and 65535 to
# 255 exactly, and no sample falls halfway between two values.
_SIXTEEN_TO_EIGHT_BITS = [round(value / 257) for value in range(65536)]

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
    """The canvas a WebP's first WEBP_HEADER_BYTES declare, or None when they are not a WebP whose
    size they give. ``header`` is shorter when the file is: then it is the whole file.

    Read wherever Pillow 13 reads a size when it opens a WebP (``WebPImagePlugin._get_size``), which
    it does just before it creates libwebp's decoder, the step that allocates the canvas. Pillow reads
    from the first chunk, the one it requires a WebP to begin with, and needs only as many bytes as
    that chunk's kind of header takes:

    - ``VP8X``, the extended format (animation, alpha, metadata): the canvas, 24 bits for each side,
      less one, in the first WEBP_HEADER_BYTES.
    - ``VP8 ``, a lossy picture: its key frame's 14-bit width and height, after the start code, in
      the first WEBP_HEADER_BYTES.
    - ``VP8L``, a lossless picture: 14 bits for each side, less one, after the signature byte, in
      the first WEBP_LOSSLESS_HEADER_BYTES. Until the final review of 17 November 2026 (PIC-1R) a
      lossless WebP was read only from WEBP_HEADER_BYTES, so one of 25 to 29 bytes reached Pillow,
      which read its size, and libwebp, which opened one of 26 or 28 bytes declaring 13,000 x 13,000
      and committed about 1.3 GB before the cap refused it.

    None for anything else, which then reaches Pillow as before. Pillow reads no size from it either,
    and libwebp creates no decoder for it: tried on one of each, a lossless header of 24 bytes, a
    VP8X or VP8 one of 29, a wrong signature byte and a wrong start code, with the libwebp (1.6.0)
    that Pillow 13 bundles.
    """
    if header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return None
    chunk = header[12:16]
    if chunk == b"VP8X" and len(header) >= WEBP_HEADER_BYTES:
        return int.from_bytes(header[24:27], "little") + 1, int.from_bytes(header[27:30], "little") + 1
    if chunk == b"VP8 " and len(header) >= WEBP_HEADER_BYTES and header[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(header[26:28], "little") & 0x3FFF
        return width, int.from_bytes(header[28:30], "little") & 0x3FFF
    if chunk == b"VP8L" and len(header) >= WEBP_LOSSLESS_HEADER_BYTES and header[20] == 0x2F:
        bits = int.from_bytes(header[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def jpeg_scan_bound(data: bytes) -> int:
    """At most how many scans libjpeg decodes from ``data``, a JPEG: the FF DA pairs in all of it.

    An upper bound, never short. Every scan begins with its SOS marker, FF DA, and an FF inside a
    scan's entropy-coded data is followed only by 00 or a restart marker, so FF DA cannot be there.
    FF DA in metadata, or after the picture ends, counts too: the module docstring says what that
    costs, and why the marker segments are not walked instead (JPG-1).
    """
    return data.count(JPEG_SCAN_MARKER)


def reencode_picture(upload) -> bytes:
    """The upload's first frame as a PNG of at most PICTURE_MAX_DIMENSION a side, and nothing else.

    Raises, in this order:

    1. ``PicturesBusy`` before reading anything when MAXIMUM_PICTURE_DECODES_IN_FLIGHT pictures are
       being decoded already.
    2. Before Pillow opens the file: ``PictureTooLarge`` for a WebP whose header declares more than
       MAX_PICTURE_PIXELS, and ``UnreadablePicture`` for a JPEG of more than MAX_PICTURE_JPEG_SCANS
       scans by ``jpeg_scan_bound``.
    3. ``UnreadablePicture`` for anything Pillow cannot open as a PNG, JPEG or WebP.
    4. ``PictureTooLarge`` before decoding anything when the header declares more than
       MAX_PICTURE_PIXELS.
    5. ``UnreadablePicture`` for a picture Pillow cannot decode.

    ``upload`` is any binary file object; it is read from the start.
    """
    with _decode_place():
        upload.seek(0)
        header = upload.read(WEBP_HEADER_BYTES)
        canvas = webp_canvas_size(header)
        if canvas is not None and canvas[0] * canvas[1] > MAX_PICTURE_PIXELS:
            # Before Image.open, which for a WebP allocates the canvas twice over (PIC-1, PIC-1R).
            raise PictureTooLarge
        if header.startswith(JPEG_START):
            upload.seek(0)
            if jpeg_scan_bound(upload.read()) > MAX_PICTURE_JPEG_SCANS:
                # Before Image.open: libjpeg would decode every scan, however small (JPG-1).
                raise UnreadablePicture
        upload.seek(0)
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
    image = _eight_bit(source)
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


def _eight_bit(image):
    """``image`` itself, unless it is 16-bit greyscale: then its samples scaled to 8 bits (COR-1).

    Pillow's own conversion of I;16 clips every sample above 255 to 255, so nearly every 16-bit grey
    picture came out white. Each sample is mapped through ``_SIXTEEN_TO_EIGHT_BITS`` instead, which
    Pillow applies to a 32-bit (mode I) image as a 65,536-entry table. A transparency key is a 16-bit
    value: it becomes an alpha band, matched against the 16-bit samples before they are scaled, since
    after scaling many samples share its 8-bit value. The rest of ``info`` is kept, so the EXIF
    orientation still applies.
    """
    if image.mode not in _SIXTEEN_BIT_GREY_MODES:
        return image
    wide = image if image.mode == "I" else image.convert("I")
    grey = wide.point(_SIXTEEN_TO_EIGHT_BITS, "L")
    key = image.info.get("transparency")
    if isinstance(key, int):
        alpha = wide.point([0 if value == key else 255 for value in range(65536)], "L")
        eight = Image.merge("LA", (grey, alpha))
    else:
        eight = grey
    eight.info = {name: value for name, value in image.info.items() if name != "transparency"}
    return eight


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
