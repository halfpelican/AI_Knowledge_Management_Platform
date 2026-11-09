"""``manage.py aggregate_knowledge_gaps``: FR-19's scheduled cycle (D-107).

The command runs one ``run_cycle`` with no ``triggered_by``, prints the database name before
anything else and the cycle's counts after, and turns a provider outage into exit status 1 with
nothing changed. The suite's stub embeds; the outage is a service that refuses every call. The
command is called in process, never as a subprocess, so it reaches neither the developer's
database nor a live provider.
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone

import apps.ai
from apps.ai.base import ProviderUnavailable
from apps.core.constants import NO_RELEVANT_PASSAGE
from apps.retrieval.models import KnowledgeGap, KnowledgeGapCycle, QueryLog, SearchLog

pytestmark = pytest.mark.django_db


def unanswered(user, question, *, hours_ago):
    row = QueryLog.objects.create(user=user, question=question, answered=False, no_answer_reason=NO_RELEVANT_PASSAGE)
    QueryLog.objects.filter(pk=row.pk).update(answered_at=timezone.now() - timedelta(hours=hours_ago))


def zero_result(user, term, *, hours_ago):
    row = SearchLog.objects.create(user=user, query_text=term, result_count=0)
    SearchLog.objects.filter(pk=row.pk).update(searched_at=timezone.now() - timedelta(hours=hours_ago))


def run():
    out = StringIO()
    call_command("aggregate_knowledge_gaps", stdout=out)
    return out.getvalue().splitlines()


def test_it_prints_the_database_first_then_runs_one_cycle_and_prints_its_counts(employee):
    unanswered(employee, "Where do I find the parking permit form?", hours_ago=3)
    unanswered(employee, "Who approves the new seating plan?", hours_ago=2)
    zero_result(employee, "seating plan approval", hours_ago=1)

    lines = run()

    assert lines[0] == f"database: {connection.settings_dict['NAME']}"
    cycle = KnowledgeGapCycle.objects.get()
    assert cycle.triggered_by is None
    assert lines[1].startswith(f"cycle {cycle.pk}: started ")
    assert lines[2] == (
        "queries_considered=2 searches_considered=1 entries_created=3 entries_updated=0"
    )
    assert KnowledgeGap.objects.count() == 3


def test_a_second_run_takes_nothing_twice(employee):
    unanswered(employee, "Where do I find the parking permit form?", hours_ago=1)
    run()
    lines = run()
    assert lines[2] == "queries_considered=0 searches_considered=0 entries_created=0 entries_updated=0"
    assert KnowledgeGapCycle.objects.count() == 2
    assert KnowledgeGap.objects.get().occurrence_count == 1


class DownService:
    def embed(self, texts):
        raise ProviderUnavailable("connection refused (designed)")

    def generate_statements(self, question, passages):
        raise AssertionError("not called")

    def health(self):
        raise AssertionError("not called")


def test_a_provider_outage_is_exit_status_1_with_the_cause_and_nothing_changed(employee, monkeypatch):
    unanswered(employee, "Where do I find the parking permit form?", hours_ago=1)
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: DownService())
    out = StringIO()

    with pytest.raises(CommandError) as raised:
        call_command("aggregate_knowledge_gaps", stdout=out)

    # Django prints a CommandError to stderr and exits with its returncode.
    assert raised.value.returncode == 1
    assert "connection refused (designed)" in str(raised.value)
    assert "nothing was changed" in str(raised.value)
    # The database line came first, before the cycle failed.
    assert out.getvalue().splitlines() == [f"database: {connection.settings_dict['NAME']}"]
    assert KnowledgeGapCycle.objects.count() == 0
    assert KnowledgeGap.objects.count() == 0
