"""``python manage.py aggregate_knowledge_gaps``: run one FR-19 aggregation cycle (D-107).

FR-19 aggregates unanswered questions and zero-result searches "on a scheduled basis". This command
is that basis: a scheduler runs it (Task Scheduler on the laptop), and each run is one cycle,
``apps.retrieval.gaps.run_cycle``, in one transaction. ``POST /api/knowledge-gaps/cycles`` runs the
same function for the demonstration.

**The database name is printed first**, before anything is read or written, so a run against the
wrong database is visible in its own output, as the measurement scripts do it (D-84). Unlike them
this command refuses no database: it is the production trigger, and the production database is
the one it is for.

**A provider outage is exit status 1.** ``run_cycle`` rolls back and lets ``ProviderUnavailable``
out; this raises ``CommandError`` with the cause, which Django prints to stderr and turns into exit
status 1. Nothing was changed, so the scheduler's next run simply tries again. The output names no
row that was left out, as nothing else does (D-107, D-108).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.ai.base import ProviderUnavailable
from apps.retrieval.gaps import run_cycle


class Command(BaseCommand):
    help = "Run one knowledge-gap aggregation cycle (FR-19, D-107) and print its counts."

    def handle(self, *args, **options):
        self.stdout.write(f"database: {connection.settings_dict['NAME']}")
        try:
            cycle = run_cycle()
        except ProviderUnavailable as exc:
            raise CommandError(
                f"The AI provider is unavailable, so no cycle ran and nothing was changed: {exc}"
            ) from exc
        self.stdout.write(
            f"cycle {cycle.pk}: started {cycle.started_at.isoformat()}, "
            f"finished {cycle.finished_at.isoformat()}"
        )
        self.stdout.write(
            f"queries_considered={cycle.queries_considered} "
            f"searches_considered={cycle.searches_considered} "
            f"entries_created={cycle.entries_created} "
            f"entries_updated={cycle.entries_updated}"
        )
