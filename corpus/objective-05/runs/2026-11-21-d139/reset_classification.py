"""Objective 05's check on D-139's prompt (21 November 2026): clear the classification rows already there.

A copy of corpus/objective-05/runs/2026-11-10-anthropic/reset_classification.py with the database
name changed, and nothing else (reset_classification.diff beside it). The check's database is a copy
of the anthropic snapshot, whose twenty documents were classified at upload, before any tag or
department existed. Those rows are cleared before the measured run, as each repeated draw's were
on 11 November (corpus/objective-05/runs/2026-11-10/rerun/rerun.md):

- the DocumentAnalysis rows, one per classified document;
- the AI tag links on documents (ContentTag, applied_by "ai").

Their counts are checked first against the counts the caller gives, read from this script's own
first line on a run that refuses. Tag rows are kept. A person-applied link would be kept too.
Everything is deleted in one transaction.

It refuses unless the database is kmp_obj05_d139_20261121 and both counts match.

Usage, in PowerShell, with the run's DATABASE_URL set::

    & $py corpus\\objective-05\\runs\\2026-11-21-d139\\reset_classification.py --expect-analyses 20 --expect-ai-links 0
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]  # corpus/objective-05/runs/<this folder>/<this file>
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

EXPECTED_DATABASE = "kmp_obj05_d139_20261121"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--expect-analyses", type=int, required=True)
    parser.add_argument("--expect-ai-links", type=int, required=True)
    arguments = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.db import transaction

    from apps.core.constants import SOURCE_TYPES
    from apps.documents.models import ContentTag, DocumentAnalysis, Tag

    database = str(settings.DATABASES["default"]["NAME"])
    if database != EXPECTED_DATABASE:
        print(f"REFUSED: connected to {database!r}, not {EXPECTED_DATABASE!r}. Nothing was deleted.")
        return 2
    analyses = DocumentAnalysis.objects.all()
    ai_links = ContentTag.objects.filter(source_type=SOURCE_TYPES[0], applied_by="ai")
    other_links = ContentTag.objects.exclude(pk__in=ai_links.values("pk"))
    counts = {"analyses": analyses.count(), "ai_links": ai_links.count(), "other_links": other_links.count(),
              "tags": Tag.objects.count()}
    print(f"database {database}: {counts}")
    if counts["analyses"] != arguments.expect_analyses or counts["ai_links"] != arguments.expect_ai_links:
        print(f"REFUSED: expected {arguments.expect_analyses} analyses and {arguments.expect_ai_links} AI links "
              "from the previous draw's record. Nothing was deleted.")
        return 2
    with transaction.atomic():
        deleted_links, _ = ai_links.delete()
        deleted_analyses, _ = analyses.delete()
    after = {"analyses": DocumentAnalysis.objects.count(),
             "ai_links": ContentTag.objects.filter(source_type=SOURCE_TYPES[0], applied_by="ai").count(),
             "other_links": ContentTag.objects.count(), "tags": Tag.objects.count()}
    print(f"deleted {deleted_analyses} analysis row(s) and {deleted_links} AI link row(s); after: {after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
