"""Seed ``release_account_locks``, held by Administrator only (FR-03, D-130).

FR-03: "An Administrator viewing a locked account can release the lock immediately, so a
locked-out user has a route forward", and "Only a user holding the Administrator role may release
a lock." ``POST /api/users/{id}/unlock`` performs the release, and ``GET /api/users`` shows each
live lock to a holder of this code. The release route checks it before anything else: 401 without
a session, 403 for a role that lacks it (invariant 4), so an Employee cannot probe user ids. It is
a code of its own rather than ``manage_roles``, so that granting one never grants the other (D-99's
reason).

Administrator only. Administrator's permission set stays a superset of Employee's, which is what
"Administrator generalises Employee" means here.

The name is frozen here as 0003 to 0008 freeze theirs, and must agree with
``RELEASE_ACCOUNT_LOCKS_PERMISSION`` in ``apps.core.constants``. Idempotent and reversible.
"""

from django.db import migrations

RELEASE_ACCOUNT_LOCKS = "release_account_locks"

ROLE_PERMISSIONS = {
    "Administrator": (RELEASE_ACCOUNT_LOCKS,),
    "Employee": (),
}


def seed_permissions(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")
    for role_name, permission_names in ROLE_PERMISSIONS.items():
        role = Role.objects.get(role_name=role_name)
        for permission_name in permission_names:
            permission, _ = Permission.objects.get_or_create(permission_name=permission_name)
            RolePermission.objects.get_or_create(role=role, permission=permission)


def unseed_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    names = {name for names in ROLE_PERMISSIONS.values() for name in names}
    # role_permissions rows cascade with their permission (D-12).
    Permission.objects.filter(permission_name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_login_attempts"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
