"""FR-02 login: POST /api/auth/login, and GET /api/auth/me (docs/api-contract.md).

200 with the user object, the session cookie and the csrftoken cookie; 400 for a
missing field or an address that is not an address, checked before the database
lookup; 401 with one generic message for an unknown address and a wrong password
alike (D-02); 403 while the account is locked and the password matched, and the
ordinary 401 when it did not, so the lock is not an enumeration oracle (D-25). Side
effects: failed_attempts, locked_until, last_login.
"""

import datetime

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    LOCKOUT_DURATION,
    LOCKOUT_NOTICE_CEILING,
    LOCKOUT_THRESHOLD,
)
from conftest import PASSWORD

User = get_user_model()

pytestmark = pytest.mark.django_db

LOGIN = reverse("auth-login")
ME = reverse("auth-me")
INVALID = {"detail": "Invalid email or password."}
USER_OBJECT_KEYS = {"id", "name", "email", "role", "created_at"}
SECRET_COLUMNS = {"password", "password_hash", "failed_attempts", "locked_until", "last_login"}


def login(client, email, password=PASSWORD):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


# --- Happy path -------------------------------------------------------------------------------------


def test_login_returns_the_user_object(api_client, employee):
    response = login(api_client, employee.email)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == USER_OBJECT_KEYS
    assert body["id"] == str(employee.id)
    assert body["email"] == employee.email
    assert body["role"] == employee.role.role_name


def test_login_sets_the_session_and_csrf_cookies(api_client, employee):
    response = login(api_client, employee.email)
    session = response.cookies[settings.SESSION_COOKIE_NAME]
    csrf = response.cookies[settings.CSRF_COOKIE_NAME]
    assert session.value and csrf.value
    assert session["httponly"] is True
    assert session["samesite"] == "Lax"
    assert not csrf["httponly"]  # the front end reads it for X-CSRFToken


def test_the_session_cookie_authenticates_later_requests(employee):
    client = APIClient()
    login(client, employee.email)
    session_key = client.cookies[settings.SESSION_COOKIE_NAME].value

    # A fresh client carrying only that cookie value is the same session.
    replay = APIClient()
    replay.cookies[settings.SESSION_COOKIE_NAME] = session_key
    response = replay.get(ME)
    assert response.status_code == 200
    assert response.json()["id"] == str(employee.id)


def test_login_email_is_case_insensitive(api_client, employee):
    assert login(api_client, "  Employee@EXAMPLE.com ").status_code == 200


def test_login_works_for_an_administrator(api_client, administrator):
    response = login(api_client, administrator.email)
    assert response.status_code == 200
    assert response.json()["role"] == ADMINISTRATOR_ROLE_NAME


def test_login_response_never_exposes_secret_columns(api_client, employee):
    assert SECRET_COLUMNS.isdisjoint(login(api_client, employee.email).json())


# --- 401: one message, whichever half of the credential is wrong --------------------------------------


def test_unknown_email_is_401_with_the_generic_message(api_client, employee):
    response = login(api_client, "nobody@example.com")
    assert response.status_code == 401
    assert response.json() == INVALID
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_wrong_password_is_401_with_the_same_message(api_client, employee):
    response = login(api_client, employee.email, "wrong password")
    assert response.status_code == 401
    assert response.json() == INVALID
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_a_failed_login_does_not_authenticate(api_client, employee):
    login(api_client, employee.email, "wrong password")
    assert api_client.get(ME).status_code == 401


# --- 400 malformed body ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [{}, {"email": "employee@example.com"}, {"password": PASSWORD}, {"email": "", "password": ""}],
)
def test_malformed_login_body_is_400(api_client, employee, payload):
    response = api_client.post(LOGIN, payload, format="json")
    assert response.status_code == 400
    assert set(response.json()) <= {"email", "password"}


@pytest.mark.parametrize(
    "address", ["not-an-address", "missing-at-sign.example.com", "two@@example.com", "@example.com"]
)
def test_an_address_that_is_not_an_address_is_400(api_client, employee, address):
    """FR-02 Validation rules: "Email format checked before database lookup", and the
    login pseudocode returns 400 for it explicitly (D-25). This was 401 before, on
    the argument that a malformed address is just an unknown one."""
    response = api_client.post(LOGIN, {"email": address, "password": PASSWORD}, format="json")
    assert response.status_code == 400
    assert list(response.json()) == ["email"]
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_a_malformed_address_discloses_nothing(api_client, employee):
    """The 400 is safe precisely because it does not depend on the account: a
    registered address and an unregistered one in the same broken shape answer
    identically, so the check is not an enumeration oracle."""
    registered = api_client.post(
        LOGIN, {"email": f"{employee.email}@", "password": PASSWORD}, format="json"
    )
    unknown = api_client.post(
        LOGIN, {"email": "nobody@example.com@", "password": PASSWORD}, format="json"
    )
    assert registered.status_code == unknown.status_code == 400
    assert registered.json() == unknown.json()


def test_a_well_formed_unknown_address_is_still_401(api_client, employee):
    # The enumeration protection is here, and it stays: format is syntax, existence
    # is not disclosed.
    response = login(api_client, "nobody@example.com")
    assert response.status_code == 401
    assert response.json() == INVALID


def test_an_over_long_address_is_400(api_client, employee):
    # Bounded by the same column length as the registration serializer.
    length = User._meta.get_field("email").max_length
    local = "a" * (length - len("@example.com") + 1)
    response = login(api_client, f"{local}@example.com")
    assert response.status_code == 400
    assert "email" in response.json()


# --- Side effects (docs/api-contract.md "Login side effects") --------------------------------------------


def test_a_failed_attempt_increments_failed_attempts(api_client, employee):
    login(api_client, employee.email, "wrong password")
    employee.refresh_from_db()
    assert employee.failed_attempts == 1
    assert employee.locked_until is None


def test_the_threshold_failure_sets_locked_until(api_client, employee):
    employee.failed_attempts = LOCKOUT_THRESHOLD - 1
    employee.save(update_fields=["failed_attempts"])

    before = timezone.now()
    login(api_client, employee.email, "wrong password")
    after = timezone.now()

    employee.refresh_from_db()
    assert employee.failed_attempts == LOCKOUT_THRESHOLD
    assert before + LOCKOUT_DURATION <= employee.locked_until <= after + LOCKOUT_DURATION


def test_a_success_resets_failed_attempts_and_sets_last_login(api_client, employee):
    employee.failed_attempts = LOCKOUT_THRESHOLD - 2
    employee.save(update_fields=["failed_attempts"])
    assert employee.last_login is None

    before = timezone.now()
    assert login(api_client, employee.email).status_code == 200

    employee.refresh_from_db()
    assert employee.failed_attempts == 0
    assert employee.last_login is not None
    assert before <= employee.last_login <= timezone.now()


def test_an_unknown_email_records_nothing(api_client, employee):
    before = User.objects.count()
    login(api_client, "nobody@example.com")
    employee.refresh_from_db()
    assert employee.failed_attempts == 0
    assert User.objects.count() == before


# --- FR-02 lockout enforcement (D-25) ----------------------------------------------
# "Failed attempts increment a counter; five consecutive failures lock the account
# for 15 minutes" and "403 forbidden if account is locked". The lock is enforced
# here, in FR-02; FR-03 adds only the warning interface.


def lock(user, remaining=LOCKOUT_DURATION):
    user.failed_attempts = LOCKOUT_THRESHOLD
    user.locked_until = timezone.now() + remaining
    user.save(update_fields=["failed_attempts", "locked_until"])
    return user


def test_a_locked_account_is_403_even_with_the_right_password(api_client, employee):
    lock(employee)

    response = login(api_client, employee.email)

    assert response.status_code == 403
    assert settings.SESSION_COOKIE_NAME not in response.cookies
    # FR-02 Front-End: "where the account is locked and the submitted password was
    # correct, a distinct message is shown", so the body identifies the lockout.
    assert response.json() == {
        "detail": (
            "This account is temporarily locked after repeated failed sign-ins. "
            "Please try again later."
        ),
        "code": "account_locked",
    }


def test_a_locked_account_with_the_wrong_password_is_the_ordinary_401(api_client, employee):
    """The lock is announced only where the password also matched. The proposal's
    handleLoginAttempt() pseudocode branches here deliberately: "Confirming a lock to
    anyone who merely knows the email address would convert a protective measure into
    an account-enumeration tool." So this response must be byte-identical to the one
    an unregistered address gets, or the 403 becomes the oracle."""
    lock(employee)

    response = login(api_client, employee.email, "wrong password")

    assert response.status_code == 401
    assert response.json() == INVALID
    assert "code" not in response.json()


def test_a_locked_account_is_indistinguishable_from_an_unknown_address(api_client, employee):
    """The enumeration property itself, asserted rather than argued: same status and
    same body for a locked account and for an address that was never registered."""
    lock(employee)

    locked = login(api_client, employee.email, "wrong password")
    unknown = login(api_client, "no-such-person@example.com", "wrong password")

    assert (locked.status_code, locked.json()) == (unknown.status_code, unknown.json())


def test_a_locked_account_issues_no_session(api_client, employee):
    lock(employee)
    login(api_client, employee.email)
    assert api_client.get(ME).status_code == 401


def test_an_attempt_during_the_lock_does_not_extend_it(api_client, employee):
    """"Locks the account for 15 minutes" stays literally true: a sustained attack
    cannot push the window out indefinitely. The counter does move, so that the
    notice can be withdrawn once guessing passes the ceiling (D-26)."""
    lock(employee)
    locked_until = employee.locked_until

    login(api_client, employee.email)  # correct password
    login(api_client, employee.email, "wrong password")

    employee.refresh_from_db()
    assert employee.locked_until == locked_until
    assert employee.failed_attempts == LOCKOUT_THRESHOLD + 2


def test_guessing_past_the_ceiling_stops_being_told_whether_it_was_right(api_client, employee):
    """The lock must withhold the answer, not only the session. Before this, guesses
    during a lock were unlimited and each response said whether that guess was
    correct, so the lock bounded nothing (D-26)."""
    lock(employee)

    # Exhaust the attempts that still earn the distinct notice.
    for _ in range(LOCKOUT_NOTICE_CEILING - LOCKOUT_THRESHOLD):
        assert login(api_client, employee.email, "wrong password").status_code == 401

    right = login(api_client, employee.email)
    wrong = login(api_client, employee.email, "wrong password")

    assert right.status_code == 401
    assert right.json() == INVALID
    assert (right.status_code, right.json()) == (wrong.status_code, wrong.json())


def test_the_notice_survives_a_mistype_by_the_locked_out_user(api_client, employee):
    """The ceiling is generous enough that a person who locks themselves out and
    then types their password correctly still learns why they cannot get in."""
    lock(employee)

    response = login(api_client, employee.email)

    assert response.status_code == 403
    assert response.json()["code"] == "account_locked"


def test_login_succeeds_once_the_lock_has_expired(api_client, employee):
    lock(employee, remaining=-datetime.timedelta(seconds=1))

    assert login(api_client, employee.email).status_code == 200


def test_a_success_clears_locked_until_as_well_as_the_counter(api_client, employee):
    """D-24 recorded the trap: a success that reset failed_attempts but left
    locked_until standing would refuse the user's next login for the rest of the
    window. D-25 closes it."""
    lock(employee, remaining=-datetime.timedelta(seconds=1))

    assert login(api_client, employee.email).status_code == 200

    employee.refresh_from_db()
    assert employee.failed_attempts == 0
    assert employee.locked_until is None
    # The proof the trap is gone: the next login is not refused.
    assert login(APIClient(), employee.email).status_code == 200


def test_an_expired_lock_does_not_re_lock_on_the_next_single_failure(api_client, employee):
    """The counter counts *consecutive* failures. Without resetting it when the
    window expires, one wrong password after a lock expired would re-lock the
    account, and "five consecutive failures" would not be true of it."""
    lock(employee, remaining=-datetime.timedelta(seconds=1))

    response = login(api_client, employee.email, "wrong password")

    assert response.status_code == 401
    employee.refresh_from_db()
    assert employee.failed_attempts == 1
    assert employee.locked_until is None


def test_five_consecutive_failures_then_403(api_client, employee):
    for attempt in range(LOCKOUT_THRESHOLD):
        response = login(api_client, employee.email, "wrong password")
        assert response.status_code == 401, attempt

    # The sixth attempt, with the right password, is refused: the account is locked.
    assert login(api_client, employee.email).status_code == 403


def test_an_administrator_account_locks_on_the_same_terms(api_client, administrator):
    # Nothing about the lock depends on the role (CLAUDE.md section 8 item 2).
    for _ in range(LOCKOUT_THRESHOLD):
        login(api_client, administrator.email, "wrong password")

    assert login(api_client, administrator.email).status_code == 403
    administrator.refresh_from_db()
    assert administrator.locked_until is not None


def test_a_lock_on_one_account_does_not_lock_another(api_client, employee, administrator):
    lock(employee)
    assert login(api_client, administrator.email).status_code == 200


def test_an_unknown_address_is_never_403(api_client, employee):
    # The 403 must not become a way to ask whether an address is registered by
    # locking it: an address with no account answers 401 whatever is submitted.
    for _ in range(LOCKOUT_THRESHOLD + 1):
        response = login(api_client, "nobody@example.com", "wrong password")
        assert response.status_code == 401


# --- GET /api/auth/me ------------------------------------------------------------------------------------


def test_me_is_401_anonymously(api_client):
    response = api_client.get(ME)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Session"


def test_me_with_a_forged_session_cookie_is_401(api_client, employee):
    api_client.cookies[settings.SESSION_COOKIE_NAME] = "not-a-session-key"
    assert api_client.get(ME).status_code == 401


def test_me_returns_the_session_user(session_client):
    response = session_client.client.get(ME)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == USER_OBJECT_KEYS
    assert body["id"] == str(session_client.user.id)
    assert body["role"] == session_client.role_name
    assert SECRET_COLUMNS.isdisjoint(body)


def test_me_refreshes_the_csrf_cookie(session_client):
    response = session_client.client.get(ME)
    assert response.cookies[settings.CSRF_COOKIE_NAME].value


def test_me_reads_the_role_from_the_database_on_every_request(employee_client, employee, administrator_role):
    # Nothing about the role is cached in the session (D-21).
    employee.role = administrator_role
    employee.save(update_fields=["role"])
    assert employee_client.get(ME).json()["role"] == ADMINISTRATOR_ROLE_NAME


def test_a_cross_site_form_post_cannot_sign_a_browser_in(api_client, employee):
    """Login CSRF (security review, Stage 2 item 7). A hidden cross-site form
    posting valid credentials would have signed the victim's browser into the
    attacker's account, and SameSite=Lax does not help because it governs when a
    cookie is sent, not when one is set. JSON-only parsing refuses the form body
    before any credential is read."""
    response = api_client.post(
        LOGIN, data={"email": employee.email, "password": PASSWORD}
    )  # urlencoded, as an HTML form sends
    assert response.status_code == 415
    assert "sessionid" not in response.cookies
