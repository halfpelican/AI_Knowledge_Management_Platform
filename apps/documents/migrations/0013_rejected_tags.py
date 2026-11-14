"""documents 0013: ``DocumentAnalysis.rejected_tags`` (13 November 2026; the requirements audit of D-128,
finding A5, and the lead's decision that a rejection sticks).

``reject_proposed_tag`` used to drop a proposal and record nothing, so the next classify, reprocess or
``classify_documents`` run that suggested the same value created and linked it at or above the
threshold, or proposed it again below it. FR-10's correction clause says otherwise ("any value a user
edits are retained and is not overwritten by later reprocessing", with "the machine assignment ...
retained alongside it"), as does UC-09 A3. This column records each rejected value with the machine's
confidence from the proposal, and ``apply_classification`` rule 4b skips every value it holds.

Additive and reversible: one ``AddField``, as 0009's added fields are. ``default=list`` fills the
existing rows with ``[]`` while the column is added, and no database default stays behind (there is
no ``db_default``). The reverse drops exactly the column.
apps/documents/tests/test_migration_0013_rejected_tags.py drives it both ways through the executor.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0012_proposed_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentanalysis",
            name="rejected_tags",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
