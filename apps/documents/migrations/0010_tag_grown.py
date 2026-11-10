"""documents 0010: ``Tags.grown`` (D-105's dated note of 10 November 2026, night, the lead's revision).

``11a610f`` closed an existence oracle by taking every unlinked Topic out of every scheme. That also
took out the six seeded, unlinked Topics Objective 05 was measured with, so it was narrowed the same
night: only a Topic that came into use through a name stops being vocabulary when nothing links it.
``grown`` records that. ``apps/documents/classification.py`` sets it on the Topic a person's
``apply_tag`` name form links and on the Topic ``confirm_proposed_topic`` links, created or fetched,
and nothing else sets it. ``tag_scheme`` admits a tag that every audience role reads a source of, or
one that nothing links and that is not grown.

Every existing row takes ``false``: a seeded Topic, and every Project and Process tag, is vocabulary
while unlinked, as before ``11a610f``. A Topic a person created or confirmed before this migration
reads ``false`` too; its history is recorded nowhere, so none is guessed. It is marked the next time
a person names it or confirms it.

Additive and reversible: one ``AddField``, no data migration, and the reverse drops exactly the
column. apps/documents/tests/test_migration_0010_tag_grown.py drives it both ways through the
executor.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0009_fr10_tag_corrections'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='grown',
            field=models.BooleanField(default=False),
        ),
    ]
