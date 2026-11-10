"""Tag the Objective 02 documents from the manifest, so FR-15's browse has something to show.

D-74. Nothing writes ``ContentTags`` until FR-10's AI classification (Objective 05). Until then
browse would demonstrate empty, so this script writes the Project, Process and Topic tags that
``corpus/objective-02/manifest.json`` gives each document:

- ``Tag`` rows by name and dimension (``Tag.save`` normalises the name to lower case);
- ``ContentTag`` rows with ``applied_by="user"`` and ``confirmed=True``.

**Not through the API.** There is no tagging route, and adding one would build part of FR-10's
surface early. The ORM is the honest path for seed data, and it writes nothing a route could not
later write the same way.

**Idempotent.** Each tag and each document-tag link is ``get_or_create``d, so a second run adds
nothing and says so.

**No Department tags.** FR-15's Department dimension is the ``documents.department`` column
(D-72), the same source FR-14's filter uses.

**A value only restricted material carries is marked grown** (D-105's dated note of 10 November
2026, night: the security review of ``84b5771``). After linking, every seeded value that has links
and no link on a document or meeting EVERY role may read is marked ``grown``, the marking
``documents 0011`` applies to an existing database, so ``tag_scheme`` withholds it from an audience
that cannot read a carrier, as it always has. On the objective-02 manifest that is the Project value
``atlas``, carried by D09 and D15 alone. A value any such source carries stays vocabulary, offered to
every reader whatever happens to its links later. ``--scheme-only`` links nothing, so it marks
nothing: its values are unlinked vocabulary, as Objective 05 measured them.

**Run it before any document is classified.** Classification sees the scheme as it stands, so a
document classified before these values existed holds a seeded name it suggested in its
``proposed_topics`` (a Topic) or ``discarded_suggestions`` (a Project or Process), not as a link. A
proposal stays pending until a person confirms or rejects it or the document is classified again;
confirming it links the seeded Topic and leaves it vocabulary (``_bring_into_use``; D-105's dated
note of 10 November 2026, night).

**Which database.** It writes wherever ``DATABASE_URL`` points, and prints the name first. Since
1 November 2026 the alpha's database is ``kmp_demo_20261101``, restored from item 6's snapshot, and
that is where these tags go (D-88). It was ``kmp`` when D-74 was written. A worktree's ``.env``
may point at its own test database, so run it with ``DATABASE_URL`` set explicitly; an
environment variable takes precedence over ``.env``. Each document is found by its manifest title, and a title that matches
nothing (corpus not ingested) or more than one document stops the run before anything is written.

Usage::

    $env:DATABASE_URL = "postgres://kmp:kmp@127.0.0.1:5432/kmp_demo_20261101"
    .venv/Scripts/python.exe scripts/seed_objective02_tags.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPOSITORY_ROOT / "corpus" / "objective-02" / "manifest.json"
SEEDED_DIMENSIONS = ("Project", "Process", "Topic")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report what would be written, write nothing")
    # D-106: the Objective 05 measurement database needs the SCHEME (the Tag rows) and no
    # document links, so the twenty arrive untagged for FR-10 to classify. Needs no corpus.
    parser.add_argument("--scheme-only", action="store_true",
                        help="write the Tag rows only, no document links; the corpus need not be ingested (D-106)")
    args = parser.parse_args()

    sys.path.insert(0, str(REPOSITORY_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.db import transaction

    from django.db.models import Q

    from apps.core.constants import ROLE_NAMES, SOURCE_TYPES, TAG_APPLIED_BY_VALUES
    from apps.documents.models import ContentTag, Document, Tag, normalise_tag_name
    from apps.retrieval.scoping import scoped_documents, scoped_meetings

    document_source_type, meeting_source_type = SOURCE_TYPES
    applied_by_user = "user"
    assert applied_by_user in TAG_APPLIED_BY_VALUES

    print(f"database: {settings.DATABASES['default']['NAME']}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tagged = [item for item in manifest["items"] if item.get("tags")]

    # Resolve every document first, so a missing corpus stops the run before any write.
    documents = {}
    problems = []
    for item in ([] if args.scheme_only else tagged):
        matches = list(Document.objects.filter(title=item["title"]))
        if len(matches) != 1:
            problems.append(f"{item['id']} {item['title']!r}: {len(matches)} documents")
        else:
            documents[item["id"]] = matches[0]
    if problems:
        print("Stopped before writing anything; ingest the corpus first:\n  " + "\n  ".join(problems))
        return 1

    created_tags = created_links = existing_links = marked_grown = 0
    seeded_tag_ids = set()
    with transaction.atomic():
        for item in tagged:
            document = documents.get(item["id"])
            for dimension, values in item["tags"].items():
                if dimension not in SEEDED_DIMENSIONS:
                    raise ValueError(f"{item['id']}: {dimension!r} is not seeded (D-72, D-74)")
                for value in values:
                    tag, tag_created = Tag.objects.get_or_create(
                        tag_name=normalise_tag_name(value), dimension=dimension
                    )
                    created_tags += tag_created
                    seeded_tag_ids.add(tag.pk)
                    if args.scheme_only:
                        continue
                    _, link_created = ContentTag.objects.get_or_create(
                        tag=tag,
                        source_type=document_source_type,
                        source_id=document.id,
                        defaults={"applied_by": applied_by_user, "confirmed": True},
                    )
                    if link_created:
                        created_links += 1
                    else:
                        existing_links += 1
        if not args.scheme_only:
            marked_grown = mark_restricted_only_values_grown(
                seeded_tag_ids, ContentTag, Tag, Q, ROLE_NAMES, scoped_documents, scoped_meetings,
                document_source_type, meeting_source_type,
            )
        if args.dry_run:
            transaction.set_rollback(True)

    verb = "would create" if args.dry_run else "created"
    print(
        f"{len(tagged)} documents: {verb} {created_tags} tag(s) and {created_links} link(s); "
        f"{existing_links} link(s) already present; marked {marked_grown} value(s) grown, carried "
        f"only by material some role cannot read"
    )
    return 0


def mark_restricted_only_values_grown(tag_ids, ContentTag, Tag, Q, role_names, scoped_documents,
                                      scoped_meetings, document_source_type, meeting_source_type):
    """Mark grown each of ``tag_ids`` that has links and no link on a source every role may read,
    as ``documents 0011`` marks an existing database; returns how many were newly marked. Every link
    counts, held and removed ones included. Readability is the scoping helpers', the one FR-11
    predicate (D-53); nothing is unmarked."""

    def readable_by_every_role(scoped):
        identifiers = None
        for role_name in role_names:
            readable = set(scoped(role_name=role_name).values_list("id", flat=True))
            identifiers = readable if identifiers is None else identifiers & readable
        return identifiers or set()

    links = ContentTag.objects.filter(tag_id__in=tag_ids)
    linked = set(links.values_list("tag_id", flat=True))
    readable_by_all = set(
        links.filter(
            Q(source_type=document_source_type, source_id__in=readable_by_every_role(scoped_documents))
            | Q(source_type=meeting_source_type, source_id__in=readable_by_every_role(scoped_meetings))
        ).values_list("tag_id", flat=True)
    )
    return Tag.objects.filter(pk__in=linked - readable_by_all, grown=False).update(grown=True)


if __name__ == "__main__":
    sys.exit(main())
