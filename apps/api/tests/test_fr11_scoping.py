"""FR-11 permission-aware retrieval scoping, at the HTTP surface. **The evidence file.**

CLAUDE.md section 6 invariant 1, in full, is what this file exists to hold evidence for:

    Permission filtering happens before ranking, never after. FR-11 restricts the
    candidate set at retrieval. Material outside the user's scope must never reach the AI
    service, must never contribute to an answer, and its existence must not be disclosed —
    not by a result count, a total, or an error message that distinguishes "not found" from
    "not permitted". Filtering a ranked list afterwards is the wrong shape and will be
    caught in the demo.

``apps/retrieval/tests/test_scoping.py`` tests the predicate: that the role condition is in
the compiled SQL, that both predicates must pass, that the scope is re-read per request.
This file tests the **boundary as a client experiences it** — every route that can return
material, or a number derived from material, from an Employee session and from an
Administrator session, with content the other role owns. Four absences are asserted on the
answer path, and the fourth is the one that is usually forgotten:

1. the answer — no statement drawn from the restricted passage;
2. the sources — not in ``sources``, not in ``partial_matches``;
3. the count — ``result_count`` does not include it, and no total anywhere discloses it;
4. **the payload sent to the AI service** — the restricted passage is not among the
   ``Passage`` objects handed to ``generate_statements``, and not in the prompt built from
   them. Asserted on the double's recorded call arguments, because that is the assertion
   that distinguishes "the answer did not mention it" from "the model never saw it", and
   invariant 1 is the second of those.

**What came before this file, honestly framed.** The eight scoped questions in
``scripts/citation_questions.json`` have scored 100% correctly-empty since item 0 and at
every harness run since. That result is weaker than it looks: the harness applied the role
filter *itself* while assembling a candidate set, with no retrieval code under test at all —
item 0 predates ``apps/retrieval/scoping.py`` existing. D-37 says the same thing in its
closing paragraph: "the scoped result measures the filter's output, not the filter under
test. FR-11 is evidenced at Stage 4 item 11, not here." **This file is item 11, and it is
the first real evidence for FR-11.** Saying so is worth more than another passing assertion.

**Every absence is paired with a presence.** An assertion that an Employee cannot see a
thing passes just as well against a system that returns nothing to anybody, which is the
weakest possible way to satisfy invariant 1. So each "absent for the Employee" test has a
named mirror asserting the same row **is** returned to an Administrator — the negative
control — and the pairs are adjacent in the file rather than left to be inferred.

**Assertions are against the raw rendered body.** ``response.content`` is every byte the
client is sent; a field-by-field check on parsed output passes a body that carried the
restricted title in a key the test did not think to look at. A serializer field nobody
anticipated is exactly the leak this file is for.

The autouse ``stub_ai_service`` is replaced by ``ControlledService``, whose query vector is
fixed, because the stub's vectors are seeded random and no score could be predicted from
them. The arrangement is the one ``apps/api/tests/test_ask.py`` and
``apps/retrieval/tests/test_pipeline.py`` use, restated rather than imported, following this
suite's habit of a test stating its own premise.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from math import sqrt

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

import apps.ai
from apps.ai.base import EmbeddingResult, Passage, Statement, StatementList
from apps.ai.prompting import build_user_prompt
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.api.answers import RECORD_ONLY_FIELDS
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    NO_ANSWER_MESSAGE,
    NO_ANSWER_REASONS,
    NO_STATEMENT_VERIFIED,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.meetings.models import Meeting, MeetingAttendee
from apps.retrieval.models import Conversation, QueryLog
from apps.retrieval.tests.scopes import unreadable_scope

pytestmark = pytest.mark.django_db

ASK_URL = "/api/ask"
SEARCH_URL = "/api/search"
DOCUMENTS_URL = "/api/documents"
MEETINGS_URL = "/api/meetings"
CONVERSATIONS_URL = "/api/conversations"

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]

# The question the whole file asks. Its only *good* answer lives in an Administrator-only
# document; the in-scope material is topically adjacent, which is the realistic shape — a
# scope that only ever excluded irrelevant material would never be tested by anything.
QUESTION = "How is annual leave accrued for senior staff?"
FOLLOW_UP = "And who signs those accruals off each year?"
assert MINIMUM_QUESTION_LENGTH <= len(QUESTION) <= MAXIMUM_QUESTION_LENGTH
assert MINIMUM_QUESTION_LENGTH <= len(FOLLOW_UP) <= MAXIMUM_QUESTION_LENGTH

# The search term, present in the body text of one in-scope and one out-of-scope item of
# each type, so the grouped counts differ between the roles in both groups (D-41).
TERM = "annual leave"
# Present in the restricted document's TITLE and in no chunk text at all, so it exercises
# the other branch of the search query — ``Q(title__icontains=...)`` — whose role predicate
# is on the source row rather than on the chunk.
TITLE_ONLY_TERM = "remuneration"

# --- The corpus: two permission levels, with real overlap between them ------------------

SHARED_DOCUMENT_TITLE = "Employee handbook"
SHARED_DOCUMENT_TEXT = "Staff may take annual leave once probation has ended."
SHARED_DOCUMENT_DEPARTMENT = "People"
SHARED_MEETING_TITLE = "All-hands briefing"
SHARED_MEETING_TEXT = "The group confirmed the annual leave embargo ends in March."

RESTRICTED_DOCUMENT_TITLE = "Board remuneration review"
RESTRICTED_DOCUMENT_TEXT = "Directors accrue annual leave at twice the ordinary rate."
RESTRICTED_DOCUMENT_DEPARTMENT = "Executive"
RESTRICTED_MEETING_TITLE = "Board in-camera session"
RESTRICTED_MEETING_TEXT = "The chair recorded a further annual leave loading for directors."
UNATTENDED_MEETING_TITLE = "Audit committee wrap-up"
UNATTENDED_MEETING_TEXT = "The committee noted the audit timetable and closed the item."

# Cosines against QUERY. RELEVANCE_THRESHOLD is imported rather than assumed, so a re-tune
# (D-37 calls the value provisional) fails this file loudly instead of silently changing
# which exit each test takes.
BELOW = 0.10
ABOVE = 0.40
NEAREST = 0.95
assert BELOW < RELEVANCE_THRESHOLD < ABOVE < NEAREST

# How many chunks ``build_corpus`` writes. Stated as a constant because assertion 3 is
# about the difference between what the store holds and what a role may count.
CORPUS_CHUNKS = 5


def wide(*components) -> list[float]:
    return list(components) + [0.0] * (settings.EMBEDDING_DIMENSION - len(components))


QUERY = wide(1.0)

# A query vector orthogonal to every chunk ``at_cosine`` builds, so each of them scores 0.0
# against it: still a candidate, still ranked, and below any floor this project would set.
ELSEWHERE = wide(0.0, 0.0, 1.0)


def at_cosine(value: float) -> list[float]:
    """A unit vector whose cosine with QUERY is exactly ``value``."""
    return wide(value, sqrt(1.0 - value * value))


def make_chunk(*, source_type, source_id, text, roles, cosine, index=0):
    """A chunk stamped with a visibility scope, as ingestion stamps it (D-17)."""
    return ContentChunk.objects.create(
        source_type=source_type,
        source_id=source_id,
        chunk_index=index,
        chunk_text=text,
        embedding=at_cosine(cosine),
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )


def make_document(uploader, *, title, roles, text, cosine, department=""):
    document = Document.objects.create(
        title=title,
        file_type="pdf",
        uploaded_by=uploader,
        department=department,
        visible_to_roles=roles,
    )
    chunk = make_chunk(
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        text=text,
        roles=roles,
        cosine=cosine,
    )
    return document, chunk


def make_meeting(*, title, roles, text, cosine, attendees=(), meeting_date=date(2026, 1, 5)):
    meeting = Meeting.objects.create(
        title=title,
        meeting_date=meeting_date,
        transcript_text=text,
        visible_to_roles=roles,
    )
    for user in attendees:
        # A participation record for FR-20, never an access control (D-16). It is written
        # here precisely so that an implementation consulting it would behave differently.
        MeetingAttendee.objects.create(meeting=meeting, user=user)
    chunk = make_chunk(
        source_type=MEETING_SOURCE_TYPE,
        source_id=meeting.id,
        text=text,
        roles=roles,
        cosine=cosine,
    )
    return meeting, chunk


@dataclass
class TwoLevelCorpus:
    """One realistic corpus at two permission levels, with overlap between them.

    Most scoping bugs only appear when the two levels genuinely overlap: the restricted
    document is the *nearest* thing to the question and shares the search term with the
    shared one, so a filter applied after ranking, or a count taken before filtering,
    changes the Employee's reply in a way a test can see.
    """

    shared_document: Document
    shared_document_chunk: ContentChunk
    shared_meeting: Meeting
    shared_meeting_chunk: ContentChunk
    restricted_document: Document
    restricted_document_chunk: ContentChunk
    restricted_meeting: Meeting
    restricted_meeting_chunk: ContentChunk
    unattended_meeting: Meeting
    unattended_meeting_chunk: ContentChunk

    @property
    def restricted_chunk_ids(self) -> set[str]:
        return {
            str(self.restricted_document_chunk.id),
            str(self.restricted_meeting_chunk.id),
            str(self.unattended_meeting_chunk.id),
        }

    @property
    def restricted_source_ids(self) -> set[str]:
        return {
            str(self.restricted_document.id),
            str(self.restricted_meeting.id),
            str(self.unattended_meeting.id),
        }

    @property
    def restricted_traces(self) -> tuple[str, ...]:
        """Every string whose appearance in an Employee's bytes would be a disclosure.

        Titles, passage text, identifiers and the department name — the department because
        "Executive" in a reply is itself a fact about material the reader cannot open.
        """
        return (
            RESTRICTED_DOCUMENT_TITLE,
            RESTRICTED_DOCUMENT_TEXT,
            RESTRICTED_DOCUMENT_DEPARTMENT,
            RESTRICTED_MEETING_TITLE,
            RESTRICTED_MEETING_TEXT,
            UNATTENDED_MEETING_TITLE,
            UNATTENDED_MEETING_TEXT,
            *sorted(self.restricted_source_ids),
            *sorted(self.restricted_chunk_ids),
        )

    def delete_restricted(self) -> None:
        """Remove every out-of-scope row, for the "is the reply any different?" test.

        ``ContentChunk.source_id`` is a plain UUID column rather than a foreign key, so the
        chunks are deleted explicitly: nothing cascades.
        """
        ContentChunk.objects.filter(
            id__in=[
                self.restricted_document_chunk.id,
                self.restricted_meeting_chunk.id,
                self.unattended_meeting_chunk.id,
            ]
        ).delete()
        MeetingAttendee.objects.filter(
            meeting__in=[self.restricted_meeting, self.unattended_meeting]
        ).delete()
        Meeting.objects.filter(
            id__in=[self.restricted_meeting.id, self.unattended_meeting.id]
        ).delete()
        Document.objects.filter(id=self.restricted_document.id).delete()


def build_corpus(
    employee, administrator, *, shared_cosine, restricted_roles=(ADMINISTRATOR_ROLE_NAME,)
) -> TwoLevelCorpus:
    """The corpus, with the in-scope material's distance from the question as the knob.

    ``shared_cosine=ABOVE`` gives an Employee an answerable question; ``BELOW`` gives them
    no-answer path A while the Administrator can still answer it, which is the headline
    arrangement: the only good answer lives out of scope.

    ``restricted_roles`` is the scope the restricted trio is INGESTED with, and it exists for
    section 8: passing ``BOTH_ROLES`` builds the identical corpus with those three items
    visible to everybody and their chunks stamped that way, so a test can then narrow them
    afterwards and hold the result to exactly the same four absences. The default is the
    static case — material an Employee never could see.
    """
    shared_document, shared_document_chunk = make_document(
        employee,
        title=SHARED_DOCUMENT_TITLE,
        roles=BOTH_ROLES,
        text=SHARED_DOCUMENT_TEXT,
        cosine=shared_cosine,
        department=SHARED_DOCUMENT_DEPARTMENT,
    )
    shared_meeting, shared_meeting_chunk = make_meeting(
        title=SHARED_MEETING_TITLE,
        roles=BOTH_ROLES,
        text=SHARED_MEETING_TEXT,
        cosine=shared_cosine - 0.05,
    )
    restricted_document, restricted_document_chunk = make_document(
        administrator,
        title=RESTRICTED_DOCUMENT_TITLE,
        roles=list(restricted_roles),
        text=RESTRICTED_DOCUMENT_TEXT,
        cosine=NEAREST,
        department=RESTRICTED_DOCUMENT_DEPARTMENT,
    )
    # D-16: the Employee ATTENDED this one. An implementation that read MeetingAttendees as
    # an access control would pass every other test in this file and fail the pair below.
    restricted_meeting, restricted_meeting_chunk = make_meeting(
        title=RESTRICTED_MEETING_TITLE,
        roles=list(restricted_roles),
        text=RESTRICTED_MEETING_TEXT,
        cosine=NEAREST - 0.05,
        attendees=[employee],
    )
    # The same scope, nobody recorded as an attendee — including the Administrator, who
    # must still be able to read it. Knowledge outlives the people who were in the room.
    unattended_meeting, unattended_meeting_chunk = make_meeting(
        title=UNATTENDED_MEETING_TITLE,
        roles=list(restricted_roles),
        text=UNATTENDED_MEETING_TEXT,
        cosine=BELOW,
    )
    return TwoLevelCorpus(
        shared_document=shared_document,
        shared_document_chunk=shared_document_chunk,
        shared_meeting=shared_meeting,
        shared_meeting_chunk=shared_meeting_chunk,
        restricted_document=restricted_document,
        restricted_document_chunk=restricted_document_chunk,
        restricted_meeting=restricted_meeting,
        restricted_meeting_chunk=restricted_meeting_chunk,
        unattended_meeting=unattended_meeting,
        unattended_meeting_chunk=unattended_meeting_chunk,
    )


@pytest.fixture
def overlapping_corpus(employee, administrator):
    """The shared material is answerable; the restricted material is nearer still.

    Named ``overlapping_corpus`` rather than ``corpus`` on purpose: conftest.py already has
    a ``corpus`` fixture, and it is the directory of committed sample FILES the ingestion
    tests upload. A module-local fixture of that name would shadow it inside this file and
    hand the wrong thing to a test that asked for the other one.
    """
    return build_corpus(employee, administrator, shared_cosine=ABOVE)


@pytest.fixture
def only_restricted_answers(employee, administrator):
    """The headline arrangement: nothing in an Employee's scope clears the floor."""
    return build_corpus(employee, administrator, shared_cosine=BELOW)


# --- The double -------------------------------------------------------------------------


class ControlledService:
    """An AIService whose query vector is known and whose generation reply is scripted.

    It records every call, and the recording is the point: the ``generate_calls`` log is
    where assertion 4 is made. ``embed_calls`` is checked too, because a query embedding is
    also a provider call, and a pipeline that embedded chunk text at query time would be
    sending material to the provider by another door.
    """

    def __init__(self, *, vector=None, statements=None):
        self.vector = QUERY if vector is None else vector
        self.statements = statements
        self.embed_calls: list[list[str]] = []
        self.generate_calls: list[tuple[str, list[Passage]]] = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[list(self.vector)],
            model=STUB_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        self.generate_calls.append((question, list(passages)))
        if self.statements is not None:
            return StatementList(statements=list(self.statements))
        return StatementList(
            statements=[Statement(text=f"Grounded in: {question}", chunk_id=passages[0].chunk_id)]
        )

    def health(self):  # pragma: no cover - the answer path does not check provider health
        raise AssertionError("the answer path does not check provider health")


def install(monkeypatch, double):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


@pytest.fixture
def service(monkeypatch):
    return install(monkeypatch, ControlledService())


def fabricating(monkeypatch):
    """A double that cites an identifier that was never supplied: no-answer path B."""
    return install(
        monkeypatch,
        ControlledService(statements=[Statement(text="Invented.", chunk_id=str(uuid.uuid4()))]),
    )


def ask(client, question=QUESTION, **body):
    return client.post(ASK_URL, {"question": question, **body}, format="json")


# --- The four absences, asserted in one place -------------------------------------------


def assert_nothing_restricted_reached(response, service, corpus):
    """Assertions 1 to 4, on one reply and on the provider calls that produced it.

    Kept as a function so that every exit from ``POST /api/ask`` is held to the identical
    standard and no exit gets a weaker version of the check by accident. ``corpus`` is any
    ``TwoLevelCorpus``, whichever distance it was built at.
    """
    raw = response.content.decode()
    body = response.json()

    # 1. The answer: no statement is drawn from a restricted passage.
    assert {s["chunk_id"] for s in body["statements"]} & corpus.restricted_chunk_ids == set()

    # 2. The sources: neither the Sources panel nor the partial-match offer names it.
    listed = {entry["source_id"] for entry in body["sources"] + body["partial_matches"]}
    assert listed & corpus.restricted_source_ids == set()

    # 3. The count: computed over the post-filter set, so it cannot disclose volume. The
    #    Employee's scope holds two of the corpus's chunks; the store holds five.
    assert body["result_count"] <= 2
    assert ContentChunk.objects.count() == CORPUS_CHUNKS

    # 4. The payload sent to the AI service. THE assertion of this file: not "the answer
    #    did not mention it" but "the model never saw it". Read off the double's recorded
    #    call arguments — the passage objects, and the prompt actually built from them.
    for prompted_question, passages in service.generate_calls:
        assert {passage.chunk_id for passage in passages} & corpus.restricted_chunk_ids == set()
        prompt = build_user_prompt(prompted_question, passages)
        for trace in corpus.restricted_traces:
            assert trace not in prompt
    # Nor by the other provider door: the query embedding carries the question, never a
    # chunk read out of the store.
    for texts in service.embed_calls:
        for text in texts:
            for trace in corpus.restricted_traces:
                assert trace not in text

    # And nothing restricted is anywhere in the bytes the client received, in any key,
    # including one this test does not know about.
    for trace in corpus.restricted_traces:
        assert trace not in raw


# --- 1. POST /api/ask, on all three exits ------------------------------------------------


@pytest.mark.parametrize("exit_taken", ["answered", "no-answer-path-a", "no-answer-path-b"])
def test_no_trace_of_a_restricted_passage_on_any_exit_from_the_answer_path(
    employee_client, monkeypatch, employee, administrator, exit_taken
):
    """The four absences, on an answered question, on no-answer path A and on path B.

    The restricted document scores 0.95 and the restricted meeting 0.90 — nearer the
    question than anything the Employee may read — so a ranked list assembled before the
    permission filter would put both at the top on every one of these exits. That is the
    arrangement: the reply, the counts and the prompt all have something to leak.

    Path A is the strongest form of assertion 4 available anywhere in the suite: the
    provider was not called at all, so the restricted passage did not merely fail to appear
    in a payload — there was no payload.
    """
    corpus = build_corpus(
        employee,
        administrator,
        shared_cosine=BELOW if exit_taken == "no-answer-path-a" else ABOVE,
    )
    if exit_taken == "no-answer-path-b":
        service = fabricating(monkeypatch)
    else:
        service = install(monkeypatch, ControlledService())

    response = ask(employee_client)

    assert response.status_code == 200
    body = response.json()
    if exit_taken == "answered":
        assert body["answered"] is True
        assert body["result_count"] == 2  # the two in-scope chunks, not the five that exist
        assert len(service.generate_calls) == 1
    else:
        assert body["answered"] is False
        assert body["message"] == NO_ANSWER_MESSAGE
        assert body["result_count"] == 0
        if exit_taken == "no-answer-path-a":
            # Nothing in scope cleared the floor, so generation was never invoked.
            assert service.generate_calls == []
        else:
            assert len(service.generate_calls) == 1
    assert_nothing_restricted_reached(response, service, corpus)


def test_the_only_good_answer_lives_out_of_scope_so_the_employee_is_told_there_is_none(
    employee_client, service, only_restricted_answers
):
    """**The headline test.** A user asks a question whose only good answer lives in a
    document their role cannot see.

    The Administrator-only remuneration review answers it at 0.95. Everything the Employee
    may read is topically adjacent and below the floor. The Employee gets the fixed
    no-answer message and nothing else: no statement, no source, a count of zero, and a
    provider that was never called with the passage — never called at all, here. The message
    is the same fixed text an empty corpus would produce, which is FR-11's own Validation
    clause: "where the scope resolves to no accessible content, FR-12's no-answer response
    is returned rather than an error disclosing that restricted material exists".
    """
    response = ask(employee_client)

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is False
    assert body["message"] == NO_ANSWER_MESSAGE
    assert body["statements"] == [] and body["sources"] == []
    assert body["result_count"] == 0
    assert service.generate_calls == []
    assert_nothing_restricted_reached(response, service, only_restricted_answers)
    # The record agrees with the reply: the turn is logged as unanswered over an empty
    # retrieval, so not even the log claims a restricted chunk was retrieved.
    [row] = QueryLog.objects.all()
    assert row.answered is False and row.retrieved_chunk_ids == []


def test_the_administrator_is_given_the_answer_the_employee_was_refused(
    administrator_client, service, only_restricted_answers
):
    """**The negative control for the headline test**, and it carries as much weight.

    Same question, same store, same request — the wider role. Without this pairing the test
    above would pass against a system that answers nobody, which is the weakest way to
    satisfy invariant 1. FR-11's Front-End clause is exactly this: "two users asking the
    same question may receive different results".
    """
    corpus = only_restricted_answers

    response = ask(administrator_client)

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    [statement] = body["statements"]
    # The nearest passage is the restricted one, so it is what the answer is drawn from.
    assert statement["chunk_id"] == str(corpus.restricted_document_chunk.id)
    assert RESTRICTED_DOCUMENT_TITLE in {source["title"] for source in body["sources"]}
    # And it genuinely reached the provider for this role: the mirror of assertion 4.
    [(prompted_question, passages)] = service.generate_calls
    assert str(corpus.restricted_document_chunk.id) in {p.chunk_id for p in passages}
    assert RESTRICTED_DOCUMENT_TEXT in build_user_prompt(prompted_question, passages)


@pytest.mark.parametrize("shared_cosine", [ABOVE, BELOW], ids=["answered", "no-answer"])
def test_an_employees_reply_is_byte_identical_whether_the_restricted_material_exists(
    employee_client, service, employee, administrator, shared_cosine
):
    """"Assert the response does not differ in a way that reveals the document exists."

    The same request is made twice: once with the restricted rows in the store, once after
    they have been deleted. The two bodies are compared as bytes, so no count, no total, no
    ordering and no field this test did not think of can differ between "there is material
    you may not see" and "there is no such material". That is the property invariant 1
    states, and the one a field-by-field check cannot establish.
    """
    corpus = build_corpus(employee, administrator, shared_cosine=shared_cosine)

    with_restricted = ask(employee_client)
    corpus.delete_restricted()
    without_restricted = ask(employee_client)

    assert with_restricted.status_code == without_restricted.status_code == 200
    assert with_restricted.content == without_restricted.content


def test_a_promotion_between_turns_takes_effect_on_the_next_turn(
    employee_client, employee, administrator_role, service, only_restricted_answers
):
    """FR-13's Validation clause over FR-11: the scope is re-evaluated on every turn.

    One thread, one session cookie, no re-login. Turn one is refused because the only answer
    is out of scope; the role is then changed with an UPDATE that does not touch the
    in-memory user at all, so an implementation caching the role from turn one would still
    refuse turn two.
    """
    corpus = only_restricted_answers
    conversation = Conversation.objects.create(user=employee, title="Leave")

    first = ask(employee_client, conversation_id=str(conversation.pk))
    assert first.json()["answered"] is False
    assert_nothing_restricted_reached(first, service, corpus)

    get_user_model().objects.filter(pk=employee.pk).update(role=administrator_role)
    second = ask(employee_client, FOLLOW_UP, conversation_id=str(conversation.pk))

    assert second.status_code == 200
    assert second.json()["answered"] is True
    assert RESTRICTED_DOCUMENT_TITLE in {s["title"] for s in second.json()["sources"]}


def test_a_demotion_between_turns_takes_effect_on_the_next_turn(
    administrator_client, administrator, employee_role, service, only_restricted_answers
):
    """The direction that matters for security, and the mirror of the test above: access
    held on turn one is gone on turn two, on the same cookie, with no re-authentication."""
    corpus = only_restricted_answers
    conversation = Conversation.objects.create(user=administrator, title="Leave")

    first = ask(administrator_client, conversation_id=str(conversation.pk))
    assert first.json()["answered"] is True

    get_user_model().objects.filter(pk=administrator.pk).update(role=employee_role)
    # Only the second turn's calls are in scope for the assertion; the first turn was
    # entitled to what it received.
    service.generate_calls.clear()
    service.embed_calls.clear()
    second = ask(administrator_client, FOLLOW_UP, conversation_id=str(conversation.pk))

    assert second.status_code == 200
    assert second.json()["answered"] is False
    assert_nothing_restricted_reached(second, service, corpus)


def test_both_roles_reach_the_answer_path_and_each_sees_only_its_own_scope(
    session_client, service, overlapping_corpus
):
    """The dual-role gate on ``POST /api/ask`` (CLAUDE.md section 8 item 2), as one test.

    The route adds no role permission beyond the global ``IsAuthenticated`` default, so both
    roles reach it and what differs is the scope: two chunks for an Employee, four for an
    Administrator, out of the five in the store.
    """
    response = ask(session_client.client)

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    if session_client.role_name == EMPLOYEE_ROLE_NAME:
        assert body["result_count"] == 2
        assert_nothing_restricted_reached(response, service, overlapping_corpus)
    else:
        assert body["result_count"] == 4  # everything but the below-threshold meeting
        assert RESTRICTED_DOCUMENT_TITLE in {s["title"] for s in body["sources"]}


# --- 2. GET /api/search: the grouped counts are the likeliest disclosure (D-41) ----------


def test_one_term_two_roles_different_counts_in_both_groups(
    employee_client, administrator_client, overlapping_corpus
):
    """The counts are the disclosure risk in this endpoint, and both groups carry one.

    ``apps/api/tests/test_search.py`` established the document group; the meeting group had
    no restricted row in it until here, and a group whose count was taken before the filter
    would be the same bug twice. The Employee's totals are what the Employee can see, never
    what exists.
    """
    employee_body = employee_client.get(SEARCH_URL, {"q": TERM}).json()
    administrator_body = administrator_client.get(SEARCH_URL, {"q": TERM}).json()

    assert employee_body["documents"]["count"] == 1
    assert employee_body["meetings"]["count"] == 1
    assert employee_body["total_count"] == 2
    # The negative control, in the same test because the pair is the assertion: the wider
    # role is told the larger number, so neither count is merely a constant.
    assert administrator_body["documents"]["count"] == 2
    assert administrator_body["meetings"]["count"] == 2
    assert administrator_body["total_count"] == 4
    assert {r["title"] for r in administrator_body["documents"]["results"]} == {
        SHARED_DOCUMENT_TITLE,
        RESTRICTED_DOCUMENT_TITLE,
    }
    assert {r["title"] for r in administrator_body["meetings"]["results"]} == {
        SHARED_MEETING_TITLE,
        RESTRICTED_MEETING_TITLE,
    }


def test_no_restricted_title_snippet_or_identifier_reaches_an_employees_search(
    employee_client, overlapping_corpus
):
    """Against the raw rendered body: a grouped search reply is mostly counts and snippets,
    and a snippet is source text. Title, passage, identifier and department, all absent."""
    response = employee_client.get(SEARCH_URL, {"q": TERM})

    assert response.status_code == 200
    raw = response.content.decode()
    for trace in overlapping_corpus.restricted_traces:
        assert trace not in raw
    # The snippets that ARE returned come from the two in-scope passages, so the endpoint is
    # not passing by being empty.
    snippets = [
        result["snippet"]
        for group in ("documents", "meetings")
        for result in response.json()[group]["results"]
    ]
    assert len(snippets) == 2
    assert all(TERM in snippet.lower() for snippet in snippets)


def test_a_restricted_document_matching_only_by_title_is_absent_for_an_employee(
    employee_client, administrator_client, overlapping_corpus
):
    """The search query has two branches, and this is the second one.

    A body match is filtered through ``scoped_chunks``; a title match is filtered on the
    source row's own ``visible_to_roles``. TITLE_ONLY_TERM appears in the restricted
    document's title and in no chunk text anywhere, so it reaches the source row by the
    branch that never touches a chunk — and the role predicate has to be on that branch too.
    Paired with its negative control in the same test.
    """
    employee_response = employee_client.get(SEARCH_URL, {"q": TITLE_ONLY_TERM})
    administrator_body = administrator_client.get(SEARCH_URL, {"q": TITLE_ONLY_TERM}).json()

    assert employee_response.json()["total_count"] == 0
    assert RESTRICTED_DOCUMENT_TITLE not in employee_response.content.decode()
    # The Administrator finds it by title, which is what makes the absence above a filter
    # rather than a term that matches nothing.
    assert administrator_body["documents"]["count"] == 1
    assert [r["title"] for r in administrator_body["documents"]["results"]] == [
        RESTRICTED_DOCUMENT_TITLE
    ]


def test_both_roles_search_and_a_role_change_lands_on_the_next_search(
    session_client, overlapping_corpus, employee_role, administrator_role
):
    """The dual-role gate on ``GET /api/search``, plus 7.10 step 2 on this route.

    ``search()`` calls ``permission_scope`` itself on every call, so the same session cookie
    must return different results once the user's role row changes — no re-login, and the
    in-memory user object is never touched.
    """
    started_as_employee = session_client.role_name == EMPLOYEE_ROLE_NAME
    other_role = administrator_role if started_as_employee else employee_role

    before = session_client.client.get(SEARCH_URL, {"q": TERM})
    get_user_model().objects.filter(pk=session_client.user.pk).update(role=other_role)
    after = session_client.client.get(SEARCH_URL, {"q": TERM})

    assert before.json()["total_count"] == (2 if started_as_employee else 4)
    assert after.json()["total_count"] == (4 if started_as_employee else 2)
    # Whichever direction it went, the narrower of the two replies carries no trace of the
    # restricted material and the wider one names it.
    narrower, wider = (after, before) if not started_as_employee else (before, after)
    for trace in overlapping_corpus.restricted_traces:
        assert trace not in narrower.content.decode()
    assert RESTRICTED_DOCUMENT_TITLE in wider.content.decode()


# --- 3. GET /api/documents and GET /api/documents/{id} (D-46) ---------------------------


def document_detail(client, document_id):
    return client.get(f"{DOCUMENTS_URL}/{document_id}")


def test_the_repository_list_discloses_nothing_out_of_scope_and_lists_it_for_the_other_role(
    employee_client, administrator_client, overlapping_corpus
):
    """The list and its mirror. A list is also a count: ``len()`` of what came back is a
    total, and it must be a total over the post-filter rows."""
    employee_response = employee_client.get(DOCUMENTS_URL)
    administrator_response = administrator_client.get(DOCUMENTS_URL)

    assert [row["title"] for row in employee_response.json()] == [SHARED_DOCUMENT_TITLE]
    for trace in overlapping_corpus.restricted_traces:
        assert trace not in employee_response.content.decode()
    assert {row["title"] for row in administrator_response.json()} == {
        SHARED_DOCUMENT_TITLE,
        RESTRICTED_DOCUMENT_TITLE,
    }


def test_an_out_of_scope_document_is_indistinguishable_from_one_that_does_not_exist(
    session_client, employee, administrator
):
    """404 for both, with the identical status and the identical bytes, from both roles.

    ``apps/api/tests/test_document_detail.py`` compares the two parsed bodies; this compares
    the rendered bytes and adds the assertion that the refusal carries no trace of the row
    it refused. A 403 here, or a differently-worded 404, would be an error message that
    distinguishes "not found" from "not permitted" — named in invariant 1.

    The document is one the asking role may not read: Administrator-only for the Employee
    and, since D-66 made Administrator generalise Employee, scoped to nobody for the
    Administrator (``apps/retrieval/tests/scopes.py``).
    """
    theirs, _ = make_document(
        administrator,
        title=RESTRICTED_DOCUMENT_TITLE,
        roles=unreadable_scope(session_client.role_name),
        text=RESTRICTED_DOCUMENT_TEXT,
        cosine=NEAREST,
        department=RESTRICTED_DOCUMENT_DEPARTMENT,
    )

    out_of_scope = document_detail(session_client.client, theirs.id)
    unknown = document_detail(session_client.client, uuid.uuid4())

    assert out_of_scope.status_code == unknown.status_code == 404
    assert out_of_scope.content == unknown.content
    raw = out_of_scope.content.decode()
    assert RESTRICTED_DOCUMENT_TITLE not in raw and str(theirs.id) not in raw


def test_the_role_that_owns_the_document_reads_it_at_the_same_url(
    administrator_client, employee_client, overlapping_corpus
):
    """The negative control for the 404 above: the same id, the other session, 200 and the
    body. Without it the route could pass by refusing everybody."""
    refused = document_detail(employee_client, overlapping_corpus.restricted_document.id)
    allowed = document_detail(administrator_client, overlapping_corpus.restricted_document.id)

    assert refused.status_code == 404
    assert allowed.status_code == 200
    assert allowed.json()["title"] == RESTRICTED_DOCUMENT_TITLE
    assert allowed.json()["doc_id"] == str(overlapping_corpus.restricted_document.id)


def test_a_promotion_makes_a_previously_refused_document_readable_on_the_next_request(
    employee_client, employee, administrator_role, overlapping_corpus
):
    """One session cookie, no re-login, three routes: the detail route, the repository list
    and the search endpoint all follow the role row rather than the session (FR-05 into
    FR-11)."""
    document_id = overlapping_corpus.restricted_document.id
    assert document_detail(employee_client, document_id).status_code == 404
    assert [row["title"] for row in employee_client.get(DOCUMENTS_URL).json()] == [
        SHARED_DOCUMENT_TITLE
    ]

    get_user_model().objects.filter(pk=employee.pk).update(role=administrator_role)

    assert document_detail(employee_client, document_id).status_code == 200
    assert RESTRICTED_DOCUMENT_TITLE in {
        row["title"] for row in employee_client.get(DOCUMENTS_URL).json()
    }
    assert employee_client.get(SEARCH_URL, {"q": TERM}).json()["total_count"] == 4


# --- 4. GET /api/meetings and GET /api/meetings/{id}, and D-16 by name -------------------


def meeting_detail(client, meeting_id):
    return client.get(f"{MEETINGS_URL}/{meeting_id}")


def test_an_employee_who_attended_an_administrator_only_meeting_still_cannot_read_it(
    employee_client, employee, overlapping_corpus
):
    """**D-16 by name.** Meetings are scoped by role, never by attendance.

    The arrangement is built so that an implementation consulting ``MeetingAttendees`` would
    pass everything else in this file and fail here: the Employee is a recorded attendee of
    ``Board in-camera session``, and of nothing else. If attendance widened the scope, that
    meeting — and only that meeting — would become readable, its transcript would be in the
    detail body, and its passage would be a retrieval candidate.

    So the assertion is made at three levels, because attendance could be consulted in three
    places: the detail route, the listing, and the chunk scope that feeds retrieval.
    """
    assert MeetingAttendee.objects.filter(user=employee).count() == 1
    assert MeetingAttendee.objects.get(user=employee).meeting == overlapping_corpus.restricted_meeting

    attended = meeting_detail(employee_client, overlapping_corpus.restricted_meeting.id)
    unattended = meeting_detail(employee_client, overlapping_corpus.unattended_meeting.id)
    listing = employee_client.get(MEETINGS_URL)

    assert attended.status_code == 404
    assert unattended.status_code == 404
    # The two refusals are identical: attendance does not change even the shape of the no.
    assert attended.content == unattended.content
    assert [row["title"] for row in listing.json()] == [SHARED_MEETING_TITLE]
    for raw in (attended.content.decode(), unattended.content.decode(), listing.content.decode()):
        assert RESTRICTED_MEETING_TITLE not in raw
        assert RESTRICTED_MEETING_TEXT not in raw
        assert str(overlapping_corpus.restricted_meeting.id) not in raw


def test_an_administrator_who_attended_nothing_reads_both_restricted_meetings(
    administrator_client, administrator, overlapping_corpus
):
    """**The negative control for D-16, and the half that catches the opposite mistake.**

    The Administrator is a recorded attendee of nothing at all. An implementation that
    scoped by attendance — rather than by role — would refuse them both meetings, and the
    test above would still pass. D-16's own argument is this one: "knowledge has to outlive
    the people who were in the room".
    """
    assert not MeetingAttendee.objects.filter(user=administrator).exists()

    attended_by_someone_else = meeting_detail(
        administrator_client, overlapping_corpus.restricted_meeting.id
    )
    attended_by_nobody = meeting_detail(
        administrator_client, overlapping_corpus.unattended_meeting.id
    )

    assert attended_by_someone_else.status_code == 200
    assert attended_by_someone_else.json()["transcript_text"] == RESTRICTED_MEETING_TEXT
    assert attended_by_nobody.status_code == 200
    assert attended_by_nobody.json()["title"] == UNATTENDED_MEETING_TITLE
    assert {row["title"] for row in administrator_client.get(MEETINGS_URL).json()} == {
        SHARED_MEETING_TITLE,
        RESTRICTED_MEETING_TITLE,
        UNATTENDED_MEETING_TITLE,
    }


def test_an_attended_meetings_passage_is_not_a_retrieval_candidate_either(
    employee_client, service, overlapping_corpus
):
    """D-16 at the level that matters most: the chunk scope.

    The attended meeting's passage scores 0.90 — second-nearest in the store — so if
    attendance leaked into the candidate set it would be cited, not merely listed. Asserted
    on the prompt as well as on the reply, because the answer path is where an unnoticed
    second scoping mechanism would do the most damage.
    """
    response = ask(employee_client)

    assert response.status_code == 200
    assert_nothing_restricted_reached(response, service, overlapping_corpus)
    assert RESTRICTED_MEETING_TEXT not in response.content.decode()


def test_an_out_of_scope_meeting_is_indistinguishable_from_one_that_does_not_exist(
    session_client, employee, administrator
):
    """The meeting half of the 404 property, from both roles: same status, same bytes.

    As for documents above: Administrator-only for the Employee, nobody's for the
    Administrator (D-66).
    """
    theirs, _ = make_meeting(
        title=RESTRICTED_MEETING_TITLE,
        roles=unreadable_scope(session_client.role_name),
        text=RESTRICTED_MEETING_TEXT,
        cosine=NEAREST,
    )

    out_of_scope = meeting_detail(session_client.client, theirs.id)
    unknown = meeting_detail(session_client.client, uuid.uuid4())

    assert out_of_scope.status_code == unknown.status_code == 404
    assert out_of_scope.content == unknown.content
    assert RESTRICTED_MEETING_TITLE not in out_of_scope.content.decode()


def test_both_roles_list_meetings_and_each_list_is_its_own_scope(
    session_client, overlapping_corpus
):
    """The dual-role gate on the listing, with the contents stated for each role."""
    titles = {row["title"] for row in session_client.client.get(MEETINGS_URL).json()}

    if session_client.role_name == EMPLOYEE_ROLE_NAME:
        assert titles == {SHARED_MEETING_TITLE}
    else:
        assert titles == {
            SHARED_MEETING_TITLE,
            RESTRICTED_MEETING_TITLE,
            UNATTENDED_MEETING_TITLE,
        }


# --- 5. GET /api/conversations and GET /api/conversations/{id} ---------------------------


def conversation_detail(client, conversation_id):
    return client.get(f"{CONVERSATIONS_URL}/{conversation_id}")


THEIR_THREAD_TITLE = "Directors' leave loading"
THEIR_ANSWER_TEXT = "Twice the ordinary rate."


def test_another_users_thread_is_404_and_appears_in_no_list(
    session_client, employee, administrator, content_chunk
):
    """A thread is scoped to its owner, not to a role — so it is the one thing in this file
    an Administrator may not read either, and the assertion runs from both sessions against
    the other user's thread and expects the same refusal both ways.

    Their title, their id and their answer text appear nowhere: not in the 404, not in the
    list.
    """
    other = administrator if session_client.user == employee else employee
    theirs = Conversation.objects.create(user=other, title=THEIR_THREAD_TITLE)
    QueryLog.objects.create(
        user=other,
        conversation=theirs,
        question=QUESTION,
        answer_text=THEIR_ANSWER_TEXT,
        retrieved_chunk_ids=[content_chunk.id],
        answered=True,
    )

    refused = conversation_detail(session_client.client, theirs.pk)
    unknown = conversation_detail(session_client.client, uuid.uuid4())
    listing = session_client.client.get(CONVERSATIONS_URL)

    assert refused.status_code == unknown.status_code == 404
    assert refused.content == unknown.content
    assert listing.json() == []
    for raw in (refused.content.decode(), listing.content.decode()):
        assert THEIR_THREAD_TITLE not in raw
        assert str(theirs.pk) not in raw
        assert THEIR_ANSWER_TEXT not in raw


def test_the_owner_of_the_thread_reads_it_at_the_same_url(
    employee_client, employee, administrator_client
):
    """The negative control: the id refused above is the id its owner reads, so the 404 is a
    scope and not a broken route."""
    theirs = Conversation.objects.create(user=employee, title=THEIR_THREAD_TITLE)

    assert conversation_detail(administrator_client, theirs.pk).status_code == 404
    owner_response = conversation_detail(employee_client, theirs.pk)

    assert owner_response.status_code == 200
    assert owner_response.json()["title"] == THEIR_THREAD_TITLE
    assert [row["title"] for row in employee_client.get(CONVERSATIONS_URL).json()] == [
        THEIR_THREAD_TITLE
    ]


def test_a_thread_does_not_follow_its_owner_into_another_role(
    employee_client, employee, administrator, administrator_role
):
    """Promotion does not hand over other people's threads.

    The Employee is promoted to Administrator, which widens their content scope — and their
    conversation scope does not widen with it, because a thread is owned rather than
    classified. The two scoping rules are easy to conflate in one middleware.
    """
    theirs = Conversation.objects.create(user=administrator, title=THEIR_THREAD_TITLE)

    get_user_model().objects.filter(pk=employee.pk).update(role=administrator_role)

    assert conversation_detail(employee_client, theirs.pk).status_code == 404
    assert employee_client.get(CONVERSATIONS_URL).json() == []


def test_a_turn_may_not_be_written_into_another_users_thread(
    session_client, service, overlapping_corpus, employee, administrator
):
    """``POST /api/ask`` with someone else's ``conversation_id``: 404, no row, and the
    provider is never reached — so a foreign thread cannot even be used as an oracle for
    whether a question is answerable."""
    other = administrator if session_client.user == employee else employee
    theirs = Conversation.objects.create(user=other, title=THEIR_THREAD_TITLE)

    response = ask(session_client.client, conversation_id=str(theirs.pk))

    assert response.status_code == 404
    assert not QueryLog.objects.exists()
    assert service.embed_calls == [] and service.generate_calls == []


# --- 6. The record-only fields reach no body, on any route -------------------------------


@pytest.mark.parametrize("forbidden", RECORD_ONLY_FIELDS + NO_ANSWER_REASONS)
def test_no_route_discloses_the_no_answer_reason_or_the_rejected_count(
    employee_client, monkeypatch, employee, administrator, content_chunk, forbidden
):
    """Parametrised over the field names AND the vocabulary values, across every route that
    renders a query outcome.

    A caller who could tell the two no-answer paths apart would know that material exists
    which could not be cited — the disclosure invariant 1 forbids, and the one a user would
    act on. ``apps/api/tests/test_ask.py`` and ``test_conversations.py`` each assert this on
    their own route; this sweeps the surface in one place so that a new route cannot quietly
    become the exception. Every body is collected from a request that really took the path in
    question, and a row carrying both columns is in the database throughout.
    """
    corpus = build_corpus(employee, administrator, shared_cosine=ABOVE)
    conversation = Conversation.objects.create(user=employee, title="Leave")
    # A logged turn that really carries both columns, so there is something to leak.
    QueryLog.objects.create(
        user=employee,
        conversation=conversation,
        question=QUESTION,
        answer_text=None,
        retrieved_chunk_ids=[content_chunk.id],
        answered=False,
        no_answer_reason=NO_STATEMENT_VERIFIED,
        rejected_count=3,
    )

    bodies = {}
    # Path B: passages supplied, and the model cites an identifier that was never supplied.
    fabricating(monkeypatch)
    bodies["ask path b"] = ask(employee_client)
    # Path A: a query vector orthogonal to the corpus, so nothing clears the floor.
    install(monkeypatch, ControlledService(vector=ELSEWHERE))
    bodies["ask path a"] = ask(employee_client)
    bodies["conversation detail"] = conversation_detail(employee_client, conversation.pk)
    bodies["conversation list"] = employee_client.get(CONVERSATIONS_URL)
    bodies["search"] = employee_client.get(SEARCH_URL, {"q": TERM})
    bodies["documents"] = employee_client.get(DOCUMENTS_URL)
    bodies["meetings"] = employee_client.get(MEETINGS_URL)
    bodies["document detail"] = document_detail(employee_client, corpus.shared_document.id)
    bodies["meeting detail"] = meeting_detail(employee_client, corpus.shared_meeting.id)

    # Three rows now carry a reason: the seeded one and the two requests above. The
    # distinction exists, in the log, for the team — and in no reply.
    assert QueryLog.objects.exclude(no_answer_reason=None).count() == 3
    for label, response in bodies.items():
        assert response.status_code == 200, label
        assert forbidden not in response.content.decode(), label


# --- 7. A chunk scoped to nobody, through every route ------------------------------------


UNSTAMPED_TITLE = "Unstamped inventory"
UNSTAMPED_TEXT = "No role may read this passage at all."


@pytest.fixture
def unstamped(employee):
    """A document in scope for both roles whose only chunk is stamped with an empty array.

    D-29 makes an empty ``visible_to_roles`` a 400 at upload, so this state should not arise;
    what these tests assert is what the routes do if it ever does. They fail closed. Note
    what is and is not claimed: the CHUNK is invisible to every role through every route,
    while the document ROW is in scope and stays listable — row visibility is a separate
    fact, and pretending otherwise would be testing a rule the project does not have.
    """
    document = Document.objects.create(
        title=UNSTAMPED_TITLE,
        file_type="pdf",
        uploaded_by=employee,
        visible_to_roles=BOTH_ROLES,
    )
    chunk = make_chunk(
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        text=UNSTAMPED_TEXT,
        roles=[],  # scoped to nobody
        cosine=NEAREST,
    )
    assert chunk.visible_to_roles == []
    return document, chunk


def test_a_chunk_scoped_to_nobody_answers_nobody(session_client, service, unstamped):
    """The nearest passage in the store is stamped for no role, so neither role may use it.

    Both roles reach a no-answer, generation is never called, and the passage text is in no
    body and no payload. This is the one case in the file with no negative control, because
    there is no role for which the mirror could hold: that is the point of an empty array.
    """
    _, chunk = unstamped

    response = ask(session_client.client)

    body = response.json()
    assert body["answered"] is False
    assert body["result_count"] == 0
    assert body["partial_matches"] == []  # not offered as a near miss either
    assert service.generate_calls == []
    raw = response.content.decode()
    assert UNSTAMPED_TEXT not in raw and str(chunk.id) not in raw


def test_a_chunk_scoped_to_nobody_is_not_searchable_by_its_text(session_client, unstamped):
    """A keyword search over the passage body finds nothing: the chunk predicate is the same
    ``scoped_chunks`` the answer path uses, so there is no second filter to disagree."""
    body = session_client.client.get(SEARCH_URL, {"q": "read this passage"}).json()

    assert body["total_count"] == 0
    assert body["documents"] == {"count": 0, "results": []}


def test_a_document_whose_chunk_is_scoped_to_nobody_shows_no_snippet(
    session_client, unstamped
):
    """The row is in scope and still listed — but its snippet is empty, because a snippet
    comes from a chunk and no chunk is readable. An implementation that took the opening
    snippet outside the scope would leak the passage here, through the title branch."""
    response = session_client.client.get(SEARCH_URL, {"q": "inventory"})

    body = response.json()
    assert body["documents"]["count"] == 1
    [result] = body["documents"]["results"]
    assert result["title"] == UNSTAMPED_TITLE
    assert result["snippet"] == ""
    assert UNSTAMPED_TEXT not in response.content.decode()


def test_a_document_whose_chunk_is_scoped_to_nobody_carries_no_passage_in_its_detail(
    session_client, unstamped
):
    """The detail route renders the document object and no passage, so there is nothing for
    an unstamped chunk to arrive through. Asserted rather than assumed: D-46 added this
    route at item 10b, and it is the newest surface in the file."""
    document, chunk = unstamped

    response = document_detail(session_client.client, document.id)

    assert response.status_code == 200
    raw = response.content.decode()
    assert UNSTAMPED_TEXT not in raw
    assert str(chunk.id) not in raw


# --- 8. The invariant-2 cascade: a scope that CHANGES after ingestion ---------------------
#
# Item 11 found this gap and left it here as a strict xfail, because a green test would have
# been a false one: nothing on Document or Meeting cascaded a visibility change, so narrowing
# a document removed it from GET /api/documents — that filter is on the row — and left
# POST /api/ask answering an Employee with a citation from it, because that filter is on the
# chunk, which still carried both roles. One change, two filters, two answers, the worse of
# them being the one that returns content.
#
# The cascade is now a model-level guarantee (apps/core/visibility.py), the marker is off,
# and the tests below are its consequence at the boundary. Sections 1 to 7 cover the STATIC
# case — a scope an Employee never could see. This section covers the SEQUENCE, which is
# what was actually broken: ingested visible to everybody, narrowed afterwards, then asked.
# The model-level properties — every chunk, both source types, widening, the same
# transaction, QuerySet.update() — are in apps/core/tests/test_visibility_cascade.py, and
# the split is deliberate: these tests would still pass if a view did the re-stamping, and
# those would not.


def test_narrowing_a_documents_visibility_re_stamps_its_chunks(
    employee_client, service, employee
):
    """CLAUDE.md invariant 2: "Changing a source's visibility **re-stamps every one of its
    chunks in the same transaction** — that cascade is a model-level guarantee, not a
    convention, and it has its own test. See D-17."

    The assertion is the guarantee itself, stated as invariant 2 words it, and then the
    consequence the gap used to cost: an ordinary ``save()`` narrowing a document to
    Administrators only leaves the Employee with no answer, where before it left them
    answered, with a citation, from a document they could no longer open.
    """
    document, chunk = make_document(
        employee,
        title=SHARED_DOCUMENT_TITLE,
        roles=BOTH_ROLES,
        text=SHARED_DOCUMENT_TEXT,
        cosine=ABOVE,
        department=SHARED_DOCUMENT_DEPARTMENT,
    )

    document.visible_to_roles = [ADMINISTRATOR_ROLE_NAME]
    document.save()

    chunk.refresh_from_db()
    assert chunk.visible_to_roles == [ADMINISTRATOR_ROLE_NAME]
    # And therefore the consequence at the boundary: the passage stops being answerable.
    body = ask(employee_client).json()
    assert body["answered"] is False
    assert SHARED_DOCUMENT_TEXT not in ask(employee_client).content.decode()


def test_narrowing_a_meetings_visibility_re_stamps_its_chunks(employee_client, service):
    """The same guarantee for a meeting, because D-16 makes meeting visibility mirror document
    visibility exactly and a cascade that only covered documents would be the second code
    path invariant 3 refuses. The attendee record is written and changes nothing."""
    meeting, chunk = make_meeting(
        title=SHARED_MEETING_TITLE,
        roles=BOTH_ROLES,
        text=SHARED_MEETING_TEXT,
        cosine=ABOVE,
    )

    meeting.visible_to_roles = [ADMINISTRATOR_ROLE_NAME]
    meeting.save()

    chunk.refresh_from_db()
    assert chunk.visible_to_roles == [ADMINISTRATOR_ROLE_NAME]
    body = ask(employee_client).json()
    assert body["answered"] is False
    assert SHARED_MEETING_TEXT not in ask(employee_client).content.decode()


@pytest.fixture
def narrowed_after_ingestion(employee, administrator):
    """The headline corpus, except that its restricted trio was ingested visible to EVERYBODY
    and narrowed to Administrators afterwards.

    One document and two meetings, so both source types travel this path in one request, and
    the chunks were genuinely stamped with both roles at ingestion — the fixture asserts that
    before narrowing, so a cascade that never ran could not be mistaken for a corpus that was
    restricted all along. Afterwards the arrangement is bit-for-bit the one sections 1 to 7
    assert against, which is the point: the same four absences must hold, and the same helper
    must be the thing that checks them.
    """
    corpus = build_corpus(
        employee, administrator, shared_cosine=BELOW, restricted_roles=BOTH_ROLES
    )
    assert corpus.restricted_document_chunk.visible_to_roles == BOTH_ROLES
    assert corpus.restricted_meeting_chunk.visible_to_roles == BOTH_ROLES
    for source in (
        corpus.restricted_document,
        corpus.restricted_meeting,
        corpus.unattended_meeting,
    ):
        source.visible_to_roles = [ADMINISTRATOR_ROLE_NAME]
        source.save()
    return corpus


def test_a_document_narrowed_after_ingestion_leaves_no_trace_on_the_answer_path(
    employee_client, service, narrowed_after_ingestion
):
    """**The sequence case, which is the one that was broken.** Ingest, narrow, then ask.

    The narrowed document is still the nearest passage in the store at 0.95, and everything
    the Employee may read is below the floor, so there is every incentive for it to surface:
    if the chunk still carried both roles it would be retrieved, sent to the provider and
    cited, and the four absences would fail one after another. All four are asserted through
    item 11's own helper rather than a local subset, so this exit is held to the identical
    standard as a scope that was always narrow.
    """
    response = ask(employee_client)

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is False
    assert body["message"] == NO_ANSWER_MESSAGE
    assert body["result_count"] == 0
    assert service.generate_calls == []  # nothing in scope cleared the floor
    assert_nothing_restricted_reached(response, service, narrowed_after_ingestion)
    assert RESTRICTED_DOCUMENT_TEXT not in response.content.decode()


def test_a_meeting_narrowed_after_ingestion_leaves_no_trace_on_the_answer_path(
    employee_client, service, narrowed_after_ingestion
):
    """The same sequence for a meeting, named separately because FR-11's meeting half has its
    own column, its own source type and its own decision behind it (D-16).

    The Employee ATTENDED the narrowed meeting, which is exactly the case where an
    implementation tempted to treat attendance as access would keep answering from it after
    the role scope was narrowed underneath.
    """
    corpus = narrowed_after_ingestion
    assert MeetingAttendee.objects.filter(meeting=corpus.restricted_meeting).exists()

    response = ask(employee_client)

    raw = response.content.decode()
    assert response.json()["answered"] is False
    assert RESTRICTED_MEETING_TEXT not in raw and UNATTENDED_MEETING_TEXT not in raw
    assert_nothing_restricted_reached(response, service, corpus)


def test_the_administrator_still_answers_from_the_material_that_was_narrowed(
    administrator_client, service, narrowed_after_ingestion
):
    """The negative control for the whole section: narrowing narrowed, it did not blank.

    A cascade that stamped every chunk with an empty array, or that dropped the rows, would
    satisfy every absence above and destroy the corpus. The role the material was narrowed TO
    still gets its answer, from the same vectors, with no re-index in between — which is also
    the assertion that nothing was re-embedded, because the provider was never asked to embed
    anything but this question.
    """
    corpus = narrowed_after_ingestion

    response = ask(administrator_client)

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    [statement] = body["statements"]
    assert statement["chunk_id"] == str(corpus.restricted_document_chunk.id)
    assert RESTRICTED_DOCUMENT_TITLE in {source["title"] for source in body["sources"]}
    # One embed call, carrying the question and its retrieval task prefix — and no chunk
    # text, because the cascade re-stamped the rows without going near the provider.
    [[embedded]] = service.embed_calls
    assert QUESTION in embedded
    assert RESTRICTED_DOCUMENT_TEXT not in embedded


def test_a_document_narrowed_and_then_widened_again_is_answerable(
    employee_client, service, narrowed_after_ingestion
):
    """Widening, which is the direction that gets found later.

    A document restricted by mistake and corrected must become answerable again without a
    re-index: the vectors were never wrong, only the stamp moved. The Employee asks the same
    question across the correction and the answer appears.
    """
    corpus = narrowed_after_ingestion
    assert ask(employee_client).json()["answered"] is False

    corpus.restricted_document.visible_to_roles = BOTH_ROLES
    corpus.restricted_document.save()
    response = ask(employee_client)

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    [statement] = body["statements"]
    assert statement["chunk_id"] == str(corpus.restricted_document_chunk.id)
    # The meetings were not corrected, so they are still absent — the widening is not a
    # blanket amnesty for everything narrowed in the same fixture.
    raw = response.content.decode()
    assert RESTRICTED_MEETING_TEXT not in raw and UNATTENDED_MEETING_TEXT not in raw


def test_both_roles_see_the_cascade_take_effect_on_the_route_they_share(
    session_client, service, narrowed_after_ingestion
):
    """The dual-role pairing for the sequence, on ``POST /api/ask``: after the same change,
    the Employee has no answer and the Administrator has one. FR-11's Front-End clause —
    "two users asking the same question may receive different results" — now holding across a
    visibility change rather than only across an ingestion-time scope.
    """
    corpus = narrowed_after_ingestion

    response = ask(session_client.client)

    assert response.status_code == 200
    body = response.json()
    if session_client.role_name == EMPLOYEE_ROLE_NAME:
        assert body["answered"] is False
        assert_nothing_restricted_reached(response, service, corpus)
    else:
        assert body["answered"] is True
        assert RESTRICTED_DOCUMENT_TITLE in {source["title"] for source in body["sources"]}


def test_a_narrowed_document_disappears_from_the_repository_and_the_search_together(
    employee_client, service, narrowed_after_ingestion
):
    """The row filter and the chunk filter now agree, which is what the gap was.

    Before the cascade these two routes disagreed about the same document after the same
    change: it was absent from the list, whose predicate is on the source row, and present in
    an answer, whose predicate is on the chunk. Asserting them in one test is the form of the
    original defect, so a regression that re-opened it would fail here as a disagreement
    rather than as two unrelated tests.
    """
    corpus = narrowed_after_ingestion

    listing = employee_client.get(DOCUMENTS_URL)
    detail = document_detail(employee_client, corpus.restricted_document.id)
    searched = employee_client.get(SEARCH_URL, {"q": TERM})
    answer = ask(employee_client)

    assert [row["title"] for row in listing.json()] == [SHARED_DOCUMENT_TITLE]
    assert detail.status_code == 404
    assert RESTRICTED_DOCUMENT_TEXT not in searched.content.decode()
    assert searched.json()["documents"]["count"] == 1
    assert answer.json()["answered"] is False
    assert_nothing_restricted_reached(answer, service, corpus)
