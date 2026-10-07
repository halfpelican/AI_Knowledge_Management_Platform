"""Seed ``manage_documents``, held by Administrator only (docs/decisions.md D-73).

FR-15's Server-End validation: "the requesting user must hold manage_documents to delete".
``DELETE /api/documents/{id}`` checks it after resolving the document through the caller's
scope, so a document outside that scope is 404 before the permission is consulted (D-46,
D-73).

Administrator only, and no ownership rule: FR-15 makes deletion a role permission. D-66 puts
every Employee-only document in an Administrator's scope, so no document is undeletable.
Administrator's permission set stays a superset of Employee's, which is what "Administrator
generalises Employee" means here.

The name is frozen here as 0003 and 0004 freeze theirs; a test asserts
``MANAGE_DOCUMENTS_PERMISSION`` in ``apps.core.constants`` agrees. Idempotent and reversible.
"""

from django.db import migrations

MANAGE_DOCUMENTS = "manage_documents"

ROLE_PERMISSIONS = {
    "Administrator": (MANAGE_DOCUMENTS,),
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
        ("accounts", "0004_seed_contribute_content"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
