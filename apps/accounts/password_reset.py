"""The self-service password reset (D-137): the email a request sends, and the link that comes back.

D-137, Benjamin's decision of 16 November 2026, takes the proposal's section 1.9 item "Self-service
password reset flow" out of the out-of-scope list. FR-03 is unchanged. Two routes use this module
(``apps/api/views.py``):

- ``POST /api/auth/password-reset`` hands every well-formed address to ``request_reset_email`` and
  answers the same 200, with the same body, whatever happens next.
- ``POST /api/auth/password-reset/confirm`` sets the new password with ``reset_password``.

**The request does the same work for every address (D-25).** Only an account is sent an email. A
request that looked the address up and sent the email itself would take longer for a registered
address, and the time would tell an anonymous caller what D-25 removed from login: whether an
address is registered. So the request path does not look the address up at all. It starts a daemon
thread and answers. The thread looks the account up and sends the email, or does nothing, after the
request has answered or while it does.

**What the thread does** (``send_reset_email``):

1. **It finds the account** whose stored address equals the submitted one, lower-cased as login
   lower-cases it (D-02). No account, or one retired with an unusable password (D-89), and it stops:
   a reset would otherwise bring a retired account back, which is also why Django's own reset form
   skips such accounts.
2. **It takes the account's cooldown** with ``cache.add``. If a reset email went to the account in the
   last PASSWORD_RESET_COOLDOWN_SECONDS, it stops, silently, since the request has already answered.
   The cooldown starts when the send is attempted, so a send that fails waits it out too.
3. **It sends one plain-text email to the stored address,** never to the address as typed. The link is
   ``{PUBLIC_BASE_URL}/reset-password?uid=<URL-safe base64 of the id>&token=<token>``, built from the
   setting alone and never from the request or its Host header.

**Nothing the thread raises reaches anyone.** A failure is logged with its traceback, which the
error file keeps (D-75), and nothing else happens. Inline mode, below, depends on that: there, a
failure for an account that reached the response would be the very difference the thread hides.

**At most MAXIMUM_PASSWORD_RESET_EMAILS_IN_FLIGHT threads at once** in one process, each holding one
database connection, which it closes when it ends. A request past the limit starts nothing. It is
logged, and it is answered like every other, because the limit is applied before any account is
looked up. The ``auth`` throttle, per client address, bounds how fast the places can be asked for.

**If the process stops before a thread finishes,** the thread dies with it, since it is a daemon, and
its email is not sent. Nothing records it and nothing retries it. The person was answered the same
200 as ever and can ask again at once: the cooldown is kept in the process's own cache, which a
restart empties. An email the mail server had already accepted before the stop is delivered. In
the file outbox, a stop while the file is being written can leave it cut short.

**``PASSWORD_RESET_EMAIL_RUNNER``** (config/settings.py) is "thread" on a server. The suite sets
"inline" (conftest.py), which does the thread's work in the caller's thread, through its database
connection and inside a test's transaction, so the email is in ``mail.outbox`` when the response
arrives. The thread path has its own tests, which join every thread they start.

**The link** (``user_for_reset_link``). Its token is Django's ``default_token_generator``: an HMAC under
SECRET_KEY of the account's id, password hash, last sign-in and address, with the time it was made.
So it stops working PASSWORD_RESET_TIMEOUT after it was made (PASSWORD_RESET_LINK_MINUTES), and once
the password changes, which is what makes a link work once. A successful sign-in ends it too, since
it changes the last sign-in. FR-03's lock and count are not hashed, so neither a failed sign-in nor a
lock spoils a link.
"""

from __future__ import annotations

import logging
import threading
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import connections, transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.accounts.models import User
from apps.core.constants import (
    MAXIMUM_PASSWORD_RESET_EMAILS_IN_FLIGHT,
    PASSWORD_RESET_COOLDOWN_SECONDS,
)

logger = logging.getLogger(__name__)

THREAD_RUNNER = "thread"
INLINE_RUNNER = "inline"
# Every reset email's thread carries this name, so a test can find and join the ones it started.
THREAD_NAME = "password-reset-email"
# The SPA's page for a reset link: it reads uid and token from the address and posts them, with the
# new password, to POST /api/auth/password-reset/confirm. config.spa.index serves it like any page.
RESET_PAGE_PATH = "/reset-password"
# What the email calls the platform: frontend/index.html's <title>.
PLATFORM_NAME = "Organisational Knowledge Platform"
EMAIL_SUBJECT = f"Reset your {PLATFORM_NAME} password"

# The reset email threads this process has started and not yet finished. Read and changed only
# under its lock.
_in_flight = 0
_in_flight_lock = threading.Lock()


class ResetLinkRefused(Exception):
    """The link names no account it can reset now: the confirm route's one 400."""


class UnacceptablePassword(Exception):
    """The new password fails AUTH_PASSWORD_VALIDATORS for the account; ``messages`` are theirs."""

    def __init__(self, messages):
        super().__init__(messages)
        self.messages = messages


def emails_in_flight() -> int:
    """How many reset email threads are running now."""
    with _in_flight_lock:
        return _in_flight


def request_reset_email(email: str) -> None:
    """Hand ``email`` to a reset email's thread, and return without waiting for it.

    Called on the request path for every well-formed address, so it does the same work for each: it
    neither looks the address up nor sends anything. It never raises.
    """
    global _in_flight
    if settings.PASSWORD_RESET_EMAIL_RUNNER == INLINE_RUNNER:
        send_reset_email_guarded(email)
        return
    with _in_flight_lock:
        admitted = _in_flight < MAXIMUM_PASSWORD_RESET_EMAILS_IN_FLIGHT
        if admitted:
            _in_flight += 1
    if not admitted:
        logger.error(
            "A password reset email was not started: %s were already in flight",
            MAXIMUM_PASSWORD_RESET_EMAILS_IN_FLIGHT,
        )
        return
    try:
        threading.Thread(target=_send_in_thread, args=(email,), name=THREAD_NAME, daemon=True).start()
    except Exception:  # noqa: BLE001 - the operating system refused a thread
        with _in_flight_lock:
            _in_flight -= 1
        logger.exception("A password reset email could not be given a thread")


def _send_in_thread(email: str) -> None:
    global _in_flight
    try:
        send_reset_email_guarded(email)
    finally:
        with _in_flight_lock:
            _in_flight -= 1
        # Django opens a connection per thread and closes it only at the end of a request, which a
        # thread never reaches.
        connections.close_all()


def send_reset_email_guarded(email: str) -> None:
    """``send_reset_email``, with anything it raises logged and nothing else."""
    try:
        send_reset_email(email)
    except Exception:  # noqa: BLE001 - nothing about the email may reach the request
        logger.exception("A password reset email could not be sent")


def send_reset_email(email: str) -> bool:
    """Send the reset email to the account whose address is ``email``, if there is one and its
    cooldown allows. Returns whether an email was sent."""
    user = User.objects.filter(email=email).first()
    if user is None or not user.has_usable_password():
        return False
    if not cache.add(_cooldown_key(user), True, timeout=PASSWORD_RESET_COOLDOWN_SECONDS):
        return False
    send_mail(EMAIL_SUBJECT, reset_email_text(user), settings.DEFAULT_FROM_EMAIL, [user.email])
    return True


def _cooldown_key(user) -> str:
    return f"password-reset-cooldown:{user.pk}"


def reset_link(user) -> str:
    """The link a reset email carries, built from PUBLIC_BASE_URL alone (D-137)."""
    query = urlencode(
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
    )
    return f"{settings.PUBLIC_BASE_URL}{RESET_PAGE_PATH}?{query}"


def reset_email_text(user) -> str:
    """The email's plain text: the link, that it works once and for how long, and that nothing has
    changed for someone who did not ask."""
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    return (
        f"Someone asked to reset the password of your {PLATFORM_NAME} account.\n"
        "\n"
        "To choose a new password, open this link:\n"
        "\n"
        f"{reset_link(user)}\n"
        "\n"
        f"The link works once, within {minutes} minutes of this email.\n"
        "\n"
        "If you did not ask, you can ignore this email: your password is unchanged.\n"
    )


def user_for_reset_link(uid: str, token: str):
    """The account a reset link names, if the link works now; None for every way it can fail.

    One answer for all of them, so the confirm route's one 400 cannot tell an unknown account from a
    wrong, expired or used token: a ``uid`` that is not URL-safe base64 of a UUID, a UUID that names no
    account, an account retired with an unusable password (D-89), and a token the generator refuses
    for the account.
    """
    try:
        pk = uuid.UUID(urlsafe_base64_decode(uid).decode())
    except (TypeError, ValueError, OverflowError):  # a UnicodeError is a ValueError
        return None
    user = User.objects.filter(pk=pk).first()
    if user is None or not user.has_usable_password():
        return None
    if not default_token_generator.check_token(user, token):
        return None
    return user


def reset_password(uid: str, token: str, new_password: str):
    """Set the account's new password from a reset link, and return the account.

    Raises ``ResetLinkRefused`` for a link that does not work, and ``UnacceptablePassword`` for a
    password registration would refuse for this account (FR-01). The link is judged first, because
    the validators compare the password with the account's own name and address.

    On success the password column alone is saved, so a role change or a count FR-02 wrote meanwhile
    is kept, and FR-03's lock and count are left as they were (D-137). Nobody is signed in. Every
    session of the account ends on its next request, remembered ones included, because each holds a
    hash of the old password (D-137).

    **A link works once, even for two confirms at once.** The account's row is locked and the token
    checked again against it before the save. A confirm that waited for the lock finds the password
    the first one set, which its token no longer matches. The new hash is made before the lock is
    taken, so the lock is held for a few queries and never for a hash, as login's is (D-130).
    """
    user = user_for_reset_link(uid, token)
    if user is None:
        raise ResetLinkRefused
    try:
        validate_password(new_password, user)
    except ValidationError as error:
        raise UnacceptablePassword(error.messages) from error
    user.set_password(new_password)
    with transaction.atomic():
        current = (
            User.objects.select_for_update(no_key=True, of=("self",)).filter(pk=user.pk).first()
        )
        if current is None or not default_token_generator.check_token(current, token):
            raise ResetLinkRefused
        user.save(update_fields=["password"])
    return user
