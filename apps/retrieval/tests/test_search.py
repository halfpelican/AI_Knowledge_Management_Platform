"""FR-12 keyword search: the second route through the FR-11 permission boundary.

``apps/retrieval/search.py`` is the Front-End clause's grouped search, and it is a filtered
read rather than an algorithm (proposal section 7.10 says so explicitly). What is tested
here is therefore mostly the boundary and the counts, not ranking, because there is no
ranking: the file that would catch a relevance order creeping in is this one.

The test that matters most is ``test_the_two_roles_get_different_counts_for_the_same_term``
and its companion ``test_nothing_about_a_restricted_source_reaches_an_employee``. A search
reply is mostly counts, and CLAUDE.md invariant 1 forbids disclosing restricted material
"by a result count, a total, or an error message" — so the pair asserts that two roles
searching one term over one store are told different numbers, and that the Employee's reply
contains no trace of the Administrator-only source in any field, count or total.

Role names come from apps.core.constants, never as literals, following
apps/retrieval/tests/test_scoping.py, so a rename fails here rather than quietly agreeing
with itself.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MINIMUM_SEARCH_LENGTH,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.meetings.models import Meeting
from apps.retrieval.models import SearchLog
from apps.retrieval.scoping import UnscopedRequestError
from apps.retrieval.search import (
    SNIPPET_WINDOW_CHARACTERS,
    SearchQueryContainsNullCharacter,
    SearchQueryTooShort,
    search,
    snippet_for,
)

pytestmark = pytest.mark.django_db

ROLE_PAIR = (EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME)
DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES

TERM = "annual leave"

SHARED_TITLE = "Leave policy"
SHARED_TEXT = "Staff may take annual leave once probation has ended."

# The Administrator-only source. Its title, its text and its identifier must not appear
# anywhere in an Employee's reply.
RESTRICTED_TITLE = "Board remuneration review"
RESTRICTED_TEXT = "Directors accrue annual leave at twice the ordinary rate."


# --- Rows ------------------------------------------------------------------------------


def make_chunk(*, source_type, source_id, index, text, roles, embedding_model=STUB_EMBEDDING_MODEL):
    """A chunk stamped with a visibility scope, as ingestion stamps it (D-17).

    The vector is zeros and is never read: nothing in this path compares vectors.
    """
    return ContentChunk.objects.create(
        source_type=source_type,
        source_id=source_id,
        chunk_index=index,
        chunk_text=text,
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model=embedding_model,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )


def make_document(user, *, title, roles, texts=(), department="People", embedding_model=STUB_EMBEDDING_MODEL):
    document = Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=user,
        department=department,
        visible_to_roles=roles,
    )
    for index, text in enumerate(texts):
        make_chunk(
            source_type=DOCUMENT_SOURCE_TYPE,
            source_id=document.id,
            index=index,
            text=text,
            roles=roles,
            embedding_model=embedding_model,
        )
    return document


def make_meeting(*, title, roles, texts=(), meeting_date=date(2026, 1, 5)):
    meeting = Meeting.objects.create(
        title=title,
        meeting_date=meeting_date,
        transcript_text=" ".join(texts) or "A transcript.",
        visible_to_roles=roles,
    )
    for index, text in enumerate(texts):
        make_chunk(
            source_type=MEETING_SOURCE_TYPE,
            source_id=meeting.id,
            index=index,
            text=text,
            roles=roles,
        )
    return meeting


@pytest.fixture
def two_matching_documents(employee):
    """One document both roles may read and one only an Administrator may, both matching.

    This is the shape the count test needs: the same term over the same store returns one
    item to an Employee and two to an Administrator, so a count that leaked would have to
    leak a different number rather than merely the same one twice.
    """
    return {
        "shared": make_document(
            employee, title=SHARED_TITLE, roles=list(ROLE_PAIR), texts=[SHARED_TEXT]
        ),
        "restricted": make_document(
            employee,
            title=RESTRICTED_TITLE,
            roles=[ADMINISTRATOR_ROLE_NAME],
            texts=[RESTRICTED_TEXT],
            department="Executive",
        ),
    }


def titles(group):
    return [result.title for result in group.results]


# --- The counts, which are the likeliest disclosure --------------------------------------


def test_the_two_roles_get_different_counts_for_the_same_term(
    two_matching_documents, employee, administrator
):
    """Invariant 1's result-count clause, in the path where counts are the whole reply.

    Two matching documents in the store; an Employee may see one of them. The Employee is
    told 1 and the Administrator 2 — the Employee's number is exactly what the Employee can
    see, not a wider total with the restricted row subtracted somewhere a refactor could
    put back.
    """
    assert Document.objects.count() == 2  # what the store holds

    as_employee = search(query_text=TERM, user=employee)
    as_administrator = search(
        query_text=TERM, user=administrator
    )

    assert as_employee.documents.count == 1
    assert as_employee.total_count == 1
    assert titles(as_employee.documents) == [SHARED_TITLE]

    assert as_administrator.documents.count == 2
    assert as_administrator.total_count == 2
    assert sorted(titles(as_administrator.documents)) == sorted([SHARED_TITLE, RESTRICTED_TITLE])

    assert as_employee.total_count != as_administrator.total_count


def test_nothing_about_a_restricted_source_reaches_an_employee(two_matching_documents, employee):
    """Not in a row, not in a snippet, not in a count, not in a total.

    The whole reply is rendered to a string and searched, because the assertion is about
    absence from the object a view is handed rather than absence from one field somebody
    remembered to check.
    """
    restricted = two_matching_documents["restricted"]
    results = search(query_text=TERM, user=employee)

    rendered = repr(results)
    assert RESTRICTED_TITLE not in rendered
    assert RESTRICTED_TEXT not in rendered
    assert str(restricted.id) not in rendered
    assert "Executive" not in rendered  # nor its department

    # And the numbers: one item, one total, no second figure anywhere to be "of".
    assert results.documents.count == len(results.documents.results) == 1
    assert results.meetings.count == len(results.meetings.results) == 0
    assert results.total_count == 1


def test_a_title_match_is_scoped_exactly_as_a_body_match_is(employee, administrator):
    """The title branch is a second route to a row, so it carries the same predicate.

    A restricted source whose TITLE matches and whose text does not must be as absent as one
    whose text matches. Without the role predicate on the Documents queryset this test is
    the one that fails.
    """
    make_document(employee, title=RESTRICTED_TITLE, roles=[ADMINISTRATOR_ROLE_NAME], texts=["Nothing relevant."])

    as_employee = search(query_text="remuneration", user=employee)
    assert as_employee.total_count == 0
    assert RESTRICTED_TITLE not in repr(as_employee)

    as_administrator = search(
        query_text="remuneration", user=administrator
    )
    assert titles(as_administrator.documents) == [RESTRICTED_TITLE]


def test_the_scope_is_taken_from_the_user_and_cannot_be_supplied_by_the_caller(
    two_matching_documents, employee
):
    """``search`` has no ``role_name`` parameter, and that is the invariant, not the style.

    Two arguments that must agree are two arguments that can disagree: a view passing one
    user's identity with another's role would hand an Employee an Administrator's result set
    and log it under the Employee, and no test inside this module could see it, because both
    values would have arrived from the caller. Resolving the scope from ``user`` makes the
    pairing impossible to state wrongly — the same shape ``answer_question`` has.
    """
    import inspect

    assert "role_name" not in inspect.signature(search).parameters
    assert list(inspect.signature(search).parameters) == ["query_text", "user"]

    # And the behaviour behind it: this user's role, and only this user's role, decides.
    assert search(query_text=TERM, user=employee).total_count == 1


def test_a_role_changed_mid_session_takes_effect_on_the_next_search(
    two_matching_documents, employee, administrator_role
):
    """7.10 step 2, on the search path: the role is re-read from the user row every time.

    The user instance is left deliberately stale — the role is changed with an UPDATE that
    does not touch it — so an implementation that cached the role, or took it from a
    parameter the view resolved once, would still return the Employee's single result here.
    """
    from django.contrib.auth import get_user_model

    assert search(query_text=TERM, user=employee).total_count == 1

    get_user_model().objects.filter(pk=employee.pk).update(role=administrator_role)
    assert employee.role.role_name == EMPLOYEE_ROLE_NAME  # the in-memory copy is stale

    widened = search(query_text=TERM, user=employee)
    assert widened.total_count == 2
    assert RESTRICTED_TITLE in titles(widened.documents)


def test_a_search_on_behalf_of_nobody_is_refused(two_matching_documents):
    """Failure path: no authenticated user means no scope, loudly, and no row.

    Routes are IsAuthenticated already (invariant 4); this is the backstop for a caller
    reached some other way, and it must not fall through to a default scope in either
    direction — an empty one would hide a bug, a non-empty one would serve content to a
    request with nobody behind it.
    """
    from django.contrib.auth.models import AnonymousUser

    with pytest.raises(UnscopedRequestError):
        search(query_text=TERM, user=AnonymousUser())
    assert SearchLog.objects.count() == 0


def test_the_count_is_derived_from_the_rows_it_labels(two_matching_documents, administrator):
    """There is no stored integer to drift from the list, and no "n of m" to compute."""
    results = search(query_text=TERM, user=administrator)
    for group in results.groups:
        assert group.count == len(group.results)
    assert results.total_count == sum(len(group.results) for group in results.groups)


# --- Grouping ----------------------------------------------------------------------------


def test_documents_and_meetings_are_separate_groups_with_their_own_counts(employee):
    """FR-12: "results grouped by type (Documents and Meetings) with a count per group"."""
    make_document(employee, title=SHARED_TITLE, roles=[EMPLOYEE_ROLE_NAME], texts=[SHARED_TEXT])
    make_meeting(
        title="Quarterly planning",
        roles=[EMPLOYEE_ROLE_NAME],
        texts=["We discussed the annual leave backlog."],
    )

    results = search(query_text=TERM, user=employee)

    assert results.documents.source_type == DOCUMENT_SOURCE_TYPE
    assert results.meetings.source_type == MEETING_SOURCE_TYPE
    assert results.documents.count == 1
    assert results.meetings.count == 1
    assert results.total_count == 2
    assert titles(results.documents) == [SHARED_TITLE]
    assert titles(results.meetings) == ["Quarterly planning"]


def test_a_meeting_is_scoped_by_role_and_not_by_attendance(employee, administrator):
    """D-16: MeetingAttendees is a participation record, not an access control.

    The Employee attended and the Administrator did not; neither fact is consulted. The
    role arrays alone decide, and they decide the opposite way round from attendance here,
    so an implementation that consulted attendance could not pass.

    Until D-66 this was arranged the other way — an Employee-only meeting the Administrator
    attended and was refused. An Administrator now reads Employee-only content, so the
    meeting is Administrator-only instead and the attendee is the Employee who is refused.
    """
    from apps.meetings.models import MeetingAttendee

    meeting = make_meeting(
        title="Leave policy review",
        roles=[ADMINISTRATOR_ROLE_NAME],
        texts=["The annual leave rules were restated."],
    )
    MeetingAttendee.objects.create(meeting=meeting, user=employee)

    assert search(query_text=TERM, user=employee).meetings.count == 0
    assert search(query_text=TERM, user=administrator).meetings.count == 1


def test_a_meeting_carries_no_department(employee):
    """Meetings model none, and an empty string is the honest rendering (see SearchResult)."""
    make_meeting(title="Quarterly planning", roles=[EMPLOYEE_ROLE_NAME], texts=[SHARED_TEXT])
    results = search(query_text=TERM, user=employee)
    assert results.meetings.results[0].department == ""
    assert results.meetings.results[0].date == date(2026, 1, 5)


def test_a_document_result_carries_its_department_and_upload_date(employee):
    document = make_document(
        employee, title=SHARED_TITLE, roles=[EMPLOYEE_ROLE_NAME], texts=[SHARED_TEXT], department="People"
    )
    result = search(query_text=TERM, user=employee).documents.results[0]
    assert result.department == "People"
    assert result.date == document.uploaded_at
    assert result.source_id == str(document.id)
    assert result.source_type == DOCUMENT_SOURCE_TYPE


# --- Snippets ----------------------------------------------------------------------------


LONG_PREFIX = "Filler sentence about unrelated policy. " * 40
LONG_SUFFIX = "More filler about something else entirely. " * 40
LONG_TEXT = f"{LONG_PREFIX}Employees accrue annual leave monthly.{LONG_SUFFIX}"


def test_the_snippet_is_a_window_around_the_match_not_the_whole_chunk(employee):
    """FR-12 shows "the matching passage as a snippet", and a snippet is not a chunk."""
    make_document(employee, title=SHARED_TITLE, roles=[EMPLOYEE_ROLE_NAME], texts=[LONG_TEXT])

    snippet = search(
        query_text=TERM, user=employee
    ).documents.results[0].snippet

    assert TERM in snippet
    assert len(snippet) < len(LONG_TEXT)
    # The window plus the two cut markers, and nothing more.
    assert len(snippet) <= SNIPPET_WINDOW_CHARACTERS + 6
    assert snippet.startswith("...") and snippet.endswith("...")


def test_a_match_at_either_end_of_the_text_still_contains_the_term():
    """Unit-level: the window clamps at both ends without losing the match."""
    at_start = snippet_for(f"{TERM} is the subject. " + "tail " * 200, TERM)
    at_end = snippet_for("head " * 200 + f"and finally {TERM}.", TERM)
    assert at_start.startswith(TERM) and TERM in at_start
    assert TERM in at_end and at_end.endswith(".")
    for snippet in (at_start, at_end):
        assert len(snippet) <= SNIPPET_WINDOW_CHARACTERS + 6


def test_a_text_shorter_than_the_window_comes_back_whole_and_unmarked():
    assert snippet_for(SHARED_TEXT, TERM) == SHARED_TEXT


def test_only_the_first_matching_chunk_of_a_source_supplies_the_snippet(employee):
    """One result per source, so the group count counts items rather than chunks."""
    make_document(
        employee,
        title=SHARED_TITLE,
        roles=[EMPLOYEE_ROLE_NAME],
        texts=[
            "First mention of annual leave, in chunk zero.",
            "Second mention of annual leave, in chunk one.",
            "Third mention of annual leave, in chunk two.",
        ],
    )
    results = search(query_text=TERM, user=employee)

    assert results.documents.count == 1  # not 3
    assert "chunk zero" in results.documents.results[0].snippet
    assert "chunk one" not in results.documents.results[0].snippet


def test_a_title_only_match_falls_back_to_the_opening_of_the_first_chunk(employee):
    """The item is found by its title; the snippet says so by being the start of the item.

    FR-12's row shows the title, so finding an item by that title is the consistent
    behaviour. The snippet deliberately does NOT contain the search term here, because no
    passage contained it.
    """
    make_document(
        employee,
        title="Employee Handbook",
        roles=[EMPLOYEE_ROLE_NAME],
        texts=["This handbook opens by describing the organisation's values." + " padding" * 100],
    )
    result = search(
        query_text="Handbook", user=employee
    ).documents.results[0]

    assert result.title == "Employee Handbook"
    assert result.snippet.startswith("This handbook opens")
    assert "Handbook" not in result.snippet  # the title matched, not the passage
    assert result.snippet.endswith("...")


def test_a_title_match_on_a_source_with_no_chunks_has_an_empty_snippet(employee):
    """An "Insufficient content" document is still findable, with nothing invented for it."""
    make_document(employee, title="Employee Handbook", roles=[EMPLOYEE_ROLE_NAME], texts=[])
    result = search(
        query_text="Handbook", user=employee
    ).documents.results[0]
    assert result.snippet == ""


# --- Matching ----------------------------------------------------------------------------


def test_the_match_is_case_insensitive_in_both_directions(employee):
    make_document(
        employee, title="Leave policy", roles=[EMPLOYEE_ROLE_NAME], texts=["ANNUAL LEAVE IN CAPITALS."]
    )
    make_document(
        employee, title="Roster", roles=[EMPLOYEE_ROLE_NAME], texts=["annual leave in lower case."]
    )

    lower = search(query_text="annual leave", user=employee)
    upper = search(query_text="ANNUAL LEAVE", user=employee)

    assert lower.documents.count == 2
    assert upper.documents.count == 2
    assert sorted(titles(lower.documents)) == sorted(titles(upper.documents))
    # And the snippet carries the text as stored, not the term as typed.
    assert "ANNUAL LEAVE IN CAPITALS." in [result.snippet for result in upper.documents.results]


# --- Whitespace: a phrase is found whatever the line breaks between its words (D-71) -------
#
# Objective 02's D06 found this: "Willow Bridge escalation ladder" is in the PDF, but its
# extracted text wraps as "escalation\nladder", chunk text keeps the line break (D-31), and a
# plain substring test then never matches. Runs of whitespace are collapsed to one space on
# both sides before matching.


def test_a_phrase_that_wraps_a_line_in_the_source_is_found(employee):
    make_document(
        employee,
        title="Customer Complaints Procedure",
        roles=[EMPLOYEE_ROLE_NAME],
        texts=["Complaints not resolved follow the Willow Bridge escalation\nladder: team leader first."],
    )

    results = search(query_text="escalation ladder", user=employee)

    assert titles(results.documents) == ["Customer Complaints Procedure"]
    # The snippet shows the phrase as one run of text, since it is a one-line preview.
    assert "escalation ladder" in results.documents.results[0].snippet


@pytest.mark.parametrize(
    "stored, typed",
    [
        ("escalation\r\n  ladder", "escalation ladder"),  # CRLF and indentation in the source
        ("escalation\tladder", "escalation ladder"),  # a tab, as XLSX cells are joined
        ("escalation ladder", "escalation   ladder"),  # extra spaces in the query
        ("escalation ladder", "escalation\nladder"),  # a line break in the query
    ],
    ids=["crlf-indent", "tab", "query-spaces", "query-newline"],
)
def test_any_run_of_whitespace_on_either_side_matches_one_space(employee, stored, typed):
    make_document(
        employee, title="Procedure", roles=[EMPLOYEE_ROLE_NAME], texts=[f"Follow the {stored} first."]
    )
    assert search(query_text=typed, user=employee).documents.count == 1


def test_a_title_is_matched_the_same_way(employee):
    make_document(employee, title="Remote  Work\nAgreement", roles=[EMPLOYEE_ROLE_NAME], texts=[])
    assert search(query_text="remote work agreement", user=employee).documents.count == 1


def test_collapsing_whitespace_does_not_cross_the_permission_boundary(employee, administrator):
    """The same match, out of scope: still nothing for the Employee, by the same predicate."""
    make_document(
        administrator,
        title="Board paper",
        roles=[ADMINISTRATOR_ROLE_NAME],
        texts=["The Willow Bridge escalation\nladder is restricted."],
    )
    assert search(query_text="escalation ladder", user=employee).total_count == 0
    assert search(query_text="escalation ladder", user=administrator).total_count == 1


def test_the_search_log_keeps_the_term_as_typed(employee):
    """Collapsing is for matching only: FR-19's evidence records what was actually typed."""
    search(query_text="escalation   ladder", user=employee)
    assert SearchLog.objects.get().query_text == "escalation   ladder"


def test_a_chunk_recorded_against_another_embedding_model_is_still_searchable(employee):
    """The risk R10 predicate belongs to vector comparison, and this path compares none.

    ``candidate_chunks`` excludes a chunk embedded by another model because a cosine score
    over mismatched vectors is meaningless. A substring test over chunk_text is
    model-independent, so applying that predicate here would hide readable material after a
    provider switch, in a path with no no-answer message to make the narrowing visible.
    """
    make_document(
        employee,
        title=SHARED_TITLE,
        roles=[EMPLOYEE_ROLE_NAME],
        texts=[SHARED_TEXT],
        embedding_model="some-other-model",
    )
    results = search(query_text=TERM, user=employee)
    assert results.documents.count == 1


def test_a_term_matching_nothing_is_an_empty_result_and_not_an_error(
    two_matching_documents, employee
):
    """Failure path, and it is not a failure: zero groups, zero counts, still a logged row."""
    results = search(query_text="parking permits", user=employee)

    assert results.documents.results == ()
    assert results.meetings.results == ()
    assert results.documents.count == 0
    assert results.meetings.count == 0
    assert results.total_count == 0
    # A search that found nothing is exactly the row FR-19 wants.
    row = SearchLog.objects.get()
    assert row.query_text == "parking permits"
    assert row.result_count == 0


# --- Ordering ----------------------------------------------------------------------------


def test_documents_come_back_newest_first_and_meetings_by_meeting_date(employee):
    """Recency, matching GET /api/documents and GET /api/meetings. Never a relevance order.

    ``uploaded_at`` is auto_now_add, so it is set here with an UPDATE rather than trusted to
    the clock: two rows created microseconds apart could tie, and a tie would make this
    test assert the pk tiebreak instead of the ordering it is about.
    """
    now = timezone.now()
    older = make_document(employee, title="Older leave policy", roles=[EMPLOYEE_ROLE_NAME], texts=[SHARED_TEXT])
    newer = make_document(employee, title="Newer leave policy", roles=[EMPLOYEE_ROLE_NAME], texts=[SHARED_TEXT])
    Document.objects.filter(pk=older.pk).update(uploaded_at=now - timedelta(days=7))
    Document.objects.filter(pk=newer.pk).update(uploaded_at=now)

    make_meeting(
        title="Old meeting",
        roles=[EMPLOYEE_ROLE_NAME],
        texts=[SHARED_TEXT],
        meeting_date=date(2026, 1, 5),
    )
    make_meeting(
        title="Recent meeting",
        roles=[EMPLOYEE_ROLE_NAME],
        texts=[SHARED_TEXT],
        meeting_date=date(2026, 3, 5),
    )

    results = search(query_text=TERM, user=employee)
    assert titles(results.documents) == ["Newer leave policy", "Older leave policy"]
    assert titles(results.meetings) == ["Recent meeting", "Old meeting"]


# --- Validation --------------------------------------------------------------------------


@pytest.mark.parametrize("query_text", ["", "a"])
def test_a_query_shorter_than_the_minimum_raises_and_writes_no_row(
    two_matching_documents, employee, query_text
):
    """FR-12's two-character floor, enforced server-side (invariant 4).

    It raises rather than returning an empty result set: an empty set would say "nothing
    matches", which is a claim about the corpus in answer to a question never properly
    asked, and it would put that claim into FR-19's evidence.
    """
    assert len(query_text) < MINIMUM_SEARCH_LENGTH
    with pytest.raises(SearchQueryTooShort):
        search(query_text=query_text, user=employee)
    assert SearchLog.objects.count() == 0


def test_a_query_at_the_minimum_length_is_accepted(employee):
    make_document(employee, title="Leave policy", roles=[EMPLOYEE_ROLE_NAME], texts=["HR owns this."])
    results = search(query_text="HR", user=employee)
    assert results.documents.count == 1


# --- The record --------------------------------------------------------------------------


def test_one_search_log_row_per_search_holding_the_post_filter_count(
    two_matching_documents, employee
):
    """The logged number is the number the caller was given, and both are post-filter.

    The store holds two matching documents; the Employee is told 1 and the row records 1.
    A row recording 2 would be the count disclosure written down instead of returned.
    """
    results = search(query_text=TERM, user=employee)

    row = SearchLog.objects.get()
    assert row.user == employee
    assert row.query_text == TERM
    assert row.result_count == results.total_count == 1
    assert Document.objects.count() == 2  # and the wider number is nowhere in the record

    search(query_text=TERM, user=employee)
    assert SearchLog.objects.count() == 2  # one row per search, not one per result


def test_the_query_text_is_recorded_verbatim(employee):
    """No sanitiser and no stripping, exactly as the answer path stores a question."""
    typed = "  Annual Leave?  "
    search(query_text=typed, user=employee)
    assert SearchLog.objects.get().query_text == typed


# --- What this path must never touch ------------------------------------------------------


def test_no_provider_is_contacted(two_matching_documents, employee, stub_ai_service):
    """No embedding, no generation, no NPU time: this is a filtered read (7.10).

    The stub is the suite's AI service for every test; if search reached a provider at all
    it would reach this one, and conftest.py's ``no_live_provider`` points the real
    endpoints at a closed port underneath it.
    """
    search(query_text=TERM, user=employee)
    assert stub_ai_service.embed_calls == []
    assert stub_ai_service.generate_calls == []


def test_the_module_does_not_import_the_ai_package():
    """The structural version of the test above, and the one that survives a refactor.

    A future "improvement" that embedded the query to order results would have to import
    apps.ai to do it, and would fail here before it could fail a behavioural test.
    """
    import apps.retrieval.search as search_module

    source = Path(search_module.__file__).read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert not [line for line in import_lines if "apps.ai" in line]
    assert "embed_question" not in source


# --- Both roles ---------------------------------------------------------------------------


def test_search_from_both_role_sessions(session_client, two_matching_documents):
    """The same search run from an Employee session and an Administrator session
    (CLAUDE.md section 8 item 2): each is told what its own role may see, and the Employee
    is told a smaller number over the same store.

    Nothing here states a role: the session's user is passed and ``search`` resolves the
    scope from it, so what this asserts is that the identity alone decides the result set.
    """
    role_name = session_client.role_name
    expected = {EMPLOYEE_ROLE_NAME: 1, ADMINISTRATOR_ROLE_NAME: 2}[role_name]

    results = search(query_text=TERM, user=session_client.user)

    assert results.documents.count == expected
    assert results.total_count == expected
    assert SearchLog.objects.get().result_count == expected
    if role_name == EMPLOYEE_ROLE_NAME:
        assert RESTRICTED_TITLE not in repr(results)


# --- Stage 4 item 12a: a NUL byte in q --------------------------------------------------
#
# THE FINDING, once, for the three tests below. ``GET /api/search?q=ab%00cd`` from any
# authenticated session raised ``psycopg.DataError`` out of the ``chunk_text__icontains``
# lookup and was answered **500 with an HTML body** — a traceback page under ``DEBUG``,
# carrying frame locals and the requester's own session cookie. ``POST /api/ask`` answers the
# same input a clean 400, because its serializer field carries DRF's
# ``ProhibitNullCharactersValidator``; ``q`` is read straight off ``request.query_params``
# and is the only user-supplied string in this system that reaches the database without
# passing through a DRF field.

NULL_TERM = "ab\x00cd"


def test_a_query_containing_a_null_character_raises_its_own_exception_and_writes_no_row(
    two_matching_documents, employee
):
    """THE FINDING at the function boundary, and the distinct exception is the point.

    NOT ``SearchQueryTooShort``: the term is four characters, comfortably over the floor, and
    a message saying it is too short would state something false about the request. Raised
    before any query runs, so no ``SearchLog`` row is written — this was not a search, the
    same reasoning the length check uses.
    """
    assert len(NULL_TERM) >= MINIMUM_SEARCH_LENGTH  # not the length rule
    with pytest.raises(SearchQueryContainsNullCharacter):
        search(query_text=NULL_TERM, user=employee)
    assert SearchLog.objects.count() == 0
    assert not issubclass(SearchQueryTooShort, SearchQueryContainsNullCharacter)
    assert not issubclass(SearchQueryContainsNullCharacter, SearchQueryTooShort)


def test_a_null_character_in_q_is_400_json_from_both_role_sessions(session_client):
    """THE FINDING at the endpoint, from an Employee session and an Administrator session
    (CLAUDE.md section 8 item 2): 400 and not 500, and a JSON body rather than an HTML
    traceback page.

    The status and the content type are asserted separately because the defect was both: a
    500 would have been wrong on its own, and a 500 rendered as ``text/html`` is the part
    that carries frame locals and a session cookie to whoever sent the byte.
    """
    response = session_client.client.get(reverse("search"), {"q": NULL_TERM})

    assert response.status_code == 400
    assert response["Content-Type"].startswith("application/json")
    assert "q" in response.json()
    assert SearchLog.objects.count() == 0
    # And the reply says what was actually wrong, not that the term was too short.
    message = " ".join(response.json()["q"])
    assert "null character" in message
    assert "characters" not in message.replace("null character", "")


def test_an_ordinary_query_is_unaffected_by_the_null_check(employee):
    """The check is one character and nothing else: no stripping, no normalising, and a term
    that merely mentions or escapes the byte in prose is a term this platform may search
    for."""
    make_document(
        employee,
        title="Encoding notes",
        roles=[EMPLOYEE_ROLE_NAME],
        texts=[r"The loader rejects a literal \x00 in a CSV column."],
    )

    results = search(query_text=r"\x00", user=employee)

    assert results.documents.count == 1
    assert SearchLog.objects.get().query_text == r"\x00"
