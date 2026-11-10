"""FR-19's aggregation cycle (apps/retrieval/gaps.py): the window, the exclusion, the grouping.

Built to docs/decisions.md D-107 (the tables and the cycle), D-108 (the permission exclusion) and
D-109 (similarity grouping). Each test reads one clause:

- FR-19 Server-End: unanswered queries and zero-result searches are aggregated, FR-13's turns
  included, "on a scheduled basis";
- Validation: "queries that returned nothing because the user lacked access are excluded";
- Business logic: "entries are grouped by similarity rather than exact wording".

**The vectors are designed, never the stub's.** ``DesignedService`` answers each text with a
vector chosen here, so every cosine, every ranking and every threshold crossing below is a
number this file decided. The stub's hash-seeded vectors are near-orthogonal noise and could
prove nothing about grouping. The vectors sit on a few axes of an ``EMBEDDING_DIMENSION``-wide
space; ``unit``, ``at_cosine`` and ``at_angle`` build them. **The grouping vectors are derived from
GAP_GROUPING_THRESHOLD**, as fractions of the angle whose cosine it is, never from a literal
cosine, so the tests follow the constant wherever D-109's sweep puts it.

**Timestamps are set, never left to the clock.** ``auto_now_add`` ignores a value passed to
``create()``, so ``answered_at`` and ``searched_at`` are written with ``update()``, hours away
from now. On this Windows machine two timestamps can be equal (about 15.6 ms ticks), so no test
relies on a row created a moment before a cycle being earlier than that cycle's start.
"""

from datetime import timedelta
from math import acos, cos, sin, sqrt

import pytest
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

import apps.ai
from apps.ai.base import EmbeddingResult, ProviderUnavailable
from apps.ai.prefixes import QUERY_TEMPLATE, query_text
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    CYCLE_GRACE_SECONDS,
    EMPLOYEE_ROLE_NAME,
    GAP_GROUPING_THRESHOLD,
    GAP_GROUPING_THRESHOLD_BY_MODEL,
    KNOWLEDGE_GAP_ADDRESSED,
    KNOWLEDGE_GAP_OPEN,
    MAXIMUM_EMBED_ATTEMPTS,
    NO_RELEVANT_PASSAGE,
    NO_STATEMENT_VERIFIED,
    RELEVANCE_THRESHOLD,
    SOURCE_TYPES,
)
from apps.documents.models import ContentChunk, Document
from apps.retrieval import gaps
from apps.retrieval.gaps import ordered_gaps, run_cycle
from apps.retrieval.models import (
    Conversation,
    KnowledgeGap,
    KnowledgeGapCycle,
    KnowledgeGapItem,
    QueryLog,
    SearchLog,
)
from apps.retrieval.ranking import cosine_similarity

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]
QUERY_PREFIX = QUERY_TEMPLATE.format(content="")

# The premise the exclusion's designed cosines rely on, so a retuned constant fails here, by name.
assert RELEVANCE_THRESHOLD < 0.40
# The grouping threshold as an angle: an item within GROUPING_ANGLE of an entry's centroid joins
# it, and one further away does not. Orthogonal vectors (cosine 0) stay apart only while the
# threshold is above 0, which every value D-109's rule can give is.
assert 0.0 < GAP_GROUPING_THRESHOLD < 1.0
GROUPING_ANGLE = acos(GAP_GROUPING_THRESHOLD)


# --- Vectors ---------------------------------------------------------------------------------


def unit(axis: int) -> list[float]:
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[axis] = 1.0
    return vector


def at_cosine(value: float, *, axis: int, towards: int) -> list[float]:
    """A unit vector whose cosine with ``unit(axis)`` is ``value``, leaning towards ``towards``."""
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[axis] = value
    vector[towards] = sqrt(1.0 - value * value)
    return vector


def at_angle(fraction: float, *, axis: int, towards: int) -> list[float]:
    """A unit vector at ``fraction`` of GROUPING_ANGLE from ``unit(axis)``, leaning towards ``towards``.

    Below 1 its cosine with ``unit(axis)`` is above GAP_GROUPING_THRESHOLD; above 1, below it.
    """
    angle = fraction * GROUPING_ANGLE
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[axis] = cos(angle)
    vector[towards] = sin(angle)
    return vector


def normalised(vector):
    length = sqrt(sum(value * value for value in vector))
    return [value / length for value in vector]


class DesignedService:
    """An AIService whose embedding of each text is chosen by the test.

    ``vectors`` maps a text, as asked or searched, to its vector. The text arrives wrapped in the
    query prefix when the configured model takes one (apps/ai/prefixes.py), so the prefix is
    taken off to look the text up, and every text received is recorded in ``embed_calls`` so a
    test can assert the prefix was applied. A text named in ``down_for`` raises
    ProviderUnavailable on every attempt. A text nobody designed is a KeyError: a test that
    forgot a vector should fail loudly rather than group by accident.
    """

    def __init__(self, vectors, *, model=STUB_EMBEDDING_MODEL, down_for=()):
        self.vectors = vectors
        self.model = model
        self.down_for = set(down_for)
        self.embed_calls: list[list[str]] = []

    def embed(self, texts, *, input_type=None):
        self.embed_calls.append(list(texts))
        [text] = texts
        raw = text[len(QUERY_PREFIX):] if text.startswith(QUERY_PREFIX) else text
        if raw in self.down_for:
            raise ProviderUnavailable(f"designed outage for {raw!r}")
        return EmbeddingResult(
            vectors=[list(self.vectors[raw])], model=self.model, dimension=settings.EMBEDDING_DIMENSION
        )

    def generate_statements(self, question, passages):
        raise AssertionError("the aggregation cycle never generates")

    def health(self):
        raise AssertionError("the aggregation cycle does not check provider health")


@pytest.fixture
def designed(monkeypatch):
    """Install a DesignedService where apps.ai.get_ai_service is looked up at call time."""

    def install(vectors, **options):
        service = DesignedService(vectors, **options)
        monkeypatch.setattr(apps.ai, "get_ai_service", lambda: service)
        return service

    return install


# --- Rows ------------------------------------------------------------------------------------


def hours_ago(hours: float):
    return timezone.now() - timedelta(hours=hours)


def ask(user, question, *, at, answered=False, conversation=None):
    """A QueryLog row as the pipeline writes it, at a set time."""
    row = QueryLog.objects.create(
        user=user,
        conversation=conversation,
        question=question,
        answered=answered,
        answer_text="An answer." if answered else None,
        no_answer_reason=None if answered else NO_RELEVANT_PASSAGE,
    )
    QueryLog.objects.filter(pk=row.pk).update(answered_at=at)
    row.refresh_from_db()
    return row


def searched(user, term, *, at, result_count=0):
    """A SearchLog row as search() writes it, at a set time."""
    row = SearchLog.objects.create(user=user, query_text=term, result_count=result_count)
    SearchLog.objects.filter(pk=row.pk).update(searched_at=at)
    row.refresh_from_db()
    return row


def stored_chunk(*, title, text, vector, roles, uploader):
    """A document and its one chunk, stamped alike (D-17), with a designed vector."""
    document = Document.objects.create(
        title=title, file_type="pdf", uploaded_by=uploader, visible_to_roles=roles
    )
    return ContentChunk.objects.create(
        source_type=DOCUMENT_SOURCE_TYPE,
        source_id=document.id,
        chunk_index=0,
        chunk_text=text,
        embedding=vector,
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )


def in_log(row) -> bool:
    if isinstance(row, QueryLog):
        return KnowledgeGapItem.objects.filter(query=row).exists()
    return KnowledgeGapItem.objects.filter(search=row).exists()


def gap_of(row) -> KnowledgeGap:
    if isinstance(row, QueryLog):
        return KnowledgeGapItem.objects.select_related("gap").get(query=row).gap
    return KnowledgeGapItem.objects.select_related("gap").get(search=row).gap


def move_cycle_back(cycle, *, to):
    """Pretend ``cycle`` started at ``to``: the next cycle's window is measured from it."""
    KnowledgeGapCycle.objects.filter(pk=cycle.pk).update(started_at=to)


# --- The window (D-107) ----------------------------------------------------------------------

Q_OLD = "Where is the policy on bringing dogs to the office?"
Q_RECENT = "How do I book the rooftop terrace for a team lunch?"
S_OLD = "parking permit"
Q_ANSWERED = "How much annual leave do I get each year?"
S_FOUND = "annual leave"


@pytest.fixture
def window_vectors(designed):
    # Every text far from every other, so each starts its own entry and none is grouped.
    return designed(
        {Q_OLD: unit(10), Q_RECENT: unit(11), S_OLD: unit(12), Q_ANSWERED: unit(13), S_FOUND: unit(14)}
    )


def test_the_first_cycle_takes_every_unanswered_question_and_zero_result_search(
    window_vectors, employee, administrator
):
    old = ask(employee, Q_OLD, at=hours_ago(72))
    recent = ask(administrator, Q_RECENT, at=hours_ago(1))
    search = searched(employee, S_OLD, at=hours_ago(30))

    cycle = run_cycle()

    assert all(in_log(row) for row in (old, recent, search))
    assert KnowledgeGap.objects.count() == 3
    assert (cycle.queries_considered, cycle.searches_considered) == (2, 1)
    assert (cycle.entries_created, cycle.entries_updated) == (3, 0)


def test_answered_questions_and_searches_with_results_are_never_considered(
    window_vectors, employee
):
    answered = ask(employee, Q_ANSWERED, at=hours_ago(2), answered=True)
    found = searched(employee, S_FOUND, at=hours_ago(2), result_count=3)

    cycle = run_cycle()

    assert not in_log(answered) and not in_log(found)
    assert KnowledgeGap.objects.count() == 0
    assert (cycle.queries_considered, cycle.searches_considered) == (0, 0)
    # Neither was even embedded: they never entered the window.
    assert window_vectors.embed_calls == []


def test_a_second_cycle_takes_only_rows_new_since_the_first(window_vectors, employee):
    taken_first = ask(employee, Q_OLD, at=hours_ago(1))
    first = run_cycle()
    assert in_log(taken_first)
    # The first cycle started two hours ago, so its window's lower bound is two hours and a
    # minute ago, and the row it took at one hour ago now sits inside the second window.
    move_cycle_back(first, to=hours_ago(2))
    new = ask(employee, Q_RECENT, at=hours_ago(0.5))
    before_the_window = searched(employee, S_OLD, at=hours_ago(3))
    window_vectors.embed_calls.clear()

    second = run_cycle()

    assert in_log(new)
    assert not in_log(before_the_window)
    # Re-scanned and counted once: still one item, still a count of one.
    assert KnowledgeGapItem.objects.filter(query=taken_first).count() == 1
    assert gap_of(taken_first).occurrence_count == 1
    assert (second.queries_considered, second.searches_considered) == (1, 0)
    assert second.entries_created == 1
    # Only the new row was embedded: a row already in the log is skipped before anything runs.
    assert window_vectors.embed_calls == [[query_text(Q_RECENT)]]


def test_the_grace_reaches_back_cycle_grace_seconds_before_the_previous_start(window_vectors, employee):
    first = run_cycle()  # nothing to take
    previous_start = hours_ago(2)
    move_cycle_back(first, to=previous_start)
    inside_grace = ask(employee, Q_OLD, at=previous_start - timedelta(seconds=CYCLE_GRACE_SECONDS - 30))
    outside_grace = ask(employee, Q_RECENT, at=previous_start - timedelta(seconds=CYCLE_GRACE_SECONDS + 30))

    run_cycle()

    assert in_log(inside_grace)
    assert not in_log(outside_grace)


def test_a_row_stamped_after_the_cycle_started_waits_for_the_next(window_vectors, employee):
    future = ask(employee, Q_OLD, at=timezone.now() + timedelta(hours=1))

    cycle = run_cycle()

    assert not in_log(future)
    assert cycle.queries_considered == 0


def test_a_conversation_turn_is_aggregated_on_its_own_wording(window_vectors, employee):
    """FR-13's turns are included (FR-19 Server-End), and each is embedded on its own wording,
    not composed with the turns before it (D-108's step 2)."""
    thread = Conversation.objects.create(user=employee, title="Office questions")
    ask(employee, Q_RECENT, at=hours_ago(3), conversation=thread)
    turn = ask(employee, Q_OLD, at=hours_ago(2), conversation=thread)

    run_cycle()

    assert in_log(turn)
    assert gap_of(turn).subject == Q_OLD
    # Each with the query prefix, as retrieval embeds a question, and alone.
    assert window_vectors.embed_calls == [[query_text(Q_RECENT)], [query_text(Q_OLD)]]


# --- The exclusion (D-108) -------------------------------------------------------------------

RESTRICTED_TEXT = "The succession register names two candidates for the chair."
READABLE_TEXT = "Staff may work from home two days a week with a manager's agreement."

Q_RESTRICTED = "Who is on the succession register for the chair?"  # top: the restricted chunk
Q_READABLE = "How many days a week can I work from home?"  # top: the readable chunk
Q_RESTRICTED_FIRST = "Is the chair's succession linked to home working?"  # both admitted, restricted top
Q_READABLE_FIRST = "Do home working days affect the chair's succession?"  # both admitted, readable top
# Below RELEVANCE_THRESHOLD everywhere (0.25 with one chunk, 0 with the other): the top-ranked
# passage still decides (D-108's note of 10 November 2026).
Q_RESTRICTED_BELOW = "Is the chair's succession being talked about?"  # top: the restricted chunk, 0.25
Q_READABLE_BELOW = "Are the home working days changing next year?"  # top: the readable chunk, 0.25
S_RESTRICTED = "succession register"  # matches the restricted chunk only
S_NOWHERE = "volcano insurance"  # matches nothing anywhere


@pytest.fixture
def corpus(administrator, designed):
    """One Administrator-only chunk on axis 0, one chunk both roles read on axis 1."""
    restricted = stored_chunk(
        title="Board succession", text=RESTRICTED_TEXT, vector=unit(0),
        roles=ADMINISTRATOR_ONLY, uploader=administrator,
    )
    readable = stored_chunk(
        title="Hybrid work policy", text=READABLE_TEXT, vector=unit(1),
        roles=BOTH_ROLES, uploader=administrator,
    )
    service = designed(
        {
            Q_RESTRICTED: unit(0),
            Q_READABLE: unit(1),
            # 0.9 with the restricted chunk and 0.436 with the readable one: both above
            # RELEVANCE_THRESHOLD, and the restricted one ranks first.
            Q_RESTRICTED_FIRST: at_cosine(0.9, axis=0, towards=1),
            Q_READABLE_FIRST: at_cosine(0.9, axis=1, towards=0),
            Q_RESTRICTED_BELOW: at_cosine(0.25, axis=0, towards=5),
            Q_READABLE_BELOW: at_cosine(0.25, axis=1, towards=5),
            S_NOWHERE: unit(6),
        }
    )
    return {"restricted": restricted, "readable": readable, "service": service}


def test_an_employees_question_whose_top_passage_is_administrator_only_is_left_out(corpus, employee):
    row = ask(employee, Q_RESTRICTED, at=hours_ago(1))

    cycle = run_cycle()

    assert not in_log(row)
    assert KnowledgeGap.objects.count() == 0
    assert cycle.queries_considered == 0
    # Nothing records it: no entry carries its words, and the row itself is untouched.
    assert not KnowledgeGap.objects.filter(subject__icontains="succession").exists()
    assert QueryLog.objects.get(pk=row.pk).question == Q_RESTRICTED


def test_an_employees_question_whose_top_passage_is_readable_is_kept(corpus, employee):
    row = ask(employee, Q_READABLE, at=hours_ago(1))

    run_cycle()

    assert in_log(row)
    assert gap_of(row).subject == Q_READABLE


def test_the_top_ranked_passage_decides_not_any_withheld_passage(corpus, employee):
    """D-108 declined "any withheld passage above the threshold". Both questions admit both
    chunks; only the one whose best match is withheld is left out."""
    restricted_first = ask(employee, Q_RESTRICTED_FIRST, at=hours_ago(2))
    readable_first = ask(employee, Q_READABLE_FIRST, at=hours_ago(1))

    run_cycle()

    assert not in_log(restricted_first)
    assert in_log(readable_first)


def test_an_administrators_unanswered_question_is_always_kept(corpus, administrator):
    """Every chunk in the Administrator's scope is readable by the Administrator (D-66)."""
    rows = [
        ask(administrator, Q_RESTRICTED, at=hours_ago(3)),
        ask(administrator, Q_RESTRICTED_FIRST, at=hours_ago(2)),
        ask(administrator, Q_READABLE, at=hours_ago(1)),
    ]

    run_cycle()

    assert all(in_log(row) for row in rows)


def test_a_question_whose_best_passage_is_restricted_is_left_out_below_the_threshold(corpus, employee):
    """Objective 06's P02, in miniature: nothing clears RELEVANCE_THRESHOLD, but the best evidence
    for an answer is Administrator-only, so the no-answer is a permission matter (D-108's note of
    10 November 2026). The rule as first built kept this row."""
    assert 0.25 < RELEVANCE_THRESHOLD  # the premise: below the threshold
    row = ask(employee, Q_RESTRICTED_BELOW, at=hours_ago(1))

    run_cycle()

    assert not in_log(row)


def test_a_question_whose_best_passage_is_readable_is_kept_below_the_threshold(corpus, employee):
    """Nothing clears RELEVANCE_THRESHOLD and the best passage is one the asker may read: a gap."""
    row = ask(employee, Q_READABLE_BELOW, at=hours_ago(1))

    run_cycle()

    assert in_log(row)


def test_an_unanswered_row_from_path_b_is_aggregated_like_path_a(corpus, employee):
    """Both no-answer paths are unanswered (invariant 7); the cycle reads ``answered`` alone."""
    row = ask(employee, Q_READABLE, at=hours_ago(1))
    QueryLog.objects.filter(pk=row.pk).update(no_answer_reason=NO_STATEMENT_VERIFIED, rejected_count=0)

    run_cycle()

    assert in_log(row)


def test_a_zero_result_search_the_administrator_would_find_is_left_out(corpus, employee):
    row = searched(employee, S_RESTRICTED, at=hours_ago(1))

    cycle = run_cycle()

    assert not in_log(row)
    assert cycle.searches_considered == 0
    assert not KnowledgeGap.objects.filter(subject__icontains="succession").exists()
    # Left out before it was embedded: a recount is all it took.
    assert [query_text(S_RESTRICTED)] not in corpus["service"].embed_calls
    # The recount wrote no SearchLog row.
    assert SearchLog.objects.count() == 1


def test_a_zero_result_search_nobody_could_find_is_kept(corpus, employee):
    row = searched(employee, S_NOWHERE, at=hours_ago(1))

    cycle = run_cycle()

    assert in_log(row)
    assert gap_of(row).subject == S_NOWHERE
    assert cycle.searches_considered == 1
    assert SearchLog.objects.count() == 1


def test_a_row_left_out_is_left_out_again_when_a_later_cycle_rescans_it(corpus, employee):
    row = ask(employee, Q_RESTRICTED, at=hours_ago(1))
    first = run_cycle()
    move_cycle_back(first, to=hours_ago(1) + timedelta(seconds=CYCLE_GRACE_SECONDS // 2))

    second = run_cycle()

    assert not in_log(row)
    assert second.queries_considered == 0


def test_the_asker_role_is_read_from_the_user_row_at_cycle_time(corpus, employee, administrator_role):
    """D-108 step 1, and its stated limitation: the log holds no role, so the role now decides."""
    row = ask(employee, Q_RESTRICTED, at=hours_ago(1))
    employee.role = administrator_role
    employee.save(update_fields=["role"])

    run_cycle()

    assert in_log(row)


def test_the_payload_of_the_exclusion_reaches_no_column(corpus, employee):
    """No table FR-19 writes has a column for an asker, a role or a reason (D-107)."""
    for model in (KnowledgeGap, KnowledgeGapItem, KnowledgeGapCycle):
        names = {field.name for field in model._meta.get_fields()}
        assert names.isdisjoint({"user", "asker", "role", "role_name", "reason", "excluded", "left_out"})


# --- The grouping (D-109) --------------------------------------------------------------------

FIRST_WORDING = "How do I claim back the cost of a train ticket?"
SECOND_WORDING = "What is the process for reimbursing rail fares?"
SEARCH_WORDING = "train fare refund"
UNRELATED = "Can I bring a bicycle into the building?"


def test_two_wordings_at_or_above_the_threshold_join_one_entry(designed, employee, administrator):
    first_vector = unit(20)
    second_vector = at_angle(0.5, axis=20, towards=21)
    assert cosine_similarity(first_vector, second_vector) >= GAP_GROUPING_THRESHOLD  # the premise
    designed({FIRST_WORDING: first_vector, SECOND_WORDING: second_vector})
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(administrator, SECOND_WORDING, at=hours_ago(1))

    cycle = run_cycle()

    gap = gap_of(first)
    assert gap_of(second) == gap
    assert KnowledgeGap.objects.count() == 1
    assert gap.occurrence_count == 2 == gap.items.count()
    # The first member's wording, verbatim, and the newest member's time.
    assert gap.subject == FIRST_WORDING
    assert gap.first_seen_at == first.answered_at
    assert gap.last_seen_at == second.answered_at
    # The centroid moved from the first vector to the members' mean, whose direction is the
    # normalised mean D-109 names.
    stored = [float(value) for value in gap.embedding]
    assert stored != first_vector
    mean = [(a + b) / 2 for a, b in zip(first_vector, second_vector)]
    assert stored == pytest.approx(mean, abs=1e-6)
    assert cosine_similarity(stored, normalised([a + b for a, b in zip(first_vector, second_vector)])) == pytest.approx(1.0)
    assert (cycle.entries_created, cycle.entries_updated) == (1, 0)


def test_two_wordings_below_the_threshold_stay_apart(designed, employee):
    second_vector = at_angle(1.5, axis=20, towards=21)
    assert cosine_similarity(unit(20), second_vector) < GAP_GROUPING_THRESHOLD  # the premise
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: second_vector})
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) != gap_of(second)
    assert KnowledgeGap.objects.count() == 2
    assert [gap.occurrence_count for gap in KnowledgeGap.objects.all()] == [1, 1]


def test_an_item_exactly_on_the_threshold_joins(designed, employee, monkeypatch):
    """D-109 says "at least", so ``>=``. The cosine here is exactly 0.5 in floating point: a
    unit vector against (1, 1, 1, 1), whose length is exactly 2.

    The threshold is patched to 0.5 for this test alone, because ``>=`` against ``>`` can only be
    told apart by a cosine that equals the threshold exactly, and the shipped 0.5256 has no exact
    binary form for a designed cosine to equal. Every other test uses the shipped constant."""
    monkeypatch.setattr(gaps, "GAP_GROUPING_THRESHOLD", 0.5)
    on_the_line = [0.0] * settings.EMBEDDING_DIMENSION
    for axis in (20, 21, 22, 23):
        on_the_line[axis] = 1.0
    assert cosine_similarity(unit(20), on_the_line) == 0.5
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: on_the_line})
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) == gap_of(second)


def test_a_search_term_groups_with_the_questions_on_its_subject(designed, employee):
    designed(
        {
            FIRST_WORDING: unit(20),
            SECOND_WORDING: at_angle(0.4, axis=20, towards=21),
            SEARCH_WORDING: at_angle(0.4, axis=20, towards=22),
            UNRELATED: unit(30),
        }
    )
    rows = [
        ask(employee, FIRST_WORDING, at=hours_ago(4)),
        searched(employee, SEARCH_WORDING, at=hours_ago(3)),
        ask(employee, UNRELATED, at=hours_ago(2)),
        ask(employee, SECOND_WORDING, at=hours_ago(1)),
    ]

    cycle = run_cycle()

    subject_gap = gap_of(rows[0])
    assert gap_of(rows[1]) == gap_of(rows[3]) == subject_gap
    assert gap_of(rows[2]) != subject_gap
    assert subject_gap.occurrence_count == 3
    assert (cycle.queries_considered, cycle.searches_considered) == (3, 1)
    assert (cycle.entries_created, cycle.entries_updated) == (2, 0)


def test_an_addressed_entry_is_not_joined(designed, employee):
    """D-109: a subject that recurs after being addressed opens a new entry."""
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: at_angle(0.4, axis=20, towards=21)})
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    move_cycle_back(run_cycle(), to=hours_ago(2))
    addressed = gap_of(first)
    KnowledgeGap.objects.filter(pk=addressed.pk).update(status=KNOWLEDGE_GAP_ADDRESSED)
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    cycle = run_cycle()

    assert gap_of(second) != addressed
    assert gap_of(second).status == KNOWLEDGE_GAP_OPEN
    addressed.refresh_from_db()
    assert addressed.occurrence_count == 1
    assert addressed.status == KNOWLEDGE_GAP_ADDRESSED
    assert (cycle.entries_created, cycle.entries_updated) == (1, 0)


def test_an_entry_from_another_embedding_model_is_not_joined(designed, employee):
    """Risk R10: an identical vector from another model is not comparable, so it starts anew."""
    designed({FIRST_WORDING: unit(20)}, model="model-a")
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    move_cycle_back(run_cycle(), to=hours_ago(2))
    designed({SECOND_WORDING: unit(20)}, model="model-b")
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) != gap_of(second)
    assert gap_of(first).embedding_model == "model-a"
    assert gap_of(second).embedding_model == "model-b"
    assert gap_of(first).occurrence_count == 1


BETWEEN_THE_TWO_VALUES = 0.515  # above voyage-4's 0.5054, below GAP_GROUPING_THRESHOLD's 0.5256


def test_the_grouping_threshold_is_the_embedding_models_own():
    """D-122: a listed model gets its value; any other model, EmbeddingGemma's included, the default."""
    assert gaps.grouping_threshold("voyage-4") == GAP_GROUPING_THRESHOLD_BY_MODEL["voyage-4"]
    assert gaps.grouping_threshold("embed-gemma") == GAP_GROUPING_THRESHOLD
    assert gaps.grouping_threshold(STUB_EMBEDDING_MODEL) == GAP_GROUPING_THRESHOLD


def test_voyage_wordings_between_the_two_values_join_one_entry(designed, employee):
    """D-122: on voyage-4 a second wording at 0.515 joins, because voyage-4's value is 0.5054."""
    second_vector = at_cosine(BETWEEN_THE_TWO_VALUES, axis=20, towards=21)
    # The premise: the cosine sits between the two values, so the model alone decides.
    assert (GAP_GROUPING_THRESHOLD_BY_MODEL["voyage-4"]
            < cosine_similarity(unit(20), second_vector) < GAP_GROUPING_THRESHOLD)
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: second_vector}, model="voyage-4")
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) == gap_of(second)
    assert gap_of(first).occurrence_count == 2


def test_wordings_between_the_two_values_stay_apart_on_an_unlisted_model(designed, employee):
    """D-122: the same pair on a model the map does not list is held to GAP_GROUPING_THRESHOLD."""
    second_vector = at_cosine(BETWEEN_THE_TWO_VALUES, axis=20, towards=21)
    designed({FIRST_WORDING: unit(20), SECOND_WORDING: second_vector})  # STUB_EMBEDDING_MODEL
    first = ask(employee, FIRST_WORDING, at=hours_ago(3))
    second = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(first) != gap_of(second)


def test_an_item_joins_the_nearest_of_two_entries_above_the_threshold(designed, employee):
    """Two entries 1.5 angles apart, so they stay apart, and an item 0.6 of the angle from the first
    and 0.9 from the second: above the threshold against both, and nearer the first."""
    first, second, item = unit(20), at_angle(1.5, axis=20, towards=21), at_angle(0.6, axis=20, towards=21)
    # The premises, so the test cannot pass by the second entry being out of reach.
    assert cosine_similarity(first, second) < GAP_GROUPING_THRESHOLD
    assert cosine_similarity(item, first) > cosine_similarity(item, second) >= GAP_GROUPING_THRESHOLD
    designed({FIRST_WORDING: first, UNRELATED: second, SECOND_WORDING: item})
    a = ask(employee, FIRST_WORDING, at=hours_ago(3))
    b = ask(employee, UNRELATED, at=hours_ago(2))
    c = ask(employee, SECOND_WORDING, at=hours_ago(1))

    run_cycle()

    assert gap_of(a) != gap_of(b)
    assert gap_of(c) == gap_of(a)
    assert gap_of(b).occurrence_count == 1


def test_entries_are_joined_across_cycles_and_the_counts_say_what_moved(designed, employee):
    """``entries_updated`` counts entries that existed before the cycle and gained a member;
    an entry started and joined in one cycle counts once, as created."""
    designed(
        {
            FIRST_WORDING: unit(20),
            SECOND_WORDING: at_angle(0.4, axis=20, towards=21),
            SEARCH_WORDING: at_angle(0.4, axis=20, towards=22),
            UNRELATED: unit(30),
            "Are bicycles allowed in the lift?": at_angle(0.4, axis=30, towards=31),
        }
    )
    a = ask(employee, FIRST_WORDING, at=hours_ago(10))
    first = run_cycle()
    move_cycle_back(first, to=hours_ago(9))
    b = ask(employee, SECOND_WORDING, at=hours_ago(5))
    c = ask(employee, UNRELATED, at=hours_ago(4))
    d = ask(employee, "Are bicycles allowed in the lift?", at=hours_ago(3))
    e = searched(employee, SEARCH_WORDING, at=hours_ago(2))

    second = run_cycle()

    assert gap_of(a) == gap_of(b) == gap_of(e)
    assert gap_of(c) == gap_of(d) != gap_of(a)
    assert (second.queries_considered, second.searches_considered) == (3, 1)
    assert (second.entries_created, second.entries_updated) == (1, 1)
    assert gap_of(a).occurrence_count == 3
    assert gap_of(a).first_seen_at == a.answered_at
    assert gap_of(a).last_seen_at == e.searched_at


def test_every_occurrence_count_equals_its_number_of_items(designed, employee, administrator):
    designed(
        {
            FIRST_WORDING: unit(20),
            SECOND_WORDING: at_angle(0.4, axis=20, towards=21),
            SEARCH_WORDING: at_angle(0.4, axis=20, towards=22),
            UNRELATED: unit(30),
        }
    )
    ask(employee, FIRST_WORDING, at=hours_ago(5))
    ask(administrator, SECOND_WORDING, at=hours_ago(4))
    searched(employee, SEARCH_WORDING, at=hours_ago(3))
    ask(employee, UNRELATED, at=hours_ago(2))
    run_cycle()

    for gap in KnowledgeGap.objects.all():
        assert gap.occurrence_count == gap.items.count()
    assert sum(gap.occurrence_count for gap in KnowledgeGap.objects.all()) == KnowledgeGapItem.objects.count() == 4


# --- The cycle row and the transaction -------------------------------------------------------


def test_the_cycle_row_records_who_triggered_it_and_when(window_vectors, employee, administrator):
    ask(employee, Q_OLD, at=hours_ago(1))
    before = timezone.now()

    by_route = run_cycle(triggered_by=administrator)
    by_command = run_cycle()

    assert by_route.triggered_by == administrator
    assert by_command.triggered_by is None
    assert before <= by_route.started_at <= by_route.finished_at
    assert by_route.started_at <= by_command.started_at
    assert KnowledgeGapCycle.objects.count() == 2


def test_a_provider_outage_rolls_the_whole_cycle_back(designed, employee):
    service = designed({FIRST_WORDING: unit(20), UNRELATED: unit(30)}, down_for={UNRELATED})
    ask(employee, FIRST_WORDING, at=hours_ago(2))  # embedded and grouped before the outage
    ask(employee, UNRELATED, at=hours_ago(1))

    with pytest.raises(ProviderUnavailable):
        run_cycle()

    assert KnowledgeGap.objects.count() == 0
    assert KnowledgeGapItem.objects.count() == 0
    assert KnowledgeGapCycle.objects.count() == 0
    # embed_question's own policy: one initial call and two retries, then out.
    assert service.embed_calls.count([query_text(UNRELATED)]) == MAXIMUM_EMBED_ATTEMPTS


# --- The list's order ------------------------------------------------------------------------


def test_ordered_gaps_puts_open_first_by_count_then_recency_then_addressed(employee):
    def entry(subject, count, status, last_seen_hours_ago):
        at = hours_ago(last_seen_hours_ago)
        return KnowledgeGap.objects.create(
            subject=subject, occurrence_count=count, status=status, first_seen_at=at, last_seen_at=at
        )

    entry("addressed, many", 9, KNOWLEDGE_GAP_ADDRESSED, 1)
    entry("open, two, older", 2, KNOWLEDGE_GAP_OPEN, 5)
    entry("open, five", 5, KNOWLEDGE_GAP_OPEN, 9)
    entry("open, two, newer", 2, KNOWLEDGE_GAP_OPEN, 1)
    entry("addressed, one", 1, KNOWLEDGE_GAP_ADDRESSED, 0.5)

    assert [gap.subject for gap in ordered_gaps()] == [
        "open, five", "open, two, newer", "open, two, older", "addressed, many", "addressed, one",
    ]


# --- The tables' own guarantees (D-107) ------------------------------------------------------


@pytest.fixture
def one_gap():
    now = timezone.now()
    return KnowledgeGap.objects.create(subject="s", occurrence_count=1, first_seen_at=now, last_seen_at=now)


def test_an_entry_starts_open(one_gap):
    assert one_gap.status == KNOWLEDGE_GAP_OPEN


def test_an_item_names_exactly_one_log_row(one_gap, employee):
    question = ask(employee, Q_OLD, at=hours_ago(1))
    search = searched(employee, S_OLD, at=hours_ago(1))
    for arguments in ({}, {"query": question, "search": search}):
        with pytest.raises(IntegrityError), transaction.atomic():
            KnowledgeGapItem.objects.create(gap=one_gap, **arguments)


def test_a_log_row_is_a_member_once(one_gap, employee):
    question = ask(employee, Q_OLD, at=hours_ago(1))
    KnowledgeGapItem.objects.create(gap=one_gap, query=question)
    with pytest.raises(IntegrityError), transaction.atomic():
        KnowledgeGapItem.objects.create(gap=one_gap, query=question)


def test_a_log_row_in_the_log_cannot_be_deleted_out_from_under_its_count(one_gap, employee):
    question = ask(employee, Q_OLD, at=hours_ago(1))
    KnowledgeGapItem.objects.create(gap=one_gap, query=question)
    with pytest.raises(ProtectedError):
        question.delete()


# --- The security review of 10 November 2026, M1: an over-long search term ------------------------


def test_an_over_long_zero_result_search_is_cut_before_it_is_embedded_and_cycles_go_on(
    designed, employee
):
    """Keyword search has no upper bound on a term, so a cycle must never send one whole to the
    embedding model: an error there on one row would roll back every later cycle. The term is cut
    to MAXIMUM_QUESTION_LENGTH for the embedding and the subject; the cycle completes, the search
    is in the log (clause 1), and a second cycle runs after it."""
    from apps.core.constants import MAXIMUM_QUESTION_LENGTH

    long_term = ("volcano insurance " * 2000).strip()  # about 36,000 characters, matching nothing
    cut = long_term[:MAXIMUM_QUESTION_LENGTH]
    service = designed({cut: unit(7), Q_RECENT: unit(8)})
    row = searched(employee, long_term, at=hours_ago(2))

    first = run_cycle()

    assert in_log(row)
    assert gap_of(row).subject == cut
    assert all(len(call[0]) <= len(query_text(cut)) for call in service.embed_calls)
    assert first.searches_considered == 1

    later = ask(employee, Q_RECENT, at=timezone.now())
    second = run_cycle()
    assert second.pk != first.pk
    assert in_log(later)
