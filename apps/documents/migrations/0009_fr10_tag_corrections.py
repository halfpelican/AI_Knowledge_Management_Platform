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

Additive and reversible: two ``AddField`` operations and no data migration forwards. **The reverse
deletes every link marked removed** before it drops the column (the security review of ``84b5771``,
its finding 5; D-105's dated note of 10 November 2026, night). Kept rows with the column gone would
read as live tags to the code before 0009, which knew no removal: under it a removal deleted the
link, and the reverse makes the database say what that code expects. Live links are untouched.
apps/documents/tests/test_migration_0009_tag_corrections.py drives it both ways through the
executor.

**Edited after it was written, before it was pushed.** The ``RunPython`` was appended on 10 November
2026 (night), by the decision recorded in D-105's dated note. Its forward does nothing, so a database
that applied this migration before the edit is in the state one applying it now reaches, and
reversing either runs the reverse written here.
"""

from django.db import migrations, models


def delete_removed_links(apps, schema_editor):
    """The reverse: a removed link is deleted, as a removal deleted it before this migration."""
    apps.get_model("documents", "ContentTag").objects.filter(removed=True).delete()


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
        # After the AddField of ``removed``, so that reversing runs it while the column still exists.
        migrations.RunPython(migrations.RunPython.noop, reverse_code=delete_removed_links),
    ]
