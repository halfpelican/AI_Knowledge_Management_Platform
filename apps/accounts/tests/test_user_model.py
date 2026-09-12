"""The User model shell (docs/decisions.md D-02): email login, no username column."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

User = get_user_model()

pytestmark = pytest.mark.django_db

PASSWORD = "correct horse battery staple"


def test_create_user_lower_cases_and_stores_the_email():
    user = User.objects.create_user("Alice.Smith@Example.COM", PASSWORD)
    user.refresh_from_db()
    assert user.email == "alice.smith@example.com"
    assert user.is_active is True


def test_primary_key_is_a_uuid():
    user = User.objects.create_user("uuid@example.com", PASSWORD)
    assert isinstance(user.pk, uuid.UUID)


def test_duplicate_email_differing_only_by_case_is_rejected():
    User.objects.create_user("dup@example.com", PASSWORD)
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("DUP@Example.com", PASSWORD)


def test_save_lower_cases_the_email_even_outside_the_manager():
    user = User(email="Mixed@Example.com")
    user.set_password(PASSWORD)
    user.save()
    user.refresh_from_db()
    assert user.email == "mixed@example.com"


def test_password_is_hashed_and_check_password_works():
    user = User.objects.create_user("hash@example.com", PASSWORD)
    assert user.password != PASSWORD
    assert PASSWORD not in user.password
    assert user.check_password(PASSWORD)
    assert not user.check_password("wrong")


def test_user_created_without_a_password_cannot_log_in_with_one():
    user = User.objects.create_user("nopw@example.com")
    assert not user.has_usable_password()
    assert not user.check_password("")


def test_create_user_requires_an_email():
    with pytest.raises(ValueError):
        User.objects.create_user("", PASSWORD)


def test_model_has_no_username_column():
    field_names = {field.name for field in User._meta.get_fields()}
    assert "username" not in field_names
    assert "email" in field_names


def test_model_has_no_django_admin_flags():
    # Roles come from the proposal's Roles table (FR-05), not from is_staff/is_superuser.
    field_names = {field.name for field in User._meta.get_fields()}
    assert "is_staff" not in field_names
    assert "is_superuser" not in field_names


def test_email_is_the_username_field():
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []


def test_get_by_natural_key_is_case_insensitive():
    created = User.objects.create_user("nk@example.com", PASSWORD)
    assert User.objects.get_by_natural_key("NK@Example.com") == created


def test_create_superuser_is_just_create_user():
    user = User.objects.create_superuser("Root@Example.com", PASSWORD)
    assert user.email == "root@example.com"
    assert user.check_password(PASSWORD)
    assert not hasattr(user, "is_superuser")
