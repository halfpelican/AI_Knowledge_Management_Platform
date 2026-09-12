"""Accounts: Users, Roles, Permissions and RolePermissions (docs/schema-v1.md section 1).

Permissions are held against roles, never against individual users (FR-05, FR-06).
Every table and column is named as the schema document names it; the email address
is the login identifier, unique case-insensitively (docs/decisions.md D-02).
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, ROLE_NAMES
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
