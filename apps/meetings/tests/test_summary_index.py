"""The summary as source material: its index entries (D-125 choice 1; CLAUDE.md invariants 1 and 2).

UC-04: "The summary is available to UC07 Query Organisational Knowledge as source material,
subject to the permission scope applying to the parent document", and in the failed state "it is
never presented to a user nor cited as a source". A Ready summary is therefore chunked and embedded
as ``ContentChunks`` rows of **the meeting itself**: the meeting's source type and id, the
meeting's ``visible_to_roles``, and ``ai_generated`` true, which is the one thing that says the
passage is AI content (NFR-15). This file holds those rows to what the meeting's own chunks are
held to, because a summary restates the meeting and so leaks exactly what the transcript would:

- **The stamp.** A summary of an Administrator-only meeting is Administrator-only from the moment
  it is written, and no Employee query can select it.
- **The stamp under a race.** A meeting narrowed while the model was working yields chunks with
  the NEW scope: the scope is read under the meeting's row lock in the storing transaction.
- **The cascade** (D-47). Changing the meeting's visibility re-stamps the summary's chunks with
  the transcript's, by ``save()`` and by a queryset ``update()``.
- **Deletion.** Deleting the meeting removes the summary, its action items and its chunks, also
  when the delete lands while a run is out.
- **Only a Ready summary is indexed, in the transaction that makes it Ready.** A failed run
  writes no chunk; a summary none of whose chunks could be embedded is not Ready at all, and the
  previous summary's chunks stay.

What the routes show of these rows is apps/api/tests/test_summary_in_retrieval.py's.
"""

from __future__ import annotations

import logging

import pytest
from django.conf import settings

from apps.ai.base import INPUT_TYPE_DOCUMENT, MalformedSummary, ProviderRefused, ProviderUnavailable
from apps.ai.prefixes import document_text
from apps.ai.testing import STUB_EMBEDDING_MODEL, StubAIService
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_EMBED_ATTEMPTS,
    MEETING_INDEXED,
    SOURCE_TYPES,
    SUMMARY_FAILED_INDEXING,
    SUMMARY_READY,
    SUMMARY_UNAVAILABLE,
)
from apps.documents.models import ContentChunk
from apps.ingestion.chunking import split_into_overlapping_chunks
from apps.ingestion.tests.ai_doubles import ScriptedEmbedService, install
from apps.meetings.deletion import delete_meeting
from apps.meetings.models import ActionItem, Meeting, MeetingSummary
from apps.meetings.summaries import (
    add_action_item,
    current_summary,
    request_summary,
    retry_queue,
    retry_summary,
    run_summary,
    summary_index_text,
)
from apps.meetings.tests.summary_builders import (
    action,
    draft,
    element,
    ingest,
    raising,
    regenerate,
    summarised,
    transcript,
)
from apps.retrieval.scoping import candidate_chunks, scoped_chunks

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]
EMPLOYEE_ONLY = [EMPLOYEE_ROLE_NAME]

TITLE = "Zeppelin procurement"
# A word that is in the summary and nowhere in the transcript, the title or an action item.
MARKER = "wombat"
NARRATIVE = [element(f"The {MARKER} programme was reviewed.", 1), element("It was paused until Easter.", 1)]
DECISIONS = [element("The programme is paused until Easter.", 1)]
HIGHLIGHTS = [element("Costs were twice the estimate.", 1), element("Two suppliers withdrew.", 1)]
ACTION_ITEMS = [action("Telephone the Carlton depot", owner="Quentin", due="next Friday")]
DRAFT = draft(narrative=NARRATIVE, decisions=DECISIONS, highlights=HIGHLIGHTS, action_items=ACTION_ITEMS)
INDEX_TEXT = (
    f"The {MARKER} programme was reviewed. It was paused until Easter.\n"
    "The programme is paused until Easter.\n"
    "Costs were twice the estimate.\n"
    "Two suppliers withdrew."
)


def chunks_of(meeting):
    return ContentChunk.objects.filter(source_type=MEETING_SOURCE_TYPE, source_id=meeting.id)


def summary_chunks(meeting):
    return chunks_of(meeting).filter(ai_generated=True)


def transcript_chunks(meeting):
    return chunks_of(meeting).filter(ai_generated=False)


def ids(queryset) -> set:
    return set(queryset.values_list("id", flat=True))


def assert_every_chunk_carries_the_meetings_scope(meeting) -> list:
    """Invariant 2's condition, read from the stored meeting row and held against EVERY chunk of
    the meeting, the summary's and the transcript's alike. Returns that scope."""
    stored = Meeting.objects.get(pk=meeting.pk).visible_to_roles
    stamps = list(chunks_of(meeting).values_list("ai_generated", "visible_to_roles"))
    assert {ai for ai, _ in stamps} == {True, False}, "the meeting must have chunks of both kinds"
    assert all(stamp == stored for _, stamp in stamps), f"meeting carries {stored}; its chunks carry {stamps}"
    return stored


@pytest.fixture
def summarised_meeting(stub_ai_service, django_capture_on_commit_callbacks):
    """A meeting visible to both roles whose summary, DRAFT, is Ready and indexed."""
    stub_ai_service.summary = DRAFT
    return summarised(django_capture_on_commit_callbacks, title=TITLE)


# --- What is indexed -----------------------------------------------------------------------------


def test_a_ready_summary_is_indexed_as_the_meetings_own_passages(summarised_meeting):
    meeting = summarised_meeting
    summary = MeetingSummary.objects.get(meeting=meeting)
    assert summary.status == SUMMARY_READY

    [chunk] = summary_chunks(meeting)

    # The meeting's own source type and id: no third source type, so the cascade, deletion and
    # the scoped source lookups reach these rows by construction.
    assert (chunk.source_type, chunk.source_id) == (MEETING_SOURCE_TYPE, meeting.id)
    assert chunk.ai_generated is True
    assert chunk.visible_to_roles == meeting.visible_to_roles == BOTH_ROLES
    # The model and width the provider answered with, recorded as for any chunk (risk R10).
    assert (chunk.embedding_model, chunk.embedding_dimension) == (STUB_EMBEDDING_MODEL, settings.EMBEDDING_DIMENSION)
    assert len(chunk.embedding) == settings.EMBEDDING_DIMENSION
    assert chunk.chunk_index == 0


def test_the_chunks_text_is_the_summarys_own_sentences_and_nothing_else(summarised_meeting):
    """The narrative joined, then each decision, then each highlight, one to a line. No heading,
    title, date or label: every word of a chunk is found by FR-12's keyword search, so a line
    naming the meeting would make a search for its title show the summary in place of the
    transcript's opening. ``ai_generated`` alone says the passage is AI content."""
    meeting = summarised_meeting
    summary = MeetingSummary.objects.get(meeting=meeting)

    [chunk] = summary_chunks(meeting)

    assert chunk.chunk_text == INDEX_TEXT == summary_index_text(summary)
    assert chunk.chunk_text.splitlines()[0] == summary.summary_text
    lowered = chunk.chunk_text.lower()
    for absent in (TITLE.lower(), "zeppelin", "ai-generated", "summary", "decisions:", "highlights:",
                   "november", "2026"):
        assert absent not in lowered, absent


def test_the_action_items_are_not_indexed(summarised_meeting):
    """D-125 choice 1: the items are the table people edit, and an index entry that disagreed
    with a record a person had corrected would be the defect. Not the description, the owner as
    said, or the deadline as said."""
    meeting = summarised_meeting
    [item] = ActionItem.objects.filter(meeting=meeting)
    assert (item.description, item.owner_name, item.due_text) == ("Telephone the Carlton depot", "Quentin", "next Friday")

    indexed = " ".join(chunks_of(meeting).values_list("chunk_text", flat=True))

    for absent in ("Telephone", "Carlton", "depot", "Quentin", "next Friday"):
        assert absent not in indexed, absent
    assert MARKER in indexed  # the premise: the summary itself is there


def test_the_transcripts_own_chunks_are_never_marked_ai_generated(stub_ai_service, django_capture_on_commit_callbacks):
    stub_ai_service.summary = DRAFT
    text = transcript(1300)
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        meeting = ingest(title=TITLE, text=text)
    before = ids(chunks_of(meeting))
    assert len(before) == 3 and not summary_chunks(meeting).exists()  # indexed, and no summary yet

    callbacks[0]()

    assert ids(transcript_chunks(meeting)) == before  # the same rows, untouched by the run
    assert list(transcript_chunks(meeting).order_by("chunk_index").values_list("chunk_text", flat=True)) == [
        chunk.text for chunk in split_into_overlapping_chunks(text)
    ]
    assert summary_chunks(meeting).count() == 1
    assert not ContentChunk.objects.filter(source_type=DOCUMENT_SOURCE_TYPE, ai_generated=True).exists()


def test_the_stored_text_is_never_the_prefixed_form_the_embedding_model_was_sent(
    stub_ai_service, django_capture_on_commit_callbacks, settings
):
    """EmbeddingGemma is sent ``title: ... | text: ...`` (apps/ai/prefixes.py), so the model still
    learns which meeting the summary is of. What is stored, and so searched and shown, is the
    summary's sentences alone."""
    settings.AI_PROVIDER = "flm"
    settings.FLM_EMBED_MODEL = "embed-gemma"
    stub_ai_service.summary = DRAFT

    meeting = summarised(django_capture_on_commit_callbacks, title=TITLE)

    [chunk] = summary_chunks(meeting)
    assert chunk.chunk_text == INDEX_TEXT
    sent = document_text(TITLE, INDEX_TEXT)
    assert sent != INDEX_TEXT and TITLE in sent  # the premise: this model does take a prefix
    assert stub_ai_service.embed_calls[-1] == [sent]
    assert stub_ai_service.embed_input_types[-1] == INPUT_TYPE_DOCUMENT


def test_a_long_summary_is_indexed_as_several_chunks_all_marked_and_stamped(
    stub_ai_service, django_capture_on_commit_callbacks
):
    sentences = [" ".join(f"s{number}w{word}" for word in range(90)) + "." for number in range(1, 7)]
    stub_ai_service.summary = draft(narrative=[element(sentence, 1) for sentence in sentences])

    meeting = summarised(django_capture_on_commit_callbacks, visible_to_roles=ADMINISTRATOR_ONLY)

    summary = MeetingSummary.objects.get(meeting=meeting)
    expected = [chunk.text for chunk in split_into_overlapping_chunks(summary_index_text(summary))]
    assert len(expected) == 2
    stored = list(summary_chunks(meeting).order_by("chunk_index"))
    assert [chunk.chunk_text for chunk in stored] == expected
    assert [chunk.chunk_index for chunk in stored] == [0, 1]
    assert all(chunk.visible_to_roles == ADMINISTRATOR_ONLY for chunk in stored)


# --- The stamp: invariant 1 at the row -------------------------------------------------------------


def test_a_summary_of_an_administrator_only_meeting_is_administrator_only_and_no_employee_query_selects_it(
    stub_ai_service, django_capture_on_commit_callbacks
):
    """THE one that matters. The summary restates the meeting, so it is restricted exactly as the
    meeting is, from the transaction that writes it. ``scoped_chunks`` is the FR-11 candidate set
    and the keyword search's predicate: a row absent from it is never ranked, never counted and
    never sent to the AI service."""
    stub_ai_service.summary = DRAFT
    restricted = summarised(django_capture_on_commit_callbacks, title=TITLE, visible_to_roles=ADMINISTRATOR_ONLY)
    shared = summarised(django_capture_on_commit_callbacks, title="Shared meeting", visible_to_roles=BOTH_ROLES)
    assert MeetingSummary.objects.get(meeting=restricted).status == SUMMARY_READY

    [chunk] = summary_chunks(restricted)
    assert chunk.visible_to_roles == ADMINISTRATOR_ONLY
    assert_every_chunk_carries_the_meetings_scope(restricted)

    for employee_scope in (
        scoped_chunks(role_name=EMPLOYEE_ROLE_NAME),
        candidate_chunks(role_name=EMPLOYEE_ROLE_NAME, embedding_model=STUB_EMBEDDING_MODEL),
    ):
        assert not employee_scope.filter(source_id=restricted.id).exists()
        assert not employee_scope.filter(pk=chunk.pk).exists()
        # The comparison that makes the absence mean something: the shared meeting's summary IS there.
        assert employee_scope.filter(source_id=shared.id, ai_generated=True).count() == 1
        assert not any(MARKER in text and source == restricted.id
                       for source, text in employee_scope.values_list("source_id", "chunk_text"))

    administrator_scope = scoped_chunks(role_name=ADMINISTRATOR_ROLE_NAME)
    assert administrator_scope.filter(pk=chunk.pk).exists()
    assert administrator_scope.filter(ai_generated=True).count() == 2


@pytest.mark.parametrize(
    "visible_to_roles,readers",
    [
        (BOTH_ROLES, {EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME}),
        (ADMINISTRATOR_ONLY, {ADMINISTRATOR_ROLE_NAME}),
        # D-66: an Administrator reads everything marked for Employees.
        (EMPLOYEE_ONLY, {EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME}),
        # Visible to nobody: the summary is too.
        ([], set()),
    ],
    ids=["both", "administrator-only", "employee-only", "nobody"],
)
def test_a_summarys_chunks_are_readable_by_exactly_the_roles_that_read_the_meeting(
    stub_ai_service, django_capture_on_commit_callbacks, visible_to_roles, readers
):
    stub_ai_service.summary = DRAFT

    meeting = summarised(django_capture_on_commit_callbacks, visible_to_roles=visible_to_roles)

    assert MeetingSummary.objects.get(meeting=meeting).status == SUMMARY_READY
    assert assert_every_chunk_carries_the_meetings_scope(meeting) == visible_to_roles
    for role_name in (EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME):
        selected = scoped_chunks(role_name=role_name).filter(source_id=meeting.id)
        assert selected.filter(ai_generated=True).exists() == (role_name in readers), role_name
        # And never a different answer for the summary than for the transcript it restates.
        assert selected.filter(ai_generated=True).exists() == selected.filter(ai_generated=False).exists()


# --- The stamp under a race: the scope is read under the lock, in the storing transaction -----------


@pytest.mark.parametrize("write", ["queryset update", "save"])
def test_a_meeting_narrowed_while_the_model_was_working_yields_chunks_with_the_new_scope(
    stub_ai_service, django_capture_on_commit_callbacks, write
):
    """The run read the meeting before the call, when both roles could see it. The meeting is
    narrowed while the call is out. A run that stamped what it read at the start would write an
    Employee-readable summary of an Administrator-only meeting; the store re-reads under the
    meeting's row lock, so the chunks carry the scope the meeting has NOW."""
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        meeting = ingest(title=TITLE, visible_to_roles=BOTH_ROLES)

    def narrowed_meanwhile(title, passages):
        if write == "save":
            fresh = Meeting.objects.get(pk=meeting.pk)
            fresh.visible_to_roles = ADMINISTRATOR_ONLY
            fresh.save()
        else:
            Meeting.objects.filter(pk=meeting.pk).update(visible_to_roles=ADMINISTRATOR_ONLY)
        return DRAFT

    stub_ai_service.summary = narrowed_meanwhile
    callbacks[0]()

    assert MeetingSummary.objects.get(meeting=meeting).status == SUMMARY_READY
    [chunk] = summary_chunks(meeting)
    assert chunk.visible_to_roles == ADMINISTRATOR_ONLY
    assert assert_every_chunk_carries_the_meetings_scope(meeting) == ADMINISTRATOR_ONLY
    assert not scoped_chunks(role_name=EMPLOYEE_ROLE_NAME).filter(source_id=meeting.id).exists()


def test_a_meeting_widened_while_the_model_was_working_yields_chunks_with_the_new_scope(
    stub_ai_service, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        meeting = ingest(title=TITLE, visible_to_roles=ADMINISTRATOR_ONLY)

    def widened_meanwhile(title, passages):
        Meeting.objects.filter(pk=meeting.pk).update(visible_to_roles=BOTH_ROLES)
        return DRAFT

    stub_ai_service.summary = widened_meanwhile
    callbacks[0]()

    assert assert_every_chunk_carries_the_meetings_scope(meeting) == BOTH_ROLES
    assert scoped_chunks(role_name=EMPLOYEE_ROLE_NAME).filter(source_id=meeting.id, ai_generated=True).exists()


# --- The cascade (D-47): the summary's chunks follow the meeting, as the transcript's do -------------


def _narrow_by_save(meeting, roles):
    meeting.visible_to_roles = roles
    meeting.save()


def _narrow_by_save_with_update_fields(meeting, roles):
    meeting.visible_to_roles = roles
    meeting.save(update_fields=["visible_to_roles"])


def _narrow_by_queryset_update(meeting, roles):
    Meeting.objects.filter(pk=meeting.pk).update(visible_to_roles=roles)


def _narrow_by_bulk_update(meeting, roles):
    meeting.visible_to_roles = roles
    Meeting.objects.bulk_update([meeting], ["visible_to_roles"])


WRITE_PATHS = {
    "save()": _narrow_by_save,
    "save(update_fields)": _narrow_by_save_with_update_fields,
    "QuerySet.update()": _narrow_by_queryset_update,
    "bulk_update()": _narrow_by_bulk_update,
}


@pytest.mark.parametrize("write_path", list(WRITE_PATHS.values()), ids=list(WRITE_PATHS))
def test_narrowing_the_meeting_re_stamps_its_summary_chunks_with_its_transcripts(summarised_meeting, write_path):
    """Invariant 2: "Changing a source's visibility re-stamps every one of its chunks in the same
    transaction." Every one includes the summary's. Before: an Employee query selects the summary.
    After: it selects nothing of the meeting, by ``save()`` and by ``update()`` alike."""
    meeting = summarised_meeting
    assert scoped_chunks(role_name=EMPLOYEE_ROLE_NAME).filter(source_id=meeting.id, ai_generated=True).exists()

    write_path(meeting, ADMINISTRATOR_ONLY)

    assert assert_every_chunk_carries_the_meetings_scope(meeting) == ADMINISTRATOR_ONLY  # the write happened
    assert not scoped_chunks(role_name=EMPLOYEE_ROLE_NAME).filter(source_id=meeting.id).exists()
    assert scoped_chunks(role_name=ADMINISTRATOR_ROLE_NAME).filter(source_id=meeting.id, ai_generated=True).exists()


@pytest.mark.parametrize("write_path", list(WRITE_PATHS.values()), ids=list(WRITE_PATHS))
def test_widening_the_meeting_re_stamps_its_summary_chunks_too(
    stub_ai_service, django_capture_on_commit_callbacks, write_path
):
    stub_ai_service.summary = DRAFT
    meeting = summarised(django_capture_on_commit_callbacks, visible_to_roles=ADMINISTRATOR_ONLY)
    assert not scoped_chunks(role_name=EMPLOYEE_ROLE_NAME).filter(source_id=meeting.id).exists()

    write_path(meeting, BOTH_ROLES)

    assert assert_every_chunk_carries_the_meetings_scope(meeting) == BOTH_ROLES
    assert scoped_chunks(role_name=EMPLOYEE_ROLE_NAME).filter(source_id=meeting.id, ai_generated=True).exists()


def test_the_cascade_moves_the_stamp_on_a_summary_chunk_and_nothing_else(summarised_meeting):
    meeting = summarised_meeting
    [before] = summary_chunks(meeting).values("id", "chunk_text", "embedding_model", "embedding_dimension", "ai_generated")
    vector_before = list(summary_chunks(meeting).get().embedding)

    Meeting.objects.filter(pk=meeting.pk).update(visible_to_roles=ADMINISTRATOR_ONLY)

    [after] = summary_chunks(meeting).values("id", "chunk_text", "embedding_model", "embedding_dimension", "ai_generated")
    assert after == before
    assert list(summary_chunks(meeting).get().embedding) == vector_before


def test_narrowing_one_meeting_leaves_another_meetings_summary_alone(
    summarised_meeting, stub_ai_service, django_capture_on_commit_callbacks
):
    other = summarised(django_capture_on_commit_callbacks, title="Another meeting")

    Meeting.objects.filter(pk=summarised_meeting.pk).update(visible_to_roles=ADMINISTRATOR_ONLY)

    assert assert_every_chunk_carries_the_meetings_scope(other) == BOTH_ROLES
    assert assert_every_chunk_carries_the_meetings_scope(summarised_meeting) == ADMINISTRATOR_ONLY


def test_a_summary_written_after_a_narrowing_carries_the_narrowed_scope(
    summarised_meeting, stub_ai_service, django_capture_on_commit_callbacks
):
    """Narrow, then Regenerate: the new chunks are stamped from the meeting as it is, not as it
    was when the first summary was written."""
    meeting = summarised_meeting
    Meeting.objects.filter(pk=meeting.pk).update(visible_to_roles=ADMINISTRATOR_ONLY)

    regenerate(django_capture_on_commit_callbacks, Meeting.objects.get(pk=meeting.pk))

    assert assert_every_chunk_carries_the_meetings_scope(meeting) == ADMINISTRATOR_ONLY


# --- Regenerate replaces the summary's chunks and leaves the transcript's ----------------------------


def test_a_regenerate_replaces_the_summarys_chunks_and_leaves_the_transcripts(
    summarised_meeting, stub_ai_service, django_capture_on_commit_callbacks
):
    meeting = summarised_meeting
    old_summary_chunks = ids(summary_chunks(meeting))
    transcript_before = ids(transcript_chunks(meeting))
    assert len(old_summary_chunks) == 1 and transcript_before

    stub_ai_service.summary = draft(narrative=[element("The lighthouse lease was renewed.", 1)])
    second = regenerate(django_capture_on_commit_callbacks, meeting)

    assert second.status == SUMMARY_READY
    [chunk] = summary_chunks(meeting)  # one set, not two: the old summary is no longer searchable
    assert chunk.id not in old_summary_chunks
    assert chunk.chunk_text == "The lighthouse lease was renewed."
    assert not ContentChunk.objects.filter(pk__in=old_summary_chunks).exists()
    assert not any(MARKER in text for text in chunks_of(meeting).values_list("chunk_text", flat=True))
    assert ids(transcript_chunks(meeting)) == transcript_before
    # And the second run read the transcript, not the first summary.
    first_sent, second_sent = (passages for _, passages in stub_ai_service.summarise_calls)
    assert first_sent == second_sent == [meeting.transcript_text]


def test_a_regenerate_of_one_meeting_leaves_another_meetings_summary_chunks(
    summarised_meeting, stub_ai_service, django_capture_on_commit_callbacks
):
    other = summarised(django_capture_on_commit_callbacks, title="Another meeting")
    other_before = ids(summary_chunks(other))

    stub_ai_service.summary = draft(narrative=[element("The lighthouse lease was renewed.", 1)])
    regenerate(django_capture_on_commit_callbacks, summarised_meeting)

    assert ids(summary_chunks(other)) == other_before


# --- Deletion: the summary goes with its meeting -------------------------------------------------------


def test_deleting_the_meeting_removes_its_summaries_its_action_items_and_every_chunk(
    summarised_meeting, stub_ai_service, django_capture_on_commit_callbacks, employee
):
    meeting = summarised_meeting
    stub_ai_service.summary = None  # the survivor's summary is the stub's default, which has no MARKER
    other = summarised(django_capture_on_commit_callbacks, title="Unrelated survivor")
    stub_ai_service.summary = DRAFT
    regenerate(django_capture_on_commit_callbacks, meeting, requested_by=employee)  # two runs, one by a person
    add_action_item(meeting, description="Hand-added", owner=employee)
    assert MeetingSummary.objects.filter(meeting=meeting).count() == 2
    assert ActionItem.objects.filter(meeting=meeting).count() == 2
    assert summary_chunks(meeting).exists() and transcript_chunks(meeting).exists()

    delete_meeting(meeting)

    assert not Meeting.objects.filter(pk=meeting.pk).exists()
    assert not MeetingSummary.objects.filter(meeting_id=meeting.pk).exists()
    assert not ActionItem.objects.filter(meeting_id=meeting.pk).exists()
    assert not ContentChunk.objects.filter(source_id=meeting.pk).exists()  # the summary's and the transcript's
    assert not any(MARKER in text for text in ContentChunk.objects.values_list("chunk_text", flat=True))
    # Nothing of any other meeting moved, and the people stay.
    assert MeetingSummary.objects.filter(meeting=other).count() == 1
    assert ActionItem.objects.filter(meeting=other).count() == 1
    assert summary_chunks(other).count() == 1
    assert type(employee).objects.filter(pk=employee.pk).exists()


def test_a_meeting_deleted_while_the_model_was_working_leaves_no_summary_and_no_chunk(
    stub_ai_service, django_capture_on_commit_callbacks
):
    """The delete lands while the call is out. The reply that then arrives must not be stored: a
    summary chunk written for a deleted meeting would have no meeting row to be scoped through or
    deleted with, and would go on being retrieved."""
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        meeting = ingest(title=TITLE)
    summary = MeetingSummary.objects.get(meeting=meeting)

    def deleted_meanwhile(title, passages):
        delete_meeting(Meeting.objects.get(pk=meeting.pk))
        return DRAFT

    stub_ai_service.summary = deleted_meanwhile

    assert run_summary(summary.pk) is None
    callbacks[0]()  # and the runner's own path: nothing raised, nothing written

    assert not MeetingSummary.objects.exists()
    assert not ActionItem.objects.exists()
    assert not ContentChunk.objects.filter(source_id=meeting.pk).exists()
    assert not ContentChunk.objects.filter(ai_generated=True).exists()


# --- Only a Ready summary is indexed --------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        raising(ProviderUnavailable("stub outage")),
        raising(ProviderRefused("stub refusal")),
        raising(MalformedSummary("stub malformed")),
        draft(narrative=[element(f"A {MARKER} sentence citing nothing sent.", 41)]),
    ],
    ids=["provider_unavailable", "provider_refused", "malformed", "no_verified_narrative"],
)
def test_a_failed_run_writes_no_summary_chunk(stub_ai_service, django_capture_on_commit_callbacks, reply):
    """UC-04: in the failed state the summary "is never ... cited as a source"."""
    stub_ai_service.summary = reply

    meeting = summarised(django_capture_on_commit_callbacks, title=TITLE)

    assert MeetingSummary.objects.get(meeting=meeting).status == SUMMARY_UNAVAILABLE
    assert not ContentChunk.objects.filter(ai_generated=True).exists()
    assert transcript_chunks(meeting).exists()  # the transcript is indexed all the same (NFR-20)
    assert Meeting.objects.get(pk=meeting.pk).status == MEETING_INDEXED
    assert not any(MARKER in text for text in ContentChunk.objects.values_list("chunk_text", flat=True))


def fails_for_the_summary(failures=MAXIMUM_EMBED_ATTEMPTS, **kwargs):
    """A stub provider that cannot embed any text holding MARKER, and embeds everything else."""
    return ScriptedEmbedService(failures=failures, should_fail=lambda text: MARKER in text, **kwargs)


def test_a_summary_none_of_whose_chunks_could_be_embedded_is_not_ready_and_is_queued(
    monkeypatch, django_capture_on_commit_callbacks
):
    """D-125: "If every summary chunk fails to embed, the transaction is rolled back and the run
    fails." A Ready summary is always searchable; this one is not searchable, so it is not Ready."""
    service = install(monkeypatch, fails_for_the_summary())
    service.summary = DRAFT

    meeting = summarised(django_capture_on_commit_callbacks, title=TITLE)

    [summary] = MeetingSummary.objects.filter(meeting=meeting)
    assert (summary.status, summary.failure_reason) == (SUMMARY_UNAVAILABLE, SUMMARY_FAILED_INDEXING)
    assert SUMMARY_FAILED_INDEXING == "indexing_failed"
    assert summary.queued_for_retry is True and list(retry_queue()) == [summary]
    # Rolled back whole: no text on the row, no extracted item, no chunk.
    assert (summary.summary_text, summary.narrative, summary.generated_at, summary.action_items_extracted) == (
        "", [], None, None,
    )
    assert current_summary(meeting) is None
    assert not ActionItem.objects.filter(meeting=meeting).exists()
    assert not summary_chunks(meeting).exists()
    # The transcript is untouched and indexed (invariant 8).
    assert transcript_chunks(meeting).count() == 1
    assert Meeting.objects.get(pk=meeting.pk).status == MEETING_INDEXED
    # MAXIMUM_EMBED_ATTEMPTS is a total: the summary's one chunk was tried exactly three times.
    assert sum(1 for call in service.embed_calls if MARKER in call[0]) == MAXIMUM_EMBED_ATTEMPTS == 3
    assert len(service.summarise_calls) == 1  # the model was asked once; the embedding failed


def test_a_regenerate_that_cannot_be_indexed_rolls_back_and_the_previous_summary_stays_searchable(
    summarised_meeting, monkeypatch, django_capture_on_commit_callbacks
):
    """The storing transaction had already saved the new row Ready, replaced the extracted items
    and deleted the old summary's chunks when the embedding failed. All of it comes back: the
    previous summary is still the current one, with its own items and its own chunks."""
    meeting = summarised_meeting
    first = MeetingSummary.objects.get(meeting=meeting)
    old_chunks = ids(summary_chunks(meeting))
    old_items = sorted(ActionItem.objects.filter(meeting=meeting).values_list("pk", flat=True))
    assert len(old_chunks) == 1 and len(old_items) == 1

    service = install(monkeypatch, fails_for_the_summary())
    service.summary = draft(
        narrative=[element(f"A second {MARKER} summary that cannot be embedded.", 1)],
        action_items=[action("An item of the run that failed")],
    )
    second = regenerate(django_capture_on_commit_callbacks, meeting)

    assert (second.status, second.failure_reason, second.queued_for_retry) == (
        SUMMARY_UNAVAILABLE, SUMMARY_FAILED_INDEXING, True,
    )
    assert (second.summary_text, second.narrative) == ("", [])
    first.refresh_from_db()
    assert first.status == SUMMARY_READY
    assert current_summary(meeting) == first
    assert ids(summary_chunks(meeting)) == old_chunks  # the same rows, not rewritten copies
    assert summary_chunks(meeting).get().chunk_text == INDEX_TEXT
    assert sorted(ActionItem.objects.filter(meeting=meeting).values_list("pk", flat=True)) == old_items
    assert not ActionItem.objects.filter(description="An item of the run that failed").exists()


def test_a_summary_that_could_not_be_indexed_is_ready_and_indexed_once_its_retry_can_embed(
    monkeypatch, django_capture_on_commit_callbacks
):
    service = install(monkeypatch, fails_for_the_summary())
    service.summary = DRAFT
    meeting = summarised(django_capture_on_commit_callbacks, title=TITLE)
    failed = MeetingSummary.objects.get(meeting=meeting)
    assert failed.failure_reason == SUMMARY_FAILED_INDEXING

    healthy = install(monkeypatch, StubAIService(summary=DRAFT))
    retried = retry_summary(failed)

    assert (retried.pk, retried.status, retried.failure_reason) == (failed.pk, SUMMARY_READY, "")
    assert summary_chunks(meeting).get().chunk_text == INDEX_TEXT
    assert len(healthy.summarise_calls) == 1
    assert list(retry_queue()) == []


def test_a_refused_embedding_fails_the_run_on_its_first_attempt(monkeypatch, django_capture_on_commit_callbacks):
    """D-118: a refusal would be refused again, so the chunk fails at once and the run with it."""
    service = install(monkeypatch, fails_for_the_summary(error=ProviderRefused("stub refusal")))
    service.summary = DRAFT

    meeting = summarised(django_capture_on_commit_callbacks, title=TITLE)

    summary = MeetingSummary.objects.get(meeting=meeting)
    assert (summary.status, summary.failure_reason) == (SUMMARY_UNAVAILABLE, SUMMARY_FAILED_INDEXING)
    assert sum(1 for call in service.embed_calls if MARKER in call[0]) == 1


def test_a_summary_some_of_whose_chunks_could_be_embedded_is_ready_with_those(
    monkeypatch, django_capture_on_commit_callbacks, caplog
):
    """Pinned as it is written: only a summary with NO embedded chunk fails. One whose second
    chunk could not be embedded is Ready and searchable through its first, and the shortfall is
    logged for the operator. There is no "partially indexed" state for a summary to report it in."""
    sentences = [" ".join(f"s{number}w{word}" for word in range(90)) + "." for number in range(1, 7)]
    only_in_the_second_chunk = "s6w80"
    service = install(
        monkeypatch,
        ScriptedEmbedService(failures=MAXIMUM_EMBED_ATTEMPTS, should_fail=lambda text: only_in_the_second_chunk in text),
    )
    service.summary = draft(narrative=[element(sentence, 1) for sentence in sentences])

    with caplog.at_level(logging.WARNING, logger="apps.meetings.summaries"):
        meeting = summarised(django_capture_on_commit_callbacks)

    summary = MeetingSummary.objects.get(meeting=meeting)
    expected = [chunk.text for chunk in split_into_overlapping_chunks(summary_index_text(summary))]
    assert len(expected) == 2 and only_in_the_second_chunk not in expected[0]  # the premise
    assert summary.status == SUMMARY_READY
    assert [chunk.chunk_text for chunk in summary_chunks(meeting)] == [expected[0]]
    assert any("1 of its chunk(s) could not be embedded" in record.getMessage() for record in caplog.records)


def test_a_run_started_with_start_false_indexes_as_any_other(stub_ai_service, django_capture_on_commit_callbacks):
    stub_ai_service.summary = DRAFT
    meeting = summarised(django_capture_on_commit_callbacks, title=TITLE, visible_to_roles=ADMINISTRATOR_ONLY)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        summary, _ = request_summary(meeting, start=False)
    assert callbacks == []
    run_summary(summary.pk)

    assert summary_chunks(meeting).count() == 1
    assert assert_every_chunk_carries_the_meetings_scope(meeting) == ADMINISTRATOR_ONLY
