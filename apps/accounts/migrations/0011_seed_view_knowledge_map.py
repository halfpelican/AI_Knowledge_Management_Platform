"""Seed ``view_knowledge_map``, held by both roles (docs/decisions.md D-132).

FR-20's knowledge map, ``GET /api/knowledge-map``, checks this code before anything else on the
request: 401 without a session, 403 for a role that lacks it (invariant 4). The proposal names no
permission for FR-20; the lead decided on 14 November 2026 that the route sits behind a code of
its own, held by Employee and Administrator.

Both roles hold it, as both hold ``contribute_content`` (0004, D-30), so in this seed it refuses
nobody: it is the enforcement point, not a restriction that does something. The test that proves
the gate works takes the code away from a role and asserts the 403
(``apps/api/tests/test_knowledge_map.py``). What a holder is shown is still only what their own
role may read, so the code is safe for a role that does not read every source.

**Why it is numbered 0011 and depends on 0010.** It was written while FR-03's branch held 0009
and 0010 (``0009_login_attempts`` and ``0010_seed_release_account_locks``, D-130), and at first
depended on ``0008_seed_manage_tags``, as FR-03's 0009 did. FR-03 reached ``main`` first, so this
migration's dependency was re-pointed to 0010 in the merge of 15 November 2026: it had never been
pushed, and no database had applied it (D-132's dated note of that day records the check). The
accounts app keeps one leaf, and no merge migration is needed. The dependency is a property of the
node and not an operation; the operations are as first written (CLAUDE.md section 7).

Administrator's permission set stays a superset of Employee's, which is what "Administrator
generalises Employee" means here. The name is frozen here as the earlier seeds freeze theirs; a test
asserts ``VIEW_KNOWLEDGE_MAP_PERMISSION`` in ``apps.core.constants`` agrees. Idempotent and
reversible.
"""

from django.db import migrations

VIEW_KNOWLEDGE_MAP = "view_knowledge_map"

ROLE_PERMISSIONS = {
    "Administrator": (VIEW_KNOWLEDGE_MAP,),
    "Employee": (VIEW_KNOWLEDGE_MAP,),
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
        ("accounts", "0010_seed_release_account_locks"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
