"""FR-13 conversation context: what a follow-up turn carries, and what it must not.

Two files' worth of subject matter in one, because the two halves cannot be separated
usefully: what the composed strings SAY (apps/retrieval/conversation.py and
apps/ai/prompting.py) and what a TURN does with them through the pipeline
(apps/retrieval/pipeline.py). An assertion about the labelling that did not also check the
string reached the provider would be testing a docstring.

The tests that matter most here are the four that assert an absence:

- ``test_a_prior_answer_never_reaches_the_prompt_or_the_query`` — no model-generated text
  re-enters a prompt, which is the whole reason the history is questions only;
- ``test_another_users_conversation_yields_no_history`` — a conversation id is a UUID a
  caller supplies, and the history query filters on user as well, so someone else's thread
  yields NOTHING rather than their questions;
- ``test_an_identifier_seen_only_among_the_earlier_questions_is_rejected`` — D-39's lesson
  in its new form: anything in a prompt is a candidate for being cited, and set membership
  against the passage labels is what refuses it;
- ``test_a_follow_up_inherits_the_context_but_not_the_access`` — FR-13's re-evaluation
  clause, over two turns of one conversation with the role changed between them.

The helpers and the double are restated here rather than imported from test_pipeline.py,
following this suite's habit of a test stating its own premise instead of inheriting it
from another module's fixture.

Nothing here reaches a provider: conftest.py's ``no_live_provider`` still points every
endpoint at a closed port underneath the double. **And nothing here measures the composed
prompt against the real model** — docs/flm-baseline.md's conformance and fabrication rates
were taken on a prompt of passages plus ONE question, scripts/citation_harness.py asks
single questions, and the multi-turn prompt is therefore unmeasured. These tests assert
what the prompt contains and what verification does with what comes back; they cannot
assert that gemma3:4b's schema conformance survives a history block.
"""

from datetime import UTC, datetime, timedelta
from math import sqrt
from uuid import uuid4

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

import apps.ai
from apps.ai.base import EmbeddingResult, Statement, StatementList
from apps.ai.prefixes import query_text
from apps.ai.prompting import (
    PRIOR_QUESTION_MARKER,
    PRIOR_QUESTIONS_HEADING,
    QUESTION_LEAD_IN,
    build_conversational_question,
    build_generation_messages,
    build_user_prompt,
)
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    MAXIMUM_CONVERSATION_TURNS,
    MAXIMUM_QUESTION_LENGTH,
    MINIMUM_QUESTION_LENGTH,
    NO_ANSWER_MESSAGE,
    NO_RELEVANT_PASSAGE,
    NO_STATEMENT_VERIFIED,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk
from apps.retrieval.conversation import (
    RETRIEVAL_JOIN,
    ConversationContext,
    conversation_context,
    prior_questions,
    prior_questions_before,
)
from apps.retrieval.models import Conversation, QueryLog
from apps.retrieval.pipeline import QuestionLengthOutOfRange, answer_question

ROLE_PAIR = (EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME)

# A thread: three questions asked, then the one being asked now. The follow-up is
# deliberately the kind FR-13 exists for — "part-time staff" of WHAT is only answerable
# from the questions above it.
FIRST = "How much annual leave do I get?"
SECOND = "Does it carry over to next year?"
THIRD = "Who has to approve the request?"
FOLLOW_UP = "What about part-time staff?"
for _question in (FIRST, SECOND, THIRD, FOLLOW_UP):
    assert MINIMUM_QUESTION_LENGTH <= len(_question) <= MAXIMUM_QUESTION_LENGTH

# What a prior turn was ANSWERED with. Distinctive enough that its appearance anywhere in
# a prompt or an embedding call is unmistakable.
PRIOR_ANSWER = "Twenty days of annual leave accrue each year, pro rata."

BELOW = 0.10
ABOVE = 0.80
NEAREST = 0.99
assert BELOW < RELEVANCE_THRESHOLD < ABOVE < NEAREST


# --- Vectors and rows ------------------------------------------------------------------


def wide(*components) -> list[float]:
    """The given leading components, zero-padded to the real column width."""
    values = list(components)
    return values + [0.0] * (settings.EMBEDDING_DIMENSION - len(values))


QUERY = wide(1.0)


def at_cosine(value: float) -> list[float]:
    """A unit vector whose cosine with QUERY is exactly ``value``."""
    return wide(value, sqrt(1.0 - value * value))


def make_chunk(document, visible_to_roles, *, index, cosine, text="A passage."):
    """A chunk stamped with a visibility scope (D-17), at a known angle to QUERY."""
    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=index,
        chunk_text=text,
        embedding=at_cosine(cosine),
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=visible_to_roles,
    )


def make_conversation(user, title="Leave policy questions") -> Conversation:
    return Conversation.objects.create(user=user, title=title)


# When the turns ``make_turn`` writes were asked: THREAD_START plus the minutes each call
# states. Fixed, and in the past, so that a turn the code under test writes afterwards, at
# the real time, is always the newest in its thread.
THREAD_START = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def make_turn(conversation, user, question, *, minute, answer_text=None) -> QueryLog:
    """A turn already in the log, as a real earlier turn would have left it.

    Written directly rather than by calling ``answer_question`` so that the history under
    test is a premise of the test rather than an output of the code under test. Where
    ``answer_text`` is given the turn was answered; where it is not, the turn is one of the
    no-answer paths — and it still counts as a turn.

    **``minute`` is when the turn was asked, in minutes after THREAD_START, and every call
    states one.** The history is read in ``answered_at`` order with the random UUID primary
    key as the tie-break, and rows written back to back can share an ``answered_at``: on
    Windows the clock steps at anything from about 0.3 ms to about 15.6 ms (D-107's note),
    and a tie is then ordered by the UUIDs, arbitrarily. Real turns are seconds apart, so the
    reading code is right and only a test's premise can be wrong; here the gap is stated
    instead of left to the clock. ``answered_at`` is ``auto_now_add``, which overwrites a
    value given to ``create()``, so the UPDATE afterwards is what sets it.
    """
    row = QueryLog.objects.create(
        user=user,
        conversation=conversation,
        question=question,
        answer_text=answer_text,
        retrieved_chunk_ids=[],
        answered=answer_text is not None,
        no_answer_reason=None if answer_text is not None else NO_RELEVANT_PASSAGE,
        rejected_count=None,
    )
    QueryLog.objects.filter(pk=row.pk).update(
        answered_at=THREAD_START + timedelta(minutes=minute)
    )
    row.refresh_from_db(fields=["answered_at"])
    return row


def touched_at_thread_start(conversation):
    """Set ``conversation.last_updated_at`` back to THREAD_START, and return it as stored.

    For a test asserting that a turn moves the timestamp forward, or that a refused question
    leaves it alone. Measured from a timestamp the clock has only just written, a turn of a
    few milliseconds can land in the same step of the clock (``make_turn``), so "moved" would
    read as "equal" and a wrongful touch would go unseen. ``last_updated_at`` is ``auto_now``,
    which a save() would overwrite, so an UPDATE sets it.
    """
    Conversation.objects.filter(pk=conversation.pk).update(last_updated_at=THREAD_START)
    conversation.refresh_from_db()
    return conversation.last_updated_at


# --- The double ------------------------------------------------------------------------


class ControlledService:
    """An AIService whose query vector is known and whose generation reply is scripted.

    ``embed_calls`` holds the texts of each embedding call and ``generate_calls`` holds
    ``(question, passages)`` per generation call, which between them are how these tests
    assert what reached the provider — the composed retrieval string on one side and the
    composed prompt string on the other.
    """

    def __init__(self, *, vector=None, model=STUB_EMBEDDING_MODEL, statements=None):
        self.vector = QUERY if vector is None else vector
        self.model = model
        self.statements = statements
        self.embed_calls: list[list[str]] = []
        self.generate_calls: list[tuple] = []

    def embed(self, texts: list[str], *, input_type=None) -> EmbeddingResult:
        self.embed_calls.append(list(texts))
        return EmbeddingResult(
            vectors=[list(self.vector)],
            model=self.model,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    def generate_statements(self, question, passages):
        self.generate_calls.append((question, list(passages)))
        if self.statements is not None:
            return StatementList(statements=list(self.statements))
        return StatementList(
            statements=[Statement(text="A grounded statement.", chunk_id=passages[0].chunk_id)]
        )

    def health(self):
        raise AssertionError("the pipeline does not check provider health")


def install(monkeypatch, double):
    monkeypatch.setattr(apps.ai, "get_ai_service", lambda: double)
    return double


@pytest.fixture
def service(monkeypatch):
    return install(monkeypatch, ControlledService())


@pytest.fixture
def service_with(monkeypatch):
    def build(**kwargs):
        return install(monkeypatch, ControlledService(**kwargs))

    return build


def sent_question(double) -> str:
    """The question string of the one generation call that was made."""
    assert len(double.generate_calls) == 1
    return double.generate_calls[0][0]


# --- No conversation: nothing changes at all -------------------------------------------


@pytest.mark.django_db
def test_no_conversation_composes_nothing(employee):
    """The default path, and the one the baseline measured: both strings ARE the question.

    Equality of value, not merely of meaning. Everything downstream — the embedded text,
    the prompt, the recorded row — is then identical to what it was before FR-13 existed,
    which is what lets docs/flm-baseline.md keep describing the one-off path.
    """
    context = conversation_context(question=FOLLOW_UP, conversation=None, user=employee)

    assert isinstance(context, ConversationContext)
    assert context.prior_questions == ()
    assert context.for_retrieval == FOLLOW_UP
    assert context.for_prompt == FOLLOW_UP


@pytest.mark.django_db
def test_an_empty_conversation_composes_nothing(employee):
    """The first turn of a NEW thread is a one-off question in everything but the row.

    Worth its own case: a conversation exists, so the history query runs, and it must
    compose nothing from no rows rather than an empty heading or a dangling lead-in.
    """
    context = conversation_context(
        question=FOLLOW_UP, conversation=make_conversation(employee), user=employee
    )

    assert context.prior_questions == ()
    assert context.for_retrieval == FOLLOW_UP
    assert context.for_prompt == FOLLOW_UP
    assert PRIOR_QUESTIONS_HEADING not in context.for_prompt


@pytest.mark.django_db
def test_a_first_turn_prompt_is_byte_identical_to_a_one_off(employee):
    """The prompt item 6 measured, unchanged, down to the bytes.

    Asserted on the built prompt rather than on the composed string alone, because the
    thing that must not have moved is what the provider receives.
    """
    from apps.ai.base import Passage

    passages = [Passage(chunk_id=str(uuid4()), text="Twenty days.")]
    context = conversation_context(
        question=FOLLOW_UP, conversation=make_conversation(employee), user=employee
    )

    assert build_user_prompt(context.for_prompt, passages) == build_user_prompt(
        FOLLOW_UP, passages
    )
    assert build_generation_messages(context.for_prompt, passages) == build_generation_messages(
        FOLLOW_UP, passages
    )


def test_the_composer_returns_the_question_unchanged_with_no_history():
    """The same property one level down, with no database and no conversation object."""
    assert build_conversational_question(FOLLOW_UP, []) == FOLLOW_UP


@pytest.mark.django_db
def test_a_one_off_question_still_records_a_null_conversation(document, service):
    """FR-13 wiring did not change what a question outside a thread records."""
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days.")

    answer_question(question=FOLLOW_UP, user=document.uploaded_by)

    assert QueryLog.objects.get().conversation is None


# --- The two composed forms ------------------------------------------------------------


@pytest.mark.django_db
def test_the_retrieval_string_is_a_plain_join_oldest_first(employee):
    """What gets EMBEDDED: the questions and nothing else, in the order they were asked.

    No heading, no markers, no lead-in. Every word of instructional prose in an embedded
    string is a word pulling the query vector away from the subject, and what a follow-up
    needs from its predecessors is their nouns.
    """
    conversation = make_conversation(employee)
    make_turn(conversation, employee, FIRST, minute=1, answer_text=PRIOR_ANSWER)
    make_turn(conversation, employee, SECOND, minute=2)

    context = conversation_context(
        question=FOLLOW_UP, conversation=conversation, user=employee
    )

    assert context.for_retrieval == RETRIEVAL_JOIN.join([FIRST, SECOND, FOLLOW_UP])
    assert PRIOR_QUESTIONS_HEADING not in context.for_retrieval
    assert PRIOR_QUESTION_MARKER not in context.for_retrieval
    assert QUESTION_LEAD_IN not in context.for_retrieval


@pytest.mark.django_db
def test_the_prompt_string_labels_the_earlier_questions_as_uncitable(employee):
    """What reaches GENERATION: a labelled block that says what it is and what it is not.

    The three clauses asserted here are the mitigation for the lesson apps/ai/prompting.py
    has learned twice — anything in a prompt is a candidate for being cited. The block
    states that these lines are earlier questions, that they are context only, and that
    they are not passages, carry no chunk_id and may not be cited.
    """
    conversation = make_conversation(employee)
    make_turn(conversation, employee, FIRST, minute=1)
    make_turn(conversation, employee, SECOND, minute=2)

    context = conversation_context(
        question=FOLLOW_UP, conversation=conversation, user=employee
    )

    assert PRIOR_QUESTIONS_HEADING in context.for_prompt
    assert "Earlier questions in this conversation" in context.for_prompt
    assert "context only" in context.for_prompt
    assert "They are NOT passages" in context.for_prompt
    assert "they carry no chunk_id" in context.for_prompt
    assert "nothing in them may be cited" in context.for_prompt
    # The earlier questions are present, marked, and not numbered: a numbered list would
    # put "1." and "2." in the prompt, and one measured fabrication was "5. Offboarding".
    assert f"{PRIOR_QUESTION_MARKER}{FIRST}" in context.for_prompt
    assert f"{PRIOR_QUESTION_MARKER}{SECOND}" in context.for_prompt
    assert f"1. {FIRST}" not in context.for_prompt
    # The question being asked is still findable as the question being asked.
    assert context.for_prompt.endswith(f"{QUESTION_LEAD_IN}{FOLLOW_UP}")
    # Nothing in the block looks like a passage label.
    assert "[chunk_id:" not in context.for_prompt


@pytest.mark.django_db
def test_the_labelled_block_sits_after_the_passages_in_the_built_prompt(employee):
    """FR-13's separation is a property of the prompt, not a hope about the model.

    ``build_user_prompt`` puts the question after the passage block, so every
    ``[chunk_id: ...]`` label precedes every line of history and the two are never
    interleaved.
    """
    from apps.ai.base import Passage

    conversation = make_conversation(employee)
    make_turn(conversation, employee, FIRST, minute=1)
    passage = Passage(chunk_id=str(uuid4()), text="Twenty days.")

    context = conversation_context(
        question=FOLLOW_UP, conversation=conversation, user=employee
    )
    prompt = build_user_prompt(context.for_prompt, [passage])

    assert prompt.index(f"[chunk_id: {passage.chunk_id}]") < prompt.index(
        PRIOR_QUESTIONS_HEADING
    )
    assert prompt.index(PRIOR_QUESTIONS_HEADING) < prompt.index(FOLLOW_UP)


@pytest.mark.django_db
def test_the_history_reads_chronologically_in_the_prompt(employee):
    """Oldest first, because the model reads the block as a sequence.

    A thread printed backwards invites a pronoun in the newest question to be resolved
    against the wrong antecedent.
    """
    conversation = make_conversation(employee)
    # A minute apart, in the order asked: stated, not left to the clock (make_turn).
    for minute, question in enumerate((FIRST, SECOND, THIRD), start=1):
        make_turn(conversation, employee, question, minute=minute)

    context = conversation_context(
        question=FOLLOW_UP, conversation=conversation, user=employee
    )

    assert context.prior_questions == (FIRST, SECOND, THIRD)
    assert context.for_prompt.index(FIRST) < context.for_prompt.index(SECOND)
    assert context.for_prompt.index(SECOND) < context.for_prompt.index(THIRD)
    assert context.for_prompt.index(THIRD) < context.for_prompt.index(QUESTION_LEAD_IN)


# --- Prior answers, and the cost of leaving them out -----------------------------------


@pytest.mark.django_db
def test_a_prior_answer_never_reaches_the_prompt_or_the_query(document, service):
    """No model-generated text re-enters a prompt. Questions only, always.

    ``QueryLog.answer_text`` is one column away from the row the history is read out of
    and is never read. Asserted at both ends of the turn: the answer is in neither the
    embedded string nor the generation prompt, and the row it came from is unmistakably
    the row the history DID come from, because its question is there.
    """
    employee = document.uploaded_by
    conversation = make_conversation(employee)
    make_turn(conversation, employee, FIRST, minute=1, answer_text=PRIOR_ANSWER)
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days.")

    answer_question(question=FOLLOW_UP, user=employee, conversation=conversation)

    question_sent = sent_question(service)
    assert FIRST in question_sent  # the question was folded in
    assert PRIOR_ANSWER not in question_sent  # the answer to it was not
    assert "accrue each year" not in question_sent  # nor any fragment of it
    embedded = " ".join(text for call in service.embed_calls for text in call)
    assert FIRST in embedded
    assert PRIOR_ANSWER not in embedded


@pytest.mark.django_db
def test_an_unanswered_turn_is_still_a_turn(employee):
    """A question that hit a no-answer path is still what a follow-up refers to.

    Filtering the history to answered rows would drop exactly the turns a follow-up is
    most likely to be shortening: a user whose question was not answered rephrases it.
    """
    conversation = make_conversation(employee)
    make_turn(conversation, employee, FIRST, minute=1)  # unanswered: answer_text is NULL

    assert prior_questions(conversation=conversation, user=employee) == (FIRST,)


# --- Truncation ------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_history_is_truncated_to_the_most_recent_turns(employee):
    """FR-13 Validation: truncated to a maximum number of prior turns, oldest dropped.

    Written against the constant rather than the number 3, so the test still means what it
    says if MAXIMUM_CONVERSATION_TURNS is tuned.
    """
    conversation = make_conversation(employee)
    asked = [
        f"Question number {index} about the leave policy?"
        for index in range(MAXIMUM_CONVERSATION_TURNS + 1)
    ]
    for minute, question in enumerate(asked, start=1):
        make_turn(conversation, employee, question, minute=minute)

    context = conversation_context(
        question=FOLLOW_UP, conversation=conversation, user=employee
    )

    assert len(context.prior_questions) == MAXIMUM_CONVERSATION_TURNS
    assert context.prior_questions == tuple(asked[1:])  # the most recent, oldest first
    assert asked[0] not in context.for_prompt  # the oldest turn is gone, not merely last
    assert asked[0] not in context.for_retrieval


# --- Another user's conversation -------------------------------------------------------


@pytest.mark.django_db
def test_another_users_conversation_yields_no_history(employee, administrator):
    """A conversation id is a UUID a caller supplies. The history query filters on USER too.

    Supplying someone else's conversation must not return their questions — into this
    turn's query vector, into this turn's prompt, or into an answer. It yields NOTHING:
    not an error, which would confirm the id exists (invariant 1), and not a partial
    thread. The turn is simply answered as a one-off.
    """
    theirs = make_conversation(administrator, title="Their private thread")
    make_turn(theirs, administrator, "What is the redundancy payout schedule?", minute=1)
    make_turn(theirs, administrator, SECOND, minute=2)

    assert prior_questions(conversation=theirs, user=employee) == ()

    context = conversation_context(question=FOLLOW_UP, conversation=theirs, user=employee)

    assert context.prior_questions == ()
    assert context.for_retrieval == FOLLOW_UP
    assert context.for_prompt == FOLLOW_UP
    assert "redundancy payout" not in context.for_prompt


@pytest.mark.django_db
def test_another_users_questions_never_reach_the_provider(document, administrator, service):
    """The same guarantee at the boundary that matters: nothing of theirs is sent anywhere.

    The employee's turn runs against the administrator's conversation, which is what a
    caller passing a guessed or stolen id would produce if the view failed to authorise
    the row. Their question is in neither provider call.
    """
    employee = document.uploaded_by
    theirs = make_conversation(administrator, title="Their private thread")
    make_turn(theirs, administrator, "What is the redundancy payout schedule?", minute=1)
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days.")

    answer_question(question=FOLLOW_UP, user=employee, conversation=theirs)

    assert service.embed_calls == [[query_text(FOLLOW_UP)]]
    assert sent_question(service) == FOLLOW_UP
    assert "redundancy" not in sent_question(service)


# --- FR-13's re-evaluation clause ------------------------------------------------------


@pytest.mark.django_db
def test_a_follow_up_inherits_the_context_but_not_the_access(
    administrator, employee_role, service
):
    """Two turns of one conversation, with the role changed between them (FR-13).

    "The permission scope in FR-11 is re-evaluated on every turn rather than cached from
    the first, so that a follow-up cannot inherit access the user no longer holds." Turn
    one is asked as an Administrator and answers from Administrator-only material. The role
    is then changed with an UPDATE that leaves the in-memory user stale, so an
    implementation caching the scope — or carrying it on the conversation — would still
    answer Administrator on turn two.

    The two halves are the point: turn two DOES inherit the thread's questions, and does
    NOT inherit its access. The restricted passage appears in neither the answer, the
    passage list, nor the prompt.
    """
    from apps.documents.models import Document

    theirs = Document.objects.create(
        title="Redundancy schedule",
        file_type="pdf",
        uploaded_by=administrator,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )
    restricted = make_chunk(
        theirs, [ADMINISTRATOR_ROLE_NAME], index=1, cosine=NEAREST, text="Administrator only."
    )
    shared = make_chunk(
        theirs, [EMPLOYEE_ROLE_NAME], index=2, cosine=ABOVE, text="Everyone may read this."
    )
    conversation = make_conversation(administrator)

    first_turn = answer_question(question=FIRST, user=administrator, conversation=conversation)
    # Since D-66 an Administrator also reads the Employee-only chunk, so turn one is given both,
    # in rank order: the restricted one led the ranking.
    assert [passage.chunk_id for passage in first_turn.passages] == [
        str(restricted.id),
        str(shared.id),
    ]

    get_user_model().objects.filter(pk=administrator.pk).update(role=employee_role)
    assert administrator.role.role_name == ADMINISTRATOR_ROLE_NAME  # the copy is stale

    second_turn = answer_question(
        question=FOLLOW_UP, user=administrator, conversation=conversation
    )

    # The scope was re-read: the restricted chunk scored NEAREST and would have led the
    # ranking, and it is not in the reply at all.
    assert [passage.chunk_id for passage in second_turn.passages] == [str(shared.id)]
    assert str(restricted.id) not in [
        statement.chunk_id for statement in second_turn.verified_statements
    ]
    # Nor in the prompt, which is the invariant-1 boundary.
    question_sent, passages_sent = service.generate_calls[-1]
    assert [passage.chunk_id for passage in passages_sent] == [str(shared.id)]
    assert "Administrator only." not in question_sent
    assert str(restricted.id) not in question_sent
    # The thread's context DID carry over: turn one's question is in turn two's prompt.
    assert FIRST in question_sent
    assert PRIOR_QUESTIONS_HEADING in question_sent


@pytest.mark.django_db
def test_each_turn_retrieves_afresh(document, service):
    """FR-13: a fresh retrieval per turn, never the previous turn's passages reused.

    The chunk that answers turn two is created AFTER turn one has been answered, so a
    cached or carried-forward candidate set could not contain it. Two embedding calls and
    two generation calls, and the second turn's passages are not the first's.
    """
    employee = document.uploaded_by
    conversation = make_conversation(employee)
    first_chunk = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days."
    )

    first_turn = answer_question(question=FIRST, user=employee, conversation=conversation)
    assert [passage.chunk_id for passage in first_turn.passages] == [str(first_chunk.id)]

    later_chunk = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=2, cosine=NEAREST, text="Part-timers accrue pro rata."
    )

    second_turn = answer_question(
        question=FOLLOW_UP, user=employee, conversation=conversation
    )

    assert len(service.embed_calls) == 2
    assert len(service.generate_calls) == 2
    # Ranked afresh: the new chunk scores higher and leads.
    assert [passage.chunk_id for passage in second_turn.passages] == [
        str(later_chunk.id),
        str(first_chunk.id),
    ]
    # And the second embedding call is the composed string, not the bare follow-up.
    assert service.embed_calls[0] == [query_text(FIRST)]
    assert service.embed_calls[1] == [query_text(RETRIEVAL_JOIN.join([FIRST, FOLLOW_UP]))]


# --- Verification is indifferent to where in the prompt an identifier came from --------


@pytest.mark.django_db
def test_an_identifier_seen_only_among_the_earlier_questions_is_rejected(
    document, administrator, service_with
):
    """D-39's lesson in its new form: the history is not a source of identifiers.

    A user's earlier question can contain anything the user typed — here the UUID of a
    chunk the asking role may not even read, which is the worst case rather than an
    unlikely one. The model is scripted to cite it, as a model given an identifier-shaped
    token in a prompt demonstrably does. ``verify_citations`` checks set membership against
    the identifiers the PASSAGE BLOCK supplied, so the statement is removed, and the turn
    ends on no-answer path B with nothing of the restricted material in the reply.

    This is why the labelled block says the earlier questions carry no chunk_id, and why
    that labelling is not the thing relied on: the guarantee is application code.
    """
    from apps.documents.models import Document

    employee = document.uploaded_by
    theirs = Document.objects.create(
        title="Redundancy schedule",
        file_type="pdf",
        uploaded_by=administrator,
        visible_to_roles=[ADMINISTRATOR_ROLE_NAME],
    )
    restricted = make_chunk(
        theirs, [ADMINISTRATOR_ROLE_NAME], index=1, cosine=NEAREST, text="Administrator only."
    )
    visible = make_chunk(
        document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days."
    )

    conversation = make_conversation(employee)
    make_turn(conversation, employee, f"What does {restricted.id} say about leave?", minute=1)

    double = service_with(
        statements=[
            Statement(text="The restricted document says otherwise.", chunk_id=str(restricted.id))
        ]
    )

    outcome = answer_question(question=FOLLOW_UP, user=employee, conversation=conversation)

    # The identifier WAS in the prompt, among the earlier questions, and was not a passage.
    question_sent, passages_sent = double.generate_calls[0]
    assert str(restricted.id) in question_sent
    assert [passage.chunk_id for passage in passages_sent] == [str(visible.id)]
    # And it was rejected, because membership is checked against the supplied passages.
    assert outcome.answered is False
    assert outcome.no_answer_reason == NO_STATEMENT_VERIFIED
    assert outcome.no_answer_reason != NO_RELEVANT_PASSAGE
    assert outcome.message == NO_ANSWER_MESSAGE
    assert outcome.verified_statements == ()
    assert outcome.rejected_count == 1
    assert outcome.result_count == 0
    # Nothing of the restricted chunk reached the reply or the citations.
    row = QueryLog.objects.get(conversation=conversation, question=FOLLOW_UP)
    assert row.answer_text is None
    assert row.citations.count() == 0
    assert row.retrieved_chunk_ids == [visible.id]


# --- The record ------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_row_carries_the_conversation_and_the_question_as_asked(document, service):
    """The turn's QueryLog row: the thread it belongs to, and the user's own question.

    The composed string is never stored. Storing it would put every predecessor in every
    follow-up's row — the log would repeat itself and grow quadratically in a long thread —
    and the thread is already reconstructible from ``conversation_id`` and ``answered_at``.
    """
    employee = document.uploaded_by
    conversation = make_conversation(employee)
    make_turn(conversation, employee, FIRST, minute=1, answer_text=PRIOR_ANSWER)
    chunk = make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days.")

    outcome = answer_question(question=FOLLOW_UP, user=employee, conversation=conversation)

    assert outcome.answered is True
    row = QueryLog.objects.get(question=FOLLOW_UP)
    assert row.conversation == conversation
    assert row.user == employee
    assert row.question == FOLLOW_UP  # bare, not composed
    assert FIRST not in row.question
    assert PRIOR_QUESTIONS_HEADING not in row.question
    assert row.retrieved_chunk_ids == [chunk.id]
    # The thread now holds two turns, and the earlier one is untouched.
    assert QueryLog.objects.filter(conversation=conversation).count() == 2


@pytest.mark.django_db
def test_every_turn_moves_the_conversations_last_updated_at(document, service):
    """``last_updated_at`` is auto_now, so saving the row is what orders a user's threads.

    Touched by the pipeline, inside the record's transaction, because that is the code that
    knows a turn happened. Asserted on an ANSWERED turn and on a no-answer turn: a question
    that could not be answered is still activity in the thread. Each turn starts from the
    timestamp set back to THREAD_START (``touched_at_thread_start``), so that "moved" cannot
    read as "equal".
    """
    employee = document.uploaded_by
    conversation = make_conversation(employee)
    make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, cosine=ABOVE, text="Twenty days.")
    before_answer = touched_at_thread_start(conversation)

    answer_question(question=FIRST, user=employee, conversation=conversation)
    conversation.refresh_from_db()
    assert conversation.last_updated_at > before_answer

    # A no-answer turn. The corpus is emptied, so nothing clears the threshold: path A.
    ContentChunk.objects.all().delete()
    before_no_answer = touched_at_thread_start(conversation)
    outcome = answer_question(question=FOLLOW_UP, user=employee, conversation=conversation)
    conversation.refresh_from_db()

    assert outcome.no_answer_reason == NO_RELEVANT_PASSAGE
    assert conversation.last_updated_at > before_no_answer


@pytest.mark.django_db
def test_a_rejected_question_leaves_the_thread_exactly_as_it_was(employee, service):
    """Failure path: no row, no touch. A query that never ran is not a turn.

    The same rule the rest of the log follows — a question rejected for its length and a
    provider outage record nothing — extended to the thread's timestamp, which would
    otherwise claim activity that left no evidence.
    """
    conversation = make_conversation(employee)
    # Set back first, so that a touch landing in the same step of the clock as the create
    # could not pass for no touch at all (touched_at_thread_start).
    before = touched_at_thread_start(conversation)

    with pytest.raises(QuestionLengthOutOfRange):
        answer_question(
            question="x" * (MINIMUM_QUESTION_LENGTH - 1),
            user=employee,
            conversation=conversation,
        )

    conversation.refresh_from_db()
    assert conversation.last_updated_at == before
    assert QueryLog.objects.count() == 0
    assert service.embed_calls == []


# --- Both roles ------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_conversation_turn_works_from_both_roles(session_client, administrator, service):
    """CLAUDE.md section 8 item 2: the requirement exercised from Employee and Administrator.

    Run through ``answer_question`` rather than a client, because FR-13's endpoint is the
    view layer's (item 11) and does not exist yet; ``session_client`` is still what supplies
    a user of each role, so this file's coverage moves with the fixture when it does.
    """
    from apps.documents.models import Document

    user = session_client.user
    document = Document.objects.create(
        title="Leave policy",
        file_type="pdf",
        uploaded_by=administrator,
        visible_to_roles=list(ROLE_PAIR),
    )
    chunk = make_chunk(document, list(ROLE_PAIR), index=1, cosine=ABOVE, text="Twenty days.")
    conversation = make_conversation(user)
    make_turn(conversation, user, FIRST, minute=1, answer_text=PRIOR_ANSWER)

    outcome = answer_question(question=FOLLOW_UP, user=user, conversation=conversation)

    assert session_client.role_name in ROLE_PAIR
    assert outcome.answered is True
    assert [passage.chunk_id for passage in outcome.passages] == [str(chunk.id)]
    question_sent = sent_question(service)
    assert FIRST in question_sent
    assert PRIOR_ANSWER not in question_sent
    row = QueryLog.objects.get(question=FOLLOW_UP)
    assert row.conversation == conversation
    assert row.user == user


# --- The history of a row already logged (D-127) ----------------------------------------------
# FR-19's aggregation cycle rebuilds the string retrieval ranked for a follow-up, after the fact.
# ``prior_questions_before`` has to return what ``prior_questions`` returned when the row was asked.


@pytest.mark.django_db
def test_the_history_of_a_logged_turn_is_the_history_it_was_asked_with(employee):
    """For every turn of a thread longer than the limit: what ``prior_questions`` returned just
    before the turn was logged is what ``prior_questions_before`` returns for it afterwards,
    with later turns in the thread by then."""
    conversation = make_conversation(employee)
    asked_with, turns = [], []
    for minute in range(1, MAXIMUM_CONVERSATION_TURNS + 4):
        asked_with.append(prior_questions(conversation=conversation, user=employee))
        turns.append(make_turn(conversation, employee, f"Question number {minute}?", minute=minute))

    assert [prior_questions_before(turn) for turn in turns] == asked_with
    # The premise: the thread outgrew the limit, so the limit and the order were both exercised.
    assert asked_with[0] == () and len(asked_with[-1]) == MAXIMUM_CONVERSATION_TURNS
    assert asked_with[-1][-1] == turns[-2].question


@pytest.mark.django_db
def test_a_logged_one_off_has_no_history(employee):
    """A one-off question is never composed: not with a conversation's turns, and not with the
    user's earlier one-off questions, which share its empty conversation."""
    conversation = make_conversation(employee)
    make_turn(conversation, employee, FIRST, minute=1)
    make_turn(None, employee, "An earlier one-off question?", minute=2)
    one_off = make_turn(None, employee, FOLLOW_UP, minute=3)

    assert prior_questions_before(one_off) == ()


@pytest.mark.django_db
def test_a_logged_turns_history_is_its_own_conversations_and_its_own_users(employee, administrator):
    """Both predicates, always, as in ``prior_questions``: a row of another conversation, and a
    row another user wrote into this one, are not this turn's history."""
    conversation = make_conversation(employee)
    elsewhere = make_conversation(employee, title="Another thread")
    make_turn(conversation, employee, FIRST, minute=1)
    make_turn(elsewhere, employee, "A question in another thread?", minute=2)
    make_turn(conversation, administrator, "A row another user wrote here?", minute=3)
    turn = make_turn(conversation, employee, FOLLOW_UP, minute=4)

    assert prior_questions_before(turn) == (FIRST,)


@pytest.mark.django_db
def test_two_turns_at_one_instant_are_ordered_as_the_ask_path_orders_them(employee):
    """A tie on ``answered_at`` is decided by the primary key, in ``prior_questions`` and here
    alike, so exactly one of the two rows has the other in its history."""
    conversation = make_conversation(employee)
    one = make_turn(conversation, employee, "One of two at the same instant?", minute=1)
    other = make_turn(conversation, employee, "The other of the two?", minute=1)
    assert one.answered_at == other.answered_at  # the premise

    first, second = sorted([one, other], key=lambda row: str(row.pk).replace("-", ""))

    assert prior_questions_before(first) == ()
    assert prior_questions_before(second) == (first.question,)
    # The ask path reads the same order: its newest row is the one that has the other before it.
    assert prior_questions(conversation=conversation, user=employee) == (first.question, second.question)
