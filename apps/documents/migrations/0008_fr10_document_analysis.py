"""Migration v2 for FR-10 (docs/decisions.md D-105): DocumentAnalysis, and two columns on ContentTags.

``DocumentAnalysis`` leaves docs/schema-v1.md section 2's deferred table for section 1, built when
FR-10 was, as that section said it would be. One row per document (a one-to-one on ``doc_id``),
holding the machine's type and department with a confidence each, the effective type, an outcome
per assignment from ASSIGNMENT_OUTCOMES, ``user_edited``, the two JSON lists of out-of-scheme
suggestions, and the run's model, truncation flag and time. The effective department is NOT here:
it is ``documents.department``, the one source FR-14 and FR-15 read (D-72).

``ContentTags`` gains ``confidence`` (decimal(4,3), null for a link a person applied) and
``provisional`` (an AI link held below CLASSIFICATION_CONFIDENCE_THRESHOLD, not yet a tag of its
document). Both have defaults the existing rows take — NULL and false — so every link seeded under
D-74 reads as a confirmed, non-provisional tag, which is what it is.

Additive and reversible: three operations, no data migration, and the reverse drops exactly what
the forward added. apps/documents/tests/test_migration_0008_document_analysis.py drives it both
ways through the executor.
"""

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0007_document_status_too_large_to_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='contenttag',
            name='confidence',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=4, null=True),
        ),
        migrations.AddField(
            model_name='contenttag',
            name='provisional',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='DocumentAnalysis',
            fields=[
                ('id', models.UUIDField(db_column='analysis_id', default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('machine_doc_type', models.CharField(blank=True, choices=[('Policy', 'Policy'), ('Procedure', 'Procedure'), ('Report', 'Report'), ('Meeting Paper', 'Meeting Paper')], max_length=32, null=True)),
                ('machine_doc_type_confidence', models.DecimalField(blank=True, decimal_places=3, max_digits=4, null=True)),
                ('machine_department', models.CharField(blank=True, max_length=255)),
                ('machine_department_confidence', models.DecimalField(blank=True, decimal_places=3, max_digits=4, null=True)),
                ('doc_type', models.CharField(blank=True, choices=[('Policy', 'Policy'), ('Procedure', 'Procedure'), ('Report', 'Report'), ('Meeting Paper', 'Meeting Paper')], max_length=32, null=True)),
                ('doc_type_outcome', models.CharField(blank=True, choices=[('applied', 'applied'), ('provisional', 'provisional'), ('discarded', 'discarded'), ('confirmed', 'confirmed')], max_length=32, null=True)),
                ('department_outcome', models.CharField(blank=True, choices=[('applied', 'applied'), ('provisional', 'provisional'), ('discarded', 'discarded'), ('confirmed', 'confirmed')], max_length=32, null=True)),
                ('user_edited', models.BooleanField(default=False)),
                ('proposed_topics', models.JSONField(blank=True, default=list)),
                ('discarded_suggestions', models.JSONField(blank=True, default=list)),
                ('model', models.CharField(blank=True, max_length=255)),
                ('input_truncated', models.BooleanField(default=False)),
                ('classified_at', models.DateTimeField()),
                ('document', models.OneToOneField(db_column='doc_id', on_delete=django.db.models.deletion.CASCADE, related_name='analysis', to='documents.document')),
            ],
            options={
                'db_table': 'document_analysis',
            },
        ),
    ]
