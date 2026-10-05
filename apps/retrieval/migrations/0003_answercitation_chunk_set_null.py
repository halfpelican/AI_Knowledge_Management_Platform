"""AnswerCitation.chunk becomes SET_NULL, and chunk_uuid keeps the identifier (D-67).

Stage 5 item 1a, FR-12's traceability clause: "the question, the retrieved chunk
identifiers, the answer and its verified citations are logged, so that any answer can
later be traced to the material that produced it."

Before this migration the foreign key was ``on_delete=CASCADE`` (D-12), so every operation that
deletes chunks deleted the citations of them: a reprocess, ``manage.py reindex``, and
FR-15's document deletion when it lands. ``apps/api/tests/
test_fr12_traceability_survives_reprocess.py`` records what the old file of that name
pinned. After this migration a citation outlives its chunk: ``chunk_id`` is set NULL and
``chunk_uuid`` still holds the identifier that was cited.

**No passage text is added.** FR-15 removes a deleted document's extracted content and
embeddings "so that deleted material cannot subsequently be surfaced through search", and a
snapshot would be that material surviving the delete. See D-67.

**The operations are ordered so that the reverse works as well as the forward.**

1. ``chunk`` becomes ``null=True`` with ``on_delete=SET_NULL``. In the database that is
   ``DROP NOT NULL``; the on_delete rule is Django's and has no DDL.
2. ``chunk_uuid`` is added NULLABLE, because the rows that already exist have no value for
   it until step 3.
3. ``RunPython``. Forward: copy ``chunk_id`` into ``chunk_uuid`` on every row. Every existing
   row has a ``chunk_id`` at this point, because before step 1 none could be NULL.
   Reverse: delete the citation rows whose ``chunk_id`` is NULL.
4. ``chunk_uuid`` becomes NOT NULL. Forward, this fails loudly if step 3 missed a row.

Reversed, Django runs these from step 4 back to step 1, so the rows are deleted (step 3)
before ``chunk_id`` goes back to NOT NULL (step 1).

**Why the reverse deletes rows.** Under 0002's schema ``chunk_id`` is NOT NULL and the
foreign key cascades, so a citation whose chunk had been deleted could not exist: the
cascade deleted it together with the chunk. After this migration such rows exist by design.
PostgreSQL will not restore NOT NULL while any row holds NULL, so the reverse puts the table
in the state the old schema would have left it in. It deletes exactly the rows the cascade
would have deleted, and no others: a row whose chunk still exists keeps its ``chunk_id``
untouched and loses only the ``chunk_uuid`` column, which 0002 does not have. This makes the
reverse lossy for those rows, and only for them. Their ``chunk_uuid`` is the one record of
what they cited, and it cannot be kept in a schema that has no column for it.
"""

from django.db import migrations, models
from django.db.models import F
import django.db.models.deletion


def copy_chunk_id_into_chunk_uuid(apps, schema_editor):
    """Backfill: every existing citation records the identifier it already points at."""
    AnswerCitation = apps.get_model("retrieval", "AnswerCitation")
    AnswerCitation.objects.update(chunk_uuid=F("chunk_id"))


def delete_citations_whose_chunk_is_gone(apps, schema_editor):
    """Reverse: remove the rows 0002's CASCADE would never have let exist. See the module
    docstring for why this, and only this, is deleted."""
    AnswerCitation = apps.get_model("retrieval", "AnswerCitation")
    AnswerCitation.objects.filter(chunk__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('retrieval', '0002_querylog_rejected_count'),
        # The model the foreign key points at, created in documents 0002. Already an
        # ancestor through retrieval 0001; named because the operations below reference it.
        ('documents', '0002_content_chunks'),
    ]

    operations = [
        migrations.AlterField(
            model_name='answercitation',
            name='chunk',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='citations', to='documents.contentchunk'),
        ),
        migrations.AddField(
            model_name='answercitation',
            name='chunk_uuid',
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(
            copy_chunk_id_into_chunk_uuid,
            reverse_code=delete_citations_whose_chunk_is_gone,
        ),
        migrations.AlterField(
            model_name='answercitation',
            name='chunk_uuid',
            field=models.UUIDField(),
        ),
    ]
