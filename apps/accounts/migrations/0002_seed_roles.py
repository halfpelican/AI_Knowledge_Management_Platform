"""Seed the two roles (FR-05) so a fresh database is usable and create_user works.

The names are frozen here, as Django freezes choices into migrations; they mirror
ROLE_NAMES in apps.core.constants and a test asserts the two agree. The proposal
gives only an example description, so these are the project's own wording.
"""

from django.db import migrations

ROLES = (
    ("Employee", "Can view and search the knowledge base"),
    ("Administrator", "Can manage documents, users and roles"),
)


def seed_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for role_name, description in ROLES:
        Role.objects.get_or_create(role_name=role_name, defaults={"description": description})


def unseed_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(role_name__in=[role_name for role_name, _ in ROLES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_roles, unseed_roles),
    ]
