"""Seed ``manage_tags``, held by Administrator only (D-105's dated note of 10 November 2026, night;
D-119 finding 5).

FR-10's taxonomy clause, "Tags are deactivated rather than deleted where content still references
them, preserving historical classification", and its CRUD line, Tags "Delete", are performed by
``GET /api/tags`` (every tag with its count of sources) and ``DELETE /api/tags/{id}`` (deactivate a
tag in use, delete an unused one). Both check this code before anything else: 401 without a
session, 403 for a role that lacks it (invariant 4). It is a code of its own rather than
``manage_documents``, so that granting one never grants the other (D-99's reason).

Administrator only. Administrator's permission set stays a superset of Employee's, which is what
"Administrator generalises Employee" means here. The inventory is not scoped, which discloses
nothing only to a role that reads every source (D-66); the seed's test holds every holder to that.

The name is frozen here as 0003 to 0007 freeze theirs; a test asserts ``MANAGE_TAGS_PERMISSION``
in ``apps.core.constants`` agrees. Idempotent and reversible.
"""

from django.db import migrations

MANAGE_TAGS = "manage_tags"

ROLE_PERMISSIONS = {
    "Administrator": (MANAGE_TAGS,),
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
        ("accounts", "0007_seed_review_knowledge_gaps"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
