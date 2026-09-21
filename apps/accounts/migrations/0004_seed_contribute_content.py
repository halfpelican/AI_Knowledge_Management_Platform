"""Seed ``contribute_content``, held by both roles (docs/decisions.md D-30).

FR-08's section 7.2 ``validateUpload()`` opens with a contribute-permission check
returning 403, before the signature, size and title checks, and says why it is
first: it is the cheapest rejection, and the user's role may have changed during a
transfer of up to 50 MB. Without this permission that check would simply be absent,
since ``manage_roles`` is the only code seeded so far (migration 0003, D-14).

The proposal's ``knowledgeArea`` argument is dropped: schema v1 models no knowledge
area, so the check is role-level. Both roles hold the permission, so in this seed it
refuses nobody — it is the enforcement point the clause requires rather than a
restriction that does something. The test that proves the gate works builds a role
*without* it and asserts 403; the seed itself is asserted to agree with
``apps.core.constants``.

Administrator's permission set stays a superset of Employee's, which is what
"Administrator generalises Employee" means here. Idempotent and reversible.
"""

from django.db import migrations

CONTRIBUTE_CONTENT = "contribute_content"

ROLE_PERMISSIONS = {
    "Administrator": (CONTRIBUTE_CONTENT,),
    "Employee": (CONTRIBUTE_CONTENT,),
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
        ("accounts", "0003_seed_permissions"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
