"""FR-16's summary as source material, seen through FR-12's routes (UC-04; D-125 choice 1).

UC-04: "The summary is available to UC07 Query Organisational Knowledge as source material,
subject to the permission scope applying to the parent document", and on failure "it is never
presented to a user nor cited as a source". A Ready summary is indexed as passages of the meeting
itself, marked ``ai_generated``. These tests read the two payloads that can show one:

- ``GET /api/search``: a meeting found through its summary is one result, and its snippet says it
  is AI content (``snippet_ai_generated``); where the transcript matches too, the transcript's own
  words are shown.
- ``POST /api/ask`` and the reopened thread: a consulted passage says whether it is AI content
  (``ai_generated``), and its source is the meeting.

And the scope: an Employee reaches nothing of an Administrator-only meeting's summary by either
route (invariant 1). The chunk-level rules (the stamp, the cascade, deletion) are in
apps/meetings/tests/test_summary_index.py.
"""

from math import sqrt

import pytest
from django.conf import settings

import apps.ai
from apps.ai.base import EmbeddingResult, Statement, StatementList
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    RELEVANCE_THRESHOLD,
    ROLE_NAMES,
    SOURCE_TYPES,
    SUMMARY_READY,
    SUMMARY_UNAVAILABLE,
)
from apps.ai.base import ProviderUnavailable
from apps.documents.models import ContentChunk
from apps.meetings.models import MeetingSummary
from apps.meetings.summaries import run_summary
from apps.meetings.tests.summary_builders import draft, element, ingest, transcript

pytestmark = pytest.mark.django_db

_, MEETING_SOURCE_TYPE = SOURCE_TYPES
SEARCH_URL = "/api/search"
ASK_URL = "/api/ask"

TITLE = "Quarterly planning"
# In the summary and nowhere in the transcript or the title.
SUMMARY_ONLY_TERM = "zeppelin"
SENTENCE = f"The team agreed to hire a {SUMMARY_ONLY_TERM} for the launch."
# In the transcript (every token of ``transcript()`` starts with its seed) and in the summary.
SHARED_TERM = "budget7"
SHARED_SENTENCE = f"The line {SHARED_TERM} was discussed."
QUESTION = "What did the team agree to hire for the launch?"

NEAREST = 0.95
assert RELEVANCE_THRESHOLD < NEAREST


def _wide(*components) -> list[float]:
    return list(components) + [0.0] * (settings.EMBEDDING_DIMENSION - len(components))


QUERY = _wide(1.0)


def _at_cosine(value: float) -> list[float]:
    return _wide(value, sqrt(1.0 - value * value))


class _CitingService:
    """A double: every question embeds to QUERY, and the reply cites the first passage supplied."""

    def embed(self, texts, *, input_type=None):
        return EmbeddingResult(
            vectors=[list(QUERY)], model=STUB_EMBEDDING_MODEL, dimension=settings.EMBEDDING_DIMENSION
        )

    def generate_statements(self, question, passages):
        return StatementList(
            statements=[Statement(text="A grounded statement.", chunk_id=passages[0].chunk_id)]
        )


def summarised_meeting(stub_ai_service, capture, *, visible_to_roles=ROLE_NAMES, narrative=None):
    """A meeting ingested through FR-09 whose summary has run: Ready, and indexed."""
    stub_ai_service.summary = draft(narrative=narrative or [element(SENTENCE), element(SHARED_SENTENCE)])
    with capture(execute=True):
        meeting = ingest(title=TITLE, visible_to_roles=visible_to_roles)
    assert MeetingSummary.objects.get(meeting=meeting).status == SUMMARY_READY
    return meeting


def nearest_is_the_summary(meeting):
    """Put the summary's chunk nearest the query and the transcript's chunks at right angles to it."""
    chunks = ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id)
    chunks.filter(ai_generated=True).update(embedding=_at_cosine(NEAREST))
    chunks.filter(ai_generated=False).update(embedding=_wide(0.0, 0.0, 1.0))
    [summary_chunk] = chunks.filter(ai_generated=True)
    return summary_chunk


# --- GET /api/search -------------------------------------------------------------------------


def test_a_meeting_found_only_through_its_summary_is_one_result_marked_as_ai_content(
    session_client, stub_ai_service, django_capture_on_commit_callbacks
):
    meeting = summarised_meeting(stub_ai_service, django_capture_on_commit_callbacks)

    body = session_client.client.get(SEARCH_URL, {"q": SUMMARY_ONLY_TERM}).json()

    [result] = body["meetings"]["results"]
    assert body["meetings"]["count"] == 1 and body["total_count"] == 1
    assert result["source_id"] == str(meeting.id)
    assert result["source_type"] == MEETING_SOURCE_TYPE
    assert SUMMARY_ONLY_TERM in result["snippet"]
    assert result["snippet_ai_generated"] is True


def test_where_the_transcript_matches_too_the_snippet_is_the_transcripts_own_words(
    employee_client, stub_ai_service, django_capture_on_commit_callbacks
):
    summarised_meeting(stub_ai_service, django_capture_on_commit_callbacks)

    [result] = employee_client.get(SEARCH_URL, {"q": SHARED_TERM}).json()["meetings"]["results"]

    assert result["snippet_ai_generated"] is False
    assert SHARED_TERM in result["snippet"]
    assert SHARED_SENTENCE not in result["snippet"]


def test_a_title_match_shows_the_opening_of_the_transcript_never_of_the_summary(
    employee_client, stub_ai_service, django_capture_on_commit_callbacks
):
    """FR-12 shows the opening of the item for a title-only match. A summary passage shares the
    meeting's source and starts its own ``chunk_index`` at 0, and it must not be taken for that
    opening; nor may the summary's index text carry the title, or a search for the title would
    match the summary itself (D-125's dated correction)."""
    meeting = summarised_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    [summary_chunk] = ContentChunk.objects.filter(source_id=meeting.id, ai_generated=True)
    assert "Quarterly" not in summary_chunk.chunk_text and TITLE not in summary_chunk.chunk_text

    [result] = employee_client.get(SEARCH_URL, {"q": "Quarterly"}).json()["meetings"]["results"]

    assert result["snippet_ai_generated"] is False
    assert result["snippet"].startswith("budget0 budget1")


def test_an_employee_cannot_find_an_administrator_only_meeting_through_its_summary(
    employee_client, administrator_client, stub_ai_service, django_capture_on_commit_callbacks
):
    meeting = summarised_meeting(
        stub_ai_service, django_capture_on_commit_callbacks, visible_to_roles=[ADMINISTRATOR_ROLE_NAME]
    )

    withheld = employee_client.get(SEARCH_URL, {"q": SUMMARY_ONLY_TERM})
    # The whole body: the term echoed back, two empty groups and a zero, with no sign of a meeting.
    assert withheld.json() == {
        "query": SUMMARY_ONLY_TERM,
        "documents": {"count": 0, "results": []},
        "meetings": {"count": 0, "results": []},
        "total_count": 0,
    }

    # The mirror, so a search that found nothing for anybody could not pass.
    [result] = administrator_client.get(SEARCH_URL, {"q": SUMMARY_ONLY_TERM}).json()["meetings"]["results"]
    assert result["source_id"] == str(meeting.id)


def test_a_failed_summary_is_not_searchable(
    employee_client, stub_ai_service, django_capture_on_commit_callbacks
):
    """UC-04, on failure: "never presented to a user nor cited as a source"."""

    def fails(title, passages):
        raise ProviderUnavailable("the provider is down")

    stub_ai_service.summary = fails
    with django_capture_on_commit_callbacks(execute=True):
        meeting = ingest(title=TITLE)
    assert MeetingSummary.objects.get(meeting=meeting).status == SUMMARY_UNAVAILABLE

    assert not ContentChunk.objects.filter(source_id=meeting.id, ai_generated=True).exists()
    # The transcript is searchable all the same (invariant 8, NFR-20).
    assert employee_client.get(SEARCH_URL, {"q": "budget7"}).json()["total_count"] == 1


# --- POST /api/ask and the reopened thread ----------------------------------------------------


def test_an_answer_drawn_from_a_summary_says_the_passage_is_ai_content_and_names_the_meeting(
    session_client, stub_ai_service, django_capture_on_commit_callbacks, monkeypatch
):
    meeting = summarised_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    summary_chunk = nearest_is_the_summary(meeting)
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: _CitingService())

    response = session_client.client.post(ASK_URL, {"question": QUESTION}, format="json")

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    assert [statement["chunk_id"] for statement in body["statements"]] == [str(summary_chunk.id)]
    [source] = [s for s in body["sources"] if s["source_id"] == str(meeting.id)]
    assert source["source_type"] == MEETING_SOURCE_TYPE and source["title"] == TITLE
    by_id = {passage["chunk_id"]: passage for passage in source["passages"]}
    cited = by_id[str(summary_chunk.id)]
    assert cited["ai_generated"] is True
    # The summary's own sentences and nothing added: the flag is what says it is AI content.
    assert cited["text"] == f"{SENTENCE} {SHARED_SENTENCE}"
    # Every other passage of the meeting that was consulted is the transcript's, and says so.
    assert all(p["ai_generated"] is False for p in source["passages"] if p["chunk_id"] != str(summary_chunk.id))


def test_a_reopened_thread_marks_the_summary_passage_as_the_live_reply_did(
    employee_client, stub_ai_service, django_capture_on_commit_callbacks, monkeypatch
):
    meeting = summarised_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    summary_chunk = nearest_is_the_summary(meeting)
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: _CitingService())
    conversation_id = employee_client.post("/api/conversations", {}, format="json").json()["conversation_id"]
    asked = employee_client.post(
        ASK_URL, {"question": QUESTION, "conversation_id": conversation_id}, format="json"
    )
    assert asked.status_code == 200 and asked.json()["answered"] is True

    [turn] = employee_client.get(f"/api/conversations/{conversation_id}").json()["turns"]

    passages = {p["chunk_id"]: p for source in turn["sources"] for p in source["passages"]}
    assert passages[str(summary_chunk.id)]["ai_generated"] is True


def test_an_employee_is_never_answered_from_an_administrator_only_meetings_summary(
    employee_client, administrator_client, stub_ai_service, django_capture_on_commit_callbacks, monkeypatch
):
    meeting = summarised_meeting(
        stub_ai_service, django_capture_on_commit_callbacks, visible_to_roles=[ADMINISTRATOR_ROLE_NAME]
    )
    summary_chunk = nearest_is_the_summary(meeting)
    assert summary_chunk.visible_to_roles == [ADMINISTRATOR_ROLE_NAME]
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: _CitingService())

    withheld = employee_client.post(ASK_URL, {"question": QUESTION}, format="json")

    assert withheld.status_code == 200
    assert withheld.json()["answered"] is False
    raw = withheld.content.decode()
    assert str(meeting.id) not in raw and str(summary_chunk.id) not in raw and SUMMARY_ONLY_TERM not in raw

    # The mirror: the Administrator, whom the meeting admits, is answered from it.
    answered = administrator_client.post(ASK_URL, {"question": QUESTION}, format="json").json()
    assert answered["answered"] is True
    assert [s["source_id"] for s in answered["sources"]] == [str(meeting.id)]


def test_regenerating_replaces_what_search_finds(
    employee_client, stub_ai_service, django_capture_on_commit_callbacks
):
    """Only the current summary is indexed: the previous one's words stop being found."""
    meeting = summarised_meeting(stub_ai_service, django_capture_on_commit_callbacks)
    stub_ai_service.summary = draft(narrative=[element("The team agreed to hire a gondola instead.")])
    with django_capture_on_commit_callbacks(execute=True):
        from apps.meetings.summaries import request_summary

        summary, started = request_summary(meeting)
    assert started and MeetingSummary.objects.get(pk=summary.pk).status == SUMMARY_READY
    assert run_summary(summary.pk).status == SUMMARY_READY  # a second call changes nothing

    assert employee_client.get(SEARCH_URL, {"q": SUMMARY_ONLY_TERM}).json()["total_count"] == 0
    [result] = employee_client.get(SEARCH_URL, {"q": "gondola"}).json()["meetings"]["results"]
    assert result["snippet_ai_generated"] is True
    assert ContentChunk.objects.filter(source_id=meeting.id, ai_generated=True).count() == 1
    assert transcript().split()[0] in ContentChunk.objects.filter(
        source_id=meeting.id, ai_generated=False
    ).order_by("chunk_index").first().chunk_text
