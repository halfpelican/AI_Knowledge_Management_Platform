"""FR-01 registration: POST /api/auth/register (docs/api-contract.md, Stage 2).

201 with the user object and the Employee role; 400 in DRF's shape for a missing
name, an invalid address or a password the validators reject; 409 for an address
already registered, compared case-insensitively (D-02).
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse

from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME

User = get_user_model()

pytestmark = pytest.mark.django_db

URL = reverse("auth-register")
USER_OBJECT_KEYS = {"id", "name", "email", "role", "created_at"}
SECRET_COLUMNS = {"password", "password_hash", "failed_attempts", "locked_until", "last_login"}

VALID = {"name": "Ada Lovelace", "email": "Ada@Example.com", "password": "correct horse battery staple"}


def register(client, **overrides):
    return client.post(URL, {**VALID, **overrides}, format="json")


# --- Happy path -------------------------------------------------------------------------------


def test_registration_creates_an_employee_and_returns_201(api_client):
    response = register(api_client)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == USER_OBJECT_KEYS
    assert body["name"] == "Ada Lovelace"
    assert body["email"] == "ada@example.com"  # lower-cased on the way in (D-02)
    assert body["role"] == EMPLOYEE_ROLE_NAME

    user = User.objects.get(pk=uuid.UUID(body["id"]))
    assert user.role.role_name == EMPLOYEE_ROLE_NAME
    assert user.check_password(VALID["password"])
    assert body["created_at"] is not None


def test_registration_stores_a_bcrypt_hash_in_password_hash(api_client):
    register(api_client)
    with connection.cursor() as cursor:
        cursor.execute("SELECT password_hash FROM users WHERE email = %s", ["ada@example.com"])
        (stored,) = cursor.fetchone()
    assert stored.startswith("bcrypt_sha256$")
    assert VALID["password"] not in stored


def test_registration_response_never_exposes_secret_columns(api_client):
    body = register(api_client).json()
    assert SECRET_COLUMNS.isdisjoint(body)


def test_registration_ignores_a_role_supplied_by_the_client(api_client):
    # Mass assignment: the role is assigned by the manager, never read from the body.
    response = register(api_client, role=ADMINISTRATOR_ROLE_NAME)
    assert response.status_code == 201
    assert response.json()["role"] == EMPLOYEE_ROLE_NAME


def test_registration_does_not_start_a_session(api_client):
    # The contract's 201 carries no session; logging in is FR-02's job.
    register(api_client)
    assert api_client.get(reverse("auth-me")).status_code == 401


def test_registration_is_open_to_an_existing_session(session_client):
    # AllowAny is the explicit opt-out (D-21); a logged-in user of either role may
    # register another account.
    assert register(session_client.client, email="new@example.com").status_code == 201


# --- 400 validation ------------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["name", "email", "password"])
def test_registration_requires_each_field(api_client, field):
    payload = {key: value for key, value in VALID.items() if key != field}
    response = api_client.post(URL, payload, format="json")
    assert response.status_code == 400
    assert list(response.json()) == [field]
    assert not User.objects.filter(email="ada@example.com").exists()


def test_registration_rejects_a_blank_name(api_client):
    response = register(api_client, name="   ")
    assert response.status_code == 400
    assert "name" in response.json()


def test_registration_rejects_an_invalid_email(api_client):
    response = register(api_client, email="not-an-address")
    assert response.status_code == 400
    assert "email" in response.json()


@pytest.mark.parametrize(
    "password",
    [
        "short",  # MinimumLengthValidator
        "12345678",  # NumericPasswordValidator
        "password",  # CommonPasswordValidator
        "ada@example.com",  # UserAttributeSimilarityValidator, email
        "AdaLovelace",  # UserAttributeSimilarityValidator, name
    ],
)
def test_registration_enforces_the_password_validators(api_client, password):
    response = register(api_client, password=password)
    assert response.status_code == 400
    assert list(response.json()) == ["password"]
    assert not User.objects.filter(email="ada@example.com").exists()


# --- 409 duplicate address (FR-01) ------------------------------------------------------------------


def test_duplicate_email_is_409(api_client, employee):
    before = User.objects.count()
    response = register(api_client, email=employee.email)
    assert response.status_code == 409
    assert response.json() == {"detail": "This email address is already registered."}
    assert User.objects.count() == before


def test_duplicate_email_is_detected_case_insensitively(api_client, employee):
    response = register(api_client, email=employee.email.upper())
    assert response.status_code == 409


# --- Security review findings (Stage 2 item 7) ------------------------------------------------


def test_an_over_long_address_is_400_not_500(api_client):
    """The column is varchar(254). Unbounded, the serializer admitted a longer
    address and the INSERT raised DataError, which is a sibling of IntegrityError
    rather than a subclass, so the 409 handler missed it and an anonymous caller
    got a 500 with a traceback under the development DEBUG setting."""
    length = User._meta.get_field("email").max_length
    local = "a" * (length - len("@example.com") + 1)
    response = register(api_client, email=f"{local}@example.com")
    assert response.status_code == 400
    assert "email" in response.json()
    assert not User.objects.filter(name=VALID["name"]).exists()


def test_an_address_of_exactly_the_column_length_is_accepted(api_client):
    length = User._meta.get_field("email").max_length
    local = "a" * (length - len("@example.com"))
    address = f"{local}@example.com"
    assert len(address) == length
    assert register(api_client, email=address).status_code == 201


def test_a_cross_site_form_post_cannot_register(api_client):
    """DRF exempts its views from CsrfViewMiddleware and only enforces CSRF once a
    session user exists, so an anonymous POST is never checked. JSON-only parsing
    is what closes it: a cross-site HTML form can only send form or multipart
    bodies, and a cross-site fetch sending JSON is held by the preflight."""
    response = api_client.post(URL, data=VALID)  # urlencoded, as an HTML form sends
    assert response.status_code == 415
    assert not User.objects.filter(email=VALID["email"].lower()).exists()
