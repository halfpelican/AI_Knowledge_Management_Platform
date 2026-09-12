"""Seed the permissions (FR-06) and hold them against roles (FR-05, D-14).

Only ``manage_roles`` exists so far, held by Administrator. Employee holds no
permission row yet; a test asserts Administrator's set stays a superset of
Employee's, which is what "Administrator generalises Employee" means here. The
names are frozen in the migration as 0002 freezes the role names; a test asserts
MANAGE_ROLES_PERMISSION in apps.core.constants agrees. Idempotent and reversible.
"""

from django.db import migrations

MANAGE_ROLES = "manage_roles"

ROLE_PERMISSIONS = {
    "Administrator": (MANAGE_ROLES,),
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
        ("accounts", "0002_seed_roles"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
