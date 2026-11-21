"""documents 0016: FR-10's document summary on ``DocumentAnalysis`` (D-139, 21 November 2026).

FR-10's front-end clause: "Each document displays a short summary and a list of key points, shown
beneath the title in search results". D-104 deferred it and D-139 reverses that. Five columns hold
it:

- ``summary``: the machine's short paragraph, ``""`` when there is none;
- ``key_points``: a list of strings, ``[]`` when there are none;
- ``summary_truncated``: the summary covers only the first sections of a long document;
- ``summary_model`` and ``summarised_at``: the chat model that wrote it and when, apart from
  ``model`` and ``classified_at`` because a summary can be written without applying a
  classification.

Additive and reversible: five ``AddField`` operations, as 0009's and 0013's are. Each field's own
default fills the existing rows while its column is added (``""``, ``[]``, false, ``""`` and null),
and no database default stays behind (there is no ``db_default``). So a document classified before
0016 has an analysis with no summary until a run or the backfill writes one. The reverse drops
exactly the five columns. apps/documents/tests/test_migration_0016_document_summary.py drives it
both ways through the executor.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0015_departments"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentanalysis",
            name="summary",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="documentanalysis",
            name="key_points",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="documentanalysis",
            name="summary_truncated",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documentanalysis",
            name="summary_model",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="documentanalysis",
            name="summarised_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
