# docs/decisions.md D-17: ContentChunks carry visible_to_roles in the same shape as
# Documents, so the FR-11 permission predicate and the vector live on one table and
# retrieval filters before ranking structurally. Ingestion stamps it from the
# source; a visibility change on a source re-stamps its chunks (Stage 3 and 4).
# No index yet.

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0004_file_type_four_formats'),
    ]

    operations = [
        migrations.AddField(
            model_name='contentchunk',
            name='visible_to_roles',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=32), blank=True, default=list, size=None),
        ),
    ]
