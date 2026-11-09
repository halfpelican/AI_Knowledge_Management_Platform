# FR-13 step 7 phase 4 (option 3, D-103): QueryLog.retrieval_rewrite — the model's
# standalone rewrite of a follow-up, exactly as embedded in place of the composed join.
# Nullable and record-only (no serializer exposes it; its one reader outside the tests
# is scripts/conversation_http_check.py's WIRED comparison). Additive and reversible:
# AddField on a nullable column reverses to RemoveField with no data loss for the
# columns that remain.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("retrieval", "0003_answercitation_chunk_set_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="querylog",
            name="retrieval_rewrite",
            field=models.TextField(blank=True, null=True),
        ),
    ]
