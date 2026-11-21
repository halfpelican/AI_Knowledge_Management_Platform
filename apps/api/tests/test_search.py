"""``GET /api/search`` — FR-12's keyword search half, over the HTTP boundary (D-41).

``apps/retrieval/tests/test_search.py`` tests the function. This file tests the *route*:
the grouped shape FR-12's Front-End clause specifies, the status codes, the single
``SearchLog`` row, and the one property that only exists once there is a response body —
that nothing about an out-of-scope source reaches an Employee through it, counts and
totals included.

**Why the leak test reads the raw body.** CLAUDE.md invariant 1 forbids disclosing
restricted material "by a result count, a total, or an error message", and a grouped search
reply is mostly counts. Asserting on parsed fields would pass a body that carried the
restricted title in some key the test did not think to look at, so
``test_nothing_about_a_restricted_document_reaches_an_employee`` asserts against
``response.content`` — every byte the client is sent.

Role names come from ``apps.core.constants``, never as literals, so a rename fails here
rather than quietly agreeing with itself.
"""

from datetime import date

import pytest
from django.conf import settings
from django.utils import timezone

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_SEARCH_LENGTH,
    MINIMUM_SEARCH_LENGTH,
    SOURCE_TYPES,
    SUMMARY_READY,
)
from apps.documents.models import ContentChunk, Document, DocumentAnalysis
from apps.meetings.models import Meeting, MeetingSummary
from apps.retrieval.models import SearchLog

pytestmark = pytest.mark.django_db

SEARCH_URL = "/api/search"
DOCUMENTS_URL = "/api/documents"
MEETINGS_URL = "/api/meetings"

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]

TERM = "annual leave"
UNMATCHED_TERM = "kayaking"

DOCUMENT_TITLE = "Leave policy"
DOCUMENT_TEXT = "Staff may take annual leave once probation has ended."
DOCUMENT_DEPARTMENT = "People"
MEETING_TITLE = "Annual leave planning"
MEETING_TEXT = "The group agreed the annual leave embargo ends in March."

# The Administrator-only document. Its title, its passage and its identifier must not
# appear anywhere in an Employee's reply, and it must not move an Employee's counts.
RESTRICTED_TITLE = "Board remuneration review"
RESTRICTED_TEXT = "Directors accrue annual leave at twice the ordinary rate."


# --- Rows -------------------------------------------------------------------------------


def make_chunk(*, source_type, source_id, text, roles, index=0, ai_generated=False):
    """A chunk stamped with a visibility scope, as ingestion stamps it (D-17).

    The vector is zeros and is never read: this path compares no vectors. ``ai_generated`` marks
    a passage of a meeting's FR-16 summary (D-125).
    """
    return ContentChunk.objects.create(
        source_type=source_type,
        source_id=source_id,
        chunk_index=index,
        chunk_text=text,
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
        ai_generated=ai_generated,
    )


def make_document(uploader, *, title, roles, text, department=DOCUMENT_DEPARTMENT):
    document = Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=uploader,
        department=department,
        visible_to_roles=roles,
    )
    make_chunk(
        source_type=DOCUMENT_SOURCE_TYPE, source_id=document.id, text=text, roles=roles
    )
    return document


def make_meeting(*, title, roles, text, meeting_date=date(2026, 1, 5)):
    meeting = Meeting.objects.create(
        title=title,
        meeting_date=meeting_date,
        transcript_text=text,
        visible_to_roles=roles,
    )
    make_chunk(
        source_type=MEETING_SOURCE_TYPE, source_id=meeting.id, text=text, roles=roles
    )
    return meeting


@pytest.fixture
def shared_corpus(employee):
    """One matching document and one matching meeting, both visible to both roles."""
    return (
        make_document(employee, title=DOCUMENT_TITLE, roles=BOTH_ROLES, text=DOCUMENT_TEXT),
        make_meeting(title=MEETING_TITLE, roles=BOTH_ROLES, text=MEETING_TEXT),
    )


@pytest.fixture
def restricted_document(administrator):
    """A matching document an Employee may not see, uploaded by the Administrator."""
    return make_document(
        administrator,
        title=RESTRICTED_TITLE,
        roles=[ADMINISTRATOR_ROLE_NAME],
        text=RESTRICTED_TEXT,
        department="Executive",
    )


# --- 200: grouped results, from both roles -----------------------------------------------


def test_a_search_returns_results_grouped_by_type_with_a_count_per_group(
    session_client, shared_corpus
):
    """FR-12's clause, from an Employee session and from an Administrator session.

    The route carries no role permission beyond the global ``IsAuthenticated`` default, so
    both roles reach it; what differs between them is the scope, which is the next test.
    """
    response = session_client.client.get(SEARCH_URL, {"q": TERM})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"query", "documents", "meetings", "total_count"}
    assert body["query"] == TERM
    assert body["documents"]["count"] == 1 == len(body["documents"]["results"])
    assert body["meetings"]["count"] == 1 == len(body["meetings"]["results"])
    assert body["total_count"] == 2
    assert [r["title"] for r in body["documents"]["results"]] == [DOCUMENT_TITLE]
    assert [r["title"] for r in body["meetings"]["results"]] == [MEETING_TITLE]


def test_each_result_carries_exactly_what_the_clause_says_it_shows(
    employee_client, shared_corpus
):
    """"its title, the matching passage as a snippet, its department, and its date", plus
    the type and identifier the front end links with, and nothing else.

    ``snippet_ai_generated`` since D-125 (FR-16): whether the snippet is from a meeting's
    AI-generated summary rather than its transcript, which NFR-15 requires the interface to mark.
    It describes the snippet shown and nothing about the source. False here, where both snippets
    are the sources' own words; apps/api/tests/test_summary_in_retrieval.py covers True.

    ``summary``, ``key_points`` and ``summary_truncated`` since D-139 (FR-10: "a short summary and
    a list of key points, shown beneath the title in search results"). Empty here, where neither
    source has one; the D-139 section at the end of this file covers a document that has."""
    body = employee_client.get(SEARCH_URL, {"q": TERM}).json()

    [document_result] = body["documents"]["results"]
    [meeting_result] = body["meetings"]["results"]
    for result in (document_result, meeting_result):
        assert set(result) == {
            "source_type",
            "source_id",
            "title",
            "snippet",
            "snippet_ai_generated",
            "department",
            "date",
            "summary",
            "key_points",
            "summary_truncated",
        }
        # The snippet is the matching passage, so the term is in it.
        assert TERM in result["snippet"].lower()
        assert result["snippet_ai_generated"] is False
        assert (result["summary"], result["key_points"], result["summary_truncated"]) == ("", [], False)
    assert document_result["source_type"] == DOCUMENT_SOURCE_TYPE
    assert document_result["department"] == DOCUMENT_DEPARTMENT
    assert meeting_result["source_type"] == MEETING_SOURCE_TYPE
    # A meeting models no department, permanently and by decision, and "" is what the
    # front end already has to render for a document without one.
    assert meeting_result["department"] == ""


def test_a_results_date_is_the_same_string_the_listing_endpoints_give(
    employee_client, shared_corpus
):
    """A document's date is its ``uploaded_at`` and a meeting's is its ``meeting_date``,
    rendered by DRF's own fields, so the same row does not appear with two different date
    strings in two places in one interface."""
    body = employee_client.get(SEARCH_URL, {"q": TERM}).json()
    [listed_document] = employee_client.get(DOCUMENTS_URL).json()
    [listed_meeting] = employee_client.get(MEETINGS_URL).json()

    assert body["documents"]["results"][0]["date"] == listed_document["uploaded_at"]
    assert body["meetings"]["results"][0]["date"] == listed_meeting["meeting_date"]


def test_a_search_result_never_carries_a_file_path_or_a_content_hash(
    employee_client, shared_corpus
):
    """The document object's rule (docs/api-contract.md), which applies identically here:
    a path inside MEDIA_ROOT is of no use to a client and an invitation to construct one,
    and the hash exists to answer FR-08's 409."""
    raw = employee_client.get(SEARCH_URL, {"q": TERM}).content.decode()

    for field in ("file_path", "content_hash", "transcript_text", "visible_to_roles"):
        assert field not in raw


# --- The permission boundary: the counts are the disclosure risk --------------------------


def test_the_two_roles_are_told_different_counts_for_the_same_term(
    employee_client, administrator_client, shared_corpus, restricted_document
):
    """One term, one store, two roles, different numbers — and that is by design.

    The Employee's document count is what the Employee can see, not what exists. Counts
    come from the post-filter set, so a total can never disclose that there is more
    (CLAUDE.md invariant 1).
    """
    employee_body = employee_client.get(SEARCH_URL, {"q": TERM}).json()
    administrator_body = administrator_client.get(SEARCH_URL, {"q": TERM}).json()

    assert employee_body["documents"]["count"] == 1
    assert administrator_body["documents"]["count"] == 2
    # The meeting is visible to both, so that group is the same for both roles: the
    # difference is the scope and nothing else.
    assert employee_body["meetings"]["count"] == administrator_body["meetings"]["count"] == 1
    assert employee_body["total_count"] == 2
    assert administrator_body["total_count"] == 3
    # And the Employee's count agrees with what the Employee can otherwise list.
    visible_titles = {d["title"] for d in employee_client.get(DOCUMENTS_URL).json()}
    assert visible_titles == {DOCUMENT_TITLE}
    assert RESTRICTED_TITLE in {
        d["title"] for d in administrator_client.get(DOCUMENTS_URL).json()
    }


def test_nothing_about_a_restricted_document_reaches_an_employee(
    employee_client, shared_corpus, restricted_document
):
    """Asserted against the raw rendered body, not the parsed fields.

    Title, passage, identifier and department: none of the four may appear anywhere in
    what the Employee is sent, in any key, including one this test does not know about.
    """
    response = employee_client.get(SEARCH_URL, {"q": TERM})

    assert response.status_code == 200
    raw = response.content.decode()
    assert RESTRICTED_TITLE not in raw
    assert "Directors accrue" not in raw
    assert str(restricted_document.id) not in raw
    assert "Executive" not in raw


# --- 200 with nothing found ---------------------------------------------------------------


def test_a_term_that_matches_nothing_is_200_with_empty_groups(session_client, shared_corpus):
    """An empty reply is a fact about the corpus, not an error. Both roles, because "no
    results" must not be reachable only from the role with the wider scope."""
    response = session_client.client.get(SEARCH_URL, {"q": UNMATCHED_TERM})

    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == {"count": 0, "results": []}
    assert body["meetings"] == {"count": 0, "results": []}
    assert body["total_count"] == 0


# --- 400 ----------------------------------------------------------------------------------


def test_a_request_without_a_term_is_400_and_records_no_search(session_client):
    """``q`` absent altogether. DRF's validation shape, keyed on the parameter's own name.

    No ``SearchLog`` row: this was not a search, so it is not evidence of one (FR-19).
    """
    response = session_client.client.get(SEARCH_URL)

    assert response.status_code == 400
    assert set(response.json()) == {"q"}
    assert not SearchLog.objects.exists()


@pytest.mark.parametrize("term", ["a", ""])
def test_a_term_below_the_minimum_is_400_and_records_no_search(
    session_client, shared_corpus, term
):
    """The view maps ``SearchQueryTooShort`` and never re-checks the length, so there is
    one definition of "too short". An empty ``q=`` is the same rule reached the same way,
    and neither writes a row."""
    assert len(term) < MINIMUM_SEARCH_LENGTH

    response = session_client.client.get(SEARCH_URL, {"q": term})

    assert response.status_code == 400
    assert set(response.json()) == {"q"}
    assert str(MINIMUM_SEARCH_LENGTH) in response.json()["q"][0]
    assert not SearchLog.objects.exists()


def test_a_term_over_the_maximum_is_400_and_records_no_search(session_client, shared_corpus):
    """The upper bound (D-79's note of 10 November 2026): keyword search bounded a term from
    below only, so one request could log a term of any length for FR-19's cycle to embed and
    show. The view maps ``SearchQueryTooLong`` as it maps the other two refusals, from both
    roles, and no row is written."""
    term = "a" * (MAXIMUM_SEARCH_LENGTH + 1)

    response = session_client.client.get(SEARCH_URL, {"q": term})

    assert response.status_code == 400
    assert set(response.json()) == {"q"}
    assert str(MAXIMUM_SEARCH_LENGTH) in response.json()["q"][0]
    assert not SearchLog.objects.exists()


def test_a_term_at_the_maximum_is_searched_and_logged(employee_client, shared_corpus):
    """The bound is inclusive, as the question's is."""
    term = "a" * MAXIMUM_SEARCH_LENGTH

    response = employee_client.get(SEARCH_URL, {"q": term})

    assert response.status_code == 200
    [log] = SearchLog.objects.all()
    assert log.query_text == term


# --- 401 ----------------------------------------------------------------------------------


def test_search_is_401_anonymously(api_client, shared_corpus):
    """The global ``IsAuthenticated`` default is the whole authorisation on this route, and
    an unauthenticated search is refused before any row is read or written."""
    assert api_client.get(SEARCH_URL, {"q": TERM}).status_code == 401
    assert not SearchLog.objects.exists()


# --- The record, and what the request did not do -------------------------------------------


def test_one_search_log_row_per_request_with_the_total_the_caller_was_given(
    session_client, shared_corpus
):
    """``search()`` writes exactly one row; the view must not write a second.

    ``result_count`` is the post-filter total, and it is the same number in the body, so
    the record and the screen cannot disagree.
    """
    body = session_client.client.get(SEARCH_URL, {"q": TERM}).json()

    [log] = SearchLog.objects.all()
    assert log.user_id == session_client.user.id
    assert log.query_text == TERM  # verbatim, as typed
    assert log.result_count == body["total_count"] == 2


def test_a_second_search_writes_a_second_row_and_no_more(employee_client, shared_corpus):
    employee_client.get(SEARCH_URL, {"q": TERM})
    employee_client.get(SEARCH_URL, {"q": UNMATCHED_TERM})

    assert SearchLog.objects.count() == 2
    # Including the search that found nothing, which is exactly the knowledge-gap
    # evidence FR-19 wants.
    assert SearchLog.objects.filter(query_text=UNMATCHED_TERM, result_count=0).exists()


def test_a_search_contacts_no_ai_provider(employee_client, shared_corpus, stub_ai_service):
    """Nothing here embeds, ranks or generates: it is a filtered read (section 7.10), so
    the endpoint costs no NPU time and a provider outage does not break search."""
    assert employee_client.get(SEARCH_URL, {"q": TERM}).status_code == 200

    assert stub_ai_service.embed_calls == []
    assert stub_ai_service.generate_calls == []


# --- FR-10's document summary beneath the title (D-139) -----------------------------------
#
# FR-10: "Each document displays a short summary and a list of key points, shown beneath the
# title in search results so users can judge relevance before opening the file." Each result
# carries ``summary``, ``key_points`` and ``summary_truncated``. The analysis rows are written
# straight through the ORM: these tests are about what a result shows of a stored summary,
# whatever wrote it. apps/retrieval/tests/test_search.py holds the function's own tests,
# including the query count.

SUMMARY = "How leave is requested, approved and carried over."
KEY_POINTS = ["Requests are made in writing.", "A manager approves each one."]
SUMMARY_MODEL = "summarising-model"

# The restricted document's summary. None of its words is in a title or a passage of the store,
# so wherever one of them turns up, the summary put it there.
RESTRICTED_SUMMARY = "The committee set the bonus pool at four per cent of profit."
RESTRICTED_KEY_POINT = "The pool is capped at two million."
# In the restricted document's TITLE, and in nothing an Employee may read.
RESTRICTED_TITLE_TERM = "remuneration"

# In a summary and its key points and nowhere else: no title and no passage holds it.
SUMMARY_ONLY_TERM = "zeppelin"

NO_SUMMARY = ("", [], False)
NOTHING_FOUND = {
    "documents": {"count": 0, "results": []},
    "meetings": {"count": 0, "results": []},
    "total_count": 0,
}


def summarise(document, **fields):
    return DocumentAnalysis.objects.create(document=document, classified_at=timezone.now(), **fields)


def summary_of(result):
    return (result["summary"], result["key_points"], result["summary_truncated"])


def test_a_document_result_carries_its_summary_its_key_points_and_whether_it_is_partial(
    session_client, shared_corpus
):
    """From an Employee session and from an Administrator session."""
    document, _ = shared_corpus
    summarise(document, summary=SUMMARY, key_points=KEY_POINTS, summary_truncated=True,
              summary_model=SUMMARY_MODEL, summarised_at=timezone.now())

    response = session_client.client.get(SEARCH_URL, {"q": TERM})

    assert response.status_code == 200
    [result] = response.json()["documents"]["results"]
    assert result["source_id"] == str(document.id)
    # ``summary_truncated`` is the summary's own flag: the classifier's ``input_truncated`` is
    # false on this row.
    assert summary_of(result) == (SUMMARY, KEY_POINTS, True)
    # The snippet is still the document's own words. The summary is beside it, not instead of it.
    assert result["snippet_ai_generated"] is False
    assert TERM in result["snippet"].lower()
    # The meeting beside it has none.
    [meeting_result] = response.json()["meetings"]["results"]
    assert summary_of(meeting_result) == NO_SUMMARY
    # Which model wrote the summary and when is a record, and no part of the body (D-139).
    raw = response.content.decode()
    for withheld in ("summary_model", "summarised_at", SUMMARY_MODEL):
        assert withheld not in raw


def test_a_document_never_classified_and_one_classified_without_a_summary_carry_the_empty_values(
    session_client, employee
):
    """``""``, ``[]`` and ``false``, never null and never a missing key, from both roles. A
    document with no analysis row at all is still a result: the summary is read beside the
    document, and its absence removes nothing."""
    never_classified = make_document(employee, title="Leave policy", roles=BOTH_ROLES, text=DOCUMENT_TEXT)
    classified = make_document(employee, title="Leave calendar", roles=BOTH_ROLES, text=DOCUMENT_TEXT)
    summarise(classified, input_truncated=True)  # the classifier's flag is not the summary's

    body = session_client.client.get(SEARCH_URL, {"q": TERM}).json()

    assert body["documents"]["count"] == 2 == body["total_count"]
    results = {result["source_id"]: result for result in body["documents"]["results"]}
    assert set(results) == {str(never_classified.id), str(classified.id)}
    for result in results.values():
        assert summary_of(result) == NO_SUMMARY


def test_a_meeting_result_carries_no_summary_even_when_the_meeting_has_one(session_client):
    """FR-10 summarises documents. A meeting's FR-16 summary is reached through its AI-generated
    passages, as a snippet marked ``snippet_ai_generated`` (D-125), and is never put in the three
    keys: found by its transcript or found by its summary, the meeting carries them empty."""
    meeting = make_meeting(title=MEETING_TITLE, roles=BOTH_ROLES, text=MEETING_TEXT)
    sentence = f"The group agreed to hire a {SUMMARY_ONLY_TERM} for the launch."
    MeetingSummary.objects.create(
        meeting=meeting, status=SUMMARY_READY, summary_text=sentence, generated_at=timezone.now(),
        narrative=[{"text": sentence, "passages": [1]}],
    )
    make_chunk(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id, text=sentence,
               roles=BOTH_ROLES, ai_generated=True)

    for term, found_through_its_summary in ((TERM, False), (SUMMARY_ONLY_TERM, True)):
        body = session_client.client.get(SEARCH_URL, {"q": term}).json()
        [result] = body["meetings"]["results"]
        assert result["source_id"] == str(meeting.id)
        assert result["snippet_ai_generated"] is found_through_its_summary
        assert summary_of(result) == NO_SUMMARY


def test_nothing_of_a_restricted_documents_summary_reaches_an_employee(
    employee_client, administrator_client, shared_corpus, restricted_document
):
    """Invariant 1. The summary is read through the scoped query that admitted the result, so an
    Employee's search that would match the Administrator-only document, by its title or by its
    passage, returns nothing of it, and no word of its summary is anywhere in the body. Asserted
    against the raw body, as the leak test above is."""
    shared, _ = shared_corpus
    summarise(shared, summary=SUMMARY, key_points=KEY_POINTS)
    summarise(restricted_document, summary=RESTRICTED_SUMMARY, key_points=[RESTRICTED_KEY_POINT])

    by_title = employee_client.get(SEARCH_URL, {"q": RESTRICTED_TITLE_TERM})
    by_passage = employee_client.get(SEARCH_URL, {"q": TERM})

    assert by_title.status_code == 200
    assert by_title.json() == {"query": RESTRICTED_TITLE_TERM, **NOTHING_FOUND}
    # The Employee is shown the summary of the document they may read, and only that one.
    [visible] = by_passage.json()["documents"]["results"]
    assert summary_of(visible) == (SUMMARY, KEY_POINTS, False)
    for response in (by_title, by_passage):
        raw = response.content.decode()
        for trace in (RESTRICTED_SUMMARY, "bonus pool", RESTRICTED_KEY_POINT, "two million",
                      str(restricted_document.id)):
            assert trace not in raw

    # The mirror: the same search by title, as an Administrator, returns the document and its
    # summary, so a search that showed nobody anything could not pass.
    [admitted] = administrator_client.get(SEARCH_URL, {"q": RESTRICTED_TITLE_TERM}).json()["documents"]["results"]
    assert admitted["source_id"] == str(restricted_document.id)
    assert summary_of(admitted) == (RESTRICTED_SUMMARY, [RESTRICTED_KEY_POINT], False)


def test_a_term_found_only_in_a_summary_finds_nothing_and_is_recorded_as_any_empty_search_is(
    session_client, shared_corpus
):
    """D-139: display only. Search matches a title or a passage and never a summary, so a word
    that only a summary and its key points hold finds nothing, from either role. What is recorded
    is what a search that found nothing has always recorded: one ``SearchLog`` row, the term as
    typed, a count of zero, which is FR-19's evidence of a gap."""
    document, _ = shared_corpus
    summarise(document, summary=f"The team hired a {SUMMARY_ONLY_TERM} for the launch.",
              key_points=[f"The {SUMMARY_ONLY_TERM} is moored at the depot."])

    in_a_summary_only = session_client.client.get(SEARCH_URL, {"q": SUMMARY_ONLY_TERM})
    in_nothing = session_client.client.get(SEARCH_URL, {"q": UNMATCHED_TERM})

    assert in_a_summary_only.status_code == 200
    assert in_a_summary_only.json() == {"query": SUMMARY_ONLY_TERM, **NOTHING_FOUND}
    assert in_nothing.json() == {"query": UNMATCHED_TERM, **NOTHING_FOUND}
    rows = {row.query_text: row for row in SearchLog.objects.all()}
    assert SearchLog.objects.count() == 2
    assert set(rows) == {SUMMARY_ONLY_TERM, UNMATCHED_TERM}
    for row in rows.values():
        assert (row.user_id, row.result_count) == (session_client.user.id, 0)
    # And the summary is there to be shown: a term the passage holds finds the document with it.
    [found] = session_client.client.get(SEARCH_URL, {"q": TERM}).json()["documents"]["results"]
    assert SUMMARY_ONLY_TERM in found["summary"]
