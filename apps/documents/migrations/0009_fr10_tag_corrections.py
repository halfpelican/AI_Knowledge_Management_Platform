"""FR-10's tag corrections (D-105's dated note of 10 November 2026, night; D-119 findings 3 and 10).

``ContentTags.removed``: a person removed an AI link. The row stays, with the confidence and the
provisional flag the machine gave it, so FR-10's "the machine assignment is retained alongside" a
person's decision holds for tags as it already did for the type and the department, and a later
classify or reprocess does not link the tag again. No read lists a removed link. Every existing row
takes ``false``: nothing before this migration kept a removal, because ``reject_tag`` deleted the
link.

``DocumentAnalysis.department_applied_by``: who supplied the department the document carries,
``"user"``, ``"ai"`` or null, in the tags' provenance vocabulary (TAG_APPLIED_BY_VALUES). The
department outcome "applied" was recorded both when a run wrote its suggestion into a blank
department and when the suggestion merely equalled the department the uploader typed, and the
interface labelled both "Suggested by AI". Existing rows take null, which the interface reads as
it read every row before: their history is not recorded anywhere, so none is guessed here. A
row's next classification run or confirmation sets it.

Additive and reversible: two ``AddField`` operations, no data migration, and the reverse drops
exactly what the forward added. apps/documents/tests/test_migration_0009_tag_corrections.py drives
it both ways through the executor.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0008_fr10_document_analysis'),
    ]

    operations = [
        migrations.AddField(
            model_name='contenttag',
            name='removed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='documentanalysis',
            name='department_applied_by',
            field=models.CharField(blank=True, choices=[('ai', 'ai'), ('user', 'user')], max_length=32, null=True),
        ),
    ]
