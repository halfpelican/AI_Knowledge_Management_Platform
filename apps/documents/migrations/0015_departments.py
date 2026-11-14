"""documents 0015: Departments, FR-10's department scheme (D-129, the lead's decision of 13 November 2026).

The list the classifier suggests departments from, kept by an Administrator on the Tags page
(``/api/departments``). Until now ``tag_scheme`` derived the departments from the documents each
audience role can read. From here it reads this table, so the table is seeded with the departments
already in use, and nothing a classification is offered changes merely because the source moved.

**The seed.** One row per distinct non-blank ``Documents.department``:

- **The name** is the value as ``Department.save()`` normalises it on 13 November 2026, frozen below:
  stripped, internal whitespace collapsed to one space, the case kept. A historical model has no
  custom ``save()``, so the migration normalises itself. A value that normalises to nothing is blank
  and seeds nothing.
- **Deduplicated case-insensitively, as the unique constraint compares names:** ``lower()`` is
  computed by the database, the same function the constraint ``departments_unique_name_ignoring_case``
  applies, so two spellings the database folds together are always one row, whatever Python's
  ``str.lower()`` would say.
- **The spelling kept** is the one most documents use, every document counted, whatever its
  audience. A tie goes to the spelling that sorts first by code point, so the seed is deterministic.
- **Grown** (hidden) when no document carrying the kept spelling exactly is readable by EVERY role:
  documents 0011's reasoning, applied to departments. A grown department is offered only for a
  document whose whole audience reads a document with that department; one that is not grown is
  vocabulary, offered to every audience. "Carrying it" is exact equality of ``Documents.department``
  with the kept name, because that is the test ``tag_scheme`` applies to a grown department at run
  time. So a department is seeded vocabulary only where today's rule already offers it to every
  audience, and after this migration no audience is offered a department it was not offered
  before. A spelling the deduplication folds away is no longer offered at all: the list holds one
  spelling, and a department in use but not listed is not assigned.

  *Corrected on 13 November 2026, after this migration was pushed, by D-129's security review,
  finding F1, and on 14 November after the re-audit of d909537 (C6). Only this comment changed;
  the operations did not. At run time ``tag_scheme`` now offers a grown department only for an
  audience every role of which reads everything (``reads_everything``), and consults no document
  carrying it. The seed's exact-spelling test still decides ``grown`` and still errs toward
  hidden. F1 narrows what an audience with a role that does not read everything is offered (no
  grown department), and widens what an audience every role of which reads everything is offered
  (every active grown department, carried or not). So the guarantee above holds for every
  audience but that one, which reads every source, so nothing is disclosed.*

  - **Readable by role r:** the document's ``visible_to_roles`` overlaps r's effective roles,
    mirroring ``apps/retrieval/scoping.py::_in_scope``.
  - **The role mapping is frozen here** as literals, the values ``ROLE_NAMES`` and ``EFFECTIVE_ROLES``
    hold in ``apps/core/constants.py`` on 13 November 2026, as documents 0011 freezes them. Only
    historical models are used, and nothing is imported from the application.

Every seeded row is active. A fresh database has no documents when it migrates, so it seeds nothing:
there the list starts empty, and departments come from an Administrator.

**Additive and reversible.** ``CreateModel``, then the seed. The reverse does nothing to the rows and
then drops the table, which removes them. apps/documents/tests/test_migration_0015_departments.py
drives it both ways through the executor.
"""

from collections import Counter

import django.db.models.functions.text
import uuid
from django.db import migrations, models
from django.db.models import Count

# apps/core/constants.py on 13 November 2026, frozen.
ROLE_NAMES = ("Employee", "Administrator")
EFFECTIVE_ROLES = {
    "Employee": ("Employee",),
    "Administrator": ("Administrator", "Employee"),
}


def normalise(value):
    """``Department.save()``'s normalisation on 13 November 2026, frozen: stripped, internal
    whitespace collapsed to one space, the case kept."""
    return " ".join(value.split())


def seed_departments(apps, schema_editor):
    Department = apps.get_model("documents", "Department")
    Document = apps.get_model("documents", "Document")

    # Documents per spelling, after normalising: two stored values that normalise alike are one.
    documents_per_spelling = Counter()
    stored = Document.objects.exclude(department="").values("department").annotate(documents=Count("id"))
    for row in stored:
        spelling = normalise(row["department"])
        if spelling:
            documents_per_spelling[spelling] += row["documents"]
    if not documents_per_spelling:
        return

    # The database's lower() of each spelling, the function the unique constraint applies.
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT spelling, lower(spelling) FROM unnest(%s::text[]) AS spelling",
            [sorted(documents_per_spelling)],
        )
        folded = dict(cursor.fetchall())
    spellings_by_name = {}
    for spelling, key in folded.items():
        spellings_by_name.setdefault(key, []).append(spelling)

    readable_by_every_role = Document.objects.all()
    for role_name in ROLE_NAMES:
        readable_by_every_role = readable_by_every_role.filter(
            visible_to_roles__overlap=list(EFFECTIVE_ROLES[role_name])
        )

    for spellings in spellings_by_name.values():
        # Most documents first, then the first by code point.
        name = min(spellings, key=lambda spelling: (-documents_per_spelling[spelling], spelling))
        grown = not readable_by_every_role.filter(department=name).exists()
        Department.objects.create(name=name, active=True, grown=grown)


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0014_merge_fr16_and_d128"),
    ]

    operations = [
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.UUIDField(db_column="department_id", default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("active", models.BooleanField(default=True)),
                ("grown", models.BooleanField(default=False)),
            ],
            options={
                "db_table": "departments",
                "constraints": [models.UniqueConstraint(django.db.models.functions.text.Lower("name"), name="departments_unique_name_ignoring_case")],
            },
        ),
        migrations.RunPython(seed_departments, migrations.RunPython.noop),
    ]
