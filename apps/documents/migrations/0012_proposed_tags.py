"""documents 0012: ``DocumentAnalysis.proposed_topics`` becomes ``proposed_tags`` (D-128, 12 November 2026).

D-128 holds a value outside the scheme for a person's confirmation in Project and Process as well as
in Topic, when the classifier's confidence in it is below the threshold, so the one list of held
values names its dimension: ``{"dimension": "Project"|"Process"|"Topic", "value", "confidence"}``.

**The column keeps its name.** CLAUDE.md section 7 requires additive migrations, and no migration in
this repository renames or removes a column. So the operations are, in this order:

1. ``AlterField`` gives the field ``db_column="proposed_topics"`` while it is still called
   ``proposed_topics``: the column it names is the one it already has, so no SQL is emitted;
2. ``RenameField`` to ``proposed_tags``: the explicit ``db_column`` keeps the column where it is, so
   again no SQL is emitted (``manage.py sqlmigrate documents 0012`` shows no ALTER);
3. ``RunPython``, on the data.

**Forward** stamps ``"dimension": "Topic"`` on every existing entry: until now only a Topic could be
proposed. **Reverse** strips ``dimension`` from each Topic entry and moves each Project or Process
entry into ``discarded_suggestions`` as ``{"dimension", "value", "confidence"}``, which is exactly
what the rule before D-128 recorded for such a value ("discarded"), so the reverse loses nothing in
the old schema's terms. An entry that is not an object is left where it is, both ways.

Only historical models are used, and nothing is imported from the application.
"""

from django.db import migrations, models

TOPIC_DIMENSION = "Topic"  # apps/core/constants.py on 12 November 2026, frozen


def stamp_topic_dimension(apps, schema_editor):
    DocumentAnalysis = apps.get_model("documents", "DocumentAnalysis")
    for analysis in DocumentAnalysis.objects.exclude(proposed_tags=[]).iterator():
        entries = analysis.proposed_tags or []
        stamped = [
            {"dimension": TOPIC_DIMENSION, **entry} if isinstance(entry, dict) else entry
            for entry in entries
        ]
        if stamped != entries:
            analysis.proposed_tags = stamped
            analysis.save(update_fields=["proposed_tags"])


def unstamp_topic_dimension(apps, schema_editor):
    DocumentAnalysis = apps.get_model("documents", "DocumentAnalysis")
    for analysis in DocumentAnalysis.objects.exclude(proposed_tags=[]).iterator():
        topics, discarded = [], list(analysis.discarded_suggestions or [])
        for entry in analysis.proposed_tags or []:
            if not isinstance(entry, dict):
                topics.append(entry)
                continue
            dimension = entry.get("dimension", TOPIC_DIMENSION)
            if dimension == TOPIC_DIMENSION:
                topics.append({key: value for key, value in entry.items() if key != "dimension"})
            else:
                discarded.append({
                    "dimension": dimension,
                    "value": entry.get("value"),
                    "confidence": entry.get("confidence"),
                })
        analysis.proposed_tags = topics
        analysis.discarded_suggestions = discarded
        analysis.save(update_fields=["proposed_tags", "discarded_suggestions"])


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0011_grown_marks_withheld_tags"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentanalysis",
            name="proposed_topics",
            field=models.JSONField(blank=True, db_column="proposed_topics", default=list),
        ),
        migrations.RenameField(
            model_name="documentanalysis",
            old_name="proposed_topics",
            new_name="proposed_tags",
        ),
        migrations.RunPython(stamp_topic_dimension, unstamp_topic_dimension),
    ]
