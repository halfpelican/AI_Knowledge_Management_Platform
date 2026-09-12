"""Accounts: the User model shell.

This is the settled slice of the proposal's Users table (docs/decisions.md D-02):
the email address is the login identifier, unique case-insensitively, and there is
no username column. Every other column (role, name, ...) comes from the proposal's
table definition and is added by a later migration, not here.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

from apps.core.models import UUIDPrimaryKeyMixin


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        # Django admin is not used and there is no is_staff or is_superuser flag.
        # Roles arrive with the proposal's Roles table (Stage 1 item 4, FR-05).
        return self.create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username):
        # Login normalises the address the same way save() does (D-02).
        return super().get_by_natural_key(username.lower())


class User(UUIDPrimaryKeyMixin, AbstractBaseUser):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        # Uniqueness is case-insensitive: the address is always stored in lower case.
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
