"""Profile pictures (D-137): an upload read by Pillow and re-encoded, and the stored file replaced.

D-137, Benjamin's decision of 16 November 2026: a picture is seen by every signed-in user, wherever
users are listed, so what is stored has to be safe to show to anybody. Three things make it so.

- **The format comes from the content.** Pillow is told to try PICTURE_FORMATS (PNG, JPEG, WebP)
  and nothing else. The upload's name and declared type are never read. A GIF, an SVG or text,
  under any name, is unidentified and refused, and no other format's parser runs at all.
- **The pixel count is checked before a pixel is decoded.** ``Image.open`` reads the header only,
  so a small file declaring enormous dimensions is refused at MAX_PICTURE_PIXELS without being
  decompressed. Pillow raises its own ``DecompressionBombError`` while reading a header that
  declares more than twice its MAX_IMAGE_PIXELS, and that is the same refusal.
- **Nothing but the pixels is kept.** The first frame is decoded, turned upright by its EXIF
  orientation, converted to RGB, or RGBA when it has transparency, and scaled down to fit
  PICTURE_MAX_DIMENSION. Then a fresh image is built from those pixels alone, with
  ``Image.frombytes``, and saved as a PNG. Pillow's PNG save copies an ICC profile, a transparency
  key and EXIF from the image's ``info``, and a fresh image has none, so a photo's location, its
  camera and its colour profile are not stored.

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
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps

from apps.accounts.models import User
from apps.core.constants import MAX_PICTURE_PIXELS, PICTURE_FORMATS, PICTURE_MAX_DIMENSION

# What FieldFile.save() is handed as the upload's name. picture_upload_path ignores it and makes
# a random one, so nothing the client sent names a file.
STORED_NAME = "picture.png"

_EPOCH = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
_ONE_MICROSECOND = timedelta(microseconds=1)


class PictureTooLarge(Exception):
    """The picture's header declares more than MAX_PICTURE_PIXELS pixels: the route's 413."""


class UnreadablePicture(Exception):
    """Not a PNG, JPEG or WebP, or one that is corrupt or truncated: the route's one 415."""


def reencode_picture(upload) -> bytes:
    """The upload's first frame as a PNG of at most PICTURE_MAX_DIMENSION a side, and nothing else.

    Raises ``PictureTooLarge`` before decoding anything when the header declares more than
    MAX_PICTURE_PIXELS, and ``UnreadablePicture`` for anything Pillow cannot open or decode as a
    PNG, JPEG or WebP. ``upload`` is any binary file object; it is read from the start.
    """
    upload.seek(0)
    try:
        source = Image.open(upload, formats=PICTURE_FORMATS)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        # The error, above twice Pillow's MAX_IMAGE_PIXELS. The warning is caught too, for a process
        # that turns warnings into errors; otherwise Pillow only warns and the cap below refuses.
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
    source.load()  # decodes it: a corrupt or truncated file fails here
    upright = ImageOps.exif_transpose(source)  # a single frame, turned as its EXIF says
    mode = "RGBA" if upright.has_transparency_data else "RGB"
    pixels = upright.convert(mode)  # a transparency key or a palette's alpha becomes an alpha band
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
