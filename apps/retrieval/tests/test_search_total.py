"""``search_total``: FR-12's keyword-search count, with no SearchLog row (FR-19, D-108).

The knowledge-gap cycle recounts a zero-result search as the Administrator to decide whether the
asker's role withheld what exists. That recount must be the SAME number ``search`` reports, from
the same code, and it must leave no trace in ``search_logs``, because it is not a search anybody
made.

The equality is asserted against ``search`` itself, term by term and role by role, over a store
built so that every way a source can match is present: a body match, a title-only match, a meeting,
a document with two matching chunks (one result, not two), a phrase that wraps a line (D-71), and
a source each role may not read.
"""

from datetime import date

import pytest
from django.conf import settings

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, SOURCE_TYPES
from apps.documents.models import ContentChunk, Document
from apps.meetings.models import Meeting
from apps.retrieval.models import SearchLog
from apps.retrieval.search import (
    SearchQueryContainsNullCharacter,
    SearchQueryTooShort,
    search,
    search_total,
)
from apps.retrieval.tests.scopes import unreadable_scope

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]


def chunk(source_type, source_id, index, text, roles):
    return ContentChunk.objects.create(
        source_type=source_type,
        source_id=source_id,
        chunk_index=index,
        chunk_text=text,
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )


def document(user, title, roles, *texts):
    row = Document.objects.create(title=title, file_type="pdf", uploaded_by=user, visible_to_roles=roles)
    for index, text in enumerate(texts):
        chunk(DOCUMENT_SOURCE_TYPE, row.id, index, text, roles)
    return row


def meeting(title, roles, *texts):
    row = Meeting.objects.create(
        title=title, meeting_date=date(2026, 9, 1), transcript_text=" ".join(texts) or "-",
        visible_to_roles=roles,
    )
    for index, text in enumerate(texts):
        chunk(MEETING_SOURCE_TYPE, row.id, index, text, roles)
    return row


@pytest.fixture
def store(employee):
    document(employee, "Leave policy", BOTH_ROLES, "Annual leave accrues monthly.", "Annual leave carries over.")
    document(employee, "Annual leave calendar", BOTH_ROLES, "Public holidays are listed here.")
    document(employee, "Directors' terms", [ADMINISTRATOR_ROLE_NAME], "Directors take annual leave by agreement.")
    document(employee, "Wrapped phrase", BOTH_ROLES, "Staff accrue annual\nleave at the standard rate.")
    meeting("Leave planning", BOTH_ROLES, "We discussed annual leave for December.")
    meeting("Board in camera", [ADMINISTRATOR_ROLE_NAME], "Annual leave for the chair.")


@pytest.mark.parametrize("term", ["annual leave", "ANNUAL LEAVE", "annual  leave", "calendar", "chair", "zebra crossing"])
def test_the_total_is_the_number_search_reports_for_each_role(store, employee, administrator, term):
    for user, role_name in ((employee, EMPLOYEE_ROLE_NAME), (administrator, ADMINISTRATOR_ROLE_NAME)):
        assert search_total(role_name=role_name, query_text=term) == search(query_text=term, user=user).total_count


def test_the_roles_get_different_totals_for_the_same_term(store):
    # Employee: the leave policy (one result for two matching chunks), the calendar (title only),
    # the wrapped phrase (D-71) and the planning meeting. The Administrator adds the directors'
    # terms and the in-camera meeting.
    assert search_total(role_name=EMPLOYEE_ROLE_NAME, query_text="annual leave") == 4
    assert search_total(role_name=ADMINISTRATOR_ROLE_NAME, query_text="annual leave") == 6
    assert search_total(role_name=EMPLOYEE_ROLE_NAME, query_text="chair") == 0
    assert search_total(role_name=ADMINISTRATOR_ROLE_NAME, query_text="chair") == 1


def test_a_source_each_role_may_not_read_is_not_counted(session_client):
    """From both roles; for the Administrator the unreadable row is stamped ``[]`` (D-66)."""
    document(session_client.user, "Sealed report", unreadable_scope(session_client.role_name), "sealed figures")
    assert search_total(role_name=session_client.role_name, query_text="sealed figures") == 0


def test_an_unknown_role_counts_nothing(store):
    assert search_total(role_name="Contractor", query_text="annual leave") == 0


def test_no_search_log_row_is_written(store):
    search_total(role_name=ADMINISTRATOR_ROLE_NAME, query_text="annual leave")
    search_total(role_name=EMPLOYEE_ROLE_NAME, query_text="zebra crossing")
    assert SearchLog.objects.count() == 0


def test_search_still_writes_its_one_row_with_the_same_total(store, employee):
    results = search(query_text="annual leave", user=employee)
    [row] = SearchLog.objects.all()
    assert row.result_count == results.total_count == search_total(role_name=EMPLOYEE_ROLE_NAME, query_text="annual leave")


@pytest.mark.parametrize("term", ["", "a"])
def test_a_term_too_short_is_refused_as_search_refuses_it(term):
    with pytest.raises(SearchQueryTooShort):
        search_total(role_name=ADMINISTRATOR_ROLE_NAME, query_text=term)


def test_a_null_character_is_refused_as_search_refuses_it():
    with pytest.raises(SearchQueryContainsNullCharacter):
        search_total(role_name=ADMINISTRATOR_ROLE_NAME, query_text="ab\x00cd")
