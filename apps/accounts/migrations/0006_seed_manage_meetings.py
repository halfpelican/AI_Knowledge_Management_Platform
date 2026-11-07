"""Seed ``manage_meetings``, held by Administrator only (docs/decisions.md D-99).

Meeting deletion is not in the proposal. FR-09 gives Meetings Create, Read and Update status
only, and FR-15's permissioned deletion covers documents. The lead asked for it on 7 November
2026 and chose a permission of its own, mirroring D-73's ``manage_documents`` (0005) rather than
reusing it, so that granting one never grants the other.

``DELETE /api/meetings/{id}`` checks it after resolving the meeting through the caller's scope,
so a meeting outside that scope is 404 before the permission is consulted (D-46, D-73, D-99).

Administrator only, and no ownership rule. D-66 puts every Employee-only meeting in an
Administrator's scope, so no meeting is undeletable. Administrator's permission set stays a
superset of Employee's, which is what "Administrator generalises Employee" means here.

The name is frozen here as 0003 to 0005 freeze theirs; a test asserts
``MANAGE_MEETINGS_PERMISSION`` in ``apps.core.constants`` agrees. Idempotent and reversible.
"""

from django.db import migrations

MANAGE_MEETINGS = "manage_meetings"

ROLE_PERMISSIONS = {
    "Administrator": (MANAGE_MEETINGS,),
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
        ("accounts", "0005_seed_manage_documents"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
