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

**Why it is numbered 0011 and depends on 0008.** 0009 and 0010 are held by FR-03's unmerged
branch (``0009_login_attempts`` and ``0010_seed_release_account_locks``, D-130), which also builds
on ``0008_seed_manage_tags``. Taking 0009 here would give two different migrations one number.
Once both branches are on ``main`` the accounts app has two leaves, and the pull request that
merges second adds a merge migration naming both; neither branch edits a migration the other has
pushed (CLAUDE.md section 7).

Administrator's permission set stays a superset of Employee's, which is what "Administrator
generalises Employee" means here. The name is frozen here as 0003 to 0008 freeze theirs; a test
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
        ("accounts", "0008_seed_manage_tags"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
