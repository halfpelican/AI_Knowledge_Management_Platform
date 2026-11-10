"""documents 0011: every tag today's scheme withholds from some audience is marked grown (D-105's dated
note of 10 November 2026, night: the security review of ``84b5771``).

From this migration on, ``Tags.grown`` means "not vocabulary". ``tag_scheme`` admits a tag that is not
grown into every scheme, whatever its links, and admits a grown tag only where every role in the
audience reads a source carrying it. So nothing a reader can see moves when links on material they
cannot read are made or destroyed, but for one exception D-105's note records: confirming a proposal
still pending from before its name became vocabulary. Until now the scheme also read every link of a
tag that was not grown, so a seeded value vanished from an Employee's options exactly when
Administrator-only material still carried it (the review's findings 1 to 3).

**The backfill.** Every Tag, of any dimension, that has at least one ``ContentTags`` row and no row on
a source readable by EVERY role is marked grown. Those are exactly the linked tags today's rule
withholds from some audience, so after this migration nothing becomes visible anywhere that was not.
A tag that is unlinked, or linked on a source every role reads, is left as it is; a tag already grown
stays grown.

- **Readable by role r:** the source's ``visible_to_roles`` overlaps r's effective roles, for
  documents and meetings both, mirroring ``apps/retrieval/scoping.py::_in_scope``.
- **Every link counts,** provisional and removed ones included, as ``tag_scheme`` counts them.
- **The role mapping is frozen here** as literals, the values ``ROLE_NAMES`` and ``EFFECTIVE_ROLES``
  hold in ``apps/core/constants.py`` on 10 November 2026, as accounts 0007 and 0008 freeze their
  permission names. Only historical models are used, and nothing is imported from the application.

**The reverse does nothing.** A tag marked here keeps the mark when the migration is reversed: unmarking
would put back a value an audience is not offered today, and grown is harmless under the rule that
preceded this one, where a linked tag's visibility did not consult it.
"""

from django.db import migrations
from django.db.models import Q

# apps/core/constants.py on 10 November 2026, frozen.
ROLE_NAMES = ("Employee", "Administrator")
EFFECTIVE_ROLES = {
    "Employee": ("Employee",),
    "Administrator": ("Administrator", "Employee"),
}
DOCUMENT_SOURCE_TYPE = "document"
MEETING_SOURCE_TYPE = "meeting"


def mark_withheld_tags_grown(apps, schema_editor):
    Tag = apps.get_model("documents", "Tag")
    ContentTag = apps.get_model("documents", "ContentTag")
    Document = apps.get_model("documents", "Document")
    Meeting = apps.get_model("meetings", "Meeting")

    def readable_by_every_role(model):
        """The identifiers of ``model``'s rows that every role in ROLE_NAMES may read."""
        rows = model.objects.all()
        for role_name in ROLE_NAMES:
            rows = rows.filter(visible_to_roles__overlap=list(EFFECTIVE_ROLES[role_name]))
        return rows.values("id")

    linked = set(ContentTag.objects.values_list("tag_id", flat=True))
    readable_by_all = set(
        ContentTag.objects.filter(
            Q(source_type=DOCUMENT_SOURCE_TYPE, source_id__in=readable_by_every_role(Document))
            | Q(source_type=MEETING_SOURCE_TYPE, source_id__in=readable_by_every_role(Meeting))
        ).values_list("tag_id", flat=True)
    )
    Tag.objects.filter(id__in=linked - readable_by_all).update(grown=True)


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0010_tag_grown"),
        ("meetings", "0002_visible_to_roles"),
    ]

    operations = [
        migrations.RunPython(mark_withheld_tags_grown, migrations.RunPython.noop),
    ]
