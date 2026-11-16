"""Accounts: Users, Roles, Permissions, RolePermissions and LoginAttempts (docs/schema-v1.md
section 1).

Permissions are held against roles, never against individual users (FR-05, FR-06).
Every table and column is named as the schema document names it; the email address
is the login identifier, unique case-insensitively (docs/decisions.md D-02).

Since D-137 a user may have a profile picture, which every signed-in user sees. The file is the
PNG ``apps/accounts/pictures.py`` re-encodes from the upload, stored beneath MEDIA_ROOT, and it
leaves only through ``GET /api/users/{id}/picture``. Nothing serves MEDIA_ROOT.
"""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    LOGIN_ATTEMPT_EVENTS,
    ROLE_NAMES,
)
from apps.core.models import NAME_MAX_LENGTH, uuid_primary_key, vocabulary_field


class Role(models.Model):
    id = uuid_primary_key("role_id")
    role_name = vocabulary_field(ROLE_NAMES, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(
        "Permission", through="RolePermission", related_name="roles", blank=True
    )

    class Meta:
        db_table = "roles"

    def __str__(self):
        return self.role_name


class Permission(models.Model):
    id = uuid_primary_key("permission_id")
    permission_name = models.CharField(max_length=NAME_MAX_LENGTH, unique=True)

    class Meta:
        db_table = "permissions"

    def __str__(self):
        return self.permission_name


class RolePermission(models.Model):
    # Composite primary key exactly as schema v1 states it (FR-06, FR-11).
    pk = models.CompositePrimaryKey("role_id", "permission_id")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="role_permissions"
    )

    class Meta:
        db_table = "role_permissions"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, *, name, role=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        if role is None:
            # "Defaults to Employee on registration" lives here so FR-01 cannot forget it.
            role = Role.objects.using(self._db).get(role_name=EMPLOYEE_ROLE_NAME)
        email = self.normalize_email(email).lower()
        user = self.model(email=email, name=name, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, *, name, **extra_fields):
        # Django admin is not used; "superuser" means the Administrator role (FR-05).
        role = Role.objects.using(self._db).get(role_name=ADMINISTRATOR_ROLE_NAME)
        return self.create_user(email, password, name=name, role=role, **extra_fields)

    def get_by_natural_key(self, username):
        # Login normalises the address the same way save() does (D-02).
        return super().get_by_natural_key(username.lower())


def picture_upload_path(instance, filename):
    """Where a profile picture is stored beneath MEDIA_ROOT (D-137): ``profile-pictures/<random>.png``.

    ``filename`` is ignored. The file is a PNG the server made, whatever the upload was called, and
    every upload gets a new random name, so a replaced picture is a different file from its
    successor, which is what lets the old one be deleted only once the new one has committed.
    """
    return f"profile-pictures/{uuid.uuid4().hex}.png"


class User(AbstractBaseUser):
    id = uuid_primary_key("user_id")
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    email = models.EmailField(unique=True)
    # AbstractBaseUser's two columns, stored under the names schema v1 gives them.
    password = models.CharField(_("password"), max_length=128, db_column="password_hash")
    last_login = models.DateTimeField(
        _("last login"), blank=True, null=True, db_column="last_login_at"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="users")
    created_at = models.DateTimeField(auto_now_add=True)
    # Written by FR-02 on failed logins, read by FR-03 (NIT3004).
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    # D-137: the profile picture, a PNG of at most PICTURE_MAX_DIMENSION a side, and when it last
    # changed, which is the user object's ?v=. Written together, by apps/accounts/pictures.py only:
    # both empty while there is no picture.
    picture = models.FileField(upload_to=picture_upload_path, blank=True)
    picture_updated_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "users"

    def save(self, *args, **kwargs):
        # Uniqueness is case-insensitive: the address is always stored in lower case.
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class LoginAttempt(models.Model):
    """One row per lockout and one per release, and nothing else (FR-03, D-130).

    FR-03: "Every lockout is recorded with the attempted email, source address, and timestamp",
    and "Every release is recorded with the Administrator who performed it, the account affected
    and the time". An ordinary sign-in, failed or successful, writes no row, so an address with
    no account is never stored.

    - **A lockout** is written by login, in the transaction that sets ``locked_until``: the
      address submitted, the source address, ``success`` false (the attempt that locked the
      account failed), the account, and the ``locked_until`` just set. An attempt during a live
      lock writes none, because it never extends the window.
    - **A release** is written by ``POST /api/users/{id}/unlock``, in the transaction that clears
      the lock: the account's address, the Administrator's source address, ``success`` null (a
      release is not an authentication attempt), the account, ``released_by``, and the
      ``locked_until`` it cleared.

    The first five columns are the proposal's field table. ``event``, ``user``, ``released_by``
    and ``locked_until`` are the four its clauses need and the table lacks
    (docs/schema-v1.md section 1). ``locked_until`` is how ``GET /api/users`` finds the lockout
    row that set the account's current lock rather than an earlier one (security finding L5).
    """

    id = uuid_primary_key("attempt_id")
    attempted_email = models.EmailField()
    # DRF's get_ident(), REMOTE_ADDR under NUM_PROXIES = 0: the key the sign-in throttle uses.
    source_ip = models.TextField(null=True, blank=True)
    success = models.BooleanField(null=True)
    attempted_at = models.DateTimeField()
    event = vocabulary_field(LOGIN_ATTEMPT_EVENTS)
    # PROTECT, as every reference to Users is (D-12): an account with a recorded lockout or
    # release cannot be deleted, and is retired as D-89 retires one instead.
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="login_attempts")
    released_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column="released_by",
        related_name="locks_released",
    )
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "login_attempts"
