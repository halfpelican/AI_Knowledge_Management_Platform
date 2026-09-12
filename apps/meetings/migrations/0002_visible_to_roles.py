# docs/decisions.md D-16: Meetings carry visible_to_roles, mirroring Documents
# exactly, as the FR-11 permission filter for meeting content. Meetings are not
# scoped by attendance; MeetingAttendees stays a participation record only.

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('meetings', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='meeting',
            name='visible_to_roles',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=32), blank=True, default=list, size=None),
        ),
    ]
