"""The seventh Documents status value: "Too large to index" (Stage 4 item 12b).

Item 12a refused a document over ``MAXIMUM_CHUNKS_PER_SOURCE`` and recorded the refusal as
"Indexing failed", which in this vocabulary means "attempted, and every chunk failed to
embed". Nothing was attempted: the guard fires on the predicted chunk count, before the
first embed call. The difference is user-visible, because FR-08's interface offers
"Processing failed. Please try again" against that status and a reprocess of an over-cap
document fails identically every time — D-32's retry re-runs extraction and chunking in
full before failing at the same point, and nothing about the file has changed.

``DOCUMENT_STATUS_VALUES`` already separated *refused before attempting, on a property of
the content* ("Insufficient content") from *attempted and failed* ("Indexing failed"). An
over-cap document is the first kind and had no term, so this **completes an existing
distinction** rather than introducing one — the same argument D-28 made one state earlier,
when five values could not express a document whose chunks partly embedded. The proposal is
silent here rather than contrary: ``MAXIMUM_CHUNKS_PER_SOURCE`` was settled in the week of
2026-09-26 and the proposal predates it.

**Choices-only, and therefore mandatory rather than optional.** Django emits a migration for
a ``choices`` change and CI runs ``makemigrations --check --dry-run``, so the models and the
migrations would disagree without this file. It alters no column type and no data: the value
is added to the vocabulary, in position, beside "Insufficient content". Additive and
reversible, and no row holds a superseded value because nothing ever wrote the new one
before now.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0006_schema_v2_storage_and_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='status',
            field=models.CharField(choices=[('Processing', 'Processing'), ('Extraction failed', 'Extraction failed'), ('Insufficient content', 'Insufficient content'), ('Too large to index', 'Too large to index'), ('Indexing failed', 'Indexing failed'), ('Partially indexed', 'Partially indexed'), ('Indexed', 'Indexed')], default='Processing', max_length=32),
        ),
    ]
