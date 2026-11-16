"""Seed ``review_knowledge_gaps``, held by Administrator only (docs/decisions.md D-107).

FR-19's knowledge-gap log is "a list, visible to Administrators". D-107 makes that a permission
code rather than a test of the role name, as every other Administrator-only route is, and this
migration seeds it the way 0006 seeds ``manage_meetings`` (D-99's pattern).

Every knowledge-gap route checks it: ``GET /api/knowledge-gaps``,
``POST /api/knowledge-gaps/cycles`` and ``PATCH /api/knowledge-gaps/{id}``, each 401 without a
session and 403 for a role that lacks it (invariant 4). The dashboard's ``knowledge_gaps`` panel is
present only for a role that holds it.

Administrator only. Administrator's permission set stays a superset of Employee's, which is what
"Administrator generalises Employee" means here.

The name is frozen here as 0003 to 0006 freeze theirs; a test asserts
``REVIEW_KNOWLEDGE_GAPS_PERMISSION`` in ``apps.core.constants`` agrees. Idempotent and reversible.
"""

from django.db import migrations

REVIEW_KNOWLEDGE_GAPS = "review_knowledge_gaps"

ROLE_PERMISSIONS = {
    "Administrator": (REVIEW_KNOWLEDGE_GAPS,),
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
        ("accounts", "0006_seed_manage_meetings"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
