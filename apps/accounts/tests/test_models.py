"""Accounts models: seeded roles, permissions held against roles, the User model.

FR-01, FR-05 and docs/decisions.md D-02 and D-12.
"""

import importlib

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError

from apps.accounts.models import Permission, Role, RolePermission
from apps.core.constants import ROLE_NAMES

User = get_user_model()

pytestmark = pytest.mark.django_db

PASSWORD = "Correct-Horse-9-Battery"  # FR-01 complexity, as conftest.PASSWORD


# --- Roles -------------------------------------------------------------------------


def test_migrate_seeds_exactly_the_two_roles():
    assert list(Role.objects.order_by("role_name").values_list("role_name", flat=True)) == sorted(ROLE_NAMES)
    assert all(role.description for role in Role.objects.all())


def test_seed_migration_uses_the_role_name_constant():
    seed = importlib.import_module("apps.accounts.migrations.0002_seed_roles")
    assert tuple(role_name for role_name, _ in seed.ROLES) == ROLE_NAMES


def test_role_name_choices_come_from_the_constant():
    assert [choice for choice, _ in Role._meta.get_field("role_name").choices] == list(ROLE_NAMES)


def test_role_outside_the_vocabulary_fails_validation():
    with pytest.raises(ValidationError) as excinfo:
        Role(role_name="Contractor").full_clean()
    assert "role_name" in excinfo.value.error_dict


def test_role_name_is_unique(employee_role):
    with pytest.raises(IntegrityError), transaction.atomic():
        Role.objects.create(role_name=employee_role.role_name)


def test_deleting_a_role_in_use_is_protected(employee):
    with pytest.raises(ProtectedError):
        employee.role.delete()


# --- Permissions and RolePermissions -----------------------------------------------

# A code no migration seeds, for the model tests below. They used "manage_documents" until
# accounts 0005 seeded it (D-73), when creating it again became the very IntegrityError the
# first test asserts for a duplicate.
UNSEEDED_PERMISSION = "example_unseeded_permission"


def test_permission_name_is_unique():
    Permission.objects.create(permission_name=UNSEEDED_PERMISSION)
    with pytest.raises(IntegrityError), transaction.atomic():
        Permission.objects.create(permission_name=UNSEEDED_PERMISSION)


def test_role_permission_pair_is_the_primary_key(employee_role):
    permission = Permission.objects.create(permission_name="search_knowledge")
    RolePermission.objects.create(role=employee_role, permission=permission)
    with pytest.raises(IntegrityError), transaction.atomic():
        RolePermission.objects.create(role=employee_role, permission=permission)


def test_permissions_are_held_against_roles_through_role_permissions(employee_role, administrator_role):
    permission = Permission.objects.create(permission_name=UNSEEDED_PERMISSION)
    administrator_role.permissions.add(permission)

    # Alongside whatever migration 0003 seeded (tested in test_permissions_seed).
    assert permission in administrator_role.permissions.all()
    assert permission not in employee_role.permissions.all()
    assert RolePermission.objects.filter(role=administrator_role, permission=permission).exists()
    assert list(permission.roles.all()) == [administrator_role]


def test_role_permissions_cascade_with_their_permission(employee_role):
    permission = Permission.objects.create(permission_name="temporary")
    RolePermission.objects.create(role=employee_role, permission=permission)
    permission.delete()
    # Only this permission's row goes; the seeded ones are untouched.
    assert not RolePermission.objects.filter(permission=permission.pk).exists()
    assert employee_role.permissions.exists()


# --- Users -------------------------------------------------------------------------


def test_create_user_lower_cases_the_email_and_defaults_to_employee(employee_role):
    user = User.objects.create_user("Alice.Smith@Example.COM", PASSWORD, name="Alice Smith")
    user.refresh_from_db()
    assert user.email == "alice.smith@example.com"
    assert user.name == "Alice Smith"
    assert user.role == employee_role
    assert user.failed_attempts == 0
    assert user.locked_until is None
    assert user.last_login is None
    assert user.created_at is not None


def test_create_user_accepts_an_explicit_role(administrator_role):
    user = User.objects.create_user("bob@example.com", PASSWORD, name="Bob", role=administrator_role)
    assert user.role == administrator_role


def test_create_superuser_is_an_administrator(administrator, administrator_role):
    assert administrator.role == administrator_role
    assert administrator.email == "admin@example.com"
    assert administrator.check_password(PASSWORD)
    assert not hasattr(administrator, "is_superuser")


def test_create_user_requires_a_name():
    with pytest.raises(TypeError):
        User.objects.create_user("noname@example.com", PASSWORD)


def test_create_user_requires_an_email():
    with pytest.raises(ValueError):
        User.objects.create_user("", PASSWORD, name="Nobody")


def test_duplicate_email_differing_only_by_case_is_rejected():
    User.objects.create_user("dup@example.com", PASSWORD, name="First")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("DUP@Example.com", PASSWORD, name="Second")


def test_save_lower_cases_the_email_even_outside_the_manager(employee_role):
    user = User(email="Mixed@Example.com", name="Mixed", role=employee_role)
    user.set_password(PASSWORD)
    user.save()
    user.refresh_from_db()
    assert user.email == "mixed@example.com"


def test_password_is_hashed_and_stored_in_password_hash(employee):
    assert employee.password != PASSWORD
    assert PASSWORD not in employee.password
    assert employee.check_password(PASSWORD)
    assert not employee.check_password("wrong")
    with connection.cursor() as cursor:
        cursor.execute("SELECT password_hash FROM users WHERE user_id = %s", [employee.pk])
        (stored,) = cursor.fetchone()
    assert stored == employee.password


def test_user_created_without_a_password_cannot_log_in_with_one():
    user = User.objects.create_user("nopw@example.com", name="No Password")
    assert not user.has_usable_password()
    assert not user.check_password("")


def test_get_by_natural_key_is_case_insensitive(employee):
    assert User.objects.get_by_natural_key("Employee@Example.com") == employee


def test_email_is_the_username_field_and_name_is_required():
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == ["name"]


def test_model_has_no_username_or_django_admin_fields():
    field_names = {field.name for field in User._meta.get_fields()}
    assert {"username", "is_staff", "is_superuser", "is_active"}.isdisjoint(field_names)
    assert User.is_active is True  # AbstractBaseUser's class attribute, enough for Django and DRF


def test_deleting_a_user_who_uploaded_a_document_is_protected(document):
    with pytest.raises(ProtectedError):
        document.uploaded_by.delete()
